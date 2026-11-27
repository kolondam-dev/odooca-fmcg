"""Accept exactly one fresh, successful B09 instrumentation test."""
import argparse
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET

TEST = "com.kolondam.odooca.field.DisposableOdooReceiptTest"


def extract(raw, uuid, phase):
    bundle = {}
    tests = []
    evidence = []
    results = []
    for line in raw.splitlines():
        if line.startswith("INSTRUMENTATION_STATUS: "):
            key, _, value = line.removeprefix("INSTRUMENTATION_STATUS: ").partition("=")
            if key in bundle:
                raise ValueError("duplicate status field")
            bundle[key] = value
        elif line.startswith("INSTRUMENTATION_STATUS_CODE: "):
            code = line.split()[-1]
            if "dev02a_evidence" in bundle and code == "0" and len(bundle) == 1 and tests == ["1"]:
                evidence.append(json.loads(bundle["dev02a_evidence"]))
            elif bundle.get("class") == TEST and bundle.get("test") == "submitOrReplay":
                tests.append(code)
            else:
                raise ValueError("unexpected instrumentation status")
            bundle.clear()
        elif line.startswith(("INSTRUMENTATION_FAILED:", "INSTRUMENTATION_ABORTED:",
                              "INSTRUMENTATION_RESULT: shortMsg=")):
            raise ValueError("instrumentation process failed")
        elif line.startswith("INSTRUMENTATION_CODE: "):
            results.append(line.split()[-1])
    if bundle or tests != ["1", "0"] or results != ["-1"] or len(evidence) != 1:
        raise ValueError("test missing, skipped, failed or duplicated")
    report = evidence[0]
    command, receipt = report["request"], report["receipt"]
    payload = command["payload"]
    line, = payload["lines"]
    if (report["phase"] != phase or command["client_uuid"] != uuid or receipt["client_uuid"] != uuid
            or command["type"] != "sales.order.submit" or receipt["status"] not in {"accepted", "needs_approval"}):
        raise ValueError("evidence does not match the current invocation")
    for value, pattern in (
        (receipt["reference"], r"S[0-9]{1,16}"),
        (payload["snapshot_version"], r"odoo-read-v1:[a-f0-9]{64}"),
        (report["user_id"], r"[1-9][0-9]*"), (report["company_id"], r"[1-9][0-9]*"),
        (report["business_date"], r"[0-9]{4}-[0-9]{2}-[0-9]{2}"),
        (payload["outlet_id"], r"[1-9][0-9]*"), (line["product_id"], r"[1-9][0-9]*"),
    ):
        if not re.fullmatch(pattern, value):
            raise ValueError("unexpected evidence value")
    if line["qty"] != "1" or line["uom"] != "carton":
        raise ValueError("unexpected fixture quantity")
    clean_command = {
        "client_uuid": uuid, "type": "sales.order.submit",
        "payload": {"outlet_id": payload["outlet_id"], "snapshot_version": payload["snapshot_version"],
                    "lines": [{"product_id": line["product_id"], "qty": "1", "uom": "carton"}]},
    }
    if command != clean_command or set(receipt) != {"client_uuid", "status", "reference"}:
        raise ValueError("unexpected command or receipt fields")
    return {
        "phase": phase, "request": clean_command, "receipt": receipt,
        **{key: report[key] for key in ("user_id", "company_id", "business_date")},
    }


def verify_junit(path, uuid, phase):
    suite = ET.parse(path).getroot()
    expected = {"uuid": uuid, "phase": phase, "tests": "1", "failures": "0", "skipped": "0"}
    if suite.tag != "testsuite" or suite.attrib != expected or len(suite) != 1:
        raise ValueError("JUnit report missing, stale or unsuccessful")
    case = suite[0]
    if (case.tag != "testcase" or case.attrib != {"classname": TEST, "name": "submitOrReplay"}
            or len(case) or (suite.text or "").strip() or (case.text or "").strip() or (case.tail or "").strip()):
        raise ValueError("JUnit report contains an unexpected test or outcome")
    # Serialize only the validated result, never arbitrary XML comments or processing instructions.
    return ET.tostring(suite, encoding="unicode")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("junit", type=Path)
    parser.add_argument("validated_xml", type=Path)
    parser.add_argument("uuid")
    parser.add_argument("phase", choices=("first", "replay"))
    args = parser.parse_args()
    try:
        report = extract(args.raw.read_text(), args.uuid, args.phase)
        xml = verify_junit(args.junit, args.uuid, args.phase)
        args.validated_xml.write_text(xml + "\n")
    except (OSError, KeyError, TypeError, ValueError, ET.ParseError):
        parser.exit(1, "B09 instrumentation missing, invalid or stale\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
