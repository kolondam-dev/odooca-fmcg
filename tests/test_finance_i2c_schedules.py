"""Fast local oracle tests for FIN37 accrual schedules and FIN38 FX revaluation."""

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ledger_schedules", ROOT / "addons/id_finance_reporting/models/ledger_schedules.py",
)
sched = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sched)

ROUND = lambda value: round(value, 2)  # noqa: E731


def accrual_line(line_id, balance, start=None, end=None, date="2026-01-01",  # noqa: PLR0913
                 account_type="asset_current", partner_id=5):
    return {
        "line_id": line_id,
        "move_id": line_id * 10,
        "move_name": f"MOVE-{line_id}",
        "date": date,
        "account_id": 140,
        "account_code": "1401",
        "account_type": account_type,
        "partner_id": partner_id,
        "partner_name": "Named Partner" if partner_id else "Missing Partner",
        "balance": balance,
        "start_date": start,
        "end_date": end,
    }


class AccrualScheduleTests(unittest.TestCase):
    def test_missing_metadata_is_exception_and_never_allocated(self):
        result = sched.build_accrual_schedules(
            [accrual_line(1, 1200.0)], "2026-06-30", ROUND,
        )
        self.assertEqual(result["rows"], [])
        self.assertEqual(len(result["exceptions"]), 1)
        self.assertEqual(result["exceptions"][0]["reason"], "missing_schedule_metadata")
        self.assertEqual(result["exception_total"], 1200.0)
        self.assertEqual(result["recognized_total"], 0.0)
        self.assertTrue(result["balanced"])

    def test_partial_metadata_is_also_exception(self):
        # Only start_date present must not be treated as a valid range.
        result = sched.build_accrual_schedules(
            [accrual_line(1, 600.0, start="2026-01-01")], "2026-06-30", ROUND,
        )
        self.assertEqual(result["exception_count"], 1)
        self.assertEqual(result["exceptions"][0]["reason"], "missing_schedule_metadata")

    def test_inverted_range_is_exception(self):
        result = sched.build_accrual_schedules(
            [accrual_line(1, 600.0, start="2026-08-01", end="2026-07-01")],
            "2026-08-31", ROUND,
        )
        self.assertEqual(result["exceptions"][0]["reason"], "invalid_schedule_range")
        self.assertEqual(result["balanced"], True)

    def test_full_year_fully_recognized_at_end(self):
        result = sched.build_accrual_schedules(
            [accrual_line(1, 1200.0, start="2026-01-01", end="2026-12-31")],
            "2026-12-31", ROUND,
        )
        row = result["rows"][0]
        self.assertEqual(row["recognized_to_date"], 1200.0)
        self.assertEqual(row["remaining"], 0.0)

    def test_mid_year_recognition_is_day_prorated_and_balanced(self):
        # ADR-I2c-02 fixes straight-line recognition across the inclusive day
        # range, so 181 of 365 days elapsed is 595.07, not 12 equal months.
        result = sched.build_accrual_schedules(
            [accrual_line(1, 1200.0, start="2026-01-01", end="2026-12-31")],
            "2026-06-30", ROUND,
        )
        row = result["rows"][0]
        self.assertEqual(len(row["periods"]), 12)
        self.assertEqual(row["recognized_to_date"], ROUND(1200.0 * 181 / 365))
        self.assertEqual(
            row["remaining"], ROUND(1200.0 - ROUND(1200.0 * 181 / 365)),
        )
        self.assertEqual(ROUND(row["recognized_to_date"] + row["remaining"]), 1200.0)
        self.assertEqual(ROUND(sum(p["amount"] for p in row["periods"])), 1200.0)

    def test_recognition_before_start_is_zero(self):
        result = sched.build_accrual_schedules(
            [accrual_line(1, 1200.0, start="2026-07-01", end="2026-12-31")],
            "2026-06-30", ROUND,
        )
        self.assertEqual(result["rows"][0]["recognized_to_date"], 0.0)
        self.assertEqual(result["rows"][0]["remaining"], 1200.0)

    def test_exceptions_and_rows_still_total_the_control_balance(self):
        lines = [
            accrual_line(1, 1200.0, start="2026-01-01", end="2026-12-31"),
            accrual_line(2, 300.0),
            accrual_line(3, 150.0, start="2026-08-01", end="2026-07-01"),
        ]
        result = sched.build_accrual_schedules(lines, "2026-06-30", ROUND)
        recognized = ROUND(1200.0 * 181 / 365)
        self.assertEqual(result["control_total"], 1650.0)
        self.assertEqual(result["recognized_total"], recognized)
        self.assertEqual(result["remaining_total"], ROUND(1200.0 - recognized))
        self.assertEqual(result["exception_total"], 450.0)
        self.assertEqual(result["unexplained_difference"], 0.0)
        self.assertTrue(result["balanced"])

    def test_month_ranges_cover_the_whole_spanned_period(self):
        result = sched.build_accrual_schedules(
            [accrual_line(1, 100.0, start="2026-03-15", end="2026-05-14")],
            "2026-05-14", ROUND,
        )
        periods = result["rows"][0]["periods"]
        self.assertEqual([p["start"] for p in periods],
                         ["2026-03-15", "2026-04-01", "2026-05-01"])
        self.assertEqual(periods[0]["end"], "2026-03-31")
        self.assertEqual(periods[-1]["end"], "2026-05-14")
        self.assertEqual(ROUND(sum(p["amount"] for p in periods)), 100.0)


