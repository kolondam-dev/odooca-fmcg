#!/usr/bin/env python3
"""Muat/backfill master wilayah Sulawesi Utara ke Odoo: id.city, id.district, id.subdistrict.

Dijalankan di dalam Odoo shell (bukan standalone):

    odoo shell -c /tmp/odoo.conf -d <db> --no-http < scripts/ops/load_geo_master.py

Sumber kebenaran (build dataset PR-1, lihat docs/geo/SULUT_ADMINISTRASI_GEO.md):

    data/master/sulut_kab_kota.csv       15 kabupaten/kota
    data/master/sulut_kecamatan.csv      171 kecamatan
    data/master/sulut_desa_kelurahan.csv 1.839 desa/kelurahan
    data/master/legacy_geo_mapping.csv   identitas record lama (KEC-*/KEL-*)
    data/geo/sulut_districts.geojson     poligon, bbox, dan metadata QA kecamatan

Jaminan:

- Idempoten: hanya field yang nilainya berbeda yang ditulis; aman diulang.
- `code` legacy (`KEC-*`/`KEL-*`) tidak pernah diubah, nama legacy tidak diganti.
- Nilai legacy yang sudah terisi (kode pos, lat/lng kelurahan) tidak ditimpa;
  hanya diisi bila masih kosong. Ini menjaga perilaku operasional yang sudah berjalan.
- Tidak menyentuh `res.partner`, transaksi, akuntansi, stok, atau `data/registers`.
- XML seed memakai `noupdate="1"`, jadi instalasi lama tidak ikut diperbarui oleh
  upgrade modul; skrip inilah jalur backfill-nya.

Variabel lingkungan:

    GEO_LOAD_DRY_RUN=1        hitung perubahan tanpa menulis ke DB
    GEO_LOAD_SKIP_POLYGON=1   lewati geojson_polygon (lebih cepat, bbox tetap diisi)
"""

import csv
import datetime
import json
import os
import pathlib
import sys

try:  # tersedia hanya di dalam Odoo shell
    from odoo import fields as odoo_fields
except ImportError:  # pragma: no cover - unit test di luar Odoo
    odoo_fields = None

PROVINCE_XMLID = "base.state_id_sa"
IN_TOWN_CITY_CODE = "7171"  # Kota Manado: satu-satunya kab/kota yang bukan "luar kota"
DISTRICT_GEOJSON = "sulut_districts.geojson"
MARKER = "sulut_kecamatan.csv"

EXPECTED = {"cities": 15, "districts": 171, "villages": 1839}
FLOAT_DIGITS = {"latitude": 7, "longitude": 7, "area_km2": 3, "bbox_xmin": 6, "bbox_ymin": 6, "bbox_xmax": 6,
                "bbox_ymax": 6}


def env_flag(name):
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def to_float(value):
    text = (value or "").strip()
    return float(text) if text else 0.0


def resolve_master_dir():
    """Cari data/master dari cwd, lokasi kontainer (/opt), atau relatif terhadap skrip."""
    candidates = [pathlib.Path("data/master"), pathlib.Path("/opt/data/master")]
    if "__file__" in globals():
        here = pathlib.Path(__file__).resolve().parent
        candidates.append(here.parent.parent / "data" / "master")
    for candidate in candidates:
        if (candidate / MARKER).is_file():
            return candidate
    raise FileNotFoundError(f"[geo_loader] data/master tidak ditemukan; kandidat: {candidates}")


def resolve_geo_dir(master_dir):
    candidate = master_dir.parent / "geo"
    if (candidate / DISTRICT_GEOJSON).is_file():
        return candidate
    raise FileNotFoundError(f"[geo_loader] {DISTRICT_GEOJSON} tidak ditemukan di {candidate}")


def bbox_of(geometry):
    """Bounding box (xmin, ymin, xmax, ymax) dari geometry GeoJSON, tanpa shapely."""
    xs, ys = [], []
    stack = [geometry.get("coordinates") or []]
    while stack:
        node = stack.pop()
        if not node:
            continue
        if isinstance(node[0], (int, float)):
            xs.append(float(node[0]))
            ys.append(float(node[1]))
        else:
            stack.extend(node)
    if not xs:
        raise ValueError("geometry tanpa koordinat")
    return min(xs), min(ys), max(xs), max(ys)


