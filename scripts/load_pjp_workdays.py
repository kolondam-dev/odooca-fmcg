#!/usr/bin/env python3
"""Loader Matriks PJP (Permanent Journey Plan), Workdays, & Visit Evidence ke Odoo.

Skrip idempoten ini:
1. Memperkaya master res.partner dengan pjp_call_day, pjp_frequency, dan delivery_route
   berdasarkan data/registers/customer_registry_354.csv.
2. Memuat penugasan harian salesman ke id.mobile.workday berdasarkan
   data/registers/pjp_july_2026_matrix.csv (Juli 2026).
3. Memuat bukti kunjungan lapangan ke id.mobile.evidence yang sinkron dengan
   transaksi penjualan (perpetual_sales_orders.csv) dan kunjungan rute.

Dapat dijalankan:
- Di dalam Odoo Shell:
    odoo shell -c /tmp/odoo.conf -d <dbname> --no-http < scripts/load_pjp_workdays.py
- Atau dieksekusi langsung oleh deploy/init.sh.
"""

import csv
import hashlib
import json
import logging
import pathlib
import uuid

_logger = logging.getLogger("pjp_workday_loader")

POSSIBLE_REG_DIRS = [
    pathlib.Path("data/registers"),
    pathlib.Path("/opt/data/registers"),
    pathlib.Path(__file__).resolve().parent.parent / "data" / "registers" if "__file__" in globals() else None,
]


def resolve_canonical_dir(candidate_dirs=None) -> pathlib.Path:
    dirs_to_check = candidate_dirs or POSSIBLE_REG_DIRS
    for candidate in dirs_to_check:
        if candidate and candidate.is_dir() and (candidate / "pjp_july_2026_matrix.csv").is_file():
            return candidate
    raise FileNotFoundError(
        f"[pjp_loader] FATAL: Direktori data/registers kanonikal tidak ditemukan di {dirs_to_check}."
    )


# Valid 1x1 base64 transparent JPEG
DUMMY_JPEG_B64 = (
    b"/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    b"wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
)

PJP_DAY_MAP = {
    "Senin": "monday", "Selasa": "tuesday", "Rabu": "wednesday",
    "Kamis": "thursday", "Jumat": "friday", "Sabtu": "saturday",
    "monday": "monday", "tuesday": "tuesday", "wednesday": "wednesday",
    "thursday": "thursday", "friday": "friday", "saturday": "saturday",
}

CANONICAL_SALESMEN_LOGINS = {
    "sls-01": "sls-01",
    "sls-02": "sls-02",
    "sls-03": "sls-03",
    "sls-04": "sls-04",
    "cvs-01": "cvs-01",
    "cvs-02": "cvs-02",
    "mgt-01": "mgt-01",
}


