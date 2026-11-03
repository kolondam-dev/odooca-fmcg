from datetime import datetime
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDeliveryCohort(TransactionCase):
    def test_backorder_cancel_backlog_and_mature_denominators(self):
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        product = self.env["product.product"].create({"name": "Cohort stock", "type": "consu", "is_storable": True})
        brand = self.env["fleet.vehicle.model.brand"].create({"name": "Cohort test brand"})
        model = self.env["fleet.vehicle.model"].create({"name": "Cohort test vehicle", "brand_id": brand.id})
        vehicle = self.env["fleet.vehicle"].create({"model_id": model.id})
        customer = self.env.ref("stock.stock_location_customers")

        def picking(demand, actual, state, done=None, parent=None, scheduled="2025-07-15 02:00:00"):
            rec = self.env["stock.picking"].create({"picking_type_id": warehouse.out_type_id.id,
                "location_id": warehouse.lot_stock_id.id, "location_dest_id": customer.id,
                "fmcg_vehicle_id": vehicle.id, "backorder_id": parent.id if parent else False,
                "move_ids": [(0, 0, {"name": "Cohort fixture", "product_id": product.id,
                    "product_uom": product.uom_id.id, "product_uom_qty": demand, "quantity": actual,
                    "location_id": warehouse.lot_stock_id.id, "location_dest_id": customer.id})]})
            # Read-model fixture: native records with explicit states/times, not a warehouse workflow test.
            rec.move_ids.write({"state": state, "date": done or scheduled})
            rec.scheduled_date = scheduled
            return rec

        partial = picking(6, 6, "done", "2025-07-15 01:00:00")
        picking(4, 4, "done", "2025-07-17 03:00:00", parent=partial)
        picking(10, 10, "done", "2025-07-15 01:00:00")
        cancel = picking(10, 0, "cancel")
        cancel.fmcg_reject_reason = "store_closed"
        picking(10, 0, "confirmed")
        picking(10, 0, "confirmed", scheduled="2025-07-20 02:00:00")
        self.env.flush_all()
        with patch.object(fields.Datetime, "now", return_value=datetime(2025, 7, 20, 4)):
            result = self.env["id.delivery.cohort"]._data("2025-07-15", "2025-07-20", vehicle.id)
        self.assertEqual(result["count"], 5)  # backorder is not a second denominator
        self.assertEqual(result["backlog"], 2)
        self.assertEqual(result["cancelled"], 1)
        self.assertEqual((result["h1_due"], result["h2_due"]), (4, 4))
        self.assertEqual(result["h1"], 25)
        self.assertEqual(result["h2"], 50)
        self.assertEqual(result["otif"], 20)
        self.assertEqual(result["reasons"], [{"reason": "store_closed", "count": 1}])
        self.assertEqual(len(result["source_ids"]), 6)
