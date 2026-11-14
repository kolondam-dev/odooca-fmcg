#!/usr/bin/env python3
"""Exposure evidence for the I2 finance report wizard (ACL, UI, role denials).

Run inside ``odoo shell`` on the disposable reports database. The report
services covered by I2a/I2b/I2c already have numeric oracles; this script only
proves the part those oracles cannot see:

* every custom report type can actually be executed from the UI entry point;
* stored report markup is sanitized server-side even on a direct ORM write;
* every report type produces a downloadable XLSX workbook whose text cells are
  inert (a leading ``=``, ``+``, ``-``, ``@``, tab or carriage return is quoted)
  and whose numeric cells stay numeric;
* the actions, menus and views needed to open it exist;
* an accounting reader can run them, while Sales and Driver cannot.

All fixtures are rolled back. No report is posted, mutated or exported, and no
catalog status is changed.
"""

import base64
import json
import re
import sys
import xml.etree.ElementTree as ElementTree
import zipfile
from io import BytesIO
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


def _xlsx_parts(payload):
    """Return the workbook, shared strings and worksheets of an XLSX blob."""
    require(payload[:2] == b"PK", "XLSX export is not a ZIP archive")
    parts = {}
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        names = archive.namelist()
        require("xl/workbook.xml" in names, "XLSX workbook part is missing")
        for name in names:
            if name.startswith("xl/") and name.endswith(".xml"):
                parts[name] = archive.read(name)
    for name, data in parts.items():
        try:
            ElementTree.fromstring(data)
        except ElementTree.ParseError as exc:
            raise AssertionError(f"XLSX part is not well-formed XML: {name}") from exc
    workbook = parts["xl/workbook.xml"].decode("utf-8")
    shared = parts.get("xl/sharedStrings.xml", b"").decode("utf-8")
    sheets = {
        name: data.decode("utf-8")
        for name, data in parts.items()
        if name.startswith("xl/worksheets/sheet")
    }
    require(bool(sheets), "XLSX has no worksheet")
    return workbook, shared, sheets


def check_xlsx_completeness(env, company):
    """The workbook and payload must not promise or lose nested values silently."""
    from odoo.addons.id_finance_reporting.wizards.finance_report_wizard import (
        MAX_JSON_CHARS,
        MAX_XLSX_CELL_CHARS,
        NESTED_COLUMN,
    )

    record = wizard(env, company, "audit_trail", {"date_from": "2026-07-01", "date_to": "2026-07-31"})
    evidence = []

    long_label = "L" * 600
    rows = [{"line_id": index, "label": f"{long_label}{index}", "amount": index} for index in range(400)]
    tail = [{"id": 999001, "label": "NESTED-TAIL-MARKER", "detail": {"nested": "NESTED-TAIL-VALUE"}}]
    wide = [{"id": 999002, "detail": {"payload": "W" * (MAX_XLSX_CELL_CHARS + 500)}}]
    snapshot = {
        "report_id": "FIN99",
        "company_id": company.id,
        "currency_id": company.currency_id.id,
        "date_from": "2026-07-01",
        "date_to": "2026-07-31",
        "rows": rows,
        "tail": tail,
        "wide": wide,
    }
    full = json.dumps(snapshot, default=str, indent=1)
    require(len(full) > MAX_JSON_CHARS,
            f"Completeness fixture is not above the payload cap: {len(full)} < {MAX_JSON_CHARS}")
    require(len(rows) < 20000, "Completeness fixture must stay below the workbook row limit")

    payload = record._payload_json(snapshot)
    require(len(payload) <= MAX_JSON_CHARS, "Bounded payload exceeds its own cap")
    parsed = json.loads(payload)  # a cap must never produce invalid JSON
    truncation = parsed.get("__truncation__") or {}
    require(truncation.get("applied") is True, "Payload truncation is not disclosed")
    require("rows" in truncation.get("omitted_sections", []),
            f"Oversized section is not named as omitted: {truncation.get('omitted_sections')}")
    require("tail" in truncation.get("included_sections", []),
            f"A small trailing section was dropped although it fits: {truncation.get('included_sections')}")
    require("detail" in json.dumps(parsed.get("tail", []), default=str),
            "A trailing nested section did not survive the bounded payload")
    small = {"report_id": "FIN99", "rows": [{"id": 1}]}
    require(json.loads(record._payload_json(small)) == small,
            "Small snapshots must stay byte-for-byte equivalent")
    evidence.append({"case": "xlsx_payload_cap_valid_json", "result": "PASS"})

    blob = record._xlsx_payload(snapshot, "FIN99-completeness.xlsx")
    _workbook, shared, sheets = _xlsx_parts(blob)
    joined = "".join(sheets.values())
    require(NESTED_COLUMN in shared, f"Workbook has no '{NESTED_COLUMN}' column")
    require("NESTED-TAIL-MARKER" in shared, "A scalar cell of the trailing section is missing")
    require("NESTED-TAIL-VALUE" in shared, "A nested trailing value is missing from the workbook")
    require("available in the JSON payload" not in shared,
            "Workbook still points at a payload that may be capped")
    require("JSON payload is capped" in shared, "Workbook does not disclose the payload cap")
    evidence.append({"case": "xlsx_nested_completeness", "result": "PASS"})

    require("(truncated)" in shared, "A cell above the cell limit was not marked inside the cell")
    require("exceeded 32000 characters" in shared or "exceeded 32,000 characters" in shared,
            "Workbook does not disclose cell truncation per section")
    require("wide" in shared, "The truncated section is not named in the disclosure")
    require(joined.count("<row ") > len(rows), "Workbook rows are fewer than the fixture")
    evidence.append({"case": "xlsx_cell_truncation_disclosed", "result": "PASS"})
    return evidence


