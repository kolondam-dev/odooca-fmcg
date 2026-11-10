"""Pure I2c schedule and FX helpers for FIN37 and FIN38, without ORM.

The production reports collect native ``account.move.line``,
``account.partial.reconcile`` and asset/payroll records, then hand plain
dictionaries to these functions. Keeping the arithmetic here makes the oracle
testable without a database and keeps the report layer from inventing figures.

Two rules are deliberately strict:

- **FIN37** never allocates a period without explicit ``start_date``/``end_date``
  metadata. A row missing that metadata becomes a nominal exception instead of
  an assumed 12-month schedule.
- **FIN38** derives realized FX from the rate carried by each reconciled leg,
  never from ``partial.amount - partial.amount`` (which is always zero), and
  ties out only against partials that carry a posted ``exchange_move_id``.
"""

from collections import defaultdict
from datetime import date

MISSING_SCHEDULE = "missing_schedule_metadata"
INVALID_SCHEDULE = "invalid_schedule_range"
MISSING_CURRENCY = "missing_currency_amount"
OVER_RECONCILED = "over_reconciled"


def _as_date(value):
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    return None


def _month_ranges(start, end):
    """Yield inclusive (first, last) day pairs covering the schedule range."""
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        last = next_month.fromordinal(next_month.toordinal() - 1)
        yield max(cursor, start), min(last, end)
        cursor = next_month


def build_accrual_schedules(lines, as_of, round_amount):
    """Build read-only accrual/prepayment/deferred schedules as of ``as_of``.

    ``lines`` are plain dictionaries with ``line_id``, ``move_id``, ``move_name``,
    ``date``, ``account_id``, ``account_code``, ``account_type``, ``partner_id``,
    ``partner_name``, ``balance``, ``start_date`` and ``end_date``.

    Recognition is straight-line across the inclusive day range. Rows without
    usable metadata are reported as nominal exceptions and are never allocated;
    document dates are not used as a substitute for the service period.
    """
    cutoff = _as_date(as_of)
    if not cutoff:
        raise ValueError("Accrual schedules require an as-of date.")

    rows = []
    exceptions = []
    control_total = 0.0
    for line in lines:
        balance = line.get("balance") or 0.0
        control_total = round_amount(control_total + balance)
        start = _as_date(line.get("start_date"))
        end = _as_date(line.get("end_date"))
        base = {
            "line_id": line.get("line_id"),
            "move_id": line.get("move_id"),
            "move_name": line.get("move_name") or "",
            "date": _as_date(line.get("date")).isoformat() if line.get("date") else None,
            "account_id": line.get("account_id"),
            "account_code": line.get("account_code") or "",
            "account_type": line.get("account_type"),
            "partner_id": line.get("partner_id") or 0,
            "partner_name": line.get("partner_name") or "",
            "partnerless": not line.get("partner_id"),
            "balance": round_amount(balance),
        }
        if not start or not end:
            exceptions.append({**base, "reason": MISSING_SCHEDULE})
            continue
        if start > end:
            exceptions.append({
                **base,
                "reason": INVALID_SCHEDULE,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            })
            continue

        total_days = (end - start).days + 1
        periods = []
        recognized = 0.0
        allocated = 0.0
        month_ranges = list(_month_ranges(start, end))
        for index, (period_start, period_end) in enumerate(month_ranges):
            days = (period_end - period_start).days + 1
            if index == len(month_ranges) - 1:
                # The last period absorbs rounding drift so the schedule sums
                # exactly to the line balance instead of 1199.99/1200.01.
                amount = round_amount(balance - allocated)
            else:
                amount = round_amount(balance * days / total_days)
            allocated = round_amount(allocated + amount)
            goes_live = period_end <= cutoff
            periods.append({
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
                "days": days,
                "amount": amount,
                "recognized": goes_live,
            })
            if goes_live:
                recognized = round_amount(recognized + amount)

        recognized = round_amount(recognized)
        rows.append({
            **base,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "total_days": total_days,
            "periods": periods,
            "recognized_to_date": recognized,
            "remaining": round_amount(balance - recognized),
        })

    rows.sort(key=lambda row: (row["start_date"], row["line_id"] or 0))
    exceptions.sort(key=lambda row: (row["date"] or "", row["line_id"] or 0))
    recognized_total = round_amount(sum(row["recognized_to_date"] for row in rows))
    remaining_total = round_amount(sum(row["remaining"] for row in rows))
    exception_total = round_amount(sum(row["balance"] for row in exceptions))
    accounted = round_amount(recognized_total + remaining_total + exception_total)

    return {
        "rows": rows,
        "exceptions": exceptions,
        "control_total": control_total,
        "recognized_total": recognized_total,
        "remaining_total": remaining_total,
        "exception_total": exception_total,
        "accounted_total": accounted,
        "unexplained_difference": round_amount(accounted - control_total),
        "balanced": round_amount(accounted - control_total) == 0,
        "line_count": len(rows),
        "exception_count": len(exceptions),
    }


