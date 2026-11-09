"""Fast local oracle and boundary tests for I2b AR/AP subledgers."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).parents[1]
SUB_SPEC = importlib.util.spec_from_file_location(
    "ledger_subledger", ROOT / "addons/id_finance_reporting/models/ledger_subledger.py",
)
sub = importlib.util.module_from_spec(SUB_SPEC)
SUB_SPEC.loader.exec_module(sub)

RUNNER_SPEC = importlib.util.spec_from_file_location(
    "i2b_runner", ROOT / "scripts/ops/verify_finance_i2_arap_subledger.py",
)
runner = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(runner)


def line(line_id, account_type, date, debit=0.0, credit=0.0, partner_id=5,  # noqa: PLR0913
         due_date=None, move_id=None):
    balance = debit - credit
    return {
        "line_id": line_id,
        "move_id": move_id or line_id,
        "move_name": f"MOVE-{line_id}",
        "date": date,
        "due_date": due_date or date,
        "partner_id": partner_id,
        "partner_name": "Named Partner" if partner_id else "Missing Partner",
        "account_id": 110 if account_type == sub.AR_TYPE else 210,
        "account_code": "1101" if account_type == sub.AR_TYPE else "2101",
        "account_type": account_type,
        "debit": debit,
        "credit": credit,
        "balance": balance,
        "currency_id": 1,
        "amount_currency": balance,
    }


def partial(partial_id, debit_line_id, credit_line_id, amount, max_date):
    return {
        "partial_id": partial_id,
        "debit_line_id": debit_line_id,
        "credit_line_id": credit_line_id,
        "amount": amount,
        "max_date": max_date,
    }


class I2bSubledgerHelperTests(unittest.TestCase):
    def test_partner_ledger_separates_ar_ap_and_partnerless(self):
        lines = [
            line(1, sub.AR_TYPE, "2026-06-30", debit=40.0),
            line(2, sub.AR_TYPE, "2026-07-01", debit=110.0),
            line(3, sub.AR_TYPE, "2026-07-15", credit=82.0),
            line(4, sub.AP_TYPE, "2026-07-02", credit=88.0),
            line(5, sub.AP_TYPE, "2026-07-16", debit=41.0),
            line(6, sub.AP_TYPE, "2026-07-25", credit=12.0, partner_id=0),
            line(7, sub.AP_TYPE, "2026-07-26", debit=12.0, partner_id=0),
        ]
        result = sub.build_partner_ledger(
            lines, "2026-07-01", "2026-07-31", lambda value: round(value, 2),
        )
        rows = {(row["partner_id"], row["account_type"]): row for row in result["rows"]}
        self.assertEqual(set(rows), {(5, sub.AR_TYPE), (5, sub.AP_TYPE), (0, sub.AP_TYPE)})
        ar = rows[(5, sub.AR_TYPE)]
        self.assertEqual(
            (ar["opening_balance"], ar["debit"], ar["credit"], ar["closing_balance"]),
            (40.0, 110.0, 82.0, 68.0),
        )
        ap = rows[(5, sub.AP_TYPE)]
        self.assertEqual(
            (ap["opening_balance"], ap["debit"], ap["credit"], ap["closing_balance"]),
            (0.0, 41.0, 88.0, -47.0),
        )
        partnerless = rows[(0, sub.AP_TYPE)]
        self.assertTrue(partnerless["partnerless"])
        self.assertEqual(
            (partnerless["debit"], partnerless["credit"], partnerless["closing_balance"]),
            (12.0, 12.0, 0.0),
        )
        self.assertEqual(result["totals"]["opening_balance"], 40.0)
        self.assertEqual(result["totals"]["debit"], 163.0)
        self.assertEqual(result["totals"]["credit"], 182.0)
        self.assertEqual(result["totals"]["closing_balance"], 21.0)
        self.assertEqual(result["totals"]["partner_count"], 2)
        self.assertEqual(result["by_account_type"][sub.AR_TYPE]["closing_balance"], 68.0)
        self.assertEqual(result["by_account_type"][sub.AP_TYPE]["closing_balance"], -47.0)

    def test_partner_ledger_rejects_unordered_period(self):
        with self.assertRaisesRegex(ValueError, "ordered period"):
            sub.build_partner_ledger(
                [], "2026-08-01", "2026-07-01", lambda value: round(value, 2),
            )

    def test_open_items_use_dated_partials_not_current_residual(self):
        lines = [
            line(1, sub.AR_TYPE, "2026-07-01", debit=110.0, due_date="2026-07-01"),
            line(2, sub.AR_TYPE, "2026-07-15", credit=60.0),
            line(3, sub.AR_TYPE, "2026-07-20", credit=22.0),
            line(4, sub.AR_TYPE, "2026-08-01", credit=28.0),
        ]
        partials = [
            partial(101, 1, 2, 60.0, "2026-07-15"),
            partial(102, 1, 3, 22.0, "2026-07-20"),
            partial(103, 1, 4, 28.0, "2026-08-01"),
        ]
        before_receipt = sub.reconstruct_open_items(
            lines, partials, "2026-07-14", lambda value: round(value, 2),
        )
        self.assertEqual(before_receipt["total_residual"], 110.0)
        self.assertEqual([row["line_id"] for row in before_receipt["rows"]], [1])
        self.assertEqual(before_receipt["rows"][0]["matched_amount"], 0.0)

        at_july_end = sub.reconstruct_open_items(
            lines, partials, "2026-07-31", lambda value: round(value, 2),
        )
        self.assertEqual(at_july_end["total_residual"], 28.0)
        self.assertEqual([row["line_id"] for row in at_july_end["rows"]], [1])
        self.assertEqual(at_july_end["rows"][0]["matched_amount"], -82.0)
        self.assertEqual(sorted(at_july_end["closed_line_ids"]), [2, 3])

        after_settlement = sub.reconstruct_open_items(
            lines, partials, "2026-08-31", lambda value: round(value, 2),
        )
        self.assertEqual(after_settlement["rows"], [])
        self.assertEqual(after_settlement["total_residual"], 0.0)
        self.assertEqual(sorted(after_settlement["closed_line_ids"]), [1, 2, 3, 4])

    def test_open_items_preserve_payable_sign_and_partnerless(self):
        lines = [
            line(1, sub.AP_TYPE, "2026-07-02", credit=88.0, due_date="2026-07-02"),
            line(2, sub.AP_TYPE, "2026-07-16", debit=30.0),
            line(3, sub.AP_TYPE, "2026-07-21", debit=11.0),
            line(4, sub.AP_TYPE, "2026-07-25", credit=12.0, partner_id=0),
        ]
        partials = [
            partial(101, 2, 1, 30.0, "2026-07-16"),
            partial(102, 3, 1, 11.0, "2026-07-21"),
        ]
        result = sub.reconstruct_open_items(
            lines, partials, "2026-07-31", lambda value: round(value, 2),
        )
        rows = {row["line_id"]: row for row in result["rows"]}
        self.assertEqual(rows[1]["residual"], -47.0)
        self.assertEqual(rows[4]["residual"], -12.0)
        self.assertTrue(rows[4]["partnerless"])
        self.assertEqual(result["total_residual"], -59.0)
        self.assertEqual(result["partnerless_residual"], -12.0)
        self.assertEqual(result["partnerless_line_ids"], [4])
        aging = sub.build_aging(result, "2026-07-31", lambda value: round(value, 2))
        self.assertEqual(aging["buckets"]["days_1_30"], -59.0)
        self.assertEqual(aging["total_residual"], -59.0)
        self.assertEqual(aging["bucket_sum"], -59.0)
        self.assertEqual(aging["unexplained_difference"], 0.0)
        self.assertTrue(aging["balanced"])

    def test_aging_bucket_boundaries_are_stable(self):
        cases = {
            ("2026-07-01", "current"),
            ("2026-06-30", "days_1_30"),
            ("2026-06-01", "days_1_30"),
            ("2026-05-31", "days_31_60"),
            ("2026-05-02", "days_31_60"),
            ("2026-05-01", "days_61_90"),
            ("2026-04-02", "days_61_90"),
            ("2026-04-01", "days_91_120"),
            ("2026-03-03", "days_91_120"),
            ("2026-03-02", "older"),
            (None, "current"),
        }
        for due, expected in cases:
            with self.subTest(due=due):
                self.assertEqual(
                    sub.bucket_for_due_date(due, "2026-07-01"), expected,
                )

    def test_aging_sum_must_equal_open_items_total(self):
        rows = [
            {**line(1, sub.AR_TYPE, "2026-07-01", debit=50.0), "residual": 50.0},
            {**line(2, sub.AR_TYPE, "2026-06-01", debit=25.0), "residual": 25.0},
            {**line(3, sub.AR_TYPE, "2026-03-01", debit=-10.0), "residual": -10.0},
        ]
        result = sub.build_aging(
            {"rows": rows, "total_residual": 65.0}, "2026-07-01",
            lambda value: round(value, 2),
        )
        self.assertEqual(result["buckets"]["current"], 50.0)
        self.assertEqual(result["buckets"]["days_1_30"], 25.0)
        self.assertEqual(result["buckets"]["older"], -10.0)
        self.assertEqual(result["bucket_sum"], 65.0)
        self.assertTrue(result["balanced"])

    def test_invalid_partner_type_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Invalid partner type"):
            sub.resolve_partner_types("employee")

    def test_open_items_ignore_partials_with_counterpart_outside_slice(self):
        # Invoice 110 in the sale journal, receipt 60 in the cash journal.
        # A journal-only slice keeps the invoice partly open: the receipt's
        # partial must not settle it because its credit leg is out of scope.
        invoice = line(1, sub.AR_TYPE, "2026-07-01", debit=110.0, due_date="2026-07-01")
        receipt = line(2, sub.AR_TYPE, "2026-07-15", credit=60.0)
        partials = [partial(101, 1, 2, 60.0, "2026-07-15")]
        round_amount = lambda value: round(value, 2)  # noqa: E731

        journal_slice = sub.reconstruct_open_items(
            [invoice], partials, "2026-07-31", round_amount,
        )
        self.assertEqual(journal_slice["total_residual"], 110.0)
        self.assertEqual(journal_slice["rows"][0]["residual"], 110.0)
        self.assertEqual(journal_slice["rows"][0]["matched_amount"], 0.0)
        self.assertEqual(journal_slice["rows"][0]["matched_partial_ids"], [])
        self.assertEqual(journal_slice["closed_line_ids"], [])
        self.assertEqual(
            journal_slice["total_residual"],
            round_amount(sum(row["balance"] for row in [invoice])),
        )

        date_slice = sub.reconstruct_open_items(
            [receipt], partials, "2026-07-31", round_amount,
        )
        self.assertEqual(date_slice["total_residual"], -60.0)
        self.assertEqual(date_slice["rows"][0]["matched_amount"], 0.0)

        full_slice = sub.reconstruct_open_items(
            [invoice, receipt], partials, "2026-07-31", round_amount,
        )
        self.assertEqual(full_slice["total_residual"], 50.0)
        self.assertEqual(full_slice["rows"][0]["matched_amount"], -60.0)
        self.assertEqual(full_slice["closed_line_ids"], [2])

    def test_open_items_slice_invariant_holds_for_every_scope(self):
        # The rule "both legs selected" is what makes the residual total equal
        # the summed balance of the slice, which is exactly what the GL control
        # total compares against. Assert it for journal, date and partner slices.
        named = [
            line(1, sub.AR_TYPE, "2026-07-01", debit=110.0, due_date="2026-07-01"),
            line(2, sub.AR_TYPE, "2026-07-15", credit=60.0),
            line(3, sub.AR_TYPE, "2026-07-20", credit=22.0),
        ]
        partnerless = [line(4, sub.AP_TYPE, "2026-07-25", credit=12.0, partner_id=0)]
        all_lines = named + partnerless
        partials = [
            partial(101, 1, 2, 60.0, "2026-07-15"),
            partial(102, 1, 3, 22.0, "2026-07-20"),
        ]
        round_amount = lambda value: round(value, 2)  # noqa: E731

        slices = {
            "journal_sale": [line for line in named if line["line_id"] in (1, 3)],
            "date_from_0710": [line for line in named if line["line_id"] in (2, 3)],
            "partner_named": named,
            "partner_named_plus_ap_partnerless": all_lines,
        }
        for label, slice_lines in slices.items():
            with self.subTest(slice=label):
                result = sub.reconstruct_open_items(
                    slice_lines, partials, "2026-07-31", round_amount,
                )
                self.assertEqual(
                    result["total_residual"],
                    round_amount(sum(line["balance"] for line in slice_lines)),
                    f"{label} residual must equal the slice balance",
                )

        partner_only = sub.reconstruct_open_items(
            named, partials, "2026-07-31", round_amount,
        )
        self.assertEqual(partner_only["partnerless_residual"], 0.0)
        self.assertEqual(partner_only["partnerless_line_ids"], [])
        self.assertEqual(partner_only["total_residual"], 28.0)

        with_partnerless = sub.reconstruct_open_items(
            all_lines, partials, "2026-07-31", round_amount,
        )
        self.assertEqual(with_partnerless["partnerless_residual"], -12.0)
        self.assertEqual(with_partnerless["partnerless_line_ids"], [4])

    def test_tie_out_reports_difference(self):
        tied = sub.tie_subledger_to_gl(28.0, 28.0, lambda value: round(value, 2))
        self.assertTrue(tied["balanced"])
        self.assertEqual(tied["issues"], [])
        broken = sub.tie_subledger_to_gl(
            28.0, 30.0, lambda value: round(value, 2), label="open_items",
        )
        self.assertFalse(broken["balanced"])
        self.assertEqual(broken["difference"], -2.0)
        self.assertEqual(broken["issues"], ["open_items_mismatch"])

    def test_oca_aged_rows_are_matched_by_account_id(self):
        oracle = {
            "rows": {
                1: {
                    "line_id": 1,
                    "account_id": 161,
                    "partner_id": 5,
                    "partner_name": "Named Partner",
                    "account_type": sub.AR_TYPE,
                    "due_date": "2026-06-01",
                    "residual": 28.0,
                },
            },
            "total_residual": 28.0,
        }
        buckets = {
            "current": 0.0, "30_days": 28.0, "60_days": 0.0,
            "90_days": 0.0, "120_days": 0.0, "older": 0.0,
        }
        values = {
            "aged_partner_balance": [{
                "id": 161,
                "residual": 28.0,
                **buckets,
                "partners": [{
                    "name": "Named Partner",
                    "residual": 28.0,
                    **buckets,
                }],
            }],
        }
        runner.assert_oca_aged_partner_balance(values, oracle, "2026-07-01")

    def test_runner_refuses_operational_database_before_orm_access(self):
        with self.assertRaisesRegex(AssertionError, "exact disposable"):
            runner.run(SimpleNamespace(cr=SimpleNamespace(dbname="railway")))


if __name__ == "__main__":
    unittest.main()
