from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


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

    def _applicable_tier_rules(self, principal_id, discount_percent, amount=0.0):
        """Tier approver berjenjang yang berlaku untuk diskon (%) dan nominal tertentu."""
        self.ensure_one()
        rules = self._rules_for_principal(principal_id)
        applicable = []
        for r in rules:
            if self.has_amount_tiers and r.min_amount > 0 and amount < r.min_amount:
                continue
            if self.has_discount_tiers and r.min_discount > 0 and discount_percent < r.min_discount:
                continue
            applicable.append(r)
        return applicable or list(rules[:1])

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

    @api.model
    def _mobile_snapshot_payload(self, principal_ids, partner_ids, user, company, anchor):
        """Konfigurasi tier diskon + pemakaian kumulatif untuk snapshot PWA (BE-18).

        Hanya baca dan tanpa rahasia: batas zona bebas, rentang tier, label tingkat approver, dan
        pemakaian diskon pada jendela WITA berjalan. Pemakaian dibaca lewat ACL pengguna sehingga
        dapat lebih rendah dari angka server; server tetap otoritatif saat order dikirim.
        PWA hanya untuk pratinjau, bukan pengambil keputusan.
        """
        category = self.sudo().search([("code", "=", "tactical_discount")], limit=1)
        if not category:
            return None

        def block(principal_id):
            free = category._free_zone_limit(principal_id)
            tiers = [
                {"min_discount": r.min_discount, "approver": r.name}
                for r in category._rules_for_principal(principal_id, free_zone=False)
            ]
            return {"free_zone_max": free, "tiers": tiers}

        principals = {}
        for pid in sorted(set(principal_ids)):
            specific = category.rule_ids.filtered(lambda r, pid=pid: r.principal_id.id == pid)
            if specific:
                principals[str(pid)] = block(pid)
        scope = category.cumulative_scope
        payload = {
            "scope": scope,
            "default": block(False),
            "principals": principals,
            "usage": [],
        }
        if scope in ("salesman_day", "outlet_month"):
            try:
                payload["usage"] = self.env["sale.order"]._approval_usage_entries(
                    scope, user, partner_ids, company, anchor)
            except AccessError:
                payload["usage"] = []  # tanpa hak baca pesanan: pratinjau tanpa pemakaian, server tetap otoritatif
        return payload
