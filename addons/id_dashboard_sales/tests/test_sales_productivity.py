from datetime import datetime

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSalesProductivity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
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
        cls.principal = cls.env["id.principal"].create({"name": "Dash Principal"})
        cls.brand = cls.env["id.brand"].create({"name": "Dash Brand", "principal_id": cls.principal.id})
        cls.products = cls.env["product.product"].create([
            {"name": f"Dash SKU {i}", "list_price": 1000.0, "type": "consu",
             "principal_id": cls.principal.id, "brand_id": cls.brand.id}
            for i in range(5)
        ])

    def _order(self, partner, user, products, day, discount=0.0, qty=10.0):
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
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
