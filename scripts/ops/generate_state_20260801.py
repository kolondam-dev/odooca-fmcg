#!/usr/bin/env python3
"""generate_state_20260801.py - Generate canonical state_20260801.json for Phase F0.

Reads the 15 frozen canonical July 2026 registers in data/registers/,
replays stock event ledger, invoices, deliveries, AP and AR collections,
and constructs the exact opening baseline state at 2026-08-01 00:00:00.

Validates that replay output matches canonical_financial_reconciliation_july_2026.json:
- Physical cartons: 53,837
- Reserved cartons: 1,038 (for the 48 carry-forward DOs on August 1)
- Available cartons: 52,799
- Quarantine cartons: 9
- Open July invoices: 309 (DPP Rp2,135,470,252.80)
- Carry-forward invoices: 48 (DPP Rp187,858,691.40)
- Total open AR at 2026-08-01 00:00: 357 invoices (DPP Rp2,323,328,944.20)
- Open AP: 1 PO (PO-2026-06-05, Unilever, DPP Rp2,899,971,200.00)
- Pending carry-forward DOs: 48 DOs
"""

from decimal import Decimal
import json
from pathlib import Path
import sys

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _q(d: Decimal) -> str:
    return str(d.quantize(Decimal("0.01")))


def load_csv_rows(path: Path):
    import csv
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def generate_state(reg_dir: Path) -> dict:
    # 1. Replay stock event ledger
    ledger_rows = load_csv_rows(reg_dir / "perpetual_stock_event_ledger.csv")
    stock_map = {}
    for row in ledger_rows:
        key = f"{row['sku_code']}||{row['lot_number']}"
        entry = stock_map.setdefault(key, {
            "sku_code": row["sku_code"],
            "lot_number": row["lot_number"],
            "physical": Decimal("0"),
            "reserved": Decimal("0"),
            "quarantine": Decimal("0"),
        })
        entry["physical"] += Decimal(str(row["physical_impact"]))
        entry["reserved"] += Decimal(str(row["reserved_impact"]))
        entry["quarantine"] += Decimal(str(row["quarantine_impact"]))

    # 2. Invoices & AR collections
    inv_rows = load_csv_rows(reg_dir / "perpetual_invoices.csv")
    ar_rows = load_csv_rows(reg_dir / "perpetual_ar_collections.csv")
    paid_inv_numbers = {row["invoice_number"] for row in ar_rows}

    open_invoices_july = {}
    carry_invoices_august = {}
    for row in inv_rows:
        inv_num = row["invoice_number"]
        inv_date = row["date_invoice"]
        dpp = Decimal(str(row["dpp_amount"]))
        total = Decimal(str(row["total_invoice_with_ppn"]))
        if inv_num not in paid_inv_numbers:
            if inv_date <= "2026-07-31":
                open_invoices_july[inv_num] = {
                    "date_invoice": inv_date,
                    "due_date": row["due_date"],
                    "customer": row["customer"],
                    "dpp_amount": str(dpp),
                    "total_invoice_with_ppn": str(total),
                }
            else:
                carry_invoices_august[inv_num] = {
                    "date_invoice": inv_date,
                    "due_date": row["due_date"],
                    "customer": row["customer"],
                    "dpp_amount": str(dpp),
                    "total_invoice_with_ppn": str(total),
                }

    # 3. Deliveries & Carry-Forward Pending DOs
    do_rows = load_csv_rows(reg_dir / "perpetual_deliveries.csv")
    pending_dos = {}
    for row in do_rows:
        sched_date = row["scheduled_delivery_date"]
        if sched_date > "2026-07-31":
            pending_dos[row["do_number"]] = {
                "so_number": row["so_number"],
                "scheduled_delivery_date": sched_date,
                "gross_order_dpp": row["gross_order_dpp"],
                "delivery_vehicle": row["delivery_vehicle"],
                "customer": row["customer"],
            }

    # 4. Inbound PO & AP payments
    po_rows = load_csv_rows(reg_dir / "inbound_po_intransit_june_headers.csv")
    ap_rows = load_csv_rows(reg_dir / "perpetual_ap_payments.csv")
    paid_pos = {row["po_number"] for row in ap_rows}

    open_po = {}
    in_transit_po = {}
    for row in po_rows:
        po_num = row["po_number"]
        arr_date = row["arrival_maumbi_date"]
        dpp = Decimal(str(row["total_dpp"]))
        if po_num not in paid_pos:
            if arr_date <= "2026-07-31":
                open_po[po_num] = {
                    "principal_code": row["principal_code"],
                    "arrival_maumbi_date": arr_date,
                    "payment_due_date": row["due_date"],
                    "total_amount_dpp": _q(dpp),
                }
            else:
                in_transit_po[po_num] = {
                    "principal_code": row["principal_code"],
                    "arrival_maumbi_date": arr_date,
                    "payment_due_date": row["due_date"],
                    "total_amount_dpp": _q(dpp),
                }

    # Filter non-zero stock
    non_zero_stock = {
        k: {
            "sku_code": v["sku_code"],
            "lot_number": v["lot_number"],
            "physical": int(v["physical"]),
            "reserved": int(v["reserved"]),
            "quarantine": int(v["quarantine"]),
        }
        for k, v in stock_map.items()
        if v["physical"] != 0 or v["reserved"] != 0 or v["quarantine"] != 0
    }

    # Sequence numbers at cut-off
    so_rows = load_csv_rows(reg_dir / "perpetual_sales_orders.csv")
    rej_rows = load_csv_rows(reg_dir / "perpetual_order_rejections.csv")

    state = {
        "as_of_datetime": "2026-08-01T00:00:00+07:00",
        "description": "Baseline canonical closing state of July 2026 transactions, ready for August 2026 seed continuation.",
        "summary": {
            "total_physical_cartons": sum(v["physical"] for v in non_zero_stock.values()),
            "total_reserved_cartons": sum(v["reserved"] for v in non_zero_stock.values()),
            "total_available_cartons": sum(v["physical"] - v["reserved"] for v in non_zero_stock.values()),
            "total_quarantine_cartons": sum(v["quarantine"] for v in non_zero_stock.values()),
            "open_july_invoices_count": len(open_invoices_july),
            "open_july_invoices_dpp": _q(sum(Decimal(v["dpp_amount"]) for v in open_invoices_july.values())),
            "carry_forward_august_invoices_count": len(carry_invoices_august),
            "carry_forward_august_invoices_dpp": _q(sum(Decimal(v["dpp_amount"]) for v in carry_invoices_august.values())),
            "total_open_ar_count": len(open_invoices_july) + len(carry_invoices_august),
            "total_open_ar_dpp": _q(sum(Decimal(v["dpp_amount"]) for v in open_invoices_july.values()) + sum(Decimal(v["dpp_amount"]) for v in carry_invoices_august.values())),
            "open_po_count": len(open_po),
            "open_po_dpp": _q(sum(Decimal(v["total_amount_dpp"]) for v in open_po.values())),
            "pending_carry_forward_dos_count": len(pending_dos),
        },
        "last_sequences": {
            "last_so_number": max(r["so_number"] for r in so_rows),
            "last_do_number": max(r["do_number"] for r in do_rows),
            "last_invoice_number": max(r["invoice_number"] for r in inv_rows),
            "last_ar_payment_id": max(r["payment_id"] for r in ar_rows),
            "last_ap_payment_id": max(r["ap_payment_id"] for r in ap_rows),
            "last_rejection_id": max(r["rejection_id"] for r in rej_rows),
            "last_event_id": max(r["event_id"] for r in ledger_rows),
        },
        "open_invoices": open_invoices_july,
        "carry_invoices": carry_invoices_august,
        "pending_dos": pending_dos,
        "open_po": open_po,
        "in_transit_po": in_transit_po,
        "stock": non_zero_stock,
    }
    return state


