"""BE-20d: handler `collection.receipt.submit` (rancangan bagian 8.1-8.4).

Tiga kelas hasil: (1) malformed/otorisasi = UserError/AccessError (tidak dicatat); (2) business rejection terotorisasi
= CommandRejected (rollback penuh, dicatat satu kali); (3) diterima. Semua berjalan di dalam savepoint dispatcher.
"""
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.id_base.models.business_day import BUSINESS_TZ
from odoo.addons.id_mobile_api.models.mobile_command import CommandRejected

from .collection_receipt import (
    ONE_PENDING_PER_MOVE, ONE_PER_SHEET_LINE, RECEIPT_CONSTRAINTS, settlement_cutoff,
)

RECEIPT_COMMAND = "collection.receipt.submit"
MAX_LINES = 200
FUTURE_TOLERANCE = timedelta(minutes=5)
OUTCOMES = ("paid", "partial", "unpaid")
METHOD_ORDER = ("cash", "transfer", "giro")
UNPAID_REASONS = ("closed", "no_cash", "dispute", "absent", "other")
DOCUMENT_RETURN = {"paid": "copy", "partial": "copy", "unpaid": "original"}


class MobileCommand(models.Model):
    _inherit = "id.mobile.command"

    @api.model
    def _supported_commands(self):
        return set(super()._supported_commands()) | {RECEIPT_COMMAND}

    def _handle_extension(self, cmd_type, payload, client_uuid):
        if cmd_type == RECEIPT_COMMAND:
            return self.env["id.collection.receipt"]._submit_from_command(payload, client_uuid)
        return super()._handle_extension(cmd_type, payload, client_uuid)

    def _map_integrity_error(self, error, cmd_type):
        if cmd_type == RECEIPT_COMMAND:
            name = getattr(getattr(error, "diag", None), "constraint_name", None)
            if name in RECEIPT_CONSTRAINTS:
                reference = {ONE_PER_SHEET_LINE: "line", ONE_PENDING_PER_MOVE: "invoice"}.get(name, "command")
                return CommandRejected(
                    _("Sudah ada penerimaan aktif untuk baris/faktur ini; sinkronkan ulang."), reference
                )
        return super()._map_integrity_error(error, cmd_type)


