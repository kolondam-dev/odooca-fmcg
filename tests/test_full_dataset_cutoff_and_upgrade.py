#!/usr/bin/env python3
"""Unit & Acceptance Tests untuk Full Dataset Runner, Two-Phase Cut-Off, dan Audit Independen.

Menguji:
1. Dynamic Oracle: ekspektasi dihitung dinamis dari CSV (lulus probe mutasi in-memory).
2. Rekonsiliasi 14 kunjungan 31 Juli menjadi 48 pesanan single-prinsipal 1 Agustus dengan lineage lengkap.
3. Eksekusi dua fase deterministik: Closing 31 Juli 2026 vs Post-Transaksi 1 Agustus 2026 dan immutabilitas.
4. Zero drift penuh pada deep state snapshot (quants, moves, move_lines, pickings, orders, AML, GL).
5. Uji mutasi negatif nyata pada database ditolak oleh audit produksi (stok salah, AML seimbang salah-nilai, tanggal).
6. Sensitivitas snapshot: perubahan singular account_move_id, product_id, location_id, atau datetime terdeteksi.
7. Safety guard: penolakan mutlak nama database non-disposable atau terlarang, serta ketahanan reporting failure.
"""

from decimal import Decimal
import json
from pathlib import Path
import tempfile
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
    resolve_canonical_company,
    resolve_canonical_locations,
    run_full_disposable_verification,
    run_real_negative_mutations_on_database,
)
from tests.test_canonical_loader_adapter import setup_standard_mock_env  # noqa: E402
from scripts.ops.verify_upgrade_baseline import (  # noqa: E402
    CREATION_COUNTERS,
    EXPECTED_SKIP_MINIMUMS,
    assert_replay_zero_creation,
    assert_upgrade_target_database,
    build_upgrade_command,
    compare_snapshot_digests,
    detect_registry_corruption,
    digest_payload,
    expected_module_versions,
    is_column_backed_field,
    load_baseline_state,
    previous_release_version,
    run_upgrade_baseline_verification,
    snapshot_digest,
    validate_upgrade_exit_code,
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

        # COGS Nominal
        self.assertEqual(Decimal(july["july_cogs_nominal"]), Decimal("4971741000.00"))
        self.assertEqual(Decimal(aug["total_cogs_nominal"]), Decimal("5138995000.00"))

        # Saldo Fisik & Reservasi Stok Dinamis (Karton & Unit Base UoM)
        self.assertEqual(july["physical_on_hand_cartons_july"], 53837)
        self.assertEqual(july["reserved_cartons_july"], 1038)
        self.assertEqual(july["available_cartons_july"], 52799)
        self.assertEqual(july["quarantine_cartons_july"], 9)
        self.assertEqual(july["physical_units_july"], 2911524)
        self.assertEqual(july["reserved_units_july"], 56282)
        self.assertEqual(july["quarantine_units_july"], 320)

        # August Post-Transaction
        self.assertEqual(aug["physical_on_hand_cartons_august"], 52799)
        self.assertEqual(aug["reserved_cartons_august"], 0)
        self.assertEqual(aug["physical_units_august"], 2855242)
        self.assertEqual(aug["reserved_units_august"], 0)
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

        # Lineage customer, salesman, and principal
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

        # Simpan snapshot baris AML Juli immutable untuk uji immutabilitas
        AML = mock_env["account.move.line"]
        july_amls = sorted([
            (
                ln.id,
                getattr(getattr(ln, "move_id", None), "id", None),
                getattr(getattr(ln, "account_id", None), "code", "") or "",
                getattr(getattr(ln, "product_id", None), "id", None),
                str(round(float(getattr(ln, "debit", 0.0) or 0.0), 2)),
                str(round(float(getattr(ln, "credit", 0.0) or 0.0), 2)),
                str(getattr(ln, "date", "") or ""),
                str(round(float(getattr(ln, "amount_residual", 0.0) or 0.0), 2)),
                getattr(ln, "reconciled", False),
                getattr(getattr(ln, "company_id", None), "id", None),
            )
            for ln in AML.search([("date", "<=", "2026-07-31")])
        ])

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

    def test_real_mutations_rejected_by_production_audit(self):
        """Mutasi negatif nyata pada database (stok swap, lot dummy, AML seimbang) wajib digagalkan audit."""
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

        # Jalankan rangkaian 9 mutasi counterexample nyata via savepoint context manager
        mut_results = run_real_negative_mutations_on_database(mock_env, oracle)
        self.assertEqual(len(mut_results), 9)
        for probe_code, probe_info in mut_results.items():
            self.assertEqual(
                probe_info.get("status"),
                "REJECTED_AS_EXPECTED",
                f"Probe {probe_code} tidak berstatus REJECTED_AS_EXPECTED: {probe_info}",
            )

        # Baseline wajib tetap PASS setelah seluruh mutasi di-rollback
        audit_database_against_oracle_july(mock_env, oracle)

    def test_july_historical_closing_immutability_detects_value_modifications(self):
        """Audit Agustus wajib mendeteksi perubahan nilai pada jurnal Juli meskipun jumlah baris tetap sama."""
        mock_env = setup_standard_mock_env()
        oracle = FullDatasetCanonicalOracle(REG_DIR)

        adapter_july = CanonicalPerpetualAdapter(
            mock_env,
            reg_path=REG_DIR,
            cutoff_date="2026-07-31",
            enforce_invoice_cutoff=True,
        )
        adapter_july.run_all()

        AML = mock_env["account.move.line"]
        july_amls_snapshot = sorted([
            (
                ln.id,
                getattr(getattr(ln, "move_id", None), "id", None),
                getattr(getattr(ln, "account_id", None), "code", "") or "",
                getattr(getattr(ln, "product_id", None), "id", None),
                str(round(float(getattr(ln, "debit", 0.0) or 0.0), 2)),
                str(round(float(getattr(ln, "credit", 0.0) or 0.0), 2)),
                str(getattr(ln, "date", "") or ""),
                str(round(float(getattr(ln, "amount_residual", 0.0) or 0.0), 2)),
                getattr(ln, "reconciled", False),
                getattr(getattr(ln, "company_id", None), "id", None),
            )
            for ln in AML.search([("date", "<=", "2026-07-31")])
        ])

        # Carry forward Agustus
        adapter_aug = CanonicalPerpetualAdapter(
            mock_env,
            reg_path=REG_DIR,
            cutoff_date="2026-08-01",
            enforce_invoice_cutoff=True,
        )
        adapter_aug.run_all()

        # Baseline as-of closing audit PASS
        audit_database_against_oracle_august(mock_env, oracle, prior_july_aml_snapshot=july_amls_snapshot)

        # PROBE SUPERVISOR: Ubah nilai debit pada baris Juli tanpa menambah baris (count tetap sama)
        target_line = next(ln for ln in AML.search([("date", "<=", "2026-07-31")]) if ln.debit > 0)
        orig_debit = target_line.debit
        target_line.debit += 1000.0

        with self.assertRaises(AssertionError):
            audit_database_against_oracle_august(mock_env, oracle, prior_july_aml_snapshot=july_amls_snapshot)

        # Rollback
        target_line.debit = orig_debit
        audit_database_against_oracle_august(mock_env, oracle, prior_july_aml_snapshot=july_amls_snapshot)

        # PROBE SUPERVISOR P1: Outbound Source Location Corruption pada Audit Agustus
        SM = mock_env["stock.move"]
        aug_target_mv = next(
            m for m in SM.search([("state", "=", "done")])
            if getattr(getattr(m, "location_dest_id", None), "usage", "") == "customer"
            and not getattr(m, "origin_returned_move_id", False)
            and getattr(m, "account_move_id", None)
        )
        sup_loc = next(
            loc for loc in mock_env["stock.location"].search([])
            if getattr(loc, "usage", "") == "supplier"
        )
        orig_mv_loc = aug_target_mv.location_id
        aug_target_mv.location_id = sup_loc
        with self.assertRaises(AssertionError) as ctx:
            audit_database_against_oracle_august(mock_env, oracle, prior_july_aml_snapshot=july_amls_snapshot)
        self.assertIn("VIOLATION OUTBOUND SOURCE", str(ctx.exception))
        aug_target_mv.location_id = orig_mv_loc
        audit_database_against_oracle_august(mock_env, oracle, prior_july_aml_snapshot=july_amls_snapshot)

    def test_deep_state_snapshot_detects_field_modifications(self):
        """Membuktikan probe supervisor: modifikasi product_id, location_id, atau datetime move line terdeteksi."""
        mock_env = setup_standard_mock_env()
        SML = mock_env["stock.move.line"]
        SM = mock_env["stock.move"]

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
        fixture_sml.date = "2026-07-31 00:00:00"

        # Probe 4: Ubah singular account_move_id pada stock move
        fixture_sm = SM.create({
            "product_id": 10,
            "location_id": 1,
            "location_dest_id": 3,
            "product_uom_qty": 50.0,
            "state": "done",
            "account_move_id": 101,
        })
        snap_sm1 = capture_deep_state_snapshot(mock_env)
        fixture_sm.account_move_id = 999
        snap_sm2 = capture_deep_state_snapshot(mock_env)
        self.assertNotEqual(snap_sm1["moves"], snap_sm2["moves"])

    def test_safety_guard_rejects_non_disposable_and_forbidden_substrings(self):
        """Safety guard wajib menolak nama database operasional atau yang memuat substring terlarang."""
        for forbidden_db in ["official_live", "fmcg_full_production", "fmcg_base", "railway", "master_db"]:
            env_bad = setup_standard_mock_env()
            env_bad.cr.dbname = forbidden_db
            with self.assertRaises(RuntimeError) as ctx:
                assert_disposable_database(env_bad)
            self.assertIn("SAFETY-ABORT", str(ctx.exception))

        for valid_db in ["fmcg_full_disposable", "ci_db", "test_disposable", "tenant_disposable_slice"]:
            env_good = setup_standard_mock_env()
            env_good.cr.dbname = valid_db
            self.assertEqual(assert_disposable_database(env_good), valid_db)

    def test_failure_reporting_resilience_and_no_unbound_local(self):
        """Kegagalan awal pada runner tidak boleh tertutup oleh UnboundLocalError dan report MD mencatat FAILED."""
        env_bad = setup_standard_mock_env()
        env_bad.cr.dbname = "official_live"

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(RuntimeError):
                run_full_disposable_verification(env_bad, output_dir=tmpdir)

            report_file = Path(tmpdir) / "full_dataset_runtime_report.json"
            summary_file = Path(tmpdir) / "full_dataset_runtime_summary.md"
            self.assertTrue(report_file.exists())
            self.assertTrue(summary_file.exists())

            summary_text = summary_file.read_text(encoding="utf-8")
            self.assertIn("Status:** FAILED", summary_text)
            self.assertIn("FAIL / INCOMPLETE", summary_text)
            self.assertNotIn("Status:** SUCCESS", summary_text)

    def test_canonical_location_resolver_rejects_ambiguity_and_foreign_company(self):
        """Resolver lokasi wajib fail-closed jika ambigu atau gudang berasal dari company lain."""
        mock_env = setup_standard_mock_env()
        self.assertEqual(resolve_canonical_company(mock_env).id, mock_env.company.id)
        wh_loc, quar_loc, comp = resolve_canonical_locations(mock_env)
        self.assertIsNotNone(wh_loc)
        self.assertIsNotNone(quar_loc)
        self.assertEqual(comp.id, mock_env.company.id)

        # 1. Foreign Warehouse: warehouse di company lain tidak boleh dipilih
        foreign_comp = mock_env["res.company"].create({"name": "Foreign Corp", "code": "FOR"})
        foreign_loc = mock_env["stock.location"].create({
            "name": "Foreign/Stock",
            "usage": "internal",
            "company_id": foreign_comp.id,
        })
        mock_env["stock.warehouse"].create({
            "name": "Foreign Warehouse",
            "code": "WH",
            "lot_stock_id": foreign_loc,
            "company_id": foreign_comp,
        })
        # Resolver tetap memilih canonical company (FMCG)
        wh_loc2, _, comp2 = resolve_canonical_locations(mock_env)
        self.assertEqual(wh_loc2.id, wh_loc.id)
        self.assertEqual(comp2.id, mock_env.company.id)

        # 2. Ambiguitas Warehouse pada canonical company: 2 warehouse dengan code WH di company yang sama
        mock_env["stock.warehouse"].create({
            "name": "Duplicate WH",
            "code": "WH",
            "lot_stock_id": wh_loc,
            "company_id": mock_env.company,
        })
        with self.assertRaises(LookupError) as ctx:
            resolve_canonical_locations(mock_env)
        self.assertIn("ambigu atau tidak ditemukan", str(ctx.exception))

        # 3. Counterexample Supervisor P2: Canonical company tidak ditemukan, env.company adalah Unrelated ID 999
        env_foreign = setup_standard_mock_env()
        # Kosongkan store res.company lalu buat unrelated company saja
        env_foreign["res.company"].store.clear()
        unrelated_comp = env_foreign["res.company"].create({"name": "Unrelated Company", "code": "OTHER"})
        env_foreign.company = unrelated_comp
        with self.assertRaises(LookupError) as ctx:
            resolve_canonical_company(env_foreign)
        self.assertIn("Canonical company binding tidak ditemukan", str(ctx.exception))

        # 4. Counterexample Supervisor P2: Canonical company ada, tapi tidak ada warehouse WH (hanya lone AUX)
        env_aux = setup_standard_mock_env()
        # Hapus warehouse WH, ganti dengan lone AUX
        env_aux["stock.warehouse"].store.clear()
        aux_loc = env_aux["stock.location"].create({
            "name": "Auxiliary Stock",
            "usage": "internal",
            "company_id": env_aux.company.id,
        })
        env_aux["stock.warehouse"].create({
            "name": "Auxiliary Depot",
            "code": "AUX",
            "lot_stock_id": aux_loc,
            "company_id": env_aux.company,
        })
        with self.assertRaises(LookupError) as ctx:
            resolve_canonical_locations(env_aux)
        self.assertIn("Warehouse gudang utama ('code'='WH') ambigu atau tidak ditemukan", str(ctx.exception))

        # 5. Explicit binding via ir.config_parameter 'fmcg.seed_company_id' untuk generic company
        env_param = setup_standard_mock_env()
        env_param["res.company"].store.clear()
        generic_comp = env_param["res.company"].create({"name": "My Company", "code": False})
        env_param["ir.config_parameter"].set_param("fmcg.seed_company_id", str(generic_comp.id))
        resolved_param = resolve_canonical_company(env_param)
        self.assertEqual(resolved_param.id, generic_comp.id)

        # 6. Explicit binding via XMLID 'id_base.fmcg_seed_company'
        env_xmlid = setup_standard_mock_env()
        env_xmlid["res.company"].store.clear()
        xmlid_comp = env_xmlid["res.company"].create({"name": "Custom Seed Company", "code": False})
        env_xmlid.ref = (
            lambda xmlid, raise_if_not_found=True: xmlid_comp if xmlid == "id_base.fmcg_seed_company" else None
        )
        # Clear config param agar menguji jalur XMLID secara independen
        env_xmlid["ir.config_parameter"].store.clear()
        resolved_xmlid = resolve_canonical_company(env_xmlid)
        self.assertEqual(resolved_xmlid.id, xmlid_comp.id)

    def test_exact_hpp_journal_binding_rejects_wrong_journal_account_direction_or_reuse(self):
        """Audit HPP produksi wajib menolak jurnal non-STJ, arah debit-kredit terbalik, nominal salah, atau reuse."""
        mock_env = setup_standard_mock_env()
        oracle = FullDatasetCanonicalOracle(REG_DIR)

        # Setup cut-off Juli
        adapter = CanonicalPerpetualAdapter(
            mock_env,
            reg_path=REG_DIR,
            cutoff_date="2026-07-31",
            enforce_invoice_cutoff=True,
        )
        adapter.run_all()

        # Baseline PASS
        audit_database_against_oracle_july(mock_env, oracle)

        SM = mock_env["stock.move"]
        target_mv = next(
            m for m in SM.search([("state", "=", "done")])
            if getattr(getattr(m, "location_dest_id", None), "usage", "") == "customer"
            and not getattr(m, "origin_returned_move_id", False)
            and getattr(m, "account_move_id", None)
        )
        orig_am = target_mv.account_move_id

        # 1. Wrong journal code (bukan STJ)
        orig_jnl = orig_am.journal_id
        orig_am.journal_id = mock_env["account.journal"].create({"name": "Bank Journal", "code": "BNK"})
        with self.assertRaises(AssertionError) as ctx:
            audit_database_against_oracle_july(mock_env, oracle)
        self.assertIn("diharapkan 'STJ'", str(ctx.exception))
        orig_am.journal_id = orig_jnl

        # 2. Date mismatch antara stock.move dan account.move
        orig_date = orig_am.date
        orig_am.date = "2026-07-20"
        target_mv.date = "2026-07-21"
        with self.assertRaises(AssertionError) as ctx:
            audit_database_against_oracle_july(mock_env, oracle)
        self.assertIn("mismatch dengan stock move date", str(ctx.exception))
        orig_am.date = orig_date
        target_mv.date = orig_date

        # 3. Direction swap pada baris HPP (510000 memiliki credit != 0.00)
        d_ln = next(ln for ln in orig_am.line_ids if getattr(ln.account_id, "code", "") == "510000")
        c_ln = next(ln for ln in orig_am.line_ids if getattr(ln.account_id, "code", "") == "113000")
        orig_debit = d_ln.debit
        orig_credit = c_ln.credit
        d_ln.debit, d_ln.credit = 0.0, orig_debit
        c_ln.debit, c_ln.credit = orig_credit, 0.0
        with self.assertRaises(AssertionError) as ctx:
            audit_database_against_oracle_july(mock_env, oracle)
        self.assertTrue(
            "Audit COGS Nominal Juli Mismatch" in str(ctx.exception)
            or "memiliki 0 baris debit 510000" in str(ctx.exception)
            or "memiliki credit" in str(ctx.exception)
            or "baris debit 510000 mismatch" in str(ctx.exception)
        )
        d_ln.debit, d_ln.credit = orig_debit, 0.0
        c_ln.debit, c_ln.credit = 0.0, orig_credit

        # 4. AML reuse / cross-move binding
        other_mv = next(
            m for m in SM.search([("state", "=", "done")])
            if getattr(getattr(m, "location_dest_id", None), "usage", "") == "customer"
            and not getattr(m, "origin_returned_move_id", False)
            and getattr(m, "account_move_id", None)
            and m.id != target_mv.id
        )
        target_mv.account_move_id = other_mv.account_move_id
        with self.assertRaises(AssertionError) as ctx:
            audit_database_against_oracle_july(mock_env, oracle)
        self.assertTrue(
            "VIOLATION AML REUSE" in str(ctx.exception)
            or "debit 510000 mismatch" in str(ctx.exception)
            or "product ID" in str(ctx.exception)
            or "unconsumed" in str(ctx.exception)
        )
        target_mv.account_move_id = orig_am

        # 5. Outbound source location corruption (supplier location / foreign internal)
        sup_loc = next(
            loc for loc in mock_env["stock.location"].search([])
            if getattr(loc, "usage", "") == "supplier"
        )
        orig_src_loc = target_mv.location_id
        target_mv.location_id = sup_loc
        with self.assertRaises(AssertionError) as ctx:
            audit_database_against_oracle_july(mock_env, oracle)
        self.assertIn("VIOLATION OUTBOUND SOURCE", str(ctx.exception))
        target_mv.location_id = orig_src_loc


class TestUpgradeBaselineRunner(unittest.TestCase):
    """Kontrak runner Prioritas 3: upgrade dari baseline persisten + replay idempotensi.

    Catatan: pengujian unit ini memvalidasi kontrak logika runner. Pembuktian upgrade
    nyata (`odoo -u`) wajib dieksekusi pada container Odoo 19 + PostgreSQL 16 melalui
    `.github/workflows/upgrade-runtime.yml`; bukan pengganti eksekusi nyata.
    """

    def test_upgrade_guard_rejects_operational_databases(self):
        """Guard database disposable upgrade wajib fail-closed untuk nama operasional."""
        for forbidden_db in [
            "fmcg_live",
            "fmcg_full_production",
            "railway",
            "master_db",
            "official_main",
            "fmcg_base",
            "prod_fmcg",
        ]:
            with self.assertRaises(RuntimeError) as ctx:
                assert_upgrade_target_database(forbidden_db)
            self.assertIn("SAFETY-ABORT", str(ctx.exception))

        for valid_db in ["fmcg_upgrade_disposable", "fmcg_full_disposable", "ci_db", "tenant_disposable_slice"]:
            self.assertEqual(assert_upgrade_target_database(valid_db), valid_db)

        with self.assertRaises(RuntimeError):
            assert_upgrade_target_database("   ")

    def test_upgrade_command_is_real_odoo_update(self):
        """Perintah upgrade wajib memuat `-u id_base,id_mobile_api` dan `--stop-after-init`."""
        argv = build_upgrade_command("fmcg_upgrade_disposable", addons_path="/opt/id-addons")
        self.assertEqual(argv[0], "odoo")
        self.assertEqual(argv[argv.index("-d") + 1], "fmcg_upgrade_disposable")
        self.assertEqual(argv[argv.index("-u") + 1], "id_base,id_mobile_api")
        self.assertIn("--stop-after-init", argv)
        self.assertIn("/opt/id-addons", argv)

        with self.assertRaises(RuntimeError):
            build_upgrade_command("fmcg_production")

    def test_upgrade_process_contract_detects_failures(self):
        """Kontrak proses: exit code 0 dan log bebas indikasi registry corruption."""
        ok = validate_upgrade_exit_code(
            0, "2026-10-30 10:00:00 INFO db odoo.modules.loading: Modules loaded.\n"
        )
        self.assertEqual(ok["status"], "PASS")
        self.assertEqual(ok["corruption_findings"], [])

        with self.assertRaises(RuntimeError) as ctx:
            validate_upgrade_exit_code(2, "log normal tanpa error")
        self.assertIn("UPGRADE-FAIL", str(ctx.exception))

        # Exit 0 tanpa penanda registry dimuat bukan bukti upgrade (mis. abort konfigurasi dini).
        with self.assertRaises(RuntimeError) as ctx:
            validate_upgrade_exit_code(0, "2026-10-30 10:00:00 WARNING db odoo.tools.config: oke\n")
        self.assertIn("Modules loaded", str(ctx.exception))

        corrupt_log = (
            "2026-10-30 10:00:00 CRITICAL db odoo.modules.loading: Registry loading failed\n"
            "Traceback (most recent call last):\n"
        )
        with self.assertRaises(RuntimeError) as ctx:
            validate_upgrade_exit_code(0, corrupt_log)
        self.assertIn("UPGRADE-FAIL", str(ctx.exception))

        self.assertEqual(detect_registry_corruption("semua baik"), [])
        self.assertTrue(detect_registry_corruption("psycopg2.errors.UndefinedColumn: kolom hilang"))

    def test_previous_release_version_is_strictly_lower(self):
        """Version skew simulasi harus benar-benar lebih rendah dari versi manifest."""
        def as_tuple(value):
            return tuple(int(part) for part in value.split("."))

        for manifest_version in ("19.0.1.0.0", "19.0.1.2.0", "19.0.2.0.0"):
            previous = previous_release_version(manifest_version)
            self.assertLess(as_tuple(previous), as_tuple(manifest_version))
        self.assertEqual(previous_release_version("19.0.1.2.0"), "19.0.1.1.0")
        self.assertEqual(previous_release_version("19.0.1.0.0"), "19.0.0.0.0")
        self.assertEqual(previous_release_version("tidak-valid"), "19.0.0.0.0")

        versions = expected_module_versions()
        self.assertEqual(set(versions), {"id_base", "id_mobile_api"})
        for name, version in versions.items():
            self.assertTrue(version.startswith("19.0."), f"{name} versi manifest tidak sah: {version}")

    def test_replay_zero_creation_contract(self):
        """Replay pasca-upgrade wajib 0 record baru dan minimum skip kanonikal terpenuhi."""
        stats = {key: 0 for key in CREATION_COUNTERS}
        stats.update(EXPECTED_SKIP_MINIMUMS)
        result = assert_replay_zero_creation(stats)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["total_created"], 0)

        created_drift = dict(stats)
        created_drift["so_created"] = 1
        with self.assertRaises(AssertionError) as ctx:
            assert_replay_zero_creation(created_drift)
        self.assertIn("UPGRADE-REPLAY", str(ctx.exception))

        skip_shortfall = dict(stats)
        skip_shortfall["skipped_so"] = 10
        with self.assertRaises(AssertionError) as ctx:
            assert_replay_zero_creation(skip_shortfall)
        self.assertIn("UPGRADE-REPLAY", str(ctx.exception))

    def test_snapshot_digest_normalizes_tuples_and_lists(self):
        """Digest snapshot harus stabil meski state melewati serialisasi JSON (tuple -> list)."""
        tuples_payload = {"quants": [(1, 2), (3, 4)], "moves": [], "gl_balances": {"113000": "x"}}
        lists_payload = {"quants": [[1, 2], [3, 4]], "moves": [], "gl_balances": {"113000": "x"}}
        self.assertEqual(digest_payload(tuples_payload["quants"]), digest_payload(lists_payload["quants"]))
        self.assertEqual(snapshot_digest(tuples_payload), snapshot_digest(lists_payload))

        baseline = snapshot_digest(tuples_payload)
        drifted = snapshot_digest({"quants": [[1, 2], [9, 9]], "moves": [], "gl_balances": {"113000": "x"}})
        with self.assertRaises(AssertionError) as ctx:
            compare_snapshot_digests(baseline, drifted)
        self.assertIn("UPGRADE-DRIFT", str(ctx.exception))

    def test_baseline_state_roundtrip_and_fail_closed_database(self):
        """State baseline wajib memuat digest dan menolak database target yang berbeda."""
        state = {
            "schema_version": 1,
            "database": "fmcg_upgrade_disposable",
            "snapshot_digests": {"quants": "abc"},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "upgrade_baseline_state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")

            loaded = load_baseline_state(state_path, expected_database="fmcg_upgrade_disposable")
            self.assertEqual(loaded["database"], "fmcg_upgrade_disposable")

            with self.assertRaises(RuntimeError) as ctx:
                load_baseline_state(state_path, expected_database="lain_disposable")
            self.assertIn("Ditolak", str(ctx.exception))

            with self.assertRaises(RuntimeError):
                load_baseline_state(Path(tmpdir) / "tidak_ada.json")

            no_digest_path = Path(tmpdir) / "no_digest.json"
            no_digest_path.write_text(json.dumps({"schema_version": 1, "database": "x"}), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                load_baseline_state(no_digest_path)

    def test_schema_integrity_skips_non_column_fields(self):
        """Field attachment/relasional/non-stored tidak boleh dianggap kolom hilang (regresi DDL)."""

        class _FakeField:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        self.assertTrue(is_column_backed_field(_FakeField(store=True, type="char", column_type="varchar")))
        self.assertTrue(is_column_backed_field(_FakeField(store=True, type="float", column_type="numeric")))
        self.assertTrue(is_column_backed_field(_FakeField(store=True, type="many2one", column_type="int4")))
        # Binary attachment=True disimpan di ir.attachment, bukan kolom tabel.
        self.assertFalse(
            is_column_backed_field(
                _FakeField(store=True, type="binary", attachment=True, column_type="varchar")
            )
        )
        self.assertFalse(is_column_backed_field(_FakeField(store=True, type="many2many", column_type=None)))
        self.assertFalse(is_column_backed_field(_FakeField(store=True, type="one2many", column_type=None)))
        self.assertFalse(is_column_backed_field(_FakeField(store=False, type="char", column_type="varchar")))
        self.assertFalse(is_column_backed_field(_FakeField(store=True, type="char", column_type=None)))

    def test_verify_failure_writes_failed_report(self):
        """Kegagalan guard pada fase verify wajib tetap menulis report FAILED untuk audit."""
        env_bad = setup_standard_mock_env()
        env_bad.cr.dbname = "official_live"

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(RuntimeError):
                run_upgrade_baseline_verification(env_bad, output_dir=tmpdir)

            report_file = Path(tmpdir) / "upgrade_runtime_report.json"
            summary_file = Path(tmpdir) / "upgrade_runtime_summary.md"
            self.assertTrue(report_file.exists())
            self.assertTrue(summary_file.exists())
            self.assertIn("FAILED", report_file.read_text(encoding="utf-8"))
            summary_text = summary_file.read_text(encoding="utf-8")
            self.assertIn("Status:** FAILED", summary_text)
            self.assertNotIn("Status:** SUCCESS", summary_text)


if __name__ == "__main__":
    unittest.main()
