"""Read-only verification of the geo backfill against the canonical dataset.

Proves set equality, not just counts: every canonical code must exist exactly
once, and no code outside the dataset may carry a Kemendagri code. A swapped
or fabricated code therefore fails even when the row count is unchanged.

Usage (same environment as the loader):

    python scripts/ops/verify_geo_backfill.py [--root .] [--report out.json]

Connection uses the standard PG* variables (PGHOST, PGPORT, PGUSER,
PGPASSWORD, PGDATABASE). The session is opened read-only.

Exit code 0 = all checks pass, 1 = at least one failure, 2 = cannot run.
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

LEVELS = (
    ("city", "id_city", "sulut_kab_kota.csv"),
    ("district", "id_district", "sulut_kecamatan.csv"),
    ("village", "id_subdistrict", "sulut_desa_kelurahan.csv"),
)
LEGACY_VILLAGE_CODES = ("KEL-BTG-GRW", "KEL-TMH-PSL")
EXPECTED = {"city": 15, "district": 171, "village": 1839}
EXPECTED_LEGACY_VILLAGES = 19
EXPECTED_LEGACY_DISTRICTS = 18


def load_codes(path):
    """Return the canonical code set of one master CSV."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["kode_kemendagri"] for row in csv.DictReader(handle) if row.get("kode_kemendagri")}


def compare(dataset, counts):
    """Compare canonical codes with database counts.

    `counts` maps code -> number of rows carrying it. Returns the codes missing
    from the database, the codes present but not canonical, and duplicates.
    """
    found = set(counts)
    return {
        "missing": sorted(dataset - found),
        "extra": sorted(found - dataset),
        "duplicates": sorted(code for code, count in counts.items() if count > 1),
        "rows": sum(counts.values()),
    }


def set_ok(dataset, counts):
    result = compare(dataset, counts)
    return not (result["missing"] or result["extra"] or result["duplicates"]), result


def _connect():
    try:
        import psycopg2
    except ImportError:  # pragma: no cover - environment dependent
        raise SystemExit("psycopg2 is required for the live check")
    params = dict(
        host=os.environ.get("GEO_PG_HOST") or os.environ["PGHOST"],
        port=os.environ.get("GEO_PG_PORT") or os.environ.get("PGPORT", "5432"),
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        dbname=os.environ.get("PGDATABASE", "postgres"),
        connect_timeout=20,
        options="-c default_transaction_read_only=on -c statement_timeout=60000",
    )
    for sslmode in ("require", "prefer"):
        try:
            return psycopg2.connect(sslmode=sslmode, **params)
        except psycopg2.OperationalError:
            last = sys.exc_info()[1]
    raise last


def _counts(cur, table):
    cur.execute(
        f"SELECT kode_kemendagri, count(*) FROM {table} "
        "WHERE kode_kemendagri IS NOT NULL GROUP BY 1"
    )
    return {code: count for code, count in cur.fetchall()}


