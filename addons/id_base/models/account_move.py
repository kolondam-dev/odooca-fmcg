# Part of odooca-fmcg. License LGPL-3.
"""Ekstensi kebijakan akuntansi perpetual FMCG distributor.

Kebijakan akuntansi perpetual FMCG (Indonesia):
HPP (Beban Pokok Penjualan, akun 510000) diakui pada saat pengeluaran barang fisik
(Surat Jalan / Delivery Order) dari Persediaan (akun 113000) ke jurnal STJ.
Ketika faktur komersial diterbitkan kemudian, pembuatan baris valuasi out tambahan
oleh stock_account akan menduplikasi HPP.

Ekstensi ini secara sempit mengecualikan pembuatan baris HPP duplikat pada invoice HANYA
jika faktur tersebut memenuhi seluruh kontrak integritas seed:
1. Penanda persisten is_fmcg_seed_invoice=True dan fmcg_seed_batch="CANONICAL_JULY_2026_PERPETUAL"
2. Company terikat secara eksplisit ke company seed terdaftar (ir.config_parameter fmcg.seed_company_id
   atau XMLID id_base.fmcg_seed_company)
3. Source SO valid, ber-company sama, dan cocok dengan invoice_origin
4. Setiap baris produk persediaan terhubung ke sale_line_ids dan pergerakan delivery stock.move
   berstatus 'done' dengan produk, arah (customer), kuantitas/UoM, dan company yang cocok
5. Memiliki bukti jurnal valuasi HPP native singular sm.account_move_id (tanpa fallback) yang posted,
   berkode STJ, bertanggal bisnis sama dengan delivery move, dan bernilai HPP seimbang
   (debit 510000 / kredit 113000) yang cocok persis dengan nilai valuasi pergerakan barang.

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

    fmcg_seed_batch = fields.Char(
        string="FMCG Seed Source Batch",
        default=False,
        copy=False,
        index=True,
        help="Identitas batch seed kanonikal resmi (misal: CANONICAL_JULY_2026_PERPETUAL).",
    )

    def _get_fmcg_seed_company_id(self):
        """Mendapatkan ID company seed yang ditentukan secara eksplisit.
        Tidak mengandalkan nama, code, atau base.main_company yang dapat kebetulan cocok.
        """
        param = self.env["ir.config_parameter"].sudo().get_param("fmcg.seed_company_id")
        if param:
            try:
                return int(param)
            except (ValueError, TypeError):
                pass
        seed_comp = self.env.ref("id_base.fmcg_seed_company", raise_if_not_found=False)
        if seed_comp and hasattr(seed_comp, "id"):
            return seed_comp.id
        return None

    def _is_seed_commercial_invoice_with_posted_delivery_cogs(self):
        """Validasi ketat: apakah invoice ini memenuhi seluruh kriteria pengecualian HPP seed."""
        self.ensure_one()

        # 1. Penanda persisten wajib aktif (menolak faktur biasa/non-seed secara instan)
        if not getattr(self, "is_fmcg_seed_invoice", False):
            return False

        # 2. Tipe wajib faktur penjualan pelanggan out_invoice (bukan vendor bill, refund, atau reversal)
        if self.move_type != "out_invoice":
            return False

        inv_lbl = getattr(self, "name", "") or getattr(self, "ref", "")

        # 3. Batasi HANYA pada company seed yang ditentukan secara eksplisit (P1 Finding 2)
        company = self.company_id
        if not company or not getattr(company, "id", None):
            return False

        explicit_seed_id = self._get_fmcg_seed_company_id()
        if not explicit_seed_id or company.id != explicit_seed_id:
            comp_name = getattr(company, "name", "")
            raise UserError(
                f"[id_base] Faktur '{inv_lbl}' ditandai seed tetapi company "
                f"'{comp_name}' (ID {company.id}) bukan company seed resmi FMCG "
                f"(expected seed company ID {explicit_seed_id})!"
            )

        # 4. Validasi identitas batch dan source seed (P1 Finding 2)
        batch = getattr(self, "fmcg_seed_batch", None)
        if not batch or batch != "CANONICAL_JULY_2026_PERPETUAL":
            raise UserError(
                f"[id_base] Faktur '{inv_lbl}' ditandai seed tetapi tidak memiliki batch "
                f"identitas seed resmi ('CANONICAL_JULY_2026_PERPETUAL')!"
            )

        inv_origin = getattr(self, "invoice_origin", "") or ""
        if not inv_origin or not inv_origin.startswith("SO-202607-"):
            raise UserError(
                f"[id_base] Faktur seed '{inv_lbl}' memiliki invoice_origin '{inv_origin}' "
                f"yang bukan Sales Order seed kanonikal resmi!"
            )

        # 5. Wajib memiliki baris produk persediaan yang terhubung ke sale_line_ids
        inv_lines = [
            ln for ln in getattr(self, "invoice_line_ids", [])
            if getattr(ln, "display_type", False) not in ("line_section", "line_note")
            and getattr(ln, "product_id", False)
        ]
        if not inv_lines:
            raise UserError(
                f"[id_base] Faktur seed '{inv_lbl}' tidak memiliki baris produk persediaan!"
            )

        # 6. SETIAP baris produk wajib memiliki sale_line_ids dan stock delivery moves yang valid
        for line in inv_lines:
            sol_list = getattr(line, "sale_line_ids", None) or []
            if not sol_list:
                raise UserError(
                    f"[id_base] Baris faktur seed '{getattr(line, 'name', '')}' tidak memiliki relasi sale_line_ids!"
                )

            stock_moves = []
            for sol in sol_list:
                # Verifikasi keterikatan order
                order = getattr(sol, "order_id", None)
                if order:
                    ord_comp = getattr(order, "company_id", None)
                    if ord_comp and getattr(ord_comp, "id", None) != company.id:
                        raise UserError(
                            f"[id_base] Baris faktur seed terhubung ke Sales Order '{getattr(order, 'name', '')}' "
                            f"dari company lain (ID {getattr(ord_comp, 'id', None)})!"
                        )
                    ord_name = getattr(order, "name", "")
                    ord_client_ref = getattr(order, "client_order_ref", "")
                    if inv_origin not in (ord_name, ord_client_ref):
                        raise UserError(
                            f"[id_base] Baris faktur seed terhubung ke Sales Order '{ord_name}' "
                            f"(ref: '{ord_client_ref}') yang berbeda dari invoice_origin '{inv_origin}'!"
                        )

                mvs = getattr(sol, "move_ids", None)
                if mvs:
                    for sm in mvs:
                        stock_moves.append(sm)

            if not stock_moves:
                ln_name = getattr(line, "name", "")
                raise UserError(
                    f"[id_base] Baris faktur seed '{ln_name}' tidak memiliki pergerakan pengiriman stock.move!"
                )

            # Verifikasi kuantitas pengiriman terhadap kuantitas baris faktur
            line_qty = float(getattr(line, "quantity", 0.0) or 0.0)
            total_sm_qty = 0.0

            # 7. Verifikasi Eksak Pergerakan Stok (P1 Finding 1)
            for sm in stock_moves:
                sm_lbl = getattr(sm, "name", getattr(sm, "id", ""))
                sm_st = getattr(sm, "state", "")
                if sm_st != "done":
                    raise UserError(
                        f"[id_base] Pergerakan stok '{sm_lbl}' untuk faktur seed belum selesai (state: '{sm_st}')!"
                    )

                # Company stock move wajib cocok dengan invoice company
                sm_comp = getattr(sm, "company_id", None)
                if sm_comp and getattr(sm_comp, "id", None) != company.id:
                    raise UserError(
                        f"[id_base] Pergerakan stok '{sm_lbl}' berasal dari company lain "
                        f"(ID {getattr(sm_comp, 'id', None)} != {company.id})!"
                    )

                # Produk stock move wajib cocok dengan baris faktur
                sm_prod = getattr(sm, "product_id", None)
                if sm_prod and getattr(sm_prod, "id", None) != getattr(line.product_id, "id", None):
                    prod_name = getattr(line.product_id, "display_name", line.product_id)
                    raise UserError(
                        f"[id_base] Produk stock move '{getattr(sm_prod, 'display_name', sm_prod)}' "
                        f"tidak cocok dengan produk baris faktur '{prod_name}'!"
                    )

                # Arah pergerakan wajib pengeluaran barang ke customer (bukan internal transfer)
                dest_loc = getattr(sm, "location_dest_id", None)
                dest_usage = getattr(dest_loc, "usage", "")
                if dest_usage == "internal":
                    raise UserError(
                        f"[id_base] Pergerakan stok '{sm_lbl}' bukan pengiriman keluar (tujuan: lokasi internal)!"
                    )

                sm_move_qty = float(getattr(sm, "quantity", 0.0) or getattr(sm, "product_uom_qty", 0.0) or 0.0)
                total_sm_qty += sm_move_qty

                # 8. Validasi Jurnal Valuasi Native HPP Eksak Singular sm.account_move_id (P1 Finding 1)
                # DILARANG fallback ke stock_valuation_layer_ids atau account_move_ids
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

                # Jurnal wajib jurnal stok yang dikonfigurasi pada company (bila ada)
                expected_stk_j = getattr(company, "account_stock_journal_id", None)
                if expected_stk_j and getattr(expected_stk_j, "id", None):
                    cogs_j_id = getattr(getattr(cogs_am, "journal_id", None), "id", None)
                    if cogs_j_id and cogs_j_id != expected_stk_j.id:
                        raise UserError(
                            f"[id_base] Jurnal valuasi stok '{cogs_lbl}' bukan jurnal persediaan resmi company!"
                        )

                # Tanggal bisnis jurnal wajib cocok dengan tanggal pergerakan pengiriman
                cogs_date = str(getattr(cogs_am, "date", ""))[:10]
                sm_date = str(getattr(sm, "date", ""))[:10]
                if not cogs_date or not sm_date or cogs_date != sm_date:
                    raise UserError(
                        f"[id_base] Tanggal jurnal valuasi '{cogs_date}' tidak cocok dengan "
                        f"tanggal pergerakan stok '{sm_date}'!"
                    )

                # Jurnal tidak boleh kosong
                am_lines = list(getattr(cogs_am, "line_ids", []))
                if not am_lines:
                    raise UserError(
                        f"[id_base] Jurnal valuasi stok '{cogs_lbl}' kosong (0 baris AML)!"
                    )

                # Wajib ada baris debit HPP (510000) dan kredit Persediaan (113000) yang seimbang
                total_debit_hpp = 0.0
                total_credit_stock = 0.0
                for aml in am_lines:
                    acc_code = getattr(getattr(aml, "account_id", None), "code", "")
                    debit_val = float(getattr(aml, "debit", 0.0) or 0.0)
                    credit_val = float(getattr(aml, "credit", 0.0) or 0.0)
                    if acc_code == "510000" and debit_val > 0.0:
                        total_debit_hpp += debit_val
                    if acc_code == "113000" and credit_val > 0.0:
                        total_credit_stock += credit_val

                if total_debit_hpp <= 0.0 or total_credit_stock <= 0.0:
                    raise UserError(
                        f"[id_base] Jurnal valuasi stok '{cogs_lbl}' tidak memuat pasangan akun "
                        f"HPP (510000) / Persediaan (113000)!"
                    )

                if abs(total_debit_hpp - total_credit_stock) > 0.01:
                    raise UserError(
                        f"[id_base] Jurnal valuasi stok '{cogs_lbl}' tidak seimbang antara "
                        f"debit HPP ({total_debit_hpp}) dan kredit Persediaan ({total_credit_stock})!"
                    )

                # Rekonsiliasi nilai valuasi HPP terhadap nilai pergerakan stok
                expected_move_val = None
                svl_list = getattr(sm, "stock_valuation_layer_ids", None)
                if svl_list:
                    expected_move_val = sum(abs(float(getattr(layer, "value", 0.0) or 0.0)) for layer in svl_list)
                elif hasattr(sm, "value") and getattr(sm, "value", None) is not None:
                    expected_move_val = abs(float(sm.value))
                elif (
                    hasattr(sm.product_id, "standard_price")
                    and getattr(sm.product_id, "standard_price", None) is not None
                ):
                    expected_move_val = round(float(sm.product_id.standard_price) * sm_move_qty, 2)

                has_any_aml_prod = any(getattr(aml, "product_id", None) for aml in am_lines)
                prod_aml_debits = [
                    float(getattr(aml, "debit", 0.0) or 0.0)
                    for aml in am_lines
                    if getattr(getattr(aml, "account_id", None), "code", "") == "510000"
                    and (
                        (getattr(aml, "product_id", None) == sm.product_id)
                        or (
                            getattr(getattr(aml, "product_id", None), "id", None) is not None
                            and getattr(getattr(aml, "product_id", None), "id", None)
                            == getattr(sm.product_id, "id", None)
                        )
                    )
                ]
                prod_debit_hpp = sum(prod_aml_debits)

                if has_any_aml_prod:
                    if prod_debit_hpp <= 0.0:
                        raise UserError(
                            f"[id_base] Jurnal valuasi stok '{cogs_lbl}' tidak memuat baris HPP untuk produk "
                            f"'{getattr(sm.product_id, 'display_name', sm.product_id)}'!"
                        )
                    if expected_move_val is not None and expected_move_val > 0.0:
                        has_exact_matching_line = any(abs(d - expected_move_val) <= 0.01 for d in prod_aml_debits)
                        total_matches = abs(prod_debit_hpp - expected_move_val) <= 0.01
                        if not (has_exact_matching_line or total_matches):
                            prod_name = getattr(sm.product_id, "display_name", sm.product_id)
                            raise UserError(
                                f"[id_base] Nilai jurnal valuasi HPP produk '{prod_name}' "
                                f"(Rp {prod_debit_hpp:.2f}) tidak sesuai "
                                f"dengan nilai valuasi pergerakan barang (Rp {expected_move_val:.2f})!"
                            )
                else:
                    if expected_move_val is not None and expected_move_val > 0.0:
                        if abs(total_debit_hpp - expected_move_val) > 0.01:
                            raise UserError(
                                f"[id_base] Nilai jurnal valuasi HPP (Rp {total_debit_hpp:.2f}) tidak sesuai "
                                f"dengan nilai valuasi pergerakan barang (Rp {expected_move_val:.2f})!"
                            )

            # Kuantitas delivery moves wajib mencukupi kuantitas baris faktur
            if line_qty > 0.0 and total_sm_qty < line_qty - 0.001:
                raise UserError(
                    f"[id_base] Total kuantitas pengiriman ({total_sm_qty}) tidak mencukupi "
                    f"kuantitas baris faktur '{getattr(line, 'name', '')}' ({line_qty})!"
                )

        return True

    def _stock_account_prepare_realtime_out_lines_vals(self):
        """Pengecualian sempit HPP faktur komersial seed yang telah diakui saat DO.

        Mendukung pemanggilan recordset multi-record / mixed secara presisi:
        - Jika faktur adalah faktur seed terverifikasi -> kembalikan [] (supresi duplikasi)
        - Jika faktur adalah faktur biasa/non-seed -> panggil parent native secara utuh.
        """
        if hasattr(self, "filtered"):
            seed_moves = self.filtered(lambda m: m._is_seed_commercial_invoice_with_posted_delivery_cogs())
            non_seed_moves = self - seed_moves

            if not non_seed_moves:
                # Seluruh record dalam self adalah seed terverifikasi -> supresi duplikasi
                return []

            if not seed_moves:
                # Seluruh record dalam self adalah non-seed -> panggil native penuh
                if hasattr(super(), "_stock_account_prepare_realtime_out_lines_vals"):
                    return super()._stock_account_prepare_realtime_out_lines_vals()
                return []

            # Mixed recordset: panggil native HANYA untuk non-seed moves
            if hasattr(super(AccountMove, non_seed_moves), "_stock_account_prepare_realtime_out_lines_vals"):
                return super(AccountMove, non_seed_moves)._stock_account_prepare_realtime_out_lines_vals()
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
