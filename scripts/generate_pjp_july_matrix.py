#!/usr/bin/env python3
"""Generator Tabel Matrix PJP (Permanent Journey Plan) Bulan Juli 2026 Lengkap.

Menghasilkan jadwal matriks kunjungan harian seluruh salesman (1 Juli - 31 Juli 2026):
- SLS-01 (Christian Wowor - Modern Trade Key Account)
- SLS-02 (Andre Pangemanan - General Trade Urban Manado Barat/Pusat)
- SLS-03 (Meidy Wowor - General Trade Urban Manado Timur/Utara)
- SLS-04 (Refly Sondakh - General Trade Luar Kota / Hinterland)
- CVS-01 (Novry Mandagi - Retail Canvass Kios Wilayah 1)
- CVS-02 (Steven Lumenta - Retail Canvass Kios Wilayah 2)
- MGT-01 (Hendrik Polii & Management - Institusional Horeka)

Kolom:
salesman, tanggal, hari, frekuensi_call, channel, area, district, customer,
latitude, longitude, delivery_date, delivery_vehicle
"""

import csv
import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.ops.fmcg_calendar import get_next_working_day, is_working_day  # noqa: E402

REG_DIR = ROOT / "data" / "registers"
REG_DIR.mkdir(parents=True, exist_ok=True)

# Nama hari bahasa Indonesia
DAY_NAMES = {
    0: "Senin",
    1: "Selasa",
    2: "Rabu",
    3: "Kamis",
    4: "Jumat",
    5: "Sabtu",
    6: "Minggu",
}

SALESMEN = [
    ("SLS-01", "Christian Wowor", "Modern Trade (MT)"),
    ("SLS-02", "Andre Pangemanan", "General Trade (GT Urban 1)"),
    ("SLS-03", "Meidy Wowor", "General Trade (GT Urban 2)"),
    ("SLS-04", "Refly Sondakh", "General Trade (GT Outer Sulut)"),
    ("CVS-01", "Novry Mandagi", "Retail Canvass (RTL Kios Area 1)"),
    ("CVS-02", "Steven Lumenta", "Retail Canvass (RTL Kios Area 2)"),
    ("MGT-01", "Hendrik Polii & Joni Kumajas", "Institusional & Key Horeka (INST)"),
]


get_delivery_date = get_next_working_day


def determine_week_of_month(d: dt.date) -> int:
    """Menentukan minggu kalender ke berapa di bulan Juli:
    Minggu 1: 1 - 4 Juli
    Minggu 2: 5 - 11 Juli
    Minggu 3: 12 - 18 Juli
    Minggu 4: 19 - 25 Juli
    Minggu 5: 26 - 31 Juli
    """
    day = d.day
    if day <= 4:
        return 1
    elif day <= 11:
        return 2
    elif day <= 18:
        return 3
    elif day <= 25:
        return 4
    else:
        return 5


