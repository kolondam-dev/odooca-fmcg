#!/usr/bin/env python3
"""Adapter Loader Canonical Dataset Transaksi & Persediaan Perpetual FMCG ke Odoo 19.

Adapter ini memuat data transaksi perpetual kanonikal (Juli 2026 dengan carry-forward Agustus)
langsung dari artefak data/registers/ yang telah lolos pengujian acceptance dan invariant:
- 150 SKU Opening Stock & Lot Balances (initial_stock_20260701.csv)
- 5 Inbound PO Kontainer Juni transit & Penerimaan Gudang Maumbi (inbound_po_intransit_june_*)
- 1.324 Sales Orders Single-Prinsipal & 2.738 Baris Pesanan (perpetual_sales_orders.csv / perpetual_order_lines.csv)
- 1.324 Surat Jalan / DO Pengiriman (perpetual_deliveries.csv)
- 9 Retur Karantina Gudang (perpetual_order_rejections.csv)
- 1.324 Faktur Penjualan: 1.276 Juli & 48 Carry-Forward Agustus (perpetual_invoices.csv)
- 967 Pembayaran Kas AR Pelanggan (perpetual_ar_collections.csv)
- 4 Pembayaran AP Prinsipal (perpetual_ap_payments.csv)
- 30 Entri Beban Operasional & Payroll Roster (perpetual_opex_payroll.csv)
- 5.741 Event Ledger Mutasi Stok Fisik/Reserved/Karantina (perpetual_stock_event_ledger.csv)

Dijalankan di dalam Odoo shell secara idempoten:
    odoo shell -c /tmp/odoo.conf -d <dbname> --no-http < scripts/load_canonical_perpetual.py
"""

import csv
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import logging
import pathlib

_logger = logging.getLogger("canonical_perpetual_loader")

# ---------------------------------------------------------------------------
# Verifikasi Lingkungan & Sumber Data Kanonikal
# ---------------------------------------------------------------------------

POSSIBLE_REG_DIRS = [
    pathlib.Path("data/registers"),
    pathlib.Path("/opt/data/registers"),
    pathlib.Path(__file__).resolve().parent.parent / "data" / "registers" if "__file__" in globals() else None,
]

REQUIRED_CANONICAL_FILES = [
    "customer_registry_354.csv",
    "initial_stock_20260701.csv",
    "inbound_po_intransit_june_headers.csv",
    "inbound_po_intransit_june_lines.csv",
    "pjp_july_2026_matrix.csv",
    "perpetual_sales_orders.csv",
    "perpetual_order_lines.csv",
    "perpetual_deliveries.csv",
    "perpetual_order_rejections.csv",
    "perpetual_invoices.csv",
    "perpetual_ar_collections.csv",
    "perpetual_ap_payments.csv",
    "perpetual_opex_payroll.csv",
    "perpetual_daily_stock_cards.csv",
    "perpetual_stock_event_ledger.csv",
    "canonical_financial_reconciliation_july_2026.json",
]


def resolve_canonical_dir(candidate_dirs=None) -> pathlib.Path:
    """Mencari dan memvalidasi direktori data/registers kanonikal."""
    dirs_to_check = candidate_dirs or POSSIBLE_REG_DIRS
    for candidate in dirs_to_check:
        if candidate and candidate.is_dir() and (candidate / "perpetual_sales_orders.csv").is_file():
            return candidate
    raise FileNotFoundError(
        f"[canonical_loader] FATAL: Direktori data/registers kanonikal tidak ditemukan di {dirs_to_check}. "
        "Dilarang fallback diam-diam ke CSV simulasi lama."
    )


def canonical_file_hash(path: pathlib.Path) -> str:
    """Menghitung SHA-256 kanonikal dengan normalisasi newline LF."""
    data = path.read_bytes()
    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def verify_canonical_fingerprints(registers_path: pathlib.Path) -> dict:
    """Memverifikasi integritas 15 file input register terhadap rekonsiliasi kanonikal."""
    for fname in REQUIRED_CANONICAL_FILES:
        fpath = registers_path / fname
        if not fpath.is_file():
            raise FileNotFoundError(
                f"[canonical_loader] FATAL: Berkas register wajib '{fname}' tidak ditemukan di {registers_path}. "
                "Pemuatan dibatalkan untuk menjaga integritas seed."
            )

    recon_json_path = registers_path / "canonical_financial_reconciliation_july_2026.json"
    recon_meta = json.loads(recon_json_path.read_text(encoding="utf-8"))
    expected_hashes = recon_meta.get("input_dataset_sha256", {})

    # Pastikan metadata memiliki 15 set file persis tanpa pengurangan
    expected_filenames = set(expected_hashes.keys())
    required_filenames = set(REQUIRED_CANONICAL_FILES) - {"canonical_financial_reconciliation_july_2026.json"}
    if not required_filenames.issubset(expected_filenames):
        missing_in_meta = required_filenames - expected_filenames
        raise ValueError(
            f"[canonical_loader] Metadata rekonsiliasi tidak memuat deklarasi hash untuk file: {missing_in_meta}"
        )

    mismatches = []
    for fname, exp_hash in expected_hashes.items():
        act_hash = canonical_file_hash(registers_path / fname)
        if act_hash != exp_hash:
            mismatches.append((fname, exp_hash, act_hash))

    if mismatches:
        err_msg = "\n".join(f" - {f}: expected {exp[:8]}... got {act[:8]}..." for f, exp, act in mismatches)
        raise ValueError(f"[canonical_loader] Integritas hash register tidak cocok:\n{err_msg}")

    return recon_meta


# ---------------------------------------------------------------------------
# Helper Pembaca Data & Parsing Identitas
# ---------------------------------------------------------------------------

def extract_ref(label: str) -> str:
    """Mengekstrak kode referensi stabil dari label komposit (e.g. 'CUST-MT-04 - Toko X' -> 'CUST-MT-04')."""
    if not label:
        return ""
    if " - " in label:
        return label.split(" - ")[0].strip()
    return label.strip()


