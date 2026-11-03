"""Kontrak audit coverage outlet vs poligon kecamatan (PR-4).

Yang dijaga:

1. Audit dapat direproduksi: 354 outlet, semuanya punya pemetaan kode, 44 di luar
   poligon kecamatan yang ditugaskan (sebaran 4/11/29), tidak ada yang jatuh ke
   poligon kecamatan lain.
2. Audit **tidak menulis** apa pun ke berkas masukan (D4=A: laporan saja).
3. Laporan markdown yang di-commit identik dengan hasil generator, sehingga tidak
   pernah basi.
4. Temuan kode pos dilaporkan sebagai informasi (40 partner, 9 kelurahan legacy),
   tanpa mengubah nilai.

Butuh `shapely`; tanpa pustaka itu uji geometri di-skip (bukan gagal).
"""

import hashlib
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ops" / "audit_geo_coverage.py"
REPORT = ROOT / "docs" / "reviews" / "GEO_COVERAGE_AUDIT_2026-11-03.md"
INPUTS = [
    "data/seed/partners_354.csv",
    "data/geo/sulut_districts.geojson",
    "data/master/sulut_desa_kelurahan.csv",
    "addons/id_base/data/id_district_data.xml",
]


def load_module():
    spec = importlib.util.spec_from_file_location("audit_geo_coverage_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class GeoCoverageAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import shapely  # noqa: F401
        except ImportError:  # pragma: no cover - lingkungan tanpa shapely
            raise unittest.SkipTest("shapely tidak tersedia")
        cls.audit = load_module()
        cls.report = cls.audit.audit(ROOT)

    def test_01_every_partner_has_a_mapped_district(self):
        self.assertEqual(self.report["partners_total"], 354)
        self.assertEqual(self.report["partners_mapped"], 354)
        self.assertEqual(self.report["partners_unmapped"], [])

    def test_02_mapping_has_no_conflict(self):
        self.assertEqual(self.report["mapping_conflicts"], [])
        self.assertEqual(self.report["mapping_source"], "id_district_data.xml")

    def test_03_outside_matches_baseline(self):
        outside = self.report["outside"]
        self.assertEqual(len(outside), 44)
        self.assertEqual(
            self.report["outside_by_district"],
            {"71.02.12": 4, "71.71.04": 11, "71.71.07": 29},
        )
        self.assertEqual(self.report["outside_without_any_polygon"], 44)
        self.assertEqual(self.report["outside_inside_other_district"], 0)
        refs = {row["ref"] for row in outside}
        self.assertEqual(len(refs), 44)
        self.assertIn("CUST-GT-69", refs)
        for row in outside:
            self.assertTrue(row["district_name"], row["ref"])
            self.assertTrue(0.2 < row["latitude"] < 5.7, row["ref"])
            self.assertTrue(123.2 < row["longitude"] < 127.5, row["ref"])

    def test_04_postal_findings_are_reported_only(self):
        self.assertEqual(len(self.report["postal_mismatch"]), 40)
        self.assertEqual(len(self.report["legacy_postal_mismatch"]), 9)
        for row in self.report["postal_mismatch"]:
            self.assertTrue(row["partner_zip"], row["ref"])
            self.assertTrue(row["canonical_zip"], row["ref"])

    def test_05_audit_does_not_modify_inputs(self):
        before = {path: sha256(ROOT / path) for path in INPUTS}
        self.audit.audit(ROOT)
        after = {path: sha256(ROOT / path) for path in INPUTS}
        self.assertEqual(before, after)

    def test_06_committed_report_matches_generator(self):
        expected = self.audit.render_markdown(self.audit.audit(ROOT))
        self.assertEqual(REPORT.read_text(encoding="utf-8").replace("\r\n", "\n"), expected)
        self.assertIn("| Outlet di luar poligon kecamatan yang ditugaskan | **44** |", expected)
        self.assertIn("`CUST-GT-69`", expected)

    def test_07_geometry_free_run_keeps_mapping_checks(self):
        report = self.audit.audit(ROOT, with_geometry=False)
        self.assertEqual(report["partners_mapped"], 354)
        self.assertEqual(report["outside"], [])
        self.assertEqual(len(report["postal_mismatch"]), 40)


if __name__ == "__main__":
    unittest.main()
