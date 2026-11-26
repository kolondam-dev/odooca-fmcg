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
from types import SimpleNamespace
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


class TestHistoricalSalesOwnership(unittest.TestCase):
    def test_august_registry_owns_every_order(self):
        manifest = PeriodPackManifest(AUG_PACK_DIR)
        loader = GenericPeriodPackLoader(env=None, pack_dir=AUG_PACK_DIR)
        owners = manifest.sales_owners()
        order_logins = [
            owners[row["customer"].split(" - ", 1)[0]] for row in loader.reader.sales_orders
        ]
        self.assertEqual(len(order_logins), 1240)
        self.assertEqual(set(order_logins), {"cvs-01", "cvs-02", "mgt-01", "sls-01", "sls-02", "sls-03"})

    def test_seed_header_restores_native_confirmation_date_and_owner_once(self):
        loader = GenericPeriodPackLoader(env=None, pack_dir=AUG_PACK_DIR)
        row = {"date_order": "2026-08-03"}
        order = MockRecord(date_order="2026-11-22 08:00:00", user_id=1)
        loader._sync_seed_order_header(order, row, 7)
        self.assertEqual(order.date_order, "2026-08-03")
        self.assertEqual(order.user_id, 7)
        order.write = lambda values: self.fail(f"Matching replay unexpectedly wrote {values}")
        loader._sync_seed_order_header(order, row, 7)


class MockModel:
    """Mock Odoo model for unit testing loader logic offline."""

    def __init__(self, records=None, count_val=0, auto_match=False):
        self._records = records if records is not None else []
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
        if self._records:
            res = []
            for r in self._records:
                match = True
                for term in domain:
                    if isinstance(term, tuple) and len(term) == 3:
                        field, op, val = term
                        r_val = getattr(r, field, None)
                        r_id = getattr(r_val, "id", None)
                        if op == "=":
                            if r_val != val and (r_id is None or r_id != val):
                                match = False
                                break
                        elif op == "in":
                            val_set = set(val) if isinstance(val, (list, tuple, set)) else {val}
                            if isinstance(r_val, (list, tuple, set)):
                                if not any(x in val_set for x in r_val):
                                    match = False
                                    break
                            else:
                                if (
                                    r_val not in val_set
                                    and (r_id is None or r_id not in val_set)
                                    and (r_val is not None or False not in val_set)
                                ):
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

        if self._auto_match:
            val_map = {}
            for term in domain:
                if isinstance(term, tuple) and len(term) == 3:
                    field, op, val = term
                    if op == "=":
                        val_map[field] = val
            rec = MockRecord(id=999, **val_map)
            return rec if limit == 1 else [rec]

        return None if limit == 1 else []

    def search_count(self, domain):
        return self._count_val

    def with_company(self, company):
        return self

    def create(self, vals):
        new_id = len(self._records) + 1
        rec = MockRecord(id=new_id, **vals)
        if "partner_id" in vals and isinstance(vals["partner_id"], int) and hasattr(self, "_env"):
            p_model = getattr(self._env, "models", {}).get("res.partner")
            if p_model:
                p_rec = p_model.browse(vals["partner_id"])
                if p_rec:
                    rec.partner_id = p_rec
        if "account_id" in vals and isinstance(vals["account_id"], int) and hasattr(self, "_env"):
            acc_model = getattr(self._env, "models", {}).get("account.account")
            if acc_model:
                acc_rec = acc_model.browse(vals["account_id"])
                if acc_rec:
                    rec.account_id = acc_rec
        if "tax_line_id" in vals and isinstance(vals["tax_line_id"], int) and hasattr(self, "_env"):
            t_model = getattr(self._env, "models", {}).get("account.tax")
            if t_model:
                t_rec = t_model.browse(vals["tax_line_id"])
                if t_rec:
                    rec.tax_line_id = t_rec
        self._records.append(rec)
        return rec


class MockRecord:
    """Mock Odoo recordset element."""

    def __init__(self, **kwargs):
        self._data = dict(kwargs)
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __bool__(self):
        return True

    def __getattr__(self, name):
        return self._data.get(name, None)

    def exists(self):
        return True

    def with_company(self, company):
        return self

    def with_context(self, **kwargs):
        return self

    def write(self, vals):
        self._data.update(vals)
        for k, v in vals.items():
            setattr(self, k, v)
        return True

    def action_post(self):
        self.write({"state": "posted"})
        return True


