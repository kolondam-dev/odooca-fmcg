# Part of odooca-fmcg. License LGPL-3.
"""Ekstensi kebijakan akuntansi perpetual FMCG distributor.

Kebijakan akuntansi perpetual FMCG (Indonesia):
HPP (Beban Pokok Penjualan, akun 510000) diakui pada saat pengeluaran barang fisik
(Surat Jalan / Delivery Order) dari Persediaan (akun 113000) ke jurnal STJ.
Ketika faktur komersial diterbitkan kemudian, pembuatan baris valuasi out tambahan
oleh stock_account akan menduplikasi HPP.

Ekstensi ini secara sempit mengecualikan pembuatan baris HPP duplikat pada invoice HANYA
jika faktur tersebut secara persisten ditandai sebagai faktur komersial seed (is_fmcg_seed_invoice=True),
perusahaan cocok dengan seed company (PT Salva Inti Mandiri), setiap baris produk persediaan
terhubung ke sale_line_ids dan pergerakan delivery stock.move-nya berstatus 'done', serta telah
membukukan valuasi HPP delivery secara native pada account_move_id singular di jurnal STJ
dengan pasangan akun 510000 / 113000.

Faktur non-seed biasa, vendor bill, refund/reversal, atau invoice tanpa marker seed tetap
menjalankan seluruh alur native _post / _stock_account_prepare_realtime_out_lines_vals secara utuh.
"""

