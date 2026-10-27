#!/usr/bin/env python3
"""scripts/ops/verify_historical_experiment.py.

Eksperimen Seeding Historis Minimal Odoo 19 (SKU ULV-RNS-03):
- Verifikasi Fingerprint SHA256 Seluruh 15 Register Kanonikal CSV Beku (Dynamic dari JSON Metadata + LF Normalization)
- Source-driven Dynamic Oracle dari Register Sumber
- Kronologi Sejati: Opening (1 Juli) -> DO Delivery (3 Juli) -> Retur Karantina (3 Juli) -> Receipt PO (4 Juli)
- Metode Opening Quant: Inventory adjustment native Odoo 19 (action_apply_inventory)
- Native Historical Readback Pasca-Injeksi: Evaluasi saldo fisik as-of per tanggal via stock.move.line
- Readback Valuasi & GL Aktual Odoo: stock.valuation.layer (jika tersedia) & GL Persediaan account.move.line menentukan kelulusan
- Pemisahan Tegas Loader vs Validator: Loader murni mengeksekusi Odoo native tanpa manipulasi nilai/jurnal sintetis; Validator read-only
- Run 2 Zero-Drift Idempotency Penuh: Deep snapshot comparison (exact IDs, dates, lots, quantities, GL, SVL)
- Actual Mutation Tests (Savepoints): Uji mutasi salah tanggal (now), mutasi nilai GL/SVL (balanced journal entry), dan kebocoran receipt masa depan
- Structured JSON Report: Diekspor via try...finally dengan CustomJSONEncoder bebas tuple keys
"""

import csv
from datetime import date, datetime
from decimal import Decimal
import hashlib
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
            return sorted(list(obj))
        if hasattr(obj, "_name"):
            return [rec.id for rec in obj] if len(obj) > 1 else (obj.id if obj else None)
        return super().default(obj)


def canonical_file_hash(filepath: Path) -> str:
    """Menghitung SHA-256 kanonikal dengan normalisasi newline LF."""
    content = filepath.read_bytes()
    normalized = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def verify_register_fingerprints():
    """Memverifikasi hash SHA256 seluruh 15 register kanonikal CSV beku terhadap metadata kanonikal (normalisasi LF)."""
    recon_json_path = REG_PATH / "canonical_financial_reconciliation_july_2026.json"
    if not recon_json_path.exists():
        raise FileNotFoundError(f"Metadata rekonsiliasi kanonikal tidak ditemukan di {recon_json_path}")

    recon_meta = json.loads(recon_json_path.read_text(encoding="utf-8"))
    expected_hashes = recon_meta.get("input_dataset_sha256", {})
    if not expected_hashes or len(expected_hashes) != 15:
        raise ValueError(
            f"Metadata input_dataset_sha256 tidak lengkap (diharapkan 15 register, ditemukan {len(expected_hashes)})"
        )

    results = {}
    mismatches = []
    for filename, expected_hash in expected_hashes.items():
        filepath = REG_PATH / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Register CSV wajib tidak ditemukan: {filepath}")
        actual_hash = canonical_file_hash(filepath)
        if actual_hash != expected_hash:
            mismatches.append((filename, expected_hash, actual_hash))
        results[filename] = actual_hash

    if mismatches:
        err_msg = "\n".join(f" - {f}: expected {exp[:10]}... got {act[:10]}..." for f, exp, act in mismatches)
        raise ValueError(f"Fingerprint register tidak cocok dengan rekonsiliasi kanonikal:\n{err_msg}")

    return results


def load_register_csv(filename):
    """Membaca berkas CSV register kanonikal."""
    filepath = REG_PATH / filename
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

    opening_cartons = float(init_item["qty_cartons_on_hand"])
    carton_qty = float(init_item["carton_qty"])
    opening_units = float(init_item["qty_units_on_hand"])
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

    do_cartons = float(so_line["qty_cartons"])
    do_units = do_cartons * carton_qty
    do_cogs = float(so_line["cogs_subtotal"])
    do_customer = do_header["customer"]
    do_date = do_header["scheduled_delivery_date"]
    do_lot = so_line["lot_number"]

    # 3. Retur Karantina (REJ-202607-001)
    rejections = load_register_csv("perpetual_order_rejections.csv")
    rej_item = next((r for r in rejections if r["rejection_id"] == "REJ-202607-001"), None)
    if not rej_item:
        raise ValueError("REJ-202607-001 tidak ditemukan di perpetual_order_rejections.csv")

    rej_cartons = float(rej_item["qty_cartons"])
    rej_units = rej_cartons * carton_qty
    rej_cogs = float(rej_item["cogs_subtotal"])
    rej_date = rej_item["rejection_date"]
    rej_lot = rej_item["lot_number"]

    # 4. PO Inbound Receipt (PO-2026-06-05)
    po_lines = load_register_csv("inbound_po_intransit_june_lines.csv")
    po_line = next((r for r in po_lines if r["po_number"] == "PO-2026-06-05" and r["sku_code"] == sku_target), None)
    if not po_line:
        raise ValueError(f"PO-2026-06-05 line untuk {sku_target} tidak ditemukan di inbound_po_intransit_june_lines.csv")

    po_headers = load_register_csv("inbound_po_intransit_june_headers.csv")
    po_header = next((r for r in po_headers if r["po_number"] == "PO-2026-06-05"), None)
    if not po_header:
        raise ValueError("PO-2026-06-05 tidak ditemukan di inbound_po_intransit_june_headers.csv")

    po_cartons = float(po_line["qty_cartons"])
    po_units = po_cartons * carton_qty
    po_val = float(po_line["subtotal_dpp"])
    po_date = po_header.get("arrival_maumbi_date") or po_header.get("actual_receipt_date") or "2026-07-04"
    po_lot = po_line["lot_number"]
    po_expiry = po_line["expiry_date"]

    oracle = {
        "sku": sku_target,
        "product_name": init_item["product_name"],
        "unit_cost": unit_cost,
        "carton_qty": carton_qty,
        "details": {
            "opening": {
                "origin": "OPENING-20260701",
                "cartons": opening_cartons,
                "units": opening_units,
                "lot": opening_lot,
                "expiry": opening_expiry,
                "val": opening_val,
                "date": "2026-07-01 00:00:00",
                "expected_debit_acc": "113000",
                "expected_credit_acc": "113900",
                "expected_amount": opening_val,
            },
            "delivery": {
                "origin": "DO-202607-0063",
                "customer": do_customer,
                "cartons": do_cartons,
                "units": do_units,
                "lot": do_lot,
                "cogs": do_cogs,
                "date": f"{do_date} 14:00:00",
                "expected_debit_acc": "510000",
                "expected_credit_acc": "113000",
                "expected_amount": do_cogs,
            },
            "rejection": {
                "origin": "REJ-202607-001",
                "cartons": rej_cartons,
                "units": rej_units,
                "lot": rej_lot,
                "cogs": rej_cogs,
                "date": f"{rej_date} 23:59:59",
                "expected_debit_acc": "113000",
                "expected_credit_acc": "510000",
                "expected_amount": rej_cogs,
            },
            "receipt": {
                "origin": "PO-2026-06-05",
                "cartons": po_cartons,
                "units": po_units,
                "lot": po_lot,
                "expiry": po_expiry,
                "val": po_val,
                "date": f"{po_date} 23:59:59",
                "expected_debit_acc": "113000",
                "expected_credit_acc": "113900",
                "expected_amount": po_val,
            },
        },
        "cutoffs": {
            "cutoff_0": {
                "title": "Cutoff 0: Pre-Opening (sebelum 1 Juli 2026)",
                "as_of": "2026-06-30 23:59:59",
                "expected_saleable_cartons": 0.0,
                "expected_quarantine_cartons": 0.0,
                "expected_total_cartons": 0.0,
                "expected_saleable_units": 0.0,
                "expected_quarantine_units": 0.0,
                "expected_total_units": 0.0,
                "expected_saleable_val": 0.0,
                "expected_quarantine_val": 0.0,
                "expected_total_val": 0.0,
                "expected_eod_gl": 0.0,
            },
            "cutoff_1": {
                "title": "Cutoff 1: Opening Stock Gudang Maumbi (1 Juli 2026)",
                "as_of": "2026-07-01 23:59:59",
                "expected_saleable_cartons": opening_cartons,
                "expected_quarantine_cartons": 0.0,
                "expected_total_cartons": opening_cartons,
                "expected_saleable_units": opening_units,
                "expected_quarantine_units": 0.0,
                "expected_total_units": opening_units,
                "expected_saleable_val": opening_val,
                "expected_quarantine_val": 0.0,
                "expected_total_val": opening_val,
                "expected_eod_gl": opening_val,
            },
            "cutoff_2": {
                "title": "Cutoff 2: Outbound Delivery DO-202607-0063 (3 Juli 2026 14:00:00)",
                "as_of": "2026-07-03 14:00:00",
                "expected_saleable_cartons": opening_cartons - do_cartons,
                "expected_quarantine_cartons": 0.0,
                "expected_total_cartons": opening_cartons - do_cartons,
                "expected_saleable_units": opening_units - do_units,
                "expected_quarantine_units": 0.0,
                "expected_total_units": opening_units - do_units,
                "expected_saleable_val": opening_val - do_cogs,
                "expected_quarantine_val": 0.0,
                "expected_total_val": opening_val - do_cogs,
                "expected_eod_gl": (opening_val - do_cogs) + rej_cogs,
            },
            "cutoff_3": {
                "title": "Cutoff 3: Retur Karantina REJ-202607-001 (3 Juli 2026 23:59:59)",
                "as_of": "2026-07-03 23:59:59",
                "expected_saleable_cartons": opening_cartons - do_cartons,
                "expected_quarantine_cartons": rej_cartons,
                "expected_total_cartons": (opening_cartons - do_cartons) + rej_cartons,
                "expected_saleable_units": opening_units - do_units,
                "expected_quarantine_units": rej_units,
                "expected_total_units": (opening_units - do_units) + rej_units,
                "expected_saleable_val": opening_val - do_cogs,
                "expected_quarantine_val": rej_cogs,
                "expected_total_val": (opening_val - do_cogs) + rej_cogs,
                "expected_eod_gl": (opening_val - do_cogs) + rej_cogs,
            },
            "cutoff_4": {
                "title": "Cutoff 4: Inbound PO-2026-06-05 Receipt (4 Juli 2026 23:59:59)",
                "as_of": "2026-07-04 23:59:59",
                "expected_saleable_cartons": (opening_cartons - do_cartons) + po_cartons,
                "expected_quarantine_cartons": rej_cartons,
                "expected_total_cartons": (opening_cartons - do_cartons) + po_cartons + rej_cartons,
                "expected_saleable_units": (opening_units - do_units) + po_units,
                "expected_quarantine_units": rej_units,
                "expected_total_units": (opening_units - do_units) + po_units + rej_units,
                "expected_saleable_val": (opening_val - do_cogs) + po_val,
                "expected_quarantine_val": rej_cogs,
                "expected_total_val": (opening_val - do_cogs) + po_val + rej_cogs,
                "expected_eod_gl": (opening_val - do_cogs) + po_val + rej_cogs,
            },
        },
    }
    return oracle


