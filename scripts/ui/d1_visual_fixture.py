"""Deterministic representative D1 evidence, only on a fresh disposable database."""
# ruff: noqa: F821
import json
import os
import uuid
from datetime import datetime

from odoo.exceptions import AccessError
from odoo.addons.id_dashboard_redesign.models.dashboard_bridge import _geo_boundaries

if not env.cr.dbname.startswith("d1_"):
    raise RuntimeError("D1 visual fixture requires a disposable d1_ database")
if env["sale.order"].search_count([]):
    raise RuntimeError("D1 visual fixture requires an empty sales database")
password = os.environ["D1_TEST_PASSWORD"]
admin = env.ref("base.user_admin")
admin.password = password
env.ref("base.IDR").active = True
company = env.company
company.currency_id = env.ref("base.IDR")
pricelist = env["product.pricelist"].create({"name": "D1 QA IDR", "currency_id": company.currency_id.id})
warehouse = env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
principals = env["id.principal"].create([
    {"name": f"D1 QA Principal {i + 1}", "code": f"D1QA_P{i}"} for i in range(4)])
channels = env["id.channel"].create([
    {"name": f"D1 QA Channel {i + 1}", "code": f"D1QA_C{i}"} for i in range(4)])
products = env["product.product"]
for i, principal in enumerate(principals):
    brand = env["id.brand"].create({"name": f"D1 QA Brand {i + 1}", "code": f"D1QA_B{i}",
                                  "principal_id": principal.id})
    products |= env["product.product"].create({"name": f"D1 QA SKU {i + 1}", "type": "consu",
        "principal_id": principal.id, "brand_id": brand.id, "taxes_id": [(5, 0, 0)]})
users = env["res.users"]
expected = {"gross": 0, "discount": 0, "net": 0, "orders": 0, "visits": 0, "effective": 0}
by_user = {}
first_refund_line = None
for i in range(8):
    user = env["res.users"].with_context(no_reset_password=True).create({
        "name": f"D1 QA Sales {i + 1:02}", "login": f"d1-visual-sales-{i + 1:02}", "password": password,
        "company_id": company.id, "company_ids": [(6, 0, company.ids)],
        "group_ids": [(6, 0, [env.ref(x).id for x in (
            "sales_team.group_sale_salesman", "id_mobile_api.group_mobile_evidence")])]})
    users |= user
    team = env["crm.team"].create({"name": f"D1 QA Team {i // 2 + 1}"})
    code = ["71.71", "71.72", "71.73", "71.02"][i % 4]
    district = env["id.district"].search([("city_id.kode_kemendagri", "=", code)], limit=1)
    if not district:
        raise AssertionError(f"Missing seeded district for {code}")
    coordinates = {}
    if code == "71.71":
        village = env.ref("id_base.subdistrict_calaca")
        district = village.district_id
    elif code == "71.73":
        district = env["id.district"].search([("kode_kemendagri", "=", "71.73.02")], limit=1)
        village = env["id.subdistrict"].create({
            "name": "D1 QA Legacy Paslaten", "district_id": district.id,
        })
        coordinates = {"partner_latitude": 1.320063, "partner_longitude": 124.829968}
    else:
        shape = _geo_boundaries("sulut_villages.geojson")[district.kode_kemendagri][0]
        village = env["id.subdistrict"].search([
            ("kode_kemendagri", "=", shape["code"]),
        ], limit=1) or env["id.subdistrict"].create({
            "name": shape["name"], "district_id": district.id, "kode_kemendagri": shape["code"],
        })
    if not village:
        raise AssertionError(f"Missing mapped fixture village for {code}")
    outlets = env["res.partner"].create([{"name": f"D1 QA Outlet {i + 1}-{j}",
        "district_id": district.id, "subdistrict_id": village.id, "channel_id": channels[i % 4].id,
        **coordinates} for j in range(2 + i % 4)])
    own = {"gross": 0, "discount": 0, "net": 0, "orders": 28}
    for day in range(1, 29):
        outlet = outlets[(day - 1) % len(outlets)]
        qty, price, discount = 100 + day + i * 10, 10000, (day + i) % 10
        gross, reduction = qty * price, qty * price * discount / 100
        for bucket in (expected, own):
            bucket["gross"] += gross
            bucket["discount"] += reduction
            bucket["net"] += gross - reduction
        expected["orders"] += 1
        order = env["sale.order"].create({"partner_id": outlet.id, "user_id": user.id,
            "team_id": team.id, "pricelist_id": pricelist.id, "order_line": [(0, 0, {
                "product_id": products[i % 4].id, "product_uom_qty": qty, "price_unit": price,
                "discount": discount, "tax_ids": [(5, 0, 0)]})]})
        order.action_confirm()
        order.date_order = datetime(2026, 10, day, 4)
        if i == 0 and day == 8:
            first_refund_line = order.order_line
        env["id.mobile.workday"].create({"user_id": user.id, "company_id": company.id,
            "business_date": f"2026-10-{day:02}", "warehouse_id": warehouse.id,
            "pricelist_id": pricelist.id, "outlet_ids": [(6, 0, outlet.ids)],
            "product_ids": [(6, 0, products.ids)]})
        if day % 7:
            command = env["id.mobile.command"].create({"user_id": user.id, "company_id": company.id,
                "client_uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"d1-visual:{i}:{day}")),
                "fingerprint": "d" * 64, "command_type": "sales.visit.check_in", "status": "accepted",
                "payload_json": json.dumps({"outlet_id": str(outlet.id), "business_date": f"2026-10-{day:02}"})})
            env.flush_all()
            # Only the disposable fixture freezes server acceptance time; production code never rewrites it.
            env.cr.execute("UPDATE id_mobile_command SET create_date=%s WHERE id=%s",
                           [datetime(2026, 10, day, 5 if day % 5 == 0 else 3), command.id])
            command.invalidate_recordset(["create_date"])
            expected["visits"] += 1
            expected["effective"] += int(day % 5 != 0)
    by_user[str(user.id)] = own
