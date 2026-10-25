#!/usr/bin/env python3
"""Independent, read-only checks of committed seed artifacts (standard library only)."""
import argparse
import collections
import csv
import datetime as dt
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


def number(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("non-finite amount")
    return result


def validate(root, sizes=(354, 150)):
    """Return violations and input fingerprints; never execute a generator or contact Odoo."""
    root = Path(root)
    violations = []
    inputs = {}

    def fail(rule, key, detail):
        violations.append({"invariant": rule, "record": str(key), "detail": detail})

    def read(path):
        data = (root / path).read_bytes()
        normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        inputs[path] = hashlib.sha256(normalized).hexdigest()
        rows = list(csv.DictReader(normalized.decode("utf-8-sig").splitlines()))
        if not rows:
            raise ValueError(f"empty required dataset: {path}")
        return rows

    def index(rows, key, rule):
        result = {}
        for row in rows:
            value = row[key]
            if not value or value in result:
                fail(rule, value, "missing or duplicate identity")
            result[value] = row
        return result

    def equal(rule, key, left, right):
        if abs(number(left) - number(right)) > Decimal("0.01"):
            fail(rule, key, f"expected {right}; observed {left}")

    registry = read("data/registers/customer_registry_354.csv")
    partners = read("data/seed/partners_354.csv")
    products = read("data/seed/products_150.csv")
    customers = index(registry, "ref", "MASTER-IDENTITY")
    partner_map = index(partners, "ref", "MASTER-IDENTITY")
    product_map = index(products, "default_code", "MASTER-IDENTITY")
    if len(registry) != sizes[0] or len(partners) != sizes[0] or len(products) != sizes[1]:
        fail("MASTER-COUNT", "dataset", f"expected {sizes}; observed {len(registry), len(partners), len(products)}")
    if set(customers) != set(partner_map):
        fail("MASTER-SYNC", "partners", "registry/seed identity sets differ")
    for key, partner in partner_map.items():
        source = customers.get(key, {})
        if any(source.get(field) != value for field, value in partner.items()):
            fail("MASTER-SYNC", key, "shared registry/seed fields differ")

    geo_path = "addons/id_base/data/id_district_data.xml"
    data = (root / geo_path).read_bytes()
    normalized_geo = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    inputs[geo_path] = hashlib.sha256(normalized_geo).hexdigest()
    districts, villages = {}, {}
    for record in ET.fromstring(normalized_geo).findall("record"):
        fields = {f.get("name"): f.get("ref") or f.text for f in record.findall("field")}
        if record.get("model") == "id.district":
            districts[fields["code"]] = record.get("id")
        elif record.get("model") == "id.subdistrict":
            villages[fields["code"]] = fields["district_id"].split(".")[-1]
    for key, customer in customers.items():
        district = districts.get(customer["district_code"])
        if not district or villages.get(customer["subdistrict_code"]) != district:
            fail("MASTER-GEO", key, "district/village pair cannot resolve consistently in Odoo XML")

    pjp = read("data/registers/pjp_july_2026_matrix.csv")
    calls = set()
    for row in pjp:
        if row["frekuensi_call"] not in ("F1", "F2", "F4"):
            continue
        key = row["customer"].split(" - ")[0]
        customer = customers.get(key)
        date = row["tanggal"]
        calls.add((date, key, row["salesman"]))
        if not customer or date < customer["cohort_date"]:
            fail("COHORT-PJP", key, f"visit before cohort: {date}")
        if dt.date.fromisoformat(date).weekday() == 6:
            fail("CALENDAR", key, f"Sunday call: {date}")

    orders = index(read("data/registers/perpetual_sales_orders.csv"), "so_number", "TX-IDENTITY")
    lines = read("data/registers/perpetual_order_lines.csv")
    deliveries = index(read("data/registers/perpetual_deliveries.csv"), "do_number", "TX-IDENTITY")
    invoices = index(read("data/registers/perpetual_invoices.csv"), "invoice_number", "TX-IDENTITY")
    cards = read("data/registers/perpetual_daily_stock_cards.csv")
    calendar = index(cards, "date", "TX-IDENTITY")
    subtotals = collections.defaultdict(Decimal)
    events = []
    lot_expiry = {}
    for row in read("data/registers/initial_stock_20260701.csv"):
        key = row["sku_code"]
        equal("STOCK-MATH", key, row["qty_units_on_hand"], number(row["qty_cartons_on_hand"]) * number(row["carton_qty"]))
        equal("STOCK-MATH", key, row["subtotal_dpp"], number(row["qty_units_on_hand"]) * number(row["unit_cost_price"]))
        events.append(("0000-01-01", 0, key, row["lot_number"], number(row["qty_cartons_on_hand"]), "opening"))
        lot_expiry[(key, row["lot_number"])] = row["expiry_date"]
    po = index(read("data/registers/inbound_po_intransit_june_headers.csv"), "po_number", "TX-IDENTITY")
    po_totals = collections.defaultdict(Decimal)
    for row in read("data/registers/inbound_po_intransit_june_lines.csv"):
        header = po.get(row["po_number"])
        if not header:
            fail("TX-FK", row["po_number"], "PO header missing")
            continue
        equal("PO-MATH", row["po_number"], row["subtotal_dpp"],
              number(row["qty_cartons"]) * number(row["carton_qty"]) * number(row["unit_cost_price"]))
        po_totals[row["po_number"]] += number(row["subtotal_dpp"])
        key = row["sku_code"]
        events.append((header["arrival_maumbi_date"], 0, key, row["lot_number"], number(row["qty_cartons"]), "receipt"))
        lot_expiry[(key, row["lot_number"])] = row["expiry_date"]
    for key, header in po.items():
        equal("PO-MATH", key, header["total_dpp"], po_totals[key])
    for row in lines:
        key = row["so_number"]
        order = orders.get(key)
        product = product_map.get(row["sku_code"])
        if not order or not product:
            fail("TX-FK", key, "order or product missing")
            continue
        qty = number(row["qty_cartons"])
        if qty <= 0:
            fail("LINE-MATH", key, "quantity must be positive")
        equal("LINE-MATH", key, row["carton_qty"], product["carton_qty"])
        equal("LINE-MATH", key, row["line_subtotal_dpp"],
              qty * number(row["carton_qty"]) * number(row["unit_price_dpp"]))
        subtotals[key] += number(row["line_subtotal_dpp"])
        events.append((order["date_order"], 1, row["sku_code"], row["lot_number"], -qty, key))
    for key, order in orders.items():
        equal("HEADER-MATH", key, order["gross_dpp"], subtotals[key])
        equal("HEADER-MATH", key, order["net_dpp"], number(order["gross_dpp"]) - number(order["discount_dpp"]))
        ref = order["customer"].split(" - ")[0]
        customer = customers.get(ref)
        if not customer or order["date_order"] < customer["cohort_date"]:
            fail("COHORT-SO", key, "order before customer cohort")
        if (order["date_order"], ref, order["salesman"]) not in calls:
            fail("PJP-SO", key, "order has no matching customer/salesperson visit")
        day = calendar.get(order["date_order"])
        if not day or str(day["is_working_day"]).lower() != "true":
            fail("CALENDAR", key, "order on non-working or unrepresented date")
    for label, rows in (("delivery", deliveries.values()), ("invoice", invoices.values())):
        if {row["so_number"] for row in rows} != set(orders):
            fail("TX-COVERAGE", label, "order identity set differs from downstream documents")
    for key, delivery in deliveries.items():
        order = orders.get(delivery["so_number"])
        date = dt.date.fromisoformat(delivery["scheduled_delivery_date"])
        if not order or delivery["scheduled_delivery_date"] < order["date_order"]:
            fail("EVENT-ORDER", key, "delivery before order or missing order")
        if date.weekday() == 6:
            fail("CALENDAR", key, "Sunday delivery")
        deliv_day = calendar.get(delivery["scheduled_delivery_date"])
        if deliv_day and str(deliv_day["is_working_day"]).lower() != "true":
            fail("CALENDAR", key, f"delivery on non-working date: {delivery['scheduled_delivery_date']}")

    order_lot_qtys = collections.defaultdict(lambda: collections.defaultdict(Decimal))
    for row in lines:
        order_lot_qtys[row["so_number"]][(row["sku_code"], row["lot_number"])] += number(row["qty_cartons"])

    for key, invoice in invoices.items():
        delivery = deliveries.get(invoice["do_number"])
        if not delivery or delivery["so_number"] != invoice["so_number"] or invoice["so_number"] not in orders:
            fail("TX-FK", key, "invoice/order/delivery link invalid")
        order = orders.get(invoice["so_number"])
        ref = order["customer"].split(" - ")[0] if order else ""
        customer = customers.get(ref)
        if not customer:
            fail("TX-FK", key, f"unknown customer for invoice: {ref}")
            continue

        top_master = int(customer.get("payment_term_days", 0))
        top_inv = int(invoice.get("payment_term_days", -1))
        if top_inv != top_master:
            fail("MASTER-TOP", key, f"payment term mismatch: invoice={top_inv} vs master={top_master}")

        inv_date = dt.date.fromisoformat(invoice["date_invoice"])
        expected_due = (inv_date + dt.timedelta(days=top_master)).isoformat()
        if invoice["due_date"] != expected_due:
            fail("EVENT-ORDER", key, f"due date mismatch: expected {expected_due}, observed {invoice['due_date']}")

        if delivery and delivery["scheduled_delivery_date"] != invoice["date_invoice"]:
            fail("PERIOD-CUTOFF", key, f"delivery date {delivery['scheduled_delivery_date']} != invoice date {invoice['date_invoice']}")

        if invoice["due_date"] < invoice["date_invoice"]:
            fail("EVENT-ORDER", key, "due date before invoice")

        if order and delivery:
            gross_order = number(order["gross_dpp"])
            deliv_dpp = number(delivery["do_delivered_dpp"])
            disc_rate = (number(order["discount_dpp"]) / gross_order) if gross_order > 0 else Decimal("0.0")
            expected_inv_disc = (deliv_dpp * disc_rate).quantize(Decimal("0.01"))
            expected_inv_dpp = deliv_dpp - expected_inv_disc
            equal("INVOICE-MATH", key, invoice["dpp_amount"], expected_inv_dpp)
            expected_ppn = (number(invoice["dpp_amount"]) * Decimal("0.11")).quantize(Decimal("0.01"))
            equal("INVOICE-MATH", key, invoice["ppn_11_amount"], expected_ppn)

        equal("INVOICE-MATH", key, invoice["total_invoice_with_ppn"],
              number(invoice["dpp_amount"]) + number(invoice["ppn_11_amount"]))

    rejections_raw = read("data/registers/perpetual_order_rejections.csv")
    rejection_dpp_totals = collections.defaultdict(Decimal)
    rejection_ids = set()

    for row in rejections_raw:
        rej_id = row["rejection_id"]
        if rej_id in rejection_ids:
            fail("TX-IDENTITY", rej_id, "duplicate rejection ID")
        rejection_ids.add(rej_id)

        so_num = row["so_number"]
        do_num = row["do_number"]
        delivery = deliveries.get(do_num)
        order = orders.get(so_num)

        if not order or not delivery or delivery["so_number"] != so_num:
            fail("TX-FK", rej_id, "rejection SO or DO link invalid")
            continue

        sku = row["sku_code"]
        lot = row["lot_number"]
        product = product_map.get(sku)
        if not product:
            fail("TX-FK", rej_id, "rejection SKU unknown")
            continue

        delivered_lot_qty = order_lot_qtys[so_num].get((sku, lot), Decimal("0.0"))
        if delivered_lot_qty <= Decimal("0.0"):
            fail("RETURN-RECON", rej_id, f"rejected SKU/lot ({sku}/{lot}) was not in order {so_num}")

        qty = number(row["qty_cartons"])
        if qty <= 0:
            fail("LINE-MATH", rej_id, "rejection quantity must be positive")
        if qty > delivered_lot_qty:
            fail("RETURN-RECON", rej_id, f"rejected quantity {qty} exceeds delivered line quantity {delivered_lot_qty}")

        if row["rejection_date"] < order["date_order"] or row["rejection_date"] != delivery["scheduled_delivery_date"]:
            fail("EVENT-ORDER", rej_id, f"rejection date {row['rejection_date']} mismatch with delivery {delivery['scheduled_delivery_date']}")

        equal("LINE-MATH", rej_id, row["carton_qty"], product["carton_qty"])
        equal("LINE-MATH", rej_id, row["line_subtotal_dpp"],
              qty * number(row["carton_qty"]) * number(row["unit_price_dpp"]))
        rejection_dpp_totals[do_num] += number(row["line_subtotal_dpp"])

    for do_num, delivery in deliveries.items():
        rej_total = rejection_dpp_totals.get(do_num, Decimal("0.00"))
        equal("RETURN-RECON", do_num, delivery["rejection_dpp"], rej_total)
        order = orders.get(delivery["so_number"])
        if order:
            equal("RETURN-RECON", do_num, delivery["do_delivered_dpp"], number(order["gross_dpp"]) - rej_total)

    for row in read("data/registers/perpetual_ar_collections.csv"):
        invoice = invoices.get(row["invoice_number"])
        if not invoice:
            fail("COLLECTION", row["payment_id"], "unknown invoice in collection")
            continue
        if row["payment_date"] < invoice["date_invoice"]:
            fail("COLLECTION", row["payment_id"], "payment before invoice date")
        equal("COLLECTION-MATH", row["payment_id"], row["invoice_dpp"], invoice["dpp_amount"])
        equal("COLLECTION-MATH", row["payment_id"], row["net_cash_collected"],
              number(row["invoice_dpp"]) - number(row["early_payment_discount"]))

    # 1. Validasi Pembayaran Hutang Usaha (AP Invariants)
    ap_rows = read("data/registers/perpetual_ap_payments.csv")
    ap_paid_total = Decimal("0.00")
    for row in ap_rows:
        pid = row["ap_payment_id"]
        po_num = row["po_number"]
        header = po.get(po_num)
        if not header:
            fail("AP-FK", pid, f"PO header not found in June intransit: {po_num}")
            continue
        if row["principal_name"] != header["principal_name"]:
            fail("AP-FK", pid, f"principal mismatch: {row['principal_name']} vs {header['principal_name']}")
        paid_dpp = number(row["amount_paid_dpp"])
        header_dpp = number(header["total_dpp"])
        if paid_dpp > header_dpp:
            fail("AP-RECON", pid, f"AP payment {paid_dpp} exceeds PO total DPP {header_dpp}")
        if row["payment_date"] < header["order_date"]:
            fail("EVENT-ORDER", pid, f"payment date {row['payment_date']} before PO order date {header['order_date']}")
        ap_paid_total += paid_dpp

    if sizes == (354, 150):
        equal("AP-RECON", "JULY_AP_TOTAL", ap_paid_total, "6597474800.00")

    # 2. Validasi Beban Operasional & Penggajian (OPEX Invariants)
    opex_rows = read("data/registers/perpetual_opex_payroll.csv")
    total_opex = sum(number(o["amount"]) for o in opex_rows)
    if sizes == (354, 150):
        equal("OPEX-MATH", "TOTAL_OPEX", total_opex, "394350000.00")

    # 3. Validasi FEFO & Lot Balances
    balances = collections.defaultdict(Decimal)
    for date, kind, sku, lot, quantity, ref in sorted(events):
        if kind == 1:
            earlier = [lot_id for (s, lot_id), balance in balances.items()
                       if s == sku and balance > 0 and lot_expiry[(s, lot_id)] < lot_expiry.get((sku, lot), "")]
            if earlier:
                fail("LOT-FEFO", ref, f"earlier expiry lot still available for {sku}")
        balances[(sku, lot)] += quantity
        if balances[(sku, lot)] < 0:
            fail("LOT-BALANCE", ref, f"allocation exceeds received lot quantity: {sku}/{lot}")
        if kind == 1 and lot_expiry.get((sku, lot), "0000-01-01") < date:
            fail("LOT-EXPIRY", ref, f"unknown or expired lot: {sku}/{lot}")

    # 4. Validasi Ledger Event Replay (Granular Multi-Level Stock State Replay)
    ledger_rows = read("data/registers/perpetual_stock_event_ledger.csv")
    lot_phys = collections.defaultdict(Decimal)
    lot_res = collections.defaultdict(Decimal)
    lot_quar = collections.defaultdict(Decimal)

    ledger_events_by_date = collections.defaultdict(list)
    for row in ledger_rows:
        ledger_events_by_date[row["date"]].append(row)

    for d_str in sorted(calendar.keys()):
        for r in ledger_events_by_date[d_str]:
            eid = r["event_id"]
            sku = r["sku_code"]
            lot = r["lot_number"]
            p_imp = number(r["physical_impact"])
            r_imp = number(r["reserved_impact"])
            q_imp = number(r["quarantine_impact"])

            lot_phys[(sku, lot)] += p_imp
            lot_res[(sku, lot)] += r_imp
            lot_quar[(sku, lot)] += q_imp

            if lot_phys[(sku, lot)] < 0:
                fail("LEDGER-REPLAY", eid, f"negative physical balance for {sku}/{lot}: {lot_phys[(sku, lot)]}")
            if lot_res[(sku, lot)] < 0:
                fail("LEDGER-REPLAY", eid, f"negative reserved balance for {sku}/{lot}: {lot_res[(sku, lot)]}")
            if lot_quar[(sku, lot)] < 0:
                fail("LEDGER-REPLAY", eid, f"negative quarantine balance for {sku}/{lot}: {lot_quar[(sku, lot)]}")
            if lot_res[(sku, lot)] > lot_phys[(sku, lot)]:
                fail("LEDGER-REPLAY", eid, f"reserved ({lot_res[(sku, lot)]}) exceeds physical ({lot_phys[(sku, lot)]}) for {sku}/{lot}")

        # Verifikasi saldo penutupan harian terhadap kartu stok harian
        card = calendar[d_str]
        tot_phys_eod = sum(lot_phys.values())
        tot_res_eod = sum(lot_res.values())
        tot_quar_eod = sum(lot_quar.values())

        equal("LEDGER-REPLAY", f"DAILY-PHYSICAL-{d_str}", tot_phys_eod, card["physical_stock_cartons"])
        equal("LEDGER-REPLAY", f"DAILY-RESERVED-{d_str}", tot_res_eod, card["reserved_stock_cartons"])
        equal("LEDGER-REPLAY", f"DAILY-QUARANTINE-{d_str}", tot_quar_eod, card["quarantine_stock_cartons"])

    # 5. Validasi Laporan Rekonsiliasi Finansial Kanonikal (Provenance Checksum & Aggregates)
    report_rel_path = "data/registers/canonical_financial_reconciliation_july_2026.json"
    report_file = root / report_rel_path
    if not report_file.exists():
        fail("REPORT-RECON", "canonical_report", f"file missing: {report_rel_path}")
    else:
        report_bytes = report_file.read_bytes()
        norm_report = report_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        inputs[report_rel_path] = hashlib.sha256(norm_report).hexdigest()
        report_data = json.loads(norm_report.decode("utf-8"))

        # a. Verifikasi 15 Checksum Input Dataset di Laporan
        for filename, expected_hash in report_data.get("input_dataset_sha256", {}).items():
            actual_hash = inputs.get(f"data/registers/{filename}")
            if actual_hash != expected_hash:
                fail("REPORT-RECON", filename, f"checksum mismatch: expected {expected_hash}, observed {actual_hash}")

        # b. Verifikasi Kesesuaian Agregat Finansial & Persediaan
        equal("REPORT-RECON", "SO_GROSS_DPP", report_data["sales_orders_booked_july"]["gross_dpp"],
              sum(number(o["gross_dpp"]) for o in orders.values()))
        equal("REPORT-RECON", "SO_NET_DPP", report_data["sales_orders_booked_july"]["net_dpp"],
              sum(number(o["net_dpp"]) for o in orders.values()))
        equal("REPORT-RECON", "INV_JULY_DPP", report_data["period_cutoff_july_invoiced"]["invoiced_dpp"],
              sum(number(i["dpp_amount"]) for i in invoices.values() if i["date_invoice"] <= "2026-07-31"))
        equal("REPORT-RECON", "AP_PAID_JULY_DPP", report_data["accounts_payable_reconciliation"]["ap_payments_july_dpp"],
              ap_paid_total)
        equal("REPORT-RECON", "CLOSING_PHYSICAL", report_data["inventory_warehouse_reconciliation"]["physical_on_hand_cartons"],
              cards[-1]["physical_stock_cartons"])
        equal("REPORT-RECON", "CLOSING_QUARANTINE", report_data["inventory_warehouse_reconciliation"]["quarantine_bad_stock_cartons"],
              cards[-1]["quarantine_stock_cartons"])

    return violations, inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        violations, inputs = validate(args.root)
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
        violations, inputs = [{"invariant": "INPUT-SCHEMA", "record": "dataset", "detail": str(error)}], {}
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=args.root, capture_output=True, text=True).stdout.strip()
    counts = dict(collections.Counter(v["invariant"] for v in violations))
    report = {"schema_version": 1, "commit": sha, "status": "FAIL" if violations else "PASS",
              "scope": "local committed artifacts; not Odoo runtime acceptance",
              "input_sha256": inputs, "counts": counts, "violations": violations}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "counts": counts}, indent=2))
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
