"""BE-20d: custody exception (rancangan 8.12). Uang yang diterima pasca-penutupan SELALU dapat dicatat oleh
`group_ar_control`; yang ditahan hanyalah ALOKASI ke faktur bila faktur sedang dipegang SJP/penerimaan lain.

Protokol lock sama dengan submit (8.4): SJP asal -> faktur -> baris receivable -> baris SJP (termasuk baris SJP lain
yang mengklaim faktur yang sama), semuanya urut id naik, lalu saldo dibaca ulang dari DB.
"""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .collection_receipt import settlement_cutoff
from .collection_receipt_submit import FUTURE_TOLERANCE, METHOD_ORDER

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
        company = self.env.user.company_id
        currency = company.currency_id
        token = self._text(desk_token, "desk_token", 64, required=True)
        reason = self._text(reason, "reason", 255, required=True)
        occurred = self._parse_occurred_at(occurred_at)
        entries = self._parse_lines(lines, currency)
        sheet_id = self._int(sheet_id, "sheet_id")
        if any(entry["outcome"] == "unpaid" for entry in entries):
            raise UserError(_("Custody hanya untuk uang yang diterima (paid/partial)."))

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
            if existing.sheet_id != sheet:
                raise UserError(_("Token %s sudah dipakai untuk SJP lain.", token))
            return existing

        now = fields.Datetime.now()
        if sheet.state not in CUSTODY_SHEET_STATES or now < settlement_cutoff(sheet.collect_date):
            raise UserError(_("Custody pengecualian hanya untuk SJP terbit yang sudah melewati hari penyelesaian."))
        if occurred > now + FUTURE_TOLERANCE:
            raise UserError(_("Waktu kejadian tidak boleh di masa depan."))
        if sheet.state == "issued":
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
                raise UserError(_("Baris %s sudah memiliki penerimaan.", line.move_id.name))
            if line.move_id.state != "posted" or current <= 0:
                raise UserError(_("Faktur %s tidak lagi memiliki sisa tagihan.", line.move_id.name))
            if currency.compare_amounts(entry["expected_balance"], current):
                raise UserError(_("Saldo faktur %s berubah; baca ulang.", line.move_id.name))
            if entry["outcome"] == "paid" and currency.compare_amounts(entry["amount"], current):
                raise UserError(_("paid harus sama dengan saldo faktur %s.", line.move_id.name))
            if entry["outcome"] == "partial" and not (0 < entry["amount"] < current):
                raise UserError(_("partial harus lebih dari nol dan kurang dari saldo."))
            entry["balance"] = current
            clash_claim = SheetLine.search([
                ("move_id", "=", line.move_id.id), ("active_claim", "=", True), ("id", "!=", line.id)], limit=1)
            clash_pending = Line.search([("move_id", "=", line.move_id.id), ("holds_invoice", "=", True)], limit=1)
            entry["allocation_state"] = "held" if (clash_claim or clash_pending) else "allocated"

        self.env.cr.execute(
            "UPDATE id_collection_sheet SET write_date = (NOW() AT TIME ZONE 'UTC') WHERE id = %s", (sheet.id,))
        receipts = Receipt.browse()
        for method in METHOD_ORDER:
            group = [e for e in entries if e["method"] == method]
            if not group:
                continue
            receipts |= Receipt.create({
                "name": self.env["ir.sequence"].sudo().next_by_code("id.collection.receipt") or _("Baru"),
                "sheet_id": sheet.id, "company_id": company.id, "collector_id": sheet.collector_id.id,
                "source": "cashier_desk", "exception": True, "exception_reason": reason, "desk_token": token,
                "method": method, "occurred_at": occurred, "submitted_at": now,
                "line_ids": [(0, 0, {
                    "sheet_line_id": e["line_id"], "move_id": e["invoice_id"], "outcome": e["outcome"],
                    "amount": e["amount"], "balance_at_submit": e["balance"],
                    "allocation_state": e["allocation_state"], "document_return": "copy",
                    "transfer_reference": e["transfer_reference"], "proof_evidence_ref": e["proof_evidence_ref"],
                    "giro_number": e["giro_number"], "giro_bank": e["giro_bank"], "giro_due_date": e["giro_due_date"],
                    "note": e["note"],
                }) for e in group],
            })
        self.env.flush_all()  # pagar terakhir: indeks unik DB bekerja sebelum method kembali
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
