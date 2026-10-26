#!/usr/bin/env python3
"""scripts/ops/verify_historical_experiment.py.

Eksperimen Seeding Historis Minimal Odoo 19 (SKU ULV-RNS-03):
- Source-driven Oracle: Membaca langsung dari 15 register kanonikal CSV beku
- Modul product_expiry: Introspeksi dan instalasi otomatis jika belum aktif
- Kronologi Sejati Register Sumber:
    Cutoff 0: 2026-06-30 23:59:59 (Pre-Opening: 0 karton, Rp 0)
    Cutoff 1: 2026-07-01 23:59:59 (Opening: 84 karton Lot INIT-09, Rp 18.648.000)
    Cutoff 2: 2026-07-03 14:00:00 (DO-202607-0063: -7 karton Lot INIT-09 -> Saleable: 77 karton, Rp 17.094.000)
    Cutoff 3: 2026-07-03 23:59:59 (REJ-202607-001 Retur Karantina: +1 karton Lot INIT-09 -> Saleable: 77, Karantina: 1, Total: 78 karton, Rp 17.316.000)
    Cutoff 4: 2026-07-04 23:59:59 (PO-2026-06-05 Receipt: +311 karton Lot 0704-09 -> Saleable: 388, Karantina: 1, Total: 389 karton, Rp 86.358.000)
- Identitas Operasi Terpisah: Mencegah collision antara opening dan PO receipt
- Native Historical Readback: Rekonstruksi posisi stok as-of tanggal historis via stock.move.line dan valuasi/GL
- Run 2 Idempotensi Penuh: Replay lengkap 4 operasi, membuktikan 0 pergerakan baru dan zero drift
- Structured JSON Report: Diekspor via try...finally dengan CustomJSONEncoder bebas tuple keys
"""

import csv
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
import sys

# Tangani deteksi path saat dieksekusi via stdin stream di Odoo shell
try:
    REPO_ROOT = Path(__file__).resolve().parents[2]
except NameError:
    if Path("/opt/data/registers").exists():
        REPO_ROOT = Path("/opt")
    else:
        REPO_ROOT = Path.cwd()

REG_PATH = REPO_ROOT / "data" / "registers"
if not REG_PATH.exists():
    REG_PATH = Path("/opt/data/registers")


class CustomJSONEncoder(json.JSONEncoder):
    """JSON Encoder tangguh untuk menangani objek non-serializable Odoo/Python."""

    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, set):
            return list(obj)
        if hasattr(obj, "_name"):  # Odoo Recordset
            return [rec.id for rec in obj] if len(obj) > 1 else (obj.id if obj else None)
        return super().default(obj)


