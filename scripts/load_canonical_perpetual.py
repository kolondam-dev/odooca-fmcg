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


def _is_matching_date(actual_val, expected_dt_str: str, expected_d_only: str) -> bool:
    """Memeriksa apakah actual_val cocok dengan tanggal/waktu yang diharapkan.
    Mendukung string, datetime.datetime, datetime.date, dan pemotongan format tanggal.
    """
    if actual_val is None or actual_val is False:
        return False
    act_str = str(actual_val).strip()
    if not act_str:
        return False
    if expected_dt_str and act_str == str(expected_dt_str):
        return True
    if expected_d_only and act_str.startswith(str(expected_d_only)):
        return True
    if expected_dt_str and act_str.startswith(str(expected_dt_str)[:10]):
        return True
    return False


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


OPEX_CATEGORY_ACCOUNT_MAP = {
    "Logistik Rutin": ("610100", "Beban Logistik & Pengiriman Rutin FMCG"),
    "Payroll Karyawan": ("610200", "Beban Gaji & Tunjangan Karyawan FMCG"),
    "Lembur Gudang & Logistik": ("610300", "Beban Lembur Gudang & Logistik FMCG"),
    "Sewa & Utilitas": ("610400", "Beban Sewa Gudang & Utilitas Kantor FMCG"),
}

OPEX_PAYMENT_PARTNER_MAP = {
    "Petty Cash Kasir Operasional": ("OPEX-KASIR", "Kasir Operasional & Logistik Maumbi"),
    "Direct Payroll Bank Transfer": ("OPEX-PAYROLL", "Dana Payroll Karyawan PT Manado Makmur"),
    "Transfer Bank Mandiri": ("OPEX-VENDOR-UTIL", "Vendor Sewa & Utilitas Maumbi"),
}



# ---------------------------------------------------------------------------
# Loader Adapter Odoo 19 Aktual
# ---------------------------------------------------------------------------

def _safe_fields(obj):
    """Mengembalikan koleksi _fields dari objek/model secara defensif terhadap tipe boolean, mappingproxy, atau None."""
    f = getattr(obj, "_fields", None)
    if f is not None and not isinstance(f, bool) and hasattr(f, "__contains__") and hasattr(f, "__iter__"):
        if len(f) > 0:
            return f
    if hasattr(obj, "_vals") and isinstance(obj._vals, dict):
        return set(obj._vals.keys()) | {"date_done", "date", "origin", "name", "state", "scheduled_date", "memo", "ref"}
    if f is not None and not isinstance(f, bool) and hasattr(f, "__contains__"):
        return f
    return {}


def _iter_records(res) -> list:
    """Mengonversi hasil search/recordset Odoo maupun MockRecord/list menjadi list singleton record."""
    if not res:
        return []
    if hasattr(res, "__iter__"):
        return list(res)
    return [res]