def leg(balance, amount_currency, account_id=110, partner_id=5, currency_id=2):
    return {
        "balance": balance,
        "amount_currency": amount_currency,
        "account_id": account_id,
        "account_code": "1101",
        "partner_id": partner_id,
        "currency_id": currency_id,
    }


def partial(partial_id, debit_leg, credit_leg, amount, max_date="2026-07-31",
            exchange_move_id=None, debit_ccy=100.0, credit_ccy=-100.0):
    return {
        "partial_id": partial_id,
        "amount": amount,
        "debit_amount_currency": debit_ccy,
        "credit_amount_currency": credit_ccy,
        "max_date": max_date,
        "exchange_move_id": exchange_move_id,
        "debit_line_id": 1,
        "credit_line_id": 2,
        "debit_leg": debit_leg,
        "credit_leg": credit_leg,
    }


class RealizedFxTests(unittest.TestCase):
    def test_gain_when_payment_rate_is_higher(self):
        # Invoice 100 USD @15,000; paid 100 USD @16,000 -> gain 100,000
        amount, reason = sched.realized_partial_amount(
            partial(1, leg(1_500_000.0, 100.0), leg(-1_600_000.0, -100.0), 1_500_000.0, exchange_move_id=9),
            leg(1_500_000.0, 100.0), leg(-1_600_000.0, -100.0), ROUND,
        )
        self.assertIsNone(reason)
        self.assertEqual(amount, -100_000.0)

    def test_loss_when_payment_rate_is_lower(self):
        amount, reason = sched.realized_partial_amount(
            partial(1, leg(1_600_000.0, 100.0), leg(-1_500_000.0, -100.0), 1_600_000.0),
            leg(1_600_000.0, 100.0), leg(-1_500_000.0, -100.0), ROUND,
        )
        self.assertIsNone(reason)
        self.assertEqual(amount, 100_000.0)

    def test_partial_settlement_scales_with_the_reconciled_amount(self):
        amount, _reason = sched.realized_partial_amount(
            partial(1, leg(1_500_000.0, 100.0), leg(-640_000.0, -40.0), 640_000.0,
                    debit_ccy=40.0, credit_ccy=-40.0),
            leg(1_500_000.0, 100.0), leg(-640_000.0, -40.0), ROUND,
        )
        self.assertEqual(amount, -40_000.0)

    def test_functional_currency_has_no_exchange_difference(self):
        amount, _reason = sched.realized_partial_amount(
            partial(1, leg(100_000.0, 100_000.0), leg(-100_000.0, -100_000.0), 100_000.0),
            leg(100_000.0, 100_000.0), leg(-100_000.0, -100_000.0), ROUND,
        )
        self.assertEqual(amount, 0.0)

    def test_zero_amount_currency_is_an_exception_not_a_crash(self):
        amount, reason = sched.realized_partial_amount(
            partial(1, leg(1000.0, 0.0), leg(-1000.0, -100.0), 1000.0),
            leg(1000.0, 0.0), leg(-1000.0, -100.0), ROUND,
        )
        self.assertIsNone(amount)
        self.assertEqual(reason, "missing_currency_amount")


