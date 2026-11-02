from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

# Expected identities after PR-2 (see docs/reviews/GEO_BASELINE_2026-11-01.md).
CITY_KODE = {
    "7171": "71.71",
    "7172": "71.72",
    "7173": "71.73",
    "7174": "71.74",
    "7102": "71.02",
    "7106": "71.06",
    "7105": "71.05",
    "7107": "71.07",
    "7101": "71.01",
    "7108": "71.08",
    "7111": "71.11",
    "7110": "71.10",
    "7103": "71.03",
    "7109": "71.09",
    "7104": "71.04",
}

DISTRICT_KODE = {
    "KEC-MND-WNG": "71.71.04",
    "KEC-MND-SRO": "71.71.06",
    "KEC-MND-MLY": "71.71.09",
    "KEC-MND-WNA": "71.71.07",
    "KEC-MND-TKL": "71.71.05",
    "KEC-MND-PLD": "71.71.11",
    "KEC-MND-TMT": "71.71.02",
    "KEC-MND-SKL": "71.71.03",
    "KEC-MND-MPG": "71.71.08",
    "KEC-BTG-MAS": "71.72.07",
    "KEC-BTG-MDR": "71.72.02",
    "KEC-BTG-GRN": "71.72.06",
    "KEC-BTG-ATB": "71.72.04",
    "KEC-TMH-TGH": "71.73.02",
    "KEC-MNH-TDN": "71.02.01",
    "KEC-MNH-KWG": "71.02.12",
    "KEC-MNT-AMD": "71.06.03",
    "KEC-MNS-AMR": "71.05.10",
}

# code -> (kode_kemendagri, is_legacy)
SUB_KODE = {
    "KEL-MND-CLC": ("71.71.04.1008", False),
    "KEL-MND-WNS": ("71.71.04.1006", False),
    "KEL-MND-SKB": ("71.71.06.1002", False),
    "KEL-MND-BAH": ("71.71.09.1002", False),
    "KEL-MND-TKB": ("71.71.05.1008", False),
    "KEL-MND-PLD": ("71.71.11.1003", False),
    "KEL-MND-TMT": ("71.71.02.1002", False),
    "KEL-MND-PKB": ("71.71.08.1001", False),
    "KEL-BTG-BTM": ("71.72.07.1005", False),
    "KEL-TMH-PSL": ("", True),
    "KEL-MNH-RNG": ("71.02.01.1008", False),
    "KEL-MNH-SDG": ("71.02.12.1005", False),
    "KEL-MNT-AMA": ("71.06.03.1008", False),
    "KEL-MNS-BYG": ("71.05.10.1004", False),
    "KEL-MND-PKW": ("71.71.07.1003", False),
    "KEL-MND-KRM": ("71.71.03.1004", False),
    "KEL-BTG-MDU": ("71.72.02.1003", False),
    "KEL-BTG-GRW": ("", True),
    "KEL-BTG-ATB": ("71.72.04.1005", False),
}


