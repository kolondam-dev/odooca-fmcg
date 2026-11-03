#!/usr/bin/env python3
"""Audit geometri outlet FMCG terhadap poligon kecamatan Sulawesi Utara.

Skrip ini **hanya membaca** berkas di `data/` dan menghasilkan laporan; tidak
menulis ke DB, seed, registry, atau poligon. Ini implementasi keputusan D4=A
(laporan saja, tanpa auto-ubah koordinat outlet).

Masukan:

    data/seed/partners_354.csv          354 outlet (latitude/longitude sintetis)
    data/master/legacy_geo_mapping.csv  kode legacy KEC-*/KEL-* -> kode Kemendagri
    data/master/sulut_desa_kelurahan.csv kode pos kanonik desa/kelurahan
    data/geo/sulut_districts.geojson    171 poligon kecamatan

Keluaran:

    docs/reviews/GEO_COVERAGE_AUDIT_<tanggal>.md   laporan (default)
    <report>.json                                  ringkasan mesin (opsional)

Pemakaian:

    python scripts/ops/audit_geo_coverage.py
    python scripts/ops/audit_geo_coverage.py --report /tmp/audit.md --json /tmp/audit.json
    python scripts/ops/audit_geo_coverage.py --fail-on-outside   # untuk gate opsional

Butuh `shapely` (>= 2.0). Tanpa shapely skrip berhenti dengan pesan jelas,
bukan menebak hasil.
"""

import argparse
import csv
import io
import json
import sys
from collections import Counter
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

DEFAULT_REPORT = "docs/reviews/GEO_COVERAGE_AUDIT_2026-11-03.md"
MAPPING_SOURCE = "id_district_data.xml"
PARTNERS = "data/seed/partners_354.csv"
MAPPING = "data/master/legacy_geo_mapping.csv"
VILLAGES = "data/master/sulut_desa_kelurahan.csv"
GEOJSON = "data/geo/sulut_districts.geojson"
SEED_XML = "addons/id_base/data/id_district_data.xml"


def read_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def seed_subdistricts(path):
    """Identitas & kode pos kelurahan legacy dari seed XML (sumber yang ada di `main`)."""
    import xml.etree.ElementTree as ET

    records = {}
    for record in ET.parse(path).getroot().findall("record"):
        model = record.get("model")
        if model not in ("id.subdistrict", "id.district"):
            continue
        fields = {field.get("name"): field.get("ref") or field.text for field in record.findall("field")}
        if fields.get("code"):
            records.setdefault(model, {})[fields["code"]] = fields
    return records.get("id.subdistrict", {}), records.get("id.district", {})


def load_mapping(root):
    """Peta kode legacy -> kode Kemendagri.

    Sumber utama adalah seed `id_district_data.xml` karena itulah identitas yang
    dipakai DB (dan sudah ada di `main`). Bila `data/master/legacy_geo_mapping.csv`
    (PR-3) tersedia, isinya dicek silang; selisih dilaporkan sebagai konflik.
    Dengan begitu laporan tetap sama sebelum dan sesudah PR-3 mendarat.
    """
    villages_seed, districts_seed = seed_subdistricts(root / SEED_XML)
    district_map = {
        code: fields["kode_kemendagri"] for code, fields in districts_seed.items() if fields.get("kode_kemendagri")
    }
    village_map = {
        code: fields["kode_kemendagri"] for code, fields in villages_seed.items() if fields.get("kode_kemendagri")
    }

    conflicts = []
    csv_path = root / MAPPING
    if csv_path.is_file():
        rows = read_csv(csv_path)
        csv_map = {
            level: {
                row["legacy_code"]: row["kode_kemendagri"]
                for row in rows
                if row["level"] == level and row["status"] == "mapped"
            }
            for level in ("district", "subdistrict")
        }
        for level, xml_map in (("district", district_map), ("subdistrict", village_map)):
            for code, kode in sorted(csv_map[level].items()):
                if xml_map.get(code) != kode:
                    conflicts.append(
                        {"level": level, "legacy_code": code, "csv": kode, "seed_xml": xml_map.get(code)}
                    )
    return district_map, village_map, conflicts


def seed_postal_codes(root):
    villages, _districts = seed_subdistricts(root / SEED_XML)
    return {code: fields.get("postal_code") or "" for code, fields in villages.items()}


def load_geometry(path):
    with io.open(path, encoding="utf-8") as handle:
        features = json.load(handle)["features"]
    return features