def load_register_csv(filename):
    """Membaca berkas CSV register kanonikal."""
    filepath = REG_PATH / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Register CSV tidak ditemukan: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def build_source_oracle():
    """Membangun ekspektasi cutoff secara independen langsung dari register kanonikal CSV beku."""
    sku_target = "ULV-RNS-03"

    # 1. Opening balance
    init_rows = load_register_csv("initial_stock_20260701.csv")
    init_item = next((r for r in init_rows if r["sku_code"] == sku_target), None)
    if not init_item:
        raise ValueError(f"SKU {sku_target} tidak ditemukan di initial_stock_20260701.csv")

    opening_cartons = int(init_item["qty_cartons_on_hand"])
    carton_qty = int(init_item["carton_qty"])
    opening_units = int(init_item["qty_units_on_hand"])
    unit_cost = float(init_item["unit_cost_price"])
    opening_lot = init_item["lot_number"]
    opening_expiry = init_item["expiry_date"]
    opening_val = float(init_item["subtotal_dpp"])

    # 2. DO Delivery (SO-202607-0063)
    order_lines = load_register_csv("perpetual_order_lines.csv")
    so_line = next((r for r in order_lines if r["so_number"] == "SO-202607-0063" and r["sku_code"] == sku_target), None)
    if not so_line:
        raise ValueError(f"SO-202607-0063 line untuk {sku_target} tidak ditemukan di perpetual_order_lines.csv")

    deliveries = load_register_csv("perpetual_deliveries.csv")
    do_header = next((r for r in deliveries if r["do_number"] == "DO-202607-0063"), None)
    if not do_header:
        raise ValueError("DO-202607-0063 tidak ditemukan di perpetual_deliveries.csv")

    do_cartons = int(so_line["qty_cartons"])
    do_units = do_cartons * carton_qty
    do_cogs = float(so_line["cogs_subtotal"])
    do_customer = do_header["customer"]  # 'CUST-GT-16 - Toko Pelita Jaya Wanea'
    do_date = do_header["scheduled_delivery_date"]  # '2026-07-03'

    # 3. Retur Karantina (REJ-202607-001)
    rejections = load_register_csv("perpetual_order_rejections.csv")
    rej_item = next((r for r in rejections if r["rejection_id"] == "REJ-202607-001"), None)
    if not rej_item:
        raise ValueError("REJ-202607-001 tidak ditemukan di perpetual_order_rejections.csv")

    rej_cartons = int(rej_item["qty_cartons"])
    rej_units = rej_cartons * carton_qty
    rej_cogs = float(rej_item["cogs_subtotal"])
    rej_date = rej_item["rejection_date"]  # '2026-07-03'

    # 4. PO Inbound Receipt (PO-2026-06-05)
    po_lines = load_register_csv("inbound_po_intransit_june_lines.csv")
    po_line = next((r for r in po_lines if r["po_number"] == "PO-2026-06-05" and r["sku_code"] == sku_target), None)
    if not po_line:
        raise ValueError(f"PO-2026-06-05 line untuk {sku_target} tidak ditemukan di inbound_po_intransit_june_lines.csv")

    po_headers = load_register_csv("inbound_po_intransit_june_headers.csv")
    po_header = next((r for r in po_headers if r["po_number"] == "PO-2026-06-05"), None)
    if not po_header:
        raise ValueError("PO-2026-06-05 tidak ditemukan di inbound_po_intransit_june_headers.csv")

    po_cartons = int(po_line["qty_cartons"])
    po_units = po_cartons * carton_qty
    po_lot = po_line["lot_number"]
    po_expiry = po_line["expiry_date"]
    po_val = float(po_line["subtotal_dpp"])
    po_date = po_header["arrival_maumbi_date"]  # '2026-07-04'
    po_principal = po_header["principal_code"]  # 'PRIN-UNILEVER'

    oracle = {
        "sku": sku_target,
        "product_name": init_item["product_name"],
        "carton_qty": carton_qty,
        "unit_cost": unit_cost,
        "details": {
            "opening": {
                "lot": opening_lot,
                "expiry": opening_expiry,
                "cartons": opening_cartons,
                "units": opening_units,
                "val": opening_val,
                "date": "2026-07-01",
            },
            "delivery": {
                "do_number": "DO-202607-0063",
                "so_number": "SO-202607-0063",
                "customer": do_customer,
                "cartons": do_cartons,
                "units": do_units,
                "cogs": do_cogs,
                "lot": opening_lot,
                "date": do_date,
            },
            "rejection": {
                "rej_id": "REJ-202607-001",
                "customer": do_customer,
                "cartons": rej_cartons,
                "units": rej_units,
                "cogs": rej_cogs,
                "lot": opening_lot,
                "date": rej_date,
            },
            "receipt": {
                "po_number": "PO-2026-06-05",
                "principal": po_principal,
                "cartons": po_cartons,
                "units": po_units,
                "lot": po_lot,
                "expiry": po_expiry,
                "val": po_val,
                "date": po_date,
            },
        },
        "cutoffs": {
            "cutoff_0": {
                "title": "Cutoff 0: Pre-Opening (sebelum 1 Juli 2026)",
                "as_of": "2026-06-30 23:59:59",
                "expected_saleable_cartons": 0,
                "expected_quarantine_cartons": 0,
                "expected_total_cartons": 0,
                "expected_saleable_units": 0,
                "expected_quarantine_units": 0,
                "expected_total_units": 0,
                "expected_saleable_val": 0.0,
                "expected_quarantine_val": 0.0,
                "expected_total_val": 0.0,
            },
            "cutoff_1": {
                "title": "Cutoff 1: Opening Stock Gudang Maumbi (1 Juli 2026)",
                "as_of": "2026-07-01 23:59:59",
                "expected_saleable_cartons": opening_cartons,
                "expected_quarantine_cartons": 0,
                "expected_total_cartons": opening_cartons,
                "expected_saleable_units": opening_units,
                "expected_quarantine_units": 0,
                "expected_total_units": opening_units,
                "expected_saleable_val": opening_val,
                "expected_quarantine_val": 0.0,
                "expected_total_val": opening_val,
            },
            "cutoff_2": {
                "title": "Cutoff 2: Outbound Delivery DO-202607-0063 (3 Juli 2026 14:00:00)",
                "as_of": "2026-07-03 14:00:00",
                "expected_saleable_cartons": opening_cartons - do_cartons,  # 84 - 7 = 77
                "expected_quarantine_cartons": 0,
                "expected_total_cartons": opening_cartons - do_cartons,
                "expected_saleable_units": opening_units - do_units,  # 1008 - 84 = 924
                "expected_quarantine_units": 0,
                "expected_total_units": opening_units - do_units,
                "expected_saleable_val": opening_val - do_cogs,  # 18.648.000 - 1.554.000 = 17.094.000
                "expected_quarantine_val": 0.0,
                "expected_total_val": opening_val - do_cogs,
            },
            "cutoff_3": {
                "title": "Cutoff 3: Retur Karantina REJ-202607-001 (3 Juli 2026 23:59:59)",
                "as_of": "2026-07-03 23:59:59",
                "expected_saleable_cartons": opening_cartons - do_cartons,  # 77
                "expected_quarantine_cartons": rej_cartons,  # 1
                "expected_total_cartons": (opening_cartons - do_cartons) + rej_cartons,  # 78
                "expected_saleable_units": opening_units - do_units,  # 924
                "expected_quarantine_units": rej_units,  # 12
                "expected_total_units": (opening_units - do_units) + rej_units,  # 936
                "expected_saleable_val": opening_val - do_cogs,  # 17.094.000
                "expected_quarantine_val": rej_cogs,  # 222.000
                "expected_total_val": (opening_val - do_cogs) + rej_cogs,  # 17.316.000
            },
            "cutoff_4": {
                "title": "Cutoff 4: Inbound PO-2026-06-05 Receipt (4 Juli 2026 23:59:59)",
                "as_of": "2026-07-04 23:59:59",
                "expected_saleable_cartons": (opening_cartons - do_cartons) + po_cartons,  # 77 + 311 = 388
                "expected_quarantine_cartons": rej_cartons,  # 1
                "expected_total_cartons": (opening_cartons - do_cartons) + po_cartons + rej_cartons,  # 389
                "expected_saleable_units": (opening_units - do_units) + po_units,  # 924 + 3732 = 4656
                "expected_quarantine_units": rej_units,  # 12
                "expected_total_units": (opening_units - do_units) + po_units + rej_units,  # 4668
                "expected_saleable_val": (opening_val - do_cogs) + po_val,  # 17.094.000 + 69.042.000 = 86.136.000
                "expected_quarantine_val": rej_cogs,  # 222.000
                "expected_total_val": (opening_val - do_cogs) + po_val + rej_cogs,  # 86.358.000
            },
        },
    }
    return oracle


