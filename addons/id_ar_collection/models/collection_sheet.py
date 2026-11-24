from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.addons.id_base.models.business_day import business_date

# Faktur pada SJP berstatus ini dianggap sedang ditagih dan tidak masuk kandidat SJP baru.
# Setelah SJP dikembalikan/ditutup/dibatalkan faktur kembali ke daftar kandidat (unpaid terbuka
# secara default, keputusan pemilik D9).
ACTIVE_STATES = ("draft", "issued")
OPEN_PAYMENT_STATES = ("not_paid", "partial")

# Mesin status server-side. `returned`/`reconciled` BELUM punya aksi publik (BE-20e); transisinya hanya
# tersedia lewat metode privat `_apply_state` (tidak terjangkau RPC, bukan context) untuk fixture tes
# dan pekerjaan berikutnya.
TRANSITIONS = {
    "draft": {"issued", "cancelled"},
    "issued": {"cancelled", "returned"},
    "returned": {"reconciled"},
    "reconciled": set(),
    "cancelled": {"draft"},
}
# Setelah diterbitkan, surat tugas yang sudah dicetak tidak boleh diam-diam berubah.
FROZEN_AFTER_DRAFT = {"company_id", "collect_date", "due_until", "collector_id", "route", "line_ids"}
SERVER_OWNED = {"name", "generated_by", "state"}
OUTCOME_FIELDS = ("outcome", "collected_amount", "unpaid_reason", "document_return")


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
        readonly=True,
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
        # Aman dijumlah: baris hanya boleh berisi faktur bermata uang perusahaan (lihat constraint baris).
        for sheet in self:
            sheet.line_count = len(sheet.line_ids)
            sheet.amount_total = sum(sheet.line_ids.mapped("amount_due"))

    # ---- guard server (semua entrypoint ORM/RPC) -----------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state", "draft") != "draft":
                raise UserError(_("SJP baru selalu berstatus draf; status berubah lewat aksi."))
            vals.pop("state", None)
            vals["name"] = self.env["ir.sequence"].next_by_code("id.collection.sheet") or _("Baru")
            vals["generated_by"] = self.env.user.id
        return super().create(vals_list)

    def write(self, vals):
        if SERVER_OWNED & vals.keys():
            raise UserError(_("Nomor, pembuat, dan status SJP hanya diubah oleh sistem lewat aksi."))
        if FROZEN_AFTER_DRAFT & vals.keys() and any(s.state != "draft" for s in self):
            raise UserError(_("SJP yang sudah diterbitkan tidak dapat diubah; batalkan lalu buat ulang."))
        return super().write(vals)

    def unlink(self):
        if any(sheet.state != "draft" for sheet in self):
            raise UserError(_("Hanya SJP draf yang dapat dihapus; batalkan SJP lainnya."))
        return super().unlink()

    def _apply_state(self, new_state):
        """Satu-satunya jalan mengubah status: validasi transisi, klaim faktur aktif, lalu tulis."""
        for sheet in self:
            if new_state not in TRANSITIONS.get(sheet.state, ()):
                raise UserError(
                    _("Transisi status SJP %(name)s dari %(old)s ke %(new)s tidak diizinkan.",
                      name=sheet.name, old=sheet.state, new=new_state)
                )
        if new_state in ACTIVE_STATES:
            self._check_no_active_clash()
        super().write({"state": new_state})
        # Paksa penulisan klaim aktif sekarang: indeks unik parsial DB menolak bentrok (juga antar sesi).
        self.env["id.collection.sheet.line"].flush_model(["active_claim"])

    def _check_no_active_clash(self):
        for sheet in self:
            moves = sheet.line_ids.move_id
            if not moves:
                continue
            clash = self.env["id.collection.sheet.line"].search([
                ("move_id", "in", moves.ids),
                ("sheet_id", "!=", sheet.id),
                ("active_claim", "=", True),
            ], limit=1)
            if clash:
                raise UserError(
                    _("Faktur %(move)s sudah ada pada SJP aktif %(other)s.",
                      move=clash.move_id.name, other=clash.sheet_id.name)
                )

    # ---- aksi publik (BE-20b: terbit, batal, kembali ke draf) ----------------------------------
    def action_issue(self):
        for sheet in self:
            if sheet.state != "draft":
                raise UserError(_("Hanya SJP draf yang dapat diterbitkan."))
            if not sheet.line_ids:
                raise UserError(_("SJP tanpa faktur tidak dapat diterbitkan."))
            collector = sheet.collector_id
            if not collector:
                raise UserError(_("Pilih kolektor sebelum menerbitkan SJP."))
            if not collector.active or collector.share:
                raise UserError(_("Kolektor harus pengguna internal yang aktif."))
            if sheet.company_id not in collector.company_ids:
                raise UserError(_("Kolektor tidak termasuk perusahaan SJP ini."))
            for line in sheet.line_ids:
                line._check_invoice_eligible()
        self._apply_state("issued")

    def action_cancel(self):
        for sheet in self:
            if sheet.state not in ACTIVE_STATES:
                raise UserError(_("Hanya SJP draf atau diterbitkan yang dapat dibatalkan."))
        self._apply_state("cancelled")

    def action_draft(self):
        for sheet in self:
            if sheet.state != "cancelled":
                raise UserError(_("Hanya SJP dibatalkan yang dapat dikembalikan ke draf."))
        self._apply_state("draft")


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
    # Klaim aktif tersimpan: dasar indeks unik parsial (satu faktur, satu SJP aktif) yang atomik di DB.
    active_claim = fields.Boolean(
        compute="_compute_active_claim", store=True, precompute=True, default=False
    )
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
    amount_due = fields.Monetary(string="Sisa Tagihan (snapshot)", readonly=True)
    outcome = fields.Selection(
        [
            ("pending", "Belum Ditagih"),
            ("paid", "Lunas"),
            ("partial", "Dibayar Sebagian"),
            ("unpaid", "Tidak Tertagih"),
        ],
        default="pending",
        required=True,
        readonly=True,
    )
    collected_amount = fields.Monetary(string="Diterima", readonly=True)
    unpaid_reason = fields.Char(string="Alasan Tidak Tertagih", readonly=True)
    document_return = fields.Selection(
        [("none", "Tidak Ada"), ("copy", "Copy Faktur"), ("original", "Faktur Asli")],
        default="none",
        required=True,
        string="Dokumen Dikembalikan",
        readonly=True,
    )

    def init(self):
        super().init()
        # Guard atomik: paling banyak satu klaim aktif per faktur, juga antar dua transaksi paralel.
        self.env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS id_collection_sheet_line_one_active_claim "
            "ON id_collection_sheet_line (move_id) WHERE active_claim"
        )

    @api.depends("sheet_id.state")
    def _compute_active_claim(self):
        for line in self:
            line.active_claim = line.sheet_id.state in ACTIVE_STATES

    @api.model
    def _validate_invoice(self, move, company):
        if move.move_type != "out_invoice" or move.state != "posted":
            raise ValidationError(_("SJP hanya memuat faktur pelanggan yang sudah diposting."))
        if move.company_id != company:
            raise ValidationError(_("Faktur %s bukan milik perusahaan SJP.", move.name))
        if move.currency_id != company.currency_id:
            raise ValidationError(_(
                "Faktur %(move)s bermata uang %(cur)s; SJP hanya mendukung mata uang perusahaan (%(base)s).",
                move=move.name, cur=move.currency_id.name, base=company.currency_id.name))
        if move.payment_state not in OPEN_PAYMENT_STATES or move.amount_residual <= 0:
            raise ValidationError(_("Faktur %s sudah tidak memiliki sisa tagihan.", move.name))

    def _check_invoice_eligible(self):
        for line in self:
            self._validate_invoice(line.move_id, line.sheet_id.company_id)

    # ---- guard server ---------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        sheets = self.env["id.collection.sheet"]
        for vals in vals_list:
            sheet = sheets.browse(vals.get("sheet_id"))
            if sheet.state != "draft":
                raise UserError(_("Faktur hanya dapat ditambahkan pada SJP berstatus draf."))
            for field in OUTCOME_FIELDS:
                vals.pop(field, None)  # hasil penagihan hanya lewat alur penerimaan (BE-20d/e)
            move = self.env["account.move"].browse(vals.get("move_id"))
            self._validate_invoice(move, sheet.company_id)
            clash = self.search([("move_id", "=", move.id), ("active_claim", "=", True)], limit=1)
            if clash:  # pesan bisnis; bentrok antar transaksi tetap ditolak oleh indeks unik DB
                raise ValidationError(
                    _("Faktur %(move)s sudah ada pada SJP aktif %(other)s.",
                      move=move.name, other=clash.sheet_id.name)
                )
            vals["amount_due"] = move.amount_residual  # snapshot dimiliki server
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(
            _("Baris SJP tidak dapat diubah langsung; hapus baris dan tambah ulang selagi SJP draf.")
        )

    def unlink(self):
        # Tanpa jalur khusus berbasis context: context request bukan batas kepercayaan.
        if any(line.sheet_id.state != "draft" for line in self):
            raise UserError(_("Faktur hanya dapat dihapus dari SJP berstatus draf."))
        return super().unlink()

    def _apply_outcome(self, vals):
        """Seam internal untuk hasil penagihan (BE-20d/e dan fixture tes); tidak terjangkau RPC."""
        allowed = {key: vals[key] for key in OUTCOME_FIELDS if key in vals}
        return super().write(allowed)

    @api.constrains("move_id", "sheet_id")
    def _check_one_active_sheet(self):
        for line in self:
            if not line.active_claim:
                continue
            clash = self.search([
                ("move_id", "=", line.move_id.id),
                ("id", "!=", line.id),
                ("active_claim", "=", True),
            ], limit=1)
            if clash:
                raise ValidationError(
                    _("Faktur %(move)s sudah ada pada SJP aktif %(other)s.",
                      move=line.move_id.name, other=clash.sheet_id.name)
                )
