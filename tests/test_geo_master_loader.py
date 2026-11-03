"""Kontrak loader master wilayah: mapping legacy, dataset kanonik, dan geometri.

Uji ini tidak membutuhkan Odoo/DB. Yang dijaga:

1. `data/master/legacy_geo_mapping.csv` konsisten dengan seed XML (18 kecamatan +
   19 kelurahan, 17 dipetakan, 2 legacy) dan dengan dataset kanonik.
2. `scripts/ops/load_geo_master.py` membaca 15/171/1.839 record dengan hierarki
   yang utuh (setiap kecamatan punya kab/kota, setiap desa punya kecamatan).
3. Bounding box yang dihitung loader dari GeoJSON sama dengan bbox di seed XML,
   sehingga backfill DB lama dan instalasi baru menghasilkan nilai identik.
4. `area_km2` seed kelurahan yang dipetakan sama dengan dataset kanonik.

Jalankan: python -m unittest tests.test_geo_master_loader -v
"""

import csv
import importlib.util
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data" / "master"
GEO = ROOT / "data" / "geo"
SEED_XML = ROOT / "addons" / "id_base" / "data" / "id_district_data.xml"
LOADER = ROOT / "scripts" / "ops" / "load_geo_master.py"

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load_loader_module():
    spec = importlib.util.spec_from_file_location("load_geo_master_under_test", LOADER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_records():
    records = {"district": {}, "subdistrict": {}}
    for record in ET.parse(SEED_XML).getroot().findall("record"):
        model = record.get("model", "").split(".")[-1]
        if model not in records:
            continue
        fields = {field.get("name"): field.get("ref") or field.text for field in record.findall("field")}
        records[model][fields["code"]] = fields
    return records


class GeoMasterLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loader = load_loader_module()
        cls.dataset = cls.loader.load_dataset(MASTER, GEO)
        cls.mapping = read_csv(MASTER / "legacy_geo_mapping.csv")
        cls.seed = seed_records()
        cls.cities = {row["kode_kemendagri"]: row for row in cls.dataset["cities"]}
        cls.districts = {row["kode_kemendagri"]: row for row in cls.dataset["districts"]}
        cls.villages = {row["kode_kemendagri"]: row for row in cls.dataset["villages"]}

    def test_01_mapping_shape_and_status(self):
        districts = [row for row in self.mapping if row["level"] == "district"]
        villages = [row for row in self.mapping if row["level"] == "subdistrict"]
        self.assertEqual(len(districts), 18)
        self.assertEqual(len(villages), 19)
        self.assertEqual(len({row["legacy_code"] for row in self.mapping}), 37)
        legacy = [row["legacy_code"] for row in self.mapping if row["status"] == "legacy"]
        self.assertEqual(sorted(legacy), ["KEL-BTG-GRW", "KEL-TMH-PSL"])
        for row in self.mapping:
            if row["status"] == "mapped":
                self.assertTrue(row["kode_kemendagri"], row["legacy_code"])
                self.assertTrue(row["canonical_name"], row["legacy_code"])
            else:
                self.assertFalse(row["kode_kemendagri"], row["legacy_code"])
                self.assertTrue(row["note"], row["legacy_code"])

    def test_02_mapping_matches_seed_xml(self):
        for level in ("district", "subdistrict"):
            seed = self.seed[level]
            mapped = {row["legacy_code"]: row for row in self.mapping if row["level"] == level}
            self.assertEqual(set(seed), set(mapped), level)
            for code, fields in seed.items():
                self.assertEqual(mapped[code]["legacy_name"], fields["name"], code)
                self.assertEqual(mapped[code]["kode_kemendagri"], fields.get("kode_kemendagri", ""), code)

    def test_03_mapped_codes_exist_in_canonical_dataset(self):
        for row in self.mapping:
            if row["status"] != "mapped":
                continue
            source = self.districts if row["level"] == "district" else self.villages
            canonical = source.get(row["kode_kemendagri"])
            self.assertIsNotNone(canonical, row["legacy_code"])
            self.assertEqual(canonical["nama"], row["canonical_name"], row["legacy_code"])
            if row["level"] == "district":
                self.assertIn(canonical["kode_kab_kota"], self.cities, row["legacy_code"])
            else:
                self.assertIn(canonical["kode_kecamatan"], self.districts, row["legacy_code"])

    def test_04_hierarchy_is_complete(self):
        self.assertEqual(len(self.cities), 15)
        self.assertEqual(len(self.districts), 171)
        self.assertEqual(len(self.villages), 1839)
        for kode, district in self.districts.items():
            self.assertIn(district["kode_kab_kota"], self.cities, kode)
            self.assertTrue(kode.startswith(district["kode_kab_kota"] + "."), kode)
        for kode, village in self.villages.items():
            self.assertIn(village["kode_kecamatan"], self.districts, kode)
            self.assertTrue(kode.startswith(village["kode_kecamatan"] + "."), kode)

    def test_05_geojson_covers_every_district(self):
        self.assertEqual(set(self.dataset["district_geo"]), set(self.districts))

    def test_05b_geojson_qa_flag_summary(self):
        """Satu-satunya kecamatan ber-flag QA non-ok adalah Wenang (71.71.04).

        Nilai ini dipakai uji runtime (`geom_quality`), jadi dikunci di sini agar
        perubahan dataset tidak lolos tanpa sadar.
        """
        flagged = {
            code: feature["properties"]["qa_flag"]
            for code, feature in self.dataset["district_geo"].items()
            if feature["properties"]["qa_flag"] != "ok"
        }
        self.assertEqual(flagged, {"71.71.04": "batas_tidak_presisi"})
        for feature in self.dataset["district_geo"].values():
            self.assertTrue(feature["properties"]["source"], feature["properties"]["code"])

    def test_06_bbox_matches_seed_xml(self):
        for code, fields in self.seed["district"].items():
            feature = self.dataset["district_geo"][fields["kode_kemendagri"]]
            xmin, ymin, xmax, ymax = self.loader.bbox_of(feature["geometry"])
            self.assertAlmostEqual(xmin, float(fields["bbox_xmin"]), places=6, msg=code)
            self.assertAlmostEqual(ymin, float(fields["bbox_ymin"]), places=6, msg=code)
            self.assertAlmostEqual(xmax, float(fields["bbox_xmax"]), places=6, msg=code)
            self.assertAlmostEqual(ymax, float(fields["bbox_ymax"]), places=6, msg=code)
            # Titik representatif seed harus berada di dalam bbox.
            self.assertTrue(xmin <= float(fields["longitude"]) <= xmax, code)
            self.assertTrue(ymin <= float(fields["latitude"]) <= ymax, code)

    def test_07_seed_village_area_matches_dataset(self):
        for code, fields in self.seed["subdistrict"].items():
            kode = fields.get("kode_kemendagri", "")
            if not kode:
                self.assertNotIn("area_km2", fields, code)
                continue
            self.assertIn("area_km2", fields, code)
            self.assertAlmostEqual(float(fields["area_km2"]), float(self.villages[kode]["luas_km2_approx"]), places=3)

    def test_08_seed_district_area_and_point_match_dataset(self):
        for code, fields in self.seed["district"].items():
            canonical = self.districts[fields["kode_kemendagri"]]
            self.assertAlmostEqual(float(fields["area_km2"]), float(canonical["luas_km2_approx"]), places=3, msg=code)
            self.assertAlmostEqual(float(fields["latitude"]), float(canonical["lat_titik_dalam"]), places=6, msg=code)
            self.assertAlmostEqual(float(fields["longitude"]), float(canonical["lng_titik_dalam"]), places=6, msg=code)

    def test_09_bbox_of_handles_nested_rings(self):
        geometry = {
            "type": "MultiPolygon",
            "coordinates": [[[[124.0, 1.0], [124.5, 1.0], [124.5, 1.5], [124.0, 1.5], [124.0, 1.0]]],
                            [[[125.0, 2.0], [125.2, 2.0], [125.2, 2.1], [125.0, 2.0]]]],
        }
        self.assertEqual(self.loader.bbox_of(geometry), (124.0, 1.0, 125.2, 2.1))
        with self.assertRaises(ValueError):
            self.loader.bbox_of({"type": "MultiPolygon", "coordinates": []})

    def test_10_loader_module_has_no_import_side_effect(self):
        """Mengimpor modul loader tidak boleh menjalankan main()/menulis DB."""
        self.assertTrue(hasattr(self.loader, "GeoLoader"))
        self.assertNotIn("env", self.loader.__dict__)
        self.assertIsNone(re.search(r"^main\(", LOADER.read_text(encoding="utf-8"), re.M))


if __name__ == "__main__":
    unittest.main()
