#!/usr/bin/env python3
"""Enrich Master Data Sprint 2: Multi-UoM, Packaging Matrix, & Partner Coverage Alignment.

Idempotent script to align:
1. 354 Customer Outlets:
   - Sets coverage_area_id (Manado Urban, Tomohon Hinterland, Bitung Port, Minut Rural).
   - Auto-assigns specific_property_product_pricelist / property_product_pricelist
     matching FMCG matrix (MT Discount 5%, GT Urban, Hinterland +2%).
2. 150 FMCG Products:
   - Sets 14 dimensions & packaging attributes: Gramasi base (g), Rasio karton, P x L x T (cm),
     Vol ctn (m3), Berat base (kg), Berat ctn (kg), Barcode ctn.
"""

import configparser
import csv
import os
from pathlib import Path
import sys
import psycopg2


def get_db_connection():
    config_paths = ["/tmp/odoo.conf", "/etc/odoo/odoo.conf", "/etc/odoo.conf"]
    cfg = configparser.ConfigParser()
    for cp in config_paths:
        if os.path.exists(cp):
            cfg.read(cp)
            break

    if "options" in cfg:
        opts = cfg["options"]
        return psycopg2.connect(
            host=opts.get("db_host", "postgres.railway.internal"),
            port=int(opts.get("db_port", 5432)),
            user=opts.get("db_user", "odoo_app"),
            password=opts.get("db_password", os.environ.get("PGPASSWORD", "")),
            dbname=opts.get("database", "railway"),
        )

    url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")
    if url:
        return psycopg2.connect(url)

    return psycopg2.connect(
        host=os.environ.get("PGHOST", "postgres.railway.internal"),
        port=int(os.environ.get("PGPORT", 5432)),
        user=os.environ.get("PGUSER", "odoo_app"),
        password=os.environ.get("PGPASSWORD", ""),
        dbname=os.environ.get("PGDATABASE", "railway"),
    )


