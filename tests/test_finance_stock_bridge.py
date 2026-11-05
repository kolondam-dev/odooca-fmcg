"""Fast oracle tests, not a substitute for native CI fixtures."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

SPEC = importlib.util.spec_from_file_location(
    "stock_bridge", Path(__file__).parents[1] / "scripts/ops/verify_finance_stock_bridge.py",
)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class StockBridgeOracleTests(unittest.TestCase):
    def test_operational_database_refused_before_access(self):
        with self.assertRaisesRegex(AssertionError, "exact disposable"):
            bridge.run(SimpleNamespace(cr=SimpleNamespace(dbname="railway")))

    def test_methods_have_independent_delivery_return_figures(self):
        self.assertEqual(bridge.EXPECTED["average"], (50, 100, 60, 15))
        self.assertEqual(bridge.EXPECTED["fifo"], (50, 100, 40, 10))
        bridge.assert_values([50, 100, 60, 15], bridge.EXPECTED["average"])
        with self.assertRaisesRegex(AssertionError, "Native stock oracle"):
            bridge.assert_values([50, 100, 40, 10], bridge.EXPECTED["average"])

    def test_balanced_wrong_value_and_unposted_rejected(self):
        def snapshot(state="posted", difference=0):
            return {"journal_groups": [{"state": state, "comparisons_current_mapping": [{"difference": difference}]}]}
        bridge.assert_groups(snapshot())
        with self.assertRaisesRegex(AssertionError, "Stock/GL difference"):
            bridge.assert_groups(snapshot(difference=1))
        with self.assertRaisesRegex(AssertionError, "Unposted"):
            bridge.assert_groups(snapshot(state="draft"))


if __name__ == "__main__":
    unittest.main()