def allocate_and_sync_move_lines(env, mv, picking, demand_qty, target_lot=None, move_date=None):
    """Mengalokasikan move lines dengan fidelitas reservasi lot, verifikasi kecocokan lot kanonikal,
    guard penolakan stok negatif / reservasi kosong pada lokasi internal, dan sinkronisasi status picked."""
    StockMoveLine = env["stock.move.line"].sudo()
    StockMove = env["stock.move"].sudo()
    is_internal = (mv.location_id.usage == "internal")

    # 1. Guard Lokasi Internal: Tolak reservasi kosong & tolak kuantitas kurang
    if is_internal:
        if not mv.move_line_ids or len(mv.move_line_ids) == 0:
            loc_name = getattr(mv.location_id, "complete_name", None) or getattr(mv.location_id, "name", "Internal")
            raise ValueError(
                f"[FAIL-FAST] Reservasi kosong pada lokasi internal {loc_name} "
                f"untuk demand {demand_qty} (origin: {mv.origin})! Penolakan stok negatif/kurang."
            )
        total_reserved = sum(getattr(ml, "quantity", 0.0) or getattr(ml, "qty_done", 0.0) for ml in mv.move_line_ids)
        if total_reserved < (demand_qty - 0.0001):
            loc_name = getattr(mv.location_id, "complete_name", None) or getattr(mv.location_id, "name", "Internal")
            raise ValueError(
                f"[FAIL-FAST] Kuantitas reservasi ({total_reserved}) tidak mencukupi demand ({demand_qty}) "
                f"untuk {mv.origin} pada lokasi {loc_name}! Penolakan stok negatif/kurang."
            )

    # 2. Verifikasi Kesesuaian Lot Target Register Kanonikal
    if target_lot and mv.move_line_ids:
        for ml in mv.move_line_ids:
            if ml.lot_id and ml.lot_id.id != target_lot.id:
                raise ValueError(
                    f"[FAIL-FAST] Lot reservasi {ml.lot_id.name} (ID {ml.lot_id.id}) tidak cocok dengan lot target register "
                    f"{target_lot.name} (ID {target_lot.id}) untuk {mv.origin}!"
                )

    # 3. Alokasi Proporsional Multi-Line & Multi-Lot
    remaining_qty = demand_qty
    if mv.move_line_ids:
        for ml in mv.move_line_ids:
            line_cap = getattr(ml, "quantity", 0.0) or getattr(ml, "qty_done", 0.0)
            if line_cap <= 0.0 and len(mv.move_line_ids) == 1:
                line_cap = remaining_qty

            if remaining_qty > 0 and line_cap > 0:
                alloc = min(remaining_qty, line_cap)
                upd_vals = {}
                if not ml.lot_id and target_lot and "lot_id" in StockMoveLine._fields:
                    upd_vals["lot_id"] = target_lot.id
                if "quantity" in StockMoveLine._fields:
                    upd_vals["quantity"] = alloc
                elif "qty_done" in StockMoveLine._fields:
                    upd_vals["qty_done"] = alloc
                if "picked" in StockMoveLine._fields:
                    upd_vals["picked"] = True
                if "date" in StockMoveLine._fields and move_date:
                    upd_vals["date"] = move_date
                if "picking_id" in StockMoveLine._fields and picking:
                    upd_vals["picking_id"] = picking.id
                ml.write(upd_vals)
                remaining_qty -= alloc
            else:
                ml.unlink()

        if remaining_qty > 0.0001:
            if is_internal:
                raise ValueError(
                    f"[FAIL-FAST] Kuantitas reservasi tidak mencukupi demand ({demand_qty}) untuk {mv.origin}! Sisa tak teralokasi: {remaining_qty}"
                )
            candidate_sml = {
                "move_id": mv.id,
                "picking_id": picking.id if picking else False,
                "product_id": mv.product_id.id,
                "product_uom_id": mv.product_uom.id if hasattr(mv, "product_uom") and mv.product_uom else False,
                "product_uom": mv.product_uom.id if hasattr(mv, "product_uom") and mv.product_uom else False,
                "quantity": remaining_qty,
                "qty_done": remaining_qty,
                "location_id": mv.location_id.id,
                "location_dest_id": mv.location_dest_id.id,
                "company_id": mv.company_id.id if mv.company_id else False,
                "lot_id": target_lot.id if target_lot else False,
                "date": move_date,
            }
            if "picked" in StockMoveLine._fields:
                candidate_sml["picked"] = True
            line_vals = {k: v for k, v in candidate_sml.items() if k in StockMoveLine._fields}
            StockMoveLine.create(line_vals)
    else:
        # Move lines kosong hanya diizinkan untuk pergerakan non-internal (e.g. Inbound PO dari vendor)
        if is_internal:
            raise ValueError(
                f"[FAIL-FAST] Reservasi kosong pada lokasi internal untuk {mv.origin}! Penolakan stok negatif."
            )
        candidate_sml = {
            "move_id": mv.id,
            "picking_id": picking.id if picking else False,
            "product_id": mv.product_id.id,
            "product_uom_id": mv.product_uom.id if hasattr(mv, "product_uom") and mv.product_uom else False,
            "product_uom": mv.product_uom.id if hasattr(mv, "product_uom") and mv.product_uom else False,
            "quantity": demand_qty,
            "qty_done": demand_qty,
            "location_id": mv.location_id.id,
            "location_dest_id": mv.location_dest_id.id,
            "company_id": mv.company_id.id if mv.company_id else False,
            "lot_id": target_lot.id if target_lot else False,
            "date": move_date,
        }
        if "picked" in StockMoveLine._fields:
            candidate_sml["picked"] = True
        line_vals = {k: v for k, v in candidate_sml.items() if k in StockMoveLine._fields}
        StockMoveLine.create(line_vals)

    # 4. Assertion Fail-Fast: Total kuantitas move lines WAJIB sama persis dengan demand
    total_ml_qty = sum(getattr(ml, "quantity", getattr(ml, "qty_done", 0.0)) for ml in mv.move_line_ids)
    if abs(total_ml_qty - demand_qty) > 0.0001:
        raise ValueError(
            f"[FAIL-FAST] Alokasi kuantitas move line ({total_ml_qty}) tidak cocok dengan demand ({demand_qty}) untuk move {mv.origin}!"
        )

    # 5. Set status picked pada move dan move line
    if "picked" in StockMove._fields:
        mv.write({"picked": True})
        mv.picked = True
    for ml in mv.move_line_ids:
        if "picked" in StockMoveLine._fields:
            ml.write({"picked": True})
            ml.picked = True


