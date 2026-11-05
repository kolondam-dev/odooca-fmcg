#!/usr/bin/env python3
"""Extended disposable ledger evidence: OCA scope, real roles and native AR/AP.

No application security is bypassed in user probes. Fixtures use the shell
operator, then user environments use sudo(False). Everything is rolled back.
"""

from datetime import date
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent) if "__file__" in globals() else "/opt/scripts/ops")
import verify_finance_golden_ledger as golden  # noqa: E402


class RollbackFixture(Exception):
    pass


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def denied(env, callback, label):
    from odoo.exceptions import AccessError

    try:
        with env.cr.savepoint():
            callback()
    except AccessError:
        env.invalidate_all()
        return {"case": label, "result": "ACCESS_DENIED"}
    raise AssertionError(f"Expected AccessError: {label}")


def actor(env, name, company, groups, companies=None):
    user = env["res.users"].with_context(no_reset_password=True, mail_create_nolog=True).create({
        "name": f"Finance fixture {name}", "login": f"finance.fixture.{name}",
        "company_id": company.id, "company_ids": [(6, 0, (companies or company).ids)],
        "group_ids": [(6, 0, [env.ref(group).id for group in ["base.group_user", *groups]])],
    })
    user_env = env["account.move"].with_user(user).sudo(False).with_context(
        allowed_company_ids=company.ids,
    ).env
    require(not user_env.su, "Role probe must never execute as superuser")
    return user, user_env


