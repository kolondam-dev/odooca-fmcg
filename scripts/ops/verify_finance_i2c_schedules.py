#!/usr/bin/env python3
"""Disposable-only I2c verification for FIN37 accrual schedules and FIN38 FX.

Covers FIN37 (Accrual / Prepayment / Deferred schedules) and FIN38 (Foreign
Currency / FX revaluation). The independent oracle reads posted
``account.move.line``, ``account.partial.reconcile`` and the company exchange
accounts directly and never calls the production helpers. Everything runs
inside a savepoint and is rolled back.

FIN37 scope note: the straight-line recognition path reads the OCA
``account_invoice_start_end_dates`` metadata (``start_date``/``end_date`` on
``account.move.line``). The module is pinned in ``oca.lock`` and installed in
this disposable database, so the assertions below verify the allocation on a
real posted schedule (310000 over July, 150000 recognised at mid-July), keep
the **fail-closed** contract for lines without metadata (nominal exception,
never an assumed schedule), and reproduce the module constraint that rejects
incomplete or reversed date pairs before anything reaches the ledger.
"""

from collections import defaultdict
from datetime import date
import base64
import json
from pathlib import Path
import sys

from odoo.exceptions import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent) if "__file__" in globals() else "/opt/scripts/ops")
import verify_finance_i2_ledgers_core as i2a  # noqa: E402
import verify_finance_i2c_xlsx as xlsx_oracle  # noqa: E402
import verify_finance_ledger_security as sec  # noqa: E402

MISSING_SCHEDULE = "missing_schedule_metadata"