class CollectionReceiptSubmit(models.Model):
    _inherit = "id.collection.receipt"

    # ---- parsing (malformed = UserError, tidak dicatat) ---------------------------------------------
    @api.model
    def _int(self, value, label):
        valid = isinstance(value, int) and not isinstance(value, bool)
        valid = valid or (isinstance(value, str) and value.isdigit())
        if not valid:
            raise UserError(_("Payload tidak valid: %s harus bilangan bulat.", label))
        return int(value)

    @api.model
    def _money(self, value, label, currency):
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise UserError(_("Payload tidak valid: %s harus angka.", label))
        try:
            number = Decimal(str(value))
        except InvalidOperation:
            raise UserError(_("Payload tidak valid: %s harus angka.", label)) from None
        if not number.is_finite():
            raise UserError(_("Payload tidak valid: %s harus angka terhingga.", label))
        amount = float(number)
        if math.isnan(amount) or math.isinf(amount) or currency.compare_amounts(amount, currency.round(amount)):
            raise UserError(_("Payload tidak valid: %s melanggar presisi mata uang.", label))
        return currency.round(amount)

    @api.model
    def _text(self, value, label, limit=255, required=False):
        if value is None or value == "":
            if required:
                raise UserError(_("Payload tidak valid: %s wajib diisi.", label))
            return ""
        if not isinstance(value, str) or len(value) > limit:
            raise UserError(_("Payload tidak valid: %s harus teks (maks %s karakter).", label, limit))
        return value.strip()

    @api.model
    def _parse_occurred_at(self, raw):
        try:
            when = datetime.fromisoformat(raw) if isinstance(raw, str) else None
        except ValueError:
            when = None
        if when is None or when.tzinfo is None:
            raise UserError(_("Payload tidak valid: occurred_at wajib ISO 8601 dengan zona waktu."))
        return when.astimezone(timezone.utc).replace(tzinfo=None)

    @api.model
    def _parse_lines(self, raw_lines, currency):
        if not isinstance(raw_lines, list) or not raw_lines or len(raw_lines) > MAX_LINES:
            raise UserError(_("Payload tidak valid: lines wajib berisi 1-%s baris.", MAX_LINES))
        parsed, seen = [], set()
        for raw in raw_lines:
            if not isinstance(raw, dict):
                raise UserError(_("Payload tidak valid: setiap baris harus objek."))
            line_id = self._int(raw.get("line_id"), "line_id")
            if line_id in seen:
                raise UserError(_("Payload tidak valid: line_id %s muncul lebih dari sekali.", line_id))
            seen.add(line_id)
            outcome = raw.get("outcome")
            if outcome not in OUTCOMES:
                raise UserError(_("Payload tidak valid: outcome harus paid, partial, atau unpaid."))
            method = raw.get("method", "cash")
            if method not in METHOD_ORDER:
                raise UserError(_("Payload tidak valid: method harus cash, transfer, atau giro."))
            entry = {
                "line_id": line_id,
                "invoice_id": self._int(raw.get("invoice_id"), "invoice_id"),
                "outcome": outcome,
                "method": method,
                "amount": self._money(raw.get("amount"), "amount", currency),
                "expected_balance": self._money(raw.get("expected_balance"), "expected_balance", currency),
                "note": self._text(raw.get("note"), "note"),
                "unpaid_reason": "",
                "transfer_reference": "",
                "proof_evidence_ref": "",
                "giro_number": "",
                "giro_bank": "",
                "giro_due_date": False,
            }
            if outcome == "unpaid":
                if method != "cash":
                    raise UserError(_("Payload tidak valid: baris unpaid tidak memakai metode transfer/giro."))
                reason = raw.get("unpaid_reason")
                if reason not in UNPAID_REASONS:
                    raise UserError(_("Payload tidak valid: unpaid_reason wajib dan harus dikenal."))
                entry["unpaid_reason"] = reason
            elif method == "transfer":
                data = raw.get("transfer") if isinstance(raw.get("transfer"), dict) else {}
                entry["transfer_reference"] = self._text(data.get("reference"), "transfer.reference", 64)
                entry["proof_evidence_ref"] = self._text(
                    data.get("proof_evidence_uuid"), "transfer.proof_evidence_uuid", 64
                )
                if not (entry["transfer_reference"] or entry["proof_evidence_ref"]):
                    raise UserError(_("Payload tidak valid: transfer wajib memuat referensi atau bukti."))
            elif method == "giro":
                data = raw.get("giro") if isinstance(raw.get("giro"), dict) else {}
                entry["giro_number"] = self._text(data.get("number"), "giro.number", 64, required=True)
                entry["giro_bank"] = self._text(data.get("bank"), "giro.bank", 64, required=True)
                try:
                    entry["giro_due_date"] = fields.Date.from_string(data.get("due_date"))
                except (ValueError, TypeError):
                    entry["giro_due_date"] = False
                if not entry["giro_due_date"]:
                    raise UserError(_("Payload tidak valid: giro.due_date wajib (YYYY-MM-DD)."))
            parsed.append(entry)
        return parsed

    # ---- penguncian (rancangan 8.4) ------------------------------------------------------------------
    def _lock_rows(self, table, where_sql, params, mode):
        """Kunci baris dengan urutan id naik (deterministik); menunggu bila dipegang transaksi lain.

        Tabel/mode adalah konstanta internal, bukan input pengguna. `FOR UPDATE` pada baris receivable wajib:
        rekonsiliasi native menyisipkan `account.partial.reconcile` yang mengambil key-share lock pada baris yang
        direferensi, dan hanya `FOR UPDATE` yang berbenturan dengannya.
        """
        self.env.cr.execute(f'SELECT id FROM "{table}" WHERE {where_sql} ORDER BY id {mode}', params)  # noqa: S608
        return [row[0] for row in self.env.cr.fetchall()]

    # ---- handler ---------------------------------------------------------------------------------------
    @api.model
    def _submit_from_command(self, payload, client_uuid):
        user = self.env.user
        company = user.company_id
        currency = company.currency_id
        sheet_id = self._int(payload.get("sheet_id"), "sheet_id")
        occurred_at = self._parse_occurred_at(payload.get("occurred_at"))
        entries = self._parse_lines(payload.get("lines"), currency)

        # Akses lintas pemilik/perusahaan: satu pesan generik, tidak dicatat, tidak mengungkap dokumen.
        sheet = self.env["id.collection.sheet"].search([("id", "=", sheet_id)], limit=1)
        if not sheet or sheet.collector_id != user or sheet.company_id != company:
            raise AccessError(_("SJP tidak ditemukan."))

        # 1. kunci SJP lebih dulu (lifecycle), lalu baca ulang statusnya dari DB.
        self._lock_rows("id_collection_sheet", "id = %s", (sheet.id,), "FOR UPDATE")
        self.env.invalidate_all()
        sheet = self.env["id.collection.sheet"].browse(sheet.id)
        SheetLine = self.env["id.collection.sheet.line"].sudo()
        lines = SheetLine.search([("id", "in", [e["line_id"] for e in entries])])
        by_line = {line.id: line for line in lines}
        for entry in entries:
            line = by_line.get(entry["line_id"])
            if not line or line.sheet_id.id != sheet.id or line.move_id.id != entry["invoice_id"]:
                raise UserError(_("Payload tidak valid: baris atau faktur tidak cocok dengan SJP."))
        move_ids = sorted({entry["invoice_id"] for entry in entries})

        # 2. kunci faktur (NO KEY UPDATE) lalu baris receivable (UPDATE), 3. baris SJP; semuanya urut id naik.
        self._lock_rows("account_move", "id IN %s", (tuple(move_ids),), "FOR NO KEY UPDATE")
        self._lock_rows(
            "account_move_line", "move_id IN %s AND display_type = 'payment_term'", (tuple(move_ids),), "FOR UPDATE"
        )
        self._lock_rows("id_collection_sheet_line", "id IN %s", (tuple(sorted(by_line)),), "FOR UPDATE")
        self.env.flush_all()
        self.env.invalidate_all()

        # Saldo dibaca ulang dari DB di dalam bagian terkunci yang sama.
        self.env.cr.execute(
            "SELECT move_id, COALESCE(SUM(amount_residual), 0) FROM account_move_line "
            "WHERE move_id IN %s AND display_type = 'payment_term' GROUP BY move_id",
            (tuple(move_ids),),
        )
        balance = {move_id: currency.round(float(amount)) for move_id, amount in self.env.cr.fetchall()}

        # ---- penolakan bisnis terotorisasi (dicatat; nol efek karena savepoint di-rollback) ----------
        sheet = self.env["id.collection.sheet"].browse(sheet.id)
        if sheet.state != "issued":
            raise CommandRejected(_("SJP %s tidak lagi berstatus diterbitkan.", sheet.name), "sheet_state")
        now = fields.Datetime.now()
        if now >= settlement_cutoff(sheet.collect_date):
            raise CommandRejected(_("SJP %s melewati hari penyelesaian.", sheet.name), "cutoff")
        occurred_wita = occurred_at.replace(tzinfo=timezone.utc).astimezone(BUSINESS_TZ).date()
        if occurred_wita != sheet.collect_date or occurred_at > now + FUTURE_TOLERANCE:
            raise CommandRejected(_("Waktu kejadian tidak sah untuk SJP %s.", sheet.name), "occurred_at")

        Line = self.env["id.collection.receipt.line"].sudo()
        by_line = {line.id: line for line in SheetLine.browse(list(by_line))}
        held_lines = Line.search([("sheet_line_id", "in", list(by_line)), ("holds_line", "=", True)])
        if held_lines:
            raise CommandRejected(
                _("Sudah ada penerimaan %s untuk baris ini.", held_lines[0].receipt_id.name), "line"
            )
        pending_moves = Line.search([("move_id", "in", move_ids), ("holds_invoice", "=", True)])
        if pending_moves:
            raise CommandRejected(
                _("Faktur sudah memiliki penerimaan pending %s.", pending_moves[0].receipt_id.name), "invoice"
            )
        for entry in entries:
            line = by_line[entry["line_id"]]
            move = line.move_id
            if line.outcome != "pending":
                raise CommandRejected(_("Baris %s sudah dilaporkan.", move.name), "line")
            current = balance.get(move.id, 0.0)
            if move.state != "posted" or current <= 0:
                raise CommandRejected(_("Faktur %s tidak lagi memiliki sisa tagihan.", move.name), "balance")
            if currency.compare_amounts(entry["expected_balance"], current):
                raise CommandRejected(_("Saldo faktur %s berubah; sinkronkan ulang.", move.name), "balance")
            entry["balance"] = current
            if entry["outcome"] == "paid" and currency.compare_amounts(entry["amount"], current):
                raise UserError(_("Payload tidak valid: paid harus sama dengan saldo faktur %s.", move.name))
            if entry["outcome"] == "partial" and not (0 < entry["amount"] < current):
                raise UserError(_("Payload tidak valid: partial harus lebih dari nol dan kurang dari saldo."))
            if entry["outcome"] == "unpaid" and entry["amount"]:
                raise UserError(_("Payload tidak valid: unpaid harus bernilai nol."))

        # Sentuh baris header SJP (UPDATE nyata): transaksi lifecycle yang menunggu lock baris ini dengan snapshot lama
        # (REPEATABLE READ) harus gagal SerializationFailure lalu diulang Odoo dan MELIHAT receipt ini, bukan lanjut
        # menulis di atas snapshot basi. Lihat `_apply_state` di collection_sheet.py.
        self.env.cr.execute("UPDATE id_collection_sheet SET write_date = (NOW() AT TIME ZONE 'UTC') WHERE id = %s",
                            (sheet.id,))

        # ---- tulis: satu receipt per metode (cash, transfer, giro), seluruhnya atomik -----------------
        Receipt = self.sudo().with_company(company)
        names = []
        for method in METHOD_ORDER:
            group = [e for e in entries if e["method"] == method]
            if not group:
                continue
            receipt = Receipt.create({
                "name": self.env["ir.sequence"].sudo().next_by_code("id.collection.receipt") or _("Baru"),
                "sheet_id": sheet.id,
                "company_id": company.id,
                "collector_id": user.id,
                "command_uuid": client_uuid,
                "source": "mobile",
                "method": method,
                "occurred_at": occurred_at,
                "submitted_at": now,
                "line_ids": [(0, 0, {
                    "sheet_line_id": e["line_id"],
                    "move_id": e["invoice_id"],
                    "outcome": e["outcome"],
                    "amount": e["amount"],
                    "balance_at_submit": e["balance"],
                    "unpaid_reason": e["unpaid_reason"],
                    "document_return": DOCUMENT_RETURN[e["outcome"]],
                    "transfer_reference": e["transfer_reference"],
                    "proof_evidence_ref": e["proof_evidence_ref"],
                    "giro_number": e["giro_number"],
                    "giro_bank": e["giro_bank"],
                    "giro_due_date": e["giro_due_date"],
                    "note": e["note"],
                }) for e in group],
            })
            names.append(receipt.name)
            for e in group:
                by_line[e["line_id"]]._apply_outcome({
                    "outcome": e["outcome"],
                    "collected_amount": e["amount"],
                    "unpaid_reason": e["unpaid_reason"],
                    "document_return": DOCUMENT_RETURN[e["outcome"]],
                })
        self.env.flush_all()  # pagar terakhir: indeks unik DB bekerja di dalam savepoint dispatcher
        return "accepted", _("Penerimaan dicatat dan menunggu validasi."), ",".join(names)
