#!/usr/bin/env python3
"""Generator Local Day-to-Day Financial & Operational Ledger FMCG (1 Juli - 24 Okt 2026).

Menghasilkan buku besar harian presisi (day-to-day ledger):
- Inbound Purchasing (PO & Penerimaan Pelabuhan Bitung)
- Inventory & Okupansi Gudang m3
- Sales Orders, DO, Invoices, Returns (Tolakan 1-2%)
- Collections & AR Aging
- OPEX Bills (BBM, Lembur, Sewa, Gaji 25)
- AP Payables Prinsipal (ditahan bertahap di Agustus)
- Bottom-Line P&L (Gross, Diskon, COGS, Net Margin, Kas)

Semua angka DILUAR PPN sesuai arahan pemilik repo.
Hari kerja operasional: Senin s/d Sabtu (Minggu & Libur Nasional libur).
"""

import csv
from datetime import date, timedelta
import json
import pathlib
import random

ROOT = pathlib.Path(__file__).resolve().parent.parent
REG_DIR = ROOT / "data" / "registers"
REG_DIR.mkdir(parents=True, exist_ok=True)

random.seed(20260701)

# Hari Libur Resmi Nasional Juli - Oktober 2026
HOLIDAYS = [
    date(2026, 7, 16),  # Tahun Baru Islam 1448 H
    date(2026, 8, 17),  # Hari Kemerdekaan RI
    date(2026, 9, 4),  # Maulid Nabi Muhammad SAW
]

DAYS_OF_WEEK = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"]


def is_working_day(d: date) -> bool:
    if d.weekday() == 6:  # Minggu libur
        return False
    return d not in HOLIDAYS


