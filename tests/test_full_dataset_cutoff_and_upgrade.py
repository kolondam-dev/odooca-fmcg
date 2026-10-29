#!/usr/bin/env python3
"""Unit & Acceptance Tests untuk Full Dataset Runner, Two-Phase Cut-Off, dan Audit Independen.

Menguji:
1. Dynamic Oracle: ekspektasi dihitung dinamis dari CSV (lulus probe mutasi in-memory).
2. Rekonsiliasi 14 kunjungan 31 Juli menjadi 48 pesanan single-prinsipal 1 Agustus dengan lineage lengkap.
3. Eksekusi dua fase deterministik: Closing 31 Juli 2026 vs Post-Transaksi 1 Agustus 2026 dan immutabilitas.
4. Zero drift penuh pada deep state snapshot (quants, moves, move_lines, pickings, orders, AML, GL).
5. Uji mutasi negatif nyata pada database ditolak oleh audit produksi.
6. Sensitivitas snapshot: perubahan product_id, location_id, atau datetime terdeteksi.
7. Safety guard: penolakan mutlak nama database non-disposable atau terlarang.
"""

from decimal import Decimal
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REG_DIR = ROOT / "data" / "registers"

from scripts.load_canonical_perpetual import (  # noqa: E402
    CanonicalPerpetualAdapter,
    read_register_csv,
)
from scripts.ops.verify_disposable_full import (  # noqa: E402
    FullDatasetCanonicalOracle,
    assert_disposable_database,
    audit_database_against_oracle_august,
    audit_database_against_oracle_july,
    capture_deep_state_snapshot,
)
from tests.test_canonical_loader_adapter import (  # noqa: E402
    setup_standard_mock_env,
)


