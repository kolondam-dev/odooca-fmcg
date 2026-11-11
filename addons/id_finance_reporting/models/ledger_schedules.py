"""Pure I2c schedule and FX helpers for FIN37 and FIN38, without ORM.

The production reports collect native ``account.move.line``,
``account.partial.reconcile`` and company exchange accounts, then hand plain
dictionaries to these functions. Keeping the arithmetic here makes the oracle
testable without a database and keeps the report layer from inventing figures.

Two rules are deliberately strict:

- **FIN37** never allocates a period without explicit ``start_date``/``end_date``
  metadata, and recognises on a **day** basis so a mid-month as-of date yields a
  proportional amount instead of waiting for the month to finish.
- **FIN38** rebuilds the residual **as of** the report date from dated partials
  instead of reading the current ``amount_residual``, derives realized FX from
  the rate each leg carries, and ties out **per currency** so amounts in
  different currencies can never mask each other.
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

    Recognition is straight-line and **day-prorated**, so an as-of date inside a
    period recognises the elapsed portion of that period rather than zero.
    Rows without usable metadata are reported as nominal exceptions and are never
    allocated; document dates are not used as a substitute.
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
            # Day-proration inside the period: an as-of date mid-month must
            # recognise the elapsed days, not wait for the period to close.
            elapsed_days = min(max((min(cutoff, period_end) - period_start).days + 1, 0), days)
            recognized_days = elapsed_days
            recognized_amount = round_amount(amount * recognized_days / days)
            recognized = round_amount(recognized + recognized_amount)
            periods.append({
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
                "days": days,
                "amount": amount,
                "recognized_days": recognized_days,
                "recognized_amount": recognized_amount,
                "recognized": recognized_days == days,
            })

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


def reconstruct_line_residuals(lines, partials, as_of, round_amount):
    """Rebuild each line's residual as of ``as_of`` from dated partials.

    Reading the current ``amount_residual`` would let an August payment change a
    July open-position report. This walks the partials instead:

    - a partial only counts when ``max_date <= as_of``;
    - on the debit leg it reduces the residual, on the credit leg it increases it;
    - currency amounts use the positive magnitudes Odoo stores on
      ``account.partial.reconcile``.
    """
    cutoff = _as_date(as_of)
    if not cutoff:
        raise ValueError("FX revaluation requires an as-of date.")

    matched = defaultdict(float)
    matched_currency = defaultdict(float)
    partial_amount_by_line = defaultdict(float)
    for partial in partials:
        max_date = _as_date(partial.get("max_date"))
        if not max_date or max_date > cutoff:
            continue
        amount = partial.get("amount") or 0.0
        debit_id = partial.get("debit_line_id")
        credit_id = partial.get("credit_line_id")
        if debit_id is not None:
            partial_amount_by_line[debit_id] = round_amount(
                partial_amount_by_line[debit_id] + abs(amount)
            )
        if credit_id is not None:
            partial_amount_by_line[credit_id] = round_amount(
                partial_amount_by_line[credit_id] + abs(amount)
            )
        if debit_id is not None:
            matched[debit_id] = round_amount(matched[debit_id] - amount)
            matched_currency[debit_id] = round_amount(
                matched_currency[debit_id] - abs(partial.get("debit_amount_currency") or 0.0)
            )
        if credit_id is not None:
            matched[credit_id] = round_amount(matched[credit_id] + amount)
            matched_currency[credit_id] = round_amount(
                matched_currency[credit_id] + abs(partial.get("credit_amount_currency") or 0.0)
            )

    reconstructed = []
    over_reconciled = []
    for line in lines:
        line_id = line.get("line_id")
        balance = line.get("balance") or 0.0
        amount_currency = line.get("amount_currency") or 0.0
        if round_amount(partial_amount_by_line[line_id]) > round_amount(abs(balance)) + 0.01:
            over_reconciled.append({
                "line_id": line_id,
                "balance": round_amount(balance),
                "matched": round_amount(partial_amount_by_line[line_id]),
                "reason": OVER_RECONCILED,
            })
            continue
        reconstructed.append({
            **line,
            "residual_as_of": round_amount(balance + matched[line_id]),
            "residual_currency_as_of": round_amount(
                amount_currency + matched_currency[line_id]
            ),
        })
    return reconstructed, over_reconciled


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


def _net_reversals(partials, round_amount):
    """Net reversed partials per reconciled pair before totalling realized FX.

    A reversal is matched to the partial it undoes by comparing the reversed
    move id against each candidate's ``move_id``. Only a matched pair cancels;
    an unmatched reversal stays in the totals so it still offsets its own amount
    instead of silently disappearing.
    """
    surviving = []
    cancelled = set()
    by_pair = defaultdict(list)
    for partial in partials:
        key = (partial.get("debit_line_id"), partial.get("credit_line_id"))
        by_pair[key].append(partial)
    for _key, group in by_pair.items():
        reversals = [p for p in group if p.get("is_reversal")]
        normals = [p for p in group if not p.get("is_reversal")]
        for reversal in reversals:
            target = reversal.get("reversed_entry_id")
            if target is None:
                continue
            match = next(
                (
                    candidate for candidate in normals
                    if target in (candidate.get("move_ids") or (candidate.get("move_id"),))
                    and id(candidate) not in cancelled
                ),
                None,
            )
            if match is None:
                # Unmatched reversal: keep it so its own amount still posts.
                continue
            cancelled.add(id(match))
            cancelled.add(id(reversal))
        surviving.extend(p for p in group if id(p) not in cancelled)
    return surviving


def build_fx_revaluation(
    lines, partials, as_of, round_amount, rate_lookup, exchange_account_ids=(),
):
    """Split FIN38 into unrealized revaluation and realized exchange differences.

    ``lines`` are posted foreign-currency lines with ``line_id``, ``account_id``,
    ``account_code``, ``account_type``, ``partner_id``, ``currency_id``,
    ``balance`` and ``amount_currency``. Residuals are rebuilt **as of** the
    report date from dated partials, never read from the current residual.

    ``partials`` carry ``debit_line_id``/``credit_line_id``,
    ``debit_amount_currency``/``credit_amount_currency``, ``max_date``,
    ``exchange_move_id``, ``move_id``, ``reversed_entry_id`` and the resolved
    ``debit_leg``/``credit_leg`` payloads.

    Unrealized comes only from open positions. Realized comes only from partial
    reconciliations at or before ``as_of``. Exchange gain/loss accounts are
    excluded from the unrealized base so the posted exchange move is not
    counted twice.
    """
    cutoff = _as_date(as_of)
    if not cutoff:
        raise ValueError("FX revaluation requires an as-of date.")
    excluded = set(exchange_account_ids or ())

    reconstructed, over_reconciled = reconstruct_line_residuals(
        lines, partials, as_of, round_amount,
    )

    unrealized_rows = []
    unrealized_total = 0.0
    for line in reconstructed:
        if line.get("account_id") in excluded:
            continue
        amount_currency = line.get("residual_currency_as_of") or 0.0
        amount_residual = line.get("residual_as_of") or 0.0
        if round_amount(amount_currency) == 0 and round_amount(amount_residual) == 0:
            continue
        currency_id = line.get("currency_id")
        if not currency_id:
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
    functional_counterpart_rows = []
    write_off_rows = []
    realized_posted_total = 0.0
    realized_unposted_total = 0.0
    tied_exchange_move_ids = set()

    surviving = _net_reversals(partials, round_amount)
    for partial in surviving:
        max_date = _as_date(partial.get("max_date"))
        if not max_date or max_date > cutoff:
            continue
        debit_leg = partial.get("debit_leg") or {}
        credit_leg = partial.get("credit_leg") or {}
        if partial.get("functional_counterpart"):
            # One leg is in company currency, so there is no exchange difference
            # to realise. Reported explicitly instead of being silently zeroed.
            functional_counterpart_rows.append({
                "partial_id": partial.get("partial_id"),
                "max_date": max_date.isoformat(),
                "amount": round_amount(partial.get("amount") or 0.0),
                "account_id": debit_leg.get("account_id") or credit_leg.get("account_id"),
                "partner_id": debit_leg.get("partner_id") or credit_leg.get("partner_id") or 0,
                "currency_id": debit_leg.get("currency_id") or credit_leg.get("currency_id"),
                "reason": MISSING_CURRENCY,
            })
            continue
        if partial.get("write_off"):
            # A write-off removes carrying value without an FX settlement.
            write_off_rows.append({
                "partial_id": partial.get("partial_id"),
                "max_date": max_date.isoformat(),
                "amount": round_amount(partial.get("amount") or 0.0),
                "account_id": debit_leg.get("account_id") or credit_leg.get("account_id"),
                "partner_id": debit_leg.get("partner_id") or credit_leg.get("partner_id") or 0,
                "currency_id": debit_leg.get("currency_id") or credit_leg.get("currency_id"),
            })
            continue
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
            "currency_id": debit_leg.get("currency_id") or credit_leg.get("currency_id"),
            "realized_amount": amount,
            "exchange_move_id": partial.get("exchange_move_id"),
            "is_reversal": bool(partial.get("is_reversal")),
            "debit_line_id": partial.get("debit_line_id"),
            "credit_line_id": partial.get("credit_line_id"),
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
        "over_reconciled_rows": over_reconciled,
        "functional_counterpart_rows": functional_counterpart_rows,
        "write_off_rows": write_off_rows,
        "tied_exchange_move_ids": sorted(tied_exchange_move_ids),
        "posted_evidence_total": round_amount(realized_posted_total),
        "complete": not over_reconciled and not exceptions,
    }


def tie_fx_to_gl(report, gl_balance_by_currency, round_amount):
    """Compare posted realized FX with the signed exchange gain/loss balance.

    The tie-out is **per currency and never netted across currencies**: a surplus
    in USD must not mask a deficit in EUR. GL currencies with no realized row are
    still compared, so an orphan exchange balance cannot be ignored.

    Odoo posts a gain as a credit on the income exchange account (negative
    balance) matching a negative ``realized_amount``; the comparison therefore
    uses the signed balance, not its negation. A non-zero difference in any
    currency fails the report.
    """
    realized_by_currency = {
        row["currency_id"]: round_amount(row["realized_amount"])
        for row in report["realized_by_currency"]
    }
    currencies = sorted(set(realized_by_currency) | set(gl_balance_by_currency or {}))
    rows = []
    failing = []
    for currency_id in currencies:
        realized = round_amount(realized_by_currency.get(currency_id, 0.0))
        expected = round_amount((gl_balance_by_currency or {}).get(currency_id, 0.0))
        difference = round_amount(realized - expected)
        rows.append({
            "currency_id": currency_id,
            "realized_amount": realized,
            "gl_balance": expected,
            "difference": difference,
            "balanced": difference == 0,
        })
        if difference != 0:
            failing.append(currency_id)
    issues = []
    if failing:
        issues.append("fx_tie_out_mismatch")
    # A non-zero realized total with no comparator at all is a missing-evidence
    # failure, never a vacuous pass.
    has_realized = any(round_amount(row["realized_amount"]) for row in rows)
    if has_realized and not gl_balance_by_currency:
        issues.append("missing_exchange_evidence")
    return {
        "rows": rows,
        "difference": round_amount(sum(row["difference"] for row in rows)),
        "failing_currency_ids": failing,
        "balanced": not issues,
        "issues": issues,
    }
