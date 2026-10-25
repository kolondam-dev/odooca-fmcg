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
    """Memastikan setiap Principal memiliki partner vendor di res.partner (supplier_rank=1)."""
    print(" -> Memeriksa dan menghubungkan Vendor Partner untuk Principal FMCG...")
    Principal = env["id.principal"].sudo()
    Partner = env["res.partner"].sudo()
    Country = env["res.country"].sudo()

    indonesia = env.ref("base.id", raise_if_not_found=False) or Country.search([("code", "=", "ID")], limit=1)

    principals = Principal.search([])
    count = 0
    for p in principals:
        vendor = Partner.search([("ref", "=", p.code)], limit=1)
        vals = {
            "name": p.name,
            "ref": p.code,
            "is_company": True,
            "supplier_rank": 1,
            "country_id": indonesia.id if indonesia else False,
            "comment": f"Official Principal FMCG: {p.name} (PKS: {p.pks_number or '-'})",
        }
        if vendor:
            vendor.write(vals)
        else:
            vendor = Partner.create(vals)
        if hasattr(p, "partner_id") and p.partner_id != vendor:
            p.partner_id = vendor.id
        count += 1
    print(f"    Selesai: {count} Principal terhubung ke Vendor Partner.")


def load_categories():
    """Menyiapkan struktur kategori produk FMCG pada product.category."""
    print(" -> Menyiapkan Kategori Produk FMCG (product.category)...")
    Category = env["product.category"].sudo()

    parent_cat = Category.search([("name", "=", "FMCG")], limit=1)
    if not parent_cat:
        parent_cat = Category.create({"name": "FMCG"})

    sub_categories = {
        "food": "Food & Grocery",
        "rtd": "Ready to Drink (RTD)",
        "home_care": "Home Care",
        "personal_care": "Personal Care",
        "confectionery": "Confectionery & Candy",
    }
    cat_map = {}
    for code, label in sub_categories.items():
        cat = Category.search([("name", "=", label), ("parent_id", "=", parent_cat.id)], limit=1)
        if not cat:
            cat = Category.create({"name": label, "parent_id": parent_cat.id})
        cat_map[code] = cat.id

    return cat_map


