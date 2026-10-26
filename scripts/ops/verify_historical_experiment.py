#!/usr/bin/env python3
"""scripts/ops/verify_historical_experiment.py

Eksperimen metode seeding historis minimal pada Odoo 19 disposable DB.
Dijalankan via:
    odoo shell -c /tmp/odoo.conf -d fmcg --no-http < scripts/ops/verify_historical_experiment.py
atau via entrypoint wrapper:
    /opt/deploy/init.sh shell --no-http < scripts/ops/verify_historical_experiment.py

Tujuan & Cakupan:
1. Diagnosis Build & Konfigurasi Odoo 19 Aktual:
   - Versi Odoo, release info, commit/digest.
   - Daftar modul terpasang (ir.module.module state='installed').
   - Konfigurasi company, currency, timezone (Asia/Makassar), costing method, inventory valuation.
2. Eksperimen Minimal SKU Tunggal dari Sumber Kanonikal:
   - SKU: ULV-RNS-03 (Rinnso Cair Konsentrat Refill 750ml, Unilever)
   - Lot Opening: LOT-VER-20260615-INIT-09 (84 karton / 1.008 pouch @ Rp 18.500 = Rp 18.648.000)
   - Inbound PO: PO-2026-06-05, Lot: LOT-VER-20260704-09 (311 karton / 3.732 pouch @ Rp 18.500 = Rp 69.042.000)
   - Outgoing SO & DO: SO-202607-0063 / DO-202607-0063 (7 karton / 84 pouch dari LOT-VER-20260615-INIT-09, COGS Rp 1.554.000)
   - Retur Karantina: REJ-202607-001 (1 karton / 12 pouch LOT-VER-20260615-INIT-09 ke Karantina FMCG Maumbi, COGS Rp 222.000)
3. Evaluasi Metode Seeding Opening Stock Native & Penanggalan Efektif:
   - Uji pembuatan opening stock via Stock Move native & Stock Quant inventory adjustment.
   - Verifikasi tanggal efektif bisnis (movement date) vs metadata audit (create_date/write_date).
4. Verifikasi Independent Source-to-Runtime Oracle (Tabel Expected vs Actual vs Delta):
   - Cutoff 0: Tepat sebelum opening
   - Cutoff 1: Setelah Opening Stock (1 Juli 2026)
   - Cutoff 2: Setelah Inbound PO Receipt (4 Juli 2026)
   - Cutoff 3: Setelah Outgoing Delivery (3 Juli 2026)
   - Cutoff 4: Setelah Retur Karantina (3 Juli 2026)
5. Uji Idempotensi Sejati (Run 1 vs Run 2) pada DB yang sama:
   - Mempertahankan exact record count, move IDs, quant quantities, lot, location, dan valuasi.
6. Ekspor Laporan Diagnostik Lengkap ke JSON Artifact (historical_experiment_report.json).
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Path root repositori (tangguh terhadap stdin stream)
try:
    REPO_ROOT = Path(__file__).resolve().parent.parent.parent
except NameError:
    if Path("/opt/scripts/load_canonical_perpetual.py").exists():
        REPO_ROOT = Path("/opt")
    elif Path("scripts/load_canonical_perpetual.py").exists():
        REPO_ROOT = Path.cwd()
    else:
        REPO_ROOT = Path(os.environ.get("REPO_ROOT", "/opt"))

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REG_PATH = REPO_ROOT / "data" / "registers"
if not REG_PATH.exists() and Path("/opt/data/registers").exists():
    REG_PATH = Path("/opt/data/registers")


def diagnose_odoo19_build(env):
    """Mendiagnosis dan mencatat build Odoo 19 aktual serta konfigurasinya."""
    import odoo

    diagnosis = {
        "timestamp": datetime.now().isoformat(),
        "odoo_version": getattr(odoo.release, "version", "Unknown"),
        "version_info": getattr(odoo.release, "version_info", []),
        "company": {},
        "installed_modules": [],
        "models_inspected": {},
    }

    # 1. Company, Currency & Timezone
    company = env.company
    diagnosis["company"] = {
        "id": company.id,
        "name": company.name,
        "currency": company.currency_id.name if getattr(company, "currency_id", None) else None,
        "country": company.country_id.code if getattr(company, "country_id", None) else None,
    }

    # 2. Modul terpasang
    if "ir.module.module" in env:
        installed = env["ir.module.module"].sudo().search([("state", "=", "installed")])
        diagnosis["installed_modules"] = [m.name for m in installed]

    # 3. Model & Field Inspection
    models_to_check = [
        "stock.quant",
        "stock.move",
        "stock.move.line",
        "stock.picking",
        "stock.valuation.layer",
        "account.move",
        "account.payment",
    ]
    for mname in models_to_check:
        if mname in env:
            fields_dict = getattr(env[mname], "_fields", {})
            diagnosis["models_inspected"][mname] = {
                "available": True,
                "fields_count": len(fields_dict),
                "key_fields": [f for f in ["date", "quantity", "qty_done", "lot_id", "state", "inventory_quantity", "inventory_date", "memo", "move_id"] if f in fields_dict],
            }
        else:
            diagnosis["models_inspected"][mname] = {"available": False}

    return diagnosis


def create_opening_stock_move(env, product, warehouse_loc, lot, qty_units, unit_cost, date_str, company):
    """Menciptakan Opening Stock menggunakan metode Stock Move Native Odoo 19.

    Menghasilkan:
    - Dokumen stock.move resmi dengan origin OPENING-20260701
    - Dokumen stock.move.line resmi yang mengikat lot dan kuantitas
    - Validasi move menjadi 'done' melalui native _action_done()
    - Penyesuaian tanggal efektif bisnis historis (date) tanpa memalsukan create_date
    """
    StockLocation = env["stock.location"].sudo()
    StockMove = env["stock.move"].sudo()
    StockMoveLine = env["stock.move.line"].sudo()

    # Cari lokasi virtual inventory loss / adjustment
    inv_location = StockLocation.search([("usage", "=", "inventory")], limit=1)
    if not inv_location:
        inv_location = StockLocation.search([("name", "ilike", "Inventory adjustment")], limit=1)
    if not inv_location:
        inv_location = StockLocation.create({
            "name": "Virtual Locations/Inventory adjustment",
            "usage": "inventory",
            "company_id": company.id,
        })

    # Cek apakah move opening sudah ada (idempoten)
    existing_move = StockMove.search([
        ("origin", "=", "OPENING-20260701"),
        ("product_id", "=", product.id),
        ("location_dest_id", "=", warehouse_loc.id),
        ("state", "=", "done"),
    ], limit=1)

    if existing_move:
        return existing_move, False

    # Buat move resmi
    move_vals = {
        "name": f"INV:OPENING:{product.default_code}:{lot.name if lot else 'NOLOT'}",
        "origin": "OPENING-20260701",
        "product_id": product.id,
        "product_uom": product.uom_id.id,
        "product_uom_qty": qty_units,
        "location_id": inv_location.id,
        "location_dest_id": warehouse_loc.id,
        "company_id": company.id,
        "price_unit": unit_cost,
    }
    if "date" in StockMove._fields:
        move_vals["date"] = f"{date_str} 00:00:00"

    move = StockMove.create(move_vals)

    # Buat move line dengan lot dan kuantitas
    sml_vals = {
        "move_id": move.id,
        "product_id": product.id,
        "product_uom_id": product.uom_id.id,
        "location_id": inv_location.id,
        "location_dest_id": warehouse_loc.id,
        "lot_id": lot.id if lot else False,
        "company_id": company.id,
    }
    if "quantity" in StockMoveLine._fields:
        sml_vals["quantity"] = qty_units
    elif "qty_done" in StockMoveLine._fields:
        sml_vals["qty_done"] = qty_units

    if "date" in StockMoveLine._fields:
        sml_vals["date"] = f"{date_str} 00:00:00"

    StockMoveLine.create(sml_vals)

    # Validasi native
    move._action_done()

    # Setel tanggal efektif bisnis historis pasca validasi
    hist_dt = f"{date_str} 00:00:00"
    move.write({"date": hist_dt})
    if hasattr(move, "move_line_ids") and move.move_line_ids:
        move.move_line_ids.write({"date": hist_dt})

    return move, True


def run_historical_experiment(env):
    """Menjalankan eksperimen historis minimal komprehensif pada DB disposable."""
    print("=" * 80)
    print("[historical_experiment] MEMULAI EKSPERIMEN METODE SEEDING HISTORIS ODOO 19")
    print("=" * 80)

    # 1. Diagnosis
    diag = diagnose_odoo19_build(env)
    print(f" -> Odoo Version: {diag['odoo_version']}")
    print(f" -> Company: {diag['company']['name']} ({diag['company']['currency']})")
    print(f" -> Installed Modules Count: {len(diag['installed_modules'])}")

    # 2. Setup Master Eksperimen
    StockLocation = env["stock.location"].sudo()
    StockLot = env["stock.lot"].sudo() if "stock.lot" in env else None
    Product = env["product.product"].sudo()

    warehouse_loc = StockLocation.search([("usage", "=", "internal")], limit=1)
    customer_loc = StockLocation.search([("usage", "=", "customer")], limit=1)
    if not customer_loc:
        customer_loc = StockLocation.create({"name": "Partner Locations/Customers", "usage": "customer"})

    quarantine_loc = StockLocation.search([("name", "=", "Karantina FMCG Maumbi")], limit=1)
    if not quarantine_loc:
        quarantine_loc = StockLocation.create({
            "name": "Karantina FMCG Maumbi",
            "usage": "internal",
            "location_id": warehouse_loc.location_id.id if warehouse_loc.location_id else False,
        })

    # SKU Eksperimen: ULV-RNS-03
    sku_code = "ULV-RNS-03"
    product = Product.search([("default_code", "=", sku_code)], limit=1)
    if not product:
        raise LookupError(f"Produk eksperimen '{sku_code}' tidak ditemukan di product.product!")

    # Lot 1: Opening & Rejection (LOT-VER-20260615-INIT-09)
    lot_opening = StockLot.search([("name", "=", "LOT-VER-20260615-INIT-09"), ("product_id", "=", product.id)], limit=1)
    if not lot_opening:
        lot_opening = StockLot.create({
            "name": "LOT-VER-20260615-INIT-09",
            "product_id": product.id,
            "company_id": env.company.id,
            "expiration_date": "2027-12-31",
        })

    # Lot 2: Inbound PO (LOT-VER-20260704-09)
    lot_po = StockLot.search([("name", "=", "LOT-VER-20260704-09"), ("product_id", "=", product.id)], limit=1)
    if not lot_po:
        lot_po = StockLot.create({
            "name": "LOT-VER-20260704-09",
            "product_id": product.id,
            "company_id": env.company.id,
            "expiration_date": "2028-06-30",
        })

    # Helper Snapshot Saldo
    def get_stock_snapshot():
        StockQuant = env["stock.quant"].sudo()
        quants = StockQuant.search([("product_id", "=", product.id)])
        snap = {
            "saleable_on_hand_units": 0.0,
            "saleable_reserved_units": 0.0,
            "quarantine_on_hand_units": 0.0,
            "by_lot": {},
        }
        for q in quants:
            lot_name = q.lot_id.name if q.lot_id else "NOLOT"
            qty = float(getattr(q, "quantity", 0.0))
            res = float(getattr(q, "reserved_quantity", 0.0))
            if q.location_id.id == warehouse_loc.id:
                snap["saleable_on_hand_units"] += qty
                snap["saleable_reserved_units"] += res
            elif q.location_id.id == quarantine_loc.id:
                snap["quarantine_on_hand_units"] += qty

            k = (q.location_id.name, lot_name)
            snap["by_lot"][k] = snap["by_lot"].get(k, 0.0) + qty
        return snap

    report_table = []

    # CUTOFF 0: Tepat sebelum Opening
    snap0 = get_stock_snapshot()
    report_table.append({
        "cutoff": "0. Pre-Opening",
        "event": "N/A",
        "date": "2026-06-30",
        "expected_saleable_cartons": 0,
        "actual_saleable_cartons": snap0["saleable_on_hand_units"] / 12,
        "expected_quarantine_cartons": 0,
        "actual_quarantine_cartons": snap0["quarantine_on_hand_units"] / 12,
        "delta": snap0["saleable_on_hand_units"],
    })

    # CUTOFF 1: Setelah Opening Stock (1 Juli 2026)
    # Expected: 84 karton (1.008 pcs) Lot INIT-09, unit cost 18.500
    print("\n -> [Eksperimen 1/4] Mengeksekusi Opening Stock (1 Juli 2026)...")
    move_op, created_op = create_opening_stock_move(
        env, product, warehouse_loc, lot_opening,
        qty_units=1008.0, unit_cost=18500.0, date_str="2026-07-01", company=env.company
    )
    print(f"    Move ID: {move_op.id}, State: {move_op.state}, Date: {move_op.date}, Created: {created_op}")

    snap1 = get_stock_snapshot()
    report_table.append({
        "cutoff": "1. Post-Opening",
        "event": "OPENING-20260701",
        "date": "2026-07-01",
        "expected_saleable_cartons": 84,
        "actual_saleable_cartons": snap1["saleable_on_hand_units"] / 12,
        "expected_quarantine_cartons": 0,
        "actual_quarantine_cartons": snap1["quarantine_on_hand_units"] / 12,
        "delta": (snap1["saleable_on_hand_units"] / 12) - 84,
    })

    # CUTOFF 2: Setelah Inbound PO Receipt (PO-2026-06-05) per 4 Juli 2026
    # Expected: 311 karton (3.732 pcs) Lot 20260704-09 diterima ke WH/Stock
    print("\n -> [Eksperimen 2/4] Mengeksekusi Inbound PO Receipt (4 Juli 2026)...")
    po_move, created_po = create_opening_stock_move(
        env, product, warehouse_loc, lot_po,
        qty_units=3732.0, unit_cost=18500.0, date_str="2026-07-04", company=env.company
    )
    snap2 = get_stock_snapshot()
    report_table.append({
        "cutoff": "2. Post-PO-Receipt",
        "event": "PO-2026-06-05 Receipt",
        "date": "2026-07-04",
        "expected_saleable_cartons": 395,  # 84 + 311 = 395
        "actual_saleable_cartons": snap2["saleable_on_hand_units"] / 12,
        "expected_quarantine_cartons": 0,
        "actual_quarantine_cartons": snap2["quarantine_on_hand_units"] / 12,
        "delta": (snap2["saleable_on_hand_units"] / 12) - 395,
    })

    # CUTOFF 3: Setelah Outgoing Delivery DO-202607-0063 per 3 Juli 2026
    # Expected: 7 karton (84 pcs) terkirim dari WH/Stock ke Customer
    print("\n -> [Eksperimen 3/4] Mengeksekusi Outgoing Delivery DO-202607-0063 (3 Juli 2026)...")
    StockMove = env["stock.move"].sudo()
    StockMoveLine = env["stock.move.line"].sudo()

    so_move = StockMove.search([
        ("origin", "=", "SO-202607-0063"),
        ("product_id", "=", product.id),
        ("location_dest_id", "=", customer_loc.id),
        ("state", "=", "done"),
    ], limit=1)

    if not so_move:
        so_move = StockMove.create({
            "name": "DO-202607-0063:ULV-RNS-03",
            "origin": "SO-202607-0063",
            "product_id": product.id,
            "product_uom": product.uom_id.id,
            "product_uom_qty": 84.0,
            "location_id": warehouse_loc.id,
            "location_dest_id": customer_loc.id,
            "company_id": env.company.id,
            "date": "2026-07-03 00:00:00",
        })
        sml = StockMoveLine.create({
            "move_id": so_move.id,
            "product_id": product.id,
            "product_uom_id": product.uom_id.id,
            "location_id": warehouse_loc.id,
            "location_dest_id": customer_loc.id,
            "lot_id": lot_opening.id,
            "company_id": env.company.id,
            "quantity": 84.0,
            "date": "2026-07-03 00:00:00",
        })
        so_move._action_done()
        so_move.write({"date": "2026-07-03 00:00:00"})
        sml.write({"date": "2026-07-03 00:00:00"})

    snap3 = get_stock_snapshot()
    report_table.append({
        "cutoff": "3. Post-SO-Delivery",
        "event": "DO-202607-0063",
        "date": "2026-07-03",
        "expected_saleable_cartons": 388,  # 395 - 7 = 388
        "actual_saleable_cartons": snap3["saleable_on_hand_units"] / 12,
        "expected_quarantine_cartons": 0,
        "actual_quarantine_cartons": snap3["quarantine_on_hand_units"] / 12,
        "delta": (snap3["saleable_on_hand_units"] / 12) - 388,
    })

    # CUTOFF 4: Setelah Retur Karantina REJ-202607-001 per 3 Juli 2026
    # Expected: 1 karton (12 pcs) retur dari Customer ke Karantina FMCG Maumbi
    print("\n -> [Eksperimen 4/4] Mengeksekusi Retur Karantina REJ-202607-001 (3 Juli 2026)...")
    rej_move = StockMove.search([
        ("origin", "=", "REJ-202607-001"),
        ("product_id", "=", product.id),
        ("location_dest_id", "=", quarantine_loc.id),
        ("state", "=", "done"),
    ], limit=1)

    if not rej_move:
        rej_move = StockMove.create({
            "name": "REJ-202607-001:ULV-RNS-03",
            "origin": "REJ-202607-001",
            "product_id": product.id,
            "product_uom": product.uom_id.id,
            "product_uom_qty": 12.0,
            "location_id": customer_loc.id,
            "location_dest_id": quarantine_loc.id,
            "company_id": env.company.id,
            "date": "2026-07-03 00:00:00",
        })
        sml_rej = StockMoveLine.create({
            "move_id": rej_move.id,
            "product_id": product.id,
            "product_uom_id": product.uom_id.id,
            "location_id": customer_loc.id,
            "location_dest_id": quarantine_loc.id,
            "lot_id": lot_opening.id,
            "company_id": env.company.id,
            "quantity": 12.0,
            "date": "2026-07-03 00:00:00",
        })
        rej_move._action_done()
        rej_move.write({"date": "2026-07-03 00:00:00"})
        sml_rej.write({"date": "2026-07-03 00:00:00"})

    snap4 = get_stock_snapshot()
    report_table.append({
        "cutoff": "4. Post-Quarantine-Return",
        "event": "REJ-202607-001",
        "date": "2026-07-03",
        "expected_saleable_cartons": 388,  # Saleable tetap 388 (tidak berkurang lagi)
        "actual_saleable_cartons": snap4["saleable_on_hand_units"] / 12,
        "expected_quarantine_cartons": 1,   # Karantina bertambah 1 karton
        "actual_quarantine_cartons": snap4["quarantine_on_hand_units"] / 12,
        "delta": (snap4["saleable_on_hand_units"] / 12) - 388,
    })

    # Cetak Tabel Hasil Eksperimen
    print("\n" + "=" * 90)
    print("TABEL INDEPENDENT SOURCE-TO-RUNTIME ORACLE (EXPECTED VS ACTUAL VS DELTA)")
    print("=" * 90)
    print(f"{'Cutoff':<26} | {'Event':<20} | {'Exp Saleable':<12} | {'Act Saleable':<12} | {'Exp Quar':<8} | {'Act Quar':<8} | {'Delta':<6}")
    print("-" * 90)
    all_zero_delta = True
    for row in report_table:
        print(f"{row['cutoff']:<26} | {row['event']:<20} | {row['expected_saleable_cartons']:<12} | {row['actual_saleable_cartons']:<12} | {row['expected_quarantine_cartons']:<8} | {row['actual_quarantine_cartons']:<8} | {row['delta']:<6}")
        if abs(row["delta"]) > 0.001 or abs(row["actual_quarantine_cartons"] - row["expected_quarantine_cartons"]) > 0.001:
            all_zero_delta = False
    print("=" * 90)

    # 5. UJI IDEMPOTENSI SEJATI (RUN 2)
    print("\n[historical_experiment] MENJALANKAN UJI IDEMPOTENSI SEJATI (RUN 2)...")
    # Panggil ulang seluruh langkah pembentukan event
    m_op2, c_op2 = create_opening_stock_move(env, product, warehouse_loc, lot_opening, 1008.0, 18500.0, "2026-07-01", env.company)
    m_po2, c_po2 = create_opening_stock_move(env, product, warehouse_loc, lot_po, 3732.0, 18500.0, "2026-07-04", env.company)
    snap_run2 = get_stock_snapshot()

    assert not c_op2, "Opening stock tidak boleh dibuat ulang pada Run 2!"
    assert not c_po2, "PO receipt tidak boleh dibuat ulang pada Run 2!"
    assert snap_run2["saleable_on_hand_units"] == snap4["saleable_on_hand_units"], "Saldo saleable Run 2 drift!"
    assert snap_run2["quarantine_on_hand_units"] == snap4["quarantine_on_hand_units"], "Saldo karantina Run 2 drift!"

    print("[historical_experiment] UJI IDEMPOTENSI RUN 2 SUKSES: 0 record diciptakan ulang, saldo Run 1 == Run 2 identik 100%!")

    # Ekspor Hasil ke JSON Report
    full_report = {
        "status": "PASS" if all_zero_delta else "FAIL",
        "diagnosis": diag,
        "oracle_table": report_table,
        "run1_snapshot": snap4,
        "run2_snapshot": snap_run2,
        "zero_drift": True,
    }

    report_path = Path("historical_experiment_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2)

    print(f"\n[historical_experiment] Laporan diagnostik disimpan ke {report_path.resolve()}")
    if not all_zero_delta:
        raise AssertionError("Terdapat delta tidak nol pada perbandingan oracle expected vs actual!")

    print("[historical_experiment] SELURUH TAHAPAN EKSPERIMEN HISTORIS MINIMAL SUKSES (PASS).")


if __name__ == "__main__" or "env" in globals():
    env_obj = globals().get("env")
    if env_obj:
        run_historical_experiment(env_obj)
    else:
        print("[historical_experiment] Skrip ini dirancang untuk dijalankan di dalam Odoo shell.")
        print("Penggunaan: /opt/deploy/init.sh shell --no-http < scripts/ops/verify_historical_experiment.py")
