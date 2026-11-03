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
        for city in self.env["id.city"].search([("kode_kemendagri", "like", "71.%")]):
            self.assertEqual(city.state_id, self.province)
        for xmlid in ("area_mnd_urban", "area_tmh_hinterland", "area_btg_port", "area_minut_rural"):
            self.assertEqual(self.env.ref("id_base." + xmlid).state_id, self.province)
        # Putaran kedua tidak boleh menemukan sisa pekerjaan.
        second = self.fixer.ProvinceFixer(self.env).run()
        for key in ("companies", "cities", "districts", "coverage_areas", "partners"):
            self.assertEqual(second[key], 0, key)


    def test_05_mixed_region_province_fill_preserves_scope_and_fks(self):
        other_state = self.env["res.country.state"].search([
            ("country_id", "=", self.province.country_id.id), ("id", "!=", self.province.id)], limit=1)
        self.assertTrue(other_state)
        Partner = self.env["res.partner"]
        district = self.env.ref("id_base.district_mnd_wenang")
        village = self.env.ref("id_base.subdistrict_calaca")
        empty = Partner.create({"name": "Verified Sulut blank",
            "country_id": self.province.country_id.id, "district_id": district.id})
        village_only = Partner.create({"name": "Village only",
            "country_id": self.province.country_id.id, "subdistrict_id": village.id})
        conflict = Partner.create({"name": "Existing province",
            "country_id": self.province.country_id.id, "district_id": district.id,
                                   "state_id": other_state.id})
        archived = Partner.create({"name": "Archived Sulut",
            "country_id": self.province.country_id.id, "district_id": district.id, "active": False})
        unknown = Partner.create({"name": "Unknown blank"})
        Company = self.env["res.company"]
        foreign_company = Company.create({"name": "Java company preserved", "state_id": other_state.id,
                                          "country_id": other_state.country_id.id})
        unknown_company = Company.create({"name": "Unknown company preserved"})
        scoped_company = Company.create({"name": "Verified company", "country_id": self.province.country_id.id})
        scoped_company.partner_id.write({"district_id": district.id, "state_id": False})
        outside_city = self.env["id.city"].create({"name": "Outside city", "code": "3201-review",
            "kode_kemendagri": "32.01", "state_id": other_state.id})
        outside_area = self.env["id.coverage.area"].create({"name": "Outside area", "code": "AREA-OTHER"})
        records = empty | village_only | conflict | archived | unknown
        before = {r.id: (r.state_id.id, r.district_id.id, r.subdistrict_id.id) for r in records}
        self.fixer.ProvinceFixer(self.env, dry_run=True).run()
        self.assertEqual(before, {r.id: (r.state_id.id, r.district_id.id, r.subdistrict_id.id) for r in records})
        self.fixer.ProvinceFixer(self.env).run()
        self.assertEqual(empty.state_id, self.province)
        self.assertEqual(village_only.state_id, self.province)
        self.assertFalse(village_only.district_id)
        self.assertEqual(conflict.state_id, other_state)
        self.assertFalse(archived.state_id)
        self.assertFalse(unknown.state_id)
        self.assertEqual(foreign_company.state_id, other_state)
        self.assertFalse(unknown_company.state_id)
        self.assertEqual(scoped_company.state_id, self.province)
        self.assertEqual(outside_city.state_id, other_state)
        self.assertFalse(outside_area.state_id)
        self.assertEqual({r.id: v[1:] for r, v in ((r, before[r.id]) for r in records)},
                         {r.id: (r.district_id.id, r.subdistrict_id.id) for r in records})
        second = self.fixer.ProvinceFixer(self.env).run()
        for key in ("companies", "cities", "districts", "coverage_areas", "partners"):
            self.assertEqual(second[key], 0)

    def test_06_explicit_company_target_is_fill_only(self):
        from unittest.mock import patch
        company = self.env["res.company"].create({"name": "Explicit company",
            "country_id": self.province.country_id.id})
        with patch.dict("os.environ", {"GEO_PROVINCE_COMPANY_IDS": str(company.id)}):
            self.fixer.ProvinceFixer(self.env, dry_run=True).run()
            self.assertFalse(company.state_id)
            self.fixer.ProvinceFixer(self.env).run()
            self.assertEqual(company.state_id, self.province)
            self.assertEqual(self.fixer.ProvinceFixer(self.env).run()["companies"], 0)

    def test_07_loader_preserves_existing_province_and_fixer_skips_conflicts(self):
        other = self.env["res.country.state"].search([
            ("country_id", "=", self.province.country_id.id), ("id", "!=", self.province.id)], limit=1)
        city = self.env.ref("id_base.city_mnd")
        city.state_id = other
        self.loader.GeoLoader(self.env, self.dataset).run()
        self.assertEqual(city.state_id, other)
        district = self.env.ref("id_base.district_mnd_wenang")
        partner = self.env["res.partner"].create({"name": "Conflicting city province",
            "country_id": self.province.country_id.id, "district_id": district.id})
        self.fixer.ProvinceFixer(self.env).run()
        self.assertFalse(partner.state_id)
        self.assertEqual(city.state_id, other)

    def test_08_archived_verified_city_and_area_are_preserved(self):
        city = self.env.ref("id_base.city_mnd")
        area = self.env.ref("id_base.area_mnd_urban")
        city.write({"state_id": False, "active": False})
        area.write({"state_id": False, "active": False})
        self.loader.GeoLoader(self.env, self.dataset).run()
        self.fixer.ProvinceFixer(self.env).run()
        self.assertFalse(city.state_id)
        self.assertFalse(area.state_id)
