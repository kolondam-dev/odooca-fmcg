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
        vehicle = self.env["fleet.vehicle"].search([], limit=1)
        if not vehicle:
            self.skipTest("No fleet vehicle available in this database")
        cost = self.env["id.delivery.trip.cost"].create(
            {
                "date": date.today(),
                "vehicle_id": vehicle.id,
                "fuel_cost": 100000.0,
                "driver_allowance": 50000.0,
                "toll_cost": 25000.0,
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
        """Verify delivery rejection count aggregation:
        - Case 1: 0 rejections -> total is 0
        - Case 2: 1 reason with count 3 -> total is 3 (not 1)
        - Case 3: 2 reasons with count 3 and 2 -> total is 5 (3 + 2 = 5)
        """
        service = self.env["id.wms.dashboard"]
        RejectModel = self.env["id.wms.reject"]

        # Case 1: 0 rejections -> 0
        with patch.object(type(RejectModel), "search_read", return_value=[]):
            data = service.get_data()
            self.assertEqual(data["kpi"]["total_rejections"], 0)
            self.assertEqual(len(data["rejections"]), 0)

        # Case 2: 1 reason group with count 3 -> total is 3 (not 1)
        mock_data_1 = [
            {"reason": "store_closed", "picking_count": 3, "rejected_value": 300000.0}
        ]
        with patch.object(type(RejectModel), "search_read", return_value=mock_data_1):
            data = service.get_data()
            self.assertEqual(data["kpi"]["total_rejections"], 3)
            self.assertEqual(len(data["rejections"]), 1)
            self.assertEqual(data["rejections"][0]["count"], 3)

        # Case 3: 2 reason groups with counts 3 and 2 -> total is 5 (3 + 2 = 5)
        mock_data_2 = [
            {"reason": "store_closed", "picking_count": 3, "rejected_value": 300000.0},
            {"reason": "packaging_damaged", "picking_count": 2, "rejected_value": 200000.0},
        ]
        with patch.object(type(RejectModel), "search_read", return_value=mock_data_2):
            data = service.get_data()
            self.assertEqual(data["kpi"]["total_rejections"], 5)
            self.assertEqual(len(data["rejections"]), 2)
            self.assertEqual(sum(r["count"] for r in data["rejections"]), 5)
