#!/usr/bin/env python3
"""Validasi payload yang dihasilkan klien native terhadap skema OpenAPI kontrak.

Pemakaian:
  python3 android/tools/validate_contract.py pwa/contracts/openapi.json android/core/domain/build/contract-samples

Sampel dikeluarkan oleh tes domain (properti sistem `contract.out`). Setiap berkas harus lolos
skema yang sesuai; kontrol negatif memastikan validator benar-benar menolak payload yang rusak.
"""
import copy
import json
import sys

from jsonschema import Draft202012Validator

spec_path, samples_dir = sys.argv[1], sys.argv[2]
spec = json.load(open(spec_path, encoding="utf-8"))


def named(name):
    return Draft202012Validator({"$ref": f"#/components/schemas/{name}", "components": spec["components"]})


def command_variant(cmd_type):
    for i, variant in enumerate(spec["components"]["schemas"]["Command"]["anyOf"]):
        if variant["properties"]["type"].get("const") == cmd_type:
            return Draft202012Validator(
                {"$ref": f"#/components/schemas/Command/anyOf/{i}", "components": spec["components"]}
            )
    raise SystemExit(f"varian command tidak ada di kontrak: {cmd_type}")


failures = 0


def check(label, sample, validator, expect_ok=True):
    global failures
    errors = sorted(validator.iter_errors(sample), key=lambda e: list(e.path))
    ok = not errors
    good = ok == expect_ok
    detail = "" if ok else "  <- " + "; ".join("/".join(map(str, e.path)) + ": " + e.message[:70] for e in errors[:3])
    print(("PASS " if good else "FAIL ") + label + detail)
    if not good:
        failures += 1


def load(name):
    return json.load(open(f"{samples_dir}/{name}", encoding="utf-8"))


check_in, check_out, evidence = load("check_in.json"), load("check_out.json"), load("evidence_metadata.json")
check("check_in", check_in, command_variant("sales.visit.check_in"))
check("check_out", check_out, command_variant("sales.visit.check_out"))
check("evidence metadata", evidence, named("OfficialEvidenceMetadata"))

bad = copy.deepcopy(check_in)
bad["payload"]["visit_uuid"] = "bukan-uuid"
check("[negatif] uuid rusak", bad, command_variant("sales.visit.check_in"), expect_ok=False)
bad = copy.deepcopy(check_in)
bad["payload"]["site"]["radius"] = 500
check("[negatif] radius 500", bad, command_variant("sales.visit.check_in"), expect_ok=False)
bad = copy.deepcopy(evidence)
bad["outlet_id"] = "OUT-7"
check("[negatif] outlet non-angka", bad, named("OfficialEvidenceMetadata"), expect_ok=False)
# Klien native hanya mengirim kunci yang memang dibutuhkan; field opsional `mode` tidak pernah dikirim.
if "mode" in evidence or "mode" in json.dumps(check_in):
    print("FAIL klien native tidak boleh mengirim field mode")
    failures += 1
sys.exit(1 if failures else 0)
