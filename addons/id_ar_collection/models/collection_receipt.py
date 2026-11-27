"""BE-20d: penerimaan penagihan (custody uang/instrumen) dan baris alokasinya ke faktur.

Rancangan: docs/ui/BE20_SJP_DESIGN.md bagian 8. Model ini hanya MENCATAT penerimaan berstatus `posted`; tidak ada
`account.payment`, rekonsiliasi, atau perubahan `amount_residual` faktur (itu BE-20e).
"""
from datetime import datetime, time, timedelta, timezone

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.id_base.models.business_day import BUSINESS_TZ

# Status yang masih "pending": uang diterima tetapi belum selesai divalidasi. Dilepas hanya oleh
# `accounting_validated` (saldo sudah turun lewat pembayaran native) atau `rejected`/`cancelled`.
PENDING_STATES = ("posted", "cashier_validated", "finance_verified", "instrument_registered")
RELEASED_STATES = ("rejected", "cancelled")
METHODS = [("cash", "Tunai"), ("transfer", "Transfer"), ("giro", "Giro")]
RECEIPT_STATES = [
    ("posted", "Diposting"),
    ("cashier_validated", "Divalidasi Kasir"),
    ("finance_verified", "Diverifikasi Finance"),
    ("instrument_registered", "Giro Terdaftar"),
    ("accounting_validated", "Divalidasi Accounting"),
    ("rejected", "Ditolak"),
    ("cancelled", "Dibatalkan"),
]

# Nama indeks unik DB yang dipetakan menjadi penolakan bisnis oleh dispatcher (bukan "retry UUID").
ONE_PER_SHEET_LINE = "id_collection_receipt_line_one_per_sheet_line"
ONE_PENDING_PER_MOVE = "id_collection_receipt_line_one_pending_per_move"
COMMAND_METHOD_INDEX = "id_collection_receipt_command_method"
RECEIPT_CONSTRAINTS = {ONE_PER_SHEET_LINE, ONE_PENDING_PER_MOVE, COMMAND_METHOD_INDEX}


def settlement_cutoff(collect_date):
    """Awal hari berikutnya (00:00 WITA) setelah `collect_date`, sebagai datetime UTC naif (format ORM)."""
    start = datetime.combine(collect_date + timedelta(days=1), time.min, tzinfo=BUSINESS_TZ)
    return start.astimezone(timezone.utc).replace(tzinfo=None)


class CollectionReceipt(models.Model):
    _name = "id.collection.receipt"
    _description = "Penerimaan Penagihan"
    _check_company_auto = True
    _order = "id desc"

    name = fields.Char(string="Nomor", readonly=True, copy=False, index=True)
    sheet_id = fields.Many2one(
        "id.collection.sheet", required=True, ondelete="restrict", index=True, readonly=True
    )
    company_id = fields.Many2one("res.company", required=True, index=True, readonly=True)
    collector_id = fields.Many2one("res.users", string="Kolektor", required=True, index=True, readonly=True)
    command_uuid = fields.Char(string="UUID Command", index=True, readonly=True)
    source = fields.Selection(
        [("mobile", "PWA/Mobile"), ("cashier_desk", "Meja Kasir")],
        default="mobile", required=True, readonly=True,
    )
    exception = fields.Boolean(string="Pengecualian", readonly=True)
    method = fields.Selection(METHODS, required=True, readonly=True)
    state = fields.Selection(RECEIPT_STATES, default="posted", required=True, readonly=True, index=True)
    occurred_at = fields.Datetime(string="Waktu Kejadian", readonly=True)
    submitted_at = fields.Datetime(string="Waktu Diterima Server", readonly=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    amount_total = fields.Monetary(compute="_compute_amount_total", store=True)
    line_ids = fields.One2many("id.collection.receipt.line", "receipt_id", string="Baris")

    def init(self):
        super().init()
        # Satu receipt per (kolektor, UUID command, metode): retry/ganda tidak dapat menggandakan custody.
        self.env.cr.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {COMMAND_METHOD_INDEX} "
            "ON id_collection_receipt (collector_id, command_uuid, method) WHERE command_uuid IS NOT NULL"
        )

    @api.depends("line_ids.amount")
    def _compute_amount_total(self):
        for receipt in self:
            receipt.amount_total = sum(receipt.line_ids.mapped("amount"))

    # ---- guard server: tidak ada jalur tulis/hapus langsung ----------------------------------------
    def write(self, vals):
        raise UserError(_("Penerimaan tidak dapat diubah langsung; status hanya berubah lewat alur validasi."))

    def unlink(self):
        raise UserError(_("Penerimaan tidak dapat dihapus."))


class CollectionReceiptLine(models.Model):
    _name = "id.collection.receipt.line"
    _description = "Baris Penerimaan Penagihan"
    _check_company_auto = True
    _order = "receipt_id, id"

    receipt_id = fields.Many2one("id.collection.receipt", required=True, ondelete="restrict", index=True)
    company_id = fields.Many2one(related="receipt_id.company_id", store=True, index=True)
    receipt_state = fields.Selection(related="receipt_id.state", store=True, index=True)
    method = fields.Selection(related="receipt_id.method", store=True)
    sheet_line_id = fields.Many2one(
        "id.collection.sheet.line", required=True, ondelete="restrict", index=True
    )
    move_id = fields.Many2one("account.move", string="Faktur", required=True, ondelete="restrict", index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    outcome = fields.Selection(
        [("paid", "Lunas"), ("partial", "Dibayar Sebagian"), ("unpaid", "Tidak Tertagih")], required=True
    )
    amount = fields.Monetary(string="Diterima")
    balance_at_submit = fields.Monetary(string="Saldo Saat Diterima")
    allocation_state = fields.Selection(
        [("allocated", "Teralokasi"), ("held", "Ditahan"), ("released", "Dilepas")],
        default="allocated", required=True,
    )
    unpaid_reason = fields.Char()
    document_return = fields.Selection(
        [("none", "Tidak Ada"), ("copy", "Copy Faktur"), ("original", "Faktur Asli")], default="none", required=True
    )
    transfer_reference = fields.Char()
    proof_evidence_ref = fields.Char()
    giro_number = fields.Char()
    giro_bank = fields.Char()
    giro_due_date = fields.Date()
    note = fields.Char()
    # Dasar dua indeks unik parsial (atomik antar transaksi). `holds_line`: satu penerimaan aktif per baris SJP
    # (termasuk unpaid). `holds_invoice`: satu penerimaan pending berisi uang per faktur lintas SJP.
    holds_line = fields.Boolean(compute="_compute_holds", store=True, precompute=True)
    holds_invoice = fields.Boolean(compute="_compute_holds", store=True, precompute=True)

    def init(self):
        super().init()
        self.env.cr.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {ONE_PER_SHEET_LINE} "
            "ON id_collection_receipt_line (sheet_line_id) WHERE holds_line"
        )
        self.env.cr.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {ONE_PENDING_PER_MOVE} "
            "ON id_collection_receipt_line (move_id) WHERE holds_invoice"
        )

    @api.depends("receipt_id.state", "allocation_state", "amount")
    def _compute_holds(self):
        for line in self:
            state = line.receipt_id.state
            line.holds_line = state not in RELEASED_STATES
            line.holds_invoice = (
                state in PENDING_STATES and line.allocation_state == "allocated" and (line.amount or 0) > 0
            )

    def write(self, vals):
        raise UserError(_("Baris penerimaan tidak dapat diubah langsung."))

    def unlink(self):
        raise UserError(_("Baris penerimaan tidak dapat dihapus."))
