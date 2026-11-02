import base64
import json
import uuid
from datetime import datetime

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSalesProductivity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.currency_id.active = True
        idr = cls.env["res.currency"].with_context(active_test=False).search([("name", "=", "IDR")], limit=1)
        if idr and not idr.active:
            idr.active = True
        cls.company_pricelist = cls.env["product.pricelist"].create({
            "name": "Dashboard company currency", "currency_id": cls.env.company.currency_id.id})
        cls.manager = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Dashboard Manager", "login": "dash_manager", "email": "dash_manager@example.com",
            "group_ids": [(6, 0, [cls.env.ref("sales_team.group_sale_manager").id,
                                  cls.env.ref("base.group_system").id])],
        })
        cls.salesman = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Dash Salesman", "login": "dash_salesman", "email": "dash_salesman@example.com",
            "group_ids": [(6, 0, [cls.env.ref("sales_team.group_sale_salesman").id])],
        })
        cls.channel_mt = cls.env["id.channel"].create({"code": "ZMT", "name": "Dash MT"})
        cls.channel_gt = cls.env["id.channel"].create({"code": "ZGT", "name": "Dash GT"})
        cls.outlet_mt = cls.env["res.partner"].create({"name": "Dash Outlet MT", "channel_id": cls.channel_mt.id})
        cls.outlet_gt = cls.env["res.partner"].create({"name": "Dash Outlet GT", "channel_id": cls.channel_gt.id})
        cls.principal = cls.env["id.principal"].create({"name": "Dash Principal", "code": "DPRIN"})
        cls.brand = cls.env["id.brand"].create({
            "name": "Dash Brand", "code": "DBRAND", "principal_id": cls.principal.id
        })
        cls.products = cls.env["product.product"].create([
            {"name": f"Dash SKU {i}", "list_price": 1000.0, "type": "consu",
             "principal_id": cls.principal.id, "brand_id": cls.brand.id}
            for i in range(5)
        ])

    def _order(self, partner, user, products, day, discount=0.0, qty=10.0, pricelist=None, company=None):
        order = self.env["sale.order"].with_company(company or self.env.company).create({
            "partner_id": partner.id, "pricelist_id": (pricelist or self.company_pricelist).id,
            "user_id": user.id,
            "order_line": [(0, 0, {"product_id": p.id, "product_uom_qty": qty, "price_unit": 1000.0,
                                   "discount": discount, "tax_ids": [(5, 0, 0)]}) for p in products],
        })
        order.action_confirm()
        order.date_order = day
        return order

    def _service(self, user=None):
        return self.env["id.sales.productivity"].with_user(user or self.manager)

    def test_period_bounds(self):
        service = self._service()
        self.assertEqual([d.isoformat() for d in service._period("day", "2026-07-15")],
                         ["2026-07-15", "2026-07-16"])
        self.assertEqual([d.isoformat() for d in service._period("week", "2026-07-15")],
                         ["2026-07-13", "2026-07-20"])
        self.assertEqual([d.isoformat() for d in service._period("month", "2026-12-15")],
                         ["2026-12-01", "2027-01-01"])
        with self.assertRaises(UserError):
            service._period("year", "2026-07-15")

    def test_access_requires_sales_role(self):
        outsider = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Outsider", "login": "dash_outsider", "email": "dash_outsider@example.com",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        with self.assertRaises(AccessError):
            self._service(outsider).get_data()

    def test_kpis_lpo_and_filters(self):
        # Order A: 4 SKU x 10 x 1000 with 10% discount -> gross 40000, discount 4000, net 36000.
        self._order(self.outlet_mt, self.salesman, self.products[:4], datetime(2026, 7, 15, 3, 0), discount=10.0)
        # Order B: 2 SKU, no discount -> gross = net = 20000.
        self._order(self.outlet_gt, self.salesman, self.products[:2], datetime(2026, 7, 16, 3, 0))
        data = self._service().get_data("month", "2026-07-10", [self.salesman.id], [])
        total = data["total"]
        self.assertEqual(total["orders"], 2)
        self.assertAlmostEqual(total["gross"], 60000.0)
        self.assertAlmostEqual(total["discount"], 4000.0)
        self.assertAlmostEqual(total["net"], 56000.0)
        self.assertAlmostEqual(total["lpo"], 3.0)
        self.assertFalse(total["lpo_ok"])
        self.assertEqual(total["sku_sold"], 4)
        self.assertEqual(total["do_count"], 0)
        self.assertAlmostEqual(total["fulfillment"], 0.0)

        by_channel = {row["id"]: row for row in data["channels"]}
        self.assertAlmostEqual(by_channel[self.channel_mt.id]["lpo"], 4.0)
        self.assertTrue(by_channel[self.channel_mt.id]["lpo_ok"])

        filtered = self._service().get_data("month", "2026-07-10", [self.salesman.id], [self.channel_gt.id])
        self.assertEqual(filtered["total"]["orders"], 1)
        self.assertAlmostEqual(filtered["total"]["net"], 20000.0)

        day = self._service().get_data("day", "2026-07-15", [self.salesman.id], [])
        self.assertEqual(day["total"]["orders"], 1)
        week = self._service().get_data("week", "2026-07-15", [self.salesman.id], [])
        self.assertEqual(week["total"]["orders"], 2)
        empty = self._service().get_data("month", "2026-09-01", [self.salesman.id], [])
        self.assertEqual(empty["total"]["orders"], 0)
        self.assertIsNone(empty["total"]["lpo"])

    def test_penetration_by_principal_and_brand(self):
        self._order(self.outlet_mt, self.salesman, self.products[:3], datetime(2026, 7, 15, 3, 0))
        data = self._service().get_data("month", "2026-07-10", [self.salesman.id], [])
        principal = next(i for i in data["penetration"]["salesman"]["principal"] if i["id"] == self.principal.id)
        cell = principal["cells"][str(self.salesman.id)]
        self.assertEqual(cell["sold"], 3)
        self.assertGreaterEqual(principal["catalog"], 5)
        self.assertAlmostEqual(cell["penetration"], 3 / principal["catalog"])
        brand = next(i for i in data["penetration"]["channel"]["brand"] if i["id"] == self.brand.id)
        self.assertEqual(brand["cells"][str(self.channel_mt.id)]["sold"], 3)

    def test_fulfillment_counts_only_delivered_and_posted_invoice(self):
        order = self._order(self.outlet_mt, self.salesman, self.products[:2], datetime(2026, 7, 15, 3, 0))
        picking = order.picking_ids
        picking.move_ids.write({"quantity": 10.0})
        picking.button_validate()
        picking.date_done = datetime(2026, 7, 15, 4, 0)
        invoice = order._create_invoices()
        data = self._service().get_data("month", "2026-07-10", [self.salesman.id], [])
        self.assertAlmostEqual(data["total"]["fulfillment"], 0.0, msg="draft invoice must not count")
        invoice.action_post()
        data = self._service().get_data("month", "2026-07-10", [self.salesman.id], [])
        self.assertAlmostEqual(data["total"]["fulfillment"], 1.0)
        self.assertEqual(data["total"]["do_count"], 1)

    def test_pjp_unavailable_without_plan(self):
        self._order(self.outlet_mt, self.salesman, self.products[:1], datetime(2026, 7, 15, 3, 0))
        data = self._service().get_data("month", "2026-07-10", [self.salesman.id], [])
        self.assertFalse(data["total"]["pjp"]["available"])
        self.assertFalse(data["pjp_status"]["available"])
        self.assertTrue(data["pjp_status"]["reason"])

    def test_filters_payload(self):
        self._order(self.outlet_mt, self.salesman, self.products[:1], datetime(2026, 7, 15, 3, 0))
        filters = self._service().get_filters()
        self.assertIn(self.salesman.id, [s["id"] for s in filters["salesmen"]])
        self.assertIn("ZMT", [c["code"] for c in filters["channels"]])
        self.assertEqual(filters["period_min"], "2026-07-01")
        self.assertEqual(filters["period_max"], "2026-10-31")
        self.assertEqual(filters["lpo_target"], 4.0)

    def test_previous_period_comparison(self):
        self._order(self.outlet_mt, self.salesman, self.products[:2], datetime(2026, 7, 15, 3, 0))
        self._order(self.outlet_mt, self.salesman, self.products[:2], datetime(2026, 8, 5, 3, 0), qty=20.0)
        data = self._service().get_data("month", "2026-08-10", [self.salesman.id], [])
        self.assertAlmostEqual(data["total"]["net"], 40000.0)
        self.assertAlmostEqual(data["previous"]["net"], 20000.0)
        self.assertEqual(data["previous_period"]["start"], "2026-07-01")
        first = self._service().get_data("month", "2026-07-10", [self.salesman.id], [])
        self.assertEqual(first["previous"]["orders"], 0)


    def test_zero_selling_groups_and_outside_catalog_are_explicit(self):
        other = self.env["id.principal"].create({"name": "Never sold principal", "code": "DNOSALE"})
        self.env["product.product"].create({"name": "Never sold SKU", "principal_id": other.id})
        self._order(self.outlet_mt, self.salesman, self.products[:3], datetime(2026, 7, 15, 3))
        self.products[0].sale_ok = False
        result = self._service().get_data("month", "2026-07-01", [self.salesman.id], [])
        matrix = {r["id"]: r for r in result["penetration"]["salesman"]["principal"]}
        zero = matrix[other.id]["cells"][str(self.salesman.id)]
        self.assertEqual(zero["sold"], 0)
        self.assertEqual(zero["penetration"], 0)
        cell = matrix[self.principal.id]["cells"][str(self.salesman.id)]
        self.assertEqual((cell["sold"], cell["eligible_sold"], cell["outside_catalog"]), (3, 2, 1))
        self.assertEqual(matrix[self.principal.id]["catalog"], 4)
        self.assertEqual(cell["penetration"], 0.5)

    def test_outlet_activity_is_period_comparison_not_first_ever_acquisition(self):
        third = self.env["res.partner"].create({"name": "Current-only outlet"})
        for outlet, day in [(self.outlet_mt, datetime(2026, 7, 15, 3)),
                            (self.outlet_gt, datetime(2026, 7, 15, 3)),
                            (self.outlet_mt, datetime(2026, 8, 15, 3)), (third, datetime(2026, 8, 15, 3))]:
            self._order(outlet, self.salesman, self.products[:1], day)
        activity = self._service().get_data("month", "2026-08-01", [self.salesman.id], [])["outlet_activity"]
        self.assertEqual(activity, {"current": 2, "previous": 2, "retained": 1, "entered": 1,
                                    "exited": 1, "retention": 0.5})

    def test_segment_targets_match_company_dimension_period_and_filter_scope(self):
        area = self.env["id.coverage.area"].create({"name": "Target area", "code": "DTA"})
        self.outlet_mt.coverage_area_id = area
        self._order(self.outlet_mt, self.salesman, self.products[:2], datetime(2026, 7, 15, 3))
        Target = self.env["id.sales.segment.target"]
        records = Target.browse()
        for dimension, ref in [("salesman", self.salesman), ("channel", self.channel_mt),
                               ("area", area), ("principal", self.principal)]:
            records |= Target.create({"name": dimension, "dimension": dimension, f"{dimension}_id": ref.id,
                "date_from": "2026-07-01", "date_to": "2026-07-31", "target_amount": 40000})
        result = self._service().get_data("month", "2026-07-01")["segment_targets"]
        self.assertEqual(len(result), 4)
        for row in result:
            self.assertEqual((row["actual"], row["achievement"]), (20000, 0.5))
        filtered = self._service().get_data("month", "2026-07-01", [str(self.salesman.id)], [])
        for row in filtered["segment_targets"]:
            self.assertEqual(row["actual"], 20000 if row["dimension"] == "salesman" else None)
        self.assertEqual(len(Target.with_user(self.salesman).search([])), 1)
        with self.assertRaises(AccessError):
            records.with_user(self.salesman).write({"target_amount": 1})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            Target.create({"name": "Overlap", "dimension": "salesman", "salesman_id": self.salesman.id,
                "date_from": "2026-07-15", "date_to": "2026-08-05", "target_amount": 1})
        other = self.env["res.company"].create({"name": "Private target company"})
        Target.create({"name": "Foreign budget", "company_id": other.id, "dimension": "channel",
            "channel_id": self.channel_mt.id, "date_from": "2026-07-01", "date_to": "2026-07-31",
            "target_amount": 999999})
        self.assertFalse(Target.with_user(self.manager).search([("company_id", "=", other.id)]))

    def test_foreign_currency_requires_rates_and_totals_reconcile_to_trend(self):
        foreign = (self.env.ref("base.EUR") if self.env.company.currency_id.name != "EUR"
                   else self.env.ref("base.USD"))
        foreign.active = True
        pricelist = self.env["product.pricelist"].create({"name": "Foreign", "currency_id": foreign.id})
        self._order(self.outlet_mt, self.salesman, self.products[:2], datetime(2026, 7, 15, 3), pricelist=pricelist)
        rates = self.env["res.currency.rate"].search([
            ("currency_id", "in", (foreign | self.env.company.currency_id).ids)])
        rates.unlink()
        with self.assertRaises(UserError):
            self._service().get_data("month", "2026-07-01", [self.salesman.id], [])
        for currency, rate in [(self.env.company.currency_id, 1), (foreign, 2)]:
            self.env["res.currency.rate"].create({"currency_id": currency.id, "company_id": self.env.company.id,
                                                "name": "2026-01-01", "rate": rate})
        result = self._service().get_data("month", "2026-07-01", [self.salesman.id], [])
        self.assertEqual(result["currency"], self.env.company.currency_id.name)
        self.assertAlmostEqual(result["total"]["net"], 10000)
        self.assertAlmostEqual(sum(p["net"] for p in result["trend"]), result["total"]["net"])

    def test_official_checkins_are_not_photos_or_orders_before_visits(self):
        if "id.mobile.command" not in self.env:
            self.skipTest("Optional mobile integration is not installed")
        company = self.env["res.company"].create({
            "name": "PJP official scope", "currency_id": self.env.ref("base.IDR").id})
        self.salesman.company_ids = [(4, company.id)]
        self.manager.company_ids = [(4, company.id)]
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
        if not warehouse:
            warehouse = self.env["stock.warehouse"].create({
                "name": "PJP warehouse", "code": "DP3", "company_id": company.id})
        pricelist = self.env["product.pricelist"].create({"name": "PJP IDR", "currency_id": company.currency_id.id})
        self.outlet_gt.parent_id = self.outlet_mt
        assignment = self.env["id.mobile.workday"].create({"company_id": company.id, "user_id": self.salesman.id,
            "business_date": "2026-07-15", "warehouse_id": warehouse.id, "pricelist_id": pricelist.id,
            "outlet_ids": [(6, 0, (self.outlet_mt | self.outlet_gt).ids)], "product_ids": [(6, 0, self.products.ids)]})
        receipt = {"company_id": str(company.id), "user_id": str(self.salesman.id),
                   "outlet_id": str(self.outlet_mt.id), "assignment_id": str(assignment.id),
                   "warehouse_id": str(warehouse.id), "business_date": "2026-07-15"}
        evidence = self.env["id.mobile.evidence"].create({"user_id": self.salesman.id, "company_id": company.id,
            "outlet_id": self.outlet_mt.id, "client_uuid": str(uuid.uuid4()), "fingerprint": "f"*64,
            "receipt_json": json.dumps(receipt), "original": base64.b64encode(b"image"),
            "watermarked": base64.b64encode(b"image")})
        self.env.flush_all()
        self.cr.execute("UPDATE id_mobile_evidence SET create_date=%s WHERE id=%s",
                        [datetime(2026, 7, 15, 2), evidence.id])
        evidence.invalidate_recordset(["create_date"])
        self._order(self.outlet_mt, self.salesman, self.products[:1], datetime(2026, 7, 15, 2),
                    pricelist=pricelist, company=company)
        service = self._service().with_context(allowed_company_ids=[company.id])
        first = service.get_data("month", "2026-07-01")["total"]["pjp"]
        self.assertEqual((first["proof_completed"], first["completed"], first["effective"]), (1, 0, 0))

        def checkin(outlet):
            command = self.env["id.mobile.command"].create({"user_id": self.salesman.id, "company_id": company.id,
                "client_uuid": str(uuid.uuid4()), "fingerprint": "c"*64, "command_type": "sales.visit.check_in",
                "status": "accepted", "payload_json": json.dumps({"outlet_id": str(outlet.id),
                                                                    "business_date": "2026-07-15"})})
            self.env.flush_all()
            self.cr.execute("UPDATE id_mobile_command SET create_date=%s WHERE id=%s",
                            [datetime(2026, 7, 15, 3), command.id])
            command.invalidate_recordset(["create_date"])
        checkin(self.outlet_mt)
        before = service.get_data("month", "2026-07-01")["total"]["pjp"]
        self.assertEqual((before["completed"], before["effective"]), (1, 0))
        self._order(self.outlet_mt, self.salesman, self.products[:1], datetime(2026, 7, 15, 4),
                    pricelist=pricelist, company=company)
        checkin(self.outlet_gt)
        checkin(self.outlet_mt)  # Same outlet/day is one planned call, not two.
        after = service.get_data("month", "2026-07-01")["total"]["pjp"]
        self.assertEqual((after["completed"], after["visits"], after["effective"]), (2, 2, 1))
        self.assertEqual(after["ec_ratio"], 0.5, "Sibling outlets must not share EC credit")
        assignment.active = False
        archived = service.get_data("month", "2026-07-01")["total"]["pjp"]
        self.assertEqual(archived["completed"], 2, "Archiving a plan must not erase historical check-ins")
