#!/usr/bin/env python3
"""Native, rollback-only stock source fixtures in an explicitly disposable DB."""

import json


EXPECTED = {
    # Two five-unit quote-linked receipts at 10 and 20. Four-unit delivery,
    # then one-unit customer return valued from its original delivery.
    "standard": (50, 100, 40, 10),
    "average": (50, 100, 60, 15),
    "fifo": (50, 100, 40, 10),
}


def assert_values(actual, expected):
    if tuple(actual) != tuple(expected):
        raise AssertionError(f"Native stock oracle: expected {expected}, got {actual}")


def assert_groups(snapshot):
    for group in snapshot["journal_groups"]:
        if group["state"] != "posted":
            raise AssertionError("Unposted stock journal")
        for row in group["comparisons_current_mapping"]:
            if row["difference"]:
                raise AssertionError(f"Stock/GL difference: {row}")


def complete(env, company, product, source, dest, qty, **extra):
    move = env["stock.move"].with_company(company).create({
        "name": "Finance native stock fixture", "company_id": company.id,
        "product_id": product.id, "product_uom": product.uom_id.id,
        "product_uom_qty": qty, "location_id": source.id, "location_dest_id": dest.id,
        **extra,
    })
    move._action_confirm()
    move.quantity = qty
    move.picked = True
    move.with_context(force_period_date="2026-07-31")._action_done()
    return move


def build(env, suffix, scale):
    company = env["res.company"].with_context(chart_template_load=True).create({
        "name": f"FINANCE STOCK {suffix}", "currency_id": env.ref("base.IDR").id,
        "country_id": env.ref("base.id").id, "inventory_valuation": "real_time",
    })
    scoped = env(context=dict(env.context, allowed_company_ids=[company.id]))
    accounts = {}
    for key, kind in (("stock", "asset_current"), ("clearing", "liability_current"), ("expense", "expense")):
        accounts[key] = scoped["account.account"].with_company(company).create({
            "name": f"Stock oracle {key}", "code": f"FS{suffix}{len(accounts)}",
            "account_type": kind, "company_ids": [(6, 0, company.ids)],
        })
    journal = scoped["account.journal"].create({
        "name": f"Stock oracle {suffix}", "code": f"FS{suffix}", "type": "general", "company_id": company.id,
    })
    company.write({"account_stock_journal_id": journal.id, "account_stock_valuation_id": accounts["stock"].id})
    locations = {}
    for name, usage, account in (("vendor", "supplier", "clearing"), ("shelf", "internal", None),
                                 ("quarantine", "internal", None), ("customer", "customer", "expense")):
        locations[name] = scoped["stock.location"].create({
            "name": f"Finance {suffix} {name}", "usage": usage, "company_id": company.id,
            "valuation_account_id": accounts[account].id if account else False,
        })
    vendor = scoped["res.partner"].create({"name": f"Finance vendor {suffix}"})
    owner = scoped["res.partner"].create({"name": f"Finance consignment owner {suffix}"})
    results = []
    for method, wanted in EXPECTED.items():
        category = scoped["product.category"].create({
            "name": f"Finance {suffix} {method}", "property_cost_method": method,
            "property_valuation": "real_time", "property_stock_valuation_account_id": accounts["stock"].id,
        })
        product = scoped["product.product"].create({
            "name": f"Finance {suffix} {method}", "type": "consu", "is_storable": True,
            "categ_id": category.id, "standard_price": 10 * scale,
        })
        receipts = []
        for price in (10, 20):
            # Explicit quotation source; not claimed as full PO/bill acceptance.
            order = scoped["purchase.order"].create({"partner_id": vendor.id, "company_id": company.id})
            line = scoped["purchase.order.line"].create({
                "order_id": order.id, "product_id": product.id, "name": product.name,
                "product_qty": 5, "product_uom_id": product.uom_id.id,
                "price_unit": price * scale, "tax_ids": [(5, 0, 0)], "date_planned": "2026-07-31",
            })
            receipts.append(complete(scoped, company, product, locations["vendor"], locations["shelf"],
                                     5, purchase_line_id=line.id))
        delivery = complete(scoped, company, product, locations["shelf"], locations["customer"], 4)
        returned = complete(scoped, company, product, locations["customer"], locations["shelf"],
                            1, origin_returned_move_id=delivery.id)
        actual = [move.value for move in [*receipts, delivery, returned]]
        assert_values(actual, [amount * scale for amount in wanted])
        internal = complete(scoped, company, product, locations["shelf"], locations["quarantine"], 1)
        assert not internal.account_move_id and not internal.is_valued
        # Owner-aware native quant update, no inventory value attributed to company.
        consigned = complete(scoped, company, product, locations["vendor"], locations["shelf"],
                             2, restrict_partner_id=owner.id)
        assert consigned.value == 0 and not consigned.account_move_id
        assert consigned.move_line_ids.owner_id == owner
        results.append({"method": method, "values": actual, "product_id": product.id})
    batch = scoped["stock.move"].create([{
        "name": "Finance grouped journal", "company_id": company.id,
        "product_id": result["product_id"], "product_uom_qty": 2,
        "location_id": locations["shelf"].id, "location_dest_id": locations["customer"].id,
    } for result in results])
    batch._action_confirm(merge=False)
    batch.write({"quantity": 2, "picked": True})
    batch.with_context(force_period_date="2026-07-31")._action_done()
    assert_values(batch.mapped("value"), [20 * scale, 30 * scale, 30 * scale])
    assert len(batch.account_move_id) == 1
    report = scoped["id.finance.stock.bridge"]
    snapshot = report._snapshot(company.id, "2026-07-01", "2026-07-31")
    assert_groups(snapshot)
    assert len(snapshot["moves"]) == 15  # only journal-linked moves: physical date is today
    assert all(row["in_posting_period"] and not row["in_physical_period"] for row in snapshot["moves"])
    assert all("physical_posting_date_difference" in row["issues"] for row in snapshot["moves"])
    owned = [row for row in snapshot["ownership"] if row["owner_id"] == owner.id]
    assert len(owned) == 3 and sum(row["quantity"] for row in owned) == 6
    assert sum(row["quantity"] for row in snapshot["ownership"] if not row["owner_id"]) == 15
    assert any(len(group["sibling_move_ids"]) == 3 for group in snapshot["journal_groups"])
    assert {row["effective_cost_method_now"] for row in snapshot["moves"]} == set(EXPECTED)
    return scoped, company, report, snapshot, results