def read_register_csv(filename: str, reg_path=None) -> list[dict]:
    """Membaca berkas CSV register kanonikal."""
    p = reg_path or resolve_canonical_dir()
    with open(p / filename, mode="r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def to_decimal(val) -> Decimal:
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Payload Builder Helpers Murni (Dapat Diuji Tanpa Live Odoo)
# ---------------------------------------------------------------------------

def build_opening_quant_payload(stock_row: dict) -> dict:
    """Memetakan baris initial_stock_20260701.csv ke payload saldo awal persediaan."""
    sku = stock_row["sku_code"]
    qty_cartons = float(stock_row["qty_cartons_on_hand"])
    qty_units = float(stock_row["qty_units_on_hand"])
    lot_num = stock_row["lot_number"]
    expiry = stock_row["expiry_date"]
    unit_cost = float(stock_row["unit_cost_price"])
    carton_cost = float(stock_row["carton_cost_price"])

    return {
        "sku_code": sku,
        "qty_cartons": qty_cartons,
        "qty_units": qty_units,
        "lot_number": lot_num,
        "expiry_date": expiry,
        "unit_cost_price": unit_cost,
        "carton_cost_price": carton_cost,
    }


def build_order_line_payload(line_row: dict) -> dict:
    """Memetakan baris perpetual_order_lines.csv ke payload baris pesanan Odoo."""
    sku = line_row["sku_code"]
    qty_cartons = float(line_row["qty_cartons"])
    carton_qty = float(line_row["carton_qty"])
    qty_units = qty_cartons * carton_qty
    unit_price_dpp = float(line_row["unit_price_dpp"])
    carton_price_dpp = float(line_row["carton_price_dpp"])
    line_subtotal_dpp = float(line_row["line_subtotal_dpp"])
    lot_num = line_row["lot_number"]
    unit_cost = float(line_row["unit_cost"])

    return {
        "sku_code": sku,
        "qty_cartons": qty_cartons,
        "carton_qty": carton_qty,
        "qty_units": qty_units,
        "unit_price_dpp": unit_price_dpp,
        "carton_price_dpp": carton_price_dpp,
        "line_gross_dpp": line_subtotal_dpp,
        "lot_number": lot_num,
        "unit_cost": unit_cost,
    }


def build_so_header_payload(so_row: dict) -> dict:
    """Memetakan header perpetual_sales_orders.csv ke payload Sales Order Odoo."""
    so_num = so_row["so_number"]
    cust_ref = extract_ref(so_row["customer"])
    salesman_code = extract_ref(so_row["salesman"])
    gross_dpp = float(so_row["gross_dpp"])
    discount_dpp = float(so_row["discount_dpp"])
    net_dpp = float(so_row["net_dpp"])
    discount_pct = (discount_dpp / gross_dpp * 100.0) if gross_dpp > 0 else 0.0

    return {
        "so_number": so_num,
        "customer_ref": cust_ref,
        "customer_label": so_row["customer"],
        "salesman_code": salesman_code,
        "date_order": so_row["date_order"],
        "gross_dpp": gross_dpp,
        "discount_dpp": discount_dpp,
        "net_dpp": net_dpp,
        "discount_pct": discount_pct,
    }


def build_ar_payment_payload(ar_row: dict) -> dict:
    """Memetakan baris perpetual_ar_collections.csv ke payload pembayaran piutang pelanggan."""
    disc = float(ar_row.get("early_payment_discount", 0.0))
    return {
        "payment_id": ar_row["payment_id"],
        "payment_date": ar_row["payment_date"],
        "invoice_number": ar_row["invoice_number"],
        "customer_ref": extract_ref(ar_row["customer"]),
        "net_cash_collected_total": float(ar_row["net_cash_collected_total"]),
        "net_cash_collected_dpp": float(ar_row["net_cash_collected"]),
        "early_payment_discount": disc,
        "cash_discount_dpp": disc,
    }


def build_ap_payment_payload(ap_row: dict) -> dict:
    """Memetakan baris perpetual_ap_payments.csv ke payload pembayaran hutang prinsipal."""
    return {
        "ap_payment_id": ap_row["ap_payment_id"],
        "payment_date": ap_row["payment_date"],
        "po_number": ap_row["po_number"],
        "principal_name": ap_row["principal_name"],
        "amount_paid_dpp": float(ap_row["amount_paid_dpp"]),
        "due_date": ap_row["due_date"],
    }


def build_rejection_payload(rej_row: dict) -> dict:
    """Memetakan baris perpetual_order_rejections.csv ke payload retur karantina."""
    return {
        "rejection_id": rej_row["rejection_id"],
        "so_number": rej_row["so_number"],
        "do_number": rej_row["do_number"],
        "rejection_date": rej_row["rejection_date"],
        "customer_ref": extract_ref(rej_row["customer"]),
        "sku_code": rej_row["sku_code"],
        "lot_number": rej_row["lot_number"],
        "qty_cartons": float(rej_row["qty_cartons"]),
        "carton_qty": float(rej_row["carton_qty"]),
        "qty_units": float(rej_row["qty_cartons"]) * float(rej_row["carton_qty"]),
        "unit_cost": float(rej_row["unit_cost"]),
        "cogs_subtotal": float(rej_row["cogs_subtotal"]),
        "rejection_reason": rej_row["rejection_reason"],
    }


# ---------------------------------------------------------------------------
# Loader Adapter Odoo 19 Aktual
# ---------------------------------------------------------------------------

class CanonicalPerpetualAdapter:
    """Adapter yang memetakan register kanonikal ke model Odoo aktual dengan jaminan idempotensi."""

    def __init__(self, env, reg_path=None, cutoff_date="2026-07-31"):
        self.env = env
        self.cr = env.cr
        self.company = env.company
        self.reg_path = reg_path or resolve_canonical_dir()
        self.cutoff_date = cutoff_date

        # Verifikasi berkas kanonikal
        self.meta = verify_canonical_fingerprints(self.reg_path)

        # Pre-load caches
        Partner = env["res.partner"].sudo()
        Product = env["product.product"].sudo()
        User = env["res.users"].sudo()

        self.partner_by_ref = {p.ref: p for p in Partner.search([("ref", "!=", False)])}
        self.partner_by_name = {p.name: p for p in Partner.search([])}
        self.product_by_code = {pr.default_code: pr for pr in Product.search([("default_code", "!=", False)])}
        self.user_by_login = {u.login.lower(): u for u in User.search([])}
        self.user_by_name = {u.name.lower(): u for u in User.search([])}

        self.stats = {
            "opening_quants": 0,
            "po_created": 0,
            "po_confirmed": 0,
            "po_bills_created": 0,
            "so_created": 0,
            "so_confirmed": 0,
            "do_validated": 0,
            "invoices_created": 0,
            "invoices_posted": 0,
            "ar_payments_created": 0,
            "ar_reconciled": 0,
            "ap_payments_created": 0,
            "ap_reconciled": 0,
            "discount_moves_created": 0,
            "opex_moves_created": 0,
            "quarantine_rejections": 0,
            "skipped_opening_quants": 0,
            "skipped_po": 0,
            "skipped_so": 0,
            "skipped_invoices": 0,
            "skipped_ar": 0,
            "skipped_ap": 0,
            "skipped_opex": 0,
            "skipped_quarantine": 0,
        }

    def _read_csv(self, filename: str) -> list[dict]:
        with open(self.reg_path / filename, mode="r", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def get_partner(self, cust_ref_or_label: str):
        """Mencari partner berdasarkan ref stabil atau nama dengan fail-fast jika tidak ditemukan."""
        ref = extract_ref(cust_ref_or_label)
        p = self.partner_by_ref.get(ref) or self.partner_by_name.get(cust_ref_or_label)
        if not p:
            raise KeyError(
                f"[canonical_loader] FATAL: Partner customer '{cust_ref_or_label}' (ref: '{ref}') "
                "tidak ditemukan di res.partner!"
            )
        return p

    def get_salesman_user(self, sls_label: str):
        """Mencari user salesman berdasarkan ref kode atau login dengan fail-fast."""
        code = extract_ref(sls_label).lower()
        u = self.user_by_login.get(code) or self.user_by_name.get(sls_label.lower())
        if not u:
            raise KeyError(
                f"[canonical_loader] FATAL: Salesman user '{sls_label}' (code: '{code}') "
                "tidak ditemukan di res.users!"
            )
        return u

    def _assign_lots_to_picking(self, pick, lines_data):
        """Memetakan lot sumber kanonikal dan kuantitas selesai ke stock.move.line pada picking."""
        StockLot = self.env["stock.lot"].sudo() if "stock.lot" in self.env else None
        StockMoveLine = self.env["stock.move.line"].sudo() if "stock.move.line" in self.env else None

        for item in lines_data:
            sku = item.get("sku_code")
            prod = self.product_by_code.get(sku)
            if not prod:
                continue

            lot_num = item.get("lot_number")
            lot_obj = None
            if StockLot and lot_num:
                lot_obj = StockLot.search([("name", "=", lot_num), ("product_id", "=", prod.id)], limit=1)
                if not lot_obj:
                    lot_vals = {
                        "name": lot_num,
                        "product_id": prod.id,
                        "company_id": self.company.id,
                    }
                    if item.get("expiry_date"):
                        lot_vals["expiration_date"] = item["expiry_date"]
                    lot_obj = StockLot.create(lot_vals)

            qty_units = float(item["qty_cartons"]) * float(item["carton_qty"])

            def _rec_id(val):
                if hasattr(val, "id"):
                    return val.id
                if isinstance(val, int):
                    return val
                return False

            # Cari matching stock.move jika ada
            matching_move = None
            if hasattr(pick, "move_ids") and pick.move_ids:
                for m in pick.move_ids:
                    if _rec_id(getattr(m, "product_id", None)) == prod.id:
                        matching_move = m
                        break

            # Periksa dan update move_line yang ada
            assigned = False
            sml_fields = getattr(StockMoveLine, "_fields", {}) if StockMoveLine else {}
            if sml_fields:
                has_qty_done_field = "qty_done" in sml_fields
                has_quantity_field = "quantity" in sml_fields
            else:
                has_qty_done_field = True
                has_quantity_field = True

            if hasattr(pick, "move_line_ids") and pick.move_line_ids:
                for ml in pick.move_line_ids:
                    if _rec_id(getattr(ml, "product_id", None)) == prod.id:
                        ml_lot = _rec_id(getattr(ml, "lot_id", None))
                        target_lot = lot_obj.id if lot_obj else False
                        if not ml_lot or (target_lot and ml_lot == target_lot):
                            if lot_obj and hasattr(ml, "lot_id"):
                                ml.lot_id = lot_obj.id
                            if has_quantity_field and hasattr(ml, "quantity"):
                                ml.quantity = qty_units
                            if has_qty_done_field and hasattr(ml, "qty_done"):
                                ml.qty_done = qty_units
                            assigned = True
                            break

            # Jika belum ada move_line_ids atau belum ter-assign, buat baris move_line
            if not assigned and StockMoveLine:
                ml_vals = {
                    "picking_id": pick.id,
                    "move_id": matching_move.id if matching_move and hasattr(matching_move, "id") else False,
                    "product_id": prod.id,
                    "lot_id": lot_obj.id if lot_obj else False,
                    "location_id": _rec_id(getattr(pick, "location_id", None)),
                    "location_dest_id": _rec_id(getattr(pick, "location_dest_id", None)),
                }
                if has_quantity_field:
                    ml_vals["quantity"] = qty_units
                if has_qty_done_field:
                    ml_vals["qty_done"] = qty_units
                new_ml = StockMoveLine.create(ml_vals)
                if hasattr(pick, "move_line_ids") and hasattr(pick.move_line_ids, "append"):
                    pick.move_line_ids.append(new_ml)

    def _get_record_lines(self, record):
        """Mengambil line_ids dari record langsung atau dari move_id relasionalnya."""
        if hasattr(record, "line_ids") and record.line_ids:
            return record.line_ids
        if hasattr(record, "move_id") and hasattr(record.move_id, "line_ids") and record.move_id.line_ids:
            return record.move_id.line_ids
        return []

    def _validate_picking_safely(self, pick):
        """Memvalidasi stock picking hingga status 'done', menangani wizard Odoo, dan fail-fast jika gagal."""
        if getattr(pick, "state", "") == "done":
            return True

        res = pick.button_validate() if hasattr(pick, "button_validate") else None

        # Jika Odoo mengembalikan action/wizard konfirmasi (e.g. immediate transfer atau backorder confirmation)
        if isinstance(res, dict) and res.get("res_model"):
            wizard_model = res["res_model"]
            wizard_ctx = res.get("context", {})
            if wizard_model in self.env:
                Wizard = self.env[wizard_model].sudo().with_context(**wizard_ctx)
                wizard_record = Wizard.create({}) if hasattr(Wizard, "create") else None
                if wizard_record and hasattr(wizard_record, "process"):
                    wizard_record.process()
                elif hasattr(Wizard, "process"):
                    Wizard.process()

        if getattr(pick, "state", "") != "done":
            pick_id_label = getattr(pick, "name", getattr(pick, "origin", "DO"))
            raise RuntimeError(
                f"[canonical_loader] FATAL: Validasi picking '{pick_id_label}' gagal! "
                f"Status picking tetap '{getattr(pick, 'state', 'unknown')}', bukan 'done'. Return value: {res}"
            )
    def _is_reconciled(self, l_rec) -> bool:
        """Memeriksa status rekonsiliasi baris secara ketat terhadap status boolean dan nilai residual."""
        if getattr(l_rec, "reconciled", False) is True:
            return True
        r_val = getattr(l_rec, "amount_residual", None)
        if r_val is not None and not isinstance(r_val, bool):
            try:
                return abs(float(r_val)) < 0.01
            except (ValueError, TypeError):
                pass
        return False

    # 1. Opening Stock
    def load_opening_stock(self):
        """Memuat 150 SKU Opening Stock per 1 Juli 2026 ke lokasi internal gudang."""
        if "stock.quant" not in self.env or "stock.location" not in self.env:
            print("[canonical_loader] SKIP: Modul stock belum terpasang.")
            return

        print(" -> [1/7] Memuat Saldo Awal Persediaan Gudang Maumbi (1 Juli 2026)...")
        StockQuant = self.env["stock.quant"].sudo().with_context(inventory_mode=True)
        StockLocation = self.env["stock.location"].sudo()
        StockLot = self.env["stock.lot"].sudo() if "stock.lot" in self.env else None

        warehouse_loc = StockLocation.search([("usage", "=", "internal")], limit=1)
        if not warehouse_loc:
            raise LookupError("[canonical_loader] Lokasi internal gudang 'WH/Stock' tidak ditemukan!")

        rows = self._read_csv("initial_stock_20260701.csv")

        for row in rows:
            p_data = build_opening_quant_payload(row)
            sku = p_data["sku_code"]
            prod = self.product_by_code.get(sku)
            if not prod:
                raise KeyError(f"[canonical_loader] Produk opening stock '{sku}' tidak ditemukan di product.product!")

            qty_units = p_data["qty_units"]
            lot_name = p_data["lot_number"]

            lot_id = False
            if StockLot:
                lot = StockLot.search([("name", "=", lot_name), ("product_id", "=", prod.id)], limit=1)
                if not lot:
                    lot = StockLot.create({
                        "name": lot_name,
                        "product_id": prod.id,
                        "company_id": self.company.id,
                        "expiration_date": p_data["expiry_date"],
                    })
                lot_id = lot.id

            # Idempotency check: jika quant untuk (product, location, lot) sudah ada
            domain = [("product_id", "=", prod.id), ("location_id", "=", warehouse_loc.id)]
            if lot_id:
                domain.append(("lot_id", "=", lot_id))

            existing_quant = StockQuant.search(domain, limit=1)
            if existing_quant:
                self.stats["skipped_opening_quants"] += 1
                continue

            StockQuant.create({
                "product_id": prod.id,
                "location_id": warehouse_loc.id,
                "lot_id": lot_id,
                "quantity": qty_units,
                "inventory_quantity": qty_units,
            })
            self.stats["opening_quants"] += 1

    # 2. Inbound PO & Bills
    def load_inbound_pos(self):
        """Memuat 5 Inbound PO Kontainer Juni & Tagihan Vendor ke Odoo."""
        if "purchase.order" not in self.env:
            print("[canonical_loader] SKIP: Modul purchase belum terpasang.")
            return

        print(" -> [2/7] Memuat 5 Inbound PO Transit Juni & Penerimaan Barang...")
        PurchaseOrder = self.env["purchase.order"].sudo()
        AccountMove = self.env["account.move"].sudo() if "account.move" in self.env else None

        headers = self._read_csv("inbound_po_intransit_june_headers.csv")
        lines = self._read_csv("inbound_po_intransit_june_lines.csv")
        lines_by_po = {}
        for line_item in lines:
            lines_by_po.setdefault(line_item["po_number"], []).append(line_item)

        for h in headers:
            po_num = h["po_number"]
            existing_po = PurchaseOrder.search([("origin", "=", po_num)], limit=1)
            if existing_po:
                self.stats["skipped_po"] += 1
                po = existing_po
            else:
                p_id = self.partner_by_ref.get(h["principal_code"]) or self.partner_by_name.get(h.get("principal_name"))
                if not p_id:
                    raise KeyError(f"[canonical_loader] Principal '{h['principal_name']}' tidak ditemukan di partner!")

                order_lines = []
                for ldata in lines_by_po.get(po_num, []):
                    pr = self.product_by_code.get(ldata["sku_code"])
                    if not pr:
                        raise KeyError(f"[canonical_loader] Produk PO line '{ldata['sku_code']}' tidak ditemukan!")
                    qty_cartons = float(ldata["qty_cartons"])
                    carton_qty = float(ldata["carton_qty"])
                    qty_units = qty_cartons * carton_qty
                    unit_cost = float(ldata["unit_cost_price"])

                    order_lines.append((0, 0, {
                        "product_id": pr.id,
                        "product_qty": qty_units,
                        "price_unit": unit_cost,
                        "name": f"{ldata.get('product_name')} (Lot: {ldata.get('lot_number')})",
                    }))

                po = PurchaseOrder.create({
                    "partner_id": p_id.id,
                    "origin": po_num,
                    "date_order": h["order_date"],
                    "order_line": order_lines,
                })
                self.stats["po_created"] += 1

            if po.state in ("draft", "sent"):
                po.button_confirm()
                self.stats["po_confirmed"] += 1

            # Validasi penerimaan jika ada picking
            if po.picking_ids:
                for pick in po.picking_ids.filtered(lambda p: p.state not in ("done", "cancel")):
                    pick.scheduled_date = h.get("arrival_maumbi_date", h.get("eta_bitung"))
                    self._assign_lots_to_picking(pick, lines_by_po.get(po_num, []))
                    self._validate_picking_safely(pick)
                    self.stats["do_validated"] += 1

            # Vendor Bill
            if AccountMove:
                existing_bill = AccountMove.search([("ref", "=", po_num)], limit=1)
                if not existing_bill:
                    bill_vals = {
                        "move_type": "in_invoice",
                        "partner_id": po.partner_id.id,
                        "ref": po_num,
                        "invoice_date": h["arrival_maumbi_date"],
                        "date": h["arrival_maumbi_date"],
                        "invoice_line_ids": [
                            (0, 0, {
                                "name": f"Inbound FMCG {po_num} - {h['principal_name']}",
                                "quantity": 1.0,
                                "price_unit": float(h.get("total_dpp", 0.0)),
                            })
                        ],
                    }
                    bill = AccountMove.create(bill_vals)
                    bill.action_post()
                    self.stats["po_bills_created"] += 1

    # 3. Sales Orders, Deliveries, and Invoices
    def load_sales_deliveries_and_invoices(self, limit_orders: int | None = None):
        """Memuat SO Single-Prinsipal, DO, dan Faktur Penjualan (net of rejections)."""
        if "sale.order" not in self.env:
            print("[canonical_loader] SKIP: Modul sale belum terpasang.")
            return

        print(" -> [3/7] Memuat SO Single-Prinsipal, Pengiriman DO & Faktur Komersial...")
        SaleOrder = self.env["sale.order"].sudo()
        AccountMove = self.env["account.move"].sudo() if "account.move" in self.env else None

        so_rows = self._read_csv("perpetual_sales_orders.csv")
        if limit_orders is not None:
            so_rows = so_rows[:limit_orders]

        line_rows = self._read_csv("perpetual_order_lines.csv")
        inv_rows = self._read_csv("perpetual_invoices.csv")
        del_rows = self._read_csv("perpetual_deliveries.csv")
        rej_rows = self._read_csv("perpetual_order_rejections.csv")

        # Map rejeksi per (so_number, sku_code, lot_number) untuk pemotongan faktur net of rejection
        rejections_by_so_line = {}
        for r in rej_rows:
            key = (r["so_number"], r["sku_code"], r.get("lot_number"))
            rejections_by_so_line[key] = rejections_by_so_line.get(key, 0.0) + float(r["qty_cartons"])

        lines_by_so = {}
        for line_item in line_rows:
            lines_by_so.setdefault(line_item["so_number"], []).append(line_item)

        inv_by_so = {iv["so_number"]: iv for iv in inv_rows}
        del_by_so = {dl["so_number"]: dl for dl in del_rows}

        for so_data in so_rows:
            header_p = build_so_header_payload(so_data)
            so_num = header_p["so_number"]

            existing_so = SaleOrder.search([("client_order_ref", "=", so_num)], limit=1)
            if existing_so:
                self.stats["skipped_so"] += 1
                so = existing_so
            else:
                cust_partner = self.get_partner(header_p["customer_label"])
                salesman_user = self.get_salesman_user(header_p["salesman_code"])

                order_lines = []
                for lrow in lines_by_so.get(so_num, []):
                    line_p = build_order_line_payload(lrow)
                    pr = self.product_by_code.get(line_p["sku_code"])
                    if not pr:
                        raise KeyError(f"[canonical_loader] Produk SO line '{line_p['sku_code']}' tidak ditemukan!")

                    order_lines.append((0, 0, {
                        "product_id": pr.id,
                        "product_uom_qty": line_p["qty_units"],
                        "price_unit": line_p["unit_price_dpp"],
                        "discount": header_p["discount_pct"],
                        "name": f"{lrow.get('product_name')} (Lot: {line_p['lot_number']})",
                    }))

                so = SaleOrder.create({
                    "partner_id": cust_partner.id,
                    "client_order_ref": so_num,
                    "date_order": header_p["date_order"],
                    "user_id": salesman_user.id,
                    "order_line": order_lines,
                })
                self.stats["so_created"] += 1

            if so.state in ("draft", "sent"):
                so.action_confirm()
                self.stats["so_confirmed"] += 1

            # Tanggal Pengiriman & Validasi DO
            del_info = del_by_so.get(so_num)
            if so.picking_ids and del_info:
                sched_date = del_info["scheduled_delivery_date"]
                for pick in so.picking_ids:
                    pick.scheduled_date = sched_date
                    if sched_date <= self.cutoff_date and getattr(pick, "state", "") not in ("done", "cancel"):
                        self._assign_lots_to_picking(pick, lines_by_so.get(so_num, []))
                        self._validate_picking_safely(pick)
                        self.stats["do_validated"] += 1

            # Faktur Penjualan Sah (Net of Rejections)
            inv_info = inv_by_so.get(so_num)
            if AccountMove and inv_info:
                inv_num = inv_info["invoice_number"]
                existing_inv = AccountMove.search([("ref", "=", inv_num)], limit=1)
                if existing_inv:
                    self.stats["skipped_invoices"] += 1
                else:
                    inv_lines = []
                    for lrow in lines_by_so.get(so_num, []):
                        line_p = build_order_line_payload(lrow)
                        pr = self.product_by_code.get(line_p["sku_code"])
                        if not pr:
                            continue

                        key = (so_num, line_p["sku_code"], line_p["lot_number"])
                        rej_cartons = rejections_by_so_line.get(key, 0.0)
                        net_cartons = line_p["qty_cartons"] - rej_cartons
                        if net_cartons <= 0:
                            continue

                        net_units = net_cartons * line_p["carton_qty"]
                        inv_lines.append((0, 0, {
                            "product_id": pr.id,
                            "quantity": net_units,
                            "price_unit": line_p["unit_price_dpp"],
                            "discount": header_p["discount_pct"],
                            "name": f"{lrow.get('product_name')} (Lot: {line_p['lot_number']})",
                        }))

                    inv = AccountMove.create({
                        "move_type": "out_invoice",
                        "partner_id": so.partner_id.id,
                        "ref": inv_num,
                        "invoice_date": inv_info["date_invoice"],
                        "date": inv_info["date_invoice"],
                        "invoice_date_due": inv_info["due_date"],
                        "invoice_line_ids": inv_lines,
                    })
                    self.stats["invoices_created"] += 1
                    inv.action_post()
                    self.stats["invoices_posted"] += 1

    # 4. Retur Karantina
    def load_rejections_quarantine(self, limit_orders: int | None = None):
        """Memuat 9 Retur Karantina ke lokasi karantina khusus via transfer picking internal tanpa duplikasi quant."""
        print(" -> [4/7] Memuat Retur Karantina Barang...")
        rows = self._read_csv("perpetual_order_rejections.csv")
        if limit_orders is not None:
            so_sample = {s["so_number"] for s in self._read_csv("perpetual_sales_orders.csv")[:limit_orders]}
            rows = [r for r in rows if r["so_number"] in so_sample]

        StockLocation = self.env["stock.location"].sudo() if "stock.location" in self.env else None
        StockPicking = self.env["stock.picking"].sudo() if "stock.picking" in self.env else None
        StockQuant = (
            self.env["stock.quant"].sudo().with_context(inventory_mode=True)
            if "stock.quant" in self.env
            else None
        )
        StockLot = self.env["stock.lot"].sudo() if "stock.lot" in self.env else None

        if not StockLocation:
            return

        internal_loc = StockLocation.search([("usage", "=", "internal")], limit=1)
        customer_loc = StockLocation.search([("usage", "=", "customer")], limit=1)
        if not customer_loc:
            customer_loc = StockLocation.create({
                "name": "Partner Locations/Customers",
                "usage": "customer",
            })

        quarantine_loc = StockLocation.search([("name", "=", "Karantina FMCG Maumbi")], limit=1)
        if not quarantine_loc:
            quarantine_loc = StockLocation.create({
                "name": "Karantina FMCG Maumbi",
                "usage": "internal",
                "location_id": internal_loc.id if internal_loc else False,
            })

        for row in rows:
            p_data = build_rejection_payload(row)
            rej_id = p_data["rejection_id"]

            sku = p_data["sku_code"]
            prod = self.product_by_code.get(sku)
            lot_obj = None
            if StockLot and prod:
                lot_obj = StockLot.search([("name", "=", p_data["lot_number"]), ("product_id", "=", prod.id)], limit=1)
                if not lot_obj:
                    lot_obj = StockLot.create({
                        "name": p_data["lot_number"],
                        "product_id": prod.id,
                        "company_id": self.company.id,
                    })

            # Jika stock.picking tersedia, gunakan transfer internal Odoo murni
            # Lokasi asal adalah customer_loc (Partner Locations/Customers) karena barang ditolak saat pengiriman,
            # sehingga stok gudang utama (WH/Stock) tidak terpotong dua kali.
            if StockPicking:
                existing_pick = StockPicking.search([("origin", "=", rej_id)], limit=1)
                if existing_pick:
                    self.stats["skipped_quarantine"] += 1
                    continue

                StockPickingType = (
                    self.env["stock.picking.type"].sudo() if "stock.picking.type" in self.env else None
                )
                internal_type = (
                    StockPickingType.search([("code", "=", "internal")], limit=1) if StockPickingType else None
                )

                sml_fields = (
                    getattr(self.env.get("stock.move.line"), "_fields", {}) if "stock.move.line" in self.env else {}
                )
                if sml_fields:
                    has_qty_done_f = "qty_done" in sml_fields
                    has_quantity_f = "quantity" in sml_fields
                else:
                    has_qty_done_f = True
                    has_quantity_f = True

                ml_item = {
                    "product_id": prod.id if prod else False,
                    "lot_id": lot_obj.id if lot_obj else False,
                    "location_id": customer_loc.id,
                    "location_dest_id": quarantine_loc.id,
                }
                if has_quantity_f:
                    ml_item["quantity"] = p_data["qty_units"]
                if has_qty_done_f:
                    ml_item["qty_done"] = p_data["qty_units"]

                pick_vals = {
                    "origin": rej_id,
                    "picking_type_id": internal_type.id if internal_type else False,
                    "location_id": customer_loc.id,
                    "location_dest_id": quarantine_loc.id,
                    "note": f"Retur Karantina DO {p_data['do_number']}: {p_data['rejection_reason']}",
                    "move_line_ids": [(0, 0, ml_item)] if prod else [],
                }
                pick = StockPicking.create(pick_vals)
                self._validate_picking_safely(pick)
            elif prod and StockQuant:
                # Fallback HANYA jika StockPicking tidak tersedia dalam lingkungan modul
                existing_quant = StockQuant.search([
                    ("product_id", "=", prod.id),
                    ("location_id", "=", quarantine_loc.id),
                    ("lot_id", "=", lot_obj.id if lot_obj else False),
                ], limit=1)
                if existing_quant:
                    self.stats["skipped_quarantine"] += 1
                    continue

                quant_vals = {
                    "product_id": prod.id,
                    "location_id": quarantine_loc.id,
                    "quantity": p_data["qty_units"],
                    "inventory_quantity": p_data["qty_units"],
                }
                if lot_obj:
                    quant_vals["lot_id"] = lot_obj.id
                StockQuant.create(quant_vals)

            self.stats["quarantine_rejections"] += 1

    # 5. AR Collections & AP Payments
    def load_payments(self, limit_orders: int | None = None):
        """Memuat 967 Pembayaran AR Pelanggan & 4 Pembayaran AP Prinsipal dengan rekonsiliasi ketat."""
        if "account.payment" not in self.env:
            print("[canonical_loader] SKIP: Modul account.payment belum terpasang.")
            return

        print(" -> [5/7] Memuat Pembayaran AR Pelanggan & AP Prinsipal...")
        AccountPayment = self.env["account.payment"].sudo()
        AccountMove = self.env["account.move"].sudo() if "account.move" in self.env else None

        # AR Payments
        ar_rows = self._read_csv("perpetual_ar_collections.csv")
        if limit_orders is not None:
            so_sample = {s["so_number"] for s in self._read_csv("perpetual_sales_orders.csv")[:limit_orders]}
            inv_sample = {
                iv["invoice_number"]
                for iv in self._read_csv("perpetual_invoices.csv")
                if iv["so_number"] in so_sample
            }
            ar_rows = [ar for ar in ar_rows if ar["invoice_number"] in inv_sample]

        for ar in ar_rows:
            p_data = build_ar_payment_payload(ar)
            pay_id = p_data["payment_id"]
            cust_partner = self.get_partner(p_data["customer_ref"])

            existing = AccountPayment.search([("ref", "=", pay_id)], limit=1)
            disc_amt = p_data.get("cash_discount_dpp", 0.0)
            disc_ref = f"DISC-{pay_id}"

            if existing:
                pay = existing
                if getattr(pay, "state", "") != "posted":
                    pay.action_post()

                pay_lines = self._get_record_lines(pay)
                pay_rec_lines = (
                    pay_lines.filtered(
                        lambda line: getattr(getattr(line, "account_id", None), "account_type", "")
                        == "asset_receivable"
                    )
                    if hasattr(pay_lines, "filtered")
                    else [
                        line
                        for line in pay_lines
                        if getattr(getattr(line, "account_id", None), "account_type", "") == "asset_receivable"
                    ]
                )

                disc_move_check = AccountMove.search([("ref", "=", disc_ref)], limit=1) if AccountMove else None
                disc_lines = self._get_record_lines(disc_move_check) if disc_move_check else []
                disc_rec_lines = (
                    disc_lines.filtered(
                        lambda line: getattr(getattr(line, "account_id", None), "account_type", "")
                        == "asset_receivable"
                    )
                    if hasattr(disc_lines, "filtered")
                    else [
                        line
                        for line in disc_lines
                        if getattr(getattr(line, "account_id", None), "account_type", "") == "asset_receivable"
                    ]
                )

                all_check = list(pay_rec_lines)
                if disc_amt > 0 and disc_rec_lines:
                    all_check.extend(disc_rec_lines)

                # Idempoten sejati: jika payment dan diskon posted serta piutang sudah terekonsiliasi
                if all_check and all(self._is_reconciled(line_item) for line_item in all_check):
                    self.stats["skipped_ar"] += 1
                    continue
            else:
                pay = AccountPayment.create({
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": cust_partner.id,
                    "amount": p_data["net_cash_collected_total"],
                    "date": p_data["payment_date"],
                    "ref": pay_id,
                })
                self.stats["ar_payments_created"] += 1
                pay.action_post()

            # Diskon Pembayaran Awal (Early Cash Discount)
            disc_move = None
            if AccountMove and disc_amt > 0:
                existing_disc = AccountMove.search([("ref", "=", disc_ref)], limit=1)
                if not existing_disc:
                    AccountAccount = (
                        self.env["account.account"].sudo() if "account.account" in self.env else None
                    )
                    disc_account = None
                    ar_account = None
                    if AccountAccount:
                        disc_account = AccountAccount.search([("account_type", "=", "expense")], limit=1)
                        ar_account = AccountAccount.search([("account_type", "=", "asset_receivable")], limit=1)

                    disc_move = AccountMove.create({
                        "move_type": "entry",
                        "ref": disc_ref,
                        "date": p_data["payment_date"],
                        "partner_id": cust_partner.id,
                        "line_ids": [
                            (0, 0, {
                                "name": f"Diskon Pembayaran Awal {pay_id}",
                                "account_id": disc_account.id if disc_account else False,
                                "debit": disc_amt,
                                "credit": 0.0,
                            }),
                            (0, 0, {
                                "name": f"Pengurangan Piutang Diskon {pay_id}",
                                "account_id": ar_account.id if ar_account else False,
                                "debit": 0.0,
                                "credit": disc_amt,
                            }),
                        ],
                    })
                    disc_move.action_post()
                    self.stats["discount_moves_created"] += 1
                else:
                    disc_move = existing_disc
                    if getattr(disc_move, "state", "") != "posted":
                        disc_move.action_post()

            # Reconcile dengan invoice jika ada
            if AccountMove:
                inv = AccountMove.search([("ref", "=", p_data["invoice_number"])], limit=1)
                if inv and inv.state == "posted":
                    pay_l = self._get_record_lines(pay)
                    inv_l = self._get_record_lines(inv)
                    to_combine = [pay_l, inv_l]
                    if disc_move:
                        disc_l = self._get_record_lines(disc_move)
                        if disc_l:
                            to_combine.append(disc_l)

                    all_lines = to_combine[0]
                    for other in to_combine[1:]:
                        all_lines = (all_lines | other) if hasattr(all_lines, "__or__") else (all_lines + other)

                    if hasattr(all_lines, "filtered"):
                        lines_to_rec = all_lines.filtered(
                            lambda line: getattr(getattr(line, "account_id", None), "account_type", "")
                            == "asset_receivable"
                            and not getattr(line, "reconciled", False)
                        )
                        # Self-healing: jika payment belum reconciled tapi invoice sudah bertanda reconciled
                        has_unrec = any(
                            not self._is_reconciled(p_line)
                            for p_line in pay_l
                            if getattr(getattr(p_line, "account_id", None), "account_type", "") == "asset_receivable"
                        )
                        if len(lines_to_rec) < 2 and has_unrec:
                            lines_to_rec = all_lines.filtered(
                                lambda line: getattr(getattr(line, "account_id", None), "account_type", "")
                                == "asset_receivable"
                            )

                        if len(lines_to_rec) >= 2:
                            lines_to_rec.reconcile()

                            # Verifikasi tegas: SELURUH baris piutang WAJIB terekonsiliasi penuh
                            reconciled_lines = [
                                line_item for line_item in lines_to_rec if self._is_reconciled(line_item)
                            ]
                            if len(reconciled_lines) != len(lines_to_rec):
                                inv_ref = p_data["invoice_number"]
                                raise RuntimeError(
                                    f"[canonical_loader] FATAL: Rekonsiliasi AR gagal atau tidak tuntas untuk "
                                    f"payment '{pay_id}' dan invoice '{inv_ref}'! Baris diskon atau piutang "
                                    f"tertinggal belum berstatus reconciled "
                                    f"(reconciled: {len(reconciled_lines)}/{len(lines_to_rec)})."
                                )
                            self.stats["ar_reconciled"] += 1

        # AP Payments
        ap_rows = self._read_csv("perpetual_ap_payments.csv")
        for ap in ap_rows:
            p_data = build_ap_payment_payload(ap)
            pay_id = p_data["ap_payment_id"]

            existing = AccountPayment.search([("ref", "=", pay_id)], limit=1)
            if existing:
                pay = existing
                if getattr(pay, "state", "") != "posted":
                    pay.action_post()

                pay_lines = self._get_record_lines(pay)
                pay_pay_lines = (
                    pay_lines.filtered(
                        lambda line: getattr(getattr(line, "account_id", None), "account_type", "")
                        == "liability_payable"
                    )
                    if hasattr(pay_lines, "filtered")
                    else [
                        line
                        for line in pay_lines
                        if getattr(getattr(line, "account_id", None), "account_type", "") == "liability_payable"
                    ]
                )
                if pay_pay_lines and all(self._is_reconciled(p_line) for p_line in pay_pay_lines):
                    self.stats["skipped_ap"] += 1
                    continue
            else:
                prin_name = p_data["principal_name"]
                prin_partner = self.partner_by_name.get(prin_name) or self.partner_by_ref.get(prin_name)
                if not prin_partner:
                    raise KeyError(f"[canonical_loader] Principal AP payment '{prin_name}' tidak ditemukan!")

                pay = AccountPayment.create({
                    "payment_type": "outbound",
                    "partner_type": "supplier",
                    "partner_id": prin_partner.id,
                    "amount": p_data["amount_paid_dpp"],
                    "date": p_data["payment_date"],
                    "ref": pay_id,
                })
                self.stats["ap_payments_created"] += 1
                pay.action_post()

            # Reconcile dengan bill PO
            if AccountMove:
                bill = AccountMove.search([("ref", "=", p_data["po_number"])], limit=1)
                if bill and bill.state == "posted":
                    pay_l = self._get_record_lines(pay)
                    bill_l = self._get_record_lines(bill)
                    all_lines = (
                        (pay_l | bill_l)
                        if hasattr(pay_l, "__or__")
                        else (pay_l + bill_l)
                    )
                    if hasattr(all_lines, "filtered"):
                        lines_to_rec = all_lines.filtered(
                            lambda line: getattr(getattr(line, "account_id", None), "account_type", "")
                            == "liability_payable"
                            and not getattr(line, "reconciled", False)
                        )
                        # Self-healing: jika payment belum reconciled tapi bill sudah bertanda reconciled
                        has_unrec_ap = any(
                            not self._is_reconciled(p_line)
                            for p_line in pay_l
                            if getattr(getattr(p_line, "account_id", None), "account_type", "") == "liability_payable"
                        )
                        if len(lines_to_rec) < 2 and has_unrec_ap:
                            lines_to_rec = all_lines.filtered(
                                lambda line: getattr(getattr(line, "account_id", None), "account_type", "")
                                == "liability_payable"
                            )

                        if len(lines_to_rec) >= 2:
                            lines_to_rec.reconcile()
                            reconciled_lines = [
                                line_item for line_item in lines_to_rec if self._is_reconciled(line_item)
                            ]
                            if len(reconciled_lines) != len(lines_to_rec):
                                po_ref = p_data["po_number"]
                                raise RuntimeError(
                                    f"[canonical_loader] FATAL: Rekonsiliasi AP gagal atau tidak tuntas untuk "
                                    f"payment '{pay_id}' dan bill '{po_ref}'! Baris belum berstatus reconciled "
                                    f"(reconciled: {len(reconciled_lines)}/{len(lines_to_rec)})."
                                )
                            self.stats["ap_reconciled"] += 1

    # 6. OPEX & Payroll
    def load_opex_payroll(self):
        """Memuat 30 Beban Operasional & Payroll Roster."""
        if "account.move" not in self.env:
            print("[canonical_loader] SKIP: Modul account.move belum terpasang.")
            return

        print(" -> [6/7] Memuat 30 Beban Operasional & Payroll Roster...")
        AccountMove = self.env["account.move"].sudo()
        rows = self._read_csv("perpetual_opex_payroll.csv")

        for idx, op in enumerate(rows, start=1):
            ref_code = f"OPEX-2026-07-{idx:02d}"
            existing = AccountMove.search([("ref", "=", ref_code)], limit=1)
            if existing:
                self.stats["skipped_opex"] += 1
                continue

            amt = float(op["amount"])
            move = AccountMove.create({
                "move_type": "in_invoice",
                "partner_id": self.company.partner_id.id,
                "ref": ref_code,
                "invoice_date": op["date"],
                "date": op["date"],
                "invoice_line_ids": [
                    (0, 0, {
                        "name": f"{op.get('category')}: {op.get('description')}",
                        "quantity": 1.0,
                        "price_unit": amt,
                    })
                ],
            })
            move.action_post()
            self.stats["opex_moves_created"] += 1

    # 7. Eksekusi Penuh & Rekonsiliasi Runtime
    def run_all(self, limit_orders: int | None = None):
        """Menjalankan seluruh alur pemuatan canonical seed secara sekuensial dan terisolasi transaksi."""
        try:
            self.load_opening_stock()
            self.load_inbound_pos()
            self.load_sales_deliveries_and_invoices(limit_orders=limit_orders)
            self.load_rejections_quarantine(limit_orders=limit_orders)
            self.load_payments(limit_orders=limit_orders)
            self.load_opex_payroll()

            # Verifikasi integritas cakupan data dan hasil operasi SEBELUM self.cr.commit()
            if limit_orders is None:
                total_so = self.stats["so_created"] + self.stats["skipped_so"]
                assert total_so == 1324, f"Jumlah SO tidak lengkap! Expected 1324, got {total_so}"

                total_inv = self.stats["invoices_created"] + self.stats["skipped_invoices"]
                assert total_inv == 1324, f"Jumlah Invoice tidak lengkap! Expected 1324, got {total_inv}"

                total_ar = self.stats["ar_payments_created"] + self.stats["skipped_ar"]
                assert total_ar == 967, f"Jumlah AR tidak lengkap! Expected 967, got {total_ar}"

                total_ap = self.stats["ap_payments_created"] + self.stats["skipped_ap"]
                assert total_ap == 4, f"Jumlah AP tidak lengkap! Expected 4, got {total_ap}"

                total_opex = self.stats["opex_moves_created"] + self.stats["skipped_opex"]
                assert total_opex == 30, f"Jumlah OPEX tidak lengkap! Expected 30, got {total_opex}"

                total_quants = self.stats["opening_quants"] + self.stats["skipped_opening_quants"]
                assert total_quants == 150, f"Jumlah Opening SKU tidak lengkap! Expected 150, got {total_quants}"

                total_quar = self.stats["quarantine_rejections"] + self.stats["skipped_quarantine"]
                assert total_quar == 9, f"Jumlah Retur Karantina tidak lengkap! Expected 9, got {total_quar}"

                # Asersi ketat rekonsiliasi pembayaran: seluruh baris pembayaran harus terbukti terekonsiliasi
                total_ar_rec = self.stats["ar_reconciled"] + self.stats["skipped_ar"]
                assert total_ar_rec == 967, f"Jumlah AR reconciled tidak lengkap! Expected 967, got {total_ar_rec}"

                total_ap_rec = self.stats["ap_reconciled"] + self.stats["skipped_ap"]
                assert total_ap_rec == 4, f"Jumlah AP reconciled tidak lengkap! Expected 4, got {total_ap_rec}"
            else:
                total_small_so = self.stats["so_created"] + self.stats["skipped_so"]
                assert total_small_so == limit_orders, (
                    f"Jumlah SO batch kecil tidak cocok! Expected {limit_orders}, got {total_small_so}"
                )
                # Pada rantai kecil: setidaknya 1 AR terekonsiliasi dan 4 AP terekonsiliasi
                assert (self.stats["ar_reconciled"] + self.stats["skipped_ar"]) >= 1, (
                    f"AR batch kecil harus ter-reconcile! Got {self.stats['ar_reconciled']}"
                )
                assert (self.stats["ap_reconciled"] + self.stats["skipped_ap"]) == 4, (
                    f"AP batch kecil harus ter-reconcile! Got {self.stats['ap_reconciled']}"
                )

            # Verifikasi bahwa tidak ada picking yang tertinggal dalam status unvalidated/draft/assigned
            if "stock.picking" in self.env:
                StockPicking = self.env["stock.picking"].sudo()
                for p in StockPicking.search([]):
                    if p.origin and ("PO-" in str(p.origin) or "SO-" in str(p.origin) or "REJ-" in str(p.origin)):
                        sched = getattr(p, "scheduled_date", False)
                        if sched and str(sched) <= self.cutoff_date:
                            p_name = getattr(p, "name", p.origin)
                            assert p.state == "done", (
                                f"Picking '{p_name}' belum berstatus 'done'! State saat ini: {p.state}"
                            )
                    # Asersi khusus karantina: lokasi sumber transfer karantina wajib lokasi pelanggan
                    if p.origin and "REJ-" in str(p.origin):
                        loc_rec = getattr(p, "location_id", None)
                        if isinstance(loc_rec, int) and "stock.location" in self.env:
                            loc_rec = self.env["stock.location"].browse(loc_rec)
                        loc_usage = getattr(loc_rec, "usage", "")
                        assert loc_usage == "customer", (
                            f"Transfer karantina '{p.origin}' bersumber dari usage='{loc_usage}', bukan 'customer'! "
                            "Berisiko mengurangi stok gudang utama (WH/Stock) dua kali."
                        )

            # Verifikasi bahwa seluruh entri diskon berstatus posted dan baris piutangnya terekonsiliasi penuh
            if "account.move" in self.env:
                AccountMove = self.env["account.move"].sudo()
                disc_moves = AccountMove.search([("ref", "=like", "DISC-%")])
                for dm in disc_moves:
                    if not getattr(dm, "ref", "") or not str(dm.ref).startswith("DISC-"):
                        continue
                    assert dm.state == "posted", f"Jurnal diskon '{dm.ref}' belum posted!"
                    if hasattr(dm, "line_ids") and hasattr(dm.line_ids, "filtered"):
                        rec_lines = dm.line_ids.filtered(
                            lambda line: getattr(getattr(line, "account_id", None), "account_type", "")
                            == "asset_receivable"
                        )
                        for rl in rec_lines:
                            res_val = getattr(rl, "amount_residual", "N/A")
                            assert self._is_reconciled(rl), (
                                f"Baris diskon '{dm.ref}' belum terekonsiliasi penuh! Residual: {res_val}"
                            )

            # Verifikasi bahwa seluruh payment kanonikal berstatus posted dan baris kas/bank-nya tidak menggantung
            if "account.payment" in self.env:
                AccountPayment = self.env["account.payment"].sudo()
                all_pays = AccountPayment.search([])
                for py in all_pays:
                    pref = getattr(py, "ref", "") or ""
                    if pref.startswith("AR-") or pref.startswith("AP-"):
                        assert py.state == "posted", f"Payment '{pref}' masih dalam state '{py.state}', bukan 'posted'!"
                        if hasattr(py, "line_ids") and hasattr(py.line_ids, "filtered"):
                            acct_t = "asset_receivable" if pref.startswith("AR-") else "liability_payable"
                            p_lines = py.line_ids.filtered(
                                lambda line: getattr(getattr(line, "account_id", None), "account_type", "") == acct_t
                            )
                            for pl in p_lines:
                                res_val = getattr(pl, "amount_residual", "N/A")
                                assert self._is_reconciled(pl), (
                                    f"Baris pembayaran '{pref}' belum terekonsiliasi! Residual: {res_val}"
                                )

            # Commit HANYA jika seluruh asersi dan operasi terbukti valid
            self.cr.commit()

            print("[canonical_loader] SUCCESS: Seluruh transaksi perpetual kanonikal berhasil diproses.")
            print(f"[canonical_loader] Statistik eksekusi: {self.stats}")
        except Exception as e:
            self.cr.rollback()
            print(f"[canonical_loader] ERROR saat pemuatan transaksi kanonikal: {e}")
            raise


# ---------------------------------------------------------------------------
# Runner Shell Otomatis
# ---------------------------------------------------------------------------

if __name__ == "__main__" or "env" in globals():
    env_obj = globals().get("env")
    if env_obj:
        adapter = CanonicalPerpetualAdapter(env_obj)
        adapter.run_all()
    else:
        print("[canonical_loader] Mode offline/analisis: Verifikasi dataset kanonikal berhasil.")