class TestGeoMaster(TransactionCase):
    """Identity, hierarchy, and seed-consistency checks for the Sulut master data."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.province = cls.env.ref("base.state_id_sa")
        cls.City = cls.env["id.city"].with_context(active_test=False)
        cls.District = cls.env["id.district"].with_context(active_test=False)
        cls.Subdistrict = cls.env["id.subdistrict"].with_context(active_test=False)

    def _by_code(self, model, codes):
        records = model.search([("code", "in", list(codes))])
        found = {record.code: record for record in records}
        self.assertEqual(set(found), set(codes), "seed records missing or duplicated")
        return found

    def test_01_city_identity_and_province(self):
        cities = self._by_code(self.City, CITY_KODE)
        self.assertEqual(len(cities), 15)
        for code, record in cities.items():
            self.assertEqual(record.kode_kemendagri, CITY_KODE[code], code)
            self.assertEqual(record.state_id, self.province, code)
            self.assertGreater(record.area_km2, 0, code)
            self.assertTrue(0.2 < record.latitude < 5.7, code)
            self.assertTrue(123.2 < record.longitude < 127.5, code)
        self.assertEqual(len({r.kode_kemendagri for r in cities.values()}), 15)
        # Total area of the 15 kab/kota is ~14.599 km2 (dataset QA figure).
        total = sum(record.area_km2 for record in cities.values())
        self.assertTrue(14500 < total < 14700, total)

    def test_02_district_hierarchy(self):
        districts = self._by_code(self.District, DISTRICT_KODE)
        self.assertEqual(len(districts), 18)
        for code, record in districts.items():
            self.assertEqual(record.kode_kemendagri, DISTRICT_KODE[code], code)
            self.assertTrue(record.city_id, code)
            self.assertEqual(record.state_id, self.province, code)
            self.assertEqual(record.state_id, record.city_id.state_id, code)
            self.assertTrue(
                record.kode_kemendagri.startswith(record.city_id.kode_kemendagri + "."),
                f"{code}: {record.kode_kemendagri} not under {record.city_id.kode_kemendagri}",
            )
            self.assertGreater(record.area_km2, 0, code)
            # Legacy text field must stay in sync with the new relation.
            self.assertEqual(
                record.city.replace("Kab. ", "Kabupaten "), record.city_id.name, code
            )

    def test_03_subdistrict_mapping_and_legacy_flag(self):
        subdistricts = self._by_code(self.Subdistrict, SUB_KODE)
        self.assertEqual(len(subdistricts), 19)
        legacy = []
        for code, record in subdistricts.items():
            expected_kode, expected_legacy = SUB_KODE[code]
            self.assertEqual(record.is_legacy, expected_legacy, code)
            if expected_legacy:
                legacy.append(code)
                self.assertFalse(record.kode_kemendagri, code)
                continue
            self.assertEqual(record.kode_kemendagri, expected_kode, code)
            self.assertTrue(
                record.kode_kemendagri.startswith(record.district_id.kode_kemendagri + "."),
                f"{code}: {record.kode_kemendagri} not under {record.district_id.kode_kemendagri}",
            )
        self.assertEqual(sorted(legacy), ["KEL-BTG-GRW", "KEL-TMH-PSL"])
        mapped = [r for r in subdistricts.values() if not r.is_legacy]
        self.assertEqual(len({r.kode_kemendagri for r in mapped}), 17)

    def test_04_legacy_codes_stay_stable(self):
        """Registry/PJP rows reference KEC-*/KEL-* codes; they must keep resolving."""
        self.assertEqual(self.District.search_count([("code", "in", list(DISTRICT_KODE))]), 18)
        self.assertEqual(self.Subdistrict.search_count([("code", "in", list(SUB_KODE))]), 19)
        village = self.env.ref("id_base.subdistrict_calaca")
        self.assertEqual(village.code, "KEL-MND-CLC")
        self.assertEqual(village.district_id.code, "KEC-MND-WNG")

    def test_05_district_form_omits_polygon(self):
        """The 1.3 MB geojson_polygon must not be loaded by the default form view."""
        view = self.env.ref("id_base.view_id_district_form")
        self.assertNotIn("geojson_polygon", view.arch)
        self.assertIn('name="city_id"', view.arch)

    def _constraint_models(self):
        return [
            (self.City, {"name": "Geo constraint city"}),
            (self.District, {"name": "Geo constraint district", "city_id": self.env.ref("id_base.city_mnd").id}),
            (self.Subdistrict, {"name": "Geo constraint village",
                               "district_id": self.env.ref("id_base.district_mnd_wenang").id}),
        ]

    def test_06_unique_constraints_exist_in_postgres(self):
        for model, _values in self._constraint_models():
            with self.subTest(model=model._name):
                self.cr.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_constraint c
                        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
                        WHERE c.conrelid = %s::regclass AND c.contype = 'u'
                          AND cardinality(c.conkey) = 1 AND a.attname = 'kode_kemendagri'
                    )
                """, [model._table])
                self.assertTrue(self.cr.fetchone()[0], model._name)

    @mute_logger("odoo.sql_db")
    def test_07_duplicate_create_and_write_are_rejected(self):
        for model, values in self._constraint_models():
            with self.subTest(model=model._name):
                first_code = f"TEST-{model._table}-A"
                model.create(dict(values, kode_kemendagri=first_code))
                other = model.create(dict(values, kode_kemendagri=f"TEST-{model._table}-B"))
                with self.assertRaises((IntegrityError, ValidationError)), self.cr.savepoint():
                    model.create(dict(values, kode_kemendagri=first_code))
                    self.env.flush_all()
                with self.assertRaises((IntegrityError, ValidationError)), self.cr.savepoint():
                    other.write({"kode_kemendagri": first_code})
                    self.env.flush_all()
                other.invalidate_recordset(["kode_kemendagri"])
                self.assertEqual(other.kode_kemendagri, f"TEST-{model._table}-B")

    def test_08_multiple_null_codes_remain_allowed(self):
        for model, values in self._constraint_models():
            with self.subTest(model=model._name):
                records = model.create([dict(values, kode_kemendagri=False), dict(values, kode_kemendagri=False)])
                self.assertEqual(len(records), 2)
                self.assertTrue(all(not record.kode_kemendagri for record in records))

    def test_09_seed_bbox_contains_representative_point(self):
        districts = self._by_code(self.District, DISTRICT_KODE)
        for code, record in districts.items():
            self.assertLess(record.bbox_xmin, record.bbox_xmax, code)
            self.assertLess(record.bbox_ymin, record.bbox_ymax, code)
            self.assertLessEqual(record.bbox_xmin, record.longitude, code)
            self.assertLessEqual(record.longitude, record.bbox_xmax, code)
            self.assertLessEqual(record.bbox_ymin, record.latitude, code)
            self.assertLessEqual(record.latitude, record.bbox_ymax, code)
        wenang = districts["KEC-MND-WNG"]
        self.assertAlmostEqual(wenang.bbox_xmin, 124.830102, places=6)
        self.assertAlmostEqual(wenang.bbox_ymax, 1.499840, places=6)