def check_xlsx_export(env, company, fixture):
    """Every report type must export a workbook that cannot run a formula."""
    from odoo.addons.id_finance_reporting.wizards.finance_report_wizard import _xlsx_text

    evidence = []
    for raw in ("=1+1", "+SUM(A1)", "-2+3", "@cmd|' /C calc'!A0", "\tvalue", "\rvalue"):
        guarded = _xlsx_text(raw)
        require(guarded.startswith("'"), f"Formula trigger was not quoted: {raw!r}")
        require(guarded[1:] == raw, f"Formula trigger text was altered: {raw!r}")
    require(_xlsx_text("safe text") == "safe text", "Plain text was changed by the guard")
    require(_xlsx_text(None) == "", "An empty value must stay empty")
    require(_xlsx_text("a\x01b") == "ab", "An illegal XML control character was kept")
    require(len(_xlsx_text("x" * 40000)) < 40000, "Long text was not bounded")
    evidence.append({"case": "xlsx_formula_guard_helper", "result": "PASS"})

    _company, accounts, journal, partner, _scale = fixture
    move = env["account.move"].with_company(company).create({
        "company_id": company.id,
        "journal_id": journal.id,
        "date": "2026-07-12",
        "ref": "=SUM(1+1)",
        "move_type": "entry",
        "line_ids": [
            (0, 0, {
                "name": "@cmd|' /C calc'!A0",
                "account_id": accounts["revenue"].id,
                "debit": 0.0,
                "credit": 7.5,
            }),
            (0, 0, {
                "name": "-7.5+1",
                "account_id": accounts["cash"].id,
                "partner_id": partner.id,
                "debit": 7.5,
                "credit": 0.0,
            }),
        ],
    })
    move.action_post()

    record = wizard(env, company, "audit_trail", {"date_from": "2026-07-01", "date_to": "2026-07-31"})
    action = record.action_export_xlsx()
    require(action.get("type") == "ir.actions.act_url", "Export did not start a download")
    url = action.get("url") or ""
    require(
        url.startswith(f"/web/content/id.finance.report.wizard/{record.id}/result_xlsx/"),
        f"Download URL does not target the wizard binary field: {url}",
    )
    require("download=true" in url, "Download URL is not a forced download")
    require(
        re.fullmatch(r"FIN04-audit-trail-2026-07-01_2026-07-31\.xlsx", record.result_filename or "") is not None,
        f"Unexpected export filename: {record.result_filename}",
    )
    payload = base64.b64decode(record.result_xlsx or b"")
    require(len(payload) > 1000, "Exported workbook is empty")
    workbook, shared, sheets = _xlsx_parts(payload)
    require("Summary" in workbook, "Workbook has no Summary sheet")
    joined = "".join(sheets.values())
    require("<f" not in joined, "Workbook contains a formula element")
    require(joined.count("<row ") > 3, "Workbook has no data rows")
    for trigger in ("=SUM(1+1)", "@cmd", "-7.5+1"):
        require(f"'{trigger}" in shared, f"Formula trigger was stored unquoted: {trigger}")
        require(f">{trigger}</t>" not in shared, f"Unquoted formula trigger reached the workbook: {trigger}")
    require("<v>7.5</v>" in joined, "The amount was not stored as a numeric cell")
    evidence.append({"case": "xlsx_formula_guard_workbook", "result": "PASS"})

    for report_type, (filters, _expected) in REPORT_SPECS.items():
        exported = wizard(env, company, report_type, dict(filters))
        result = exported.action_export_xlsx()
        require(result.get("type") == "ir.actions.act_url", f"{report_type}: export did not download")
        blob = base64.b64decode(exported.result_xlsx or b"")
        exported_book, _shared, _sheets = _xlsx_parts(blob)
        require("Summary" in exported_book, f"{report_type}: workbook has no Summary sheet")
        evidence.append({"case": f"xlsx_export_{report_type}", "result": "PASS"})

    rerun = wizard(env, company, "audit_trail", {"date_from": "2026-07-01", "date_to": "2026-07-31"})
    rerun.action_export_xlsx()
    require(bool(rerun.result_xlsx), "Export produced no workbook")
    rerun.action_run()
    require(not rerun.result_xlsx and not rerun.result_filename,
            "A re-run kept the previous workbook downloadable")
    evidence.append({"case": "xlsx_cleared_on_rerun", "result": "PASS"})

    _reader_user, reader = actor(env, "xlsx_reader", company, ["account.group_account_readonly"])
    reader_record = wizard(reader, company, "audit_trail", {"date_from": "2026-07-01", "date_to": "2026-07-31"})
    reader_record.action_export_xlsx()
    require(bool(reader_record.result_xlsx), "Finance Reader could not export the workbook")
    evidence.append({"case": "reader_can_export_xlsx", "result": "PASS"})

    _sales_user, sales = actor(env, "xlsx_sales", company, ["sales_team.group_sale_salesman"])
    evidence.append(denied(
        lambda e=sales: wizard(
            e, company, "audit_trail", {"date_from": "2026-07-01", "date_to": "2026-07-31"},
        ).action_export_xlsx(),
        "sales_export_denied",
    ))
    return evidence


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
            evidence["xlsx"] = check_xlsx_export(env, company, fixture)
            evidence["completeness"] = check_xlsx_completeness(env, company)
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
