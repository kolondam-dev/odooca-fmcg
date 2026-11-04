"""Regression tests for geo ops guards and dataset set verification.

Run: python -m unittest tests.test_geo_ops_guards -v
"""

import unittest

from scripts.ops import archive_staging_company as archive
from scripts.ops import verify_geo_backfill as verify


class ArchiveGuardTests(unittest.TestCase):
    def test_no_activity_does_not_block(self):
        counts = {"account.move": 0, "stock.move": 0, "stock.quant": 0}
        self.assertEqual(archive.blocking_documents(counts), {})

    def test_any_stock_activity_blocks(self):
        for model in ("stock.move", "stock.move.line", "stock.scrap", "mrp.production", "stock.quant"):
            with self.subTest(model=model):
                self.assertEqual(archive.blocking_documents({model: 1}), {model: 1})

    def test_quant_reservation_counts_as_activity(self):
        # The quant counter uses quantity OR reserved_quantity, so a pure
        # reservation yields a non-zero count and must block archiving.
        self.assertTrue(archive.blocking_documents({"stock.quant": 2}))

    def test_test_logins_are_accepted(self):
        self.assertEqual(archive.unexpected_logins(["staging.capture.1", "staging.capture.2"]), [])

    def test_non_test_login_is_reported(self):
        self.assertEqual(archive.unexpected_logins(["staging.capture.1", "admin"]), ["admin"])


class DatasetSetTests(unittest.TestCase):
    dataset = {"71.71.01", "71.71.02", "71.71.03"}

    def test_identical_set_passes(self):
        ok, detail = verify.set_ok(self.dataset, {code: 1 for code in self.dataset})
        self.assertTrue(ok)
        self.assertEqual(detail["missing"], [])
        self.assertEqual(detail["extra"], [])
        self.assertEqual(detail["rows"], 3)

    def test_swapped_code_fails_even_with_same_count(self):
        counts = {"71.71.01": 1, "71.71.02": 1, "71.99.99": 1}
        ok, detail = verify.set_ok(self.dataset, counts)
        self.assertFalse(ok)
        self.assertEqual(detail["rows"], 3)
        self.assertEqual(detail["missing"], ["71.71.03"])
        self.assertEqual(detail["extra"], ["71.99.99"])

    def test_fabricated_code_with_same_row_count_fails(self):
        counts = {code: 1 for code in self.dataset}
        counts["71.00.00"] = 1
        del counts["71.71.02"]
        ok, detail = verify.set_ok(self.dataset, counts)
        self.assertFalse(ok)
        self.assertEqual(detail["missing"], ["71.71.02"])
        self.assertEqual(detail["extra"], ["71.00.00"])

    def test_duplicate_code_fails(self):
        counts = {code: 1 for code in self.dataset}
        counts["71.71.01"] = 2
        ok, detail = verify.set_ok(self.dataset, counts)
        self.assertFalse(ok)
        self.assertEqual(detail["duplicates"], ["71.71.01"])

    def test_missing_code_fails(self):
        counts = {"71.71.01": 1, "71.71.02": 1}
        ok, detail = verify.set_ok(self.dataset, counts)
        self.assertFalse(ok)
        self.assertEqual(detail["missing"], ["71.71.03"])

    def test_dataset_expectations_match_acceptance(self):
        self.assertEqual(verify.EXPECTED, {"city": 15, "district": 171, "village": 1839})


if __name__ == "__main__":
    unittest.main()
