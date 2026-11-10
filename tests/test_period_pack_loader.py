"""Unit tests for Generic Period Pack Loader (Fase F4).

Validates:
1. Manifest verification (LF SHA-256 integrity, tamper detection, missing files).
2. Continuity & preflight rules (master preservation, previous period baseline).
3. Idempotency logic and fail-closed drift detection.
4. Cross-period AP settlement binding.
"""

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

REPO_ROOT = Path(__file__).resolve().parents[1]
AUG_PACK_DIR = REPO_ROOT / "data" / "registers" / "periods" / "2026-08"


class MockModel:
    """Mock Odoo model for unit testing loader logic offline."""

    def __init__(self, records=None, count_val=0):
        self._records = records or []
        self._count_val = count_val

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
                    elif op == "in" and r_val not in val:
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
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "stock.location": MockModel(records=[mock_loc]),
            "res.partner": MockModel(count_val=354),
            "product.product": MockModel(count_val=150),
            "sale.order": MockModel(records=[existing_so], count_val=1324),
            "account.move": MockModel(count_val=1),
            "purchase.order": MockModel(),
            "account.payment": MockModel(),
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
        )
        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "sale.order": MockModel(records=[drifted_so], count_val=1324),
            "account.move": MockModel(),
            "purchase.order": MockModel(),
            "account.payment": MockModel(),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, strict=True)
        loader.company = mock_company
        with self.assertRaises(StateInconsistencyError) as ctx:
            loader.evaluate_dry_run()
        self.assertIn("Drift detected on existing SO-202608-0001", str(ctx.exception))

    def test_ap_payment_settles_july_unilever_bill(self):
        mock_company = MockRecord(id=1, name="PT Salva Inti Mandiri")
        mock_partner_unilever = MockRecord(id=50, name="PT Unilever Indonesia")
        mock_july_bill = MockRecord(
            id=201,
            company_id=1,
            move_type="in_invoice",
            state="posted",
            payment_state="not_paid",
            amount_total=2899971200.00,
            ref="PO-2026-06-05",
            partner_id=mock_partner_unilever,
        )
        mock_journal_bank = MockRecord(id=5, company_id=1, type="bank")

        mock_models = {
            "res.company": MockModel(records=[mock_company]),
            "account.move": MockModel(records=[mock_july_bill]),
            "account.journal": MockModel(records=[mock_journal_bank]),
            "account.payment": MockModel(),
        }
        env = MockEnv(mock_models)
        loader = GenericPeriodPackLoader(env=env, pack_dir=AUG_PACK_DIR, dry_run=True, company_id=1)
        loader.company = mock_company

        # In dry run, AP should detect 1 to reconcile
        plan = loader.evaluate_dry_run()
        self.assertEqual(plan["ap"]["to_reconcile"], 1)
        self.assertEqual(plan["ap"]["to_skip"], 0)


if __name__ == "__main__":
    unittest.main()