class FxRevaluationTests(unittest.TestCase):
    def test_realized_split_between_posted_and_unposted_evidence(self):
        invoice = leg(1_500_000.0, 100.0)
        payment = leg(-1_600_000.0, -100.0)
        partials = [
            partial(1, invoice, payment, 1_500_000.0, exchange_move_id=9),
            partial(2, invoice, payment, 100_000.0, exchange_move_id=None),
        ]
        report = sched.build_fx_revaluation([], partials, "2026-07-31", ROUND, lambda *_: 1.0)
        self.assertEqual(report["realized_posted_total"], -100_000.0)
        self.assertEqual(len(report["realized_rows"]), 1)
        self.assertEqual(report["realized_unposted_total"], -100_000.0)
        self.assertEqual(len(report["realized_unposted_rows"]), 1)
        self.assertEqual(report["tied_exchange_move_ids"], [9])

    def test_partial_after_as_of_is_excluded(self):
        invoice = leg(1_500_000.0, 100.0)
        payment = leg(-1_600_000.0, -100.0)
        report = sched.build_fx_revaluation(
            [], [partial(1, invoice, payment, 1_500_000.0, max_date="2026-08-01",
                         exchange_move_id=9)],
            "2026-07-31", ROUND, lambda *_: 1.0,
        )
        self.assertEqual(report["realized_posted_total"], 0.0)
        self.assertEqual(report["realized_rows"], [])

    def test_exchange_accounts_are_excluded_from_unrealized_base(self):
        open_line = {
            "line_id": 1, "account_id": 110, "account_type": "asset_receivable",
            "partner_id": 5, "currency_id": 2, "company_currency_id": 1,
            "amount_residual_currency": 100.0, "amount_residual": 1_500_000.0,
        }
        fx_line = {**open_line, "line_id": 2, "account_id": 999}
        report = sched.build_fx_revaluation(
            [open_line, fx_line], [], "2026-07-31", ROUND,
            lambda currency_id, as_of: 16_000.0, exchange_account_ids=[999],
        )
        self.assertEqual(len(report["unrealized_rows"]), 1)
        self.assertEqual(report["unrealized_rows"][0]["line_id"], 1)
        self.assertEqual(report["unrealized_total"], 100_000.0)

    def test_closed_positions_contribute_no_unrealized(self):
        closed = {
            "line_id": 1, "account_id": 110, "account_type": "asset_receivable",
            "partner_id": 5, "currency_id": 2, "company_currency_id": 1,
            "amount_residual_currency": 0.0, "amount_residual": 0.0,
        }
        report = sched.build_fx_revaluation(
            [closed], [], "2026-07-31", ROUND, lambda *_: 16_000.0,
        )
        self.assertEqual(report["unrealized_rows"], [])
        self.assertEqual(report["unrealized_total"], 0.0)

    def test_tie_out_uses_signed_balance_for_gain(self):
        invoice = leg(1_500_000.0, 100.0)
        payment = leg(-1_600_000.0, -100.0)
        report = sched.build_fx_revaluation(
            [], [partial(1, invoice, payment, 1_500_000.0, exchange_move_id=9)],
            "2026-07-31", ROUND, lambda *_: 1.0,
        )
        # Gain -100,000 posts as a credit on the income exchange account.
        tie = sched.tie_fx_to_gl(report, {2: -100_000.0}, ROUND)
        self.assertTrue(tie["balanced"], tie)
        self.assertEqual(tie["difference"], 0.0)

    def test_tie_out_uses_signed_balance_for_loss(self):
        invoice = leg(1_600_000.0, 100.0)
        payment = leg(-1_500_000.0, -100.0)
        report = sched.build_fx_revaluation(
            [], [partial(1, invoice, payment, 1_600_000.0, exchange_move_id=9)],
            "2026-07-31", ROUND, lambda *_: 1.0,
        )
        tie = sched.tie_fx_to_gl(report, {2: 100_000.0}, ROUND)
        self.assertTrue(tie["balanced"], tie)

    def test_negated_gl_balance_fails_the_gain_case(self):
        invoice = leg(1_500_000.0, 100.0)
        payment = leg(-1_600_000.0, -100.0)
        report = sched.build_fx_revaluation(
            [], [partial(1, invoice, payment, 1_500_000.0, exchange_move_id=9)],
            "2026-07-31", ROUND, lambda *_: 1.0,
        )
        tie = sched.tie_fx_to_gl(report, {2: 100_000.0}, ROUND)
        self.assertFalse(tie["balanced"])
        self.assertEqual(tie["difference"], -200_000.0)
        self.assertEqual(tie["issues"], ["fx_tie_out_mismatch"])


if __name__ == "__main__":
    unittest.main()
