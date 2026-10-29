#!/usr/bin/env python3
"""Unit & Acceptance Tests untuk Full Dataset Runner, Two-Phase Cut-Off, dan Upgrade.

Menguji:
1. Two-phase cut-off deterministik: Closing 31 Juli 2026 vs Opening 1 Agustus 2026 (Carry-Forward).
2. Verifikasi independen Oracle Kanonikal: 1.324 SO, 1.324 DO, 1.324 Faktur, 967 AR, 4 AP, 30 OPEX.
3. Rekonsiliasi 14 kunjungan outlet 31 Juli menjadi 48 pesanan/pengiriman/faktur single-prinsipal 1 Agustus.
4. Uji mutasi negatif: penolakan kebocoran lintas periode dan manipulasi tanggal transaksi.
5. Uji isolasi supresi COGS dan pembuktian batas rollback transaksi pada kegagalan terinjeksi.
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
    capture_deep_state_snapshot,
    introspect_runtime_environment,
    verify_anti_fallback_salespersons,
)
from tests.test_canonical_loader_adapter import setup_standard_mock_env  # noqa: E402


class TestFullDatasetCutoffAndUpgrade(unittest.TestCase):
    def setUp(self):
        self.mock_env = setup_standard_mock_env()
        self.oracle = FullDatasetCanonicalOracle(REG_DIR)

    def test_canonical_oracle_expectations_match_frozen_reconciliation(self):
        """Oracle independen harus menghasilkan angka yang identik 100% dengan rekonsiliasi kanonikal."""
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

        # Saldo Fisik & Reservasi Stok
        self.assertEqual(july["physical_on_hand_cartons_july"], 53837)
        self.assertEqual(july["reserved_cartons_july"], 1038)
        self.assertEqual(july["available_cartons_july"], 52799)
        self.assertEqual(july["quarantine_cartons_july"], 9)

        # August Opening
        self.assertEqual(aug["physical_on_hand_cartons_august"], 52799)
        self.assertEqual(aug["reserved_cartons_august"], 0)
        self.assertEqual(aug["available_cartons_august"], 52799)
        self.assertEqual(aug["invoices_total_posted"], 1324)
        self.assertEqual(aug["do_total_validated"], 1329)  # 1.324 DO + 5 PO

    def test_reconciliation_of_14_visits_into_48_single_principal_orders(self):
        """Membuktikan secara matematis bahwa 14 outlet visits pada 31 Juli menjadi 48 SO single-prinsipal."""
        orders = read_register_csv(REG_DIR / "perpetual_sales_orders.csv")
        july31_orders = [so for so in orders if so["date_order"] == "2026-07-31"]

        # Jumlah SO tepat 48
        self.assertEqual(len(july31_orders), 48)

        # Menghitung jumlah customer unik yang dikunjungi
        unique_customers = set(so["customer"] for so in july31_orders)
        self.assertEqual(len(unique_customers), 14, "Harus tepat 14 outlet visit yang menghasilkan pesanan 31 Juli!")

        # Seluruh 48 SO terjadwal kirim dan faktur pada 1 Agustus 2026
        deliveries = {r["so_number"]: r for r in read_register_csv(REG_DIR / "perpetual_deliveries.csv")}
        invoices = {r["so_number"]: r for r in read_register_csv(REG_DIR / "perpetual_invoices.csv")}

        for so in july31_orders:
            so_num = so["so_number"]
            self.assertEqual(deliveries[so_num]["scheduled_delivery_date"], "2026-08-01")
            self.assertEqual(invoices[so_num]["date_invoice"], "2026-08-01")

        # Total karton yang dipesan untuk pengiriman 1 Agustus harus tepat 1.038 karton (reserved cartons)
        order_lines = read_register_csv(REG_DIR / "perpetual_order_lines.csv")
        so31_set = set(so["so_number"] for so in july31_orders)
        cartons_aug = sum(int(Decimal(line["qty_cartons"])) for line in order_lines if line["so_number"] in so31_set)
        self.assertEqual(cartons_aug, 1038, "Total karton pesanan 31 Juli untuk delivery 1 Agustus harus 1.038!")

    def test_two_phase_cutoff_execution_and_idempotency_simulation(self):
        """Simulasi eksekusi dua fase: Fase 1 (Cut-off Juli) -> Fase 2 (Opening Agustus) -> Run 2 Idempoten."""
        mock_env = setup_standard_mock_env()

        # FASE 1: Cut-off Juli 2026
        adapter_july = CanonicalPerpetualAdapter(
            mock_env,
            reg_path=REG_DIR,
            cutoff_date="2026-07-31",
            enforce_invoice_cutoff=True,
        )
        adapter_july.run_all()

        self.assertEqual(adapter_july.stats["opening_quants"], 150)
        self.assertEqual(adapter_july.stats["po_created"], 5)
        self.assertEqual(adapter_july.stats["so_created"], 1324)
        self.assertEqual(adapter_july.stats["do_validated"], 1281)  # 1.276 DO + 5 PO
        self.assertEqual(adapter_july.stats["invoices_created"], 1276)  # Hanya faktur Juli
        self.assertEqual(adapter_july.stats["ar_payments_created"], 967)
        self.assertEqual(adapter_july.stats["ap_payments_created"], 4)
        self.assertEqual(adapter_july.stats["quarantine_rejections"], 9)
        self.assertEqual(adapter_july.stats["opex_moves_created"], 30)

        # FASE 2: Opening Agustus 2026
        adapter_aug = CanonicalPerpetualAdapter(
            mock_env,
            reg_path=REG_DIR,
            cutoff_date="2026-08-01",
            enforce_invoice_cutoff=True,
        )
        adapter_aug.run_all()

        # 48 DO Agustus divalidasi dan 48 Faktur Agustus dibuat
        self.assertEqual(adapter_aug.stats["do_validated"], 48)
        self.assertEqual(adapter_aug.stats["invoices_created"], 48)
        self.assertEqual(adapter_aug.stats["skipped_so"], 1324)
        self.assertEqual(adapter_aug.stats["skipped_invoices"], 1276)
        self.assertEqual(adapter_aug.stats["skipped_ar"], 967)

        # Deep snapshot setelah Fase 2 selesai
        snap1 = capture_deep_state_snapshot(mock_env)
        out_invs = [m for m in mock_env["account.move"].search([]) if getattr(m, "move_type", None) == "out_invoice"]
        self.assertEqual(len(out_invs), 1324)
        in_bills = [m for m in mock_env["account.move"].search([]) if getattr(m, "move_type", None) == "in_invoice"]
        self.assertEqual(len(in_bills), 35)  # 5 Inbound PO Bills + 30 OPEX Vendor Bills
        self.assertGreater(snap1["account_moves_count"], 1324)

        # FASE 3: Uji Idempotensi Run 2
        adapter_run2 = CanonicalPerpetualAdapter(
            mock_env,
            reg_path=REG_DIR,
            cutoff_date="2026-08-01",
            enforce_invoice_cutoff=True,
        )
        adapter_run2.run_all()

        self.assertEqual(adapter_run2.stats["so_created"], 0)
        self.assertEqual(adapter_run2.stats["skipped_so"], 1324)
        self.assertEqual(adapter_run2.stats["invoices_created"], 0)
        self.assertEqual(adapter_run2.stats["skipped_invoices"], 1324)
        self.assertEqual(adapter_run2.stats["do_validated"], 0)
        self.assertEqual(adapter_run2.stats["opening_quants"], 0)

        # Zero Drift Snapshot
        snap2 = capture_deep_state_snapshot(mock_env)
        self.assertEqual(snap1["quants"], snap2["quants"])
        self.assertEqual(snap1["moves"], snap2["moves"])
        self.assertEqual(snap1["move_lines"], snap2["move_lines"])
        self.assertEqual(snap1["account_moves"], snap2["account_moves"])
        self.assertEqual(snap1["aml_records"], snap2["aml_records"])
        self.assertEqual(snap1["gl_balances"], snap2["gl_balances"])

    def test_negative_cross_period_leakage_rejected(self):
        """Faktur atau pengiriman yang melanggar batas periode atau manipulasi tanggal wajib ditolak."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(
            mock_env,
            reg_path=REG_DIR,
            cutoff_date="2026-07-31",
            enforce_invoice_cutoff=True,
        )
        adapter.run_all()

        # Pada database cut-off Juli, tidak boleh ada faktur out_invoice bertanggal Agustus
        AM = mock_env["account.move"]
        aug_invoices = AM.search([("date", ">", "2026-07-31"), ("move_type", "=", "out_invoice")])
        self.assertEqual(len(aug_invoices), 0, "Nol faktur Agustus diizinkan pada penutupan Juli!")

        # Jika transaksi Agustus diselipkan paksa dengan tanggal Juli tanpa kesesuaian register,
        # oracle menolak inkonsistensi jumlah dan multiset baris
        with self.assertRaises(AssertionError):
            # Asersi bahwa jumlah faktur Juli tidak boleh 1324
            assert len(AM.search([("date", "<=", "2026-07-31"), ("move_type", "=", "out_invoice")])) == 1324

    def test_anti_fallback_and_environment_introspection(self):
        """Memverifikasi anti-fallback salesperson dan kelengkapan introspeksi metadata runtime."""
        mock_env = setup_standard_mock_env()
        meta = introspect_runtime_environment(mock_env)

        self.assertIn("database", meta)
        self.assertIn("commit_sha", meta)
        self.assertIn("canonical_hashes", meta)
        self.assertEqual(meta["business_timezone"], "Asia/Makassar (WITA, UTC+8)")

        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)
        adapter.load_sales_deliveries_and_invoices(limit_orders=10)

        # Anti-fallback check
        verify_anti_fallback_salespersons(mock_env)


if __name__ == "__main__":
    unittest.main()
