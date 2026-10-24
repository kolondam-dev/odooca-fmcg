from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    channel_id = fields.Many2one("id.channel", string="Distribution Channel", index=True)
    tier_id = fields.Many2one("id.tier", string="Customer Tier", index=True)
    coverage_area_id = fields.Many2one("id.coverage.area", string="Coverage Area", index=True)
    district_id = fields.Many2one("id.district", string="Kecamatan (District)", index=True)
    subdistrict_id = fields.Many2one("id.subdistrict", string="Kelurahan / Desa", index=True)
    principal_ids = fields.Many2many(
        "id.principal",
        "partner_principal_rel",
        "partner_id",
        "principal_id",
        string="Authorized Principals",
    )
    credit_mode = fields.Selection(
        [
            ("strict", "Strict Lock (Wajib Lunas Sebelum Faktur Baru)"),
            ("limit", "Berbasis Limit Kredit"),
            ("limit_due", "Limit dan Batas Jatuh Tempo"),
            ("approval", "Override dengan Approval"),
        ],
        string="Credit Policy Mode",
        default="limit",
        help="Kebijakan kredit outlet saat transaksi baru diajukan (Playbook §3.6)",
    )
    pic_name = fields.Char(string="Outlet PIC Name")
    pic_phone = fields.Char(string="Outlet PIC Phone")
    delivery_notes = fields.Text(string="Delivery & Staging Notes")
