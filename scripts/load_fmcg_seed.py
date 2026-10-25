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


def load_principals_and_vendors():
    """Memuat master data 4 Principal Nasional beserta kontak resmi dan partner vendor di res.partner."""
    print(" -> Memuat Master Principal FMCG dan Vendor Partner...")
    Principal = env["id.principal"].sudo()
    Partner = env["res.partner"].sudo().with_context(no_vat_validation=True, tracking_disable=True)
    Country = env["res.country"].sudo()

    indonesia = env.ref("base.id", raise_if_not_found=False) or Country.search([("code", "=", "ID")], limit=1)

    csv_file = seed_dir / "principals_4.csv"
    principals_data = []
    if csv_file.is_file():
        with open(csv_file, mode="r", encoding="utf-8") as f:
            principals_data = list(csv.DictReader(f))

    count = 0
    for p_row in principals_data:
        code = p_row["code"]
        name = p_row["name"]
        street = p_row.get("street", "")
        city = p_row.get("city", "Jakarta")
        zip_code = p_row.get("zip", "")
        phone = p_row.get("phone", "")
        email = p_row.get("email", "")
        vat = p_row.get("vat", "")
        pic_name = p_row.get("pic_name", "")
        pic_phone = p_row.get("pic_phone", "")
        pic_email = p_row.get("pic_email", "")

        # 1. Partner Vendor
        vendor = Partner.search([("ref", "=", code)], limit=1)
        vendor_vals = {
            "name": name,
            "ref": code,
            "is_company": True,
            "supplier_rank": 1,
            "street": street,
            "city": city,
            "zip": zip_code,
            "phone": phone,
            "email": email,
            "vat": vat,
            "country_id": indonesia.id if indonesia else False,
            "comment": f"Principal Resmi FMCG: {name} (PIC: {pic_name} / {pic_phone})",
        }
        vendor_vals = {k: v for k, v in vendor_vals.items() if k in Partner._fields}
        if vendor:
            vendor.write(vendor_vals)
        else:
            vendor = Partner.create(vendor_vals)

        # 2. Model id.principal
        prin_record = Principal.search([("code", "=", code)], limit=1)
        prin_vals = {
            "name": name,
            "code": code,
            "legal_name": p_row.get("legal_name", name),
            "partner_id": vendor.id,
            "pic_name": pic_name,
            "pic_phone": pic_phone,
            "pic_email": pic_email,
            "lead_time_days": int(p_row.get("lead_time_days", 14)),
            "sla_delivery_pct": float(p_row.get("sla_delivery_pct", 95.0)),
        }
        prin_vals = {k: v for k, v in prin_vals.items() if k in Principal._fields}
        if prin_record:
            prin_record.write(prin_vals)
        else:
            Principal.create(prin_vals)
        count += 1

    print(f"    Selesai: {count} Principal & Vendor Partner terhubung.")


def get_or_create_category(Category, name, parent_id=False):
    """Mencari atau membuat product.category secara idempoten."""
    domain = [("name", "=", name)]
    if parent_id:
        domain.append(("parent_id", "=", parent_id))
    else:
        domain.append(("parent_id", "=", False))

    cat = Category.search(domain, limit=1)
    if not cat:
        cat = Category.create({"name": name, "parent_id": parent_id})
    return cat