class RollbackI2c(Exception):
    pass


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def _cutoff(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _independent_month_ranges(start, end):
    """Yield inclusive calendar-month slices without production helpers."""
    cursor = start
    while cursor <= end:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        month_end = date.fromordinal(next_month.toordinal() - 1)
        yield cursor, min(month_end, end)
        cursor = next_month


def independent_accrual(env, company, account, as_of):
    """Rebuild FIN37 without the production helper.

    With no schedule metadata installed every line must be an exception, so the
    oracle reports rows={} and exceptions=all lines.
    """
    cutoff = _cutoff(as_of)
    round_amt = company.currency_id.round
    lines = env["account.move.line"].search([
        ("company_id", "=", company.id),
        ("account_id", "=", account.id),
        ("parent_state", "=", "posted"),
        ("date", "<=", cutoff),
        ("display_type", "not in", ["line_note", "line_section", "line_subsection"]),
    ], order="date asc, move_id asc, id asc")
    has_metadata = "start_date" in lines._fields
    rows, exceptions = {}, {}
    control = 0.0
    for line in lines:
        balance = round_amt(line.balance)
        control = round_amt(control + balance)
        start = getattr(line, "start_date", None) if has_metadata else None
        end = getattr(line, "end_date", None) if has_metadata else None
        identity = {
            "move_id": line.move_id.id,
            "account_id": line.account_id.id,
            "partner_id": line.partner_id.id or 0,
            "balance": balance,
        }
        if not start or not end:
            exceptions[line.id] = {**identity, "reason": MISSING_SCHEDULE}
            continue
        if start > end:
            exceptions[line.id] = {**identity, "reason": "invalid_schedule_range"}
            continue
        total_days = (end - start).days + 1
        periods = []
        allocated = recognized = 0.0
        month_ranges = list(_independent_month_ranges(start, end))
        for position, (period_start, period_end) in enumerate(month_ranges):
            days = (period_end - period_start).days + 1
            if position == len(month_ranges) - 1:
                amount = round_amt(balance - allocated)
            else:
                amount = round_amt(balance * days / total_days)
            allocated = round_amt(allocated + amount)
            recognized_days = min(
                max((min(cutoff, period_end) - period_start).days + 1, 0),
                days,
            )
            recognized_amount = round_amt(amount * recognized_days / days)
            recognized = round_amt(recognized + recognized_amount)
            periods.append({
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
                "days": days,
                "amount": amount,
                "recognized_days": recognized_days,
                "recognized_amount": recognized_amount,
                "recognized": recognized_days == days,
            })
        rows[line.id] = {
            **identity,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "total_days": total_days,
            "periods": periods,
            "recognized": recognized,
            "remaining": round_amt(balance - recognized),
        }
    return {
        "has_metadata": has_metadata,
        "rows": rows,
        "exceptions": exceptions,
        "control_total": control,
        "recognized_total": round_amt(sum(row["recognized"] for row in rows.values())),
        "exception_total": round_amt(sum(row["balance"] for row in exceptions.values())),
    }


def assert_accrual(snapshot, oracle):
    require(
        snapshot["schedule_metadata_available"] == oracle["has_metadata"],
        "FIN37 metadata availability flag does not match the line model",
    )
    observed = {
        row["line_id"]: (row["balance"], row["recognized_to_date"])
        for row in snapshot["rows"]
    }
    expected = {
        line_id: (row["balance"], row["recognized"]) for line_id, row in oracle["rows"].items()
    }
    require(observed == expected, f"FIN37 recognition mismatch: {observed} != {expected}")
    observed_exc = {row["line_id"]: row["reason"] for row in snapshot["exceptions"]}
    expected_exc = {line_id: row["reason"] for line_id, row in oracle["exceptions"].items()}
    require(observed_exc == expected_exc, f"FIN37 exception mismatch: {observed_exc} != {expected_exc}")
    require(
        snapshot["control_total"] == oracle["control_total"],
        f"FIN37 control total mismatch: {snapshot['control_total']} != {oracle['control_total']}",
    )
    require(
        snapshot["recognized_total"] == oracle["recognized_total"],
        f"FIN37 recognized total mismatch: {snapshot['recognized_total']} != {oracle['recognized_total']}",
    )
    require(
        snapshot["exception_total"] == oracle["exception_total"],
        f"FIN37 exception total mismatch: {snapshot['exception_total']} != {oracle['exception_total']}",
    )
    require(
        snapshot["balanced"] and snapshot["unexplained_difference"] == 0.0,
        f"FIN37 schedule does not tie: {snapshot['unexplained_difference']}",
    )


def _export_report(env, company, report_type, as_of, **values):
    """Render the real wizard XLSX inside the disposable fixture."""
    wizard = env["id.finance.report.wizard"].with_context(
        allowed_company_ids=company.ids,
    ).create({
        "company_id": company.id,
        "company_ids": [(6, 0, company.ids)],
        "report_type": report_type,
        "as_of_date": as_of,
        "only_posted_moves": True,
        **values,
    })
    action = wizard.action_export_xlsx()
    require(action.get("type") == "ir.actions.act_url",
            f"XLSX export did not download for {report_type}")
    return base64.b64decode(wizard.result_xlsx or b"")


def assert_accrual_export(env, company, oracle, as_of, account_ids):
    payload = _export_report(
        env, company, "accrual_schedule", as_of,
        account_ids=[(6, 0, account_ids)],
    )
    totals = {
        "control_total": oracle["control_total"],
        "recognized_total": oracle["recognized_total"],
        "remaining_total": company.currency_id.round(
            oracle["control_total"] - oracle["recognized_total"]
            - oracle["exception_total"],
        ),
        "exception_total": oracle["exception_total"],
    }
    return xlsx_oracle.verify_accrual_schedule(
        payload, oracle["rows"], oracle["exceptions"], totals,
    )


def build_fx_fixture(env, suffix):
    """Company with two USD transactions at different rates, fully reconciled.

    Invoice 100 USD booked at 15,000 (1,500,000 IDR); payment 100 USD at 16,000
    (1,600,000 IDR). Full reconciliation makes Odoo post a 100,000 IDR exchange
    gain for the fixture.
    """
    company = i2a.build_i2a_fixture(env, suffix, 1)
    fx_company, accounts, journals, partner, scale, docs = company
    round_amt = fx_company.currency_id.round

    usd = env.ref("base.USD")
    usd.active = True
    env["res.currency.rate"].create({
        "name": "2026-01-01", "currency_id": usd.id, "company_id": fx_company.id,
        "rate": 1 / 15000.0,
    })
    env["res.currency.rate"].create({
        "name": "2026-07-31", "currency_id": usd.id, "company_id": fx_company.id,
        "rate": 1 / 16000.0,
    })

    fx_income = env["account.account"].with_company(fx_company).create({
        "name": f"FX gain {suffix}", "code": f"FXG{suffix}", "account_type": "income",
        "company_ids": [(6, 0, fx_company.ids)], "reconcile": False,
    })
    fx_expense = env["account.account"].with_company(fx_company).create({
        "name": f"FX loss {suffix}", "code": f"FXL{suffix}", "account_type": "expense",
        "company_ids": [(6, 0, fx_company.ids)], "reconcile": False,
    })
    fx_journal = env["account.journal"].with_company(fx_company).create({
        "name": f"FX {suffix}", "code": f"FX{suffix}", "type": "general",
        "company_id": fx_company.id,
    })
    fx_company.write({
        "income_currency_exchange_account_id": fx_income.id,
        "expense_currency_exchange_account_id": fx_expense.id,
        "currency_exchange_journal_id": fx_journal.id,
    })

    def usd_entry(label, when, ar_balance, ar_currency, journal=None):
        move = env["account.move"].with_company(fx_company).create({
            "company_id": fx_company.id,
            "journal_id": (journal or journals["general"]).id,
            "date": when,
            "ref": f"I2C-{label}-{suffix}",
            "move_type": "entry",
            "line_ids": [
                (0, 0, {
                    "name": label, "account_id": accounts["ar"].id,
                    "partner_id": partner.id, "currency_id": usd.id,
                    "debit": ar_balance if ar_balance > 0 else 0,
                    "credit": -ar_balance if ar_balance < 0 else 0,
                    "amount_currency": ar_currency,
                }),
                (0, 0, {
                    "name": label, "account_id": accounts["cash"].id,
                    "currency_id": usd.id,
                    "debit": -ar_balance if ar_balance < 0 else 0,
                    "credit": ar_balance if ar_balance > 0 else 0,
                    "amount_currency": -ar_currency,
                }),
            ],
        })
        move.action_post()
        return move

    # Invoice in the SALE journal, settlement in the CASH journal. This makes a
    # journal filter meaningful: selecting only the sale journal keeps the
    # invoice line in scope while dropping the payment leg.
    invoice = usd_entry("invoice", "2026-07-01", 1_500_000, 100, journals["sale"])
    payment = usd_entry("payment", "2026-07-15", -1_600_000, -100, journals["cash"])
    (sec.control_line(invoice, accounts["ar"])
     | sec.control_line(payment, accounts["ar"])).reconcile()

    # August noise: a second USD invoice that stays open. It must not change the
    # July position, and it proves the report rebuilds residuals as of the date
    # instead of reading the current amount_residual.
    august_invoice = usd_entry("aug_invoice", "2026-08-10", 480_000, 32)
    require(
        round_amt(august_invoice.line_ids.filtered(
            lambda line: line.account_id == accounts["ar"]
        ).balance) == 480_000,
        "August FX invoice must post the expected AR balance",
    )

    # July invoice settled in August through the cash journal. At 31 July it must
    # be fully open (110 USD / 1,500,000); at 31 August it must be closed. This is
    # the case the previous fixture could not prove.
    july_invoice = usd_entry("july_open_invoice", "2026-07-20", 1_500_000, 100,
                              journals["sale"])
    august_receipt = usd_entry("aug_receipt", "2026-08-05", -1_500_000, -100,
                               journals["cash"])
    (sec.control_line(july_invoice, accounts["ar"])
     | sec.control_line(august_receipt, accounts["ar"])).reconcile()

    # Write-off fixture: an AR line settled against the expense account. It must
    # be classified as a write-off and produce no realized FX.
    write_off_invoice = usd_entry("write_off_invoice", "2026-07-25", 750_000, 50,
                                  journals["sale"])
    write_off_move = env["account.move"].with_company(fx_company).create({
        "company_id": fx_company.id,
        "journal_id": journals["general"].id,
        "date": "2026-07-28",
        "ref": f"I2C-WRITEOFF-{suffix}",
        "move_type": "entry",
        "line_ids": [
            (0, 0, {
                "name": "write off", "account_id": accounts["expense"].id,
                "currency_id": usd.id, "debit": 750_000, "amount_currency": 50,
            }),
            (0, 0, {
                "name": "write off", "account_id": accounts["ar"].id,
                "partner_id": partner.id, "currency_id": usd.id,
                "credit": 750_000, "amount_currency": -50,
            }),
        ],
    })
    write_off_move.action_post()
    (sec.control_line(write_off_invoice, accounts["ar"])
     | sec.control_line(write_off_move, accounts["ar"])).reconcile()

    # Reversal fixture A: reversed with cancel=False. Odoo keeps the original
    # reconcile and only posts a mirror move, so the settlement still stands.
    reversal_source = usd_entry("reversal_source", "2026-06-10", 300_000, 20,
                                journals["sale"])
    reversal_settle = usd_entry("reversal_settle", "2026-06-20", -320_000, -20,
                                journals["cash"])
    (sec.control_line(reversal_source, accounts["ar"])
     | sec.control_line(reversal_settle, accounts["ar"])).reconcile()
    reversal_move = reversal_settle._reverse_moves(
        default_values_list=[{
            "date": date(2026, 6, 25),
            "journal_id": journals["cash"].id,
            "ref": f"I2C-REVERSAL-{suffix}",
        }],
        cancel=False,
    )
    reversal_move.action_post()

    # Reversal fixture B: reversed with cancel=True ("reverse and reconcile").
    # Odoo removes the original reconcile and reconciles the mirror move with the
    # original lines, which is the shape that can leave a genuine reversed
    # partial behind. This is the case the netting contract must be proven on.
    cancel_source = usd_entry("cancel_source", "2026-06-05", 300_000, 20,
                              journals["sale"])
    cancel_settle = usd_entry("cancel_settle", "2026-06-15", -320_000, -20,
                              journals["cash"])
    (sec.control_line(cancel_source, accounts["ar"])
     | sec.control_line(cancel_settle, accounts["ar"])).reconcile()
    cancel_reversal = cancel_settle._reverse_moves(
        default_values_list=[{
            "date": date(2026, 6, 18),
            "journal_id": journals["cash"].id,
            "ref": f"I2C-CANCEL-{suffix}",
        }],
        cancel=True,
    )

    return {
        "company": fx_company,
        "accounts": accounts,
        "journals": journals,
        "partner": partner,
        "scale": scale,
        "usd": usd,
        "fx_income": fx_income,
        "fx_expense": fx_expense,
        "invoice": invoice,
        "payment": payment,
        "august_invoice": august_invoice,
        "july_invoice": july_invoice,
        "august_receipt": august_receipt,
        "write_off_invoice": write_off_invoice,
        "write_off_move": write_off_move,
        "reversal_source": reversal_source,
        "reversal_settle": reversal_settle,
        "reversal_move": reversal_move,
        "cancel_source": cancel_source,
        "cancel_settle": cancel_settle,
        "cancel_reversal": cancel_reversal,
        "round_amt": round_amt,
    }


MONETARY_ACCOUNT_TYPES = (
    "asset_receivable", "liability_payable", "asset_cash",
    "liability_credit_card", "asset_current", "liability_current",
    "asset_non_current", "liability_non_current",
)


def _fx_leg_currency(line, company):
    return line.currency_id.id or company.currency_id.id


def _fx_leg_rate(line):
    """Company currency per unit of the leg's foreign currency."""
    if not line.amount_currency:
        return None
    return line.balance / line.amount_currency


def _fx_partial_currency(partial, company):
    return (
        partial.debit_move_id.currency_id.id
        or partial.credit_move_id.currency_id.id
        or company.currency_id.id
    )


def _fx_is_write_off(move):
    """A plain entry mixing a monetary line with a non-monetary one."""
    if move.move_type != "entry":
        return False
    types = move.line_ids.mapped("account_id.account_type")
    return any(t and t not in MONETARY_ACCOUNT_TYPES for t in types) and any(
        t in MONETARY_ACCOUNT_TYPES for t in types
    )


def _fx_move_ids(partial):
    return {
        partial.debit_move_id.move_id.id,
        partial.credit_move_id.move_id.id,
    }


def _fx_reverse_target(partial):
    debit_move = partial.debit_move_id.move_id
    credit_move = partial.credit_move_id.move_id
    return debit_move.reversed_entry_id.id or credit_move.reversed_entry_id.id or None


def _fx_cancelled_reversals(partials, company, round_amt):
    """Return ids of partials that undo each other completely.

    Only mutual, unique pairs whose currency and functional magnitudes mirror
    exactly cancel. A non-mirror pair makes the report incomplete, so the oracle
    fails instead of netting an unexplained residual.
    """
    parent = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left, right):
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for partial in partials:
        find(partial.debit_move_id.id)
        find(partial.credit_move_id.id)
        union(partial.debit_move_id.id, partial.credit_move_id.id)

    groups = defaultdict(list)
    for partial in partials:
        groups[find(partial.debit_move_id.id)].append(partial)

    cancelled = set()
    for group in groups.values():
        candidates = {
            partial.id: [
                other for other in group
                if other.id != partial.id
                and (_fx_reverse_target(partial) in _fx_move_ids(other)
                     or _fx_reverse_target(other) in _fx_move_ids(partial))
            ]
            for partial in group
        }
        seen = set()
        for partial in group:
            if partial.id in seen:
                continue
            component = []
            stack = [partial]
            while stack:
                node = stack.pop()
                if node.id in seen:
                    continue
                seen.add(node.id)
                component.append(node)
                stack.extend(candidates[node.id])
            links = {
                (item.id, other.id)
                for item in component
                for other in candidates[item.id]
            }
            if not links:
                continue
            if len(component) != 2 or len(links) != 2:
                raise ValueError(
                    "FIN38 reversal component is ambiguous: "
                    f"{sorted(item.id for item in component)}"
                )
            first, second = component
            currency_gap = round_amt(
                max(abs(first.debit_amount_currency), abs(first.credit_amount_currency))
                - max(abs(second.debit_amount_currency), abs(second.credit_amount_currency))
            )
            functional_gap = round_amt(abs(first.amount) - abs(second.amount))
            if (_fx_partial_currency(first, company)
                    != _fx_partial_currency(second, company)
                    or currency_gap or functional_gap):
                raise ValueError(
                    "FIN38 reversal pair does not cancel: "
                    f"{sorted((first.id, second.id))}"
                )
            cancelled.update((first.id, second.id))
    return cancelled