def _leg_rate(leg):
    """Functional currency per unit of the leg's foreign currency."""
    amount_currency = leg.get("amount_currency")
    if not amount_currency:
        return None
    return leg.get("balance") / amount_currency


def realized_partial_amount(partial, debit_leg, credit_leg, round_amount):
    """Realized FX for one ``account.partial.reconcile`` record.

    ``partial.amount`` is always positive and expressed in company currency, so
    ``amount - amount`` is identically zero. The exchange difference comes from
    the *rate* each leg carries:

        realized = debit_amount_currency * rate_debit
                 - credit_amount_currency * rate_credit

    Odoo stores ``debit_amount_currency`` and ``credit_amount_currency`` as
    positive magnitudes on ``account.partial.reconcile`` (verified in
    ``account_move_line._prepare_reconcile_vals``:
    ``partial_credit_amount_currency = credit_currency.round(credit_rate *
    min_recon_amount)``). That differs from ``account.move.line.amount_currency``,
    which is signed. ``abs()`` keeps the formula correct if a future version
    returns a signed value.

    Positive means loss, negative means gain. That direction matches Odoo's
    ``_get_exchange_account()``, which picks the expense account for positive
    residuals and the income account otherwise.
    """
    rate_debit = _leg_rate(debit_leg)
    rate_credit = _leg_rate(credit_leg)
    if rate_debit is None or rate_credit is None:
        return None, MISSING_CURRENCY
    functional_debit = abs(partial.get("debit_amount_currency") or 0.0) * rate_debit
    functional_credit = abs(partial.get("credit_amount_currency") or 0.0) * rate_credit
    return round_amount(functional_debit - functional_credit), None