def load_hierarchical_categories():
    """Membangun struktur hirarki produk FMCG: [PRINSIPAL] > [DIVISI KATEGORI] > [BRAND].

    Struktur ini mengisolasi akun penilaian persediaan, COGS, dan SLA retur antar-prinsipal,
    sekaligus mencegah pencampuran kategori lintas pabrikan.
    """
    print(" -> Menyiapkan Hirarki Kategori Produk ([PRINSIPAL] > [DIVISI] > [BRAND])...")
    Category = env["product.category"].sudo()
    Principal = env["id.principal"].sudo()
    Brand = env["id.brand"].sudo()

    division_labels = {
        "food": "Food & Grocery",
        "rtd": "Ready to Drink (RTD)",
        "home_care": "Home Care",
        "personal_care": "Personal Care",
        "confectionery": "Confectionery & Candy",
    }

    # Map: (principal_code, fmcg_cat, brand_code) -> category_id
    leaf_cat_map = {}

    principals = Principal.search([])

    for p in principals:
        # Level 1: Principal
        p_cat = get_or_create_category(Category, p.name)

        # Dapatkan semua brand di bawah principal ini
        p_brands = Brand.search([("principal_id", "=", p.id)])
        for b in p_brands:
            # Tentukan divisi default
            div_code = "food"
            for code, lbl in division_labels.items():
                if lbl.lower() in (b.name or "").lower():
                    div_code = code
                    break

            # Level 2: Divisi Kategori di bawah Principal
            div_label = division_labels.get(div_code, "Food & Grocery")
            div_cat = get_or_create_category(Category, div_label, parent_id=p_cat.id)

            # Level 3: Brand di bawah Divisi
            brand_cat = get_or_create_category(Category, b.name, parent_id=div_cat.id)
            leaf_cat_map[(p.code, b.code)] = brand_cat.id

    return leaf_cat_map


