#!/usr/bin/env python3
"""Generator Simulasi Transaksi Historis FMCG Manado (1 Juli 2026 s/d 24 Oktober 2026).

Menghasilkan dataset transaksi harian deterministik dan realistis:
1. Inbound PO & Kontainer Pelabuhan Bitung (FEFO Lot & AP Payments)
2. Daily Granular Sales Orders & Invoices (~3.800 transaksi harian riil)
3. Detail Line Items Produk & Karton
4. OPEX Vendor Bills (Lembur, BBM, Perawatan Armada, Gaji, Sewa)
5. Metrik Harian Okupansi Gudang & Utilisasi 9 Armada Logistik
6. Ringkasan Rekonsiliasi Finansial P&L dan Cashflow (Semua nilai DILUAR PPN)
"""

import csv
from datetime import date, datetime, timedelta
import json
import pathlib
import random

ROOT = pathlib.Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "data" / "seed"
SEED_DIR.mkdir(parents=True, exist_ok=True)

# Set seed deterministik
random.seed(20260701)


def is_working_day(d: date) -> bool:
    """Senin s/d Sabtu (Minggu libur). Libur nasional resmi diabaikan untuk operasional khusus."""
    # 6 is Sunday
    if d.weekday() == 6:
        return False
    # Libur nasional resmi
    holidays = [
        date(2026, 7, 16),  # Tahun Baru Islam
        date(2026, 8, 17),  # HUT RI
        date(2026, 9, 4),  # Maulid Nabi
    ]
    return d not in holidays


def get_working_days(start_date: date, end_date: date) -> list[date]:
    """Mengembalikan daftar hari kerja operasional."""
    days = []
    curr = start_date
    while curr <= end_date:
        if is_working_day(curr):
            days.append(curr)
        curr += timedelta(days=1)
    return days


