#!/usr/bin/env python3
"""Analisis Komprehensif Rasio Finansial & Logistik PJP Bulan Juli 2026 (PT MDU Manado).

Menghitung:
1. Rasio Omset per Call (Drop Size per Visit) per Channel & Total
2. Rasio Omset per Customer (Monthly Spend per Customer / ARPU)
3. Estimasi KM Delivery (Jarak Tempuh Armada H+1 dari Gudang Maumbi)
4. Struktur Biaya Delivery (BBM vs Non-BBM: Tunjangan Trip, Tol/Retribusi, M&R, KIR/Pajak, Depresiasi)
"""

import csv
import math
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
REG_DIR = ROOT / "data" / "registers"

# Koordinat Gudang Pusat PT Manado Distribusi Utama (Interchange Maumbi, Minahasa Utara)
WH_LAT = 1.442500
WH_LNG = 124.975500

# Total Target Omset Juli 2026 (Gross diluar PPN)
TOTAL_REVENUE_JULY = 5_500_000_000.0  # Rp 5.5 BIO


def haversine_km(lat1, lon1, lat2, lon2):
    """Menghitung jarak Haversine (lingkaran besar) antar dua titik koordinat."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def main():
    pjp_file = REG_DIR / "pjp_july_2026_matrix.csv"
    with open(pjp_file, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Saring hanya baris call kunjungan aktif
    call_rows = [r for r in rows if r["frekuensi_call"] in ("F1", "F2", "F4")]

    # 1. Distribusi Kontribusi Omset per Channel (Berdasarkan bobot volume Juli)
    # MT: 32% (Rp 1.76 BIO), GT: 50% (Rp 2.75 BIO), RTL: 15% (Rp 0.825 BIO), INST: 3% (Rp 0.165 BIO)
    channel_revenue = {
        "MT": TOTAL_REVENUE_JULY * 0.320,    # Rp 1,760,000,000
        "GT": TOTAL_REVENUE_JULY * 0.500,    # Rp 2,750,000,000
        "RTL": TOTAL_REVENUE_JULY * 0.150,   # Rp   825,000,000
        "INST": TOTAL_REVENUE_JULY * 0.030,  # Rp   165,000,000
    }

    # Hitung jumlah call dan jumlah customer unik per channel
    calls_per_ch = defaultdict(int)
    custs_per_ch = defaultdict(set)
    for r in call_rows:
        ch = r["channel"]
        calls_per_ch[ch] += 1
        custs_per_ch[ch].add(r["customer"].split(" - ")[0])

    print("=" * 80)
    print("ANALISIS RASIO OMSET & CALL PJP BULAN JULI 2026 (PT MANADO DISTRIBUSI UTAMA)")
    print("=" * 80)
    print(f"Total Omset Juli 2026: Rp {TOTAL_REVENUE_JULY:,.2f}")
    print(f"Total Call Kunjungan : {len(call_rows)} call (27 hari kerja operasional)\n")

    print("-" * 80)
    print(f"{'Channel':<8} | {'Revenue (IDR)':<18} | {'Calls':<6} | {'Drop/Call (IDR)':<16} | {'Cust':<5} | {'Spend/Cust/Bln':<18}")
    print("-" * 80)

    total_unique_custs = set()
    for ch in ["MT", "GT", "RTL", "INST"]:
        rev = channel_revenue[ch]
        n_calls = calls_per_ch[ch]
        drop_per_call = rev / n_calls if n_calls else 0
        n_cust = len(custs_per_ch[ch])
        total_unique_custs.update(custs_per_ch[ch])
        spend_per_cust = rev / n_cust if n_cust else 0
        print(f"{ch:<8} | Rp {rev:>14,.0f} | {n_calls:>5} | Rp {drop_per_call:>12,.0f} | {n_cust:>4} | Rp {spend_per_cust:>14,.0f}")

    print("-" * 80)
    avg_drop_all = TOTAL_REVENUE_JULY / len(call_rows)
    avg_spend_all = TOTAL_REVENUE_JULY / len(total_unique_custs)
    print(f"{'TOTAL':<8} | Rp {TOTAL_REVENUE_JULY:>14,.0f} | {len(call_rows):>5} | Rp {avg_drop_all:>12,.0f} | {len(total_unique_custs):>4} | Rp {avg_spend_all:>14,.0f}\n")

    # 2. Analisis Logistik & KM Delivery H+1
    # Kelompokkan titik pengiriman per tanggal delivery dan per rute kendaraan
    # Faktor belokan jalan (tortuosity factor) Manado-Minahasa adalah 1.35x dari garis lurus Haversine
    TORTUOSITY = 1.35

    delivery_trips = defaultdict(list)
    for r in call_rows:
        deliv_date = r["delivery_date"]
        vehicle = r["delivery_vehicle"]
        lat = float(r["latitude"])
        lng = float(r["longitude"])
        delivery_trips[(deliv_date, vehicle)].append((lat, lng, r["district"], r["customer"]))

    total_km_july = 0.0
    trip_records = []

    for (d_date, veh), stops in delivery_trips.items():
        if not stops:
            continue
        # Urutkan stops berdasarkan jarak terdekat (TSP greedy approximation sederhana)
        curr_lat, curr_lng = WH_LAT, WH_LNG
        trip_km = 0.0
        remaining = list(stops)
        while remaining:
            # Cari stop terdekat dari posisi saat ini
            best_idx = 0
            best_dist = 999999.0
            for i, (slat, slng, _, _) in enumerate(remaining):
                d = haversine_km(curr_lat, curr_lng, slat, slng)
                if d < best_dist:
                    best_dist = d
                    best_idx = i
            target = remaining.pop(best_idx)
            trip_km += best_dist * TORTUOSITY
            curr_lat, curr_lng = target[0], target[1]

        # Kembali ke Gudang Maumbi
        trip_km += haversine_km(curr_lat, curr_lng, WH_LAT, WH_LNG) * TORTUOSITY
        # Tambahkan jarak manuver lokal antar lorong toko (+10%)
        trip_km *= 1.10
        total_km_july += trip_km
        trip_records.append((d_date, veh, trip_km, len(stops)))

    avg_km_per_day = total_km_july / 27.0
    avg_km_per_trip = total_km_july / len(trip_records) if trip_records else 0

    print("=" * 80)
    print("ANALISIS JARAK TEMPUH PENGIRIMAN (KM DELIVERY H+1)")
    print("=" * 80)
    print("Titik Staging / Hub       : Pergudangan Interchange Maumbi (Minahasa Utara)")
    print(f"Total Trip Pengiriman    : {len(trip_records)} trip armada")
    print(f"Total KM Tempuh Juli     : {total_km_july:,.1f} KM (27 hari kerja operasional)")
    print(f"Rata-rata KM per Hari    : {avg_km_per_day:,.1f} KM / hari kerja (gabungan armada)")
    print(f"Rata-rata KM per Trip    : {avg_km_per_trip:,.1f} KM / trip armada\n")

    # 3. Potensi Struktur Biaya Pengiriman (BBM vs Non-BBM)
    # Standar rasio armada logistik FMCG Manado & Sulawesi Utara:
    # Konsumsi BBM Solar rata-rata armada gabungan (CDD, L300, Gran Max): ~7.5 km/liter
    # Harga Solar industri / dexlite rata-rata 2026: Rp 14.500 / liter
    liters_solar = total_km_july / 7.5
    cost_bbm = liters_solar * 14500.0

    # NON-BBM Delivery Cost Components:
    # a. Uang Jalan / Insentif Ritase Driver & Helper (Rp 75.000 / trip L300/Granmax, Rp 120.000 / trip CDD/Elf)
    cost_insentif_ritase = len(trip_records) * 85_000.0

    # b. Tol Manado-Bitung & Retribusi Parkir / Bongkar Muat Pasar
    # Tol Manado-Bitung (Airmadidi-Danowudu PP ~Rp 50.000), karcis retribusi pasar (Rp 5.000 - 10.000 per toko GT)
    cost_tol_retribusi = (len(trip_records) * 25_000.0) + (len(call_rows) * 3_500.0)

    # c. Maintenance & Repair (Ban, Oli Mesin, Gardan, Kampas Rem) ~Rp 650 / KM
    cost_maintenance = total_km_july * 650.0

    # d. Depresiasi Box Kargo & Kendaraan (Alokasi bulanan 9 armada ~Rp 32.5 Juta/bln)
    cost_depresiasi_fleet = 32_500_000.0

    # e. Uji KIR, Pajak STNK, Izin Trayek Komersial Dishub (Alokasi bulanan ~Rp 4.5 Juta/bln)
    cost_kir_pajak = 4_500_000.0

    # f. Risiko Kerusakan Transit / Bad Stock In-Transit Packaging Defect (0.15% dari Gross)
    cost_transit_loss = TOTAL_REVENUE_JULY * 0.0015

    total_non_bbm = (
        cost_insentif_ritase
        + cost_tol_retribusi
        + cost_maintenance
        + cost_depresiasi_fleet
        + cost_kir_pajak
        + cost_transit_loss
    )
    total_delivery_cost = cost_bbm + total_non_bbm

    pct_delivery_to_sales = (total_delivery_cost / TOTAL_REVENUE_JULY) * 100.0
    pct_bbm_of_deliv = (cost_bbm / total_delivery_cost) * 100.0
    pct_non_bbm_of_deliv = (total_non_bbm / total_delivery_cost) * 100.0

    print("=" * 80)
    print("STRUKTUR BIAYA DELIVERY (BBM VS POTENSI NON-BBM)")
    print("=" * 80)
    print("1. Biaya Bahan Bakar (BBM Solar / Dexlite):")
    print(f"   - Konsumsi Solar : {liters_solar:,.0f} Liter (rasio 7.5 km/l)")
    print(f"   - Nominal BBM    : Rp {cost_bbm:>14,.2f} ({pct_bbm_of_deliv:5.1f}% dari total cost)\n")

    print("2. Potensi Biaya Non-BBM (Operational & Maintenance Logistics):")
    print(f"   a. Insentif Ritase & Uang Jalan Crew (Driver+Helper) : Rp {cost_insentif_ritase:>14,.2f}")
    print(f"   b. Tol Manado-Bitung & Retribusi Bongkar Pasar 45/Tmh: Rp {cost_tol_retribusi:>14,.2f}")
    print(f"   c. Maintenance, Ban, Rem, & Pelumas (Rp 650/km)      : Rp {cost_maintenance:>14,.2f}")
    print(f"   d. Depresiasi Armada & Box Kargo Pendingin/Dry       : Rp {cost_depresiasi_fleet:>14,.2f}")
    print(f"   e. Uji KIR, STNK, Izin Bongkar Dishub Komersial       : Rp {cost_kir_pajak:>14,.2f}")
    print(f"   f. Risiko Kerusakan Transit / Bad Stock (0.15% Gross): Rp {cost_transit_loss:>14,.2f}")
    print("   " + "-" * 70)
    print(f"   Subtotal Biaya Non-BBM                               : Rp {total_non_bbm:>14,.2f} ({pct_non_bbm_of_deliv:5.1f}%)\n")

    print(f"TOTAL BIAYA DELIVERY BULAN JULI 2026                    : Rp {total_delivery_cost:>14,.2f}")
    print(f"Rasio Biaya Pengiriman terhadap Omset (Freight-to-Sales): {pct_delivery_to_sales:.2f}% (Sehat di FMCG Sulut ~2.0% - 3.5%)")
    print(f"Biaya Pengiriman per Kunjungan Call (Cost per Call)    : Rp {total_delivery_cost / len(call_rows):,.0f} / call")
    print(f"Biaya Pengiriman per KM Tempuh (Cost per KM)           : Rp {total_delivery_cost / total_km_july:,.0f} / KM")
    print("=" * 80)


if __name__ == "__main__":
    main()