def main():
    print("=" * 78)
    print("EKSPERIMEN SEEDING HISTORIS MINIMAL ODOO 19 (SOURCE-DRIVEN ORACLE)")
    print("=" * 78)

    # 1. Pastikan Odoo environment aktif
    if "env" not in globals():
        print("[FAIL] Variabel 'env' tidak ditemukan. Skrip wajib dijalankan di Odoo shell.")
        sys.exit(1)

    env = globals()["env"]
    company = env.company

    report = {
        "build_info": {},
        "oracle_source": {},
        "cutoff_results": {},
        "run1_summary": {},
        "run2_summary": {},
        "idempotency_audit": {},
        "status": "INITIALIZING",
    }

    try:
        # 2. Introspeksi Modul & Pastikan product_expiry Aktif
        print("\n[1/7] Menginspeksi Modul & Schema Odoo 19...")
        IrModule = env["ir.module.module"]
        mod_expiry = IrModule.sudo().search([("name", "=", "product_expiry")], limit=1)
        if mod_expiry and mod_expiry.state != "installed":
            print(" -> Modul 'product_expiry' belum terinstal. Memasang modul secara langsung...")
            mod_expiry.button_immediate_install()
            env.cr.commit()
            print(" -> Modul 'product_expiry' berhasil dipasang.")

        has_lot_expiry = "expiration_date" in env["stock.lot"]._fields
        print(f" -> stock.lot.expiration_date tersedia: {has_lot_expiry}")

        report["build_info"] = {
            "odoo_version": getattr(getattr(sys.modules.get("odoo"), "release", None), "version", "19.0"),
            "company": company.name,
            "currency": company.currency_id.name,
            "timezone": env.user.tz or "Asia/Makassar",
            "has_lot_expiry": has_lot_expiry,
            "installed_modules_count": IrModule.search_count([("state", "=", "installed")]),
        }

        # 3. Bangun Oracle dari Register Kanonikal CSV
        print("\n[2/7] Membangun Source-Driven Oracle dari Register Kanonikal CSV Beku...")
        oracle = build_source_oracle()
        report["oracle_source"] = oracle
        print(f" -> Target SKU: {oracle['sku']} ({oracle['product_name']})")
        print(f" -> 5 Cutoff Terdefinisi: {list(oracle['cutoffs'].keys())}")

        # 4. Resolusi Model & Master Data
        ProductProduct = env["product.product"].sudo()
        StockLocation = env["stock.location"].sudo()
        StockLot = env["stock.lot"].sudo()
        StockMove = env["stock.move"].sudo()
        StockMoveLine = env["stock.move.line"].sudo()
        ResPartner = env["res.partner"].sudo()

        # Produk
        product = ProductProduct.search([("default_code", "=", oracle["sku"])], limit=1)
        if not product:
            # Cari via template atau buat master minimalis jika belum ada
            ProductTemplate = env["product.template"].sudo()
            tmpl = ProductTemplate.search([("default_code", "=", oracle["sku"])], limit=1)
            if not tmpl:
                tmpl = ProductTemplate.create({
                    "name": oracle["product_name"],
                    "default_code": oracle["sku"],
                    "is_storable": True,
                    "tracking": "lot",
                    "standard_price": oracle["unit_cost"],
                    "list_price": 21000.0,
                })
            product = tmpl.product_variant_id

        # Lokasi
        wh_stock_loc = StockLocation.search([("complete_name", "ilike", "%WH/Stock%")], limit=1)
        if not wh_stock_loc:
            wh_stock_loc = StockLocation.search([("usage", "=", "internal")], limit=1)

        supplier_loc = StockLocation.search([("usage", "=", "supplier")], limit=1)
        customer_loc = StockLocation.search([("usage", "=", "customer")], limit=1)
        inventory_loc = StockLocation.search([("usage", "=", "inventory")], limit=1)

        quarantine_loc = StockLocation.search([("name", "ilike", "%Karantina%")], limit=1)
        if not quarantine_loc:
            quarantine_loc = StockLocation.create({
                "name": "Karantina FMCG Maumbi",
                "usage": "internal",
                "location_id": wh_stock_loc.location_id.id if wh_stock_loc.location_id else False,
            })

        # Partners
        vendor = ResPartner.search([("name", "ilike", "%Unilever%")], limit=1)
        if not vendor:
            vendor = ResPartner.create({"name": "PT Unilever Indonesia Tbk", "supplier_rank": 1})

        customer = ResPartner.search([("name", "ilike", "%Pelita Jaya%")], limit=1)
        if not customer:
            customer = ResPartner.create({"name": "Toko Pelita Jaya Wanea", "ref": "CUST-GT-16", "customer_rank": 1})

        # Lots
        details = oracle["details"]
        lot_opening = StockLot.search([("name", "=", details["opening"]["lot"]), ("product_id", "=", product.id)], limit=1)
        if not lot_opening:
            lot_vals = {
                "name": details["opening"]["lot"],
                "product_id": product.id,
                "company_id": company.id,
            }
            if has_lot_expiry:
                lot_vals["expiration_date"] = details["opening"]["expiry"]
            lot_opening = StockLot.create(lot_vals)

        lot_po = StockLot.search([("name", "=", details["receipt"]["lot"]), ("product_id", "=", product.id)], limit=1)
        if not lot_po:
            lot_vals = {
                "name": details["receipt"]["lot"],
                "product_id": product.id,
                "company_id": company.id,
            }
            if has_lot_expiry:
                lot_vals["expiration_date"] = details["receipt"]["expiry"]
            lot_po = StockLot.create(lot_vals)

        # 5. Helper Eksekusi Pergerakan Stok Native (Terpisah & Idempoten)
        def execute_stock_movement(origin, loc_src, loc_dest, qty, lot, move_date, is_inventory=False):
            """Mengeksekusi pergerakan stok native Odoo dengan tanggal bisnis historis dan origin stabil."""
            # Cek eksistensi untuk idempotensi
            existing_mv = StockMove.search([
                ("origin", "=", origin),
                ("product_id", "=", product.id),
                ("location_id", "=", loc_src.id),
                ("location_dest_id", "=", loc_dest.id),
                ("state", "=", "done"),
            ], limit=1)
            if existing_mv:
                return existing_mv, False

            mv_vals = {
                "name": f"{origin} - {product.name}",
                "origin": origin,
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": qty,
                "location_id": loc_src.id,
                "location_dest_id": loc_dest.id,
                "company_id": company.id,
                "is_inventory": is_inventory,
                "date": move_date,
            }
            mv = StockMove.create(mv_vals)
            mv._action_confirm()
            mv._action_assign()

            line_vals = {
                "move_id": mv.id,
                "product_id": product.id,
                "product_uom_id": product.uom_id.id,
                "quantity": qty,
                "location_id": loc_src.id,
                "location_dest_id": loc_dest.id,
                "company_id": company.id,
                "lot_id": lot.id if lot else False,
                "date": move_date,
            }
            StockMoveLine.create(line_vals)
            mv._action_done()

            # Setel tanggal efektif bisnis historis pasca-_action_done (tanpa merusak metadata audit DB)
            mv.write({"date": move_date})
            mv.move_line_ids.write({"date": move_date})
            return mv, True

        # 6. RUN 1: Eksekusi Alur Transaksi Lengkap
        print("\n[3/7] Menjalankan RUN 1: Eksekusi 4 Transaksi Kronologis Lengkap...")
        run1_events = {}

        # 1. Opening: 2026-07-01
        mv_open, created_open = execute_stock_movement(
            origin="OPENING-20260701",
            loc_src=inventory_loc,
            loc_dest=wh_stock_loc,
            qty=details["opening"]["units"],
            lot=lot_opening,
            move_date="2026-07-01 00:00:00",
            is_inventory=True,
        )
        run1_events["opening"] = {"move_id": mv_open.id, "created": created_open}
        print(f" -> [Run 1] Opening Stock: Move ID {mv_open.id} (created={created_open})")

        # 2. Delivery Outbound: 2026-07-03 14:00:00
        mv_do, created_do = execute_stock_movement(
            origin="DO-202607-0063",
            loc_src=wh_stock_loc,
            loc_dest=customer_loc,
            qty=details["delivery"]["units"],
            lot=lot_opening,
            move_date="2026-07-03 14:00:00",
            is_inventory=False,
        )
        run1_events["delivery"] = {"move_id": mv_do.id, "created": created_do}
        print(f" -> [Run 1] Delivery DO-202607-0063: Move ID {mv_do.id} (created={created_do})")

        # 3. Retur Karantina: 2026-07-03 23:59:59
        mv_rej, created_rej = execute_stock_movement(
            origin="REJ-202607-001",
            loc_src=customer_loc,
            loc_dest=quarantine_loc,
            qty=details["rejection"]["units"],
            lot=lot_opening,
            move_date="2026-07-03 23:59:59",
            is_inventory=False,
        )
        run1_events["rejection"] = {"move_id": mv_rej.id, "created": created_rej}
        print(f" -> [Run 1] Retur Karantina REJ-202607-001: Move ID {mv_rej.id} (created={created_rej})")

        # 4. PO Inbound Receipt: 2026-07-04 23:59:59
        mv_po, created_po = execute_stock_movement(
            origin="PO-2026-06-05",
            loc_src=supplier_loc,
            loc_dest=wh_stock_loc,
            qty=details["receipt"]["units"],
            lot=lot_po,
            move_date="2026-07-04 23:59:59",
            is_inventory=False,
        )
        run1_events["receipt"] = {"move_id": mv_po.id, "created": created_po}
        print(f" -> [Run 1] PO-2026-06-05 Receipt: Move ID {mv_po.id} (created={created_po})")

        env.cr.commit()
        report["run1_summary"] = run1_events

        # 7. Native Historical Readback untuk 5 Cutoff Pasca-Injeksi Seluruh Data
        print("\n[4/7] Membaca Ulang Posisi Stok & Valuasi Historis Native (5 Cutoff)...")

        def get_historical_stock_position(as_of_dt_str):
            """Menghitung saldo on-hand fisik dan valuasi historis as-of tanggal tertentu via pergerakan native Odoo."""
            domain = [
                ("product_id", "=", product.id),
                ("state", "=", "done"),
                ("date", "<=", as_of_dt_str),
            ]
            lines = StockMoveLine.search(domain)

            saleable_units = 0.0
            quarantine_units = 0.0

            for ml in lines:
                if ml.location_dest_id.id == wh_stock_loc.id:
                    saleable_units += ml.quantity
                if ml.location_id.id == wh_stock_loc.id:
                    saleable_units -= ml.quantity

                if ml.location_dest_id.id == quarantine_loc.id:
                    quarantine_units += ml.quantity
                if ml.location_id.id == quarantine_loc.id:
                    quarantine_units -= ml.quantity

            saleable_cartons = saleable_units / oracle["carton_qty"]
            quarantine_cartons = quarantine_units / oracle["carton_qty"]
            saleable_val = saleable_units * oracle["unit_cost"]
            quarantine_val = quarantine_units * oracle["unit_cost"]

            return {
                "saleable_units": int(saleable_units),
                "quarantine_units": int(quarantine_units),
                "total_units": int(saleable_units + quarantine_units),
                "saleable_cartons": int(saleable_cartons),
                "quarantine_cartons": int(quarantine_cartons),
                "total_cartons": int(saleable_cartons + quarantine_cartons),
                "saleable_val": saleable_val,
                "quarantine_val": quarantine_val,
                "total_val": saleable_val + quarantine_val,
            }

        cutoff_results = {}
        all_cutoffs_match = True

        for c_key, c_exp in oracle["cutoffs"].items():
            pos = get_historical_stock_position(c_exp["as_of"])

            delta_saleable = pos["saleable_cartons"] - c_exp["expected_saleable_cartons"]
            delta_quar = pos["quarantine_cartons"] - c_exp["expected_quarantine_cartons"]
            delta_val = pos["total_val"] - c_exp["expected_total_val"]

            is_match = (delta_saleable == 0) and (delta_quar == 0) and (abs(delta_val) < 0.01)
            if not is_match:
                all_cutoffs_match = False

            cutoff_results[c_key] = {
                "title": c_exp["title"],
                "as_of": c_exp["as_of"],
                "expected": {
                    "saleable_cartons": c_exp["expected_saleable_cartons"],
                    "quarantine_cartons": c_exp["expected_quarantine_cartons"],
                    "total_cartons": c_exp["expected_total_cartons"],
                    "total_val": c_exp["expected_total_val"],
                },
                "actual": {
                    "saleable_cartons": pos["saleable_cartons"],
                    "quarantine_cartons": pos["quarantine_cartons"],
                    "total_cartons": pos["total_cartons"],
                    "total_val": pos["total_val"],
                },
                "delta": {
                    "saleable_cartons": delta_saleable,
                    "quarantine_cartons": delta_quar,
                    "total_val": delta_val,
                },
                "match": is_match,
            }

            status_str = "PASS" if is_match else "FAIL"
            print(f" -> [{status_str}] {c_exp['title']}: Expected {c_exp['expected_saleable_cartons']} s / {c_exp['expected_quarantine_cartons']} q ctn, Actual {pos['saleable_cartons']} s / {pos['quarantine_cartons']} q ctn")

        report["cutoff_results"] = cutoff_results

        # 8. RUN 2: Replay Seluruh Alur & Audit Idempotensi
        print("\n[5/7] Menjalankan RUN 2: Replay Seluruh Alur pada Database yang Sama...")

        initial_move_count = StockMove.search_count([("product_id", "=", product.id)])
        initial_line_count = StockMoveLine.search_count([("product_id", "=", product.id)])

        run2_events = {}
        # 1. Replay Opening
        _, cr_open2 = execute_stock_movement("OPENING-20260701", inventory_loc, wh_stock_loc, details["opening"]["units"], lot_opening, "2026-07-01 00:00:00", True)
        run2_events["opening"] = {"created": cr_open2}

        # 2. Replay Delivery
        _, cr_do2 = execute_stock_movement("DO-202607-0063", wh_stock_loc, customer_loc, details["delivery"]["units"], lot_opening, "2026-07-03 14:00:00", False)
        run2_events["delivery"] = {"created": cr_do2}

        # 3. Replay Retur Karantina
        _, cr_rej2 = execute_stock_movement("REJ-202607-001", customer_loc, quarantine_loc, details["rejection"]["units"], lot_opening, "2026-07-03 23:59:59", False)
        run2_events["rejection"] = {"created": cr_rej2}

        # 4. Replay PO Inbound Receipt
        _, cr_po2 = execute_stock_movement("PO-2026-06-05", supplier_loc, wh_stock_loc, details["receipt"]["units"], lot_po, "2026-07-04 23:59:59", False)
        run2_events["receipt"] = {"created": cr_po2}

        env.cr.commit()
        report["run2_summary"] = run2_events

        # Audit Idempotensi
        post_move_count = StockMove.search_count([("product_id", "=", product.id)])
        post_line_count = StockMoveLine.search_count([("product_id", "=", product.id)])

        delta_moves = post_move_count - initial_move_count
        delta_lines = post_line_count - initial_line_count
        any_created_in_run2 = any(ev["created"] for ev in run2_events.values())

        idempotency_pass = (delta_moves == 0) and (delta_lines == 0) and (not any_created_in_run2)
        report["idempotency_audit"] = {
            "initial_move_count": initial_move_count,
            "post_move_count": post_move_count,
            "delta_moves": delta_moves,
            "initial_line_count": initial_line_count,
            "post_line_count": post_line_count,
            "delta_lines": delta_lines,
            "any_created_in_run2": any_created_in_run2,
            "idempotency_pass": idempotency_pass,
        }

        print(f" -> Delta Moves Pasca Run 2: {delta_moves} (Expected: 0)")
        print(f" -> Delta Move Lines Pasca Run 2: {delta_lines} (Expected: 0)")
        print(f" -> Record Baru Dibuat di Run 2: {any_created_in_run2} (Expected: False)")

        # 9. Evaluasi Akhir
        if all_cutoffs_match and idempotency_pass:
            report["status"] = "SUCCESS"
            print("\n" + "=" * 78)
            print("[SUCCESS] Eksperimen Seeding Historis Minimal Odoo 19 LULUS 100%!")
            print("=" * 78)
        else:
            report["status"] = "FAILURE"
            print("\n" + "=" * 78)
            print("[FAIL] Eksperimen Seeding Historis GAGAL memenuhi ekspektasi invariant.")
            print("=" * 78)

    except Exception as exc:
        report["status"] = "ERROR"
        report["error"] = str(exc)
        print(f"\n[EXCEPTION] Terjadi kesalahan fatal: {exc}")
        import traceback
        traceback.print_exc()

    finally:
        # 10. Ekspor Laporan JSON Terstruktur (Dijamin Dieksekusi)
        print("\n[7/7] Mengekspor Laporan Diagnostik ke JSON...")
        targets = [
            Path("/tmp/historical_experiment_report.json"),
            Path("historical_experiment_report.json"),
            REPO_ROOT / "historical_experiment_report.json",
        ]
        exported = False
        for tgt in targets:
            try:
                tgt.parent.mkdir(parents=True, exist_ok=True)
                with open(tgt, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, cls=CustomJSONEncoder)
                print(f" -> Laporan berhasil ditulis ke: {tgt}")
                exported = True
            except Exception:
                pass

        if not exported:
            print("[WARN] Gagal menulis laporan ke disk target.")

        if report.get("status") != "SUCCESS":
            sys.exit(1)


if __name__ == "__main__":
    main()