def build_fx_revaluation(
    open_lines, partials, as_of, round_amount, rate_lookup, exchange_account_ids=(),
):
    """Split FIN38 into unrealized revaluation and realized exchange differences.

    ``open_lines`` are posted monetary lines with ``line_id``, ``account_id``,
    ``account_code``, ``account_type``, ``partner_id``, ``currency_id``,
    ``amount_residual_currency`` and ``amount_residual``.

    ``partials`` carry ``debit_line_id``/``credit_line_id``,
    ``debit_amount_currency``/``credit_amount_currency``, ``max_date`` and
    ``exchange_move_id``; the matching legs are resolved from ``open_lines``
    plus the caller-supplied leg payloads.

    Unrealized comes only from open positions. Realized comes only from
    partial reconciliations at or before ``as_of``. Exchange gain/loss accounts
    are excluded from the unrealized base so the posted exchange move is not
    counted twice.
    """
    cutoff = _as_date(as_of)
    if not cutoff:
        raise ValueError("FX revaluation requires an as-of date.")
    excluded = set(exchange_account_ids or ())

    unrealized_rows = []
    unrealized_total = 0.0
    for line in open_lines:
        if line.get("account_id") in excluded:
            continue
        amount_currency = line.get("amount_residual_currency") or 0.0
        amount_residual = line.get("amount_residual") or 0.0
        if round_amount(amount_currency) == 0 and round_amount(amount_residual) == 0:
            continue
        currency_id = line.get("currency_id")
        if not currency_id or currency_id == line.get("company_currency_id"):
            continue
        rate = rate_lookup(currency_id, cutoff)
        if rate is None:
            continue
        revalued = round_amount(amount_currency * rate)
        difference = round_amount(revalued - amount_residual)
        unrealized_total = round_amount(unrealized_total + difference)
        unrealized_rows.append({
            "line_id": line.get("line_id"),
            "move_id": line.get("move_id"),
            "account_id": line.get("account_id"),
            "account_code": line.get("account_code") or "",
            "account_type": line.get("account_type"),
            "partner_id": line.get("partner_id") or 0,
            "partner_name": line.get("partner_name") or "",
            "currency_id": currency_id,
            "amount_residual_currency": round_amount(amount_currency),
            "amount_residual": round_amount(amount_residual),
            "rate_as_of": rate,
            "revalued_balance": revalued,
            "unrealized_difference": difference,
        })

    realized_rows = []
    unposted_rows = []
    exceptions = []
    realized_posted_total = 0.0
    realized_unposted_total = 0.0
    tied_exchange_move_ids = set()
    for partial in partials:
        max_date = _as_date(partial.get("max_date"))
        if not max_date or max_date > cutoff:
            continue
        debit_leg = partial.get("debit_leg") or {}
        credit_leg = partial.get("credit_leg") or {}
        amount, reason = realized_partial_amount(partial, debit_leg, credit_leg, round_amount)
        if reason:
            exceptions.append({
                "partial_id": partial.get("partial_id"),
                "reason": reason,
                "max_date": max_date.isoformat(),
            })
            continue
        payload = {
            "partial_id": partial.get("partial_id"),
            "max_date": max_date.isoformat(),
            "amount": round_amount(partial.get("amount") or 0.0),
            "account_id": debit_leg.get("account_id"),
            "account_code": debit_leg.get("account_code") or "",
            "partner_id": debit_leg.get("partner_id") or 0,
            "currency_id": debit_leg.get("currency_id"),
            "realized_amount": amount,
            "exchange_move_id": partial.get("exchange_move_id"),
        }
        if partial.get("exchange_move_id"):
            tied_exchange_move_ids.add(partial["exchange_move_id"])
            realized_posted_total = round_amount(realized_posted_total + amount)
            realized_rows.append(payload)
        else:
            realized_unposted_total = round_amount(realized_unposted_total + amount)
            unposted_rows.append(payload)

    by_currency = defaultdict(float)
    for row in realized_rows:
        by_currency[row["currency_id"]] = round_amount(
            by_currency[row["currency_id"]] + row["realized_amount"]
        )

    return {
        "unrealized_rows": unrealized_rows,
        "unrealized_total": unrealized_total,
        "realized_rows": realized_rows,
        "realized_posted_total": realized_posted_total,
        "realized_unposted_rows": unposted_rows,
        "realized_unposted_total": realized_unposted_total,
        "realized_by_currency": [
            {"currency_id": currency_id, "realized_amount": by_currency[currency_id]}
            for currency_id in sorted(by_currency)
        ],
        "exceptions": exceptions,
        "tied_exchange_move_ids": sorted(tied_exchange_move_ids),
        "posted_evidence_total": round_amount(realized_posted_total),
    }


def tie_fx_to_gl(report, gl_balance_by_currency, round_amount):
    """Compare posted realized FX with the signed exchange gain/loss balance.

    The tie-out uses the **signed** balance as Odoo posts it, not its negation:
    a gain credits the income exchange account (negative balance) and matches a
    negative ``realized_amount``. A non-zero difference fails the report.
    """
    differences = []
    total_difference = 0.0
    for row in report["realized_by_currency"]:
        currency_id = row["currency_id"]
        expected = round_amount(gl_balance_by_currency.get(currency_id, 0.0))
        difference = round_amount(row["realized_amount"] - expected)
        total_difference = round_amount(total_difference + difference)
        differences.append({
            "currency_id": currency_id,
            "realized_amount": row["realized_amount"],
            "gl_balance": expected,
            "difference": difference,
        })
    return {
        "rows": differences,
        "difference": total_difference,
        "balanced": total_difference == 0,
        "issues": [] if total_difference == 0 else ["fx_tie_out_mismatch"],
    }
