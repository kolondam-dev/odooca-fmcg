#!/usr/bin/env python3
"""Enrich Master Data Sprint 1 for PT Manado Distribusi Utama (MDU).

Populates:
1. Bank Master Data (res.bank, res.partner.bank) for Company, Principals, Employees, and Key Customers.
2. Outlet Child PIC Contacts (res.partner) for all 354 active FMCG outlets.
3. 9 Internal Physical Warehouse Sections (stock.location) under Maumbi Warehouse.
4. Packaging Types (stock.package.type) for Carton, Box, Pack, Renceng, Dus.

All actions are 100% additive, idempotent, and non-destructive.
"""

import configparser
import os
import random
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

    # Fallback to standard environment variables
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


def enrich_banks(cur):
    print("--- 1. Enriching Banks & Bank Accounts ---")
    banks = [
        ("Bank Central Asia (BCA)", "CENAIDJA"),
        ("Bank Mandiri", "BMRIIDJA"),
        ("Bank Rakyat Indonesia (BRI)", "BRINIDJA"),
        ("Bank Negara Indonesia (BNI)", "BNINIDJA"),
        ("Bank SulutGo (BSG)", "BSLGIDJA"),
        ("Bank Danamon", "BDINIDJA"),
        ("Bank Permata", "BBBAIDJA"),
        ("Citibank Indonesia", "CITIIDJA"),
    ]

    bank_ids = {}
    for name, bic in banks:
        cur.execute("SELECT id FROM res_bank WHERE bic = %s OR name = %s;", (bic, name))
        row = cur.fetchone()
        if row:
            bank_ids[bic] = row[0]
        else:
            cur.execute(
                """
                INSERT INTO res_bank (name, bic, active, create_date, write_date)
                VALUES (%s, %s, true, NOW(), NOW())
                RETURNING id;
                """,
                (name, bic),
            )
            bank_ids[bic] = cur.fetchone()[0]
            print(f"  + Created bank: {name} ({bic})")

    # Bank Accounts mapping: (partner_search_clause, params, acc_number, bic, holder_name)
    accounts = [
        # Company
        ("name ILIKE %s", ("%Manado Distribusi Utama%",), "026-888-1234", "CENAIDJA", "PT Manado Distribusi Utama"),
        ("name ILIKE %s", ("%Manado Distribusi Utama%",), "150-00-9876543-2", "BMRIIDJA", "PT Manado Distribusi Utama"),
        ("name ILIKE %s", ("%Manado Distribusi Utama%",), "001-01-99887-1", "BSLGIDJA", "PT Manado Distribusi Utama"),
        # Principals / Vendors
        ("name ILIKE %s", ("%Mayora%",), "088-234-5678", "CENAIDJA", "PT Mayora Indah Tbk"),
        ("name ILIKE %s", ("%Santos%",), "011-876-5432", "CENAIDJA", "PT Santos Jaya Abadi"),
        ("name ILIKE %s", ("%Unilever%",), "102-00-1122334-5", "BMRIIDJA", "PT Unilever Indonesia Tbk"),
        ("name ILIKE %s", ("%Wings%",), "066-778-8990", "CENAIDJA", "PT Sayap Mas Utama"),
        ("name ILIKE %s", ("%Indofood%",), "122-00-5544332-1", "BMRIIDJA", "PT Indofood CBP Sukses Makmur Tbk"),
        ("name ILIKE %s", ("%Danone%Tirta%",), "001-998-8776", "CENAIDJA", "PT Tirta Investama"),
        ("name ILIKE %s", ("%Frisian Flag%",), "103-00-8877665-4", "BMRIIDJA", "PT Frisian Flag Indonesia"),
        ("name ILIKE %s", ("%Ultra Jaya%",), "008-776-6554", "CENAIDJA", "PT Ultra Jaya Milk Industry Tbk"),
        ("name ILIKE %s", ("%ABC President%",), "071-223-3445", "CENAIDJA", "PT ABC President Indonesia"),
        ("name ILIKE %s", ("%Nestle%",), "101-00-6655443-2", "BMRIIDJA", "PT Nestle Indonesia"),
        ("name ILIKE %s", ("%Forisa%",), "084-556-6778", "CENAIDJA", "PT Forisa Nusapersada"),
        ("name ILIKE %s", ("%Kalbe Farma%",), "106-00-4433221-9", "BMRIIDJA", "PT Kalbe Farma Tbk"),
        # Key Customers
        ("name ILIKE %s", ("%Indomaret%DC%",), "026-900-1122", "CENAIDJA", "PT Indomarco Prismatama DC"),
        ("name ILIKE %s", ("%Alfamidi%DC%",), "026-900-3344", "CENAIDJA", "PT Midi Utama Indonesia DC"),
        ("name ILIKE %s", ("%FreshMart%Bahu%",), "001-01-55667-8", "BSLGIDJA", "FreshMart Bahu Manado"),
        ("name ILIKE %s", ("%Jumbo Swalayan%",), "026-445-5667", "CENAIDJA", "Jumbo Swalayan Manado"),
        ("name ILIKE %s", ("%Sembako Berkat Pasar 45%",), "005-01-002233-50-1", "BRINIDJA", "Toko Sembako Berkat"),
        # Employees
        ("name ILIKE %s", ("%Andre%",), "001-02-12345-6", "BSLGIDJA", "Andre - Salesman Urban"),
        ("name ILIKE %s", ("%Novry%",), "001-02-23456-7", "BSLGIDJA", "Novry Mandagi - Driver Canvass"),
        ("name ILIKE %s", ("%Steven%",), "001-02-34567-8", "BSLGIDJA", "Steven Lumenta - Canvasser"),
        ("name ILIKE %s", ("%Christian Wowor%",), "026-112-2334", "CENAIDJA", "Christian Wowor - MT Sales"),
        ("name ILIKE %s", ("%Boyke Tendean%",), "150-00-4455667-1", "BMRIIDJA", "Boyke Tendean - Logistik"),
    ]

    created_accounts = 0
    for clause, params, acc_no, bic, holder in accounts:
        cur.execute(f"SELECT id FROM res_partner WHERE {clause} LIMIT 1;", params)
        partner_row = cur.fetchone()
        if not partner_row:
            continue
        partner_id = partner_row[0]
        bank_id = bank_ids.get(bic)

        cur.execute("SELECT id FROM res_partner_bank WHERE acc_number = %s;", (acc_no,))
        if cur.fetchone():
            continue

        cur.execute(
            """
            INSERT INTO res_partner_bank (
                acc_number, partner_id, bank_id, acc_holder_name, company_id, active, create_date, write_date
            ) VALUES (%s, %s, %s, %s, 1, true, NOW(), NOW());
            """,
            (acc_no, partner_id, bank_id, holder),
        )
        created_accounts += 1

    print(f"  ✓ Bank accounts created: {created_accounts}")


