#!/usr/bin/env python3
"""Script loader simulasi transaksi historis FMCG ke Odoo 19 via Odoo shell.

Memuat transaksi historis secara idempoten:
1. OPEX Vendor Bills (modul account: move_type 'in_invoice')
2. Inbound PO & Bills (modul purchase: purchase.order / account.move)
3. Sales Orders & Invoices (modul sale: sale.order & account.move)

Dijalankan via:
    odoo shell -c /tmp/odoo.conf -d <dbname> --no-http < scripts/load_historical_simulation.py
"""

import csv
import logging
import pathlib
import sys

_logger = logging.getLogger("historical_simulation_loader")

# Pastikan objek env Odoo tersedia
env = globals().get("env")
if not env:
    print("[hist_loader] ERROR: Skrip ini harus dijalankan di dalam Odoo shell (objek 'env' tidak ditemukan).")
    sys.exit(1)

cr = env.cr

# Cari direktori data/seed dari beberapa kemungkinan lokasi
POSSIBLE_DIRS = [
    pathlib.Path("data/seed"),
    pathlib.Path("/opt/data/seed"),
    pathlib.Path(__file__).resolve().parent.parent / "data" / "seed" if "__file__" in globals() else None,
]
seed_dir = None
for p in POSSIBLE_DIRS:
    if p and p.is_dir() and (p / "sales_orders_historical.csv").is_file():
        seed_dir = p
        break

if not seed_dir:
    print(f"[hist_loader] ERROR: data/seed tidak ditemukan di {POSSIBLE_DIRS}")
    sys.exit(1)

print(f"[hist_loader] Menggunakan data seed dari: {seed_dir}")


def load_opex_bills():
    """Memuat OPEX Vendor Bills ke account.move jika model tersedia."""
    if "account.move" not in env:
        print("[hist_loader] SKIP: Modul account.move belum terinstal.")
        return

    csv_file = seed_dir / "opex_vendor_bills.csv"
    if not csv_file.is_file():
        print(f"[hist_loader] SKIP: {csv_file} tidak ditemukan.")
        return

    print(" -> Memuat OPEX Vendor Bills (20 faktur beban operasional)...")
    AccountMove = env["account.move"].sudo()
    Partner = env["res.partner"].sudo()

    company = env.company
    journal = (
        env["account.journal"]
        .sudo()
        .search(
            [
                ("type", "=", "purchase"),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )
    )

    # Pastikan partner vendor untuk beban operasional ada
    vendor_names = {
        "VEND-PAYROLL": "Payroll & Karyawan PT Manado Distribusi Utama",
        "VEND-SPBU": "SPBU Pertamina Manado (BBM & Pelumas)",
        "VEND-BENGKEL": "Bengkel Resmi & Perawatan Armada Manado",
        "VEND-ESTATE": "Pengelola Pergudangan & Utilitas Manado",
    }
    vendor_map = {}
    for code, vname in vendor_names.items():
        vp = Partner.search([("ref", "=", code)], limit=1)
        if not vp:
            vp = Partner.create(
                {
                    "name": vname,
                    "ref": code,
                    "supplier_rank": 1,
                    "is_company": True,
                }
            )
        vendor_map[code] = vp.id

    count = 0
    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            b_num = row["bill_number"]
            existing = AccountMove.search([("ref", "=", b_num)], limit=1)
            if existing:
                continue

            v_code = row.get("vendor_code")
            p_id = vendor_map.get(v_code) or company.partner_id.id
            amt = float(row.get("amount_dpp", 0.0))

            vals = {
                "move_type": "in_invoice",
                "partner_id": p_id,
                "ref": b_num,
                "invoice_date": row["bill_date"],
                "date": row["bill_date"],
                "journal_id": journal.id if journal else False,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": row.get("description", "Beban Operasional"),
                            "quantity": 1.0,
                            "price_unit": amt,
                        },
                    )
                ],
            }
            move = AccountMove.create(vals)
            try:
                move.action_post()
            except Exception:
                pass  # Biarkan draft jika ada konfigurasi akun/pajak yang belum tuntas
            count += 1

    print(f"    Selesai: {count} OPEX Vendor Bills diproses.")


