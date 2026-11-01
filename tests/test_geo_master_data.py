"""Invarian paket data master wilayah Sulawesi Utara (data/master + data/geo).

Uji ini menjaga kontrak data yang dipakai loader Odoo:
1 provinsi -> 15 kab/kota -> 171 kecamatan -> 1.839 desa/kelurahan, dengan poligon
yang konsisten antara CSV WKT dan GeoJSON.

Bagian yang membutuhkan `shapely` (luas, tumpang tindih, nesting) di-skip otomatis
bila pustaka tidak tersedia, sehingga uji struktur tetap berjalan di lingkungan minimal.

Jalankan: python -m unittest tests.test_geo_master_data -v
"""

import csv
import json
from pathlib import Path
import math
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data" / "master"
GEO = ROOT / "data" / "geo"

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

LEVELS = {
    "provinsi": "sulut_provinsi.csv",
    "kab_kota": "sulut_kab_kota.csv",
    "kecamatan": "sulut_kecamatan.csv",
    "desa_kelurahan": "sulut_desa_kelurahan.csv",
}

# Desa yang titik-dalamnya berada di kecamatan lain pada sumber (dikecualikan dari dissolve).
MISPLACED_VILLAGES = {"71.01.10.2020", "71.07.10.2006", "71.71.06.1005"}


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


class GeoMasterDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = {level: read_csv(MASTER / name) for level, name in LEVELS.items()}
        cls.polygons = {
            level: {row["kode_kemendagri"]: row for row in read_csv(MASTER / f"sulut_poligon_{level}.csv")}
            for level in LEVELS
        }
        cls.districts_geojson = json.loads((GEO / "sulut_districts.geojson").read_text(encoding="utf-8"))
        cls.villages_geojson = json.loads((GEO / "sulut_villages.geojson").read_text(encoding="utf-8"))

    def test_01_hierarchy_counts(self):
        self.assertEqual(len(self.rows["provinsi"]), 1)
        self.assertEqual(len(self.rows["kab_kota"]), 15)
        self.assertEqual(len(self.rows["kecamatan"]), 171)
        self.assertEqual(len(self.rows["desa_kelurahan"]), 1839)
        jenis = [row["jenis"] for row in self.rows["desa_kelurahan"]]
        self.assertEqual(jenis.count("Kelurahan"), 332)
        self.assertEqual(jenis.count("Desa"), 1507)
        self.assertEqual([row["jenis"].lower() for row in self.rows["kab_kota"]].count("kabupaten"), 11)
        self.assertEqual([row["jenis"].lower() for row in self.rows["kab_kota"]].count("kota"), 4)

    def test_02_codes_unique_and_parents_resolve(self):
        for level, rows in self.rows.items():
            codes = [row["kode_kemendagri"] for row in rows]
            self.assertEqual(len(codes), len(set(codes)), f"kode duplikat di {level}")

        kab_codes = {row["kode_kemendagri"] for row in self.rows["kab_kota"]}
        kec_codes = {row["kode_kemendagri"] for row in self.rows["kecamatan"]}
        for row in self.rows["kecamatan"]:
            self.assertIn(row["kode_kab_kota"], kab_codes)
            self.assertTrue(row["kode_kemendagri"].startswith(row["kode_kab_kota"] + "."))
        for row in self.rows["desa_kelurahan"]:
            self.assertIn(row["kode_kecamatan"], kec_codes)
            self.assertTrue(row["kode_kemendagri"].startswith(row["kode_kecamatan"] + "."))

    def test_03_polygon_files_cover_every_region(self):
        for level, rows in self.rows.items():
            geoms = self.polygons[level]
            self.assertEqual(set(geoms), {row["kode_kemendagri"] for row in rows}, f"kode poligon {level} tidak cocok")
            for row in geoms.values():
                self.assertTrue(row["wkt_epsg4326_lng_lat"].startswith("MULTIPOLYGON"), level)
                self.assertEqual(row["geom_valid_di_output"].lower(), "true", row["kode_kemendagri"])
                self.assertNotEqual(row["qa_flag"], "", row["kode_kemendagri"])

    def test_04_polygon_origin_matches_build_method(self):
        # Kecamatan/kab/provinsi dibentuk dari gabungan desa; desa memakai poligon sumber apa adanya.
        for level in ("provinsi", "kab_kota", "kecamatan"):
            for row in self.polygons[level].values():
                self.assertEqual(row["asal_poligon"], "gabungan_desa", row["kode_kemendagri"])
            for row in self.rows[level]:
                self.assertEqual(row["asal_poligon"], "gabungan_desa", row["kode_kemendagri"])
        for row in self.rows["desa_kelurahan"]:
            self.assertEqual(row["asal_poligon"], "sumber", row["kode_kemendagri"])

    def test_05_geojson_matches_csv(self):
        expected_districts = {row["kode_kemendagri"] for row in self.rows["kecamatan"]}
        got_districts = {feature["properties"]["code"] for feature in self.districts_geojson["features"]}
        self.assertEqual(got_districts, expected_districts)

        expected_villages = {row["kode_kemendagri"] for row in self.rows["desa_kelurahan"]}
        got_villages = {feature["properties"]["code"] for feature in self.villages_geojson["features"]}
        self.assertEqual(got_villages, expected_villages)

        for feature in self.districts_geojson["features"]:
            props = feature["properties"]
            self.assertEqual(props["polygon_origin"], "gabungan_desa")
            self.assertEqual(props["parent_code"], props["code"][:5])
            self.assertIn(feature["geometry"]["type"], ("Polygon", "MultiPolygon"))

    def test_06_postal_codes_filled(self):
        rows = self.rows["desa_kelurahan"]
        self.assertTrue(all(row["kodepos"] for row in rows))
        self.assertTrue(all(row["kodepos"].startswith("95") for row in rows))
        self.assertEqual(len({row["kodepos"] for row in rows}), 269)

    def test_07_misplaced_villages_flagged_low_nesting(self):
        flagged = {row["kode_kemendagri"] for row in self.rows["desa_kelurahan"] if row["qa_flag"] == "periksa_lokasi"}
        self.assertEqual(len(flagged), 19)
        attrs = {row["kode_kemendagri"]: row for row in self.rows["desa_kelurahan"]}
        for code in MISPLACED_VILLAGES:
            self.assertIn("periksa_lokasi", self.polygons["desa_kelurahan"][code]["qa_flag"])
            self.assertLess(float(attrs[code]["qa_persen_di_dalam_induk"]), 50.0)

    def test_08_validation_report_has_no_critical_findings(self):
        report = json.loads((MASTER / "validation_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["ringkasan_jumlah"]["kecamatan"], {"hasil": 171, "diharapkan": 171})
        self.assertEqual(report["temuan_kritis"], [])


class GeoMasterGeometryTests(unittest.TestCase):
    """Pemeriksaan geometri; butuh shapely (>= 2.0)."""

    @classmethod
    def setUpClass(cls):
        try:
            from shapely import from_wkt
            from shapely.geometry import shape
            from shapely.strtree import STRtree
        except ImportError:  # pragma: no cover - lingkungan tanpa shapely
            raise unittest.SkipTest("shapely tidak tersedia")
        cls.from_wkt = staticmethod(from_wkt)
        cls.shape = staticmethod(shape)
        cls.strtree = staticmethod(STRtree)

    KM2_PER_DEG2 = 111.32 ** 2 * math.cos(math.radians(1.3))

    def _wkt(self, level):
        rows = read_csv(MASTER / f"sulut_poligon_{level}.csv")
        return {row["kode_kemendagri"]: self.from_wkt(row["wkt_epsg4326_lng_lat"]) for row in rows}

    def test_01_province_area_in_expected_range(self):
        kab = self._wkt("kab_kota")
        area = sum(geom.area for geom in kab.values()) * self.KM2_PER_DEG2
        # Luas Sulawesi Utara menurut sumber poligon; dipakai sebagai sanity check bukan angka resmi.
        self.assertGreater(area, 13000)
        self.assertLess(area, 16000)

    def test_02_districts_do_not_overlap_materially(self):
        kec = self._wkt("kecamatan")
        codes = sorted(kec)
        geoms = [kec[code] for code in codes]
        tree = self.strtree(geoms)
        overlap = 0.0
        for index, code in enumerate(codes):
            for other in tree.query(kec[code], predicate="intersects"):
                if other <= index:
                    continue
                overlap += kec[code].intersection(geoms[other]).area
        self.assertLess(overlap * self.KM2_PER_DEG2, 5.0)

    def test_03_districts_nested_in_their_city(self):
        kec = self._wkt("kecamatan")
        kab = self._wkt("kab_kota")
        for row in read_csv(MASTER / "sulut_kecamatan.csv"):
            code = row["kode_kemendagri"]
            parent = kab[row["kode_kab_kota"]]
            ratio = kec[code].intersection(parent).area / kec[code].area
            self.assertGreater(ratio, 0.999, code)

    def test_04_village_geometry_valid_and_inside_province(self):
        desa = self._wkt("desa_kelurahan")
        self.assertEqual(len(desa), 1839)
        self.assertTrue(all(geom.is_valid for geom in desa.values()))
        province = self._wkt("provinsi")["71"]
        inside = sum(1 for geom in desa.values() if province.intersects(geom))
        self.assertEqual(inside, 1839)


if __name__ == "__main__":
    unittest.main()