from odoo import fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    """Ekstensi sempit account.move untuk seed perpetual accounting distributor FMCG."""

    _inherit = "account.move"

    is_fmcg_seed_invoice = fields.Boolean(
        string="Is FMCG Seed Commercial Invoice",
        default=False,
        copy=False,
        index=True,
        help="Penanda persisten bahwa faktur ini adalah faktur komersial seed FMCG yang HPP-nya "
        "telah dibukukan saat pengiriman barang (DO) di jurnal STJ.",
    )

    def _is_seed_commercial_invoice_with_posted_delivery_cogs(self):
        """Validasi ketat: apakah invoice ini memenuhi seluruh kriteria pengecualian HPP seed."""
        self.ensure_one()

        # 1. Penanda persisten wajib aktif (menolak faktur biasa/non-seed secara instan)
        if not getattr(self, "is_fmcg_seed_invoice", False):
            return False

        # 2. Tipe wajib faktur penjualan pelanggan out_invoice (bukan vendor bill, refund, atau reversal)
        if self.move_type != "out_invoice":
            return False

        # 3. Batasi hanya pada seed company distributor FMCG PT Salva Inti Mandiri
        company = self.company_id
        if not company:
            return False
        company_name = getattr(company, "name", "")
        company_code = getattr(company, "code", "")
        is_seed_company = company_name == "PT Salva Inti Mandiri" or company_code == "FMCG"
        if not is_seed_company:
            # Marked seed tapi company bukan PT Salva Inti Mandiri -> fail-closed!
            inv_lbl = getattr(self, "name", "") or getattr(self, "ref", "")
            raise UserError(
                f"[id_base] Faktur '{inv_lbl}' ditandai seed tetapi company "
                f"'{company_name}' bukan perusahaan seed FMCG PT Salva Inti Mandiri!"
            )

        # 4. Wajib memiliki baris produk persediaan yang terhubung ke sale_line_ids
        inv_lines = [
            ln for ln in getattr(self, "invoice_line_ids", [])
            if getattr(ln, "display_type", False) not in ("line_section", "line_note")
            and getattr(ln, "product_id", False)
        ]
        if not inv_lines:
            inv_lbl = self.name or getattr(self, "ref", "")
            raise UserError(
                f"[id_base] Faktur seed '{inv_lbl}' tidak memiliki baris produk persediaan!"
            )

        # 5. SETIAP baris produk wajib memiliki sale_line_ids dan stock delivery moves
        for line in inv_lines:
            sol_list = getattr(line, "sale_line_ids", None) or []
            if not sol_list:
                raise UserError(
                    f"[id_base] Baris faktur seed '{getattr(line, 'name', '')}' tidak memiliki relasi sale_line_ids!"
                )

            stock_moves = []
            for sol in sol_list:
                mvs = getattr(sol, "move_ids", None)
                if mvs:
                    for sm in mvs:
                        stock_moves.append(sm)

            if not stock_moves:
                ln_name = getattr(line, "name", "")
                raise UserError(
                    f"[id_base] Baris faktur seed '{ln_name}' tidak memiliki pergerakan pengiriman stock.move!"
                )

            # Setiap move pengiriman wajib berstatus 'done'
            for sm in stock_moves:
                sm_lbl = getattr(sm, "name", getattr(sm, "id", ""))
                sm_st = getattr(sm, "state", "")
                if sm_st != "done":
                    raise UserError(
                        f"[id_base] Pergerakan stok '{sm_lbl}' untuk faktur seed belum selesai (state: '{sm_st}')!"
                    )

                # 6. Validasi Jurnal Valuasi Native HPP Eksak via account_move_id singular
                cogs_am = getattr(sm, "account_move_id", None)
                if not cogs_am or not getattr(cogs_am, "id", None):
                    raise UserError(
                        f"[id_base] Pergerakan stok '{sm_lbl}' belum memiliki jurnal valuasi native "
                        f"(account_move_id kosong)!"
                    )

                cogs_lbl = getattr(cogs_am, "name", getattr(cogs_am, "id", ""))
                # Jurnal wajib berstatus posted
                if getattr(cogs_am, "state", "") != "posted":
                    raise UserError(
                        f"[id_base] Jurnal valuasi stok '{cogs_lbl}' belum berstatus 'posted'!"
                    )

                # Company jurnal wajib sama dengan company stock move dan invoice
                if getattr(getattr(cogs_am, "company_id", None), "id", None) != company.id:
                    raise UserError(
                        f"[id_base] Jurnal valuasi stok '{cogs_lbl}' berasal dari company lain!"
                    )

                # Jurnal wajib jurnal persediaan STJ
                j_code = getattr(getattr(cogs_am, "journal_id", None), "code", "")
                if j_code != "STJ":
                    raise UserError(
                        f"[id_base] Jurnal valuasi stok '{cogs_lbl}' bertipe '{j_code}', diharapkan 'STJ'!"
                    )

                # Jurnal tidak boleh kosong
                am_lines = list(getattr(cogs_am, "line_ids", []))
                if not am_lines:
                    raise UserError(
                        f"[id_base] Jurnal valuasi stok '{cogs_lbl}' kosong (0 baris AML)!"
                    )

                # Wajib ada baris debit HPP (510000) dan kredit Persediaan (113000)
                has_debit_hpp = False
                has_credit_stock = False
                for aml in am_lines:
                    acc_code = getattr(getattr(aml, "account_id", None), "code", "")
                    debit_val = float(getattr(aml, "debit", 0.0) or 0.0)
                    credit_val = float(getattr(aml, "credit", 0.0) or 0.0)
                    if acc_code == "510000" and debit_val > 0.0:
                        has_debit_hpp = True
                    if acc_code == "113000" and credit_val > 0.0:
                        has_credit_stock = True

                if not (has_debit_hpp and has_credit_stock):
                    raise UserError(
                        f"[id_base] Jurnal valuasi stok '{cogs_lbl}' tidak memuat pasangan akun "
                        f"HPP (510000) / Persediaan (113000)!"
                    )

        return True

    def _stock_account_prepare_realtime_out_lines_vals(self):
        """Pengecualian sempit HPP faktur komersial seed yang telah diakui saat DO.

        Faktur non-seed biasa, vendor bill, refund/reversal, atau invoice tanpa marker seed tetap
        menjalankan alur native super()._stock_account_prepare_realtime_out_lines_vals() secara utuh.
        """
        if hasattr(self, "filtered"):
            non_seed = self.filtered(lambda m: not m._is_seed_commercial_invoice_with_posted_delivery_cogs())
            if not non_seed:
                return []
            if hasattr(super(AccountMove, non_seed), "_stock_account_prepare_realtime_out_lines_vals"):
                return super(AccountMove, non_seed)._stock_account_prepare_realtime_out_lines_vals()
            return []

        res = []
        for move in self:
            if move._is_seed_commercial_invoice_with_posted_delivery_cogs():
                continue
            if hasattr(super(), "_stock_account_prepare_realtime_out_lines_vals"):
                lines = super(AccountMove, move)._stock_account_prepare_realtime_out_lines_vals()
                if lines:
                    res.extend(lines)
        return res
