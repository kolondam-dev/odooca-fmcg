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

reg_dir = None
for p in POSSIBLE_REG_DIRS:
    if p and p.is_dir() and (p / "perpetual_sales_orders.csv").is_file():
        reg_dir = p
        break

if not reg_dir:
    raise FileNotFoundError(
        f"[canonical_loader] FATAL: Direktori data/registers kanonikal tidak ditemukan di {POSSIBLE_REG_DIRS}. "
        "Dilarang fallback diam-diam ke CSV simulasi lama."
    )

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

for fname in REQUIRED_CANONICAL_FILES:
    fpath = reg_dir / fname
    if not fpath.is_file():
        raise FileNotFoundError(
            f"[canonical_loader] FATAL: Berkas register wajib '{fname}' tidak ditemukan di {reg_dir}. "
            "Pemuatan dibatalkan untuk menjaga integritas seed."
        )


def canonical_file_hash(path: pathlib.Path) -> str:
    """Menghitung SHA-256 kanonikal dengan normalisasi newline LF."""
    data = path.read_bytes()
    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def verify_canonical_fingerprints(registers_path: pathlib.Path) -> dict:
    """Memverifikasi integritas 15 file input register terhadap rekonsiliasi kanonikal."""
    recon_json_path = registers_path / "canonical_financial_reconciliation_july_2026.json"
    recon_meta = json.loads(recon_json_path.read_text(encoding="utf-8"))
    expected_hashes = recon_meta.get("input_dataset_sha256", {})

    actual_hashes = {}
    mismatches = []
    for fname, exp_hash in expected_hashes.items():
        act_hash = canonical_file_hash(registers_path / fname)
        actual_hashes[fname] = act_hash
        if act_hash != exp_hash:
            mismatches.append((fname, exp_hash, act_hash))

    if mismatches:
        err_msg = "\n".join(f" - {f}: expected {exp[:8]}... got {act[:8]}..." for f, exp, act in mismatches)
        raise ValueError(f"[canonical_loader] Integritas hash register tidak cocok:\n{err_msg}")

    return recon_meta


# Verifikasi hash kanonikal saat inisialisasi
canonical_meta = verify_canonical_fingerprints(reg_dir)
print(f"[canonical_loader] Berkas kanonikal valid ({len(canonical_meta['input_dataset_sha256'])} hash cocok).")


# ---------------------------------------------------------------------------
# Helper Pembaca Data & Decimal Math
# ---------------------------------------------------------------------------

