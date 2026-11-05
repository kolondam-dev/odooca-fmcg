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
COMPARE_SPEC = importlib.util.spec_from_file_location(
    "stock_compare", Path(__file__).parents[1] / "addons/id_finance_reporting/models/stock_compare.py",
)
compare = importlib.util.module_from_spec(COMPARE_SPEC)
COMPARE_SPEC.loader.exec_module(compare)


class StockBridgeOracleTests(unittest.TestCase):
    def test_production_comparison_rejects_extra_product_in_linked_journal(self):
        expected = {(100, 1): 50}
        baseline = [(1, 100, 1, 50), (2, 200, 1, -50)]
        rows = compare.compare_stock_gl(expected, baseline, {100}, round)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["difference"], 0)
        self.assertEqual(rows[0]["issues"], [])
        for product in (2, False):
            with self.subTest(product=product):
                lines = baseline + [(3, 100, product, 10), (4, 200, product, -10)]
                self.assertEqual(sum(row[3] for row in lines), 0)
                rows = compare.compare_stock_gl(expected, lines, {100}, round)
                anomaly = next(row for row in rows if row["product_id"] == product)
                self.assertEqual(anomaly["difference"], 10)
                self.assertEqual(anomaly["gl_line_ids"], [3])
                self.assertEqual(anomaly["issues"], ["gl_without_stock_move"])
                with self.assertRaisesRegex(AssertionError, "Unmatched stock/GL sources"):
                    bridge.assert_groups({"journal_groups": [{"state": "posted", "comparisons_current_mapping": rows}]})
        self.assertEqual(compare.compare_stock_gl(expected, baseline, {100}, round)[0]["issues"], [])

    def test_other_mapped_account_and_zero_net_unmatched_key_remain_visible(self):
        rows = compare.compare_stock_gl({(100, 1): 50}, [
            (1, 100, 1, 50), (2, 300, 2, 10), (3, 300, 2, -10),
        ], {100, 300}, round)
        self.assertEqual(rows[1]["difference"], 0)
        self.assertEqual(rows[1]["gl_line_ids"], [2, 3])
        self.assertEqual(rows[1]["issues"], ["gl_without_stock_move"])

    def test_missing_stock_gl_key_is_reported(self):
        rows = compare.compare_stock_gl({(100, 1): 50}, [], {100}, round)
        self.assertEqual(rows[0]["difference"], -50)
        self.assertEqual(rows[0]["issues"], ["stock_move_without_gl"])

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
