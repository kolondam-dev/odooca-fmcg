#!/usr/bin/env python3
"""Generator Master Customer Registry & PJP Schedule untuk FMCG Manado & Sulut.

Menghasilkan:
1. data/registers/customer_registry_354.json & .csv (Register master customer lengkap)
2. data/registers/pjp_schedule_354.json & .csv (Jadwal rute kunjungan PJP terstruktur)
3. Memperbarui data/seed/partners_354.csv dengan alamat dan koordinat presisi.
"""

import csv
import json
import pathlib
import random

ROOT = pathlib.Path(__file__).resolve().parent.parent
REG_DIR = ROOT / "data" / "registers"
SEED_DIR = ROOT / "data" / "seed"
REG_DIR.mkdir(parents=True, exist_ok=True)
SEED_DIR.mkdir(parents=True, exist_ok=True)

random.seed(20260701)

# Koordinat dasar koridor jalan darat tiap kecamatan (terestrial, anti-drowning, anti-gunung)
DISTRICT_MASTER = {
    "KEC-MND-WNG": {
        "name": "Wenang",
        "city": "Kota Manado",
        "subdist": "KEL-MND-CLC",
        "subdist_name": "Calaca",
        "zip": "95121",
        "lat": 1.496746,
        "lng": 124.842834,
        "street": "Jl. Sam Ratulangi / Calaca",
        "kode_kemendagri": "71.71.04",
        "subdist_kemendagri": "71.71.04.1008",
    },
    "KEC-MND-SRO": {
        "name": "Sario",
        "city": "Kota Manado",
        "subdist": "KEL-MND-SKB",
        "subdist_name": "Sario Kotabaru",
        "zip": "95113",
        "lat": 1.473254,
        "lng": 124.834766,
        "street": "Jl. Sam Ratulangi Sario",
        "kode_kemendagri": "71.71.06",
        "subdist_kemendagri": "71.71.06.1001",
    },
    "KEC-MND-MLY": {
        "name": "Malalayang",
        "city": "Kota Manado",
        "subdist": "KEL-MND-BAH",
        "subdist_name": "Bahu",
        "zip": "95115",
        "lat": 1.455761,
        "lng": 124.825362,
        "street": "Jl. Wolter Monginsidi Bahu",
        "kode_kemendagri": "71.71.09",
        "subdist_kemendagri": "71.71.09.1002",
    },
    "KEC-MND-WNA": {
        "name": "Wanea",
        "city": "Kota Manado",
        "subdist": "KEL-MND-PKW",
        "subdist_name": "Pakowa",
        "zip": "95119",
        "lat": 1.484260,
        "lng": 124.833992,
        "street": "Jl. Sam Ratulangi Wanea",
        "kode_kemendagri": "71.71.07",
        "subdist_kemendagri": "71.71.07.1006",
    },
    "KEC-MND-TKL": {
        "name": "Tikala",
        "city": "Kota Manado",
        "subdist": "KEL-MND-TKB",
        "subdist_name": "Tikala Baru",
        "zip": "95126",
        "lat": 1.476822,
        "lng": 124.858722,
        "street": "Jl. Tikala Ares",
        "kode_kemendagri": "71.71.05",
        "subdist_kemendagri": "71.71.05.1008",
    },
    "KEC-MND-PLD": {
        "name": "Paal Dua",
        "city": "Kota Manado",
        "subdist": "KEL-MND-PLD",
        "subdist_name": "Paal Dua",
        "zip": "95129",
        "lat": 1.485462,
        "lng": 124.876639,
        "street": "Jl. Yos Sudarso Paal Dua",
        "kode_kemendagri": "71.71.11",
        "subdist_kemendagri": "71.71.11.1003",
    },
    "KEC-MND-TMT": {
        "name": "Tuminting",
        "city": "Kota Manado",
        "subdist": "KEL-MND-TMT",
        "subdist_name": "Tuminting",
        "zip": "95239",
        "lat": 1.511663,
        "lng": 124.852055,
        "street": "Jl. Hasanuddin Tuminting",
        "kode_kemendagri": "71.71.02",
        "subdist_kemendagri": "71.71.02.1001",
    },
    "KEC-MND-SKL": {
        "name": "Singkil",
        "city": "Kota Manado",
        "subdist": "KEL-MND-KRM",
        "subdist_name": "Karame",
        "zip": "95231",
        "lat": 1.505081,
        "lng": 124.861446,
        "street": "Jl. Singkil Karame",
        "kode_kemendagri": "71.71.03",
        "subdist_kemendagri": "71.71.03.1002",
    },
    "KEC-MND-MPG": {
        "name": "Mapanget",
        "city": "Kota Manado",
        "subdist": "KEL-MND-PKB",
        "subdist_name": "Paniki Bawah",
        "zip": "95256",
        "lat": 1.517818,
        "lng": 124.905102,
        "street": "Jl. AA Maramis Paniki",
        "kode_kemendagri": "71.71.08",
        "subdist_kemendagri": "71.71.08.1001",
    },
    "KEC-BTG-MAS": {
        "name": "Maesa",
        "city": "Kota Bitung",
        "subdist": "KEL-BTG-BTM",
        "subdist_name": "Bitung Timur",
        "zip": "95521",
        "lat": 1.456776,
        "lng": 125.188108,
        "street": "Kompleks Pasar Tua Maesa",
        "kode_kemendagri": "71.72.07",
        "subdist_kemendagri": "71.72.07.1001",
    },
    "KEC-BTG-MDR": {
        "name": "Madidir",
        "city": "Kota Bitung",
        "subdist": "KEL-BTG-MDU",
        "subdist_name": "Madidir Ure",
        "zip": "95531",
        "lat": 1.450674,
        "lng": 125.160930,
        "street": "Jl. Wolter Monginsidi Madidir",
        "kode_kemendagri": "71.72.02",
        "subdist_kemendagri": "71.72.02.1001",
    },
    "KEC-BTG-GRN": {
        "name": "Girian",
        "city": "Kota Bitung",
        "subdist": "KEL-BTG-GRW",
        "subdist_name": "Girian Weru",
        "zip": "95541",
        "lat": 1.449474,
        "lng": 125.132163,
        "street": "Jl. Manado-Bitung Girian",
        "kode_kemendagri": "71.72.06",
        "subdist_kemendagri": "71.72.06.1001",
    },
    "KEC-BTG-ATB": {
        "name": "Aertembaga",
        "city": "Kota Bitung",
        "subdist": "KEL-BTG-ATB",
        "subdist_name": "Aertembaga Satu",
        "zip": "95524",
        "lat": 1.489889,
        "lng": 125.206728,
        "street": "Jl. Pelabuhan Samudera Aertembaga",
        "kode_kemendagri": "71.72.04",
        "subdist_kemendagri": "71.72.04.1001",
    },
    "KEC-TMH-TGH": {
        "name": "Tomohon Tengah",
        "city": "Kota Tomohon",
        "subdist": "KEL-TMH-PSL",
        "subdist_name": "Paslaten Satu",
        "zip": "95446",
        "lat": 1.320825,
        "lng": 124.833702,
        "street": "Pasar Beriman Paslaten",
        "kode_kemendagri": "71.73.02",
        "subdist_kemendagri": "71.73.02.1001",
    },
    "KEC-MNH-TDN": {
        "name": "Tondano Barat",
        "city": "Kab. Minahasa",
        "subdist": "KEL-MNH-RNG",
        "subdist_name": "Roong",
        "zip": "95617",
        "lat": 1.261181,
        "lng": 124.891521,
        "street": "Jl. Sam Ratulangi Tondano",
        "kode_kemendagri": "71.02.01",
        "subdist_kemendagri": "71.02.01.1009",
    },
    "KEC-MNH-KWG": {
        "name": "Kawangkoan",
        "city": "Kab. Minahasa",
        "subdist": "KEL-MNH-SDG",
        "subdist_name": "Sendangan",
        "zip": "95690",
        "lat": 1.202694,
        "lng": 124.780301,
        "street": "Pasar Kawangkoan Sendangan",
        "kode_kemendagri": "71.02.12",
        "subdist_kemendagri": "71.02.12.1005",
    },
    "KEC-MNT-AMD": {
        "name": "Airmadidi",
        "city": "Kab. Minahasa Utara",
        "subdist": "KEL-MNT-AMA",
        "subdist_name": "Airmadidi Atas",
        "zip": "95371",
        "lat": 1.435948,
        "lng": 124.997710,
        "street": "Jl. Raya Manado-Bitung Airmadidi",
        "kode_kemendagri": "71.06.03",
        "subdist_kemendagri": "71.06.03.1008",
    },
    "KEC-MNS-AMR": {
        "name": "Amurang",
        "city": "Kab. Minahasa Selatan",
        "subdist": "KEL-MNS-BYG",
        "subdist_name": "Buyungon",
        "zip": "95954",
        "lat": 1.145596,
        "lng": 124.588270,
        "street": "Jl. Trans Sulawesi Amurang",
        "kode_kemendagri": "71.05.10",
        "subdist_kemendagri": "71.05.10.1004",
    },
}