def independent_fx(env, fixture, as_of):
    """Rebuild FIN38 totals without the production helper.

    Residuals are reconstructed from dated partials, never read from the current
    ``amount_residual``, and the tie-out is per currency with no netting. A
    partial whose counterpart falls outside the report filter still reduces the
    selected line; otherwise a filtered payment would look open again.
    """
    company = fixture["company"]
    cutoff = _cutoff(as_of)
    round_amt = fixture["round_amt"]
    exchange_ids = {fixture["fx_income"].id, fixture["fx_expense"].id}

    lines = env["account.move.line"].search([
        ("company_id", "=", company.id),
        ("date", "<=", cutoff),
        ("parent_state", "=", "posted"),
        ("display_type", "not in", ["line_note", "line_section", "line_subsection"]),
        ("currency_id", "!=", company.currency_id.id),
        # FIN38 is a monetary-position report: expense/revenue lines are not
        # revalued even when they carry a foreign currency.
        ("account_id.account_type", "in", [
            "asset_receivable", "liability_payable", "asset_cash",
            "liability_credit_card", "asset_current", "liability_current",
            "asset_non_current", "liability_non_current",
        ]),
    ], order="date asc, move_id asc, id asc")

    # Scope the partials by every posted monetary line, not only the foreign
    # ones: a settlement, write-off or functional-currency counterpart outside
    # the revaluation base still reduces the selected line's residual.
    monetary = env["account.move.line"].search([
        ("company_id", "=", company.id),
        ("date", "<=", cutoff),
        ("parent_state", "=", "posted"),
        ("display_type", "not in", ["line_note", "line_section", "line_subsection"]),
        ("account_id.account_type", "in", list(MONETARY_ACCOUNT_TYPES)),
    ])
    scoped_ids = list(monetary.ids)
    partials = env["account.partial.reconcile"].search([
        ("company_id", "=", company.id),
        ("max_date", "<=", cutoff),
        "|",
        ("debit_move_id", "in", scoped_ids),
        ("credit_move_id", "in", scoped_ids),
    ], order="max_date asc, id asc") if scoped_ids else env["account.partial.reconcile"]

    matched = defaultdict(float)
    matched_currency = defaultdict(float)
    matched_amount = defaultdict(float)
    for partial in partials:
        debit_id = partial.debit_move_id.id
        credit_id = partial.credit_move_id.id
        matched[debit_id] = round_amt(matched[debit_id] - partial.amount)
        matched_currency[debit_id] = round_amt(
            matched_currency[debit_id] - abs(partial.debit_amount_currency)
        )
        matched[credit_id] = round_amt(matched[credit_id] + partial.amount)
        matched_currency[credit_id] = round_amt(
            matched_currency[credit_id] + abs(partial.credit_amount_currency)
        )
        matched_amount[debit_id] = round_amt(
            matched_amount[debit_id] + abs(partial.amount)
        )
        matched_amount[credit_id] = round_amt(
            matched_amount[credit_id] + abs(partial.amount)
        )

    tied = {
        partial.exchange_move_id.id
        for partial in partials
        if partial.exchange_move_id
    }
    cancelled = _fx_cancelled_reversals(partials, company, round_amt)

    realized = unposted = 0.0
    realized_rows = {}
    unposted_rows = {}
    for partial in sorted(
        (item for item in partials if item.id not in cancelled),
        key=lambda item: (str(item.max_date or ""), item.id),
    ):
        debit = partial.debit_move_id
        credit = partial.credit_move_id
        debit_currency = _fx_leg_currency(debit, company)
        credit_currency = _fx_leg_currency(credit, company)
        if (company.currency_id.id in {debit_currency, credit_currency}
                and len({debit_currency, credit_currency}) > 1):
            # One leg is already in company currency: no exchange difference.
            continue
        if _fx_is_write_off(debit.move_id) or _fx_is_write_off(credit.move_id):
            # A write-off removes carrying value without an FX settlement.
            continue
        debit_rate = _fx_leg_rate(debit)
        credit_rate = _fx_leg_rate(credit)
        if debit_rate is None or credit_rate is None:
            raise ValueError(
                f"FIN38 partial {partial.id} cannot be classified without a "
                "leg currency amount"
            )
        amount = round_amt(
            abs(partial.debit_amount_currency) * debit_rate
            - abs(partial.credit_amount_currency) * credit_rate
        )
        if partial.exchange_move_id:
            realized = round_amt(realized + amount)
            realized_rows[partial.id] = (amount,)
        else:
            unposted = round_amt(unposted + amount)
            unposted_rows[partial.id] = (amount,)

    realized_by_currency = defaultdict(float)
    # Currency totals follow the realized rows, keyed by the partial's currency.
    by_partial = {partial.id: partial for partial in partials}
    for partial_id, values in realized_rows.items():
        partial = by_partial[partial_id]
        currency_id = _fx_leg_currency(partial.debit_move_id, company)
        realized_by_currency[currency_id] = round_amt(
            realized_by_currency[currency_id] + values[0]
        )

    unrealized = 0.0
    unrealized_rows = {}
    over_reconciled = {
        line.id for line in lines
        if round_amt(matched_amount[line.id]) > round_amt(abs(line.balance)) + 0.01
    }
    for line in lines:
        if line.account_id.id in exchange_ids or line.id in over_reconciled:
            continue
        residual = round_amt(line.balance + matched[line.id])
        residual_currency = round_amt(line.amount_currency + matched_currency[line.id])
        if round_amt(residual) == 0 and round_amt(residual_currency) == 0:
            continue
        rate = line.currency_id._get_conversion_rate(
            line.currency_id, company.currency_id, company, cutoff,
        )
        revalued = round_amt(residual_currency * rate)
        difference = round_amt(revalued - residual)
        unrealized = round_amt(unrealized + difference)
        unrealized_rows[line.id] = (
            residual_currency, residual, rate, revalued, difference,
        )

    gl_totals = defaultdict(float)
    for line in env["account.move.line"].search([
        ("company_id", "=", company.id),
        ("account_id", "in", list(exchange_ids)),
        ("date", "<=", cutoff),
        ("parent_state", "=", "posted"),
        ("display_type", "not in", ["line_note", "line_section", "line_subsection"]),
    ]):
        currency_id = line.currency_id.id or company.currency_id.id
        gl_totals[currency_id] = round_amt(gl_totals[currency_id] + line.balance)

    return {
        "unrealized_total": unrealized,
        "unrealized_rows": unrealized_rows,
        "realized_total": realized,
        "realized_rows": realized_rows,
        "unposted_total": unposted,
        "unposted_rows": unposted_rows,
        "tied_exchange_move_ids": sorted(tied),
        "realized_by_currency": dict(realized_by_currency),
        "gl_totals": dict(gl_totals),
    }