def check_roles_and_scope(env, fixtures):
    a, b = fixtures
    evidence = []
    for fixture in fixtures:
        # With both companies readable and no account/journal filter, company
        # domain alone must isolate the report, including its account universe.
        visible_env = env["account.move"].with_context(allowed_company_ids=(a[0] | b[0]).ids).env
        actual = golden.trial_balance(visible_env, fixture, "2026-07-01", "2026-07-31", scoped_filters=False)
        golden.assert_figures(actual, golden.JULY, fixture[1], fixture[4])
        evidence.append({"case": f"unfiltered_company_{fixture[0].name}", "result": "PASS"})
        empty = {key: (0, 0, 0, 0) for key in golden.JULY}
        golden.assert_figures(
            golden.trial_balance(visible_env, fixture, "2026-05-01", "2026-05-31", scoped_filters=False),
            empty, fixture[1], fixture[4],
        )
        evidence.append({"case": f"empty_period_{fixture[0].name}", "result": "PASS"})

    user, reader = actor(env, "reader", a[0], ["account.group_account_readonly"])
    _accountant, accountant = actor(env, "accountant", a[0], ["account.group_account_user"], a[0] | b[0])
    _sales, sales = actor(env, "sales", a[0], ["sales_team.group_sale_salesman"])
    # Current driver and mobile sales share these actual backend groups. There
    # is no group_mobile_driver in the project; never invent a weaker fallback.
    _driver, driver = actor(env, "driver", a[0], ["id_mobile_api.group_mobile_evidence"])

    # Reader positive control then write/create negatives on the same source.
    actual = golden.trial_balance(reader, a, "2026-07-01", "2026-07-31", scoped_filters=False)
    golden.assert_figures(actual, golden.JULY, a[1])
    evidence.append({"case": "reader_report", "result": "PASS"})
    source = env["account.move"].search([("company_id", "=", a[0].id), ("state", "=", "posted")], limit=1)
    evidence.append(denied(env, lambda: source.with_env(reader).write({"ref": "FORBIDDEN"}), "reader_cannot_write"))
    evidence.append(denied(env, lambda: golden.make_entry(reader, a, "forbidden", "2026-07-01", {"cash": 1, "equity": -1}), "reader_cannot_create"))
    evidence.append(denied(env, lambda: golden.trial_balance(reader, b, "2026-07-01", "2026-07-31", scoped_filters=False), "reader_foreign_company"))
    foreign_line = env["account.move.line"].search([("company_id", "=", b[0].id)], limit=1)
    evidence.append(denied(env, lambda: foreign_line.with_env(reader).read(["balance"]), "reader_foreign_line"))
    require(not reader["account.move.line"].search([("company_id", "=", b[0].id)]), "Foreign AML visible to reader")
    for label, user_env in (("sales", sales), ("driver", driver)):
        evidence.append(denied(env, lambda e=user_env: golden.trial_balance(e, a, "2026-07-01", "2026-07-31", scoped_filters=False), f"{label}_report_denied"))
        evidence.append(denied(env, lambda e=user_env: e["report.account_financial_report.trial_balance"]._get_report_values([], {"company_id": a[0].id}), f"{label}_render_data_denied"))
        evidence.append(denied(env, lambda e=user_env: golden.make_entry(e, a, "forbidden", "2026-07-01", {"cash": 1, "equity": -1}), f"{label}_posting_denied"))
    for fixture in fixtures:
        totals = golden.trial_balance(accountant, fixture, "2026-07-01", "2026-07-31", scoped_filters=False)
        print("FINANCE_ACCOUNTANT_SCOPE=" + json.dumps({
            "company": fixture[0].name, "user_companies": accountant.user.company_ids.ids,
            "context_companies": accountant.context.get("allowed_company_ids"),
            "reported_account_ids": sorted(totals),
            "fixture_accounts": {key: account.id for key, account in fixture[1].items()},
        }, sort_keys=True, default=str))
        golden.assert_figures(totals, golden.JULY, fixture[1], fixture[4])
        require(not fixture[0].chart_template, "Synthetic fixture unexpectedly loaded a localization chart")
    evidence.append({"case": "accountant_company_switch", "result": "PASS"})
    # Assert role assignment has not inherited system/admin through defaults.
    require(not user.has_group("base.group_system"), "Fixture reader accidentally became administrator")
    # A custom restriction can make a mathematically balanced report incomplete.
    # Known expected coverage must reject it, rather than treating missing AML as 0.
    try:
        with env.cr.savepoint():
            env["ir.rule"].create({
                "name": "Golden restricted source", "model_id": env["ir.model"]._get_id("account.move.line"),
                "domain_force": f"[('account_id', '!=', {a[1]['cash'].id})]",
                "perm_read": True, "perm_write": False, "perm_create": False, "perm_unlink": False,
            })
            try:
                restricted = golden.trial_balance(reader, a, "2026-07-01", "2026-07-31", scoped_filters=False)
                golden.assert_figures(restricted, golden.JULY, a[1])
            except AssertionError as exc:
                require("Golden ledger cash" in str(exc), "Wrong restricted-source assertion")
            else:
                raise AssertionError("Restricted source incorrectly passed complete-coverage oracle")
            raise RollbackFixture()
    except RollbackFixture:
        env.invalidate_all()
        # ir.rule.create clears registry ormcache, but PostgreSQL rollback does
        # not evict domains cached while the temporary rule was active.
        env.registry.clear_cache()
    golden.assert_figures(golden.trial_balance(reader, a, "2026-07-01", "2026-07-31", scoped_filters=False), golden.JULY, a[1])
    evidence.append({"case": "restricted_source_oracle", "result": "REJECTED_BASELINE_RESTORED"})
    return evidence


NATIVE_JULY = {
    "cash": (100, 60, 30, 130), "ar": (0, 100, 80, 20),
    "ap": (0, 40, 80, -40), "revenue": (0, 20, 100, -80),
    "tax_output": (0, 0, 0, 0), "expense": (0, 80, 10, 70),
    "tax_input": (0, 0, 0, 0), "equity": (-100, 0, 0, -100),
}
NATIVE_AUGUST = {
    "cash": (130, 20, 40, 110), "ar": (20, 0, 20, 0),
    "ap": (-40, 40, 0, 0), "revenue": (-80, 0, 0, -80),
    "tax_output": (0, 0, 0, 0), "expense": (70, 0, 0, 70),
    "tax_input": (0, 0, 0, 0), "equity": (-100, 0, 0, -100),
}