def load_master_seed():
    """Memuat master produk dan outlet dari file CSV yang sudah ada."""
    products = []
    with open(SEED_DIR / "products_150.csv", mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            products.append(
                {
                    "default_code": row["default_code"],
                    "name": row["name"],
                    "principal_code": row["principal_code"],
                    "fmcg_category": row["fmcg_category"],
                    "cost_price": float(row["cost_price"]),
                    "list_price": float(row["list_price"]),
                    "weight_kg": float(row["weight_kg"]),
                    "volume_cbm": float(row["volume_cbm"]),
                    "carton_qty": int(row["carton_qty"]),
                }
            )

    partners = []
    with open(SEED_DIR / "partners_354.csv", mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            partners.append(
                {
                    "ref": row["ref"],
                    "name": row["name"],
                    "channel_code": row["channel_code"],
                    "tier_code": row.get("tier_code", ""),
                    "district_code": row["district_code"],
                    "payment_term_days": int(row["payment_term_days"]),
                    "salesman_code": row["salesman_code"],
                }
            )

    vehicles = []
    with open(SEED_DIR / "vehicles_9.csv", mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for v_idx, row in enumerate(reader, start=1):
            vehicles.append(
                {
                    "code": f"VH-{v_idx:02d}",
                    "plate": row["plate"],
                    "type": row["type"],
                    "cbm": float(row["cbm"]),
                    "ton": float(row["ton"]),
                    "route": row["route"],
                }
            )

    return products, partners, vehicles


def generate_inbound_po_dataset(products: list[dict]) -> tuple[list[dict], list[dict]]:
    """Menghasilkan Inbound PO & Penerimaan Kontainer di Pelabuhan Bitung serta AP Bills."""
    po_records = []
    po_lines = []

    # Skenario Inbound:
    # 1. PO Juni (Masuk 28 Juni - 3 Juli): Total Rp 5.750.000.000 (14 Kontainer)
    #    AP: Rp 4.0B JT Juli, Rp 2.75B JT 25-31 Juli, Rp 2.75B JT 1-10 Agustus (total komitmen Rp 9.5B)
    # 2. Agustus: ZERO INBOUND (Flushing Mode).
    #    Release PO Week 3 (18 Agustus): Rp 3.200.000.000. Tiba 2-4 September.
    # 3. September: PO 18 Agt tiba (Rp 3.2B). Release PO September (15 September) Rp 3.6B (tiba akhir Sept/awal Okt).
    # 4. Oktober: Tiba Rp 3.6B. Release PO 10 Oktober Rp 4.5B.

    shipments = [
        # --- PO JUNI (Tiba Akhir Juni / Awal Juli) ---
        (
            "PO-2026-06-01",
            "PRIN-WINGS",
            "2026-06-15",
            "2026-06-28",
            "2026-07-01",
            1850000000,
            21,
            "2026-07-15",
            "2026-07-15",
            "FCL-20FT-01",
        ),
        (
            "PO-2026-06-02",
            "PRIN-KAPALAPI",
            "2026-06-12",
            "2026-06-27",
            "2026-07-01",
            1450000000,
            28,
            "2026-07-20",
            "2026-07-20",
            "FCL-20FT-02",
        ),
        (
            "PO-2026-06-03",
            "PRIN-MAYORA",
            "2026-06-10",
            "2026-06-29",
            "2026-07-02",
            700000000,
            30,
            "2026-07-25",
            "2026-07-25",
            "FCL-20FT-03",
        ),
        (
            "PO-2026-06-04",
            "PRIN-MAYORA",
            "2026-06-20",
            "2026-07-01",
            "2026-07-03",
            2600000000,
            30,
            "2026-07-31",
            "2026-07-30",
            "FCL-40FT-04",
        ),
        (
            "PO-2026-06-05",
            "PRIN-UNILEVER",
            "2026-06-18",
            "2026-07-02",
            "2026-07-04",
            2900000000,
            35,
            "2026-08-08",
            "2026-08-07",
            "FCL-40FT-05",
        ),
        # --- AGUSTUS: ZERO INBOUND (Hanya PO Release di Week 3) ---
        # Tiba September:
        (
            "PO-2026-08-01",
            "PRIN-MAYORA",
            "2026-08-18",
            "2026-09-01",
            "2026-09-03",
            1800000000,
            30,
            "2026-09-30",
            "2026-09-29",
            "FCL-40FT-06",
        ),
        (
            "PO-2026-08-02",
            "PRIN-KAPALAPI",
            "2026-08-18",
            "2026-08-30",
            "2026-09-02",
            1400000000,
            28,
            "2026-09-28",
            "2026-09-28",
            "FCL-20FT-07",
        ),
        # --- SEPTEMBER: Inbound Tiba & PO Release Baru ---
        (
            "PO-2026-09-01",
            "PRIN-WINGS",
            "2026-09-15",
            "2026-09-27",
            "2026-09-29",
            1600000000,
            21,
            "2026-10-10",
            "2026-10-09",
            "FCL-20FT-08",
        ),
        (
            "PO-2026-09-02",
            "PRIN-UNILEVER",
            "2026-09-15",
            "2026-09-30",
            "2026-10-02",
            2000000000,
            35,
            "2026-10-25",
            "2026-10-24",
            "FCL-40FT-09",
        ),
        # --- OKTOBER: Inbound Berjalan & PO Baru Q4 ---
        (
            "PO-2026-10-01",
            "PRIN-MAYORA",
            "2026-10-10",
            "2026-10-23",
            "2026-10-24",
            2500000000,
            30,
            "2026-11-15",
            "Unpaid",
            "FCL-40FT-10",
        ),
        (
            "PO-2026-10-02",
            "PRIN-KAPALAPI",
            "2026-10-12",
            "2026-10-24",
            "2026-10-24",
            2000000000,
            28,
            "2026-11-12",
            "Unpaid",
            "FCL-20FT-11",
        ),
    ]

    for po_num, prin_code, order_dt, eta, rcv_dt, total_amt, top_days, due_dt, pay_dt, cont in shipments:
        po_records.append(
            {
                "po_number": po_num,
                "principal_code": prin_code,
                "order_date": order_dt,
                "eta_bitung": eta,
                "receive_date": rcv_dt,
                "container_no": cont,
                "total_dpp": total_amt,
                "payment_term_days": top_days,
                "due_date": due_dt,
                "payment_date": pay_dt,
                "ap_status": "Paid" if pay_dt != "Unpaid" else "Open",
            }
        )

        # Generate sample lines per PO
        prin_prods = [p for p in products if p["principal_code"] == prin_code]
        remaining = total_amt
        for idx, p in enumerate(prin_prods[:8]):
            line_val = total_amt // min(8, len(prin_prods))
            cartons = int(line_val // (p["cost_price"] * p["carton_qty"]))
            if cartons < 10:
                cartons = 50
            actual_subtotal = cartons * p["cost_price"] * p["carton_qty"]
            lot_exp = (datetime.strptime(rcv_dt, "%Y-%m-%d") + timedelta(days=540)).strftime("%Y-%m-%d")
            po_lines.append(
                {
                    "po_number": po_num,
                    "sku_code": p["default_code"],
                    "qty_cartons": cartons,
                    "unit_cost_price": p["cost_price"],
                    "subtotal_dpp": actual_subtotal,
                    "lot_number": f"LOT-{prin_code[-3:]}-{rcv_dt.replace('-', '')}-{idx:02d}",
                    "expiry_date": lot_exp,
                }
            )
            remaining -= actual_subtotal

    return po_records, po_lines


def generate_sales_and_logistics(
    working_days: list[date],
    products: list[dict],
    partners: list[dict],
    vehicles: list[dict],
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Menghasilkan transaksi penjualan harian (~3.800 transaksi), line items, OPEX, dan metrik logistik."""
    sales_orders = []
    order_lines = []
    opex_bills = []
    logistics_metrics = []

    # Pembagian Outlet Coverage:
    # Baseline Juli: 272 outlet (12 MT, 60 GT, 192 RTL, 8 INST)
    # Agustus (+6%): 288 outlet (12 MT, 64 GT, 203 RTL, 9 INST)
    # September (+8%): 313 outlet (12 MT, 68 GT, 223 RTL, 10 INST)
    # Oktober: 354 outlet (12 MT, 72 GT, 260 RTL, 10 INST)
    mt_list = [p for p in partners if p["channel_code"] == "MT"]
    gt_list = [p for p in partners if p["channel_code"] == "GT"]
    rtl_list = [p for p in partners if p["channel_code"] == "RTL"]
    inst_list = [p for p in partners if p["channel_code"] == "INST"]

    # Target Omset DPP Bulanan:
    # Juli (26 hari): Rp 5.500.000.000 (Rata-rata Rp 211.538.461/hari)
    # Agustus (25 hari): Rp 4.235.000.000 (Rata-rata Rp 169.400.000/hari)
    # September (25 hari): Rp 3.960.000.000 (Rata-rata Rp 158.400.000/hari)
    # Oktober MTD (22 hari): Rp 5.300.000.000 (Rata-rata Rp 240.909.091/hari)

    so_counter = 1

    for d in working_days:
        m_str = d.strftime("%Y-%m")
        day_str = d.strftime("%Y-%m-%d")

        # Tentukan target harian & parameter bulanan
        if m_str == "2026-07":
            day_target = 211538461 * random.uniform(0.85, 1.15)
            # Push order di akhir Juli lebih tinggi
            if d.day >= 24:
                day_target *= 1.35
            avg_discount = 0.050  # 5% suntikan diskon taktis
            active_outlets = mt_list + gt_list[:60] + rtl_list[:192] + inst_list[:8]
            rejection_rate = 0.038  # 3.8% tolakan karena gudang luber & picking error
            cogs_ratio = 0.892
            wh_pallets = 1260  # 105% rated capacity
            wh_visual_pct = 195  # 2x lipat visual
            fleet_util_pct = 95  # armada kerja rodi
        elif m_str == "2026-08":
            day_target = 169400000 * random.uniform(0.88, 1.12)
            avg_discount = 0.025  # diskon dinormalisasi ke 2.5%
            active_outlets = mt_list + gt_list[:64] + rtl_list[:203] + inst_list[:9]
            rejection_rate = 0.024  # 2.4% tolakan
            cogs_ratio = 0.888
            wh_pallets = int(1260 - ((d.day / 31.0) * 350))  # Flushing stok turun ke ~910
            wh_visual_pct = int(195 - ((d.day / 31.0) * 80))
            fleet_util_pct = 76
        elif m_str == "2026-09":
            day_target = 158400000 * random.uniform(0.90, 1.10)
            avg_discount = 0.020  # disiplin katalog 2.0%
            active_outlets = mt_list + gt_list[:68] + rtl_list[:223] + inst_list[:10]
            rejection_rate = 0.018  # 1.8% tolakan
            cogs_ratio = 0.885
            wh_pallets = 880  # Stabil teratur
            wh_visual_pct = 105
            fleet_util_pct = 78
        else:  # 2026-10
            day_target = 240909091 * random.uniform(0.92, 1.10)
            avg_discount = 0.020  # disiplin katalog 2.0%
            active_outlets = partners  # Semua 354 outlet aktif
            rejection_rate = 0.008  # 0.8% tolakan minor
            cogs_ratio = 0.875
            wh_pallets = 1060  # Penuh sehat di rack
            wh_visual_pct = 110
            fleet_util_pct = 89  # Sinyal kritis 89% kapasitas armada

        # Pilih outlet harian sesuai PJP (sekitar 35-42 kunjungan per hari)
        # MT dapat kunjungan 2x seminggu, GT 2x seminggu, RTL 1x seminggu
        daily_tx_count = random.randint(36, 42)
        sampled_partners = random.sample(active_outlets, min(daily_tx_count, len(active_outlets)))

        # Alokasi nominal per outlet
        current_day_total = 0.0
        daily_cartons = 0
        daily_tonnage = 0.0

        for p in sampled_partners:
            ch = p["channel_code"]
            # Proporsi order berdasarkan channel
            if ch == "MT":
                # Push order ekstrem di Juli
                base_amt = (
                    random.uniform(25000000, 55000000) if m_str == "2026-07" else random.uniform(15000000, 32000000)
                )
            elif ch == "GT":
                base_amt = (
                    random.uniform(6000000, 18000000) if m_str == "2026-07" else random.uniform(4000000, 12000000)
                )
            elif ch == "INST":
                base_amt = random.uniform(3000000, 8000000)
            else:  # RTL
                base_amt = random.uniform(450000, 1850000)

            gross_amt = base_amt
            disc_pct = avg_discount * random.uniform(0.9, 1.1)
            disc_amt = gross_amt * disc_pct
            net_amt = gross_amt - disc_amt
            cogs_amt = net_amt * cogs_ratio
            gross_margin = net_amt - cogs_amt

            # Tolakan pengiriman
            is_rejected = random.random() < rejection_rate
            rejection_amt = 0.0
            rejection_reason = ""
            if is_rejected:
                rejection_pct = random.uniform(0.15, 0.40)  # parsial
                rejection_amt = net_amt * rejection_pct
                if m_str == "2026-07":
                    rejection_reason = random.choice(
                        [
                            "Gudang outlet penuh sesak (overstok)",
                            "Salah varian kemasan akibat lorong gudang padat",
                            "Retur lama belum dipotong pada faktur",
                        ]
                    )
                elif m_str == "2026-08":
                    rejection_reason = random.choice(
                        [
                            "Outlet kekurangan uang tunai saat COD",
                            "Toko tutup sementara (acara keluarga)",
                        ]
                    )
                else:
                    rejection_reason = random.choice(
                        [
                            "Kemasan karton penyok di perjalanan luar kota",
                            "Retur produk rusak belum selesai verifikasi",
                        ]
                    )

            final_billed = net_amt - rejection_amt

            # Termin & Pembayaran
            top = p["payment_term_days"]
            due_dt = d + timedelta(days=top)
            # Pelunasan
            if top == 0:
                pay_dt = day_str  # Cash COD
                pay_status = "Paid"
            else:
                # MT & GT pelunasan berkisar pada jatuh tempo +/- 3 hari
                actual_pay_dt = due_dt + timedelta(days=random.randint(-2, 5))
                if actual_pay_dt <= date(2026, 10, 24):
                    pay_dt = actual_pay_dt.strftime("%Y-%m-%d")
                    pay_status = "Paid"
                else:
                    pay_dt = "Unpaid"
                    pay_status = "Open"

            # Pilih armada penugasan
            if ch == "MT":
                veh = vehicles[7] if "Bitung" in p["name"] else vehicles[8]  # CDD / CDDL
            elif ch == "GT":
                veh = vehicles[5] if "Tomohon" in p["name"] else vehicles[3]  # CDE / L300
            elif ch == "INST":
                veh = vehicles[4]  # Traga
            else:  # RTL
                veh = vehicles[0] if "Urban" in p["district_code"] else vehicles[1]  # Gran Max BV / Box

            so_code = f"SO-2026-{so_counter:05d}"
            inv_code = f"INV-2026-{so_counter:05d}"
            so_counter += 1

            sales_orders.append(
                {
                    "so_number": so_code,
                    "invoice_number": inv_code,
                    "date_order": day_str,
                    "date_invoice": day_str,
                    "partner_ref": p["ref"],
                    "salesman_code": p["salesman_code"],
                    "channel_code": ch,
                    "district_code": p["district_code"],
                    "gross_amount_dpp": round(gross_amt, 2),
                    "discount_pct": round(disc_pct * 100, 2),
                    "discount_amount": round(disc_amt, 2),
                    "net_amount_dpp": round(net_amt, 2),
                    "cogs_amount": round(cogs_amt, 2),
                    "gross_margin": round(gross_margin, 2),
                    "delivery_vehicle": veh["code"],
                    "delivery_status": "Delivered" if not is_rejected else "Partial Rejected",
                    "rejection_reason": rejection_reason,
                    "rejection_amount": round(rejection_amt, 2),
                    "final_billed_amount": round(final_billed, 2),
                    "payment_term_days": top,
                    "due_date": due_dt.strftime("%Y-%m-%d"),
                    "payment_date": pay_dt,
                    "payment_status": pay_status,
                }
            )

            # Line items (2-4 SKU per faktur)
            num_lines = random.randint(2, 4) if ch in ["GT", "MT"] else 2
            sampled_prods = random.sample(products, num_lines)
            for prod in sampled_prods:
                line_val = final_billed / num_lines
                ctn = max(1, int(line_val // (prod["list_price"] * prod["carton_qty"])))
                unit_price = prod["list_price"]
                line_net = ctn * unit_price * prod["carton_qty"]
                order_lines.append(
                    {
                        "so_number": so_code,
                        "sku_code": prod["default_code"],
                        "qty_carton": ctn,
                        "unit_price_dpp": unit_price,
                        "subtotal_dpp": round(line_net, 2),
                        "lot_number": f"LOT-{prod['principal_code'][-3:]}-20260701-01",
                    }
                )
                daily_cartons += ctn
                daily_tonnage += (ctn * prod["weight_kg"] * prod["carton_qty"]) / 1000.0

            current_day_total += final_billed

        # Catat metrik logistik harian
        logistics_metrics.append(
            {
                "date": day_str,
                "working_day_index": len(logistics_metrics) + 1,
                "daily_revenue_dpp": round(current_day_total, 2),
                "daily_orders_count": len(sampled_partners),
                "daily_cartons_delivered": daily_cartons,
                "daily_tonnage_delivered": round(daily_tonnage, 2),
                "warehouse_pallets_occupied": wh_pallets,
                "warehouse_occupancy_rated_pct": round((wh_pallets / 1200.0) * 100, 1),
                "warehouse_visual_occupancy_pct": wh_visual_pct,
                "fleet_average_utilization_pct": fleet_util_pct,
                "rejection_rate_pct": round(rejection_rate * 100, 1),
            }
        )

    # Buat OPEX Vendor Bills Bulanan
    # Sesuai tabel di Cetak Biru:
    # Juli: Rp 544.500.000 (Net margin 0.9%)
    # Agustus: Rp 368.445.000 (Net margin 2.5%)
    # September: Rp 308.780.000 (Net margin 3.7%)
    # Oktober MTD: Rp 397.500.000 (Net margin 5.0%)
    opex_schedule = [
        ("2026-07-31", "Gaji Pokok & Tunjangan Karyawan Juli 2026", "VEND-PAYROLL", 185000000),
        ("2026-07-31", "Lembur Gudang & Logistik Juli 2026 (Krisis Overstok)", "VEND-PAYROLL", 68500000),
        ("2026-07-31", "BBM & Tol Armada 9 Kendaraan Juli 2026", "VEND-SPBU", 92400000),
        ("2026-07-31", "Pemeliharaan & Bengkel Armada 9 Unit Juli 2026", "VEND-BENGKEL", 34600000),
        ("2026-07-31", "Sewa Gudang, Listrik, Depresiasi Juli 2026", "VEND-ESTATE", 164000000),
        ("2026-08-31", "Gaji Pokok & Tunjangan Karyawan Agustus 2026", "VEND-PAYROLL", 185000000),
        ("2026-08-31", "Lembur Gudang & Logistik Agustus 2026 (Penurunan 73%)", "VEND-PAYROLL", 18200000),
        ("2026-08-31", "BBM & Tol Armada 9 Kendaraan Agustus 2026", "VEND-SPBU", 62800000),
        ("2026-08-31", "Pemeliharaan & Servis Rutin Armada Agustus 2026", "VEND-BENGKEL", 18500000),
        ("2026-08-31", "Sewa Gudang, Listrik, Depresiasi Agustus 2026", "VEND-ESTATE", 83945000),
        ("2026-09-30", "Gaji Pokok & Tunjangan Karyawan September 2026", "VEND-PAYROLL", 185000000),
        ("2026-09-30", "Lembur Gudang & Logistik September 2026", "VEND-PAYROLL", 14500000),
        ("2026-09-30", "BBM & Tol Armada 9 Kendaraan September 2026", "VEND-SPBU", 56400000),
        ("2026-09-30", "Pemeliharaan & Servis Rutin Armada September 2026", "VEND-BENGKEL", 16200000),
        ("2026-09-30", "Sewa Gudang, Listrik, Depresiasi September 2026", "VEND-ESTATE", 36680000),
        ("2026-10-24", "Gaji Pokok Pradana Karyawan Oktober 2026 MTD", "VEND-PAYROLL", 165000000),
        ("2026-10-24", "Lembur Gudang & Logistik Oktober 2026 MTD", "VEND-PAYROLL", 19800000),
        ("2026-10-24", "BBM & Tol Armada 9 Kendaraan Oktober 2026 MTD", "VEND-SPBU", 78200000),
        ("2026-10-24", "Pemeliharaan & Ban Armada 9 Unit Oktober 2026 MTD", "VEND-BENGKEL", 22400000),
        ("2026-10-24", "Sewa Gudang, Listrik, Depresiasi Oktober 2026 MTD", "VEND-ESTATE", 112100000),
    ]

    for b_idx, (b_date, desc, vend, amt) in enumerate(opex_schedule, start=1):
        opex_bills.append(
            {
                "bill_number": f"BILL-OPEX-2026-{b_idx:03d}",
                "bill_date": b_date,
                "vendor_code": vend,
                "description": desc,
                "amount_dpp": amt,
                "due_date": b_date,
                "payment_status": "Paid",
            }
        )

    # Kalibrasi presisi bulanan sesuai target blueprint narasi
    targets = {
        "2026-07": 5500000000.0,
        "2026-08": 4235000000.0,
        "2026-09": 3960000000.0,
        "2026-10": 5300000000.0,
    }
    cogs_ratios = {
        "2026-07": 4906000000.0 / 5500000000.0,
        "2026-08": 3760680000.0 / 4235000000.0,
        "2026-09": 3504700000.0 / 3960000000.0,
        "2026-10": 4637500000.0 / 5300000000.0,
    }

    so_scale_map = {}
    for m, target in targets.items():
        m_orders = [so for so in sales_orders if so["date_order"].startswith(m)]
        curr_total = sum(so["final_billed_amount"] for so in m_orders)
        if curr_total > 0:
            scale = target / curr_total
            for so in m_orders:
                so_scale_map[so["so_number"]] = scale
                so["gross_amount_dpp"] = round(so["gross_amount_dpp"] * scale, 2)
                so["discount_amount"] = round(so["discount_amount"] * scale, 2)
                so["net_amount_dpp"] = round(so["net_amount_dpp"] * scale, 2)
                so["rejection_amount"] = round(so["rejection_amount"] * scale, 2)
                so["final_billed_amount"] = round(so["final_billed_amount"] * scale, 2)
                so["cogs_amount"] = round(so["final_billed_amount"] * cogs_ratios[m], 2)
                so["gross_margin"] = round(so["final_billed_amount"] - so["cogs_amount"], 2)

    for line in order_lines:
        sc = so_scale_map.get(line["so_number"], 1.0)
        line["subtotal_dpp"] = round(line["subtotal_dpp"] * sc, 2)
        line["qty_carton"] = max(1, int(round(line["qty_carton"] * sc)))

    return sales_orders, order_lines, opex_bills, logistics_metrics


def main():
    print("Mempersiapkan Simulasi Transaksi Historis FMCG Manado (Juli - 24 Okt 2026)...")
    products, partners, vehicles = load_master_seed()
    print(f" -> Master data terverifikasi: {len(products)} SKU, {len(partners)} Outlets, {len(vehicles)} Armada.")

    working_days = get_working_days(date(2026, 7, 1), date(2026, 10, 24))
    print(f" -> Teridentifikasi {len(working_days)} hari kerja operasional (Senin-Sabtu di luar libur resmi).")

    # 1. Inbound POs
    po_records, po_lines = generate_inbound_po_dataset(products)
    print(f" -> Menghasilkan {len(po_records)} Inbound POs & Kontainer Bitung...")

    # 2. Sales Orders & Logistics
    sales_orders, order_lines, opex_bills, logistics_metrics = generate_sales_and_logistics(
        working_days, products, partners, vehicles
    )
    print(f" -> Menghasilkan {len(sales_orders)} transaksi Sales Order harian riil...")
    print(f" -> Menghasilkan {len(order_lines)} detail line item produk...")
    print(f" -> Menghasilkan {len(opex_bills)} OPEX Vendor Bills...")
    print(f" -> Menghasilkan {len(logistics_metrics)} catatan metrik logistik & gudang harian...")

    # Tulis CSV files
    # 1. Inbound POs
    with open(SEED_DIR / "inbound_po_historical.csv", mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=po_records[0].keys())
        writer.writeheader()
        writer.writerows(po_records)

    # 2. Inbound PO Lines
    with open(SEED_DIR / "inbound_po_lines_historical.csv", mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=po_lines[0].keys())
        writer.writeheader()
        writer.writerows(po_lines)

    # 3. Sales Orders
    with open(SEED_DIR / "sales_orders_historical.csv", mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sales_orders[0].keys())
        writer.writeheader()
        writer.writerows(sales_orders)

    # 4. Sales Order Lines
    with open(SEED_DIR / "sales_order_lines_historical.csv", mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=order_lines[0].keys())
        writer.writeheader()
        writer.writerows(order_lines)

    # 5. OPEX Vendor Bills
    with open(SEED_DIR / "opex_vendor_bills.csv", mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=opex_bills[0].keys())
        writer.writeheader()
        writer.writerows(opex_bills)

    # 6. Logistics Metrics
    with open(SEED_DIR / "daily_logistics_metrics.csv", mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=logistics_metrics[0].keys())
        writer.writeheader()
        writer.writerows(logistics_metrics)

    # 7. Summary JSON
    tot_revenue = sum(so["final_billed_amount"] for so in sales_orders)
    tot_cogs = sum(so["cogs_amount"] for so in sales_orders)
    tot_opex = sum(b["amount_dpp"] for b in opex_bills)
    tot_net_profit = tot_revenue - tot_cogs - tot_opex

    summary = {
        "simulation_period": "2026-07-01 to 2026-10-24",
        "working_days": len(working_days),
        "total_sales_transactions": len(sales_orders),
        "total_revenue_dpp": round(tot_revenue, 2),
        "total_cogs_dpp": round(tot_cogs, 2),
        "gross_margin_dpp": round(tot_revenue - tot_cogs, 2),
        "total_opex_dpp": round(tot_opex, 2),
        "net_profit_dpp": round(tot_net_profit, 2),
        "overall_net_margin_pct": round((tot_net_profit / tot_revenue) * 100, 2),
        "monthly_net_revenue": {
            "2026-07": round(
                sum(so["final_billed_amount"] for so in sales_orders if so["date_order"].startswith("2026-07")), 2
            ),
            "2026-08": round(
                sum(so["final_billed_amount"] for so in sales_orders if so["date_order"].startswith("2026-08")), 2
            ),
            "2026-09": round(
                sum(so["final_billed_amount"] for so in sales_orders if so["date_order"].startswith("2026-09")), 2
            ),
            "2026-10_mtd": round(
                sum(so["final_billed_amount"] for so in sales_orders if so["date_order"].startswith("2026-10")), 2
            ),
        },
    }
    with open(SEED_DIR / "historical_simulation_summary.json", mode="w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("Selesai! Seluruh berkas simulasi transaksi historis tersimpan di data/seed/.")


if __name__ == "__main__":
    main()