def load_products():
    """Memuat 150 Master SKU FMCG ke product.template lengkap dengan dimensi fisik (Pcs & Karton)."""
    csv_file = seed_dir / "products_150.csv"
    if not csv_file.is_file():
        print(f"[seed_loader] SKIP: {csv_file} tidak ditemukan")
        return

    print(" -> Memuat Master SKU Produk (150 SKU) beserta dimensi fisik...")
    ProductTemplate = env["product.template"].sudo()
    Principal = env["id.principal"].sudo()
    Brand = env["id.brand"].sudo()
    Category = env["product.category"].sudo()
    Uom = env["uom.uom"].sudo()
    Packaging = env["product.packaging"].sudo() if "product.packaging" in env else None

    # Preload Category Tree
    leaf_cat_map = load_hierarchical_categories()

    uom_unit = env.ref("uom.product_uom_unit", raise_if_not_found=False) or Uom.search([], limit=1)

    principal_map = {p.code: p for p in Principal.search([])}
    brand_map = {b.code: b for b in Brand.search([])}

    count_created = 0
    count_updated = 0

    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row["default_code"]
            name = row["name"]
            prin_code = row.get("principal_code")
            brand_code = row.get("brand_code")
            fmcg_cat = row.get("fmcg_category", "food")

            prin = principal_map.get(prin_code)
            brand = brand_map.get(brand_code)

            # Lookup leaf category: [PRINSIPAL] > [DIVISI] > [BRAND]
            categ_id = leaf_cat_map.get((prin_code, brand_code))
            if not categ_id and prin:
                # Fallback: Buat di bawah Principal / Divisi / Brand
                div_lbl = fmcg_cat.replace("_", " ").title()
                p_cat = get_or_create_category(Category, prin.name)
                div_cat = get_or_create_category(Category, div_lbl, parent_id=p_cat.id)
                brand_name = brand.name if brand else brand_code
                b_cat = get_or_create_category(Category, brand_name, parent_id=div_cat.id)
                categ_id = b_cat.id
                leaf_cat_map[(prin_code, brand_code)] = categ_id

            vals = {
                "name": name,
                "default_code": code,
                "fmcg_category": fmcg_cat,
                "principal_id": prin.id if prin else False,
                "brand_id": brand.id if brand else False,
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

            if categ_id and "categ_id" in ProductTemplate._fields:
                vals["categ_id"] = categ_id

            # Odoo 19 Storable & Lot Tracking
            if "is_storable" in ProductTemplate._fields:
                vals["is_storable"] = True
                vals["type"] = "consu"
            elif "type" in ProductTemplate._fields:
                vals["type"] = "consu"

            if "tracking" in ProductTemplate._fields:
                vals["tracking"] = "lot"

            vals = {k: v for k, v in vals.items() if k in ProductTemplate._fields}

            prod = ProductTemplate.search([("default_code", "=", code)], limit=1)
            if prod:
                prod.write(vals)
                count_updated += 1
            else:
                prod = ProductTemplate.create(vals)
                count_created += 1

            # Konfigurasi Packaging (Karton)
            carton_qty = int(row.get("carton_qty", 1))
            base_uom = row.get("base_uom", "Pcs")
            if Packaging and carton_qty > 1:
                try:
                    variant = prod.product_variant_id or (
                        prod.product_variant_ids and prod.product_variant_ids[0]
                    )
                    if variant:
                        pkg_name = f"Karton ({carton_qty} {base_uom})"
                        pkg = Packaging.search(
                            [("product_id", "=", variant.id), ("qty", "=", float(carton_qty))],
                            limit=1,
                        )
                        pkg_vals = {
                            "name": pkg_name,
                            "product_id": variant.id,
                            "qty": float(carton_qty),
                        }
                        if not pkg:
                            Packaging.create(pkg_vals)
                except Exception as pkg_err:
                    _logger.warning("Gagal membuat packaging untuk %s: %s", code, pkg_err)

    print(
        f"    Selesai: {count_created} dibuat, {count_updated} diperbarui "
        "(Hirarki Kategori, Dimensi Fisik, & Packaging aktif)."
    )


def load_employees():
    """Memuat 24 Karyawan ke hr.employee dan hr.department dengan struktur organisasi lengkap."""
    csv_file = seed_dir / "employees_24.csv"
    if not csv_file.is_file():
        print(f"[seed_loader] SKIP: {csv_file} tidak ditemukan")
        return

    if "hr.employee" not in env or "hr.department" not in env:
        print("[seed_loader] SKIP: Modul hr belum terpasang.")
        return

    print(" -> Memuat Master 24 Karyawan & Struktur Organisasi (hr.employee & hr.department)...")
    Employee = env["hr.employee"].sudo()
    Department = env["hr.department"].sudo()

    # Siapkan pohon departemen
    mgt_dept = Department.search([("name", "=", "Management")], limit=1)
    if not mgt_dept:
        mgt_dept = Department.create({"name": "Management"})

    dept_defs = [
        ("Finance & Akuntansi", mgt_dept.id),
        ("Sales & Distribusi", mgt_dept.id),
        ("Warehouse & Logistik", mgt_dept.id),
    ]
    dept_map = {"Management": mgt_dept.id}
    for d_name, parent_id in dept_defs:
        d = Department.search([("name", "=", d_name)], limit=1)
        if not d:
            d = Department.create({"name": d_name, "parent_id": parent_id})
        dept_map[d_name] = d.id

    dept_alias = {
        "Finance": dept_map["Finance & Akuntansi"],
        "Sales": dept_map["Sales & Distribusi"],
        "Warehouse": dept_map["Warehouse & Logistik"],
        "Logistik": dept_map["Warehouse & Logistik"],
        "Management": dept_map["Management"],
    }

    count_created = 0
    count_updated = 0

    emp_records = {}

    with open(csv_file, mode="r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Pass 1: Buat/Update data dasar karyawan
    for row in rows:
        code = row["code"]
        name = row["name"]
        raw_dept = row.get("dept", "Sales")
        dept_id = dept_alias.get(raw_dept, dept_map["Sales & Distribusi"])
        job = row.get("role", "").replace("_", " ").title()

        vals = {
            "name": name,
            "job_title": job,
            "work_email": row.get("work_email") or False,
            "work_phone": row.get("work_phone") or False,
            "department_id": dept_id,
        }
        vals = {k: v for k, v in vals.items() if k in Employee._fields}

        emp = Employee.search([("name", "=", name)], limit=1)
        if emp:
            emp.write(vals)
            count_updated += 1
        else:
            emp = Employee.create(vals)
            count_created += 1
        emp_records[code] = emp

    # Pass 2: Hubungkan hirarki pelaporan (parent_id / Manager)
    for row in rows:
        code = row["code"]
        mgr_code = row.get("manager_code")
        if mgr_code and mgr_code in emp_records and code in emp_records:
            emp = emp_records[code]
            mgr = emp_records[mgr_code]
            if "parent_id" in Employee._fields and emp.parent_id != mgr:
                emp.write({"parent_id": mgr.id})

    print(f"    Selesai: {count_created} dibuat, {count_updated} diperbarui (Hirarki Organisasi terhubung).")


def load_vehicles():
    """Memuat 9 Armada Logistik ke fleet.vehicle beserta spesifikasi kargo dan dimensi box."""
    csv_file = seed_dir / "vehicles_9.csv"
    if not csv_file.is_file():
        print(f"[seed_loader] SKIP: {csv_file} tidak ditemukan")
        return

    if "fleet.vehicle" not in env or "fleet.vehicle.model" not in env:
        print("[seed_loader] SKIP: Modul fleet belum terpasang.")
        return

    print(" -> Memuat Master 9 Armada Logistik beserta spesifikasi kargo (fleet.vehicle)...")
    Vehicle = env["fleet.vehicle"].sudo()
    Model = env["fleet.vehicle.model"].sudo()
    Brand = env["fleet.vehicle.model.brand"].sudo()
    Partner = env["res.partner"].sudo()

    count_created = 0
    count_updated = 0

    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            plate = row["plate"]
            model_name = row.get("model", "Box Truck")
            driver_name = row.get("driver")

            # Brand detection
            brand_name = model_name.split()[0]
            brand = Brand.search([("name", "=", brand_name)], limit=1)
            if not brand:
                brand = Brand.create({"name": brand_name})

            # Model creation / lookup
            model = Model.search([("name", "=", model_name)], limit=1)
            if not model:
                model = Model.create({"name": model_name, "brand_id": brand.id})

            # Driver partner lookup
            driver_partner = Partner.search([("name", "=", driver_name)], limit=1) if driver_name else None

            vals = {
                "license_plate": plate,
                "model_id": model.id,
                "driver_id": driver_partner.id if driver_partner else False,
                "capacity_ton": float(row.get("ton", 0.0)),
                "capacity_cbm": float(row.get("cbm", 0.0)),
                "box_length": float(row.get("box_length_m", 0.0)),
                "box_width": float(row.get("box_width_m", 0.0)),
                "box_height": float(row.get("box_height_m", 0.0)),
                "operational_route": row.get("route", ""),
                "stnk_expiry": row.get("stnk_exp") or False,
                "kir_expiry": row.get("kir_exp") or False,
            }
            vals = {k: v for k, v in vals.items() if k in Vehicle._fields}

            veh = Vehicle.search([("license_plate", "=", plate)], limit=1)
            if veh:
                veh.write(vals)
                count_updated += 1
            else:
                Vehicle.create(vals)
                count_created += 1

    print(f"    Selesai: {count_created} dibuat, {count_updated} diperbarui (Spesifikasi Kargo & Dimensi Box lengkap).")


def load_partners():
    """Memuat 354 Partner Outlet ke res.partner lengkap dengan alamat, TOP, dan Salesman."""
    csv_file = seed_dir / "partners_354.csv"
    if not csv_file.is_file():
        print(f"[seed_loader] SKIP: {csv_file} tidak ditemukan")
        return

    print(" -> Memuat Master Partner & Outlet (354 Outlet)...")
    Partner = env["res.partner"].sudo().with_context(no_vat_validation=True, tracking_disable=True)
    Channel = env["id.channel"].sudo()
    District = env["id.district"].sudo()
    Subdistrict = env["id.subdistrict"].sudo()
    Country = env["res.country"].sudo()
    State = env["res.country.state"].sudo()
    PaymentTerm = env["account.payment.term"].sudo() if "account.payment.term" in env else None
    User = env["res.users"].sudo()

    # Preload wilayah
    indonesia = env.ref("base.id", raise_if_not_found=False) or Country.search([("code", "=", "ID")], limit=1)
    sulut = State.search(
        [("code", "in", ["SA", "ID-SA"]), ("country_id", "=", indonesia.id if indonesia else False)],
        limit=1,
    )
    if not sulut:
        sulut = State.search([("name", "ilike", "Sulawesi Utara")], limit=1)

    # Preload payment terms (TOP)
    term_immediate = None
    term_15 = None
    term_21 = None
    term_30 = None
    term_45 = None
    if PaymentTerm:
        term_immediate = (
            env.ref("account.account_payment_term_immediate", raise_if_not_found=False)
            or PaymentTerm.search([("name", "ilike", "Immediate")], limit=1)
            or PaymentTerm.search([], limit=1)
        )
        term_15 = PaymentTerm.search([("name", "ilike", "15")], limit=1)
        term_21 = PaymentTerm.search([("name", "ilike", "21")], limit=1) or term_15
        term_30 = PaymentTerm.search([("name", "ilike", "30")], limit=1)
        term_45 = PaymentTerm.search([("name", "ilike", "45")], limit=1) or term_30

    def get_term(days):
        if not PaymentTerm:
            return False
        if days == 0:
            return term_immediate.id if term_immediate else False
        elif days <= 15:
            return term_15.id if term_15 else (term_immediate.id if term_immediate else False)
        elif days <= 21:
            return term_21.id if term_21 else (term_15.id if term_15 else False)
        elif days <= 30:
            return term_30.id if term_30 else False
        else:
            return term_45.id if term_45 else False

    # Preload users / salesmen
    admin_user = env.ref("base.user_admin", raise_if_not_found=False) or User.search([("id", "=", 2)], limit=1)
    user_map = {}
    for u in User.search([]):
        user_map[u.login.lower()] = u.id

    def get_salesman_user(code):
        if not code:
            return admin_user.id if admin_user else False
        code_l = code.lower()
        if code_l in user_map:
            return user_map[code_l]
        return admin_user.id if admin_user else False

    channel_map = {c.code: c.id for c in Channel.search([])}
    district_map = {d.code: d.id for d in District.search([])}
    district_city_map = {d.code: d.city for d in District.search([]) if d.city}
    subdistrict_map = {s.code: s.id for s in Subdistrict.search([])}

    count_created = 0
    count_updated = 0

    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ref = row["ref"]
            name = row["name"]
            dist_code = row.get("district_code")
            channel_id = channel_map.get(row.get("channel_code"))
            district_id = district_map.get(dist_code)
            subdistrict_id = subdistrict_map.get(row.get("subdistrict_code"))
            city = row.get("city") or district_city_map.get(dist_code, "Kota Manado")
            pt_days = int(row.get("payment_term_days", 0))
            sls_code = row.get("salesman_code")

            vals = {
                "name": name,
                "ref": ref,
                "is_company": row.get("is_company", "True").lower() == "true",
                "customer_rank": 1,
                "channel_id": channel_id,
                "district_id": district_id,
                "subdistrict_id": subdistrict_id,
                "street": row.get("street", ""),
                "city": city,
                "state_id": sulut.id if sulut else False,
                "country_id": indonesia.id if indonesia else False,
                "zip": row.get("zip", ""),
                "phone": row.get("phone") or False,
                "vat": row.get("vat") or False,
                "credit_limit": float(row.get("credit_limit", 0.0)),
                "credit_mode": row.get("credit_mode", "strict"),
                "partner_latitude": float(row.get("latitude", 0.0)),
                "partner_longitude": float(row.get("longitude", 0.0)),
                "property_payment_term_id": get_term(pt_days),
                "user_id": get_salesman_user(sls_code),
            }

            vals = {k: v for k, v in vals.items() if k in Partner._fields}

            partner = Partner.search([("ref", "=", ref)], limit=1)
            if partner:
                partner.write(vals)
                count_updated += 1
            else:
                Partner.create(vals)
                count_created += 1

    print(f"    Selesai: {count_created} dibuat, {count_updated} diperbarui (Alamat, TOP, & Salesman lengkap).")


def load_all():
    try:
        load_principals_and_vendors()
        load_products()
        load_employees()
        load_vehicles()
        load_partners()
        cr.commit()
        print("[seed_loader] SUCCESS: Seluruh data master FMCG berhasil dimuat secara lengkap.")
    except Exception as e:
        cr.rollback()
        import traceback

        print(f"[seed_loader] GAGAL saat memuat data: {type(e).__name__} - {e}")
        traceback.print_exc()
        raise


load_all()

