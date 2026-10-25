from odoo import fields, models


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    fleet_type_id = fields.Many2one("id.fleet.type", string="Tipe Operasional FMCG", index=True)
    capacity_cbm = fields.Float(string="Kapasitas Kubikasi (m³)", digits=(6, 2))
    capacity_ton = fields.Float(string="Kapasitas Tonase (Ton)", digits=(6, 2))
    box_length = fields.Float(string="Panjang Box (m)", digits=(4, 2))
    box_width = fields.Float(string="Lebar Box (m)", digits=(4, 2))
    box_height = fields.Float(string="Tinggi Box (m)", digits=(4, 2))
    stnk_expiry = fields.Date(string="Masa Berlaku STNK")
    kir_expiry = fields.Date(string="Masa Berlaku KIR")
    operational_route = fields.Char(string="Rute / Wilayah Operasional")
