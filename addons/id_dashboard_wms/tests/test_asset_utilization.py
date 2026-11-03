import json

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.asset_measure import measure
from ..models.delivery_cohort import local_day


@tagged("post_install", "-at_install")
class TestAssetUtilization(TransactionCase):
    def _source(self):
        self.env.company.currency_id.active = True
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        product = self.env["product.product"].create({"name": "Measured carton SKU", "type": "consu",
            "is_storable": True, "carton_qty": 12, "carton_length_cm": 100, "carton_width_cm": 100,
            "carton_height_cm": 100, "carton_weight_kg": 24})
        brand = self.env["fleet.vehicle.model.brand"].create({"name": "Asset brand"})
        model = self.env["fleet.vehicle.model"].create({"name": "Asset vehicle", "brand_id": brand.id})
        vehicle = self.env["fleet.vehicle"].create({"model_id": model.id, "capacity_cbm": 2, "capacity_ton": .1})
        picking = self.env["stock.picking"].create({"picking_type_id": warehouse.out_type_id.id,
            "location_id": warehouse.lot_stock_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "fmcg_vehicle_id": vehicle.id,
            "move_ids": [(0, 0, {"product_id": product.id, "product_uom": product.uom_id.id,
                "product_uom_qty": 12, "quantity": 12, "location_id": warehouse.lot_stock_id.id,
                "location_dest_id": self.env.ref("stock.stock_location_customers").id})]})
        picking.move_ids.write({"state": "assigned", "picked": True})
        trip = self.env["id.asset.trip"].create({"name": "Asset trip", "vehicle_id": vehicle.id,
            "picking_ids": [(6, 0, picking.ids)]})
        return warehouse, product, vehicle, picking, trip

    def test_frozen_departure_survives_master_changes_and_closure(self):
        warehouse, product, vehicle, picking, trip = self._source()
        trip.action_depart()
        snapshot = json.loads(trip.snapshot_json)
        self.assertEqual((snapshot["lines"][0]["volume"], snapshot["lines"][0]["kg"]), (1, 24))
        product.carton_length_cm = 200
        vehicle.capacity_cbm = 200
        picking.move_ids.state = "done"
        trip.write({"odometer_end_km": 100, "fuel_cost": 60, "cost_basis": "QA receipt"})
        trip.action_close()
        day = str(local_day(trip.departed_at))
        result = self.env["id.asset.utilization"]._data(day, day, vehicle.id)
        self.assertEqual(result["trip_count"], 1)
        self.assertEqual((result["volume_pct"], result["weight_pct"], result["km"]), (50, 24, 100))
        self.assertEqual(result["cost_per_km"], .6)
        self.assertIsNone(result["cost_per_delivered_dpp"])  # No SO linkage, never manufacture revenue.
        with self.assertRaises(AccessError):
            trip.write({"fuel_cost": 0})
        with self.assertRaises(AccessError):
            trip.unlink()
        with self.assertRaises(AccessError):
            self.env["id.asset.trip"].create({"name": "Spoof", "vehicle_id": vehicle.id, "state": "closed"})

    def test_duplicate_departure_wrong_vehicle_and_context_spoof_rejected(self):
        warehouse, product, vehicle, picking, trip = self._source()
        trip.action_depart()
        duplicate = self.env["id.asset.trip"].with_context(
            default_state="closed", default_snapshot_json="spoof").create({
            "name": "Duplicate", "vehicle_id": vehicle.id, "picking_ids": [(6, 0, picking.ids)]})
        self.assertEqual(duplicate.state, "draft")
        self.assertFalse(duplicate.snapshot_json)
        with self.assertRaises(UserError):
            duplicate.action_depart()
        with self.assertRaises(AccessError):
            trip.write({"snapshot_json": "spoof"})

    def test_warehouse_coverage_negative_positions_and_capacity_validation(self):
        warehouse, product, vehicle, picking, trip = self._source()
        warehouse.write({"usable_volume_cbm": 10, "capacity_basis": "Usable storage survey"})
        self.env["stock.quant"]._update_available_quantity(product, warehouse.lot_stock_id, 24)
        self.env.flush_all()
        day = str(self.env["id.delivery.cohort"]._data()["end"])
        data = self.env["id.asset.utilization"]._data(day, day, vehicle.id)
        row = next(w for w in data["warehouses"] if w["id"] == warehouse.id)
        self.assertEqual((row["volume"], row["occupancy"]), (2, 20))
        product.carton_length_cm = 0
        self.env.flush_all()
        data = self.env["id.asset.utilization"]._data(day, day, vehicle.id)
        row = next(w for w in data["warehouses"] if w["id"] == warehouse.id)
        self.assertIsNone(row["occupancy"])
        self.assertEqual(row["missing_volume"], 1)
        with self.assertRaises(ValidationError):
            warehouse.usable_volume_cbm = -1
        with self.assertRaises(ValidationError):
            warehouse.write({"usable_volume_cbm": 10, "capacity_basis": False})
        self.assertEqual(measure(product, 12), (None, 24))

    def test_trip_read_only_stock_user_and_foreign_company_isolation(self):
        warehouse, product, vehicle, picking, trip = self._source()
        user = self.env["res.users"].with_context(no_reset_password=True).create({"name": "Asset reader",
            "login": "asset_reader", "company_ids": [(6, 0, self.env.company.ids)],
            "group_ids": [(6, 0, [self.env.ref("stock.group_stock_user").id])]})
        with self.assertRaises(AccessError):
            trip.with_user(user).action_depart()
        foreign = self.env["res.company"].create({"name": "Foreign asset company"})
        other = self.env["id.asset.trip"].create({"name": "Foreign trip", "company_id": foreign.id,
            "vehicle_id": vehicle.copy({"company_id": foreign.id}).id})
        self.assertFalse(self.env["id.asset.trip"].with_user(user).search([("id", "=", other.id)]))
