"""Disposable B09 client/oracle for a lost successful command receipt."""
import argparse
import hashlib
from http.client import IncompleteRead
import json
import os
from pathlib import Path
import ssl
from urllib.request import Request

from verify_dev02a_apk import verify
from verify_dev02b_session import AUTH, BASE, BOOTSTRAP, SNAPSHOT, Client

COMMANDS = "/api/v1/sync/commands"


def post(client, wire, csrf):
    headers = {"Content-Type": "application/json", "X-CSRF-Token": csrf}
    with client.opener.open(Request(BASE + COMMANDS, data=wire, headers=headers), timeout=30) as response:
        if response.code != 200:
            raise ValueError("expected successful upstream command")
        return json.load(response)


def run_request(phase, directory, ca):
    db = os.environ["FMCG_STAGING_DATABASE"]
    uuid = os.environ["DEV02A_UUID"]
    if not db.startswith("fmcg_staging_") or os.environ.get("FMCG_STAGING_DISPOSABLE") != "YES":
        raise ValueError("disposable fixture required")
    client = Client(ssl.create_default_context(cafile=ca))
    result = client.request(AUTH, params={
        "db": db, "login": "staging.capture.1", "password": os.environ["FMCG_STAGING_PASSWORD_1"],
    })
    identity = client.request(BOOTSTRAP)
    snapshot = client.request(SNAPSHOT)
    scope = snapshot["scope"]
    if (str(result["result"]["uid"]) != identity["id"]
            or (scope["user_id"], scope["company_id"]) != (identity["id"], identity["companyId"])):
        raise ValueError("actor scope mismatch")
    metadata = {key: scope[key] for key in ("user_id", "company_id", "business_date")}
    if phase == "first":
        outlet, = snapshot["outlets"]
        product, = snapshot["products"]
        command = {"client_uuid": uuid, "type": "sales.order.submit", "payload": {
            "outlet_id": outlet["id"], "snapshot_version": snapshot["version"],
            "lines": [{"product_id": product["id"], "qty": "1", "uom": "carton"}],
        }}
        wire = json.dumps(command, sort_keys=True, separators=(",", ":")).encode()
        (directory / "command.json").write_bytes(wire)
        (directory / "actor.json").write_text(json.dumps(metadata))
    else:
        wire = (directory / "command.json").read_bytes()

    try:
        receipt = post(client, wire, identity["csrfToken"])
    except IncompleteRead:
        if phase != "first":
            raise
        print("first_response=truncated receipt_received=false")
        return
    if phase != "replay":
        raise ValueError("expected to lose the first receipt")
    (directory / "replay.json").write_text(json.dumps({
        "phase": "replay", "request": json.loads(wire), **metadata,
        "receipt": {key: receipt[key] for key in ("client_uuid", "status", "reference")},
    }))


def check(directory):
    def read(name):
        return json.loads((directory / name).read_text())

    before, after_loss, after_replay = (read(name) for name in ("before.json", "after.json", "after_replay.json"))
    # The first receipt was lost. Use the upstream durable ledger as the expected receipt oracle.
    row, = after_loss["ledger"]
    expected = {
        "phase": "first", "request": read("command.json"), **read("actor.json"),
        "receipt": {key: row[key] for key in ("client_uuid", "status", "reference")},
    }
    report = verify(expected, read("replay.json"), before, after_loss, after_replay)
    report.update(first_receipt_oracle="odoo_ledger", first_receipt_received=False,
                  wire_sha256=hashlib.sha256((directory / "command.json").read_bytes()).hexdigest())
    print(json.dumps(report, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("first", "replay", "verify"))
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        if args.phase == "verify":
            check(args.directory)
        else:
            run_request(args.phase, args.directory, args.directory / "ca.pem")
    except (OSError, IncompleteRead, KeyError, TypeError, ValueError):
        parser.exit(1, f"DEV-03A {args.phase} evidence failed\n")


if __name__ == "__main__":
    main()
