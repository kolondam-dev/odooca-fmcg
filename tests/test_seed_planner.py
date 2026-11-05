#!/usr/bin/env python3
"""test_seed_planner.py - Unit & Reproducibility Tests for Phase F2 Seed Planner."""

import datetime as dt
from decimal import Decimal
import json
from pathlib import Path
import unittest

from scripts.ops.fmcg_calendar import is_working_day
from scripts.ops.generate_period_pack import compute_sha256_lf
from scripts.ops.seed_planner import (
    PeriodConfig,
    SeedPlanner,
    deterministic_seed,
    extract_existing_numbers,
    prepare_gate_opening,
)
from scripts.ops.seed_v2_gates import validate_pack_report

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestSeedPlannerF2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg_dir = REPO_ROOT / "data" / "registers"
        cls.opening_path = cls.reg_dir / "state_20260801.json"
        with cls.opening_path.open("r", encoding="utf-8") as f:
            cls.raw_opening = json.load(f)

        cls.config = PeriodConfig(
            pack_start="2026-08-01",
            pack_end="2026-08-31",
            opening_cash=Decimal("5000000000.00"),
            tax_rate=Decimal("0.11"),
            target_net_dpp=Decimal("4235000000.00"),
            target_discount_pct=Decimal("2.50"),
            target_rejection_pct=Decimal("2.40"),
        )
        cls.planner = SeedPlanner(cls.config, root_dir=REPO_ROOT)
        cls.res = cls.planner.plan_period(cls.raw_opening)
        cls.pack = cls.res["pack"]
        cls.narrative = cls.res["narrative_report"]
        cls.last_seq = cls.res["last_sequences"]

        cls.gate_opening = prepare_gate_opening(cls.raw_opening)
        cls.existing = extract_existing_numbers(cls.gate_opening)

    def test_deterministic_seed_is_consistent(self):
        s1 = deterministic_seed("42", "call_order", "2026-08-01")
        s2 = deterministic_seed("42", "call_order", "2026-08-01")
        self.assertEqual(s1, s2)
        s3 = deterministic_seed("42", "call_order", "2026-08-03")
        self.assertNotEqual(s1, s3)

    def test_full_pack_passes_seed_v2_gates_in_strict_mode(self):
        bands = {
            "net_dpp": (Decimal("4000000000.00"), Decimal("4500000000.00")),
            "discount_pct": (Decimal("2.00"), Decimal("3.20")),
            "rejection_pct": (Decimal("1.80"), Decimal("3.00")),
            "active_outlets": (Decimal("200"), Decimal("215")),
        }
        gate_config = {
            "pack_start": "2026-08-01",
            "pack_end": "2026-08-31",
            "opening_cash": "5000000000.00",
            "min_lead_days": self.config.min_lead_days,
            "tax": {
                "rate": "0.11",
                "source": "PMK 131/2024 & UU HPP No. 7/2021",
                "source_date": "2024-12-31",
                "effective_from": "2025-01-01",
            },
        }
        report = validate_pack_report(
            pack=self.pack,
            opening=self.gate_opening,
            previous_closing=self.gate_opening,
            existing_numbers=self.existing,
            config=gate_config,
            bands=bands,
            strict=True,
        )
        self.assertEqual(report.get("violations"), [])
        self.assertEqual(report.get("gates_skipped"), [])
        self.assertGreaterEqual(len(report.get("gates_run", [])), 10)

    def test_calendar_working_days_strict_dispatch(self):
        # 17 Aug (Proklamasi) & 25 Aug (Maulid Nabi) must not contain SOs or deliveries
        for so in self.pack["sales_orders"]:
            d_str = so["date_order"]
            d = dt.date.fromisoformat(d_str)
            self.assertTrue(is_working_day(d), f"SO on non-working day: {d_str}")
            self.assertNotIn(d_str, ("2026-08-17", "2026-08-25"))

        for deliv in self.pack["deliveries"]:
            d_str = deliv["scheduled_delivery_date"]
            d = dt.date.fromisoformat(d_str)
            self.assertTrue(is_working_day(d), f"Delivery on non-working day: {d_str}")
            self.assertNotIn(d_str, ("2026-08-17", "2026-08-25"))

    def test_numbering_sequences_start_from_1_for_monthly_documents(self):
        first_so = self.pack["sales_orders"][0]["so_number"]
        self.assertEqual(first_so, "SO-202608-0001")

        first_do = self.pack["deliveries"][0]["do_number"]
        self.assertEqual(first_do, "DO-202608-0001")

        first_inv = self.pack["invoices"][0]["invoice_number"]
        self.assertEqual(first_inv, "INV-202608-0001")

        first_rej = self.pack["rejections"][0]["rejection_id"]
        self.assertEqual(first_rej, "REJ-202608-001")

        first_po = self.pack["po_headers"][0]["po_number"]
        self.assertEqual(first_po, "PO-2026-08-01")

    def test_global_numbering_continues_from_july_baseline(self):
        first_ar = self.pack["ar_collections"][0]["payment_id"]
        self.assertEqual(first_ar, "PAY-AR-00968")

        first_ap = self.pack["ap_payments"][0]["ap_payment_id"]
        self.assertEqual(first_ap, "PAY-AP-05")

        first_evt = self.pack["stock_events"][0]["event_id"]
        self.assertEqual(first_evt, "EVT-005742")

    def test_narrative_metrics_within_authorized_bands(self):
        m = self.narrative["metrics"]
        net_dpp = Decimal(m["net_dpp"])
        self.assertTrue(
            Decimal("4000000000.00") <= net_dpp <= Decimal("4500000000.00"),
            f"net_dpp {net_dpp} out of band",
        )

        disc_pct = Decimal(m["discount_pct"])
        self.assertTrue(Decimal("2.00") <= disc_pct <= Decimal("3.20"), f"discount_pct {disc_pct} out of band")

        rej_pct = Decimal(m["rejection_pct"])
        self.assertTrue(Decimal("1.80") <= rej_pct <= Decimal("3.00"), f"rejection_pct {rej_pct} out of band")

        active_outlets = m["active_outlets"]
        self.assertTrue(200 <= active_outlets <= 215, f"active_outlets {active_outlets} out of band")

    def test_ap_unilever_june_paid_on_due_date_august_8(self):
        ap_payments = self.pack["ap_payments"]
        self.assertEqual(len(ap_payments), 1)
        p = ap_payments[0]
        self.assertEqual(p["po_number"], "PO-2026-06-05")
        self.assertEqual(p["payment_date"], "2026-08-08")
        self.assertEqual(p["amount_paid_dpp"], "2899971200.00")

    def test_pack_manifest_sha256_integrity(self):
        pack_dir = self.reg_dir / "periods" / "2026-08"
        manifest_file = pack_dir / "MANIFEST.json"
        self.assertTrue(manifest_file.exists(), "MANIFEST.json must exist in pack directory")

        with manifest_file.open("r", encoding="utf-8") as f:
            manifest = json.load(f)

        files_sha = manifest["files_sha256"]
        self.assertGreaterEqual(len(files_sha), 20)

        for filename, recorded_hash in files_sha.items():
            fpath = pack_dir / filename
            self.assertTrue(fpath.exists(), f"File {filename} in manifest missing on disk")
            computed_hash = compute_sha256_lf(fpath)
            self.assertEqual(computed_hash, recorded_hash, f"Hash mismatch for {filename}")


if __name__ == "__main__":
    unittest.main()
