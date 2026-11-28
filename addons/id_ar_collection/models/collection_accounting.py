"""BE-20e 2/n: validasi accounting tunai (rancangan 8.9). Accounting, independen dari kasir, memposting
pembayaran native lewat `account.payment.register` (yang juga merekonsiliasi) dan melepas proteksi pending.

Protokol lock 8.4: SJP -> faktur -> baris receivable -> baris SJP; saldo dibaca ulang dari DB di bawah lock sebelum
memposting. Satu transaksi: kegagalan di mana pun membatalkan seluruh pembayaran dan transisi (tanpa setengah jadi).
"""
from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

ACCOUNTING_GROUP = "id_ar_collection.group_ar_accounting"
OPEN_STATES = ("posted", "cashier_validated", "finance_verified", "instrument_registered")


class CollectionReceiptAccounting(models.Model):
    _inherit = "id.collection.receipt"

    def _require_accounting(self):
        if not self.env.user.has_group(ACCOUNTING_GROUP):
            raise AccessError(_("Hanya Accounting Penerimaan yang dapat memutuskan penerimaan."))

    def _lock_for_decision(self, receipt):
        """Kunci urut 8.4 untuk receipt ini lalu baca ulang dari DB; kembalikan receipt segar."""
        move_ids = sorted(receipt.line_ids.move_id.ids)
        self._lock_rows("id_collection_sheet", "id = %s", (receipt.sheet_id.id,), "FOR UPDATE")
        if move_ids:
            self._lock_rows("account_move", "id IN %s", (tuple(move_ids),), "FOR NO KEY UPDATE")
            self._lock_rows(
                "account_move_line", "move_id IN %s AND display_type = 'payment_term'", (tuple(move_ids),),
                "FOR UPDATE")
            self._lock_rows(
                "id_collection_sheet_line", "id IN %s OR move_id IN %s",
                (tuple(sorted(receipt.line_ids.sheet_line_id.ids)), tuple(move_ids)), "FOR UPDATE")
        self.env.flush_all()
        self.env.invalidate_all()
        return self.sudo().browse(receipt.id)

    def accounting_validate(self, journal_id):
        """Validasi accounting atas penerimaan tunai yang sudah dihitung kasir: posting pembayaran + rekonsiliasi.

        Syarat: `cashier_validated`, validator berbeda dari kasir, semua baris uang `allocated` dengan selisih kas nol
        (selisih diselesaikan terpisah), saldo faktur di bawah lock masih mencukupi. Jurnal kas/bank dipilih eksplisit.
        """
        self._require_accounting()
        if len(self) != 1:
            raise UserError(_("Validasi accounting dilakukan satu penerimaan per kali."))
        company = self.env.user.company_id
        currency = company.currency_id
        receipt = self.sudo()
        if receipt.sheet_id.company_id != company:
            raise AccessError(_("Penerimaan tidak ditemukan."))
        receipt = self._lock_for_decision(receipt)
        sheet = receipt.sheet_id
        if receipt.method != "cash" or receipt.state != "cashier_validated":
            raise UserError(_("Hanya penerimaan tunai yang sudah divalidasi kasir yang dapat divalidasi accounting."))
        if receipt.cashier_id == self.env.user:
            raise UserError(_("Pemisahan tugas: kasir tidak boleh memvalidasi accounting atas penerimaannya sendiri."))
        money_lines = receipt.line_ids.filtered(lambda line: line.amount > 0)
        for line in money_lines:
            if line.allocation_state != "allocated":
                raise UserError(_("Alokasi faktur %s belum diselesaikan (held/released).", line.move_id.name))
            if currency.compare_amounts(line.difference, 0.0):
                raise UserError(_("Selisih kas pada faktur %s belum diselesaikan.", line.move_id.name))
        journal = self.env["account.journal"].sudo().browse(self._int(journal_id, "journal_id")).exists()
        if not journal or journal.company_id != company or journal.type not in ("cash", "bank") or not journal.active:
            raise UserError(_("Jurnal pembayaran harus jurnal kas/bank aktif milik perusahaan ini."))
        balances = self._read_balances(money_lines.move_id.ids, currency)
        for line in money_lines:  # saldo dibaca ulang di bawah lock: pelunasan lewat jalur lain tidak dilanggar
            balance = balances.get(line.move_id.id, 0.0)
            if line.move_id.state != "posted" or currency.compare_amounts(line.amount, balance) > 0:
                raise UserError(_("Saldo faktur %s berubah dan tidak lagi cukup; tolak penerimaan.", line.move_id.name))
        self.env.cr.execute(
            "UPDATE id_collection_sheet SET write_date = (NOW() AT TIME ZONE 'UTC') WHERE id = %s", (sheet.id,))
        Register = self.env["account.payment.register"].sudo().with_company(company)
        for line in money_lines:
            move = line.move_id
            payments = Register.with_context(active_model="account.move", active_ids=move.ids).create({
                "amount": line.amount, "payment_date": sheet.collect_date, "journal_id": journal.id,
                "communication": f"{receipt.name} {sheet.name}", "group_payment": False,
            })._create_payments()
            if len(payments) != 1 or payments.state not in ("paid", "in_process"):
                raise UserError(_("Pembayaran faktur %s tidak terbentuk.", move.name))
            line._apply_allocation({"payment_id": payments.id})
        after = self._read_balances(money_lines.move_id.ids, currency)
        for line in money_lines:
            if currency.compare_amounts(balances[line.move_id.id] - after.get(line.move_id.id, 0.0), line.amount):
                raise UserError(_("Saldo faktur %s tidak berkurang sebesar penerimaan; dibatalkan.", line.move_id.name))
        receipt._apply_validation({
            "state": "accounting_validated", "accountant_id": self.env.user.id, "accounting_at": fields.Datetime.now()})
        self.env.flush_all()
        return True

    def reject_receipt(self, reason):
        """Accounting menolak penerimaan yang belum divalidasi accounting; proteksi pending lepas, alasan wajib."""
        self._require_accounting()
        if len(self) != 1:
            raise UserError(_("Penolakan dilakukan satu penerimaan per kali."))
        reason = self._text(reason, "reason", 255, required=True)
        receipt = self.sudo()
        if receipt.sheet_id.company_id != self.env.user.company_id:
            raise AccessError(_("Penerimaan tidak ditemukan."))
        receipt = self._lock_for_decision(receipt)
        if receipt.state not in OPEN_STATES:
            raise UserError(_("Penerimaan ini sudah diputuskan."))
        self.env.cr.execute(
            "UPDATE id_collection_sheet SET write_date = (NOW() AT TIME ZONE 'UTC') WHERE id = %s",
            (receipt.sheet_id.id,))
        receipt._apply_validation({
            "state": "rejected", "accountant_id": self.env.user.id, "accounting_at": fields.Datetime.now(),
            "reject_reason": reason})
        self.env.flush_all()
        return True
