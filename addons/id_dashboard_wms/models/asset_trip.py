"""Explicit departure snapshots; no reconstruction of historical trips from DOs."""
import json
from math import isfinite

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .asset_measure import measure

FACTS = {"state", "departed_at", "closed_at", "snapshot_json", "departed_by", "closed_by"}


class AssetWarehouse(models.Model):
    _inherit = "stock.warehouse"

    usable_volume_cbm = fields.Float(string="Usable Stock Capacity (m³)")
    capacity_basis = fields.Char(string="Capacity Source / Basis")

    @api.constrains("usable_volume_cbm", "capacity_basis")
    def _check_capacity(self):
        for rec in self:
            if not isfinite(rec.usable_volume_cbm) or rec.usable_volume_cbm < 0:
                raise ValidationError(_("Capacity must be finite and nonnegative."))
            if rec.usable_volume_cbm > 0 and not rec.capacity_basis:
                raise ValidationError(_("Record the usable capacity source."))


class AssetTrip(models.Model):
    _name = "id.asset.trip"
    _description = "Frozen Delivery Load and Trip"
    _check_company_auto = True
    _order = "departed_at desc, id desc"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    vehicle_id = fields.Many2one("fleet.vehicle", required=True, check_company=True)
    picking_ids = fields.Many2many("stock.picking", check_company=True, string="Loaded Deliveries")
    state = fields.Selection([("draft", "Draft"), ("departed", "Departed"), ("closed", "Closed")],
                             default="draft", readonly=True, required=True, copy=False)
    departed_at = fields.Datetime(readonly=True, index=True, copy=False)
    departed_by = fields.Many2one("res.users", readonly=True, copy=False)
    closed_at = fields.Datetime(readonly=True, copy=False)
    closed_by = fields.Many2one("res.users", readonly=True, copy=False)
    snapshot_json = fields.Text(readonly=True, copy=False)
    odometer_start_km = fields.Float(string="Departure Odometer (km)")
    odometer_end_km = fields.Float(string="Return Odometer (km)")
    fuel_cost = fields.Monetary()
    helper_cost = fields.Monetary()
    other_delivery_cost = fields.Monetary(string="Other Direct Delivery Cost")
    cost_basis = fields.Char(string="Cost Receipt / Source")
    note = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if FACTS.intersection(vals) - ({"state"} if vals.get("state") == "draft" else set()):
                raise AccessError(_("Trip facts are written by departure and closure actions only."))
            vals.update(state="draft", departed_at=False, closed_at=False, snapshot_json=False,
                        departed_by=False, closed_by=False)
        return super().create(vals_list)

    def write(self, vals):
        if FACTS.intersection(vals):
            raise AccessError(_("Trip facts are written by departure and closure actions only."))
        for rec in self:
            if rec.state == "closed" or (rec.state == "departed" and set(vals) - {
                    "odometer_end_km", "fuel_cost", "helper_cost", "other_delivery_cost", "cost_basis", "note"}):
                raise AccessError(_("Departure facts and closed trips are immutable."))
        return super().write(vals)

    def unlink(self):
        if any(rec.state != "draft" for rec in self):
            raise AccessError(_("Departed trips cannot be deleted."))
        return super().unlink()

    @api.constrains("odometer_start_km", "odometer_end_km", "fuel_cost", "helper_cost", "other_delivery_cost")
    def _check_numbers(self):
        for rec in self:
            values = [rec.odometer_start_km, rec.odometer_end_km, rec.fuel_cost,
                      rec.helper_cost, rec.other_delivery_cost]
            if any(not isfinite(v) or v < 0 for v in values):
                raise ValidationError(_("Trip readings and costs must be finite and nonnegative."))

    def _lock(self):
        self.check_access("write")
        for rec in self.sorted("id"):
            self.env.cr.execute("UPDATE id_asset_trip SET write_date=write_date WHERE id=%s", [rec.id])

    def action_depart(self):
        self._lock()
        for rec in self:
            if rec.state != "draft" or not rec.picking_ids:
                raise UserError(_("Select loaded deliveries on a draft trip."))
            vehicle = rec.vehicle_id
            if vehicle.company_id != rec.company_id:
                raise UserError(_("Trip vehicle must belong to the trip company."))
            self.env.cr.execute("UPDATE fleet_vehicle SET write_date=write_date WHERE id=%s", [vehicle.id])
            if self.search_count([("id", "!=", rec.id), ("vehicle_id", "=", vehicle.id), ("state", "=", "departed")]):
                raise UserError(_("The vehicle already has an open trip."))
            prior = self.search([("vehicle_id", "=", vehicle.id), ("state", "=", "closed")],
                                order="closed_at desc, id desc", limit=1)
            if prior and rec.odometer_start_km < prior.odometer_end_km:
                raise UserError(_("Departure odometer cannot precede the last closed trip reading."))
            picks = rec.picking_ids
            # RR write conflict serializes competing departure attempts, including the DO relation.
            for pick in picks.sorted("id"):
                pick.check_access("read")
                self.env.cr.execute("UPDATE stock_picking SET write_date=write_date WHERE id=%s", [pick.id])
            if self.search_count([("id", "!=", rec.id), ("state", "!=", "draft"),
                                  ("picking_ids", "in", picks.ids)]):
                raise UserError(_("A delivery already belongs to a departed trip."))
            if any(p.company_id != rec.company_id or p.fmcg_vehicle_id != rec.vehicle_id
                   or p.picking_type_code != "outgoing" or p.location_dest_id.usage != "customer"
                   or p.state != "assigned" for p in picks):
                raise UserError(_("Deliveries must be ready, customer-bound, and match company and vehicle."))
            moves = picks.move_ids.filtered(lambda m: m.state != "cancel")
            if not moves or any(not m.picked or not isfinite(m.quantity) or m.quantity <= 0 for m in moves):
                raise UserError(_("Confirm picked quantities before recording departure."))
            rows = []
            for move in moves:
                qty = move.product_uom._compute_quantity(move.quantity, move.product_id.uom_id, round=False)
                vol, kg = measure(move.product_id, qty)
                rows.append({"move_id": move.id, "picking_id": move.picking_id.id,
                             "product_id": move.product_id.id, "quantity": qty, "volume": vol, "kg": kg})
            vehicle = rec.vehicle_id
            snapshot = {"lines": rows, "capacity_volume": (vehicle.capacity_cbm
                        if isfinite(vehicle.capacity_cbm) and vehicle.capacity_cbm > 0 else None),
                        "capacity_kg": (vehicle.capacity_ton*1000
                        if isfinite(vehicle.capacity_ton) and vehicle.capacity_ton > 0 else None)}
            super(AssetTrip, rec).write({"state": "departed", "departed_at": fields.Datetime.now(),
                                        "snapshot_json": json.dumps(snapshot, allow_nan=False),
                                        "departed_by": self.env.uid})
        return True

    def action_close(self):
        self._lock()
        for rec in self:
            if rec.state != "departed" or any(p.state not in ("done", "cancel") for p in rec.picking_ids):
                raise UserError(_("Close all deliveries before closing the trip."))
            if rec.odometer_end_km < rec.odometer_start_km or not rec.cost_basis:
                raise UserError(_("Check return odometer and record the cost source, including zero-cost trips."))
            snap = json.loads(rec.snapshot_json)
            delivered = 0.0
            known = True
            for pick in rec.picking_ids:
                for move in pick.move_ids.filtered(lambda m: m.state == "done"):
                    line = move.sale_line_id
                    if not line or line.currency_id != rec.currency_id or line.product_uom_qty <= 0:
                        known = False
                        continue
                    qty = move.product_uom._compute_quantity(move.quantity, line.product_uom_id, round=False)
                    delivered += line.price_subtotal / line.product_uom_qty * qty
            snap["delivered_dpp"] = delivered if known else None
            super(AssetTrip, rec).write({"state": "closed", "closed_at": fields.Datetime.now(),
                                        "snapshot_json": json.dumps(snap, allow_nan=False), "closed_by": self.env.uid})
        return True
