#!/usr/bin/env python3
"""Script loader seed data FMCG ke Odoo 19 via Odoo shell.

Dijalankan secara idempoten via:
    odoo shell -c /tmp/odoo.conf -d <dbname> --no-http < scripts/load_fmcg_seed.py
atau diimpor dalam Python script runner.
"""

import csv
import logging
import pathlib
import sys

_logger = logging.getLogger("fmcg_seed_loader")

# Pastikan objek env Odoo tersedia
env = globals().get("env")
if not env:
    print("[seed_loader] ERROR: Skrip ini harus dijalankan di dalam Odoo shell (objek 'env' tidak ditemukan).")
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
    if p and p.is_dir() and (p / "products_150.csv").is_file():
        seed_dir = p
        break

if not seed_dir:
    print(f"[seed_loader] ERROR: data/seed tidak ditemukan di {POSSIBLE_DIRS}")
    sys.exit(1)


def load_products():
    """Memuat 150 Master SKU FMCG ke product.template."""
    csv_file = seed_dir / "products_150.csv"
    if not csv_file.is_file():
        print(f"[seed_loader] SKIP: {csv_file} tidak ditemukan")
        return

    print(" -> Memuat Master SKU Produk (150 SKU)...")
    ProductTemplate = env["product.template"].sudo()
    Principal = env["id.principal"].sudo()
    Brand = env["id.brand"].sudo()
    Uom = env["uom.uom"].sudo()

    # Cache uom & master
    uom_unit = env.ref("uom.product_uom_unit", raise_if_not_found=False) or Uom.search([], limit=1)

    principal_map = {p.code: p.id for p in Principal.search([])}
    brand_map = {b.code: b.id for b in Brand.search([])}

    count_created = 0
    count_updated = 0

    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row["default_code"]
            name = row["name"]
            prin_code = row.get("principal_code")
            brand_code = row.get("brand_code")

            prin_id = principal_map.get(prin_code)
            brand_id = brand_map.get(brand_code)

            vals = {
                "name": name,
                "default_code": code,
                "fmcg_category": row.get("fmcg_category", "food"),
                "principal_id": prin_id,
                "brand_id": brand_id,
                "inner_qty": int(row.get("inner_qty", 1)),
                "carton_qty": int(row.get("carton_qty", 1)),
                "standard_price": float(row.get("cost_price", 0.0)),
                "list_price": float(row.get("list_price", 0.0)),
                "weight": float(row.get("weight_kg", 0.0)),
                "volume": float(row.get("volume_cbm", 0.0)),
                "barcode": row.get("barcode") or False,
                "description_sale": row.get("description", ""),
                "uom_id": uom_unit.id if uom_unit else False,
                "uom_po_id": uom_unit.id if uom_unit else False,
                "sale_ok": True,
                "purchase_ok": True,
            }

            prod = ProductTemplate.search([("default_code", "=", code)], limit=1)
            if prod:
                prod.write(vals)
                count_updated += 1
            else:
                ProductTemplate.create(vals)
                count_created += 1

    print(f"    Selesai: {count_created} dibuat, {count_updated} diperbarui.")


def load_partners():
    """Memuat 354 Partner Outlet ke res.partner."""
    csv_file = seed_dir / "partners_354.csv"
    if not csv_file.is_file():
        print(f"[seed_loader] SKIP: {csv_file} tidak ditemukan")
        return

    print(" -> Memuat Master Partner & Outlet (354 Outlet)...")
    Partner = env["res.partner"].sudo()
    Channel = env["id.channel"].sudo()
    Tier = env["id.tier"].sudo()
    District = env["id.district"].sudo()
    Subdistrict = env["id.subdistrict"].sudo()

    channel_map = {c.code: c.id for c in Channel.search([])}
    tier_map = {t.code: t.id for t in Tier.search([])}
    district_map = {d.code: d.id for d in District.search([])}
    subdistrict_map = {s.code: s.id for s in Subdistrict.search([])}

    count_created = 0
    count_updated = 0

    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ref = row["ref"]
            name = row["name"]
            channel_id = channel_map.get(row.get("channel_code"))
            tier_id = tier_map.get(row.get("tier_code"))
            district_id = district_map.get(row.get("district_code"))
            subdistrict_id = subdistrict_map.get(row.get("subdistrict_code"))

            vals = {
                "name": name,
                "ref": ref,
                "is_company": row.get("is_company", "True").lower() == "true",
                "customer_rank": 1,
                "channel_id": channel_id,
                "tier_id": tier_id,
                "district_id": district_id,
                "subdistrict_id": subdistrict_id,
                "street": row.get("street", ""),
                "zip": row.get("zip", ""),
                "vat": row.get("vat") or False,
                "credit_limit": float(row.get("credit_limit", 0.0)),
                "credit_mode": row.get("credit_mode", "strict"),
                "partner_latitude": float(row.get("latitude", 0.0)),
                "partner_longitude": float(row.get("longitude", 0.0)),
            }

            partner = Partner.search([("ref", "=", ref)], limit=1)
            if partner:
                partner.write(vals)
                count_updated += 1
            else:
                Partner.create(vals)
                count_created += 1

    print(f"    Selesai: {count_created} dibuat, {count_updated} diperbarui.")


def load_all():
    try:
        load_products()
        load_partners()
        cr.commit()
        print("[seed_loader] SUCCESS: Seluruh data master seed berhasil dimuat.")
    except Exception as e:
        cr.rollback()
        print(f"[seed_loader] ERROR saat memuat data: {e}")
        raise


load_all()
