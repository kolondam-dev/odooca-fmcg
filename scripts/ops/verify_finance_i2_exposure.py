#!/usr/bin/env python3
"""Exposure evidence for the I2 finance report wizard (ACL, UI, role denials).

Run inside ``odoo shell`` on the disposable reports database. The report
services covered by I2a/I2b/I2c already have numeric oracles; this script only
proves the part those oracles cannot see:

* every custom report type can actually be executed from the UI entry point;
* stored report markup is sanitized server-side even on a direct ORM write;
* the actions, menus and views needed to open it exist;
* an accounting reader can run them, while Sales and Driver cannot.

All fixtures are rolled back. No report is posted, mutated or exported, and no
catalog status is changed.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent) if "__file__" in globals() else "/opt/scripts/ops")
import verify_finance_golden_ledger as golden  # noqa: E402

DISPOSABLE_DB = "finance_i0_reports_disposable"

# report_type -> (filters, expected report_id values)
REPORT_SPECS = {
    "audit_trail": (
        {"date_from": "2026-07-01", "date_to": "2026-07-31"},
        {"FIN04"},
    ),
    "partner_ledger": (
        {"date_from": "2026-07-01", "date_to": "2026-07-31", "partner_type": "customer"},
        {"FIN05"},
    ),
    "open_items": (
        {"as_of_date": "2026-07-31", "partner_type": "customer"},
        {"FIN07"},
    ),
    "aged_partner_balance": (
        {"as_of_date": "2026-07-31", "partner_type": "customer"},
        {"FIN08"},
    ),
    "combined_trial_balance": (
        {"date_from": "2026-07-01", "date_to": "2026-07-31"},
        {"FIN51"},
    ),
    "sales_purchase_register": (
        {"date_from": "2026-07-01", "date_to": "2026-07-31"},
        {"FIN57"},
    ),
    "accrual_schedule": (
        {"as_of_date": "2026-07-31"},
        {"FIN37"},
    ),
    "fx_revaluation": (
        {"as_of_date": "2026-07-31"},
        {"FIN38"},
    ),
}

ACTIONS = {
    "audit_trail": "action_finance_report_audit_trail",
    "partner_ledger": "action_finance_report_partner_ledger",
    "open_items": "action_finance_report_open_items",
    "aged_partner_balance": "action_finance_report_aged_partner_balance",
    "combined_trial_balance": "action_finance_report_combined_trial_balance",
    "sales_purchase_register": "action_finance_report_sales_purchase_register",
    "accrual_schedule": "action_finance_report_accrual_schedule",
    "fx_revaluation": "action_finance_report_fx_revaluation",
}

MENUS = {
    "audit_trail": "menu_finance_report_audit_trail",
    "partner_ledger": "menu_finance_report_partner_ledger",
    "open_items": "menu_finance_report_open_items",
    "aged_partner_balance": "menu_finance_report_aged_partner_balance",
    "combined_trial_balance": "menu_finance_report_combined_trial_balance",
    "sales_purchase_register": "menu_finance_report_sales_purchase_register",
    "accrual_schedule": "menu_finance_report_accrual_schedule",
    "fx_revaluation": "menu_finance_report_fx_revaluation",
}


class RollbackFixture(Exception):
    pass


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def denied(callback, label):
    from odoo.exceptions import AccessError

    try:
        callback()
    except AccessError:
        return {"case": label, "result": "ACCESS_DENIED"}
    raise AssertionError(f"Expected AccessError: {label}")


def actor(env, name, company, groups):
    user = env["res.users"].with_context(no_reset_password=True, mail_create_nolog=True).create({
        "name": f"Finance exposure fixture {name}",
        "login": f"finance.exposure.{name}",
        "company_id": company.id,
        "company_ids": [(6, 0, company.ids)],
        "group_ids": [(6, 0, [env.ref(group).id for group in ["base.group_user", *groups]])],
    })
    user_env = env["id.finance.report.wizard"].with_user(user).sudo(False).with_context(
        allowed_company_ids=company.ids,
    ).env
    require(not user_env.su, f"Role probe {name} must never execute as superuser")
    return user, user_env


def wizard(env, company, report_type, overrides=None):
    values = {
        "report_type": report_type,
        "company_id": company.id,
        "company_ids": [(6, 0, company.ids)],
    }
    values.update(overrides or {})
    return env["id.finance.report.wizard"].with_context(
        allowed_company_ids=company.ids,
    ).create(values)


def check_ui_surface(env):
    require(
        env["ir.module.module"].search_count([
            ("name", "=", "id_finance_reporting"), ("state", "=", "installed"),
        ]) == 1,
        "id_finance_reporting must be installed before exposure evidence",
    )
    selection = dict(env["id.finance.report.wizard"]._fields["report_type"].selection)
    require(set(selection) == set(REPORT_SPECS), f"Wizard report types drifted: {sorted(selection)}")

    report_menu = env.ref("id_finance_foundation.menu_finance_reports")
    require(env.ref("id_finance_foundation.group_finance_reader") in report_menu.group_ids,
            "Finance Reports menu is not restricted to Finance Reader")
    require(env.ref("id_finance_foundation.menu_finance").id in report_menu.parent_id.ids,
            "Finance Reports menu is not hosted under the Finance app")

    evidence = []
    for report_type in sorted(REPORT_SPECS):
        action = env.ref(f"id_finance_reporting.{ACTIONS[report_type]}")
        require(action.res_model == "id.finance.report.wizard", f"{report_type}: wrong action model")
        require(action.view_mode == "form", f"{report_type}: action is not a form entry point")
        menu = env.ref(f"id_finance_foundation.{MENUS[report_type]}")
        require(menu.action.id == action.id, f"{report_type}: menu does not open its action")
        require(menu.parent_id.id == report_menu.id, f"{report_type}: menu is not under Finance Reports")
        evidence.append({"case": f"menu_action_{report_type}", "result": "PASS"})
    view = env.ref("id_finance_reporting.view_finance_report_wizard_form")
    require(view.model == "id.finance.report.wizard", "Wizard form view targets the wrong model")
    require(view.type == "form", "Wizard view is not a form")
    evidence.append({"case": "wizard_form_view", "result": "PASS"})
    return evidence


def check_wizard_runs(env, company):
    evidence = []
    for report_type, (filters, expected_ids) in REPORT_SPECS.items():
        overrides = dict(filters)
        record = wizard(env, company, report_type, overrides)
        action = record.action_run()
        require(action.get("res_model") == "id.finance.report.wizard", f"{report_type}: run did not reopen the form")
        require(bool(record.result_html), f"{report_type}: preview HTML is empty")
        require("<script" not in record.result_html.lower(), f"{report_type}: preview is not escaped")
        payload = json.loads(record.result_json)
        require(payload.get("report_id") in expected_ids,
                f"{report_type}: unexpected report_id {payload.get('report_id')}")
        expected = sorted(expected_ids)[0]
        require(isinstance(record.result_summary, str) and expected in record.result_summary,
                f"{report_type}: summary does not name the report")
        evidence.append({"case": f"wizard_run_{report_type}", "result": "PASS"})
    return evidence


def check_roles(env, company):
    _reader_user, reader = actor(env, "reader", company, ["account.group_account_readonly"])
    _sales_user, sales = actor(env, "sales", company, ["sales_team.group_sale_salesman"])
    _driver_user, driver = actor(env, "driver", company, ["id_mobile_api.group_mobile_evidence"])

    evidence = []
    allowed = wizard(reader, company, "audit_trail", {"date_from": "2026-07-01", "date_to": "2026-07-31"})
    allowed.action_run()
    require(bool(allowed.result_html), "Finance Reader could not run the audit trail report")
    evidence.append({"case": "reader_can_run", "result": "PASS"})

    for label, user_env in (("sales", sales), ("driver", driver)):
        evidence.append(denied(
            lambda e=user_env: wizard(e, company, "audit_trail", {"date_from": "2026-07-01", "date_to": "2026-07-31"}).action_run(),
            f"{label}_wizard_denied",
        ))
        evidence.append(denied(
            lambda e=user_env: e["id.finance.audit.trail"]._snapshot(
                company_id=company.id, date_from="2026-07-01", date_to="2026-07-31",
            ),
            f"{label}_service_denied",
        ))

    foreign = env["res.company"].create({"name": "FINANCE EXPOSURE FOREIGN"})
    evidence.append(denied(
        lambda: reader["id.finance.audit.trail"]._snapshot(
            company_id=foreign.id, date_from="2026-07-01", date_to="2026-07-31",
        ),
        "reader_foreign_company_denied",
    ))
    return evidence


def check_html_sanitization(env, company):
    """A direct ORM write must not persist active markup for a Finance Reader.

    ``readonly`` only locks the form widget, and the Accounting Readonly group
    holds create/write on this transient model, so the field itself must
    sanitize. The report preview must still keep its whitelisted table tags.
    """
    _user, reader = actor(env, "html_reader", company, ["account.group_account_readonly"])
    field = env["id.finance.report.wizard"]._fields["result_html"]
    require(getattr(field, "sanitize", False) is True, "result_html must sanitize stored markup")

    record = wizard(reader, company, "audit_trail", {"date_from": "2026-07-01", "date_to": "2026-07-31"})
    markup = (
        "<script>alert('xss')</script>"
        "<img src=x onerror=\"alert('xss')\">"
        "<a href=\"javascript:alert('xss')\">go</a>"
        "<table class=\"table\"><tbody><tr><td>report-cell</td></tr></tbody></table>"
    )
    record.write({"result_html": markup})
    record.invalidate_recordset(["result_html"])
    stored = (record.result_html or "").lower()
    for needle in ("<script", "onerror", "javascript:"):
        require(needle not in stored, f"Sanitizer kept active markup: {needle}")
    require("<table" in stored, "Sanitizer removed the report table")
    require("report-cell" in stored, "Sanitizer removed the report cell text")

    preview = wizard(reader, company, "audit_trail", {"date_from": "2026-07-01", "date_to": "2026-07-31"})
    preview.action_run()
    require("<table" in (preview.result_html or "").lower(), "Reader preview lost its report table")
    return [
        {"case": "reader_direct_write_sanitized", "result": "PASS"},
        {"case": "reader_preview_keeps_table", "result": "PASS"},
    ]


def run(env):
    require(env.cr.dbname == DISPOSABLE_DB, "Exposure evidence requires the exact disposable reports database")
    companies_before = set(env["res.company"].search([]).ids)
    users_before = set(env["res.users"].with_context(active_test=False).search([]).ids)
    evidence = {"scope": "I2 exposure only: ACL, menu, action, view and role denial; not FIN01-58 acceptance"}
    try:
        with env.cr.savepoint():
            evidence["surface"] = check_ui_surface(env)
            fixture = golden.build_fixture(env, "E", 1)
            company = fixture[0]
            evidence["runs"] = check_wizard_runs(env, company)
            evidence["roles"] = check_roles(env, company)
            evidence["sanitization"] = check_html_sanitization(env, company)
            raise RollbackFixture()
    except RollbackFixture:
        env.invalidate_all()
    require(set(env["res.company"].search([]).ids) == companies_before, "Company fixture leakage")
    require(set(env["res.users"].with_context(active_test=False).search([]).ids) == users_before, "User fixture leakage")
    evidence["fixture_rollback"] = "PASS"
    print("FINANCE_I2_EXPOSURE=" + json.dumps(evidence, sort_keys=True))
    print("FINANCE_I2_EXPOSURE=PASS")
    return evidence


if "env" in globals():
    run(globals()["env"])
