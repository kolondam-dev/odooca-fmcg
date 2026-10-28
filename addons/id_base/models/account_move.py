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


def _convert_qty_to_product_uom(qty, uom, prod):
    """Konversi kuantitas dari UoM transaksi ke base UoM produk secara presisi."""
    if not qty:
        return 0.0
    prod_uom = getattr(prod, "uom_id", None)
    if not uom or not prod_uom or uom == prod_uom:
        return float(qty)
    if callable(getattr(uom, "_compute_quantity", None)):
        return float(uom._compute_quantity(qty, prod_uom))
    uom_factor_inv = getattr(uom, "factor_inv", None)
    uom_factor = getattr(uom, "factor", None)
    prod_factor = getattr(prod_uom, "factor", 1.0)
    prod_factor_inv = getattr(prod_uom, "factor_inv", 1.0)
    if uom_factor_inv and prod_factor:
        return float(qty) * float(uom_factor_inv) * float(prod_factor)
    if uom_factor and prod_factor_inv:
        return float(qty) / float(uom_factor) / float(prod_factor_inv)
    uom_name = str(getattr(uom, "name", "")).lower()
    carton_qty = float(getattr(prod, "carton_qty", 0.0) or 0.0)
    if ("karton" in uom_name or "ctn" in uom_name or "box" in uom_name) and carton_qty > 0.0:
        return float(qty) * carton_qty
    return float(qty)


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
        all_required_moves = []
        for line in inv_lines:
            sol_list = getattr(line, "sale_line_ids", None) or []
            if not sol_list:
                raise UserError(
                    f"[id_base] Baris faktur seed '{getattr(line, 'name', '')}' tidak memiliki relasi sale_line_ids!"
                )

            line_prod = line.product_id
            line_uom = getattr(line, "product_uom_id", getattr(line_prod, "uom_id", None))
            line_qty = float(getattr(line, "quantity", 0.0) or 0.0)
            line_base_qty = _convert_qty_to_product_uom(line_qty, line_uom, line_prod)

            line_outbound_moves = []
            line_return_moves = []

            for sol in sol_list:
                # Verifikasi keterikatan order secara WAJIB (fail-closed jika order tidak ada)
                order = getattr(sol, "order_id", None)
                if not order:
                    raise UserError(
                        f"[id_base] Baris penjualan '{getattr(sol, 'name', '')}' tidak memiliki relasi order_id!"
                    )

                # Company order wajib sama dengan company faktur
                ord_comp = getattr(order, "company_id", None)
                if not ord_comp or getattr(ord_comp, "id", None) != company.id:
                    raise UserError(
                        f"[id_base] Baris faktur seed terhubung ke Sales Order '{getattr(order, 'name', '')}' "
                        f"dari company lain (ID {getattr(ord_comp, 'id', None)})!"
                    )

                # Batch identitas persisten pada SO wajib sama dengan fmcg_seed_batch invoice
                ord_batch = getattr(order, "fmcg_seed_batch", None)
                if not ord_batch or ord_batch != self.fmcg_seed_batch:
                    raise UserError(
                        f"[id_base] Sales Order '{getattr(order, 'name', '')}' memiliki batch identitas "
                        f"'{ord_batch}' yang tidak cocok dengan batch seed faktur ('{self.fmcg_seed_batch}')!"
                    )

                ord_name = getattr(order, "name", "")
                ord_client_ref = getattr(order, "client_order_ref", "")
                if inv_origin not in (ord_name, ord_client_ref):
                    raise UserError(
                        f"[id_base] Baris faktur seed terhubung ke Sales Order '{ord_name}' "
                        f"(ref: '{ord_client_ref}') yang berbeda dari invoice_origin '{inv_origin}'!"
                    )

                mvs = getattr(sol, "move_ids", None) or []
                for sm in mvs:
                    if getattr(sm, "state", "") != "done":
                        sm_lbl = getattr(sm, "name", getattr(sm, "id", ""))
                        raise UserError(
                            f"[id_base] Pergerakan stok '{sm_lbl}' untuk faktur seed belum selesai "
                            f"(state: '{sm.state}')!"
                        )

                    sm_comp = getattr(sm, "company_id", None)
                    if sm_comp and getattr(sm_comp, "id", None) != company.id:
                        raise UserError(
                            f"[id_base] Pergerakan stok '{getattr(sm, 'name', sm.id)}' berasal dari company lain!"
                        )

                    sm_prod = getattr(sm, "product_id", None)
                    if sm_prod and getattr(sm_prod, "id", None) != getattr(line_prod, "id", None):
                        prod_name = getattr(line_prod, "display_name", line_prod)
                        raise UserError(
                            f"[id_base] Produk stock move '{getattr(sm_prod, 'display_name', sm_prod)}' "
                            f"tidak cocok dengan produk baris faktur '{prod_name}'!"
                        )

                    src_usage = getattr(getattr(sm, "location_id", None), "usage", "")
                    dest_usage = getattr(getattr(sm, "location_dest_id", None), "usage", "")

                    if src_usage == "internal" and dest_usage == "customer":
                        line_outbound_moves.append(sm)
                    elif src_usage == "customer" and dest_usage in ("internal", "inventory"):
                        line_return_moves.append(sm)
                    else:
                        raise UserError(
                            f"[id_base] Arah pergerakan stok '{getattr(sm, 'name', sm.id)}' tidak sah "
                            f"(asal: '{src_usage}', tujuan: '{dest_usage}')!"
                        )

            if not line_outbound_moves:
                ln_name = getattr(line, "name", "")
                raise UserError(
                    f"[id_base] Baris faktur seed '{ln_name}' tidak memiliki pergerakan pengiriman outbound stock.move!"
                )

            dispatched_base_qty = sum(
                _convert_qty_to_product_uom(
                    float(getattr(sm, "quantity", getattr(sm, "product_uom_qty", 0.0)) or 0.0),
                    getattr(sm, "product_uom", getattr(sm, "product_uom_id", None)),
                    line_prod,
                )
                for sm in line_outbound_moves
            )

            return_base_qty = sum(
                _convert_qty_to_product_uom(
                    float(getattr(sm, "quantity", getattr(sm, "product_uom_qty", 0.0)) or 0.0),
                    getattr(sm, "product_uom", getattr(sm, "product_uom_id", None)),
                    line_prod,
                )
                for sm in line_return_moves
            )

            if abs(dispatched_base_qty - line_base_qty) > 0.001 and return_base_qty == 0.0:
                if hasattr(self, "env") and "stock.move" in self.env:
                    StockMove = self.env["stock.move"].sudo()
                    matching_returns = StockMove.search([
                        ("product_id", "=", line_prod.id),
                        ("company_id", "=", company.id),
                        ("state", "=", "done"),
                        ("location_id.usage", "=", "customer"),
                    ])
                    for ret_sm in matching_returns:
                        ret_note = str(getattr(getattr(ret_sm, "picking_id", None), "note", "") or "")
                        ret_orig = str(getattr(ret_sm, "origin", "") or "")
                        has_matching_m_origin = any(
                            getattr(m, "origin", "") in ret_note
                            for m in line_outbound_moves
                            if getattr(m, "origin", "")
                        )
                        if inv_origin in ret_note or inv_origin in ret_orig or has_matching_m_origin:
                            return_base_qty += _convert_qty_to_product_uom(
                                float(getattr(ret_sm, "quantity", getattr(ret_sm, "product_uom_qty", 0.0)) or 0.0),
                                getattr(ret_sm, "product_uom", getattr(ret_sm, "product_uom_id", None)),
                                line_prod,
                            )

            net_delivered_base_qty = dispatched_base_qty - return_base_qty
            if abs(net_delivered_base_qty - line_base_qty) > 0.001:
                raise UserError(
                    f"[id_base] Total kuantitas pengiriman ({dispatched_base_qty} - retur {return_base_qty} = "
                    f"{net_delivered_base_qty}) tidak cocok dengan kuantitas baris faktur "
                    f"'{getattr(line, 'name', '')}' ({line_base_qty})!"
                )

            all_required_moves.extend(line_outbound_moves)

        # 7. Validasi Jurnal Valuasi Native HPP Eksak Singular sm.account_move_id & Rekonsiliasi Terkelompok
        grouped_expected_val = {}
        cogs_journal_entries = {}
        for sm in all_required_moves:
            sm_lbl = getattr(sm, "name", getattr(sm, "id", ""))
            cogs_am = getattr(sm, "account_move_id", None)
            if not cogs_am or not getattr(cogs_am, "id", None):
                raise UserError(
                    f"[id_base] Pergerakan stok '{sm_lbl}' belum memiliki jurnal valuasi native "
                    f"(account_move_id kosong)!"
                )

            cogs_lbl = getattr(cogs_am, "name", getattr(cogs_am, "id", ""))
            if getattr(cogs_am, "state", "") != "posted":
                raise UserError(
                    f"[id_base] Jurnal valuasi stok '{cogs_lbl}' belum berstatus 'posted'!"
                )

            if getattr(getattr(cogs_am, "company_id", None), "id", None) != company.id:
                raise UserError(
                    f"[id_base] Jurnal valuasi stok '{cogs_lbl}' berasal dari company lain!"
                )

            j_code = getattr(getattr(cogs_am, "journal_id", None), "code", "")
            if j_code != "STJ":
                raise UserError(
                    f"[id_base] Jurnal valuasi stok '{cogs_lbl}' bertipe '{j_code}', diharapkan 'STJ'!"
                )

            expected_stk_j = getattr(company, "account_stock_journal_id", None)
            if expected_stk_j and getattr(expected_stk_j, "id", None):
                cogs_j_id = getattr(getattr(cogs_am, "journal_id", None), "id", None)
                if cogs_j_id and cogs_j_id != expected_stk_j.id:
                    raise UserError(
                        f"[id_base] Jurnal valuasi stok '{cogs_lbl}' bukan jurnal persediaan resmi company!"
                    )

            cogs_date = str(getattr(cogs_am, "date", ""))[:10]
            sm_date = str(getattr(sm, "date", ""))[:10]
            if not cogs_date or not sm_date or cogs_date != sm_date:
                raise UserError(
                    f"[id_base] Tanggal jurnal valuasi '{cogs_date}' tidak cocok dengan "
                    f"tanggal pergerakan stok '{sm_date}'!"
                )

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
                sm_qty = float(getattr(sm, "quantity", getattr(sm, "product_uom_qty", 0.0)) or 0.0)
                expected_move_val = round(float(sm.product_id.standard_price) * sm_qty, 2)

            group_key = (cogs_am.id, getattr(getattr(sm, "product_id", None), "id", None))
            grouped_expected_val[group_key] = grouped_expected_val.get(group_key, 0.0) + (expected_move_val or 0.0)
            cogs_journal_entries[cogs_am.id] = cogs_am

        # 8. Rekonsiliasi Nilai Jurnal Valuasi HPP Terkelompok per (Jurnal, Produk)
        for (cogs_id, prod_id), exp_val in grouped_expected_val.items():
            cogs_am = cogs_journal_entries[cogs_id]
            cogs_lbl = getattr(cogs_am, "name", getattr(cogs_am, "id", ""))
            am_lines = list(getattr(cogs_am, "line_ids", []))
            if not am_lines:
                raise UserError(
                    f"[id_base] Jurnal valuasi stok '{cogs_lbl}' kosong (0 baris AML)!"
                )

            total_debit_hpp = sum(
                float(getattr(aml, "debit", 0.0) or 0.0)
                for aml in am_lines
                if getattr(getattr(aml, "account_id", None), "code", "") == "510000"
            )
            total_credit_stock = sum(
                float(getattr(aml, "credit", 0.0) or 0.0)
                for aml in am_lines
                if getattr(getattr(aml, "account_id", None), "code", "") == "113000"
            )

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

            has_any_aml_prod = any(getattr(aml, "product_id", None) for aml in am_lines)
            if has_any_aml_prod:
                prod_aml_debits = [
                    float(getattr(aml, "debit", 0.0) or 0.0)
                    for aml in am_lines
                    if getattr(getattr(aml, "account_id", None), "code", "") == "510000"
                    and (
                        getattr(getattr(aml, "product_id", None), "id", None) == prod_id
                        or (prod_id is None and getattr(aml, "product_id", None) is None)
                    )
                ]
                total_prod_debit = sum(prod_aml_debits)
                if total_prod_debit <= 0.0:
                    raise UserError(
                        f"[id_base] Jurnal valuasi stok '{cogs_lbl}' tidak memuat baris HPP untuk produk ID {prod_id}!"
                    )
                if exp_val > 0.0 and abs(total_prod_debit - exp_val) > 0.01:
                    raise UserError(
                        f"[id_base] Total nilai jurnal valuasi HPP produk ID {prod_id} (Rp {total_prod_debit:.2f}) "
                        f"tidak sesuai dengan nilai valuasi pergerakan barang (Rp {exp_val:.2f})!"
                    )
            else:
                if exp_val > 0.0 and abs(total_debit_hpp - exp_val) > 0.01:
                    raise UserError(
                        f"[id_base] Nilai jurnal valuasi HPP (Rp {total_debit_hpp:.2f}) tidak sesuai "
                        f"dengan nilai valuasi pergerakan barang (Rp {exp_val:.2f})!"
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
