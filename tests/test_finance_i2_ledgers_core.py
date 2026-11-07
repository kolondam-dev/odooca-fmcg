"""Fast local oracle and boundary tests for I2a core ledgers."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).parents[1]
RUNNER_SPEC = importlib.util.spec_from_file_location(
    "i2a_runner", ROOT / "scripts/ops/verify_finance_i2_ledgers_core.py",
)
runner = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(runner)

COMPARE_SPEC = importlib.util.spec_from_file_location(
    "ledger_compare", ROOT / "addons/id_finance_reporting/models/ledger_compare.py",
)
compare = importlib.util.module_from_spec(COMPARE_SPEC)
COMPARE_SPEC.loader.exec_module(compare)


class I2aLedgerCoreTests(unittest.TestCase):
    def test_operational_database_refused_before_any_orm_access(self):
        with self.assertRaisesRegex(AssertionError, "exact disposable"):
            runner.run(SimpleNamespace(cr=SimpleNamespace(dbname="railway")))

    def test_control_figures_balance_and_rollforward(self):
        for table in (runner.I2A_JULY, runner.I2A_AUGUST, runner.I2A_JULY_SALE_JOURNAL):
            self.assertEqual(sum(r[1] for r in table.values()), sum(r[2] for r in table.values()))
            self.assertEqual(sum(r[0] for r in table.values()), 0)
            self.assertEqual(sum(r[3] for r in table.values()), 0)
            for opening, debit, credit, closing in table.values():
                self.assertEqual(opening + debit - credit, closing)
        for key in runner.I2A_JULY:
            self.assertEqual(runner.I2A_JULY[key][3], runner.I2A_AUGUST[key][0])

    def test_fin51_combined_trial_balance_and_translation_math(self):
        entities = [
            {
                "company_id": 1,
                "company_name": "Entity A",
                "currency_id": 10,
                "currency_name": "IDR",
                "rate_to_presentation": 1.0,
                "rate_date": "2026-07-31",
                "rows": [
                    {
                        "account_id": 101, "code": "100", "name": "Cash",
                        "account_type": "asset_cash",
                        "initial_balance": 100.0, "debit": 75.0, "credit": 30.0,
                        "balance": 45.0, "ending_balance": 145.0,
                    },
                    {
                        "account_id": 102, "code": "300", "name": "Equity",
                        "account_type": "equity",
                        "initial_balance": -100.0, "debit": 30.0, "credit": 75.0,
                        "balance": -45.0, "ending_balance": -145.0,
                    },
                ],
            },
            {
                "company_id": 2,
                "company_name": "Entity B",
                "currency_id": 20,
                "currency_name": "USD",
                "rate_to_presentation": 2.0,
                "rate_date": "2026-07-31",
                "rows": [
                    {
                        "account_id": 201, "code": "100", "name": "Cash",
                        "account_type": "asset_cash",
                        "initial_balance": 50.0, "debit": 10.0, "credit": 5.0,
                        "balance": 5.0, "ending_balance": 55.0,
                    },
                    {
                        "account_id": 202, "code": "300", "name": "Equity",
                        "account_type": "equity",
                        "initial_balance": -50.0, "debit": 5.0, "credit": 10.0,
                        "balance": -5.0, "ending_balance": -55.0,
                    },
                ],
            },
        ]
        res = compare.combine_trial_balances(entities, lambda x: round(x, 2))
        self.assertEqual(res["scope"], "combined_multi_entity_trial_balance_not_consolidated")
        self.assertFalse(res["eliminations_applied"])
        by_code = {row["code"]: row for row in res["combined_rows"]}
        # Entity A (145) + Entity B (55 * 2 = 110) = 255
        self.assertEqual(by_code["100"]["ending_balance"], 255.0)
        self.assertEqual(by_code["300"]["ending_balance"], -255.0)
        self.assertEqual(res["totals"]["debit"], res["totals"]["credit"])
        self.assertEqual(res["totals"]["ending_balance"], 0.0)
        with self.assertRaisesRegex(ValueError, "at least one entity"):
            compare.combine_trial_balances([], round)
        with self.assertRaisesRegex(ValueError, "positive"):
            compare.combine_trial_balances([{**entities[0], "rate_to_presentation": 0}], round)

    def test_fin57_register_reconciles_to_gl_and_detects_duplicates_or_manual_gl(self):
        docs = [
            {
                "move_id": 10, "move_name": "INV/001", "move_type": "out_invoice",
                "date": "2026-07-01", "partner_id": 5, "state": "posted",
                "lines": [
                    {"line_id": 1, "account_id": 400, "display_type": "product", "balance": -100.0},
                    {"line_id": 2, "account_id": 210, "display_type": "tax", "tax_line_id": 9, "balance": -10.0},
                    {
                        "line_id": 3, "account_id": 110, "display_type": "payment_term",
                        "is_control": True, "balance": 110.0,
                    },
                ],
            },
            {
                "move_id": 11, "move_name": "RINV/001", "move_type": "out_refund",
                "date": "2026-07-20", "partner_id": 5, "state": "posted",
                "lines": [
                    {"line_id": 4, "account_id": 400, "display_type": "product", "balance": 20.0},
                    {"line_id": 5, "account_id": 210, "display_type": "tax", "tax_line_id": 9, "balance": 2.0},
                    {
                        "line_id": 6, "account_id": 110, "display_type": "payment_term",
                        "is_control": True, "balance": -22.0,
                    },
                ],
            },
        ]
        gl_lines = [
            (1, 10, 400, -100.0),
            (2, 10, 210, -10.0),
            (4, 11, 400, 20.0),
            (5, 11, 210, 2.0),
            (99, 50, 400, -15.0),  # Non-register manual journal entry on revenue account 400
        ]
        res = compare.reconcile_register_to_gl(docs, gl_lines, {400, 210}, lambda x: round(x, 2))
        self.assertEqual(res["duplicate_move_ids"], [])
        self.assertEqual(res["duplicate_line_ids"], [])
        self.assertEqual(len(res["non_register_gl_lines"]), 1)
        self.assertEqual(res["non_register_gl_lines"][0]["line_id"], 99)
        tie = {row["account_id"]: row for row in res["gl_tie_out"]}
        self.assertEqual(tie[400]["register_balance"], -80.0)
        self.assertEqual(tie[400]["gl_balance"], -95.0)
        self.assertEqual(tie[400]["non_register_gl_balance"], -15.0)
        self.assertEqual(tie[400]["unexplained_difference"], 0.0)
        self.assertEqual(tie[210]["register_balance"], -8.0)
        self.assertEqual(tie[210]["unexplained_difference"], 0.0)

        # Duplicate document and duplicate line detection
        dup_docs = docs + [docs[0]]
        dup_res = compare.reconcile_register_to_gl(dup_docs, gl_lines, {400, 210}, lambda x: round(x, 2))
        self.assertEqual(dup_res["duplicate_move_ids"], [10])


if __name__ == "__main__":
    unittest.main()
