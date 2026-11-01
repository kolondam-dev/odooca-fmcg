import uuid
from odoo import fields
from odoo.tests import TransactionCase, tagged
from .test_read_api import MobileFixture


@tagged("post_install", "-at_install")
class TestMobileCommandsApi(MobileFixture, TransactionCase):

    def setUp(self):
        super().setUp()
        self.outlet = self.env["res.partner"].create({
            "name": "Outlet Test Command",
            "company_id": self.company.id,
            "partner_latitude": 1.487,
            "partner_longitude": 124.842,
        })
        self.assignment = self.env["id.mobile.workday"].create({
            "user_id": self.mobile.id,
            "company_id": self.company.id,
            "business_date": fields.Date.today(),
            "warehouse_id": self.warehouse.id,
            "pricelist_id": self.pricelist.id,
            "outlet_ids": [(6, 0, [self.outlet.id])],
            "product_ids": [(6, 0, [self.product.id])],
            "outlet_radius": 100,
        })

    def test_geofence_relaxed_radius(self):
        """Pastikan outlet radius 100m dan office 150m diterima oleh constraint."""
        self.assertEqual(self.assignment.outlet_radius, 100)
        office = self.env["id.mobile.office"].create({
            "name": "Kantor Pusat Manado",
            "company_id": self.company.id,
            "latitude": 1.488,
            "longitude": 124.843,
            "radius": 150,
            "coordinate_status": "verified",
            "coordinate_note": "Kantor Pusat Manado Radius 150m",
        })
        self.assertEqual(office.radius, 150)

    def test_sales_order_submit_idempotent(self):
        """Pastikan submit order membuat SO Odoo dan idempoten terhadap UUID yang sama."""
        cmd_uuid = str(uuid.uuid4())
        command = {
            "client_uuid": cmd_uuid,
            "type": "sales.order.submit",
            "occurred_at": "2026-11-01T10:00:00Z",
            "payload": {
                "outlet_id": str(self.outlet.id),
                "snapshot_version": "v1",
                "customer_po_number": "PO-TEST-001",
                "lines": [
                    {"product_id": str(self.product.id), "qty": "2", "uom": "carton"}
                ],
                "discount_request": {"percent": 5, "reason": "Promo Opening"},
            }
        }

        CommandModel = self.env["id.mobile.command"].with_user(self.mobile).with_company(self.company)
        receipt1 = CommandModel.process_command(command)

        self.assertEqual(receipt1["client_uuid"], cmd_uuid)
        self.assertIn(receipt1["status"], ["accepted", "needs_approval"])

        # Cek SO yang dibuat di Odoo
        so = self.env["sale.order"].search([("origin", "=", f"PWA Mobile Order {cmd_uuid[:8]}")])
        self.assertTrue(so.exists(), "Sales Order harus berhasil dibuat di Odoo!")
        self.assertEqual(so.partner_id, self.outlet)
        self.assertEqual(so.client_order_ref, "PO-TEST-001")
        self.assertEqual(len(so.order_line), 1)
        self.assertEqual(so.order_line.product_id, self.product)
        # 2 carton * 24 pcs = 48 unit
        self.assertEqual(so.order_line.product_uom_qty, 48.0)
        self.assertEqual(so.order_line.discount, 5.0)

        # Re-submit UUID yang sama -> Idempoten
        receipt2 = CommandModel.process_command(command)
        self.assertEqual(receipt1["reference"], receipt2["reference"])
        self.assertEqual(receipt1["status"], receipt2["status"])

    def test_visit_checkin_and_delivery_pod(self):
        """Pastikan check-in dan delivery POD tercatat dengan receipt yang valid."""
        CommandModel = self.env["id.mobile.command"].with_user(self.mobile).with_company(self.company)

        # Check-in
        checkin_uuid = str(uuid.uuid4())
        rc_in = CommandModel.process_command({
            "client_uuid": checkin_uuid,
            "type": "sales.visit.check_in",
            "payload": {"outlet_id": str(self.outlet.id)}
        })
        self.assertEqual(rc_in["status"], "accepted")

        # POD Delivery
        pod_uuid = str(uuid.uuid4())
        rc_pod = CommandModel.process_command({
            "client_uuid": pod_uuid,
            "type": "delivery.pod.submit",
            "payload": {"outcome": "delivered", "recipient": "Ko Freddy"}
        })
        self.assertEqual(rc_pod["status"], "accepted")
        self.assertEqual(rc_pod["reference"], f"POD-{pod_uuid[:8]}")