def main():
    print("=" * 80)
    print("EKSPERIMEN SEEDING HISTORIS MINIMAL ODOO 19 — RUNTIME VERIFICATION")
    print("=" * 80)

    if "env" not in globals():
        print("[FAIL] Variabel 'env' tidak ditemukan. Skrip wajib dijalankan di Odoo shell.")
        sys.exit(1)

    env = globals()["env"]
    company = env.company

    report = {
        "build_info": {},
        "fingerprints": {},
        "oracle_source": {},
        "cutoff_results": {},
        "run1_summary": {},
        "run2_summary": {},
        "idempotency_audit": {},
        "mutation_tests": {},
        "status": "INITIALIZING",
    }

    try:
        # 1. Verifikasi Fingerprint 15 Register Kanonikal
        print("\n[1/8] Memverifikasi Fingerprint SHA256 15 Register Kanonikal CSV...")
        fingerprints = verify_register_fingerprints()
        report["fingerprints"] = fingerprints
        print(f" -> Seluruh {len(fingerprints)} berkas register kanonikal valid dan cocok 100% (LF normalized).")

        # 2. Introspeksi Modul & Schema Odoo 19
        print("\n[2/8] Menginspeksi Modul & Schema Odoo 19 Aktual...")
        IrModule = env["ir.module.module"]

        # Pastikan product_expiry aktif
        mod_expiry = IrModule.sudo().search([("name", "=", "product_expiry")], limit=1)
        if mod_expiry and mod_expiry.state != "installed":
            print(" -> Memasang modul 'product_expiry'...")
            mod_expiry.button_immediate_install()
            env.cr.commit()

        # Pastikan stock_account aktif
        mod_sa = IrModule.sudo().search([("name", "=", "stock_account")], limit=1)
        if mod_sa and mod_sa.state != "installed":
            print(" -> Memasang modul 'stock_account'...")
            mod_sa.button_immediate_install()
            env.cr.commit()

        if "expiration_date" not in env["stock.lot"]._fields:
            raise RuntimeError("Field 'expiration_date' wajib tersedia di stock.lot!")

        has_svl = "stock.valuation.layer" in env
        has_aml = "account.move.line" in env

        ProductCategory = env["product.category"].sudo()
        cat_fields = ProductCategory._fields
        has_cost_method = "property_cost_method" in cat_fields
        has_valuation = "property_valuation" in cat_fields
        cost_method_sel = [s[0] if isinstance(s, (list, tuple)) else s for s in getattr(cat_fields.get("property_cost_method"), "selection", [])] if has_cost_method else []
        valuation_sel = [s[0] if isinstance(s, (list, tuple)) else s for s in getattr(cat_fields.get("property_valuation"), "selection", [])] if has_valuation else []

        # Audit schema runtime Odoo 19 komprehensif
        sm_fields = env["stock.move"]._fields if "stock.move" in env else {}
        sml_fields = env["stock.move.line"]._fields if "stock.move.line" in env else {}
        sl_fields = env["stock.location"]._fields if "stock.location" in env else {}
        am_fields = env["account.move"]._fields if "account.move" in env else {}

        print(f" -> Keberadaan 'stock.valuation.layer': {'ADA' if has_svl else 'TIDAK ADA'}")
        print(f" -> Field 'property_cost_method' pada product.category: {has_cost_method} (options: {cost_method_sel})")
        print(f" -> Field 'property_valuation' pada product.category: {has_valuation} (options: {valuation_sel})")
        print(f" -> Audit stock.move fields: name={'name' in sm_fields}, desc={'description_picking' in sm_fields}, picked={'picked' in sm_fields}, price_unit={'price_unit' in sm_fields}, uom={'product_uom' in sm_fields}, uom_id={'product_uom_id' in sm_fields}, ref={'reference' in sm_fields}, pick={'picking_id' in sm_fields}, acc_move={'account_move_id' in sm_fields}, acc_moves={'account_move_ids' in sm_fields}")
        print(f" -> Audit stock.move.line fields: quantity={'quantity' in sml_fields}, qty_done={'qty_done' in sml_fields}, lot_id={'lot_id' in sml_fields}")
        print(f" -> Audit stock.location fields: val_acc={'valuation_account_id' in sl_fields}, val_in={'valuation_in_account_id' in sl_fields}, val_out={'valuation_out_account_id' in sl_fields}")
        print(f" -> Audit account.move fields: stock_move_id={'stock_move_id' in am_fields}")

        cat_acc_fields = [f for f in cat_fields if any(w in f for w in ["stock", "valuation", "account", "journal"])]
        print(f" -> Field Akun/Jurnal pada product.category: {cat_acc_fields}")

        # Introspeksi mendalam method ORM stock_account Odoo 19
        print("\n" + "=" * 60)
        print("[INTROSPEKSI SOURCE CODE ORM ODOO 19]")
        try:
            import inspect
            print("--- [A] stock.move._action_done source snippet ---")
            lines_ad = inspect.getsourcelines(env["stock.move"]._action_done)[0][:35]
            print("".join(lines_ad))
        except Exception as e_ad:
            print(f"Gagal inspect _action_done: {e_ad}")

        try:
            import inspect
            print("--- [B] stock.quant.action_apply_inventory source snippet ---")
            lines_ai = inspect.getsourcelines(env["stock.quant"].action_apply_inventory)[0][:30]
            print("".join(lines_ai))
        except Exception as e_ai:
            print(f"Gagal inspect action_apply_inventory: {e_ai}")

        if hasattr(env["stock.move"], "_create_account_move"):
            try:
                import inspect
                print("--- [C] stock.move._create_account_move source snippet ---")
                lines_cam = inspect.getsourcelines(env["stock.move"]._create_account_move)[0][:45]
                print("".join(lines_cam))
            except Exception as e_cam:
                print(f"Gagal inspect _create_account_move: {e_cam}")

        sm_val_methods = [m for m in dir(env["stock.move"]) if any(k in m.lower() for k in ["valuation", "account_move", "create_account", "account_entry"])]
        print(f"--- [D] Method akuntansi di stock.move: {sm_val_methods} ---")
        for vm in sm_val_methods[:5]:
            try:
                import inspect
                src_vm = inspect.getsourcelines(getattr(env["stock.move"], vm))[0][:20]
                print(f"  * {vm}:\n{''.join(src_vm)}")
            except Exception:
                pass
        print("=" * 60 + "\n")

        report["build_info"] = {
            "odoo_version": getattr(getattr(sys.modules.get("odoo"), "release", None), "version", "19.0"),
            "company": company.name,
            "currency": company.currency_id.name,
            "timezone": env.user.tz or "Asia/Makassar",
            "has_lot_expiry": True,
            "has_svl": has_svl,
            "has_aml": has_aml,
            "has_property_valuation": has_valuation,
            "property_valuation_selection": valuation_sel,
            "has_property_cost_method": has_cost_method,
            "property_cost_method_selection": cost_method_sel,
            "installed_modules_count": IrModule.search_count([("state", "=", "installed")]),
            "stock_move_has_name": "name" in sm_fields,
            "stock_move_has_desc": "description_picking" in sm_fields,
            "stock_move_has_acc_move": "account_move_id" in sm_fields,
            "stock_move_has_acc_moves": "account_move_ids" in sm_fields,
            "location_has_val_acc": "valuation_account_id" in sl_fields,
        }

        # 3. Bangun Oracle dari Register Kanonikal CSV
        print("\n[3/8] Membangun Source-Driven Oracle dari Register Kanonikal CSV Beku...")
        oracle = build_source_oracle()
        report["oracle_source"] = oracle
        print(f" -> Target SKU: {oracle['sku']} ({oracle['product_name']})")
        print(f" -> Cartons: Opening={oracle['details']['opening']['cartons']}, DO={oracle['details']['delivery']['cartons']}, PO={oracle['details']['receipt']['cartons']}")

        # 4. Resolusi Model & Master Data
        ProductProduct = env["product.product"].sudo()
        StockLocation = env["stock.location"].sudo()
        StockLot = env["stock.lot"].sudo()
        StockQuant = env["stock.quant"].sudo()
        StockMove = env["stock.move"].sudo()
        StockMoveLine = env["stock.move.line"].sudo()
        ResPartner = env["res.partner"].sudo()

        # Akun & Jurnal untuk Real-Time Automated Valuation
        AccountAccount = env["account.account"].sudo() if "account.account" in env else None
        AccountJournal = env["account.journal"].sudo() if "account.journal" in env else None

        stock_valuation_acc = None
        stock_input_acc = None
        stock_output_acc = None
        cogs_acc = None
        stock_journal = None

        if AccountAccount is not None:
            # Bangun domain company tangguh Odoo 19 (company_ids Many2many) vs versi lama (company_id Many2one)
            acc_fields = AccountAccount._fields
            comp_domain = []
            comp_vals = {}
            if "company_ids" in acc_fields:
                comp_domain = [("company_ids", "in", [company.id])]
                comp_vals = {"company_ids": [(4, company.id)]}
            elif "company_id" in acc_fields:
                comp_domain = [("company_id", "in", [False, company.id])]
                comp_vals = {"company_id": company.id}

            # 1. Stock Valuation Account (Persediaan 113000 / 113100)
            stock_valuation_acc = AccountAccount.search(comp_domain + [
                ("code", "in", ["113000", "113100"]),
            ], limit=1)
            if not stock_valuation_acc:
                stock_valuation_acc = AccountAccount.search(comp_domain + [
                    ("account_type", "=", "asset_current"),
                    ("name", "ilike", "Persediaan"),
                ], limit=1)
            if not stock_valuation_acc:
                vals = {
                    "code": "113000",
                    "name": "Persediaan Barang Dagang FMCG",
                    "account_type": "asset_current",
                }
                vals.update(comp_vals)
                stock_valuation_acc = AccountAccount.create(vals)

            # 2. Stock Interim Input Account (113900 / 211000)
            stock_input_acc = AccountAccount.search(comp_domain + [
                ("code", "in", ["113900", "211000"]),
            ], limit=1)
            if not stock_input_acc:
                vals = {
                    "code": "113900",
                    "name": "Penerimaan Barang Sementara (Interim)",
                    "account_type": "asset_current",
                }
                vals.update(comp_vals)
                stock_input_acc = AccountAccount.create(vals)

            # 3. Stock Interim Output Account (113910)
            stock_output_acc = AccountAccount.search(comp_domain + [
                ("code", "=", "113910"),
            ], limit=1)
            if not stock_output_acc:
                vals = {
                    "code": "113910",
                    "name": "Pengiriman Barang Sementara (Interim)",
                    "account_type": "asset_current",
                }
                vals.update(comp_vals)
                stock_output_acc = AccountAccount.create(vals)

            # 4. COGS / Expense Account (510000)
            cogs_acc = AccountAccount.search(comp_domain + [
                ("code", "=", "510000"),
            ], limit=1)
            if not cogs_acc:
                vals = {
                    "code": "510000",
                    "name": "Harga Pokok Penjualan (HPP) FMCG",
                    "account_type": "expense_direct_cost",
                }
                vals.update(comp_vals)
                cogs_acc = AccountAccount.create(vals)

        if AccountJournal is not None:
            j_fields = AccountJournal._fields
            j_domain = [("company_id", "in", [False, company.id])] if "company_id" in j_fields else []
            stock_journal = AccountJournal.search(j_domain + [
                ("code", "in", ["STJ", "MISC", "VAL"]),
            ], limit=1)
            if not stock_journal:
                stock_journal = AccountJournal.search(j_domain + [
                    ("type", "=", "general"),
                ], limit=1)
            if not stock_journal:
                vals = {
                    "name": "Penilaian Persediaan",
                    "type": "general",
                    "code": "STJ",
                }
                if "company_id" in j_fields:
                    vals["company_id"] = company.id
                if "auto_post" in j_fields:
                    vals["auto_post"] = True
                stock_journal = AccountJournal.create(vals)

        # Pastikan anglo_saxon_accounting aktif jika field tersedia pada res.company
        if "anglo_saxon_accounting" in company._fields and not company.anglo_saxon_accounting:
            company.sudo().write({"anglo_saxon_accounting": True})

        # Konfigurasi Kategori Produk dengan Automated Real-Time Valuation secara tangguh
        categ = ProductCategory.search([("name", "=", "FMCG Perpetual Experiment")], limit=1)
        categ_vals = {}
        if has_cost_method and "fifo" in cost_method_sel:
            categ_vals["property_cost_method"] = "fifo"
        if has_valuation and "real_time" in valuation_sel:
            categ_vals["property_valuation"] = "real_time"

        # Pemetaan alias akun persediaan pada kategori produk
        for fname in ["property_stock_valuation_account_id", "stock_valuation_account_id", "account_stock_valuation_id"]:
            if fname in cat_fields and stock_valuation_acc:
                categ_vals[fname] = stock_valuation_acc.id
        for fname in ["property_stock_journal", "stock_journal_id", "stock_journal"]:
            if fname in cat_fields and stock_journal:
                categ_vals[fname] = stock_journal.id
        for fname in ["property_stock_account_input_categ_id", "property_stock_account_input_id", "account_stock_in_id", "stock_input_account_id"]:
            if fname in cat_fields and stock_input_acc:
                categ_vals[fname] = stock_input_acc.id
        for fname in ["property_stock_account_output_categ_id", "property_stock_account_output_id", "account_stock_out_id", "stock_output_account_id"]:
            if fname in cat_fields and (cogs_acc or stock_output_acc):
                categ_vals[fname] = (cogs_acc or stock_output_acc).id
        for fname in ["property_account_expense_categ_id", "property_account_expense_id", "account_expense_id"]:
            if fname in cat_fields and cogs_acc:
                categ_vals[fname] = cogs_acc.id

        if not categ:
            categ_vals["name"] = "FMCG Perpetual Experiment"
            categ = ProductCategory.with_company(company).create(categ_vals)
        else:
            categ.with_company(company).write(categ_vals)

        print(f" -> Kategori '{categ.name}' dikonfigurasi: valuation={getattr(categ, 'property_valuation', 'N/A')}, cost_method={getattr(categ, 'property_cost_method', 'N/A')}")
        if stock_valuation_acc:
            print(f" -> Akun Valuasi Persediaan: {stock_valuation_acc.code} - {stock_valuation_acc.name}")

        # Konfigurasi Akun di Tingkat Lokasi (Non-Internal: Inventory, Supplier, Customer, Production)
        # Catatan Kritis Arsitektur Odoo 19:
        # Lokasi INTERNAL (WH/Stock, Karantina) WAJIB bernilai False pada valuation_account_id,
        # agar Odoo mengambil akun persediaan murni dari product.category (113000).
        # Jika lokasi internal diberi valuation_account_id, delivery akan menghasilkan debit-kredit
        # persediaan ke akun yang sama alih-alih mendebit HPP (510000).
        if "valuation_account_id" in sl_fields:
            # 1. Bersihkan seluruh lokasi internal agar valuation_account_id = False
            for inloc in StockLocation.search([("usage", "=", "internal")]):
                if inloc.valuation_account_id:
                    inloc.write({"valuation_account_id": False})

            # 2. Lokasi Inventory Adjustment: counterpart = stock_input_acc (113900)
            if stock_input_acc:
                for iloc in StockLocation.search([("usage", "=", "inventory")]):
                    iloc.write({"valuation_account_id": stock_input_acc.id})

            # 3. Lokasi Supplier: counterpart = stock_input_acc (113900)
            if stock_input_acc:
                for sloc in StockLocation.search([("usage", "=", "supplier")]):
                    sloc.write({"valuation_account_id": stock_input_acc.id})

            # 4. Lokasi Customer: counterpart = cogs_acc (510000)
            cust_acc = cogs_acc or stock_output_acc
            if cust_acc:
                for cloc in StockLocation.search([("usage", "=", "customer")]):
                    cloc.write({"valuation_account_id": cust_acc.id})

            # 5. Lokasi Production (jika ada): counterpart = stock_input_acc (113900)
            if stock_input_acc:
                for ploc in StockLocation.search([("usage", "=", "production")]):
                    ploc.write({"valuation_account_id": stock_input_acc.id})

        # Kompatibilitas field legacy jika ada
        if "valuation_out_account_id" in sl_fields and stock_input_acc:
            for loc in StockLocation.search([("usage", "in", ["inventory", "supplier"])]):
                loc.write({"valuation_out_account_id": stock_input_acc.id})
        if "valuation_in_account_id" in sl_fields and (cogs_acc or stock_output_acc):
            for loc in StockLocation.search([("usage", "in", ["inventory", "customer"])]):
                loc.write({"valuation_in_account_id": (cogs_acc or stock_output_acc).id})

        # Produk
        product = ProductProduct.search([("default_code", "=", oracle["sku"]), ("company_id", "in", [False, company.id])], limit=1)
        if not product:
            ProductTemplate = env["product.template"].sudo()
            tmpl = ProductTemplate.search([("default_code", "=", oracle["sku"])], limit=1)
            if not tmpl:
                tmpl_vals = {
                    "name": oracle["product_name"],
                    "default_code": oracle["sku"],
                    "tracking": "lot",
                    "standard_price": oracle["unit_cost"],
                    "list_price": 21000.0,
                    "categ_id": categ.id,
                    "company_id": False,
                }
                if "is_storable" in ProductTemplate._fields:
                    tmpl_vals["is_storable"] = True
                elif "type" in ProductTemplate._fields:
                    tmpl_vals["type"] = "consu"
                tmpl = ProductTemplate.create(tmpl_vals)
            product = tmpl.product_variant_id
        else:
            product.with_company(company).write({"categ_id": categ.id, "standard_price": oracle["unit_cost"]})

        # Pastikan standard_price terekam pada tingkat company
        product.with_company(company).write({"standard_price": oracle["unit_cost"]})

        # Lokasi
        wh_stock_loc = StockLocation.search([("complete_name", "ilike", "%WH/Stock%"), ("company_id", "in", [False, company.id])], limit=1)
        if not wh_stock_loc:
            wh_stock_loc = StockLocation.search([("usage", "=", "internal"), ("company_id", "in", [False, company.id])], limit=1)

        supplier_loc = StockLocation.search([("usage", "=", "supplier")], limit=1)
        customer_loc = StockLocation.search([("usage", "=", "customer")], limit=1)

        quarantine_loc = StockLocation.search([("name", "ilike", "%Karantina%"), ("company_id", "in", [False, company.id])], limit=1)
        if not quarantine_loc:
            quarantine_loc = StockLocation.create({
                "name": "Karantina FMCG Maumbi",
                "usage": "internal",
                "location_id": wh_stock_loc.location_id.id if wh_stock_loc.location_id else False,
                "company_id": company.id,
            })
        if "valuation_account_id" in sl_fields:
            if wh_stock_loc.valuation_account_id:
                wh_stock_loc.write({"valuation_account_id": False})
            if quarantine_loc.valuation_account_id:
                quarantine_loc.write({"valuation_account_id": False})

        # Partners
        details = oracle["details"]
        vendor = ResPartner.search([("name", "ilike", "%Unilever%")], limit=1)
        if not vendor:
            vendor = ResPartner.create({"name": "PT Unilever Indonesia Tbk", "supplier_rank": 1})

        customer = ResPartner.search([("ref", "=", "CUST-GT-16")], limit=1)
        if not customer:
            customer = ResPartner.create({"name": "Toko Pelita Jaya Wanea", "ref": "CUST-GT-16", "customer_rank": 1})

        # Lots
        lot_opening = StockLot.search([("name", "=", details["opening"]["lot"]), ("product_id", "=", product.id), ("company_id", "=", company.id)], limit=1)
        if not lot_opening:
            lot_opening = StockLot.create({
                "name": details["opening"]["lot"],
                "product_id": product.id,
                "company_id": company.id,
                "expiration_date": details["opening"]["expiry"],
            })

        lot_po = StockLot.search([("name", "=", details["receipt"]["lot"]), ("product_id", "=", product.id), ("company_id", "=", company.id)], limit=1)
        if not lot_po:
            lot_po = StockLot.create({
                "name": details["receipt"]["lot"],
                "product_id": product.id,
                "company_id": company.id,
                "expiration_date": details["receipt"]["expiry"],
            })

        experiment_account_move_ids = set()
        experiment_account_move_event_dates = {}

        # Helper: Pencari dan Pengelola Entri Akuntansi Odoo Native
        def find_and_backdate_native_account_moves(stock_move, origin_ref, target_date_str):
            """Mencari entri jurnal native Odoo yang terbentuk dari stock.move dan menyelaraskan tanggalnya."""
            found_moves = env["account.move"].sudo()

            # 1. Melalui field relasi account_move_id (Many2one tunggal Odoo 19) atau account_move_ids
            if getattr(stock_move, "account_move_id", None):
                found_moves = found_moves | stock_move.account_move_id
            elif getattr(stock_move, "account_move_ids", None):
                found_moves = found_moves | stock_move.account_move_ids

            # 2. Melalui field stock_move_id pada account.move jika tersedia
            if "stock_move_id" in env["account.move"]._fields:
                found_moves = found_moves | env["account.move"].sudo().search([("stock_move_id", "=", stock_move.id)])

            # 3. Melalui ref jika belum ditemukan
            if not found_moves and origin_ref:
                found_moves = found_moves | env["account.move"].sudo().search([
                    ("company_id", "=", company.id),
                    ("ref", "ilike", origin_ref),
                ])

            # Verifikasi entri jurnal native Odoo tanpa modifikasi ilegal pada entri posted
            for am in found_moves:
                target_date = target_date_str[:10]
                if am.state == "draft":
                    # Jika masih draft, selaraskan tanggal sebelum posting
                    am.write({"date": target_date})
                    if hasattr(am, "line_ids") and am.line_ids:
                        am.line_ids.write({"date": target_date})
                    # Fail-Fast: Posting jurnal native tanpa menelan kegagalan
                    am.action_post()

                # Fail-Fast: Pastikan entri jurnal telah berhasil diposting
                if am.state != "posted":
                    raise ValueError(
                        f"[FAIL-FAST] Entri jurnal native {am.id} ({am.ref or am.name}) gagal diposting! "
                        f"State aktual: {am.state}"
                    )

                # Verifikasi FAIL-FAST: tanggal native jurnal wajib cocok 100% dengan target cut-off
                if str(am.date) != target_date:
                    raise ValueError(
                        f"[FAIL-FAST] Tanggal entri jurnal native {am.id} ({am.date}) "
                        f"tidak cocok dengan target cut-off ({target_date})!"
                    )

                # Verifikasi Khusus Delivery: Wajib mendebit akun HPP 510000
                if origin_ref == "DO-202607-0063":
                    debit_accs = [line.account_id.code for line in am.line_ids if line.debit > 0]
                    if "510000" not in debit_accs:
                        raise ValueError(
                            f"[FAIL-FAST] Jurnal delivery {am.id} mendebit akun {debit_accs}, "
                            f"bukan akun HPP 510000!"
                        )

                experiment_account_move_ids.add(am.id)
                experiment_account_move_event_dates[am.id] = target_date_str
                print(f" -> [Native Account Move] ID={am.id}, Ref={am.ref}, Date={am.date}, State={am.state}, Lines={len(am.line_ids)}")
                for line in am.line_ids:
                    print(f"     * Account: {line.account_id.code} ({line.account_id.name}) | Debit: {line.debit} | Credit: {line.credit}")

            return found_moves

        # Helper: Audit Pasangan Akun Debit-Kredit Jurnal Native Odoo secara Formal
        def audit_event_account_pair(event_name, stock_move, expected_debit_code, expected_credit_code, expected_amount):
            """Memverifikasi bahwa jurnal native mendebit dan mengkredit akun yang sesuai serta berimbang tanpa substitusi/split fraud."""
            found_ams = env["account.move"].sudo()
            # 1. Relasi langsung account_move_id (Many2one Odoo 19)
            if getattr(stock_move, "account_move_id", None):
                found_ams = found_ams | stock_move.account_move_id
            # 2. Relasi account_move_ids
            if getattr(stock_move, "account_move_ids", None):
                found_ams = found_ams | stock_move.account_move_ids
            # 3. Field stock_move_id pada account.move jika tersedia
            if "stock_move_id" in env["account.move"]._fields:
                found_ams = found_ams | env["account.move"].sudo().search([("stock_move_id", "=", stock_move.id)])
            # 4. Pencarian referensi eksak (tanpa substring/ilike) pada origin atau picking name
            if not found_ams and stock_move.origin:
                exact_refs = [stock_move.origin]
                if getattr(stock_move, "picking_id", None) and stock_move.picking_id.name:
                    exact_refs.append(stock_move.picking_id.name)
                found_ams = env["account.move"].sudo().search([
                    ("ref", "in", exact_refs),
                    ("company_id", "in", [False, company.id]),
                ])

            # Wajibkan relasi dokumen unik dan pasti (fail-fast jika 0 atau > 1)
            if len(found_ams) == 0:
                raise ValueError(f"[FAIL-FAST] Event '{event_name}' ({stock_move.origin}) tidak memiliki entri account.move native Odoo yang valid!")
            if len(found_ams) > 1:
                raise ValueError(
                    f"[FAIL-FAST] Event '{event_name}' ({stock_move.origin}) memiliki lebih dari 1 entri account.move ({len(found_ams)} entri: {found_ams.ids})! "
                    f"Wajib relasi dokumen unik dan pasti tanpa ambiguitas."
                )

            am = found_ams[0]

            if am.state != "posted":
                raise ValueError(f"[FAIL-FAST] Jurnal {am.id} untuk event '{event_name}' belum posted (state: {am.state})!")

            fin_lines = [line for line in am.line_ids if round(line.debit, 2) > 0 or round(line.credit, 2) > 0]
            if not fin_lines:
                raise ValueError(f"[FAIL-FAST] Jurnal {am.id} ({event_name}) tidak memiliki baris finansial (debit/kredit > 0)!")

            debit_map = {}
            credit_map = {}
            for line in fin_lines:
                code = str(line.account_id.code).strip()
                d = round(line.debit, 2)
                c = round(line.credit, 2)
                if d > 0:
                    debit_map[code] = round(debit_map.get(code, 0.0) + d, 2)
                if c > 0:
                    credit_map[code] = round(credit_map.get(code, 0.0) + c, 2)

            tot_debit = round(sum(debit_map.values()), 2)
            tot_credit = round(sum(credit_map.values()), 2)

            # 1. Keseimbangan Jurnal
            if abs(tot_debit - tot_credit) > 0.01:
                raise ValueError(f"[FAIL-FAST] Jurnal {am.id} ({event_name}) tidak berimbang! Debit={tot_debit}, Credit={tot_credit}")

            # 2. Akurasi Total Nominal Jurnal terhadap Ekspektasi
            if abs(tot_debit - expected_amount) > 0.01:
                raise ValueError(f"[FAIL-FAST] Nominal jurnal {am.id} ({event_name}) sebesar Rp{tot_debit:,.2f} tidak cocok dengan expected Rp{expected_amount:,.2f}!")

            # 3. Verifikasi Eksak Akun Debit (Menolak Keras Split Fraud Rp1 HPP + Rp99 Akun Asing)
            if expected_debit_code not in debit_map:
                raise ValueError(f"[FAIL-FAST] Jurnal {am.id} ({event_name}) tidak mendebit akun yang diharapkan ({expected_debit_code})! Terdeteksi: {list(debit_map.keys())}")

            actual_expected_debit = debit_map[expected_debit_code]
            if abs(actual_expected_debit - expected_amount) > 0.01:
                raise ValueError(
                    f"[FAIL-FAST] Nominal debit pada akun {expected_debit_code} untuk jurnal {am.id} ({event_name}) "
                    f"adalah Rp{actual_expected_debit:,.2f}, tidak cocok dengan expected Rp{expected_amount:,.2f}!"
                )

            unexpected_debits = {k: v for k, v in debit_map.items() if k != expected_debit_code}
            if unexpected_debits:
                raise ValueError(
                    f"[FAIL-FAST] Jurnal {am.id} ({event_name}) memiliki baris debit tidak sah/ekstra: {unexpected_debits}! "
                    f"Seluruh debit wajib tunggal pada akun {expected_debit_code}."
                )

            # 4. Verifikasi Eksak Akun Kredit (Menolak Substitusi Akun atau Kredit Ekstra)
            if expected_credit_code not in credit_map:
                raise ValueError(f"[FAIL-FAST] Jurnal {am.id} ({event_name}) tidak mengkredit akun yang diharapkan ({expected_credit_code})! Terdeteksi: {list(credit_map.keys())}")

            actual_expected_credit = credit_map[expected_credit_code]
            if abs(actual_expected_credit - expected_amount) > 0.01:
                raise ValueError(
                    f"[FAIL-FAST] Nominal kredit pada akun {expected_credit_code} untuk jurnal {am.id} ({event_name}) "
                    f"adalah Rp{actual_expected_credit:,.2f}, tidak cocok dengan expected Rp{expected_amount:,.2f}!"
                )

            unexpected_credits = {k: v for k, v in credit_map.items() if k != expected_credit_code}
            if unexpected_credits:
                raise ValueError(
                    f"[FAIL-FAST] Jurnal {am.id} ({event_name}) memiliki baris kredit tidak sah/ekstra: {unexpected_credits}! "
                    f"Seluruh kredit wajib tunggal pada akun {expected_credit_code}."
                )

            print(f" -> [Audit Pasangan Akun OK] Event '{event_name}' | Jurnal {am.id} ({am.ref or am.name}) | Debit: {expected_debit_code} (Rp{tot_debit:,.2f}) | Kredit: {expected_credit_code} (Rp{tot_credit:,.2f})")
            return {
                "account_move_id": am.id,
                "ref": am.ref,
                "debit_account": expected_debit_code,
                "credit_account": expected_credit_code,
                "amount": tot_debit,
                "balanced": True,
                "debit_map": debit_map,
                "credit_map": credit_map,
            }

        # Helper 1: Eksekusi Opening Stock via Mekanisme Quant Adjustment Asli Odoo 19
        # (Loader murni: tidak merekayasa/mensintesis nilai atau jurnal buatan)
        def execute_opening_quant_adjustment(origin, loc_dest, qty, lot, move_date):
            existing_mv = StockMove.search([
                ("origin", "=", origin),
                ("product_id", "=", product.id),
                ("location_dest_id", "=", loc_dest.id),
                ("state", "=", "done"),
                ("company_id", "=", company.id),
            ], limit=1)
            if existing_mv:
                return existing_mv, False

            quant_vals = {
                "product_id": product.id,
                "location_id": loc_dest.id,
                "lot_id": lot.id,
                "inventory_quantity": qty,
            }
            if "inventory_date" in StockQuant._fields:
                quant_vals["inventory_date"] = move_date

            quant = StockQuant.with_context(inventory_mode=True, force_period_date=move_date[:10]).create(quant_vals)
            quant.with_context(force_period_date=move_date[:10]).action_apply_inventory()

            # Cari move hasil inventory adjustment Odoo
            adj_moves = StockMove.search([
                ("product_id", "=", product.id),
                ("location_dest_id", "=", loc_dest.id),
                ("is_inventory", "=", True),
                ("state", "=", "done"),
                ("company_id", "=", company.id),
            ], order="id desc", limit=1)
            if not adj_moves:
                raise ValueError(f"action_apply_inventory() gagal menghasilkan stock.move done untuk {product.name}!")

            adj_moves.write({"date": move_date, "origin": origin})
            if hasattr(adj_moves, "move_line_ids") and adj_moves.move_line_ids:
                adj_moves.move_line_ids.write({"date": move_date})

            # Selaraskan tanggal jurnal native Odoo
            native_ams = find_and_backdate_native_account_moves(adj_moves, origin, move_date)
            if not native_ams or len(native_ams) == 0:
                raise ValueError(f"[FAIL-FAST] Opening adjustment {origin} wajib menghasilkan entri jurnal native Odoo!")
            print(f" -> Opening adjustment move ID {adj_moves.id} (native Odoo account_moves: {len(native_ams)})")
            return adj_moves, True

        # Helper 2: Eksekusi Pergerakan Operasional Native Odoo 19 (Delivery, Retur, PO Receipt)
        # Dilengkapi dokumen/picking native Odoo 19 agar move.reference valid (string) dan lifecycle akuntansi lengkap
        def execute_operational_movement(origin, loc_src, loc_dest, qty, lot, move_date, partner=None):
            existing_mv = StockMove.search([
                ("origin", "=", origin),
                ("product_id", "=", product.id),
                ("location_id", "=", loc_src.id),
                ("location_dest_id", "=", loc_dest.id),
                ("state", "=", "done"),
                ("company_id", "=", company.id),
            ], limit=1)
            if existing_mv:
                return existing_mv, False

            # Dapatkan partner jika belum ditentukan
            if not partner:
                if loc_dest.usage == "customer" or loc_src.usage == "customer":
                    partner = customer
                elif loc_src.usage == "supplier":
                    partner = vendor

            # Dapatkan tipe operasi stock.picking.type native
            StockPickingType = env["stock.picking.type"].sudo()
            ptype = False
            if loc_dest.usage == "customer":
                ptype = StockPickingType.search([("code", "=", "outgoing"), ("company_id", "in", [False, company.id])], limit=1)
            elif loc_src.usage == "supplier":
                ptype = StockPickingType.search([("code", "=", "incoming"), ("company_id", "in", [False, company.id])], limit=1)
            elif loc_src.usage == "customer":
                ptype = StockPickingType.search([("code", "=", "incoming"), ("company_id", "in", [False, company.id])], limit=1)
                if not ptype:
                    ptype = StockPickingType.search([("code", "=", "internal"), ("company_id", "in", [False, company.id])], limit=1)
            if not ptype:
                ptype = StockPickingType.search([("company_id", "in", [False, company.id])], limit=1)

            # Buat atau temukan stock.picking native
            StockPicking = env["stock.picking"].sudo()
            picking = StockPicking.search([("origin", "=", origin), ("company_id", "=", company.id)], limit=1)
            if not picking:
                candidate_pick = {
                    "name": origin,
                    "origin": origin,
                    "partner_id": partner.id if partner else False,
                    "picking_type_id": ptype.id if ptype else False,
                    "location_id": loc_src.id,
                    "location_dest_id": loc_dest.id,
                    "company_id": company.id,
                    "scheduled_date": move_date,
                    "date": move_date,
                }
                pick_vals = {k: v for k, v in candidate_pick.items() if k in StockPicking._fields}
                picking = StockPicking.with_context(force_period_date=move_date[:10]).create(pick_vals)

            # Payload stock.move diaudit terhadap schema runtime Odoo 19
            candidate_mv = {
                "origin": origin,
                "picking_id": picking.id,
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_id": product.uom_id.id,
                "product_uom_qty": qty,
                "quantity": qty,
                "location_id": loc_src.id,
                "location_dest_id": loc_dest.id,
                "company_id": company.id,
                "is_inventory": False,
                "date": move_date,
                "name": f"{origin} - {product.name}",
                "description_picking": f"{origin} - {product.name}",
                "price_unit": oracle["unit_cost"],
            }
            if "reference" in StockMove._fields:
                candidate_mv["reference"] = origin
            if "partner_id" in StockMove._fields and partner:
                candidate_mv["partner_id"] = partner.id

            mv_vals = {k: v for k, v in candidate_mv.items() if k in StockMove._fields}

            mv = StockMove.with_context(force_period_date=move_date[:10]).create(mv_vals)
            mv.with_context(force_period_date=move_date[:10])._action_confirm()
            mv.with_context(force_period_date=move_date[:10])._action_assign()

            # Delegasikan alokasi move lines ke helper modular dengan guard reservasi kosong, fidelitas lot, dan sinkronisasi picked
            allocate_and_sync_move_lines(env, mv, picking, qty, target_lot=lot, move_date=move_date)

            # Jika tersedia pada stock.picking (Odoo 17/18/19), set quantities sesuai reservasi
            if hasattr(picking, "action_set_quantities_to_reservation"):
                picking.action_set_quantities_to_reservation()

            if "picked" in StockPicking._fields:
                picking.write({"picked": True})

            # Instrumentasi komprehensif pra-validasi native
            print(f" -> [PRE-VALIDATE] Picking {picking.name} ({origin}): state={picking.state}")
            for m in picking.move_ids:
                print(f"    * Move {m.id}: state={m.state}, picked={getattr(m, 'picked', 'N/A')}, demand={getattr(m, 'product_uom_qty', 'N/A')}, qty={getattr(m, 'quantity', 'N/A')}")
            for ml_rec in picking.move_line_ids:
                print(f"    * MoveLine {ml_rec.id}: state={getattr(ml_rec, 'state', 'N/A')}, picked={getattr(ml_rec, 'picked', 'N/A')}, qty={getattr(ml_rec, 'quantity', 'N/A')}, qty_done={getattr(ml_rec, 'qty_done', 'N/A')}, lot={ml_rec.lot_id.name if ml_rec.lot_id else 'None'}")

            # Validasi picking secara native melalui lifecycle Odoo (button_validate)
            # Tanpa fallback pemaksaan status atau _action_done manual
            val_ctx = {
                "force_period_date": move_date[:10],
                "skip_backorder": True,
                "skip_immediate": True,
                "skip_expired": True,
            }
            validate_res = picking.with_context(**val_ctx).button_validate()
            print(f" -> [VALIDATE RES] Picking {picking.name} ({origin}): {validate_res}")

            # Penanganan recursive/iterative wizard native Odoo 19
            wiz_iter = 0
            current_res = validate_res
            while isinstance(current_res, dict) and "res_model" in current_res and wiz_iter < 5:
                wiz_iter += 1
                wiz_model = current_res["res_model"]
                wiz_id = current_res.get("res_id")
                wiz_ctx = dict(val_ctx)
                if "context" in current_res and isinstance(current_res["context"], dict):
                    wiz_ctx.update(current_res["context"])
                print(f" -> [WIZARD RESOLVER {wiz_iter}] Resolving wizard {wiz_model} (id: {wiz_id}) with context: {list(wiz_ctx.keys())}")
                wizard = (
                    env[wiz_model].sudo().with_context(**wiz_ctx).browse(wiz_id)
                    if wiz_id
                    else env[wiz_model].sudo().with_context(**wiz_ctx).create({})
                )
                action_taken = False
                for act_name in ["process", "action_confirm", "process_cancel_backorder", "action_process", "apply"]:
                    if hasattr(wizard, act_name):
                        current_res = getattr(wizard.with_context(**wiz_ctx), act_name)()
                        action_taken = True
                        print(f" -> [WIZARD ACTION] Executed {act_name}() on {wiz_model} -> res: {current_res}")
                        break
                if not action_taken:
                    print(f" -> [WIZARD WARNING] Tidak ditemukan action umum pada {wiz_model} (dir: {[m for m in dir(wizard) if not m.startswith('_')]})")
                    break

            print(f" -> [POST-VALIDATE] Picking {picking.name} ({origin}): state={picking.state}")

            # Verifikasi FAIL-FAST: Dokumen picking dan move WAJIB berstatus 'done' secara native
            if picking.state != "done":
                raise ValueError(
                    f"[FAIL-FAST] Validasi native picking {picking.name} ({origin}) gagal mencapai state 'done'! "
                    f"State aktual: {picking.state}"
                )
            if mv.state != "done":
                raise ValueError(
                    f"[FAIL-FAST] Stock move {mv.id} ({origin}) belum berstatus 'done' pasca validasi native picking! "
                    f"State aktual: {mv.state}"
                )

            if "date_done" in StockPicking._fields:
                picking.write({"date_done": move_date})

            mv.write({"date": move_date})
            if hasattr(mv, "move_line_ids") and mv.move_line_ids:
                mv.move_line_ids.write({"date": move_date})

            # Selaraskan tanggal jurnal native Odoo
            native_ams = find_and_backdate_native_account_moves(mv, origin, move_date)
            if not native_ams or len(native_ams) == 0:
                raise ValueError(f"[FAIL-FAST] Move {origin} ({mv.id}) wajib menghasilkan entri jurnal native Odoo!")
            print(f" -> Move {origin} ID {mv.id} (native Odoo account_moves: {len(native_ams)})")
            return mv, True

        # Validator Read-Only: Evaluasi Posisi Fisik & Akuntansi Native Odoo 19
        def get_historical_position(as_of_dt_str):
            domain = [
                ("product_id", "=", product.id),
                ("state", "=", "done"),
                ("date", "<=", as_of_dt_str),
                ("company_id", "=", company.id),
            ]
            lines = StockMoveLine.search(domain)

            saleable_units = 0.0
            quarantine_units = 0.0

            for ml in lines:
                ml_qty = getattr(ml, "quantity", getattr(ml, "qty_done", 0.0))
                if ml.location_dest_id.id == wh_stock_loc.id:
                    saleable_units += ml_qty
                if ml.location_id.id == wh_stock_loc.id:
                    saleable_units -= ml_qty

                if ml.location_dest_id.id == quarantine_loc.id:
                    quarantine_units += ml_qty
                if ml.location_id.id == quarantine_loc.id:
                    quarantine_units -= ml_qty

            saleable_cartons = round(saleable_units / oracle["carton_qty"], 4)
            quarantine_cartons = round(quarantine_units / oracle["carton_qty"], 4)
            total_cartons = round(saleable_cartons + quarantine_cartons, 4)

            # Pembacaan Valuasi Aktual dari stock.valuation.layer Odoo (jika tersedia)
            svl_val = None
            if has_svl:
                svl_domain = [
                    ("product_id", "=", product.id),
                    ("company_id", "=", company.id),
                    ("stock_move_id.date", "<=", as_of_dt_str),
                ]
                svl_records = env["stock.valuation.layer"].sudo().search(svl_domain)
                svl_val = round(sum(svl_records.mapped("value")), 2)

            # Pembacaan GL Aktual Akun Persediaan (113000)
            gl_balance = None
            eod_gl_balance = None
            if has_aml and stock_valuation_acc:
                aml_domain = [
                    ("account_id", "=", stock_valuation_acc.id),
                    ("date", "<=", as_of_dt_str[:10]),
                ]
                if "company_id" in env["account.move.line"]._fields:
                    aml_domain.append(("company_id", "=", company.id))
                amls = env["account.move.line"].sudo().search(aml_domain)
                posted_amls = [a for a in amls if getattr(a.move_id, "state", "posted") == "posted"]
                matching_amls = [
                    a for a in posted_amls
                    if (getattr(a, "product_id", None) and a.product_id.id == product.id)
                    or (getattr(a, "stock_move_id", None) and getattr(a.stock_move_id, "product_id", None) and a.stock_move_id.product_id.id == product.id)
                    or (getattr(a.move_id, "stock_move_id", None) and getattr(a.move_id.stock_move_id, "product_id", None) and a.move_id.stock_move_id.product_id.id == product.id)
                    or any(ref in (a.move_id.ref or "") for ref in ["OPENING-20260701", "DO-202607-0063", "REJ-202607-001", "PO-2026-06-05"])
                ]
                # Saldo GL Harian Native Odoo (EOD GL Balance pada Akun Persediaan 113000)
                eod_gl_balance = round(sum(a.debit - a.credit for a in matching_amls), 2)

                # Evaluasi GL Pergerakan Historis Intrahari:
                # Membaca murni dari tabel stock.move Odoo via ORM (stock_move.date <= as_of_dt_str),
                # tanpa bergantung pada variabel memori loader.
                moves_before_cutoff = StockMove.search([
                    ("product_id", "=", product.id),
                    ("state", "=", "done"),
                    ("date", "<=", as_of_dt_str),
                    ("company_id", "in", [False, company.id]),
                ])
                cutoff_move_ids = set()
                for sm in moves_before_cutoff:
                    if getattr(sm, "account_move_id", None):
                        cutoff_move_ids.add(sm.account_move_id.id)
                    if "stock_move_id" in env["account.move"]._fields:
                        for am in env["account.move"].sudo().search([("stock_move_id", "=", sm.id)]):
                            cutoff_move_ids.add(am.id)
                    if sm.origin:
                        for am in env["account.move"].sudo().search([("ref", "ilike", sm.origin), ("company_id", "in", [False, company.id])]):
                            cutoff_move_ids.add(am.id)

                cutoff_amls = []
                for a in matching_amls:
                    if a.move_id.id in cutoff_move_ids:
                        cutoff_amls.append(a)
                    elif not any(ref in (a.move_id.ref or "") for ref in ["OPENING-20260701", "DO-202607-0063", "REJ-202607-001", "PO-2026-06-05"]):
                        # Jurnal manual/mutasi yang dibuat langsung pada tanggal cutoff
                        if str(a.date) <= as_of_dt_str[:10]:
                            cutoff_amls.append(a)

                gl_balance = round(sum(a.debit - a.credit for a in cutoff_amls), 2)

            return {
                "saleable_units": saleable_units,
                "quarantine_units": quarantine_units,
                "total_units": saleable_units + quarantine_units,
                "saleable_cartons": saleable_cartons,
                "quarantine_cartons": quarantine_cartons,
                "total_cartons": total_cartons,
                "odoo_svl_valuation": svl_val,
                "odoo_gl_balance": gl_balance,
                "odoo_eod_gl_balance": eod_gl_balance,
            }

        # 5. RUN 1: Eksekusi Alur Transaksi Lengkap
        print("\n[4/8] Menjalankan RUN 1: Eksekusi 4 Transaksi Kronologis Lengkap...")
        run1_events = {}

        # 1. Opening via quant adjustment mode
        mv_open, cr_open = execute_opening_quant_adjustment(
            origin="OPENING-20260701",
            loc_dest=wh_stock_loc,
            qty=details["opening"]["units"],
            lot=lot_opening,
            move_date=details["opening"]["date"],
        )
        run1_events["opening"] = {"move_id": mv_open.id, "created": cr_open}

        # 2. Delivery Outbound: 2026-07-03 14:00:00
        mv_do, cr_do = execute_operational_movement(
            origin="DO-202607-0063",
            loc_src=wh_stock_loc,
            loc_dest=customer_loc,
            qty=details["delivery"]["units"],
            lot=lot_opening,
            move_date=details["delivery"]["date"],
        )
        run1_events["delivery"] = {"move_id": mv_do.id, "created": cr_do}

        # 3. Retur Karantina: 2026-07-03 23:59:59
        mv_rej, cr_rej = execute_operational_movement(
            origin="REJ-202607-001",
            loc_src=customer_loc,
            loc_dest=quarantine_loc,
            qty=details["rejection"]["units"],
            lot=lot_opening,
            move_date=details["rejection"]["date"],
        )
        run1_events["rejection"] = {"move_id": mv_rej.id, "created": cr_rej}

        # 4. PO Inbound Receipt: 2026-07-04 23:59:59
        mv_po, cr_po = execute_operational_movement(
            origin="PO-2026-06-05",
            loc_src=supplier_loc,
            loc_dest=wh_stock_loc,
            qty=details["receipt"]["units"],
            lot=lot_po,
            move_date=details["receipt"]["date"],
        )
        run1_events["receipt"] = {"move_id": mv_po.id, "created": cr_po}

        env.cr.commit()
        report["run1_summary"] = run1_events

        # 5.1 Audit Formal Pasangan Akun Debit-Kredit Jurnal Native (Run 1)
        print("\n[Audit Pasangan Akun] Memvalidasi kelengkapan pasangan debit-kredit akuntansi native Odoo...")
        pair_audit_results = {}
        for ev_key, ev_data in run1_events.items():
            ev_spec = details[ev_key]
            sm_record = StockMove.browse(ev_data["move_id"])
            audit_res = audit_event_account_pair(
                event_name=ev_key,
                stock_move=sm_record,
                expected_debit_code=ev_spec["expected_debit_acc"],
                expected_credit_code=ev_spec["expected_credit_acc"],
                expected_amount=ev_spec["expected_amount"],
            )
            pair_audit_results[ev_key] = audit_res

        report["account_pair_audit"] = pair_audit_results

        # 6. Evaluasi 5 Cutoff Pasca-Injeksi Seluruh Data
        print("\n[5/8] Membaca Ulang Posisi Stok & Valuasi Historis Native (5 Cutoff)...")
        cutoff_results = {}
        all_cutoffs_match = True

        for c_key, c_exp in oracle["cutoffs"].items():
            pos = get_historical_position(c_exp["as_of"])

            # 1. Delta Fisik (Kartons)
            delta_saleable = round(pos["saleable_cartons"] - c_exp["expected_saleable_cartons"], 4)
            delta_quar = round(pos["quarantine_cartons"] - c_exp["expected_quarantine_cartons"], 4)
            stock_match = (delta_saleable == 0.0) and (delta_quar == 0.0)

            # 2. GL Balance Pergerakan hingga Cutoff
            if pos["odoo_gl_balance"] is not None:
                delta_gl = round(pos["odoo_gl_balance"] - c_exp["expected_total_val"], 2)
                gl_match = (abs(delta_gl) < 0.01)
                actual_gl_display = pos["odoo_gl_balance"]
            else:
                delta_gl = None
                gl_match = False
                actual_gl_display = "GL_NOT_FOUND"

            # 3. GL Harian Native Odoo (EOD GL Balance pada Akun 113000) - Menentukan Kelulusan Mutlak
            if pos["odoo_eod_gl_balance"] is not None and "expected_eod_gl" in c_exp:
                delta_eod_gl = round(pos["odoo_eod_gl_balance"] - c_exp["expected_eod_gl"], 2)
                eod_gl_match = (abs(delta_eod_gl) < 0.01)
                actual_eod_gl_display = pos["odoo_eod_gl_balance"]
            else:
                delta_eod_gl = None
                eod_gl_match = False
                actual_eod_gl_display = "EOD_GL_NOT_FOUND"

            # 4. SVL Valuation (jika model SVL terpasang di build)
            if has_svl:
                if pos["odoo_svl_valuation"] is not None:
                    delta_svl = round(pos["odoo_svl_valuation"] - c_exp["expected_total_val"], 2)
                    svl_match = (abs(delta_svl) < 0.01)
                    actual_svl_display = pos["odoo_svl_valuation"]
                else:
                    delta_svl = None
                    svl_match = False
                    actual_svl_display = "SVL_NOT_FOUND"
            else:
                delta_svl = 0.0
                svl_match = True
                actual_svl_display = "N/A (Odoo 19 removed SVL)"

            # Kelulusan mutlak ditentukan oleh Fisik + GL Intrahari/Cutoff + GL Harian Native EOD + SVL
            is_match = stock_match and gl_match and eod_gl_match and svl_match
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
                    "eod_gl": c_exp.get("expected_eod_gl"),
                },
                "actual": {
                    "saleable_cartons": pos["saleable_cartons"],
                    "quarantine_cartons": pos["quarantine_cartons"],
                    "total_cartons": pos["total_cartons"],
                    "odoo_svl_valuation": pos["odoo_svl_valuation"],
                    "odoo_gl_balance": pos["odoo_gl_balance"],
                    "odoo_eod_gl_balance": pos["odoo_eod_gl_balance"],
                },
                "delta": {
                    "saleable_cartons": delta_saleable,
                    "quarantine_cartons": delta_quar,
                    "total_gl": delta_gl,
                    "total_eod_gl": delta_eod_gl,
                    "total_svl": delta_svl,
                },
                "stock_match": stock_match,
                "gl_match": gl_match,
                "eod_gl_match": eod_gl_match,
                "svl_match": svl_match,
                "match": is_match,
            }

            status_str = "PASS" if is_match else "FAIL"
            print(f" -> [{status_str}] {c_exp['title']}: Expected {c_exp['expected_saleable_cartons']} s / {c_exp['expected_quarantine_cartons']} q ctn | Actual {pos['saleable_cartons']} s / {pos['quarantine_cartons']} q ctn | Cutoff GL: {actual_gl_display} | EOD GL: {actual_eod_gl_display} (SVL: {actual_svl_display})")

        report["cutoff_results"] = cutoff_results

        # 7. RUN 2: Replay Seluruh Alur & Audit Zero-Drift Penuh
        print("\n[6/8] Menjalankan RUN 2: Replay Seluruh Alur & Audit Zero Drift Penuh...")

        # Helper Snapshot Jurnal Akuntansi Native
        def take_accounting_snapshot():
            acc_moves = env["account.move"].sudo().search([("company_id", "in", [False, company.id])])
            acc_lines = env["account.move.line"].sudo().search([("company_id", "in", [False, company.id])])
            return {
                "moves": {
                    m.id: {"name": m.name, "ref": m.ref, "date": str(m.date), "state": m.state}
                    for m in acc_moves
                },
                "lines": {
                    line.id: {
                        "move_id": line.move_id.id,
                        "account_id": line.account_id.id,
                        "account_code": line.account_id.code,
                        "debit": line.debit,
                        "credit": line.credit,
                        "date": str(line.date),
                    }
                    for line in acc_lines
                },
                "total_persediaan_gl": sum(
                    line.debit - line.credit
                    for line in acc_lines
                    if line.account_id.id == stock_valuation_acc.id and line.move_id.state == "posted"
                ),
            }

        # Deep Snapshot Pre-Run 2
        moves_pre = StockMove.search([("product_id", "=", product.id), ("company_id", "=", company.id)])
        lines_pre = StockMoveLine.search([("product_id", "=", product.id), ("company_id", "=", company.id)])
        quants_pre = StockQuant.search([("product_id", "=", product.id), ("company_id", "=", company.id)])
        svl_pre = env["stock.valuation.layer"].sudo().search([("product_id", "=", product.id), ("company_id", "=", company.id)]) if has_svl else None

        snapshot_pre = {
            "moves": {m.id: {"origin": m.origin, "date": str(m.date), "state": m.state, "qty": m.product_uom_qty} for m in moves_pre},
            "lines": {ml.id: {"move_id": ml.move_id.id, "date": str(ml.date), "state": ml.state, "qty": ml.quantity, "lot_id": ml.lot_id.id} for ml in lines_pre},
            "quants": {q.id: {"location_id": q.location_id.id, "lot_id": q.lot_id.id, "qty": q.quantity, "reserved": getattr(q, "reserved_quantity", 0.0)} for q in quants_pre},
            "svls": {s.id: {"value": s.value, "qty": s.quantity, "cost": s.unit_cost} for s in svl_pre} if svl_pre else {},
            "accounting": take_accounting_snapshot(),
            "cutoffs": {k: get_historical_position(v["as_of"]) for k, v in oracle["cutoffs"].items()},
        }

        run2_events = {}
        # 1. Replay Opening
        _, cr_open2 = execute_opening_quant_adjustment("OPENING-20260701", wh_stock_loc, details["opening"]["units"], lot_opening, details["opening"]["date"])
        run2_events["opening"] = {"created": cr_open2}

        # 2. Replay Delivery
        _, cr_do2 = execute_operational_movement("DO-202607-0063", wh_stock_loc, customer_loc, details["delivery"]["units"], lot_opening, details["delivery"]["date"])
        run2_events["delivery"] = {"created": cr_do2}

        # 3. Replay Retur Karantina
        _, cr_rej2 = execute_operational_movement("REJ-202607-001", customer_loc, quarantine_loc, details["rejection"]["units"], lot_opening, details["rejection"]["date"])
        run2_events["rejection"] = {"created": cr_rej2}

        # 4. Replay PO Inbound Receipt
        _, cr_po2 = execute_operational_movement("PO-2026-06-05", supplier_loc, wh_stock_loc, details["receipt"]["units"], lot_po, details["receipt"]["date"])
        run2_events["receipt"] = {"created": cr_po2}

        env.cr.commit()
        report["run2_summary"] = run2_events

        # Deep Snapshot Post-Run 2
        moves_post = StockMove.search([("product_id", "=", product.id), ("company_id", "=", company.id)])
        lines_post = StockMoveLine.search([("product_id", "=", product.id), ("company_id", "=", company.id)])
        quants_post = StockQuant.search([("product_id", "=", product.id), ("company_id", "=", company.id)])
        svl_post = env["stock.valuation.layer"].sudo().search([("product_id", "=", product.id), ("company_id", "=", company.id)]) if has_svl else None

        snapshot_post = {
            "moves": {m.id: {"origin": m.origin, "date": str(m.date), "state": m.state, "qty": m.product_uom_qty} for m in moves_post},
            "lines": {ml.id: {"move_id": ml.move_id.id, "date": str(ml.date), "state": ml.state, "qty": ml.quantity, "lot_id": ml.lot_id.id} for ml in lines_post},
            "quants": {q.id: {"location_id": q.location_id.id, "lot_id": q.lot_id.id, "qty": q.quantity, "reserved": getattr(q, "reserved_quantity", 0.0)} for q in quants_post},
            "svls": {s.id: {"value": s.value, "qty": s.quantity, "cost": s.unit_cost} for s in svl_post} if svl_post else {},
            "accounting": take_accounting_snapshot(),
            "cutoffs": {k: get_historical_position(v["as_of"]) for k, v in oracle["cutoffs"].items()},
        }

        moves_identical = (snapshot_pre["moves"] == snapshot_post["moves"])
        lines_identical = (snapshot_pre["lines"] == snapshot_post["lines"])
        quants_identical = (snapshot_pre["quants"] == snapshot_post["quants"])
        svls_identical = (snapshot_pre["svls"] == snapshot_post["svls"])
        accounting_identical = (snapshot_pre["accounting"] == snapshot_post["accounting"])
        cutoffs_identical = (snapshot_pre["cutoffs"] == snapshot_post["cutoffs"])
        any_created_in_run2 = any(ev["created"] for ev in run2_events.values())

        zero_drift_pass = (
            moves_identical
            and lines_identical
            and quants_identical
            and svls_identical
            and accounting_identical
            and cutoffs_identical
            and (not any_created_in_run2)
        )

        report["idempotency_audit"] = {
            "moves_identical": moves_identical,
            "lines_identical": lines_identical,
            "quants_identical": quants_identical,
            "svls_identical": svls_identical,
            "accounting_identical": accounting_identical,
            "cutoffs_identical": cutoffs_identical,
            "any_created_in_run2": any_created_in_run2,
            "zero_drift_pass": zero_drift_pass,
        }

        print(f" -> Moves Identik: {moves_identical} (Pre={len(moves_pre)}, Post={len(moves_post)})")
        print(f" -> Move Lines Identik: {lines_identical} (Pre={len(lines_pre)}, Post={len(lines_post)})")
        print(f" -> Quants Identik: {quants_identical}")
        print(f" -> SVLs Identik: {svls_identical}")
        print(f" -> Jurnal Akuntansi Native Identik: {accounting_identical} (Moves Pre={len(snapshot_pre['accounting']['moves'])}, Post={len(snapshot_post['accounting']['moves'])})")
        print(f" -> 5 Cutoffs Re-Readback Identik: {cutoffs_identical}")

        # 8. Mutasi Terarah Aktual (Mutation Tests dengan Savepoint & Verifikasi 3-Fase: Baseline Valid -> Mutasi Ditolak -> Rollback Valid)
        print("\n[7/8] Menjalankan Mutasi Terarah Aktual (Mutation Tests via Savepoints)...")
        mutation_results = {}

        # Mutasi 1: Wrong Effective Date (DO Delivery bergeser ke now/hari ini)
        env.cr.execute("SAVEPOINT test_mutation_date")
        try:
            # Fase 1: Baseline validasi
            base_pos1 = get_historical_position("2026-07-03 14:00:00")
            base_ok1 = (base_pos1["saleable_cartons"] == oracle["cutoffs"]["cutoff_2"]["expected_saleable_cartons"])

            # Fase 2: Mutasi diterapkan
            mv_do.write({"date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            mv_do.move_line_ids.write({"date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            pos_mutated1 = get_historical_position("2026-07-03 14:00:00")
            mutated_rejected1 = (pos_mutated1["saleable_cartons"] != oracle["cutoffs"]["cutoff_2"]["expected_saleable_cartons"])
        finally:
            # Fase 3: Rollback dan revalidasi
            env.cr.execute("ROLLBACK TO SAVEPOINT test_mutation_date")
            env.invalidate_all()
            roll_pos1 = get_historical_position("2026-07-03 14:00:00")
            roll_ok1 = (roll_pos1["saleable_cartons"] == oracle["cutoffs"]["cutoff_2"]["expected_saleable_cartons"])

        mut1_pass = base_ok1 and mutated_rejected1 and roll_ok1
        mutation_results["wrong_date_rejected"] = mut1_pass
        print(f" -> Mutasi 1 (DO Date ke Now Ditolak): {'PASS' if mut1_pass else 'FAIL'} (Baseline={base_ok1}, Rejected={mutated_rejected1}, Rollback={roll_ok1})")

        # Mutasi 2: Manipulasi Nilai Valuasi & GL (+ Rp 50.000.000)
        env.cr.execute("SAVEPOINT test_mutation_val")
        try:
            # Fase 1: Baseline validasi
            base_pos2 = get_historical_position("2026-07-01 23:59:59")
            base_gl2 = base_pos2["odoo_gl_balance"]
            base_ok2 = (base_gl2 is not None and abs(base_gl2 - oracle["cutoffs"]["cutoff_1"]["expected_total_val"]) < 0.01)

            # Fase 2: Mutasi diterapkan via jurnal berimbang sah yang mendistorsi akun persediaan
            AccountMove = env["account.move"].sudo()
            mutated_move = AccountMove.create({
                "journal_id": stock_journal.id,
                "date": "2026-07-01",
                "ref": "OPENING-20260701-MUTATION",
                "company_id": company.id,
                "line_ids": [
                    (0, 0, {
                        "name": "Mutasi GL Uji Penolakan (Debit Persediaan)",
                        "account_id": stock_valuation_acc.id,
                        "product_id": product.id,
                        "debit": 50000000.0,
                        "credit": 0.0,
                        "date": "2026-07-01",
                    }),
                    (0, 0, {
                        "name": "Mutasi GL Uji Penolakan (Credit Lawan)",
                        "account_id": stock_input_acc.id,
                        "product_id": product.id,
                        "debit": 0.0,
                        "credit": 50000000.0,
                        "date": "2026-07-01",
                    }),
                ],
            })
            mutated_move.action_post()

            pos_mutated2 = get_historical_position("2026-07-01 23:59:59")
            gl_mutated2 = pos_mutated2["odoo_gl_balance"] or 0.0
            mutated_rejected2 = (abs(gl_mutated2 - oracle["cutoffs"]["cutoff_1"]["expected_total_val"]) > 100.0)
        finally:
            # Fase 3: Rollback dan revalidasi
            env.cr.execute("ROLLBACK TO SAVEPOINT test_mutation_val")
            env.invalidate_all()
            roll_pos2 = get_historical_position("2026-07-01 23:59:59")
            roll_gl2 = roll_pos2["odoo_gl_balance"]
            roll_ok2 = (roll_gl2 is not None and abs(roll_gl2 - oracle["cutoffs"]["cutoff_1"]["expected_total_val"]) < 0.01)

        mut2_pass = base_ok2 and mutated_rejected2 and roll_ok2
        mutation_results["bogus_valuation_rejected"] = mut2_pass
        print(f" -> Mutasi 2 (Nilai Valuasi/GL Palsu Ditolak): {'PASS' if mut2_pass else 'FAIL'} (Baseline={base_ok2}, Rejected={mutated_rejected2}, Rollback={roll_ok2})")

        # Mutasi 3: Future Receipt Leakage (PO Receipt 4 Juli bocor ke 2 Juli)
        env.cr.execute("SAVEPOINT test_mutation_leak")
        try:
            # Fase 1: Baseline validasi
            base_pos3 = get_historical_position("2026-07-03 14:00:00")
            base_ok3 = (base_pos3["saleable_cartons"] == oracle["cutoffs"]["cutoff_2"]["expected_saleable_cartons"])

            # Fase 2: Mutasi diterapkan
            mv_po.write({"date": "2026-07-02 10:00:00"})
            mv_po.move_line_ids.write({"date": "2026-07-02 10:00:00"})
            pos_mutated3 = get_historical_position("2026-07-03 14:00:00")
            mutated_rejected3 = (pos_mutated3["saleable_cartons"] > oracle["cutoffs"]["cutoff_2"]["expected_saleable_cartons"])
        finally:
            # Fase 3: Rollback dan revalidasi
            env.cr.execute("ROLLBACK TO SAVEPOINT test_mutation_leak")
            env.invalidate_all()
            roll_pos3 = get_historical_position("2026-07-03 14:00:00")
            roll_ok3 = (roll_pos3["saleable_cartons"] == oracle["cutoffs"]["cutoff_2"]["expected_saleable_cartons"])

        mut3_pass = base_ok3 and mutated_rejected3 and roll_ok3
        mutation_results["future_receipt_leakage_rejected"] = mut3_pass
        print(f" -> Mutasi 3 (Kebocoran PO Receipt Ditolak): {'PASS' if mut3_pass else 'FAIL'} (Baseline={base_ok3}, Rejected={mutated_rejected3}, Rollback={roll_ok3})")

        # Mutasi 4: Journal Date Only Distortion (Stok Tetap Benar, Tanggal Jurnal Bergeser Ditolak Gate EOD GL)
        env.cr.execute("SAVEPOINT test_mutation_journal_date")
        try:
            # Fase 1: Baseline validasi
            base_pos4 = get_historical_position("2026-07-04 23:59:59")
            base_ok4 = (base_pos4["odoo_eod_gl_balance"] is not None and abs(base_pos4["odoo_eod_gl_balance"] - oracle["cutoffs"]["cutoff_4"]["expected_eod_gl"]) < 0.01)

            # Fase 2: Mutasi diterapkan - hanya geser tanggal account.move native tanpa menyentuh stok fisik
            am_po = getattr(mv_po, "account_move_id", None) or env["account.move"].sudo().search([("stock_move_id", "=", mv_po.id)], limit=1)
            if not am_po:
                am_po = env["account.move"].sudo().search([("ref", "ilike", "PO-2026-06-05"), ("company_id", "in", [False, company.id])], limit=1)
            # Geser tanggal jurnal dari 4 Juli ke 10 Juli (di luar cut-off)
            env.cr.execute("UPDATE account_move SET date = '2026-07-10' WHERE id = %s", [am_po.id])
            env.cr.execute("UPDATE account_move_line SET date = '2026-07-10' WHERE move_id = %s", [am_po.id])
            env.invalidate_all()

            pos_mutated4 = get_historical_position("2026-07-04 23:59:59")
            # Fisik tetap cocok tapi saldo EOD GL pada 4 Juli wajib berubah/salah
            gl_mutated4 = pos_mutated4["odoo_eod_gl_balance"] or 0.0
            mutated_rejected4 = (abs(gl_mutated4 - oracle["cutoffs"]["cutoff_4"]["expected_eod_gl"]) > 100.0)
        finally:
            # Fase 3: Rollback dan revalidasi
            env.cr.execute("ROLLBACK TO SAVEPOINT test_mutation_journal_date")
            env.invalidate_all()
            roll_pos4 = get_historical_position("2026-07-04 23:59:59")
            roll_ok4 = (roll_pos4["odoo_eod_gl_balance"] is not None and abs(roll_pos4["odoo_eod_gl_balance"] - oracle["cutoffs"]["cutoff_4"]["expected_eod_gl"]) < 0.01)

        mut4_pass = base_ok4 and mutated_rejected4 and roll_ok4
        mutation_results["journal_date_only_distortion_rejected"] = mut4_pass
        print(f" -> Mutasi 4 (Tanggal Jurnal Saja Bergeser Ditolak EOD GL): {'PASS' if mut4_pass else 'FAIL'} (Baseline={base_ok4}, Rejected={mutated_rejected4}, Rollback={roll_ok4})")

        # Mutasi 5: Split Fraud Akun Pasangan (Debit Rp1 HPP + Sisa Akun Asing Ditolak)
        env.cr.execute("SAVEPOINT test_mutation_split_fraud")
        try:
            # Fase 1: Baseline validasi
            base_audit5 = audit_event_account_pair(
                "delivery", mv_do, details["delivery"]["expected_debit_acc"],
                details["delivery"]["expected_credit_acc"], details["delivery"]["expected_amount"]
            )
            base_ok5 = base_audit5.get("balanced", False)

            # Fase 2: Mutasi diterapkan - split debit Rp1 ke HPP 510000 + sisanya ke akun salah
            am_do = getattr(mv_do, "account_move_id", None) or env["account.move"].sudo().search([("stock_move_id", "=", mv_do.id)], limit=1)
            if not am_do:
                am_do = env["account.move"].sudo().search([("ref", "ilike", "DO-202607-0063"), ("company_id", "in", [False, company.id])], limit=1)

            debit_line = [line_rec for line_rec in am_do.line_ids if line_rec.debit > 0][0]
            orig_debit = debit_line.debit
            # Mutasi via ORM resmi Odoo (with_context check_move_validity=False)
            debit_line.with_context(check_move_validity=False).write({"debit": 1.0})
            aml_vals = {
                "move_id": am_do.id,
                "account_id": stock_input_acc.id,
                "debit": orig_debit - 1.0,
                "credit": 0.0,
                "date": debit_line.date,
                "name": "Fake Split Line",
                "company_id": company.id,
            }
            env["account.move.line"].with_context(check_move_validity=False).create(aml_vals)
            env.invalidate_all()

            mutated_rejected5 = False
            try:
                audit_event_account_pair(
                    "delivery", mv_do, details["delivery"]["expected_debit_acc"],
                    details["delivery"]["expected_credit_acc"], details["delivery"]["expected_amount"]
                )
            except ValueError as ve:
                if "memiliki baris debit tidak sah/ekstra" in str(ve) or "tidak cocok dengan expected" in str(ve):
                    mutated_rejected5 = True
        finally:
            # Fase 3: Rollback dan revalidasi
            env.cr.execute("ROLLBACK TO SAVEPOINT test_mutation_split_fraud")
            env.invalidate_all()
            roll_audit5 = audit_event_account_pair(
                "delivery", mv_do, details["delivery"]["expected_debit_acc"],
                details["delivery"]["expected_credit_acc"], details["delivery"]["expected_amount"]
            )
            roll_ok5 = roll_audit5.get("balanced", False)

        mut5_pass = base_ok5 and mutated_rejected5 and roll_ok5
        mutation_results["account_pair_split_fraud_rejected"] = mut5_pass
        print(f" -> Mutasi 5 (Split Fraud Rp1 HPP + Sisa Akun Asing Ditolak): {'PASS' if mut5_pass else 'FAIL'} (Baseline={base_ok5}, Rejected={mutated_rejected5}, Rollback={roll_ok5})")

        # Mutasi 6: Akun Kredit Substitusi / Kredit Ekstra Ditolak
        env.cr.execute("SAVEPOINT test_mutation_credit_sub")
        try:
            # Fase 1: Baseline validasi
            base_audit6 = audit_event_account_pair(
                "receipt", mv_po, details["receipt"]["expected_debit_acc"],
                details["receipt"]["expected_credit_acc"], details["receipt"]["expected_amount"]
            )
            base_ok6 = base_audit6.get("balanced", False)

            # Fase 2: Mutasi diterapkan - ganti akun kredit 211000 dengan akun beban/lain via ORM
            am_po = getattr(mv_po, "account_move_id", None) or env["account.move"].sudo().search([("stock_move_id", "=", mv_po.id)], limit=1)
            if not am_po:
                am_po = env["account.move"].sudo().search([("ref", "ilike", "PO-2026-06-05"), ("company_id", "in", [False, company.id])], limit=1)
            credit_line = [line_rec for line_rec in am_po.line_ids if line_rec.credit > 0][0]
            credit_line.with_context(check_move_validity=False).write({"account_id": cogs_acc.id})
            env.invalidate_all()

            mutated_rejected6 = False
            try:
                audit_event_account_pair(
                    "receipt", mv_po, details["receipt"]["expected_debit_acc"],
                    details["receipt"]["expected_credit_acc"], details["receipt"]["expected_amount"]
                )
            except ValueError as ve:
                if "tidak mengkredit akun yang diharapkan" in str(ve) or "baris kredit tidak sah" in str(ve):
                    mutated_rejected6 = True
        finally:
            # Fase 3: Rollback dan revalidasi
            env.cr.execute("ROLLBACK TO SAVEPOINT test_mutation_credit_sub")
            env.invalidate_all()
            roll_audit6 = audit_event_account_pair(
                "receipt", mv_po, details["receipt"]["expected_debit_acc"],
                details["receipt"]["expected_credit_acc"], details["receipt"]["expected_amount"]
            )
            roll_ok6 = roll_audit6.get("balanced", False)

        mut6_pass = base_ok6 and mutated_rejected6 and roll_ok6
        mutation_results["account_pair_credit_substitution_rejected"] = mut6_pass
        print(f" -> Mutasi 6 (Substitusi Akun Kredit Ditolak): {'PASS' if mut6_pass else 'FAIL'} (Baseline={base_ok6}, Rejected={mutated_rejected6}, Rollback={roll_ok6})")

        # Mutasi 7: Kuantitas Sumber Tak Mencukupi / Negative Stock Fail-Fast Ditolak
        env.cr.execute("SAVEPOINT test_mutation_insufficient_stock")
        try:
            # Fase 1: Baseline validasi (snapshot stok fisik dan saldo EOD GL sebelum mutasi)
            base_pos7 = get_historical_position("2026-07-04 23:59:59")
            base_ok7 = (
                base_pos7["saleable_cartons"] == oracle["cutoffs"]["cutoff_4"]["expected_saleable_cartons"]
                and base_pos7["quarantine_cartons"] == oracle["cutoffs"]["cutoff_4"]["expected_quarantine_cartons"]
                and base_pos7["odoo_eod_gl_balance"] is not None
                and abs(base_pos7["odoo_eod_gl_balance"] - oracle["cutoffs"]["cutoff_4"]["expected_eod_gl"]) < 0.01
            )

            # Fase 2: Mutasi diterapkan - mencoba pergerakan outbound internal sebesar 999.999 unit (melebihi stok)
            mutated_rejected7 = False
            try:
                execute_operational_movement(
                    origin="DO-EXCESSIVE-DEMAND",
                    loc_src=wh_stock_loc,
                    loc_dest=customer_loc,
                    qty=999999.0,
                    lot=lot_opening,
                    move_date="2026-07-04 12:00:00",
                )
            except ValueError as ve:
                if any(k in str(ve) for k in ["tidak mencukupi demand", "Penolakan stok negatif", "Reservasi kosong"]):
                    mutated_rejected7 = True
        finally:
            # Fase 3: Rollback dan revalidasi (verifikasi pemulihan 100% tanpa drift)
            env.cr.execute("ROLLBACK TO SAVEPOINT test_mutation_insufficient_stock")
            env.invalidate_all()
            roll_pos7 = get_historical_position("2026-07-04 23:59:59")
            roll_ok7 = (
                roll_pos7["saleable_cartons"] == base_pos7["saleable_cartons"]
                and roll_pos7["quarantine_cartons"] == base_pos7["quarantine_cartons"]
                and roll_pos7["odoo_eod_gl_balance"] is not None
                and abs(roll_pos7["odoo_eod_gl_balance"] - base_pos7["odoo_eod_gl_balance"]) < 0.01
            )

        mut7_pass = base_ok7 and mutated_rejected7 and roll_ok7
        mutation_results["insufficient_stock_demand_rejected"] = mut7_pass
        print(f" -> Mutasi 7 (Kuantitas Tak Mencukupi / Stok Negatif Ditolak): {'PASS' if mut7_pass else 'FAIL'} (Baseline={base_ok7}, Rejected={mutated_rejected7}, Rollback={roll_ok7})")

        all_mutations_rejected = all(mutation_results.values())
        report["mutation_tests"] = mutation_results

        # 9. Verifikasi Readback Stateless via Environment & Cursor Baru Odoo 19
        print("\n[Stateless Readback] Memverifikasi seluruh cut-off EOD GL via Cursor/Environment Baru...")
        with env.registry.cursor() as new_cr:
            new_env = env(cr=new_cr)
            new_product = new_env["product.product"].browse(product.id)
            new_company = new_env.company
            for c_key, c_exp in oracle["cutoffs"].items():
                eod_date = c_exp["as_of"][:10]
                amls = new_env["account.move.line"].search([
                    ("account_id.code", "=", "113000"),
                    ("product_id", "=", new_product.id),
                    ("parent_state", "=", "posted"),
                    ("date", "<=", eod_date),
                    ("company_id", "in", [False, new_company.id]),
                ])
                eod_balance = round(sum(a.debit - a.credit for a in amls), 2)
                if abs(eod_balance - c_exp["expected_eod_gl"]) > 0.01:
                    raise ValueError(
                        f"[FAIL-FAST] Stateless readback gagal pada {c_key} ({eod_date})! "
                        f"Aktual: Rp{eod_balance:,.2f}, Expected: Rp{c_exp['expected_eod_gl']:,.2f}"
                    )
        print(" -> [Stateless Readback OK] Seluruh 5 cut-off EOD GL terbukti 100% konsisten pada cursor independen!")

        # Evaluasi Akhir
        if all_cutoffs_match and zero_drift_pass and all_mutations_rejected:
            report["status"] = "SUCCESS"
            print("\n" + "=" * 80)
            print("[SUCCESS] Eksperimen Seeding Historis Minimal Odoo 19 LULUS 100%!")
            print("=" * 80)
        else:
            report["status"] = "FAILURE"
            print("\n" + "=" * 80)
            print("[FAIL] Eksperimen Seeding Historis GAGAL memenuhi kriteria acceptance.")
            print("=" * 80)

    except Exception as exc:
        report["status"] = "ERROR"
        report["error"] = str(exc)
        print(f"\n[EXCEPTION] Terjadi kesalahan fatal: {exc}")
        import traceback
        traceback.print_exc()

    finally:
        print("\n[8/8] Mengekspor Laporan Diagnostik ke JSON...")
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
