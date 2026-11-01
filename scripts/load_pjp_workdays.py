#!/usr/bin/env python3
"""Loader Matriks PJP (Permanent Journey Plan), Workdays, & Visit Evidence ke Odoo.

Skrip idempoten ini:
1. Memverifikasi ketersediaan modul id_mobile_api (fail-fast jika model belum terpasang).
2. Memperkaya master res.partner dengan pjp_call_day, pjp_frequency, dan delivery_route
   berdasarkan data/registers/customer_registry_354.csv dengan isolasi multi-company.
3. Memuat penugasan harian salesman ke id.mobile.workday berdasarkan
   data/registers/pjp_july_2026_matrix.csv (Juli 2026).
4. Memuat bukti kunjungan lapangan ke id.mobile.evidence yang sinkron dengan
   transaksi penjualan (perpetual_sales_orders.csv) dan kunjungan rute, lengkap dengan
   attachment foto asli yang valid serta watermark khusus demo per kunjungan.

Dapat dijalankan:
- Di dalam Odoo Shell:
    odoo shell -c /tmp/odoo.conf -d <dbname> --no-http < scripts/load_pjp_workdays.py
- Atau dieksekusi langsung oleh deploy/init.sh.
"""

import base64
import csv
import hashlib
import io
import json
import logging
import pathlib
import uuid
import warnings

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    Image = ImageDraw = ImageFont = ImageOps = None

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


# Fallback minimal JPEG bytes (valid JPEG 1x1 header-trailer) bila PIL tidak tersedia di CLI host
MINIMAL_VALID_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08"
    b"\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' \",#"
    b"\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00"
    b"\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff"
    b"\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x80\xff\xd9"
)


def get_or_create_sample_fmcg_photo() -> bytes:
    """Menghasilkan contoh foto JPEG toko FMCG yang valid sebagai base photo kunjungan."""
    if Image is None:
        return MINIMAL_VALID_JPEG_BYTES

    stream = io.BytesIO()
    img = Image.new("RGB", (640, 480), "#1e293b")
    draw = ImageDraw.Draw(img)

    # Frame toko & display
    draw.rectangle([16, 16, 624, 464], outline="#38bdf8", width=3)
    draw.rectangle([16, 16, 624, 76], fill="#0f172a")

    # Rak produk FMCG
    for y in [160, 260, 360]:
        draw.line([(30, y), (610, y)], fill="#94a3b8", width=4)
        for x in range(45, 590, 68):
            draw.rectangle([x, y - 56, x + 48, y - 2], fill="#f59e0b", outline="#b45309", width=2)

    try:
        font = ImageFont.load_default(size=18)
    except TypeError:
        font = ImageFont.load_default()

    draw.text((36, 32), "FMCG STORE DISPLAY & MERCHANDISING (MANADO)", fill="#f8fafc", font=font)
    img.save(stream, format="JPEG", quality=85)
    return stream.getvalue()


