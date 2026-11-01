from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    channel_id = fields.Many2one("id.channel", string="Distribution Channel", index=True)
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

    # Permanent Journey Plan (PJP) & Route Logistics
    pjp_call_day = fields.Selection(
        [
            ("monday", "Monday (Senin)"),
            ("tuesday", "Tuesday (Selasa)"),
            ("wednesday", "Wednesday (Rabu)"),
            ("thursday", "Thursday (Kamis)"),
            ("friday", "Friday (Jumat)"),
            ("saturday", "Saturday (Sabtu)"),
        ],
        string="PJP Call Day",
        index=True,
        help="Jadwal hari kunjungan tetap salesman (Permanent Journey Plan)",
    )
    pjp_frequency = fields.Selection(
        [
            ("F1", "F1 - Weekly (1x / Minggu)"),
            ("F2", "F2 - Bi-weekly (1x / 2 Minggu)"),
            ("F4", "F4 - Monthly (1x / 4 Minggu)"),
        ],
        string="PJP Call Frequency",
        index=True,
        default="F1",
        help="Frekuensi siklus kunjungan salesman ke outlet",
    )
    delivery_route = fields.Char(
        string="Delivery Route",
        index=True,
        help="Kode rute logistik/pengiriman yang melayani outlet ini",
    )

    def _get_matrix_pricelist(self):
        """Menemukan daftar harga matriks FMCG paling sesuai berdasarkan channel dan coverage."""
        self.ensure_one()
        pricelist_model = self.env["product.pricelist"]
        cov_cat = self.coverage_area_id.category if self.coverage_area_id else False

        # 1. Exact match: channel + specific coverage category
        if self.channel_id and cov_cat:
            pl = pricelist_model.search([
                ("is_fmcg_matrix", "=", True),
                ("channel_id", "=", self.channel_id.id),
                ("coverage_category", "=", cov_cat),
                ("active", "=", True),
            ], limit=1)
            if pl:
                return pl

        # 2. Channel match with all coverage
        if self.channel_id:
            pl = pricelist_model.search([
                ("is_fmcg_matrix", "=", True),
                ("channel_id", "=", self.channel_id.id),
                ("coverage_category", "in", ["all", False]),
                ("active", "=", True),
            ], limit=1)
            if pl:
                return pl

        # 3. Coverage match with generic channel
        if cov_cat:
            pl = pricelist_model.search([
                ("is_fmcg_matrix", "=", True),
                ("channel_id", "=", False),
                ("coverage_category", "=", cov_cat),
                ("active", "=", True),
            ], limit=1)
            if pl:
                return pl

        # 4. Default FMCG Base Matrix
        pl = pricelist_model.search([
            ("is_fmcg_matrix", "=", True),
            ("active", "=", True),
        ], order="sequence, id", limit=1)
        return pl

    def action_assign_matrix_pricelist(self):
        """Mengaitkan pricelist matriks otomatis untuk partner outlet."""
        for partner in self:
            best_pl = partner._get_matrix_pricelist()
            if best_pl:
                partner.property_product_pricelist = best_pl.id

    @api.onchange("channel_id", "coverage_area_id")
    def _onchange_channel_coverage_for_pricelist(self):
        for partner in self:
            if partner.channel_id or partner.coverage_area_id:
                best_pl = partner._get_matrix_pricelist()
                if best_pl:
                    partner.property_product_pricelist = best_pl.id
