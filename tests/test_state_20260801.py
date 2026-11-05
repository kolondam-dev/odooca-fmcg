#!/usr/bin/env python3
"""test_state_20260801.py - Verification of canonical state_20260801.json for Phase F0."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.ops.generate_state_20260801 import generate_state

ROOT = Path(__file__).resolve().parent.parent


class TestState20260801(unittest.TestCase):
    def setUp(self):
        self.state_file = ROOT / "data" / "registers" / "state_20260801.json"
        self.assertTrue(self.state_file.exists(), "state_20260801.json must exist")
        with self.state_file.open(encoding="utf-8") as f:
            self.data = json.load(f)

    def test_timezone_is_wita_utc_plus_8(self):
        self.assertEqual(self.data["as_of_datetime"], "2026-08-01T00:00:00+08:00")
        self.assertEqual(self.data["timezone"], "Asia/Makassar (+08:00 WITA)")

    def test_summary_invariants_match_canonical_reconciliation(self):
        summary = self.data["summary"]
        self.assertEqual(summary["total_physical_cartons"], 53837)
        self.assertEqual(summary["total_reserved_cartons"], 1038)
        self.assertEqual(summary["total_available_cartons"], 52799)
        self.assertEqual(summary["total_quarantine_cartons"], 9)

        # Differentiate posted July vs carry-forward pending August
        self.assertEqual(summary["open_posted_july_invoices_count"], 309)
        self.assertEqual(summary["open_posted_july_invoices_dpp"], "2135470252.80")
        self.assertEqual(summary["carry_forward_pending_august_invoices_count"], 48)
        self.assertEqual(summary["carry_forward_pending_august_invoices_dpp"], "187858691.40")

        self.assertEqual(summary["total_open_ar_count"], 357)
        self.assertEqual(summary["total_open_ar_dpp"], "2323328944.20")

        self.assertEqual(summary["open_po_count"], 1)
        self.assertEqual(summary["open_po_dpp"], "2899971200.00")
        self.assertEqual(summary["pending_carry_forward_dos_count"], 48)

    def test_open_po_is_unilever_june_due_august_8(self):
        open_po = self.data["open_po"]
        self.assertIn("PO-2026-06-05", open_po)
        entry = open_po["PO-2026-06-05"]
        self.assertEqual(entry["principal_code"], "PRIN-UNILEVER")
        self.assertEqual(entry["payment_due_date"], "2026-08-08")
        self.assertEqual(entry["total_amount_dpp"], "2899971200.00")

    def test_last_sequences(self):
        seq = self.data["last_sequences"]
        self.assertEqual(seq["last_so_number"], "SO-202607-1324")
        self.assertEqual(seq["last_do_number"], "DO-202607-1324")
        self.assertEqual(seq["last_invoice_number"], "INV-202607-1324")
        self.assertEqual(seq["last_ar_payment_id"], "PAY-AR-00967")
        self.assertEqual(seq["last_ap_payment_id"], "PAY-AP-04")
        self.assertEqual(seq["last_rejection_id"], "REJ-202607-009")
        self.assertEqual(seq["last_event_id"], "EVT-005741")

    def test_generator_reproducibility_zero_drift(self):
        fresh = generate_state(ROOT / "data" / "registers", verify_fingerprint=True)
        self.assertEqual(fresh["as_of_datetime"], self.data["as_of_datetime"])
        self.assertEqual(fresh["timezone"], self.data["timezone"])
        self.assertEqual(fresh["summary"], self.data["summary"])
        self.assertEqual(fresh["last_sequences"], self.data["last_sequences"])
        self.assertEqual(len(fresh["stock"]), len(self.data["stock"]))
        self.assertEqual(len(fresh["open_posted_invoices_july"]), len(self.data["open_posted_invoices_july"]))
        self.assertEqual(
            len(fresh["carry_forward_pending_invoices_august"]),
            len(self.data["carry_forward_pending_invoices_august"]),
        )
        self.assertEqual(len(fresh["pending_dos"]), len(self.data["pending_dos"]))
        self.assertEqual(len(fresh["open_po"]), len(self.data["open_po"]))

    def test_mutation_fractional_carton_fails_fast(self):
        """Regression test for supervisor probe: fractional Decimal('0.5') carton mutation must fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # Copy all files from registers to tempdir
            reg_dir = ROOT / "data" / "registers"
            for item in reg_dir.glob("*.csv"):
                shutil.copy(item, tmp_path / item.name)
            for item in reg_dir.glob("*.json"):
                shutil.copy(item, tmp_path / item.name)

            # Mutate physical_impact in stock event ledger with 0.5
            ledger_file = tmp_path / "perpetual_stock_event_ledger.csv"
            content = ledger_file.read_text(encoding="utf-8")
            old_str = "MYR-RMA-01,LOT-ORA-20260615-INIT-01,202,7500.0,45450000.0,202,"
            new_str = "MYR-RMA-01,LOT-ORA-20260615-INIT-01,202.5,7500.0,45450000.0,202.5,"
            mutated_content = content.replace(old_str, new_str)
            ledger_file.write_text(mutated_content, encoding="utf-8")

            # Must raise ValueError, never silently truncate or pass
            with self.assertRaises(ValueError) as ctx:
                generate_state(tmp_path, verify_fingerprint=False)
            self.assertIn("Non-integral carton quantity", str(ctx.exception))

    def test_canonical_fingerprint_mismatch_fails_fast(self):
        """Mutated file triggers fingerprint verification error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            reg_dir = ROOT / "data" / "registers"
            for item in reg_dir.glob("*.csv"):
                shutil.copy(item, tmp_path / item.name)
            for item in reg_dir.glob("*.json"):
                shutil.copy(item, tmp_path / item.name)

            # Modify a single byte in perpetual_sales_orders.csv
            so_file = tmp_path / "perpetual_sales_orders.csv"
            so_file.write_text(so_file.read_text(encoding="utf-8") + "\n#mutation", encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                generate_state(tmp_path, verify_fingerprint=True)
            self.assertIn("Canonical register fingerprint mismatch", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
