# Part of odooca-fmcg. License LGPL-3.
"""Ekstensi kebijakan akuntansi perpetual FMCG distributor.

Kebijakan akuntansi perpetual FMCG (Indonesia):
HPP (Beban Pokok Penjualan, akun 510000) diakui pada saat pengeluaran barang fisik
(Surat Jalan / Delivery Order) dari Persediaan (akun 114100) ke jurnal STJ.
Ketika faktur komersial diterbitkan kemudian, pembuatan baris valuasi out tambahan
oleh stock_account akan menduplikasi HPP.

Ekstensi ini secara sempit mengecualikan pembuatan baris HPP duplikat pada invoice HANYA
jika terbukti sebagai faktur penjualan seed yang seluruh pergerakan barang terkaitnya sudah
'done' dan telah membukukan valuasi HPP delivery secara native.
Seluruh rantai native action_post / _post (termasuk _set_value pada moves) tetap berjalan utuh.
"""

from odoo import models


class AccountMove(models.Model):
    """Ekstensi sempit account.move untuk seed perpetual accounting distributor FMCG."""

    _inherit = "account.move"

    def _is_seed_commercial_invoice_with_posted_delivery_cogs(self):
        """Validasi ketat: apakah invoice ini memenuhi seluruh kriteria pengecualian HPP seed."""
        self.ensure_one()
        # 1. Tipe wajib faktur penjualan pelanggan out_invoice (bukan vendor bill, refund, atau reversal)
        if self.move_type != "out_invoice":
            return False

        # 2. Batasi hanya pada seed company distributor FMCG
        company = self.company_id
        if not company:
            return False
        is_seed_company = (
            getattr(company, "id", None) == 1
            or "Salva" in getattr(company, "name", "")
            or getattr(company, "id", None)
            == getattr(self.env.ref("base.main_company", raise_if_not_found=False), "id", -1)
        )
        if not is_seed_company:
            return False

        # 3. Wajib memiliki baris produk persediaan yang terhubung ke sale_line_ids
        inv_lines = [
            ln for ln in getattr(self, "invoice_line_ids", [])
            if getattr(ln, "display_type", False) not in ("line_section", "line_note")
            and getattr(ln, "product_id", False)
        ]
        if not inv_lines:
            return False

        has_sol = any(getattr(ln, "sale_line_ids", False) for ln in inv_lines)
        if not has_sol:
            return False

        # 4. Validasi bahwa setiap delivery move terkait berstatus 'done'
        # dan telah membukukan jurnal valuasi HPP native di STJ
        for line in inv_lines:
            sol_list = getattr(line, "sale_line_ids", None) or []
            if not sol_list:
                continue

            stock_moves = []
            for sol in sol_list:
                if hasattr(sol, "move_ids") and sol.move_ids:
                    for sm in sol.move_ids:
                        stock_moves.append(sm)

            if not stock_moves:
                continue

            # Seluruh move pengiriman wajib berstatus 'done'
            for sm in stock_moves:
                if getattr(sm, "state", "") != "done":
                    return False

            # Validasi keberadaan native HPP journal entry atau valuation layer
            has_posted_cogs = False
            for sm in stock_moves:
                # Cek account_move_ids pada stock.move
                am_recs = getattr(sm, "account_move_ids", None)
                if am_recs:
                    posted_ams = [am for am in am_recs if getattr(am, "state", "") == "posted"]
                    if posted_ams:
                        has_posted_cogs = True
                        break
                # Cek stock_valuation_layer_ids
                svl_recs = getattr(sm, "stock_valuation_layer_ids", None)
                if svl_recs:
                    has_posted_cogs = True
                    break
                # Cek jika picking memiliki move valuasi terkait di STJ
                pick = getattr(sm, "picking_id", None)
                if pick and "account.move" in self.env:
                    stj_moves = self.env["account.move"].search([
                        ("ref", "ilike", getattr(pick, "name", "---")),
                        ("state", "=", "posted"),
                    ], limit=1)
                    if stj_moves:
                        has_posted_cogs = True
                        break

            # Jika stock move ada tetapi belum membukukan HPP native, jangan kecualikan!
            if not has_posted_cogs:
                return False

        return True

    def _stock_account_prepare_realtime_out_lines_vals(self):
        """Pengecualian sempit HPP faktur komersial seed yang telah diakui saat DO."""
        res = []
        for move in self:
            if move._is_seed_commercial_invoice_with_posted_delivery_cogs():
                continue
            if hasattr(super(), "_stock_account_prepare_realtime_out_lines_vals"):
                lines = super(AccountMove, move)._stock_account_prepare_realtime_out_lines_vals()
                if lines:
                    res.extend(lines)
        return res