def assert_fx(snapshot, oracle, round_amt):
    require(
        snapshot["unrealized_total"] == oracle["unrealized_total"],
        f"FIN38 unrealized mismatch: {snapshot['unrealized_total']} != {oracle['unrealized_total']}",
    )
    require(
        snapshot["realized_posted_total"] == oracle["realized_total"],
        f"FIN38 realized mismatch: {snapshot['realized_posted_total']} != {oracle['realized_total']}",
    )
    require(
        snapshot["realized_unposted_total"] == oracle["unposted_total"],
        f"FIN38 unposted evidence mismatch: "
        f"{snapshot['realized_unposted_total']} != {oracle['unposted_total']}",
    )
    require(
        snapshot["tied_exchange_move_ids"] == oracle["tied_exchange_move_ids"],
        f"FIN38 exchange move coverage mismatch: "
        f"{snapshot['tied_exchange_move_ids']} != {oracle['tied_exchange_move_ids']}",
    )
    require(
        snapshot["gl_tie_out"]["balanced"],
        f"FIN38 FX does not tie out: {snapshot['gl_tie_out']}",
    )
    # A report with over-reconciled lines or unclassified partials must never
    # present itself as complete, even when the totals happen to balance.
    require(
        snapshot["complete"] is True,
        f"FIN38 report must be complete: over_reconciled="
        f"{len(snapshot['over_reconciled_rows'])}, exceptions={len(snapshot['exceptions'])}",
    )
    require(
        snapshot["over_reconciled_rows"] == [],
        f"FIN38 must not report over-reconciled lines: {snapshot['over_reconciled_rows']}",
    )
    # Independent per-currency comparison: no netting across currencies, and GL
    # currencies without realized rows still have to match.
    currencies = set(oracle["realized_by_currency"]) | set(oracle["gl_totals"])
    for currency_id in currencies:
        expected = round_amt(oracle["gl_totals"].get(currency_id, 0.0))
        realized = round_amt(oracle["realized_by_currency"].get(currency_id, 0.0))
        require(
            round_amt(realized - expected) == 0,
            f"FIN38 independent tie-out fails for currency {currency_id}: "
            f"{realized} != {expected}",
        )
    failing = set(snapshot["gl_tie_out"].get("failing_currency_ids") or [])
    require(not failing, f"FIN38 tie-out flagged currencies: {sorted(failing)}")


def assert_fx_export(env, company, oracle, as_of):
    payload = _export_report(env, company, "fx_revaluation", as_of)
    currencies = set(oracle["realized_by_currency"]) | set(oracle["gl_totals"])
    expected_gl = {
        currency_id: (
            oracle["realized_by_currency"].get(currency_id, 0.0),
            oracle["gl_totals"].get(currency_id, 0.0),
            company.currency_id.round(
                oracle["realized_by_currency"].get(currency_id, 0.0)
                - oracle["gl_totals"].get(currency_id, 0.0),
            ),
        )
        for currency_id in currencies
    }
    return xlsx_oracle.verify_fx_revaluation(
        payload,
        oracle["unrealized_rows"],
        oracle["realized_rows"],
        oracle["unposted_rows"],
        {currency_id: (amount,)
         for currency_id, amount in oracle["realized_by_currency"].items()},
        oracle["tied_exchange_move_ids"],
        expected_gl,
    )


