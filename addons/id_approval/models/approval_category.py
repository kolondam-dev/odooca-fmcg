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
    cumulative_scope = fields.Selection([
        ("order", "Per pesanan"),
        ("outlet_month", "Akumulasi per outlet per bulan"),
        ("salesman_day", "Akumulasi per salesman per hari"),
    ], string="Cakupan Diskon Kumulatif", default="order", required=True,
        help="Diskon kumulatif (%) dihitung berbobot nilai pada cakupan ini, per principal, "
             "termasuk diskon program resmi.")

    def _rules_for_principal(self, principal_id=False, free_zone=False):
        """Aturan kategori untuk zona bebas (free_zone=True) atau tier approver (False).

        Aturan khusus principal menimpa aturan umum, dihitung terpisah untuk zona bebas dan
        tier approver: principal yang hanya punya zona bebas sendiri tetap memakai tier umum.
        """
        self.ensure_one()
        rules = self.rule_ids.filtered(lambda r: bool(r.is_free_zone) == bool(free_zone))
        rules = rules.sorted(key=lambda r: (r.tier_sequence, r.id))
        if principal_id:
            specific = rules.filtered(lambda r: r.principal_id.id == principal_id)
            if specific:
                return specific
        return rules.filtered(lambda r: not r.principal_id)

    def _free_zone_limit(self, principal_id=False):
        """Batas diskon (%) zona bebas (Tier 0), atau None bila tidak ada aturan zona bebas."""
        self.ensure_one()
        zone = self._rules_for_principal(principal_id, free_zone=True)
        return max(zone.mapped("max_discount")) if zone else None
    active = fields.Boolean(string="Aktif", default=True)

    @api.constrains("code")
    def _check_code_unique(self):
        for rec in self:
            if rec.code:
                duplicate = self.search([("code", "=", rec.code), ("id", "!=", rec.id)], limit=1)
                if duplicate:
                    raise ValidationError(f"Kode kategori persetujuan '{rec.code}' sudah terdaftar!")
