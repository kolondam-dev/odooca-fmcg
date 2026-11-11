#!/usr/bin/env python3
"""Disposable-only I2c verification for FIN37 accrual schedules and FIN38 FX.

Covers FIN37 (Accrual / Prepayment / Deferred schedules) and FIN38 (Foreign
Currency / FX revaluation). The independent oracle reads posted
``account.move.line``, ``account.partial.reconcile`` and the company exchange
accounts directly and never calls the production helpers. Everything runs
inside a savepoint and is rolled back.

FIN37 scope note: the straight-line recognition path needs the OCA
``account_invoice_start_end_dates`` metadata (``start_date``/``end_date`` on
``account.move.line``), which is not installed in this disposable database yet.
The native assertions here therefore verify the **fail-closed** contract: with
no metadata the report must produce only nominal exceptions, never an assumed
schedule, and must still tie to the control balance. The recognition arithmetic
is covered by ``tests/test_finance_i2c_schedules.py``.
"""

from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent) if "__file__" in globals() else "/opt/scripts/ops")
import verify_finance_i2_ledgers_core as i2a  # noqa: E402
import verify_finance_ledger_security as sec  # noqa: E402

MISSING_SCHEDULE = "missing_schedule_metadata"


class RollbackI2c(Exception):
    pass


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def _cutoff(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


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
        if not start or not end:
            exceptions[line.id] = {"balance": balance, "reason": MISSING_SCHEDULE}
            continue
        if start > end:
            exceptions[line.id] = {"balance": balance, "reason": "invalid_schedule_range"}
            continue
        total_days = (end - start).days + 1
        elapsed = min(max((min(cutoff, end) - start).days + 1, 0), total_days)
        rows[line.id] = {"balance": balance, "recognized": round_amt(balance * elapsed / total_days)}
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

    # Reversal fixture: a settlement whose move is reversed. The pair must net to
    # zero realized FX rather than double count.
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
        "round_amt": round_amt,
    }


def independent_fx(env, fixture, as_of):
    """Rebuild FIN38 totals without the production helper.

    Residuals are reconstructed from dated partials, never read from the current
    ``amount_residual``, and the tie-out is per currency with no netting.
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
    line_by_id = {line.id: line for line in lines}

    selected = list(line_by_id)
    # Same OR scope as production: a partial touching a selected line must apply
    # even when its counterpart is outside the filtered set, otherwise a July
    # invoice paid through a bank journal looks open again under journal filters.
    partials = env["account.partial.reconcile"].search([
        ("company_id", "=", company.id),
        ("max_date", "<=", cutoff),
        "|",
        ("debit_move_id", "in", selected),
        ("credit_move_id", "in", selected),
    ], order="max_date asc, id asc") if selected else env["account.partial.reconcile"]

    matched = defaultdict(float)
    matched_currency = defaultdict(float)
    realized = unposted = 0.0
    realized_by_currency = defaultdict(float)
    tied = set()
    for partial in partials:
        debit = line_by_id.get(partial.debit_move_id.id)
        credit = line_by_id.get(partial.credit_move_id.id)
        if not debit or not credit:
            continue
        if not debit.amount_currency or not credit.amount_currency:
            continue
        matched[debit.id] = round_amt(matched[debit.id] - partial.amount)
        matched_currency[debit.id] = round_amt(
            matched_currency[debit.id] - abs(partial.debit_amount_currency)
        )
        matched[credit.id] = round_amt(matched[credit.id] + partial.amount)
        matched_currency[credit.id] = round_amt(
            matched_currency[credit.id] + abs(partial.credit_amount_currency)
        )
        amount = round_amt(
            abs(partial.debit_amount_currency) * (debit.balance / debit.amount_currency)
            - abs(partial.credit_amount_currency) * (credit.balance / credit.amount_currency)
        )
        if partial.exchange_move_id:
            tied.add(partial.exchange_move_id.id)
            realized = round_amt(realized + amount)
            realized_by_currency[debit.currency_id.id] = round_amt(
                realized_by_currency[debit.currency_id.id] + amount
            )
        else:
            unposted = round_amt(unposted + amount)

    unrealized = 0.0
    for line in lines:
        if line.account_id.id in exchange_ids:
            continue
        residual = round_amt(line.balance + matched[line.id])
        residual_currency = round_amt(line.amount_currency + matched_currency[line.id])
        if round_amt(residual) == 0 and round_amt(residual_currency) == 0:
            continue
        rate = line.currency_id._get_conversion_rate(
            line.currency_id, company.currency_id, company, cutoff,
        )
        unrealized = round_amt(unrealized + round_amt(residual_currency * rate - residual))

    gl_totals = defaultdict(float)
    for line in env["account.move.line"].search([
        ("company_id", "=", company.id),
        ("account_id", "in", list(exchange_ids)),
        ("date", "<=", cutoff),
        ("parent_state", "=", "posted"),
    ]):
        currency_id = line.currency_id.id or company.currency_id.id
        gl_totals[currency_id] = round_amt(gl_totals[currency_id] + line.balance)

    return {
        "unrealized_total": unrealized,
        "realized_total": realized,
        "unposted_total": unposted,
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


def check_fin37(env, fixture, evidence, check_hard_coded=False):
    company, accounts, _journals, _partner, scale, _docs = fixture
    models = env(context=dict(env.context, allowed_company_ids=[company.id]))
    for as_of in ("2026-07-15", "2026-07-31", "2026-08-31"):
        oracle = independent_accrual(env, company, accounts["cash"], as_of)
        snapshot = models["id.finance.accrual.schedule"]._snapshot(
            company.id, as_of, account_ids=[accounts["cash"].id],
        )
        assert_accrual(snapshot, oracle)
        evidence["cases"].append({
            "company": company.name, "scale": scale, "report": "FIN37",
            "as_of": as_of, "result": "PASS",
        })
        if check_hard_coded and not oracle["has_metadata"]:
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


def check_fin38(env, fixture, evidence, check_hard_coded=False):
    company = fixture["company"]
    models = env(context=dict(env.context, allowed_company_ids=[company.id]))
    round_amt = fixture["round_amt"]
    for as_of in ("2026-07-31", "2026-08-31"):
        oracle = independent_fx(env, fixture, as_of)
        snapshot = models["id.finance.fx.revaluation"]._snapshot(company.id, as_of)
        assert_fx(snapshot, oracle, round_amt)
        evidence["cases"].append({
            "company": company.name, "scale": 1, "report": "FIN38",
            "as_of": as_of, "result": "PASS",
        })
        if check_hard_coded and as_of == "2026-07-31":
            require(
                snapshot["realized_posted_total"] == round_amt(-100_000),
                f"FIN38 gain must be -100000 for the USD fixture, got "
                f"{snapshot['realized_posted_total']}",
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

            # Reversal netting must be visible through the reader: the pair must
            # not double count realized FX.
            require(
                all(
                    not row.get("is_reversal")
                    for row in write_off_snapshot["realized_rows"]
                ),
                "FIN38 realized rows must not contain unmatched reversal noise",
            )


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
    for addon in ("account_financial_report", "id_finance_reporting", "id_finance_foundation"):
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
            fx = build_fx_fixture(env, "X")
            check_fin37(env, fix_a, evidence, check_hard_coded=True)
            check_fin37(env, fix_b, evidence)
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