def check_fin37(env, fixture, evidence, check_hard_coded=False):
    company, accounts, _journals, _partner, scale, _docs = fixture
    models = env(context=dict(env.context, allowed_company_ids=[company.id]))
    for as_of in ("2026-07-15", "2026-07-31", "2026-08-31"):
        oracle = independent_accrual(env, company, accounts["cash"], as_of)
        snapshot = models["id.finance.accrual.schedule"]._snapshot(
            company.id, as_of, account_ids=[accounts["cash"].id],
        )
        assert_accrual(snapshot, oracle)
        exported = assert_accrual_export(
            env, company, oracle, as_of, [accounts["cash"].id],
        )
        evidence["cases"].append({
            "case": "FIN37_xlsx_vs_independent_AML", "company": company.id,
            "as_of": as_of, **exported,
        })
        evidence["cases"].append({
            "company": company.name, "scale": scale, "report": "FIN37",
            "as_of": as_of, "result": "PASS",
        })
        if check_hard_coded:
            # The A/B fixtures post their lines without start_date/end_date, so
            # the fail-closed contract must still hold with the OCA metadata
            # module installed: no allocation, every line a nominal exception.
            require(
                snapshot["rows"] == [],
                "FIN37 must not allocate without start_date/end_date metadata",
            )
            require(
                snapshot["exception_count"] == len(snapshot["exceptions"]) > 0,
                "FIN37 must report every metadata-less line as a nominal exception",
            )
            require(
                snapshot["exception_total"] == snapshot["control_total"],
                "FIN37 exceptions must carry the full control balance when nothing is allocatable",
            )


def build_schedule_fixture(env, suffix):
    """Posted schedule lines with and without OCA date metadata.

    The OCA ``account_invoice_start_end_dates`` module (pinned in ``oca.lock``)
    adds ``start_date``/``end_date`` to ``account.move.line``. Four extra
    expense lines on an I2a fixture company cover the native cases:

    - July window 310000 over 2026-07-01..2026-07-31: 15 of 31 days elapsed at
      2026-07-15, so 150000 is recognised and 160000 remains;
    - a June window that closed before every cutoff: fully recognised;
    - a 100001 cross-month window over 2026-07-20..2026-08-10: two monthly
      periods, a partial July cutoff, and a final-period rounding remainder;
    - a posted line without dates: an exception for itself only.
    """
    company, accounts, journals, partner, scale, docs = i2a.build_i2a_fixture(
        env, suffix, 1,
    )

    def entry(ref, when, lines):
        move = env["account.move"].with_company(company).create({
            "company_id": company.id,
            "journal_id": journals["general"].id,
            "date": when,
            "ref": f"I2C-{ref}-{suffix}",
            "move_type": "entry",
            "line_ids": lines,
        })
        move.action_post()
        return move

    july = entry("SCHEDULE-JULY", "2026-07-01", [
        (0, 0, {
            "name": "July accrual", "account_id": accounts["expense"].id,
            "debit": 310_000 * scale, "credit": 0,
            "start_date": "2026-07-01", "end_date": "2026-07-31",
        }),
        (0, 0, {
            "name": "July accrual", "account_id": accounts["cash"].id,
            "debit": 0, "credit": 310_000 * scale,
        }),
    ])
    june = entry("SCHEDULE-JUNE", "2026-06-15", [
        (0, 0, {
            "name": "June accrual", "account_id": accounts["expense"].id,
            "debit": 30_000 * scale, "credit": 0,
            "start_date": "2026-06-01", "end_date": "2026-06-30",
        }),
        (0, 0, {
            "name": "June accrual", "account_id": accounts["cash"].id,
            "debit": 0, "credit": 30_000 * scale,
        }),
    ])
    cross_month = entry("SCHEDULE-CROSS-MONTH", "2026-07-01", [
        (0, 0, {
            "name": "Cross-month accrual", "account_id": accounts["expense"].id,
            "debit": 100_001 * scale, "credit": 0,
            "start_date": "2026-07-20", "end_date": "2026-08-10",
        }),
        (0, 0, {
            "name": "Cross-month accrual", "account_id": accounts["cash"].id,
            "debit": 0, "credit": 100_001 * scale,
        }),
    ])
    bare = entry("SCHEDULE-BARE", "2026-07-20", [
        (0, 0, {
            "name": "Metadata-less accrual", "account_id": accounts["expense"].id,
            "debit": 9_000 * scale, "credit": 0,
        }),
        (0, 0, {
            "name": "Metadata-less accrual", "account_id": accounts["cash"].id,
            "debit": 0, "credit": 9_000 * scale,
        }),
    ])

    def expense_line(move):
        return move.line_ids.filtered(lambda line: line.account_id == accounts["expense"])

    return {
        "company": company,
        "accounts": accounts,
        "journals": journals,
        "partner": partner,
        "scale": scale,
        "docs": docs,
        "july_move": july,
        "june_move": june,
        "cross_month_move": cross_month,
        "bare_move": bare,
        "july_line": expense_line(july),
        "june_line": expense_line(june),
        "cross_month_line": expense_line(cross_month),
        "bare_line": expense_line(bare),
    }


def check_fin37_schedule(env, fixture, evidence, check_hard_coded=False):
    """Prove FIN37 allocates a real posted schedule, not only exceptions."""
    company = fixture["company"]
    accounts = fixture["accounts"]
    scale = fixture["scale"]
    models = env(context=dict(env.context, allowed_company_ids=[company.id]))
    for as_of in ("2026-07-15", "2026-07-25", "2026-07-31", "2026-08-31"):
        oracle = independent_accrual(env, company, accounts["expense"], as_of)
        snapshot = models["id.finance.accrual.schedule"]._snapshot(
            company.id, as_of, account_ids=[accounts["expense"].id],
        )
        assert_accrual(snapshot, oracle)
        exported = assert_accrual_export(
            env, company, oracle, as_of, [accounts["expense"].id],
        )
        evidence["cases"].append({
            "case": "FIN37_xlsx_vs_independent_AML", "company": company.id,
            "as_of": as_of, **exported,
        })
        evidence["cases"].append({
            "company": company.name, "scale": scale, "report": "FIN37",
            "as_of": as_of, "metadata": oracle["has_metadata"], "result": "PASS",
        })
        if not check_hard_coded:
            continue
        require(
            snapshot["schedule_metadata_available"] is True,
            "FIN37 must expose the OCA schedule metadata pinned in oca.lock",
        )
        rows = {row["line_id"]: row for row in snapshot["rows"]}
        exceptions = {row["line_id"]: row["reason"] for row in snapshot["exceptions"]}
        july_id = fixture["july_line"].id
        june_id = fixture["june_line"].id
        cross_month_id = fixture["cross_month_line"].id
        bare_id = fixture["bare_line"].id
        require(
            july_id in rows and june_id in rows and cross_month_id in rows,
            f"FIN37 must allocate the metadata-bearing lines: rows={sorted(rows)} "
            f"exceptions={sorted(exceptions)}",
        )
        # Record the allocated figures in the evidence payload, not only in the
        # assertion: the CI log must show what was recognised, not just PASS.
        evidence.setdefault("schedule_cases", []).append({
            "as_of": as_of,
            "july_balance": rows[july_id]["balance"],
            "july_recognized": rows[july_id]["recognized_to_date"],
            "june_recognized": rows[june_id]["recognized_to_date"],
            "cross_month_recognized": rows[cross_month_id]["recognized_to_date"],
            "cross_month_periods": rows[cross_month_id]["periods"],
            "recognized_total": snapshot["recognized_total"],
            "exception_total": snapshot["exception_total"],
            "unexplained_difference": snapshot["unexplained_difference"],
            "bare_exception": exceptions.get(bare_id),
        })
        require(
            rows[july_id]["balance"] == 310_000 * scale,
            f"FIN37 July schedule balance mismatch: {rows[july_id]}",
        )
        # Recognition is capped at the window end: the June window closed before
        # every cutoff in the list.
        require(
            rows[june_id]["recognized_to_date"] == 30_000 * scale,
            f"FIN37 must recognise a closed window in full: {rows[june_id]}",
        )
        cross_periods = rows[cross_month_id]["periods"]
        require(
            [(period["start"], period["end"], period["days"], period["amount"])
             for period in cross_periods] == [
                ("2026-07-20", "2026-07-31", 12, 54_546 * scale),
                ("2026-08-01", "2026-08-10", 10, 45_455 * scale),
            ],
            "FIN37 must split the cross-month schedule and put rounding drift "
            f"in its final period: {cross_periods}",
        )
        expected_cross_recognized = {
            "2026-07-15": 0,
            "2026-07-25": 27_273 * scale,
            "2026-07-31": 54_546 * scale,
            "2026-08-31": 100_001 * scale,
        }[as_of]
        require(
            rows[cross_month_id]["recognized_to_date"] == expected_cross_recognized,
            "FIN37 cross-month partial recognition mismatch: "
            f"{rows[cross_month_id]}",
        )
        if as_of == "2026-07-15":
            require(
                rows[july_id]["recognized_to_date"] == 150_000 * scale,
                "FIN37 must prorate 310000 over the 31-day July window: "
                f"{rows[july_id]}",
            )
            require(
                snapshot["recognized_total"] == 180_000 * scale,
                "FIN37 recognised total must be the allocated amounts only: "
                f"{snapshot['recognized_total']}",
            )
            require(
                bare_id not in exceptions,
                "FIN37 must not include a line dated after the cutoff",
            )
        elif as_of == "2026-07-25":
            require(
                rows[july_id]["recognized_to_date"] == 250_000 * scale,
                "FIN37 must prorate the July window at the partial cutoff: "
                f"{rows[july_id]}",
            )
            require(
                exceptions.get(bare_id) == MISSING_SCHEDULE,
                "FIN37 must retain the in-scope metadata-less line as an exception: "
                f"{exceptions}",
            )
        else:
            require(
                rows[july_id]["recognized_to_date"] == 310_000 * scale,
                "FIN37 must recognise the July window in full at month end: "
                f"{rows[july_id]}",
            )
            require(
                exceptions.get(bare_id) == MISSING_SCHEDULE,
                "FIN37 must keep only the metadata-less line as an exception: "
                f"{exceptions}",
            )