class MockEnv:
    """Mock Odoo environment dictionary."""

    def __init__(self, models):
        self.models = models
        for m in models.values():
            if isinstance(m, MockModel):
                m._env = self

    def __getitem__(self, item):
        return self.models.get(item, MockModel())

    def get(self, item, default=None):
        return self.models.get(item, default)

    def __contains__(self, item):
        return item in self.models

    def __iter__(self):
        return iter(self.models)


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
            "account.journal": MockModel(records=[MockRecord(id=1, code="MISC", type="general", company_id=1)]),
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

    def test_ap_bank_resolution_fails_closed(self):
        row = {"ap_payment_id": "PAY-TEST", "bank_source": "Bank Mandiri Rekening Operasional"}
        bank = MockRecord(
            id=1, company_id=1, type="bank", code="BNK1", default_account_id=MockRecord(id=8, code="101401"),
        )
        loader = GenericPeriodPackLoader(env=MockEnv({"account.journal": MockModel(records=[bank])}),
                                         pack_dir=AUG_PACK_DIR, dry_run=False)
        loader.company = MockRecord(id=1)
        self.assertIs(loader._resolve_ap_bank_journal(row), bank)
        with self.assertRaisesRegex(PreflightContinuityError, "unmapped bank source"):
            loader._resolve_ap_bank_journal({**row, "bank_source": ""})
        wrong = MockRecord(id=2, company_id=1, type="bank", code="BNK1",
                           default_account_id=MockRecord(id=9, code="101402"))
        for candidates in ([], [bank, bank], [wrong]):
            loader.env = MockEnv({"account.journal": MockModel(records=candidates)})
            with self.assertRaisesRegex(PreflightContinuityError, "expected one company bank journal"):
                loader._resolve_ap_bank_journal(row)

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
        mock_journal_bank = MockRecord(
            id=5, company_id=1, type="bank", code="BNK1", default_account_id=MockRecord(id=90, code="101401"),
        )
        mock_journal_misc = MockRecord(id=6, company_id=1, type="general", code="MISC")

        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "product.product": MockModel(auto_match=True),
            "res.partner": MockModel(records=[mock_partner_unilever], auto_match=True),
            "account.move": MockModel(records=[mock_july_bill]),
            "account.journal": MockModel(records=[mock_journal_bank, mock_journal_misc]),
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

    def test_opex_and_cash_account_auto_provisioning_in_disposable_db(self):
        """Account 111100 and OPEX expense accounts (610100..610700) must auto-provision if absent."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        # Empty account.account model (disposable baseline before provisioning)
        acc_model = MockModel(records=[])
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "account.account": acc_model,
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, strict=True)
        loader.company = mock_company

        # 1. Resolve 111100 with no pre-existing account and no explicit fallback_type passed
        acc_111100 = loader._resolve_account("111100")
        self.assertIsNotNone(acc_111100)
        self.assertEqual(acc_111100.code, "111100")
        self.assertEqual(acc_111100.account_type, "asset_cash")

        # 2. Resolve OPEX account with no pre-existing account and no explicit fallback_type passed
        acc_610100 = loader._resolve_account("610100")
        self.assertIsNotNone(acc_610100)
        self.assertEqual(acc_610100.code, "610100")
        self.assertEqual(acc_610100.account_type, "expense")

        # 3. Bootstrap configuration creates all accounts
        loader._ensure_accounting_and_stock_configuration()
        created_codes = {a.code for a in acc_model._records}
        self.assertIn("111100", created_codes)
        for expected_opex_code in ["610100", "610200", "610300", "610400", "610500", "610600", "610700"]:
            self.assertIn(expected_opex_code, created_codes)

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

    def test_ap_payment_settlement_fails_when_unilever_bill_residual_mismatch(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        mock_partner_unilever = MockRecord(id=50, name="PT Unilever Indonesia", ref="PRIN-002")
        mock_tampered_bill = MockRecord(
            id=201,
            company_id=1,
            name="BILL/2026/07/0001",
            move_type="in_invoice",
            state="posted",
            payment_state="not_paid",
            amount_total=2899971200.00,
            amount_residual=500.00,  # Tampered residual
            ref="PO-2026-06-05",
            partner_id=mock_partner_unilever,
        )
        mock_journal_bank = MockRecord(
            id=5, company_id=1, type="bank", code="BNK1", default_account_id=MockRecord(id=90, code="101401"),
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "product.product": MockModel(auto_match=True),
            "res.partner": MockModel(records=[mock_partner_unilever], auto_match=True),
            "account.move": MockModel(records=[mock_tampered_bill]),
            "account.journal": MockModel(records=[mock_journal_bank]),
            "account.payment": MockModel(),
            "account.account": MockModel(auto_match=True),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=False, strict=True, company_id=1)
        loader.company = mock_company
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader._apply_ap_payments()
        self.assertIn("does not match expected payment amount", str(ctx.exception))

    def test_scenario_b_fails_if_database_not_empty(self):
        mock_cr = MockRecord(dbname="test_disposable")
        mock_models = {
            "res.company": MockModel(records=[MockRecord(id=1, name="PT Salva Inti Mandiri")]),
            "sale.order": MockModel(count_val=10),  # Not empty!
            "account.move": MockModel(count_val=20),
        }
        env = MockEnv(mock_models)
        env.cr = mock_cr
        with self.assertRaises(PreflightContinuityError) as ctx:
            from scripts.ops.verify_disposable_period_pack import run_scenario_b_from_empty_database
            run_scenario_b_from_empty_database(env=env, pack_dir=AUG_PACK_DIR)
        self.assertIn("requires an empty disposable database", str(ctx.exception))

    def test_scenario_b_bootstraps_july_with_enforced_invoice_cutoff(self):
        """Scenario B July baseline loader must strictly enforce invoice cutoff to prevent uncompleted delivery moves.
        """
        mock_cr = MockRecord(dbname="test_disposable_b")
        mock_models = {
            "res.company": MockModel(records=[MockRecord(id=1, name="PT Salva Inti Mandiri")]),
            "sale.order": MockModel(count_val=0),
            "account.move": MockModel(count_val=0),
        }
        env = MockEnv(mock_models)
        env.cr = mock_cr
        from unittest.mock import patch
        from scripts.ops.verify_disposable_period_pack import run_scenario_b_from_empty_database

        captured_kwargs = {}

        class DummyAdapter:
            def __init__(self, *args, **kwargs):
                captured_kwargs.update(kwargs)

            def run_all(self):
                pass

        mock_audit = {"status": "PASS", "violations": []}
        mock_snap = {"digest": "abc"}
        with patch("scripts.load_canonical_perpetual.CanonicalPerpetualAdapter", DummyAdapter), \
             patch.object(GenericPeriodPackLoader, "execute_apply", return_value={}), \
             patch("scripts.ops.verify_disposable_period_pack.audit_period_database", return_value=mock_audit), \
             patch("scripts.ops.verify_disposable_period_pack.capture_period_state_snapshot", return_value=mock_snap):
            res = run_scenario_b_from_empty_database(env=env, pack_dir=AUG_PACK_DIR)

        self.assertEqual(captured_kwargs.get("cutoff_date"), "2026-07-31")
        self.assertTrue(captured_kwargs.get("enforce_invoice_cutoff"))
        self.assertEqual(res.get("july_status"), "LOADED_SUCCESSFULLY")

    def test_deep_idempotency_opex_drift_detected(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        mock_acc_610100 = MockRecord(id=11, code="610100", name="Beban Logistik")
        mock_acc_wrong = MockRecord(id=99, code="619900", name="Beban Lain-lain")
        mock_acc_contra = MockRecord(id=21, code="111100", name="Kas Operasional")
        # Existing OPEX entry with wrong debit account
        existing_opex = MockRecord(
            id=301,
            company_id=1,
            move_type="entry",
            date="2026-08-01",
            ref="BBM Solar 6 Armada, Tol & Retribusi Pengiriman 2026-08-01",
            state="posted",
            line_ids=[
                MockRecord(id=1, account_id=mock_acc_wrong, debit=3200000.00, credit=0.0),
                MockRecord(id=2, account_id=mock_acc_contra, debit=0.0, credit=3200000.00),
            ],
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "product.product": MockModel(auto_match=True),
            "account.move": MockModel(records=[existing_opex]),
            "sale.order": MockModel(),
            "purchase.order": MockModel(),
            "account.payment": MockModel(),
            "account.account": MockModel(records=[mock_acc_610100, mock_acc_wrong, mock_acc_contra], auto_match=True),
            "account.journal": MockModel(records=[MockRecord(id=1, code="MISC", type="general", company_id=1)]),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, strict=True)
        loader.company = mock_company
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader.evaluate_dry_run()
        self.assertIn("debit account mismatch", str(ctx.exception))

    def test_ap_payment_rejects_decoy_bill(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        mock_partner_unilever = MockRecord(id=50, name="PT Unilever Enterprise Indonesia", ref="PRIN-002")
        decoy_bill = MockRecord(
            id=201,
            company_id=1,
            name="BILL/2026/07/0001",
            move_type="in_invoice",
            state="posted",
            payment_state="not_paid",
            amount_total=2899971200.00,
            amount_residual=2899971200.00,
            ref="PO-2026-06-050",  # Decoy! Should NOT match PO-2026-06-05
            partner_id=mock_partner_unilever,
        )
        mock_journal_bank = MockRecord(
            id=5, company_id=1, type="bank", code="BNK1", default_account_id=MockRecord(id=90, code="101401"),
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "product.product": MockModel(auto_match=True),
            "res.partner": MockModel(records=[mock_partner_unilever]),
            "account.move": MockModel(records=[decoy_bill]),
            "account.journal": MockModel(records=[mock_journal_bank]),
            "account.payment": MockModel(),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=False, strict=True, company_id=1)
        loader.company = mock_company
        with self.assertRaises(PreflightContinuityError) as ctx:
            loader._apply_ap_payments()
        self.assertIn("not found for AP payment", str(ctx.exception))

    def test_ap_payment_rejects_ambiguous_duplicate_bills(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        mock_partner_unilever = MockRecord(id=50, name="PT Unilever Enterprise Indonesia", ref="PRIN-002")
        bill_1 = MockRecord(
            id=201,
            company_id=1,
            name="BILL/2026/07/0001",
            move_type="in_invoice",
            state="posted",
            amount_residual=2899971200.00,
            ref="PO-2026-06-05",
            partner_id=mock_partner_unilever,
        )
        bill_2 = MockRecord(
            id=202,
            company_id=1,
            name="BILL/2026/07/0002",
            move_type="in_invoice",
            state="posted",
            amount_residual=2899971200.00,
            ref="PO-2026-06-05",
            partner_id=mock_partner_unilever,
        )
        mock_journal_bank = MockRecord(
            id=5, company_id=1, type="bank", code="BNK1", default_account_id=MockRecord(id=90, code="101401"),
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "res.partner": MockModel(records=[mock_partner_unilever]),
            "account.move": MockModel(records=[bill_1, bill_2]),
            "account.journal": MockModel(records=[mock_journal_bank]),
            "account.payment": MockModel(),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=False, strict=True, company_id=1)
        loader.company = mock_company
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader._apply_ap_payments()
        self.assertIn("Ambiguous posted vendor bills", str(ctx.exception))

    def test_preflight_replay_with_settled_paid_bill_passes_if_payment_exists(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_partner_unilever = MockRecord(id=50, name="PT Unilever Enterprise Indonesia", ref="PRIN-002")
        paid_bill = MockRecord(
            id=201,
            company_id=1,
            name="BILL/2026/07/0001",
            move_type="in_invoice",
            state="posted",
            payment_state="paid",
            amount_total=2899971200.00,
            amount_residual=0.00,
            ref="PO-2026-06-05",
            partner_id=mock_partner_unilever,
        )
        matching_payment = MockRecord(
            id=901,
            company_id=1,
            ref="AP-202608-0001",
            payment_type="outbound",
            state="posted",
            amount=2899971200.00,
            reconciled_bill_ids=[paid_bill],
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "stock.location": MockModel(records=[MockRecord(id=1, company_id=1, usage="internal")]),
            "res.partner": MockModel(records=[mock_partner_unilever], count_val=400),
            "product.product": MockModel(count_val=200),
            "sale.order": MockModel(count_val=1200),
            "account.move": MockModel(records=[paid_bill]),
            "account.payment": MockModel(records=[matching_payment]),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, strict=True, company_id=1)
        loader.company = mock_company
        # Should not raise PreflightContinuityError because replay with verified payment is valid
        loader.verify_preflight()

    def test_preflight_replay_with_settled_paid_bill_fails_if_payment_missing(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_partner_unilever = MockRecord(id=50, name="PT Unilever Enterprise Indonesia", ref="PRIN-002")
        paid_bill = MockRecord(
            id=201,
            company_id=1,
            name="BILL/2026/07/0001",
            move_type="in_invoice",
            state="posted",
            payment_state="paid",
            amount_total=2899971200.00,
            amount_residual=0.00,
            ref="PO-2026-06-05",
            partner_id=mock_partner_unilever,
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "stock.location": MockModel(records=[MockRecord(id=1, company_id=1, usage="internal")]),
            "res.partner": MockModel(records=[mock_partner_unilever], count_val=400),
            "product.product": MockModel(count_val=200),
            "sale.order": MockModel(count_val=1200),
            "account.move": MockModel(records=[paid_bill]),
            "account.payment": MockModel(records=[]),  # No payment!
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, strict=True, company_id=1)
        loader.company = mock_company
        with self.assertRaises(PreflightContinuityError) as ctx:
            loader.verify_preflight()
        self.assertIn("matching reconciled August AP payment", str(ctx.exception))

    def test_ar_payment_validator_rejects_wrong_partner(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        mock_cust_correct = MockRecord(id=10, name="Toko ABC", ref="CUST-0001")
        mock_cust_wrong = MockRecord(id=20, name="Toko XYZ", ref="CUST-9999")
        inv = MockRecord(
            id=101,
            company_id=1,
            payment_reference="INV-202608-0001",
            partner_id=mock_cust_correct,
            line_ids=[],
        )
        existing_pay = MockRecord(
            id=401,
            company_id=1,
            ref="PAY-AR-202608-0001",
            partner_id=mock_cust_wrong,  # Wrong partner!
            date="2026-08-05",
            amount=500000.00,
            state="posted",
            payment_type="inbound",
            journal_id=MockRecord(type="bank"),
            is_reconciled=True,
            reconciled_invoice_ids=[inv],
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "account.move": MockModel(records=[inv]),
            "res.partner": MockModel(records=[mock_cust_correct, mock_cust_wrong]),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, strict=True, company_id=1)
        loader.company = mock_company
        ar_row = {
            "payment_id": "PAY-AR-202608-0001",
            "invoice_number": "INV-202608-0001",
            "customer": "CUST-0001",
            "payment_date": "2026-08-05",
            "net_cash_collected_total": "500000.00",
        }
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader._validate_existing_ar_payment(existing_pay, ar_row)
        self.assertIn("partner mismatch", str(ctx.exception))

    def test_scenario_b_requires_separate_db_in_all_scenario(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_cr = MockRecord(dbname="test_disposable")
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "sale.order": MockModel(records=[]),
            "account.move": MockModel(records=[]),
        }
        env = MockEnv(mock_models)
        env.cr = mock_cr
        from unittest.mock import patch
        from scripts.ops.verify_disposable_period_pack import run_full_disposable_period_verification

        with patch.object(GenericPeriodPackLoader, "execute_apply", return_value={}):
            report = run_full_disposable_period_verification(
                env=env, pack_dir=AUG_PACK_DIR, scenario="all", env_b=None
            )
        self.assertEqual(
            report["scenario_b_continuation"]["status"], "FAIL_SEPARATE_DB_REQUIRED"
        )

    def test_audit_fails_when_mandatory_gl_account_missing(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_cr = MockRecord(dbname="test_disposable")
        # Missing accounts 113000, 211200, 114100
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "sale.order": MockModel(records=[]),
            "account.move": MockModel(records=[]),
            "purchase.order": MockModel(records=[]),
            "account.payment": MockModel(records=[]),
            "stock.picking": MockModel(records=[]),
            "stock.move": MockModel(records=[]),
            "stock.quant": MockModel(records=[]),
            "account.move.line": MockModel(records=[]),
            "account.account": MockModel(records=[
                MockRecord(id=1, code="112000", name="AR", company_id=1),
                MockRecord(id=2, code="211000", name="AP", company_id=1),
            ]),
        }
        env = MockEnv(mock_models)
        env.cr = mock_cr
        oracle = PeriodPackOracle(AUG_PACK_DIR)
        report = audit_period_database(env, oracle)
        self.assertEqual(report["status"], "FAIL")
        missing_violations = [v for v in report["violations"] if "Mandatory GL account" in v]
        self.assertGreaterEqual(len(missing_violations), 3)

    def test_audit_fails_on_tax_code_04_calculation_mismatch(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_cr = MockRecord(dbname="test_disposable")
        # Invoices with invalid tax calculation (PPN 20% instead of 11% effective / 12% on 11/12)
        corrupt_inv = MockRecord(
            id=101,
            company_id=1,
            name="INV/2026/08/0001",
            payment_reference="INV-202608-0001",
            move_type="out_invoice",
            state="posted",
            is_fmcg_seed_invoice=True,
            amount_untaxed=100000.00,
            amount_tax=20000.00,  # 20% instead of 11% / 11000
            amount_total=120000.00,
            line_ids=[
                MockRecord(id=1, account_id=MockRecord(code="211200"), credit=20000.00, debit=0.0)
            ],
        )
        mock_acc_ppn_out = MockRecord(id=10, code="211200", name="PPN Keluaran", company_id=1)
        mock_acc_ppn_in = MockRecord(id=11, code="114100", name="PPN Masukan", company_id=1)
        mock_acc_stock = MockRecord(id=12, code="113000", name="Stock", company_id=1)
        mock_acc_ar = MockRecord(id=13, code="112000", name="AR", company_id=1)
        mock_acc_ap = MockRecord(id=14, code="211000", name="AP", company_id=1)
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "sale.order": MockModel(records=[]),
            "account.move": MockModel(records=[corrupt_inv]),
            "purchase.order": MockModel(records=[]),
            "account.payment": MockModel(records=[]),
            "stock.picking": MockModel(records=[]),
            "stock.move": MockModel(records=[]),
            "stock.quant": MockModel(records=[]),
            "account.move.line": MockModel(records=[]),
            "account.account": MockModel(records=[
                mock_acc_ppn_out, mock_acc_ppn_in, mock_acc_stock, mock_acc_ar, mock_acc_ap
            ]),
        }
        env = MockEnv(mock_models)
        env.cr = mock_cr
        oracle = PeriodPackOracle(AUG_PACK_DIR)
        report = audit_period_database(env, oracle)
        self.assertEqual(report["status"], "FAIL")
        tax_violations = [v for v in report["violations"] if "Tax Code 04" in v or "Effective tax rate mismatch" in v]
        self.assertGreaterEqual(len(tax_violations), 1)

    def test_output_tax_gl_uses_posting_period_not_all_pack_invoices(self):
        from scripts.ops.verify_disposable_period_pack import PeriodPackOracle

        oracle = PeriodPackOracle(AUG_PACK_DIR)
        self.assertEqual(oracle.expected_period_output_tax, Decimal("426858171.17"))
        self.assertEqual(oracle.expected_inv_ppn, Decimal("446229567.06"))

    def test_input_tax_gl_excludes_september_receipt_from_august_cutoff(self):
        from scripts.ops.verify_disposable_period_pack import PeriodPackOracle

        oracle = PeriodPackOracle(AUG_PACK_DIR)
        self.assertEqual(oracle.expected_period_input_tax, Decimal("720627600.00"))
        self.assertEqual(oracle.expected_po_input_tax, Decimal("782852400.00"))

    def test_so_replay_with_real_csv_schema_cartons_and_price(self):
        """Supervisor Counterexample 1: Verify SO line qty matches qty_cartons * carton_qty and price."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        cust = MockRecord(id=10, ref="CUST-001", name="Toko ABC")
        sku_prod = MockRecord(id=20, default_code="SKU-FD-001", name="Food 1")
        so_row = {
            "so_number": "SO-202608-0001",
            "customer": "CUST-001",
            "net_dpp": "150000.00",
        }
        order_lines = [
            {
                "sku_code": "SKU-FD-001",
                "qty_cartons": "2",
                "carton_qty": "10",  # Total expected qty = 20
                "unit_price_dpp": "7500.00",
                "discount_pct": "0.0",
            }
        ]
        # Matching SO: 20 pcs @ 7500 = 150,000
        matching_so = MockRecord(
            id=100,
            amount_untaxed=150000.00,
            partner_id=cust,
            order_line=[
                MockRecord(
                    id=1,
                    product_id=sku_prod,
                    product_uom_qty=20.0,
                    price_unit=7500.00,
                    discount=0.0,
                )
            ],
        )
        loader = GenericPeriodPackLoader(env=MockEnv({}), pack_dir=AUG_PACK_DIR, dry_run=True)
        loader.company = mock_company
        # Must pass with zero drift
        loader._validate_existing_so(matching_so, so_row, order_lines)

        # Mutate price (e.g. 8000 instead of 7500) -> MUST FAIL
        drifted_price_so = MockRecord(
            id=100,
            amount_untaxed=150000.00,
            partner_id=cust,
            order_line=[
                MockRecord(
                    id=1,
                    product_id=sku_prod,
                    product_uom_qty=20.0,
                    price_unit=8000.00,
                    discount=0.0,
                )
            ],
        )
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader._validate_existing_so(drifted_price_so, so_row, order_lines)
        self.assertIn("price mismatch", str(ctx.exception))

    def test_po_validator_catches_price_drift_via_unit_cost_price(self):
        """Supervisor Counterexample 2: Verify PO line price 999 vs 7500 is rejected via unit_cost_price."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        vendor = MockRecord(id=30, ref="PRIN-001", name="Principal A")
        sku_prod = MockRecord(id=20, default_code="SKU-FD-001", name="Food 1")
        po_row = {
            "po_number": "PO-2026-08-01",
            "principal_code": "PRIN-001",
            "dpp_total": "75000.00",
        }
        po_lines = [
            {
                "sku_code": "SKU-FD-001",
                "qty_cartons": "1",
                "carton_qty": "10",
                "unit_cost_price": "7500.00",  # CSV schema column
            }
        ]
        # Drifted PO line with price 999.00 instead of 7500.00
        drifted_po = MockRecord(
            id=200,
            amount_untaxed=75000.00,
            partner_id=vendor,
            order_line=[
                MockRecord(
                    id=1,
                    product_id=sku_prod,
                    product_qty=10.0,
                    price_unit=999.00,  # Wrong price!
                )
            ],
        )
        loader = GenericPeriodPackLoader(env=MockEnv({}), pack_dir=AUG_PACK_DIR, dry_run=True)
        loader.company = mock_company
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader._validate_existing_po(drifted_po, po_row, po_lines)
        self.assertIn("price mismatch", str(ctx.exception))

    def test_ap_payment_validator_rejects_empty_reconciled_bill_edge(self):
        """Supervisor Counterexample 3: Payment marked is_reconciled=True but reconciled_bill_ids is empty."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        vendor = MockRecord(id=50, ref="PRIN-002", name="PT Unilever Enterprise Indonesia")
        bill = MockRecord(
            id=301,
            name="BILL/2026/07/0001",
            move_type="in_invoice",
            state="posted",
            payment_state="paid",
            amount_residual=0.0,
            partner_id=vendor,
        )
        # Payment claims is_reconciled=True, but has empty reconciled_bill_ids and no move line partial edges
        fake_reconciled_pay = MockRecord(
            id=401,
            company_id=1,
            ref="AP-202608-0001",
            partner_id=vendor,
            state="posted",
            amount=2899971200.00,
            is_reconciled=True,
            reconciled_bill_ids=[],  # Empty!
            move_id=MockRecord(line_ids=[]),
        )
        loader = GenericPeriodPackLoader(env=MockEnv({}), pack_dir=AUG_PACK_DIR, dry_run=True)
        loader.company = mock_company
        ap_row = {"ap_payment_id": "AP-202608-0001", "amount_paid_dpp": "2899971200.00"}
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader._validate_existing_ap_payment(fake_reconciled_pay, ap_row, bill)
        self.assertIn("not reconciled to target July Unilever bill", str(ctx.exception))

    def test_ar_payment_validator_rejects_empty_reconciled_inv_edge(self):
        """Supervisor Counterexample 4: Payment marked is_reconciled=True but reconciled_invoice_ids is empty."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        cust = MockRecord(id=60, ref="CUST-001", name="Toko X")
        target_inv = MockRecord(
            id=501,
            company_id=1,
            payment_reference="INV-202608-0001",
            partner_id=cust,
            state="posted",
        )
        # Payment claims is_reconciled=True, but reconciled_invoice_ids is empty
        fake_reconciled_ar_pay = MockRecord(
            id=601,
            company_id=1,
            ref="PAY-AR-202608-0001",
            partner_id=cust,
            date="2026-08-05",
            state="posted",
            amount=500000.00,
            is_reconciled=True,
            reconciled_invoice_ids=[],  # Empty!
            move_id=MockRecord(line_ids=[]),
        )
        mock_models = {
            "account.move": MockModel(records=[target_inv]),
            "res.partner": MockModel(records=[cust]),
        }
        loader = GenericPeriodPackLoader(env=MockEnv(mock_models), pack_dir=AUG_PACK_DIR, dry_run=True)
        loader.company = mock_company
        ar_row = {
            "payment_id": "PAY-AR-202608-0001",
            "invoice_number": "INV-202608-0001",
            "customer": "CUST-001",
            "payment_date": "2026-08-05",
            "net_cash_collected_total": "500000.00",
        }
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader._validate_existing_ar_payment(fake_reconciled_ar_pay, ar_row)
        self.assertIn("not reconciled to target invoice", str(ctx.exception))

    def test_ar_payment_validator_accepts_paid_state_in_native_odoo19(self):
        """Native Odoo 19 transitions reconciled account.payment to 'paid' (or 'in_process'). Replay must accept it."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        cust = MockRecord(id=60, ref="CUST-001", name="Toko X")
        target_inv = MockRecord(
            id=501,
            company_id=1,
            payment_reference="INV-202608-0001",
            partner_id=cust,
            state="posted",
        )
        valid_reconciled_ar_pay = MockRecord(
            id=601,
            company_id=1,
            ref="PAY-AR-202608-0001",
            partner_id=cust,
            journal_id=MockRecord(type="bank"),
            date="2026-08-05",
            payment_type="inbound",
            state="paid",  # Native Odoo 19 reconciled payment state
            amount=500000.00,
            is_reconciled=True,
            reconciled_invoice_ids=[target_inv],
            move_id=MockRecord(line_ids=[]),
        )
        mock_models = {
            "account.move": MockModel(records=[target_inv]),
            "res.partner": MockModel(records=[cust]),
        }
        loader = GenericPeriodPackLoader(env=MockEnv(mock_models), pack_dir=AUG_PACK_DIR, dry_run=True)
        loader.company = mock_company
        ar_row = {
            "payment_id": "PAY-AR-202608-0001",
            "invoice_number": "INV-202608-0001",
            "customer": "CUST-001",
            "payment_date": "2026-08-05",
            "net_cash_collected_total": "500000.00",
        }
        # Must validate without error
        loader._validate_existing_ar_payment(valid_reconciled_ar_pay, ar_row)

        # Draft payment must fail closed
        valid_reconciled_ar_pay.state = "draft"
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader._validate_existing_ar_payment(valid_reconciled_ar_pay, ar_row)
        self.assertIn("state is 'draft'", str(ctx.exception))

    def test_opex_validator_rejects_journal_mismatch(self):
        """Supervisor Counterexample 5: OPEX move posted in wrong journal (BNK1 vs MISC)."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        journal_bank = MockRecord(id=2, code="BNK1", name="Bank Journal")
        drifted_opex = MockRecord(
            id=701,
            state="posted",
            journal_id=journal_bank,
            line_ids=[
                MockRecord(id=1, account_id=MockRecord(code="610100"), debit=500000.00, credit=0.0),
                MockRecord(id=2, account_id=MockRecord(code="111100"), debit=0.0, credit=500000.00),
            ],
        )
        loader = GenericPeriodPackLoader(env=MockEnv({}), pack_dir=AUG_PACK_DIR, dry_run=True)
        loader.company = mock_company
        op_row = {"description": "Biaya Listrik", "amount": "500000.00"}
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader._validate_existing_opex(
                drifted_opex, op_row, target_code="610100", credit_acc_code="111100", exp_journal_code="MISC"
            )
        self.assertIn("journal mismatch BNK1 vs expected MISC", str(ctx.exception))

    def test_snapshot_normalization_business_keys_deterministic(self):
        """Supervisor Counterexample 6: Snapshots across two databases with different surrogate IDs
        must yield identical digests.
        """
        from scripts.ops.verify_disposable_period_pack import capture_period_state_snapshot

        # DB 1: Move Lines with IDs 101 and 102
        ml1_db1 = MockRecord(
            id=101,
            move_id=MockRecord(name="INV/2026/08/0001", ref="INV-202608-0001"),
            account_id=MockRecord(code="112000"),
            partner_id=MockRecord(ref="CUST-001"),
            date="2026-08-05",
            debit=100000.00,
            credit=0.0,
            reconciled=True,
            parent_state="posted",
        )
        ml2_db1 = MockRecord(
            id=102,
            move_id=MockRecord(name="PAY/2026/08/0001", ref="PAY-AR-202608-0001"),
            account_id=MockRecord(code="112000"),
            partner_id=MockRecord(ref="CUST-001"),
            date="2026-08-05",
            debit=0.0,
            credit=100000.00,
            reconciled=True,
            parent_state="posted",
        )
        pr_db1 = MockRecord(
            id=1,
            debit_move_id=ml1_db1,
            credit_move_id=ml2_db1,
            amount=100000.00,
        )
        pay_db1 = MockRecord(
            id=1,
            memo="PAY-AR-202608-0001",
            partner_id=MockRecord(ref="CUST-001"),
            journal_id=MockRecord(code="BNK1"),
            date="2026-08-05",
            amount=100000.00,
            payment_type="inbound",
            state="paid",
        )
        env1 = MockEnv({
            "purchase.order": MockModel(),
            "sale.order": MockModel(),
            "account.move": MockModel(),
            "account.payment": MockModel(records=[pay_db1]),
            "stock.move": MockModel(),
            "stock.move.line": MockModel(),
            "stock.quant": MockModel(),
            "account.move.line": MockModel(records=[ml1_db1, ml2_db1]),
            "account.partial.reconcile": MockModel(records=[pr_db1]),
        })

        # DB 2: Identical business data, completely different surrogate primary keys (IDs 888 and 999)
        ml1_db2 = MockRecord(
            id=888,
            move_id=MockRecord(name="INV/2026/08/0001", ref="INV-202608-0001"),
            account_id=MockRecord(code="112000"),
            partner_id=MockRecord(ref="CUST-001"),
            date="2026-08-05",
            debit=100000.00,
            credit=0.0,
            reconciled=True,
            parent_state="posted",
        )
        ml2_db2 = MockRecord(
            id=999,
            move_id=MockRecord(name="PAY/2026/08/0001", ref="PAY-AR-202608-0001"),
            account_id=MockRecord(code="112000"),
            partner_id=MockRecord(ref="CUST-001"),
            date="2026-08-05",
            debit=0.0,
            credit=100000.00,
            reconciled=True,
            parent_state="posted",
        )
        pr_db2 = MockRecord(
            id=777,
            debit_move_id=ml1_db2,
            credit_move_id=ml2_db2,
            amount=100000.00,
        )
        pay_db2 = MockRecord(
            id=999,
            memo="PAY-AR-202608-0001",
            partner_id=MockRecord(ref="CUST-001"),
            journal_id=MockRecord(code="BNK1"),
            date="2026-08-05",
            amount=100000.00,
            payment_type="inbound",
            state="paid",
        )
        env2 = MockEnv({
            "purchase.order": MockModel(),
            "sale.order": MockModel(),
            "account.move": MockModel(),
            "account.payment": MockModel(records=[pay_db2]),
            "stock.move": MockModel(),
            "stock.move.line": MockModel(),
            "stock.quant": MockModel(),
            "account.move.line": MockModel(records=[ml1_db2, ml2_db2]),
            "account.partial.reconcile": MockModel(records=[pr_db2]),
        })

        snap1 = capture_period_state_snapshot(env1)
        snap2 = capture_period_state_snapshot(env2)
        # Digests must be 100% identical because local database surrogate integer IDs were normalized to business keys!
        self.assertEqual(snap1["digest"], snap2["digest"])

    def test_cross_database_snapshot_uses_stock_document_but_preserves_amounts_and_lots(self):
        from scripts.ops.verify_disposable_period_pack import capture_period_state_snapshot

        def snapshot(number, lot="LOT-A", debit=100):
            product = MockRecord(default_code="SKU")
            journal = MockRecord(
                id=1, name=f"STJ/{number}", ref=f"OUT/{number}", move_type="entry", invoice_line_ids=[],
            )
            move = MockRecord(
                id=2, reference=f"OUT/{number}", account_move_id=journal, product_id=product,
                picking_id=MockRecord(
                    sale_id=MockRecord(client_order_ref="SO-202608-0001"),
                    picking_type_id=MockRecord(code="outgoing"),
                ),
            )
            detail = MockRecord(move_id=move, product_id=product, lot_id=MockRecord(name=lot))
            aml = MockRecord(move_id=journal, product_id=product, debit=debit)
            env = MockEnv({
                "purchase.order": MockModel(), "sale.order": MockModel(), "account.payment": MockModel(),
                "account.move": MockModel(records=[journal]), "account.move.line": MockModel(records=[aml]),
                "stock.move": MockModel(records=[move]), "stock.move.line": MockModel(records=[detail]),
                "stock.quant": MockModel(), "account.partial.reconcile": MockModel(),
            })
            return (
                capture_period_state_snapshot(env)["digest"],
                capture_period_state_snapshot(env, cross_database=True)["digest"],
            )

        raw_a, business_a = snapshot("0003")
        raw_b, business_b = snapshot("0004")
        self.assertNotEqual(raw_a, raw_b)
        self.assertEqual(business_a, business_b)
        self.assertNotEqual(business_a, snapshot("0004", lot="LOT-B")[1])
        self.assertNotEqual(business_a, snapshot("0004", debit=200)[1])

    def test_audit_period_database_resolves_native_odoo19_payment_memo(self):
        """Audit oracle resolves AR/AP payments via native Odoo 19 'memo' field without rejecting as invalid field."""
        from scripts.ops.verify_disposable_period_pack import audit_period_database, PeriodPackOracle

        class NativeOdoo19PaymentModel(MockModel):
            _fields = {"memo": True, "amount": True, "date": True, "payment_type": True, "company_id": True}

        oracle = PeriodPackOracle(AUG_PACK_DIR)
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_cr = MockRecord(dbname="test_disposable")

        pay_ar = MockRecord(
            id=10,
            company_id=1,
            memo="PAY-AR-202608-0001",
            payment_type="inbound",
            date="2026-08-10",
            amount=50000.00,
        )
        pay_ap = MockRecord(
            id=20,
            company_id=1,
            memo="PAY-AP-202608-0001",
            payment_type="outbound",
            date="2026-08-10",
            amount=100000.00,
        )

        env = MockEnv({
            "account.payment": NativeOdoo19PaymentModel(records=[pay_ar, pay_ap]),
            "account.move": MockModel(records=[]),
            "purchase.order": MockModel(records=[]),
            "sale.order": MockModel(records=[]),
            "stock.picking": MockModel(records=[]),
            "stock.move": MockModel(records=[]),
            "stock.quant": MockModel(records=[]),
            "account.move.line": MockModel(records=[]),
            "account.account": MockModel(records=[
                MockRecord(id=10, code="211200", company_id=1),
                MockRecord(id=11, code="114100", company_id=1),
                MockRecord(id=12, code="113000", company_id=1),
                MockRecord(id=13, code="112000", company_id=1),
                MockRecord(id=14, code="211000", company_id=1),
            ]),
        })
        env.company = mock_company
        env.cr = mock_cr

        report = audit_period_database(env, oracle)
        self.assertEqual(report["checks"]["ar_collections_count"]["actual"], 1)
        self.assertEqual(report["checks"]["ap_payments_count"]["actual"], 1)

    def test_audit_fails_when_tax_base_matches_commercial_dpp_legacy(self):
        """Supervisor Counterexample 7: Tax Code 04 invoice has tax_base_amount equal to commercial DPP
        (legacy fail-open).
        """
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_cr = MockRecord(dbname="test_disposable")
        # Commercial DPP = 100,000; DPP Nilai Lain should be 91,666.67; PPN = 11,000.00
        # If line has tax_base_amount = 100,000.00 (legacy 11% tax base), audit must flag TAX-SOURCE violation
        legacy_inv = MockRecord(
            id=101,
            company_id=1,
            payment_reference="INV-202608-0001",
            move_type="out_invoice",
            state="posted",
            is_fmcg_seed_invoice=True,
            amount_untaxed=100000.00,
            amount_tax=11000.00,
            amount_total=111000.00,
            line_ids=[
                MockRecord(
                    id=1,
                    account_id=MockRecord(code="211200"),
                    credit=11000.00,
                    debit=0.0,
                    tax_base_amount=100000.00,  # Matches commercial DPP instead of 11/12 (91666.67)!
                )
            ],
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "sale.order": MockModel(),
            "account.move": MockModel(records=[legacy_inv]),
            "purchase.order": MockModel(),
            "account.payment": MockModel(),
            "stock.picking": MockModel(),
            "stock.move": MockModel(),
            "stock.quant": MockModel(),
            "account.move.line": MockModel(),
            "account.account": MockModel(records=[
                MockRecord(id=10, code="211200", company_id=1),
                MockRecord(id=11, code="114100", company_id=1),
                MockRecord(id=12, code="113000", company_id=1),
                MockRecord(id=13, code="112000", company_id=1),
                MockRecord(id=14, code="211000", company_id=1),
            ]),
        }
        env = MockEnv(mock_models)
        env.cr = mock_cr
        oracle = PeriodPackOracle(AUG_PACK_DIR)
        report = audit_period_database(env, oracle)
        self.assertEqual(report["status"], "FAIL")
        tax_fail_open_violations = [v for v in report["violations"] if "TAX-SOURCE fail-open" in v]
        self.assertGreaterEqual(len(tax_fail_open_violations), 1)

    def test_reader_persistent_overrides_across_property_accesses(self):
        """Supervisor Counterexample 8: Reader overrides persist across property access."""
        from scripts.ops.load_period_pack import PeriodPackReader
        reader = PeriodPackReader(AUG_PACK_DIR)
        corrupt_row = [{"so_number": "SO-PROBE-01", "net_dpp": "123.00"}]
        reader.set_override("sales_orders.csv", corrupt_row)
        # Property accessed 1st time
        res1 = reader.sales_orders
        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0]["so_number"], "SO-PROBE-01")
        # Property accessed 2nd time (must NOT reload disk)
        res2 = reader.sales_orders
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0]["so_number"], "SO-PROBE-01")
        # Clear override
        reader.clear_overrides()
        res3 = reader.sales_orders
        self.assertEqual(len(res3), 1240)

    def test_audit_fails_when_tax_base_is_zero_or_missing(self):
        """Supervisor Review #5843536397 Blocker 2: Tax Code 04 invoice has tax_base_amount=0 or missing.
        Must be rejected as TAX-SOURCE fail-open violation.
        """
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_cr = MockRecord(dbname="test_disposable")
        # Taxable invoice with amount_untaxed=100,000, PPN=11,000, but tax_base_amount = 0 (fail-open bypass)
        zero_tb_inv = MockRecord(
            id=101,
            company_id=1,
            payment_reference="INV-202608-0001",
            move_type="out_invoice",
            state="posted",
            is_fmcg_seed_invoice=True,
            amount_untaxed=100000.00,
            amount_tax=11000.00,
            amount_total=111000.00,
            line_ids=[
                MockRecord(
                    id=1,
                    account_id=MockRecord(code="211200"),
                    credit=11000.00,
                    debit=0.0,
                    tax_base_amount=0.0,  # Zero base amount!
                )
            ],
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "sale.order": MockModel(),
            "account.move": MockModel(records=[zero_tb_inv]),
            "purchase.order": MockModel(),
            "account.payment": MockModel(),
            "stock.picking": MockModel(),
            "stock.move": MockModel(),
            "stock.quant": MockModel(),
            "account.move.line": MockModel(),
            "account.account": MockModel(records=[
                MockRecord(id=10, code="211200", company_id=1),
                MockRecord(id=11, code="114100", company_id=1),
                MockRecord(id=12, code="113000", company_id=1),
                MockRecord(id=13, code="112000", company_id=1),
                MockRecord(id=14, code="211000", company_id=1),
            ]),
        }
        env = MockEnv(mock_models)
        env.cr = mock_cr
        oracle = PeriodPackOracle(AUG_PACK_DIR)
        report = audit_period_database(env, oracle)
        self.assertEqual(report["status"], "FAIL")
        zero_tb_violations = [
            v for v in report["violations"]
            if "TAX-SOURCE fail-open" in v and "tax_base_amount is zero or missing" in v
        ]
        self.assertGreaterEqual(len(zero_tb_violations), 1)

    def test_audit_fails_on_closing_stock_lot_and_valuation_mismatches(self):
        """Supervisor Review #5843536397 Blocker 1: Audit fails when closing stock, lots, or valuation mismatch."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_cr = MockRecord(dbname="test_disposable")
        # Internal quant with wrong quantity (e.g. 5 pcs instead of expected carton conversion)
        corrupt_quant = MockRecord(
            id=1,
            company_id=1,
            location_id=MockRecord(usage="internal"),
            product_id=MockRecord(default_code="KPA-ABC-01", standard_price=1000.00),
            lot_id=MockRecord(name="LOT-TOS-20260701-13"),
            quantity=5.0,  # Far below expected physical pieces
            reserved_quantity=0.0,
        )
        mock_acc_stock = MockRecord(id=12, code="113000", company_id=1)
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "sale.order": MockModel(),
            "account.move": MockModel(),
            "purchase.order": MockModel(),
            "account.payment": MockModel(),
            "stock.picking": MockModel(),
            "stock.move": MockModel(),
            "stock.quant": MockModel(records=[corrupt_quant]),
            "account.move.line": MockModel(records=[
                MockRecord(
                    id=1,
                    company_id=1,
                    account_id=mock_acc_stock,
                    parent_state="posted",
                    date="2026-08-31",
                    debit=5000.00,
                    credit=0.0,
                )
            ]),
            "account.account": MockModel(records=[
                MockRecord(id=10, code="211200", company_id=1),
                MockRecord(id=11, code="114100", company_id=1),
                mock_acc_stock,
                MockRecord(id=13, code="112000", company_id=1),
                MockRecord(id=14, code="211000", company_id=1),
            ]),
        }
        env = MockEnv(mock_models)
        env.cr = mock_cr
        oracle = PeriodPackOracle(AUG_PACK_DIR)
        report = audit_period_database(env, oracle)
        self.assertEqual(report["status"], "FAIL")
        # Must catch SKU quantity mismatch, lot physical mismatch, and total physical cartons mismatch
        quant_violations = [
            v for v in report["violations"]
            if "Closing stock quantity mismatch" in v or "Closing lot" in v
        ]
        self.assertGreaterEqual(len(quant_violations), 1)

    def test_audit_fails_when_expected_closing_lots_are_missing_in_database(self):
        """Supervisor Review #5851374243 Finding 1: Audit must FAIL when expected lots are missing in DB.
        Previously, empty actual_lot_physical resulted in 0 violations because loop only checked 'if key in actual'.
        """
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_cr = MockRecord(dbname="test_disposable")
        mock_acc_stock = MockRecord(id=12, code="113000", company_id=1)
        # Completely empty quants: all 213 expected lots are missing!
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "sale.order": MockModel(),
            "account.move": MockModel(),
            "purchase.order": MockModel(),
            "account.payment": MockModel(),
            "stock.picking": MockModel(),
            "stock.move": MockModel(),
            "stock.quant": MockModel(records=[]),  # Empty quants
            "account.move.line": MockModel(),
            "account.account": MockModel(records=[
                MockRecord(id=10, code="211200", company_id=1),
                MockRecord(id=11, code="114100", company_id=1),
                mock_acc_stock,
                MockRecord(id=13, code="112000", company_id=1),
                MockRecord(id=14, code="211000", company_id=1),
            ]),
        }
        env = MockEnv(mock_models)
        env.cr = mock_cr
        oracle = PeriodPackOracle(AUG_PACK_DIR)
        report = audit_period_database(env, oracle)
        self.assertEqual(report["status"], "FAIL")
        missing_lot_violations = [
            v for v in report["violations"]
            if "Closing lot physical mismatch" in v
        ]
        # Must catch missing expected lots (non-empty violations)
        self.assertGreaterEqual(len(missing_lot_violations), 1)

    def test_audit_fails_when_tax_configuration_is_legacy_11_or_absent(self):
        """Supervisor Review #5851374243 Finding 2: Reject legacy 11% or missing tax_line_id."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_cr = MockRecord(dbname="test_disposable")
        # Legacy tax line configured with 11% instead of 12% on DPP Nilai Lain
        legacy_tax_rec = MockRecord(id=1, name="PPN 11%", description="Legacy 11%", amount=11.00)
        inv_legacy_tax = MockRecord(
            id=101,
            company_id=1,
            payment_reference="INV-202608-0001",
            move_type="out_invoice",
            state="posted",
            is_fmcg_seed_invoice=True,
            amount_untaxed=100000.00,
            amount_tax=11000.00,
            amount_total=111000.00,
            line_ids=[
                MockRecord(
                    id=1,
                    account_id=MockRecord(code="211200"),
                    credit=11000.00,
                    debit=0.0,
                    tax_base_amount=91666.67,  # Correct base, but wrong configured tax rate (11% vs 12%)
                    tax_line_id=legacy_tax_rec,
                )
            ],
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "sale.order": MockModel(),
            "account.move": MockModel(records=[inv_legacy_tax]),
            "purchase.order": MockModel(),
            "account.payment": MockModel(),
            "stock.picking": MockModel(),
            "stock.move": MockModel(),
            "stock.quant": MockModel(),
            "account.move.line": MockModel(),
            "account.account": MockModel(records=[
                MockRecord(id=10, code="211200", company_id=1),
                MockRecord(id=11, code="114100", company_id=1),
                MockRecord(id=12, code="113000", company_id=1),
                MockRecord(id=13, code="112000", company_id=1),
                MockRecord(id=14, code="211000", company_id=1),
            ]),
        }
        env = MockEnv(mock_models)
        env.cr = mock_cr
        oracle = PeriodPackOracle(AUG_PACK_DIR)
        report = audit_period_database(env, oracle)
        self.assertEqual(report["status"], "FAIL")
        tax_config_violations = [
            v for v in report["violations"]
            if "tax configuration mismatch" in v or "strictly requires 12.00%" in v
        ]
        self.assertGreaterEqual(len(tax_config_violations), 1)

    def test_audit_fails_on_quarantine_lot_mismatch(self):
        """Supervisor Review #5851374243 Finding 1b: Audit fails when quarantine quantities mismatch."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_cr = MockRecord(dbname="test_disposable")
        # Quant placed in quarantine location but with wrong quantity
        quar_quant = MockRecord(
            id=1,
            company_id=1,
            location_id=MockRecord(name="Karantina FMCG Maumbi", usage="internal"),
            product_id=MockRecord(default_code="KPA-ABC-02", standard_price=1000.00),
            lot_id=MockRecord(name="LOT-TOS-20260701-14"),
            quantity=999.0,  # Expected quarantine is 20 cartons * carton_qty
            reserved_quantity=0.0,
        )
        mock_acc_stock = MockRecord(id=12, code="113000", company_id=1)
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "sale.order": MockModel(),
            "account.move": MockModel(),
            "purchase.order": MockModel(),
            "account.payment": MockModel(),
            "stock.picking": MockModel(),
            "stock.move": MockModel(),
            "stock.quant": MockModel(records=[quar_quant]),
            "account.move.line": MockModel(),
            "account.account": MockModel(records=[
                MockRecord(id=10, code="211200", company_id=1),
                MockRecord(id=11, code="114100", company_id=1),
                mock_acc_stock,
                MockRecord(id=13, code="112000", company_id=1),
                MockRecord(id=14, code="211000", company_id=1),
            ]),
        }
        env = MockEnv(mock_models)
        env.cr = mock_cr
        oracle = PeriodPackOracle(AUG_PACK_DIR)
        report = audit_period_database(env, oracle)
        self.assertEqual(report["status"], "FAIL")
        quar_violations = [
            v for v in report["violations"]
            if "quarantine" in v.lower()
        ]
        self.assertGreaterEqual(len(quar_violations), 1)

    def test_audit_fails_when_sku_total_preserved_but_lot_redistributed(self):
        """Supervisor Review #5851374243: Mutation preserving SKU total but moving qty between lots must FAIL."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_cr = MockRecord(dbname="test_disposable")
        mock_acc_stock = MockRecord(id=12, code="113000", company_id=1)
        # SKU KPA-ABC-01 total expected is 8,040 pcs (67 cartons * 120)
        # Move all 8,040 pcs to a fake/wrong lot, leaving LOT-TOS-20260701-13 empty
        redistributed_quant = MockRecord(
            id=1,
            company_id=1,
            location_id=MockRecord(name="Stock Gudang Maumbi", usage="internal"),
            product_id=MockRecord(default_code="KPA-ABC-01", standard_price=1400.00),
            lot_id=MockRecord(name="LOT-WRONG-REDISTRIBUTED-01"),  # Wrong lot!
            quantity=8040.0,  # SKU total matches exactly!
            reserved_quantity=0.0,
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "sale.order": MockModel(),
            "account.move": MockModel(),
            "purchase.order": MockModel(),
            "account.payment": MockModel(),
            "stock.picking": MockModel(),
            "stock.move": MockModel(),
            "stock.quant": MockModel(records=[redistributed_quant]),
            "account.move.line": MockModel(),
            "account.account": MockModel(records=[
                MockRecord(id=10, code="211200", company_id=1),
                MockRecord(id=11, code="114100", company_id=1),
                mock_acc_stock,
                MockRecord(id=13, code="112000", company_id=1),
                MockRecord(id=14, code="211000", company_id=1),
            ]),
        }
        env = MockEnv(mock_models)
        env.cr = mock_cr
        oracle = PeriodPackOracle(AUG_PACK_DIR)
        report = audit_period_database(env, oracle)
        self.assertEqual(report["status"], "FAIL")
        # Must catch lot mismatch despite SKU total matching
        lot_mismatches = [
            v for v in report["violations"]
            if "Closing lot physical mismatch" in v or "Unexpected closing lot" in v
        ]
        self.assertGreaterEqual(len(lot_mismatches), 1)

    def test_audit_fails_when_reservation_mutated(self):
        """Supervisor Review #5851374243: Mutation changing reserved quantities must FAIL."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_cr = MockRecord(dbname="test_disposable")
        mock_acc_stock = MockRecord(id=12, code="113000", company_id=1)
        # Expected reserved for KPA-ABC-01||LOT-TOS-20260701-13 is 14 cartons * 120 = 1,680 pcs
        # Mutate reserved quantity to 999 pcs
        mutated_res_quant = MockRecord(
            id=1,
            company_id=1,
            location_id=MockRecord(name="Stock Gudang Maumbi", usage="internal"),
            product_id=MockRecord(default_code="KPA-ABC-01", standard_price=1400.00),
            lot_id=MockRecord(name="LOT-TOS-20260701-13"),
            quantity=8040.0,
            reserved_quantity=999.0,  # Wrong reserved qty!
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "sale.order": MockModel(),
            "account.move": MockModel(),
            "purchase.order": MockModel(),
            "account.payment": MockModel(),
            "stock.picking": MockModel(),
            "stock.move": MockModel(),
            "stock.quant": MockModel(records=[mutated_res_quant]),
            "account.move.line": MockModel(),
            "account.account": MockModel(records=[
                MockRecord(id=10, code="211200", company_id=1),
                MockRecord(id=11, code="114100", company_id=1),
                mock_acc_stock,
                MockRecord(id=13, code="112000", company_id=1),
                MockRecord(id=14, code="211000", company_id=1),
            ]),
        }
        env = MockEnv(mock_models)
        env.cr = mock_cr
        oracle = PeriodPackOracle(AUG_PACK_DIR)
        report = audit_period_database(env, oracle)
        self.assertEqual(report["status"], "FAIL")
        res_mismatches = [
            v for v in report["violations"]
            if "Closing lot reserved mismatch" in v or "total reserved cartons mismatch" in v
        ]
        self.assertGreaterEqual(len(res_mismatches), 1)


    def test_resolve_canonical_tax_code_04_success(self):
        """Loader successfully resolves authoritative Tax Code 04 / DPP Nilai Lain 12%."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        tax_04 = MockRecord(
            id=10,
            company_id=mock_company,
            type_tax_use="sale",
            amount=12.0,
            name="PPN Keluaran 12% (DPP Nilai Lain - Kode 04)",
            description="PPN 12% atas DPP Nilai Lain 11/12 PMK 131/2024",
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "account.tax": MockModel(records=[tax_04]),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, company_id=1)
        loader.company = mock_company
        resolved = loader._resolve_canonical_tax_code_04()
        self.assertEqual(resolved.id, 10)

    def test_resolve_canonical_tax_code_04_rejects_generic_or_wrong_code(self):
        """Supervisor Review #5851786779: Loader rejects generic 'PPN 12%' without authoritative 04 identifier."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        # Generic 12% tax without 04 or Nilai Lain semantics
        generic_tax = MockRecord(
            id=11,
            company_id=mock_company,
            type_tax_use="sale",
            amount=12.0,
            name="PPN 12%",
            description="Generic PPN 12% Standard",
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "account.tax": MockModel(records=[generic_tax]),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, company_id=1)
        loader.company = mock_company
        with self.assertRaises(PreflightContinuityError) as ctx:
            loader._resolve_canonical_tax_code_04()
        self.assertIn("Tax Code 04 resolution failed", str(ctx.exception))
        self.assertIn("Generic/wrong-code 12% taxes strictly rejected", str(ctx.exception))

    def test_resolve_canonical_tax_code_04_rejects_ambiguous_taxes(self):
        """Loader rejects ambiguous configuration when multiple candidate taxes match."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        tax_04_a = MockRecord(
            id=10,
            company_id=mock_company,
            type_tax_use="sale",
            amount=12.0,
            name="PPN Keluaran 12% (DPP Nilai Lain - Kode 04)",
        )
        tax_04_b = MockRecord(
            id=12,
            company_id=mock_company,
            type_tax_use="sale",
            amount=12.0,
            name="PPN 12% Nilai Lain Alt (04)",
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "account.tax": MockModel(records=[tax_04_a, tax_04_b]),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, company_id=1)
        loader.company = mock_company
        with self.assertRaises(PreflightContinuityError) as ctx:
            loader._resolve_canonical_tax_code_04()
        self.assertIn("Ambiguous Tax Code 04 configuration", str(ctx.exception))

    def test_audit_fails_when_tax_rate_is_12_but_lacks_code_04_identifier(self):
        """Supervisor Review #5851786779: Audit fails when tax rate is 12% but lacks Code 04 identifier."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_cr = MockRecord(dbname="test_disposable")
        # Tax configured with 12% rate but generic name "PPN 12%" (no 04 or Nilai Lain)
        generic_12_tax_rec = MockRecord(id=1, name="PPN 12%", description="Generic 12%", amount=12.00)
        inv_wrong_tax_id = MockRecord(
            id=101,
            company_id=1,
            payment_reference="INV-202608-0001",
            move_type="out_invoice",
            state="posted",
            is_fmcg_seed_invoice=True,
            amount_untaxed=100000.00,
            amount_tax=11000.00,
            amount_total=111000.00,
            line_ids=[
                MockRecord(
                    id=1,
                    account_id=MockRecord(code="211200"),
                    credit=11000.00,
                    debit=0.0,
                    tax_base_amount=91666.67,  # Correct base, 12% rate, but wrong tax identity
                    tax_line_id=generic_12_tax_rec,
                )
            ],
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "sale.order": MockModel(),
            "account.move": MockModel(records=[inv_wrong_tax_id]),
            "purchase.order": MockModel(),
            "account.payment": MockModel(),
            "stock.picking": MockModel(),
            "stock.move": MockModel(),
            "stock.quant": MockModel(),
            "account.move.line": MockModel(),
            "account.account": MockModel(records=[
                MockRecord(id=10, code="211200", company_id=1),
                MockRecord(id=11, code="114100", company_id=1),
                MockRecord(id=12, code="113000", company_id=1),
                MockRecord(id=13, code="112000", company_id=1),
                MockRecord(id=14, code="211000", company_id=1),
            ]),
        }
        env = MockEnv(mock_models)
        env.cr = mock_cr
        oracle = PeriodPackOracle(AUG_PACK_DIR)
        report = audit_period_database(env, oracle)
        self.assertEqual(report["status"], "FAIL")
        wrong_code_violations = [
            v for v in report["violations"]
            if "wrong-code same-rate tax" in v or "lacks authoritative Tax Code 04" in v
        ]
        self.assertGreaterEqual(len(wrong_code_violations), 1)

    def test_audit_fails_when_invoices_missing_is_fmcg_seed_invoice_flag(self):
        """Supervisor Review #5860849497: Audit fails when August invoices lack is_fmcg_seed_invoice."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_cr = MockRecord(dbname="test_disposable")
        # Invoices valid in numbers but missing is_fmcg_seed_invoice
        unflagged_inv = MockRecord(
            id=101,
            company_id=1,
            name="INV/2026/08/0001",
            payment_reference="INV-202608-0001",
            move_type="out_invoice",
            state="posted",
            is_fmcg_seed_invoice=False,  # Unflagged
            amount_untaxed=100000.00,
            amount_tax=11000.00,
            amount_total=111000.00,
            line_ids=[
                MockRecord(id=1, account_id=MockRecord(code="211200"), credit=11000.00, debit=0.0)
            ],
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "sale.order": MockModel(records=[]),
            "account.move": MockModel(records=[unflagged_inv]),
            "purchase.order": MockModel(records=[]),
            "account.payment": MockModel(records=[]),
            "stock.picking": MockModel(records=[]),
            "stock.move": MockModel(records=[]),
            "stock.quant": MockModel(records=[]),
            "account.move.line": MockModel(records=[]),
            "account.account": MockModel(records=[
                MockRecord(id=10, code="211200", company_id=1),
                MockRecord(id=11, code="114100", company_id=1),
                MockRecord(id=12, code="113000", company_id=1),
                MockRecord(id=13, code="112000", company_id=1),
                MockRecord(id=14, code="211000", company_id=1),
            ]),
        }
        env = MockEnv(mock_models)
        env.cr = mock_cr
        oracle = PeriodPackOracle(AUG_PACK_DIR)
        report = audit_period_database(env, oracle)
        self.assertEqual(report["status"], "FAIL")
        missing_flag_violations = [v for v in report["violations"] if "missing is_fmcg_seed_invoice flag" in v]
        self.assertGreaterEqual(len(missing_flag_violations), 1)

    def test_tax_code_04_native_computation_formula(self):
        """PMK 131/2024: Tax Code 04 DPP Nilai Lain (11/12) and PPN 12% native formula verification."""
        # Commercial DPP: 355,680.00
        commercial_dpp = 355680.00
        # Expected DPP Nilai Lain: (11/12) * 355680.00 = 326040.00
        expected_dpp_nl = (commercial_dpp * 11.0) / 12.0
        self.assertAlmostEqual(expected_dpp_nl, 326040.00, places=2)
        # Expected PPN 12%: 12% * 326040.00 = 39124.80
        expected_ppn = expected_dpp_nl * 0.12
        self.assertAlmostEqual(expected_ppn, 39124.80, places=2)
        # Effective rate is exactly 11% of commercial DPP
        effective_ppn = commercial_dpp * 0.11
        self.assertAlmostEqual(expected_ppn, effective_ppn, places=2)
        # Total invoice with PPN
        expected_total = commercial_dpp + expected_ppn
        self.assertAlmostEqual(expected_total, 394804.80, places=2)

    def test_loader_period_attribute_and_batch_naming(self):
        """Verify loader exposes period attribute and correct PERIOD_ batch formatting."""
        env = MockEnv({})
        loader = GenericPeriodPackLoader(env, AUG_PACK_DIR, dry_run=True, strict=True)
        self.assertEqual(loader.period, "2026-08")
        self.assertEqual(loader.manifest.period, "2026-08")
        expected_batch = f"PERIOD_{loader.period}"
        self.assertEqual(expected_batch, "PERIOD_2026-08")

    def test_multi_lot_picking_allocation_and_move_lines(self):
        """Verify _assign_lots_to_picking correctly maps multi-lot split lines for same SKU."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_prod = MockRecord(id=101, default_code="MYR-RMA-02", name="Roma Kelapa")
        created_lots = []
        created_move_lines = []

        class MockLotModel:
            def search(self, domain, limit=None):
                return []
            def create(self, vals):
                rec = MockRecord(id=len(created_lots) + 1, **vals)
                created_lots.append(rec)
                return rec
            def sudo(self):
                return self

        class MockMoveLineModel:
            _fields = {"lot_name": True, "quantity": True, "picked": True}
            def create(self, vals):
                rec = MockRecord(id=len(created_move_lines) + 1, **vals)
                created_move_lines.append(rec)
                return rec
            def sudo(self):
                return self

        class MockProdModel:
            def search(self, domain, limit=None):
                return mock_prod
            def sudo(self):
                return self

        mock_move_1 = MockRecord(id=501, product_id=mock_prod, product_uom_qty=270.0, quantity=0.0, picked=False)
        mock_move_2 = MockRecord(id=502, product_id=mock_prod, product_uom_qty=30.0, quantity=0.0, picked=False)
        mock_picking = MockRecord(
            id=301,
            name="WH/OUT/0035",
            state="assigned",
            move_ids=[mock_move_1, mock_move_2],
            move_line_ids=[],
            location_id=MockRecord(id=11),
            location_dest_id=MockRecord(id=12),
        )

        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "stock.lot": MockLotModel(),
            "stock.move.line": MockMoveLineModel(),
            "product.product": MockProdModel(),
            "stock.picking": MockModel(records=[mock_picking]),
            "sale.order": MockModel(records=[]),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env, AUG_PACK_DIR, dry_run=False, strict=True)
        loader.company = mock_company

        lines_data = [
            {"sku_code": "MYR-RMA-02", "qty_cartons": 9, "carton_qty": 30, "lot_number": "LOT-ORA-20260615-INIT-02"},
            {"sku_code": "MYR-RMA-02", "qty_cartons": 1, "carton_qty": 30, "lot_number": "LOT-ORA-20260702-02"},
        ]
        loader._assign_lots_to_picking(mock_picking, lines_data)

        self.assertEqual(len(created_lots), 2)
        self.assertEqual(len(created_move_lines), 2)
        self.assertEqual(created_move_lines[0].quantity, 270.0)
        self.assertEqual(created_move_lines[0].lot_id, created_lots[0].id)
        self.assertEqual(created_move_lines[1].quantity, 30.0)
        self.assertEqual(created_move_lines[1].lot_id, created_lots[1].id)

    def test_validate_picking_safely_fails_closed_with_descriptive_error(self):
        """Verify _validate_picking_safely raises descriptive StateInconsistencyError when move is assigned."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_prod = MockRecord(id=101, default_code="MYR-RMA-02", name="Roma Kelapa")
        mock_move = MockRecord(id=3311, name="move_3311", product_id=mock_prod, state="assigned")
        mock_picking = MockRecord(
            id=301,
            name="WH/OUT/0035",
            origin="SO-202608-0035",
            state="done",  # picking reports done, but internal move stayed assigned
            move_ids=[mock_move],
        )
        env = MockEnv({"res.company": MockModel(records=[mock_company])})
        loader = GenericPeriodPackLoader(env, AUG_PACK_DIR, dry_run=False, strict=True)
        loader.company = mock_company

        with self.assertRaises(StateInconsistencyError) as ctx:
            loader._validate_picking_safely(mock_picking, ref_num="SO-202608-0035")

        err_msg = str(ctx.exception)
        self.assertIn("3311", err_msg)
        self.assertIn("MYR-RMA-02", err_msg)
        self.assertIn("assigned", err_msg)
        self.assertIn("SO-202608-0035", err_msg)

    def test_single_invoice_reproduction_and_pack_contract_resolution(self):
        """Reproduksi INV-202608-0001 lewat jalur loader sebenarnya:
        Verifikasi DPP komersial (355.680,00), DPP Nilai Lain (326.040,00),
        PPN 12% (39.124,80), total (394.804,80), dan jurnal pajak pada akun 211200.
        """
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_partner = MockRecord(
            id=10,
            ref="CUST-RTL-006",
            name="Warung Dani Ujung Lorong",
            property_account_receivable_id=MockRecord(
                id=110, code="112000", name="Piutang Usaha", account_type="asset_receivable"
            ),
        )
        mock_prod = MockRecord(
            id=20,
            default_code="MYR-CND-02",
            name="Koppiko Blister Pack 32g",
            uom_id=MockRecord(id=1, name="Pcs"),
            taxes_id=None,
        )
        # Mock income account
        mock_acc_inc = MockRecord(id=40, code="410100", name="Pendapatan Penjualan")
        mock_prod._get_product_accounts = lambda: {"income": mock_acc_inc}

        mock_acc_ppn_out = MockRecord(id=50, code="211200", name="PPN Keluaran", company_id=mock_company)
        mock_acc_ar = MockRecord(
            id=110, code="112000", name="Piutang Usaha", account_type="asset_receivable", company_id=mock_company
        )

        # Canonical Tax Code 04
        mock_tax_04 = MockRecord(
            id=77,
            name="PPN Keluaran 12% (DPP Nilai Lain - Kode 04)",
            description="PPN 12% atas DPP Nilai Lain 11/12 PMK 131/2024 (Kode Transaksi 04)",
            amount=12.0,
            amount_type="percent",
            type_tax_use="sale",
            l10n_id_tax_transaction_code="04",
            company_id=mock_company,
            invoice_repartition_line_ids=[
                MockRecord(id=1, repartition_type="base", factor_percent=91.6667),
                MockRecord(id=2, repartition_type="tax", factor_percent=100.0, account_id=mock_acc_ppn_out),
            ],
            refund_repartition_line_ids=[
                MockRecord(id=3, repartition_type="base", factor_percent=91.6667),
                MockRecord(id=4, repartition_type="tax", factor_percent=100.0, account_id=mock_acc_ppn_out),
            ],
        )

        mock_sol = MockRecord(
            id=501,
            product_id=mock_prod,
            tax_id=mock_tax_04,
            tax_ids=[mock_tax_04],
        )
        mock_so = MockRecord(
            id=601,
            name="SO/2026/08/0001",
            client_order_ref="SO-202608-0001",
            partner_id=mock_partner,
            company_id=mock_company,
            order_line=[mock_sol],
            picking_ids=[],
        )
        mock_sale_journal = MockRecord(id=701, code="SJL", name="Sales Journal", type="sale", company_id=mock_company)

        mock_moves = []
        mock_am_lines = []

        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "res.partner": MockModel(records=[mock_partner]),
            "product.product": MockModel(records=[mock_prod]),
            "product.template": MockModel(records=[]),
            "account.tax": MockModel(records=[mock_tax_04]),
            "sale.order": MockModel(records=[mock_so]),
            "account.journal": MockModel(records=[mock_sale_journal]),
            "account.account": MockModel(records=[mock_acc_ppn_out, mock_acc_ar, mock_acc_inc]),
            "account.move": MockModel(records=mock_moves),
            "account.move.line": MockModel(records=mock_am_lines),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env, AUG_PACK_DIR, dry_run=False, strict=True)
        loader.company = mock_company

        # Target invoice row
        inv_row = {
            "invoice_number": "INV-202608-0001",
            "so_number": "SO-202608-0001",
            "do_number": "DO-202608-0001",
            "date_invoice": "2026-08-03",
            "due_date": "2026-08-03",
            "commercial_dpp": "355680.00",
            "dpp_amount": "326040.00",
            "tax_rate": "0.12",
            "ppn_amount": "39124.80",
            "total_invoice_with_ppn": "394804.80",
            "customer": "CUST-RTL-006 - Warung Dani Ujung Lorong",
            "is_pkp": "False",
            "tax_code": "04",
        }
        loader.reader.set_override("invoices.csv", [inv_row])

        processed = loader._apply_invoices()
        self.assertEqual(processed, 1)

        created_inv = mock_moves[0]
        self.assertEqual(created_inv.state, "posted")
        self.assertEqual(created_inv.payment_reference, "INV-202608-0001")
        self.assertEqual(created_inv.amount_untaxed, 355680.00)
        self.assertEqual(created_inv.amount_tax, 39124.80)
        self.assertEqual(created_inv.amount_total, 394804.80)
        self.assertEqual(created_inv.l10n_id_tax_transaction_code, "04")

        # Verify tax move lines on account 211200
        t_lines = [
            aml for aml in mock_am_lines if getattr(getattr(aml, "account_id", None), "code", "") == "211200"
        ]
        self.assertEqual(len(t_lines), 1)
        self.assertEqual(t_lines[0].credit, 39124.80)
        self.assertEqual(t_lines[0].debit, 0.0)
        self.assertEqual(t_lines[0].tax_base_amount, 326040.00)
        self.assertEqual(t_lines[0].tax_line_id.id, mock_tax_04.id)

    def test_single_invoice_old_unpatched_divergence_fails_validation(self):
        """Supervisor Contract: Older unpatched code where tax is omitted and total is 355680
        must fail validation closed with exact drift message."""
        mock_inv = MockRecord(
            payment_reference="INV-202608-0001",
            partner_id=MockRecord(ref="CUST-RTL-006", name="Warung Dani"),
            invoice_date="2026-08-03",
            amount_untaxed=355680.00,
            amount_tax=0.00,  # Missing tax
            amount_total=355680.00,  # Expected 394804.80
            state="posted",
        )
        inv_row = {
            "invoice_number": "INV-202608-0001",
            "customer": "CUST-RTL-006",
            "date_invoice": "2026-08-03",
            "commercial_dpp": "355680.00",
            "dpp_amount": "326040.00",
            "ppn_amount": "39124.80",
            "total_invoice_with_ppn": "394804.80",
        }
        loader = GenericPeriodPackLoader(MockEnv({}), AUG_PACK_DIR, dry_run=True)
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader._validate_existing_invoice(mock_inv, inv_row)
        expected_msg = "Drift detected on Invoice INV-202608-0001: expected total 394804.80, found 355680.00"
        self.assertIn(expected_msg, str(ctx.exception))

    def test_resolve_account_supports_odoo19_company_ids_schema(self):
        """Odoo 19 schema: account.account uses company_ids (Many2many) rather than company_id.
        _resolve_account must query company_ids without raising invalid field error."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        mock_acc_211200 = MockRecord(id=88, code="211200", name="PPN Keluaran", company_ids=[1])
        account_model = MockModel(records=[mock_acc_211200])
        account_model._fields = {"code": None, "company_ids": None}

        # Subclass or wrap search to reject 'company_id' like native Odoo 19
        orig_search = account_model.search
        def guarded_search(domain, limit=None):
            for term in domain:
                if isinstance(term, tuple) and term[0] == "company_id":
                    raise ValueError(
                        "Invalid field account.account.company_id in condition ('company_id', 'in', [1, False])"
                    )
            return orig_search(domain, limit=limit)
        account_model.search = guarded_search

        env = MockEnv({"account.account": account_model, "res.company": MockModel(records=[mock_company])})
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, strict=True)
        loader.company = mock_company

        resolved = loader._resolve_account("211200")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, 88)
        self.assertEqual(resolved.code, "211200")

    def test_split_lot_rejection_invoice_balance_and_contract(self):
        """Regression test for INV-202608-0083 / SO-202608-0083:
        When an SO contains multiple lines for the same SKU with different lots
        (e.g. MYR-BBG-03 lot A: 13 cartons, lot B: 3 cartons) and a rejection
        specifies lot A (13 cartons), only lot A must be deducted.
        Lot B (3 cartons) must remain in the invoice, keeping commercial DPP
        at Rp 2.700.475,20, PPN at Rp 297.052,27, total at Rp 2.997.527,47,
        and ensuring debit == credit balance without UserError: The entry is not balanced.
        """
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri Manado")
        mock_partner = MockRecord(
            id=10,
            ref="CUST-MT-02",
            name="Alfamidi DC Manado",
            property_account_receivable_id=MockRecord(
                id=110, code="112000", name="Piutang Usaha", account_type="asset_receivable"
            ),
        )
        mock_prod_bbg = MockRecord(id=21, default_code="MYR-BBG-03", name="Beng-Beng Share It", uom_id=MockRecord(id=1))
        mock_prod_cnd = MockRecord(id=22, default_code="MYR-CND-05", name="Kiss Mint Barley", uom_id=MockRecord(id=1))
        mock_prod_kpk = MockRecord(id=23, default_code="MYR-KPK-RTD-04", name="Kopiko 78C", uom_id=MockRecord(id=1))

        mock_acc_inc = MockRecord(id=40, code="410100", name="Pendapatan Penjualan")
        for p in (mock_prod_bbg, mock_prod_cnd, mock_prod_kpk):
            p._get_product_accounts = lambda: {"income": mock_acc_inc}

        mock_acc_ppn_out = MockRecord(id=50, code="211200", name="PPN Keluaran", company_ids=[1])
        mock_acc_ar = MockRecord(
            id=110, code="112000", name="Piutang Usaha", account_type="asset_receivable", company_ids=[1]
        )

        mock_tax_04 = MockRecord(
            id=77,
            name="PPN Keluaran 12% (DPP Nilai Lain - Kode 04)",
            amount=12.0,
            type_tax_use="sale",
            l10n_id_tax_transaction_code="04",
            company_id=mock_company,
        )

        mock_sol_1 = MockRecord(id=601, product_id=mock_prod_bbg, product_uom_qty=312.0)
        mock_sol_2 = MockRecord(id=602, product_id=mock_prod_bbg, product_uom_qty=72.0)
        mock_sol_3 = MockRecord(id=603, product_id=mock_prod_cnd, product_uom_qty=168.0)
        mock_sol_4 = MockRecord(id=604, product_id=mock_prod_kpk, product_uom_qty=72.0)

        mock_so = MockRecord(
            id=701,
            name="SO/2026/08/0083",
            client_order_ref="SO-202608-0083",
            partner_id=mock_partner,
            company_id=mock_company,
            order_line=[mock_sol_1, mock_sol_2, mock_sol_3, mock_sol_4],
            picking_ids=[],
        )

        created_moves = []
        class MockAccountMoveModel(MockModel):
            def create(self, vals):
                lines = []
                inv_lines = []
                vals_copy = dict(vals)
                vals_copy.pop("invoice_line_ids", None)
                vals_copy.pop("line_ids", None)
                vals_copy.setdefault("partner_id", mock_partner)
                vals_copy.setdefault("state", "draft")
                inv_rec = MockRecord(
                    id=len(created_moves) + 1,
                    line_ids=lines,
                    invoice_line_ids=inv_lines,
                    **vals_copy,
                )
                for item in vals.get("invoice_line_ids", []):
                    if isinstance(item, tuple) and len(item) == 3 and item[0] == 0:
                        lvals = item[2]
                        # Calculate line subtotal
                        l_qty = float(lvals.get("quantity", 0.0))
                        l_price = float(lvals.get("price_unit", 0.0))
                        l_disc = float(lvals.get("discount", 0.0))
                        subtotal = round(l_qty * l_price * (1.0 - l_disc / 100.0), 2)
                        line_rec = MockRecord(
                            id=len(lines) + 1,
                            move_id=inv_rec,
                            display_type="product",
                            price_subtotal=subtotal,
                            credit=subtotal,
                            debit=0.0,
                            balance=-subtotal,
                            **lvals,
                        )
                        lines.append(line_rec)
                        inv_rec.invoice_line_ids.append(line_rec)
                # Odoo automatically creates receivable balancing line
                tot_sub = sum(line_item.price_subtotal for line_item in lines)
                ar_line = MockRecord(
                    id=len(lines) + 1,
                    move_id=inv_rec,
                    display_type="payment_term",
                    account_id=mock_acc_ar,
                    debit=tot_sub,
                    credit=0.0,
                    balance=tot_sub,
                )
                lines.append(ar_line)
                created_moves.append(inv_rec)
                return inv_rec

        class MockAccountMoveLineModel(MockModel):
            def create(self, vals):
                rec = MockRecord(id=999 + len(self._records), **vals)
                self._records.append(rec)
                return rec

        env = MockEnv({
            "res.company": MockModel(records=[mock_company]),
            "res.partner": MockModel(records=[mock_partner]),
            "product.product": MockModel(records=[mock_prod_bbg, mock_prod_cnd, mock_prod_kpk]),
            "sale.order": MockModel(records=[mock_so]),
            "account.tax": MockModel(records=[mock_tax_04]),
            "account.account": MockModel(records=[mock_acc_inc, mock_acc_ppn_out, mock_acc_ar]),
            "account.move": MockAccountMoveModel(records=[]),
            "account.move.line": MockAccountMoveLineModel(records=[]),
            "account.journal": MockModel(records=[MockRecord(id=1, code="SJL", type="sale", company_id=mock_company)]),
        })

        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=False, strict=True)
        loader.company = mock_company

        # Target invoice row
        inv_row = {
            "invoice_number": "INV-202608-0083",
            "so_number": "SO-202608-0083",
            "date_invoice": "2026-08-04",
            "due_date": "2026-09-18",
            "commercial_dpp": "2700475.20",
            "dpp_amount": "2475435.60",
            "ppn_amount": "297052.27",
            "total_invoice_with_ppn": "2997527.47",
        }
        loader.reader.set_override("invoices.csv", [inv_row])

        processed = loader._apply_invoices()
        self.assertEqual(processed, 1)
        self.assertEqual(len(created_moves), 1)

        inv = created_moves[0]
        # Must have 3 invoice lines (Line 2 BBG lot 17, Line 3 CND, Line 4 KPK)
        self.assertEqual(len(inv.invoice_line_ids), 3)

        # Beng-Beng line must be linked to mock_sol_2 (72.0 units), NOT mock_sol_1 (312.0 units, rejected)
        bbg_line = next(
            line for line in inv.invoice_line_ids
            if getattr(line, "product_id", None) in (mock_prod_bbg, mock_prod_bbg.id)
        )
        self.assertEqual(bbg_line.quantity, 72.0)
        self.assertEqual(bbg_line.sale_line_ids, [(6, 0, [602])])

        # Check total credit (product lines + tax line) vs total debit (receivable line)
        product_credits = sum(ml.credit for ml in inv.line_ids if ml.display_type == "product")
        tax_credits = sum(ml.credit for ml in inv.line_ids if ml.display_type == "tax")
        ar_debits = sum(ml.debit for ml in inv.line_ids if ml.display_type == "payment_term")

        self.assertAlmostEqual(product_credits, 2700475.20, places=2)
        self.assertAlmostEqual(tax_credits, 297052.27, places=2)
        self.assertAlmostEqual(ar_debits, 2997527.47, places=2)
        self.assertAlmostEqual(product_credits + tax_credits, ar_debits, places=2)


