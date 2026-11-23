"""Offline mutation tests for FIN37/FIN38 XLSX comparators."""

import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "scripts" / "ops"
sys.path.insert(0, str(OPS))

SPEC = importlib.util.spec_from_file_location(
    "verify_finance_i2c_xlsx", OPS / "verify_finance_i2c_xlsx.py",
)
oracle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(oracle)

HELPERS = importlib.util.spec_from_file_location(
    "test_finance_i2_xlsx_helpers", ROOT / "tests" / "test_finance_i2_xlsx.py",
)
helpers = importlib.util.module_from_spec(HELPERS)
HELPERS.loader.exec_module(helpers)
write_workbook = helpers.write_workbook


class I2CXlsxTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.xlsx = Path(self.temp.name) / "i2c.xlsx"

    def accrual_sheets(self):
        periods = [
            {
                "start": "2026-07-20", "end": "2026-07-31", "days": 12,
                "amount": 54545, "recognized_days": 6,
                "recognized_amount": 27273, "recognized": False,
            },
            {
                "start": "2026-08-01", "end": "2026-08-10", "days": 10,
                "amount": 45455, "recognized_days": 0,
                "recognized_amount": 0, "recognized": False,
            },
        ]
        return [
            ("Summary", [{"A": "Finance report export"}]),
            ("rows", [
                {"A": "line_id", "B": "move_id", "C": "account_id",
                 "D": "partner_id", "E": "balance", "F": "start_date",
                 "G": "end_date", "H": "total_days", "I": "recognized_to_date",
                 "J": "remaining", "K": "__nested"},
                {"A": 11, "B": 21, "C": 31, "D": 7, "E": 100000,
                 "F": "2026-07-20", "G": "2026-08-10", "H": 22,
                 "I": 27273, "J": 72727, "K": json.dumps({"periods": periods})},
            ]),
            ("exceptions", [
                {"A": "line_id", "B": "move_id", "C": "account_id",
                 "D": "partner_id", "E": "balance", "F": "reason"},
                {"A": 12, "B": 22, "C": 31, "D": 0, "E": 40,
                 "F": "missing_schedule_metadata"},
            ]),
        ]

    def verify_accrual(self):
        return oracle.verify_accrual_schedule(
            self.xlsx.read_bytes(),
            {11: {"move_id": 21, "account_id": 31, "partner_id": 7,
                   "balance": 100000, "start_date": "2026-07-20",
                   "end_date": "2026-08-10", "total_days": 22,
                   "recognized": 27273, "remaining": 72727,
                   "periods": [
                       {"start": "2026-07-20", "end": "2026-07-31", "days": 12,
                        "amount": 54545, "recognized_days": 6,
                        "recognized_amount": 27273, "recognized": False},
                       {"start": "2026-08-01", "end": "2026-08-10", "days": 10,
                        "amount": 45455, "recognized_days": 0,
                        "recognized_amount": 0, "recognized": False},
                   ]}},
            {12: {"move_id": 22, "account_id": 31, "partner_id": 0,
                  "balance": 40, "reason": "missing_schedule_metadata"}},
            {"control_total": 100040, "recognized_total": 27273,
             "remaining_total": 72727, "exception_total": 40},
        )

    def test_accrual_matches(self):
        write_workbook(self.xlsx, self.accrual_sheets())
        self.assertEqual(self.verify_accrual()["rows"], 1)

    def test_accrual_consistent_row_offset_rejected(self):
        sheets = self.accrual_sheets()
        row = sheets[1][1][1]
        row.update({"E": 100001, "I": 27274, "J": 72727})
        periods = json.loads(row["K"])
        periods["periods"][0].update({"amount": 54546, "recognized_amount": 27274})
        row["K"] = json.dumps(periods)
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "periods mismatch"):
            self.verify_accrual()

    def test_accrual_period_mutation_rejected(self):
        sheets = self.accrual_sheets()
        row = sheets[1][1][1]
        periods = json.loads(row["K"])
        periods["periods"][0]["recognized_amount"] = 149
        row["K"] = json.dumps(periods)
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "periods do not equal recognized"):
            self.verify_accrual()

    def test_accrual_period_dates_and_days_mutation_rejected(self):
        sheets = self.accrual_sheets()
        row = sheets[1][1][1]
        periods = json.loads(row["K"])
        periods["periods"][0].update({
            "start": "2099-01-01", "end": "2099-12-31", "days": 999,
            "recognized_days": 999, "recognized": True,
        })
        row["K"] = json.dumps(periods)
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "periods mismatch"):
            self.verify_accrual()

    def test_accrual_period_redistribution_with_same_totals_rejected(self):
        sheets = self.accrual_sheets()
        row = sheets[1][1][1]
        periods = json.loads(row["K"])
        periods["periods"][0].update({"amount": 1, "recognized_amount": 1})
        periods["periods"][1].update({
            "amount": 99999, "recognized_days": 0,
            "recognized_amount": 27272,
        })
        row["K"] = json.dumps(periods)
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "periods mismatch"):
            self.verify_accrual()

    def test_accrual_exception_reason_rejected(self):
        sheets = self.accrual_sheets()
        sheets[2][1][1]["F"] = "invalid_schedule_range"
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "exceptions mismatch"):
            self.verify_accrual()

    def fx_sheets(self):
        gl_rows = [{"currency_id": 2, "realized_amount": -100,
                    "gl_balance": -100, "difference": 0, "balanced": True}]
        return [
            ("Summary", [{"A": "Finance report export"}]),
            ("unrealized_rows", [
                {"A": "line_id", "B": "amount_residual_currency",
                 "C": "amount_residual", "D": "rate_as_of",
                 "E": "revalued_balance", "F": "unrealized_difference"},
                {"A": 71, "B": 100, "C": 1500, "D": 16,
                 "E": 1600, "F": 100},
            ]),
            ("realized_rows", [
                {"A": "partial_id", "B": "realized_amount"},
                {"A": 81, "B": -100},
            ]),
            ("realized_unposted_rows", [{"A": "No rows."}]),
            ("realized_by_currency", [
                {"A": "currency_id", "B": "realized_amount"},
                {"A": 2, "B": -100},
            ]),
            ("tied_exchange_move_ids", [{"A": "value"}, {"A": 91}]),
            ("gl_tie_out", [
                {"A": "key", "B": "value"},
                {"A": "rows", "B": json.dumps(gl_rows)},
                {"A": "difference", "B": 0},
                {"A": "balanced", "B": "Yes"},
            ]),
        ]

    def verify_fx(self):
        return oracle.verify_fx_revaluation(
            self.xlsx.read_bytes(),
            {71: (100, 1500, 16, 1600, 100)},
            {81: (-100,)}, {}, {2: (-100,)}, [91],
            {2: (-100, -100, 0)},
        )

    def test_fx_matches(self):
        write_workbook(self.xlsx, self.fx_sheets())
        self.assertEqual(self.verify_fx()["realized_rows"], 1)

    def test_fx_rate_accepts_excel_precision_only(self):
        write_workbook(self.xlsx, self.fx_sheets())
        result = oracle.verify_fx_revaluation(
            self.xlsx.read_bytes(),
            {71: (100, 1500, 15.999999999999998, 1600, 100)},
            {81: (-100,)}, {}, {2: (-100,)}, [91],
            {2: (-100, -100, 0)},
        )
        self.assertEqual(result["unrealized_rows"], 1)

    def test_fx_rate_material_difference_rejected(self):
        write_workbook(self.xlsx, self.fx_sheets())
        with self.assertRaisesRegex(ValueError, "rate_as_of"):
            oracle.verify_fx_revaluation(
                self.xlsx.read_bytes(),
                {71: (100, 1500, 15.9, 1600, 100)},
                {81: (-100,)}, {}, {2: (-100,)}, [91],
                {2: (-100, -100, 0)},
            )

    def test_fx_extra_unrealized_line_rejected(self):
        sheets = self.fx_sheets()
        sheets[1][1].append({"A": 72, "B": 0, "C": 0, "D": 16, "E": 0, "F": 0})
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "unrealized_rows coverage mismatch"):
            self.verify_fx()

    def test_fx_text_amount_rejected(self):
        sheets = self.fx_sheets()
        sheets[2][1][1]["B"] = "-100"
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "numeric cell is missing"):
            self.verify_fx()

    def test_fx_exchange_move_coverage_rejected(self):
        sheets = self.fx_sheets()
        sheets[5][1][1]["A"] = 92
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "exchange move coverage"):
            self.verify_fx()

    def test_fx_per_currency_netting_rejected(self):
        sheets = self.fx_sheets()
        rows = [
            {"currency_id": 2, "realized_amount": -90, "gl_balance": -100,
             "difference": 10, "balanced": False},
            {"currency_id": 3, "realized_amount": -10, "gl_balance": 0,
             "difference": -10, "balanced": False},
        ]
        sheets[6][1][1]["B"] = json.dumps(rows)
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "per-currency GL mismatch"):
            self.verify_fx()


if __name__ == "__main__":
    unittest.main()