sales_group = env.ref("sales_team.group_sale_salesman")
target_users = env["res.users"].search([("active", "=", True), ("all_group_ids", "in", sales_group.ids),
                                         ("company_ids", "in", company.ids)])
for user in target_users:
    env["id.sales.segment.target"].create({"name": f"D1 QA Target {user.id}", "dimension": "salesman",
        "salesman_id": user.id, "date_from": "2026-10-01", "date_to": "2026-10-31",
        "target_amount": 50000000})
accounts = {}
for key, kind, code in (("income", "income", "D1QA01"), ("ar", "asset_receivable", "D1QA02")):
    accounts[key] = env["account.account"].create({"name": "D1 QA " + key, "code": code,
        "account_type": kind, "reconcile": key == "ar", "company_ids": [(6, 0, company.ids)]})
first_refund_line.order_id.partner_id.property_account_receivable_id = accounts["ar"]
journal = env["account.journal"].create({"name": "D1 QA Refunds", "code": "D1QR", "type": "sale"})
for posted, amount in ((True, 60000), (False, 99000)):
    refund = env["account.move"].create({"move_type": "out_refund", "invoice_date": "2026-10-08",
        "partner_id": first_refund_line.order_id.partner_id.id, "invoice_user_id": users[0].id,
        "journal_id": journal.id, "invoice_line_ids": [(0, 0, {"product_id": products[0].id,
            "quantity": 1, "price_unit": amount, "account_id": accounts["income"].id,
            "tax_ids": [(5, 0, 0)], "sale_line_ids": [(6, 0, first_refund_line.ids)]})]})
    if posted:
        refund.action_post()
negative = env["sale.order"].create({"partner_id": first_refund_line.order_id.partner_id.id,
    "user_id": admin.id, "pricelist_id": pricelist.id, "order_line": [(0, 0, {
        "product_id": products[0].id, "product_uom_qty": 1, "price_unit": -900000, "tax_ids": [(5, 0, 0)]})]})
negative.action_confirm()
negative.date_order = datetime(2026, 9, 4, 4)
query = {"period": {"from": "2026-10-01", "to": "2026-10-31", "compare": False}, "filters": {}}
service = env["id.dashboard.redesign"]
source = service.with_user(admin).get_data("D1", {"query": query})["source"]
checks = []


