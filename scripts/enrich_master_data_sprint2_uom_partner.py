#!/usr/bin/env python3
"""Enrich Master Data Sprint 2: Multi-UoM, Packaging Matrix, & Partner Coverage Alignment.

Idempotent script to align:
1. 354 Customer Outlets:
   - Sets coverage_area_id (Manado Urban, Tomohon Hinterland, Bitung Port, Minut Rural).
   - Auto-assigns property_product_pricelist matching FMCG matrix (MT Discount 5%, GT Urban, Hinterland +2%).
2. 150 FMCG Products:
   - Sets 14 dimensions: Gramasi base (g), Rasio karton, P x L x T (cm), Vol ctn (m3), Berat base (kg),
     Berat ctn (kg), Barcode ctn.
3. Multi-UoM Packaging (product.packaging):
   - Sets up Carton (CTN) packaging for all 150 SKUs.
   - Sets up Inner/Renceng/Pack/Box packaging for multi-pack SKUs.
   - Links to stock.package.type and configures sales/purchase flags.
"""

import configparser
import csv
import os
import sys
from pathlib import Path
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
    cur.execute("SELECT id, channel_id, coverage_category FROM product_pricelist WHERE is_fmcg_matrix = TRUE;")
    pl_rows = cur.fetchall()
    # (channel_id, cov_category) -> pl_id
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

    # Get property field for property_product_pricelist
    cur.execute("SELECT id FROM ir_model_fields WHERE model = 'res.partner' AND name = 'property_product_pricelist';")
    ir_field_row = cur.fetchone()
    prop_field_id = ir_field_row[0] if ir_field_row else None

    # Read customer_registry_354.csv
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
            city = row.get("city", "Kota Manado")
            cov_id = city_to_area.get(city) or urban_id

            # Find partner
            cur.execute("SELECT id, channel_id, coverage_area_id FROM res_partner WHERE ref = %s LIMIT 1;", (ref,))
            p_row = cur.fetchone()
            if not p_row:
                continue

            partner_id, channel_id, existing_cov = p_row

            # Update coverage_area_id if not set or different
            if cov_id and existing_cov != cov_id:
                cur.execute("UPDATE res_partner SET coverage_area_id = %s WHERE id = %s;", (cov_id, partner_id))
                updated_coverage_count += 1

            # Determine best pricelist
            cov_category = "urban"
            if cov_id == hinterland_id:
                cov_category = "hinterland"
            elif cov_id == port_id:
                cov_category = "port"
            elif cov_id == rural_id:
                cov_category = "rural"

            target_pl = pl_map.get((channel_id, cov_category)) or channel_fallback_pl.get(channel_id) or default_pl_id

            if target_pl and prop_field_id:
                # Update ir_property or native field
                prop_val = f"product.pricelist,{target_pl}"
                cur.execute(
                    """
                    SELECT id FROM ir_property
                    WHERE name = 'property_product_pricelist'
                      AND res_id = %s
                      AND fields_id = %s
                    LIMIT 1;
                    """,
                    (f"res.partner,{partner_id}", prop_field_id),
                )
                prop_row = cur.fetchone()
                if prop_row:
                    cur.execute(
                        "UPDATE ir_property SET value_reference = %s WHERE id = %s;",
                        (prop_val, prop_row[0]),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO ir_property (name, res_id, company_id, fields_id, value_reference, type)
                        VALUES ('property_product_pricelist', %s, 1, %s, %s, 'many2one');
                        """,
                        (f"res.partner,{partner_id}", prop_field_id, prop_val),
                    )
                updated_pricelist_count += 1

    print(
        f" -> Selesai: {updated_coverage_count} coverage area diperbarui, "
        f"{updated_pricelist_count} matriks harga diselaraskan."
    )


def align_product_dimensions_and_packaging(cur, repo_root):
    print("--- 2. Menyelaraskan 14 Kolom Dimensi FMCG & Packaging 150 SKU ---")

    # Get package type IDs (CTN, RCG, PACK, BOX)
    cur.execute("SELECT id, name FROM stock_package_type;")
    pkg_type_map = {row[1].upper(): row[0] for row in cur.fetchall()}
    ctn_type_id = pkg_type_map.get("CTN") or pkg_type_map.get("KARTON")
    rcg_type_id = pkg_type_map.get("RCG") or pkg_type_map.get("RENCENG")
    pack_type_id = pkg_type_map.get("PACK") or pkg_type_map.get("BOX")

    csv_path = repo_root / "data" / "seed" / "products_150.csv"
    if not csv_path.exists():
        print(f"File {csv_path} tidak ditemukan, skip.")
        return

    updated_products = 0
    created_packaging = 0

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

            # Find product template
            cur.execute(
                """
                SELECT pt.id, pp.id, pt.uom_id
                FROM product_template pt
                LEFT JOIN product_product pp ON pp.product_tmpl_id = pt.id
                WHERE pt.default_code = %s
                LIMIT 1;
                """,
                (code,),
            )
            prod_row = cur.fetchone()
            if not prod_row:
                continue

            tmpl_id, variant_id, uom_id = prod_row

            # Update product_template dimensions
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
                WHERE id = %s;
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
                    tmpl_id,
                ),
            )
            updated_products += 1

            if not variant_id:
                continue

            # 1. Primary Packaging: Karton (CTN)
            base_uom_name = row.get("base_uom", "Pcs")
            if carton_qty > 1:
                cur.execute(
                    """
                    SELECT id FROM product_packaging
                    WHERE product_id = %s AND qty = %s
                    LIMIT 1;
                    """,
                    (variant_id, float(carton_qty)),
                )
                pkg_row = cur.fetchone()
                pkg_name = f"Karton ({carton_qty} {base_uom_name})"
                if pkg_row:
                    cur.execute(
                        """
                        UPDATE product_packaging
                        SET name = %s,
                            barcode = %s,
                            package_type_id = %s,
                            sales = TRUE,
                            purchase = TRUE
                        WHERE id = %s;
                        """,
                        (pkg_name, carton_barcode, ctn_type_id, pkg_row[0]),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO product_packaging
                            (name, product_id, qty, uom_id, barcode, package_type_id, sales, purchase)
                        VALUES (%s, %s, %s, %s, %s, %s, TRUE, TRUE);
                        """,
                        (pkg_name, variant_id, float(carton_qty), uom_id, carton_barcode, ctn_type_id),
                    )
                    created_packaging += 1

            # 2. Secondary Packaging: Inner / Renceng / Pack / Box (jika ada)
            if inner_qty > 1 and inner_qty < carton_qty:
                cur.execute(
                    """
                    SELECT id FROM product_packaging
                    WHERE product_id = %s AND qty = %s
                    LIMIT 1;
                    """,
                    (variant_id, float(inner_qty)),
                )
                inner_row = cur.fetchone()
                inner_name = f"Inner/Pack ({inner_qty} {base_uom_name})"
                type_id = rcg_type_id if base_uom_name in ["Sachet", "SCH"] else pack_type_id

                if inner_row:
                    cur.execute(
                        """
                        UPDATE product_packaging
                        SET name = %s,
                            package_type_id = %s,
                            sales = TRUE,
                            purchase = FALSE
                        WHERE id = %s;
                        """,
                        (inner_name, type_id, inner_row[0]),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO product_packaging (name, product_id, qty, uom_id, package_type_id, sales, purchase)
                        VALUES (%s, %s, %s, %s, %s, TRUE, FALSE);
                        """,
                        (inner_name, variant_id, float(inner_qty), uom_id, type_id),
                    )
                    created_packaging += 1

    print(f" -> Selesai: {updated_products} produk diperbarui, {created_packaging} packaging dibuat/diselaraskan.")


def main():
    repo_root = Path(__file__).resolve().parent.parent
    print("Memulai Sinkronisasi & Penyelarasan Master Data Sprint 2...")
    try:
        conn = get_db_connection()
        conn.autocommit = False
        with conn.cursor() as cur:
            align_partner_coverage_and_pricelists(cur, repo_root)
            align_product_dimensions_and_packaging(cur, repo_root)
            conn.commit()
            print("[SUCCESS] Seluruh data master multi-UoM, kemasan, dan partner coverage berhasil diperbarui 100%!")
    except Exception as e:
        print(f"[ERROR] Gagal menyelaraskan master data: {e}", file=sys.stderr)
        raise
    finally:
        if 'conn' in locals() and conn:
            conn.close()


if __name__ == "__main__":
    main()