DAYS_OF_WEEK = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"]


def generate_all_customers():
    customers = []

    # 1. MODERN TRADE (12 Outlets) - SLS-01 (Christian Wowor)
    # F1 (Weekly) - Visit day assigned
    mt_defs = [
        ("Indomarett DC Manado", "KEC-MND-MPG", "Jl. AA Maramis KM 10 Paniki", "Senin", 250000000, 45),
        ("Alfamiddii DC Manado", "KEC-MND-MPG", "Kawasan Pergudangan Kairagi Dua", "Senin", 200000000, 45),
        ("FreshhMart Superstore Bahu", "KEC-MND-MLY", "Bahu Mall Blok A No. 1", "Selasa", 120000000, 30),
        ("FreshhMart Lifestyle Paniki", "KEC-MND-MPG", "Grand Kawanua City Walk", "Rabu", 80000000, 30),
        ("FreshhMart Express Tikala", "KEC-MND-TKL", "Jl. Balai Kota No. 12", "Kamis", 50000000, 30),
        ("MultiiMart Megamas Manado", "KEC-MND-WNG", "Kawasan Megamas Blok 1D", "Jumat", 100000000, 30),
        ("MultiiMart Sam Ratulangi", "KEC-MND-WNA", "Jl. Sam Ratulangi No. 188", "Sabtu", 75000000, 30),
        ("MultiiMart Tomohon", "KEC-TMH-TGH", "Jl. Raya Tomohon-Manado Paslaten", "Rabu", 50000000, 30),
        ("Goldenn Swalayan Pasar 45", "KEC-MND-WNG", "Jl. Sam Ratulangi No. 12 Calaca", "Selasa", 80000000, 14),
        ("Jumbbo Swalayan Pasar 45", "KEC-MND-WNG", "Kawasan Pasar 45 Manado", "Kamis", 50000000, 14),
        ("Jumbbo Swalayan Bitung", "KEC-BTG-MAS", "Jl. Sam Ratulangi Bitung Timur", "Jumat", 40000000, 14),
        ("Tranzmart Star Square Bahu", "KEC-MND-MLY", "Star Square Mall Bahu", "Sabtu", 40000000, 45),
    ]

    for idx, (name, dist_code, street, call_day, cl, pt) in enumerate(mt_defs, start=1):
        dm = DISTRICT_MASTER[dist_code]
        d_lat = (((idx * 3) % 7) - 3) * 0.0003
        d_lng = (((idx * 5) % 7) - 3) * 0.0003
        customers.append(
            {
                "ref": f"CUST-MT-{idx:02d}",
                "name": name,
                "channel_code": "MT",
                "district_code": dist_code,
                "district_name": dm["name"],
                "subdistrict_code": dm["subdist"],
                "subdistrict_name": dm["subdist_name"],
                "city": dm["city"],
                "state": "Sulawesi Utara",
                "country": "Indonesia",
                "zip": dm["zip"],
                "street": street,
                "phone": f"0811-430-{idx:04d}",
                "vat": f"01234567890{idx:05d}",
                "credit_limit": cl,
                "credit_mode": "strict" if pt > 30 else "limit",
                "payment_term_days": pt,
                "salesman_code": "SLS-01",
                "salesman_name": "Christian Wowor",
                "pjp_frequency": "F1",  # Weekly
                "pjp_call_day": call_day,
                "delivery_route": f"DELIV-MT-{call_day.upper()}",
                "delivery_vehicle": "DB 8345 MK (Canter CDD)",
                "cohort_date": "2026-07-01",  # MT is active from day 1
                "latitude": round(dm["lat"] + d_lat, 6),
                "longitude": round(dm["lng"] + d_lng, 6),
                "is_company": True,
            }
        )

    # 2. GENERAL TRADE (72 Grosir / Sembako Besar)
    # 33 Manado Pusat & Barat -> SLS-02 (Andre Pangemanan)
    # 24 Manado Timur & Utara -> SLS-03 (Meidy Wowor)
    # 15 Luar Kota / Hinterland -> SLS-04 (Refly Sondakh)
    gt_master = [
        # SLS-02: Manado Barat & Pusat (33)
        ("Toko Sembako Berkat Pasar 45", "KEC-MND-WNG", "SLS-02", "Andre Pangemanan", "F1", "Senin"),
        ("Toko Kawanua Sejati Wenang", "KEC-MND-WNG", "SLS-02", "Andre Pangemanan", "F1", "Senin"),
        ("Grosir Sinar Terang Calaca", "KEC-MND-WNG", "SLS-02", "Andre Pangemanan", "F1", "Senin"),
        ("Toko Pinaesaan Calaca", "KEC-MND-WNG", "SLS-02", "Andre Pangemanan", "F2", "Senin"),
        ("Grosir Istiqlal Sentosa", "KEC-MND-WNG", "SLS-02", "Andre Pangemanan", "F2", "Senin"),
        ("Grosir Calaca Baru", "KEC-MND-WNG", "SLS-02", "Andre Pangemanan", "F2", "Senin"),
        ("Toko Harapan Bersehati", "KEC-MND-SRO", "SLS-02", "Andre Pangemanan", "F1", "Selasa"),
        ("Grosir Bintang Samrat Sario", "KEC-MND-SRO", "SLS-02", "Andre Pangemanan", "F1", "Selasa"),
        ("Grosir Manado Raya Sario", "KEC-MND-SRO", "SLS-02", "Andre Pangemanan", "F2", "Selasa"),
        ("Toko Sario Makmur", "KEC-MND-SRO", "SLS-02", "Andre Pangemanan", "F2", "Selasa"),
        ("Grosir Krida Bahu", "KEC-MND-MLY", "SLS-02", "Andre Pangemanan", "F1", "Rabu"),
        ("Toko Sumber Berkat Malalayang", "KEC-MND-MLY", "SLS-02", "Andre Pangemanan", "F1", "Rabu"),
        ("Grosir Malalayang Satu", "KEC-MND-MLY", "SLS-02", "Andre Pangemanan", "F2", "Rabu"),
        ("Toko Batu Kota Indah", "KEC-MND-MLY", "SLS-02", "Andre Pangemanan", "F2", "Rabu"),
        ("Grosir Kleak Mandiri", "KEC-MND-MLY", "SLS-02", "Andre Pangemanan", "F2", "Rabu"),
        ("Toko Pelita Jaya Wanea", "KEC-MND-WNA", "SLS-02", "Andre Pangemanan", "F1", "Kamis"),
        ("Toko Anugerah Kasih Karombasan", "KEC-MND-WNA", "SLS-02", "Andre Pangemanan", "F1", "Kamis"),
        ("Grosir Rukun Damai Ranotana", "KEC-MND-WNA", "SLS-02", "Andre Pangemanan", "F2", "Kamis"),
        ("Grosir Teling Sentosa Wanea", "KEC-MND-WNA", "SLS-02", "Andre Pangemanan", "F2", "Kamis"),
        ("Toko Pakowa Sejahtera Wanea", "KEC-MND-WNA", "SLS-02", "Andre Pangemanan", "F2", "Kamis"),
        ("Grosir Tingkulu Jaya Wanea", "KEC-MND-WNA", "SLS-02", "Andre Pangemanan", "F2", "Kamis"),
        ("Toko Winangun Berkat", "KEC-MND-WNA", "SLS-02", "Andre Pangemanan", "F2", "Kamis"),
        ("Toko Bumi Nyiur Permai", "KEC-MND-WNA", "SLS-02", "Andre Pangemanan", "F2", "Kamis"),
        ("Toko Cahaya Samrat Wenang", "KEC-MND-WNG", "SLS-02", "Andre Pangemanan", "F1", "Jumat"),
        ("Grosir Megamas Abadi", "KEC-MND-WNG", "SLS-02", "Andre Pangemanan", "F1", "Jumat"),
        ("Toko Karombasan Baru", "KEC-MND-WNA", "SLS-02", "Andre Pangemanan", "F2", "Jumat"),
        ("Grosir Bahu Sentosa", "KEC-MND-MLY", "SLS-02", "Andre Pangemanan", "F2", "Jumat"),
        ("Toko Sam Ratulangi Perkasa", "KEC-MND-SRO", "SLS-02", "Andre Pangemanan", "F2", "Jumat"),
        ("Grosir Pasar 45 Rezeki", "KEC-MND-WNG", "SLS-02", "Andre Pangemanan", "F1", "Sabtu"),
        ("Toko Berkat Bahu Sejahtera", "KEC-MND-MLY", "SLS-02", "Andre Pangemanan", "F2", "Sabtu"),
        ("Grosir Sario Damai", "KEC-MND-SRO", "SLS-02", "Andre Pangemanan", "F2", "Sabtu"),
        ("Toko Ranotana Jaya", "KEC-MND-WNA", "SLS-02", "Andre Pangemanan", "F2", "Sabtu"),
        ("Toko Malalayang Megah", "KEC-MND-MLY", "SLS-02", "Andre Pangemanan", "F2", "Sabtu"),
        # SLS-03: Manado Timur & Utara (24)
        ("Grosir Tikala Baru", "KEC-MND-TKL", "SLS-03", "Meidy Wowor", "F1", "Senin"),
        ("Toko Banjer Berkah Tikala", "KEC-MND-TKL", "SLS-03", "Meidy Wowor", "F1", "Senin"),
        ("Grosir Taas Damai Tikala", "KEC-MND-TKL", "SLS-03", "Meidy Wowor", "F2", "Senin"),
        ("Grosir Makmur Abadi Tikala", "KEC-MND-TKL", "SLS-03", "Meidy Wowor", "F2", "Senin"),
        ("Toko Paal Dua Jaya", "KEC-MND-PLD", "SLS-03", "Meidy Wowor", "F1", "Selasa"),
        ("Toko Berkat Melimpah Paal Dua", "KEC-MND-PLD", "SLS-03", "Meidy Wowor", "F1", "Selasa"),
        ("Grosir Sentosa Perkasa Perkamil", "KEC-MND-PLD", "SLS-03", "Meidy Wowor", "F2", "Selasa"),
        ("Toko Dendengan Mandiri Paal Dua", "KEC-MND-PLD", "SLS-03", "Meidy Wowor", "F2", "Selasa"),
        ("Toko Bintang Timur Ranomuut", "KEC-MND-PLD", "SLS-03", "Meidy Wowor", "F2", "Selasa"),
        ("Grosir Sumber Mulia Tuminting", "KEC-MND-TMT", "SLS-03", "Meidy Wowor", "F1", "Rabu"),
        ("Toko Surya Indah Tuminting", "KEC-MND-TMT", "SLS-03", "Meidy Wowor", "F1", "Rabu"),
        ("Grosir Tumumpa Berkat", "KEC-MND-TMT", "SLS-03", "Meidy Wowor", "F2", "Rabu"),
        ("Toko Sindulang Jaya", "KEC-MND-TMT", "SLS-03", "Meidy Wowor", "F2", "Rabu"),
        ("Toko Bintang Matuari Singkil", "KEC-MND-SKL", "SLS-03", "Meidy Wowor", "F1", "Kamis"),
        ("Toko Usaha Bersama Singkil", "KEC-MND-SKL", "SLS-03", "Meidy Wowor", "F2", "Kamis"),
        ("Grosir Kombos Jaya Singkil", "KEC-MND-SKL", "SLS-03", "Meidy Wowor", "F2", "Kamis"),
        ("Grosir Cahaya Utara Mahakeret", "KEC-MND-SKL", "SLS-03", "Meidy Wowor", "F2", "Kamis"),
        ("Toko Paniki Permai Mapanget", "KEC-MND-MPG", "SLS-03", "Meidy Wowor", "F1", "Jumat"),
        ("Grosir Kairagi Mandiri", "KEC-MND-MPG", "SLS-03", "Meidy Wowor", "F1", "Jumat"),
        ("Grosir Buha Indah Mapanget", "KEC-MND-MPG", "SLS-03", "Meidy Wowor", "F2", "Jumat"),
        ("Toko Bengkol Sejahtera", "KEC-MND-MPG", "SLS-03", "Meidy Wowor", "F2", "Jumat"),
        ("Toko Pandu Berkah Mapanget", "KEC-MND-MPG", "SLS-03", "Meidy Wowor", "F2", "Jumat"),
        ("Toko Kairagi Satu Makmur", "KEC-MND-MPG", "SLS-03", "Meidy Wowor", "F2", "Sabtu"),
        ("Grosir Bailang Mandiri", "KEC-MND-TMT", "SLS-03", "Meidy Wowor", "F2", "Sabtu"),
        # SLS-04: Luar Kota / Hinterland (15)
        ("Toko Bintang Matuari Maesa", "KEC-BTG-MAS", "SLS-04", "Refly Sondakh", "F1", "Senin"),
        ("Grosir Girian Indah Bitung", "KEC-BTG-GRN", "SLS-04", "Refly Sondakh", "F1", "Senin"),
        ("Toko Madidir Berkat Bitung", "KEC-BTG-MDR", "SLS-04", "Refly Sondakh", "F2", "Senin"),
        ("Grosir Danowudu Jaya Bitung", "KEC-BTG-MDR", "SLS-04", "Refly Sondakh", "F2", "Senin"),
        ("Toko Matuari Sejati Bitung", "KEC-BTG-ATB", "SLS-04", "Refly Sondakh", "F2", "Senin"),
        ("Toko Jaya Sejahtera Tomohon", "KEC-TMH-TGH", "SLS-04", "Refly Sondakh", "F1", "Selasa"),
        ("Grosir Paslaten Mandiri Tomohon", "KEC-TMH-TGH", "SLS-04", "Refly Sondakh", "F1", "Selasa"),
        ("Toko Kakaskasen Sejahtera", "KEC-TMH-TGH", "SLS-04", "Refly Sondakh", "F2", "Selasa"),
        ("Toko Rezeki Tondano", "KEC-MNH-TDN", "SLS-04", "Refly Sondakh", "F1", "Rabu"),
        ("Toko Tondano Makmur Tondano", "KEC-MNH-TDN", "SLS-04", "Refly Sondakh", "F2", "Rabu"),
        ("Toko Berkat Kawangkoan", "KEC-MNH-KWG", "SLS-04", "Refly Sondakh", "F1", "Kamis"),
        ("Grosir Kawangkoan Permai", "KEC-MNH-KWG", "SLS-04", "Refly Sondakh", "F2", "Kamis"),
        ("Grosir Airmadidi Baru Minut", "KEC-MNT-AMD", "SLS-04", "Refly Sondakh", "F1", "Jumat"),
        ("Toko Kalawat Berkat Minut", "KEC-MNT-AMD", "SLS-04", "Refly Sondakh", "F2", "Jumat"),
        ("Toko Amurang Sentosa Minsel", "KEC-MNS-AMR", "SLS-04", "Refly Sondakh", "F2", "Sabtu"),
    ]

    for idx, (name, dist_code, sls, sls_name, freq, call_day) in enumerate(gt_master, start=1):
        dm = DISTRICT_MASTER[dist_code]
        d_lat = (((idx * 7) % 11) - 5) * 0.00035
        d_lng = (((idx * 13) % 11) - 5) * 0.00035
        # Cohort distribution:
        # First 40 GT stores active since July
        # Next 15 active in August (+6%)
        # Next 10 active in Sept (+8%)
        # Remaining 7 active in Oct
        if idx <= 40:
            cdate = "2026-07-01"
        elif idx <= 55:
            cdate = "2026-08-01"
        elif idx <= 65:
            cdate = "2026-09-01"
        else:
            cdate = "2026-10-01"

        customers.append(
            {
                "ref": f"CUST-GT-{idx:02d}",
                "name": name,
                "channel_code": "GT",
                "district_code": dist_code,
                "district_name": dm["name"],
                "subdistrict_code": dm["subdist"],
                "subdistrict_name": dm["subdist_name"],
                "city": dm["city"],
                "state": "Sulawesi Utara",
                "country": "Indonesia",
                "zip": dm["zip"],
                "street": f"{dm['street']} No. {idx * 2}",
                "phone": f"0812-441-{idx:04d}",
                "vat": f"0800{idx:04d}1234821000",
                "credit_limit": 45000000 if freq == "F1" else 25000000,
                "credit_mode": "limit",
                "payment_term_days": 14 if freq == "F1" else 7,
                "salesman_code": sls,
                "salesman_name": sls_name,
                "pjp_frequency": freq,
                "pjp_call_day": call_day,
                "delivery_route": f"DELIV-GT-{dm['city'].split()[-1].upper()}-{call_day.upper()}",
                "delivery_vehicle": (
                    "DB 8456 FB (L300 Urban Barat)"
                    if sls == "SLS-02"
                    else ("DB 8567 TR (Traga Urban Timur)" if sls == "SLS-03" else "DB 8910 TK (Elf Luar Kota)")
                ),
                "cohort_date": cdate,
                "latitude": round(dm["lat"] + d_lat, 6),
                "longitude": round(dm["lng"] + d_lng, 6),
                "is_company": True,
            }
        )

    # 3. RETAIL KIOS CANVASS (260 Kios)
    # Tersebar proporsional ke SELURUH 18 KECAMATAN
    rtl_districts_weights = [
        ("KEC-MND-WNG", 25),
        ("KEC-MND-SRO", 18),
        ("KEC-MND-MLY", 22),
        ("KEC-MND-WNA", 18),
        ("KEC-MND-TKL", 23),
        ("KEC-MND-PLD", 21),
        ("KEC-MND-TMT", 20),
        ("KEC-MND-SKL", 16),
        ("KEC-MND-MPG", 23),
        ("KEC-BTG-MAS", 15),
        ("KEC-BTG-MDR", 8),
        ("KEC-BTG-GRN", 5),
        ("KEC-BTG-ATB", 4),
        ("KEC-TMH-TGH", 12),
        ("KEC-MNH-TDN", 10),
        ("KEC-MNH-KWG", 6),
        ("KEC-MNT-AMD", 8),
        ("KEC-MNS-AMR", 6),
    ]

    rtl_prefixes = [
        "Kios Tante",
        "Warung Om",
        "Kios Ci",
        "Warung Tante",
        "Kios Ko",
        "Warung",
        "Kios Berkat",
        "Kios Gloria",
        "Warung Kasih",
        "Kios Filadelfia",
    ]
    rtl_names_pool = [
        "Tin",
        "Oce",
        "Utu",
        "Meyke",
        "Ferry",
        "Dani",
        "Ventje",
        "Novry",
        "Ritha",
        "Meylan",
        "Hein",
        "Vonny",
        "Meiske",
        "Joppy",
        "Deasy",
        "Ronny",
        "Grace",
        "Bobby",
        "Erna",
        "Jacky",
        "Lita",
        "Nico",
        "Vicky",
        "Yola",
        "Franky",
        "Siska",
        "Stenly",
        "Wanda",
        "Roy",
        "Vera",
        "Pingkan",
        "Toar",
        "Lumimuut",
        "Engelin",
        "Marietje",
    ]
    rtl_suffixes = [
        "Lorong 1",
        "Lorong 2",
        "Lorong 3",
        "Dekat Gereja",
        "Pintu Masuk",
        "Ujung Lorong",
        "Bawah Pohon",
        "Perempatan",
        "Jalan Salib",
        "Pondok Damai",
        "Samping Lapangan",
        "Tikungan",
        "Jembatan",
        "Kompleks",
        "Pasar",
        "Depan SD",
        "Dekat Mesjid",
        "Puncak",
    ]

    rtl_counter = 1
    for dist_code, target_count in rtl_districts_weights:
        dm = DISTRICT_MASTER[dist_code]
        # Penugasan Sales Canvass:
        # Manado Barat, Pusat, Selatan -> CVS-01 (Novry Mandagi)
        # Manado Timur, Utara & Luar Kota -> CVS-02 (Steven Lumenta)
        is_cvs_1 = dist_code in [
            "KEC-MND-WNG",
            "KEC-MND-SRO",
            "KEC-MND-MLY",
            "KEC-MND-WNA",
            "KEC-TMH-TGH",
            "KEC-MNH-KWG",
            "KEC-MNS-AMR",
        ]
        sls = "CVS-01" if is_cvs_1 else "CVS-02"
        sls_name = "Novry Mandagi (Van 01)" if is_cvs_1 else "Steven Lumenta (Van 02)"
        van_plate = "DB 8123 QA (Gran Max BV)" if is_cvs_1 else "DB 8234 QX (Gran Max Box)"

        for sub_idx in range(target_count):
            pfx = rtl_prefixes[(rtl_counter - 1) % len(rtl_prefixes)]
            nm = rtl_names_pool[(rtl_counter - 1) % len(rtl_names_pool)]
            sfx = rtl_suffixes[(rtl_counter - 1) % len(rtl_suffixes)]
            kios_name = f"{pfx} {nm} {sfx}"

            d_lat = (((rtl_counter * 5) % 13) - 6) * 0.0003
            d_lng = (((rtl_counter * 11) % 13) - 6) * 0.0003
            call_day = DAYS_OF_WEEK[(rtl_counter - 1) % 6]
            freq = "F2" if rtl_counter <= 80 else "F4"

            # Cohort distribution:
            # Baseline July: ~120 RTL
            # August: +15 RTL
            # Sept: +20 RTL
            # Oct: remaining ~105 RTL
            if rtl_counter <= 120:
                cdate = "2026-07-01"
            elif rtl_counter <= 135:
                cdate = "2026-08-01"
            elif rtl_counter <= 155:
                cdate = "2026-09-01"
            else:
                cdate = "2026-10-01"

            customers.append(
                {
                    "ref": f"CUST-RTL-{rtl_counter:03d}",
                    "name": kios_name,
                    "channel_code": "RTL",
                    "district_code": dist_code,
                    "district_name": dm["name"],
                    "subdistrict_code": dm["subdist"],
                    "subdistrict_name": dm["subdist_name"],
                    "city": dm["city"],
                    "state": "Sulawesi Utara",
                    "country": "Indonesia",
                    "zip": dm["zip"],
                    "street": f"Lorong Pemukiman {dm['name']} RW 0{sub_idx % 6 + 1}",
                    "phone": f"0852-401-{rtl_counter:04d}",
                    "vat": "",
                    "credit_limit": 1500000,
                    "credit_mode": "strict",
                    "payment_term_days": 0,  # Cash COD
                    "salesman_code": sls,
                    "salesman_name": sls_name,
                    "pjp_frequency": freq,
                    "pjp_call_day": call_day,
                    "delivery_route": f"CANVASS-{dm['name'].upper()}-{call_day.upper()}",
                    "delivery_vehicle": van_plate,
                    "cohort_date": cdate,
                    "latitude": round(dm["lat"] + d_lat, 6),
                    "longitude": round(dm["lng"] + d_lng, 6),
                    "is_company": False,
                }
            )
            rtl_counter += 1

    # 4. INSTITUSIONAL / HOREKA (10 Outlets) - MGT-01
    inst_defs = [
        ("RSUP Prof. Kandou Malalayang", "KEC-MND-MLY", "Jl. Raya Tanawangko Malalayang", "Senin", 60000000, 30),
        ("Four Points by Sheraton Manado", "KEC-MND-SRO", "Jl. Piere Tendean Boulevard", "Selasa", 40000000, 30),
        ("Hotel Sintesa Peninsula Manado", "KEC-MND-WNG", "Jl. Jendral Sudirman No. 1", "Rabu", 35000000, 30),
        ("Katering Minahasa Indah", "KEC-MND-TKL", "Jl. Balai Kota Tikala Ares", "Kamis", 25000000, 14),
        ("Restoran Raja Sate Paniki", "KEC-MND-MPG", "Jl. AA Maramis Paniki Dua", "Jumat", 20000000, 14),
        ("Hotel Novotel Manado Golf Resort", "KEC-MND-MPG", "Jl. AA Maramis Kairagi Dua", "Sabtu", 25000000, 30),
        ("Katering Bahu Makmur", "KEC-MND-MLY", "Jl. Wolter Monginsidi Bahu", "Selasa", 15000000, 14),
        ("Restoran Nelayan Megamas", "KEC-MND-WNG", "Kawasan Megamas Blok 2B", "Rabu", 20000000, 14),
        ("Katering Berkat Tondano", "KEC-MNH-TDN", "Jl. Sam Ratulangi Tondano", "Kamis", 15000000, 14),
        ("Mess Karyawan Pelabuhan Bitung", "KEC-BTG-MAS", "Kawasan Pelabuhan Samudera", "Jumat", 15000000, 30),
    ]

    for idx, (name, dist_code, street, call_day, cl, pt) in enumerate(inst_defs, start=1):
        dm = DISTRICT_MASTER[dist_code]
        d_lat = (((idx * 2) % 5) - 2) * 0.0003
        d_lng = (((idx * 4) % 5) - 2) * 0.0003
        customers.append(
            {
                "ref": f"CUST-INST-{idx:02d}",
                "name": name,
                "channel_code": "INST",
                "district_code": dist_code,
                "district_name": dm["name"],
                "subdistrict_code": dm["subdist"],
                "subdistrict_name": dm["subdist_name"],
                "city": dm["city"],
                "state": "Sulawesi Utara",
                "country": "Indonesia",
                "zip": dm["zip"],
                "street": street,
                "phone": f"0811-432-{idx:04d}",
                "vat": f"01123456788210{idx:02d}",
                "credit_limit": cl,
                "credit_mode": "limit",
                "payment_term_days": pt,
                "salesman_code": "MGT-01",
                "salesman_name": "Hendrik Polii & Joni Kumajas",
                "pjp_frequency": "F2",
                "pjp_call_day": call_day,
                "delivery_route": f"DELIV-INST-{call_day.upper()}",
                "delivery_vehicle": (
                    "DB 8456 FB (L300 Urban Barat)"
                    if dist_code in ["KEC-MND-WNG", "KEC-MND-SRO", "KEC-MND-MLY", "KEC-MND-WNA"]
                    else (
                        "DB 8567 TR (Traga Urban Timur)"
                        if dist_code in ["KEC-MND-TKL", "KEC-MND-PLD", "KEC-MND-TMT", "KEC-MND-SKL", "KEC-MND-MPG"]
                        else "DB 8910 TK (Elf Luar Kota)"
                    )
                ),
                "cohort_date": "2026-07-01",
                "latitude": round(dm["lat"] + d_lat, 6),
                "longitude": round(dm["lng"] + d_lng, 6),
                "is_company": True,
            }
        )

    return customers