def check_schedule_constraints(env, fixture, evidence):
    """Reproduce the OCA module constraints on invalid date pairs.

    The module's own tests expect ValidationError straight from create() for a
    reversed pair and for a line carrying only one date. Each attempt runs in a
    savepoint so the rejected record never reaches the ledger.
    """
    company = fixture["company"]
    accounts = fixture["accounts"]
    journals = fixture["journals"]
    cases = (
        ("start_date_without_end_date", {"start_date": "2026-07-05"}),
        ("end_date_without_start_date", {"end_date": "2026-07-05"}),
        ("start_after_end", {"start_date": "2026-07-10", "end_date": "2026-07-01"}),
    )
    for label, dates in cases:
        try:
            with env.cr.savepoint():
                env["account.move"].with_company(company).create({
                    "company_id": company.id,
                    "journal_id": journals["general"].id,
                    "date": "2026-07-05",
                    "ref": f"I2C-INVALID-{label}",
                    "move_type": "entry",
                    "line_ids": [
                        (0, 0, {
                            "name": "invalid schedule",
                            "account_id": accounts["expense"].id,
                            "debit": 1, "credit": 0,
                            **dates,
                        }),
                        (0, 0, {
                            "name": "invalid schedule",
                            "account_id": accounts["cash"].id,
                            "debit": 0, "credit": 1,
                        }),
                    ],
                })
        except ValidationError:
            env.invalidate_all()
            evidence["counterexamples"].append({
                "case": f"schedule_{label}", "result": "REJECTED",
            })
        else:
            raise AssertionError(
                f"OCA schedule constraint accepted an invalid date pair: {label}"
            )


