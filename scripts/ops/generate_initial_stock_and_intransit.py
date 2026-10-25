#!/usr/bin/env python3
"""Generator Saldo Awal Persediaan per 1 Juli 2026 & PO In-Transit Juni FMCG Manado.

Menghasilkan:
1. data/registers/initial_stock_20260701.csv & .json:
   Saldo awal fisik on-hand 150 SKU di Gudang Maumbi per 1 Juli 2026 00:00:00 WITA.
   Total nilai: ~Rp 4,33 Miliar (DPP), volume ~1.850 m³ (52,9% kapasitas gudang).
2. data/registers/inbound_po_intransit_june.csv & .json:
   Daftar PO Juni yang dalam pengapalan laut Surabaya-Bitung dan bersandar awal Juli:
   - PO-2026-06-01 (Wings): Tiba 1 Juli (Rp 1.849.620.000 DPP, 4 Kontainer 20ft, TOP 21 hari)
   - PO-2026-06-02 (Kapal Api): Tiba 1 Juli (Rp 1.448.970.000 DPP, 3 Kontainer 20ft, TOP 28 hari)
   - PO-2026-06-03 (Mayora): Tiba 2 Juli (Rp 699.850.000 DPP, 1 Kontainer 20ft, TOP 30 hari)
   - PO-2026-06-04 (Mayora): Tiba 3 Juli (Rp 2.598.740.000 DPP, 2 Kontainer 40ft, TOP 30 hari)
   - PO-2026-06-05 (Unilever): Tiba 4 Juli (Rp 2.899.430.000 DPP, 2 Kontainer 40ft, TOP 35 hari)
   Total kedatangan awal Juli: Rp 9.496.610.000 DPP (memicu krisis overstok 107,4% pada 3-10 Juli).
"""

import csv
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SEED_DIR = ROOT / "data" / "seed"
REG_DIR = ROOT / "data" / "registers"
REG_DIR.mkdir(parents=True, exist_ok=True)


