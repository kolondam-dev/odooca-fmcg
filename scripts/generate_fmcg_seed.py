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


def get_product_dimensions(fmcg_category: str, weight_kg: float, carton_qty: int) -> dict:
    """Menghitung dimensi fisik realistis untuk satuan terkecil (Pcs) dan satuan terbesar (Karton)."""
    if fmcg_category in ("food", "biscuit_wafer", "noodles_food", "foods_savory"):
        if weight_kg <= 0.05:
            p_l, p_w, p_h = 10.0, 7.0, 1.5
        elif weight_kg <= 0.15:
            p_l, p_w, p_h = 16.0, 11.0, 3.5
        else:
            p_l, p_w, p_h = 20.0, 14.0, 4.5
    elif fmcg_category in ("rtd", "beverages_rtd"):
        if weight_kg <= 0.25:
            p_l, p_w, p_h = 5.5, 5.5, 14.0
        else:
            p_l, p_w, p_h = 6.2, 6.2, 17.5
    elif fmcg_category in ("coffee_powder", "coffee_hot", "coffee_wings"):
        if weight_kg <= 0.04:
            p_l, p_w, p_h = 6.0, 5.0, 12.0
        elif weight_kg <= 0.10:
            p_l, p_w, p_h = 12.0, 8.0, 3.5
        else:
            p_l, p_w, p_h = 16.0, 10.0, 5.0
    elif fmcg_category == "home_care":
        if weight_kg <= 0.3:
            p_l, p_w, p_h = 14.0, 6.0, 18.0
        else:
            p_l, p_w, p_h = 16.0, 8.0, 24.0
    elif fmcg_category == "personal_care":
        if weight_kg <= 0.12:
            p_l, p_w, p_h = 10.0, 4.5, 3.0
        elif weight_kg <= 0.2:
            p_l, p_w, p_h = 18.0, 4.5, 4.0
        else:
            p_l, p_w, p_h = 15.0, 7.0, 20.0
    else:  # Confectionery
        p_l, p_w, p_h = 14.0, 10.0, 2.5

    p_vol = round((p_l * p_w * p_h) / 1_000_000.0, 5)
    total_vol = p_vol * carton_qty * 1.18
    c_l = round(max(24.0, min(60.0, (total_vol * 1_000_000 / 3.0) ** (1 / 3) * 1.6)), 1)
    c_w = round(max(18.0, min(45.0, c_l * 0.72)), 1)
    c_h = round(max(14.0, (total_vol * 1_000_000) / (c_l * c_w)), 1)
    c_vol = round((c_l * c_w * c_h) / 1_000_000.0, 4)
    c_weight = round((weight_kg * carton_qty) + 0.45, 2)

    return {
        "length_cm": p_l,
        "width_cm": p_w,
        "height_cm": p_h,
        "volume_cbm": p_vol,
        "carton_length_cm": c_l,
        "carton_width_cm": c_w,
        "carton_height_cm": c_h,
        "carton_volume_cbm": c_vol,
        "carton_weight_kg": c_weight,
    }


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
                "name": f"Rroma {name}",
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
            "name": "Bettar Vanilla Sandwich 22g",
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
            "name": "Bettar Cokelat 120g",
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
            "description": "Biskuit Bettar Family Pack",
        }
    )

    products.append(
        {
            "default_code": "MYR-SLI-01",
            "name": "Slaii O'lai Strawberry 128g",
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
            "name": "Slaii O'lai Blueberry 128g",
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
        ("Share It Pouch 100g", 1, 24, 11000, 13000, "Benn-Beng Mini Pouch Pesta"),
        ("White 22g", 20, 160, 2200, 2700, "Wafer Lapis Cokelat Putih & Kelapa"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(beng_sub, start=1):
        products.append(
            {
                "default_code": f"MYR-BBG-{idx:02d}",
                "name": f"Benn-Beng {name}",
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
                "name": f"Torabikka {name}",
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
                "name": f"Koppiko {name}",
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
                "name": f"Ennergen {name}",
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
        ("Koppiko Coffee Candy Sak 150g", "BRD-KPK", 1, 24, 7500, 9000, "Permen Kopi Asli"),
        ("Koppiko Blister Pack 32g", "BRD-KPK", 12, 120, 2500, 3000, "Permen Kopi Kantong Saku"),
        ("Koppiko Cappuccino 150g", "BRD-KPK", 1, 24, 7800, 9200, "Permen Rasa Cappuccino"),
        ("Kiss Mint Cherry Sak 125g", "BRD-KIS", 1, 24, 6800, 8000, "Permen Mint Segar Emoticon"),
        ("Kiss Mint Barley Sak 125g", "BRD-KIS", 1, 24, 6800, 8000, "Permen Mint Barley"),
        ("Kiss Mint Apple Peach 125g", "BRD-KIS", 1, 24, 6800, 8000, "Permen Rasa Apel Persik"),
        ("Kiss Grape Mint 125g", "BRD-KIS", 1, 24, 6800, 8000, "Permen Rasa Anggur Segar"),
        ("Tamarrin Permen Asam Sak 135g", "BRD-TMR", 1, 24, 7000, 8200, "Permen Asam Jawa Alami"),
        ("Tamarrin Bag 50g", "BRD-TMR", 1, 48, 3000, 3600, "Permen Asam Kemasan Mini"),
        ("Tamarrin Roll Pack 30g", "BRD-TMR", 12, 120, 2000, 2500, "Permen Asam Roll Praktis"),
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
                "name": f"Kapall Api {name}",
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
                "name": f"Kopi ABCC {name}",
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
            "name": "Koppi Ya! Susu Sachet 25g",
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
            "name": "Koppi Ya! Hitam Manis 20g",
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
                "name": f"Koppi Kapten {name}",
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
        ("Kapall Api Signature Black Botol 200ml", "BRD-KA", 1, 24, 5500, 6500, "Kopi Hitam Dingin"),
        ("Kapall Api White Coffee Botol 200ml", "BRD-KA", 1, 24, 5800, 7000, "Kopi Putih Dingin"),
        ("Kapall Api Kopi Susu Kaleng 240ml", "BRD-KA", 1, 24, 7500, 8800, "Kopi Susu Kaleng Premium"),
        ("Kapall Api Cold Brew Can 240ml", "BRD-KA", 1, 24, 8200, 9500, "Kopi Cold Brew Ekstraktif"),
        ("Kopi ABCC Choco Malt Tetra Pack 200ml", "BRD-ABC", 1, 24, 4500, 5300, "Minuman Malt Cokelat Susu"),
        ("Kopi ABCC Coffee Latte Tetra 200ml", "BRD-ABC", 1, 24, 4500, 5300, "Latte Kemasan Kotak"),
        ("Kopi ABCC Kopi Moka Botol 250ml", "BRD-ABC", 1, 24, 6000, 7000, "Kopi Moka Siap Minum"),
        ("Kopi ABCC Kopi Susu Botol 250ml", "BRD-ABC", 1, 24, 6000, 7000, "Kopi Susu Siap Minum"),
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
                "name": f"Sunnlight {name}",
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
        ("Mollto Rose Fresh 770g", 1, 12, 22000, 25000, "Deterjen Harum Bunga"),
        ("Cair Konsentrat Refill 750ml", 2, 12, 18500, 21000, "Deterjen Cair Anti Noda"),
        ("Matic Front Load Cair 1.6L", 1, 6, 42000, 48000, "Khusus Mesin Cuci Bukaan Depan"),
        ("Matic Top Load Cair 1.6L", 1, 6, 38000, 44000, "Khusus Mesin Cuci Bukaan Atas"),
        ("Japanese Peach Cair 700ml", 2, 12, 19000, 22000, "Deterjen Wangi Buah Peach"),
    ]
    for idx, (name, in_q, ctn_q, cp, lp, desc) in enumerate(rinso_sub, start=1):
        products.append(
            {
                "default_code": f"ULV-RNS-{idx:02d}",
                "name": f"Rinnso {name}",
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
                "name": f"Mollto {name}",
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
                "name": f"Lifebuooy {name}",
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
                "name": f"Pepsodentt {name}",
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
                "name": f"Clearr Shampoo {name}",
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
            "name": "Rexxona Men Roll On Invisible Dry 45ml",
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
            "name": "Rexxona Women Brightening Roll On 45ml",
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
                "name": f"Royyco {name}",
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
            "name": "Banngo Kecap Manis Pouch Refill 550ml",
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
            "name": "Banngo Kecap Manis Pouch Refill 220ml",
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
                "name": f"Mie Seddaap {name}",
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
                "name": f"Jassjus {name}",
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
            "name": "Segarr Dingin Madu Lemon Box 24s",
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
            "name": "Segarr Dingin Sirsak Box 24s",
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
                "name": f"Topp Kopi {name}",
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
                "name": f"Floriddina {name}",
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
                "name": f"Tehh Javana {name}",
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
                "name": f"Goldaa Coffee {name}",
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

    brand_cat_map = {
        # Mayora
        "BRD-RMA": "biscuit_wafer",
        "BRD-BTR": "biscuit_wafer",
        "BRD-SLI": "biscuit_wafer",
        "BRD-BBG": "confectionery",
        "BRD-KPK": "confectionery",
        "BRD-KIS": "confectionery",
        "BRD-TMR": "confectionery",
        "BRD-TRB": "coffee_powder",
        "BRD-EGN": "coffee_powder",
        # Santos (Kapal Api)
        "BRD-KA": "coffee_hot",
        "BRD-ABC": "coffee_hot",
        "BRD-YA": "coffee_hot",
        "BRD-KPT": "coffee_hot",
        # Unilever
        "BRD-RYC": "foods_savory",
        "BRD-BNG": "foods_savory",
        "BRD-RNS": "home_care",
        "BRD-MLT": "home_care",
        "BRD-SNL": "home_care",
        "BRD-LFB": "personal_care",
        "BRD-CLR": "personal_care",
        "BRD-PSD": "personal_care",
        "BRD-RXN": "personal_care",
        # Wings
        "BRD-SDP": "noodles_food",
        "BRD-JSJ": "beverages_rtd",
        "BRD-SGD": "beverages_rtd",
        "BRD-TOP": "coffee_wings",
        "BRD-FLD": "beverages_rtd",
        "BRD-JVN": "beverages_rtd",
        "BRD-GLD": "beverages_rtd",
    }

    for p in products:
        b_code = p.get("brand_code")
        if b_code in brand_cat_map:
            p["fmcg_category"] = brand_cat_map[b_code]
        dims = get_product_dimensions(p["fmcg_category"], p["weight_kg"], p["carton_qty"])
        p.update(dims)
        p["carton_barcode"] = f"1{p['barcode']}"

    return products


def generate_partners() -> list[dict]:
    """Menghasilkan 354 Partner Outlet terstratifikasi (12 MT, 72 GT, 260 RTL, 10 INST)
    konsisten 100% dengan customer registry terestrial Sulut."""
    registry_file = ROOT / "data" / "registers" / "customer_registry_354.json"
    if registry_file.exists():
        with registry_file.open("r", encoding="utf-8") as f:
            reg = json.load(f)
        partners = []
        cust_list = reg if isinstance(reg, list) else reg.get("customers", [])
        for c in cust_list:
            partners.append(
                {
                    "ref": c["ref"],
                    "name": c["name"],
                    "channel_code": c["channel_code"],
                    "district_code": c["district_code"],
                    "subdistrict_code": c["subdistrict_code"],
                    "street": c["street"],
                    "city": c["city"],
                    "state": c["state"],
                    "country": c["country"],
                    "zip": c["zip"],
                    "phone": c["phone"],
                    "vat": c["vat"],
                    "credit_limit": c["credit_limit"],
                    "credit_mode": c["credit_mode"],
                    "payment_term_days": c["payment_term_days"],
                    "salesman_code": c["salesman_code"],
                    "latitude": c["latitude"],
                    "longitude": c["longitude"],
                    "is_company": c["is_company"],
                }
            )
        return partners

    from scripts.generate_customer_registry_and_pjp import build_customer_registry

    return build_customer_registry()


def generate_principals() -> list[dict]:
    """Menghasilkan master data 4 Principal Nasional FMCG (konsisten dengan id_principal_data.xml)."""
    return [
        {
            "code": "PRIN-MAYORA",
            "name": "PT Mayyora Indahh Tbk",
            "legal_name": "PT Mayyora Indahh Tbk",
            "street": "Gedung Mayora, Jl. Tomang Raya 21-23",
            "city": "Jakarta Barat",
            "zip": "11440",
            "phone": "021-5655320",
            "email": "customercare@mayora.co.id",
            "vat": "012345678054000",
            "pic_name": "Indra Wijaya",
            "pic_phone": "08123344556",
            "pic_email": "indra.wijaya@mayora.co.id",
            "lead_time_days": 10,
            "sla_delivery_pct": 96.0,
        },
        {
            "code": "PRIN-SANTOS",
            "name": "PT Santos Jaya Abadii",
            "legal_name": "PT Santos Jaya Abadii",
            "street": "Jl. Raya Gilang 159, Taman",
            "city": "Kab. Sidoarjo",
            "zip": "61257",
            "phone": "031-7882200",
            "email": "corporate@kapalapi.co.id",
            "vat": "013245678054000",
            "pic_name": "Ahmad Fauzi",
            "pic_phone": "08134455667",
            "pic_email": "ahmad.fauzi@kapalapi.co.id",
            "lead_time_days": 12,
            "sla_delivery_pct": 94.5,
        },
        {
            "code": "PRIN-UNILEVER",
            "name": "PT Unilevr Indonezia Tbk",
            "legal_name": "PT Unilevr Indonezia Tbk",
            "street": "Grha Unilever, Green Office Park Kav. 3, Jl. BSD Boulevard Barat",
            "city": "Kab. Tangerang",
            "zip": "15345",
            "phone": "021-80827000",
            "email": "suara.konsumen@unilever.com",
            "vat": "011234567054000",
            "pic_name": "Dewi Lestari",
            "pic_phone": "08145566778",
            "pic_email": "dewi.lestari@unilever.com",
            "lead_time_days": 14,
            "sla_delivery_pct": 97.0,
        },
        {
            "code": "PRIN-WINGS",
            "name": "PT Sayapp Mas Utamma",
            "legal_name": "PT Sayapp Mas Utamma",
            "street": "Jl. Tipar Cakung Kav. F 5-7, Cakung Barat",
            "city": "Jakarta Timur",
            "zip": "13910",
            "phone": "021-4602685",
            "email": "sales.corporate@wingscorp.com",
            "vat": "013456789054000",
            "pic_name": "Budi Santoso",
            "pic_phone": "08111223344",
            "pic_email": "budi.santoso@wingscorp.com",
            "lead_time_days": 14,
            "sla_delivery_pct": 95.0,
        },
    ]


def generate_employees() -> list[dict]:
    """Menghasilkan roster 24 personel PT Manado Distribusi Utama dengan hirarki pelaporan."""
    roster = [
        (
            "EMP-001",
            "Bpk. Ronald Mongisidi",
            "owner",
            "Management",
            "CC-MGT",
            "",
            "ronald.mongisidi@mdu-manado.co.id",
            "0811-432-1001",
            "",
        ),
        (
            "EMP-002",
            "Hendrik Polii",
            "branch_manager",
            "Management",
            "CC-MGT",
            "SIM A",
            "hendrik.polii@mdu-manado.co.id",
            "0811-432-1002",
            "EMP-001",
        ),
        (
            "EMP-003",
            "Feybe Lumempouw",
            "finance_lead",
            "Finance",
            "CC-FIN",
            "SIM A",
            "feybe.lumempouw@mdu-manado.co.id",
            "0812-441-2003",
            "EMP-002",
        ),
        (
            "EMP-004",
            "Grace Sumual",
            "accounting_staff",
            "Finance",
            "CC-FIN",
            "",
            "grace.sumual@mdu-manado.co.id",
            "0813-562-2004",
            "EMP-003",
        ),
        (
            "EMP-005",
            "Rudi Tumbelaka",
            "tax_staff",
            "Finance",
            "CC-FIN",
            "",
            "rudi.tumbelaka@mdu-manado.co.id",
            "0821-883-2005",
            "EMP-003",
        ),
        (
            "EMP-006",
            "Meike Wondal",
            "cashier",
            "Finance",
            "CC-FIN",
            "",
            "meike.wondal@mdu-manado.co.id",
            "0852-401-2006",
            "EMP-003",
        ),
        (
            "EMP-007",
            "Joni Kumajas",
            "sales_spv",
            "Sales",
            "CC-SALES",
            "SIM A",
            "joni.kumajas@mdu-manado.co.id",
            "0811-432-3007",
            "EMP-002",
        ),
        (
            "EMP-008",
            "Rivaldo Mamahit",
            "sales_admin_lead",
            "Sales",
            "CC-SALES",
            "",
            "rivaldo.mamahit@mdu-manado.co.id",
            "0812-441-3008",
            "EMP-007",
        ),
        (
            "EMP-009",
            "Priscilia Tielung",
            "sales_admin",
            "Sales",
            "CC-SALES",
            "",
            "priscilia.tielung@mdu-manado.co.id",
            "0813-562-3009",
            "EMP-008",
        ),
        (
            "EMP-010",
            "Willem Runtu",
            "warehouse_lead",
            "Warehouse",
            "CC-WMS",
            "SIM B1",
            "willem.runtu@mdu-manado.co.id",
            "0811-432-4010",
            "EMP-002",
        ),
        (
            "EMP-011",
            "Jemmy Pangaila",
            "staging_lead",
            "Warehouse",
            "CC-WMS",
            "",
            "jemmy.pangaila@mdu-manado.co.id",
            "0821-883-4011",
            "EMP-010",
        ),
        (
            "EMP-012",
            "Robby Karundeng",
            "picker_staff",
            "Warehouse",
            "CC-WMS",
            "",
            "robby.karundeng@mdu-manado.co.id",
            "0852-401-4012",
            "EMP-011",
        ),
        (
            "EMP-013",
            "Christian Wowor",
            "sales_mt",
            "Sales",
            "CC-SALES",
            "SIM A",
            "christian.wowor@mdu-manado.co.id",
            "0812-441-5013",
            "EMP-007",
        ),
        (
            "EMP-014",
            "Andre Pangemanan",
            "sales_to",
            "Sales",
            "CC-SALES",
            "SIM C & A",
            "andre.pangemanan@mdu-manado.co.id",
            "0813-562-5014",
            "EMP-007",
        ),
        (
            "EMP-015",
            "Meidy Wowor",
            "sales_to",
            "Sales",
            "CC-SALES",
            "SIM C & A",
            "meidy.wowor@mdu-manado.co.id",
            "0821-883-5015",
            "EMP-007",
        ),
        (
            "EMP-016",
            "Refly Sondakh",
            "sales_to",
            "Sales",
            "CC-SALES",
            "SIM C & A",
            "refly.sondakh@mdu-manado.co.id",
            "0852-401-5016",
            "EMP-007",
        ),
        (
            "EMP-017",
            "Novry Mandagi",
            "sales_canvass",
            "Sales",
            "CC-SALES",
            "SIM A",
            "novry.mandagi@mdu-manado.co.id",
            "0812-441-5017",
            "EMP-007",
        ),
        (
            "EMP-018",
            "Steven Lumenta",
            "sales_canvass",
            "Sales",
            "CC-SALES",
            "SIM A",
            "steven.lumenta@mdu-manado.co.id",
            "0813-562-5018",
            "EMP-007",
        ),
        (
            "EMP-019",
            "Eko Prasetyo",
            "driver",
            "Logistik",
            "CC-LOG",
            "SIM B1",
            "eko.prasetyo@mdu-manado.co.id",
            "0821-883-6019",
            "EMP-010",
        ),
        (
            "EMP-020",
            "Frits Wenas",
            "driver",
            "Logistik",
            "CC-LOG",
            "SIM B1",
            "frits.wenas@mdu-manado.co.id",
            "0852-401-6020",
            "EMP-010",
        ),
        (
            "EMP-021",
            "Stenly Rompas",
            "driver",
            "Logistik",
            "CC-LOG",
            "SIM B1",
            "stenly.rompas@mdu-manado.co.id",
            "0812-441-6021",
            "EMP-010",
        ),
        (
            "EMP-022",
            "Johan Rori",
            "driver",
            "Logistik",
            "CC-LOG",
            "SIM B2",
            "johan.rori@mdu-manado.co.id",
            "0813-562-6022",
            "EMP-010",
        ),
        (
            "EMP-023",
            "Maxi Walangitan",
            "helper",
            "Logistik",
            "CC-LOG",
            "",
            "maxi.walangitan@mdu-manado.co.id",
            "0821-883-6023",
            "EMP-010",
        ),
        (
            "EMP-024",
            "Royke Manopo",
            "helper",
            "Logistik",
            "CC-LOG",
            "",
            "royke.manopo@mdu-manado.co.id",
            "0852-401-6024",
            "EMP-010",
        ),
    ]
    return [
        {
            "code": c,
            "name": n,
            "role": r,
            "dept": d,
            "cost_center": cc,
            "sim": s,
            "work_email": em,
            "work_phone": ph,
            "manager_code": m,
        }
        for c, n, r, d, cc, s, em, ph, m in roster
    ]


def generate_vehicles() -> list[dict]:
    """Menghasilkan master 9 armada logistik beserta kapasitas dan dimensi box cargo."""
    return [
        {
            "plate": "DB 8123 QA",
            "type": "GM_BV",
            "model": "Daihatsu Gran Max BV 1.3",
            "box_length_m": 2.1,
            "box_width_m": 1.4,
            "box_height_m": 1.25,
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
            "box_length_m": 2.35,
            "box_width_m": 1.45,
            "box_height_m": 1.4,
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
            "box_length_m": 2.35,
            "box_width_m": 1.55,
            "box_height_m": 0.95,
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
            "box_length_m": 2.7,
            "box_width_m": 1.55,
            "box_height_m": 1.3,
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
            "box_length_m": 2.8,
            "box_width_m": 1.6,
            "box_height_m": 1.35,
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
            "box_length_m": 3.1,
            "box_width_m": 1.7,
            "box_height_m": 1.9,
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
            "box_length_m": 4.4,
            "box_width_m": 1.8,
            "box_height_m": 1.8,
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
            "box_length_m": 4.3,
            "box_width_m": 2.0,
            "box_height_m": 2.0,
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
            "box_length_m": 6.8,
            "box_width_m": 2.3,
            "box_height_m": 2.2,
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

    principals = generate_principals()
    products = generate_products()
    partners = generate_partners()
    employees = generate_employees()
    vehicles = generate_vehicles()

    print(f" - Menghasilkan {len(principals)} Principal Nasional...")
    write_csv(SEED_DIR / "principals_4.csv", principals, list(principals[0].keys()))

    print(f" - Menghasilkan {len(products)} Produk SKU...")
    write_csv(SEED_DIR / "products_150.csv", products, list(products[0].keys()))

    print(f" - Menghasilkan {len(partners)} Partner Outlet (MT, GT, RTL, INST)...")
    write_csv(SEED_DIR / "partners_354.csv", partners, list(partners[0].keys()))

    print(f" - Menghasilkan {len(employees)} Karyawan Roster...")
    write_csv(SEED_DIR / "employees_24.csv", employees, list(employees[0].keys()))

    print(f" - Menghasilkan {len(vehicles)} Armada Logistik...")
    write_csv(SEED_DIR / "vehicles_9.csv", vehicles, list(vehicles[0].keys()))

    # Summary JSON untuk simulasi historis selaras dengan ledger operasional
    historical_summary = {
        "period": "2026-07-01 to 2026-10-24",
        "working_days": 98,
        "monthly_realization": {
            "2026-07": {
                "target": 5500000000,
                "actual": 5500000000,
                "net_margin_pct": 0.90,
                "active_outlets": 177,
                "otif_pct": 91.5,
                "peak_warehouse_occupancy_pct": 107.4,
            },
            "2026-08": {
                "target": 4235000000,
                "actual": 4235000000,
                "growth_pct": -23.0,
                "net_margin_pct": 2.50,
                "active_outlets": 198,
                "otif_pct": 94.8,
            },
            "2026-09": {
                "target": 3960000000,
                "actual": 3960000000,
                "growth_pct": -6.5,
                "net_margin_pct": 3.70,
                "active_outlets": 226,
                "otif_pct": 96.2,
            },
            "2026-10_mtd": {
                "target": 5300000000,
                "actual": 5300000000,
                "net_margin_pct": 5.00,
                "active_outlets": 354,
                "otif_pct": 97.8,
            },
        },
        "total_revenue_idr": 18995000000,
        "inventory_metrics": {
            "initial_stock_july_1_idr": 4300000000,
            "inbound_purchases_idr": 18274000000,
            "cogs_pct": 90.8,
            "dsi_days": 24.1,
            "stock_turnover_monthly": 1.15,
        },
        "logistics_metrics": {
            "total_fleet": 9,
            "average_daily_cartons": 1480,
            "average_daily_tonnage": 6.8,
            "overall_otif_pct": 95.1,
            "delivery_rejection_pct": 0.8,
        },
    }
    with (SEED_DIR / "historical_simulation_summary.json").open("w", encoding="utf-8") as f:
        json.dump(historical_summary, f, indent=2)

    print("Selesai! Seluruh file seed tersimpan di data/seed/.")


if __name__ == "__main__":
    main()