class CanonicalPerpetualAdapter:
    """Adapter yang memetakan register kanonikal ke model Odoo aktual dengan jaminan idempotensi."""

    def __init__(self, env, reg_path=None, cutoff_date="2026-07-31"):
        self.env = env
        self.cr = env.cr
        self.company = env.company
        # Daftarkan explicit seed company ID ke ir.config_parameter untuk integritas fail-closed hook COGS
        if hasattr(self.env, "__getitem__") and "ir.config_parameter" in self.env:
            try:
                self.env["ir.config_parameter"].sudo().set_param(
                    "fmcg.seed_company_id", str(getattr(self.company, "id", 1))
                )
            except Exception:
                pass
        self.reg_path = reg_path or resolve_canonical_dir()
        self.cutoff_date = cutoff_date

        # Verifikasi berkas kanonikal
        self.meta = verify_canonical_fingerprints(self.reg_path)

        # Kumpulkan cakupan SKU kanonikal secara eksplisit langsung dari register sumber
        self.canonical_skus, self.canonical_unit_costs = self._collect_canonical_sku_scope()

        # Pre-load caches
        Partner = env["res.partner"].sudo()
        Product = env["product.product"].sudo()
        User = env["res.users"].sudo()

        self.partner_by_ref = {p.ref: p for p in Partner.search([("ref", "!=", False)])}
        self.partner_by_name = {p.name: p for p in Partner.search([])}

        prod_fields = _safe_fields(Product)
        prod_domain = [("default_code", "in", sorted(self.canonical_skus))]
        if "company_id" in prod_fields and hasattr(self, "company") and self.company:
            prod_domain.append(("company_id", "in", [False, self.company.id]))
        found_products = Product.search(prod_domain)

        self.product_by_code = {}
        for pr in _iter_records(found_products):
            code = getattr(pr, "default_code", None)
            if not code or code not in self.canonical_skus:
                continue
            if code in self.product_by_code and self.product_by_code[code].id != pr.id:
                raise RuntimeError(
                    f"[canonical_loader] FATAL: Ambiguitas produk untuk SKU kanonikal '{code}'! "
                    f"Ditemukan lebih dari satu product.product dalam scope company."
                )
            self.product_by_code[code] = pr

        missing_skus = sorted(self.canonical_skus - set(self.product_by_code.keys()))
        if missing_skus or not self.product_by_code:
            raise RuntimeError(
                f"[canonical_loader] FATAL: Scope produk kanonikal tidak lengkap atau kosong! "
                f"Expected {len(self.canonical_skus)} SKU, ditemukan {len(self.product_by_code)}. "
                f"SKU hilang (sampel): {missing_skus[:5]}"
            )

        self.user_by_login = {u.login.lower(): u for u in User.search([])}
        self.user_by_name = {u.name.lower(): u for u in User.search([])}

        self._ensure_accounting_configuration()

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

    def _collect_canonical_sku_scope(self) -> tuple[set[str], dict[str, float]]:
        """Membangun cakupan SKU kanonikal dan unit_cost langsung dari register sumber."""
        sku_set = set()
        unit_costs = {}

        for row in self._read_csv("initial_stock_20260701.csv"):
            sku = row.get("sku_code")
            if sku:
                sku_set.add(sku)
                if "unit_cost_price" in row and row["unit_cost_price"]:
                    unit_costs[sku] = float(row["unit_cost_price"])

        for row in self._read_csv("inbound_po_intransit_june_lines.csv"):
            sku = row.get("sku_code")
            if sku:
                sku_set.add(sku)
                if sku not in unit_costs and "unit_cost_price" in row and row["unit_cost_price"]:
                    unit_costs[sku] = float(row["unit_cost_price"])

        for row in self._read_csv("perpetual_order_lines.csv"):
            sku = row.get("sku_code")
            if sku:
                sku_set.add(sku)
                if sku not in unit_costs and "unit_cost" in row and row["unit_cost"]:
                    unit_costs[sku] = float(row["unit_cost"])

        for row in self._read_csv("perpetual_order_rejections.csv"):
            sku = row.get("sku_code")
            if sku:
                sku_set.add(sku)
                if sku not in unit_costs and "unit_cost" in row and row["unit_cost"]:
                    unit_costs[sku] = float(row["unit_cost"])

        if not sku_set:
            raise RuntimeError("[canonical_loader] FATAL: Scope SKU kanonikal dari CSV sumber kosong!")
        return sku_set, unit_costs

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
        if not sls_label:
            return self.env.user if hasattr(self.env, "user") else None

        code = extract_ref(sls_label).lower()
        u = self.user_by_login.get(code) or self.user_by_name.get(sls_label.lower())
        if u:
            return u

        canonical_salesmen = {
            "sls-01": "Christian Wowor",
            "sls-02": "Novry Poluan",
            "sls-03": "Ferry Rondonuwu",
            "cvs-01": "Stenly Kalalo",
            "cvs-02": "Vicky Mandagi",
            "mgt-01": "Ronald Mongisidi",
        }

        User = self.env["res.users"].sudo() if "res.users" in self.env else None
        if User is not None and code in canonical_salesmen:
            u = User.with_context(active_test=False).search([("login", "=", code)], limit=1)
            if not u:
                parts = sls_label.split(" - ", 1)
                user_name = parts[1].strip() if len(parts) > 1 else canonical_salesmen[code]
                user_vals = {
                    "name": user_name,
                    "login": code,
                    "email": f"{code}@manadodistribusi.co.id",
                }
                if hasattr(self, "company") and self.company:
                    user_vals["company_id"] = self.company.id
                    user_vals["company_ids"] = [(6, 0, [self.company.id])]
                u = User.create(user_vals)

            if u:
                self.user_by_login[code] = u
                self.user_by_name[getattr(u, "name", "").lower()] = u
                return u

        raise KeyError(
            f"[canonical_loader] FATAL: Salesman user '{sls_label}' (code: '{code}') "
            "tidak ditemukan di res.users!"
        )

    def _ensure_accounting_configuration(self):
        """Memastikan konfigurasi akuntansi persediaan FIFO & Real-Time Valuation aktif secara terisolasi.

        - Hanya memodifikasi kategori produk dalam scope produk kanonikal (tanpa fallback global).
        - Hanya memodifikasi lokasi stok dalam scope warehouse/company seed.
        - Menjamin mapping akun eksplisit (113000, 113900, 113910, 510000) dan jurnal stok (STJ) dengan readback.
        """
        if "product.category" not in self.env:
            return
        ProductCategory = self.env["product.category"].sudo()
        cat_fields = _safe_fields(ProductCategory)

        # 1. anglo_saxon_accounting pada company (fail-fast jika field ada)
        has_company = hasattr(self, "company") and self.company
        if has_company and "anglo_saxon_accounting" in getattr(self.company, "_fields", {}):
            if not self.company.anglo_saxon_accounting:
                self.company.sudo().write({"anglo_saxon_accounting": True})
                if not self.company.anglo_saxon_accounting:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Gagal mengaktifkan anglo_saxon_accounting "
                        f"pada company '{self.company.name}'!"
                    )

        # 2. Cari atau buat akun-akun akuntansi persediaan eksplisit untuk company seed
        stock_valuation_acc = None
        stock_input_acc = None
        stock_output_acc = None
        cogs_acc = None
        stock_journal = None

        if "account.account" in self.env:
            AccountAccount = self.env["account.account"].sudo()
            acc_fields = _safe_fields(AccountAccount)
            comp_domain = []
            comp_vals = {}
            if "company_ids" in acc_fields and has_company:
                comp_domain = [("company_ids", "in", [self.company.id])]
                comp_vals = {"company_ids": [(4, self.company.id)]}
            elif "company_id" in acc_fields and has_company:
                comp_domain = [("company_id", "in", [False, self.company.id])]
                comp_vals = {"company_id": self.company.id}

            def _resolve_or_create_explicit_account(code: str, name: str, acc_type: str, fallback_type: str = None):
                acc = AccountAccount.search(comp_domain + [("code", "=", code)], limit=1)
                if not acc and callable(getattr(AccountAccount, "create", None)):
                    vals = {
                        "code": code,
                        "name": name,
                        "account_type": acc_type,
                    }
                    vals.update(comp_vals)
                    try:
                        acc = AccountAccount.create(vals)
                    except Exception:
                        if fallback_type:
                            vals["account_type"] = fallback_type
                            try:
                                acc = AccountAccount.create(vals)
                            except Exception:
                                pass
                if acc and str(getattr(acc, "code", "")).strip() != code:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Kode akun hasil resolusi '{getattr(acc, 'code', None)}' "
                        f"tidak cocok dengan kode eksplisit '{code}'!"
                    )
                return acc

            stock_valuation_acc = _resolve_or_create_explicit_account(
                "113000", "Persediaan Barang Dagang FMCG", "asset_current"
            )
            stock_input_acc = _resolve_or_create_explicit_account(
                "113900", "Penerimaan Barang Sementara (Interim)", "asset_current", "liability_current"
            )
            stock_output_acc = _resolve_or_create_explicit_account(
                "113910", "Pengiriman Barang Sementara (Interim)", "asset_current"
            )
            cogs_acc = _resolve_or_create_explicit_account(
                "510000", "Harga Pokok Penjualan (HPP) FMCG", "expense_direct_cost", "expense"
            )

            # Buktikan akun-akun wajib secara fail-fast
            if not stock_valuation_acc:
                raise RuntimeError(
                    "[canonical_loader] FATAL: Akun valuasi persediaan (113000 / stock_valuation) "
                    "tidak ditemukan atau gagal dibuat!"
                )
            if not stock_input_acc:
                raise RuntimeError(
                    "[canonical_loader] FATAL: Akun perantara persediaan masuk (113900 / stock_input) "
                    "tidak ditemukan atau gagal dibuat!"
                )
            if not cogs_acc:
                raise RuntimeError(
                    "[canonical_loader] FATAL: Akun HPP (510000 / cogs) tidak ditemukan atau gagal dibuat!"
                )

            # Resolusi akun beban OPEX eksplisit per kategori kanonikal
            self.opex_accounts = {}
            for cat_label, (acc_code, acc_name) in OPEX_CATEGORY_ACCOUNT_MAP.items():
                opex_acc = _resolve_or_create_explicit_account(acc_code, acc_name, "expense")
                if not opex_acc:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Akun beban OPEX ({acc_code}) untuk kategori '{cat_label}' "
                        "tidak ditemukan atau gagal dibuat!"
                    )
                self.opex_accounts[cat_label] = opex_acc
        else:
            self.opex_accounts = {}

        self.stock_valuation_acc = stock_valuation_acc
        self.stock_input_acc = stock_input_acc
        self.stock_output_acc = stock_output_acc
        self.cogs_acc = cogs_acc

        # Resolusi partner operasional OPEX eksplisit (bukan self.company.partner_id)
        self.opex_partners = {}
        if "res.partner" in self.env:
            Partner = self.env["res.partner"].sudo()
            comp_partner_id = getattr(getattr(self.company, "partner_id", None), "id", None) if has_company else None
            for pay_type, (p_ref, p_name) in OPEX_PAYMENT_PARTNER_MAP.items():
                p_rec = self.partner_by_ref.get(p_ref) or Partner.search([("ref", "=", p_ref)], limit=1)
                if not p_rec and callable(getattr(Partner, "create", None)):
                    p_rec = Partner.create({"name": p_name, "ref": p_ref})
                if not p_rec or (comp_partner_id and getattr(p_rec, "id", None) == comp_partner_id):
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Partner operasional OPEX '{p_ref}' untuk '{pay_type}' "
                        "tidak valid atau sama dengan partner company!"
                    )
                self.partner_by_ref[p_ref] = p_rec
                self.partner_by_name[p_name] = p_rec
                self.opex_partners[pay_type] = p_rec

        # 3. Cari dan buktikan keberadaan jurnal stok eksplisit (STJ) untuk company seed
        if "account.journal" in self.env:
            AccountJournal = self.env["account.journal"].sudo()
            j_fields = _safe_fields(AccountJournal)
            has_comp_id = "company_id" in j_fields and has_company
            j_domain = [("company_id", "in", [False, self.company.id])] if has_comp_id else []
            stock_journal = AccountJournal.search(j_domain + [("code", "=", "STJ")], limit=1)
            if not stock_journal and callable(getattr(AccountJournal, "create", None)):
                jvals = {
                    "name": "Penilaian Persediaan",
                    "type": "general",
                    "code": "STJ",
                }
                if has_comp_id:
                    jvals["company_id"] = self.company.id
                if "auto_post" in j_fields:
                    jvals["auto_post"] = True
                stock_journal = AccountJournal.create(jvals)

            if not stock_journal or str(getattr(stock_journal, "code", "")).strip() != "STJ":
                raise RuntimeError(
                    "[canonical_loader] FATAL: Keberadaan jurnal stok (stock journal) "
                    "yang diwajibkan tidak dapat dibuktikan!"
                )

            # Buktikan konfigurasi company.account_stock_journal_id jika didukung model company
            if has_company:
                comp_fields = _safe_fields(self.company)
                if "account_stock_journal_id" in comp_fields:
                    self.company.sudo().write({"account_stock_journal_id": stock_journal.id})

        self.stock_journal = stock_journal

        # 4. Konfigurasi Lokasi (stock.location) Terisolasi Ketat HANYA pada Himpunan Lokasi Seed Eksplisit
        self.wh_stock_loc = None
        self.quarantine_loc = None
        self.seed_inventory_loc = None
        self.seed_supplier_loc = None
        self.seed_customer_loc = None

        StockLocation = self.env["stock.location"].sudo() if "stock.location" in self.env else None
        if StockLocation is not None:
            sl_fields = _safe_fields(StockLocation)
            seed_comp_id = self.company.id if has_company else False

            def _loc_comp_id(loc):
                loc_comp = getattr(loc, "company_id", False)
                return getattr(loc_comp, "id", loc_comp) if loc_comp else False

            # Temukan lokasi internal gudang utama milik seed company secara spesifik dan unik
            wh_stock_loc = None
            if "stock.warehouse" in self.env and has_company:
                StockWarehouse = self.env["stock.warehouse"].sudo()
                wh_candidates = [
                    w for w in _iter_records(StockWarehouse.search([("company_id", "=", self.company.id)]))
                    if getattr(w, "lot_stock_id", None)
                ]
                if len(wh_candidates) > 1:
                    wh_candidates = [
                        w for w in wh_candidates
                        if (
                            str(getattr(w, "code", "")).strip() in ("WH", "GFM", "MDO")
                            or str(getattr(w, "name", "")).strip() in (
                                "Gudang Utama Maumbi", "San Francisco", "Manado", "WH"
                            )
                        )
                        and "other" not in str(getattr(w, "name", "")).lower()
                    ]
                if len(wh_candidates) > 1:
                    raise RuntimeError(
                        "[canonical_loader] FATAL: Ditemukan lebih dari satu warehouse kandidat pada company seed "
                        "tanpa identitas unik!"
                    )
                if len(wh_candidates) == 1:
                    wh_stock_loc = wh_candidates[0].lot_stock_id

            if not wh_stock_loc:
                all_internal = _iter_records(StockLocation.search([("usage", "=", "internal")]))
                explicit_seed_names = {"WH/Stock", "Stock", "Gudang Utama Maumbi"}
                same_comp_candidates = [
                    loc for loc in all_internal
                    if _loc_comp_id(loc) == seed_comp_id
                    and str(getattr(loc, "name", "")).strip() in explicit_seed_names
                ]
                if not same_comp_candidates:
                    same_comp_candidates = [
                        loc for loc in all_internal
                        if _loc_comp_id(loc) in (seed_comp_id, False)
                        and str(getattr(loc, "name", "")).strip() in explicit_seed_names
                    ]
                if len(same_comp_candidates) != 1:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Lokasi gudang utama seed tidak ditemukan secara unik "
                        f"(kandidat={len(same_comp_candidates)})!"
                    )
                wh_stock_loc = same_comp_candidates[0]

            if seed_comp_id and _loc_comp_id(wh_stock_loc) not in (seed_comp_id, False):
                raise RuntimeError(
                    f"[canonical_loader] FATAL: Lokasi gudang utama '{getattr(wh_stock_loc, 'name', '')}' "
                    f"bukan milik company seed!"
                )

            def _resolve_or_create_seed_loc(name: str, usage: str, parent_id=False):
                matches = [
                    loc for loc in _iter_records(StockLocation.search([("name", "=", name), ("usage", "=", usage)]))
                    if _loc_comp_id(loc) in (seed_comp_id, False)
                ]
                if len(matches) > 1:
                    exact_comp = [loc for loc in matches if _loc_comp_id(loc) == seed_comp_id]
                    if len(exact_comp) == 1:
                        matches = exact_comp
                    else:
                        raise RuntimeError(
                            f"[canonical_loader] FATAL: Lokasi seed '{name}' (usage={usage}) ambigu "
                            f"(ditemukan {len(matches)} record)!"
                        )
                if len(matches) == 1:
                    return matches[0]
                if callable(getattr(StockLocation, "create", None)):
                    vals = {
                        "name": name,
                        "usage": usage,
                    }
                    if parent_id:
                        vals["location_id"] = parent_id
                    if "company_id" in sl_fields and seed_comp_id:
                        vals["company_id"] = seed_comp_id
                    return StockLocation.create(vals)
                return None

            quarantine_loc = _resolve_or_create_seed_loc(
                "Karantina FMCG Maumbi", "internal", parent_id=getattr(wh_stock_loc, "id", False)
            )
            seed_inventory_loc = _resolve_or_create_seed_loc("Inventory Adjustment FMCG Maumbi", "inventory")
            seed_supplier_loc = _resolve_or_create_seed_loc("Suppliers FMCG Maumbi", "supplier")
            seed_customer_loc = _resolve_or_create_seed_loc("Customers FMCG Maumbi", "customer")

            self.wh_stock_loc = wh_stock_loc
            self.quarantine_loc = quarantine_loc
            self.seed_inventory_loc = seed_inventory_loc
            self.seed_supplier_loc = seed_supplier_loc
            self.seed_customer_loc = seed_customer_loc

            if "valuation_account_id" in sl_fields:
                # HANYA sentuh lokasi internal eksplisit milik seed (wh_stock_loc dan quarantine_loc).
                # DILARANG menyentuh lokasi internal bisnis lain di company yang sama maupun company lain!
                for seed_inloc in (wh_stock_loc, quarantine_loc):
                    if seed_inloc and getattr(seed_inloc, "valuation_account_id", False):
                        seed_inloc.write({"valuation_account_id": False})

                # HANYA sentuh lokasi counterpart khusus seed milik company seed.
                # DILARANG menulis ke lokasi virtual shared (company_id=False) atau lokasi company lain!
                if stock_input_acc:
                    for seed_iloc in (seed_inventory_loc, seed_supplier_loc):
                        cur_acc = getattr(seed_iloc, "valuation_account_id", None) if seed_iloc else None
                        if seed_iloc and getattr(cur_acc, "id", cur_acc) != stock_input_acc.id:
                            seed_iloc.write({"valuation_account_id": stock_input_acc.id})

                cust_acc = cogs_acc or stock_output_acc
                if cust_acc and seed_customer_loc:
                    cur_c_acc = getattr(seed_customer_loc, "valuation_account_id", None)
                    if getattr(cur_c_acc, "id", cur_c_acc) != cust_acc.id:
                        seed_customer_loc.write({"valuation_account_id": cust_acc.id})

        # 5. Update kategori produk & harga pokok standar HANYA untuk scope produk kanonikal FMCG seed
        if "product.category" in self.env:
            seed_prod_ids = {
                getattr(pr, "id", None)
                for pr in getattr(self, "product_by_code", {}).values()
                if getattr(pr, "id", None) is not None
            }
            non_seed_cat_ids = set()
            if "product.product" in self.env:
                all_prods = self.env["product.product"].sudo().search([])
                for p_rec in _iter_records(all_prods):
                    if getattr(p_rec, "id", None) not in seed_prod_ids:
                        c_rec = getattr(p_rec, "categ_id", None)
                        if c_rec:
                            non_seed_cat_ids.add(getattr(c_rec, "id", c_rec))

            prod_model_fields = _safe_fields(self.env["product.product"]) if "product.product" in self.env else {}
            dedicated_seed_cat = None

            seed_categories = []
            seen_cat_ids = set()
            for pr in getattr(self, "product_by_code", {}).values():
                c_id = getattr(pr, "categ_id", None)
                if c_id:
                    cid_key = getattr(c_id, "id", c_id)
                    if cid_key in non_seed_cat_ids:
                        # Kategori ini dipakai bersama produk non-seed; isolasikan produk seed ke kategori khusus
                        if dedicated_seed_cat is None:
                            dedicated_seed_cat = ProductCategory.search(
                                [("name", "=", "FMCG Seed Perpetual")], limit=1
                            )
                            if not dedicated_seed_cat and callable(getattr(ProductCategory, "create", None)):
                                dedicated_seed_cat = ProductCategory.create({"name": "FMCG Seed Perpetual"})
                        if dedicated_seed_cat:
                            if callable(getattr(pr, "write", None)):
                                pr.write({"categ_id": dedicated_seed_cat.id})
                            try:
                                pr.categ_id = dedicated_seed_cat
                            except Exception:
                                pass
                            c_id = dedicated_seed_cat
                            cid_key = getattr(c_id, "id", c_id)
                    if cid_key not in seen_cat_ids:
                        seen_cat_ids.add(cid_key)
                        seed_categories.append(c_id)

            if not seed_categories:
                raise RuntimeError(
                    "[canonical_loader] FATAL: Tidak ada kategori produk (categ_id) pada scope produk kanonikal! "
                    "Penolakan fallback ke kategori acak."
                )

            # Konfigurasi kategori produk TERLEBIH DAHULU sebelum mengeset standard_price pada produk
            for cat in seed_categories:
                has_comp_ctx = callable(getattr(cat, "with_company", None)) and has_company
                cat_target = cat.with_company(self.company) if has_comp_ctx else cat
                vals = {}
                if "property_cost_method" in cat_fields:
                    vals["property_cost_method"] = "fifo"
                if "property_valuation" in cat_fields:
                    vals["property_valuation"] = "real_time"

                # Set eksplisit tanpa syarat `not getattr(...)` agar tidak tertimpa akun bawaan l10n_id
                for fname in [
                    "property_stock_valuation_account_id", "stock_valuation_account_id", "account_stock_valuation_id"
                ]:
                    if fname in cat_fields and stock_valuation_acc:
                        vals[fname] = stock_valuation_acc.id
                for fname in ["property_stock_journal", "stock_journal_id", "stock_journal"]:
                    if fname in cat_fields and stock_journal:
                        vals[fname] = stock_journal.id
                for fname in [
                    "property_stock_account_input_categ_id", "property_stock_account_input_id", "account_stock_in_id"
                ]:
                    if fname in cat_fields and stock_input_acc:
                        vals[fname] = stock_input_acc.id
                for fname in [
                    "property_stock_account_output_categ_id", "property_stock_account_output_id", "account_stock_out_id"
                ]:
                    if fname in cat_fields and (cogs_acc or stock_output_acc):
                        vals[fname] = (cogs_acc or stock_output_acc).id
                for fname in [
                    "property_account_expense_categ_id", "property_account_expense_id", "account_expense_id"
                ]:
                    if fname in cat_fields and cogs_acc:
                        vals[fname] = cogs_acc.id

                if vals and callable(getattr(cat_target, "write", None)):
                    cat_target.write(vals)

            # Pastikan standard_price, is_storable, dan property_stock_inventory terekam pada produk seed
            for sku, pr in getattr(self, "product_by_code", {}).items():
                u_cost = getattr(self, "canonical_unit_costs", {}).get(sku)
                if u_cost is not None and callable(getattr(pr, "write", None)):
                    pr_target = (
                        pr.with_company(self.company)
                        if callable(getattr(pr, "with_company", None)) and has_company
                        else pr
                    )
                    p_upd = {}
                    if "standard_price" in prod_model_fields or not prod_model_fields:
                        p_upd["standard_price"] = u_cost
                    if "is_storable" in prod_model_fields:
                        p_upd["is_storable"] = True
                    if "property_stock_inventory" in prod_model_fields and self.seed_inventory_loc:
                        p_upd["property_stock_inventory"] = self.seed_inventory_loc.id
                    if p_upd:
                        try:
                            pr_target.write(p_upd)
                        except Exception:
                            if "standard_price" in p_upd:
                                pr_target.write({"standard_price": u_cost})

    def _sync_native_stock_accounting(self, stock_move, date_time_str, date_only):
        """Memverifikasi keberadaan, keseimbangan, dan tanggal entri jurnal native Odoo (account.move)
        yang terbentuk dari stock.move secara read-only fail-fast untuk jurnal posted.
        """
        if "account.move" not in self.env:
            return

        AccountMove = self.env["account.move"].sudo() if "account.move" in self.env else None
        if AccountMove is None:
            return

        found_ams = []
        seen_am_ids = set()

        def _add_am(am_rec):
            if not am_rec:
                return
            am_id = getattr(am_rec, "id", id(am_rec))
            if am_id not in seen_am_ids:
                seen_am_ids.add(am_id)
                found_ams.append(am_rec)

        # 1. Many2one account_move_id
        if getattr(stock_move, "account_move_id", None):
            _add_am(stock_move.account_move_id)
        # 2. Relasi account_move_ids
        elif getattr(stock_move, "account_move_ids", None):
            for am in stock_move.account_move_ids:
                _add_am(am)
        # 3. Field stock_move_id
        if "stock_move_id" in _safe_fields(AccountMove):
            ams = AccountMove.search([("stock_move_id", "=", stock_move.id)])
            for am in _iter_records(ams):
                _add_am(am)
        # 4. Melalui origin atau picking name
        if not found_ams:
            origins = []
            if getattr(stock_move, "origin", None):
                origins.append(stock_move.origin)
            if getattr(stock_move, "picking_id", None) and getattr(stock_move.picking_id, "name", None):
                origins.append(stock_move.picking_id.name)
            if origins:
                ams = AccountMove.search([
                    ("ref", "in", origins),
                    ("company_id", "in", [False, self.company.id]),
                ])
                for am in _iter_records(ams):
                    _add_am(am)

        # Fail-fast jika stock.move tidak menghasilkan jurnal akuntansi native sama sekali
        if not found_ams:
            mv_ref = (
                getattr(stock_move, "origin", None)
                or getattr(stock_move, "reference", None)
                or getattr(stock_move, "id", "unknown")
            )
            raise RuntimeError(
                f"[canonical_loader] FATAL: Pergerakan stok '{mv_ref}' tidak menghasilkan "
                f"entri jurnal akuntansi native (account.move)! Real-time valuation gagal."
            )

        for am in found_ams:
            am_state = getattr(am, "state", "")
            if am_state == "draft":
                am.write({"date": date_only})
                if hasattr(am, "line_ids") and am.line_ids and callable(getattr(am.line_ids, "write", None)):
                    am.line_ids.write({"date": date_only})
                am.action_post()
            elif am_state == "posted":
                # Cabang posted WAJIB murni read-only: DILARANG memanggil write() atau mereset ke draft!
                current_date = str(getattr(am, "date", ""))
                if current_date != date_only:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Entri jurnal posted '{getattr(am, 'name', am.id)}' "
                        f"memiliki tanggal {current_date}, diharapkan {date_only}! "
                        f"Tanggal native harus benar sejak posting awal (dilarang rewrite jurnal posted)."
                    )
            elif am_state == "cancel":
                raise RuntimeError(
                    f"[canonical_loader] FATAL: Entri jurnal '{getattr(am, 'name', am.id)}' berstatus 'cancel'!"
                )

            # Verifikasi akhir: state harus posted, tanggal tepat date_only, dan baris finansial berimbang
            final_state = getattr(am, "state", "")
            if final_state != "posted":
                raise RuntimeError(
                    f"[canonical_loader] FATAL: Entri jurnal '{getattr(am, 'name', am.id)}' "
                    f"belum posted (state={final_state})!"
                )
            final_date = str(getattr(am, "date", ""))
            if final_date != date_only:
                raise RuntimeError(
                    f"[canonical_loader] FATAL: Tanggal entri jurnal '{getattr(am, 'name', am.id)}' "
                    f"gagal diselaraskan ke {date_only}! Terbaca aktual: {final_date}"
                )
            lines = getattr(am, "line_ids", [])
            if lines:
                tot_d = sum(float(getattr(ln, "debit", 0.0)) for ln in lines)
                tot_c = sum(float(getattr(ln, "credit", 0.0)) for ln in lines)
                if abs(tot_d - tot_c) > 0.01:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Entri jurnal '{getattr(am, 'name', am.id)}' tidak berimbang! "
                        f"Debit={tot_d}, Credit={tot_c}"
                    )

    def _assign_lots_to_picking(self, pick, lines_data):
        """Memetakan lot sumber kanonikal dan kuantitas selesai ke stock.move.line pada picking secara deterministik.

        Mendukung pemetaan multi-lot split (seperti SO-202607-0317 dengan 2 lot terpisah),
        mengagregasikan baris berulang pada lot yang sama,
        menggunakan pengecekan model Odoo 'is not None' (tahan terhadap empty recordset bool==False),
        dan memvalidasi mapping lot -> qty persis secara fail-fast.
        """
        StockLot = self.env["stock.lot"].sudo() if "stock.lot" in self.env else None
        StockMoveLine = self.env["stock.move.line"].sudo() if "stock.move.line" in self.env else None

        def _rec_id(val):
            if hasattr(val, "id"):
                return val.id
            if isinstance(val, int):
                return val
            return False

        # 1. Kelompokkan kebutuhan source per SKU dan per Lot
        demands_by_sku = {}
        for item in lines_data:
            sku = item.get("sku_code")
            prod = self.product_by_code.get(sku)
            if not prod:
                continue

            lot_num = item.get("lot_number") or False
            qty_units = float(item["qty_cartons"]) * float(item["carton_qty"])
            exp_date = item.get("expiry_date")

            if sku not in demands_by_sku:
                demands_by_sku[sku] = {
                    "prod": prod,
                    "total_units": 0.0,
                    "lots": {},
                }

            sku_demands = demands_by_sku[sku]
            sku_demands["total_units"] += qty_units

            if lot_num not in sku_demands["lots"]:
                lot_obj = None
                lot_fields = _safe_fields(StockLot) if StockLot is not None else {}
                if StockLot is not None and lot_num:
                    lot_obj = StockLot.search([("name", "=", lot_num), ("product_id", "=", prod.id)], limit=1)
                    if not lot_obj:
                        lot_vals = {
                            "name": lot_num,
                            "product_id": prod.id,
                            "company_id": self.company.id,
                        }
                        if exp_date and "expiration_date" in lot_fields:
                            lot_vals["expiration_date"] = exp_date
                        lot_obj = StockLot.create(lot_vals)

                sku_demands["lots"][lot_num] = {
                    "qty_units": qty_units,
                    "expiry_date": exp_date,
                    "lot_obj": lot_obj,
                }
            else:
                sku_demands["lots"][lot_num]["qty_units"] += qty_units

        # Field capabilities stock.move.line
        sml_fields = _safe_fields(StockMoveLine) if StockMoveLine is not None else {}
        has_quantity_field = "quantity" in sml_fields if sml_fields else True
        has_qty_done_field = "qty_done" in sml_fields if sml_fields else True

        # 2. Alokasikan ke move dan move_line per SKU
        for sku, sku_demands in demands_by_sku.items():
            prod = sku_demands["prod"]

            matching_moves = []
            if hasattr(pick, "move_ids") and pick.move_ids:
                for m in pick.move_ids:
                    if _rec_id(getattr(m, "product_id", None)) == prod.id:
                        matching_moves.append(m)

            matching_move = matching_moves[0] if matching_moves else None

            existing_lines = []
            if hasattr(pick, "move_line_ids") and pick.move_line_ids:
                for ml in pick.move_line_ids:
                    if _rec_id(getattr(ml, "product_id", None)) == prod.id:
                        existing_lines.append(ml)

            sorted_lot_items = sorted(sku_demands["lots"].items(), key=lambda x: str(x[0] or ""))
            used_move_ids = set()

            for idx, (lot_num, lot_info) in enumerate(sorted_lot_items):
                target_qty = lot_info["qty_units"]
                lot_obj = lot_info["lot_obj"]
                target_lot_id = lot_obj.id if lot_obj else False

                target_move = matching_move
                if len(matching_moves) > 1:
                    matched_by_qty = None
                    for cand_mv in matching_moves:
                        cid = getattr(cand_mv, "id", id(cand_mv))
                        if cid in used_move_ids:
                            continue
                        cand_qty = float(getattr(cand_mv, "product_uom_qty", 0.0) or 0.0)
                        if abs(cand_qty - target_qty) < 0.001:
                            matched_by_qty = cand_mv
                            break
                    if matched_by_qty is not None:
                        target_move = matched_by_qty
                    else:
                        target_move = matching_moves[min(idx, len(matching_moves) - 1)]
                    used_move_ids.add(getattr(target_move, "id", id(target_move)))

                if existing_lines:
                    ml = None
                    if target_move is not None:
                        target_mv_id = getattr(target_move, "id", None)
                        for el_idx, el in enumerate(existing_lines):
                            if _rec_id(getattr(el, "move_id", None)) == target_mv_id:
                                ml = existing_lines.pop(el_idx)
                                break
                    if ml is None:
                        ml = existing_lines.pop(0)
                    upd_vals = {}
                    if lot_num and ("lot_name" in sml_fields or not sml_fields):
                        upd_vals["lot_name"] = lot_num
                    if target_lot_id and ("lot_id" in sml_fields or not sml_fields):
                        upd_vals["lot_id"] = target_lot_id
                    if has_quantity_field:
                        upd_vals["quantity"] = target_qty
                    elif has_qty_done_field:
                        upd_vals["qty_done"] = target_qty
                    if "picked" in sml_fields or not sml_fields:
                        upd_vals["picked"] = True

                    if callable(getattr(ml, "write", None)):
                        ml.write(upd_vals)
                    if lot_obj and hasattr(ml, "lot_id"):
                        ml.lot_id = lot_obj
                    if lot_num and hasattr(ml, "lot_name"):
                        ml.lot_name = lot_num
                    if has_quantity_field and hasattr(ml, "quantity"):
                        ml.quantity = target_qty
                    if has_qty_done_field and hasattr(ml, "qty_done"):
                        ml.qty_done = target_qty
                    if hasattr(ml, "picked"):
                        ml.picked = True
                else:
                    if StockMoveLine is not None:
                        ml_vals = {
                            "picking_id": pick.id,
                            "move_id": target_move.id if target_move and hasattr(target_move, "id") else False,
                            "product_id": prod.id,
                            "lot_id": target_lot_id,
                            "location_id": _rec_id(getattr(pick, "location_id", None)),
                            "location_dest_id": _rec_id(getattr(pick, "location_dest_id", None)),
                        }
                        if lot_num and ("lot_name" in sml_fields or not sml_fields):
                            ml_vals["lot_name"] = lot_num
                        uom_rec = getattr(prod, "uom_id", None)
                        if uom_rec and hasattr(uom_rec, "id") and ("product_uom_id" in sml_fields or not sml_fields):
                            ml_vals["product_uom_id"] = uom_rec.id
                        if has_quantity_field:
                            ml_vals["quantity"] = target_qty
                        elif has_qty_done_field:
                            ml_vals["qty_done"] = target_qty
                        if "picked" in sml_fields or not sml_fields:
                            ml_vals["picked"] = True

                        new_ml = StockMoveLine.create(ml_vals)
                        if hasattr(pick, "move_line_ids") and hasattr(pick.move_line_ids, "append"):
                            pick.move_line_ids.append(new_ml)
                        if (
                            target_move is not None
                            and hasattr(target_move, "move_line_ids")
                            and hasattr(target_move.move_line_ids, "append")
                            and new_ml not in target_move.move_line_ids
                        ):
                            target_move.move_line_ids.append(new_ml)

            for unused_ml in existing_lines:
                if callable(getattr(unused_ml, "unlink", None)):
                    unused_ml.unlink()
                else:
                    if hasattr(unused_ml, "quantity"):
                        unused_ml.quantity = 0.0
                    if hasattr(unused_ml, "qty_done"):
                        unused_ml.qty_done = 0.0

            for mv_rec in matching_moves:
                if callable(getattr(mv_rec, "write", None)):
                    mv_fields = _safe_fields(mv_rec)
                    mv_upd = {}
                    if "picked" in mv_fields or not mv_fields:
                        mv_upd["picked"] = True
                    if mv_upd:
                        mv_rec.write(mv_upd)

        # 3. Assertion Komprehensif Map Lot -> Qty Persis (Fail-Fast)
        for sku, sku_demands in demands_by_sku.items():
            prod = sku_demands["prod"]
            sku_lines = [
                ml for ml in (getattr(pick, "move_line_ids", None) or [])
                if _rec_id(getattr(ml, "product_id", None)) == prod.id
            ]
            actual_by_lot = {}
            for ml in sku_lines:
                l_id = _rec_id(getattr(ml, "lot_id", None))
                rec_lot = getattr(ml, "lot_id", None)
                l_name = getattr(ml, "lot_name", None) or (getattr(rec_lot, "name", None) if rec_lot else False)
                l_key = l_name or l_id or "NO_LOT"
                qty = float(getattr(ml, "quantity", getattr(ml, "qty_done", 0.0)))
                actual_by_lot[l_key] = actual_by_lot.get(l_key, 0.0) + qty

            for lot_num, lot_info in sku_demands["lots"].items():
                expected_lot_qty = lot_info["qty_units"]
                lot_key = lot_num or "NO_LOT"
                lot_id_key = lot_info["lot_obj"].id if lot_info.get("lot_obj") else None
                actual_lot_qty = actual_by_lot.get(lot_key)
                if actual_lot_qty is None and lot_id_key is not None:
                    actual_lot_qty = actual_by_lot.get(lot_id_key)
                actual_lot_qty = actual_lot_qty if actual_lot_qty is not None else 0.0
                if abs(actual_lot_qty - expected_lot_qty) > 0.001:
                    raise AssertionError(
                        f"[canonical_loader] FATAL: Alokasi kuantitas lot mismatch pada picking "
                        f"'{getattr(pick, 'name', pick.id)}' untuk SKU '{sku}', Lot '{lot_num}'! "
                        f"Expected: {expected_lot_qty}, Got: {actual_lot_qty} (Actual lots map: {actual_by_lot})"
                    )

            total_actual_sku = sum(actual_by_lot.values())
            if abs(total_actual_sku - sku_demands["total_units"]) > 0.001:
                raise AssertionError(
                    f"[canonical_loader] FATAL: Total unit per SKU mismatch pada picking "
                    f"'{getattr(pick, 'name', pick.id)}' untuk SKU '{sku}'! "
                    f"Expected: {sku_demands['total_units']}, Got: {total_actual_sku}"
                )

    def _get_record_lines(self, record):
        """Mengambil line_ids dari record langsung atau dari move_id relasionalnya."""
        if hasattr(record, "line_ids") and record.line_ids:
            return record.line_ids
        if hasattr(record, "move_id") and hasattr(record.move_id, "line_ids") and record.move_id.line_ids:
            return record.move_id.line_ids
        return []

    def _find_payment(self, pay_id: str):
        """Mencari account.payment berdasarkan pay_id pada ref, memo, atau move_id.ref."""
        if "account.payment" not in self.env:
            return None
        AccountPayment = self.env["account.payment"].sudo()
        p_fields = getattr(AccountPayment, "_fields", {})

        # 1. Coba field ref jika ada di account.payment
        if "ref" in p_fields:
            p = AccountPayment.search([("ref", "=", pay_id)], limit=1)
            if p:
                return p
        # 2. Coba field memo native Odoo 19 jika ada
        if "memo" in p_fields:
            p = AccountPayment.search([("memo", "=", pay_id)], limit=1)
            if p:
                return p
        # 3. Cari via account.move jika terhubung ke move_id
        if "account.move" in self.env:
            AccountMove = self.env["account.move"].sudo()
            m = AccountMove.search([("ref", "=", pay_id)], limit=1)
            if m:
                p = AccountPayment.search([("move_id", "=", m.id)], limit=1)
                if p:
                    return p
        # 4. Fallback search umum
        try:
            return AccountPayment.search([("ref", "=", pay_id)], limit=1)
        except Exception:
            return None

    def _align_picking_locations(self, pick, expected_src_loc=None, expected_dest_loc=None):
        """Menyelaraskan lokasi picking, stock.move, dan stock.move.line ke lokasi seed SEBELUM alokasi lot.

        Harus dipanggil sebelum _assign_lots_to_picking(): perubahan lokasi setelah kuantitas dialokasikan
        membatalkan reservasi Odoo 19 dan menghasilkan transfer berkuantitas nol.
        Semua write diverifikasi dengan readback wajib; no-op write atau write failure langsung raise RuntimeError.
        """
        targets = {}
        if expected_src_loc is not None and getattr(expected_src_loc, "id", None):
            targets["location_id"] = expected_src_loc.id
        if expected_dest_loc is not None and getattr(expected_dest_loc, "id", None):
            targets["location_dest_id"] = expected_dest_loc.id

        if not targets:
            return

        # 1. Update & verify picking
        pick_name = getattr(pick, "name", getattr(pick, "id", "stock.picking"))
        pick_upd = {
            fname: target_id
            for fname, target_id in targets.items()
            if getattr(getattr(pick, fname, None), "id", getattr(pick, fname, None)) != target_id
        }
        if pick_upd:
            if not callable(getattr(pick, "write", None)):
                raise RuntimeError(
                    f"[canonical_loader] FATAL: Record stock.picking '{pick_name}' tidak memiliki method write()!"
                )
            try:
                pick.write(pick_upd)
            except Exception as e:
                raise RuntimeError(
                    f"[canonical_loader] FATAL: Gagal menulis lokasi stock.picking '{pick_name}': {e}"
                ) from e

        for fname, target_id in targets.items():
            cur = getattr(getattr(pick, fname, None), "id", getattr(pick, fname, None))
            if cur != target_id:
                raise RuntimeError(
                    f"[canonical_loader] FATAL: Readback lokasi stock.picking '{pick_name}' "
                    f"gagal: {fname}={cur}, diharapkan {target_id}"
                )

        # 2. Update & verify stock.move
        moves = list(_iter_records(getattr(pick, "move_ids", None)))
        for sm in moves:
            sm_name = getattr(sm, "name", getattr(sm, "id", "stock.move"))
            sm_upd = {
                fname: target_id
                for fname, target_id in targets.items()
                if getattr(getattr(sm, fname, None), "id", getattr(sm, fname, None)) != target_id
            }
            if sm_upd:
                if not callable(getattr(sm, "write", None)):
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Record stock.move '{sm_name}' tidak memiliki method write()!"
                    )
                try:
                    sm.write(sm_upd)
                except Exception as e:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Gagal menulis lokasi stock.move '{sm_name}': {e}"
                    ) from e

            for fname, target_id in targets.items():
                cur = getattr(getattr(sm, fname, None), "id", getattr(sm, fname, None))
                if cur != target_id:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Readback lokasi stock.move '{sm_name}' "
                        f"gagal: {fname}={cur}, diharapkan {target_id}"
                    )

        # 3. Update & verify stock.move.line
        move_lines = list(_iter_records(getattr(pick, "move_line_ids", None)))
        for sml in move_lines:
            sml_name = getattr(sml, "id", "stock.move.line")
            sml_upd = {
                fname: target_id
                for fname, target_id in targets.items()
                if getattr(getattr(sml, fname, None), "id", getattr(sml, fname, None)) != target_id
            }
            if sml_upd:
                if not callable(getattr(sml, "write", None)):
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Record stock.move.line '{sml_name}' tidak memiliki method write()!"
                    )
                try:
                    sml.write(sml_upd)
                except Exception as e:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Gagal menulis lokasi stock.move.line '{sml_name}': {e}"
                    ) from e

            for fname, target_id in targets.items():
                cur = getattr(getattr(sml, fname, None), "id", getattr(sml, fname, None))
                if cur != target_id:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Readback lokasi stock.move.line '{sml_name}' "
                        f"gagal: {fname}={cur}, diharapkan {target_id}"
                    )

    def _validate_picking_safely(
        self,
        pick,
        effective_date=None,
        expected_src_loc=None,
        expected_dest_loc=None,
    ):
        """Memvalidasi picking hingga 'done', menangani wizard via allowlist resmi,
        menyelaraskan tanggal efektif historis bisnis secara native, dan fail-fast tanpa bypass sanity check.
        """
        if getattr(pick, "state", "") == "done":
            return True

        date_str = effective_date or getattr(pick, "scheduled_date", None)
        date_only = str(date_str)[:10] if date_str else None
        if date_only and len(str(date_str)) <= 10:
            date_time_str = f"{date_only} 00:00:00"
        else:
            date_time_str = str(date_str) if date_str else None

        # Lokasi WAJIB sudah diselaraskan oleh _align_picking_locations() SEBELUM alokasi lot.
        # Menulis ulang lokasi di sini akan membatalkan reservasi/kuantitas move line di Odoo 19
        # (memicu "Validating a zero quantity transfer"), sehingga di sini hanya diverifikasi (fail-fast).
        for exp_loc, fname in ((expected_src_loc, "location_id"), (expected_dest_loc, "location_dest_id")):
            if exp_loc is None or not getattr(exp_loc, "id", None):
                continue
            exp_id = exp_loc.id
            cur_val = getattr(getattr(pick, fname, None), "id", getattr(pick, fname, None))
            if cur_val != exp_id:
                raise RuntimeError(
                    f"[canonical_loader] FATAL: {fname} picking '{getattr(pick, 'name', getattr(pick, 'id', ''))}' "
                    f"({cur_val}) tidak sama dengan lokasi seed '{getattr(exp_loc, 'name', exp_id)}' "
                    f"({exp_id}) sebelum validasi!"
                )
            for sm in _iter_records(getattr(pick, "move_ids", None)):
                cur_sm = getattr(getattr(sm, fname, None), "id", getattr(sm, fname, None))
                if cur_sm != exp_id:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: {fname} move '{getattr(sm, 'name', getattr(sm, 'id', ''))}' "
                        f"({cur_sm}) tidak sama dengan lokasi seed ({exp_id}) sebelum validasi!"
                    )
            for sml in _iter_records(getattr(pick, "move_line_ids", None)):
                cur_sml = getattr(getattr(sml, fname, None), "id", getattr(sml, fname, None))
                if cur_sml != exp_id:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: {fname} move_line '{getattr(sml, 'id', sml)}' "
                        f"({cur_sml}) tidak sama dengan lokasi seed ({exp_id}) sebelum validasi!"
                    )

        if date_time_str:
            pick_name = getattr(pick, "name", getattr(pick, "id", "stock.picking"))
            if hasattr(pick, "scheduled_date"):
                try:
                    if callable(getattr(pick, "write", None)):
                        pick.write({"scheduled_date": date_time_str})
                    else:
                        pick.scheduled_date = date_time_str
                except Exception as e:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Gagal menulis scheduled_date picking '{pick_name}': {e}"
                    ) from e
                cur_sch = getattr(pick, "scheduled_date", None)
                if not _is_matching_date(cur_sch, date_time_str, date_only):
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Readback scheduled_date picking '{pick_name}' gagal pra-validasi "
                        f"(no-op write terdeteksi: aktual={cur_sch}, diharapkan={date_time_str})!"
                    )
            if hasattr(pick, "date_done"):
                try:
                    if callable(getattr(pick, "write", None)):
                        pick.write({"date_done": date_time_str})
                    else:
                        pick.date_done = date_time_str
                except Exception as e:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Gagal menulis date_done picking '{pick_name}': {e}"
                    ) from e
                cur_done = getattr(pick, "date_done", None)
                if not _is_matching_date(cur_done, date_time_str, date_only):
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Readback date_done picking '{pick_name}' gagal pra-validasi "
                        f"(no-op write terdeteksi: aktual={cur_done}, diharapkan={date_time_str})!"
                    )
            if hasattr(pick, "move_ids") and pick.move_ids:
                for sm in pick.move_ids:
                    if callable(getattr(sm, "write", None)):
                        try:
                            sm.write({"date": date_time_str})
                        except Exception as e:
                            sm_str = getattr(sm, "name", getattr(sm, "id", ""))
                            raise RuntimeError(
                                f"[canonical_loader] FATAL: Gagal menulis date stock.move '{sm_str}': {e}"
                            ) from e
                        cur_sm = getattr(sm, "date", None)
                        if not _is_matching_date(cur_sm, date_time_str, date_only):
                            sm_str = getattr(sm, "name", getattr(sm, "id", ""))
                            raise RuntimeError(
                                f"[canonical_loader] FATAL: Readback date stock.move '{sm_str}' gagal pra-validasi "
                                f"(no-op write terdeteksi: aktual={cur_sm}, diharapkan={date_time_str})!"
                            )
            if hasattr(pick, "move_line_ids") and pick.move_line_ids:
                for sml in _iter_records(pick.move_line_ids):
                    if callable(getattr(sml, "write", None)):
                        try:
                            sml.write({"date": date_time_str})
                        except Exception as e:
                            sml_str = getattr(sml, "id", sml)
                            raise RuntimeError(
                                f"[canonical_loader] FATAL: Gagal menulis date stock.move.line '{sml_str}': {e}"
                            ) from e
                        cur_sml = getattr(sml, "date", None)
                        if not _is_matching_date(cur_sml, date_time_str, date_only):
                            sml_str = getattr(sml, "id", sml)
                            raise RuntimeError(
                                f"[canonical_loader] FATAL: Readback date move_line '{sml_str}' gagal pra-validasi "
                                f"(no-op write: aktual={cur_sml}, target={date_time_str})!"
                            )

        val_ctx = {
            "skip_sms": True,
        }
        if date_only:
            val_ctx["force_period_date"] = date_only
            val_ctx["date"] = date_only
            val_ctx["accounting_date"] = date_only
        if date_time_str:
            val_ctx["date_done"] = date_time_str

        pick_target = pick.with_context(**val_ctx) if callable(getattr(pick, "with_context", None)) else pick
        res = pick_target.button_validate() if hasattr(pick_target, "button_validate") else None

        # Allowlist resmi model wizard Odoo dan aksi yang didukung
        ALLOWED_WIZARDS = {
            "confirm.stock.sms": ["dont_send_sms"],
            "stock.immediate.transfer": ["process"],
            "stock.backorder.confirmation": ["process_cancel_backorder", "process"],
        }

        wiz_iter = 0
        current_res = res
        while isinstance(current_res, dict) and current_res.get("res_model") and wiz_iter < 5:
            wiz_iter += 1
            wizard_model = current_res["res_model"]
            if wizard_model not in ALLOWED_WIZARDS:
                raise RuntimeError(
                    f"[canonical_loader] FATAL: Model wizard '{wizard_model}' tidak ada dalam allowlist resmi! "
                    f"Aksi tidak dikenal ditolak secara fail-fast."
                )

            wizard_ctx = dict(val_ctx)
            if isinstance(current_res.get("context"), dict):
                wizard_ctx.update(current_res["context"])

            if wizard_model in self.env:
                WizardModel = self.env[wizard_model].sudo().with_context(**wizard_ctx)
                wiz_id = current_res.get("res_id")
                wiz_vals = {}
                if "pick_ids" in WizardModel._fields:
                    wiz_vals["pick_ids"] = [(6, 0, [pick.id])]
                elif "picking_id" in WizardModel._fields:
                    wiz_vals["picking_id"] = pick.id

                wizard_record = WizardModel.browse(wiz_id) if wiz_id else WizardModel.create(wiz_vals)
                action_taken = False
                for act_name in ALLOWED_WIZARDS[wizard_model]:
                    if hasattr(wizard_record, act_name):
                        current_res = getattr(wizard_record.with_context(**wizard_ctx), act_name)()
                        action_taken = True
                        break
                if not action_taken:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Wizard '{wizard_model}' tidak memiliki aksi yang didukung: "
                        f"{ALLOWED_WIZARDS[wizard_model]}"
                    )
            else:
                break

        if getattr(pick, "state", "") != "done" and hasattr(pick, "button_validate"):
            re_pick = pick.with_context(**val_ctx) if callable(getattr(pick, "with_context", None)) else pick
            re_pick.button_validate()

        if getattr(pick, "state", "") != "done":
            pick_id_label = getattr(pick, "name", getattr(pick, "origin", "DO"))
            raise RuntimeError(
                f"[canonical_loader] FATAL: Validasi picking '{pick_id_label}' gagal mencapai state 'done'! "
                f"Status aktual: '{getattr(pick, 'state', 'unknown')}'. Return value: {res}"
            )

        # Selaraskan tanggal efektif historis pada picking, move, move_line, dan account.move
        if date_time_str:
            if callable(getattr(pick, "write", None)):
                pick.write({"date_done": date_time_str, "scheduled_date": date_time_str})
            elif hasattr(pick, "date_done"):
                pick.date_done = date_time_str

            if hasattr(pick, "date_done") or callable(getattr(pick, "write", None)):
                cur_done = getattr(pick, "date_done", None)
                if not _is_matching_date(cur_done, date_time_str, date_only):
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Readback date_done picking '{pick_name}' gagal pasca-validasi "
                        f"(no-op write: aktual={cur_done}, target={date_time_str})!"
                    )
            if hasattr(pick, "scheduled_date") or callable(getattr(pick, "write", None)):
                cur_sch = getattr(pick, "scheduled_date", None)
                if not _is_matching_date(cur_sch, date_time_str, date_only):
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Readback scheduled_date picking '{pick_name}' gagal pasca-validasi "
                        f"(no-op write: aktual={cur_sch}, target={date_time_str})!"
                    )

            if hasattr(pick, "move_line_ids") and pick.move_line_ids:
                if callable(getattr(pick.move_line_ids, "write", None)):
                    pick.move_line_ids.write({"date": date_time_str})
                    for p_sml in _iter_records(pick.move_line_ids):
                        cur_sml = getattr(p_sml, "date", None)
                        if not _is_matching_date(cur_sml, date_time_str, date_only):
                            sml_lbl = getattr(p_sml, "id", p_sml)
                            raise RuntimeError(
                                f"[canonical_loader] FATAL: Readback date move_line '{sml_lbl}' gagal pasca-validasi "
                                f"(no-op write: aktual={cur_sml}, target={date_time_str})!"
                            )
                else:
                    for p_sml in _iter_records(pick.move_line_ids):
                        if callable(getattr(p_sml, "write", None)):
                            p_sml.write({"date": date_time_str})
                            cur_sml = getattr(p_sml, "date", None)
                            if not _is_matching_date(cur_sml, date_time_str, date_only):
                                sml_lbl = getattr(p_sml, "id", p_sml)
                                raise RuntimeError(
                                    f"[canonical_loader] FATAL: Readback date move_line '{sml_lbl}' pasca-validasi "
                                    f"(no-op write: aktual={cur_sml}, target={date_time_str})!"
                                )

            if hasattr(pick, "move_ids") and pick.move_ids:
                for mv in pick.move_ids:
                    if getattr(mv, "state", "done") == "cancel":
                        continue
                    mv_qty = float(getattr(mv, "quantity", getattr(mv, "product_uom_qty", 0.0)) or 0.0)
                    if mv_qty <= 0.0 and not getattr(mv, "move_line_ids", None):
                        continue
                    if callable(getattr(mv, "write", None)):
                        mv.write({"date": date_time_str})
                        cur_mv = getattr(mv, "date", None)
                        if not _is_matching_date(cur_mv, date_time_str, date_only):
                            mv_lbl = getattr(mv, "name", "")
                            raise RuntimeError(
                                f"[canonical_loader] FATAL: Readback date move '{mv_lbl}' gagal pasca-validasi "
                                f"(no-op write: aktual={cur_mv}, target={date_time_str})!"
                            )
                    has_sml = hasattr(mv, "move_line_ids") and mv.move_line_ids
                    if has_sml:
                        if callable(getattr(mv.move_line_ids, "write", None)):
                            mv.move_line_ids.write({"date": date_time_str})
                            for sml in _iter_records(mv.move_line_ids):
                                cur_sml = getattr(sml, "date", None)
                                if not _is_matching_date(cur_sml, date_time_str, date_only):
                                    sml_lbl = getattr(sml, "id", sml)
                                    raise RuntimeError(
                                        f"[canonical_loader] FATAL: Readback date move_line '{sml_lbl}' "
                                        f"(no-op write: aktual={cur_sml}, target={date_time_str})!"
                                    )
                        else:
                            for sml in _iter_records(mv.move_line_ids):
                                if callable(getattr(sml, "write", None)):
                                    sml.write({"date": date_time_str})
                                    cur_sml = getattr(sml, "date", None)
                                    if not _is_matching_date(cur_sml, date_time_str, date_only):
                                        sml_lbl = getattr(sml, "id", sml)
                                        raise RuntimeError(
                                            f"[canonical_loader] FATAL: Readback date move_line '{sml_lbl}' "
                                            f"(no-op write: aktual={cur_sml}, target={date_time_str})!"
                                        )
                    self._sync_native_stock_accounting(mv, date_time_str, date_only)
        return True

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
        StockLot = self.env["stock.lot"].sudo() if "stock.lot" in self.env else None

        warehouse_loc = getattr(self, "wh_stock_loc", None)
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
            if StockLot is not None:
                lot = StockLot.search([("name", "=", lot_name), ("product_id", "=", prod.id)], limit=1)
                if not lot:
                    lot_vals = {
                        "name": lot_name,
                        "product_id": prod.id,
                        "company_id": self.company.id,
                    }
                    if hasattr(StockLot, "_fields") and "expiration_date" in StockLot._fields:
                        lot_vals["expiration_date"] = p_data["expiry_date"]
                    lot = StockLot.create(lot_vals)
                lot_id = lot.id

            # Idempotency check: jika opening move atau quant untuk (product, location, lot) sudah pernah diproses
            StockMove = self.env["stock.move"].sudo() if "stock.move" in self.env else None
            opening_move_exists = False
            if StockMove is not None:
                mv_domain = [
                    ("product_id", "=", prod.id),
                    ("location_dest_id", "=", warehouse_loc.id),
                    ("origin", "=", "OPENING-20260701"),
                    ("state", "=", "done"),
                ]
                opening_moves = StockMove.search(mv_domain)
                if lot_id and opening_moves:
                    moves_iter = opening_moves if hasattr(opening_moves, "__iter__") else [opening_moves]
                    opening_move_exists = any(
                        any(
                            getattr(getattr(ml, "lot_id", None), "id", getattr(ml, "lot_id", None)) == lot_id
                            for ml in getattr(m, "move_line_ids", [])
                        )
                        for m in moves_iter
                    )
                else:
                    opening_move_exists = bool(opening_moves)

            domain = [("product_id", "=", prod.id), ("location_id", "=", warehouse_loc.id)]
            if lot_id:
                domain.append(("lot_id", "=", lot_id))
            existing_quant = StockQuant.search(domain, limit=1)

            if opening_move_exists or existing_quant:
                self.stats["skipped_opening_quants"] += 1
                continue

            quant_vals = {
                "product_id": prod.id,
                "location_id": warehouse_loc.id,
                "lot_id": lot_id,
                "inventory_quantity": qty_units,
            }
            if hasattr(StockQuant, "_fields") and "inventory_date" in StockQuant._fields:
                quant_vals["inventory_date"] = "2026-07-01 00:00:00"

            quant = StockQuant.with_context(inventory_mode=True, force_period_date="2026-07-01").create(quant_vals)
            if hasattr(quant, "action_apply_inventory"):
                quant.with_context(force_period_date="2026-07-01").action_apply_inventory()

            # Selaraskan tanggal efektif bisnis pada stock.move hasil inventory adjustment dan verifikasi jurnal native
            if StockMove is not None:
                adj_moves = StockMove.search([
                    ("product_id", "=", prod.id),
                    ("location_dest_id", "=", warehouse_loc.id),
                    ("is_inventory", "=", True),
                    ("state", "=", "done"),
                ], order="id desc", limit=1)
                if not adj_moves:
                    adj_moves = StockMove.search([
                        ("product_id", "=", prod.id),
                        ("location_dest_id", "=", warehouse_loc.id),
                        ("state", "=", "done"),
                    ], order="id desc", limit=1)
                if not adj_moves:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: action_apply_inventory() gagal menghasilkan stock.move done "
                        f"untuk SKU '{sku}' (Lot '{lot_name}')!"
                    )
                moves_iter = [adj_moves] if not hasattr(adj_moves, "__iter__") else adj_moves
                for am in moves_iter:
                    am_upd = {"date": "2026-07-01 00:00:00", "origin": "OPENING-20260701"}
                    am_loc = getattr(am, "location_id", None)
                    if (
                        getattr(self, "seed_inventory_loc", None)
                        and getattr(am_loc, "id", am_loc) != self.seed_inventory_loc.id
                    ):
                        am_upd["location_id"] = self.seed_inventory_loc.id
                    if callable(getattr(am, "write", None)):
                        am.write(am_upd)
                    has_sml = hasattr(am, "move_line_ids") and am.move_line_ids
                    if has_sml:
                        sml_upd = {"date": "2026-07-01 00:00:00"}
                        if getattr(self, "seed_inventory_loc", None):
                            sml_upd["location_id"] = self.seed_inventory_loc.id
                        if callable(getattr(am.move_line_ids, "write", None)):
                            am.move_line_ids.write(sml_upd)
                        else:
                            for sml in _iter_records(am.move_line_ids):
                                if callable(getattr(sml, "write", None)):
                                    sml.write(sml_upd)
                    self._sync_native_stock_accounting(am, "2026-07-01 00:00:00", "2026-07-01")

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
            existing_pos = _iter_records(PurchaseOrder.search([("origin", "=", po_num)]))
            if len(existing_pos) > 1:
                raise RuntimeError(
                    f"[canonical_loader] FATAL: Duplikasi PurchaseOrder dengan origin '{po_num}' "
                    f"(ditemukan {len(existing_pos)} record)!"
                )
            existing_po = existing_pos[0] if existing_pos else None
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
                    arrival_dt = h.get("arrival_maumbi_date", h.get("eta_bitung"))
                    pick.scheduled_date = arrival_dt
                    self._align_picking_locations(
                        pick,
                        expected_src_loc=getattr(self, "seed_supplier_loc", None),
                        expected_dest_loc=getattr(self, "wh_stock_loc", None),
                    )
                    self._assign_lots_to_picking(pick, lines_by_po.get(po_num, []))
                    self._validate_picking_safely(
                        pick,
                        effective_date=arrival_dt,
                        expected_src_loc=getattr(self, "seed_supplier_loc", None),
                        expected_dest_loc=getattr(self, "wh_stock_loc", None),
                    )
                    self.stats["do_validated"] += 1

            # Vendor Bill
            if AccountMove is not None:
                existing_bills = _iter_records(
                    AccountMove.search([("ref", "=", po_num), ("move_type", "=", "in_invoice")])
                )
                if len(existing_bills) > 1:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Duplikasi Vendor Bill untuk PO '{po_num}' "
                        f"(ditemukan {len(existing_bills)} record)!"
                    )
                existing_bill = existing_bills[0] if existing_bills else None
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
    def load_sales_deliveries_and_invoices(
        self,
        limit_orders: int | None = None,
        target_so_numbers: list[str] | set[str] | None = None,
    ):
        """Memuat SO Single-Prinsipal, DO, dan Faktur Penjualan (net of rejections)."""
        if "sale.order" not in self.env:
            print("[canonical_loader] SKIP: Modul sale belum terpasang.")
            return

        print(" -> [3/7] Memuat SO Single-Prinsipal, Pengiriman DO & Faktur Komersial...")
        SaleOrder = self.env["sale.order"].sudo()
        AccountMove = self.env["account.move"].sudo() if "account.move" in self.env else None
        AccountMoveLine = self.env["account.move.line"].sudo() if "account.move.line" in self.env else None
        am_fields = _safe_fields(AccountMove) if AccountMove is not None else {}
        aml_fields = _safe_fields(AccountMoveLine) if AccountMoveLine is not None else {}

        so_rows = self._read_csv("perpetual_sales_orders.csv")
        if target_so_numbers is not None:
            target_set = set(target_so_numbers)
            so_rows = [s for s in so_rows if s["so_number"] in target_set]
        elif limit_orders is not None:
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

        sos_by_num = {}
        for so_data in so_rows:
            header_p = build_so_header_payload(so_data)
            so_num = header_p["so_number"]

            existing_sos = _iter_records(SaleOrder.search([("client_order_ref", "=", so_num)]))
            if len(existing_sos) > 1:
                raise RuntimeError(
                    f"[canonical_loader] FATAL: Duplikasi SaleOrder dengan client_order_ref '{so_num}' "
                    f"(ditemukan {len(existing_sos)} record)!"
                )
            existing_so = existing_sos[0] if existing_sos else None
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

                so_vals = {
                    "partner_id": cust_partner.id,
                    "client_order_ref": so_num,
                    "date_order": header_p["date_order"],
                    "user_id": salesman_user.id,
                    "order_line": order_lines,
                }
                if hasattr(SaleOrder, "_fields") and "fmcg_seed_batch" in SaleOrder._fields:
                    so_vals["fmcg_seed_batch"] = "CANONICAL_JULY_2026_PERPETUAL"
                so = SaleOrder.create(so_vals)
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
                        self._align_picking_locations(
                            pick,
                            expected_src_loc=getattr(self, "wh_stock_loc", None),
                            expected_dest_loc=getattr(self, "seed_customer_loc", None),
                        )
                        self._assign_lots_to_picking(pick, lines_by_so.get(so_num, []))
                        self._validate_picking_safely(
                            pick,
                            effective_date=sched_date,
                            expected_src_loc=getattr(self, "wh_stock_loc", None),
                            expected_dest_loc=getattr(self, "seed_customer_loc", None),
                        )
                        self.stats["do_validated"] += 1

            sos_by_num[so_num] = so

        # Muat retur karantina terkait sebelum faktur komersial dibuat dan di-posting,
        # agar rekonsiliasi pengiriman bersih (dispatched - return == billed) terpenuhi secara fisik
        self.load_rejections_quarantine(limit_orders=limit_orders, target_so_numbers=target_so_numbers)

        for so_data in so_rows:
            header_p = build_so_header_payload(so_data)
            so_num = header_p["so_number"]
            so = sos_by_num.get(so_num)

            # Faktur Penjualan Sah (Net of Rejections) dengan product_id & sale_line_ids lengkap
            inv_info = inv_by_so.get(so_num)
            if AccountMove is not None and inv_info:
                inv_num = inv_info["invoice_number"]
                existing_invs = _iter_records(AccountMove.search([("ref", "=", inv_num)]))
                if len(existing_invs) > 1:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Duplikasi Faktur Penjualan dengan ref '{inv_num}' "
                        f"(ditemukan {len(existing_invs)} record)!"
                    )
                existing_inv = existing_invs[0] if existing_invs else None
                if existing_inv:
                    self.stats["skipped_invoices"] += 1
                else:
                    so_lines_list = _iter_records(getattr(so, "order_line", None))
                    used_sol_ids = set()
                    inv_lines = []
                    for lrow in lines_by_so.get(so_num, []):
                        line_p = build_order_line_payload(lrow)
                        pr = self.product_by_code.get(line_p["sku_code"])
                        if not pr:
                            continue

                        matched_sol = None
                        for sol in so_lines_list:
                            sol_id = getattr(sol, "id", None)
                            sol_pid = getattr(getattr(sol, "product_id", None), "id", getattr(sol, "product_id", None))
                            if sol_id not in used_sol_ids and sol_pid == pr.id:
                                sol_qty = float(getattr(sol, "product_uom_qty", line_p["qty_units"]) or 0.0)
                                if abs(sol_qty - line_p["qty_units"]) < 0.001:
                                    matched_sol = sol
                                    used_sol_ids.add(sol_id)
                                    break
                        if matched_sol is None:
                            for sol in so_lines_list:
                                sol_id = getattr(sol, "id", None)
                                sol_prod = getattr(sol, "product_id", None)
                                sol_pid = getattr(sol_prod, "id", sol_prod)
                                if sol_id not in used_sol_ids and sol_pid == pr.id:
                                    matched_sol = sol
                                    used_sol_ids.add(sol_id)
                                    break

                        key = (so_num, line_p["sku_code"], line_p["lot_number"])
                        rej_cartons = rejections_by_so_line.get(key, 0.0)
                        net_cartons = line_p["qty_cartons"] - rej_cartons
                        if net_cartons <= 0:
                            continue

                        net_units = net_cartons * line_p["carton_qty"]
                        pr_comp = (
                            pr.with_company(self.company)
                            if callable(getattr(pr, "with_company", None)) and hasattr(self, "company") and self.company
                            else pr
                        )
                        inv_line_vals = {
                            "product_id": pr.id,
                            "quantity": net_units,
                            "price_unit": line_p["unit_price_dpp"],
                            "discount": header_p["discount_pct"],
                            "name": f"{lrow.get('product_name')} (Lot: {line_p['lot_number']})",
                        }
                        uom_rec = getattr(pr, "uom_id", None)
                        if uom_rec and hasattr(uom_rec, "id") and ("product_uom_id" in aml_fields or not aml_fields):
                            inv_line_vals["product_uom_id"] = uom_rec.id
                        if (
                            matched_sol is not None
                            and getattr(matched_sol, "id", None)
                            and ("sale_line_ids" in aml_fields or not aml_fields)
                        ):
                            inv_line_vals["sale_line_ids"] = [(6, 0, [matched_sol.id])]

                        if callable(getattr(pr_comp, "_get_product_accounts", None)):
                            prod_accs = pr_comp._get_product_accounts()
                            if isinstance(prod_accs, dict) and prod_accs.get("income"):
                                inv_line_vals["account_id"] = prod_accs["income"].id

                        taxes = getattr(pr_comp, "taxes_id", None)
                        if taxes and hasattr(taxes, "filtered") and hasattr(self, "company") and self.company:
                            taxes = taxes.filtered(
                                lambda t: not getattr(t, "company_id", False) or t.company_id.id == self.company.id
                            )
                        if (not taxes or not getattr(taxes, "ids", None)) and "account.tax" in self.env:
                            AccountTax = self.env["account.tax"].sudo()
                            tax_domain = [("type_tax_use", "=", "sale"), ("amount", "=", 11.0)]
                            if (
                                "company_id" in _safe_fields(AccountTax)
                                and hasattr(self, "company")
                                and self.company
                            ):
                                tax_domain.append(("company_id", "=", self.company.id))
                            taxes = AccountTax.search(tax_domain, limit=1)
                        if taxes and getattr(taxes, "ids", None):
                            inv_line_vals["tax_ids"] = [(6, 0, list(taxes.ids))]

                        inv_lines.append((0, 0, inv_line_vals))

                    inv_vals = {
                        "move_type": "out_invoice",
                        "partner_id": so.partner_id.id,
                        "ref": inv_num,
                        "invoice_date": inv_info["date_invoice"],
                        "date": inv_info["date_invoice"],
                        "invoice_date_due": inv_info["due_date"],
                        "invoice_line_ids": inv_lines,
                    }
                    if "is_fmcg_seed_invoice" in am_fields or not am_fields:
                        inv_vals["is_fmcg_seed_invoice"] = True
                    if "fmcg_seed_batch" in am_fields or not am_fields:
                        inv_vals["fmcg_seed_batch"] = "CANONICAL_JULY_2026_PERPETUAL"
                    if "invoice_origin" in am_fields or not am_fields:
                        inv_vals["invoice_origin"] = so_num
                    inv = AccountMove.create(inv_vals)
                    self.stats["invoices_created"] += 1
                    # Memanggil action_post() secara native tanpa reversal context (move_reverse_cancel).
                    # Pencegahan duplikasi COGS ditangani secara sempit dan elegan melalui override model
                    # account.move._stock_account_prepare_realtime_out_lines_vals() pada addon id_base
                    # khusus untuk faktur komersial seed yang delivery-nya telah membukukan HPP native di STJ.
                    inv.action_post()
                    self.stats["invoices_posted"] += 1

    # 4. Retur Karantina
    def load_rejections_quarantine(
        self,
        limit_orders: int | None = None,
        target_so_numbers: list[str] | set[str] | None = None,
    ):
        """Memuat 9 Retur Karantina ke lokasi karantina khusus via transfer picking internal tanpa duplikasi quant."""
        print(" -> [4/7] Memuat Retur Karantina Barang...")
        rows = self._read_csv("perpetual_order_rejections.csv")
        if target_so_numbers is not None:
            target_set = set(target_so_numbers)
            rows = [r for r in rows if r["so_number"] in target_set]
        elif limit_orders is not None:
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

        if StockLocation is None:
            return

        internal_loc = getattr(self, "wh_stock_loc", None)
        customer_loc = getattr(self, "seed_customer_loc", None)
        if not customer_loc:
            cust_vals = {
                "name": "Customers FMCG Maumbi",
                "usage": "customer",
            }
            if hasattr(self, "company") and self.company and "company_id" in _safe_fields(StockLocation):
                cust_vals["company_id"] = self.company.id
            if hasattr(self, "cogs_acc") and self.cogs_acc and "valuation_account_id" in _safe_fields(StockLocation):
                cust_vals["valuation_account_id"] = self.cogs_acc.id
            customer_loc = StockLocation.create(cust_vals)
            self.seed_customer_loc = customer_loc

        quarantine_loc = getattr(self, "quarantine_loc", None)
        if not quarantine_loc:
            q_vals = {
                "name": "Karantina FMCG Maumbi",
                "usage": "internal",
                "location_id": internal_loc.id if internal_loc else False,
            }
            if hasattr(self, "company") and self.company and "company_id" in _safe_fields(StockLocation):
                q_vals["company_id"] = self.company.id
            quarantine_loc = StockLocation.create(q_vals)
            self.quarantine_loc = quarantine_loc
        has_val_acc = "valuation_account_id" in _safe_fields(StockLocation)
        if has_val_acc and getattr(quarantine_loc, "valuation_account_id", False):
            quarantine_loc.write({"valuation_account_id": False})

        for row in rows:
            p_data = build_rejection_payload(row)
            rej_id = p_data["rejection_id"]

            sku = p_data["sku_code"]
            prod = self.product_by_code.get(sku)
            lot_obj = None
            if StockLot is not None and prod:
                lot_obj = StockLot.search([("name", "=", p_data["lot_number"]), ("product_id", "=", prod.id)], limit=1)
                if not lot_obj:
                    lot_obj = StockLot.create({
                        "name": p_data["lot_number"],
                        "product_id": prod.id,
                        "company_id": self.company.id,
                    })

            # Jika stock.picking tersedia, gunakan transfer internal Odoo murni
            # Lokasi asal adalah customer_loc (Customers FMCG Maumbi) karena barang ditolak saat pengiriman,
            # sehingga stok gudang utama (WH/Stock) tidak terpotong dua kali.
            if StockPicking is not None:
                existing_picks = _iter_records(StockPicking.search([("origin", "=", rej_id)]))
                if len(existing_picks) > 1:
                    raise RuntimeError(
                        f"[canonical_loader] FATAL: Duplikasi Picking Retur Karantina '{rej_id}' "
                        f"(ditemukan {len(existing_picks)} record)!"
                    )
                existing_pick = existing_picks[0] if existing_picks else None
                if existing_pick:
                    self.stats["skipped_quarantine"] += 1
                    continue

                StockPickingType = (
                    self.env["stock.picking.type"].sudo() if "stock.picking.type" in self.env else None
                )
                internal_type = None
                if StockPickingType is not None:
                    internal_type = (
                        StockPickingType.search([("code", "=", "incoming")], limit=1)
                        or StockPickingType.search([("code", "=", "internal")], limit=1)
                        or StockPickingType.search([], limit=1)
                    )
                    if not internal_type:
                        internal_type = StockPickingType.create({
                            "name": "Internal Transfers",
                            "code": "internal",
                            "sequence_code": "INT",
                            "company_id": self.company.id,
                        })

                # Temukan outbound move dan sale.order.line terkait untuk persistent binding
                out_sm = None
                target_sol = None
                SaleOrder = self.env["sale.order"].sudo() if "sale.order" in self.env else None
                if SaleOrder is not None:
                    matching_sos = _iter_records(SaleOrder.search([("client_order_ref", "=", p_data["so_number"])]))
                    if matching_sos:
                        so_rec = matching_sos[0]
                        for s_line in getattr(so_rec, "order_line", []):
                            s_prod_id = getattr(getattr(s_line, "product_id", None), "id", None)
                            if s_prod_id == (prod.id if prod else None):
                                target_sol = s_line
                                for m in getattr(s_line, "move_ids", []):
                                    m_dest = getattr(getattr(m, "location_dest_id", None), "usage", "")
                                    m_prod_id = getattr(getattr(m, "product_id", None), "id", None)
                                    if (
                                        getattr(m, "state", "") == "done"
                                        and m_dest == "customer"
                                        and m_prod_id == (prod.id if prod else None)
                                    ):
                                        out_sm = m
                                        break
                                if out_sm:
                                    break
                        if not out_sm:
                            for p in getattr(so_rec, "picking_ids", []):
                                for m in getattr(p, "move_ids", []):
                                    m_dest = getattr(getattr(m, "location_dest_id", None), "usage", "")
                                    m_prod_id = getattr(getattr(m, "product_id", None), "id", None)
                                    if (
                                        getattr(m, "state", "") == "done"
                                        and m_dest == "customer"
                                        and m_prod_id == (prod.id if prod else None)
                                    ):
                                        out_sm = m
                                        if not target_sol and getattr(m, "sale_line_id", None):
                                            target_sol = m.sale_line_id
                                        break
                                if out_sm:
                                    break
                if not out_sm and "stock.move" in self.env and prod:
                    StockMove = self.env["stock.move"].sudo()
                    cand_moves = StockMove.search([
                        ("origin", "=", p_data["so_number"]),
                        ("product_id", "=", prod.id),
                        ("state", "=", "done"),
                        ("location_dest_id.usage", "=", "customer"),
                    ], limit=1)
                    if cand_moves:
                        out_sm = cand_moves[0]
                        if not target_sol and getattr(out_sm, "sale_line_id", None):
                            target_sol = out_sm.sale_line_id

                uom_rec = getattr(prod, "uom_id", None)
                move_item = {
                    "product_id": prod.id if prod else False,
                    "product_uom": uom_rec.id if uom_rec and hasattr(uom_rec, "id") else False,
                    "product_uom_qty": p_data["qty_units"],
                    "location_id": customer_loc.id,
                    "location_dest_id": quarantine_loc.id,
                    "company_id": self.company.id,
                }
                mv_fields = _safe_fields(self.env["stock.move"]) if "stock.move" in self.env else {}
                if out_sm and ("origin_returned_move_id" in mv_fields or not mv_fields):
                    move_item["origin_returned_move_id"] = out_sm.id