def enrich_outlet_pic_contacts(cur):
    print("--- 2. Enriching Outlet Child PIC Contacts ---")
    cur.execute(
        """
        SELECT id, name, phone, street, city
        FROM res_partner
        WHERE customer_rank > 0 AND parent_id IS NULL
        ORDER BY id;
        """
    )
    outlets = cur.fetchall()
    print(f"  Found {len(outlets)} parent customer outlets.")

    first_names_male = [
        "Erwin", "Benny", "Royke", "Hengky", "Utu", "Dani", "Jopie", "Frits",
        "Stenly", "David", "Johan", "Agus", "Welly", "Ferry", "Ronny", "Teddy",
    ]
    first_names_female = [
        "Meilani", "Marlina", "Elsje", "Sandra", "Tin", "Meyke", "Shirley", "Jenny",
        "Grace", "Debby", "Vicky", "Linda", "Paula", "Fanny", "Astrid",
    ]
    family_names = [
        "Tanod", "Wijaya", "Wenas", "Kumendong", "Lumenta", "Pongoh", "Runtuwene",
        "Mandagi", "Tendean", "Kandou", "Kalasuat", "Supit", "Rori", "Rompas",
        "Kalalo", "Pangemanan",
    ]

    created_pics = 0
    rng = random.Random(42)  # Deterministic seed for repeatable demo data

    for outlet_id, outlet_name, _phone, _street, _city in outlets:
        cur.execute("SELECT count(*) FROM res_partner WHERE parent_id = %s AND type = 'contact';", (outlet_id,))
        if cur.fetchone()[0] > 0:
            continue

        is_mt = any(kw in outlet_name for kw in ["DC", "Supermarket", "Swalayan", "FreshMart", "MultiMart"])
        is_gt = any(kw in outlet_name for kw in ["Grosir", "Toko", "Sembako"])

        if is_mt:
            gender = rng.choice(["M", "F"])
            fn = rng.choice(first_names_male if gender == "M" else first_names_female)
            ln = rng.choice(family_names)
            title = "Pak" if gender == "M" else "Ibu"
            pic_name = f"{title} {fn} {ln}"
            function = rng.choice([
                "Store Manager", "Kepala Toko", "Purchasing & Receiving DC", "Supervisor Merchandiser"
            ])
        elif is_gt:
            gender = rng.choice(["M", "F"])
            fn = rng.choice(first_names_male if gender == "M" else first_names_female)
            ln = rng.choice(family_names)
            prefix = "Ko" if gender == "M" else "Ci"
            pic_name = f"{prefix} {fn} {ln}"
            function = rng.choice(["Owner / Pemilik Toko", "Penanggung Jawab Toko", "Kepala Gudang & Kasir"])
        else:
            gender = rng.choice(["M", "F"])
            fn = rng.choice(first_names_male if gender == "M" else first_names_female)
            if gender == "M":
                prefix = "Om" if fn in ["Utu", "Dani", "Jopie"] else "Pak"
            else:
                prefix = "Tante" if fn in ["Tin", "Marlina", "Meyke"] else "Ibu"
            pic_name = f"{prefix} {fn}"
            function = "Pemilik Kios / Warung"

        rand_digits = rng.randint(1000, 9999)
        pic_phone = f"+62 8{rng.choice(['11', '12', '13', '52', '21'])}-{rng.randint(400, 999)}-{rand_digits}"

        cur.execute(
            """
            INSERT INTO res_partner (
                name, parent_id, type, function, phone,
                company_id, active, customer_rank, supplier_rank,
                autopost_bills, group_rfq, group_on,
                create_date, write_date
            ) VALUES (%s, %s, 'contact', %s, %s, 1, true, 0, 0, 'ask', 'default', 'default', NOW(), NOW());
            """,
            (pic_name, outlet_id, function, pic_phone),
        )
        created_pics += 1

    print(f"  ✓ Outlet PIC contacts created: {created_pics}")