class TestStockCutoff(unittest.TestCase):
    def test_reverses_future_receipt_delivery_and_quarantine_by_lot(self):
        from unittest.mock import Mock

        from scripts.ops.verify_disposable_period_pack import _stock_at_cutoff

        stock = SimpleNamespace(id=1, usage="internal")
        quarantine = SimpleNamespace(id=2, usage="internal")
        supplier = SimpleNamespace(id=3, usage="supplier")
        customer = SimpleNamespace(id=4, usage="customer")
        product = SimpleNamespace(id=1)
        older_lot = SimpleNamespace(id=1)
        new_lot = SimpleNamespace(id=2)
        sale = SimpleNamespace(client_order_ref="SO-before-cutoff")

        def line(qty, lot, source, destination, order=None):
            return SimpleNamespace(
                quantity_product_uom=qty, product_id=product, lot_id=lot,
                location_id=source, location_dest_id=destination,
                picking_id=SimpleNamespace(sale_id=order),
            )

        def quant(qty, lot, location):
            return SimpleNamespace(
                quantity=qty, reserved_quantity=0, product_id=product, lot_id=lot, location_id=location,
            )

        env = MockEnv({"stock.move.line": Mock()})
        env.cr = SimpleNamespace(dbname="fmcg_period_disposable")
        search = env["stock.move.line"].sudo().search
        search.return_value = [
            line(20, new_lot, supplier, stock),
            line(7, older_lot, stock, customer, sale),
            line(1, older_lot, customer, quarantine),
        ]
        oracle = SimpleNamespace(
            manifest=SimpleNamespace(pack_end="2026-08-31"),
            reader=SimpleNamespace(sales_orders=[{"so_number": sale.client_order_ref, "date_order": "2026-08-31"}]),
        )
        quants = [quant(3, older_lot, stock), quant(20, new_lot, stock), quant(2, older_lot, quarantine)]
        result = {
            (row.location_id.id, row.lot_id.id): (row.quantity, row.reserved_quantity)
            for row in _stock_at_cutoff(env, SimpleNamespace(id=1), quants, oracle)
        }
        self.assertEqual(result, {(1, 1): (10, 7), (1, 2): (0, 0), (2, 1): (1, 0)})
        self.assertIn(("date", ">=", "2026-09-01 00:00:00"), search.call_args.args[0])
        self.assertIn(("state", "=", "done"), search.call_args.args[0])
        self.assertIn(("company_id", "=", 1), search.call_args.args[0])


