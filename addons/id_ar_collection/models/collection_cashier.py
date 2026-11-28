"""BE-20e 1/n: kasir tunai (rancangan 8.11). Penerimaan di meja kasir tanpa PWA dan validasi kasir atas klaim mobile.

Memakai jalur lock/idempotensi yang sama dengan custody (`_record_desk`) dan protokol lock 8.4.
"""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

CASHIER_GROUPS = ("id_ar_collection.group_ar_cashier", "id_ar_collection.group_ar_control")


class CollectionReceiptCashier(models.Model):
    _inherit = "id.collection.receipt"

    def _require_cashier(self):
        if not any(self.env.user.has_group(group) for group in CASHIER_GROUPS):
            raise AccessError(_("Hanya Kasir Penerimaan atau AR Control yang dapat menghitung uang tunai."))

    @api.model
    def record_desk_cash(self, sheet_id, desk_token, occurred_at, lines):
        """Kasir menerima uang tunai dari kolektor di meja: receipt langsung `cashier_validated` (kasir menghitung
        uang fisik); accounting tetap langkah independen di 20e berikutnya. Baris harus milik SJP kolektor itu,
        SJP masih sebelum hari penyelesaian lewat, dan baris belum punya penerimaan (bila ada klaim mobile,
        gunakan `validate_cash`). Konflik/saldo basi menolak seluruh operasi tanpa receipt. Idempoten per token.
        """
        self._require_cashier()
        return self._record_desk("cashier", sheet_id, desk_token, "", occurred_at, lines)

    def validate_cash(self, counted, note=""):
        """Kasir memvalidasi klaim tunai `mobile`: `counted` memetakan id baris penerimaan ke nominal hitungan fisik.

        Selisih (hitungan - klaim) dicatat per baris dan wajib bercatatan; nominal klaim tidak diubah dan
        akuntansi/rekonsiliasi tetap di langkah berikutnya. Atomik di bawah lock SJP.
        """
        self._require_cashier()
        if len(self) != 1:
            raise UserError(_("Validasi kasir dilakukan satu penerimaan per kali."))
        company = self.env.user.company_id
        currency = company.currency_id
        note = self._text(note, "note", 255)
        receipt = self.sudo()
        sheet = receipt.sheet_id
        if sheet.company_id != company:
            raise AccessError(_("Penerimaan tidak ditemukan."))
        self._lock_rows("id_collection_sheet", "id = %s", (sheet.id,), "FOR UPDATE")
        self._lock_rows("id_collection_receipt_line", "receipt_id = %s", (receipt.id,), "FOR UPDATE")
        self.env.invalidate_all()
        receipt = self.sudo().browse(receipt.id)
        if receipt.method != "cash" or receipt.state != "posted":
            raise UserError(_("Hanya penerimaan tunai berstatus posted (klaim mobile atau custody) yang divalidasi."))
        money_lines = receipt.line_ids.filtered(lambda line: line.amount > 0)
        if not money_lines:
            raise UserError(_("Penerimaan ini tidak memuat uang untuk dihitung."))
        if not isinstance(counted, dict):
            raise UserError(_("Hitungan kasir harus berupa pemetaan baris ke nominal."))
        counted = {int(key): value for key, value in counted.items()}
        if not set(money_lines.ids) <= set(counted) or not set(counted) <= set(receipt.line_ids.ids):
            raise UserError(_("Hitungan kasir harus memuat seluruh baris yang berisi uang."))
        values = {}
        for line in receipt.line_ids:  # baris tanpa uang (unpaid nol) tidak perlu dihitung
            amount = 0.0 if line not in money_lines else self._money(counted[line.id], "counted", currency)
            if amount < 0 or (line not in money_lines and counted.get(line.id)):
                raise UserError(_("Hitungan kasir tidak valid."))
            values[line.id] = (amount, currency.round(amount - line.amount))
        if any(diff for _amount, diff in values.values()) and not note:
            raise UserError(_("Ada selisih antara klaim dan hitungan kasir: catatan wajib diisi."))
        self.env.cr.execute(
            "UPDATE id_collection_sheet SET write_date = (NOW() AT TIME ZONE 'UTC') WHERE id = %s", (sheet.id,))
        for line in receipt.line_ids:
            amount, diff = values[line.id]
            line._apply_counting({
                "counted_amount": amount, "difference": diff, "difference_note": note if diff else ""})
        receipt._apply_validation({
            "state": "cashier_validated", "cashier_id": self.env.user.id,
            "cashier_validated_at": fields.Datetime.now()})
        self.env.flush_all()
        return True
