#!/usr/bin/env python3
"""Disposable-only I0 ledger fixture and real OCA Trial Balance counterexamples.

Run in Odoo shell after installing account_financial_report. No fixture is
committed. These general-journal cases are not invoice/tax/stock acceptance.
"""

import json


# Independently specified figures: opening, period debit, period credit, closing.
JULY = {
    "cash": (100, 60, 25, 135),
    "ar": (0, 110, 82, 28),
    "ap": (0, 25, 55, -30),
    "revenue": (0, 20, 100, -80),
    "tax_output": (0, 2, 10, -8),
    "expense": (0, 50, 0, 50),
    "tax_input": (0, 5, 0, 5),
    "equity": (-100, 0, 0, -100),
}
AUGUST = {
    "cash": (135, 28, 30, 133),
    "ar": (28, 0, 28, 0),
    "ap": (-30, 30, 0, 0),
    "revenue": (-80, 0, 0, -80),
    "tax_output": (-8, 0, 0, -8),
    "expense": (50, 0, 0, 50),
    "tax_input": (5, 0, 0, 5),
    "equity": (-100, 0, 0, -100),
}
ACCOUNT_TYPES = {
    "cash": "asset_cash", "ar": "asset_receivable", "ap": "liability_payable",
    "revenue": "income", "tax_output": "liability_current", "expense": "expense",
    "tax_input": "asset_current", "equity": "equity",
}
EVENTS = (
    ("opening", "2026-06-30", {"cash": 100, "equity": -100}),
    ("sale_ledger", "2026-07-01", {"ar": 110, "revenue": -100, "tax_output": -10}),
    ("receipt", "2026-07-15", {"cash": 60, "ar": -60}),
    ("credit_ledger", "2026-07-20", {"revenue": 20, "tax_output": 2, "ar": -22}),
    ("purchase_ledger", "2026-07-25", {"expense": 50, "tax_input": 5, "ap": -55}),
    ("supplier_payment", "2026-07-31", {"ap": 25, "cash": -25}),
    ("aug_receipt", "2026-08-01", {"cash": 28, "ar": -28}),
    ("aug_payment", "2026-08-02", {"ap": 30, "cash": -30}),
)


def assert_figures(actual, expected, accounts, scale=1):
    """Fail on missing/extra accounts and every independently specified amount."""
    if set(actual) != {account.id for account in accounts.values()}:
        raise AssertionError("Golden ledger account coverage mismatch")
    for key, figures in expected.items():
        row = actual[accounts[key].id]
        observed = tuple(row[name] for name in (
            "initial_balance", "debit", "credit", "ending_balance",
        ))
        wanted = tuple(value * scale for value in figures)
        if observed != wanted:
            raise AssertionError(f"Golden ledger {key}: expected {wanted}, got {observed}")


def make_entry(env, fixture, label, date, balances, posted=True):
    company, accounts, journal, partner, scale = fixture
    move = env["account.move"].with_company(company).create({
        "company_id": company.id, "journal_id": journal.id, "date": date,
        "ref": f"FINANCE-GOLDEN-{label}", "move_type": "entry",
        "line_ids": [(0, 0, {
            "name": f"Synthetic ledger fixture: {label}",
            "account_id": accounts[key].id,
            "partner_id": partner.id if key in ("ar", "ap") else False,
            "date_maturity": date if key in ("ar", "ap") else False,
            "debit": max(value * scale, 0), "credit": max(-value * scale, 0),
        }) for key, value in balances.items()],
    })
    if posted:
        move.action_post()
    return move


def build_fixture(env, suffix, scale):
    currency = env.ref("base.IDR")
    currency.active = True
    company = env["res.company"].create({
        "name": f"FINANCE GOLDEN {suffix}", "currency_id": currency.id,
        "country_id": env.ref("base.id").id,
    })
    accounts = {}
    for index, (key, account_type) in enumerate(ACCOUNT_TYPES.items()):
        accounts[key] = env["account.account"].with_company(company).create({
            "name": f"Golden {suffix} {key}", "code": f"FG{suffix}{index:03}",
            "account_type": account_type, "company_ids": [(6, 0, company.ids)],
            "reconcile": key in ("ar", "ap"),
        })
    journal = env["account.journal"].with_company(company).create({
        "name": f"Golden {suffix}", "code": f"FG{suffix}",
        "type": "general", "company_id": company.id,
    })
    partner = env["res.partner"].create({"name": f"Golden partner {suffix}", "company_id": company.id})
    fixture = company, accounts, journal, partner, scale
    for label, date, balances in EVENTS:
        make_entry(env, fixture, label, date, balances)
    make_entry(env, fixture, "draft_noise", "2026-07-31", {"cash": 999, "equity": -999}, posted=False)
    return fixture