def document(env, fixture, kind, journal, amount, when):
    company, accounts, _journal, partner, scale = fixture
    move = env["account.move"].with_company(company).create({
        "move_type": kind, "company_id": company.id, "journal_id": journal.id,
        "partner_id": partner.id, "invoice_date": when, "date": when,
        "invoice_date_due": when,
        "invoice_line_ids": [(0, 0, {
            "name": "Synthetic tax-free service fixture", "quantity": 1,
            "price_unit": amount * scale, "tax_ids": [(5, 0, 0)],
            "account_id": accounts["revenue" if kind.startswith("out_") else "expense"].id,
        })],
    })
    move.action_post()
    require(move.state == "posted", "Native invoice failed to post")
    return move


def payment(env, fixture, journal, amount, when, inbound):
    company, accounts, _journal, partner, scale = fixture
    method = journal.inbound_payment_method_line_ids if inbound else journal.outbound_payment_method_line_ids
    require(bool(method), "Native journal has no payment method")
    method = method[0]
    method.payment_account_id = accounts["cash"]
    pay = env["account.payment"].with_company(company).create({
        "company_id": company.id, "journal_id": journal.id,
        "payment_method_line_id": method.id, "outstanding_account_id": accounts["cash"].id,
        "partner_id": partner.id, "payment_type": "inbound" if inbound else "outbound",
        "partner_type": "customer" if inbound else "supplier",
        "amount": amount * scale, "date": when,
    })
    pay.action_post()
    require(bool(pay.move_id) and pay.move_id.state == "posted", "Payment has no posted native journal")
    return pay


def control_line(move, account):
    return move.line_ids.filtered(lambda line: line.account_id == account)


def residual_as_of(line, cutoff):
    """Independent AML/dated partial oracle, not current amount_residual."""
    require(len(line) == 1, "Expected singular control line")
    return line.balance + sum(
        p.amount for p in line.matched_debit_ids if p.max_date <= cutoff
    ) - sum(p.amount for p in line.matched_credit_ids if p.max_date <= cutoff)


