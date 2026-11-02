# Part of odooca-fmcg. License LGPL-3.
from datetime import date
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

GROUPS = ["food", "rtd_beverage", "home_care", "personal_care", "confectionery", "other"]
BUCKETS = ["critical", "warning", "good"]
REASONS = ["packaging_damaged", "near_expiry", "wrong_sku_qty", "store_closed"]


@tagged("post_install", "-at_install")
class TestWmsDashboard(TransactionCase):
    def test_module_installed(self):
        module = self.env["ir.module.module"].search([("name", "=", "id_dashboard_wms")])
        self.assertEqual(module.state, "installed")

    def test_stock_category_view_is_queryable(self):
        records = self.env["id.wms.stock.category"].search([])
        for record in records:
            self.assertIn(record.category_group, GROUPS)
            self.assertIsInstance(record.qty_on_hand, float)
            self.assertGreaterEqual(record.product_count, 1)

    def test_expiry_buckets_match_days_to_expiry(self):
        records = self.env["id.wms.expiry"].search([])
        for record in records:
            self.assertIn(record.bucket, BUCKETS)
            self.assertTrue(record.recommended_action)
            if record.days_to_expiry < 30:
                self.assertEqual(record.bucket, "critical")
            elif record.days_to_expiry <= 90:
                self.assertEqual(record.bucket, "warning")
            else:
                self.assertEqual(record.bucket, "good")

    def test_delivery_views_are_queryable(self):
        deliveries = self.env["id.wms.delivery"].search([])
        for delivery in deliveries:
            self.assertEqual(delivery.picking_type_code, "outgoing")
            self.assertGreaterEqual(delivery.delivered_value, 0.0)
        for summary in self.env["id.wms.delivery.summary"].search([]):
            self.assertGreaterEqual(summary.scheduled_count, 1)
            self.assertGreaterEqual(summary.delivery_rate, 0.0)
        for reject in self.env["id.wms.reject"].search([]):
            self.assertIn(reject.reason, REASONS + ["not_recorded"])

    def test_picking_carries_standard_rejection_reasons(self):
        picking = self.env["stock.picking"]
        self.assertIn("fmcg_reject_reason", picking._fields)
        self.assertIn("fmcg_vehicle_id", picking._fields)
        selection = [code for code, _label in picking._fields["fmcg_reject_reason"].selection]
        self.assertEqual(selection, REASONS)

    def test_trip_cost_total_and_fleet_ratio(self):
        brand = self.env["fleet.vehicle.model.brand"].create({"name": "Cost test brand"})
        model = self.env["fleet.vehicle.model"].create({"name": "Cost test model", "brand_id": brand.id})
        vehicle = self.env["fleet.vehicle"].create({"model_id": model.id})
        cost = self.env["id.delivery.trip.cost"].create(
            {
                "date": date.today(),
                "vehicle_id": vehicle.id,
                "fuel_cost": 100000.0,
                "helper_cost": 75000.0,
            }
        )
        self.assertAlmostEqual(cost.total_cost, 175000.0, places=2)
        records = self.env["id.wms.fleet.cost"].search([("vehicle_id", "=", vehicle.id)])
        for record in records:
            self.assertGreaterEqual(record.total_cost, 0.0)
            self.assertGreaterEqual(record.cost_ratio_percent, 0.0)

    def test_wms_dashboard_service(self):
        service = self.env["id.wms.dashboard"]
        filters = service.get_filters()
        self.assertIn("categories", filters)
        self.assertIn("vehicles", filters)
        data = service.get_data()
        self.assertIn("kpi", data)
        self.assertIn("expiry_buckets", data)
        self.assertIn("categories", data)
        self.assertEqual(len(data["expiry_buckets"]), 3)
        self.assertIn("total_rejections", data["kpi"])

    def test_rejection_count_aggregation(self):
        service = self.env["id.wms.dashboard"]
        delivery = self.env["id.wms.delivery"]
        for reasons, expected in [([], 0), (["store_closed"] * 3, 3),
                                  (["store_closed"] * 3 + ["packaging_damaged"] * 2, 5)]:
            rows = [{"reject_reason": reason, "state": "cancel", "is_delivered": False,
                     "is_late": False, "delivered_value": 0} for reason in reasons]
            with patch.object(type(delivery), "search_read", return_value=rows):
                data = service.get_data()
            self.assertEqual(data["kpi"]["total_rejections"], expected)
            self.assertEqual(sum(r["count"] for r in data["rejections"]), expected)
        with patch.object(type(delivery), "search_read", return_value=[]):
            self.assertIsNone(service.get_data()["kpi"]["fulfillment_rate"])

    def test_vehicle_rejection_numerator_uses_same_delivery_population(self):
        delivery = self.env["id.wms.delivery"]
        reject = self.env["id.wms.reject"]
        accepted = [{"reject_reason": "not_recorded", "state": "done", "is_delivered": True,
                     "is_late": False, "delivered_value": 1000000}]
        with patch.object(type(delivery), "search_read", return_value=accepted) as read, \
             patch.object(type(reject), "search_read", return_value=[{"reason": "store_closed", "picking_count": 2}]):
            data = self.env["id.wms.dashboard"].get_data(vehicle_id=99)
        self.assertIn(("vehicle_id", "=", 99), read.call_args.args[0])
        self.assertEqual(data["kpi"]["total_deliveries"], 1)
        self.assertEqual(data["kpi"]["total_rejections"], 0)
        self.assertEqual(data["kpi"]["rejection_rate"], 0)

    def test_direct_stock_view_isolated_by_role_and_company(self):
        from odoo.exceptions import AccessError
        other = self.env["res.company"].create({"name": "Foreign stock company"})
        location = self.env["stock.location"].create({
            "name": "Foreign internal", "usage": "internal", "company_id": other.id})
        product = self.env["product.product"].create({
            "name": "Foreign stock probe", "type": "consu", "is_storable": True})
        self.env["stock.quant"].with_company(other)._update_available_quantity(product, location, 5)
        self.env.flush_all()
        view = self.env["id.wms.stock.category"]
        self.assertTrue(view.sudo().search([("company_id", "=", other.id)]))
        user = self.env["res.users"].with_context(no_reset_password=True).create({"name": "Stock access probe",
            "login": "stock_dashboard_probe", "company_id": self.env.company.id,
            "company_ids": [(6, 0, [self.env.company.id])],
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])]})
        with self.assertRaises(AccessError):
            view.with_user(user).search([])
        user.group_ids = [(4, self.env.ref("stock.group_stock_user").id)]
        self.assertFalse(view.with_user(user).search([("company_id", "=", other.id)]))

    def test_category_rows_keep_company_identity(self):
        model = self.env["id.wms.stock.category"]
        rows = [{"id": 11, "company_id": [1, "A"], "fmcg_category": "food",
                 "qty_on_hand": 2, "stock_value": 20, "product_count": 1},
                {"id": 22, "company_id": [2, "B"], "fmcg_category": "food",
                 "qty_on_hand": 3, "stock_value": 30, "product_count": 1}]
        with patch.object(type(model), "search_read", return_value=rows):
            data = self.env["id.wms.dashboard"].get_data()
        self.assertEqual(data["kpi"]["total_stock_value"], 50)
        self.assertEqual({c["key"] for c in data["categories"]}, {11, 22})
        self.assertEqual({c["company"] for c in data["categories"]}, {"A", "B"})
