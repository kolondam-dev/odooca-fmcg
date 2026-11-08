#!/usr/bin/env python3
"""Explicit versioned profile planner/attestation, executed in Odoo shell.

Never installs modules or commits. Caller runs normal CLI -i/-u in maintenance;
attest only records verified registry versions. Not wired into init.sh.
"""

import json

PROFILE = "finance_reports_v1"
MODULES = ("account_usability", "account_financial_report", "id_finance_reporting", "id_finance_foundation")
KEY = "id_finance.activation.finance_reports_v1"


def plan(env, profile=PROFILE):
    if profile != PROFILE:
        raise ValueError("Unknown finance profile")
    found = {}
    pending = set(MODULES)
    while pending:
        modules = env["ir.module.module"].search([("name", "in", sorted(pending))])
        batch = {module.name: module for module in modules}
        missing = pending - set(batch)
        if missing:
            raise RuntimeError(f"Profile sources missing from registry: {sorted(missing)}")
        found.update(batch)
        pending = {name for module in modules for name in module.dependencies_id.mapped("name")} - set(found)
    return {"profile": profile, "modules": [
        {"name": name, "state": found[name].state, "version": found[name].latest_version}
        for name in sorted(found)], "requested_modules": list(MODULES),
        "activation": "explicit_operator_only_no_costing_or_chart_changes"}


def attest(env, profile=PROFILE):
    if not env.su:
        raise PermissionError("Finance activation attestation requires a maintenance superuser")
    payload = plan(env, profile)
    if any(row["state"] != "installed" for row in payload["modules"]):
        raise RuntimeError("Cannot attest an incompletely installed finance profile")
    value = json.dumps(payload, sort_keys=True)
    params = env["ir.config_parameter"]
    previous = params.get_param(KEY)
    if previous == value:
        return {"result": "UNCHANGED", "profile": profile}
    if previous:
        raise RuntimeError("Activation version drift: use a reviewed new profile version")
    params.set_param(KEY, value)
    return {"result": "RECORDED", "profile": profile}
