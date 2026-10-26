#!/usr/bin/env python3
"""Unit tests untuk Canonical Perpetual Loader Adapter (scripts/load_canonical_perpetual.py).

Menguji:
1. Verifikasi 15 hash SHA-256 kanonikal LF dan penolakan jika berkas/deklarasi hilang.
2. Resolusi ref stabil customer (1.324/1.324 SO & 967/967 AR) dan salesman (1.324/1.324 SO).
3. Pemetaan saldo awal (initial_stock_20260701.csv): qty_cartons_on_hand, qty_units, lot, expiry.
4. Pemetaan baris pesanan (perpetual_order_lines.csv): qty base unit, carton price, line DPP.
5. Pemetaan pembayaran AR & AP dengan field yang benar (net_cash_collected_total).
6. Pemetaan 9 retur karantina dan nilai aset COGS Rp 1.963.200.
7. Delegator scripts/load_historical_simulation.py dengan init_globals env.
8. Uji idempotensi pemuatan ganda adapter menggunakan mock model Odoo 19.
"""

import csv
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REG_DIR = ROOT / "data" / "registers"

from scripts.load_canonical_perpetual import (  # noqa: E402
    build_ap_payment_payload,
    build_ar_payment_payload,
    build_opening_quant_payload,
    build_order_line_payload,
    build_rejection_payload,
    canonical_file_hash,
    extract_ref,
    read_register_csv,
    verify_canonical_fingerprints,
    CanonicalPerpetualAdapter,
    REQUIRED_CANONICAL_FILES,
)


