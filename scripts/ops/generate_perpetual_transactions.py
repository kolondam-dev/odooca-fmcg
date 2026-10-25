#!/usr/bin/env python3
"""Granular Perpetual Inventory Turnover & Transaction Engine FMCG Manado.

Mensimulasikan seluruh rantai transaksi kausal dan deterministik:
1. Saldo Awal Fisik 1 Juli 2026 (150 SKU, 32.748 karton).
2. PO In-Transit Juni tiba 1-4 Juli di Pelabuhan Bitung & Gudang Maumbi (41.442 karton).
3. Daily Sales Order (SO) hanya atas stok AVAILABLE (Physical - Reserved) pada jam 08:00.
4. Pemisahan eksplisit: Physical On-Hand vs Reserved vs Delivered vs Quarantine.
5. Picklist, Packlist/DO H+1, dan Invoice tercetak atas barang diterima (net of rejection).
6. Rekonsiliasi retur: Rejection masuk ke Aset Persediaan Karantina Gudang Maumbi senilai COGS.
   COGS Laba Rugi hanya membebankan barang yang benar-benar diterima customer (Accepted COGS).
7. AR Cash Collection terikat 1-ke-1 dengan invoice_number secara deterministik (kebal PYTHONHASHSEED).
8. AP Payments ke principal sesuai termin dagang resmi.
9. OPEX harian logistik + Payroll 24 Personel & Lembur Overstok di akhir Juli.
10. Event ledger stok terpisah per SKU/lot/tanggal untuk auditability dan replay.
"""

import collections
import csv
import datetime as dt
import hashlib
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from scripts.ops.fmcg_calendar import get_next_working_day, is_working_day  # noqa: E402

REG_DIR = ROOT / "data" / "registers"
SEED_DIR = ROOT / "data" / "seed"
REG_DIR.mkdir(parents=True, exist_ok=True)

# Seed PRNG deterministik
random.seed(20260701)


