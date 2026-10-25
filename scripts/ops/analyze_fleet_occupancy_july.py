#!/usr/bin/env python3
"""Analisis Okupansi Harian Armada Logistik (Kubikasi & Tonase) Bulan Juli 2026.

Menghitung per hari kerja dan rata-rata bulanan:
1. Beban muatan harian (Volume m³ dan Berat Ton) per armada
2. Persentase Okupansi Kubikasi (CBM Occupancy %)
3. Persentase Okupansi Tonase (Tonnage Occupancy %)
4. Analisis Batasan Muatan (Space-Constrained vs Weight-Constrained) khas FMCG
"""

import csv
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
REG_DIR = ROOT / "data" / "registers"
SEED_DIR = ROOT / "data" / "seed"

# Data Armada Outbound Aktif (Plat, Tipe, Model, CBM Box, Tonase Max)
FLEET = {
    "DB 8345 MK": {
        "model": "Canter CDD 6-Roda Box",
        "role": "Modern Trade & Grosir Pareto",
        "cbm_max": 17.2,
        "ton_max": 6.0,
    },
    "DB 8456 FB": {
        "model": "L300 Box Euro 4",
        "role": "Delivery Urban Barat (Wenang/Sario/Mly/Wna)",
        "cbm_max": 5.4,
        "ton_max": 1.5,
    },
    "DB 8567 TR": {
        "model": "Isuzu Traga Box Euro 4",
        "role": "Delivery Urban Timur (Tkl/Pld/Tmt/Skl/Mpg)",
        "cbm_max": 6.1,
        "ton_max": 1.8,
    },
    "DB 8910 TK": {
        "model": "Isuzu Elf CDE 4-Roda Box",
        "role": "Delivery Luar Kota (Tomohon/Tondano/Kwg)",
        "cbm_max": 10.0,
        "ton_max": 3.5,
    },
    "DB 8123 QA": {
        "model": "Daihatsu Gran Max Blind Van",
        "role": "Canvass CVS-01 Kios Urban",
        "cbm_max": 3.6,
        "ton_max": 0.75,
    },
    "DB 8234 QX": {
        "model": "Daihatsu Gran Max Box 1.5",
        "role": "Canvass CVS-02 Kios Sub-Urban",
        "cbm_max": 4.7,
        "ton_max": 1.0,
    },
}


