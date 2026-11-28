"""BE-20d: custody exception (rancangan 8.12). Uang yang diterima pasca-penutupan SELALU dapat dicatat oleh
`group_ar_control`; yang ditahan hanyalah ALOKASI ke faktur bila faktur sedang dipegang SJP/penerimaan lain.

Protokol lock sama dengan submit (8.4): SJP asal -> faktur -> baris receivable -> baris SJP (termasuk baris SJP lain
yang mengklaim faktur yang sama), semuanya urut id naik, lalu saldo dibaca ulang dari DB.
"""
import hashlib
import json

from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .collection_receipt import DESK_TOKEN_INDEX, settlement_cutoff
from .collection_receipt_submit import DOCUMENT_RETURN, FUTURE_TOLERANCE, METHOD_ORDER

CONTROL_GROUP = "id_ar_collection.group_ar_control"
CUSTODY_SHEET_STATES = ("issued", "returned", "reconciled", "expired")


class CollectionReceiptCustody(models.Model):
    _inherit = "id.collection.receipt"

    def _require_control(self):
        if not self.env.user.has_group(CONTROL_GROUP):
            raise AccessError(_("Hanya AR Control yang dapat mencatat custody pengecualian."))

    def _read_balances(self, move_ids, currency):
        self.env.cr.execute(
            "SELECT move_id, COALESCE(SUM(amount_residual), 0) FROM account_move_line "
            "WHERE move_id IN %s AND display_type = 'payment_term' GROUP BY move_id", (tuple(move_ids),))
        return {move_id: currency.round(float(amount)) for move_id, amount in self.env.cr.fetchall()}

    @api.model
    def record_custody_exception(self, sheet_id, desk_token, reason, occurred_at, lines):
        """Catat uang yang diterima setelah cutoff SJP; kembalikan receipt (satu per metode), idempoten per token.

        `lines` memakai format baris command receipt (line_id, invoice_id, outcome paid/partial, amount,
        expected_balance, method, transfer/giro). Baris yang fakturnya sedang dipegang SJP/penerimaan lain dicatat
        `held`; sisanya `allocated`. Nominal tidak pernah diubah untuk menutupi selisih.
        """
        self._require_control()
        return self._record_desk("custody", sheet_id, desk_token, reason, occurred_at, lines)

    @api.model
    def _record_desk(self, mode, sheet_id, desk_token, reason, occurred_at, lines):
        """Satu jalur lock/idempotensi untuk custody (`custody`) dan meja kasir tunai (`cashier`, 8.11)."""
        cashier = mode == "cashier"
        company = self.env.user.company_id
        currency = company.currency_id
        token = self._text(desk_token, "desk_token", 64, required=True)
        reason = self._text(reason, "reason", 255, required=not cashier)
        occurred = self._parse_occurred_at(occurred_at)
        entries = self._parse_lines(lines, currency)
        sheet_id = self._int(sheet_id, "sheet_id")
        if cashier and any(entry["method"] != "cash" for entry in entries):
            raise UserError(_("Meja kasir hanya untuk tunai; transfer dan giro lewat verifikasi finance."))
        # Token mengikat SATU operasi beserta payload-nya: payload berbeda dengan token sama ditolak.
        fingerprint_payload = {
            "sheet": sheet_id, "reason": reason, "occurred": occurred.isoformat(),
            "lines": sorted(entries, key=lambda entry: entry["line_id"]),
        }
        if cashier:  # custody mempertahankan bentuk lama agar token receipt #210 tetap dapat di-replay
            fingerprint_payload["mode"] = "cashier"
        fingerprint = hashlib.sha256(json.dumps(
            fingerprint_payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
        if any(entry["outcome"] == "unpaid" for entry in entries):
            raise UserError(_("Penerimaan di meja hanya untuk uang yang diterima (paid/partial)."))

        sheet = self.env["id.collection.sheet"].search(
            [("id", "=", sheet_id), ("company_id", "=", company.id)], limit=1)
        if not sheet:
            raise AccessError(_("SJP tidak ditemukan."))
        self._lock_rows("id_collection_sheet", "id = %s", (sheet.id,), "FOR UPDATE")
        self.env.invalidate_all()
        sheet = self.env["id.collection.sheet"].browse(sheet.id)
        Receipt = self.sudo().with_company(company)

        existing = Receipt.search([("desk_token", "=", token)])
        if existing:  # retry/klik ganda: kembalikan hasil yang sama, tanpa efek ganda
            if any(receipt.desk_fingerprint != fingerprint for receipt in existing):
                raise UserError(_("Token %s sudah dipakai untuk operasi yang berbeda.", token))
            return existing

        now = fields.Datetime.now()
        past_cutoff = now >= settlement_cutoff(sheet.collect_date)
        if cashier and (sheet.state != "issued" or past_cutoff):
            raise UserError(_("Meja kasir hanya untuk SJP terbit sebelum hari penyelesaian lewat; gunakan custody."))
        if not cashier and (sheet.state not in CUSTODY_SHEET_STATES or not past_cutoff):
            raise UserError(_("Custody pengecualian hanya untuk SJP terbit yang sudah melewati hari penyelesaian."))
        if occurred > now + FUTURE_TOLERANCE:
            raise UserError(_("Waktu kejadian tidak boleh di masa depan."))
        if not cashier and sheet.state == "issued":
            sheet._close_settlement_day()  # normalkan: baris tanpa penerimaan menjadi lapsed (idempoten)
            self.env.invalidate_all()
            sheet = self.env["id.collection.sheet"].browse(sheet.id)

        SheetLine = self.env["id.collection.sheet.line"].sudo()
        by_line = {line.id: line for line in SheetLine.search([("id", "in", [e["line_id"] for e in entries])])}
        for entry in entries:
            line = by_line.get(entry["line_id"])
            if not line or line.sheet_id != sheet or line.move_id.id != entry["invoice_id"]:
                raise UserError(_("Baris atau faktur tidak cocok dengan SJP."))
        move_ids = sorted({entry["invoice_id"] for entry in entries})
        self._lock_rows("account_move", "id IN %s", (tuple(move_ids),), "FOR NO KEY UPDATE")
        self._lock_rows(
            "account_move_line", "move_id IN %s AND display_type = 'payment_term'", (tuple(move_ids),), "FOR UPDATE")
        self._lock_rows(
            "id_collection_sheet_line", "id IN %s OR move_id IN %s", (tuple(sorted(by_line)), tuple(move_ids)),
            "FOR UPDATE")
        self.env.flush_all()
        self.env.invalidate_all()
        balance = self._read_balances(move_ids, currency)

        Line = self.env["id.collection.receipt.line"].sudo()
        by_line = {line_id: SheetLine.browse(line_id) for line_id in by_line}
        for entry in entries:
            line = by_line[entry["line_id"]]
            current = balance.get(line.move_id.id, 0.0)
            if Line.search_count([("sheet_line_id", "=", line.id), ("holds_line", "=", True)]):
                raise UserError(_("Baris %s sudah memiliki penerimaan; validasi penerimaan itu.", line.move_id.name))
            if entry["amount"] <= 0:
                raise UserError(_("Nominal penerimaan harus lebih dari nol."))
            entry["balance"] = current
            # Uang fisik tidak pernah ditolak karena saldo/status faktur (8.12): bila faktur sudah lunas, tidak lagi
            # posted, saldonya berubah, atau nominal melebihi saldo, penerimaan tetap tercatat dengan alokasi `held`.
            allocatable = (
                line.move_id.state == "posted" and current > 0
                and not currency.compare_amounts(entry["expected_balance"], current)
                and currency.compare_amounts(entry["amount"], current) <= 0
                and (entry["outcome"] == "partial" or not currency.compare_amounts(entry["amount"], current))
            )
            clash_claim = SheetLine.search([
                ("move_id", "=", line.move_id.id), ("active_claim", "=", True), ("id", "!=", line.id)], limit=1)
            clash_pending = Line.search([("move_id", "=", line.move_id.id), ("holds_invoice", "=", True)], limit=1)
            if cashier:  # jalur biasa: tanpa `held`; konflik atau saldo basi ditolak utuh (atomik, tanpa receipt)
                if line.outcome != "pending" or not allocatable or clash_claim or clash_pending:
                    raise UserError(_("Faktur %s tidak dapat diterima di meja kasir: saldo/klaim/pending berubah.",
                                      line.move_id.name))
                entry["allocation_state"] = "allocated"
            else:
                entry["allocation_state"] = (
                    "allocated" if allocatable and not (clash_claim or clash_pending) else "held")

        self.env.cr.execute(
            "UPDATE id_collection_sheet SET write_date = (NOW() AT TIME ZONE 'UTC') WHERE id = %s", (sheet.id,))
        try:
            with self.env.cr.savepoint():
                receipts = self._create_custody_receipts(Receipt, sheet, company, entries, vals_common={
                    "reason": reason, "token": token, "fingerprint": fingerprint, "occurred": occurred, "now": now,
                    "cashier": cashier, "user": self.env.user})
                if cashier:  # sama dengan command mobile: hasil per baris SJP tercatat
                    for entry in entries:
                        by_line[entry["line_id"]]._apply_outcome({
                            "outcome": entry["outcome"], "collected_amount": entry["amount"],
                            "document_return": DOCUMENT_RETURN[entry["outcome"]]})
        except IntegrityError as error:
            if error.pgcode == "23505" and getattr(error.diag, "constraint_name", None) == DESK_TOKEN_INDEX:
                raise UserError(_("Token %s sedang atau sudah dipakai untuk operasi custody lain.", token)) from None
            raise
        return receipts

    def _create_custody_receipts(self, Receipt, sheet, company, entries, vals_common):
        receipts = Receipt.browse()
        reason, token = vals_common["reason"], vals_common["token"]
        occurred, now = vals_common["occurred"], vals_common["now"]
        for method in METHOD_ORDER:
            group = [e for e in entries if e["method"] == method]
            if not group:
                continue
            receipts |= Receipt.create({
                "name": self.env["ir.sequence"].sudo().next_by_code("id.collection.receipt") or _("Baru"),
                "sheet_id": sheet.id, "company_id": company.id, "collector_id": sheet.collector_id.id,
                "source": "cashier_desk", "exception": not vals_common["cashier"], "exception_reason": reason,
                "desk_token": token,
                **({"state": "cashier_validated", "cashier_id": vals_common["user"].id,
                    "cashier_validated_at": now} if vals_common["cashier"] else {}),
                "desk_fingerprint": vals_common["fingerprint"], "desk_primary": not receipts,
                "method": method, "occurred_at": occurred, "submitted_at": now,
                "line_ids": [(0, 0, {
                    "sheet_line_id": e["line_id"], "move_id": e["invoice_id"], "outcome": e["outcome"],
                    "amount": e["amount"], "balance_at_submit": e["balance"],
                    "allocation_state": e["allocation_state"], "document_return": "copy",
                    **({"counted_amount": e["amount"], "difference": 0.0} if vals_common["cashier"] else {}),
                    "transfer_reference": e["transfer_reference"], "proof_evidence_ref": e["proof_evidence_ref"],
                    "giro_number": e["giro_number"], "giro_bank": e["giro_bank"], "giro_due_date": e["giro_due_date"],
                    "note": e["note"],
                }) for e in group],
            })
        self.env.flush_all()  # pagar terakhir: indeks unik DB bekerja di dalam savepoint pemanggil
        return receipts


class CollectionReceiptLineCustody(models.Model):
    _inherit = "id.collection.receipt.line"

    def resolve_held(self, mode, reason):
        """Resolusi alokasi `held` oleh AR Control: `reassign` (SJP lain belum menagih, tanpa pending) atau `release`.

        Selalu beralasan dan atomik di bawah protokol lock; nominal custody tidak berubah.
        """
        self.env["id.collection.receipt"]._require_control()
        Receipt = self.env["id.collection.receipt"]
        reason = Receipt._text(reason, "reason", 255, required=True)
        if mode not in ("reassign", "release") or len(self) != 1:
            raise UserError(_("Resolusi: pilih satu baris dan mode reassign atau release."))
        line = self.sudo()
        sheet = line.receipt_id.sheet_id
        if sheet.company_id != self.env.user.company_id:
            raise AccessError(_("Baris penerimaan tidak ditemukan."))
        currency = sheet.company_id.currency_id
        Receipt._lock_rows("id_collection_sheet", "id = %s", (sheet.id,), "FOR UPDATE")
        Receipt._lock_rows("account_move", "id = %s", (line.move_id.id,), "FOR NO KEY UPDATE")
        Receipt._lock_rows(
            "account_move_line", "move_id = %s AND display_type = 'payment_term'", (line.move_id.id,), "FOR UPDATE")
        Receipt._lock_rows(
            "id_collection_sheet_line", "id = %s OR move_id = %s", (line.sheet_line_id.id, line.move_id.id),
            "FOR UPDATE")
        self.env.flush_all()
        self.env.invalidate_all()
        line = self.sudo().browse(line.id)
        if line.allocation_state != "held" or line.receipt_id.state not in (
                "posted", "cashier_validated", "finance_verified", "instrument_registered"):
            raise UserError(_("Hanya alokasi yang ditahan dan masih pending yang dapat diselesaikan."))
        values = {"resolution_note": reason, "resolution_by": self.env.user.id, "resolution_at": fields.Datetime.now()}
        if mode == "release":
            line._apply_allocation({**values, "allocation_state": "released"})
            return True
        SheetLine = self.env["id.collection.sheet.line"].sudo()
        others = SheetLine.search([
            ("move_id", "=", line.move_id.id), ("active_claim", "=", True), ("id", "!=", line.sheet_line_id.id)])
        pending = self.sudo().search([
            ("move_id", "=", line.move_id.id), ("holds_invoice", "=", True), ("id", "!=", line.id)], limit=1)
        if pending or any(other.outcome != "pending" for other in others):
            raise UserError(_("SJP lain sudah menagih atau punya penerimaan pending: lepaskan saja (release)."))
        balance = Receipt._read_balances([line.move_id.id], currency).get(line.move_id.id, 0.0)
        if line.move_id.state != "posted" or currency.compare_amounts(line.amount, balance) > 0:
            raise UserError(_("Saldo faktur %s tidak lagi cukup untuk alokasi ini.", line.move_id.name))
        for other in others:
            other._apply_outcome({
                "outcome": "lapsed", "unpaid_reason": _("Digantikan custody %s", line.receipt_id.name)})
        line._apply_allocation({**values, "allocation_state": "allocated"})
        self.env.flush_all()
        return True