def trial_balance(env, fixture, date_from, date_to, posted=True):
    company, accounts, journal, _partner, _scale = fixture
    report = env["report.account_financial_report.trial_balance"].with_company(company)
    totals, _accounts_data, _partners = report._get_data(
        account_ids=[account.id for account in accounts.values()], journal_ids=journal.ids,
        partner_ids=[], company_id=company.id, date_to=date_to, date_from=date_from,
        foreign_currency=False, only_posted_moves=posted, show_partner_details=False,
        hide_account_at_0=False, unaffected_earnings_account=False,
        fy_start_date="2026-01-01", grouped_by=False,
    )
    return totals


def run(env):
    if env.cr.dbname != "finance_i0_reports_disposable":
        raise RuntimeError("Golden ledger requires exact disposable reports database")
    if "report.account_financial_report.trial_balance" not in env:
        raise RuntimeError("OCA Trial Balance must be installed; no fallback oracle")

    class FixtureRollback(Exception):
        pass

    evidence = {"scope": "I0 minimal general-journal oracle; not FIN02 accepted", "cases": []}
    try:
        with env.cr.savepoint():
            fixtures = [build_fixture(env, "A", 1), build_fixture(env, "B", 7)]
            for fixture in fixtures:
                company, accounts, _journal, _partner, scale = fixture
                for date_from, date_to, expected in (
                    ("2026-07-01", "2026-07-31", JULY),
                    ("2026-08-01", "2026-08-31", AUGUST),
                ):
                    totals = trial_balance(env, fixture, date_from, date_to)
                    assert_figures(totals, expected, accounts, scale)
                    if sum(row["debit"] for row in totals.values()) != sum(row["credit"] for row in totals.values()):
                        raise AssertionError("Unbalanced Trial Balance period totals")
                    evidence["cases"].append({"company": company.name, "from": date_from, "to": date_to, "result": "PASS"})
                draft = dict(JULY)
                draft["cash"] = (100, 1059, 25, 1134)
                draft["equity"] = (-100, 0, 999, -1099)
                assert_figures(trial_balance(env, fixture, "2026-07-01", "2026-07-31", posted=False), draft, accounts, scale)

            # Call the actual OCA report before, during and after a balanced mutation.
            fixture = fixtures[0]
            try:
                with env.cr.savepoint():
                    make_entry(env, fixture, "balanced_wrong_value", "2026-07-31", {"cash": 1, "equity": -1})
                    try:
                        assert_figures(trial_balance(env, fixture, "2026-07-01", "2026-07-31"), JULY, fixture[1])
                    except AssertionError as exc:
                        if "Golden ledger cash" not in str(exc):
                            raise
                    else:
                        raise AssertionError("Balanced mutation unexpectedly accepted")
                    raise FixtureRollback()
            except FixtureRollback:
                env.invalidate_all()
            assert_figures(trial_balance(env, fixture, "2026-07-01", "2026-07-31"), JULY, fixture[1])
            evidence["balanced_mutation"] = "REJECTED_BASELINE_RESTORED"
            raise FixtureRollback()
    except FixtureRollback:
        env.invalidate_all()
    if env["res.company"].search_count([("name", "in", ["FINANCE GOLDEN A", "FINANCE GOLDEN B"])]):
        raise AssertionError("Golden fixture leaked after rollback")
    evidence["fixture_rollback"] = "PASS"
    print("FINANCE_GOLDEN_LEDGER=" + json.dumps(evidence, sort_keys=True))
    print("FINANCE_GOLDEN_LEDGER=PASS")
    return evidence


if "env" in globals():
    run(globals()["env"])
