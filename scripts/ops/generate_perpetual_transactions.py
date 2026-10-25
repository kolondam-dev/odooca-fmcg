#!/usr/bin/env python3
"""Granular Perpetual Inventory Turnover & Transaction Engine FMCG Manado.

Mensimulasikan seluruh rantai transaksi kausal dan deterministik:
1. Saldo Awal Fisik 1 Juli 2026 (150 SKU)
2. PO In-Transit Juni tiba 1-4 Juli di Pelabuhan Bitung & Gudang Maumbi
3. Daily Sales Order (SO) hanya atas stok ON-HAND yang ada pada jam 08:00
4. Picklist, Packlist/DO H+1, dan Invoice tercetak dengan DPP di luar PPN (PPN 11%)
5. Tidak ada angka genap/bulat buatan (berpatokan pada karton x harga satuan SKU)
6. AR Cash Collection terikat 1-ke-1 dengan invoice_number (termasuk skenario pemajuan tagihan cash discount 1%)
7. Purchasing Reorder Point saat stok menipis
8. AP Payments ke principal sesuai termin (21, 28, 30, 35 hari)
9. OPEX harian (BBM, uang jalan, tol) + Payroll Penggajian Karyawan Rp 185 Jt & Lembur di tanggal 30/31
"""

import csv
from datetime import date, datetime, timedelta
import json
import pathlib
import random

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
REG_DIR = ROOT / "data" / "registers"
SEED_DIR = ROOT / "data" / "seed"

# Seed deterministik agar transaksi 100% dapat di-reproduksi
random.seed(20260701)


def is_working_day(d: date) -> bool:
    """Senin s/d Sabtu adalah hari kerja operasional FMCG Manado."""
    if d.weekday() == 6:  # Minggu off
        return False
    holidays = [date(2026, 7, 16)]  # Tahun Baru Islam
    return d not in holidays