def enrich_warehouse_locations(cur):
    print("--- 3. Enriching 9 Maumbi Internal Warehouse Sections ---")
    cur.execute("SELECT id FROM stock_location WHERE complete_name = 'WH/Stock' LIMIT 1;")
    stock_parent = cur.fetchone()
    if not stock_parent:
        cur.execute("SELECT id FROM stock_location WHERE usage = 'internal' AND location_id IS NULL LIMIT 1;")
        stock_parent = cur.fetchone()

    parent_id = stock_parent[0]

    sections = [
        ("GD-MND/UTAMA", "Gudang Utama Pallet & Bulk Stock", "WH/Stock/GD-MND/UTAMA"),
        ("GD-MND/EACHES", "Area Pecahan / Eaches Picking", "WH/Stock/GD-MND/EACHES"),
        ("GD-MND/RETURN-STAGING", "Staging Area Retur Toko Masuk", "WH/Stock/GD-MND/RETURN-STAGING"),
        ("GD-MND/BAD-STOCK", "Karantina Bad Stock & Rusak", "WH/Stock/GD-MND/BAD-STOCK"),
        ("GD-MND/PROMO", "Staging POSM & Hadiah Promosi", "WH/Stock/GD-MND/PROMO"),
        ("GD-MND/PREMIUM", "Gudang High-Value FMCG Terkunci", "WH/Stock/GD-MND/PREMIUM"),
        ("GD-MND/COLD", "Cool Storage Dairy & Chocolate", "WH/Stock/GD-MND/COLD"),
        ("GD-MND/DOCK", "Loading Dock Inbound & Outbound", "WH/Stock/GD-MND/DOCK"),
        ("GD-MND/IN-TRANSIT", "Transit Antar Gudang / Delivery Truck", "WH/Stock/GD-MND/IN-TRANSIT"),
    ]

    created_locs = 0
    for code, _desc, comp_name in sections:
        cur.execute("SELECT id FROM stock_location WHERE name = %s AND location_id = %s;", (code, parent_id))
        if cur.fetchone():
            continue

        cur.execute(
            """
            INSERT INTO stock_location (
                name, complete_name, usage, location_id, company_id, active, create_date, write_date
            ) VALUES (%s, %s, 'internal', %s, 1, true, NOW(), NOW());
            """,
            (code, comp_name, parent_id),
        )
        created_locs += 1

    print(f"  ✓ Physical warehouse locations created: {created_locs}")


def enrich_stock_package_types(cur):
    print("--- 4. Enriching Stock Package Types ---")
    pkg_types = [
        ("CTN - Karton Standar FMCG", "CTN", 40.0, 30.0, 25.0, 15.0),
        ("BOX - Inner Box Display", "BOX", 25.0, 18.0, 15.0, 5.0),
        ("PACK - Polybag Pack", "PACK", 18.0, 12.0, 8.0, 2.0),
        ("RCG - Hanging Strip Renceng", "RCG", 35.0, 8.0, 4.0, 0.5),
        ("DUS - Corrugated Master Box", "DUS", 45.0, 35.0, 30.0, 20.0),
    ]

    created_pkgs = 0
    for name, barcode, length, width, height, max_w in pkg_types:
        cur.execute("SELECT id FROM stock_package_type WHERE barcode = %s OR name = %s;", (barcode, name))
        if cur.fetchone():
            continue

        cur.execute(
            """
            INSERT INTO stock_package_type (
                name, barcode, package_use, packaging_length, width,
                height, max_weight, base_weight, company_id,
                create_date, write_date
            ) VALUES (%s, %s, 'reusable', %s, %s, %s, %s, 0.2, 1, NOW(), NOW());
            """,
            (name, barcode, length, width, height, max_w),
        )
        created_pkgs += 1

    print(f"  ✓ Stock package types created: {created_pkgs}")


def main():
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        enrich_banks(cur)
        enrich_outlet_pic_contacts(cur)
        enrich_warehouse_locations(cur)
        enrich_stock_package_types(cur)
        conn.commit()
        print("🎉 ALL SPRINT 1 MASTER DATA ENRICHMENTS COMMITTED SUCCESSFULLY!")
    except Exception as e:
        conn.rollback()
        print(f"❌ Error during enrichment: {e}", file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