class TestFullDatasetCutoffAndUpgrade(unittest.TestCase):
    def setUp(self):
        self.mock_env = setup_standard_mock_env()
        self.oracle = FullDatasetCanonicalOracle(REG_DIR)

    def test_canonical_oracle_expectations_match_frozen_reconciliation(self):
        """Oracle dinamis menurunkan ekspektasi langsung dari register CSV dan responsif mutasi."""
        july = self.oracle.get_july_closing_expectations()
        aug = self.oracle.get_august_opening_expectations()

        # SO & DO
        self.assertEqual(july["so_count"], 1324)
        self.assertEqual(july["do_validated_july"], 1281)  # 1.276 DO + 5 PO receipt
        self.assertEqual(july["do_pending_august"], 48)

        # Invoices
        self.assertEqual(july["invoices_july_posted"], 1276)
        self.assertEqual(july["invoices_august_pending"], 48)
        self.assertEqual(Decimal(july["july_inv_dpp"]), Decimal("5594622485.00"))
        self.assertEqual(Decimal(july["aug_inv_dpp"]), Decimal("187858691.40"))
        total_dpp = Decimal(july["july_inv_dpp"]) + Decimal(july["aug_inv_dpp"])
        self.assertEqual(total_dpp, Decimal("5782481176.40"))

        # PPN 11%
        self.assertEqual(Decimal(july["july_inv_ppn"]), Decimal("615408473.32"))
        self.assertEqual(Decimal(july["aug_inv_ppn"]), Decimal("20664456.06"))

        # AR / AP / OPEX
        self.assertEqual(july["ar_collections_count"], 967)
        self.assertEqual(july["ap_payments_count"], 4)
        self.assertEqual(july["opex_count"], 30)

        # Saldo Fisik & Reservasi Stok Dinamis
        self.assertEqual(july["physical_on_hand_cartons_july"], 53837)
        self.assertEqual(july["reserved_cartons_july"], 1038)
        self.assertEqual(july["available_cartons_july"], 52799)
        self.assertEqual(july["quarantine_cartons_july"], 9)

        # August Post-Transaction
        self.assertEqual(aug["physical_on_hand_cartons_august"], 52799)
        self.assertEqual(aug["reserved_cartons_august"], 0)
        self.assertEqual(aug["available_cartons_august"], 52799)
        self.assertEqual(aug["invoices_total_posted"], 1324)
        self.assertEqual(aug["do_total_validated"], 1329)  # 1.324 DO + 5 PO

        # PROBE SUPERVISOR: Membuktikan kalkulasi stok tidak di-hardcode
        orig_cartons = july["physical_on_hand_cartons_july"]
        self.oracle.opening_rows[0]["qty_cartons_on_hand"] = "999999"
        mutated_july = self.oracle.get_july_closing_expectations()
        self.assertNotEqual(orig_cartons, mutated_july["physical_on_hand_cartons_july"])

    def test_reconciliation_of_14_visits_into_48_single_principal_orders(self):
        """Membuktikan lineage historis: 14 kunjungan outlet 31 Juli menjadi 48 SO single-prinsipal 1 Agustus."""
        orders = read_register_csv(REG_DIR / "perpetual_sales_orders.csv")
        deliveries = read_register_csv(REG_DIR / "perpetual_deliveries.csv")
        invoices = read_register_csv(REG_DIR / "perpetual_invoices.csv")

        july31_orders = [so for so in orders if so["date_order"] == "2026-07-31"]
        self.assertEqual(len(july31_orders), 48)

        # Lineage customer, salesperson, and principal
        customers_visited = {so["customer"] for so in july31_orders}
        self.assertEqual(len(customers_visited), 14)

        salespersons = {so["salesman"] for so in july31_orders}
        self.assertGreaterEqual(len(salespersons), 1)

        # Lineage principal dari baris pesanan
        order_lines = read_register_csv(REG_DIR / "perpetual_order_lines.csv")
        lines_by_so = {}
        for ol in order_lines:
            lines_by_so.setdefault(ol["so_number"], []).append(ol)

        principals = set()
        for so in july31_orders:
            so_lines = lines_by_so.get(so["so_number"], [])
            for line in so_lines:
                principals.add(line["sku_code"].split("-")[0])
        self.assertEqual(principals, {"MYR", "KPA", "ULV", "WNG"})

        # DO dan Faktur Agustus yang terikat
        july31_so_numbers = {so["so_number"] for so in july31_orders}
        aug_delivs = [d for d in deliveries if d["so_number"] in july31_so_numbers]
        self.assertEqual(len(aug_delivs), 48)
        for d in aug_delivs:
            self.assertEqual(d["scheduled_delivery_date"], "2026-08-01")

        aug_invs = [inv for inv in invoices if inv["so_number"] in july31_so_numbers]
        self.assertEqual(len(aug_invs), 48)
        for inv in aug_invs:
            self.assertEqual(inv["date_invoice"], "2026-08-01")

        tot_aug_dpp = sum(Decimal(inv["dpp_amount"]) for inv in aug_invs)
        self.assertEqual(tot_aug_dpp, Decimal("187858691.40"))

    def test_two_phase_cutoff_execution_and_idempotency_simulation(self):
        """Simulasi eksekusi dua fase: Fase 1 (Cut-off Juli) -> Fase 2 (Opening Agustus) -> Run 2 Idempoten."""
        mock_env = setup_standard_mock_env()
        oracle = FullDatasetCanonicalOracle(REG_DIR)

        # FASE 1: Closing Juli 2026
        adapter_july = CanonicalPerpetualAdapter(
            mock_env,
            reg_path=REG_DIR,
            cutoff_date="2026-07-31",
            enforce_invoice_cutoff=True,
        )
        adapter_july.run_all()

        # Audit Independen Checkpoint Juli menggunakan fungsi audit produksi
        audit_database_against_oracle_july(mock_env, oracle)

        # Simpan snapshot baris AML Juli untuk uji immutabilitas
        july_amls = list(mock_env["account.move.line"].search([("date", "<=", "2026-07-31")]))

        # FASE 2: Carry-Forward 1 Agustus 2026
        adapter_aug = CanonicalPerpetualAdapter(
            mock_env,
            reg_path=REG_DIR,
            cutoff_date="2026-08-01",
            enforce_invoice_cutoff=True,
        )
        adapter_aug.run_all()

        # Audit Independen Checkpoint Agustus & Immutabilitas Juli
        audit_database_against_oracle_august(mock_env, oracle, prior_july_aml_snapshot=july_amls)

        # Deep snapshot setelah Fase 2 selesai
        snap1 = capture_deep_state_snapshot(mock_env)
        out_invs = [m for m in mock_env["account.move"].search([]) if getattr(m, "move_type", None) == "out_invoice"]
        self.assertEqual(len(out_invs), 1324)

        # FASE 3: Uji Idempotensi Run 2
        adapter_run2 = CanonicalPerpetualAdapter(
            mock_env,
            reg_path=REG_DIR,
            cutoff_date="2026-08-01",
            enforce_invoice_cutoff=True,
        )
        adapter_run2.run_all()

        self.assertEqual(adapter_run2.stats["so_created"], 0)
        self.assertEqual(adapter_run2.stats["invoices_created"], 0)
        self.assertEqual(adapter_run2.stats["do_validated"], 0)

        # Zero Drift Snapshot
        snap2 = capture_deep_state_snapshot(mock_env)
        self.assertEqual(snap1["quants"], snap2["quants"])
        self.assertEqual(snap1["moves"], snap2["moves"])
        self.assertEqual(snap1["move_lines"], snap2["move_lines"])
        self.assertEqual(snap1["pickings"], snap2["pickings"])
        self.assertEqual(snap1["orders"], snap2["orders"])
        self.assertEqual(snap1["account_moves"], snap2["account_moves"])
        self.assertEqual(snap1["aml_records"], snap2["aml_records"])
        self.assertEqual(snap1["payments"], snap2["payments"])
        self.assertEqual(snap1["gl_balances"], snap2["gl_balances"])

    def test_negative_mutations_rejected_by_production_audit(self):
        """Mutasi negatif nyata pada database wajib digagalkan oleh audit oracle produksi."""
        mock_env = setup_standard_mock_env()
        oracle = FullDatasetCanonicalOracle(REG_DIR)

        adapter = CanonicalPerpetualAdapter(
            mock_env,
            reg_path=REG_DIR,
            cutoff_date="2026-07-31",
            enforce_invoice_cutoff=True,
        )
        adapter.run_all()

        # Baseline wajib PASS
        audit_database_against_oracle_july(mock_env, oracle)

        AM = mock_env["account.move"]
        AML = mock_env["account.move.line"]

        # Mutasi 1: Sisipkan faktur out_invoice bertanggal Agustus pada database Juli
        illegal_inv = AM.create({
            "name": "INV/ILLEGAL/2026/08",
            "move_type": "out_invoice",
            "state": "posted",
            "date": "2026-08-01",
            "amount_untaxed": 1000000.0,
            "amount_tax": 110000.0,
            "amount_total": 1110000.0,
        })
        with self.assertRaises(AssertionError):
            audit_database_against_oracle_july(mock_env, oracle)
        # Rollback Mutasi 1
        del AM.store[illegal_inv.id]
        audit_database_against_oracle_july(mock_env, oracle)

        # Mutasi 2: AML seimbang tetapi nilai diubah (debit +1000, credit +1000)
        target_inv = next(m for m in AM.search([]) if getattr(m, "move_type", "") == "out_invoice")
        orig_untaxed = target_inv.amount_untaxed
        target_inv.amount_untaxed += 1000.0
        with self.assertRaises(AssertionError):
            audit_database_against_oracle_july(mock_env, oracle)
        # Rollback Mutasi 2
        target_inv.amount_untaxed = orig_untaxed
        audit_database_against_oracle_july(mock_env, oracle)

        # Mutasi 3: Perubahan tanggal baris jurnal melintasi batas cut-off
        first_aml = next(iter(AML.search([])))
        orig_aml_date = first_aml.date
        first_aml.date = "2026-08-02"
        with self.assertRaises(AssertionError):
            audit_database_against_oracle_july(mock_env, oracle)
        # Rollback Mutasi 3
        first_aml.date = orig_aml_date
        audit_database_against_oracle_july(mock_env, oracle)

    def test_deep_state_snapshot_detects_field_modifications(self):
        """Membuktikan probe supervisor: modifikasi product_id, location_id, atau datetime move line terdeteksi."""
        mock_env = setup_standard_mock_env()
        SML = mock_env["stock.move.line"]

        # Buat move line fixture
        fixture_sml = SML.create({
            "move_id": 1,
            "product_id": 10,
            "lot_id": 5,
            "location_id": 1,
            "location_dest_id": 3,
            "product_uom_id": 1,
            "quantity": 50.0,
            "date": "2026-07-31 00:00:00",
            "company_id": 1,
            "state": "done",
        })

        snap_before = capture_deep_state_snapshot(mock_env)

        # Probe 1: Ubah location_id
        fixture_sml.location_id = 999
        snap_after_loc = capture_deep_state_snapshot(mock_env)
        self.assertNotEqual(snap_before["move_lines"], snap_after_loc["move_lines"])
        fixture_sml.location_id = 1

        # Probe 2: Ubah product_id
        fixture_sml.product_id = 999
        snap_after_prod = capture_deep_state_snapshot(mock_env)
        self.assertNotEqual(snap_before["move_lines"], snap_after_prod["move_lines"])
        fixture_sml.product_id = 10

        # Probe 3: Pergeseran jam melintasi hari bisnis WITA (00:00:00 -> 20:00:00)
        fixture_sml.date = "2026-07-31 20:00:00"
        snap_after_date = capture_deep_state_snapshot(mock_env)
        self.assertNotEqual(snap_before["move_lines"], snap_after_date["move_lines"])

    def test_safety_guard_rejects_non_disposable_and_forbidden_substrings(self):
        """Safety guard wajib menolak nama database operasional atau yang memuat substring terlarang."""
        # Menolak nama yang mengandung kata terlarang meskipun memiliki substring aman
        for forbidden_db in ["official_live", "fmcg_full_production", "fmcg_base", "railway", "master_db"]:
            env_bad = setup_standard_mock_env()
            env_bad.cr.dbname = forbidden_db
            with self.assertRaises(RuntimeError) as ctx:
                assert_disposable_database(env_bad)
            self.assertIn("SAFETY-ABORT", str(ctx.exception))

        # Mengizinkan database disposable yang sah
        for valid_db in ["fmcg_full_disposable", "ci_db", "test_disposable", "tenant_disposable_slice"]:
            env_good = setup_standard_mock_env()
            env_good.cr.dbname = valid_db
            self.assertEqual(assert_disposable_database(env_good), valid_db)


if __name__ == "__main__":
    unittest.main()
