"""Local contract tests; actual OCA report execution is a separate CI gate."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


SPEC = importlib.util.spec_from_file_location(
    "golden", Path(__file__).parents[1] / "scripts/ops/verify_finance_golden_ledger.py"
)
golden = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(golden)


class GoldenOracleTests(unittest.TestCase):
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