def load_dataset(master_dir, geo_dir):
    """Baca CSV/GeoJSON dan pastikan bentuknya sesuai kontrak dataset."""
    dataset = {
        "cities": read_csv(master_dir / "sulut_kab_kota.csv"),
        "districts": read_csv(master_dir / "sulut_kecamatan.csv"),
        "villages": read_csv(master_dir / "sulut_desa_kelurahan.csv"),
        "mapping": read_csv(master_dir / "legacy_geo_mapping.csv"),
    }
    with open(geo_dir / DISTRICT_GEOJSON, encoding="utf-8") as handle:
        features = json.load(handle)["features"]
    dataset["district_geo"] = {feature["properties"]["code"]: feature for feature in features}

    for key, expected in EXPECTED.items():
        if len(dataset[key]) != expected:
            raise ValueError(f"[geo_loader] {key}: {len(dataset[key])} baris, seharusnya {expected}")
    if len(dataset["district_geo"]) != EXPECTED["districts"]:
        raise ValueError(f"[geo_loader] geojson kecamatan: {len(dataset['district_geo'])} fitur")

    for key, field in (("cities", "kode_kemendagri"), ("districts", "kode_kemendagri"),
                       ("villages", "kode_kemendagri")):
        codes = [row[field] for row in dataset[key]]
        if len(set(codes)) != len(codes):
            raise ValueError(f"[geo_loader] {key}: kode_kemendagri duplikat di sumber")
    return dataset


