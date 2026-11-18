#!/usr/bin/env python3
"""Runtime proof of the I2-3 demo activation block in deploy/init.sh (CI only).

Executed with ``odoo shell`` after a boot of ``deploy/init.sh``. Read-only: it
proves that the marked activation blocks installed the two finance modules,
gave the Finance Reader role to the demo admin only, and left the custom report
menu reachable. It never writes, posts, or commits, and it does not change any
catalog status.
"""

import json

from lxml import etree


EXPECTED_MODULES = ("id_finance_reporting", "id_finance_foundation")
READER_GROUP = "id_finance_foundation.group_finance_reader"
READER_MENU = "id_finance_foundation.menu_finance_reports"
REPORT_MENU = "id_finance_foundation.menu_finance_report_audit_trail"
ACTION = "id_finance_reporting.action_finance_report_audit_trail"
WIZARD_MODEL = "id.finance.report.wizard"
WIZARD_VIEW = "id_finance_reporting.view_finance_report_wizard_form"
HEADER_BUTTONS = ("action_run", "action_export_xlsx")
REPORT_ACTIONS = (
    "id_finance_reporting.action_finance_report_audit_trail",
    "id_finance_reporting.action_finance_report_partner_ledger",
    "id_finance_reporting.action_finance_report_open_items",
    "id_finance_reporting.action_finance_report_aged_partner_balance",
    "id_finance_reporting.action_finance_report_combined_trial_balance",
    "id_finance_reporting.action_finance_report_sales_purchase_register",
    "id_finance_reporting.action_finance_report_accrual_schedule",
    "id_finance_reporting.action_finance_report_fx_revaluation",
)


def field_name(record, *names):
    for name in names:
        if name in record._fields:
            return name
    raise AssertionError(f"None of the fields {names} exist on {record._name}")


def button_names(element):
    if element is None:
        return set()
    return {button.get("name") for button in element.iter("button") if button.get("name")}


def check_wizard_buttons(env):
    """The Run/Export buttons must live in <header> for target="current" actions.

    Odoo 19 renders <footer> only when ``env.inDialog`` is true, and that is
    derived from ``target="new"``. All eight finance actions open a full page,
    so a footer button would be invisible and the UAT run step unreachable.
    """
    view = env.ref(WIZARD_VIEW, raise_if_not_found=False)
    if not view:
        raise AssertionError("Finance report wizard view is missing")
    resolved = env[WIZARD_MODEL].get_view(view_id=view.id, view_type="form")
    arch = etree.fromstring(resolved["arch"].encode())

    header = arch.find("header")
    if header is None:
        raise AssertionError("Finance report wizard has no <header> block")
    header_buttons = button_names(header)
    missing = [name for name in HEADER_BUTTONS if name not in header_buttons]
    if missing:
        raise AssertionError(f"Wizard header lost its buttons: {missing}")

    footer_buttons = button_names(arch.find("footer"))
    duplicated = sorted(set(HEADER_BUTTONS) & footer_buttons)
    if duplicated:
        raise AssertionError(f"Wizard buttons are duplicated in <footer>: {duplicated}")

    targets = {}
    for xmlid in REPORT_ACTIONS:
        action = env.ref(xmlid, raise_if_not_found=False)
        if not action:
            raise AssertionError(f"Finance report action is missing: {xmlid}")
        if action.res_model != WIZARD_MODEL or "form" not in (action.view_mode or ""):
            raise AssertionError(f"Finance report action does not open the wizard form: {xmlid}")
        target = action.target or "current"
        targets[xmlid] = target
        if target != "current":
            raise AssertionError(
                f"Finance report action {xmlid} uses target={target!r}; "
                "the wizard is a full page, so it must stay 'current'"
            )
    return {
        "header_buttons": sorted(header_buttons),
        "footer_buttons": sorted(footer_buttons),
        "action_targets": targets,
    }


def run(env):
    if env.cr.dbname != "fmcg":
        raise AssertionError("Activation proof requires the exact init.sh database")

    modules = env["ir.module.module"].search([("name", "in", list(EXPECTED_MODULES))])
    states = {module.name: module.state for module in modules}
    missing = {name: states.get(name) for name in EXPECTED_MODULES if states.get(name) != "installed"}
    if missing:
        raise AssertionError(f"Finance modules are not installed: {missing}")

    group = env.ref(READER_GROUP, raise_if_not_found=False)
    if not group:
        raise AssertionError("Finance Reader group is missing")
    if env.ref("account.group_account_readonly", raise_if_not_found=False) not in group.implied_ids:
        raise AssertionError("Finance Reader no longer implies account.group_account_readonly")

    admin = env.ref("base.user_admin", raise_if_not_found=False)
    if not admin:
        raise AssertionError("Demo admin user is missing")
    if not admin.has_group(READER_GROUP):
        raise AssertionError("Demo admin does not have the Finance Reader role")

    menu = env.ref(READER_MENU, raise_if_not_found=False)
    if not menu:
        raise AssertionError("Finance Reports menu is missing")
    if group not in menu[field_name(menu, "group_ids", "groups_id")]:
        raise AssertionError("Finance Reports menu is not restricted to the Finance Reader role")

    report_menu = env.ref(REPORT_MENU, raise_if_not_found=False)
    if not report_menu or not report_menu.action:
        raise AssertionError("A custom finance report menu lost its action")
    if report_menu.action.id != env.ref(ACTION).id:
        raise AssertionError("Custom finance report menu points at an unexpected action")

    wizard = check_wizard_buttons(env)

    others = env["res.users"].search([
        ("id", "!=", admin.id),
        (field_name(admin, "group_ids", "groups_id"), "in", group.id),
    ])
    if others:
        raise AssertionError(f"Finance Reader leaked to other users: {others.mapped('login')}")

    print("INIT_FINANCE_ACTIVATION=" + json.dumps({
        "modules": states,
        "reader_group": group.name,
        "admin": admin.login,
        "menu": menu.complete_name,
        "report_menu_action": report_menu.action.name,
        "wizard": wizard,
        "other_reader_users": [],
    }, sort_keys=True))
    print("INIT_FINANCE_ACTIVATION=PASS")


if "env" in globals():
    run(globals()["env"])