def _scalar(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def verify(root, conn):
    master = Path(root) / "data" / "master"
    seed = Path(root) / "data" / "seed" / "partners_354.csv"
    results = {"levels": {}, "legacy": {}, "province": {}, "companies": {}, "partners": {}}
    failures = []

    cur = conn.cursor()
    for level, table, filename in LEVELS:
        dataset = load_codes(master / filename)
        counts = _counts(cur, table)
        ok, detail = set_ok(dataset, counts)
        detail["dataset"] = len(dataset)
        detail["expected"] = EXPECTED[level]
        results["levels"][level] = detail
        if len(dataset) != EXPECTED[level]:
            failures.append(f"{level}: dataset has {len(dataset)} codes, expected {EXPECTED[level]}")
        if not ok:
            failures.append(f"{level}: set mismatch {detail}")

    results["legacy"] = {
        "villages": _scalar(cur, "SELECT count(*) FROM id_subdistrict WHERE code LIKE 'KEL-%%'"),
        "districts": _scalar(cur, "SELECT count(*) FROM id_district WHERE code LIKE 'KEC-%%'"),
        "legacy_without_code": _scalar(
            cur, "SELECT count(*) FROM id_subdistrict WHERE is_legacy AND kode_kemendagri IS NULL"
        ),
        "legacy_rows": _scalar(
            cur, "SELECT count(*) FROM id_subdistrict WHERE code = ANY(%s)", (list(LEGACY_VILLAGE_CODES),)
        ),
    }
    if results["legacy"]["villages"] != EXPECTED_LEGACY_VILLAGES:
        failures.append(f"legacy villages: {results['legacy']['villages']}")
    if results["legacy"]["districts"] != EXPECTED_LEGACY_DISTRICTS:
        failures.append(f"legacy districts: {results['legacy']['districts']}")
    if results["legacy"]["legacy_without_code"] != 2:
        failures.append(f"legacy rows without code: {results['legacy']['legacy_without_code']}")
    if results["legacy"]["legacy_rows"] != 2:
        failures.append(f"legacy sentinel rows present: {results['legacy']['legacy_rows']}")

    results["province"] = {
        "cities_without_state": _scalar(
            cur, "SELECT count(*) FROM id_city WHERE kode_kemendagri LIKE '71.%%' AND state_id IS NULL"
        ),
        "districts_without_state": _scalar(
            cur, "SELECT count(*) FROM id_district WHERE kode_kemendagri LIKE '71.%%' AND state_id IS NULL"
        ),
        "coverage_areas_without_state": _scalar(
            cur, "SELECT count(*) FROM id_coverage_area WHERE state_id IS NULL"
        ),
    }
    for key, value in results["province"].items():
        if value:
            failures.append(f"{key}: {value}")

    results["companies"] = {
        "active": _scalar(cur, "SELECT count(*) FROM res_company WHERE active"),
        "without_state": _scalar(
            cur,
            "SELECT count(*) FROM res_company c JOIN res_partner p ON p.id = c.partner_id "
            "WHERE c.active AND p.state_id IS NULL",
        ),
    }
    if results["companies"]["without_state"]:
        failures.append(f"active companies without province: {results['companies']['without_state']}")

    with seed.open(encoding="utf-8-sig", newline="") as handle:
        refs = sorted(row["ref"] for row in csv.DictReader(handle) if row.get("ref"))
    results["partners"] = {
        "seed_refs": len(refs),
        "matched": _scalar(cur, "SELECT count(*) FROM res_partner WHERE ref = ANY(%s)", (refs,)),
        "with_district_fk": _scalar(
            cur, "SELECT count(*) FROM res_partner WHERE ref = ANY(%s) AND district_id IS NOT NULL", (refs,)
        ),
        "with_state": _scalar(
            cur, "SELECT count(*) FROM res_partner WHERE ref = ANY(%s) AND state_id IS NOT NULL", (refs,)
        ),
    }
    for key, expected in (
        ("matched", len(refs)),
        ("with_district_fk", len(refs)),
        ("with_state", len(refs)),
    ):
        if results["partners"][key] != expected:
            failures.append(f"partners {key}: {results['partners'][key]} != {expected}")

    cur.close()
    return results, failures


def print_report(results, failures):
    for level, detail in results["levels"].items():
        status = "PASS" if not (detail["missing"] or detail["extra"] or detail["duplicates"]) else "FAIL"
        print(
            f"[geo_verify] {level}: {status} rows={detail['rows']} dataset={detail['dataset']} "
            f"missing={len(detail['missing'])} extra={len(detail['extra'])} "
            f"duplicates={len(detail['duplicates'])}"
        )
        for key in ("missing", "extra", "duplicates"):
            if detail[key]:
                print(f"[geo_verify]   {key}: {detail[key][:10]}")
    for section in ("legacy", "province", "companies", "partners"):
        print(f"[geo_verify] {section}: {results[section]}")
    if failures:
        print(f"[geo_verify] FAIL ({len(failures)} issue(s))")
        for failure in failures:
            print(f"[geo_verify]   - {failure}")
        return 1
    print("[geo_verify] PASS: dataset set equality and acceptance checks hold")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root (default: current directory)")
    parser.add_argument("--report", help="write the JSON result to this path")
    args = parser.parse_args(argv)

    try:
        conn = _connect()
    except SystemExit as exc:
        print(f"[geo_verify] cannot connect: {exc}")
        return 2
    try:
        results, failures = verify(args.root, conn)
    finally:
        conn.close()

    if args.report:
        Path(args.report).write_text(
            json.dumps({"results": results, "failures": failures}, indent=2, default=str),
            encoding="utf-8",
        )
    return print_report(results, failures)


if __name__ == "__main__":
    sys.exit(main())