class GeoLoader:
    """Backfill idempoten master wilayah dari dataset kanonik."""

    def __init__(self, env, dataset, dry_run=False, with_polygons=True):
        self.env = env
        self.dataset = dataset
        self.dry_run = dry_run
        self.with_polygons = with_polygons
        self.province = env.ref(PROVINCE_XMLID, raise_if_not_found=False)
        self.report = {
            "cities": self._stats(),
            "districts": self._stats(),
            "villages": self._stats(),
            "warnings": [],
        }

    @staticmethod
    def _stats():
        return {"created": 0, "updated": 0, "unchanged": 0, "fields": {}}

    # ---------------------------------------------------------------- util
    def _same(self, record, field, value):
        current = record[field]
        field_type = record._fields[field].type
        if field_type == "many2one":
            return (current.id or False) == (value or False)
        if field_type == "float":
            places = FLOAT_DIGITS.get(field, 6)
            return round(current or 0.0, places) == round(value or 0.0, places)
        return (current or False) == (value or False)

    def _changed(self, record, values):
        return {name: value for name, value in values.items() if not self._same(record, name, value)}

    def _create(self, model, values, stats):
        stats["created"] += 1
        if self.dry_run:
            return None
        return model.create(values)

    def _update(self, record, values, stats):
        changes = self._changed(record, values)
        if not changes:
            stats["unchanged"] += 1
            return False
        stats["updated"] += 1
        for name in changes:
            stats["fields"][name] = stats["fields"].get(name, 0) + 1
        if not self.dry_run:
            record.write(changes)
        return True

    def _warn(self, message):
        self.report["warnings"].append(message)

    @staticmethod
    def _index(records, key):
        index = {}
        for record in records:
            value = key(record)
            if value:
                index.setdefault(value, record)
        return index

    def _geometry_values(self, record, feature):
        """Nilai geometri kecamatan; `geom_updated_at` hanya berubah bila geometri berubah."""
        geometry = feature["geometry"]
        polygon = json.dumps(geometry, separators=(",", ":"), ensure_ascii=False)
        xmin, ymin, xmax, ymax = bbox_of(geometry)
        properties = feature["properties"]
        bbox = {"bbox_xmin": xmin, "bbox_ymin": ymin, "bbox_xmax": xmax, "bbox_ymax": ymax}
        if record is not None and (record.geojson_polygon or "") == polygon:
            if all(self._same(record, name, value) for name, value in bbox.items()):
                return {}
        values = dict(bbox)
        if self.with_polygons:
            values["geojson_polygon"] = polygon
        values["geom_source"] = (properties.get("source") or "")[:255]
        values["geom_quality"] = (properties.get("qa_flag") or "")[:255]
        values["geom_updated_at"] = (
            odoo_fields.Datetime.now() if odoo_fields else datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        )
        return values

    # ---------------------------------------------------------------- cities
    def _load_cities(self):
        City = self.env["id.city"].sudo().with_context(active_test=False)
        stats = self.report["cities"]
        existing = City.search([])
        by_code = self._index(existing, lambda record: record.code)
        by_kode = self._index(existing, lambda record: record.kode_kemendagri)
        for row in self.dataset["cities"]:
            values = {
                "kode_kemendagri": row["kode_kemendagri"],
                "type": "kota" if row["jenis"].strip().lower() == "kota" else "kabupaten",
                "state_id": self.province.id,
                "latitude": to_float(row["lat_titik_dalam"]),
                "longitude": to_float(row["lng_titik_dalam"]),
                "area_km2": to_float(row["luas_km2_approx"]),
            }
            record = by_code.get(row["kode_nodot"]) or by_kode.get(row["kode_kemendagri"])
            if record is None:
                values.update(
                    {
                        "code": row["kode_nodot"],
                        "name": row["nama"],
                        "is_out_of_town": row["kode_nodot"] != IN_TOWN_CITY_CODE,
                    }
                )
                self._create(City, values, stats)
            else:
                if record.state_id or not record.active:
                    values.pop("state_id")  # Province backfill never overwrites an existing state.
                self._update(record, values, stats)

    # ---------------------------------------------------------------- districts
    def _load_districts(self):
        District = self.env["id.district"].sudo().with_context(active_test=False)
        City = self.env["id.city"].sudo().with_context(active_test=False)
        stats = self.report["districts"]
        city_by_kode = self._index(City.search([("kode_kemendagri", "!=", False)]),
                                   lambda record: record.kode_kemendagri)
        existing = District.search([])
        by_kode = self._index(existing, lambda record: record.kode_kemendagri)
        by_code = self._index(existing, lambda record: record.code)
        by_parent_name = self._index(
            existing, lambda record: (record.city_id.kode_kemendagri, (record.name or "").strip().lower())
        )
        legacy_by_kode = {
            row["kode_kemendagri"]: row["legacy_code"]
            for row in self.dataset["mapping"]
            if row["level"] == "district" and row["status"] == "mapped"
        }

        for row in self.dataset["districts"]:
            city = city_by_kode.get(row["kode_kab_kota"])
            if city is None:
                self._warn(f"kecamatan {row['kode_kemendagri']}: kab/kota {row['kode_kab_kota']} tidak ada")
                continue
            record = by_kode.get(row["kode_kemendagri"])
            if record is None:
                record = by_code.get(legacy_by_kode.get(row["kode_kemendagri"]))
            if record is None:
                record = by_parent_name.get((row["kode_kab_kota"], row["nama"].strip().lower()))

            values = {
                "kode_kemendagri": row["kode_kemendagri"],
                "city_id": city.id,
                # Field teks legacy dijaga identik dengan relasi (lihat tests/test_geo_master.py).
                "city": city.name,
                "latitude": to_float(row["lat_titik_dalam"]),
                "longitude": to_float(row["lng_titik_dalam"]),
                "area_km2": to_float(row["luas_km2_approx"]),
            }
            feature = self.dataset["district_geo"].get(row["kode_kemendagri"])
            if feature is None:
                self._warn(f"kecamatan {row['kode_kemendagri']}: poligon tidak ditemukan di geojson")
            else:
                values.update(self._geometry_values(record, feature))

            if record is None:
                values["code"] = row["kode_kemendagri"]
                values["name"] = row["nama"]
                self._create(District, values, stats)
            else:
                self._update(record, values, stats)

    # ---------------------------------------------------------------- villages
    def _load_villages(self):
        Subdistrict = self.env["id.subdistrict"].sudo().with_context(active_test=False)
        District = self.env["id.district"].sudo().with_context(active_test=False)
        stats = self.report["villages"]
        district_by_kode = self._index(District.search([("kode_kemendagri", "!=", False)]),
                                       lambda record: record.kode_kemendagri)
        existing = Subdistrict.search([])
        by_kode = self._index(existing, lambda record: record.kode_kemendagri)
        by_code = self._index(existing, lambda record: record.code)
        legacy_by_kode = {
            row["kode_kemendagri"]: row["legacy_code"]
            for row in self.dataset["mapping"]
            if row["level"] == "subdistrict" and row["status"] == "mapped"
        }

        for row in self.dataset["villages"]:
            district = district_by_kode.get(row["kode_kecamatan"])
            if district is None:
                self._warn(f"desa {row['kode_kemendagri']}: kecamatan {row['kode_kecamatan']} tidak ada")
                continue
            record = by_kode.get(row["kode_kemendagri"])
            if record is None:
                record = by_code.get(legacy_by_kode.get(row["kode_kemendagri"]))

            values = {
                "kode_kemendagri": row["kode_kemendagri"],
                "district_id": district.id,
                "area_km2": to_float(row["luas_km2_approx"]),
                "is_legacy": False,
            }
            if record is None:
                values.update(
                    {
                        "name": row["nama"],
                        "code": row["kode_kemendagri"],
                        "postal_code": row["kodepos"],
                        "latitude": to_float(row["lat_titik_dalam"]),
                        "longitude": to_float(row["lng_titik_dalam"]),
                    }
                )
                self._create(Subdistrict, values, stats)
                continue
            # Nilai legacy yang sudah ada dipertahankan (keputusan D4=A: laporan, bukan auto-ubah).
            if not record.postal_code:
                values["postal_code"] = row["kodepos"]
            if not record.latitude and not record.longitude:
                values["latitude"] = to_float(row["lat_titik_dalam"])
                values["longitude"] = to_float(row["lng_titik_dalam"])
            self._update(record, values, stats)

        # Dua kelurahan legacy tanpa padanan 1:1 tetap ada, ditandai agar tidak ditebak.
        for row in self.dataset["mapping"]:
            if row["level"] != "subdistrict" or row["status"] != "legacy":
                continue
            record = by_code.get(row["legacy_code"])
            if record is None:
                self._warn(f"kelurahan legacy {row['legacy_code']} tidak ditemukan")
                continue
            self._update(record, {"is_legacy": True}, stats)

    # ---------------------------------------------------------------- verify
    def _verify(self):
        """Pastikan seluruh kode dataset benar-benar ada dan hierarkinya utuh.

        Yang dihitung adalah kemunculan kode dataset, bukan seluruh isi tabel: DB
        boleh berisi record wilayah tambahan di luar paket ini (mis. record uji).
        """
        City = self.env["id.city"].sudo().with_context(active_test=False)
        District = self.env["id.district"].sudo().with_context(active_test=False)
        Subdistrict = self.env["id.subdistrict"].sudo().with_context(active_test=False)
        codes = {key: [row["kode_kemendagri"] for row in self.dataset[key]] for key in EXPECTED}
        counts = {
            "cities": City.search_count([("kode_kemendagri", "in", codes["cities"])]),
            "districts": District.search_count([("kode_kemendagri", "in", codes["districts"])]),
            "villages": Subdistrict.search_count([("kode_kemendagri", "in", codes["villages"])]),
        }
        self.report["counts"] = counts
        if self.dry_run:
            return
        for key, expected in EXPECTED.items():
            if counts[key] != expected:
                raise RuntimeError(
                    f"[geo_loader] {key}: {counts[key]} dari {expected} kode dataset ditemukan"
                )
        without_city = District.search_count(
            [("kode_kemendagri", "in", codes["districts"]), ("city_id", "=", False)]
        )
        if without_city:
            raise RuntimeError(f"[geo_loader] {without_city} kecamatan dataset tanpa city_id")

    def run(self):
        if self.province is None:
            raise RuntimeError(f"[geo_loader] provinsi {PROVINCE_XMLID} tidak ditemukan")
        self._load_cities()
        self._load_districts()
        self._load_villages()
        self._verify()
        return self.report