def load_products():
    with open(SEED_DIR / "products_150.csv", "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def generate_initial_stock(products: list[dict]):
    """Membuat saldo awal on-hand per 1 Juli 2026 untuk 150 SKU."""
    initial_stock = []
    tot_val = 0.0
    tot_cbm = 0.0
    tot_weight = 0.0

    # Proporsi fast-moving vs slow-moving per principal:
    # Target saldo awal total ~Rp 4.330.000.000 DPP
    # Wings ~34% (Rp 1.47B), Mayora ~28% (Rp 1.21B), Kapal Api ~20% (Rp 0.86B), Unilever ~18% (Rp 0.79B)
    target_by_prin = {
        "PRIN-WINGS": 1_472_000_000.0,
        "PRIN-MAYORA": 1_212_000_000.0,
        "PRIN-SANTOS": 866_000_000.0,
        "PRIN-UNILEVER": 780_000_000.0,
    }

    prods_by_prin = {}
    for p in products:
        prods_by_prin.setdefault(p["principal_code"], []).append(p)

    for prin, p_list in prods_by_prin.items():
        prin_target = target_by_prin.get(prin, 1_000_000_000.0)
        # Alokasi per SKU secara realistis berbasis rotasi produk
        base_sku_target = prin_target / len(p_list)

        for idx, p in enumerate(p_list, start=1):
            cost_price = float(p["cost_price"])
            carton_qty = int(p["carton_qty"])
            c_cost = cost_price * carton_qty

            # Variasi alami SKU fast moving (mie instan goreng, kopi special, biskuit kelapa) vs slow moving
            if any(k in p["name"].lower() for k in ["goreng", "soto", "kelapa", "special", "jeruk nipis", "anti noda"]):
                multiplier = 1.65
            elif any(k in p["name"].lower() for k in ["rawon", "peach", "tamarrin", "klepon", "roll on"]):
                multiplier = 0.55
            else:
                multiplier = 1.0

            sku_target_val = base_sku_target * multiplier
            ctn_qty = max(15, int(round(sku_target_val / c_cost)))

            subtotal_dpp = ctn_qty * c_cost
            tot_units = ctn_qty * carton_qty
            sku_cbm = ctn_qty * float(p["carton_volume_cbm"])
            sku_wt = ctn_qty * float(p["carton_weight_kg"])

            tot_val += subtotal_dpp
            tot_cbm += sku_cbm
            tot_weight += sku_wt

            initial_stock.append({
                "sku_code": p["default_code"],
                "product_name": p["name"],
                "principal_code": p["principal_code"],
                "brand_code": p["brand_code"],
                "fmcg_category": p["fmcg_category"],
                "base_uom": p["base_uom"],
                "purchase_uom": p["purchase_uom"],
                "carton_qty": carton_qty,
                "qty_cartons_on_hand": ctn_qty,
                "qty_units_on_hand": tot_units,
                "unit_cost_price": cost_price,
                "carton_cost_price": c_cost,
                "subtotal_dpp": round(subtotal_dpp, 2),
                "volume_cbm": round(sku_cbm, 4),
                "weight_kg": round(sku_wt, 2),
                "lot_number": f"LOT-{p['principal_code'][-3:]}-20260615-INIT-{idx:02d}",
                "expiry_date": "2027-12-31",
            })

    print(f"Saldo Awal 1 Juli 2026: {len(initial_stock)} SKU | Total DPP: Rp {tot_val:,.2f} | Volume: {tot_cbm:.1f} m³ | Berat: {tot_weight / 1000.0:.2f} Ton")
    return initial_stock


def generate_intransit_po(products: list[dict]):
    """Membuat daftar PO Juni In-Transit yang sandar di Bitung & masuk Maumbi awal Juli 2026."""
    prods_by_prin = {}
    for p in products:
        prods_by_prin.setdefault(p["principal_code"], []).append(p)

    po_headers = [
        {
            "po_number": "PO-2026-06-01",
            "principal_code": "PRIN-WINGS",
            "principal_name": "PT Sayapp Mas Utamma",
            "order_date": "2026-06-15",
            "eta_bitung": "2026-06-28",
            "arrival_maumbi_date": "2026-07-01",
            "container_spec": "4x 20ft FCL Container",
            "payment_term_days": 21,
            "due_date": "2026-07-22",
            "ap_payment_date": "2026-07-22",
        },
        {
            "po_number": "PO-2026-06-02",
            "principal_code": "PRIN-SANTOS",
            "principal_name": "PT Santos Jaya Abadii",
            "order_date": "2026-06-12",
            "eta_bitung": "2026-06-27",
            "arrival_maumbi_date": "2026-07-01",
            "container_spec": "3x 20ft FCL Container",
            "payment_term_days": 28,
            "due_date": "2026-07-29",
            "ap_payment_date": "2026-07-29",
        },
        {
            "po_number": "PO-2026-06-03",
            "principal_code": "PRIN-MAYORA",
            "principal_name": "PT Mayyora Indahh Tbk",
            "order_date": "2026-06-10",
            "eta_bitung": "2026-06-29",
            "arrival_maumbi_date": "2026-07-02",
            "container_spec": "1x 20ft FCL Container (Biskuit)",
            "payment_term_days": 30,
            "due_date": "2026-08-01",
            "ap_payment_date": "2026-07-31",
        },
        {
            "po_number": "PO-2026-06-04",
            "principal_code": "PRIN-MAYORA",
            "principal_name": "PT Mayyora Indahh Tbk",
            "order_date": "2026-06-20",
            "eta_bitung": "2026-07-01",
            "arrival_maumbi_date": "2026-07-03",
            "container_spec": "2x 40ft High Cube Container (Kopi & Wafer)",
            "payment_term_days": 30,
            "due_date": "2026-08-02",
            "ap_payment_date": "2026-07-31",
        },
        {
            "po_number": "PO-2026-06-05",
            "principal_code": "PRIN-UNILEVER",
            "principal_name": "PT Unilevr Indonezia Tbk",
            "order_date": "2026-06-18",
            "eta_bitung": "2026-07-02",
            "arrival_maumbi_date": "2026-07-04",
            "container_spec": "2x 40ft High Cube Container (Home & Personal)",
            "payment_term_days": 35,
            "due_date": "2026-08-08",
            "ap_payment_date": "2026-08-08",
        },
    ]

    target_po_amounts = {
        "PO-2026-06-01": 1_849_620_000.0,
        "PO-2026-06-02": 1_448_970_000.0,
        "PO-2026-06-03": 699_850_000.0,
        "PO-2026-06-04": 2_598_740_000.0,
        "PO-2026-06-05": 2_899_430_000.0,
    }

    po_lines = []
    for h in po_headers:
        p_code = h["principal_code"]
        p_list = prods_by_prin[p_code]
        po_num = h["po_number"]
        tgt = target_po_amounts[po_num]
        sub_alloc = tgt / len(p_list)

        curr_po_tot = 0.0
        curr_po_cbm = 0.0
        curr_po_ton = 0.0

        for idx, p in enumerate(p_list, start=1):
            cost_p = float(p["cost_price"])
            ctn_q = int(p["carton_qty"])
            c_cost = cost_p * ctn_q
            ctns = max(10, int(round(sub_alloc / c_cost)))
            subtotal = ctns * c_cost
            cbm = ctns * float(p["carton_volume_cbm"])
            wt = ctns * float(p["carton_weight_kg"])

            curr_po_tot += subtotal
            curr_po_cbm += cbm
            curr_po_ton += wt

            po_lines.append({
                "po_number": po_num,
                "principal_code": p_code,
                "sku_code": p["default_code"],
                "product_name": p["name"],
                "brand_code": p["brand_code"],
                "qty_cartons": ctns,
                "carton_qty": ctn_q,
                "unit_cost_price": cost_p,
                "carton_cost_price": c_cost,
                "subtotal_dpp": round(subtotal, 2),
                "volume_cbm": round(cbm, 4),
                "weight_kg": round(wt, 2),
                "lot_number": f"LOT-{p_code[-3:]}-{h['arrival_maumbi_date'].replace('-', '')}-{idx:02d}",
                "expiry_date": "2028-06-30",
            })

        h["total_dpp"] = round(curr_po_tot, 2)
        h["total_cbm"] = round(curr_po_cbm, 2)
        h["total_tonnage"] = round(curr_po_ton / 1000.0, 2)
        print(f"PO In-Transit {po_num} ({h['principal_name']}): Rp {h['total_dpp']:,.2f} | {h['total_cbm']} m³ | Masuk Maumbi: {h['arrival_maumbi_date']}")

    return po_headers, po_lines


def main():
    print("=" * 80)
    print("MEMBUAT MASTER SALDO AWAL PERSADAAN 1 JULI 2026 & PO IN-TRANSIT JUNI")
    print("=" * 80)

    products = load_products()
    assert len(products) == 150, f"Total produk harus tepat 150, didapat {len(products)}"

    # 1. Saldo Awal Fisik 1 Juli 2026
    initial_stock = generate_initial_stock(products)
    with open(REG_DIR / "initial_stock_20260701.json", "w", encoding="utf-8") as f:
        json.dump(initial_stock, f, indent=2)
    with open(REG_DIR / "initial_stock_20260701.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(initial_stock[0].keys()))
        writer.writeheader()
        writer.writerows(initial_stock)
    print(" -> Saldo Awal 150 SKU tersimpan di data/registers/initial_stock_20260701.{json,csv}")

    # 2. PO In-Transit Juni (Kedatangan 1-4 Juli)
    po_headers, po_lines = generate_intransit_po(products)
    with open(REG_DIR / "inbound_po_intransit_june_headers.json", "w", encoding="utf-8") as f:
        json.dump(po_headers, f, indent=2)
    with open(REG_DIR / "inbound_po_intransit_june_headers.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(po_headers[0].keys()))
        writer.writeheader()
        writer.writerows(po_headers)

    with open(REG_DIR / "inbound_po_intransit_june_lines.json", "w", encoding="utf-8") as f:
        json.dump(po_lines, f, indent=2)
    with open(REG_DIR / "inbound_po_intransit_june_lines.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(po_lines[0].keys()))
        writer.writeheader()
        writer.writerows(po_lines)

    print(" -> PO In-Transit tersimpan di data/registers/inbound_po_intransit_june_{headers,lines}.{json,csv}")
    print("=" * 80)


if __name__ == "__main__":
    main()
