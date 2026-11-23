from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.addons.id_base.models.business_day import business_date

# Faktur pada SJP berstatus ini dianggap sedang ditagih dan tidak masuk kandidat SJP baru.
# Setelah SJP dikembalikan/ditutup/dibatalkan faktur kembali ke daftar kandidat (unpaid terbuka
# secara default, keputusan pemilik D9).
ACTIVE_STATES = ("draft", "issued")
OPEN_PAYMENT_STATES = ("not_paid", "partial")


class CollectionSheet(models.Model):
    _name = "id.collection.sheet"
    _description = "Surat Jalan Penagihan"
    _inherit = ["mail.thread"]
    _check_company_auto = True
    _order = "collect_date desc, id desc"

    name = fields.Char(
        string="Nomor SJP", readonly=True, copy=False, default=lambda self: _("Baru"), index=True
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    collect_date = fields.Date(
        string="Tanggal Penagihan", required=True, default=lambda self: business_date(), tracking=True
    )
    due_until = fields.Date(
        string="Jatuh Tempo Sampai", required=True, default=lambda self: business_date(), tracking=True
    )
    collector_id = fields.Many2one(
        "res.users", string="Kolektor", tracking=True, index=True, domain="[('share', '=', False)]"
    )
    route = fields.Char(string="Rute", tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draf"),
            ("issued", "Diterbitkan"),
            ("returned", "Dikembalikan"),
            ("reconciled", "Ditutup"),
            ("cancelled", "Dibatalkan"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    generated_by = fields.Many2one(
        "res.users", string="Dibuat Oleh", default=lambda self: self.env.user, readonly=True
    )
    note = fields.Text(string="Catatan")
    line_ids = fields.One2many("id.collection.sheet.line", "sheet_id", string="Faktur")
    currency_id = fields.Many2one(related="company_id.currency_id")
    line_count = fields.Integer(compute="_compute_totals", string="Jumlah Faktur")
    amount_total = fields.Monetary(compute="_compute_totals", string="Total Tagihan")

    @api.depends("line_ids.amount_due")
    def _compute_totals(self):
        for sheet in self:
            sheet.line_count = len(sheet.line_ids)
            sheet.amount_total = sum(sheet.line_ids.mapped("amount_due"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("Baru"):
                vals["name"] = self.env["ir.sequence"].next_by_code("id.collection.sheet") or _("Baru")
        return super().create(vals_list)

    # ---- transisi (BE-20b: terbit dan batal; kembali/tutup menyusul bersama penerimaan, BE-20e) ----
    def action_issue(self):
        for sheet in self:
            if sheet.state != "draft":
                raise UserError(_("Hanya SJP draf yang dapat diterbitkan."))
            if not sheet.line_ids:
                raise UserError(_("SJP tanpa faktur tidak dapat diterbitkan."))
            if not sheet.collector_id:
                raise UserError(_("Pilih kolektor sebelum menerbitkan SJP."))
        self.write({"state": "issued"})

    def action_cancel(self):
        for sheet in self:
            if sheet.state not in ACTIVE_STATES:
                raise UserError(_("Hanya SJP draf atau diterbitkan yang dapat dibatalkan."))
        self.write({"state": "cancelled"})

    def action_draft(self):
        for sheet in self:
            if sheet.state != "cancelled":
                raise UserError(_("Hanya SJP dibatalkan yang dapat dikembalikan ke draf."))
        self.write({"state": "draft"})

    def unlink(self):
        if any(sheet.state != "draft" for sheet in self):
            raise UserError(_("Hanya SJP draf yang dapat dihapus; batalkan SJP lainnya."))
        return super().unlink()


class CollectionSheetLine(models.Model):
    _name = "id.collection.sheet.line"
    _description = "Baris Surat Jalan Penagihan"
    _check_company_auto = True
    _order = "sheet_id, due_date, id"

    sheet_id = fields.Many2one(
        "id.collection.sheet", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="sheet_id.company_id", store=True, index=True)
    sheet_state = fields.Selection(related="sheet_id.state", store=True, index=True)
    move_id = fields.Many2one(
        "account.move",
        string="Faktur",
        required=True,
        ondelete="restrict",
        index=True,
        check_company=True,
        domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]",
    )
    partner_id = fields.Many2one(related="move_id.partner_id", store=True)
    commercial_partner_id = fields.Many2one(related="move_id.commercial_partner_id", store=True)
    due_date = fields.Date(related="move_id.invoice_date_due", store=True)
    currency_id = fields.Many2one(related="move_id.currency_id")
    amount_due = fields.Monetary(string="Sisa Tagihan (snapshot)", required=True)
    outcome = fields.Selection(
        [
            ("pending", "Belum Ditagih"),
            ("paid", "Lunas"),
            ("partial", "Dibayar Sebagian"),
            ("unpaid", "Tidak Tertagih"),
        ],
        default="pending",
        required=True,
    )
    collected_amount = fields.Monetary(string="Diterima")
    unpaid_reason = fields.Char(string="Alasan Tidak Tertagih")
    document_return = fields.Selection(
        [("none", "Tidak Ada"), ("copy", "Copy Faktur"), ("original", "Faktur Asli")],
        default="none",
        required=True,
        string="Dokumen Dikembalikan",
    )

    @api.constrains("move_id", "sheet_id")
    def _check_one_active_sheet(self):
        for line in self:
            if line.sheet_id.state not in ACTIVE_STATES:
                continue
            clash = self.search_count([
                ("move_id", "=", line.move_id.id),
                ("id", "!=", line.id),
                ("sheet_id.state", "in", ACTIVE_STATES),
            ])
            if clash:
                raise ValidationError(
                    _("Faktur %s sudah ada pada SJP aktif lain.", line.move_id.name)
                )

    @api.constrains("move_id")
    def _check_invoice(self):
        for line in self:
            move = line.move_id
            if move.move_type != "out_invoice" or move.state != "posted":
                raise ValidationError(_("SJP hanya memuat faktur pelanggan yang sudah diposting."))
