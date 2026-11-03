"""Uji runtime loader master wilayah (PR-3) di DB Odoo sungguhan.

Yang dibuktikan:

1. `scripts/ops/load_geo_master.py` melengkapi hierarki 15/171/1.839 dan
   mempertahankan identitas legacy (`KEC-*`/`KEL-*`, 2 kelurahan `is_legacy`).
2. Loader idempoten: putaran kedua tidak membuat/mengubah satu record pun.
3. `scripts/ops/fix_geo_province.py` mengisi `state_id` dan idempoten.

Uji ini berjalan di CI `install-test` (`--test-tags /id_base`). Skrip dibaca dari
`/opt/scripts/ops/...` (image) atau `<repo>/scripts/ops/...` (lokal).
"""

import importlib.util
import pathlib

from odoo.tests.common import TransactionCase


def load_script(relative_path):
    root = pathlib.Path(__file__).resolve().parents[3]
    path = root / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"skrip geo tidak ditemukan: {path}")
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestGeoMasterLoader(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loader = load_script("scripts/ops/load_geo_master.py")
        cls.fixer = load_script("scripts/ops/fix_geo_province.py")
        master_dir = cls.loader.resolve_master_dir()
        cls.dataset = cls.loader.load_dataset(master_dir, cls.loader.resolve_geo_dir(master_dir))
        # Satu kali backfill untuk seluruh kelas; tiap metode uji memakai savepoint.
        cls.first_report = cls.loader.GeoLoader(cls.env, cls.dataset).run()
        cls.District = cls.env["id.district"].with_context(active_test=False)
        cls.Subdistrict = cls.env["id.subdistrict"].with_context(active_test=False)
        cls.province = cls.env.ref("base.state_id_sa")

    def test_01_loader_fills_full_hierarchy(self):
        self.assertEqual(self.first_report["counts"], {"cities": 15, "districts": 171, "villages": 1839})
        self.assertGreater(self.first_report["districts"]["created"], 0)
        self.assertGreater(self.first_report["villages"]["created"], 0)
        self.assertEqual(self.first_report["warnings"], [])

    def test_02_legacy_identity_geometry_and_province(self):
        village = self.env.ref("id_base.subdistrict_calaca")
        self.assertEqual(village.code, "KEL-MND-CLC")
        self.assertEqual(village.kode_kemendagri, "71.71.04.1008")
        self.assertAlmostEqual(village.area_km2, 0.225, places=3)
        self.assertFalse(village.is_legacy)

        girian = self.env.ref("id_base.subdistrict_girian_weru")
        self.assertTrue(girian.is_legacy)
        self.assertFalse(girian.kode_kemendagri)

        wenang = self.env.ref("id_base.district_mnd_wenang")
        self.assertEqual(wenang.kode_kemendagri, "71.71.04")
        self.assertTrue(wenang.geojson_polygon)
        # Satu-satunya kecamatan ber-flag QA "batas_tidak_presisi" di dataset adalah Wenang.
        self.assertEqual(wenang.geom_quality, "batas_tidak_presisi")
        self.assertTrue(wenang.geom_updated_at)
        self.assertAlmostEqual(wenang.bbox_xmin, 124.830102, places=6)
        self.assertAlmostEqual(wenang.bbox_ymax, 1.499840, places=6)
        self.assertEqual(wenang.state_id, self.province)

        sample = self.District.search([("kode_kemendagri", "=", "71.04.05")])
        self.assertEqual(len(sample), 1)
        self.assertEqual(sample.code, "71.04.05")
        self.assertEqual(sample.city_id.kode_kemendagri, "71.04")
        self.assertEqual(sample.state_id, self.province)

        villages = self.Subdistrict.search([("kode_kemendagri", "=", "71.01.05.2001")])
        self.assertEqual(len(villages), 1)
        self.assertEqual(villages.district_id.kode_kemendagri, "71.01.05")

    def test_03_loader_is_idempotent(self):
        second = self.loader.GeoLoader(self.env, self.dataset).run()
        for level in ("cities", "districts", "villages"):
            self.assertEqual(second[level]["created"], 0, level)
            self.assertEqual(second[level]["updated"], 0, f"{level}: {second[level]['fields']}")

    def test_04_province_fix_fills_and_is_idempotent(self):
        self.fixer.ProvinceFixer(self.env).run()
        for company in self.env["res.company"].with_context(active_test=False).search([]):
            self.assertEqual(company.state_id, self.province, company.name)
        self.assertEqual(self.env.company.state_id, self.province)
        for area in self.env["id.coverage.area"].with_context(active_test=False).search([]):
            self.assertEqual(area.state_id, self.province, area.code)
        for partner in self.env["res.partner"].with_context(active_test=False).search(
            [("district_id", "!=", False)]
        ):
            self.assertEqual(partner.state_id, self.province, partner.name)

        # Putaran kedua tidak boleh menemukan sisa pekerjaan.
        second = self.fixer.ProvinceFixer(self.env).run()
        for key in ("companies", "cities", "districts", "coverage_areas", "partners"):
            self.assertEqual(second[key], 0, key)
        self.assertEqual(second["partners_village_only"], 0)
