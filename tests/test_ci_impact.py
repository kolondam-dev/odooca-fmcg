from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ci_plan", ROOT / "scripts" / "ci" / "plan.py")
assert SPEC and SPEC.loader
PLAN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PLAN
SPEC.loader.exec_module(PLAN)


class TestCiImpactPlanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = PLAN.load_config()

    def suites(self, *files: str) -> set[str]:
        return set(PLAN.select(list(files), self.config).suites)

    def test_pwa_change_is_targeted(self):
        self.assertEqual(self.suites("pwa/src/App.tsx"), {"pwa"})

    def test_docs_only_has_no_runtime_suite(self):
        self.assertEqual(self.suites("docs/DEVELOPMENT.md", "agent-log/claude-dev.log"), set())

    def test_po_change_requires_real_odoo_install_and_upgrade(self):
        suites = self.suites("addons/id_dashboard_redesign/i18n/id.po")
        self.assertTrue({"odoo_install", "upgrade", "dashboard", "odoo_ui"} <= suites)

    def test_mobile_change_selects_mobile_runtime(self):
        suites = self.suites("addons/id_mobile_api/models/mobile.py")
        self.assertTrue({"odoo_install", "mobile", "upgrade"} <= suites)

    def test_shared_odoo_foundation_escalates_cross_domain_runtime(self):
        suites = self.suites("addons/id_base/models/res_partner.py")
        self.assertTrue(
            {"odoo_install", "odoo_init", "dashboard", "mobile", "finance", "full_dataset", "upgrade"}
            <= suites
        )

    def test_finance_change_selects_init_and_finance(self):
        suites = self.suites("addons/id_finance_reporting/models/report.py")
        self.assertTrue({"odoo_install", "odoo_init", "finance", "upgrade"} <= suites)

    def test_seed_contract_selects_heavy_data_proofs(self):
        suites = self.suites("data/registers/sales.csv")
        self.assertTrue({"seed", "full_dataset", "upgrade"} <= suites)

    def test_ci_control_change_forces_every_suite(self):
        result = PLAN.select([".github/workflows/ci.yml"], self.config)
        self.assertTrue(result.full)
        self.assertEqual(result.unknown, ())
        self.assertEqual(set(result.suites), set(self.config["all_suites"]))

    def test_unmapped_path_fails_closed(self):
        result = PLAN.select(["new-platform/runtime.xyz"], self.config)
        self.assertTrue(result.full)
        self.assertEqual(result.unknown, ("new-platform/runtime.xyz",))
        self.assertEqual(set(result.suites), set(self.config["all_suites"]))

    def test_force_suite_can_only_add(self):
        result = PLAN.select(
            ["pwa/src/App.tsx"],
            self.config,
            force_suites=("seed",),
        )
        self.assertEqual(set(result.suites), {"pwa", "seed"})

    def test_unknown_forced_suite_is_rejected(self):
        with self.assertRaises(ValueError):
            PLAN.select([], self.config, force_suites=("fast-pass",))


if __name__ == "__main__":
    unittest.main()