def main():
    print("=" * 85)
    print("GRANULAR PERPETUAL INVENTORY TURNOVER & TRANSACTION ENGINE (JULI 2026)")
    print("=" * 85)

    # 1. Muat Master Data
    with open(SEED_DIR / "products_150.csv", "r", encoding="utf-8") as f:
        products = list(csv.DictReader(f))
    prod_map = {p["default_code"]: p for p in products}

    with open(REG_DIR / "initial_stock_20260701.json", "r", encoding="utf-8") as f:
        initial_stock = json.load(f)

    with open(REG_DIR / "inbound_po_intransit_june_headers.json", "r", encoding="utf-8") as f:
        po_headers = json.load(f)

    with open(REG_DIR / "inbound_po_intransit_june_lines.json", "r", encoding="utf-8") as f:
        po_lines = json.load(f)

    with open(REG_DIR / "pjp_july_2026_matrix.csv", "r", encoding="utf-8") as f:
        pjp_matrix = list(csv.DictReader(f))

    # Inisialisasi Perpetual Stock per SKU (Karton on-hand, FIFO Lot queue)
    # stock_on_hand[sku] = { "cartons": int, "lots": [ {"lot": str, "qty": int, "cost": float, "exp": str} ] }
    stock_on_hand = {}
    for item in initial_stock:
        sku = item["sku_code"]
        stock_on_hand[sku] = {
            "cartons": item["qty_cartons_on_hand"],
            "lots": [
                {
                    "lot": item["lot_number"],
                    "qty": item["qty_cartons_on_hand"],
                    "cost": item["unit_cost_price"],
                    "exp": item["expiry_date"],
                }
            ],
        }

    # Kelompokkan PO Lines berdasarkan tanggal tiba di Gudang Maumbi
    inbound_by_date = {}
    for h in po_headers:
        arr_dt = h["arrival_maumbi_date"]
        po_num = h["po_number"]
        lines = [line for line in po_lines if line["po_number"] == po_num]
        inbound_by_date.setdefault(arr_dt, []).extend(lines)

    # Kelompokkan PJP visits per tanggal
    pjp_by_date = {}
    for row in pjp_matrix:
        if row["frekuensi_call"] in ("F1", "F2", "F4"):
            pjp_by_date.setdefault(row["tanggal"], []).append(row)

    # Struktur penampung transaksi granular
    sales_orders = []
    order_lines = []
    deliveries = []
    invoices = []
    ar_collections = []
    ap_payments = []
    daily_stock_cards = []
    opex_payroll_entries = []

    so_counter = 1
    inv_counter = 1
    do_counter = 1
    pay_counter = 1

    # Open AR Tracking: list of unpaid invoices
    # [ {"inv_no": str, "partner_name": str, "channel": str, "amount": float, "date": str, "due_date": str, "pjp_day": str, "salesman": str} ]
    open_ar_ledger = []

    # AP Tracking
    open_ap_ledger = []
    for h in po_headers:
        open_ap_ledger.append({
            "po_number": h["po_number"],
            "principal_name": h["principal_name"],
            "amount": h["total_dpp"],
            "due_date": h["due_date"],
            "pay_date": h["ap_payment_date"],
            "status": "Open",
        })

    # Simulasi 31 hari Juli 2026 (1 s/d 31 Juli)
    start_dt = date(2026, 7, 1)
    end_dt = date(2026, 7, 31)
    curr_dt = start_dt

    total_gross_july = 0.0
    total_disc_july = 0.0
    total_net_july = 0.0
    total_cogs_july = 0.0
    total_do_july = 0.0
    total_ar_collected_july = 0.0
    total_ap_paid_july = 0.0
    total_opex_july = 0.0

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
            ctns = line["qty_cartons"]
            stock_on_hand[sku]["cartons"] += ctns
            stock_on_hand[sku]["lots"].append({
                "lot": line["lot_number"],
                "qty": ctns,
                "cost": line["unit_cost_price"],
                "exp": line["expiry_date"],
            })

        # -------------------------------------------------------------
        # STEP 2: PJP SALES CALLS & STRICT ON-HAND ORDERS (08:00 - 14:00)
        # -------------------------------------------------------------
        visits_today = pjp_by_date.get(d_str, [])
        daily_so_gross = 0.0
        daily_so_disc = 0.0
        daily_so_cogs = 0.0
        daily_so_delivered = 0.0

        if is_work and visits_today:
            # Urutkan kunjungan salesman
            for visit in visits_today:
                ch = visit["channel"]
                sls = visit["salesman"]
                cust = visit["customer"]
                dist = visit["district"]
                veh = visit["delivery_vehicle"]

                # Target basket size realistis per channel untuk mencapai target Juli ~Rp 5.50 BIO
                if ch == "MT":
                    target_subtotal = random.uniform(30_000_000, 39_000_000)
                    sku_count = random.randint(8, 14)
                    disc_pct = 0.052  # 5.2% trade promo push MT Juli
                elif ch == "GT":
                    target_subtotal = random.uniform(10_500_000, 16_500_000)
                    sku_count = random.randint(5, 9)
                    disc_pct = 0.048  # 4.8% diskon taktis grosir
                elif ch == "INST":
                    target_subtotal = random.uniform(6_000_000, 10_000_000)
                    sku_count = random.randint(3, 6)
                    disc_pct = 0.040
                else:  # RTL
                    target_subtotal = random.uniform(1_800_000, 3_800_000)
                    sku_count = random.randint(2, 4)
                    disc_pct = 0.035  # 3.5% cash discount kios

                # Filter SKU yang HANYA memiliki stok ON-HAND > 0 pada hari ini!
                available_skus = [s for s, data in stock_on_hand.items() if data["cartons"] >= 2]
                if not available_skus:
                    continue

                # Pilih SKU sesuai ketersediaan stok
                selected_skus = random.sample(available_skus, min(sku_count, len(available_skus)))

                current_so_gross = 0.0
                current_so_cogs = 0.0
                current_so_lines = []

                so_num = f"SO-202607-{so_counter:04d}"
                so_counter += 1

                for sku in selected_skus:
                    p = prod_map[sku]
                    c_cost = float(p["cost_price"]) * int(p["carton_qty"])
                    c_price = float(p["list_price"]) * int(p["carton_qty"])

                    # Kuantitas karton dipesan (disesuaikan dengan sisa stok on-hand)
                    desired_ctns = max(1, int(round((target_subtotal / len(selected_skus)) / c_price)))
                    # Potong sesuai batas on-hand maksimal
                    allocated_ctns = min(desired_ctns, stock_on_hand[sku]["cartons"])
                    if allocated_ctns <= 0:
                        continue

                    # Potong stok on-hand perpetual (Strict Allocation)
                    stock_on_hand[sku]["cartons"] -= allocated_ctns

                    # Ambil FEFO lot & hitung COGS per baris
                    assigned_lot = stock_on_hand[sku]["lots"][0]["lot"] if stock_on_hand[sku]["lots"] else "LOT-DEF"

                    line_gross = allocated_ctns * c_price
                    line_cogs = allocated_ctns * c_cost

                    current_so_gross += line_gross
                    current_so_cogs += line_cogs

                    current_so_lines.append({
                        "so_number": so_num,
                        "date_order": d_str,
                        "sku_code": sku,
                        "product_name": p["name"],
                        "brand_code": p["brand_code"],
                        "fmcg_category": p["fmcg_category"],
                        "qty_cartons": allocated_ctns,
                        "carton_qty": int(p["carton_qty"]),
                        "unit_price_dpp": float(p["list_price"]),
                        "carton_price_dpp": c_price,
                        "line_subtotal_dpp": round(line_gross, 2),
                        "cogs_subtotal": round(line_cogs, 2),
                        "lot_number": assigned_lot,
                    })

                if not current_so_lines:
                    continue

                order_lines.extend(current_so_lines)

                # Hitung Diskon Faktur
                disc_amt = round(current_so_gross * disc_pct, 2)
                net_so = round(current_so_gross - disc_amt, 2)

                # Skenario Tolakan Toko (Partial Rejection / Damage Transit 1-2%)
                has_rejection = random.random() < 0.08 and ch in ("GT", "MT")
                if has_rejection:
                    # Tolak 1 karton dari baris pertama
                    rej_line = current_so_lines[0]
                    rej_amt = rej_line["carton_price_dpp"]
                    rej_cogs = float(prod_map[rej_line["sku_code"]]["cost_price"]) * rej_line["carton_qty"]
                    # Balikkan 1 karton ke stok karantina
                    stock_on_hand[rej_line["sku_code"]]["cartons"] += 1
                else:
                    rej_amt = 0.0
                    rej_cogs = 0.0

                do_delivered_amt = round(current_so_gross - rej_amt, 2)
                final_inv_dpp = round(net_so - (rej_amt * (1 - disc_pct)), 2)
                ppn_11_amt = round(final_inv_dpp * 0.11, 2)
                final_inv_total = round(final_inv_dpp + ppn_11_amt, 2)

                # Simpan Sales Order Header
                sales_orders.append({
                    "so_number": so_num,
                    "date_order": d_str,
                    "salesman": sls,
                    "customer": cust,
                    "channel": ch,
                    "district": dist,
                    "delivery_vehicle": veh,
                    "gross_dpp": round(current_so_gross, 2),
                    "discount_dpp": round(disc_amt, 2),
                    "net_dpp": round(net_so, 2),
                    "cogs_dpp": round(current_so_cogs, 2),
                    "rejection_dpp": round(rej_amt, 2),
                    "do_delivered_dpp": round(do_delivered_amt, 2),
                })

                # Simpan Packlist / Delivery Order (DO H+1)
                do_num = f"DO-202607-{do_counter:04d}"
                do_counter += 1
                deliv_date = (curr_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                deliveries.append({
                    "do_number": do_num,
                    "so_number": so_num,
                    "scheduled_delivery_date": deliv_date,
                    "delivery_vehicle": veh,
                    "customer": cust,
                    "channel": ch,
                    "do_delivered_dpp": round(do_delivered_amt, 2),
                    "rejection_reason": "Kemasan basah/penyok saat transit" if rej_amt > 0 else "-",
                })

                # Simpan Customer Invoice (Tercetak H+1 Pagi)
                inv_num = f"INV-202607-{inv_counter:04d}"
                inv_counter += 1
                top_days = 0 if ch == "RTL" else (14 if ch == "GT" else (30 if ch == "MT" else 21))
                due_date_str = (curr_dt + timedelta(days=top_days)).strftime("%Y-%m-%d")

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

                # Daftarkan ke Open AR Tracking
                open_ar_ledger.append({
                    "invoice_number": inv_num,
                    "customer": cust,
                    "channel": ch,
                    "salesman": sls,
                    "dpp_amount": final_inv_dpp,
                    "invoice_date": deliv_date,
                    "due_date": due_date_str,
                    "pjp_call_day": day_name,
                    "status": "Open",
                })

                daily_so_gross += current_so_gross
                daily_so_disc += disc_amt
                daily_so_cogs += (current_so_cogs - rej_cogs)
                daily_so_delivered += do_delivered_amt

        # -------------------------------------------------------------
        # STEP 3: AR CASH & TRANSFER COLLECTIONS (Pelunasan Piutang)
        # -------------------------------------------------------------
        # Logika Pelunasan:
        # A. Kios RTL Canvass (COD): Lunas pada hari H penyerahan
        # B. GT (TOP 7-14 hari): Ditagih saat salesman PJP datang pada hari yang sama di minggu berikutnya
        #    Skenario Pemajuan Tagihan (Cash Discount 1% 7 hari): Toko membayar maju di hari ke-5/7.
        # C. MT (TOP 21-35 hari): Lunas pada tanggal jatuh tempo.
        daily_ar_collected = 0.0
        for ar in open_ar_ledger:
            if ar["status"] != "Open":
                continue

            inv_dt = datetime.strptime(ar["invoice_date"], "%Y-%m-%d").date()
            days_passed = (curr_dt - inv_dt).days

            is_paid = False
            disc_taken = 0.0
            pay_reason = ""

            # Skenario A: Kios RTL Cash COD
            if ar["channel"] == "RTL" and days_passed >= 0:
                is_paid = True
                pay_reason = "Cash COD Salesman Canvass"
            # Skenario B: GT Pemajuan Tagihan (Hari ke 5-7 untuk dapat potongan 1%)
            elif ar["channel"] == "GT" and days_passed in (5, 6, 7) and random.random() < 0.40:
                is_paid = True
                disc_taken = round(ar["dpp_amount"] * 0.01, 2)
                pay_reason = "Early Payment Discount (Maju Bayar Cash Disc 1%)"
            # Skenario C: GT Regular Weekly Call (Hari ke 12-14 saat salesman PJP berkunjung)
            elif ar["channel"] == "GT" and days_passed >= 12 and ar["pjp_call_day"] == day_name:
                is_paid = True
                pay_reason = f"Pelunasan PJP Mingguan Salesman ({ar['salesman']})"
            # Skenario D: MT & INST Jatuh Tempo
            elif ar["channel"] in ("MT", "INST") and curr_dt >= datetime.strptime(ar["due_date"], "%Y-%m-%d").date():
                is_paid = True
                pay_reason = "Bank Batch Transfer Jatuh Tempo"

            if is_paid:
                ar["status"] = "Paid"
                net_collected = ar["dpp_amount"] - disc_taken
                daily_ar_collected += net_collected
                ar_collections.append({
                    "payment_id": f"PAY-AR-{pay_counter:05d}",
                    "payment_date": d_str,
                    "invoice_number": ar["invoice_number"],
                    "customer": ar["customer"],
                    "channel": ar["channel"],
                    "salesman": ar["salesman"],
                    "invoice_dpp": round(ar["dpp_amount"], 2),
                    "early_payment_discount": round(disc_taken, 2),
                    "net_cash_collected": round(net_collected, 2),
                    "payment_method": "Cash Tunai" if ar["channel"] == "RTL" else "Transfer Bank BCA/Mandiri",
                    "payment_note": pay_reason,
                })
                pay_counter += 1

        # -------------------------------------------------------------
        # STEP 4: PEMBAYARAN HUTANG PRINCIPAL (AP PAYMENTS)
        # -------------------------------------------------------------
        daily_ap_paid = 0.0
        for ap in open_ap_ledger:
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
        # STEP 5: OPEX HARIAN & PENGGAJIAN AKHIR BULAN (PAYROLL TGL 30/31)
        # -------------------------------------------------------------
        # Beban Harian: Solar BBM (Rp 817.000/hari) + Uang jalan ritase driver (Rp 1.200.000) + Tol/Retribusi (Rp 350.000) + M&R (Rp 1.183.000) = Rp 3.550.000/hari
        daily_routine_opex = 3_550_000.0 if is_work else 0.0

        daily_payroll_opex = 0.0
        if d_str == "2026-07-31":
            # Gaji Pokok 24 Karyawan Roster (Rp 185 Juta)
            daily_payroll_opex += 185_000_000.0
            opex_payroll_entries.append({
                "date": d_str,
                "category": "Payroll Karyawan",
                "description": "Gaji Pokok & Tunjangan 24 Personel Roster Juli 2026",
                "amount": 185_000_000.0,
                "payment_type": "Direct Payroll Bank Transfer",
            })
            # Lembur Gudang & Logistik Puncak Krisis Overstok Juli (Rp 68,5 Juta)
            daily_payroll_opex += 68_500_000.0
            opex_payroll_entries.append({
                "date": d_str,
                "category": "Lembur Gudang & Logistik",
                "description": "Upah Lembur Shift Malam Bongkar Muat Overstok Kontainer Juli 2026",
                "amount": 68_500_000.0,
                "payment_type": "Direct Payroll Bank Transfer",
            })
            # Sewa Gudang & Utilitas Listrik/Genset Juli (Rp 45 Juta)
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
        # STEP 6: KARTU STOK PERPETUAL SUMMARY HARI INI
        # -------------------------------------------------------------
        closing_stock_cartons = sum(data["cartons"] for data in stock_on_hand.values())
        closing_stock_val = sum(
            data["cartons"] * float(prod_map[sku]["cost_price"]) * int(prod_map[sku]["carton_qty"])
            for sku, data in stock_on_hand.items()
        )
        closing_stock_cbm = sum(
            data["cartons"] * float(prod_map[sku]["carton_volume_cbm"])
            for sku, data in stock_on_hand.items()
        )
        # Kapasitas racking terpasang gudang Maumbi adalah 1.200 pallet (~2.500 m³)
        warehouse_occ_pct = round((closing_stock_cbm / 2500.0) * 100.0, 1)

        daily_stock_cards.append({
            "date": d_str,
            "day_name": day_name,
            "is_working_day": is_work,
            "inbound_lines_count": len(inbound_lines_today),
            "so_count": len(visits_today) if is_work else 0,
            "gross_sales_dpp": round(daily_so_gross, 2),
            "discount_dpp": round(daily_so_disc, 2),
            "net_sales_dpp": round(daily_so_gross - daily_so_disc, 2),
            "cogs_dpp": round(daily_so_cogs, 2),
            "do_delivered_dpp": round(daily_so_delivered, 2),
            "ar_collected": round(daily_ar_collected, 2),
            "ap_paid": round(daily_ap_paid, 2),
            "opex_paid": round(total_daily_opex, 2),
            "closing_stock_cartons": closing_stock_cartons,
            "closing_stock_val_dpp": round(closing_stock_val, 2),
            "closing_stock_cbm": round(closing_stock_cbm, 2),
            "warehouse_occupancy_pct": warehouse_occ_pct,
        })

        total_gross_july += daily_so_gross
        total_disc_july += daily_so_disc
        total_net_july += (daily_so_gross - daily_so_disc)
        total_cogs_july += daily_so_cogs
        total_do_july += daily_so_delivered
        total_ar_collected_july += daily_ar_collected
        total_ap_paid_july += daily_ap_paid
        total_opex_july += total_daily_opex

        curr_dt += timedelta(days=1)

    print("\n--- REKONSILIASI AKHIR SIMULASI PERPETUAL BULAN JULI 2026 ---")
    print(f"Total Gross Sales DPP      : Rp {total_gross_july:,.2f}")
    print(f"Total Diskon Promosi DPP   : Rp {total_disc_july:,.2f}")
    print(f"Total Net Sales DPP        : Rp {total_net_july:,.2f}")
    print(f"Total COGS Persediaan DPP  : Rp {total_cogs_july:,.2f}")
    print(f"Gross Margin               : Rp {total_net_july - total_cogs_july:,.2f}")
    print(f"Total Beban OPEX & Payroll : Rp {total_opex_july:,.2f}")
    net_profit = (total_net_july - total_cogs_july) - total_opex_july
    net_margin_pct = (net_profit / total_net_july) * 100.0
    print(f"Net Profit Bersih          : Rp {net_profit:,.2f} (Net Margin: {net_margin_pct:.2f}%)")
    print(f"Total AR Cash Collected    : Rp {total_ar_collected_july:,.2f}")
    print(f"Total AP Principal Paid    : Rp {total_ap_paid_july:,.2f}")
    max_occ = max(d["warehouse_occupancy_pct"] for d in daily_stock_cards)
    print(f"Puncak Okupansi Gudang     : {max_occ:.1f}%")

    # 4. Simpan seluruh dataset transaksi perpetual ke data/registers/
    datasets = [
        ("perpetual_sales_orders", sales_orders),
        ("perpetual_order_lines", order_lines),
        ("perpetual_deliveries", deliveries),
        ("perpetual_invoices", invoices),
        ("perpetual_ar_collections", ar_collections),
        ("perpetual_ap_payments", ap_payments),
        ("perpetual_opex_payroll", opex_payroll_entries),
        ("perpetual_daily_stock_cards", daily_stock_cards),
    ]

    for filename, data in datasets:
        if not data:
            continue
        with open(REG_DIR / f"{filename}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        with open(REG_DIR / f"{filename}.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            writer.writeheader()
            writer.writerows(data)
        print(f" -> {filename}.csv tersimpan ({len(data)} records).")

    print("=" * 85)


if __name__ == "__main__":
    main()