def main():
    reg_file = REG_DIR / "customer_registry_354.json"
    with open(reg_file, "r", encoding="utf-8") as f:
        customers = json.load(f)

    # Indeks pelanggan per salesman dan hari call
    cust_map = {}
    for c in customers:
        sls = c["salesman_code"]
        cday = c["pjp_call_day"]
        cust_map.setdefault(sls, {}).setdefault(cday, []).append(c)

    # Periode Juli 2026: 1 Juli s/d 31 Juli (31 hari kalender)
    start_date = dt.date(2026, 7, 1)
    end_date = dt.date(2026, 7, 31)

    matrix_rows = []

    curr_date = start_date
    while curr_date <= end_date:
        w_idx = curr_date.weekday()
        day_name = DAY_NAMES[w_idx]
        is_work = is_working_day(curr_date)
        week_num = determine_week_of_month(curr_date)
        date_str = curr_date.strftime("%Y-%m-%d")

        if not is_work:
            reason = "LIBUR OPERASIONAL (MINGGU)" if w_idx == 6 else "LIBUR OPERASIONAL (TAHUN BARU ISLAM 1448 H)"
            for sls_code, sls_name, sls_role in SALESMEN:
                salesman_label = f"{sls_code} - {sls_name}"
                matrix_rows.append(
                    {
                        "salesman": salesman_label,
                        "salesman_role": sls_role,
                        "tanggal": date_str,
                        "hari": day_name,
                        "frekuensi_call": "OFF",
                        "channel": "-",
                        "area": "-",
                        "district": "-",
                        "customer": reason,
                        "latitude": "-",
                        "longitude": "-",
                        "delivery_date": "-",
                        "delivery_vehicle": "-",
                    }
                )
            curr_date += dt.timedelta(days=1)
            continue

        for sls_code, sls_name, sls_role in SALESMEN:
            salesman_label = f"{sls_code} - {sls_name}"
            # Ambil seluruh outlet kandidat untuk hari ini
            day_candidates = cust_map.get(sls_code, {}).get(day_name, [])

            # Saring berdasarkan siklus frekuensi:
            # F1: Muncul setiap minggu
            # F2: Muncul 2 minggu sekali (Genap vs Ganjil)
            # F4: Muncul 1 bulan sekali (pada week_num yang sesuai)
            scheduled_calls = []
            for idx, c in enumerate(day_candidates):
                if c.get("cohort_date") and date_str < c["cohort_date"]:
                    continue
                freq = c["pjp_frequency"]
                include = False

                if freq == "F1":
                    include = True
                elif freq == "F2":
                    sub_cycle = idx % 2
                    if sub_cycle == 0 and week_num in (1, 3, 5):
                        include = True
                    elif sub_cycle == 1 and week_num in (2, 4):
                        include = True
                elif freq == "F4":
                    target_week = (idx % 4) + 1
                    if week_num == target_week:
                        include = True

                if include:
                    scheduled_calls.append(c)

            # Jika tidak ada jadwal call spesifik pada hari kerja tersebut (misal standby)
            if not scheduled_calls:
                matrix_rows.append(
                    {
                        "salesman": salesman_label,
                        "salesman_role": sls_role,
                        "tanggal": date_str,
                        "hari": day_name,
                        "frekuensi_call": "STANDBY",
                        "channel": "-",
                        "area": "Kantor PT MDU Maumbi",
                        "district": "Kalawat / Airmadidi",
                        "customer": "ADMIN / STAGING LOGISTIK",
                        "latitude": "1.442000",
                        "longitude": "124.975000",
                        "delivery_date": "-",
                        "delivery_vehicle": "-",
                    }
                )
            else:
                deliv_date = get_delivery_date(curr_date).strftime("%Y-%m-%d")
                for c in scheduled_calls:
                    matrix_rows.append(
                        {
                            "salesman": salesman_label,
                            "salesman_role": sls_role,
                            "tanggal": date_str,
                            "hari": day_name,
                            "frekuensi_call": c["pjp_frequency"],
                            "channel": c["channel_code"],
                            "area": c["city"],
                            "district": c["district_name"],
                            "customer": f"{c['ref']} - {c['name']}",
                            "latitude": f"{c['latitude']:.6f}",
                            "longitude": f"{c['longitude']:.6f}",
                            "delivery_date": deliv_date,
                            "delivery_vehicle": c["delivery_vehicle"],
                        }
                    )

        curr_date += dt.timedelta(days=1)

    out_csv = REG_DIR / "pjp_july_2026_matrix.csv"
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "salesman",
            "salesman_role",
            "tanggal",
            "hari",
            "frekuensi_call",
            "channel",
            "area",
            "district",
            "customer",
            "latitude",
            "longitude",
            "delivery_date",
            "delivery_vehicle",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matrix_rows)

    print(f"Sukses menghasilkan PJP Matrix Juli 2026: {out_csv}")
    print(f"Total baris matrix: {len(matrix_rows)} baris.")

    # Statistik ringkasan
    call_rows = [r for r in matrix_rows if r["frekuensi_call"] in ("F1", "F2", "F4")]
    print(f"Total kunjungan call efektif di bulan Juli: {len(call_rows)} call.")


if __name__ == "__main__":
    main()
