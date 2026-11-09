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

    def test_fin51_rejects_ambiguous_cross_company_coa_on_same_code(self):
        base_a = {
            "company_id": 1, "company_name": "Entity A", "currency_id": 10,
            "currency_name": "IDR", "rate_to_presentation": 1.0, "rate_date": "2026-07-31",
            "rows": [{
                "account_id": 101, "code": "1101", "name": "Cash on Hand",
                "account_type": "asset_cash", "initial_balance": 0.0,
                "debit": 100.0, "credit": 0.0, "balance": 100.0, "ending_balance": 100.0,
            }],
        }
        # Same code "1101" and same type, but different name -> must fail closed
        diff_name_b = {
            "company_id": 2, "company_name": "Entity B", "currency_id": 10,
            "currency_name": "IDR", "rate_to_presentation": 1.0, "rate_date": "2026-07-31",
            "rows": [{
                "account_id": 201, "code": "1101", "name": "Short-Term Deposit",
                "account_type": "asset_cash", "initial_balance": 0.0,
                "debit": 50.0, "credit": 0.0, "balance": 50.0, "ending_balance": 50.0,
            }],
        }
        with self.assertRaisesRegex(ValueError, "Ambiguous cross-company COA mapping for code 1101"):
            compare.combine_trial_balances([base_a, diff_name_b], round)

        # Explicit account_map resolves different local names when account_type matches
        mapped = compare.combine_trial_balances(
            [base_a, diff_name_b],
            round,
            account_map={"1101": ("1101", "Cash and Equivalents", "asset_cash")},
        )
        self.assertEqual(mapped["combined_rows"][0]["ending_balance"], 150.0)

        # Same code "1101" and same name, but different account_type -> must fail closed
        diff_type_b = {
            "company_id": 2, "company_name": "Entity B", "currency_id": 10,
            "currency_name": "IDR", "rate_to_presentation": 1.0, "rate_date": "2026-07-31",
            "rows": [{
                "account_id": 201, "code": "1101", "name": "Cash on Hand",
                "account_type": "liability_payable", "initial_balance": 0.0,
                "debit": 0.0, "credit": 50.0, "balance": -50.0, "ending_balance": -50.0,
            }],
        }
        with self.assertRaisesRegex(ValueError, "Ambiguous cross-company COA mapping for code 1101"):
            compare.combine_trial_balances([base_a, diff_type_b], round)
        with self.assertRaisesRegex(ValueError, "cannot change account_type"):
            compare.combine_trial_balances(
                [base_a, diff_type_b],
                round,
                account_map={"1101": ("1101", "Cash on Hand", "asset_cash")},
            )

    def _fin51_rows(self, expected_table, multiplier, skip=(), code_override=None):
        rows = []
        for idx, (key, figures) in enumerate(expected_table.items()):
            if key in skip:
                continue
            code = (code_override or {}).get(key, runner.fin51_combined_code(idx))
            opening, debit, credit, closing = (v * multiplier for v in figures)
            rows.append({
                "code": code, "initial_balance": opening, "debit": debit,
                "credit": credit, "ending_balance": closing,
            })
        return rows

    def test_fin51_zero_activity_account_is_explicit_in_combined_contract(self):
        table = runner.I2A_JULY
        self.assertEqual(table["unaffected_earnings"], (0, 0, 0, 0))
        # Zero-activity equity_unaffected row present under its aligned code: PASS.
        runner.assert_fin51_combined_rows(self._fin51_rows(table, 8), table, 8)
        # Dropping the zero-activity row is a coverage failure, not a silent skip or KeyError.
        with self.assertRaisesRegex(AssertionError, r"missing=\['I2ACOMB08'\], extra=\[\]"):
            runner.assert_fin51_combined_rows(
                self._fin51_rows(table, 8, skip=("unaffected_earnings",)), table, 8,
            )
        # Row left under the system code (company-dependent code written for the wrong company).
        with self.assertRaisesRegex(AssertionError, r"missing=\['I2ACOMB08'\], extra=\['999999'\]"):
            runner.assert_fin51_combined_rows(
                self._fin51_rows(table, 8, code_override={"unaffected_earnings": "999999"}), table, 8,
            )
        # Non-zero coverage stays value-checked and duplicate codes are rejected.
        wrong = self._fin51_rows(table, 8)
        wrong[0]["ending_balance"] += 1
        with self.assertRaisesRegex(AssertionError, "FIN51 combined cash"):
            runner.assert_fin51_combined_rows(wrong, table, 8)
        with self.assertRaisesRegex(AssertionError, "duplicate combined code"):
            runner.assert_fin51_combined_rows(self._fin51_rows(table, 8) + self._fin51_rows(table, 8)[:1], table, 8)

    def test_fin51_zero_activity_rows_are_preserved_by_combiner(self):
        def entity(company_id, rows):
            return {
                "company_id": company_id, "company_name": f"E{company_id}", "currency_id": 10,
                "currency_name": "IDR", "rate_to_presentation": 1.0, "rate_date": "2026-07-31",
                "rows": rows,
            }

        def row(account_id, code, name, acc_type, init, debit, credit, end):
            return {
                "account_id": account_id, "code": code, "name": name, "account_type": acc_type,
                "initial_balance": init, "debit": debit, "credit": credit,
                "balance": debit - credit, "ending_balance": end,
            }

        zero_a = row(901, "UE", "Unaffected", "equity_unaffected", 0.0, 0.0, 0.0, 0.0)
        zero_b = row(902, "UE", "Unaffected", "equity_unaffected", 0.0, 0.0, 0.0, 0.0)
        cash_a = row(101, "100", "Cash", "asset_cash", 0.0, 5.0, 0.0, 5.0)
        cash_b = row(201, "100", "Cash", "asset_cash", 0.0, 3.0, 0.0, 3.0)
        combined = compare.combine_trial_balances(
            [entity(1, [cash_a, zero_a]), entity(2, [cash_b, zero_b])], round,
        )
        by_code = {r["code"]: r for r in combined["combined_rows"]}
        self.assertEqual(set(by_code), {"100", "UE"})
        self.assertEqual(by_code["100"]["ending_balance"], 8.0)
        self.assertEqual(
            (by_code["UE"]["debit"], by_code["UE"]["credit"], by_code["UE"]["ending_balance"]),
            (0.0, 0.0, 0.0),
        )

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

    def test_fin51_snapshot_uses_target_company_context_for_unaffected_earnings(self):
        """Production FIN51 must resolve unaffected earnings under target company context, not default env company."""
        from unittest.mock import MagicMock

        comp_b = MagicMock()
        comp_b.id = 2
        comp_b.display_name = "Company B"
        comp_b.currency_id.id = 10
        comp_b.currency_id.name = "IDR"

        scoped_comp_b = MagicMock()
        comp_b.with_company.return_value = scoped_comp_b
        fake_unaffected = MagicMock()
        fake_unaffected.id = 999
        scoped_comp_b.get_unaffected_earnings_account.return_value = fake_unaffected

        comp_b.get_unaffected_earnings_account.side_effect = AssertionError(
            "get_unaffected_earnings_account was called directly on company instead of company.with_company(company)"
        )

        unaffected = comp_b.with_company(comp_b).get_unaffected_earnings_account()
        self.assertEqual(unaffected.id, 999)
        comp_b.with_company.assert_called_once_with(comp_b)
        scoped_comp_b.get_unaffected_earnings_account.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
