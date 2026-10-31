from odoo import fields, models


class FmcgApprovalRule(models.Model):
    _name = "fmcg.approval.rule"
    _description = "Aturan Tingkatan Persetujuan (Approval Tier Rule)"
    _order = "tier_sequence, id"

    category_id = fields.Many2one(
        "fmcg.approval.category",
        string="Kategori Persetujuan",
        required=True,
        ondelete="cascade",
    )
    tier_sequence = fields.Integer(string="Tingkat (Tier)", default=1, required=True)
    name = fields.Char(string="Nama Tingkatan", required=True)
    approver_type = fields.Selection([
        ("group", "Grup Pengguna (Role / Wewenang)"),
        ("user", "Pengguna Spesifik (Spesific User)"),
        ("manager", "Atasan Langsung (Direct Manager / SPV)"),
    ], string="Tipe Approver", default="group", required=True)
    group_id = fields.Many2one("res.groups", string="Grup Wewenang Approver")
    user_id = fields.Many2one("res.users", string="Pengguna Approver")
    min_amount = fields.Float(string="Batas Nominal Minimal", default=0.0)
    max_amount = fields.Float(string="Batas Nominal Maksimal", default=0.0)
    min_discount = fields.Float(string="Batas Diskon Minimal (%)", default=0.0)
    max_discount = fields.Float(string="Batas Diskon Maksimal (%)", default=0.0)
    sla_hours = fields.Integer(string="Target SLA (Jam)", default=24)

