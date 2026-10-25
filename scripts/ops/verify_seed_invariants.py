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
        inputs[path] = hashlib.sha256(data).hexdigest()
        rows = list(csv.DictReader(data.decode("utf-8-sig").splitlines()))
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
    inputs[geo_path] = hashlib.sha256(data).hexdigest()
    districts, villages = {}, {}
    for record in ET.fromstring(data).findall("record"):
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
    for key, invoice in invoices.items():
        delivery = deliveries.get(invoice["do_number"])
        if not delivery or delivery["so_number"] != invoice["so_number"] or invoice["so_number"] not in orders:
            fail("TX-FK", key, "invoice/order/delivery link invalid")
        if invoice["due_date"] < invoice["date_invoice"]:
            fail("EVENT-ORDER", key, "due date before invoice")
        equal("INVOICE-MATH", key, invoice["total_invoice_with_ppn"],
              number(invoice["dpp_amount"]) + number(invoice["ppn_11_amount"]))
    for row in read("data/registers/perpetual_ar_collections.csv"):
        invoice = invoices.get(row["invoice_number"])
        if not invoice or row["payment_date"] < invoice["date_invoice"]:
            fail("COLLECTION", row["payment_id"], "unknown invoice or payment before invoice")
        equal("COLLECTION", row["payment_id"], row["net_cash_collected"],
              number(row["invoice_dpp"]) - number(row["early_payment_discount"]))

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