def run(env):
    if env.cr.dbname != "finance_i0_reports_disposable":
        raise AssertionError("Stock fixture requires exact disposable reports database")

    class Rollback(Exception):
        pass

    evidence = {"scope": "I0 sources, not I3 or complete COGS acceptance", "companies": []}
    before = env["res.company"].search([]).ids
    try:
        with env.cr.savepoint():
            for suffix, scale in (("A", 1), ("B", 7)):
                scoped, company, report, snapshot, results = build(env, suffix, scale)
                evidence["companies"].append({"scale": scale, "scenarios": results})
                # Balanced GL mutation must be detected by the bridge, not just TB.
                try:
                    with env.cr.savepoint():
                        journal = scoped["account.move"].browse(snapshot["journal_groups"][0]["account_move_id"])
                        stock_line = journal.line_ids.filtered(lambda line: line.debit)[:1]
                        offset_line = journal.line_ids.filtered(lambda line: line.credit)[:1]
                        journal.button_draft()
                        stock_line.with_context(check_move_validity=False).write({"debit": stock_line.debit + scale})
                        offset_line.write({"credit": offset_line.credit + scale})
                        journal.action_post()
                        try:
                            assert_groups(report._snapshot(company.id, "2026-07-01", "2026-07-31"))
                        except AssertionError as exc:
                            assert "Stock/GL difference" in str(exc)
                        else:
                            raise AssertionError("Balanced mutation accepted")
                        raise Rollback()
                except Rollback:
                    pass
                env.invalidate_all()
                assert_groups(report._snapshot(company.id, "2026-07-01", "2026-07-31"))
                # Boundary readback in disposable fixture only. Not a backdating loader.
                try:
                    with env.cr.savepoint():
                        selected = scoped["stock.move"].browse([row["move_id"] for row in snapshot["moves"][:2]])
                        selected[0].date = "2026-07-31 15:59:59"
                        selected[1].date = "2026-07-31 16:00:00"
                        dated = report._snapshot(company.id, "2026-07-01", "2026-07-31")
                        by_id = {row["move_id"]: row for row in dated["moves"]}
                        assert by_id[selected[0].id]["in_physical_period"]
                        assert not by_id[selected[1].id]["in_physical_period"]
                        assert by_id[selected[1].id]["in_posting_period"]
                        raise Rollback()
                except Rollback:
                    pass
                env.invalidate_all()
                try:
                    with env.cr.savepoint():
                        selected = scoped["stock.move"].browse(snapshot["moves"][0]["move_id"])
                        journal_id = selected.account_move_id.id
                        selected.account_move_id = False
                        unlinked = report._snapshot(company.id, "2026-07-01", "2026-07-31")
                        assert journal_id in unlinked["gl_without_selected_stock_link"]
                        raise Rollback()
                except Rollback:
                    pass
                env.invalidate_all()
                from odoo.exceptions import AccessError
                for role, groups in (("accountant", ["account.group_account_user", "stock.group_stock_user"]),
                                     ("sales", ["sales_team.group_sale_salesman"])):
                    user = scoped["res.users"].with_context(no_reset_password=True).create({
                        "name": f"Stock probe {suffix} {role}", "login": f"stock.probe.{suffix}.{role}",
                        "company_id": company.id, "company_ids": [(6, 0, company.ids)],
                        "group_ids": [(6, 0, [scoped.ref(name).id for name in ["base.group_user", *groups]])],
                    })
                    probe = report.with_user(user).sudo(False)
                    assert not probe.env.su
                    if role == "accountant":
                        observed = probe._snapshot(company.id, "2026-07-01", "2026-07-31")
                        assert observed["moves"] == snapshot["moves"]
                        assert_groups(observed)
                    else:
                        try:
                            probe._snapshot(company.id, "2026-07-01", "2026-07-31")
                        except AccessError:
                            pass
                        else:
                            raise AssertionError("Sales role accepted")
                foreign = report.with_context(allowed_company_ids=[env.company.id])
                try:
                    foreign._snapshot(company.id, "2026-07-01", "2026-07-31")
                except AccessError:
                    pass
                else:
                    raise AssertionError("Foreign company accepted")
            raise Rollback()
    except Rollback:
        pass
    env.invalidate_all()
    assert env["res.company"].search([]).ids == before
    evidence["balanced_mutation"] = "REJECTED_BASELINE_RESTORED"
    evidence["fixture_rollback"] = "PASS"
    print("FINANCE_STOCK_BRIDGE=" + json.dumps(evidence, sort_keys=True))
    print("FINANCE_STOCK_BRIDGE=PASS")


if "env" in globals():
    try:
        run(globals()["env"])
    except Exception:
        import traceback
        traceback.print_exc()
        print("FINANCE_STOCK_BRIDGE=FAIL")
        raise