def run_pjp_workdays_loader(env):
    reg_dir = resolve_canonical_dir()
    print(f"[pjp_loader] Memulai pemuatan PJP & Workdays dari {reg_dir}...")

    cr = env.cr
    Partner = env["res.partner"].sudo()
    User = env["res.users"].sudo()
    Company = env["res.company"].sudo()
    Product = env["product.product"].sudo()

    company = Company.search([("name", "ilike", "Manado")], limit=1) or env.company or Company.browse(1)

    # -------------------------------------------------------------------------
    # 1. Pastikan Kolom PJP Tersedia di DB & Update Master res.partner
    # -------------------------------------------------------------------------
    cr.execute("""
        ALTER TABLE res_partner
        ADD COLUMN IF NOT EXISTS pjp_call_day varchar,
        ADD COLUMN IF NOT EXISTS pjp_frequency varchar,
        ADD COLUMN IF NOT EXISTS delivery_route varchar;
    """)

    cust_reg_file = reg_dir / "customer_registry_354.csv"
    if cust_reg_file.is_file():
        print(" -> Memperkaya data PJP pada 354 outlet (res.partner)...")
        updated_partners = 0
        with open(cust_reg_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ref = row.get("ref")
                if not ref:
                    continue
                day_val = PJP_DAY_MAP.get(row.get("pjp_call_day"), "monday")
                freq_val = row.get("pjp_frequency") or "F1"
                route_val = row.get("delivery_route") or ""
                cr.execute("""
                    UPDATE res_partner
                    SET pjp_call_day = %s, pjp_frequency = %s, delivery_route = %s
                    WHERE ref = %s
                """, [day_val, freq_val, route_val, ref])
                updated_partners += cr.rowcount
        print(f" -> Sukses memperbarui {updated_partners} record partner dengan atribut PJP.")

    # -------------------------------------------------------------------------
    # 2. Persiapan Pemetaan Salesman, Warehouse, Pricelist, dan Produk
    # -------------------------------------------------------------------------
    user_map = {}
    for u in User.search([]):
        user_map[u.login.lower()] = u.id

    admin_user = env.ref("base.user_admin", raise_if_not_found=False) or User.search([("id", "=", 2)], limit=1)

    def resolve_salesman_id(sls_str):
        code = sls_str.split(" - ")[0].strip().lower()
        if code in user_map:
            return user_map[code]
        # create user if missing
        parts = sls_str.split(" - ", 1)
        name = parts[1].strip() if len(parts) > 1 else code.upper()
        new_u = User.create({
            "name": name,
            "login": code,
            "email": f"{code}@manadodistribusi.co.id",
            "company_id": company.id,
            "company_ids": [(6, 0, [company.id])],
        })
        user_map[code] = new_u.id
        return new_u.id

    Warehouse = env["stock.warehouse"].sudo()
    wh = Warehouse.search([("company_id", "=", company.id)], limit=1)
    if not wh:
        wh = Warehouse.search([], limit=1)

    Pricelist = env["product.pricelist"].sudo()
    pl = Pricelist.search([
        ("currency_id.name", "=", "IDR"),
        "|", ("company_id", "=", company.id), ("company_id", "=", False)
    ], limit=1)
    if not pl:
        pl = Pricelist.search([], limit=1)

    # Active sale products (max 500)
    allowed_products = Product.search([
        ("sale_ok", "=", True),
        ("active", "=", True),
        "|", ("company_id", "=", company.id), ("company_id", "=", False)
    ], limit=300)
    product_ids = allowed_products.ids

    # Preload partner ref -> partner_id
    partner_ref_map = {}
    for p in Partner.search([("ref", "!=", False)]):
        partner_ref_map[p.ref] = p.id

    # -------------------------------------------------------------------------
    # 3. Muat Matriks PJP Juli 2026 ke id.mobile.workday
    # -------------------------------------------------------------------------
    pjp_matrix_file = reg_dir / "pjp_july_2026_matrix.csv"
    if not pjp_matrix_file.is_file():
        print(f"[pjp_loader] PERINGATAN: {pjp_matrix_file} tidak ditemukan.")
        return

    print(" -> Memuat jadwal PJP Juli 2026 ke id.mobile.workday...")
    with open(pjp_matrix_file, mode="r", encoding="utf-8") as f:
        pjp_rows = list(csv.DictReader(f))

    # Kelompokkan per (salesman, tanggal)
    workday_groups = {}
    visit_list = []
    for row in pjp_rows:
        sls = row["salesman"]
        tgl = row["tanggal"]
        cust_ref = row["customer"].split(" - ")[0].strip()
        pid = partner_ref_map.get(cust_ref)
        if not pid:
            continue
        uid = resolve_salesman_id(sls)
        key = (uid, tgl)
        workday_groups.setdefault(key, []).append(pid)
        visit_list.append({
            "user_id": uid,
            "date": tgl,
            "partner_id": pid,
            "cust_ref": cust_ref,
        })

    Workday = env["id.mobile.workday"].sudo().with_company(company) if "id.mobile.workday" in env else None
    if Workday is not None:
        created_wd = 0
        updated_wd = 0
        for (uid, tgl), outlets in workday_groups.items():
            existing = Workday.search([
                ("user_id", "=", uid),
                ("company_id", "=", company.id),
                ("business_date", "=", tgl),
            ], limit=1)
            # Batasi outlet per workday maksimal 500
            outlets_unique = list(dict.fromkeys(outlets))[:500]
            vals = {
                "active": True,
                "business_date": tgl,
                "user_id": uid,
                "company_id": company.id,
                "warehouse_id": wh.id,
                "pricelist_id": pl.id,
                "outlet_radius": 10,
                "outlet_ids": [(6, 0, outlets_unique)],
                "product_ids": [(6, 0, product_ids)],
            }
            if existing:
                existing.write(vals)
                updated_wd += 1
            else:
                Workday.create(vals)
                created_wd += 1
        print(
            f" -> id.mobile.workday: {created_wd} dibuat, {updated_wd} diperbarui "
            f"(Total {len(workday_groups)} jadwal harian salesman)."
        )

    # -------------------------------------------------------------------------
    # 4. Muat Bukti Kunjungan Lapangan ke id.mobile.evidence
    # -------------------------------------------------------------------------
    so_file = reg_dir / "perpetual_sales_orders.csv"
    ordered_visits = set()
    if so_file.is_file():
        with open(so_file, mode="r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ref = row["customer"].split(" - ")[0].strip()
                pid = partner_ref_map.get(ref)
                uid = resolve_salesman_id(row["salesman"])
                ordered_visits.add((uid, row["date_order"], pid))

    Evidence = env["id.mobile.evidence"].sudo() if "id.mobile.evidence" in env else None
    if Evidence is not None:
        print(" -> Menyelaraskan bukti kunjungan lapangan ke id.mobile.evidence...")
        # Kunjungan yang diverifikasi: Seluruh kunjungan efektif (dengan order) + subset zero-sale
        zero_sale_count = 0
        evidence_to_create = []

        for v in visit_list:
            v_key = (v["user_id"], v["date"], v["partner_id"])
            is_effective = v_key in ordered_visits
            should_record_visit = is_effective
            if not is_effective and zero_sale_count < 55:
                # Rekam sebagian zero-sale visits sebagai kunjungan terlaksana tapi tidak order
                should_record_visit = True
                zero_sale_count += 1

            if should_record_visit:
                evidence_to_create.append(v)

        # Cek bukti yang sudah ada
        cr.execute("SELECT client_uuid FROM id_mobile_evidence")
        existing_uuids = {r[0] for r in cr.fetchall()}

        admin_id = admin_user.id if admin_user else 1
        created_ev = 0
        for idx, ev_info in enumerate(evidence_to_create):
            uid = ev_info["user_id"]
            pid = ev_info["partner_id"]
            tgl = ev_info["date"]
            # Deterministic client_uuid
            cuuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"fmcg-visit-{uid}-{pid}-{tgl}"))
            if cuuid in existing_uuids:
                continue

            # Waktu kunjungan realistis (antara 08:30 s/d 14:00 WITA)
            hour = 8 + (idx % 6)
            minute = 10 + ((idx * 7) % 50)
            visit_timestamp_str = f"{tgl} {hour:02d}:{minute:02d}:00"

            meta = {
                "client_uuid": cuuid,
                "outlet_id": str(pid),
                "business_date": tgl,
                "snapshot_version": "v1-canonical-july-2026",
                "photo_selected_at": f"{tgl}T{hour:02d}:{minute:02d}:00Z",
                "device_recorded_at": f"{tgl}T{hour:02d}:{minute:02d}:05Z",
                "fix_sampled_at": f"{tgl}T{hour:02d}:{minute:02d}:02Z",
                "latitude": 1.482187,
                "longitude": 124.848921,
                "accuracy": 8.5,
            }
            fprint = hashlib.sha256(json.dumps(meta, sort_keys=True).encode() + DUMMY_JPEG_B64).hexdigest()

            cr.execute("""
                INSERT INTO id_mobile_evidence
                (user_id, company_id, outlet_id, client_uuid, fingerprint, receipt_json,
                 create_date, write_date, create_uid, write_uid)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, [
                uid, company.id, pid, cuuid, fprint, json.dumps(meta),
                visit_timestamp_str, visit_timestamp_str, admin_id, admin_id
            ])
            existing_uuids.add(cuuid)
            created_ev += 1

        print(f" -> id.mobile.evidence: {created_ev} bukti kunjungan lapangan berhasil di-insert.")

    env.cr.commit()
    print("[pjp_loader] Selesai: Seluruh matriks PJP, Workdays, dan Evidence berhasil diselaraskan.")


if "env" in globals():
    # Dijalankan langsung dalam Odoo shell
    run_pjp_workdays_loader(env)  # noqa: F821