def render_historical_watermark(
    source_bytes: bytes,
    outlet_ref: str,
    outlet_name: str,
    salesman_name: str,
    salesman_login: str,
    visit_timestamp_str: str,
    lat: float,
    lon: float,
    acc: float,
    client_uuid: str,
) -> bytes:
    """Menghasilkan foto JPEG ber-watermark per kunjungan dengan label resmi data demo."""
    if Image is None:
        return MINIMAL_VALID_JPEG_BYTES

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with Image.open(io.BytesIO(source_bytes)) as photo:
            photo = ImageOps.exif_transpose(photo).convert("RGB")
            photo.thumbnail((1280, 1280))

            footer_height = 145
            canvas = Image.new("RGB", (max(640, photo.width), photo.height + footer_height), "#0b192c")
            canvas.paste(photo, ((canvas.width - photo.width) // 2, 0))
            draw = ImageDraw.Draw(canvas)

            # Garis pemisah foto dan panel watermark
            draw.line([(0, photo.height), (canvas.width, photo.height)], fill="#38bdf8", width=3)

            lines = [
                ("DATA AWAL DEMO — FOTO ILUSTRASI (INJECT HISTORIS JULI 2026)", "#facc15"),
                (f"OUTLET: [{outlet_ref}] {outlet_name[:40]}", "#ffffff"),
                (f"PETUGAS: {salesman_name} ({salesman_login})", "#ffffff"),
                (f"WAKTU KUNJUNGAN: {visit_timestamp_str} WITA", "#ffffff"),
                (f"GPS: {lat:.6f}, {lon:.6f} +/- {acc:.1f} m (GEOFENCE TERVALIDASI)", "#93c5fd"),
                (f"UUID BUKTI: {client_uuid}", "#94a3b8"),
            ]

            try:
                font = ImageFont.load_default(size=13)
            except TypeError:
                font = ImageFont.load_default()

            y_pos = photo.height + 8
            for text, color in lines:
                draw.text((12, y_pos), text, fill=color, font=font)
                y_pos += 22

            result = io.BytesIO()
            canvas.save(result, format="JPEG", quality=85)
            return result.getvalue()


def run_pjp_workdays_loader(env, max_evidence_limit=None):
    # -------------------------------------------------------------------------
    # 0. Verifikasi Kesiapan Modul & Model (Fail-Fast: Mencegah Sukses Palsu)
    # -------------------------------------------------------------------------
    required_models = ["id.mobile.workday", "id.mobile.evidence"]
    missing_models = [m for m in required_models if m not in env]
    if missing_models:
        raise RuntimeError(
            f"[pjp_loader] FATAL: Model {missing_models} belum terpasang di registry Odoo. "
            f"Pemuatan PJP Workdays dan Evidence dibatalkan agar tidak terjadi false success. "
            f"Pastikan modul 'id_mobile_api' telah terpasang sebelum menjalankan loader ini."
        )

    reg_dir = resolve_canonical_dir()
    print(f"[pjp_loader] Memulai pemuatan PJP & Workdays dari {reg_dir}...")

    cr = env.cr
    Partner = env["res.partner"].sudo()
    User = env["res.users"].sudo()
    Company = env["res.company"].sudo()
    Product = env["product.product"].sudo()

    company = Company.search([("name", "ilike", "Manado")], limit=1) or env.company or Company.browse(1)

    # -------------------------------------------------------------------------
    # 1. Pastikan Kolom PJP Tersedia di DB & Update Master res.partner (Multi-Company Safe)
    # -------------------------------------------------------------------------
    cr.execute("""
        ALTER TABLE res_partner
        ADD COLUMN IF NOT EXISTS pjp_call_day varchar,
        ADD COLUMN IF NOT EXISTS pjp_frequency varchar,
        ADD COLUMN IF NOT EXISTS delivery_route varchar;
    """)

    cust_reg_file = reg_dir / "customer_registry_354.csv"
    if cust_reg_file.is_file():
        print(f" -> Memperkaya data PJP pada 354 outlet (res.partner) untuk Company ID {company.id}...")
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

                # Scope update HANYA pada partner milik company target atau partner shared
                cr.execute("""
                    UPDATE res_partner
                    SET pjp_call_day = %s, pjp_frequency = %s, delivery_route = %s
                    WHERE ref = %s AND (company_id = %s OR company_id IS NULL)
                """, [day_val, freq_val, route_val, ref, company.id])
                updated_partners += cr.rowcount
        print(f" -> Sukses memperbarui {updated_partners} record partner dengan atribut PJP.")

    # -------------------------------------------------------------------------
    # 2. Persiapan Pemetaan Salesman, Warehouse, Pricelist, dan Produk
    # -------------------------------------------------------------------------
    user_map = {}
    user_obj_map = {}
    for u in User.search([]):
        user_map[u.login.lower()] = u.id
        user_obj_map[u.id] = u

    def resolve_salesman_id(sls_str):
        code = sls_str.split(" - ")[0].strip().lower()
        if code in user_map:
            return user_map[code]
        # Buat user jika belum ada
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
        user_obj_map[new_u.id] = new_u
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

    allowed_products = Product.search([
        ("sale_ok", "=", True),
        ("active", "=", True),
        "|", ("company_id", "=", company.id), ("company_id", "=", False)
    ], limit=300)
    product_ids = allowed_products.ids

    # Preload partner ref -> partner record (terisolasi ke company target)
    partner_ref_map = {}
    for p in Partner.search([
        ("ref", "!=", False),
        "|", ("company_id", "=", company.id), ("company_id", "=", False)
    ]):
        partner_ref_map[p.ref] = p

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

    workday_groups = {}
    visit_list = []
    for row in pjp_rows:
        sls = row["salesman"]
        tgl = row["tanggal"]
        cust_ref = row["customer"].split(" - ")[0].strip()
        partner_rec = partner_ref_map.get(cust_ref)
        if not partner_rec:
            continue
        uid = resolve_salesman_id(sls)
        key = (uid, tgl)
        workday_groups.setdefault(key, []).append(partner_rec.id)
        visit_list.append({
            "user_id": uid,
            "date": tgl,
            "partner_id": partner_rec.id,
            "partner_rec": partner_rec,
            "cust_ref": cust_ref,
        })

    Workday = env["id.mobile.workday"].sudo().with_company(company)
    created_wd = 0
    updated_wd = 0
    workday_id_map = {}

    Office = env["id.mobile.office"].sudo() if "id.mobile.office" in env else None
    office_rec = Office.search([("company_id", "=", company.id), ("active", "=", True)], limit=1) if Office else None
    if not office_rec and Office:
        office_rec = Office.search([("active", "=", True)], limit=1)

    for (uid, tgl), outlets in workday_groups.items():
        existing = Workday.search([
            ("user_id", "=", uid),
            ("company_id", "=", company.id),
            ("business_date", "=", tgl),
        ], limit=1)
        outlets_unique = list(dict.fromkeys(outlets))[:500]
        vals = {
            "active": True,
            "business_date": tgl,
            "user_id": uid,
            "company_id": company.id,
            "warehouse_id": wh.id,
            "pricelist_id": pl.id,
            "outlet_radius": 10,
            "office_id": office_rec.id if office_rec else False,
            "outlet_ids": [(6, 0, outlets_unique)],
            "product_ids": [(6, 0, product_ids)],
        }
        if existing:
            existing.write(vals)
            updated_wd += 1
            workday_id_map[(uid, tgl)] = existing.id
        else:
            new_wd = Workday.create(vals)
            created_wd += 1
            workday_id_map[(uid, tgl)] = new_wd.id

    print(
        f" -> id.mobile.workday: {created_wd} dibuat, {updated_wd} diperbarui "
        f"(Total {len(workday_groups)} jadwal harian salesman)."
    )

    # -------------------------------------------------------------------------
    # 4. Muat Bukti Kunjungan Lapangan ke id.mobile.evidence Lengkap dengan Foto & Watermark
    # -------------------------------------------------------------------------
    so_file = reg_dir / "perpetual_sales_orders.csv"
    ordered_visits = set()
    if so_file.is_file():
        with open(so_file, mode="r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ref = row["customer"].split(" - ")[0].strip()
                p_rec = partner_ref_map.get(ref)
                if p_rec:
                    uid = resolve_salesman_id(row["salesman"])
                    ordered_visits.add((uid, row["date_order"], p_rec.id))

    Evidence = env["id.mobile.evidence"].sudo()
    print(" -> Menyelaraskan bukti kunjungan lapangan ke id.mobile.evidence dengan foto & watermark...")

    zero_sale_count = 0
    evidence_to_create = []

    for v in visit_list:
        v_key = (v["user_id"], v["date"], v["partner_id"])
        is_effective = v_key in ordered_visits
        should_record_visit = is_effective
        if not is_effective and zero_sale_count < 55:
            should_record_visit = True
            zero_sale_count += 1

        if should_record_visit:
            evidence_to_create.append(v)

    if max_evidence_limit:
        evidence_to_create = evidence_to_create[:max_evidence_limit]

    # Ambil sample photo base yang valid
    sample_source_photo = get_or_create_sample_fmcg_photo()
    original_sha256 = hashlib.sha256(sample_source_photo).hexdigest()
    original_b64 = base64.b64encode(sample_source_photo)

    created_ev = 0
    healed_ev = 0

    for idx, ev_info in enumerate(evidence_to_create):
        uid = ev_info["user_id"]
        pid = ev_info["partner_id"]
        tgl = ev_info["date"]
        p_rec = ev_info["partner_rec"]
        u_rec = user_obj_map.get(uid) or User.browse(uid)

        cuuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"fmcg-visit-{uid}-{pid}-{tgl}"))

        hour = 8 + (idx % 6)
        minute = 10 + ((idx * 7) % 50)
        visit_timestamp_str = f"{tgl} {hour:02d}:{minute:02d}:00"
        wd_id = workday_id_map.get((uid, tgl), False)

        lat = p_rec.partner_latitude or 1.482187
        lon = p_rec.partner_longitude or 124.848921
        acc = 8.5

        # Cek record yang sudah ada
        existing = Evidence.search([("client_uuid", "=", cuuid)], limit=1)
        if existing:
            # Periksa apakah sudah memiliki attachment original & watermarked valid
            if existing.original and existing.watermarked:
                continue
            # Self-healing: hapus record yang cacat/tanpa attachment dari run sebelumnya
            existing.unlink()
            healed_ev += 1

        # Render watermark khusus kunjungan historis demo
        watermarked_bytes = render_historical_watermark(
            source_bytes=sample_source_photo,
            outlet_ref=p_rec.ref or ev_info["cust_ref"],
            outlet_name=p_rec.name or "Outlet FMCG",
            salesman_name=u_rec.name or "Salesman",
            salesman_login=u_rec.login or "salesman",
            visit_timestamp_str=visit_timestamp_str,
            lat=lat,
            lon=lon,
            acc=acc,
            client_uuid=cuuid,
        )
        watermarked_sha256 = hashlib.sha256(watermarked_bytes).hexdigest()
        watermarked_b64 = base64.b64encode(watermarked_bytes)

        meta = {
            "client_uuid": cuuid,
            "outlet_id": str(pid),
            "business_date": tgl,
            "snapshot_version": "v1-canonical-july-2026",
            "photo_selected_at": f"{tgl}T{hour:02d}:{minute:02d}:00Z",
            "device_recorded_at": f"{tgl}T{hour:02d}:{minute:02d}:05Z",
            "fix_sampled_at": f"{tgl}T{hour:02d}:{minute:02d}:02Z",
            "latitude": lat,
            "longitude": lon,
            "accuracy": acc,
        }

        fprint = hashlib.sha256(
            json.dumps(meta, sort_keys=True, separators=(",", ":")).encode()
            + hashlib.sha256(sample_source_photo).digest()
        ).hexdigest()

        receipt = {
            "client_uuid": cuuid,
            "outlet_id": str(pid),
            "user_id": str(uid),
            "company_id": str(company.id),
            "warehouse_id": str(wh.id),
            "assignment_id": str(wd_id) if wd_id else "0",
            "business_date": tgl,
            "snapshot_version": "v1-canonical-july-2026",
            "received_at": f"{tgl}T{hour:02d}:{minute:02d}:06Z",
            "device_recorded_at": f"{tgl}T{hour:02d}:{minute:02d}:05Z",
            "photo_selected_at": f"{tgl}T{hour:02d}:{minute:02d}:00Z",
            "fix_sampled_at": f"{tgl}T{hour:02d}:{minute:02d}:02Z",
            "latitude": lat,
            "longitude": lon,
            "accuracy": acc,
            "master_latitude": lat,
            "master_longitude": lon,
            "distance_m": 0.0,
            "radius_m": 10,
            "original_sha256": original_sha256,
            "watermarked_sha256": watermarked_sha256,
            "seed_batch": "pjp_workdays_july_2026_v1",
            "is_historical_seed": True,
            "original_url": f"/api/v1/evidence/{cuuid}/original",
            "watermarked_url": f"/api/v1/evidence/{cuuid}/watermarked",
        }
        binding = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        receipt["binding_sha256"] = hashlib.sha256(binding).hexdigest()

        # Pembuatan melalui ORM dengan sudo() sehingga attachment tersimpan di ir.attachment
        Evidence.create({
            "user_id": uid,
            "company_id": company.id,
            "outlet_id": pid,
            "client_uuid": cuuid,
            "fingerprint": fprint,
            "receipt_json": json.dumps(receipt),
            "original": original_b64,
            "watermarked": watermarked_b64,
        })
        created_ev += 1

    print(
        f" -> id.mobile.evidence: {created_ev} bukti kunjungan lapangan berhasil dibuat "
        f"(Self-healed: {healed_ev})."
    )

    env.cr.commit()
    print("[pjp_loader] Selesai: Seluruh matriks PJP, Workdays, dan Evidence berhasil diselaraskan.")


if "env" in globals():
    # Dijalankan langsung dalam Odoo shell
    run_pjp_workdays_loader(env)  # noqa: F821