def main():
    reg_dir = REPO_ROOT / "data" / "registers"
    state = generate_state(reg_dir)

    # Invariant verification against canonical reconciliation
    summary = state["summary"]
    assert summary["total_physical_cartons"] == 53837, f"Expected 53837 physical, got {summary['total_physical_cartons']}"
    assert summary["total_reserved_cartons"] == 1038, f"Expected 1038 reserved, got {summary['total_reserved_cartons']}"
    assert summary["total_available_cartons"] == 52799, f"Expected 52799 available, got {summary['total_available_cartons']}"
    assert summary["total_quarantine_cartons"] == 9, f"Expected 9 quarantine, got {summary['total_quarantine_cartons']}"
    assert summary["open_july_invoices_count"] == 309, f"Expected 309 open July invoices, got {summary['open_july_invoices_count']}"
    assert summary["carry_forward_august_invoices_count"] == 48, f"Expected 48 carry invoices, got {summary['carry_forward_august_invoices_count']}"
    assert summary["total_open_ar_count"] == 357, f"Expected 357 total open AR, got {summary['total_open_ar_count']}"
    assert summary["total_open_ar_dpp"] == "2323328944.20", f"Expected DPP 2323328944.20, got {summary['total_open_ar_dpp']}"
    assert summary["open_po_count"] == 1, f"Expected 1 open PO, got {summary['open_po_count']}"
    assert summary["open_po_dpp"] == "2899971200.00", f"Expected DPP 2899971200.00, got {summary['open_po_dpp']}"
    assert summary["pending_carry_forward_dos_count"] == 48, f"Expected 48 pending DOs, got {summary['pending_carry_forward_dos_count']}"

    out_file = reg_dir / "state_20260801.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    print(f"Generated {out_file} successfully.")
    print("Reconciliation checks passed:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print("Last sequences:")
    for k, v in state["last_sequences"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
