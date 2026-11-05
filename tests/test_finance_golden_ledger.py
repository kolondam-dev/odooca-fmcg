"""Local contract tests; actual OCA report execution is a separate CI gate."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from datetime import date


SPEC = importlib.util.spec_from_file_location(
    "golden", Path(__file__).parents[1] / "scripts/ops/verify_finance_golden_ledger.py"
)
golden = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(golden)
EXTENDED_SPEC = importlib.util.spec_from_file_location(
    "ledger_security", Path(__file__).parents[1] / "scripts/ops/verify_finance_ledger_security.py"
)
extended = importlib.util.module_from_spec(EXTENDED_SPEC)
EXTENDED_SPEC.loader.exec_module(extended)


class GoldenOracleTests(unittest.TestCase):
    def test_extended_native_controls_and_period_rollforward(self):
        for figures in (extended.NATIVE_JULY, extended.NATIVE_AUGUST):
            self.assertEqual(sum(row[1] for row in figures.values()), sum(row[2] for row in figures.values()))
            self.assertEqual(sum(row[0] for row in figures.values()), 0)
            self.assertEqual(sum(row[3] for row in figures.values()), 0)
            for opening, debit, credit, closing in figures.values():
                self.assertEqual(opening + debit - credit, closing)
        for key in extended.NATIVE_JULY:
            self.assertEqual(extended.NATIVE_JULY[key][3], extended.NATIVE_AUGUST[key][0])

    def test_dated_partial_oracle_excludes_future_settlement(self):
        class Line:
            balance = 100
            matched_debit_ids = []
            matched_credit_ids = [
                SimpleNamespace(amount=60, max_date=date(2026, 7, 15)),
                SimpleNamespace(amount=20, max_date=date(2026, 7, 20)),
                SimpleNamespace(amount=20, max_date=date(2026, 8, 1)),
            ]

            def __len__(self):
                return 1

        self.assertEqual(extended.residual_as_of(Line(), date(2026, 7, 31)), 20)
        self.assertEqual(extended.residual_as_of(Line(), date(2026, 8, 31)), 0)

    def test_extended_runner_refuses_operational_database_before_access(self):
        with self.assertRaisesRegex(AssertionError, "exact disposable"):
            extended.run(SimpleNamespace(cr=SimpleNamespace(dbname="railway")))

    def test_control_figures_balance_and_period_rollforward(self):
        for figures in (golden.JULY, golden.AUGUST):
            self.assertEqual(sum(row[1] for row in figures.values()), sum(row[2] for row in figures.values()))
            self.assertEqual(sum(row[0] for row in figures.values()), 0)
            self.assertEqual(sum(row[3] for row in figures.values()), 0)
            for opening, debit, credit, closing in figures.values():
                self.assertEqual(opening + debit - credit, closing)
        for key in golden.JULY:
            self.assertEqual(golden.JULY[key][3], golden.AUGUST[key][0])

    def test_missing_extra_wrong_value_rejected(self):
        accounts = {name: SimpleNamespace(id=i) for i, name in enumerate(golden.JULY, 1)}
        actual = {
            accounts[name].id: dict(zip(("initial_balance", "debit", "credit", "ending_balance"), row))
            for name, row in golden.JULY.items()
        }
        golden.assert_figures(actual, golden.JULY, accounts)
        with self.assertRaisesRegex(AssertionError, "coverage mismatch"):
            golden.assert_figures({**actual, 999: {}}, golden.JULY, accounts)
        with self.assertRaisesRegex(AssertionError, "coverage mismatch"):
            golden.assert_figures({}, golden.JULY, accounts)
        actual[accounts["cash"].id]["ending_balance"] += 1
        with self.assertRaisesRegex(AssertionError, "Golden ledger cash"):
            golden.assert_figures(actual, golden.JULY, accounts)

    def test_operational_database_refused_before_any_orm_access(self):
        with self.assertRaisesRegex(RuntimeError, "exact disposable"):
            golden.run(SimpleNamespace(cr=SimpleNamespace(dbname="railway")))


if __name__ == "__main__":
    unittest.main()
