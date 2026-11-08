from decimal import Decimal
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ops"))
import seed_f0b_stock_reconcile_live as f0b  # noqa: E402


COMPANY = 7  # explicit reconciliation scope used by these tests
OTHER_COMPANY = 9


def _canon_rows(canon, carton, reserved_cartons=0, company_id=COMPANY):
    return [
        (company_id, s, lot, (q + reserved_cartons) * carton[s], reserved_cartons * carton[s])
        for (s, lot), q in canon.items()
    ]


def _compare(rows, canon, carton, company_id=COMPANY):
    return f0b.compare(rows, canon, carton, company_id)


class F0bTests(unittest.TestCase):
    def setUp(self):
        if not f0b.STATE.is_file():
            self.fail(
                f"Required tracked canonical state fixture is missing: {f0b.STATE}. "
                "Ensure data/registers/state_20260801.json is present in the checkout."
            )
        state = f0b.load_canonical_state(f0b.STATE)
        self.canon = f0b.canonical_available(state)
        self.carton = f0b.carton_sizes()

    def test_missing_state_fixture_fails_with_clear_message(self):
        missing = f0b.ROOT / "data" / "registers" / "nonexistent_state_fixture.json"
        with self.assertRaisesRegex(FileNotFoundError, "Required canonical state fixture"):
            f0b.load_canonical_state(missing)

    def test_canonical_total_matches_state(self):
        self.assertEqual(sum(self.canon.values()), 52799)
        self.assertEqual(len(self.canon), 236)

    def test_identical_live_has_no_diff(self):
        r = _compare(_canon_rows(self.canon, self.carton), self.canon, self.carton)
        self.assertEqual(r["reconciliation_basis"], "available_vs_available")
        self.assertEqual(r["lot_diffs_count"], 0)
        self.assertEqual(r["live_available_total_cartons"], "52799")
        self.assertFalse(r["hypothesis_100x150_proven"])

    def test_non_zero_reservations_reconcile_without_false_positive_diff(self):
        # Physical stock is higher by 5 cartons per lot, but 5 cartons per lot are reserved:
        # available stock (physical - reserved) equals canonical available (52,799 cartons).
        rows = _canon_rows(self.canon, self.carton, reserved_cartons=5)
        r = _compare(rows, self.canon, self.carton)
        self.assertEqual(r["lot_diffs_count"], 0)
        self.assertEqual(r["live_physical_total_cartons"], str(52799 + 5 * 236))
        self.assertEqual(r["live_reserved_total_cartons"], str(5 * 236))
        self.assertEqual(r["live_available_total_cartons"], "52799")
        self.assertEqual(r["per_sku_diff_total"], "0")
        self.assertFalse(r["hypothesis_100x150_proven"])

    def test_constant_physical_with_varying_reservation_changes_available_diff(self):
        # Hold physical stock constant while adding a 10-carton reservation on one lot:
        # available stock drops by 10 cartons and must be reported as a -10 carton diff.
        rows = _canon_rows(self.canon, self.carton, reserved_cartons=0)
        co0, sku0, lot0, phys0, _resv0 = rows[0]
        rows[0] = (co0, sku0, lot0, phys0, 10 * self.carton[sku0])
        r = _compare(rows, self.canon, self.carton)
        self.assertEqual(r["live_physical_total_cartons"], "52799")
        self.assertEqual(r["live_reserved_total_cartons"], "10")
        self.assertEqual(r["live_available_total_cartons"], "52789")
        self.assertEqual(r["lot_diffs_count"], 1)
        self.assertEqual(r["per_sku_diff_cartons"][sku0], "-10")
        self.assertEqual(r["per_sku_diff_total"], "-10")
        self.assertFalse(r["hypothesis_100x150_proven"])
        # Verify production SQL selects both sq.quantity and sq.reserved_quantity
        self.assertIn("SUM(sq.quantity)", f0b.LIVE_STOCK_SQL)
        self.assertIn("SUM(sq.reserved_quantity)", f0b.LIVE_STOCK_SQL)

    def test_lotless_100_per_sku_proves_hypothesis(self):
        rows = _canon_rows(self.canon, self.carton)
        rows += [(COMPANY, s, None, 100 * c, 0) for s, c in self.carton.items()]
        r = _compare(rows, self.canon, self.carton)
        self.assertTrue(r["hypothesis_100x150_proven"])
        self.assertEqual(r["per_sku_diff_total"], "15000")

    def test_100_in_existing_lots_counts_as_per_sku(self):
        rows = _canon_rows(self.canon, self.carton)
        first = {}
        for i, (_co, s, _lot, _phys, _resv) in enumerate(rows):
            first.setdefault(s, i)
        for s, i in first.items():
            co_i, sku_i, lot_i, phys_i, resv_i = rows[i]
            rows[i] = (co_i, sku_i, lot_i, phys_i + 100 * self.carton[s], resv_i)
        r = _compare(rows, self.canon, self.carton)
        self.assertTrue(r["hypothesis_100x150_proven"])

    def test_partial_or_uneven_is_not_proven(self):
        rows = _canon_rows(self.canon, self.carton)
        s = next(iter(self.carton))
        rows.append((COMPANY, s, None, 99 * self.carton[s], 0))
        r = _compare(rows, self.canon, self.carton)
        self.assertFalse(r["hypothesis_100x150_proven"])

    def test_other_active_company_rows_are_rejected_not_summed(self):
        # Same SKU/lot held by a second active company must never be added to the scoped result.
        rows = _canon_rows(self.canon, self.carton)
        co, sku, lot, phys, resv = rows[0]
        contaminated = rows + [(OTHER_COMPANY, sku, lot, 100 * self.carton[sku], 0)]
        with self.assertRaisesRegex(ValueError, "outside the reconciliation scope"):
            _compare(contaminated, self.canon, self.carton)
        # The scoped rows alone reconcile cleanly, so the rejection is the only guard needed.
        self.assertEqual(_compare(rows, self.canon, self.carton)["lot_diffs_count"], 0)
        # Rows without a company id cannot be scoped and are refused too.
        with self.assertRaisesRegex(ValueError, "5-tuple"):
            _compare([(sku, lot, phys, resv)], self.canon, self.carton)

    def test_live_sql_is_company_scoped_against_real_query_text(self):
        # Execute the production SQL text on a minimal schema holding two active companies.
        db = sqlite3.connect(":memory:")
        db.executescript(
            """
            CREATE TABLE res_company (id INTEGER PRIMARY KEY, name TEXT, active BOOLEAN);
            CREATE TABLE product_template (id INTEGER PRIMARY KEY, default_code TEXT);
            CREATE TABLE product_product (id INTEGER PRIMARY KEY, product_tmpl_id INTEGER, active BOOLEAN);
            CREATE TABLE stock_location (id INTEGER PRIMARY KEY, complete_name TEXT, usage TEXT);
            CREATE TABLE stock_lot (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE stock_quant (
                id INTEGER PRIMARY KEY, company_id INTEGER, product_id INTEGER, location_id INTEGER,
                lot_id INTEGER, quantity REAL, reserved_quantity REAL
            );
            INSERT INTO res_company VALUES (7, 'PT Salva Inti Mandiri', 1), (9, 'Other Active Co', 1);
            INSERT INTO product_template VALUES (1, 'SKU-A');
            INSERT INTO product_product VALUES (1, 1, 1);
            INSERT INTO stock_location VALUES (1, 'WH/Stock', 'internal'), (2, 'WH/Stock', 'internal');
            INSERT INTO stock_lot VALUES (1, 'LOT-1');
            INSERT INTO stock_quant VALUES (1, 7, 1, 1, 1, 240, 24), (2, 9, 1, 2, 1, 14400, 0);
            """
        )
        sql = f0b.LIVE_STOCK_SQL.replace("%(company_id)s", ":company_id")
        scoped = db.execute(sql, {"company_id": 7}).fetchall()
        self.assertEqual(scoped, [(7, "SKU-A", "LOT-1", 240.0, 24.0)])
        other = db.execute(sql, {"company_id": 9}).fetchall()
        self.assertEqual(other, [(9, "SKU-A", "LOT-1", 14400.0, 0.0)])
        # Every returned row carries the scope, so compare() accepts only the selected company.
        carton = {"SKU-A": 24}
        res = f0b.compare(scoped, {("SKU-A", "LOT-1"): 9}, carton, 7)
        self.assertEqual(res["company_id"], 7)
        self.assertEqual(Decimal(res["live_available_total_cartons"]), 9)
        self.assertEqual(res["lot_diffs_count"], 0)
        with self.assertRaisesRegex(ValueError, "outside the reconciliation scope"):
            f0b.compare(scoped + other, {("SKU-A", "LOT-1"): 9}, carton, 7)

    def test_company_validation_is_fail_closed(self):
        name = f0b.CANONICAL_COMPANY_NAME
        self.assertEqual(f0b.check_company_row((7, name, True), 7), name)
        with self.assertRaisesRegex(ValueError, "does not exist"):
            f0b.check_company_row(None, 7)
        with self.assertRaisesRegex(ValueError, "inactive"):
            f0b.check_company_row((7, name, False), 7)
        with self.assertRaisesRegex(ValueError, "canonical state represents"):
            f0b.check_company_row((9, "Other Active Co", True), 9)
        with self.assertRaisesRegex(ValueError, "returned id"):
            f0b.check_company_row((8, name, True), 7)
        # No default scope: the CLI must be given an explicit company id.
        self.assertIn("sq.company_id = %(company_id)s", f0b.LIVE_STOCK_SQL)


if __name__ == "__main__":
    unittest.main()