def print_report(report, dry_run):
    prefix = "[geo_loader] DRY-RUN" if dry_run else "[geo_loader]"
    for level in ("cities", "districts", "villages"):
        stats = report[level]
        fields = ", ".join(f"{name}={count}" for name, count in sorted(stats["fields"].items())) or "-"
        print(
            f"{prefix} {level}: dibuat={stats['created']} diperbarui={stats['updated']} "
            f"tetap={stats['unchanged']} ({fields})"
        )
    counts = report.get("counts") or {}
    if counts:
        print(f"{prefix} kode dataset ditemukan: {counts}")
    for warning in report["warnings"][:20]:
        print(f"{prefix} PERINGATAN: {warning}")
    if len(report["warnings"]) > 20:
        print(f"{prefix} PERINGATAN: {len(report['warnings']) - 20} peringatan lain tidak ditampilkan")


def main(env):
    master_dir = resolve_master_dir()
    dataset = load_dataset(master_dir, resolve_geo_dir(master_dir))
    dry_run = env_flag("GEO_LOAD_DRY_RUN")
    loader = GeoLoader(env, dataset, dry_run=dry_run, with_polygons=not env_flag("GEO_LOAD_SKIP_POLYGON"))
    report = loader.run()
    print_report(report, dry_run)
    if dry_run:
        print("[geo_loader] DRY-RUN selesai; tidak ada perubahan yang di-commit.")
        return report
    env.cr.commit()
    print("[geo_loader] selesai dan di-commit.")
    return report


if "env" in globals():
    try:
        main(globals()["env"])
    except Exception:
        globals()["env"].cr.rollback()
        import traceback

        traceback.print_exc()
        raise
elif __name__ == "__main__":  # pragma: no cover - dijalankan di luar Odoo shell
    sys.exit("[geo_loader] skrip ini harus dijalankan di dalam Odoo shell (objek 'env' tidak ada).")