def main():
    print("Membuat Master Customer Register & PJP Schedule (354 Outlets)...")
    customers = generate_all_customers()
    assert len(customers) == 354, f"Total outlet harus tepat 354, didapat {len(customers)}"

    # 1. Simpan ke data/registers/customer_registry_354.json
    reg_json_file = REG_DIR / "customer_registry_354.json"
    with open(reg_json_file, "w", encoding="utf-8") as f:
        json.dump(customers, f, indent=2, ensure_ascii=False)
    print(f" -> {reg_json_file} tersimpan ({len(customers)} records).")

    # 2. Simpan ke data/registers/customer_registry_354.csv
    reg_csv_file = REG_DIR / "customer_registry_354.csv"
    with open(reg_csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(customers[0].keys()))
        writer.writeheader()
        writer.writerows(customers)
    print(f" -> {reg_csv_file} tersimpan ({len(customers)} records).")

    # 3. Ekstrak PJP Schedule ke data/registers/pjp_schedule_354.json & .csv
    pjp_schedule = []
    for c in customers:
        pjp_schedule.append(
            {
                "customer_ref": c["ref"],
                "customer_name": c["name"],
                "channel": c["channel_code"],
                "city": c["city"],
                "district": c["district_name"],
                "salesman_code": c["salesman_code"],
                "salesman_name": c["salesman_name"],
                "pjp_frequency": c["pjp_frequency"],
                "pjp_call_day": c["pjp_call_day"],
                "delivery_route": c["delivery_route"],
                "delivery_vehicle": c["delivery_vehicle"],
                "cohort_date": c["cohort_date"],
            }
        )
    pjp_json_file = REG_DIR / "pjp_schedule_354.json"
    with open(pjp_json_file, "w", encoding="utf-8") as f:
        json.dump(pjp_schedule, f, indent=2, ensure_ascii=False)
    print(f" -> {pjp_json_file} tersimpan.")

    pjp_csv_file = REG_DIR / "pjp_schedule_354.csv"
    with open(pjp_csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(pjp_schedule[0].keys()))
        writer.writeheader()
        writer.writerows(pjp_schedule)
    print(f" -> {pjp_csv_file} tersimpan.")

    # 4. Sinkronkan langsung ke data/seed/partners_354.csv
    seed_partner_file = SEED_DIR / "partners_354.csv"
    seed_fields = [
        "ref",
        "name",
        "channel_code",
        "district_code",
        "subdistrict_code",
        "street",
        "city",
        "state",
        "country",
        "zip",
        "phone",
        "vat",
        "credit_limit",
        "credit_mode",
        "payment_term_days",
        "salesman_code",
        "latitude",
        "longitude",
        "is_company",
    ]
    with open(seed_partner_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=seed_fields)
        writer.writeheader()
        for c in customers:
            row = {k: c[k] for k in seed_fields}
            writer.writerow(row)
    print(f" -> {seed_partner_file} disinkronkan 100% konsisten dengan register.")


if __name__ == "__main__":
    main()
