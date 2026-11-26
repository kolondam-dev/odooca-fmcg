#!/usr/bin/env python3
"""Join sanitized instrumentation receipts with three read-only Odoo checkpoints."""
import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def verify(first, replay, before, after, after_replay):
    require(first["phase"] == "first" and replay["phase"] == "replay", "unexpected APK phases")
    before_counts = before["company_command_count"], before["ledger"], before["orders"], before["approvals"]
    require(before_counts == (0, [], [], []), "fixture already has business effects")
    require(after == after_replay, "replay changed the Odoo checkpoint")
    fixture_keys = ("fixture", "uuid", "user_id", "company_id", "outlet_id", "product_id")
    require(all(before[key] == after[key] for key in fixture_keys), "fixture changed across checkpoints")
    require(after["fixture"] == "id_mobile_api_staging", "wrong fixture")
    require(after["company_command_count"] == 1 and len(after["ledger"]) == len(after["orders"]) == 1,
            "expected exactly one command and one sales order")
    ledger, order = after["ledger"][0], after["orders"][0]

    command = first["request"]
    receipt = first["receipt"]
    uuid = after["uuid"]
    parsed = UUID(uuid)
    require(parsed.version == 4 and str(parsed) == uuid, "invalid UUID")
    require(command == replay["request"], "replay changed the wire payload")
    require(first["business_date"] == replay["business_date"], "WITA business date changed")
    require(receipt == replay["receipt"], "APK receipt changed on replay")
    require(command["client_uuid"] == uuid and command["type"] == ledger["type"] == "sales.order.submit",
            "different command identity")
    require(receipt == {key: ledger[key] for key in ("client_uuid", "status", "reference")}
            and receipt["client_uuid"] == uuid and receipt["status"] in {"accepted", "needs_approval"}
            and receipt["reference"], "APK receipt does not match ledger")
    for key in ("user_id", "company_id"):
        require(first[key] == replay[key] == after[key] == ledger[key] == order[key], "actor scope mismatch")

    payload = command["payload"]
    require(payload["outlet_id"] == order["outlet_id"] == after["outlet_id"], "wrong outlet")
    require(payload["lines"] == [{"product_id": after["product_id"], "qty": "1", "uom": "carton"}],
            "wrong command line")
    require(len(order["lines"]) == 1 and order["lines"][0]["product_id"] == after["product_id"]
            and order["lines"][0]["qty"] == 24, "wrong sales order line")
    serialized = json.dumps(command, sort_keys=True, separators=(",", ":"))
    require(hashlib.sha256(serialized.encode()).hexdigest() == ledger["fingerprint"],
            "Odoo did not ledger the exact APK command")
    require(ledger["sale_order_ids"] == [order["id"]] and order["reference"] == receipt["reference"],
            "sales order is not the one identified by the receipt")
    require(order["state"] == "draft" and not order["picking_ids"] and not order["invoice_ids"],
            "fixture order advanced past draft")
    return {
        "result": "passed",
        "client_uuid": uuid,
        "status": receipt["status"],
        "reference": receipt["reference"],
        "ledger_count": 1,
        "sale_order_count": 1,
        "replay_changed_checkpoint": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("first", "replay", "before", "after", "after_replay"):
        parser.add_argument(field, type=Path)
    args = parser.parse_args()
    try:
        sources = [json.loads(path.read_text()) for path in vars(args).values()]
        report = verify(*sources)
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        text = str(error) if type(error) is ValueError else "missing or malformed evidence"
        parser.exit(1, f"DEV-02A evidence failed: {text}\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
