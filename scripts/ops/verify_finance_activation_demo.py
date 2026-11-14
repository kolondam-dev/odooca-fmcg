#!/usr/bin/env python3
"""Runtime proof of the I2-3 demo activation block in deploy/init.sh (CI only).

Executed with ``odoo shell`` after a boot of ``deploy/init.sh``. Read-only: it
proves that the marked activation blocks installed the two finance modules,
gave the Finance Reader role to the demo admin only, and left the custom report
menu reachable. It never writes, posts, or commits, and it does not change any
catalog status.
"""

import json


EXPECTED_MODULES = ("id_finance_reporting", "id_finance_foundation")
READER_GROUP = "id_finance_foundation.group_finance_reader"
READER_MENU = "id_finance_foundation.menu_finance_reports"
REPORT_MENU = "id_finance_foundation.menu_finance_report_audit_trail"
ACTION = "id_finance_reporting.action_finance_report_audit_trail"


def field_name(record, *names):
    for name in names:
        if name in record._fields:
            return name
    raise AssertionError(f"None of the fields {names} exist on {record._name}")


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
        "other_reader_users": [],
    }, sort_keys=True))
    print("INIT_FINANCE_ACTIVATION=PASS")


if "env" in globals():
    run(globals()["env"])
