"""Unit tests for Generic Period Pack Loader (Fase F4).

Validates:
1. Manifest verification (LF SHA-256 integrity, tamper detection, missing files).
2. Continuity & preflight rules (master preservation, previous period baseline).
3. Idempotency logic and fail-closed drift detection.
4. Cross-period AP settlement binding.
"""

from decimal import Decimal
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.ops.load_period_pack import (
    GenericPeriodPackLoader,
    ManifestVerificationError,
    PeriodPackManifest,
    PreflightContinuityError,
    StateInconsistencyError,
)
from scripts.ops.verify_disposable_period_pack import (
    PeriodPackOracle,
    assert_disposable_database,
    audit_period_database,
    run_period_pack_fault_injection_probes,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
AUG_PACK_DIR = REPO_ROOT / "data" / "registers" / "periods" / "2026-08"


class MockModel:
    """Mock Odoo model for unit testing loader logic offline."""

    def __init__(self, records=None, count_val=0, auto_match=False):
        self._records = records or []
        self._count_val = count_val
        self._auto_match = auto_match

    def sudo(self):
        return self

    def with_context(self, **kwargs):
        return self

    def browse(self, record_id):
        for r in self._records:
            if getattr(r, "id", None) == record_id:
                return r
        return None

    def search(self, domain, limit=None):
        if self._auto_match:
            val_map = {}
            for term in domain:
                if isinstance(term, tuple) and len(term) == 3:
                    field, op, val = term
                    if op == "=":
                        val_map[field] = val
            rec = MockRecord(id=999, **val_map)
            return rec if limit == 1 else [rec]

        res = []
        for r in self._records:
            match = True
            for term in domain:
                if isinstance(term, tuple) and len(term) == 3:
                    field, op, val = term
                    r_val = getattr(r, field, None)
                    if op == "=" and r_val != val:
                        match = False
                        break
                    elif op == "in" and (r_val not in val and (r_val is not None or False not in val)):
                        match = False
                        break
                    elif op == "ilike" and (r_val is None or str(val).lower() not in str(r_val).lower()):
                        match = False
                        break
            if match:
                res.append(r)
        if limit == 1:
            return res[0] if res else None
        return res

    def search_count(self, domain):
        return self._count_val


class MockRecord:
    """Mock Odoo recordset element."""

    def __init__(self, **kwargs):
        self._data = kwargs
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __bool__(self):
        return True

    def __getattr__(self, name):
        return self._data.get(name, None)

    def exists(self):
        return True


class MockEnv:
    """Mock Odoo environment dictionary."""

    def __init__(self, models):
        self.models = models

    def __getitem__(self, item):
        return self.models.get(item, MockModel())


class TestPeriodPackManifest(unittest.TestCase):
    """Test manifest parsing and LF SHA-256 verification."""

    def test_august_manifest_checksums_all_pass(self):
        manifest = PeriodPackManifest(AUG_PACK_DIR)
        verified = manifest.verify_checksums(strict=True)
        self.assertEqual(manifest.period, "2026-08")
        self.assertEqual(manifest.pack_start, "2026-08-01")
        self.assertEqual(manifest.pack_end, "2026-08-31")
        self.assertGreater(len(verified), 10)
        self.assertIn("sales_orders.csv", verified)
        self.assertIn("invoices.csv", verified)
        self.assertIn("ap_payments.csv", verified)

    def test_missing_manifest_fails_fast(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with self.assertRaises(ManifestVerificationError):
                PeriodPackManifest(tmp_path)

    def test_tampered_file_triggers_manifest_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            shutil.copytree(AUG_PACK_DIR, tmp_path, dirs_exist_ok=True)

            # Tamper one file
            so_file = tmp_path / "sales_orders.csv"
            content = so_file.read_text(encoding="utf-8")
            so_file.write_text(content + "\nTAMPERED_ROW\n", encoding="utf-8")

            manifest = PeriodPackManifest(tmp_path)
            with self.assertRaises(ManifestVerificationError):
                manifest.verify_checksums(strict=True)

    def test_missing_declared_file_triggers_manifest_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            shutil.copytree(AUG_PACK_DIR, tmp_path, dirs_exist_ok=True)

            # Delete one declared file
            (tmp_path / "po_headers.csv").unlink()

            manifest = PeriodPackManifest(tmp_path)
            with self.assertRaises(ManifestVerificationError):
                manifest.verify_checksums(strict=True)


class TestGenericPeriodPackLoaderOffline(unittest.TestCase):
    """Test loader logic without live Odoo database."""

    def test_dry_run_evaluation_offline(self):
        loader = GenericPeriodPackLoader(
            env=None,
            pack_dir=AUG_PACK_DIR,
            dry_run=True,
            strict=True,
        )
        plan = loader.evaluate_dry_run()
        self.assertEqual(plan["period"], "2026-08")
        self.assertEqual(plan["so"]["to_create"], 1240)
        self.assertEqual(plan["delivery"]["to_create"], 1240)
        self.assertEqual(plan["invoice"]["to_create"], 1240)
        self.assertEqual(plan["ar"]["to_reconcile"], 1202)
        self.assertEqual(plan["ap"]["to_reconcile"], 1)
        self.assertEqual(plan["po"]["to_create"], 16)
        self.assertEqual(plan["opex"]["to_create"], 48)

    def test_preflight_fails_when_partner_count_low(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        mock_loc = MockRecord(id=10, company_id=1, usage="internal", complete_name="WH/Stock")
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "stock.location": MockModel(records=[mock_loc]),
            "res.partner": MockModel(count_val=200),  # Below threshold 350
            "product.product": MockModel(count_val=150),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, company_id=1)
        with self.assertRaises(PreflightContinuityError) as ctx:
            loader.verify_preflight()
        self.assertIn("partner count too low", str(ctx.exception))

    def test_preflight_fails_when_sku_count_low(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        mock_loc = MockRecord(id=10, company_id=1, usage="internal", complete_name="WH/Stock")
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "stock.location": MockModel(records=[mock_loc]),
            "res.partner": MockModel(count_val=354),
            "product.product": MockModel(count_val=80),  # Below threshold 140
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, company_id=1)
        with self.assertRaises(PreflightContinuityError) as ctx:
            loader.verify_preflight()
        self.assertIn("SKU count too low", str(ctx.exception))

    def test_preflight_fails_when_july_baseline_missing(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        mock_loc = MockRecord(id=10, company_id=1, usage="internal", complete_name="WH/Stock")
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "stock.location": MockModel(records=[mock_loc]),
            "res.partner": MockModel(count_val=354),
            "product.product": MockModel(count_val=150),
            "sale.order": MockModel(count_val=50),  # July SO missing
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, company_id=1)
        with self.assertRaises(PreflightContinuityError) as ctx:
            loader.verify_preflight()
        self.assertIn("Previous period (July) SO count too low", str(ctx.exception))

    def test_idempotency_skip_existing_matching_records(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        mock_loc = MockRecord(id=10, complete_name="WH/Stock")
        # Pre-populate one existing SO with exact matching net_dpp
        existing_so = MockRecord(
            id=101,
            company_id=1,
            client_order_ref="SO-202608-0001",
            amount_untaxed=355680.00,
            partner_id=MockRecord(id=1, ref="CUST-RTL-006", name="Warung Dani"),
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "stock.location": MockModel(records=[mock_loc]),
            "res.partner": MockModel(count_val=354, auto_match=True),
            "product.product": MockModel(count_val=150, auto_match=True),
            "sale.order": MockModel(records=[existing_so], count_val=1324),
            "account.move": MockModel(count_val=1),
            "purchase.order": MockModel(),
            "account.payment": MockModel(),
            "account.account": MockModel(auto_match=True),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True)
        loader.company = mock_company
        plan = loader.evaluate_dry_run()

        # 1 SO should be skipped, 1239 to create
        self.assertEqual(plan["so"]["to_skip"], 1)
        self.assertEqual(plan["so"]["to_create"], 1239)
        self.assertEqual(plan["so"]["conflicts"], 0)

    def test_idempotency_drift_fails_closed(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        # Pre-populate one existing SO with DRIFTED net_dpp (e.g. 500000 instead of 355680)
        drifted_so = MockRecord(
            id=101,
            company_id=1,
            client_order_ref="SO-202608-0001",
            amount_untaxed=500000.00,
            partner_id=MockRecord(id=1, ref="CUST-RTL-006", name="Warung Dani"),
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "product.product": MockModel(auto_match=True),
            "sale.order": MockModel(records=[drifted_so], count_val=1324),
            "account.move": MockModel(),
            "purchase.order": MockModel(),
            "account.payment": MockModel(),
            "account.account": MockModel(auto_match=True),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, strict=True)
        loader.company = mock_company
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader.evaluate_dry_run()
        self.assertIn("Drift detected on existing SO-202608-0001", str(ctx.exception))

    def test_ap_payment_settles_july_unilever_bill(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        mock_partner_unilever = MockRecord(id=50, name="PT Unilever Indonesia", ref="PRIN-002")
        mock_july_bill = MockRecord(
            id=201,
            company_id=1,
            move_type="in_invoice",
            state="posted",
            payment_state="not_paid",
            amount_total=2899971200.00,
            amount_residual=2899971200.00,
            ref="PO-2026-06-05",
            partner_id=mock_partner_unilever,
        )
        mock_journal_bank = MockRecord(id=5, company_id=1, type="bank")

        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "product.product": MockModel(auto_match=True),
            "res.partner": MockModel(records=[mock_partner_unilever], auto_match=True),
            "account.move": MockModel(records=[mock_july_bill]),
            "account.journal": MockModel(records=[mock_journal_bank]),
            "account.payment": MockModel(),
            "account.account": MockModel(auto_match=True),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, company_id=1)
        loader.company = mock_company

        # In dry run, AP should detect 1 to reconcile
        plan = loader.evaluate_dry_run()
        self.assertEqual(plan["ap"]["to_reconcile"], 1)
        self.assertEqual(plan["ap"]["to_skip"], 0)


class TestPeriodPackDisposableRuntimeVerification(unittest.TestCase):
    """Test runtime verification oracle, safety guard, and fault injection offline."""

    def test_oracle_expectations_match_august_registers(self):
        oracle = PeriodPackOracle(AUG_PACK_DIR)
        self.assertEqual(oracle.expected_po_count, 16)
        self.assertEqual(oracle.expected_so_count, 1240)
        self.assertEqual(oracle.expected_do_count, 1240)
        self.assertEqual(oracle.expected_inv_count, 1240)
        self.assertEqual(oracle.expected_ar_count, 1202)
        self.assertEqual(oracle.expected_ap_count, 1)
        self.assertEqual(oracle.expected_opex_count, 48)

        # Financial totals tie-out
        self.assertEqual(oracle.expected_gross_dpp, Decimal("4247988000.00"))
        self.assertEqual(oracle.expected_discount_dpp, Decimal("108961922.80"))
        self.assertEqual(oracle.expected_net_dpp, Decimal("4139026077.20"))
        self.assertEqual(oracle.expected_ap_paid, Decimal("2899971200.00"))

    def test_safety_guard_rejects_forbidden_databases(self):
        forbidden_names = [
            "production_db",
            "railway_live",
            "odoo_main",
            "official_live",
            "fmcg_prod",
        ]
        for db_name in forbidden_names:
            mock_cr = MockRecord(dbname=db_name)
            mock_env = MockRecord(cr=mock_cr)
            with self.assertRaises(RuntimeError) as ctx:
                assert_disposable_database(mock_env)
            self.assertIn("SAFETY-ABORT", str(ctx.exception))

    def test_safety_guard_accepts_disposable_databases(self):
        allowed_names = [
            "fmcg_full_disposable",
            "ci_db",
            "test_disposable",
            "disposable_runner",
            "test_db_2026",
        ]
        for db_name in allowed_names:
            mock_cr = MockRecord(dbname=db_name)
            mock_env = MockRecord(cr=mock_cr)
            res = assert_disposable_database(mock_env)
            self.assertEqual(res, db_name)

    def test_safety_guard_rejects_none_env(self):
        with self.assertRaises(RuntimeError) as ctx:
            assert_disposable_database(None)
        self.assertIn("Live disposable Odoo environment required", str(ctx.exception))

    def test_runtime_verifier_functions_reject_none_env(self):
        oracle = PeriodPackOracle(AUG_PACK_DIR)
        with self.assertRaises(RuntimeError) as ctx:
            audit_period_database(env=None, oracle=oracle)
        self.assertIn("Live disposable Odoo environment required", str(ctx.exception))

        with self.assertRaises(RuntimeError) as ctx2:
            run_period_pack_fault_injection_probes(env=None, pack_dir=AUG_PACK_DIR)
        self.assertIn("Live disposable Odoo environment required", str(ctx2.exception))

    def test_unresolved_sku_fails_fast_in_dry_run(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        # Empty product search -> any SKU will be unresolved
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "product.product": MockModel(records=[]),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, strict=True)
        loader.company = mock_company
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader.evaluate_dry_run()
        self.assertIn("missing SKU", str(ctx.exception))

    def test_opex_account_mapping_resolves_all_categories(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        mock_acc_610100 = MockRecord(id=11, code="610100", name="Beban Logistik", company_id=1)
        mock_acc_610200 = MockRecord(id=12, code="610200", name="Beban Gaji", company_id=1)
        mock_acc_610400 = MockRecord(id=13, code="610400", name="Beban Sewa", company_id=1)
        mock_acc_111100 = MockRecord(id=21, code="111100", name="Kas Operasional", company_id=1)
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "account.account": MockModel(records=[mock_acc_610100, mock_acc_610200, mock_acc_610400, mock_acc_111100]),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, strict=True)
        loader.company = mock_company
        # Verify resolution of explicit accounts
        acc_log = loader._resolve_account("610100", "expense")
        self.assertEqual(acc_log.code, "610100")
        acc_gaji = loader._resolve_account("610200", "expense")
        self.assertEqual(acc_gaji.code, "610200")
        acc_sewa = loader._resolve_account("610400", "expense")
        self.assertEqual(acc_sewa.code, "610400")

    def test_invoice_idempotency_drift_fails_closed(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        # Existing invoice with drifted total
        existing_inv = MockRecord(
            id=501,
            company_id=1,
            move_type="out_invoice",
            payment_reference="INV-202608-0001",
            amount_total=9999999.00,  # Drifted total
            amount_untaxed=355680.00,
            is_fmcg_seed_invoice=True,
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "product.product": MockModel(auto_match=True),
            "account.move": MockModel(records=[existing_inv]),
            "sale.order": MockModel(),
            "purchase.order": MockModel(),
            "account.payment": MockModel(),
            "account.account": MockModel(records=[MockRecord(id=1, code="610100", company_id=1)]),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, strict=True)
        loader.company = mock_company
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader.evaluate_dry_run()
        self.assertIn("Drift detected on Invoice INV-202608-0001", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
