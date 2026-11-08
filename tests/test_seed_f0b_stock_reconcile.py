import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ops"))
import seed_f0b_stock_reconcile_live as f0b  # noqa: E402


def _canon_rows(canon, carton, reserved_cartons=0):
    return [
        (s, lot, (q + reserved_cartons) * carton[s], reserved_cartons * carton[s])
        for (s, lot), q in canon.items()
    ]


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
        r = f0b.compare(_canon_rows(self.canon, self.carton), self.canon, self.carton)
        self.assertEqual(r["reconciliation_basis"], "available_vs_available")
        self.assertEqual(r["lot_diffs_count"], 0)
        self.assertEqual(r["live_available_total_cartons"], "52799")
        self.assertFalse(r["hypothesis_100x150_proven"])

    def test_non_zero_reservations_reconcile_without_false_positive_diff(self):
        # Physical stock is higher by 5 cartons per lot, but 5 cartons per lot are reserved:
        # available stock (physical - reserved) equals canonical available (52,799 cartons).
        rows = _canon_rows(self.canon, self.carton, reserved_cartons=5)
        r = f0b.compare(rows, self.canon, self.carton)
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
        sku0, lot0, phys0, _resv0 = rows[0]
        rows[0] = (sku0, lot0, phys0, 10 * self.carton[sku0])
        r = f0b.compare(rows, self.canon, self.carton)
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
        rows += [(s, None, 100 * c, 0) for s, c in self.carton.items()]
        r = f0b.compare(rows, self.canon, self.carton)
        self.assertTrue(r["hypothesis_100x150_proven"])
        self.assertEqual(r["per_sku_diff_total"], "15000")

    def test_100_in_existing_lots_counts_as_per_sku(self):
        rows = _canon_rows(self.canon, self.carton)
        first = {}
        for i, (s, _lot, _phys, _resv) in enumerate(rows):
            first.setdefault(s, i)
        for s, i in first.items():
            sku_i, lot_i, phys_i, resv_i = rows[i]
            rows[i] = (sku_i, lot_i, phys_i + 100 * self.carton[s], resv_i)
        r = f0b.compare(rows, self.canon, self.carton)
        self.assertTrue(r["hypothesis_100x150_proven"])

    def test_partial_or_uneven_is_not_proven(self):
        rows = _canon_rows(self.canon, self.carton)
        s = next(iter(self.carton))
        rows.append((s, None, 99 * self.carton[s], 0))
        r = f0b.compare(rows, self.canon, self.carton)
        self.assertFalse(r["hypothesis_100x150_proven"])


if __name__ == "__main__":
    unittest.main()