class TestCanonicalLoaderAdapter(unittest.TestCase):
    def test_canonical_fingerprints_integrity(self):
        """Memastikan seluruh 15 hash register kanonikal valid dan cocok dengan rekonsiliasi."""
        meta = verify_canonical_fingerprints(REG_DIR)
        expected_hashes = meta["input_dataset_sha256"]
        self.assertEqual(len(expected_hashes), 15)
        for fname, exp_hash in expected_hashes.items():
            fpath = REG_DIR / fname
            self.assertTrue(fpath.is_file(), f"File {fname} harus ada")
            self.assertEqual(canonical_file_hash(fpath), exp_hash)

    def test_fail_fast_on_missing_canonical_file(self):
        """Adapter harus raise FileNotFoundError jika berkas register kanonikal hilang."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            # Salin hanya sebagian file
            for f in REQUIRED_CANONICAL_FILES[:3]:
                (tmp_path / f).write_text("test", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                verify_canonical_fingerprints(tmp_path)

    def test_fail_fast_on_incomplete_metadata_hashes(self):
        """Adapter harus menolak jika metadata JSON tidak memuat seluruh 15 file kanonikal."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            for f in REQUIRED_CANONICAL_FILES:
                (tmp_path / f).write_text("dummy", encoding="utf-8")
            # Metadata tidak lengkap (hanya mendeklarasikan 1 file)
            hash_val = canonical_file_hash(tmp_path / "customer_registry_354.csv")
            fake_meta = {"input_dataset_sha256": {"customer_registry_354.csv": hash_val}}
            meta_file = tmp_path / "canonical_financial_reconciliation_july_2026.json"
            meta_file.write_text(json.dumps(fake_meta), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_canonical_fingerprints(tmp_path)

    def test_customer_and_salesman_ref_extraction_and_resolution(self):
        """Memastikan 100% dari 1.324 SO dan 967 AR terekstraksi ke customer ref & salesman yang valid."""
        with open(REG_DIR / "customer_registry_354.csv", encoding="utf-8") as f:
            valid_cust_refs = {r["ref"] for r in csv.DictReader(f)}
        self.assertEqual(len(valid_cust_refs), 354)

        so_rows = read_register_csv("perpetual_sales_orders.csv")
        self.assertEqual(len(so_rows), 1324)

        for so in so_rows:
            cust_ref = extract_ref(so["customer"])
            self.assertIn(cust_ref, valid_cust_refs, f"Customer label '{so['customer']}' gagal di-resolve ke ref!")
            sls_code = extract_ref(so["salesman"])
            self.assertIn(sls_code, ["CVS-01", "CVS-02", "MGT-01", "SLS-01", "SLS-02", "SLS-03"])

        ar_rows = read_register_csv("perpetual_ar_collections.csv")
        self.assertEqual(len(ar_rows), 967)

        for ar in ar_rows:
            cust_ref = extract_ref(ar["customer"])
            self.assertIn(cust_ref, valid_cust_refs, f"AR Customer label '{ar['customer']}' gagal di-resolve ke ref!")

    def test_opening_stock_payload_mapping(self):
        """Memverifikasi pemetaan saldo awal 150 SKU: qty_cartons_on_hand, lot, dan unit cost."""
        stock_rows = read_register_csv("initial_stock_20260701.csv")
        self.assertEqual(len(stock_rows), 150)

        total_cartons = 0.0
        for row in stock_rows:
            p = build_opening_quant_payload(row)
            self.assertGreater(p["qty_cartons"], 0)
            self.assertEqual(p["qty_units"], p["qty_cartons"] * float(row["carton_qty"]))
            self.assertTrue(p["lot_number"].startswith("LOT-"), f"Lot invalid: {p['lot_number']}")
            is_valid_exp = len(p["expiry_date"]) == 10 and p["expiry_date"].startswith("202")
            self.assertTrue(is_valid_exp, f"Expiry invalid: {p['expiry_date']}")
            total_cartons += p["qty_cartons"]

        self.assertEqual(total_cartons, 29804.0)

    def test_order_line_payload_math_and_units(self):
        """Memverifikasi baris pesanan: konversi kuantitas base unit, carton price, dan total gross DPP."""
        lines = read_register_csv("perpetual_order_lines.csv")
        self.assertEqual(len(lines), 2738)

        total_gross_dpp = Decimal("0.00")
        for lrow in lines:
            p = build_order_line_payload(lrow)
            self.assertEqual(p["qty_units"], p["qty_cartons"] * p["carton_qty"])
            expected_line_dpp = Decimal(str(p["qty_cartons"])) * Decimal(str(p["carton_price_dpp"]))
            self.assertEqual(expected_line_dpp, Decimal(str(p["line_gross_dpp"])))
            self.assertTrue(p["lot_number"])
            total_gross_dpp += Decimal(str(p["line_gross_dpp"]))

        self.assertEqual(total_gross_dpp, Decimal("6065892600.00"))

    def test_ar_collection_payload_and_field_names(self):
        """Memverifikasi field AR: net_cash_collected_total dan keberadaan invoice number."""
        inv_rows = read_register_csv("perpetual_invoices.csv")
        inv_numbers = {r["invoice_number"] for r in inv_rows}
        self.assertEqual(len(inv_numbers), 1324)

        ar_rows = read_register_csv("perpetual_ar_collections.csv")
        self.assertEqual(len(ar_rows), 967)

        total_collected_dpp = Decimal("0.00")
        for ar in ar_rows:
            p = build_ar_payment_payload(ar)
            self.assertIn(p["invoice_number"], inv_numbers)
            self.assertGreater(p["net_cash_collected_total"], 0)
            total_collected_dpp += Decimal(str(p["net_cash_collected_dpp"]))

        self.assertEqual(total_collected_dpp, Decimal("3448145006.75"))

    def test_ap_payment_payload(self):
        """Memverifikasi pembayaran AP: referensi PO riil dan total nominal bayar."""
        headers = read_register_csv("inbound_po_intransit_june_headers.csv")
        po_numbers = {h["po_number"] for h in headers}

        ap_rows = read_register_csv("perpetual_ap_payments.csv")
        self.assertEqual(len(ap_rows), 4)

        total_ap_paid = Decimal("0.00")
        for ap in ap_rows:
            p = build_ap_payment_payload(ap)
            self.assertIn(p["po_number"], po_numbers)
            total_ap_paid += Decimal(str(p["amount_paid_dpp"]))

        self.assertEqual(total_ap_paid, Decimal("6597474800.00"))

    def test_rejection_payload_and_quarantine_asset(self):
        """Memverifikasi 9 retur karantina: jumlah karton = 9 dan nilai aset COGS = Rp 1.963.200."""
        rej_rows = read_register_csv("perpetual_order_rejections.csv")
        self.assertEqual(len(rej_rows), 9)

        total_rej_cartons = 0.0
        total_rej_cogs = Decimal("0.00")
        for rej in rej_rows:
            p = build_rejection_payload(rej)
            total_rej_cartons += p["qty_cartons"]
            total_rej_cogs += Decimal(str(p["cogs_subtotal"]))

        self.assertEqual(total_rej_cartons, 9.0)
        self.assertEqual(total_rej_cogs, Decimal("1963200.00"))

    def test_adapter_idempotency_simulation_with_mock_environment(self):
        """Menguji CanonicalPerpetualAdapter secara nyata terhadap mock Odoo Environment: Run 1 vs Run 2."""
        class MockRecordList(list):
            def filtered(self, func):
                return MockRecordList([x for x in self if func(x)])

            def reconcile(self):
                pass

        class MockRecord:
            def __init__(self, vals, model_name, rec_id, env=None):
                self._vals = vals or {}
                self._model = model_name
                self.id = rec_id
                self.state = "draft"
                self.picking_ids = MockRecordList()
                self.line_ids = MockRecordList()
                self.reconciled = False
                self._env = env

            def __getattr__(self, name):
                if name == "partner_id":
                    p_val = self._vals.get("partner_id", 1)
                    if isinstance(p_val, MockRecord):
                        return p_val
                    if self._env and "res.partner" in self._env:
                        existing = self._env["res.partner"].store.get(p_val)
                        return existing or MockRecord({"name": "Partner"}, "res.partner", p_val, self._env)
                    return MockRecord({"name": "Partner"}, "res.partner", p_val)
                elif name == "account_id":
                    return MockRecord({"account_type": "asset_receivable"}, "account.account", 1)
                return self._vals.get(name, False)

            def action_confirm(self):
                self.state = "sale"

            def button_confirm(self):
                self.state = "purchase"

            def action_post(self):
                self.state = "posted"

            def button_validate(self):
                self.state = "done"

        class MockModel:
            def __init__(self, name, env=None):
                self.name = name
                self.store = {}
                self.seq = 1
                self.env = env

            def sudo(self):
                return self

            def with_context(self, **kw):
                return self

            def search(self, domain=None, limit=None):
                domain = domain or []
                results = []
                for rec in self.store.values():
                    match = True
                    for term in domain:
                        field, op, val = term
                        rec_val = getattr(rec, field, False)
                        if op == "=" and rec_val != val:
                            match = False
                        elif op == "!=" and rec_val == val:
                            match = False
                        elif op == "ilike" and (not rec_val or val.lower() not in str(rec_val).lower()):
                            match = False
                    if match:
                        results.append(rec)
                        if limit == 1:
                            break
                if limit == 1:
                    return results[0] if results else False
                return results

            def create(self, vals):
                rec = MockRecord(vals, self.name, self.seq, env=self.env)
                self.store[self.seq] = rec
                self.seq += 1
                return rec

        class MockCompany:
            def __init__(self):
                self.id = 1
                self.partner_id = None

        class MockCursor:
            def commit(self):
                pass

            def rollback(self):
                pass

        class MockEnv(dict):
            def __init__(self):
                super().__init__()
                self.cr = MockCursor()
                self.company = MockCompany()
                models = [
                    "res.partner", "product.product", "res.users", "stock.quant", "stock.location",
                    "stock.lot", "purchase.order", "sale.order", "account.move", "account.payment", "stock.picking",
                ]
                for m in models:
                    self[m] = MockModel(m, env=self)
                self.company.partner_id = self["res.partner"].create({"name": "PT MDU", "ref": "COMPANY"})

            def ref(self, xml_id, raise_if_not_found=False):
                return MockRecord({"name": xml_id}, "base", 1)

        mock_env = MockEnv()

        # Prepopulate partners & products dari register
        cust_rows = read_register_csv("customer_registry_354.csv")
        for c in cust_rows:
            mock_env["res.partner"].create({"name": c["name"], "ref": c["ref"]})

        # Prepopulate 4 principal partners
        principals = [
            "PT Sayapp Mas Utamma", "PT Santos Jaya Abadii", "PT Mayyora Indahh Tbk", "PT Unileverr Indonesia Tbk",
            "PRIN-WINGS", "PRIN-KAPALAPI", "PRIN-MAYORA", "PRIN-UNILEVER",
        ]
        for p in principals:
            mock_env["res.partner"].create({"name": p, "ref": p})

        # Prepopulate 150 SKUs
        prod_rows = read_register_csv("initial_stock_20260701.csv")
        for pr in prod_rows:
            mock_env["product.product"].create({"name": pr["product_name"], "default_code": pr["sku_code"]})

        # Prepopulate internal warehouse location
        mock_env["stock.location"].create({"name": "WH/Stock", "usage": "internal"})

        # Jalankan RUN 1 dengan CanonicalPerpetualAdapter
        adapter_run1 = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)
        adapter_run1.run_all()

        # Verifikasi hasil Run 1
        self.assertEqual(adapter_run1.stats["so_created"], 1324)
        self.assertEqual(adapter_run1.stats["invoices_created"], 1324)
        self.assertEqual(adapter_run1.stats["ar_payments_created"], 967)
        self.assertEqual(adapter_run1.stats["ap_payments_created"], 4)
        self.assertEqual(adapter_run1.stats["opex_moves_created"], 30)
        self.assertEqual(adapter_run1.stats["opening_quants"], 150)
        self.assertEqual(adapter_run1.stats["po_created"], 5)
        self.assertEqual(adapter_run1.stats["quarantine_rejections"], 9)

        # Jalankan RUN 2 (Uji Idempotensi Sejati: harus 0 create baru, seluruhnya skipped)
        adapter_run2 = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)
        adapter_run2.run_all()

        self.assertEqual(adapter_run2.stats["so_created"], 0)
        self.assertEqual(adapter_run2.stats["skipped_so"], 1324)
        self.assertEqual(adapter_run2.stats["invoices_created"], 0)
        self.assertEqual(adapter_run2.stats["skipped_invoices"], 1324)
        self.assertEqual(adapter_run2.stats["ar_payments_created"], 0)
        self.assertEqual(adapter_run2.stats["skipped_ar"], 967)
        self.assertEqual(adapter_run2.stats["ap_payments_created"], 0)
        self.assertEqual(adapter_run2.stats["skipped_ap"], 4)
        self.assertEqual(adapter_run2.stats["opex_moves_created"], 0)
        self.assertEqual(adapter_run2.stats["skipped_opex"], 30)
        self.assertEqual(adapter_run2.stats["opening_quants"], 0)
        self.assertEqual(adapter_run2.stats["skipped_opening_quants"], 150)
        self.assertEqual(adapter_run2.stats["po_created"], 0)
        self.assertEqual(adapter_run2.stats["skipped_po"], 5)
        self.assertEqual(adapter_run2.stats["quarantine_rejections"], 0)
        self.assertEqual(adapter_run2.stats["skipped_quarantine"], 9)


if __name__ == "__main__":
    unittest.main()