def check_fin38(env, fixture, evidence, check_hard_coded=False):
    company = fixture["company"]
    models = env(context=dict(env.context, allowed_company_ids=[company.id]))
    round_amt = fixture["round_amt"]
    for as_of in ("2026-07-31", "2026-08-31"):
        oracle = independent_fx(env, fixture, as_of)
        snapshot = models["id.finance.fx.revaluation"]._snapshot(company.id, as_of)
        assert_fx(snapshot, oracle, round_amt)
        exported = assert_fx_export(env, company, oracle, as_of)
        evidence["cases"].append({
            "case": "FIN38_xlsx_vs_independent_AML", "company": company.id,
            "as_of": as_of, **exported,
        })
        evidence["cases"].append({
            "company": company.name, "scale": 1, "report": "FIN38",
            "as_of": as_of, "result": "PASS",
        })
        if check_hard_coded and as_of == "2026-07-31":
            # Target the specific invoice/payment reconciliation rather than the
            # grand total: the fixture now also carries a reversal pair and a
            # write-off, so the total legitimately exceeds this one gain.
            amounts = [row["realized_amount"] for row in snapshot["realized_rows"]]
            require(
                round_amt(-100_000) in amounts,
                f"FIN38 must realise the -100000 gain on the main settlement, got {amounts}",
            )
            require(
                snapshot["tied_exchange_move_ids"],
                "FIN38 must tie to a posted exchange move",
            )
            # The July-settled invoice must be gone from the 31 July base, while
            # the July invoice settled in August must still be there. Asserting
            # per invoice, not per account, because both live on AR.
            settled_line = fixture["invoice"].line_ids.filtered(
                lambda line: line.account_id == fixture["accounts"]["ar"]
            )
            require(
                all(row["line_id"] != settled_line.id
                    for row in snapshot["unrealized_rows"]),
                "FIN38 must drop the invoice settled before the as-of date",
            )
            require(
                snapshot["gl_tie_out"]["balanced"],
                f"FIN38 must tie out to the signed exchange balance: {snapshot['gl_tie_out']}",
            )
            # July must not see the August invoice: this is the regression for
            # "FIN38 memakai residual saat ini".
            august_currency = fixture["august_invoice"].line_ids.filtered(
                lambda line: line.account_id == fixture["accounts"]["ar"]
            ).mapped("amount_currency")
            require(
                all(
                    row["amount_residual_currency"] != august_currency[0]
                    for row in snapshot["unrealized_rows"]
                ),
                "FIN38 July report must not include the August open invoice",
            )

            # A July invoice settled in August must be FULLY OPEN at 31 July and
            # CLOSED at 31 August. This is the two-cutoff acceptance the review
            # asked for, and it is what the current-residual bug broke.
            july_line = fixture["july_invoice"].line_ids.filtered(
                lambda line: line.account_id == fixture["accounts"]["ar"]
            )
            july_august_scope = models["id.finance.fx.revaluation"]._snapshot(
                company.id, "2026-08-31",
            )
            july_rows_july_cutoff = [
                row for row in snapshot["unrealized_rows"]
                if row["line_id"] == july_line.id
            ]
            require(
                len(july_rows_july_cutoff) == 1
                and july_rows_july_cutoff[0]["amount_residual_currency"] == 100.0,
                "FIN38 at 31 July must keep the July invoice fully open at 100 USD",
            )
            require(
                all(row["line_id"] != july_line.id
                    for row in july_august_scope["unrealized_rows"]),
                "FIN38 at 31 August must show the July invoice as settled",
            )

            # Journal filter must not un-settle a line paid through another
            # journal. The July invoice is settled in the cash journal; selecting
            # only the sale journal must still net it, must still realise the FX,
            # and must still find the exchange move.
            sale_journal_id = fixture["journals"]["sale"].id
            sale_scope = models["id.finance.fx.revaluation"]._snapshot(
                company.id, "2026-08-31", journal_ids=[sale_journal_id],
            )
            require(
                all(row["line_id"] != july_line.id
                    for row in sale_scope["unrealized_rows"]),
                "FIN38 journal filter must not hide a settlement made in another journal",
            )
            require(
                sale_scope["gl_tie_out"]["balanced"],
                f"FIN38 filtered tie-out must balance: {sale_scope['gl_tie_out']}",
            )
            require(
                sale_scope["gl_tie_out"]["scope_limited"],
                "FIN38 filtered tie-out must report that its comparator is scoped",
            )
            # Lock the nominal amount and the exchange coverage, not just the
            # boolean: a filtered report that realises nothing still balanced.
            require(
                round_amt(sale_scope["realized_posted_total"]) != 0,
                "FIN38 filtered report must realise a non-zero FX amount",
            )
            require(
                bool(sale_scope["tied_exchange_move_ids"]),
                "FIN38 filtered report must find its exchange move coverage",
            )
            require(
                sale_scope["gl_tie_out"]["rows"]
                and all(
                    round_amt(row["gl_balance"]) != 0
                    for row in sale_scope["gl_tie_out"]["rows"]
                ),
                "FIN38 filtered comparator must not be empty",
            )
            require(
                bool(sale_scope["realized_rows"]),
                "FIN38 filtered report must still produce realized rows",
            )
            require(
                not sale_scope["functional_counterpart_rows"],
                "FIN38 filtered report must not misclassify a filtered-out "
                "counterpart as functional currency",
            )
            require(
                sale_scope["gl_tie_out"].get("issues") == [],
                f"FIN38 filtered tie-out must report no issue: {sale_scope['gl_tie_out']}",
            )

            # Write-off must be classified through the production reader and must
            # not create realized FX.
            write_off_snapshot = models["id.finance.fx.revaluation"]._snapshot(
                company.id, "2026-08-31",
            )
            require(
                write_off_snapshot["write_off_rows"],
                "FIN38 must classify the expense-settled AR line as a write-off",
            )
            write_off_partials = {
                row["partial_id"] for row in write_off_snapshot["write_off_rows"]
            }
            require(
                not write_off_partials & {
                    row["partial_id"] for row in write_off_snapshot["realized_rows"]
                },
                "FIN38 write-off must not also appear in realized rows",
            )

            # P1: the comparator scope must come from the selected partials, not
            # from the ones that survived classification. Recompute the selection
            # straight from the database and require an exact match.
            monetary_lines = env["account.move.line"].search([
                ("company_id", "=", company.id),
                ("date", "<=", "2026-08-31"),
                ("parent_state", "=", "posted"),
                ("display_type", "not in", ["line_note", "line_section", "line_subsection"]),
                ("account_id.account_type", "in", [
                    "asset_receivable", "liability_payable", "asset_cash",
                    "liability_credit_card", "asset_current", "liability_current",
                    "asset_non_current", "liability_non_current",
                ]),
            ])
            in_scope_partials = env["account.partial.reconcile"].search([
                ("company_id", "=", company.id),
                ("max_date", "<=", "2026-08-31"),
                "|",
                ("debit_move_id", "in", monetary_lines.ids),
                ("credit_move_id", "in", monetary_lines.ids),
            ])
            in_scope_partials.check_access("read")
            expected_scope = {
                record.exchange_move_id.id for record in in_scope_partials
                if record.exchange_move_id
            }
            require(
                set(write_off_snapshot["tied_exchange_move_ids"]) == expected_scope,
                "FIN38 comparator scope must equal the exchange moves of the selected "
                f"partials: {set(write_off_snapshot['tied_exchange_move_ids'])} "
                f"!= {expected_scope}",
            )

            # Reversal proof. The native log must show that a reversal really
            # produces a pair, and that netting yields the expected number. Both
            # were previously asserted only by absence of duplicate rows, which a
            # silently dead code path also satisfies.
            diagnostics = reversal_diagnostics(env, fixture)
            evidence["reversal_diagnostics"] = diagnostics
            require(
                any(row["debit_has_reversal"] or row["credit_has_reversal"]
                    for row in diagnostics),
                f"reversal fixture must produce a reversed partial: {diagnostics}",
            )
            # cancel=True ("reverse and reconcile") deletes the original partial and
            # reconciles the mirror move against the settlement line. That pair must
            # exist and must carry no exchange move of its own.
            cancel_pair = [
                row for row in diagnostics
                if {row["debit_move_id"], row["credit_move_id"]}
                == {fixture["cancel_settle"].id, fixture["cancel_reversal"].id}
            ]
            require(
                len(cancel_pair) == 1,
                f"reverse-and-reconcile must form exactly one reversal pair: {cancel_pair}",
            )
            require(
                cancel_pair[0]["exchange_move_id"] is None,
                "a fully reversed settlement must not carry exchange evidence",
            )
            require(
                cancel_pair[0]["debit_reversed_entry"] == fixture["cancel_settle"].id
                or cancel_pair[0]["credit_reversed_entry"] == fixture["cancel_settle"].id,
                "the reversal pair must link back to the settlement it reversed: "
                f"{cancel_pair[0]}",
            )
            # The cancelled settlement must not resurface as realized FX, and the
            # cancel=False settlement must still be there: it was never undone.
            cancel_line_ids = {
                row["debit_line_id"] for row in cancel_pair
            } | {row["credit_line_id"] for row in cancel_pair}
            realized_line_ids = {
                row["debit_line_id"] for row in write_off_snapshot["realized_rows"]
            } | {row["credit_line_id"] for row in write_off_snapshot["realized_rows"]}
            require(
                not cancel_line_ids & realized_line_ids,
                f"a reversed settlement must not produce realized FX: {cancel_line_ids & realized_line_ids}",
            )
            expected_pairs = {
                (row["debit_line_id"], row["credit_line_id"])
                for row in write_off_snapshot["realized_rows"]
            }
            require(
                len(expected_pairs) == len(write_off_snapshot["realized_rows"]),
                "a reconciled pair must not be counted twice",
            )
            # Standard flows must not produce an ambiguous reversal, and the
            # report must therefore be able to claim completeness.
            require(
                write_off_snapshot["reversal_exceptions"] == [],
                "FIN38 must not report an ambiguous reversal for the standard flows: "
                f"{write_off_snapshot['reversal_exceptions']}",
            )
            # Locked nominal: main settlement -100000, cancel=False settlement
            # -20000 still standing, cancelled settlement 0, write-off 0.
            require(
                round_amt(write_off_snapshot["realized_posted_total"]) == round_amt(-120_000),
                "FIN38 realized total must equal the reconciled settlements only, got "
                f"{write_off_snapshot['realized_posted_total']}",
            )