def audit(root, with_geometry=True):
    """Hitung coverage outlet; `with_geometry=False` hanya memvalidasi pemetaan kode."""
    root = Path(root)
    district_map, village_map, mapping_conflicts = load_mapping(root)
    partners = read_csv(root / PARTNERS)
    canonical_villages = {row["kode_kemendagri"]: row for row in read_csv(root / VILLAGES)}

    report = {
        "mapping_source": MAPPING_SOURCE,
        "mapping_conflicts": mapping_conflicts,
        "partners_total": len(partners),
        "partners_mapped": 0,
        "partners_unmapped": [],
        "outside": [],
        "outside_by_district": {},
        "outside_without_any_polygon": 0,
        "outside_inside_other_district": 0,
        "postal_mismatch": [],
        "legacy_postal_mismatch": [],
    }

    polygons, codes, names, tree = None, [], {}, None
    if with_geometry:
        from shapely.geometry import Point, shape
        from shapely.strtree import STRtree

        features = load_geometry(root / GEOJSON)
        codes = [feature["properties"]["code"] for feature in features]
        names = {feature["properties"]["code"]: feature["properties"]["name"] for feature in features}
        polygons = [shape(feature["geometry"]) for feature in features]
        tree = STRtree(polygons)
        index = {code: position for position, code in enumerate(codes)}
        point_factory = Point

    for partner in partners:
        kode = district_map.get(partner["district_code"])
        if not kode:
            report["partners_unmapped"].append(
                {"ref": partner["ref"], "district_code": partner["district_code"]}
            )
            continue
        report["partners_mapped"] += 1

        village_kode = village_map.get(partner["subdistrict_code"])
        canonical = canonical_villages.get(village_kode or "")
        if canonical and partner["zip"] and partner["zip"] != canonical["kodepos"]:
            report["postal_mismatch"].append(
                {
                    "ref": partner["ref"],
                    "subdistrict_code": partner["subdistrict_code"],
                    "partner_zip": partner["zip"],
                    "canonical_zip": canonical["kodepos"],
                }
            )

        if not with_geometry:
            continue
        latitude, longitude = float(partner["latitude"]), float(partner["longitude"])
        point = point_factory(longitude, latitude)
        if polygons[index[kode]].covers(point):
            continue
        containers = [codes[position] for position in tree.query(point, predicate="covers")]
        report["outside"].append(
            {
                "ref": partner["ref"],
                "name": partner["name"],
                "district_code": partner["district_code"],
                "kode_kemendagri": kode,
                "district_name": names.get(kode, ""),
                "latitude": latitude,
                "longitude": longitude,
                "containers": containers,
            }
        )

    if with_geometry:
        report["outside"].sort(key=lambda row: (row["kode_kemendagri"], row["ref"]))
        report["outside_by_district"] = dict(
            sorted(Counter(row["kode_kemendagri"] for row in report["outside"]).items())
        )
        report["outside_without_any_polygon"] = sum(1 for row in report["outside"] if not row["containers"])
        report["outside_inside_other_district"] = sum(1 for row in report["outside"] if row["containers"])

    seed_postal = seed_postal_codes(root)
    for legacy_code, kode in sorted(village_map.items()):
        canonical = canonical_villages.get(kode)
        legacy_zip = seed_postal.get(legacy_code) or ""
        if canonical and legacy_zip and legacy_zip != canonical["kodepos"]:
            report["legacy_postal_mismatch"].append(
                {
                    "subdistrict_code": legacy_code,
                    "kode_kemendagri": kode,
                    "seed_zip": legacy_zip,
                    "canonical_zip": canonical["kodepos"],
                }
            )
    return report


