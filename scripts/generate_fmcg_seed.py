#!/usr/bin/env python3
"""Generator Seed Dataset FMCG Manado & Sulawesi Utara (PT Manado Distribusi Utama).

Menghasilkan dataset deterministik dan realistis:
1. 150 SKU FMCG (Mayora 44, Kapal Api 32, Unilever 42, Wings Food 32)
2. 354 Partner Outlet Aktif (12 MT, 72 GT, 260 RTL, 10 INST) di 18 Kecamatan se-Sulut
3. 24 Karyawan & App Roles
4. 9 Armada Kendaraan Logistik & Spesifikasi Box Riil
5. Ringkasan Simulasi Transaksi Historis (Juli - Oktober 2026, total Rp 19.88 BIO IDR)
"""

import csv
import json
import pathlib
import random

ROOT = pathlib.Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "data" / "seed"
SEED_DIR.mkdir(parents=True, exist_ok=True)

# Set seed agar hasil selalu deterministik (reproducible)
random.seed(20260701)


def generate_products() -> list[dict]:
    """Menghasilkan 150 Master SKU FMCG terbagi pada 4 Principal Nasional."""
    products = []

    # --- 1. MAYORA (44 SKU) ---
    # Food (18)
    roma_sub = [
        ("Kelapa 300g", 300, "Biskuit Kelapa Gurih"),
        ("Marie Susu 115g", 115, "Biskuit Marie Susu"),
        ("Sandwich Cokelat 216g", 216, "Biskuit Sandwich Krim Cokelat"),
        ("Sandwich Peanut 216g", 216, "Biskuit Sandwich Krim Kacang"),
        ("Sari Gandum 149g", 149, "Biskuit Gandum Utuh"),
        ("Sari Gandum Cokelat 115g", 115, "Biskuit Gandum Lapis Cokelat"),
        ("Malkist Keju Manis 120g", 120, "Malkist Tabur Keju Manis"),
        ("Malkist Abon 135g", 135, "Malkist Tabur Abon Sapi Gurih"),
        ("Malkist Crackers 135g", 135, "Malkist Gurih Renyah"),
        ("Malkist Cokelat 120g", 120, "Malkist Salut Cokelat Belgia"),
    ]
    for idx, (name, gr, desc) in enumerate(roma_sub, start=1):
        code = f"MYR-RMA-{idx:02d}"
        products.append(
            {
                "default_code": code,
                "name": f"Roma {name}",
                "principal_code": "PRIN-MAYORA",
                "fmcg_category": "food",
                "brand_code": "BRD-RMA",
                "base_uom": "Pcs",
                "purchase_uom": "Karton",
                "inner_qty": 1,
                "carton_qty": 30,
                "cost_price": 7500,
                "list_price": 8500,
                "weight_kg": gr / 1000.0,
                "volume_cbm": 0.0012,
                "barcode": f"8992753{10000 + idx}",
                "description": desc,
            }
        )

    products.append(
        {
            "default_code": "MYR-BTR-01",
            "name": "Better Vanilla Sandwich 22g",
            "principal_code": "PRIN-MAYORA",
            "fmcg_category": "food",
            "brand_code": "BRD-BTR",
            "base_uom": "Pcs",
            "purchase_uom": "Karton",
            "inner_qty": 20,
            "carton_qty": 160,
            "cost_price": 1800,
            "list_price": 2000,
            "weight_kg": 0.022,
            "volume_cbm": 0.0001,
            "barcode": "899275320001",
            "description": "Biskuit Sandwich Lapis Cokelat Krim Vanila",
        }
    )
    products.append(
        {
            "default_code": "MYR-BTR-02",
            "name": "Better Cokelat 120g",
            "principal_code": "PRIN-MAYORA",
            "fmcg_category": "food",
            "brand_code": "BRD-BTR",
            "base_uom": "Pcs",
            "purchase_uom": "Karton",
            "inner_qty": 1,
            "carton_qty": 24,
            "cost_price": 8200,
            "list_price": 9500,
            "weight_kg": 0.120,
            "volume_cbm": 0.0008,
            "barcode": "899275320002",
            "description": "Biskuit Better Family Pack",
        }
    )

    products.append(
        {
            "default_code": "MYR-SLI-01",
            "name": "Slai O'lai Strawberry 128g",
            "principal_code": "PRIN-MAYORA",
            "fmcg_category": "food",
            "brand_code": "BRD-SLI",
            "base_uom": "Pcs",
            "purchase_uom": "Karton",
            "inner_qty": 1,
            "carton_qty": 24,
            "cost_price": 6500,
            "list_price": 7500,
            "weight_kg": 0.128,
            "volume_cbm": 0.0006,
            "barcode": "899275330001",
            "description": "Biskuit Selai Buah Stroberi Asli",
        }
    )
    products.append(
        {
            "default_code": "MYR-SLI-02",
            "name": "Slai O'lai Blueberry 128g",
            "principal_code": "PRIN-MAYORA",
            "fmcg_category": "food",
            "brand_code": "BRD-SLI",
            "base_uom": "Pcs",
            "purchase_uom": "Karton",
            "inner_qty": 1,
            "carton_qty": 24,
            "cost_price": 6500,
            "list_price": 7500,
            "weight_kg": 0.128,
            "volume_cbm": 0.0006,
            "barcode": "899275330002",
            "description": "Biskuit Selai Buah Blueberry Asli",
        }
    )

    beng_sub = [
        ("Reguler 20g", 20, 160, 2000, 2500, "Wafer Karamel Cokelat Crispy"),
        ("Maxx 32g", 12, 120, 3200, 3800, "Wafer Cokelat Porsi Ekstra"),
        ("Share It Pouch 100g", 1, 24, 11000, 13000, "Beng-Beng Mini Pouch Pesta"),
        ("White 22g", 20, 160, 2200, 2700, "Wafer Lapis Cokelat Putih & Kelapa"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(beng_sub, start=1):
        products.append(
            {
                "default_code": f"MYR-BBG-{idx:02d}",
                "name": f"Beng-Beng {name}",
                "principal_code": "PRIN-MAYORA",
                "fmcg_category": "food",
                "brand_code": "BRD-BBG",
                "base_uom": "Pcs",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.025,
                "volume_cbm": 0.0002,
                "barcode": f"89927534000{idx}",
                "description": desc,
            }
        )

    # RTD / Minuman Kopi (16)
    torabika_sub = [
        ("Duo 25g", 10, 120, 1200, 1500, "Kopi + Gula Mantap"),
        ("Duo Susu Full Cream 28g", 10, 120, 1400, 1700, "Kopi Susu Gurih"),
        ("Cappuccino 25g + Choco Granule", 10, 120, 1800, 2200, "Cappuccino Busa Melimpah"),
        ("Gilus Mix Gula Aren 23g", 10, 120, 1100, 1300, "Kopi Giling Halus Aroma Aren"),
        ("Gilus Mix Pandan 23g", 10, 120, 1100, 1300, "Kopi Halus Wangi Pandan"),
        ("Creamy Latte 25g", 10, 120, 1600, 2000, "Latte Lembut Rasa Susu"),
        ("Kopi Susu Espresso 28g", 10, 120, 1500, 1800, "Kopi Espresso Susu Kental"),
        ("Moka 28g", 10, 120, 1400, 1700, "Paduan Kopi & Cokelat Moka"),
        ("Natacinno 25g", 10, 120, 1700, 2100, "Cappuccino Kelapa Segar"),
        ("Jahe Susu 25g", 10, 120, 1500, 1800, "Kopi Hangat Jahe Alami"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(torabika_sub, start=1):
        products.append(
            {
                "default_code": f"MYR-TRB-{idx:02d}",
                "name": f"Torabika {name}",
                "principal_code": "PRIN-MAYORA",
                "fmcg_category": "rtd",
                "brand_code": "BRD-TRB",
                "base_uom": "Sachet",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.030,
                "volume_cbm": 0.00015,
                "barcode": f"8992753500{idx:02d}",
                "description": desc,
            }
        )

    kopiko_rtd = [
        ("Lucky Day Kopi Botol 250ml", 1, 24, 6500, 7500, "Kopi Susu Energi Thailand Blend"),
        ("78C Coffee Latte 240ml", 1, 24, 6000, 7000, "Latte Suhu Sempurna Ekstraksi"),
        ("78C Macchiato 240ml", 1, 24, 6000, 7000, "Kopi Macchiato Gurih"),
        ("78C Calorie Low 240ml", 1, 24, 6200, 7200, "Kopi Ringan Rendah Kalori"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(kopiko_rtd, start=1):
        products.append(
            {
                "default_code": f"MYR-KPK-RTD-{idx:02d}",
                "name": f"Kopiko {name}",
                "principal_code": "PRIN-MAYORA",
                "fmcg_category": "rtd",
                "brand_code": "BRD-KPK",
                "base_uom": "Botol",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.280,
                "volume_cbm": 0.0008,
                "barcode": f"8992753600{idx:02d}",
                "description": desc,
            }
        )

    energen_sub = [
        ("Sereal Cokelat 30g", 10, 120, 1800, 2200, "Minuman Sereal Nutrisi Sarapan"),
        ("Sereal Vanila 30g", 10, 120, 1800, 2200, "Minuman Sereal Vanila Lezat"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(energen_sub, start=1):
        products.append(
            {
                "default_code": f"MYR-EGN-{idx:02d}",
                "name": f"Energen {name}",
                "principal_code": "PRIN-MAYORA",
                "fmcg_category": "rtd",
                "brand_code": "BRD-EGN",
                "base_uom": "Sachet",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.035,
                "volume_cbm": 0.0002,
                "barcode": f"8992753700{idx:02d}",
                "description": desc,
            }
        )

    # Confectionery (10)
    candy_sub = [
        ("Kopiko Coffee Candy Sak 150g", "BRD-KPK", 1, 24, 7500, 9000, "Permen Kopi Asli"),
        ("Kopiko Blister Pack 32g", "BRD-KPK", 12, 120, 2500, 3000, "Permen Kopi Kantong Saku"),
        ("Kopiko Cappuccino 150g", "BRD-KPK", 1, 24, 7800, 9200, "Permen Rasa Cappuccino"),
        ("Kis Mint Cherry Sak 125g", "BRD-KIS", 1, 24, 6800, 8000, "Permen Mint Segar Emoticon"),
        ("Kis Mint Barley Sak 125g", "BRD-KIS", 1, 24, 6800, 8000, "Permen Mint Barley"),
        ("Kis Mint Apple Peach 125g", "BRD-KIS", 1, 24, 6800, 8000, "Permen Rasa Apel Persik"),
        ("Kis Grape Mint 125g", "BRD-KIS", 1, 24, 6800, 8000, "Permen Rasa Anggur Segar"),
        ("Tamarin Permen Asam Sak 135g", "BRD-TMR", 1, 24, 7000, 8200, "Permen Asam Jawa Alami"),
        ("Tamarin Bag 50g", "BRD-TMR", 1, 48, 3000, 3600, "Permen Asam Kemasan Mini"),
        ("Tamarin Roll Pack 30g", "BRD-TMR", 12, 120, 2000, 2500, "Permen Asam Roll Praktis"),
    ]
    for idx, (name, brd, in_q, ctn_q, cp, lp, desc) in enumerate(candy_sub, start=1):
        products.append(
            {
                "default_code": f"MYR-CND-{idx:02d}",
                "name": name,
                "principal_code": "PRIN-MAYORA",
                "fmcg_category": "confectionery",
                "brand_code": brd,
                "base_uom": "Pcs",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.150,
                "volume_cbm": 0.0004,
                "barcode": f"8992753800{idx:02d}",
                "description": desc,
            }
        )

    # --- 2. KAPAL API / SANTOS (32 SKU) ---
    kapal_api_sub = [
        ("Special Merah 65g", 1, 40, 4800, 5600, "Kopi Bubuk Murni Khas"),
        ("Special Merah 165g", 1, 24, 11500, 13200, "Kopi Bubuk Sedang"),
        ("Special Merah 380g", 1, 12, 25500, 29000, "Kopi Bubuk Kemasan Keluarga"),
        ("Special Mix 24g (Kopi+Gula)", 10, 120, 1300, 1600, "Kopi Campur Gula Sachet"),
        ("Kopi Susu Mantap 31g", 10, 120, 1500, 1800, "Kopi Susu Formula Baru"),
        ("White Koffie 20g", 10, 120, 1400, 1700, "Kopi Putih Ramah Lambung"),
        ("Grande White Coffee 20g", 10, 120, 1600, 1900, "Kopi Putih Premium Creamy"),
        ("Signature Original 65g", 1, 30, 8500, 10000, "Kopi Bubuk Pilihan Arabika"),
        ("Easy Drip Blend 50g", 1, 20, 18000, 21000, "Kopi Drip Bag Eksklusif"),
        ("Mantap 75g", 1, 40, 5500, 6500, "Kopi Bubuk Aroma Tajam"),
        ("Krim Cafe Non-Dairy 500g", 1, 12, 28000, 32000, "Krimer Bubuk Pengganti Susu"),
        ("Gula Aren 23g", 10, 120, 1400, 1700, "Kopi Bubuk Manis Aren Asli"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(kapal_api_sub, start=1):
        products.append(
            {
                "default_code": f"KPA-KA-{idx:02d}",
                "name": f"Kapal Api {name}",
                "principal_code": "PRIN-SANTOS",
                "fmcg_category": "food",
                "brand_code": "BRD-KA",
                "base_uom": "Pcs",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.080,
                "volume_cbm": 0.0003,
                "barcode": f"8991001100{idx:02d}",
                "description": desc,
            }
        )

    abc_sub = [
        ("Kopi Susu 31g", 10, 120, 1400, 1700, "Kopi Susu Melegenda"),
        ("Kopi Moka 31g", 10, 120, 1400, 1700, "Kopi Moka Manis"),
        ("Plus Gula 25g", 10, 120, 1200, 1500, "Kopi Hitam Gula"),
        ("Brownies Kopi 27g", 10, 120, 1600, 1900, "Kopi Rasa Kue Brownies"),
        ("White Coffee 20g", 10, 120, 1400, 1700, "Kopi Putih Nikmat"),
        ("Kopi Klepon 25g", 10, 120, 1600, 1900, "Kopi Rasa Tradisional Klepon"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(abc_sub, start=1):
        products.append(
            {
                "default_code": f"KPA-ABC-{idx:02d}",
                "name": f"Kopi ABC {name}",
                "principal_code": "PRIN-SANTOS",
                "fmcg_category": "food",
                "brand_code": "BRD-ABC",
                "base_uom": "Sachet",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.035,
                "volume_cbm": 0.00018,
                "barcode": f"8991001200{idx:02d}",
                "description": desc,
            }
        )

    # Ya & Kapten
    products.append(
        {
            "default_code": "KPA-YA-01",
            "name": "Kopi Ya! Susu Sachet 25g",
            "principal_code": "PRIN-SANTOS",
            "fmcg_category": "food",
            "brand_code": "BRD-YA",
            "base_uom": "Sachet",
            "purchase_uom": "Karton",
            "inner_qty": 10,
            "carton_qty": 120,
            "cost_price": 950,
            "list_price": 1200,
            "weight_kg": 0.025,
            "volume_cbm": 0.00015,
            "barcode": "899100130001",
            "description": "Kopi Susu Ekonomis Kios",
        }
    )
    products.append(
        {
            "default_code": "KPA-YA-02",
            "name": "Kopi Ya! Hitam Manis 20g",
            "principal_code": "PRIN-SANTOS",
            "fmcg_category": "food",
            "brand_code": "BRD-YA",
            "base_uom": "Sachet",
            "purchase_uom": "Karton",
            "inner_qty": 10,
            "carton_qty": 120,
            "cost_price": 850,
            "list_price": 1100,
            "weight_kg": 0.020,
            "volume_cbm": 0.00015,
            "barcode": "899100130002",
            "description": "Kopi Hitam Gula Ekonomis",
        }
    )

    kapten_sub = [
        ("Hitam Mantap 60g", 1, 40, 4200, 5000, "Kopi Bubuk Sedang"),
        ("Kopi Murni 150g", 1, 24, 9800, 11500, "Kopi Murni Robusta"),
        ("Plus Gula 25g", 10, 120, 1100, 1350, "Kopi Hitam Gula Sachet"),
        ("Kopi Susu 28g", 10, 120, 1300, 1600, "Kopi Susu Mantap"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(kapten_sub, start=1):
        products.append(
            {
                "default_code": f"KPA-KPT-{idx:02d}",
                "name": f"Kopi Kapten {name}",
                "principal_code": "PRIN-SANTOS",
                "fmcg_category": "food",
                "brand_code": "BRD-KPT",
                "base_uom": "Pcs",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.070,
                "volume_cbm": 0.00025,
                "barcode": f"8991001400{idx:02d}",
                "description": desc,
            }
        )

    # Kapal Api RTD & ABC RTD (8)
    rtd_santos = [
        ("Kapal Api Signature Black Botol 200ml", "BRD-KA", 1, 24, 5500, 6500, "Kopi Hitam Dingin"),
        ("Kapal Api White Coffee Botol 200ml", "BRD-KA", 1, 24, 5800, 7000, "Kopi Putih Dingin"),
        ("Kapal Api Kopi Susu Kaleng 240ml", "BRD-KA", 1, 24, 7500, 8800, "Kopi Susu Kaleng Premium"),
        ("Kapal Api Cold Brew Can 240ml", "BRD-KA", 1, 24, 8200, 9500, "Kopi Cold Brew Ekstraktif"),
        ("ABC Choco Malt Tetra Pack 200ml", "BRD-ABC", 1, 24, 4500, 5300, "Minuman Malt Cokelat Susu"),
        ("ABC Coffee Latte Tetra 200ml", "BRD-ABC", 1, 24, 4500, 5300, "Latte Kemasan Kotak"),
        ("ABC Kopi Moka Botol 250ml", "BRD-ABC", 1, 24, 6000, 7000, "Kopi Moka Siap Minum"),
        ("ABC Kopi Susu Botol 250ml", "BRD-ABC", 1, 24, 6000, 7000, "Kopi Susu Siap Minum"),
    ]
    for idx, (name, brd, in_q, ctn_q, cp, lp, desc) in enumerate(rtd_santos, start=1):
        products.append(
            {
                "default_code": f"KPA-RTD-{idx:02d}",
                "name": name,
                "principal_code": "PRIN-SANTOS",
                "fmcg_category": "rtd",
                "brand_code": brd,
                "base_uom": "Botol",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.240,
                "volume_cbm": 0.0007,
                "barcode": f"8991001500{idx:02d}",
                "description": desc,
            }
        )

    # --- 3. UNILEVER (42 SKU) ---
    # Home Care (16)
    sunlight_sub = [
        ("Jeruk Nipis Pouch 650ml", 2, 24, 13500, 15500, "Pencuci Piring Jeruk Nipis"),
        ("Jeruk Nipis Pouch 210ml", 1, 48, 5200, 6000, "Kemasan Ekonomis Kios"),
        ("Habbatussauda 650ml", 2, 24, 14000, 16000, "Pembersih dengan Anti Bakteri Habbatus"),
        ("Ekstra Higienis 650ml", 2, 24, 14200, 16500, "Formula Higienis Sayur & Buah"),
        ("Botol Pompa 750ml", 1, 12, 19500, 22500, "Kemasan Botol Meja"),
        ("Biocare Alami 650ml", 2, 24, 14500, 17000, "Formula Ramah Lingkungan"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(sunlight_sub, start=1):
        products.append(
            {
                "default_code": f"ULV-SNL-{idx:02d}",
                "name": f"Sunlight {name}",
                "principal_code": "PRIN-UNILEVER",
                "fmcg_category": "home_care",
                "brand_code": "BRD-SNL",
                "base_uom": "Pouch",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.680,
                "volume_cbm": 0.0011,
                "barcode": f"8999999100{idx:02d}",
                "description": desc,
            }
        )

    rinso_sub = [
        ("Anti Noda Klasik Bubuk 770g", 1, 12, 21500, 24500, "Deterjen Bubuk Bersih Cemerlang"),
        ("Molto Rose Fresh 770g", 1, 12, 22000, 25000, "Deterjen Harum Bunga"),
        ("Cair Konsentrat Refill 750ml", 2, 12, 18500, 21000, "Deterjen Cair Anti Noda"),
        ("Matic Front Load Cair 1.6L", 1, 6, 42000, 48000, "Khusus Mesin Cuci Bukaan Depan"),
        ("Matic Top Load Cair 1.6L", 1, 6, 38000, 44000, "Khusus Mesin Cuci Bukaan Atas"),
        ("Japanese Peach Cair 700ml", 2, 12, 19000, 22000, "Deterjen Wangi Buah Peach"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(rinso_sub, start=1):
        products.append(
            {
                "default_code": f"ULV-RNS-{idx:02d}",
                "name": f"Rinso {name}",
                "principal_code": "PRIN-UNILEVER",
                "fmcg_category": "home_care",
                "brand_code": "BRD-RNS",
                "base_uom": "Pouch",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.800,
                "volume_cbm": 0.0015,
                "barcode": f"8999999200{idx:02d}",
                "description": desc,
            }
        )

    molto_sub = [
        ("All-in-1 Blue Refill 720ml", 2, 12, 17500, 20000, "Pelembut & Pewangi Pakaian Biru"),
        ("All-in-1 Pink Refill 720ml", 2, 12, 17500, 20000, "Pelembut Wangi Mawar Merah"),
        ("Floral Bliss Refill 780ml", 2, 12, 16000, 18500, "Pewangi Konsentrat"),
        ("Pure Softener Bayi 720ml", 2, 12, 19000, 22000, "Formula Lembut Kulit Sensitif"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(molto_sub, start=1):
        products.append(
            {
                "default_code": f"ULV-MLT-{idx:02d}",
                "name": f"Molto {name}",
                "principal_code": "PRIN-UNILEVER",
                "fmcg_category": "home_care",
                "brand_code": "BRD-MLT",
                "base_uom": "Pouch",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.750,
                "volume_cbm": 0.0012,
                "barcode": f"8999999300{idx:02d}",
                "description": desc,
            }
        )

    # Personal Care (20)
    lifebuoy_sub = [
        ("Sabun Batang Total 10 110g", 3, 72, 3800, 4500, "Sabun Mandi Anti Bakteri Merah"),
        ("Sabun Batang Lemon 110g", 3, 72, 3800, 4500, "Sabun Mandi Kesegaran Lemon"),
        ("Sabun Batang Mild Care 110g", 3, 72, 3800, 4500, "Sabun Mandi Susu Lembut"),
        ("Bodywash Refill Total 10 450ml", 1, 24, 21000, 24000, "Sabun Cair Pouch"),
        ("Bodywash Refill Lemon 450ml", 1, 24, 21000, 24000, "Sabun Cair Lemon Fresh Pouch"),
        ("Shampoo Rambut Sehat 170ml", 1, 24, 18500, 21500, "Sampo Rambut Kuat Berkilau"),
        ("Shampoo Anti Dandruff 170ml", 1, 24, 19500, 22500, "Sampo Bebas Ketombe"),
        ("Hand Sanitizer Gel 50ml", 1, 48, 7500, 9000, "Pembersih Tangan Higienis"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(lifebuoy_sub, start=1):
        products.append(
            {
                "default_code": f"ULV-LFB-{idx:02d}",
                "name": f"Lifebuoy {name}",
                "principal_code": "PRIN-UNILEVER",
                "fmcg_category": "personal_care",
                "brand_code": "BRD-LFB",
                "base_uom": "Pcs",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.120,
                "volume_cbm": 0.0003,
                "barcode": f"8999999400{idx:02d}",
                "description": desc,
            }
        )

    pepsodent_sub = [
        ("Pencegah Gigi Berlubang 190g", 1, 72, 11500, 13500, "Pasta Gigi Perlindungan Maksimal"),
        ("Pencegah Gigi Berlubang 120g", 1, 72, 8500, 10000, "Pasta Gigi Sedang"),
        ("Pencegah Gigi Berlubang 75g", 1, 72, 5500, 6500, "Pasta Gigi Ekonomis"),
        ("Herbal Alami 190g", 1, 72, 14500, 17000, "Pasta Gigi Daun Sirih & Garam"),
        ("Complete 8 Multi Action 150g", 1, 72, 16000, 18500, "Pasta Gigi Komplit Perlindungan"),
        ("White Action Double 190g", 1, 72, 15000, 17500, "Gigi Putih Alami Bersinar"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(pepsodent_sub, start=1):
        products.append(
            {
                "default_code": f"ULV-PSD-{idx:02d}",
                "name": f"Pepsodent {name}",
                "principal_code": "PRIN-UNILEVER",
                "fmcg_category": "personal_care",
                "brand_code": "BRD-PSD",
                "base_uom": "Pcs",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.210,
                "volume_cbm": 0.0004,
                "barcode": f"8999999500{idx:02d}",
                "description": desc,
            }
        )

    clear_sub = [
        ("Ice Cool Menthol 160ml", 1, 24, 23000, 26500, "Sampo Dingin Anti Ketombe"),
        ("Complete Soft Care 160ml", 1, 24, 23000, 26500, "Sampo Lembut Kulit Kepala"),
        ("Men Cool Sport Menthol 160ml", 1, 24, 24000, 27500, "Khusus Pria Aktif"),
        ("Men Anti Hairfall 160ml", 1, 24, 24000, 27500, "Pengurang Rambut Rontok"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(clear_sub, start=1):
        products.append(
            {
                "default_code": f"ULV-CLR-{idx:02d}",
                "name": f"Clear Shampoo {name}",
                "principal_code": "PRIN-UNILEVER",
                "fmcg_category": "personal_care",
                "brand_code": "BRD-CLR",
                "base_uom": "Botol",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.180,
                "volume_cbm": 0.0005,
                "barcode": f"8999999600{idx:02d}",
                "description": desc,
            }
        )

    products.append(
        {
            "default_code": "ULV-RXN-01",
            "name": "Rexona Men Roll On Invisible Dry 45ml",
            "principal_code": "PRIN-UNILEVER",
            "fmcg_category": "personal_care",
            "brand_code": "BRD-RXN",
            "base_uom": "Botol",
            "purchase_uom": "Karton",
            "inner_qty": 6,
            "carton_qty": 36,
            "cost_price": 17500,
            "list_price": 20500,
            "weight_kg": 0.065,
            "volume_cbm": 0.0002,
            "barcode": "899999970001",
            "description": "Deodoran Pria Tanpa Noda",
        }
    )
    products.append(
        {
            "default_code": "ULV-RXN-02",
            "name": "Rexona Women Brightening Roll On 45ml",
            "principal_code": "PRIN-UNILEVER",
            "fmcg_category": "personal_care",
            "brand_code": "BRD-RXN",
            "base_uom": "Botol",
            "purchase_uom": "Karton",
            "inner_qty": 6,
            "carton_qty": 36,
            "cost_price": 17500,
            "list_price": 20500,
            "weight_kg": 0.065,
            "volume_cbm": 0.0002,
            "barcode": "899999970002",
            "description": "Deodoran Wanita Mencerahkan",
        }
    )

    # Food / Bumbu Dapur (6)
    royco_sub = [
        ("Bumbu Pelezat Rasa Ayam 230g", 1, 40, 8500, 10000, "Kaldu Ayam Alami"),
        ("Bumbu Pelezat Rasa Sapi 230g", 1, 40, 8500, 10000, "Kaldu Sapi Gurih"),
        ("Kaldu Spesial Jamur 100g", 1, 40, 6500, 7800, "Kaldu Vegetarian Jamur"),
        ("Bumbu Kuah Bakso 100g", 1, 40, 6000, 7200, "Bumbu Kuah Spesial Bakso"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(royco_sub, start=1):
        products.append(
            {
                "default_code": f"ULV-RYC-{idx:02d}",
                "name": f"Royco {name}",
                "principal_code": "PRIN-UNILEVER",
                "fmcg_category": "food",
                "brand_code": "BRD-RYC",
                "base_uom": "Pouch",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.240,
                "volume_cbm": 0.0005,
                "barcode": f"8999999800{idx:02d}",
                "description": desc,
            }
        )

    products.append(
        {
            "default_code": "ULV-BNG-01",
            "name": "Bango Kecap Manis Pouch Refill 550ml",
            "principal_code": "PRIN-UNILEVER",
            "fmcg_category": "food",
            "brand_code": "BRD-BNG",
            "base_uom": "Pouch",
            "purchase_uom": "Karton",
            "inner_qty": 1,
            "carton_qty": 24,
            "cost_price": 21000,
            "list_price": 24000,
            "weight_kg": 0.720,
            "volume_cbm": 0.0012,
            "barcode": "899999990001",
            "description": "Kecap Kedelai Hitam Malika",
        }
    )
    products.append(
        {
            "default_code": "ULV-BNG-02",
            "name": "Bango Kecap Manis Pouch Refill 220ml",
            "principal_code": "PRIN-UNILEVER",
            "fmcg_category": "food",
            "brand_code": "BRD-BNG",
            "base_uom": "Pouch",
            "purchase_uom": "Karton",
            "inner_qty": 1,
            "carton_qty": 48,
            "cost_price": 9500,
            "list_price": 11000,
            "weight_kg": 0.280,
            "volume_cbm": 0.0006,
            "barcode": "899999990002",
            "description": "Kecap Manis Kemasan Sedang",
        }
    )

    # --- 4. WINGS FOOD (32 SKU) ---
    sedaap_sub = [
        ("Goreng 90g", 40, 2700, 3100, "Mie Goreng Bawang Renyah"),
        ("Kuah Rasa Soto 75g", 40, 2500, 2900, "Mie Kuah Rasa Soto Segar"),
        ("Kuah Ayam Bawang 70g", 40, 2500, 2900, "Mie Kuah Kaldu Gurih"),
        ("Kuah Kari Spesial 72g", 40, 2600, 3000, "Kari Kental Kaya Rempah"),
        ("Korean Spicy Chicken 87g", 40, 3000, 3500, "Pedas Korea Level 1-2"),
        ("Korean Spicy Soup 75g", 40, 3000, 3500, "Kuah Pedas Hangat Korea"),
        ("Singapore Spicy Laksa 83g", 40, 3100, 3600, "Laksa Santan Gurih"),
        ("Rawon Asli Jawa Timur 80g", 40, 2900, 3400, "Kuah Hitam Khas Rawon"),
        ("Cup Goreng 85g", 24, 4500, 5200, "Mie Cup Praktis"),
        ("Cup Soto 81g", 24, 4400, 5100, "Mie Cup Kuah Soto"),
        ("Cup Rawon 81g", 24, 4600, 5300, "Mie Cup Kuah Rawon"),
        ("Sambal Goreng 88g", 40, 2800, 3200, "Mie Rasa Sambal Nikmat"),
    ]
    for idx, (name, ctn_q, cp, lp, desc) in enumerate(sedaap_sub, start=1):
        products.append(
            {
                "default_code": f"WNG-SDP-{idx:02d}",
                "name": f"Mie Sedaap {name}",
                "principal_code": "PRIN-WINGS",
                "fmcg_category": "food",
                "brand_code": "BRD-SDP",
                "base_uom": "Pcs",
                "purchase_uom": "Karton",
                "inner_qty": 1,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.090,
                "volume_cbm": 0.0005,
                "barcode": f"8998866100{idx:02d}",
                "description": desc,
            }
        )

    jasjus_sub = [
        ("Jeruk Segar Renceng 10s", 10, 120, 850, 1100, "Minuman Serbuk Buah"),
        ("Mangga Manis Renceng 10s", 10, 120, 850, 1100, "Minuman Rasa Mangga"),
        ("Anggur Merah Renceng 10s", 10, 120, 850, 1100, "Minuman Rasa Anggur"),
        ("Melon Wangi Renceng 10s", 10, 120, 850, 1100, "Minuman Rasa Melon"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(jasjus_sub, start=1):
        products.append(
            {
                "default_code": f"WNG-JSJ-{idx:02d}",
                "name": f"Jasjus {name}",
                "principal_code": "PRIN-WINGS",
                "fmcg_category": "food",
                "brand_code": "BRD-JSJ",
                "base_uom": "Sachet",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.015,
                "volume_cbm": 0.0001,
                "barcode": f"8998866200{idx:02d}",
                "description": desc,
            }
        )

    products.append(
        {
            "default_code": "WNG-SGD-01",
            "name": "Segar Dingin Madu Lemon Box 24s",
            "principal_code": "PRIN-WINGS",
            "fmcg_category": "food",
            "brand_code": "BRD-SGD",
            "base_uom": "Box",
            "purchase_uom": "Karton",
            "inner_qty": 1,
            "carton_qty": 24,
            "cost_price": 18500,
            "list_price": 22000,
            "weight_kg": 0.250,
            "volume_cbm": 0.0006,
            "barcode": "899886630001",
            "description": "Pereda Panas Dalam Alami",
        }
    )
    products.append(
        {
            "default_code": "WNG-SGD-02",
            "name": "Segar Dingin Sirsak Box 24s",
            "principal_code": "PRIN-WINGS",
            "fmcg_category": "food",
            "brand_code": "BRD-SGD",
            "base_uom": "Box",
            "purchase_uom": "Karton",
            "inner_qty": 1,
            "carton_qty": 24,
            "cost_price": 18500,
            "list_price": 22000,
            "weight_kg": 0.250,
            "volume_cbm": 0.0006,
            "barcode": "899886630002",
            "description": "Pereda Panas Dalam Rasa Sirsak",
        }
    )

    top_sub = [
        ("Gula Aren 25g", 10, 120, 1200, 1500, "Kopi Instan Gula Aren"),
        ("Kopi Susu 31g", 10, 120, 1300, 1600, "Kopi Susu Mantap"),
        ("Kopi Moka 31g", 10, 120, 1300, 1600, "Kopi Paduan Cokelat Moka"),
        ("Barista Tubruk 25g", 10, 120, 1100, 1400, "Kopi Tubruk Asli"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(top_sub, start=1):
        products.append(
            {
                "default_code": f"WNG-TOP-{idx:02d}",
                "name": f"Top Kopi {name}",
                "principal_code": "PRIN-WINGS",
                "fmcg_category": "food",
                "brand_code": "BRD-TOP",
                "base_uom": "Sachet",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.030,
                "volume_cbm": 0.00018,
                "barcode": f"8998866400{idx:02d}",
                "description": desc,
            }
        )

    # RTD Wings (10)
    floridina_sub = [
        ("Orange Pulpy 350ml Pet", 1, 24, 3000, 3600, "Jus Jeruk Bulir Nyata"),
        ("Lemon Coco 350ml Pet", 1, 24, 3000, 3600, "Jus Lemon Kelapa"),
        ("Apple Pulpy 350ml Pet", 1, 24, 3000, 3600, "Jus Apel Bulir Segar"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(floridina_sub, start=1):
        products.append(
            {
                "default_code": f"WNG-FLD-{idx:02d}",
                "name": f"Floridina {name}",
                "principal_code": "PRIN-WINGS",
                "fmcg_category": "rtd",
                "brand_code": "BRD-FLD",
                "base_uom": "Botol",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.380,
                "volume_cbm": 0.0010,
                "barcode": f"8998866500{idx:02d}",
                "description": desc,
            }
        )

    javana_sub = [
        ("Gula Batu 350ml Pet", 1, 24, 2800, 3300, "Teh Melati Rasa Gula Batu"),
        ("Melati Asli 350ml Pet", 1, 24, 2800, 3300, "Teh Wangi Melati Murni"),
        ("Less Sugar 350ml Pet", 1, 24, 2800, 3300, "Teh Rendah Gula"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(javana_sub, start=1):
        products.append(
            {
                "default_code": f"WNG-JVN-{idx:02d}",
                "name": f"Teh Javana {name}",
                "principal_code": "PRIN-WINGS",
                "fmcg_category": "rtd",
                "brand_code": "BRD-JVN",
                "base_uom": "Botol",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.380,
                "volume_cbm": 0.0010,
                "barcode": f"8998866600{idx:02d}",
                "description": desc,
            }
        )

    golda_sub = [
        ("Dolce Latte 200ml Pet", 1, 24, 3000, 3500, "Kopi Latte Susu Gurih"),
        ("Cappuccino 200ml Pet", 1, 24, 3000, 3500, "Kopi Cappuccino Dingin"),
        ("Classic Black 200ml Pet", 1, 24, 2800, 3300, "Kopi Hitam Nikmat"),
        ("White Mocha 200ml Pet", 1, 24, 3000, 3500, "Kopi Moka Putih"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(golda_sub, start=1):
        products.append(
            {
                "default_code": f"WNG-GLD-{idx:02d}",
                "name": f"Golda Coffee {name}",
                "principal_code": "PRIN-WINGS",
                "fmcg_category": "rtd",
                "brand_code": "BRD-GLD",
                "base_uom": "Botol",
                "purchase_uom": "Karton",
                "inner_qty": in_q,
                "carton_qty": ctn_q,
                "cost_price": cp,
                "list_price": lp,
                "weight_kg": 0.220,
                "volume_cbm": 0.0006,
                "barcode": f"8998866700{idx:02d}",
                "description": desc,
            }
        )

    return products


def generate_partners() -> list[dict]:
    """Menghasilkan 354 Partner Outlet terstratifikasi (12 MT, 72 GT, 260 RTL, 10 INST)."""
    partners = []

    # 1. Modern Trade (12 Key Accounts)
    mt_accounts = [
        (
            "Indomaret DC Manado",
            "KEC-MND-MPG",
            "KEL-MND-PKB",
            "Jl. AA Maramis KM 10 Paniki",
            "95258",
            "01.234.567.8-054.000",
            250000000,
            "strict",
            45,
            "SLS-01",
            1.5280,
            124.9080,
        ),
        (
            "Alfamidi DC Manado",
            "KEC-MND-MPG",
            "KEL-MND-PKB",
            "Kawasan Pergudangan Kairagi Dua",
            "95254",
            "01.876.543.2-054.000",
            200000000,
            "strict",
            45,
            "SLS-01",
            1.5190,
            124.8970,
        ),
        (
            "FreshMart Superstore Bahu Mall",
            "KEC-MND-MLY",
            "KEL-MND-BAH",
            "Bahu Mall Blok A No. 1",
            "95115",
            "02.111.222.3-821.000",
            120000000,
            "limit",
            30,
            "SLS-01",
            1.4580,
            124.8250,
        ),
        (
            "FreshMart Lifestyle Paniki",
            "KEC-MND-MPG",
            "KEL-MND-PKB",
            "Grand Kawanua City Walk",
            "95258",
            "02.111.222.3-821.001",
            80000000,
            "limit",
            30,
            "SLS-01",
            1.5210,
            124.9010,
        ),
        (
            "FreshMart Express Tikala",
            "KEC-MND-TKL",
            "KEL-MND-TKB",
            "Jl. Balai Kota No. 12",
            "95126",
            "02.111.222.3-821.002",
            50000000,
            "limit",
            30,
            "SLS-01",
            1.4815,
            124.8580,
        ),
        (
            "MultiMart Megamas Manado",
            "KEC-MND-WNG",
            "KEL-MND-WNS",
            "Kawasan Megamas Blok 1D",
            "95111",
            "03.444.555.6-821.000",
            100000000,
            "limit",
            30,
            "SLS-01",
            1.4880,
            124.8350,
        ),
        (
            "MultiMart Sam Ratulangi",
            "KEC-MND-WNA",
            "KEL-MND-WNS",
            "Jl. Sam Ratulangi No. 188",
            "95117",
            "03.444.555.6-821.001",
            75000000,
            "limit",
            30,
            "SLS-01",
            1.4750,
            124.8410,
        ),
        (
            "MultiMart Tomohon",
            "KEC-TMH-TGH",
            "KEL-TMH-PSL",
            "Jl. Raya Tomohon-Manado",
            "95431",
            "03.444.555.6-821.002",
            50000000,
            "limit",
            30,
            "SLS-01",
            1.3250,
            124.8390,
        ),
        (
            "Golden Swalayan Pasar 45",
            "KEC-MND-WNG",
            "KEL-MND-CLC",
            "Jl. Sam Ratulangi No. 12 Calaca",
            "95112",
            "04.777.888.9-821.000",
            80000000,
            "limit",
            14,
            "SLS-01",
            1.4925,
            124.8421,
        ),
        (
            "Jumbo Swalayan Pasar 45",
            "KEC-MND-WNG",
            "KEL-MND-CLC",
            "Kawasan Pasar 45 Manado",
            "95112",
            "05.999.000.1-821.000",
            50000000,
            "limit",
            14,
            "SLS-01",
            1.4930,
            124.8418,
        ),
        (
            "Jumbo Swalayan Bitung",
            "KEC-BTG-MAS",
            "KEL-BTG-BTM",
            "Jl. Sam Ratulangi Bitung Timur",
            "95521",
            "05.999.000.1-821.002",
            40000000,
            "limit",
            14,
            "SLS-01",
            1.4420,
            125.1880,
        ),
        (
            "Transmart Star Square Bahu",
            "KEC-MND-MLY",
            "KEL-MND-BAH",
            "Star Square Mall Bahu",
            "95115",
            "06.222.333.4-054.000",
            40000000,
            "strict",
            45,
            "SLS-01",
            1.4590,
            124.8260,
        ),
    ]
    for idx, (name, dist, subdist, street, zipc, npwp, cl, cm, pt, sls, lat, lng) in enumerate(mt_accounts, start=1):
        partners.append(
            {
                "ref": f"CUST-MT-{idx:02d}",
                "name": name,
                "channel_code": "MT",
                "tier_code": "PLATINUM",
                "district_code": dist,
                "subdistrict_code": subdist,
                "street": street,
                "zip": zipc,
                "vat": npwp,
                "credit_limit": cl,
                "credit_mode": cm,
                "payment_term_days": pt,
                "salesman_code": sls,
                "latitude": lat,
                "longitude": lng,
                "is_company": True,
            }
        )

    # 2. General Trade (72 Grosir & Sembako)
    gt_samples = [
        (
            "Toko Sembako Berkat Pasar 45",
            "KEC-MND-WNG",
            "KEL-MND-CLC",
            "Pasar 45 Calaca",
            "95112",
            "SLS-02",
            1.4920,
            124.8425,
        ),
        (
            "Toko Harapan Bersehati",
            "KEC-MND-WNG",
            "KEL-MND-CLC",
            "Jl. Nusantara No. 5",
            "95112",
            "SLS-02",
            1.4935,
            124.8430,
        ),
        (
            "Grosir Bintang Samrat",
            "KEC-MND-SRO",
            "KEL-MND-SKB",
            "Jl. Sam Ratulangi Sario",
            "95114",
            "SLS-02",
            1.4720,
            124.8315,
        ),
        (
            "Grosir Krida Bahu",
            "KEC-MND-MLY",
            "KEL-MND-BAH",
            "Jl. Wolter Monginsidi Bahu",
            "95115",
            "SLS-02",
            1.4575,
            124.8240,
        ),
        ("Grosir Tikala Baru", "KEC-MND-TKL", "KEL-MND-TKB", "Jl. Tikala Ares", "95126", "SLS-03", 1.4820, 124.8575),
        (
            "Toko Paal Dua Jaya",
            "KEC-MND-PLD",
            "KEL-MND-PLD",
            "Jl. Yos Sudarso Paal Dua",
            "95129",
            "SLS-03",
            1.4865,
            124.8685,
        ),
        (
            "Grosir Sumber Mulia Tuminting",
            "KEC-MND-TMT",
            "KEL-MND-TMT",
            "Jl. Hasanuddin Tuminting",
            "95239",
            "SLS-03",
            1.5045,
            124.8495,
        ),
        (
            "Toko Bintang Matuari Maesa",
            "KEC-BTG-MAS",
            "KEL-BTG-BTM",
            "Kompleks Pasar Tua Maesa",
            "95521",
            "SLS-04",
            1.4415,
            125.1875,
        ),
        (
            "Toko Jaya Sejahtera Tomohon",
            "KEC-TMH-TGH",
            "KEL-TMH-PSL",
            "Pasar Beriman Tomohon",
            "95431",
            "SLS-04",
            1.3245,
            124.8385,
        ),
        (
            "Toko Berkat Kawangkoan",
            "KEC-MNH-KWG",
            "KEL-MNH-SDG",
            "Pasar Kawangkoan Sendangan",
            "95671",
            "SLS-04",
            1.2175,
            124.7885,
        ),
        (
            "Toko Rezeki Tondano",
            "KEC-MNH-TDN",
            "KEL-MNH-RNG",
            "Jl. Sam Ratulangi Tondano",
            "95618",
            "SLS-04",
            1.3045,
            124.9115,
        ),
        (
            "Grosir Kauditan Makmur",
            "KEC-MNT-AMD",
            "KEL-MNT-AMA",
            "Jl. Raya Manado-Bitung Kauditan",
            "95371",
            "SLS-04",
            1.4275,
            124.9775,
        ),
    ]
    # Replicate GT to 72 outlets
    gt_districts = [
        ("KEC-MND-WNG", "KEL-MND-CLC", "Wenang", "SLS-02"),
        ("KEC-MND-SRO", "KEL-MND-SKB", "Sario", "SLS-02"),
        ("KEC-MND-MLY", "KEL-MND-BAH", "Malalayang", "SLS-02"),
        ("KEC-MND-WNA", "KEL-MND-WNS", "Wanea", "SLS-02"),
        ("KEC-MND-TKL", "KEL-MND-TKB", "Tikala", "SLS-03"),
        ("KEC-MND-PLD", "KEL-MND-PLD", "Paal Dua", "SLS-03"),
        ("KEC-MND-TMT", "KEL-MND-TMT", "Tuminting", "SLS-03"),
        ("KEC-MND-SKL", "KEL-MND-TMT", "Singkil", "SLS-03"),
        ("KEC-MND-MPG", "KEL-MND-PKB", "Mapanget", "SLS-03"),
        ("KEC-BTG-MAS", "KEL-BTG-BTM", "Bitung Maesa", "SLS-04"),
        ("KEC-TMH-TGH", "KEL-TMH-PSL", "Tomohon", "SLS-04"),
        ("KEC-MNH-KWG", "KEL-MNH-SDG", "Kawangkoan", "SLS-04"),
    ]
    for idx in range(1, 73):
        if idx <= len(gt_samples):
            name, dist, subdist, street, zip_code, sls, lat, lng = gt_samples[idx - 1]
            t_name = name
        else:
            dist, subdist, dname, sls = gt_districts[(idx - 1) % len(gt_districts)]
            t_name = f"Toko Sembako Grosir {dname} {idx:02d}"
            street = f"Jl. Raya Niaga No. {idx * 3}"
            zip_code = "95100"
            lat = 1.4800 + (idx * 0.001)
            lng = 124.8400 + (idx * 0.001)

        partners.append(
            {
                "ref": f"CUST-GT-{idx:02d}",
                "name": t_name,
                "channel_code": "GT",
                "tier_code": "GOLD" if idx <= 25 else "SILVER",
                "district_code": dist,
                "subdistrict_code": subdist,
                "street": street,
                "zip": zip_code,
                "vat": f"08.{idx:03d}.123.4-821.000",
                "credit_limit": 45000000 if idx <= 25 else 25000000,
                "credit_mode": "limit",
                "payment_term_days": 14 if idx <= 25 else 7,
                "salesman_code": sls,
                "latitude": lat,
                "longitude": lng,
                "is_company": True,
            }
        )

    # 3. Retail Kios Canvass (260 Kios)
    for idx in range(1, 261):
        sls = "CVS-01" if idx <= 135 else "CVS-02"
        dist = (
            "KEC-MND-WNG"
            if idx <= 70
            else ("KEC-MND-MLY" if idx <= 135 else ("KEC-MND-MPG" if idx <= 200 else "KEC-MNT-AMD"))
        )
        subdist = "KEL-MND-WNS" if idx <= 70 else ("KEL-MND-BAH" if idx <= 135 else "KEL-MND-PKB")
        owner = ["Tin", "Oce", "Utu", "Meyke", "Ferry", "Dani", "Ventje", "Novry", "Ritha"][idx % 9]
        partners.append(
            {
                "ref": f"CUST-RTL-{idx:03d}",
                "name": f"Kios Tante {owner} {idx:03d}",
                "channel_code": "RTL",
                "tier_code": "BRONZE",
                "district_code": dist,
                "subdistrict_code": subdist,
                "street": f"Lorong Pemukiman RW 0{idx % 6 + 1}",
                "zip": "95100",
                "vat": "",
                "credit_limit": 1500000,
                "credit_mode": "strict",
                "payment_term_days": 0,  # Cash COD
                "salesman_code": sls,
                "latitude": 1.4850 + (idx * 0.0005),
                "longitude": 124.8450 + (idx * 0.0005),
                "is_company": False,
            }
        )

    # 4. Institusional (10 Outlet Horeka & RS)
    inst_samples = [
        (
            "RSUP Prof. Dr. R. D. Kandou",
            "KEC-MND-MLY",
            "KEL-MND-BAH",
            "Jl. Raya Tanawangko Malalayang",
            "95162",
            "01.123.456.7-821.000",
            60000000,
            30,
        ),
        (
            "Four Points by Sheraton Manado",
            "KEC-MND-SRO",
            "KEL-MND-SKB",
            "Jl. Sam Ratulangi Sario",
            "95114",
            "02.345.678.9-821.000",
            45000000,
            30,
        ),
        (
            "Hotel Sintesa Peninsula",
            "KEC-MND-WNG",
            "KEL-MND-WNS",
            "Jl. Jend. Sudirman Wenang",
            "95111",
            "03.567.890.1-821.000",
            40000000,
            30,
        ),
        (
            "Hotel Grand Puri Manado",
            "KEC-MND-SRO",
            "KEL-MND-SKB",
            "Jl. Sam Ratulangi No. 458",
            "95114",
            "04.789.012.3-821.000",
            30000000,
            30,
        ),
        (
            "Novotel Manado Golf Resort",
            "KEC-MND-MPG",
            "KEL-MND-PKB",
            "Grand Kawanua International City",
            "95258",
            "05.890.123.4-821.000",
            35000000,
            30,
        ),
        (
            "RS Siloam Hospitals Manado",
            "KEC-MND-WNG",
            "KEL-MND-WNS",
            "Jl. Sam Ratulangi No. 22",
            "95111",
            "06.901.234.5-821.000",
            35000000,
            30,
        ),
        (
            "Katering Minahasa Indah",
            "KEC-MND-TKL",
            "KEL-MND-TKB",
            "Jl. Tikala Ares No. 8",
            "95126",
            "07.012.345.6-821.000",
            25000000,
            14,
        ),
        (
            "Katering Bahu Sejahtera",
            "KEC-MND-MLY",
            "KEL-MND-BAH",
            "Jl. Wolter Monginsidi No. 12",
            "95115",
            "08.123.456.7-821.000",
            20000000,
            14,
        ),
        (
            "Restoran Raja Sate Megamas",
            "KEC-MND-WNG",
            "KEL-MND-WNS",
            "Kawasan Megamas Blok 2C",
            "95111",
            "09.234.567.8-821.000",
            20000000,
            14,
        ),
        (
            "Dapur Minahasa Tomohon",
            "KEC-TMH-TGH",
            "KEL-TMH-PSL",
            "Jl. Raya Paslaten Tomohon",
            "95431",
            "10.345.678.9-821.000",
            15000000,
            14,
        ),
    ]
    for idx, (name, dist, subdist, street, zipc, npwp, cl, pt) in enumerate(inst_samples, start=1):
        partners.append(
            {
                "ref": f"CUST-INST-{idx:02d}",
                "name": name,
                "channel_code": "INST",
                "tier_code": "GOLD",
                "district_code": dist,
                "subdistrict_code": subdist,
                "street": street,
                "zip": zipc,
                "vat": npwp,
                "credit_limit": cl,
                "credit_mode": "limit",
                "payment_term_days": pt,
                "salesman_code": "MGT-01",
                "latitude": 1.4800,
                "longitude": 124.8400,
                "is_company": True,
            }
        )

    return partners


def generate_employees() -> list[dict]:
    """Menghasilkan roster 24 personel PT Manado Distribusi Utama."""
    return [
        {
            "code": "EMP-001",
            "name": "Bpk. Teddy Kolondam",
            "role": "owner",
            "dept": "Management",
            "cost_center": "CC-MGT",
            "sim": "",
        },
        {
            "code": "EMP-002",
            "name": "Hendrik Polii",
            "role": "branch_manager",
            "dept": "Management",
            "cost_center": "CC-MGT",
            "sim": "SIM A",
        },
        {
            "code": "EMP-003",
            "name": "Feybe Lumempouw",
            "role": "finance_lead",
            "dept": "Finance",
            "cost_center": "CC-FIN",
            "sim": "SIM A",
        },
        {
            "code": "EMP-004",
            "name": "Grace Sumual",
            "role": "accounting_staff",
            "dept": "Finance",
            "cost_center": "CC-FIN",
            "sim": "",
        },
        {
            "code": "EMP-005",
            "name": "Rudi Tumbelaka",
            "role": "tax_staff",
            "dept": "Finance",
            "cost_center": "CC-FIN",
            "sim": "",
        },
        {
            "code": "EMP-006",
            "name": "Meike Wondal",
            "role": "cashier",
            "dept": "Finance",
            "cost_center": "CC-FIN",
            "sim": "",
        },
        {
            "code": "EMP-007",
            "name": "Joni Kumajas",
            "role": "sales_spv",
            "dept": "Sales",
            "cost_center": "CC-SALES",
            "sim": "SIM A",
        },
        {
            "code": "EMP-008",
            "name": "Rivaldo Mamahit",
            "role": "sales_admin_lead",
            "dept": "Sales",
            "cost_center": "CC-SALES",
            "sim": "",
        },
        {
            "code": "EMP-009",
            "name": "Priscilia Tielung",
            "role": "sales_admin",
            "dept": "Sales",
            "cost_center": "CC-SALES",
            "sim": "",
        },
        {
            "code": "EMP-010",
            "name": "Willem Runtu",
            "role": "warehouse_lead",
            "dept": "Warehouse",
            "cost_center": "CC-WMS",
            "sim": "SIM B1",
        },
        {
            "code": "EMP-011",
            "name": "Jemmy Pangaila",
            "role": "staging_lead",
            "dept": "Warehouse",
            "cost_center": "CC-WMS",
            "sim": "",
        },
        {
            "code": "EMP-012",
            "name": "Robby Karundeng",
            "role": "picker_staff",
            "dept": "Warehouse",
            "cost_center": "CC-WMS",
            "sim": "",
        },
        {
            "code": "EMP-013",
            "name": "Christian Wowor",
            "role": "sales_mt",
            "dept": "Sales",
            "cost_center": "CC-SALES",
            "sim": "SIM A",
        },
        {
            "code": "EMP-014",
            "name": "Andre Pangemanan",
            "role": "sales_to",
            "dept": "Sales",
            "cost_center": "CC-SALES",
            "sim": "SIM C & A",
        },
        {
            "code": "EMP-015",
            "name": "Meidy Wowor",
            "role": "sales_to",
            "dept": "Sales",
            "cost_center": "CC-SALES",
            "sim": "SIM C & A",
        },
        {
            "code": "EMP-016",
            "name": "Refly Sondakh",
            "role": "sales_to",
            "dept": "Sales",
            "cost_center": "CC-SALES",
            "sim": "SIM C & A",
        },
        {
            "code": "EMP-017",
            "name": "Novry Mandagi",
            "role": "sales_canvass",
            "dept": "Sales",
            "cost_center": "CC-SALES",
            "sim": "SIM A",
        },
        {
            "code": "EMP-018",
            "name": "Steven Lumenta",
            "role": "sales_canvass",
            "dept": "Sales",
            "cost_center": "CC-SALES",
            "sim": "SIM A",
        },
        {
            "code": "EMP-019",
            "name": "Eko Prasetyo",
            "role": "driver",
            "dept": "Logistik",
            "cost_center": "CC-LOG",
            "sim": "SIM B1",
        },
        {
            "code": "EMP-020",
            "name": "Frits Wenas",
            "role": "driver",
            "dept": "Logistik",
            "cost_center": "CC-LOG",
            "sim": "SIM B1",
        },
        {
            "code": "EMP-021",
            "name": "Stenly Rompas",
            "role": "driver",
            "dept": "Logistik",
            "cost_center": "CC-LOG",
            "sim": "SIM B1",
        },
        {
            "code": "EMP-022",
            "name": "Johan Rori",
            "role": "driver",
            "dept": "Logistik",
            "cost_center": "CC-LOG",
            "sim": "SIM B2",
        },
        {
            "code": "EMP-023",
            "name": "Maxi Walangitan",
            "role": "helper",
            "dept": "Logistik",
            "cost_center": "CC-LOG",
            "sim": "",
        },
        {
            "code": "EMP-024",
            "name": "Royke Manopo",
            "role": "helper",
            "dept": "Logistik",
            "cost_center": "CC-LOG",
            "sim": "",
        },
    ]


def generate_vehicles() -> list[dict]:
    """Menghasilkan master 9 armada logistik."""
    return [
        {
            "plate": "DB 8123 QA",
            "type": "GM_BV",
            "model": "Daihatsu Gran Max BV 1.3",
            "cbm": 3.6,
            "ton": 0.75,
            "route": "Canvassing Urban",
            "driver": "Novry Mandagi",
            "stnk_exp": "2027-05-14",
            "kir_exp": "2026-11-18",
        },
        {
            "plate": "DB 8234 QX",
            "type": "GM_BOX",
            "model": "Daihatsu Gran Max Box 1.5",
            "cbm": 4.7,
            "ton": 1.0,
            "route": "Canvassing Sub-Urban",
            "driver": "Steven Lumenta",
            "stnk_exp": "2028-08-22",
            "kir_exp": "2026-12-05",
        },
        {
            "plate": "DB 8345 PL",
            "type": "GM_OPEN",
            "model": "Daihatsu Gran Max Bak 1.5",
            "cbm": 3.5,
            "ton": 1.0,
            "route": "Staging Cepat & Retur",
            "driver": "Boyke Tendean",
            "stnk_exp": "2026-11-10",
            "kir_exp": "2026-10-28",
        },
        {
            "plate": "DB 8456 FB",
            "type": "L300",
            "model": "Mitsubishi L300 Box Euro 4",
            "cbm": 5.4,
            "ton": 1.5,
            "route": "Delivery Urban Barat",
            "driver": "Eko Prasetyo",
            "stnk_exp": "2027-03-19",
            "kir_exp": "2026-09-15",
        },
        {
            "plate": "DB 8567 TR",
            "type": "TRAGA",
            "model": "Isuzu Traga Box Euro 4",
            "cbm": 6.1,
            "ton": 1.8,
            "route": "Delivery Urban Timur",
            "driver": "Frits Wenas",
            "stnk_exp": "2028-07-04",
            "kir_exp": "2027-01-12",
        },
        {
            "plate": "DB 8910 TK",
            "type": "CDE",
            "model": "Isuzu Elf NLR 55 TX 4-Roda",
            "cbm": 10.0,
            "ton": 3.5,
            "route": "Delivery Tomohon/Kawangkoan",
            "driver": "Stenly Rompas",
            "stnk_exp": "2027-09-11",
            "kir_exp": "2026-10-20",
        },
        {
            "plate": "DB 8890 EL",
            "type": "CDEL",
            "model": "Hino Dutro 110 SDBL 4-Roda Long",
            "cbm": 14.3,
            "ton": 4.0,
            "route": "Delivery Minsel/Amurang",
            "driver": "David Kalalo",
            "stnk_exp": "2028-12-16",
            "kir_exp": "2027-02-08",
        },
        {
            "plate": "DB 8345 MK",
            "type": "CDD",
            "model": "Canter FE 74 HD 6-Roda Double",
            "cbm": 17.2,
            "ton": 6.0,
            "route": "Grosir & MT Bitung",
            "driver": "Johan Rori",
            "stnk_exp": "2027-01-25",
            "kir_exp": "2026-08-14",
        },
        {
            "plate": "DB 8765 DL",
            "type": "CDDL",
            "model": "Hino Ranger FG 235 JJ 6-Roda Long",
            "cbm": 34.4,
            "ton": 8.5,
            "route": "Inbound Pelabuhan Bitung",
            "driver": "Agus Supit",
            "stnk_exp": "2027-10-30",
            "kir_exp": "2026-11-19",
        },
    ]


def write_csv(filepath: pathlib.Path, data: list[dict], fieldnames: list[str]) -> None:
    """Menulis list of dict ke file CSV dengan encoding utf-8."""
    with filepath.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)


def main():
    print("Mempersiapkan dataset FMCG Manado...")

    products = generate_products()
    partners = generate_partners()
    employees = generate_employees()
    vehicles = generate_vehicles()

    print(f" - Menghasilkan {len(products)} Produk SKU...")
    write_csv(SEED_DIR / "products_150.csv", products, list(products[0].keys()))

    print(f" - Menghasilkan {len(partners)} Partner Outlet (MT, GT, RTL, INST)...")
    write_csv(SEED_DIR / "partners_354.csv", partners, list(partners[0].keys()))

    print(f" - Menghasilkan {len(employees)} Karyawan Roster...")
    write_csv(SEED_DIR / "employees_24.csv", employees, list(employees[0].keys()))

    print(f" - Menghasilkan {len(vehicles)} Armada Logistik...")
    write_csv(SEED_DIR / "vehicles_9.csv", vehicles, list(vehicles[0].keys()))

    # Summary JSON untuk simulasi historis
    historical_summary = {
        "period": "2026-07-01 to 2026-10-24",
        "working_days": 98,
        "monthly_realization": {
            "2026-07": {"target": 5500000000, "actual": 4850000000, "active_outlets": 310, "otif_pct": 94.2},
            "2026-08": {"target": 5500000000, "actual": 5250000000, "active_outlets": 335, "otif_pct": 95.5},
            "2026-09": {"target": 5500000000, "actual": 5500000000, "active_outlets": 354, "otif_pct": 96.1},
            "2026-10_mtd": {"target": 4200000000, "actual": 4280000000, "active_outlets": 354, "otif_pct": 97.4},
        },
        "total_revenue_idr": 19880000000,
        "inventory_metrics": {
            "initial_stock_july_1_idr": 4100000000,
            "average_inventory_idr": 4400000000,
            "cogs_pct": 89.5,
            "dsi_days": 22.3,
            "stock_turnover_monthly": 1.12,
        },
        "logistics_metrics": {
            "total_fleet": 9,
            "average_daily_cartons": 1540,
            "average_daily_tonnage": 6.5,
            "overall_otif_pct": 95.8,
            "delivery_rejection_pct": 1.2,
        },
    }
    with (SEED_DIR / "historical_simulation_summary.json").open("w", encoding="utf-8") as f:
        json.dump(historical_summary, f, indent=2)

    print("Selesai! Seluruh file seed tersimpan di data/seed/.")


if __name__ == "__main__":
    main()
