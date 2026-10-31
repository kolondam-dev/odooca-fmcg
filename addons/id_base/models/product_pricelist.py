from datetime import timedelta
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ProductPricelist(models.Model):
    _name = "product.pricelist"
    _inherit = ["product.pricelist", "mail.thread", "mail.activity.mixin"]

    channel_id = fields.Many2one(
        "id.channel",
        string="Distribution Channel",
        tracking=True,
        index=True,
        help="Target kanal distribusi (Modern Trade, General Trade, Horeka, Wholesale)",
    )
    coverage_category = fields.Selection(
        [
            ("all", "Semua Wilayah (All)"),
            ("urban", "Dalam Kota (Urban)"),
            ("hinterland", "Dataran Tinggi (Hinterland)"),
            ("port", "Pelabuhan & Industri"),
            ("rural", "Luar Kota (Rural)"),
        ],
        string="Area Coverage Type",
        default="all",
        tracking=True,
        help="Kategori wilayah jangkauan operasional logistik distributor",
    )
    coverage_area_id = fields.Many2one(
        "id.coverage.area",
        string="Spesifik Area",
        tracking=True,
        index=True,
        help="Area cakupan spesifik jika harga dibatasi pada wilayah tertentu",
    )
    tier = fields.Selection(
        [
            ("cash", "Tier 1 - Cash / CBD"),
            ("credit_14", "Tier 2 - Kredit 14 Hari"),
            ("credit_30", "Tier 3 - Kredit 30 Hari"),
            ("custom", "Tier Khusus / Kontrak"),
        ],
        string="Payment / Credit Tier",
        default="cash",
        tracking=True,
    )
    date_start = fields.Date(
        string="Mulai Berlaku",
        tracking=True,
        help="Tanggal awal berlakunya daftar harga matriks",
    )
    date_end = fields.Date(
        string="Jatuh Tempo / Selesai",
        tracking=True,
        help="Tanggal batas akhir berlakunya daftar harga matriks",
    )
    alert_days_before = fields.Integer(
        string="Hari Peringatan Jatuh Tempo",
        default=14,
        help="Jumlah hari sebelum jatuh tempo untuk memicu notifikasi pembaruan harga berkala",
    )
    expiry_state = fields.Selection(
        [
            ("draft", "Draft / Belum Berlaku"),
            ("active", "Aktif Berjalan"),
            ("near_expiry", "Mendekati Jatuh Tempo"),
            ("expired", "Kadaluarsa / Perlu Update"),
        ],
        string="Status Masa Berlaku",
        compute="_compute_expiry_state",
        store=True,
        tracking=True,
    )
    is_fmcg_matrix = fields.Boolean(
        string="FMCG Matrix Pricelist",
        default=True,
        help="Menandai bahwa daftar harga ini merupakan bagian dari matriks harga resmi FMCG MDU",
    )
    item_count = fields.Integer(
        string="Jumlah Aturan Harga",
        compute="_compute_item_count",
    )

    @api.depends("item_ids")
    def _compute_item_count(self):
        for record in self:
            record.item_count = len(record.item_ids)

    @api.depends("date_start", "date_end", "alert_days_before")
    def _compute_expiry_state(self):
        today = fields.Date.context_today(self)
        for record in self:
            if not record.date_start and not record.date_end:
                record.expiry_state = "active"
                continue

            if record.date_start and record.date_start > today:
                record.expiry_state = "draft"
            elif record.date_end and record.date_end < today:
                record.expiry_state = "expired"
            elif record.date_end and (record.date_end - today) <= timedelta(days=record.alert_days_before or 14):
                record.expiry_state = "near_expiry"
            else:
                record.expiry_state = "active"

    @api.model
    def _cron_check_pricelist_expiry(self):
        """Cron terjadwal harian: memindai daftar harga yang mendekati jatuh tempo

        dan memicu activity reminder bagi tim Sales Manager untuk update periodik.
        """
        today = fields.Date.context_today(self)
        self.search([])._compute_expiry_state()

        expiring_pricelists = self.search([
            ("active", "=", True),
            ("expiry_state", "in", ["near_expiry", "expired"]),
        ])
        mail_activity = self.env["mail.activity"]
        sales_manager_group = self.env.ref("sales_team.group_sale_manager", raise_if_not_found=False)
        managers = sales_manager_group.users if sales_manager_group else self.env.ref("base.user_admin")

        activity_type_todo = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type_todo:
            return

        for pl in expiring_pricelists:
            existing = mail_activity.search([
                ("res_model", "=", "product.pricelist"),
                ("res_id", "=", pl.id),
                ("activity_type_id", "=", activity_type_todo.id),
            ], limit=1)
            if not existing:
                for mgr in managers[:1]:
                    days_left = (pl.date_end - today).days if pl.date_end else 0
                    summary = (
                        f"Pricelist '{pl.name}' telah kadaluarsa!"
                        if days_left < 0
                        else f"Pricelist '{pl.name}' akan jatuh tempo dalam {days_left} hari ({pl.date_end})"
                    )
                    note = (
                        f"<p>Perhatian: Daftar harga <b>{pl.name}</b> (Channel: {pl.channel_id.name or 'Semua'}, "
                        f"Area: {pl.coverage_category}) memerlukan peninjauan dan update berkala.</p>"
                    )
                    mail_activity.create({
                        "activity_type_id": activity_type_todo.id,
                        "res_model": "product.pricelist",
                        "res_id": pl.id,
                        "user_id": mgr.id,
                        "summary": summary,
                        "note": note,
                        "date_deadline": pl.date_end or today,
                    })
                    _logger.info("Created pricelist expiry activity for pricelist %s (id %s)", pl.name, pl.id)