def main():
    pjp_file = REG_DIR / "pjp_july_2026_matrix.csv"
    with open(pjp_file, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Rasio fisik rata-rata SKU FMCG:
    # 1 Juta Rupiah omset ~ 3.47 karton ~ 0.129 m³ ~ 23.2 kg (0.0232 ton)
    CBM_PER_MILLION = 0.1290
    TON_PER_MILLION = 0.0232

    # Revenue per channel di Juli 2026
    REV_PER_CALL = {
        "MT": 32_592_593.0,
        "GT": 12_222_222.0,
        "RTL": 2_391_304.0,
        "INST": 7_173_913.0,
    }

    # Kelompokkan call aktif per hari delivery (H+1) dan per armada
    calls_by_day_veh = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["frekuensi_call"] not in ("F1", "F2", "F4"):
            continue
        deliv_date = r["delivery_date"]
        veh_str = r["delivery_vehicle"]

        # Cocokkan nomor plat
        plate = None
        for p in FLEET.keys():
            if p in veh_str:
                plate = p
                break
        if not plate:
            # Fallback jika Traga / L300 alternatif
            if "Urban Timur" in veh_str or "Tuminting" in r["district"]:
                plate = "DB 8567 TR"
            else:
                plate = "DB 8456 FB"

        calls_by_day_veh[deliv_date][plate].append(r)

    print("=" * 95)
    print("ANALISIS OKUPANSI KUBIKASI (CBM) & TONASE PER ARMADA PER HARI (JULI 2026)")
    print("=" * 95)
    print(f"{'Plat Armada':<12} | {'Model Kendaraan':<24} | {'Drops/Hr':<8} | {'Kapasitas':<14} | {'Muatan Harian':<16} | {'Okupansi CBM':<12} | {'Okupansi Ton':<12}")
    print("-" * 105)

    fleet_summary = defaultdict(lambda: {"cbm": [], "ton": [], "trips": 0, "drops": []})

    for d_date, plates in sorted(calls_by_day_veh.items()):
        for plate, c_list in plates.items():
            tot_rev = sum(REV_PER_CALL.get(c["channel"], 5_000_000.0) for c in c_list)
            # Hitung kubikasi dan tonase
            tot_cbm = (tot_rev / 1_000_000.0) * CBM_PER_MILLION
            tot_ton = (tot_rev / 1_000_000.0) * TON_PER_MILLION

            fleet_summary[plate]["cbm"].append(tot_cbm)
            fleet_summary[plate]["ton"].append(tot_ton)
            fleet_summary[plate]["trips"] += 1
            fleet_summary[plate]["drops"].append(len(c_list))

    for plate, info in FLEET.items():
        stats = fleet_summary[plate]
        cbm_cap = info["cbm_max"]
        ton_cap = info["ton_max"]

        if stats["cbm"]:
            avg_cbm = sum(stats["cbm"]) / len(stats["cbm"])
            avg_ton = sum(stats["ton"]) / len(stats["ton"])
            avg_drops = sum(stats["drops"]) / len(stats["drops"])
            occ_cbm_pct = (avg_cbm / cbm_cap) * 100.0
            occ_ton_pct = (avg_ton / ton_cap) * 100.0
        else:
            avg_cbm, avg_ton, avg_drops = 0.0, 0.0, 0.0
            occ_cbm_pct, occ_ton_pct = 0.0, 0.0

        cap_str = f"{cbm_cap:4.1f}m³/{ton_cap:3.1f}T"
        load_str = f"{avg_cbm:4.1f}m³/{avg_ton:3.1f}T"
        drops_str = f"{avg_drops:4.1f}"

        print(f"{plate:<12} | {info['model']:<24} | {drops_str:<8} | {cap_str:<14} | {load_str:<16} | {occ_cbm_pct:>10.1f}% | {occ_ton_pct:>10.1f}%")

    print("=" * 105)

    # Cetak sampel beban harian pada hari sibuk (misal 2 Juli 2026)
    sample_date = "2026-07-02"
    print(f"\nDETAIL BEBAN ANGKUT PENGIRIMAN H+1 PADA TANGGAL SAMPEL: {sample_date}")
    print("-" * 95)
    print(f"{'Plat':<12} | {'Rute / Wilayah':<30} | {'Outlet':<8} | {'Omset Kirim':<16} | {'CBM (% Occ)':<15} | {'Ton (% Occ)':<15}")
    print("-" * 95)

    sample_plates = calls_by_day_veh.get(sample_date, {})
    for plate, c_list in sample_plates.items():
        info = FLEET[plate]
        tot_rev = sum(REV_PER_CALL.get(c["channel"], 5_000_000.0) for c in c_list)
        cbm = (tot_rev / 1_000_000.0) * CBM_PER_MILLION
        ton = (tot_rev / 1_000_000.0) * TON_PER_MILLION
        cbm_pct = (cbm / info["cbm_max"]) * 100.0
        ton_pct = (ton / info["ton_max"]) * 100.0
        rev_str = f"Rp {tot_rev:,.0f}"
        cbm_str = f"{cbm:.1f}m³ ({cbm_pct:.0f}%)"
        ton_str = f"{ton:.2f}T ({ton_pct:.0f}%)"
        print(f"{plate:<12} | {info['role']:<30} | {len(c_list):<8} | {rev_str:<16} | {cbm_str:<15} | {ton_str:<15}")

    print("-" * 95)


if __name__ == "__main__":
    main()