def check_native_documents(env, suffix, scale):
    # Reuse company/account creation without the earlier general-journal events.
    fixture = golden.build_fixture(env, suffix, scale, events=(), draft_noise=False)
    company, accounts, _journal, partner, _scale = fixture
    partner.with_company(company).write({
        "property_account_receivable_id": accounts["ar"].id,
        "property_account_payable_id": accounts["ap"].id,
    })
    journals = {}
    for kind in ("sale", "purchase", "cash"):
        journals[kind] = env["account.journal"].with_company(company).create({
            "name": f"Golden {suffix} {kind}", "code": f"{suffix}{kind[:2]}",
            "type": kind, "company_id": company.id,
            **({"default_account_id": accounts["cash"].id} if kind == "cash" else {}),
        })
    golden.make_entry(env, fixture, "native_opening", "2026-06-30", {"cash": 100, "equity": -100})
    invoice = document(env, fixture, "out_invoice", journals["sale"], 100, "2026-07-01")
    refund = document(env, fixture, "out_refund", journals["sale"], 20, "2026-07-20")
    bill = document(env, fixture, "in_invoice", journals["purchase"], 80, "2026-07-02")
    vendor_refund = document(env, fixture, "in_refund", journals["purchase"], 10, "2026-07-21")
    receipt = payment(env, fixture, journals["cash"], 60, "2026-07-15", True)
    outgoing = payment(env, fixture, journals["cash"], 30, "2026-07-16", False)
    ar = control_line(invoice, accounts["ar"])
    ap = control_line(bill, accounts["ap"])
    (ar | control_line(refund, accounts["ar"]) | control_line(receipt.move_id, accounts["ar"])).reconcile()
    (ap | control_line(vendor_refund, accounts["ap"]) | control_line(outgoing.move_id, accounts["ap"])).reconcile()
    require(invoice.amount_residual == 20 * scale, "Invoice partial residual mismatch")
    require(bill.amount_residual == 40 * scale, "Bill partial residual mismatch")
    require(refund.amount_residual == vendor_refund.amount_residual == 0, "Credits not reconciled")
    golden.assert_figures(golden.trial_balance(env, fixture, "2026-07-01", "2026-07-31", scoped_filters=False), NATIVE_JULY, accounts, scale)

    aug_receipt = payment(env, fixture, journals["cash"], 20, "2026-08-01", True)
    aug_outgoing = payment(env, fixture, journals["cash"], 40, "2026-08-02", False)
    (ar | control_line(aug_receipt.move_id, accounts["ar"])).reconcile()
    (ap | control_line(aug_outgoing.move_id, accounts["ap"])).reconcile()
    require(invoice.amount_residual == bill.amount_residual == 0, "August settlement incomplete")
    require(residual_as_of(ar, date(2026, 7, 31)) == 20 * scale, "Historical AR leaked August reconciliation")
    require(residual_as_of(ap, date(2026, 7, 31)) == -40 * scale, "Historical AP leaked August reconciliation")
    require(residual_as_of(ar, date(2026, 8, 31)) == residual_as_of(ap, date(2026, 8, 31)) == 0, "Settled historical residual mismatch")
    for start, end, expected in (
        ("2026-07-01", "2026-07-31", NATIVE_JULY),
        ("2026-08-01", "2026-08-31", NATIVE_AUGUST),
    ):
        golden.assert_figures(golden.trial_balance(env, fixture, start, end, scoped_filters=False), expected, accounts, scale)

    # Unreconcile is not a ledger reversal: TB must remain identical but residual changes.
    try:
        with env.cr.savepoint():
            ar.remove_move_reconcile()
            require(invoice.amount_residual == 100 * scale, "Unreconcile did not restore invoice residual")
            golden.assert_figures(golden.trial_balance(env, fixture, "2026-07-01", "2026-07-31", scoped_filters=False), NATIVE_JULY, accounts, scale)
            raise RollbackFixture()
    except RollbackFixture:
        env.invalidate_all()
    require(invoice.amount_residual == 0, "Reconciliation rollback did not restore settlement")
    partner.active = False
    golden.assert_figures(golden.trial_balance(env, fixture, "2026-07-01", "2026-07-31", scoped_filters=False), NATIVE_JULY, accounts, scale)
    return {"company": company.name, "scale": scale, "native_invoice_refunds_payments": "PASS", "as_of_partial_dates": "PASS", "unreconcile_rollback": "PASS", "archived_partner": "PASS"}


def run(env):
    require(env.cr.dbname == "finance_i0_reports_disposable", "Extended ledger requires exact disposable reports database")
    require(env["ir.module.module"].search_count([("name", "=", "id_finance_reporting"), ("state", "=", "installed")]) == 1,
            "Finance reporting boundary addon must be installed; no silent missing guard")
    evidence = {"scope": "I0 ledger/security package, not full FIN01-58 acceptance"}
    companies_before = set(env["res.company"].search([]).ids)
    users_before = set(env["res.users"].with_context(active_test=False).search([]).ids)
    try:
        with env.cr.savepoint():
            fixtures = [golden.build_fixture(env, "A", 1), golden.build_fixture(env, "B", 7)]
            evidence["security"] = check_roles_and_scope(env, fixtures)
            evidence["native"] = [check_native_documents(env, "C", 1), check_native_documents(env, "D", 7)]
            raise RollbackFixture()
    except RollbackFixture:
        env.invalidate_all()
    require(set(env["res.company"].search([]).ids) == companies_before, "Company fixture leakage")
    require(set(env["res.users"].with_context(active_test=False).search([]).ids) == users_before, "User fixture leakage")
    evidence["fixture_rollback"] = "PASS"
    print("FINANCE_LEDGER_SECURITY=" + json.dumps(evidence, sort_keys=True))
    print("FINANCE_LEDGER_SECURITY=PASS")
    return evidence


if "env" in globals():
    run(globals()["env"])