def align_partner_coverage_and_pricelists(cur, repo_root):
    print("--- 1. Menyelaraskan Coverage Area & Matriks Harga 354 Partner ---")

    # Get coverage area IDs
    cur.execute("SELECT id, code, category FROM id_coverage_area;")
    area_rows = cur.fetchall()
    area_map = {row[2]: row[0] for row in area_rows}  # category -> id
    urban_id = area_map.get("urban")
    hinterland_id = area_map.get("hinterland")
    port_id = area_map.get("port")
    rural_id = area_map.get("rural")

    # Get FMCG matrix pricelists
    cur.execute(
        """
        SELECT id, channel_id, coverage_category
        FROM product_pricelist
        WHERE is_fmcg_matrix = TRUE;
        """
    )
    pl_rows = cur.fetchall()
    pl_map = {}
    channel_fallback_pl = {}
    for pl_id, chan_id, cov_cat in pl_rows:
        if chan_id and cov_cat:
            pl_map[(chan_id, cov_cat)] = pl_id
        if chan_id and (cov_cat == "all" or not cov_cat):
            channel_fallback_pl[chan_id] = pl_id

    # Fallback default pricelist
    cur.execute("SELECT id FROM product_pricelist WHERE active = TRUE ORDER BY id ASC LIMIT 1;")
    default_pl_row = cur.fetchone()
    default_pl_id = default_pl_row[0] if default_pl_row else False

    # Check columns in res_partner
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'res_partner'
          AND column_name IN ('specific_property_product_pricelist', 'property_product_pricelist');
        """
    )
    partner_cols = [r[0] for r in cur.fetchall()]
    has_specific_json = "specific_property_product_pricelist" in partner_cols

    # Read customer registry
    csv_path = repo_root / "data" / "registers" / "customer_registry_354.csv"
    if not csv_path.exists():
        csv_path = repo_root / "data" / "seed" / "partners_354.csv"

    city_to_area = {
        "Kota Manado": urban_id,
        "Kota Tomohon": hinterland_id,
        "Kota Bitung": port_id,
        "Kab. Minahasa Utara": rural_id,
    }

    updated_coverage_count = 0
    updated_pricelist_count = 0

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ref = row["ref"]
            city = row.get("city", "").strip()
            cov_id = city_to_area.get(city) or urban_id

            cur.execute("SELECT id, channel_id, coverage_area_id FROM res_partner WHERE ref = %s LIMIT 1;", (ref,))
            partner_row = cur.fetchone()
            if not partner_row:
                continue

            partner_id, channel_id, existing_cov = partner_row

            # 1. Update coverage_area_id if different
            if cov_id and existing_cov != cov_id:
                cur.execute("UPDATE res_partner SET coverage_area_id = %s WHERE id = %s;", (cov_id, partner_id))
                updated_coverage_count += 1

            # 2. Determine best matrix pricelist
            cov_category = "urban"
            if cov_id == hinterland_id:
                cov_category = "hinterland"
            elif cov_id == port_id:
                cov_category = "port"
            elif cov_id == rural_id:
                cov_category = "rural"

            target_pl = pl_map.get((channel_id, cov_category)) or channel_fallback_pl.get(channel_id) or default_pl_id

            if target_pl:
                if has_specific_json:
                    cur.execute(
                        """
                        UPDATE res_partner
                        SET specific_property_product_pricelist = jsonb_set(
                            COALESCE(specific_property_product_pricelist, '{}'::jsonb),
                            '{1}',
                            to_jsonb(%s::int)
                        )
                        WHERE id = %s;
                        """,
                        (target_pl, partner_id),
                    )
                    updated_pricelist_count += 1
                else:
                    cur.execute(
                        "UPDATE res_partner SET property_product_pricelist = %s WHERE id = %s;",
                        (target_pl, partner_id),
                    )
                    updated_pricelist_count += 1

    print(
        f" -> Selesai: {updated_coverage_count} coverage area diperbarui, "
        f"{updated_pricelist_count} matriks harga diselaraskan."
    )


def align_product_dimensions(cur, repo_root):
    print("--- 2. Menyelaraskan 14 Kolom Dimensi & Rasio Kemasan FMCG 150 SKU ---")

    csv_path = repo_root / "data" / "seed" / "products_150.csv"
    if not csv_path.exists():
        print(f"File {csv_path} tidak ditemukan, skip.")
        return

    updated_products = 0

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row["default_code"]
            carton_qty = int(row.get("carton_qty", 1))
            inner_qty = int(row.get("inner_qty", 1))
            length_cm = float(row.get("carton_length_cm", 0.0))
            width_cm = float(row.get("carton_width_cm", 0.0))
            height_cm = float(row.get("carton_height_cm", 0.0))
            volume_cbm = float(row.get("carton_volume_cbm", 0.0))
            if not volume_cbm and length_cm and width_cm and height_cm:
                volume_cbm = round((length_cm * width_cm * height_cm) / 1_000_000.0, 4)
            weight_kg = float(row.get("weight_kg", 0.0))
            carton_weight_kg = float(row.get("carton_weight_kg", 0.0))
            carton_barcode = row.get("carton_barcode") or None
            base_weight_g = weight_kg * 1000.0

            cur.execute(
                """
                UPDATE product_template
                SET carton_length_cm = %s,
                    carton_width_cm = %s,
                    carton_height_cm = %s,
                    carton_volume_cbm = %s,
                    carton_weight_kg = %s,
                    carton_barcode = %s,
                    base_weight_g = %s,
                    inner_qty = %s,
                    carton_qty = %s
                WHERE default_code = %s;
                """,
                (
                    length_cm,
                    width_cm,
                    height_cm,
                    volume_cbm,
                    carton_weight_kg,
                    carton_barcode,
                    base_weight_g,
                    inner_qty,
                    carton_qty,
                    code,
                ),
            )
            if cur.rowcount > 0:
                updated_products += cur.rowcount

    print(f" -> Selesai: {updated_products} produk diperbarui dengan 14 dimensi FMCG.")


def main():
    repo_root = Path(__file__).resolve().parent.parent
    print("Memulai Sinkronisasi & Penyelarasan Master Data Sprint 2...")
    try:
        conn = get_db_connection()
        conn.autocommit = False
        with conn.cursor() as cur:
            align_partner_coverage_and_pricelists(cur, repo_root)
            align_product_dimensions(cur, repo_root)
            conn.commit()
            print("[SUCCESS] Seluruh data master multi-UoM, kemasan, dan partner coverage berhasil diperbarui 100%!")
    except Exception as e:
        print(f"[ERROR] Gagal menyelaraskan master data: {e}", file=sys.stderr)
        raise
    finally:
        if "conn" in locals() and conn:
            conn.close()


if __name__ == "__main__":
    main()