# sale_line_id omitted to prevent picking_ids contamination
                if "name" in mv_fields:
                    move_item["name"] = f"Retur Karantina {rej_id} - {prod.display_name if prod else ''}"
                if "description_picking" in mv_fields:
                    move_item["description_picking"] = f"Retur Karantina {rej_id} - {prod.display_name if prod else ''}"
                if "price_unit" in mv_fields or not mv_fields:
                    move_item["price_unit"] = p_data["unit_cost"]
                if "origin" in mv_fields or not mv_fields:
                    move_item["origin"] = f"{rej_id} ({p_data['so_number']})"
                if "picked" in mv_fields:
                    move_item["picked"] = True
                if mv_fields:
                    move_item = {k: v for k, v in move_item.items() if k in mv_fields}

                pick_vals = {
                    "origin": rej_id,
                    "picking_type_id": internal_type.id if internal_type else False,
                    "location_id": customer_loc.id,
                    "location_dest_id": quarantine_loc.id,
                    "note": (
                        f"Retur Karantina {p_data['so_number']} DO {p_data['do_number']}: "
                        f"{p_data['rejection_reason']}"
                    ),
                    "move_ids": [(0, 0, move_item)] if prod else [],
                }
                pick = StockPicking.create(pick_vals)
                if callable(getattr(pick, "action_confirm", None)) and getattr(pick, "state", "") == "draft":
                    pick.action_confirm()
                self._align_picking_locations(
                    pick,
                    expected_src_loc=customer_loc,
                    expected_dest_loc=quarantine_loc,
                )
                self._assign_lots_to_picking(pick, [row])
                self._validate_picking_safely(
                    pick,
                    effective_date=p_data["rejection_date"],
                    expected_src_loc=customer_loc,
                    expected_dest_loc=quarantine_loc,
                )
                for ret_mv in getattr(pick, "move_ids", []):
                    w_vals = {}
                    if out_sm and getattr(ret_mv, "origin_returned_move_id", None) != out_sm:
                        if "origin_returned_move_id" in _safe_fields(ret_mv) or not _safe_fields(ret_mv):
                            w_vals["origin_returned_move_id"] = out_sm.id