def deterministic_hash(key: str, salt: str = "fmcg-manado-salt") -> int:
    """Hash deterministik berbasis SHA-256 (independen dari PYTHONHASHSEED)."""
    digest = hashlib.sha256(f"{salt}:{key}".encode("utf-8")).hexdigest()
    return int(digest, 16)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=pathlib.Path, default=REG_DIR)
    args = parser.parse_args()
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 85)
    print("GRANULAR PERPETUAL INVENTORY TURNOVER & TRANSACTION ENGINE (JULI 2026)")
    print("=" * 85)

    # 1. Muat Master Data
    with open(SEED_DIR / "products_150.csv", "r", encoding="utf-8") as f:
        products = list(csv.DictReader(f))
    prod_map = {p["default_code"]: p for p in products}

    with open(REG_DIR / "customer_registry_354.json", "r", encoding="utf-8") as f:
        customers_reg = json.load(f)
    cust_map = {c["ref"]: c for c in customers_reg}

    with open(REG_DIR / "initial_stock_20260701.json", "r", encoding="utf-8") as f:
        initial_stock = json.load(f)

    with open(REG_DIR / "inbound_po_intransit_june_headers.json", "r", encoding="utf-8") as f:
        po_headers = json.load(f)

    with open(REG_DIR / "inbound_po_intransit_june_lines.json", "r", encoding="utf-8") as f:
        po_lines = json.load(f)

    with open(REG_DIR / "pjp_july_2026_matrix.csv", "r", encoding="utf-8") as f:
        pjp_matrix = list(csv.DictReader(f))

    # Struktur Status Stok Multi-Level per SKU
    stock_state = {}
    for item in initial_stock:
        sku = item["sku_code"]
        qty = int(item["qty_cartons_on_hand"])
        stock_state[sku] = {
            "physical": qty,
            "reserved": 0,
            "quarantine": 0,
            "lots": [
                {
                    "lot": item["lot_number"],
                    "physical": qty,
                    "reserved": 0,
                    "cost": float(item["unit_cost_price"]),
                    "exp": item["expiry_date"],
                }
            ],
        }

    # Inbound PO lines dikelompokkan per tanggal tiba
    inbound_by_date = {}
    for h in po_headers:
        arr_dt = h["arrival_maumbi_date"]
        po_num = h["po_number"]
        lines = [line for line in po_lines if line["po_number"] == po_num]
        inbound_by_date.setdefault(arr_dt, []).extend(lines)

    # PJP Matrix dikelompokkan per tanggal kunjungan (hanya kunjungan outlet riil, abaikan STANDBY kantor)
    pjp_by_date = {}
    for row in pjp_matrix:
        if row.get("frekuensi_call") == "STANDBY" or row.get("customer") == "ADMIN / STAGING LOGISTIK":
            continue
        pjp_by_date.setdefault(row["tanggal"], []).append(row)

    # Jadwal AP Payments atas PO In-Transit Juni diturunkan langsung dari PO Header sumber
    ap_schedule = []
    for h in po_headers:
        ap_schedule.append({
            "po_number": h["po_number"],
            "principal_name": h["principal_name"],
            "amount": float(h["total_dpp"]),
            "due_date": h["due_date"],
            "pay_date": h["ap_payment_date"],
            "status": "Open",
        })

    # Containers Output Transaksi
    sales_orders = []
    order_lines = []
    deliveries = []
    rejections = []
    invoices = []
    ar_collections = []
    ap_payments = []
    opex_payroll_entries = []
    daily_stock_cards = []
    stock_event_ledger = []

    # Penampung Open Deliveries yang menunggu dispatch fisik per tanggal:
    # pending_dispatches[deliv_date] = [ { "so_num": str, "do_num": str, "lines": list, ... } ]
    pending_dispatches = collections.defaultdict(list)

    open_ar_ledger = []
    so_counter = 1
    do_counter = 1
    rej_counter = 1
    inv_counter = 1
    pay_counter = 1
    event_counter = 1
    visit_order_counter = 0

    # Catat event saldo awal 1 Juli 2026 di event ledger
    for item in initial_stock:
        sku = item["sku_code"]
        stock_event_ledger.append({
            "event_id": f"EVT-{event_counter:06d}",
            "date": "2026-07-01",
            "event_type": "INITIAL_STOCK",
            "reference": "OPENING-20260701",
            "sku_code": sku,
            "lot_number": item["lot_number"],
            "qty_cartons": int(item["qty_cartons_on_hand"]),
            "unit_cost_price": float(item["unit_cost_price"]),
            "total_cost_dpp": float(item["subtotal_dpp"]),
            "physical_impact": int(item["qty_cartons_on_hand"]),
            "reserved_impact": 0,
            "quarantine_impact": 0,
            "notes": "Saldo Awal Fisik Gudang Maumbi per 1 Juli 2026",
        })
        event_counter += 1

    start_dt = dt.date(2026, 7, 1)
    end_dt = dt.date(2026, 7, 31)
    curr_dt = start_dt

    while curr_dt <= end_dt:
        d_str = curr_dt.strftime("%Y-%m-%d")
        day_name = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"][curr_dt.weekday()]
        is_work = is_working_day(curr_dt)

        # -------------------------------------------------------------
        # STEP 1: TERIMA INBOUND PO JUNI / KAPAL BITUNG (Pagi 07:00 WITA)
        # -------------------------------------------------------------
        inbound_lines_today = inbound_by_date.get(d_str, [])
        for line in inbound_lines_today:
            sku = line["sku_code"]
            ctns = int(line["qty_cartons"])
            cost = float(line["unit_cost_price"])
            lot = line["lot_number"]
            exp = line["expiry_date"]
            stock_state[sku]["physical"] += ctns
            stock_state[sku]["lots"].append({
                "lot": lot,
                "physical": ctns,
                "reserved": 0,
                "cost": cost,
                "exp": exp,
            })
            stock_event_ledger.append({
                "event_id": f"EVT-{event_counter:06d}",
                "date": d_str,
                "event_type": "PO_RECEIPT",
                "reference": line["po_number"],
                "sku_code": sku,
                "lot_number": lot,
                "qty_cartons": ctns,
                "unit_cost_price": cost,
                "total_cost_dpp": round(float(line["subtotal_dpp"]), 2),
                "physical_impact": ctns,
                "reserved_impact": 0,
                "quarantine_impact": 0,
                "notes": f"Penerimaan Kontainer In-Transit Juni {line['po_number']}",
            })
            event_counter += 1

        # -------------------------------------------------------------
        # STEP 2: DISPATCH FISIK DO PADA HARI INI (Pagi 07:30 WITA)
        # -------------------------------------------------------------
        # Pengiriman fisik atas SO yang dijadwalkan tiba/dikirim hari ini
        dispatches_today = pending_dispatches.get(d_str, [])
        daily_do_delivered_dpp = 0.0
        daily_do_rejection_dpp = 0.0
        daily_cogs_accepted = 0.0
        daily_cogs_rejection = 0.0

        for disp in dispatches_today:
            # Eksekusi pengurangan fisik gudang dan pelepasan reservasi
            for line_disp in disp["lines"]:
                sku = line_disp["sku_code"]
                lot = line_disp["lot_number"]
                take_qty = line_disp["qty_cartons"]

                stock_state[sku]["physical"] -= take_qty
                stock_state[sku]["reserved"] -= take_qty

                # Update status di dalam lot
                for lot_item in stock_state[sku]["lots"]:
                    if lot_item["lot"] == lot:
                        lot_item["physical"] -= take_qty
                        lot_item["reserved"] -= take_qty
                        break

                stock_event_ledger.append({
                    "event_id": f"EVT-{event_counter:06d}",
                    "date": d_str,
                    "event_type": "DO_DISPATCH",
                    "reference": disp["do_number"],
                    "sku_code": sku,
                    "lot_number": lot,
                    "qty_cartons": take_qty,
                    "unit_cost_price": line_disp["unit_cost"],
                    "total_cost_dpp": round(take_qty * line_disp["unit_cost"] * line_disp["carton_qty"], 2),
                    "physical_impact": -take_qty,
                    "reserved_impact": -take_qty,
                    "quarantine_impact": 0,
                    "notes": f"Dispatch Pengiriman Fisik DO {disp['do_number']} atas SO {disp['so_number']}",
                })
                event_counter += 1

            # Tangani jika ada barang reject / retur handling transit
            if disp["rejection_line"]:
                rej = disp["rejection_line"]
                rej_sku = rej["sku_code"]
                rej_lot = rej["lot_number"]
                rej_qty = rej["qty_cartons"]

                stock_state[rej_sku]["quarantine"] += rej_qty

                stock_event_ledger.append({
                    "event_id": f"EVT-{event_counter:06d}",
                    "date": d_str,
                    "event_type": "QUARANTINE_RECEIPT",
                    "reference": rej["rejection_id"],
                    "sku_code": rej_sku,
                    "lot_number": rej_lot,
                    "qty_cartons": rej_qty,
                    "unit_cost_price": rej["unit_cost"],
                    "total_cost_dpp": round(rej["cogs_subtotal"], 2),
                    "physical_impact": 0,
                    "reserved_impact": 0,
                    "quarantine_impact": rej_qty,
                    "notes": f"Penerimaan Retur Karantina Bad Stock DO {disp['do_number']}",
                })
                event_counter += 1

            daily_do_delivered_dpp += disp["do_delivered_dpp"]
            daily_do_rejection_dpp += disp["rejection_dpp"]
            daily_cogs_accepted += disp["delivered_cogs_dpp"]
            daily_cogs_rejection += disp["rejection_cogs_dpp"]

        # -------------------------------------------------------------
        # STEP 3: PJP SALES CALLS & STRICT AVAILABLE ORDERS (08:00 - 14:00)
        # -------------------------------------------------------------
        visits_today = pjp_by_date.get(d_str, [])
        daily_so_gross = 0.0
        daily_so_disc = 0.0
        daily_so_net = 0.0
        daily_so_cogs = 0.0

        if is_work and visits_today:
            for visit in visits_today:
                ch = visit["channel"]
                sls = visit["salesman"]
                cust = visit["customer"]
                dist = visit["district"]
                veh = visit["delivery_vehicle"]

                # Target basket size realistis per channel untuk target distributor ~Rp 5.2 - 5.5 BIO
                if ch == "MT":
                    target_subtotal = random.uniform(30_000_000, 42_000_000)
                    sku_count = random.randint(8, 14)
                    disc_pct = 0.052  # 5.2% trade promo push MT Juli
                elif ch == "GT":
                    target_subtotal = random.uniform(16_000_000, 26_000_000)
                    sku_count = random.randint(6, 11)
                    disc_pct = 0.048  # 4.8% diskon taktis grosir
                elif ch == "INST":
                    target_subtotal = random.uniform(15_000_000, 24_000_000)
                    sku_count = random.randint(4, 8)
                    disc_pct = 0.040
                else:  # RTL
                    target_subtotal = random.uniform(3_500_000, 6_500_000)
                    sku_count = random.randint(3, 5)
                    disc_pct = 0.035  # 3.5% cash discount kios

                # Filter SKU yang memiliki AVAILABLE stock (Physical - Reserved) > 0 dan belum kedaluwarsa
                available_skus = []
                for s, data in stock_state.items():
                    avail_qty = sum(
                        lot_item["physical"] - lot_item["reserved"]
                        for lot_item in data["lots"]
                        if (lot_item["physical"] - lot_item["reserved"]) > 0 and lot_item["exp"] >= d_str
                    )
                    if avail_qty > 0:
                        available_skus.append(s)

                if not available_skus:
                    continue

                selected_skus = random.sample(available_skus, min(sku_count, len(available_skus)))

                visit_candidate_lines = []

                for sku in selected_skus:
                    p = prod_map[sku]
                    c_cost = float(p["cost_price"]) * int(p["carton_qty"])
                    c_price = float(p["list_price"]) * int(p["carton_qty"])

                    desired_ctns = max(1, int(round((target_subtotal / len(selected_skus)) / c_price)))
                    sku_lots = stock_state[sku]["lots"]
                    available_for_sku = sum(
                        lot_item["physical"] - lot_item["reserved"]
                        for lot_item in sku_lots
                        if (lot_item["physical"] - lot_item["reserved"]) > 0 and lot_item["exp"] >= d_str
                    )
                    allocated_ctns = min(desired_ctns, available_for_sku)
                    if allocated_ctns <= 0:
                        continue

                    # Alokasi strictly FEFO pada ketersediaan available
                    sku_lots.sort(key=lambda x: x["exp"])
                    rem_to_take = allocated_ctns

                    for lot_entry in sku_lots:
                        lot_avail = lot_entry["physical"] - lot_entry["reserved"]
                        if lot_avail <= 0 or lot_entry["exp"] < d_str:
                            continue

                        take_qty = min(rem_to_take, lot_avail)
                        # Reservasi bertambah; fisik BELUM berkurang hingga DO diberangkatkan
                        lot_entry["reserved"] += take_qty
                        stock_state[sku]["reserved"] += take_qty
                        rem_to_take -= take_qty

                        line_gross = round(take_qty * c_price, 2)
                        line_cogs = round(take_qty * c_cost, 2)

                        visit_candidate_lines.append({
                            "date_order": d_str,
                            "sku_code": sku,
                            "product_name": p["name"],
                            "brand_code": p["brand_code"],
                            "principal_code": p["principal_code"],
                            "fmcg_category": p["fmcg_category"],
                            "qty_cartons": take_qty,
                            "carton_qty": int(p["carton_qty"]),
                            "unit_price_dpp": float(p["list_price"]),
                            "carton_price_dpp": c_price,
                            "line_subtotal_dpp": line_gross,
                            "cogs_subtotal": line_cogs,
                            "lot_number": lot_entry["lot"],
                            "unit_cost": float(p["cost_price"]),
                        })

                        if rem_to_take == 0:
                            break

                if not visit_candidate_lines:
                    continue

                visit_order_counter += 1

                # Cek apakah kunjungan ini mengalami rejection penolakan transit (~4-5% order GT & MT)
                has_visit_rejection = (ch in ("GT", "MT") and len(visit_candidate_lines) >= 2 and ((visit_order_counter + 1) % 20 == 0))
                target_rej_sku = visit_candidate_lines[0]["sku_code"] if has_visit_rejection else None
                target_rej_lot = visit_candidate_lines[0]["lot_number"] if has_visit_rejection else None
                target_rej_prin = prod_map[target_rej_sku]["principal_code"] if has_visit_rejection else None

                deliv_dt = get_next_working_day(curr_dt)
                deliv_date = deliv_dt.strftime("%Y-%m-%d")
                cust_ref = cust.split(" - ")[0]
                cust_master = cust_map[cust_ref]
                top_days = int(cust_master["payment_term_days"])
                due_dt = deliv_dt + dt.timedelta(days=top_days)
                due_date_str = due_dt.strftime("%Y-%m-%d")

                # Kelompokkan baris pesanan kunjungan per prinsipal
                lines_by_prin = collections.defaultdict(list)
                for cand_line in visit_candidate_lines:
                    lines_by_prin[cand_line["principal_code"]].append(cand_line)

                for prin in sorted(lines_by_prin.keys()):
                    prin_lines = lines_by_prin[prin]
                    so_num = f"SO-202607-{so_counter:04d}"
                    so_counter += 1
                    do_num = f"DO-202607-{do_counter:04d}"
                    do_counter += 1

                    current_so_gross = 0.0
                    current_so_cogs = 0.0

                    for line in prin_lines:
                        current_so_gross += line["line_subtotal_dpp"]
                        current_so_cogs += line["cogs_subtotal"]

                        order_lines.append({
                            "so_number": so_num,
                            "date_order": d_str,
                            "sku_code": line["sku_code"],
                            "product_name": line["product_name"],
                            "brand_code": line["brand_code"],
                            "fmcg_category": line["fmcg_category"],
                            "qty_cartons": line["qty_cartons"],
                            "carton_qty": line["carton_qty"],
                            "unit_price_dpp": line["unit_price_dpp"],
                            "carton_price_dpp": line["carton_price_dpp"],
                            "line_subtotal_dpp": line["line_subtotal_dpp"],
                            "cogs_subtotal": line["cogs_subtotal"],
                            "lot_number": line["lot_number"],
                            "unit_cost": line["unit_cost"],
                        })

                        stock_event_ledger.append({
                            "event_id": f"EVT-{event_counter:06d}",
                            "date": d_str,
                            "event_type": "SO_RESERVATION",
                            "reference": so_num,
                            "sku_code": line["sku_code"],
                            "lot_number": line["lot_number"],
                            "qty_cartons": line["qty_cartons"],
                            "unit_cost_price": line["unit_cost"],
                            "total_cost_dpp": line["cogs_subtotal"],
                            "physical_impact": 0,
                            "reserved_impact": line["qty_cartons"],
                            "quarantine_impact": 0,
                            "notes": f"Reservasi Stok Pesanan Sales Order {so_num}",
                        })
                        event_counter += 1

                    rej_amt = 0.0
                    rej_cogs = 0.0
                    rejection_payload = None

                    if has_visit_rejection and prin == target_rej_prin:
                        rej_sku = target_rej_sku
                        rej_lot = target_rej_lot
                        rej_qty = 1
                        rej_c_price = prin_lines[0]["carton_price_dpp"]
                        rej_c_cost = float(prod_map[rej_sku]["cost_price"]) * int(prod_map[rej_sku]["carton_qty"])
                        rej_amt = round(rej_c_price * rej_qty, 2)
                        rej_cogs = round(rej_c_cost * rej_qty, 2)

                        rej_id = f"REJ-202607-{rej_counter:03d}"
                        rej_counter += 1

                        rejection_payload = {
                            "rejection_id": rej_id,
                            "so_number": so_num,
                            "do_number": do_num,
                            "rejection_date": deliv_date,
                            "customer": cust,
                            "channel": ch,
                            "sku_code": rej_sku,
                            "product_name": prin_lines[0]["product_name"],
                            "lot_number": rej_lot,
                            "qty_cartons": rej_qty,
                            "carton_qty": prin_lines[0]["carton_qty"],
                            "unit_price_dpp": prin_lines[0]["unit_price_dpp"],
                            "line_subtotal_dpp": rej_amt,
                            "cogs_subtotal": rej_cogs,
                            "rejection_reason": "Kemasan basah/penyok saat handling transit",
                            "disposition": "Karantina Gudang Maumbi / Bad Stock",
                            "unit_cost": float(prod_map[rej_sku]["cost_price"]),
                        }
                        rejections.append(rejection_payload)

                    do_delivered_amt = round(current_so_gross - rej_amt, 2)
                    so_disc_amt = round(current_so_gross * disc_pct, 2)
                    so_net_dpp = round(current_so_gross - so_disc_amt, 2)
                    delivered_cogs = round(current_so_cogs - rej_cogs, 2)

                    pending_dispatches[deliv_date].append({
                        "so_number": so_num,
                        "do_number": do_num,
                        "deliv_date": deliv_date,
                        "lines": prin_lines,
                        "rejection_line": rejection_payload,
                        "do_delivered_dpp": do_delivered_amt,
                        "rejection_dpp": rej_amt,
                        "delivered_cogs_dpp": delivered_cogs,
                        "rejection_cogs_dpp": rej_cogs,
                    })

                    sales_orders.append({
                        "so_number": so_num,
                        "date_order": d_str,
                        "salesman": sls,
                        "customer": cust,
                        "channel": ch,
                        "district": dist,
                        "delivery_vehicle": veh,
                        "gross_dpp": round(current_so_gross, 2),
                        "discount_dpp": round(so_disc_amt, 2),
                        "net_dpp": round(so_net_dpp, 2),
                        "cogs_dpp": round(current_so_cogs, 2),
                        "rejection_dpp": round(rej_amt, 2),
                        "do_delivered_dpp": round(do_delivered_amt, 2),
                    })

                    deliveries.append({
                        "do_number": do_num,
                        "so_number": so_num,
                        "scheduled_delivery_date": deliv_date,
                        "delivery_vehicle": veh,
                        "customer": cust,
                        "channel": ch,
                        "gross_order_dpp": round(current_so_gross, 2),
                        "rejection_dpp": round(rej_amt, 2),
                        "do_delivered_dpp": round(do_delivered_amt, 2),
                        "rejection_reason": "Kemasan basah/penyok saat handling transit" if rej_amt > 0 else "-",
                    })

                    inv_num = f"INV-202607-{inv_counter:04d}"
                    inv_counter += 1

                    inv_disc_amt = round(do_delivered_amt * disc_pct, 2)
                    final_inv_dpp = round(do_delivered_amt - inv_disc_amt, 2)
                    ppn_11_amt = round(final_inv_dpp * 0.11, 2)
                    final_inv_total = round(final_inv_dpp + ppn_11_amt, 2)

                    invoices.append({
                        "invoice_number": inv_num,
                        "so_number": so_num,
                        "do_number": do_num,
                        "date_invoice": deliv_date,
                        "due_date": due_date_str,
                        "customer": cust,
                        "channel": ch,
                        "salesman": sls,
                        "dpp_amount": round(final_inv_dpp, 2),
                        "ppn_11_amount": round(ppn_11_amt, 2),
                        "total_invoice_with_ppn": round(final_inv_total, 2),
                        "payment_term_days": top_days,
                    })

                    open_ar_ledger.append({
                        "invoice_number": inv_num,
                        "customer": cust,
                        "channel": ch,
                        "salesman": sls,
                        "dpp_amount": final_inv_dpp,
                        "ppn_amount": ppn_11_amt,
                        "total_with_ppn": final_inv_total,
                        "invoice_date": deliv_date,
                        "due_date": due_date_str,
                        "payment_term_days": top_days,
                        "status": "Open",
                    })

                    daily_so_gross += current_so_gross
                    daily_so_disc += so_disc_amt
                    daily_so_net += so_net_dpp
                    daily_so_cogs += current_so_cogs

        # -------------------------------------------------------------
        # STEP 4: AR CASH & TRANSFER COLLECTIONS (Pelunasan Piutang)
        # -------------------------------------------------------------
        # Pelunasan deterministik:
        # A. Kios RTL Cash COD (TOP 0 hari): Lunas pada hari H penyerahan/faktur terbit
        # B. GT/MT/INST dengan termin kredit (TOP >= 7):
        #    Skenario Pemajuan Tagihan (Cash Discount 1% 7 hari): Bayar maju di hari ke 5-7.
        #    Pemilihan stabil memakai deterministic_hash(invoice_number).
        # C. Pelunasan saat jatuh tempo sesuai termin master customer.
        daily_ar_collected_dpp = 0.0
        daily_ar_collected_total = 0.0
        daily_early_discount_dpp = 0.0

        for ar in open_ar_ledger:
            if ar["status"] != "Open":
                continue

            inv_dt = dt.date.fromisoformat(ar["invoice_date"])
            due_dt = dt.date.fromisoformat(ar["due_date"])
            term_days = ar["payment_term_days"]

            if curr_dt < inv_dt:
                continue

            days_passed = (curr_dt - inv_dt).days
            is_paid = False
            disc_taken = 0.0
            pay_reason = ""

            # Skenario A: Kios RTL Cash COD (TOP 0 hari)
            if term_days == 0 and curr_dt >= inv_dt:
                is_paid = True
                pay_reason = "Cash COD Penyerahan Barang"
            # Skenario B: Termin kredit yang memanfaatkan Cash Discount 1% (maju bayar di hari ke 5-7)
            elif term_days >= 7 and days_passed in (5, 6, 7) and (deterministic_hash(ar["invoice_number"]) % 10 < 3):
                is_paid = True
                disc_taken = round(ar["dpp_amount"] * 0.01, 2)
                pay_reason = "Early Payment Discount (Maju Bayar Cash Disc 1%)"
            # Skenario C: Pelunasan saat jatuh tempo sesuai termin master
            elif curr_dt >= due_dt:
                is_paid = True
                pay_reason = f"Pelunasan Termin Jatuh Tempo ({term_days} Hari)"

            if is_paid:
                ar["status"] = "Paid"
                net_collected_dpp = round(ar["dpp_amount"] - disc_taken, 2)
                net_collected_total = round(ar["total_with_ppn"] - disc_taken, 2)

                daily_ar_collected_dpp += net_collected_dpp
                daily_ar_collected_total += net_collected_total
                daily_early_discount_dpp += disc_taken

                ar_collections.append({
                    "payment_id": f"PAY-AR-{pay_counter:05d}",
                    "payment_date": d_str,
                    "invoice_number": ar["invoice_number"],
                    "customer": ar["customer"],
                    "channel": ar["channel"],
                    "salesman": ar["salesman"],
                    "invoice_dpp": round(ar["dpp_amount"], 2),
                    "invoice_ppn": round(ar["ppn_amount"], 2),
                    "invoice_total_with_ppn": round(ar["total_with_ppn"], 2),
                    "early_payment_discount": round(disc_taken, 2),
                    "net_cash_collected": round(net_collected_dpp, 2),
                    "net_cash_collected_total": round(net_collected_total, 2),
                    "payment_method": "Cash Tunai" if term_days == 0 else "Transfer Bank BCA/Mandiri",
                    "payment_reason": pay_reason,
                })
                pay_counter += 1

        # -------------------------------------------------------------
        # STEP 5: AP PRINCIPAL PAYMENTS
        # -------------------------------------------------------------
        daily_ap_paid = 0.0
        for ap in ap_schedule:
            if ap["status"] == "Open" and d_str == ap["pay_date"]:
                ap["status"] = "Paid"
                daily_ap_paid += ap["amount"]
                ap_payments.append({
                    "ap_payment_id": f"PAY-AP-{len(ap_payments)+1:02d}",
                    "payment_date": d_str,
                    "po_number": ap["po_number"],
                    "principal_name": ap["principal_name"],
                    "amount_paid_dpp": round(ap["amount"], 2),
                    "due_date": ap["due_date"],
                    "bank_source": "Bank Mandiri Rekening Operasional",
                })

        # -------------------------------------------------------------
        # STEP 6: OPEX HARIAN & PAYROLL BULANAN
        # -------------------------------------------------------------
        daily_routine_opex = 3_550_000.0 if is_work else 0.0
        daily_payroll_opex = 0.0

        if d_str == "2026-07-31":
            # Gaji Pokok 24 Karyawan (Rp 185 Jt)
            daily_payroll_opex += 185_000_000.0
            opex_payroll_entries.append({
                "date": d_str,
                "category": "Payroll Karyawan",
                "description": "Gaji Pokok & Tunjangan 24 Personel Roster Juli 2026",
                "amount": 185_000_000.0,
                "payment_type": "Direct Payroll Bank Transfer",
            })
            # Lembur Shift Malam Overstok (Rp 68,5 Jt)
            daily_payroll_opex += 68_500_000.0
            opex_payroll_entries.append({
                "date": d_str,
                "category": "Lembur Gudang & Logistik",
                "description": "Upah Lembur Shift Malam Bongkar Muat Overstok Kontainer Juli 2026",
                "amount": 68_500_000.0,
                "payment_type": "Direct Payroll Bank Transfer",
            })
            # Sewa Gudang Tambahan & Fasilitas Listrik (Rp 45 Jt)
            daily_payroll_opex += 45_000_000.0
            opex_payroll_entries.append({
                "date": d_str,
                "category": "Sewa & Utilitas",
                "description": "Sewa Fasilitas Pergudangan & Listrik Pendingin Juli 2026",
                "amount": 45_000_000.0,
                "payment_type": "Transfer Bank Mandiri",
            })

        if daily_routine_opex > 0:
            opex_payroll_entries.append({
                "date": d_str,
                "category": "Logistik Rutin",
                "description": f"BBM Solar 6 Armada, Uang Jalan Ritase, Tol & Retribusi Pengiriman {d_str}",
                "amount": daily_routine_opex,
                "payment_type": "Petty Cash Kasir Operasional",
            })

        total_daily_opex = daily_routine_opex + daily_payroll_opex

        # -------------------------------------------------------------
        # STEP 7: KARTU STOK HARIAN (PHYSICAL VS RESERVED VS QUARANTINE)
        # -------------------------------------------------------------
        total_physical_ctns = sum(d["physical"] for d in stock_state.values())
        total_reserved_ctns = sum(d["reserved"] for d in stock_state.values())
        total_available_ctns = total_physical_ctns - total_reserved_ctns
        total_quarantine_ctns = sum(d["quarantine"] for d in stock_state.values())

        # Valuasi fisik on-hand gudang (physical saleable + quarantine)
        total_physical_val = sum(
            d["physical"] * float(prod_map[sku]["cost_price"]) * int(prod_map[sku]["carton_qty"])
            for sku, d in stock_state.items()
        )
        total_physical_cbm = sum(
            (d["physical"] + d["quarantine"]) * float(prod_map[sku]["carton_volume_cbm"])
            for sku, d in stock_state.items()
        )
        occupancy_pct = (total_physical_cbm / 2500.0) * 100.0

        daily_stock_cards.append({
            "date": d_str,
            "day_name": day_name,
            "is_working_day": is_work,
            "inbound_lines_count": len(inbound_lines_today),
            "so_count": len([so for so in sales_orders if so["date_order"] == d_str]),
            "gross_sales_dpp": round(daily_so_gross, 2),
            "discount_dpp": round(daily_so_disc, 2),
            "net_sales_dpp": round(daily_so_net, 2),
            "cogs_dpp": round(daily_so_cogs, 2),
            "do_count": len(dispatches_today),
            "do_delivered_dpp": round(daily_do_delivered_dpp, 2),
            "rejection_dpp": round(daily_do_rejection_dpp, 2),
            "accepted_cogs_dpp": round(daily_cogs_accepted, 2),
            "rejection_cogs_dpp": round(daily_cogs_rejection, 2),
            "ar_collected": round(daily_ar_collected_dpp, 2),
            "ap_paid": round(daily_ap_paid, 2),
            "opex_paid": round(total_daily_opex, 2),
            "physical_stock_cartons": total_physical_ctns,
            "reserved_stock_cartons": total_reserved_ctns,
            "available_stock_cartons": total_available_ctns,
            "quarantine_stock_cartons": total_quarantine_ctns,
            "closing_stock_cartons": total_physical_ctns,
            "closing_stock_val_dpp": round(total_physical_val, 2),
            "closing_stock_cbm": round(total_physical_cbm, 2),
            "warehouse_occupancy_pct": round(occupancy_pct, 2),
        })

        curr_dt += dt.timedelta(days=1)

    # 4. Simpan seluruh dataset transaksi perpetual ke data/registers/
    datasets = [
        ("perpetual_sales_orders", sales_orders),
        ("perpetual_order_lines", order_lines),
        ("perpetual_deliveries", deliveries),
        ("perpetual_order_rejections", rejections),
        ("perpetual_invoices", invoices),
        ("perpetual_ar_collections", ar_collections),
        ("perpetual_ap_payments", ap_payments),
        ("perpetual_opex_payroll", opex_payroll_entries),
        ("perpetual_daily_stock_cards", daily_stock_cards),
        ("perpetual_stock_event_ledger", stock_event_ledger),
    ]

    for name, data in datasets:
        csv_file = out_dir / f"{name}.csv"
        json_file = out_dir / f"{name}.json"

        if data:
            fieldnames = list(data[0].keys())
        else:
            fieldnames = []

        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(data)

        with open(json_file, "w", newline="\n", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

        print(f"   [OK] {name}.csv & .json ({len(data):,} records)")

    print()
    print("REKONSILIASI KANONIKAL AWAL DARI ENGINE GENERATOR:")
    inv_july = [i for i in invoices if i["date_invoice"] <= "2026-07-31"]
    inv_aug = [i for i in invoices if i["date_invoice"] > "2026-07-31"]
    rej_july = [r for r in rejections if r["rejection_date"] <= "2026-07-31"]
    rej_aug = [r for r in rejections if r["rejection_date"] > "2026-07-31"]

    print(f"Total SO Booked Juli        : {len(sales_orders):,} SO (Gross Rp {sum(s['gross_dpp'] for s in sales_orders):,.2f})")
    print(f"Total Faktur Juli Terbit    : {len(inv_july):,} Faktur (Invoiced DPP Rp {sum(i['dpp_amount'] for i in inv_july):,.2f})")
    print(f"Total Retur Karantina Juli  : {len(rej_july):,} Retur (DPP Rp {sum(r['line_subtotal_dpp'] for r in rej_july):,.2f}, COGS Rp {sum(r['cogs_subtotal'] for r in rej_july):,.2f})")
    print(f"Total Carry-Forward Agustus : {len(inv_aug):,} Faktur (Invoiced DPP Rp {sum(i['dpp_amount'] for i in inv_aug):,.2f}, Retur: {len(rej_aug)})")
    print(f"Total Kas Tertagih Juli     : Rp {sum(c['net_cash_collected'] for c in ar_collections):,.2f}")
    print(f"Saldo Akhir Fisik 31 Juli   : {daily_stock_cards[-1]['physical_stock_cartons']:,} Karton (Reserved: {daily_stock_cards[-1]['reserved_stock_cartons']:,})")
    print(f"Saldo Akhir Karantina       : {daily_stock_cards[-1]['quarantine_stock_cartons']:,} Karton")
    print("=" * 85)


if __name__ == "__main__":
    main()
