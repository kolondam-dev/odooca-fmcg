#!/usr/bin/env python3
"""Persisted finance install/upgrade preservation and native role probes (CI only)."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path


def load(name):
    root = Path(__file__).resolve().parent if "__file__" in globals() else Path("/opt/scripts/ops")
    spec = importlib.util.spec_from_file_location(name, root / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fingerprint(env):
    # Read-only SQL in a disposable fixture oracle, not a production endpoint.
    tables = {
        "account_move": "id,company_id,date,state,name,move_type",
        "account_move_line": "id,move_id,company_id,account_id,partner_id,product_id,debit,credit,balance",
        "stock_move": "id,company_id,state,date,value,account_move_id,product_id",
        "stock_quant": "id,company_id,product_id,location_id,lot_id,owner_id,quantity,reserved_quantity",
        "res_company": "id,currency_id,chart_template,cost_method,inventory_valuation,account_stock_valuation_id",
        "product_category": "id,property_cost_method,property_valuation,property_stock_valuation_account_id",
        "account_partial_reconcile": "id,debit_move_id,credit_move_id,amount,max_date",
    }
    payload = {}
    for table, columns in tables.items():
        env.cr.execute(f"SELECT {columns} FROM {table} ORDER BY id")
        payload[table] = env.cr.fetchall()
    payload["account_account"] = env["account.account"].search([], order="id").read(["code", "account_type", "company_ids"])
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def run(env, phase):
    if env.cr.dbname != "finance_i0_reports_disposable":
        raise AssertionError("Foundation fixture requires exact disposable reports database")
    activation = load("finance_activation")
    key = "id_finance.test.foundation.baseline"
    params = env["ir.config_parameter"]
    if phase == "prepare":
        assert not params.get_param(key), "Do not seed twice"
        golden = load("verify_finance_golden_ledger")
        golden.build_fixture(env, "FA", 1)
        golden.build_fixture(env, "FB", 7)
        stock = load("verify_finance_stock_bridge")
        stock.build(env, "P", 1)
        env.flush_all()
        params.set_param(key, fingerprint(env))
        assert any(row["state"] != "installed" for row in activation.plan(env)["modules"])
        try:
            activation.attest(env)
        except RuntimeError as exc:
            assert "incompletely installed" in str(exc)
        else:
            raise AssertionError("Uninstalled profile attested")
        env.cr.commit()  # intentionally persistent fixture only in exact disposable DB
        print("FINANCE_FOUNDATION_PREPARE=PASS")
        return
    if phase != "verify":
        raise ValueError("Unknown foundation fixture phase")
    assert params.get_param(key) == fingerprint(env), "Finance install/upgrade changed persisted business sources"
    first = activation.attest(env)
    assert first["result"] in ("RECORDED", "UNCHANGED")
    assert activation.attest(env)["result"] == "UNCHANGED"
    env.cr.commit()  # persist attestation across a separate upgrade/restart process
    ledger = load("verify_finance_ledger_security")
    golden = load("verify_finance_golden_ledger")

    class Rollback(Exception):
        pass

    cases = []
    try:
        with env.cr.savepoint():
            fixture = golden.build_fixture(env, "FR", 1)
            company = fixture[0]
            for role, group in (("reader", "group_finance_reader"), ("accountant", "group_finance_accountant"),
                                ("manager", "group_finance_manager"), ("tax", "group_tax_pic"),
                                ("sales", None)):
                groups = [f"id_finance_foundation.{group}"] if group else ["sales_team.group_sale_salesman"]
                user, actor = ledger.actor(env, f"foundation.{role}", company, groups)
                assert not actor.su
                menu = actor["ir.ui.menu"]._visible_menu_ids()
                root = env.ref("id_finance_foundation.menu_finance").id
                assert (root in menu) == (role != "sales")
                if role != "sales":
                    for name in ("trial_balance", "general_ledger", "journal_ledger", "open_items", "aged_partner_balance"):
                        assert env.ref(f"id_finance_foundation.menu_{name}").id in menu
                    golden.assert_figures(golden.trial_balance(actor, fixture, "2026-07-01", "2026-07-31"), golden.JULY, fixture[1])
                for name in ("trial_balance", "general_ledger", "journal_ledger", "open_items", "aged_partner_balance"):
                    report = actor[f"report.account_financial_report.{name}"]
                    if role == "sales":
                        ledger.denied(env, lambda r=report: r._get_report_values([], {"company_id": company.id}), f"sales_render_{name}")
                    ledger.denied(env, lambda r=report: r._get_report_values([], {"company_id": env.company.id}), f"foreign_render_{role}_{name}")
                if role in ("reader", "tax"):
                    ledger.denied(env, lambda: actor["account.move"].create({
                        "company_id": company.id, "journal_id": fixture[2].id,
                    }), f"{role}_write")
                    assert not user.has_group("account.group_account_user")
                elif role in ("accountant", "manager"):
                    golden.make_entry(actor, fixture, f"{role}_write", "2026-08-01", {"cash": 1, "equity": -1})
                cases.append(role)
            raise Rollback()
    except Rollback:
        pass
    env.invalidate_all()
    env.registry.clear_cache()
    assert params.get_param(key) == fingerprint(env)
    print("FINANCE_FOUNDATION=" + json.dumps({"roles": cases, "business_source_preservation": "PASS",
          "profile_replay": "UNCHANGED", "fixture_rollback": "PASS"}, sort_keys=True))
    print("FINANCE_FOUNDATION=PASS")


if "env" in globals():
    run(globals()["env"], os.environ.get("FINANCE_FOUNDATION_PHASE", "verify"))