def load_products():
    """Memuat 150 Master SKU FMCG ke product.template dengan is_storable=True, tracking=lot, dan packaging."""
    csv_file = seed_dir / "products_150.csv"
    if not csv_file.is_file():
        print(f"[seed_loader] SKIP: {csv_file} tidak ditemukan")
        return

    print(" -> Memuat Master SKU Produk (150 SKU)...")
    ProductTemplate = env["product.template"].sudo()
    Principal = env["id.principal"].sudo()
    Brand = env["id.brand"].sudo()
    Uom = env["uom.uom"].sudo()
    Packaging = env["product.packaging"].sudo() if "product.packaging" in env else None

    cat_map = load_categories()

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
            fmcg_cat = row.get("fmcg_category", "food")

            prin_id = principal_map.get(prin_code)
            brand_id = brand_map.get(brand_code)
            categ_id = cat_map.get(fmcg_cat)

            vals = {
                "name": name,
                "default_code": code,
                "fmcg_category": fmcg_cat,
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

            # Odoo 19 Storable & Lot Tracking
            if "is_storable" in ProductTemplate._fields:
                vals["is_storable"] = True
            elif "type" in ProductTemplate._fields:
                vals["type"] = "consu"

            if "tracking" in ProductTemplate._fields:
                vals["tracking"] = "lot"

            if categ_id and "categ_id" in ProductTemplate._fields:
                vals["categ_id"] = categ_id

            # Filter field valid
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
            if Packaging and carton_qty > 1 and prod.product_variant_id:
                pkg_name = f"Karton ({carton_qty} {base_uom})"
                pkg = Packaging.search(
                    [("product_id", "=", prod.product_variant_id.id), ("qty", "=", carton_qty)],
                    limit=1,
                )
                if not pkg:
                    Packaging.create(
                        {
                            "name": pkg_name,
                            "product_id": prod.product_variant_id.id,
                            "qty": carton_qty,
                            "barcode": row.get("barcode") or False,
                        }
                    )

    print(
        f"    Selesai: {count_created} dibuat, {count_updated} diperbarui "
        "(Storable, Lot-tracking, & Packaging aktif)."
    )


def load_employees():
    """Memuat 24 Karyawan ke hr.employee dan hr.department."""
    csv_file = seed_dir / "employees_24.csv"
    if not csv_file.is_file():
        print(f"[seed_loader] SKIP: {csv_file} tidak ditemukan")
        return

    if "hr.employee" not in env or "hr.department" not in env:
        print("[seed_loader] SKIP: Modul hr belum terpasang.")
        return

    print(" -> Memuat Master 24 Karyawan (hr.employee & hr.department)...")
    Employee = env["hr.employee"].sudo()
    Department = env["hr.department"].sudo()

    # Siapkan departemen
    dept_names = ["Management", "Finance", "Sales", "Warehouse", "Logistik"]
    dept_map = {}
    for d_name in dept_names:
        d = Department.search([("name", "=", d_name)], limit=1)
        if not d:
            d = Department.create({"name": d_name})
        dept_map[d_name] = d.id

    count_created = 0
    count_updated = 0

    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["name"]
            dept_name = row.get("dept", "Sales")
            dept_id = dept_map.get(dept_name)
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
                Employee.create(vals)
                count_created += 1

    print(f"    Selesai: {count_created} dibuat, {count_updated} diperbarui.")


def load_vehicles():
    """Memuat 9 Armada Logistik ke fleet.vehicle."""
    csv_file = seed_dir / "vehicles_9.csv"
    if not csv_file.is_file():
        print(f"[seed_loader] SKIP: {csv_file} tidak ditemukan")
        return

    if "fleet.vehicle" not in env or "fleet.vehicle.model" not in env:
        print("[seed_loader] SKIP: Modul fleet belum terpasang.")
        return

    print(" -> Memuat Master 9 Armada Logistik (fleet.vehicle)...")
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
            }
            vals = {k: v for k, v in vals.items() if k in Vehicle._fields}

            veh = Vehicle.search([("license_plate", "=", plate)], limit=1)
            if veh:
                veh.write(vals)
                count_updated += 1
            else:
                Vehicle.create(vals)
                count_created += 1

    print(f"    Selesai: {count_created} dibuat, {count_updated} diperbarui.")


def load_partners():
    """Memuat 354 Partner Outlet ke res.partner lengkap dengan alamat, TOP, dan Salesman."""
    csv_file = seed_dir / "partners_354.csv"
    if not csv_file.is_file():
        print(f"[seed_loader] SKIP: {csv_file} tidak ditemukan")
        return

    print(" -> Memuat Master Partner & Outlet (354 Outlet)...")
    Partner = env["res.partner"].sudo()
    Channel = env["id.channel"].sudo()
    District = env["id.district"].sudo()
    Subdistrict = env["id.subdistrict"].sudo()
    Country = env["res.country"].sudo()
    State = env["res.country.state"].sudo()
    PaymentTerm = env["account.payment.term"].sudo()
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
    term_immediate = PaymentTerm.search([("name", "ilike", "Immediate")], limit=1) or PaymentTerm.browse(1)
    term_15 = PaymentTerm.search([("name", "ilike", "15")], limit=1)
    term_21 = PaymentTerm.search([("name", "ilike", "21")], limit=1) or term_15
    term_30 = PaymentTerm.search([("name", "ilike", "30")], limit=1)
    term_45 = PaymentTerm.search([("name", "ilike", "45")], limit=1) or term_30

    def get_term(days):
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
                "tier_id": False,  # Customer tier didecouple sesuai arahan
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
        print(f"[seed_loader] ERROR saat memuat data: {e}")
        raise


load_all()
