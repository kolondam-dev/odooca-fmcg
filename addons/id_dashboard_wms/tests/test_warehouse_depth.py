from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.delivery_cohort import local_day


@tagged("post_install", "-at_install")
class TestWarehouseDepth(TransactionCase):
    def _source(self):
        wh = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        product = self.env["product.product"].create({"name": "Warehouse depth carton", "type": "consu",
            "is_storable": True, "carton_qty": 12, "carton_length_cm": 100, "carton_width_cm": 100,
            "carton_height_cm": 100, "carton_weight_kg": 24})
        zone = self.env["stock.location"].create({"name": "Measured zone", "location_id": wh.lot_stock_id.id,
            "usage": "internal", "company_id": self.env.company.id, "fmcg_storage_kind": "zone",
            "fmcg_usable_cbm": 10, "fmcg_capacity_source": "Signed warehouse survey",
            "fmcg_length_m": 10, "fmcg_width_m": 10, "fmcg_height_m": 5,
            "fmcg_frame": "WH surveyed origin", "fmcg_spatial_verified": True})
        day = str(local_day(fields.Datetime.now()))
        return wh, product, zone, day

    def test_native_package_hierarchy_capacity_unknown_and_geometry(self):
        wh, product, zone, day = self._source()
        pallet_type = self.env["stock.package.type"].create({"name": "Physical pallet", "is_fmcg_pallet": True})
        category = self.env["stock.storage.category"].create({"name": "Measured pallet bay", "max_weight": 100,
            "package_capacity_ids": [(0, 0, {"package_type_id": pallet_type.id, "quantity": 4})]})
        zone.storage_category_id = category
        pallet = self.env["stock.package"].create({"name": "Physical outer pallet", "package_type_id": pallet_type.id})
        carton = self.env["stock.package"].create({"name": "Inner carton", "parent_package_id": pallet.id})
        self.env["stock.quant"]._update_available_quantity(product, zone, 24, package_id=carton)
        depth = self.env["id.warehouse.depth"]
        data = depth._data(day, day, wh.id)
        row = next(r for r in data["locations"] if r["id"] == zone.id)
        self.assertEqual((row["volume"], row["volume_pct"], row["pallets"], row["slots"], row["slot_pct"]),
                         (2, 20, 1, 4, 25))
        self.assertTrue(row["verified"])
        product.carton_length_cm = 0
        row = next(r for r in depth._data(day, day, wh.id)["locations"] if r["id"] == zone.id)
        self.assertIsNone(row["volume_pct"])
        self.assertEqual(row["missing_volume"], 1)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["stock.location"].create({"name": "Outside parent", "location_id": zone.id,
                "company_id": self.env.company.id, "usage": "internal", "fmcg_storage_kind": "bin",
                "fmcg_capacity_source": "Survey", "fmcg_frame": zone.fmcg_frame, "fmcg_spatial_verified": True,
                "fmcg_length_m": 2, "fmcg_width_m": 2, "fmcg_height_m": 2, "fmcg_x_m": 9})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            wh.write({"slow_stock_days": 200, "dead_stock_days": 100})

    def test_clock_server_facts_native_completion_and_worker_guard(self):
        wh, product, zone, day = self._source()
        pick = self.env["stock.picking"].create({"picking_type_id": wh.out_type_id.id,
            "location_id": zone.id, "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "move_ids": [(0, 0, {"product_id": product.id, "product_uom": product.uom_id.id,
                "product_uom_qty": 12, "quantity": 12, "location_id": zone.id,
                "location_dest_id": self.env.ref("stock.stock_location_customers").id})]})
        pick.move_ids.write({"state": "assigned", "picked": True})
        Clock = self.env["id.warehouse.clock"]
        clock = Clock.with_context(default_state="done", default_started_at="2000-01-01").create({
            "name": "Picking elapsed", "picking_id": pick.id, "kind": "picking"})
        self.assertEqual(clock.state, "draft")
        self.assertFalse(clock.started_at)
        clock.action_start()
        clock.action_start()
        duplicate = Clock.create({"name": "Duplicate", "picking_id": pick.id, "kind": "picking"})
        with self.assertRaises(UserError):
            duplicate.action_start()
        with self.assertRaises(UserError):
            clock.action_complete()
        with self.assertRaises(AccessError):
            clock.write({"started_at": "2000-01-01"})
        worker = self.env["res.users"].with_context(no_reset_password=True).create({"name": "Other picker",
            "login": "warehouse_other_picker", "company_id": self.env.company.id,
            "company_ids": [(6, 0, self.env.company.ids)],
            "group_ids": [(6, 0, [self.env.ref("stock.group_stock_user").id])]})
        pick.move_ids.state = "done"
        with self.assertRaises(AccessError):
            clock.with_user(worker).action_complete()
        with patch.object(fields.Datetime, "now", return_value=clock.started_at+timedelta(minutes=12)):
            clock.action_complete()
        self.assertEqual(clock.duration_minutes, 12)
        ended = clock.ended_at
        clock.action_complete()
        self.assertEqual(clock.ended_at, ended)
        with self.assertRaises(AccessError):
            clock.unlink()
        data = self.env["id.warehouse.depth"]._data(day, day, wh.id)
        row = next(c for c in data["clocks"] if c["kind"] == "picking")
        self.assertEqual((row["count"], row["median_minutes"], row["p90_minutes"]), (1, 12, 12))
        self.assertFalse(self.env["id.warehouse.depth"].with_user(worker)._valuation_control()["available"])
        with self.assertRaises(AccessError):
            zone.with_user(worker).write({"fmcg_usable_cbm": 100})

    def test_movement_flow_stock_age_and_selected_company_scope(self):
        wh, product, zone, day = self._source()
        self.env["stock.quant"]._update_available_quantity(product, zone, 24)
        quant = self.env["stock.quant"].search([("product_id", "=", product.id), ("location_id", "=", zone.id)])
        quant.in_date = fields.Datetime.now()-timedelta(days=200)
        data = self.env["id.warehouse.depth"]._data(day, day, wh.id)
        sku = next(r for r in data["skus"] if r["product_id"] == product.id)
        self.assertEqual((sku["quantity"], sku["available"], sku["inactive"]), (24, 24, True))
        # Native done movement line, not a fabricated quantity aggregate across unrelated SKUs.
        move = self.env["stock.move"].create({"product_id": product.id, "product_uom": product.uom_id.id,
            "product_uom_qty": 1, "quantity": 1, "location_id": zone.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id, "state": "done"})
        self.env["stock.move.line"].create({"move_id": move.id, "product_id": product.id,
            "product_uom_id": product.uom_id.id, "quantity": 1, "location_id": zone.id,
            "location_dest_id": move.location_dest_id.id, "date": fields.Datetime.now()})
        data = self.env["id.warehouse.depth"]._data(day, day, wh.id)
        self.assertEqual(data["flow_counts"]["shipped"], 1)
        sku = next(r for r in data["skus"] if r["product_id"] == product.id)
        self.assertFalse(sku["inactive"])
        foreign = self.env["res.company"].create({"name": "Other warehouse depth"})
        other = self.env["stock.warehouse"].search([("company_id", "=", foreign.id)], limit=1)
        with self.assertRaises(UserError):
            self.env["id.warehouse.depth"].with_context(allowed_company_ids=wh.company_id.ids)._data(day, day, other.id)

    def test_native_valuation_mapping_and_posted_ledger_control(self):
        wh, product, zone, day = self._source()
        company = self.env.company
        company.currency_id.active = True
        account = self.env["account.account"].create({"name": "Mapped stock valuation control", "code": "993501",
            "account_type": "asset_current", "company_ids": [(6, 0, company.ids)]})
        offset = self.env["account.account"].create({"name": "Stock control opening offset", "code": "993502",
            "account_type": "equity", "company_ids": [(6, 0, company.ids)]})
        company.account_stock_valuation_id = account
        self.env["product.category"].search([]).with_company(company).write({
            "property_stock_valuation_account_id": account.id})
        journal = self.env["account.journal"].create({"name": "Warehouse control", "code": "WDC", "type": "general"})
        entry = self.env["account.move"].create({"journal_id": journal.id, "date": fields.Date.context_today(self),
            "line_ids": [(0, 0, {"account_id": account.id, "debit": 240}),
                         (0, 0, {"account_id": offset.id, "credit": 240})]})
        entry.action_post()
        result = self.env["id.warehouse.depth"]._valuation_control()
        row = next(r for r in result["rows"] if r["company"] == company.name)
        self.assertTrue(row["available"])
        self.assertEqual(row["ledger_value"], 240)
        self.assertAlmostEqual(row["gap"], row["native_value"]-240)
        self.assertIn(("account_id", "in", [account.id]), row["domain"])
