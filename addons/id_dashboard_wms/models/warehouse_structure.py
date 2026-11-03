"""Extend native locations/packages; no parallel bin or pallet inventory ledger."""
from math import isfinite

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

GEO = ("fmcg_length_m", "fmcg_width_m", "fmcg_height_m", "fmcg_x_m", "fmcg_y_m", "fmcg_z_m")


class WarehousePolicy(models.Model):
    _inherit = "stock.warehouse"

    slow_stock_days = fields.Integer(default=90, string="Slow Stock Observation Days")
    dead_stock_days = fields.Integer(default=180, string="Inactive Stock Observation Days")

    @api.constrains("slow_stock_days", "dead_stock_days")
    def _check_observation_policy(self):
        for rec in self:
            if not 1 <= rec.slow_stock_days <= rec.dead_stock_days <= 3650:
                raise ValidationError(_("Stock observation days must satisfy 1 <= slow <= inactive <= 3650."))


class PalletPackageType(models.Model):
    _inherit = "stock.package.type"

    is_fmcg_pallet = fields.Boolean(string="Physical Pallet Type")

    @api.model_create_multi
    def create(self, vals_list):
        flagged = any(vals.get("is_fmcg_pallet", self.env.context.get("default_is_fmcg_pallet"))
                      for vals in vals_list)
        if flagged and not (
                self.env.user.has_group("stock.group_stock_manager") or self.env.user.has_group("base.group_system")):
            raise AccessError(_("Warehouse manager access is required for pallet classification."))
        return super().create(vals_list)

    def write(self, vals):
        if "is_fmcg_pallet" in vals and not (self.env.user.has_group("stock.group_stock_manager")
                                             or self.env.user.has_group("base.group_system")):
            raise AccessError(_("Warehouse manager access is required for pallet classification."))
        return super().write(vals)


class WarehouseLocation(models.Model):
    _inherit = "stock.location"

    fmcg_storage_kind = fields.Selection([("zone", "Zone"), ("rack", "Rack"), ("bin", "Bin"),
                                         ("pallet", "Pallet Position")], string="Physical Storage Role")
    fmcg_usable_cbm = fields.Float(string="Usable Storage Volume (m³)", digits=(16, 4))
    fmcg_pallet_slots = fields.Integer(string="Explicit Pallet Slots")
    fmcg_capacity_source = fields.Char(string="Capacity / Layout Source")
    fmcg_length_m = fields.Float(string="Length (m)", digits=(16, 4))
    fmcg_width_m = fields.Float(string="Width (m)", digits=(16, 4))
    fmcg_height_m = fields.Float(string="Height (m)", digits=(16, 4))
    fmcg_x_m = fields.Float(string="Warehouse Frame X (m)", digits=(16, 4))
    fmcg_y_m = fields.Float(string="Warehouse Frame Y (m)", digits=(16, 4))
    fmcg_z_m = fields.Float(string="Warehouse Frame Z (m)", digits=(16, 4))
    fmcg_frame = fields.Char(string="Warehouse Coordinate Frame")
    fmcg_spatial_verified = fields.Boolean(string="Layout Source Verified")

    @api.model_create_multi
    def create(self, vals_list):
        protected = set(self._fields).intersection(
            key[8:] for key in self.env.context if key.startswith("default_fmcg_"))
        if (protected or any(any(key.startswith("fmcg_") for key in vals) for vals in vals_list)) and not (
                self.env.user.has_group("stock.group_stock_manager") or self.env.user.has_group("base.group_system")):
            raise AccessError(_("Warehouse manager access is required for storage master changes."))
        return super().create(vals_list)

    def write(self, vals):
        if any(key.startswith("fmcg_") for key in vals) and not (
                self.env.user.has_group("stock.group_stock_manager") or self.env.user.has_group("base.group_system")):
            raise AccessError(_("Warehouse manager access is required for storage master changes."))
        return super().write(vals)

    @api.constrains("fmcg_storage_kind", "fmcg_usable_cbm", "fmcg_pallet_slots", "fmcg_capacity_source",
                    "fmcg_length_m", "fmcg_width_m", "fmcg_height_m", "fmcg_x_m", "fmcg_y_m", "fmcg_z_m",
                    "fmcg_frame", "fmcg_spatial_verified", "location_id", "company_id", "usage")
    def _check_physical_master(self):
        affected = self | self.child_ids.filtered("fmcg_spatial_verified")
        for rec in affected:
            if any(not isfinite(rec[key]) for key in GEO+("fmcg_usable_cbm",)):
                raise ValidationError(_("Storage dimensions and coordinates must be finite."))
            if any(rec[key] < 0 for key in GEO[:3]) or rec.fmcg_usable_cbm < 0 or rec.fmcg_pallet_slots < 0:
                raise ValidationError(_("Storage dimensions and capacities cannot be negative."))
            if rec.fmcg_usable_cbm or rec.fmcg_pallet_slots:
                if rec.usage not in ("internal", "view") or not rec.company_id or not (
                        rec.fmcg_capacity_source or "").strip():
                    raise ValidationError(_("Physical capacity needs a company-owned storage node and source."))
            if rec.fmcg_spatial_verified:
                if (rec.usage not in ("internal", "view") or not rec.company_id
                        or not rec.fmcg_storage_kind or not rec.fmcg_frame
                        or not rec.fmcg_capacity_source):
                    raise ValidationError(_("Verified layout needs company, role, coordinate frame and source."))
                if not all(rec[key] > 0 for key in GEO[:3]):
                    raise ValidationError(_("Verified layout needs positive length, width and height."))
                if rec.fmcg_usable_cbm > rec.fmcg_length_m*rec.fmcg_width_m*rec.fmcg_height_m + .000001:
                    raise ValidationError(_("Usable volume exceeds the measured storage envelope."))
                parent = rec.location_id
                if parent.fmcg_spatial_verified:
                    if parent.fmcg_frame != rec.fmcg_frame:
                        raise ValidationError(_("Parent and child must use the same warehouse coordinate frame."))
                    for axis, dim in zip(GEO[3:], GEO[:3]):
                        if (rec[axis] < parent[axis]-.000001
                                or rec[axis]+rec[dim] > parent[axis]+parent[dim]+.000001):
                            raise ValidationError(_("Verified child geometry exceeds its parent envelope."))