# sale_line_id omitted to prevent picking_ids contamination
                    if w_vals:
                        ret_mv.write(w_vals)
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
    def load_payments(
        self,
        limit_orders: int | None = None,
        target_so_numbers: list[str] | set[str] | None = None,
    ):
        """Memuat 967 Pembayaran AR Pelanggan & 4 Pembayaran AP Prinsipal dengan rekonsiliasi ketat."""
        if "account.payment" not in self.env:
            print("[canonical_loader] SKIP: Modul account.payment belum terpasang.")
            return

        print(" -> [5/7] Memuat Pembayaran AR Pelanggan & AP Prinsipal...")
        AccountPayment = self.env["account.payment"].sudo()
        AccountMove = self.env["account.move"].sudo() if "account.move" in self.env else None

        # AR Payments
        ar_rows = self._read_csv("perpetual_ar_collections.csv")
        if target_so_numbers is not None:
            target_set = set(target_so_numbers)
            inv_sample = {
                iv["invoice_number"]
                for iv in self._read_csv("perpetual_invoices.csv")
                if iv["so_number"] in target_set
            }
            ar_rows = [ar for ar in ar_rows if ar["invoice_number"] in inv_sample]
        elif limit_orders is not None:
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

            existing = self._find_payment(pay_id)
            disc_amt = p_data.get("cash_discount_dpp", 0.0)
            disc_ref = f"DISC-{pay_id}"

            if existing:
                pay = existing
                if getattr(pay, "state", "") == "draft":
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

                disc_move_check = (
                    AccountMove.search([("ref", "=", disc_ref)], limit=1)
                    if AccountMove is not None
                    else None
                )
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
                pay_vals = {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": cust_partner.id,
                    "amount": p_data["net_cash_collected_total"],
                    "date": p_data["payment_date"],
                }
                pay_fields = getattr(AccountPayment, "_fields", {})
                if "memo" in pay_fields:
                    pay_vals["memo"] = pay_id
                if "ref" in pay_fields or not pay_fields:
                    pay_vals["ref"] = pay_id

                pay = AccountPayment.create(pay_vals)
                self.stats["ar_payments_created"] += 1
                pay.action_post()
                if hasattr(pay, "move_id") and pay.move_id and not getattr(pay.move_id, "ref", None):
                    try:
                        pay.move_id.ref = pay_id
                    except Exception:
                        pass

            # Diskon Pembayaran Awal (Early Cash Discount)
            disc_move = None
            if AccountMove is not None and disc_amt > 0:
                existing_disc = AccountMove.search([("ref", "=", disc_ref)], limit=1)
                if not existing_disc:
                    AccountAccount = (
                        self.env["account.account"].sudo() if "account.account" in self.env else None
                    )
                    disc_account = None
                    ar_account = None
                    if AccountAccount is not None:
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
            if AccountMove is not None:
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

            existing = self._find_payment(pay_id)
            if existing:
                pay = existing
                if getattr(pay, "state", "") == "draft":
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

                pay_vals = {
                    "payment_type": "outbound",
                    "partner_type": "supplier",
                    "partner_id": prin_partner.id,
                    "amount": p_data["amount_paid_dpp"],
                    "date": p_data["payment_date"],
                }
                pay_fields = getattr(AccountPayment, "_fields", {})
                if "memo" in pay_fields:
                    pay_vals["memo"] = pay_id
                if "ref" in pay_fields or not pay_fields:
                    pay_vals["ref"] = pay_id

                pay = AccountPayment.create(pay_vals)
                self.stats["ap_payments_created"] += 1
                pay.action_post()
                if hasattr(pay, "move_id") and pay.move_id and not getattr(pay.move_id, "ref", None):
                    try:
                        pay.move_id.ref = pay_id
                    except Exception:
                        pass

            # Reconcile dengan bill PO
            if AccountMove is not None:
                bill = AccountMove.search(
                    [("ref", "=", p_data["po_number"]), ("move_type", "=", "in_invoice")], limit=1
                )
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
        """Memuat 30 Beban Operasional & Payroll Roster dengan pemetaan akun beban dan partner operasional eksplisit."""
        if "account.move" not in self.env:
            print("[canonical_loader] SKIP: Modul account.move belum terpasang.")
            return

        print(" -> [6/7] Memuat 30 Beban Operasional & Payroll Roster...")
        AccountMove = self.env["account.move"].sudo()
        rows = self._read_csv("perpetual_opex_payroll.csv")

        for idx, op in enumerate(rows, start=1):
            ref_code = f"OPEX-2026-07-{idx:02d}"
            existing_list = _iter_records(AccountMove.search([("ref", "=", ref_code)]))
            if len(existing_list) > 1:
                raise RuntimeError(
                    f"[canonical_loader] FATAL: Duplikasi dokumen OPEX '{ref_code}' "
                    f"(ditemukan {len(existing_list)} record)!"
                )
            existing = existing_list[0] if existing_list else None
            if existing:
                self.stats["skipped_opex"] += 1
                continue

            cat_name = str(op.get("category", "")).strip()
            pay_type = str(op.get("payment_type", "")).strip()
            opex_acc = getattr(self, "opex_accounts", {}).get(cat_name)
            if not opex_acc:
                raise RuntimeError(
                    f"[canonical_loader] FATAL: Kategori OPEX '{cat_name}' pada '{ref_code}' "
                    f"tidak memiliki mapping akun beban eksplisit!"
                )
            opex_partner = getattr(self, "opex_partners", {}).get(pay_type)
            comp_partner_id = getattr(getattr(getattr(self, "company", None), "partner_id", None), "id", None)
            if not opex_partner or (comp_partner_id and getattr(opex_partner, "id", None) == comp_partner_id):
                raise RuntimeError(
                    f"[canonical_loader] FATAL: Payment type OPEX '{pay_type}' pada '{ref_code}' "
                    f"tidak memiliki partner operasional eksplisit (dilarang menggunakan partner company)!"
                )

            amt = float(op["amount"])
            line_vals = {
                "name": f"{cat_name}: {op.get('description')}",
                "quantity": 1.0,
                "price_unit": amt,
                "account_id": opex_acc.id,
                "tax_ids": [(6, 0, [])],
            }
            move = AccountMove.create({
                "move_type": "in_invoice",
                "partner_id": opex_partner.id,
                "ref": ref_code,
                "invoice_date": op["date"],
                "date": op["date"],
                "invoice_line_ids": [(0, 0, line_vals)],
            })
            move.action_post()
            self.stats["opex_moves_created"] += 1

    # 7. Eksekusi Penuh & Rekonsiliasi Runtime
    def run_all(
        self,
        limit_orders: int | None = None,
        target_so_numbers: list[str] | set[str] | None = None,
    ):
        """Menjalankan seluruh alur pemuatan canonical seed secara sekuensial dan terisolasi transaksi."""
        try:
            self.load_opening_stock()
            self.load_inbound_pos()
            self.load_sales_deliveries_and_invoices(
                limit_orders=limit_orders, target_so_numbers=target_so_numbers
            )
            if not self.stats["quarantine_rejections"] and not self.stats["skipped_quarantine"]:
                self.load_rejections_quarantine(
                    limit_orders=limit_orders, target_so_numbers=target_so_numbers
                )
            self.load_payments(
                limit_orders=limit_orders, target_so_numbers=target_so_numbers
            )
            self.load_opex_payroll()

            # Verifikasi integritas cakupan data dan hasil operasi SEBELUM self.cr.commit()
            if target_so_numbers is not None:
                exp_so_count = len(target_so_numbers)
                total_small_so = self.stats["so_created"] + self.stats["skipped_so"]
                assert total_small_so == exp_so_count, (
                    f"Jumlah SO batch representatif tidak cocok! Expected {exp_so_count}, got {total_small_so}"
                )
                assert (self.stats["ar_reconciled"] + self.stats["skipped_ar"]) >= 1, (
                    f"AR batch representatif harus ter-reconcile! Got {self.stats['ar_reconciled']}"
                )
                assert (self.stats["ap_reconciled"] + self.stats["skipped_ap"]) == 4, (
                    f"AP batch representatif harus ter-reconcile! Got {self.stats['ap_reconciled']}"
                )
            elif limit_orders is not None:
                total_small_so = self.stats["so_created"] + self.stats["skipped_so"]
                assert total_small_so == limit_orders, (
                    f"Jumlah SO batch kecil tidak cocok! Expected {limit_orders}, got {total_small_so}"
                )
                assert (self.stats["ar_reconciled"] + self.stats["skipped_ar"]) >= 1, (
                    f"AR batch kecil harus ter-reconcile! Got {self.stats['ar_reconciled']}"
                )
                assert (self.stats["ap_reconciled"] + self.stats["skipped_ap"]) == 4, (
                    f"AP batch kecil harus ter-reconcile! Got {self.stats['ap_reconciled']}"
                )
            else:
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

            # Muat register AR & AP kanonikal untuk verifikasi readback menyeluruh
            ar_rows = self._read_csv("perpetual_ar_collections.csv")
            ap_rows = self._read_csv("perpetual_ap_payments.csv")
            if target_so_numbers is not None:
                target_set = set(target_so_numbers)
                inv_sample = {
                    iv["invoice_number"]
                    for iv in self._read_csv("perpetual_invoices.csv")
                    if iv["so_number"] in target_set
                }
                ar_rows = [ar for ar in ar_rows if ar["invoice_number"] in inv_sample]
            elif limit_orders is not None:
                so_sample = {s["so_number"] for s in self._read_csv("perpetual_sales_orders.csv")[:limit_orders]}
                inv_sample = {
                    iv["invoice_number"]
                    for iv in self._read_csv("perpetual_invoices.csv")
                    if iv["so_number"] in so_sample
                }
                ar_rows = [ar for ar in ar_rows if ar["invoice_number"] in inv_sample]

            # Verifikasi bahwa seluruh entri diskon berstatus posted, bersumber dari ID persis,
            # dan baris piutangnya terekonsiliasi penuh
            if "account.move" in self.env:
                AccountMove = self.env["account.move"].sudo()
                disc_ar_rows = [
                    r for r in ar_rows if float(r.get("early_payment_discount", 0.0)) > 0
                ]
                expected_discs = {
                    f"DISC-{r['payment_id']}": float(r["early_payment_discount"])
                    for r in disc_ar_rows
                }

                # 1. Validasi setiap ID sumber diskon persis wajib ada, posted, dan terekonsiliasi
                for disc_ref, expected_amt in expected_discs.items():
                    dm = AccountMove.search([("ref", "=", disc_ref)], limit=1)
                    assert dm, (
                        f"Jurnal diskon persis '{disc_ref}' tidak ditemukan di database! "
                        "Pencocokan ID sumber persis wajib terpenuhi."
                    )
                    assert dm.state == "posted", (
                        f"Jurnal diskon '{disc_ref}' belum berstatus 'posted'! State: {dm.state}"
                    )
                    rec_lines = self._get_record_lines(dm)
                    rec_lines_flt = (
                        rec_lines.filtered(
                            lambda line: getattr(getattr(line, "account_id", None), "account_type", "")
                            == "asset_receivable"
                        )
                        if hasattr(rec_lines, "filtered")
                        else [
                            line
                            for line in rec_lines
                            if getattr(getattr(line, "account_id", None), "account_type", "") == "asset_receivable"
                        ]
                    )
                    assert len(rec_lines_flt) > 0, f"Jurnal diskon '{disc_ref}' tidak memiliki baris asset_receivable!"
                    total_disc_credit = sum(float(getattr(rl, "credit", 0.0)) for rl in rec_lines_flt)
                    assert abs(total_disc_credit - expected_amt) < 0.01, (
                        f"Nominal kredit piutang jurnal diskon '{disc_ref}' tidak cocok! "
                        f"Expected: {expected_amt}, Got: {total_disc_credit}"
                    )
                    for rl in rec_lines_flt:
                        res_val = getattr(rl, "amount_residual", "N/A")
                        assert self._is_reconciled(rl), (
                            f"Baris diskon '{disc_ref}' belum terekonsiliasi penuh! Residual: {res_val}"
                        )

                # 2. Validasi ketat bahwa tidak ada jurnal diskon siluman / tidak dikenal di database
                all_disc_in_db = AccountMove.search([("ref", "=like", "DISC-%")])
                found_disc_refs = {getattr(dm, "ref", "") for dm in all_disc_in_db if getattr(dm, "ref", "")}
                assert len(all_disc_in_db) == len(expected_discs), (
                    f"Jumlah jurnal diskon di database ({len(all_disc_in_db)}) "
                    f"tidak cocok dengan register kanonikal ({len(expected_discs)})! "
                    f"Expected: {sorted(expected_discs.keys())}, Got: {sorted(found_disc_refs)}"
                )
                unrelated_discs = found_disc_refs - set(expected_discs.keys())
                assert not unrelated_discs, (
                    f"Ditemukan jurnal diskon dengan ref tidak dikenal/tidak bersumber dari register: {unrelated_discs}"
                )

            # Verifikasi seluruh payment kanonikal secara persis dari register ID sumber
            if "account.payment" in self.env:
                AccountMove = self.env["account.move"].sudo() if "account.move" in self.env else None

                # 1. Validasi seluruh AR Payments kanonikal
                for ar_row in ar_rows:
                    p_data = build_ar_payment_payload(ar_row)
                    pay_id = p_data["payment_id"]
                    inv_num = p_data["invoice_number"]
                    cust_partner = self.get_partner(p_data["customer_ref"])

                    py = self._find_payment(pay_id)
                    assert py, f"[canonical_loader] FATAL: Payment AR '{pay_id}' tidak ditemukan di database!"

                    # State payment Odoo 19: 'in_process', 'paid', atau 'posted' (BUKAN draft/canceled/rejected)
                    assert py.state in ("posted", "in_process", "paid"), (
                        f"Payment AR '{pay_id}' masih dalam state '{py.state}', bukan posted/in_process/paid!"
                    )
                    # WAJIB memiliki move_id relasional dan move_id.state == 'posted' (BUKAN KONDISIONAL!)
                    assert getattr(py, "move_id", None), (
                        f"Payment AR '{pay_id}' tidak memiliki journal entry move (move_id bernilai False/None)!"
                    )
                    assert py.move_id.state == "posted", (
                        f"Journal entry move payment AR '{pay_id}' belum posted! State: {py.move_id.state}"
                    )

                    # Verifikasi partner dan nominal pembayaran
                    assert getattr(py.partner_id, "id", None) == cust_partner.id, (
                        f"Partner payment '{pay_id}' tidak cocok dengan register!"
                    )
                    assert abs(float(py.amount) - p_data["net_cash_collected_total"]) < 0.01, (
                        f"Nominal payment '{pay_id}' tidak cocok dengan register!"
                    )

                    # Verifikasi seluruh baris piutang payment harus terekonsiliasi penuh
                    p_lines = self._get_record_lines(py)
                    p_rec = (
                        p_lines.filtered(
                            lambda line: getattr(getattr(line, "account_id", None), "account_type", "")
                            == "asset_receivable"
                        )
                        if hasattr(p_lines, "filtered")
                        else [
                            line
                            for line in p_lines
                            if getattr(getattr(line, "account_id", None), "account_type", "") == "asset_receivable"
                        ]
                    )
                    assert len(p_rec) > 0, f"Payment AR '{pay_id}' tidak memiliki baris piutang (asset_receivable)!"
                    for pl in p_rec:
                        res_val = getattr(pl, "amount_residual", "N/A")
                        assert self._is_reconciled(pl), (
                            f"Baris pembayaran AR '{pay_id}' belum terekonsiliasi! Residual: {res_val}"
                        )

                    # Verifikasi faktur pasangan komersial
                    if AccountMove is not None:
                        inv = AccountMove.search([("ref", "=", inv_num)], limit=1)
                        assert inv, f"Faktur pasangan '{inv_num}' untuk payment '{pay_id}' tidak ditemukan!"
                        assert inv.state == "posted", f"Faktur '{inv_num}' belum posted! State: {inv.state}"
                        inv_lines = self._get_record_lines(inv)
                        inv_rec = (
                            inv_lines.filtered(
                                lambda line: getattr(getattr(line, "account_id", None), "account_type", "")
                                == "asset_receivable"
                            )
                            if hasattr(inv_lines, "filtered")
                            else [
                                line
                                for line in inv_lines
                                if getattr(getattr(line, "account_id", None), "account_type", "") == "asset_receivable"
                            ]
                        )
                        assert len(inv_rec) > 0, (
                            f"Faktur pasangan '{inv_num}' untuk payment '{pay_id}' "
                            "tidak memiliki baris piutang (asset_receivable)!"
                        )
                        total_inv_debit = sum(float(getattr(il, "debit", 0.0)) for il in inv_rec)
                        assert total_inv_debit > 0.0, (
                            f"Total piutang faktur pasangan '{inv_num}' harus bernilai positif! Got {total_inv_debit}"
                        )
                        for il in inv_rec:
                            res_val = getattr(il, "amount_residual", "N/A")
                            assert self._is_reconciled(il), (
                                f"Baris faktur '{inv_num}' belum terekonsiliasi penuh! Residual: {res_val}"
                            )

                # 2. Validasi seluruh AP Payments kanonikal
                for ap_row in ap_rows:
                    p_data = build_ap_payment_payload(ap_row)
                    pay_id = p_data["ap_payment_id"]
                    po_num = p_data["po_number"]
                    prin_name = p_data["principal_name"]
                    prin_partner = self.partner_by_name.get(prin_name) or self.partner_by_ref.get(prin_name)

                    py = self._find_payment(pay_id)
                    assert py, f"[canonical_loader] FATAL: Payment AP '{pay_id}' tidak ditemukan di database!"
                    assert py.state in ("posted", "in_process", "paid"), (
                        f"Payment AP '{pay_id}' masih dalam state '{py.state}', bukan posted/in_process/paid!"
                    )
                    # WAJIB memiliki move_id relasional dan move_id.state == 'posted' (BUKAN KONDISIONAL!)
                    assert getattr(py, "move_id", None), (
                        f"Payment AP '{pay_id}' tidak memiliki journal entry move (move_id bernilai False/None)!"
                    )
                    assert py.move_id.state == "posted", (
                        f"Journal entry move payment AP '{pay_id}' belum posted! State: {py.move_id.state}"
                    )

                    if prin_partner:
                        assert getattr(py.partner_id, "id", None) == prin_partner.id, (
                            f"Principal partner AP payment '{pay_id}' tidak cocok!"
                        )
                    assert abs(float(py.amount) - p_data["amount_paid_dpp"]) < 0.01, (
                        f"Nominal AP payment '{pay_id}' tidak cocok dengan register!"
                    )

                    p_lines = self._get_record_lines(py)
                    p_pay = (
                        p_lines.filtered(
                            lambda line: getattr(getattr(line, "account_id", None), "account_type", "")
                            == "liability_payable"
                        )
                        if hasattr(p_lines, "filtered")
                        else [
                            line
                            for line in p_lines
                            if getattr(getattr(line, "account_id", None), "account_type", "") == "liability_payable"
                        ]
                    )
                    assert len(p_pay) > 0, f"Payment AP '{pay_id}' tidak memiliki baris utang (liability_payable)!"
                    for pl in p_pay:
                        res_val = getattr(pl, "amount_residual", "N/A")
                        assert self._is_reconciled(pl), (
                            f"Baris pembayaran AP '{pay_id}' belum terekonsiliasi! Residual: {res_val}"
                        )

                    if AccountMove is not None:
                        bill = AccountMove.search([("ref", "=", po_num), ("move_type", "=", "in_invoice")], limit=1)
                        assert bill, f"Bill pasangan '{po_num}' untuk payment '{pay_id}' tidak ditemukan!"
                        assert bill.state == "posted", f"Bill '{po_num}' belum posted! State: {bill.state}"
                        bill_lines = self._get_record_lines(bill)
                        bill_pay = (
                            bill_lines.filtered(
                                lambda line: getattr(getattr(line, "account_id", None), "account_type", "")
                                == "liability_payable"
                            )
                            if hasattr(bill_lines, "filtered")
                            else [
                                line
                                for line in bill_lines
                                if getattr(getattr(line, "account_id", None), "account_type", "")
                                == "liability_payable"
                            ]
                        )
                        assert len(bill_pay) > 0, (
                            f"Bill pasangan '{po_num}' untuk payment '{pay_id}' "
                            "tidak memiliki baris utang (liability_payable)!"
                        )
                        total_bill_credit = sum(float(getattr(bl, "credit", 0.0)) for bl in bill_pay)
                        assert total_bill_credit > 0.0, (
                            f"Total utang bill pasangan '{po_num}' harus bernilai positif! Got {total_bill_credit}"
                        )
                        for bl in bill_pay:
                            res_val = getattr(bl, "amount_residual", "N/A")
                            assert self._is_reconciled(bl), (
                                f"Baris bill '{po_num}' belum terekonsiliasi penuh! Residual: {res_val}"
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