def render_markdown(report, source_root="."):
    outside = report["outside"]
    lines = [
        "# Audit Coverage Outlet vs Poligon Kecamatan — Sulawesi Utara",
        "",
        "**Dibuat oleh:** `scripts/ops/audit_geo_coverage.py` (baca-saja)",
        "**Keputusan terkait:** D4=A — temuan dilaporkan, **tidak** ada auto-edit koordinat outlet.",
        "**Sumber:** `data/seed/partners_354.csv`, `data/geo/sulut_districts.geojson`; "
        "pemetaan kode legacy dari `addons/id_base/data/id_district_data.xml`, dicek silang dengan "
        "`data/master/legacy_geo_mapping.csv` bila tersedia.",
        "",
        "## 1. Ringkasan",
        "",
        "| Metrik | Nilai |",
        "|---|---:|",
        f"| Outlet diuji | {report['partners_total']} |",
        f"| Outlet dengan kode kecamatan terpetakan | {report['partners_mapped']} |",
        f"| Outlet di luar poligon kecamatan yang ditugaskan | **{len(outside)}** |",
        f"| — di luar seluruh poligon Sulut | {report['outside_without_any_polygon']} |",
        f"| — berada di dalam poligon kecamatan lain | {report['outside_inside_other_district']} |",
        f"| Outlet tanpa pemetaan kode | {len(report['partners_unmapped'])} |",
        f"| Sumber pemetaan kode legacy | `{report['mapping_source']}` |",
        "",
        "Koordinat outlet bersifat sintetis (data demo), jadi angka ini adalah bukti bahwa "
        "deteksi bekerja, bukan vonis kualitas data lapangan.",
        "",
        "## 2. Sebaran temuan per kecamatan",
        "",
        "| Kode Kemendagri | Kecamatan | Outlet di luar |",
        "|---|---|---:|",
    ]
    district_names = {row["kode_kemendagri"]: row["district_name"] for row in outside}
    for kode, count in report["outside_by_district"].items():
        lines.append(f"| `{kode}` | {district_names.get(kode, '')} | {count} |")

    lines += [
        "",
        "## 3. Daftar outlet di luar poligon",
        "",
        "| Ref | Nama | Kecamatan (kode) | Latitude | Longitude | Di dalam poligon lain |",
        "|---|---|---|---:|---:|---|",
    ]
    for row in outside:
        containers = ", ".join(f"`{code}`" for code in row["containers"]) or "—"
        lines.append(
            f"| `{row['ref']}` | {row['name']} | {row['district_name']} (`{row['kode_kemendagri']}`) | "
            f"{row['latitude']:.6f} | {row['longitude']:.6f} | {containers} |"
        )

    lines += [
        "",
        "## 4. Temuan lain (D4=A: dilaporkan, tidak diubah)",
        "",
        f"- Konflik pemetaan kode legacy antara CSV dan seed XML: "
        f"**{len(report['mapping_conflicts'])}** (harus 0).",
        f"- Kode pos partner berbeda dari kode pos kanonik desa/kelurahan: "
        f"**{len(report['postal_mismatch'])}** dari {report['partners_total']} outlet.",
        f"- Kode pos record legacy di seed berbeda dari master: "
        f"**{len(report['legacy_postal_mismatch'])}** dari 17 kelurahan terpetakan.",
        "",
        "Rincian kode pos ada di berkas JSON bila `--json` dipakai; tidak ada nilai yang ditulis ulang.",
        "",
        "## 5. Cara membaca dan menindaklanjuti",
        "",
        "1. Temuan ini **tidak** mengubah data apa pun. Loader `scripts/ops/load_geo_master.py` "
        "hanya mengisi koordinat kelurahan yang masih kosong.",
        "2. Outlet di luar poligon dapat berarti: koordinat sintetis, poligon sumber yang belum presisi, "
        "atau outlet memang di perbatasan. Keputusan lapangan tetap milik pemilik data.",
        "3. Bila koordinat nyata tersedia, perbarui `data/seed/partners_354.csv` lewat PR terpisah "
        "beserta regenerasi artefak rekonsiliasi.",
        "",
        "## 6. Reproduksi",
        "",
        "```bash",
        "python scripts/ops/audit_geo_coverage.py",
        "python -m unittest tests.test_geo_coverage_audit -v",
        "```",
        "",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit coverage outlet vs poligon kecamatan.")
    parser.add_argument("--root", default=".", help="akar repo (default: direktori kerja)")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="berkas markdown keluaran")
    parser.add_argument("--json", default="", help="berkas JSON ringkasan (opsional)")
    parser.add_argument(
        "--fail-on-outside",
        action="store_true",
        help="keluar dengan status 1 bila ada outlet di luar poligon (gate opsional)",
    )
    args = parser.parse_args(argv)

    try:
        report = audit(args.root)
    except ImportError as error:  # pragma: no cover - lingkungan tanpa shapely
        sys.exit(f"[geo_audit] shapely tidak tersedia: {error}")

    markdown = render_markdown(report, args.root)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(markdown, encoding="utf-8", newline="\n")
    print(f"[geo_audit] laporan ditulis: {report_path}")
    print(
        f"[geo_audit] outlet={report['partners_total']} terpetakan={report['partners_mapped']} "
        f"di_luar={len(report['outside'])}"
    )
    if args.json:
        json_path = Path(args.json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"[geo_audit] ringkasan JSON ditulis: {json_path}")
    if args.fail_on_outside and report["outside"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