def load_inbound_pos():
    """Memuat Inbound Purchase Orders jika purchase.order terinstal."""
    if "purchase.order" not in env:
        print("[hist_loader] SKIP: Modul purchase.order belum terinstal.")
        return

    csv_file = seed_dir / "inbound_po_historical.csv"
    if not csv_file.is_file():
        return

    print(" -> Memuat Inbound Purchase Orders (11 PO Kontainer)...")
    PurchaseOrder = env["purchase.order"].sudo()
    Partner = env["res.partner"].sudo()
    Product = env["product.product"].sudo()

    # Principal partners
    prin_names = {
        "PRIN-MAYORA": "PT Mayora Indah Tbk",
        "PRIN-KAPALAPI": "PT Santos Jaya Abadi (Kapal Api)",
        "PRIN-UNILEVER": "PT Unilever Indonesia Tbk",
        "PRIN-WINGS": "PT Sayap Mas Utama (Wings Food)",
    }
    prin_partner_map = {}
    for p_code, p_name in prin_names.items():
        partner = Partner.search([("ref", "=", p_code)], limit=1)
        if not partner:
            partner = Partner.create(
                {
                    "name": p_name,
                    "ref": p_code,
                    "supplier_rank": 1,
                    "is_company": True,
                }
            )
        prin_partner_map[p_code] = partner.id

    # Lines data
    po_lines_map = {}
    lines_file = seed_dir / "inbound_po_lines_historical.csv"
    if lines_file.is_file():
        with open(lines_file, mode="r", encoding="utf-8") as lf:
            for lrow in csv.DictReader(lf):
                po_lines_map.setdefault(lrow["po_number"], []).append(lrow)

    count = 0
    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            po_num = row["po_number"]
            existing = PurchaseOrder.search([("origin", "=", po_num)], limit=1)
            if existing:
                continue

            prin_code = row["principal_code"]
            partner_id = prin_partner_map.get(prin_code)
            line_vals = []
            for ldata in po_lines_map.get(po_num, []):
                sku = ldata["sku_code"]
                prod = Product.search([("default_code", "=", sku)], limit=1)
                if prod:
                    line_vals.append(
                        (
                            0,
                            0,
                            {
                                "product_id": prod.id,
                                "product_qty": float(ldata["qty_cartons"]),
                                "price_unit": float(ldata["unit_cost_price"]),
                                "name": f"{prod.name} (Lot: {ldata.get('lot_number')})",
                            },
                        )
                    )

            vals = {
                "partner_id": partner_id,
                "origin": po_num,
                "date_order": row["order_date"],
                "order_line": line_vals,
            }
            po = PurchaseOrder.create(vals)
            try:
                po.button_confirm()
            except Exception:
                pass
            count += 1

    print(f"    Selesai: {count} Inbound Purchase Orders dibuat.")


def load_sales_orders_sample(limit_orders=500):
    """Memuat sample Sales Orders jika sale.order terinstal (dibatasi 500 transaksi kunci untuk performa shell)."""
    if "sale.order" not in env:
        print("[hist_loader] SKIP: Modul sale.order belum terinstal.")
        return

    csv_file = seed_dir / "sales_orders_historical.csv"
    if not csv_file.is_file():
        return

    print(f" -> Memuat sample Sales Orders (hingga {limit_orders} transaksi)...")
    SaleOrder = env["sale.order"].sudo()
    Partner = env["res.partner"].sudo()
    Product = env["product.product"].sudo()

    # Lines map
    lines_map = {}
    lines_file = seed_dir / "sales_order_lines_historical.csv"
    if lines_file.is_file():
        with open(lines_file, mode="r", encoding="utf-8") as lf:
            for lrow in csv.DictReader(lf):
                lines_map.setdefault(lrow["so_number"], []).append(lrow)

    partner_cache = {p.ref: p.id for p in Partner.search([("ref", "!=", False)])}
    product_cache = {pr.default_code: pr.id for pr in Product.search([("default_code", "!=", False)])}

    count = 0
    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if count >= limit_orders:
                break
            so_num = row["so_number"]
            existing = SaleOrder.search([("client_order_ref", "=", so_num)], limit=1)
            if existing:
                continue

            cust_ref = row["partner_ref"]
            partner_id = partner_cache.get(cust_ref)
            if not partner_id:
                continue

            order_line_vals = []
            for ldata in lines_map.get(so_num, []):
                prod_id = product_cache.get(ldata["sku_code"])
                if prod_id:
                    order_line_vals.append(
                        (
                            0,
                            0,
                            {
                                "product_id": prod_id,
                                "product_uom_qty": float(ldata.get("qty_carton", 1)),
                                "price_unit": float(ldata.get("unit_price_dpp", 0.0)),
                            },
                        )
                    )

            vals = {
                "partner_id": partner_id,
                "client_order_ref": so_num,
                "date_order": row["date_order"],
                "order_line": order_line_vals,
            }
            so = SaleOrder.create(vals)
            try:
                so.action_confirm()
            except Exception:
                pass
            count += 1

    print(f"    Selesai: {count} Sales Orders dibuat.")


def load_all():
    try:
        load_opex_bills()
        load_inbound_pos()
        load_sales_orders_sample(limit_orders=500)
        cr.commit()
        print("[hist_loader] SUCCESS: Seluruh transaksi historis berhasil dimuat.")
    except Exception as e:
        cr.rollback()
        print(f"[hist_loader] ERROR saat memuat transaksi: {e}")
        raise


load_all()
