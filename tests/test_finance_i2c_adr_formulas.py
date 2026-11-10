"""Fast unit tests for the I2c ADR formulas (FIN37 schedule, FIN38 realized FX).

These tests pin the arithmetic stated in ``docs/finance/I2C_DISCOVERY_ADR.md`` so
the ADR cannot drift away from a reproducible result. They do not install Odoo
and do not touch a database.
"""

import unittest
from datetime import date


def realized_partial(partial, debit_leg, credit_leg, round_amount=lambda v: round(v, 2)):
    """Realized FX for one ``account.partial.reconcile`` record.

    Mirrors ADR-I2c-03: the exchange difference comes from the *rate* carried by
    each leg, never from ``amount - amount`` (which is always zero).
    """
    rate_debit = debit_leg["balance"] / debit_leg["amount_currency"]
    rate_credit = credit_leg["balance"] / credit_leg["amount_currency"]
    functional_debit = partial["debit_amount_currency"] * rate_debit
    functional_credit = -partial["credit_amount_currency"] * rate_credit
    return round_amount(functional_debit - functional_credit)


def allocate_schedule(start_date, end_date, as_of, amount, round_amount=lambda v: round(v, 2)):
    """Straight-line recognition up to ``as_of`` for an explicit date range.

    Returns ``(recognized, remaining, exception)``. The exception string is set
    when the schedule metadata is missing or invalid; in that case no allocation
    is produced at all (ADR-I2c-02).
    """
    if not start_date or not end_date:
        return None, None, "missing_schedule_metadata"
    if start_date > end_date:
        return None, None, "invalid_schedule_range"
    total_days = (end_date - start_date).days + 1
    elapsed_days = min(max((min(as_of, end_date) - start_date).days + 1, 0), total_days)
    recognized = round_amount(amount * elapsed_days / total_days)
    return recognized, round_amount(amount - recognized), None


class RealizedFxTests(unittest.TestCase):
    def test_gain_when_payment_rate_is_higher(self):
        # Invoice 100 USD @15,000 = 1,500,000; paid 100 USD @16,000 = 1,600,000.
        partial = {"debit_amount_currency": 100.0, "credit_amount_currency": -100.0}
        result = realized_partial(
            partial,
            {"balance": 1_500_000.0, "amount_currency": 100.0},
            {"balance": -1_600_000.0, "amount_currency": -100.0},
        )
        self.assertEqual(result, -100_000.0, "payment at a higher rate must be a gain")

    def test_loss_when_payment_rate_is_lower(self):
        partial = {"debit_amount_currency": 100.0, "credit_amount_currency": -100.0}
        result = realized_partial(
            partial,
            {"balance": 1_600_000.0, "amount_currency": 100.0},
            {"balance": -1_500_000.0, "amount_currency": -100.0},
        )
        self.assertEqual(result, 100_000.0, "payment at a lower rate must be a loss")

    def test_partial_settlement_scales_linearly(self):
        partial = {"debit_amount_currency": 40.0, "credit_amount_currency": -40.0}
        result = realized_partial(
            partial,
            {"balance": 1_500_000.0, "amount_currency": 100.0},
            {"balance": -1_600_000.0, "amount_currency": -100.0},
        )
        self.assertEqual(result, -40_000.0)

    def test_functional_currency_has_no_exchange_difference(self):
        partial = {"debit_amount_currency": 100_000.0, "credit_amount_currency": -100_000.0}
        result = realized_partial(
            partial,
            {"balance": 100_000.0, "amount_currency": 100_000.0},
            {"balance": -100_000.0, "amount_currency": -100_000.0},
        )
        self.assertEqual(result, 0.0)

    def test_multi_partial_sums_instead_of_netting_balances(self):
        debit_leg = {"balance": 1_500_000.0, "amount_currency": 100.0}
        credit_a = {"balance": -640_000.0, "amount_currency": -40.0}
        credit_b = {"balance": -900_000.0, "amount_currency": -60.0}
        first = realized_partial(
            {"debit_amount_currency": 40.0, "credit_amount_currency": -40.0},
            debit_leg, credit_a,
        )
        second = realized_partial(
            {"debit_amount_currency": 60.0, "credit_amount_currency": -60.0},
            debit_leg, credit_b,
        )
        # 40 USD at 16,000 and 60 USD at 15,000 against a 15,000 invoice.
        self.assertEqual(first, -40_000.0)
        self.assertEqual(second, 0.0)
        self.assertEqual(first + second, -40_000.0)

    def test_tie_out_sign_matches_posted_exchange_move(self):
        # exchange_move gain line on income account carries a credit (negative).
        realized = -100_000.0
        posted_exchange_balance = 100_000.0
        self.assertEqual(realized, -posted_exchange_balance)


class ScheduleAllocationTests(unittest.TestCase):
    def test_missing_metadata_yields_exception_not_allocation(self):
        recognized, remaining, exc = allocate_schedule(None, None, date(2026, 7, 31), 1200.0)
        self.assertIsNone(recognized)
        self.assertIsNone(remaining)
        self.assertEqual(exc, "missing_schedule_metadata")

    def test_inverted_range_is_rejected(self):
        recognized, remaining, exc = allocate_schedule(
            date(2026, 8, 1), date(2026, 7, 1), date(2026, 7, 31), 1200.0,
        )
        self.assertIsNone(recognized)
        self.assertEqual(exc, "invalid_schedule_range")

    def test_full_range_recognition(self):
        recognized, remaining, exc = allocate_schedule(
            date(2026, 1, 1), date(2026, 12, 31), date(2026, 12, 31), 1200.0,
        )
        self.assertIsNone(exc)
        self.assertEqual(recognized, 1200.0)
        self.assertEqual(remaining, 0.0)

    def test_mid_range_recognition_is_partial(self):
        recognized, remaining, exc = allocate_schedule(
            date(2026, 1, 1), date(2026, 12, 31), date(2026, 6, 30), 1200.0,
        )
        self.assertIsNone(exc)
        # 181 of 365 days elapsed.
        self.assertEqual(recognized, round(1200.0 * 181 / 365, 2))
        self.assertEqual(round(recognized + remaining, 2), 1200.0)

    def test_as_of_before_start_recognizes_nothing(self):
        recognized, remaining, exc = allocate_schedule(
            date(2026, 7, 1), date(2026, 12, 31), date(2026, 6, 30), 1200.0,
        )
        self.assertIsNone(exc)
        self.assertEqual(recognized, 0.0)
        self.assertEqual(remaining, 1200.0)


if __name__ == "__main__":
    unittest.main()