def build_daily_ledger():
    start_date = date(2026, 7, 1)
    end_date = date(2026, 10, 24)
    all_dates = []
    curr = start_date
    while curr <= end_date:
        all_dates.append(curr)
        curr += timedelta(days=1)

    working_days = [d for d in all_dates if is_working_day(d)]
    july_workdays = [d for d in working_days if d.month == 7]
    aug_workdays = [d for d in working_days if d.month == 8]
    sept_workdays = [d for d in working_days if d.month == 9]
    oct_workdays = [d for d in working_days if d.month == 10]

    month_workdays_map = {
        7: july_workdays,
        8: aug_workdays,
        9: sept_workdays,
        10: oct_workdays,
    }

    # Target Omset Bulanan (Diluar PPN):
    target_turnover = {
        7: 5_500_000_000.0,
        8: 4_235_000_000.0,
        9: 3_960_000_000.0,
        10: 5_300_000_000.0,
    }

    # Target Diskon & Net Margin per Bulan:
    # Juli: Diskon 5.0%, Net Margin 0.90%
    # Agustus: Diskon 3.5%, Net Margin 2.50%
    # September: Diskon 3.0%, Net Margin 3.70%
    # Oktober: Diskon 2.5%, Net Margin 5.00%
    discount_rates = {7: 0.050, 8: 0.035, 9: 0.030, 10: 0.025}
    target_margins = {7: 0.0090, 8: 0.0250, 9: 0.0370, 10: 0.0500}

    # Saldo Awal per 1 Juli 2026:
    cash_balance = 850_000_000.0
    stock_value = 4_300_000_000.0  # COGS stok awal carry-over (total persediaan Juli = 4.3 + 5.7 = 10.0 BIO)
    ar_balance = 1_450_000_000.0
    ap_balance = 4_000_000_000.0

    warehouse_capacity_m3 = 3500.0  # Kapasitas gudang 3.500 m3

    # Jadwal Inbound PO (Nilai COGS):
    # 1. PO Juni (5.7 BIO): Tiba di Pelabuhan Bitung dalam 2 batch di awal Juli:
    #    - 3 Juli: Rp 3.0 BIO (inbound 1)
    #    - 10 Juli: Rp 2.7 BIO (inbound 2)
    #    -> Menjadikan total stok tersedia Juli = Rp 4.3 + Rp 5.7 = Rp 10.0 BIO (puncak overstok Juli)
    # 2. Agustus: Tidak ada kedatangan inbound (flushing stok sisa Juli hingga tersisa buffer).
    #    - 21 Agustus: Release PO Pembelian Rp 4.2 BIO (Lead time pengiriman Jawa -> Bitung 14 hari)
    # 3. September: Kedatangan PO Agustus di awal Sept & PO reguler:
    #    - 4 September: Rp 2.1 BIO (batch 1 PO Agustus)
    #    - 11 September: Rp 2.1 BIO (batch 2 PO Agustus)
    #    - 22 September: Rp 1.5 BIO (replenishment reguler)
    # 4. Oktober: Kedatangan PO Reguler:
    #    - 3 Oktober: Rp 2.5 BIO
    #    - 14 Oktober: Rp 2.5 BIO
    inbound_schedule = {
        date(2026, 7, 3): 3_000_000_000.0,
        date(2026, 7, 10): 2_700_000_000.0,
        date(2026, 9, 4): 2_100_000_000.0,
        date(2026, 9, 11): 2_100_000_000.0,
        date(2026, 9, 22): 1_500_000_000.0,
        date(2026, 10, 3): 2_500_000_000.0,
        date(2026, 10, 14): 2_500_000_000.0,
    }

    # Jadwal Pembayaran AP Terkendali (Menghindari Kas Negatif, AP sedikit ditahan di Agustus):
    ap_payment_schedule = {
        # Juli: Pembayaran AP rutin (total Rp 3.8 BIO)
        date(2026, 7, 10): 800_000_000.0,
        date(2026, 7, 17): 1_000_000_000.0,
        date(2026, 7, 24): 1_000_000_000.0,
        date(2026, 7, 31): 1_000_000_000.0,
        # Agustus: AP sedikit ditahan, dibayar bertahap sesuai arus kas masuk (total Rp 2.8 BIO)
        date(2026, 8, 7): 700_000_000.0,
        date(2026, 8, 14): 700_000_000.0,
        date(2026, 8, 21): 700_000_000.0,
        date(2026, 8, 28): 700_000_000.0,
        # September: Pembayaran AP bertahap (total Rp 3.6 BIO)
        date(2026, 9, 8): 900_000_000.0,
        date(2026, 9, 15): 900_000_000.0,
        date(2026, 9, 22): 900_000_000.0,
        date(2026, 9, 29): 900_000_000.0,
        # Oktober: Pembayaran AP lancar (total Rp 3.5 BIO)
        date(2026, 10, 6): 1_000_000_000.0,
        date(2026, 10, 13): 1_250_000_000.0,
        date(2026, 10, 20): 1_250_000_000.0,
    }

    # Antrian jatuh tempo piutang (AR collections)
    ar_due_queue = {}
    ar_due_queue[date(2026, 7, 4)] = 450_000_000.0
    ar_due_queue[date(2026, 7, 8)] = 500_000_000.0
    ar_due_queue[date(2026, 7, 13)] = 500_000_000.0

    # Hitung rata-rata penjualan per hari kerja per bulan
    daily_sales_target = {}
    for m, days in month_workdays_map.items():
        daily_sales_target[m] = target_turnover[m] / len(days)

    cumulative_sales_month = {7: 0.0, 8: 0.0, 9: 0.0, 10: 0.0}

    # Anggaran OPEX Bulanan (Rasional FMCG Distributor):
    # Juli: Rp 515 juta (tinggi: lembur, BBM darurat overstok, handling)
    # Agustus: Rp 470 juta (turun 8.7% <10% dari Juli sesuai brief)
    # September: Rp 435 juta (efisiensi berlanjut)
    # Oktober (MTD 24 hari): Rp 360 juta
    monthly_opex_budget = {7: 515_000_000.0, 8: 470_000_000.0, 9: 435_000_000.0, 10: 360_000_000.0}

    # Hitung COGS Rate per bulan agar Net Margin tercapai presisi:
    # Net_Sales = Gross * (1 - disc)
    # Net_Profit = Net_Sales * margin_rate
    # Gross_Margin = Net_Profit + OPEX
    # COGS = Net_Sales - Gross_Margin
    monthly_cogs = {}
    for m in [7, 8, 9, 10]:
        gross = target_turnover[m]
        net = gross * (1.0 - discount_rates[m])
        net_prof = net * target_margins[m]
        opex = monthly_opex_budget[m]
        gm = net_prof + opex
        cogs = net - gm
        monthly_cogs[m] = cogs

    ledger_entries = []

    for d in all_dates:
        is_work = is_working_day(d)
        m = d.month

        inbound_received = inbound_schedule.get(d, 0.0)
        ap_paid = ap_payment_schedule.get(d, 0.0)

        daily_gross_sales = 0.0
        daily_discount = 0.0
        daily_net_sales = 0.0
        daily_cogs = 0.0
        daily_do_delivered = 0.0
        daily_returns = 0.0
        daily_collections = 0.0
        daily_opex = 0.0

        # Penentuan outlet coverage aktif berdasarkan periode
        if m == 7:
            outlet_coverage_count = 177  # Baseline Juli 50%
        elif m == 8:
            outlet_coverage_count = 198  # Pertumbuhan +6% (+21)
        elif m == 9:
            outlet_coverage_count = 226  # Pertumbuhan +8% (+28)
        else:
            outlet_coverage_count = 354  # Full universe aktif

        if is_work:
            workdays_count = len(month_workdays_map[m])
            # Fluktuasi deterministik harian (+- 5%)
            day_factor = 1.0 + (((d.day * 5) % 11) - 5) * 0.01

            is_last_workday = d == month_workdays_map[m][-1]
            if is_last_workday:
                daily_gross_sales = target_turnover[m] - cumulative_sales_month[m]
            else:
                daily_gross_sales = round(daily_sales_target[m] * day_factor, -3)

            cumulative_sales_month[m] += daily_gross_sales

            disc_rate = discount_rates[m]
            daily_discount = round(daily_gross_sales * disc_rate, 2)
            daily_net_sales = round(daily_gross_sales - daily_discount, 2)

            # COGS harian dialokasikan proporsional terhadap net sales
            cogs_ratio = monthly_cogs[m] / (target_turnover[m] * (1.0 - disc_rate))
            daily_cogs = round(daily_net_sales * cogs_ratio, 2)

            # Tolakan pengiriman 1.5%
            daily_returns = round(daily_gross_sales * 0.015, 2)
            daily_do_delivered = round(daily_gross_sales - daily_returns, 2)

            # 28% Cash COD, 72% Tempo kredit
            cash_sales = round(daily_net_sales * 0.28, 2)
            credit_sales = round(daily_net_sales * 0.72, 2)
            daily_collections += cash_sales

            # Jadwal penagihan tempo (TOP 12-16 hari)
            due_d = d + timedelta(days=14)
            ar_due_queue[due_d] = ar_due_queue.get(due_d, 0.0) + credit_sales

            # Beban operasional harian (di luar gaji tgl 25)
            # Alokasikan rata-rata harian
            payroll = 145_000_000.0 if m in [7, 8, 9] else 0.0  # Okt belum tgl 25
            daily_base_opex = (monthly_opex_budget[m] - payroll) / workdays_count
            daily_opex += round(daily_base_opex, 2)

        # Penagihan piutang tempo yang jatuh tempo hari ini
        if d in ar_due_queue:
            daily_collections += ar_due_queue[d]

        # Payroll bulanan rutin setiap tanggal 25
        if d.day == 25 and m in [7, 8, 9]:
            daily_opex += 145_000_000.0

        # Update Saldo Akuntansi:
        # 1. Stock Persediaan:
        stock_value += inbound_received - (daily_cogs if is_work else 0.0)

        # 2. Kas:
        cash_balance += daily_collections - daily_opex - ap_paid

        # 3. Piutang (AR):
        if is_work:
            ar_balance += daily_net_sales - daily_collections
        else:
            ar_balance -= daily_collections

        # 4. Hutang (AP):
        ap_balance += inbound_received - ap_paid

        # Okupansi Gudang m3:
        # Pada puncaknya di 10 Juli (setelah kedatangan 5.7 BIO inbound),
        # stok barang fisik mencapai puncaknya hingga okupansi 105.2% (>100% narasi over 5%)
        occupied_cbm = round((stock_value / 8_200_000_000.0) * 3682.0, 1)
        occupancy_pct = round((occupied_cbm / warehouse_capacity_m3) * 100.0, 1)

        # Profit & Margin:
        daily_gross_margin = round(daily_net_sales - daily_cogs, 2) if is_work else 0.0
        daily_net_profit = round(daily_gross_margin - daily_opex, 2)
        net_margin_pct = round((daily_net_profit / daily_net_sales * 100.0), 2) if daily_net_sales > 0 else 0.0

        ledger_entries.append(
            {
                "date": d.isoformat(),
                "day_name": DAYS_OF_WEEK[d.weekday()] if d.weekday() < 6 else "Minggu",
                "is_working_day": is_work,
                "month": m,
                "active_outlets": outlet_coverage_count,
                "inbound_po_received": inbound_received,
                "gross_sales": daily_gross_sales,
                "discount_amount": daily_discount,
                "net_sales": daily_net_sales,
                "cogs": daily_cogs,
                "returns_tolakan": daily_returns,
                "do_delivered": daily_do_delivered,
                "collections_ar": round(daily_collections, 2),
                "opex_bills_paid": round(daily_opex, 2),
                "ap_principal_paid": ap_paid,
                "gross_margin": daily_gross_margin,
                "net_profit": daily_net_profit,
                "net_margin_pct": net_margin_pct,
                "closing_stock_value": round(stock_value, 2),
                "warehouse_occupancy_cbm": occupied_cbm,
                "warehouse_occupancy_pct": occupancy_pct,
                "closing_cash_balance": round(cash_balance, 2),
                "closing_ar_balance": round(ar_balance, 2),
                "closing_ap_balance": round(ap_balance, 2),
            }
        )

    return ledger_entries


def main():
    print("Menyusun Calibrated Day-to-Day Financial & Operational Ledger FMCG...")
    entries = build_daily_ledger()
    json_path = REG_DIR / "historical_ledger_day_to_day.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
    print(f" -> {json_path} tersimpan ({len(entries)} hari).")

    csv_path = REG_DIR / "historical_ledger_day_to_day.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(entries[0].keys()))
        writer.writeheader()
        writer.writerows(entries)
    print(f" -> {csv_path} tersimpan.")


if __name__ == "__main__":
    main()