class TestArResolverCrossPeriod(unittest.TestCase):
    """Test AR resolver handles cross-period invoice lookup & strict fail-closed contract (BUG-1)."""

    def test_ar_cross_period_july_data_count(self):
        """Pack Agustus must contain exactly 1202 AR rows (339 July invoices, 863 August invoices)."""
        import csv
        pack_dir = AUG_PACK_DIR
        if not pack_dir.exists():
            self.skipTest("Pack data not available")
        with open(pack_dir / "ar_collections.csv", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        july_rows = [r for r in rows if r["invoice_number"].startswith("INV-202607")]
        aug_rows = [r for r in rows if r["invoice_number"].startswith("INV-202608")]
        self.assertEqual(len(rows), 1202)
        self.assertEqual(len(july_rows), 339)
        self.assertEqual(len(aug_rows), 863)

    def test_ar_resolver_fallback_to_ref(self):
        """AR resolver must resolve July baseline invoices via 'ref' field."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        july_inv = MockRecord(
            id=401,
            company_id=1,
            ref="INV-202607-0002",  # July convention: saved in ref, not payment_reference
            payment_reference=False,
            name="INV/2026/07/0002",
            state="posted",
        )
        mock_env = MockEnv({"account.move": MockModel(records=[july_inv])})
        loader = GenericPeriodPackLoader(env=mock_env, pack_dir=AUG_PACK_DIR, dry_run=True)
        loader.company = mock_company

        resolved = loader._resolve_ar_invoice("INV-202607-0002")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, 401)
        self.assertEqual(resolved.ref, "INV-202607-0002")

    def test_ar_silent_skip_forbidden_strict(self):
        """AR loader must raise StateInconsistencyError when target invoice is missing (no silent skip)."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        bank_journal = MockRecord(id=10, type="bank")
        mock_env = MockEnv({
            "account.move": MockModel(records=[]),
            "account.payment": MockModel(records=[]),
            "account.journal": MockModel(records=[bank_journal]),
        })
        loader = GenericPeriodPackLoader(env=mock_env, pack_dir=AUG_PACK_DIR, dry_run=False, strict=True)
        loader.company = mock_company
        # Overwrite reader with a single unresolved AR row
        test_ar = [{
            "payment_id": "PAY-AR-TEST-001",
            "invoice_number": "INV-NONEXISTENT-9999",
            "payment_date": "2026-08-01",
            "net_cash_collected_total": "1000000.00",
            "customer": "CUST-RTL-001",
        }]
        loader.reader.set_override("ar_collections.csv", test_ar)
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader._apply_ar_collections()
        self.assertIn("Silent skip forbidden", str(ctx.exception))

    def test_ar_resolver_carry_forward_fallback(self):
        """AR resolver triggers carry-forward fallback when July carry-forward invoice is requested."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        mock_env = MockEnv({"account.move": MockModel(records=[])})
        loader = GenericPeriodPackLoader(env=mock_env, pack_dir=AUG_PACK_DIR, dry_run=False, strict=True)
        loader.company = mock_company

        cf_called = []

        def mock_cf():
            cf_called.append(True)
            # Simulate invoice becoming available after carry forward run
            cf_inv = MockRecord(id=999, company_id=1, ref="INV-202607-1300", name="INV/2026/08/0001", state="posted")
            mock_env.models["account.move"]._records.append(cf_inv)
            return 1

        loader._apply_prior_period_carry_forward = mock_cf

        resolved = loader._resolve_ar_invoice("INV-202607-1300")
        self.assertTrue(len(cf_called) > 0, "Carry forward should have been triggered")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.ref, "INV-202607-1300")


class TestDoDateChronology(unittest.TestCase):
    """Test DO date matches delivery schedule, not SO date (BUG-2)."""

    def test_all_so_have_different_do_date(self):
        """All 1240 SOs in August pack must have scheduled_delivery_date != date_order."""
        import csv
        pack_dir = AUG_PACK_DIR
        if not pack_dir.exists():
            self.skipTest("Pack data not available")
        with open(pack_dir / "sales_orders.csv", encoding="utf-8-sig") as f_so:
            so_rows = {r["so_number"]: r for r in csv.DictReader(f_so)}
        with open(pack_dir / "deliveries.csv", encoding="utf-8-sig") as f_do:
            do_rows = {r["so_number"]: r for r in csv.DictReader(f_do)}
        mismatches = [
            so_num for so_num, so_r in so_rows.items()
            if so_num in do_rows and so_r["date_order"] != do_rows[so_num]["scheduled_delivery_date"]
        ]
        self.assertEqual(len(mismatches), 1240)

    def test_do_date_map_resolves_exact_delivery_dates(self):
        """Loader do_date_map property must resolve exact scheduled delivery dates."""
        loader = GenericPeriodPackLoader(env=None, pack_dir=AUG_PACK_DIR, dry_run=True)
        self.assertEqual(loader.do_date_map.get("SO-202608-0001"), "2026-08-03")
        self.assertEqual(loader.do_date_map.get("SO-202608-0002"), "2026-08-03")


class TestSantosPromoDateConflict(unittest.TestCase):
    """Test Santos promo date conflict handling and date validity guard (P2-C)."""

    def test_santos_promo_before_aug15_count(self):
        """Exactly 65 Santos promo lines occur before Aug 15."""
        import csv
        pack_dir = AUG_PACK_DIR
        if not pack_dir.exists():
            self.skipTest("Pack data not available")
        with open(pack_dir / "order_lines.csv", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        santos_rows = [r for r in rows if "SANTOS" in r.get("promo_id", "")]
        santos_before_aug15 = [r for r in santos_rows if r["date_order"] < "2026-08-15"]
        self.assertEqual(len(santos_rows), 143)
        self.assertEqual(len(santos_before_aug15), 65)



class TestRejectionsReturnQuarantine(unittest.TestCase):
    """Test rejections register count and return picking creation to Quarantine (P2-H)."""

    def test_rejections_data_count(self):
        """August pack rejections.csv must have exactly 47 rejection records."""
        loader = GenericPeriodPackLoader(env=None, pack_dir=AUG_PACK_DIR, dry_run=True)
        self.assertEqual(len(loader.reader.rejections), 47)

    def test_apply_rejections_creates_quarantine_picking_mock(self):
        """_apply_rejections_and_quarantine must create picking with destination = quarantine_loc."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        wh_loc = MockRecord(id=11, name="WH/Stock", usage="internal")
        cust_loc = MockRecord(id=12, name="Customers FMCG Maumbi", usage="customer")
        quarantine_loc = MockRecord(id=13, name="Karantina FMCG Maumbi", usage="internal")
        prod = MockRecord(id=101, default_code="ULV-CLR-02", uom_id=MockRecord(id=1))
        lot = MockRecord(id=201, name="LOT-VER-20260704-32", product_id=prod)

        created_pickings = []
        created_moves = []
        created_move_lines = []

        class MockPickingModel(MockModel):
            def search(self, domain, limit=None):
                if ("sale_id.client_order_ref", "=", "SO-202608-0045") in domain:
                    return [MockRecord(id=42)]
                return super().search(domain, limit)

            def create(self, vals):
                p = MockRecord(id=len(created_pickings) + 1, **vals)
                created_pickings.append(p)
                return p

        class MockMoveModel(MockModel):
            def create(self, vals):
                m = MockRecord(id=len(created_moves) + 1, **vals)
                created_moves.append(m)
                return m

        class MockMoveLineModel(MockModel):
            def create(self, vals):
                ml = MockRecord(id=len(created_move_lines) + 1, **vals)
                created_move_lines.append(ml)
                return ml

        mock_models = {
            "stock.picking": MockPickingModel(records=[]),
            "stock.move": MockMoveModel(records=[]),
            "stock.move.line": MockMoveLineModel(records=[]),
            "stock.picking.type": MockModel(records=[MockRecord(id=1, code="internal")]),
            "stock.lot": MockModel(records=[lot]),
            "product.product": MockModel(records=[prod]),
        }
        loader = GenericPeriodPackLoader(env=MockEnv(mock_models), pack_dir=AUG_PACK_DIR, dry_run=False)
        loader.company = mock_company
        loader.wh_stock_loc = wh_loc
        loader.seed_customer_loc = cust_loc
        loader.quarantine_loc = quarantine_loc

        # Override rejections with a single sample row
        single_rej = [{
            "rejection_id": "REJ-TEST-001",
            "rejection_date": "2026-08-03",
            "so_number": "SO-202608-0045",
            "do_number": "DO-202608-0045",
            "sku_code": "ULV-CLR-02",
            "lot_number": "LOT-VER-20260704-32",
            "qty_cartons": "12",
            "rejection_reason": "SEGEL_PABRIK_BOCOR",
            "incident_batch_ref": "TEST-INCIDENT",
            "evidence_type": "SYNTHETIC",
            "evidence_photo_ref": "data/evidence/example.jpg",
        }]
        loader.reader.set_override("rejections.csv", single_rej)
        processed = loader._apply_rejections_and_quarantine()
        self.assertEqual(processed, 1)
        self.assertEqual(len(created_pickings), 1)
        self.assertEqual(created_pickings[0].location_id, cust_loc.id)
        self.assertEqual(created_pickings[0].location_dest_id, quarantine_loc.id)
        self.assertEqual(created_pickings[0].fmcg_seed_rejection_delivery_id, 42)
        self.assertEqual(created_pickings[0].fmcg_seed_rejection_incident_ref, "TEST-INCIDENT")
        self.assertEqual(created_pickings[0].fmcg_seed_rejection_evidence_ref, "data/evidence/example.jpg")
        self.assertEqual(len(created_moves), 1)
        self.assertNotIn(
            "name", getattr(created_moves[0], "_data", {}), "stock.move must not have 'name' field (Odoo 19)."
        )


class TestTaxPkpNonPkpIdentity(unittest.TestCase):
    """Test PKP / Non-PKP buyer identity handling in invoice processing (P2-I)."""

    def test_invoices_contain_pkp_non_pkp_identity_attributes(self):
        """invoices.csv must contain is_pkp, buyer_id_type, customer_tax_id, and tax_code."""
        import csv
        pack_dir = AUG_PACK_DIR
        if not pack_dir.exists():
            self.skipTest("Pack data not available")
        with open(pack_dir / "invoices.csv", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        first = rows[0]
        self.assertIn("is_pkp", first)
        self.assertIn("buyer_id_type", first)
        self.assertIn("customer_tax_id", first)
        self.assertIn("tax_code", first)
        self.assertEqual(first["tax_code"], "04")

    def test_invoice_creation_populates_buyer_identity_mock(self):
        """_apply_invoices must populate Indonesian tax buyer identity fields."""
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri", currency_id=MockRecord(id=1))
        cust = MockRecord(id=50, ref="CUST-RTL-006", name="Warung Dani", vat=False, l10n_id_pkp=False,
                          l10n_id_buyer_document_type="TIN", l10n_id_buyer_document_number=False)
        cust.commercial_partner_id = cust
        cust._fields = {"vat", "l10n_id_pkp", "l10n_id_buyer_document_type", "l10n_id_buyer_document_number"}
        write = cust.write

        def write_with_native_pkp(values):
            if "vat" in values and "l10n_id_pkp" not in values:
                cust.l10n_id_pkp = bool(values["vat"])
            return write(values)

        cust.write = write_with_native_pkp
        prod = MockRecord(id=101, default_code="MYR-CND-02", name="Koppiko", uom_id=MockRecord(id=1))
        tax_04 = MockRecord(id=14, name="PPN 12% (Kode 04)", amount=12.0, type_tax_use="sale")
        sol = MockRecord(id=701, product_id=prod, product_uom_qty=120.0, price_unit=3000.0)
        so = MockRecord(
            id=601, company_id=1, client_order_ref="SO-202608-0001", partner_id=cust, order_line=[sol], picking_ids=[]
        )

        created_invoices = []

        class MockInvoiceModel(MockModel):
            def create(self, vals):
                inv = MockRecord(id=len(created_invoices) + 1, **vals)
                inv.partner_id = cust
                created_invoices.append(inv)
                return inv

        mock_models = {
            "account.move": MockInvoiceModel(records=[]),
            "account.move.line": MockModel(records=[]),
            "account.journal": MockModel(records=[MockRecord(id=1, type="sale")]),
            "account.tax": MockModel(records=[tax_04]),
            "sale.order": MockModel(records=[so]),
            "product.product": MockModel(records=[prod]),
            "res.partner": MockModel(records=[cust]),
        }
        loader = GenericPeriodPackLoader(env=MockEnv(mock_models), pack_dir=AUG_PACK_DIR, dry_run=False)
        loader.company = mock_company
        single_inv = [{
            "invoice_number": "INV-TEST-001",
            "so_number": "SO-202608-0001",
            "do_number": "DO-202608-0001",
            "date_invoice": "2026-08-03",
            "due_date": "2026-08-03",
            "is_pkp": "False",
            "buyer_id_type": "NIK",
            "customer_tax_id": "7171010808890090",
            "customer_vat": "7171010808890090",
            "customer": "CUST-RTL-006 - Warung Dani",
            "commercial_dpp": "355680.00",
            "dpp_amount": "326040.00",
            "tax_rate": "0.12",
            "ppn_amount": "39124.80",
            "total_invoice_with_ppn": "394804.80",
        }]
        loader.reader.set_override("invoices.csv", single_inv)
        processed = loader._apply_invoices()
        self.assertEqual(processed, 1)
        self.assertEqual(len(created_invoices), 1)
        inv = created_invoices[0]
        self.assertEqual(cust.l10n_id_buyer_document_type, "NIK")
        self.assertEqual(cust.l10n_id_buyer_document_number, "7171010808890090")
        self.assertFalse(cust.l10n_id_pkp)
        self.assertEqual(inv.l10n_id_kode_transaksi, "04")


class TestCascadingAndFooterDiscountSpecification(unittest.TestCase):
    """Test specifications for cascading discount and footer discount (P2-A & P2-B)."""

    def test_cascading_discount_formula_differs_from_additive(self):
        """Sequential compounding discount != simple additive discount."""
        d1 = Decimal("0.016")  # 1.6% basic
        d2 = Decimal("0.016")  # 1.6% promo
        sequential_net = (Decimal("1.0") - d1) * (Decimal("1.0") - d2)
        effective_disc_pct = Decimal("1.0") - sequential_net
        additive_disc_pct = d1 + d2
        # 3.1744% != 3.2000%
        self.assertNotEqual(effective_disc_pct, additive_disc_pct)
        self.assertAlmostEqual(float(effective_disc_pct), 0.031744, places=6)

    def test_baseline_footer_discount_equals_line_aggregate(self):
        """In baseline 2026-08, sales_orders.csv discount_dpp is an exact aggregate of line discounts."""
        import csv
        from collections import defaultdict
        pack_dir = AUG_PACK_DIR
        if not pack_dir.exists():
            self.skipTest("Pack data not available")
        with open(pack_dir / "order_lines.csv", encoding="utf-8-sig") as f_lines:
            lines = list(csv.DictReader(f_lines))
        with open(pack_dir / "sales_orders.csv", encoding="utf-8-sig") as f_sos:
            sos = list(csv.DictReader(f_sos))

        line_sum_by_so = defaultdict(Decimal)
        for line_row in lines:
            line_sum_by_so[line_row["so_number"]] += Decimal(line_row.get("discount_dpp") or "0")

        mismatches = 0
        for so in sos:
            so_num = so["so_number"]
            so_disc = Decimal(so.get("discount_dpp") or "0")
            line_disc = line_sum_by_so[so_num]
            if abs(so_disc - line_disc) > Decimal("0.01"):
                mismatches += 1

        self.assertEqual(mismatches, 0, "All 1240 SOs in baseline have header discount equal to line sum.")


if __name__ == "__main__":
    unittest.main()


class TestPeriodEventChronology(unittest.TestCase):
    def setUp(self):
        self.loader = GenericPeriodPackLoader(env=None, pack_dir=AUG_PACK_DIR, dry_run=False)
        self.loader.reader = SimpleNamespace(
            po_headers=[{"po_number": "PO1", "order_date": "2026-08-24", "arrival_maumbi_date": "2026-08-27"}],
            po_lines=[{"po_number": "PO1", "sku_code": "SKU1", "lot_number": "LOT1", "qty_cartons": "10"}],
            sales_orders=[{"so_number": "SO1", "date_order": "2026-08-25"}],
            order_lines=[{"so_number": "SO1", "sku_code": "SKU1", "lot_number": "LOT1", "qty_cartons": "2"}],
            deliveries=[{"so_number": "SO1", "scheduled_delivery_date": "2026-08-27"}],
            rejections=[],
            invoices=[{"so_number": "SO1", "invoice_number": "INV1", "date_invoice": "2026-08-27"}],
            ar_collections=[{"payment_id": "PAY1", "payment_date": "2026-08-28"}],
            ap_payments=[],
            opex=[],
        )

    def test_dispatcher_interleaves_order_receipt_and_finance(self):
        events = [(phase, rows) for day in self.loader._period_event_days() for phase, rows in day.items() if rows]
        self.assertEqual([phase for phase, _ in events], ["po", "so", "receipt", "dispatch", "invoices", "ar"])
        self.assertEqual(events[3][1], self.loader.reader.sales_orders)

    def test_oracle_detects_future_receipt_with_same_closing_quantity(self):
        from scripts.ops.verify_disposable_period_pack import source_dispatch_shortages

        opening = {"stock": {}, "pending_dos": {}}
        self.assertEqual(source_dispatch_shortages(self.loader.reader, opening, []), [])
        self.loader.reader.po_headers[0]["arrival_maumbi_date"] = "2026-08-29"
        self.assertEqual(
            source_dispatch_shortages(self.loader.reader, opening, []),
            [("2026-08-27", "SO1", "SKU1||LOT1", "0", "2")],
        )


class TestHistoricalCommercialOracle(unittest.TestCase):
    def test_rejects_same_total_discount_swap_and_unverified_promo_binding(self):
        from scripts.ops.verify_disposable_period_pack import commercial_line_differences

        source = [
            {"so_number": "SO1", "sku_code": sku, "qty_cartons": "1", "carton_qty": "1",
             "unit_price_dpp": "100", "discount_pct": discount, "promo_id": promo}
            for sku, discount, promo in (("A", "8", "SOURCE-A"), ("B", "2", ""))
        ]
        first = ("SO1", "A", Decimal(1), Decimal(100), Decimal(8), "SOURCE-A", False)
        second = ("SO1", "B", Decimal(1), Decimal(100), Decimal(2), "", False)
        self.assertFalse(any(commercial_line_differences(source, [first, second])))
        swapped = [first[:4] + (Decimal(2),) + first[5:], second[:4] + (Decimal(8),) + second[5:]]
        self.assertTrue(all(commercial_line_differences(source, swapped)))
        self.assertTrue(all(commercial_line_differences(source, [first[:-1] + (True,), second])))