def equal(actual, wanted, label):
    if abs(actual - wanted) > .001:
        raise AssertionError(f"{label}: {actual} != {wanted}")
    checks.append({"name": label, "actual": actual, "expected": wanted})


for key in ("gross", "discount", "net", "orders"):
    equal(source["total"][key], expected[key], "whole_scope_" + key)
for key in ("principal", "channel", "city", "salesmen"):
    equal(sum(row["net"] for row in source[key]), expected["net"], "ranking_tie_out_" + key)
city_shapes = {feature["code"] for features in _geo_boundaries("sulut_kab_kota.geojson").values()
               for feature in features}
dashboard = service.with_user(admin)
conversion = dashboard._service("D1")
evidence_geo = []
for label, filters in (("all", {}), ("sku", {"sku": {"mode": "in", "ids": [products[2].id]}})):
    data = dashboard.get_data("D1", {"query": {**query, "filters": filters}})["source"]
    net = data["total"]["net"]
    city_total = district_total = village_total = 0
    for city_row in data["city"]:
        city = city_row.get("code")
        assert city in city_shapes, (label, city_row["name"])
        city_total += city_row["net"]
        district_shapes = {feature["code"] for feature in dashboard.get_geo_boundaries("D1", city)}
        district_amounts = data["geo"].get(city, {})
        equal(sum(district_amounts.values()), city_row["net"], f"{label}: districts of {city}")
        for district, amount in district_amounts.items():
            assert district in district_shapes, (label, city, district)
            district_total += amount
            village_shapes = {feature["code"] for feature in dashboard.get_geo_boundaries("D1", district)}
            village_amounts = data["geo"].get(district, {})
            equal(sum(village_amounts.values()), amount, f"{label}: villages of {district}")
            for village, value in village_amounts.items():
                assert village in village_shapes, (label, district, village)
                village_total += value
                ids = data["geo_partners"][district][village]
                lines = env["sale.order.line"].with_user(admin).search([
                    *data["line_domain"], ("order_id.partner_id", "in", ids),
                ])
                fx = {}
                equal(sum(line.price_subtotal * conversion._conversion(line.order_id, fx)
                          for line in lines), value, f"{label}: source lines of {village}")
    assert data["geo"]["71.73.02"]["71.73.02.1012"] > 0
    for level, total in (("city", city_total), ("district", district_total), ("village", village_total)):
        equal(total, net, f"{label}: {level} vs KPI")
    evidence_geo.append({"company": company.name, "period": data["period"], "filters": filters,
                         "net": net, "city": city_total, "district": district_total,
                         "village": village_total, "outside_orders": 0, "outside_net": 0})
equal(source["total"]["pjp"]["visits"], expected["visits"], "accepted_visits")
equal(source["total"]["pjp"]["effective"], expected["effective"], "effective_after_checkin")
equal(source["total"]["calls_per_day"], expected["visits"] / 224, "assigned_day_denominator")
equal(source["target"]["amount"], len(target_users) * 50000000, "complete_target_partition")
equal(source["refund"]["amount"], 60000, "posted_refund_only")
for user in users:
    own = service.with_user(user).get_data("D1", {"query": query})["source"]
    equal(own["total"]["net"], by_user[str(user.id)]["net"], "own_sales_" + str(user.id))
    equal(own["total"]["orders"], 28, "own_order_count_" + str(user.id))
no_role = env["res.users"].with_context(no_reset_password=True).create({"name": "D1 QA No Sales",
    "login": "d1-visual-no-sales", "password": password, "group_ids": [(6, 0, env.ref("base.group_user").ids)]})
try:
    service.with_user(no_role).get_data("D1", {"query": query})
except AccessError:
    checks.append({"name": "no_sales_role_rejected", "actual": True, "expected": True})
else:
    raise AssertionError("Non-sales role accessed D1")
expected.update({"target": len(target_users) * 50000000, "refund": 60000,
    "salesmen": 8, "assigned_days": 224, "first_user": users[0].login,
    "first_user_id": users[0].id, "first_user_net": by_user[str(users[0].id)]["net"],
    "sku": products[0].id, "negative_net": -900000})
env.cr.commit()
report = {"expected": expected, "reconciliation": checks, "geo": evidence_geo}
print("D1_VISUAL_FIXTURE=" + json.dumps(report, sort_keys=True))
