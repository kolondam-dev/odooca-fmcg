from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FmcgApprovalCategory(models.Model):
    _name = "fmcg.approval.category"
    _description = "Kategori Persetujuan FMCG"
    _order = "sequence, id"

    name = fields.Char(string="Nama Kategori", required=True)
    code = fields.Char(string="Kode Unik", required=True, index=True)
    sequence = fields.Integer(string="Urutan", default=10)
    res_model = fields.Selection([
        ("res.partner", "Mitra / Pelanggan (Credit Limit & ToP)"),
        ("sale.order", "Pesanan Penjualan (Diskon Taktikal & Harga < HPP)"),
        ("product.template", "Master Produk (New SKU)"),
        ("loyalty.program", "Promosi & Diskon (New Promo)"),
        ("account.payment", "Keuangan (Biaya Operasional)"),
        ("hr.leave", "SDM (Cuti Karyawan 2-Line)"),
        ("stock.picking", "Gudang & Logistik (Early Inbound & Disposal)"),
        ("fmcg.pjp.visit", "Penjualan Lapangan (Extra Call Salesman)"),
    ], string="Model Sasaran", required=True)
    description = fields.Text(string="Keterangan & Petunjuk")
    has_amount_tiers = fields.Boolean(
        string="Tiering Berdasarkan Nominal",
        help="Jika aktif, tier approver ditentukan berdasarkan batas nominal transaksi.",
    )
    has_discount_tiers = fields.Boolean(
        string="Tiering Berdasarkan Persentase Diskon",
        help="Jika aktif, tier approver ditentukan berdasarkan persentase diskon.",
    )
    rule_ids = fields.One2many(
        "fmcg.approval.rule",
        "category_id",
        string="Aturan & Tingkatan Approver (Tiers)",
    )
    active = fields.Boolean(string="Aktif", default=True)

    @api.constrains("code")
    def _check_code_unique(self):
        for rec in self:
            if rec.code:
                duplicate = self.search([("code", "=", rec.code), ("id", "!=", rec.id)], limit=1)
                if duplicate:
                    raise ValidationError(f"Kode kategori persetujuan '{rec.code}' sudah terdaftar!")