def reversal_diagnostics(env, fixture):
    """Record the real shape of every partial that touches the reversal fixtures.

    Odoo keeps the reversed link on the mirror move, while the original move only
    knows ``reversal_move_ids``. Dumping both directions makes the pairing
    provable from the native log instead of asserted from assumption.
    """
    company = fixture["company"]
    moves = (
        fixture["reversal_settle"] | fixture["reversal_move"]
        | fixture["cancel_settle"] | fixture["cancel_reversal"]
    )
    lines = moves.mapped("line_ids").filtered(
        lambda line: line.account_id == fixture["accounts"]["ar"]
    )
    partials = env["account.partial.reconcile"].search([
        ("company_id", "=", company.id),
        "|", ("debit_move_id", "in", lines.ids), ("credit_move_id", "in", lines.ids),
    ], order="id asc")
    partials.check_access("read")
    rows = []
    for record in partials:
        debit_move = record.debit_move_id.move_id
        credit_move = record.credit_move_id.move_id
        rows.append({
            "partial_id": record.id,
            "amount": record.amount,
            "max_date": str(record.max_date),
            "exchange_move_id": record.exchange_move_id.id or None,
            "debit_line_id": record.debit_move_id.id,
            "credit_line_id": record.credit_move_id.id,
            "debit_move_id": debit_move.id,
            "credit_move_id": credit_move.id,
            "debit_reversed_entry": debit_move.reversed_entry_id.id or None,
            "credit_reversed_entry": credit_move.reversed_entry_id.id or None,
            "debit_has_reversal": bool(debit_move.reversal_move_ids),
            "credit_has_reversal": bool(credit_move.reversal_move_ids),
            "debit_amount_currency": record.debit_amount_currency,
            "credit_amount_currency": record.credit_amount_currency,
        })
    return rows


def check_security(env, fixture_a, fixture_b, evidence):
    comp_a = fixture_a[0]
    comp_b, _acc_b, jnl_b, partner_b, _scale_b, _docs_b = fixture_b
    _reader_user, reader = sec.actor(
        env, "i2c.reader", comp_a, ["id_finance_foundation.group_finance_reader"],
    )
    _sales_user, sales = sec.actor(env, "i2c.sales", comp_a, ["sales_team.group_sale_salesman"])
    calls = (
        ("id.finance.accrual.schedule",
         lambda env_obj, cid: env_obj["id.finance.accrual.schedule"]._snapshot(cid, "2026-07-31")),
        ("id.finance.fx.revaluation",
         lambda env_obj, cid: env_obj["id.finance.fx.revaluation"]._snapshot(cid, "2026-07-31")),
    )
    for label, callback in calls:
        callback(reader, comp_a.id)
        evidence["cases"].append({"case": f"reader_allowed_{label}", "result": "PASS"})
        evidence["counterexamples"].append(sec.denied(
            env, lambda cb=callback: cb(reader, comp_b.id), f"reader_foreign_company_{label}",
        ))
        evidence["counterexamples"].append(sec.denied(
            env, lambda cb=callback, e=sales: cb(e, comp_a.id), f"sales_denied_{label}",
        ))
    evidence["counterexamples"].append(sec.denied(
        env,
        lambda: reader["id.finance.fx.revaluation"]._snapshot(
            comp_a.id, "2026-07-31", journal_ids=[jnl_b["sale"].id],
        ),
        "reader_foreign_journal_fin38",
    ))
    evidence["counterexamples"].append(sec.denied(
        env,
        lambda: reader["id.finance.accrual.schedule"]._snapshot(
            comp_a.id, "2026-07-31", journal_ids=[jnl_b["sale"].id],
        ),
        "reader_foreign_journal_fin37",
    ))
    evidence["counterexamples"].append(sec.denied(
        env,
        lambda: reader["id.finance.accrual.schedule"]._snapshot(
            comp_a.id, "2026-07-31", partner_ids=[partner_b.id],
        ),
        "reader_cross_company_partner_fin37",
    ))
    return reader


def check_tamper(env, fixture, evidence):
    company, accounts, journals, partner, scale, _docs = fixture
    models = env(context=dict(env.context, allowed_company_ids=[company.id]))
    baseline = independent_accrual(env, company, accounts["cash"], "2026-07-31")
    try:
        with env.cr.savepoint():
            env["account.move"].with_company(company).create({
                "company_id": company.id,
                "journal_id": journals["general"].id,
                "date": "2026-07-30",
                "ref": "I2C-TAMPER",
                "move_type": "entry",
                "line_ids": [
                    (0, 0, {
                        "name": "tamper", "account_id": accounts["cash"].id,
                        "debit": 9 * scale, "credit": 0,
                    }),
                    (0, 0, {
                        "name": "tamper", "account_id": accounts["expense"].id,
                        "debit": 0, "credit": 9 * scale,
                    }),
                ],
            }).action_post()
            try:
                assert_accrual(
                    models["id.finance.accrual.schedule"]._snapshot(
                        company.id, "2026-07-31", account_ids=[accounts["cash"].id],
                    ),
                    baseline,
                )
            except AssertionError:
                evidence["counterexamples"].append({
                    "case": "tamper_rejected_FIN37", "result": "REJECTED",
                })
            else:
                raise AssertionError("Tampered schedule unexpectedly accepted by FIN37")
            raise RollbackI2c()
    except RollbackI2c:
        env.invalidate_all()


def run(env):
    require(
        env.cr.dbname == "finance_i0_reports_disposable",
        "I2c verification requires exact disposable reports database",
    )
    for addon in (
        "account_financial_report", "account_invoice_start_end_dates",
        "id_finance_reporting", "id_finance_foundation",
    ):
        require(
            env["ir.module.module"].search_count([
                ("name", "=", addon), ("state", "=", "installed"),
            ]) == 1,
            f"Required addon {addon} is not installed",
        )

    companies_before = set(env["res.company"].search([]).ids)
    evidence = {
        "scope": "I2c accrual schedules and FX revaluation disposable native oracle; "
                 "not FIN01-58 acceptance",
        "reports_verified": ["FIN37", "FIN38"],
        "cases": [],
        "counterexamples": [],
    }

    try:
        with env.cr.savepoint():
            fix_a = i2a.build_i2a_fixture(env, "A", 1)
            fix_b = i2a.build_i2a_fixture(env, "B", 7)
            sched = build_schedule_fixture(env, "S")
            fx = build_fx_fixture(env, "X")
            check_fin37(env, fix_a, evidence, check_hard_coded=True)
            check_fin37(env, fix_b, evidence)
            check_fin37_schedule(env, sched, evidence, check_hard_coded=True)
            check_schedule_constraints(env, sched, evidence)
            check_fin38(env, fx, evidence, check_hard_coded=True)
            check_security(env, fix_a, fix_b, evidence)
            check_tamper(env, fix_a, evidence)
            raise RollbackI2c()
    except RollbackI2c:
        env.invalidate_all()

    require(
        set(env["res.company"].search([]).ids) == companies_before,
        "Company fixture leaked in I2c",
    )
    evidence["fixture_rollback"] = "PASS"
    print("FINANCE_I2C_SCHEDULES=" + json.dumps(evidence, sort_keys=True))
    print("FINANCE_I2C_SCHEDULES=PASS")
    return evidence


if "env" in globals():
    run(globals()["env"])