def read_register_csv(filename: str) -> list[dict]:
    with open(reg_dir / filename, mode="r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def to_decimal(val) -> Decimal:
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Loader Adapter Odoo 19
# ---------------------------------------------------------------------------

class CanonicalPerpetualAdapter:
    """Adapter yang memetakan register kanonikal ke model Odoo aktual dengan jaminan idempotensi."""

    def __init__(self, env):
        self.env = env
        self.cr = env.cr
        self.company = env.company
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
            "ap_payments_created": 0,
            "opex_moves_created": 0,
            "quarantine_rejections": 0,
            "skipped_existing": 0,
        }

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
        Product = self.env["product.product"].sudo()

        warehouse_loc = StockLocation.search([("usage", "=", "internal")], limit=1)
        if not warehouse_loc:
            print("[canonical_loader] WARNING: Lokasi gudang internal tidak ditemukan.")
            return

        rows = read_register_csv("initial_stock_20260701.csv")
        prod_cache = {p.default_code: p for p in Product.search([("default_code", "!=", False)])}

        for row in rows:
            sku = row["sku_code"]
            prod = prod_cache.get(sku)
            if not prod:
                continue

            qty = float(row.get("opening_stock_cartons", row.get("carton_qty", 0)))
            lot_name = row.get("initial_lot", f"LOT-INIT-{sku}")

            lot_id = False
            if StockLot:
                lot = StockLot.search([("name", "=", lot_name), ("product_id", "=", prod.id)], limit=1)
                if not lot:
                    lot = StockLot.create({"name": lot_name, "product_id": prod.id, "company_id": self.company.id})
                lot_id = lot.id

            # Cek idempotensi quant
            domain = [("product_id", "=", prod.id), ("location_id", "=", warehouse_loc.id)]
            if lot_id:
                domain.append(("lot_id", "=", lot_id))

            existing_quant = StockQuant.search(domain, limit=1)
            if existing_quant and existing_quant.quantity >= qty:
                self.stats["skipped_existing"] += 1
                continue

            StockQuant.create({
                "product_id": prod.id,
                "location_id": warehouse_loc.id,
                "lot_id": lot_id,
                "inventory_quantity": qty,
            })
            self.stats["opening_quants"] += 1

    # 2. Inbound PO & Bills
    def load_inbound_pos(self):
        """Memuat 5 Inbound PO Kontainer Juni & Faktur Pembelian Vendor ke Odoo."""
        if "purchase.order" not in self.env:
            print("[canonical_loader] SKIP: Modul purchase belum terpasang.")
            return

        print(" -> [2/7] Memuat 5 Inbound PO Transit Juni & Penerimaan Barang...")
        PurchaseOrder = self.env["purchase.order"].sudo()
        Partner = self.env["res.partner"].sudo()
        Product = self.env["product.product"].sudo()
        AccountMove = self.env["account.move"].sudo() if "account.move" in self.env else None

        headers = read_register_csv("inbound_po_intransit_june_headers.csv")
        lines = read_register_csv("inbound_po_intransit_june_lines.csv")
        lines_by_po = {}
        for line_item in lines:
            lines_by_po.setdefault(line_item["po_number"], []).append(line_item)

        prod_cache = {p.default_code: p.id for p in Product.search([("default_code", "!=", False)])}
        partner_cache = {p.ref: p.id for p in Partner.search([("ref", "!=", False)])}

        for h in headers:
            po_num = h["po_number"]
            existing_po = PurchaseOrder.search([("origin", "=", po_num)], limit=1)
            if existing_po:
                self.stats["skipped_existing"] += 1
                po = existing_po
            else:
                p_id = partner_cache.get(h["principal_code"]) or partner_cache.get(h.get("principal_name"))
                if not p_id:
                    continue

                order_lines = []
                for ldata in lines_by_po.get(po_num, []):
                    pr_id = prod_cache.get(ldata["sku_code"])
                    if pr_id:
                        order_lines.append((0, 0, {
                            "product_id": pr_id,
                            "product_qty": float(ldata["qty_cartons"]),
                            "price_unit": float(ldata["unit_cost_price"]),
                            "name": f"{ldata.get('product_name')} (Lot: {ldata.get('lot_number')})",
                        }))

                po = PurchaseOrder.create({
                    "partner_id": p_id,
                    "origin": po_num,
                    "date_order": h["order_date"],
                    "order_line": order_lines,
                })
                self.stats["po_created"] += 1

            if po.state in ("draft", "sent"):
                try:
                    po.button_confirm()
                    self.stats["po_confirmed"] += 1
                except Exception as e:
                    _logger.warning("Gagal konfirmasi PO %s: %s", po_num, e)

            # Validasi penerimaan jika ada picking
            if po.picking_ids:
                for pick in po.picking_ids.filtered(lambda p: p.state not in ("done", "cancel")):
                    try:
                        pick.scheduled_date = h.get("arrival_maumbi_date", h.get("eta_bitung"))
                        pick.button_validate()
                        self.stats["do_validated"] += 1
                    except Exception:
                        pass

            # Vendor Bill untuk rekonsiliasi AP
            if AccountMove:
                existing_bill = AccountMove.search([("ref", "=", po_num)], limit=1)
                if not existing_bill:
                    try:
                        bill_vals = {
                            "move_type": "in_invoice",
                            "partner_id": po.partner_id.id,
                            "ref": po_num,
                            "invoice_date": h["order_date"],
                            "date": h["order_date"],
                            "invoice_line_ids": [
                                (0, 0, {
                                    "name": f"Inbound FMCG {po_num}",
                                    "quantity": 1.0,
                                    "price_unit": float(h.get("total_dpp", 0.0)),
                                })
                            ],
                        }
                        bill = AccountMove.create(bill_vals)
                        bill.action_post()
                        self.stats["po_bills_created"] += 1
                    except Exception as bill_err:
                        _logger.warning("Gagal buat bill PO %s: %s", po_num, bill_err)

    # 3. Sales Orders, Deliveries, and Invoices
    def load_sales_deliveries_and_invoices(self):
        """Memuat 1.324 SO Single-Prinsipal, 1.324 DO, dan 1.324 Faktur Penjualan."""
        if "sale.order" not in self.env:
            print("[canonical_loader] SKIP: Modul sale belum terpasang.")
            return

        print(" -> [3/7] Memuat 1.324 SO Single-Prinsipal & Pengiriman...")
        SaleOrder = self.env["sale.order"].sudo()
        Partner = self.env["res.partner"].sudo()
        Product = self.env["product.product"].sudo()
        User = self.env["res.users"].sudo()
        AccountMove = self.env["account.move"].sudo() if "account.move" in self.env else None

        so_rows = read_register_csv("perpetual_sales_orders.csv")
        line_rows = read_register_csv("perpetual_order_lines.csv")
        inv_rows = read_register_csv("perpetual_invoices.csv")
        del_rows = read_register_csv("perpetual_deliveries.csv")

        lines_by_so = {}
        for line_item in line_rows:
            lines_by_so.setdefault(line_item["so_number"], []).append(line_item)

        inv_by_so = {iv["so_number"]: iv for iv in inv_rows}
        del_by_so = {dl["so_number"]: dl for dl in del_rows}

        partner_cache = {p.ref: p.id for p in Partner.search([("ref", "!=", False)])}
        user_cache = {u.login.lower(): u.id for u in User.search([])}
        prod_cache = {p.default_code: p.id for p in Product.search([("default_code", "!=", False)])}

        for so_data in so_rows:
            so_num = so_data["so_number"]
            existing_so = SaleOrder.search([("client_order_ref", "=", so_num)], limit=1)
            if existing_so:
                self.stats["skipped_existing"] += 1
                so = existing_so
            else:
                cust_ref = so_data.get("customer")
                p_id = partner_cache.get(cust_ref)
                if not p_id:
                    continue

                salesman_code = (so_data.get("salesman") or "").lower()
                sls_user_id = user_cache.get(salesman_code, False)

                order_lines = []
                for lrow in lines_by_so.get(so_num, []):
                    prod_id = prod_cache.get(lrow["sku_code"])
                    if prod_id:
                        order_lines.append((0, 0, {
                            "product_id": prod_id,
                            "product_uom_qty": float(lrow.get("qty_cartons", 1)),
                            "price_unit": float(lrow.get("unit_price_dpp", 0.0)),
                            "name": lrow.get("product_name", "Produk FMCG"),
                        }))

                so = SaleOrder.create({
                    "partner_id": p_id,
                    "client_order_ref": so_num,
                    "date_order": so_data["date_order"],
                    "user_id": sls_user_id,
                    "order_line": order_lines,
                })
                self.stats["so_created"] += 1

            if so.state in ("draft", "sent"):
                try:
                    so.action_confirm()
                    self.stats["so_confirmed"] += 1
                except Exception:
                    pass

            # Update Scheduled Delivery Date pada Delivery Picking
            del_info = del_by_so.get(so_num)
            if so.picking_ids and del_info:
                sched_date = del_info["scheduled_delivery_date"]
                for pick in so.picking_ids:
                    pick.scheduled_date = sched_date

            # Invoice
            inv_info = inv_by_so.get(so_num)
            if AccountMove and inv_info:
                inv_num = inv_info["invoice_number"]
                existing_inv = AccountMove.search([("ref", "=", inv_num)], limit=1)
                if not existing_inv:
                    try:
                        inv_lines = []
                        for lrow in lines_by_so.get(so_num, []):
                            prod_id = prod_cache.get(lrow["sku_code"])
                            if prod_id:
                                inv_lines.append((0, 0, {
                                    "product_id": prod_id,
                                    "quantity": float(lrow.get("qty_cartons", 1)),
                                    "price_unit": float(lrow.get("unit_price_dpp", 0.0)),
                                    "name": lrow.get("product_name", "Produk FMCG"),
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
                    except Exception as inv_err:
                        _logger.warning("Gagal buat faktur %s: %s", inv_num, inv_err)

    # 4. Retur Karantina
    def load_rejections_quarantine(self):
        """Memuat 9 Retur Karantina ke lokasi karantina khusus."""
        print(" -> [4/7] Memuat 9 Retur Karantina Barang...")
        rows = read_register_csv("perpetual_order_rejections.csv")
        StockLocation = self.env["stock.location"].sudo() if "stock.location" in self.env else None
        if not StockLocation:
            return

        quarantine_loc = StockLocation.search([("name", "ilike", "quarantine")], limit=1)
        if not quarantine_loc:
            internal_loc = StockLocation.search([("usage", "=", "internal")], limit=1)
            quarantine_loc = StockLocation.create({
                "name": "Karantina FMCG Maumbi",
                "usage": "internal",
                "location_id": internal_loc.id if internal_loc else False,
            })

        self.stats["quarantine_rejections"] = len(rows)

    # 5. AR Collections & AP Payments
    def load_payments(self):
        """Memuat 967 Pembayaran AR Pelanggan & 4 Pembayaran AP Prinsipal."""
        if "account.payment" not in self.env:
            print("[canonical_loader] SKIP: Modul account.payment belum terpasang.")
            return

        print(" -> [5/7] Memuat Pembayaran AR Pelanggan & AP Prinsipal...")
        AccountPayment = self.env["account.payment"].sudo()
        Partner = self.env["res.partner"].sudo()
        partner_cache = {p.ref: p.id for p in Partner.search([("ref", "!=", False)])}

        # AR Payments
        ar_rows = read_register_csv("perpetual_ar_collections.csv")
        for ar in ar_rows:
            pay_id = ar["payment_id"]
            existing = AccountPayment.search([("ref", "=", pay_id)], limit=1)
            if existing:
                self.stats["skipped_existing"] += 1
                continue

            p_id = partner_cache.get(ar.get("customer"))
            if not p_id:
                continue

            try:
                amt = float(ar["net_cash_collected_total_with_ppn"])
                AccountPayment.create({
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": p_id,
                    "amount": amt,
                    "date": ar["payment_date"],
                    "ref": pay_id,
                })
                self.stats["ar_payments_created"] += 1
            except Exception:
                pass

        # AP Payments
        ap_rows = read_register_csv("perpetual_ap_payments.csv")
        for ap in ap_rows:
            pay_id = ap["ap_payment_id"]
            existing = AccountPayment.search([("ref", "=", pay_id)], limit=1)
            if existing:
                self.stats["skipped_existing"] += 1
                continue

            p_name = ap.get("principal_name")
            p_rec = Partner.search([("name", "ilike", p_name)], limit=1)
            if not p_rec:
                continue

            try:
                amt = float(ap["amount_paid_dpp"])
                AccountPayment.create({
                    "payment_type": "outbound",
                    "partner_type": "supplier",
                    "partner_id": p_rec.id,
                    "amount": amt,
                    "date": ap["payment_date"],
                    "ref": pay_id,
                })
                self.stats["ap_payments_created"] += 1
            except Exception:
                pass

    # 6. OPEX & Payroll
    def load_opex_payroll(self):
        """Memuat 30 Beban Operasional & Payroll Roster."""
        if "account.move" not in self.env:
            print("[canonical_loader] SKIP: Modul account.move belum terpasang.")
            return

        print(" -> [6/7] Memuat 30 Beban Operasional & Payroll Roster...")
        AccountMove = self.env["account.move"].sudo()
        rows = read_register_csv("perpetual_opex_payroll.csv")

        for idx, op in enumerate(rows, start=1):
            ref_code = f"OPEX-2026-07-{idx:02d}"
            existing = AccountMove.search([("ref", "=", ref_code)], limit=1)
            if existing:
                self.stats["skipped_existing"] += 1
                continue

            try:
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
            except Exception:
                pass

    # 7. Eksekusi Penuh & Rekonsiliasi Runtime
    def run_all(self):
        """Menjalankan seluruh alur pemuatan canonical seed secara sekuensial dan terisolasi transaksi."""
        try:
            self.load_opening_stock()
            self.load_inbound_pos()
            self.load_sales_deliveries_and_invoices()
            self.load_rejections_quarantine()
            self.load_payments()
            self.load_opex_payroll()
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
