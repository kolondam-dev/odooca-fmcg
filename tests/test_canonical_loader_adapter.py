#!/usr/bin/env python3
"""Unit tests untuk Canonical Perpetual Loader Adapter (scripts/load_canonical_perpetual.py).

Menutup seluruh temuan supervisi pada PR #15:
1. Opening stock idempoten bahkan setelah kuantitas on-hand berkurang (quant reduction).
2. Kuantitas dan nilai invoice net of rejections (menutup selisih Rp 2.168.937,60 DPP).
3. Pemetaan pergerakan stok: picking PO, DO, dan karantina dengan move lines, lot, dan qty selesai.
4. Pembukuan diskon pembayaran awal (early cash discount) dan eksekusi rekonsiliasi AR/AP.
5. Pencegahan masking error: penghapusan try-except pass, fail-fast salesman tanpa admin fallback,
   serta assert integritas dilakukan sebelum commit DB (sehingga rollback berfungsi).
6. Pembuktian rantai transaksi kecil (small transaction chain simulation: limit_orders=1).
7. Pengujian adapter pada mock Odoo environment dengan 15 hash fingerprint LF utuh.
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


class MockRecordList(list):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mock_noop_reconcile = False
        self.mock_partial_reconcile = False

    def filtered(self, func):
        res = MockRecordList([x for x in self if func(x)])
        res.mock_noop_reconcile = self.mock_noop_reconcile
        res.mock_partial_reconcile = self.mock_partial_reconcile
        return res

    def __or__(self, other):
        combined = list(self)
        for item in other:
            if item not in combined:
                combined.append(item)
        res = MockRecordList(combined)
        res.mock_noop_reconcile = self.mock_noop_reconcile or getattr(other, "mock_noop_reconcile", False)
        res.mock_partial_reconcile = self.mock_partial_reconcile or getattr(other, "mock_partial_reconcile", False)
        return res

    def reconcile(self):
        if self.mock_noop_reconcile:
            return
        if self.mock_partial_reconcile:
            # Simulasi celah: hanya 2 baris pertama diselesaikan, baris diskon tertinggal
            for idx, rec in enumerate(self):
                if idx < 2:
                    rec.reconciled = True
                else:
                    rec.reconciled = False
            return
        for rec in self:
            rec.reconciled = True
            pay_obj = getattr(rec, "_payment", None)
            if pay_obj:
                pay_obj.state = "paid"


class MockRecord:
    def __init__(self, vals, model_name, rec_id, env=None):
        self._vals = vals.copy() if vals else {}
        self._model = model_name
        self.id = rec_id
        self.state = self._vals.get("state", "draft")
        self.picking_ids = MockRecordList()
        self.line_ids = MockRecordList()
        self.reconciled = False
        self._env = env
        self.scheduled_date = False
        self.mock_wizard_mode = False
        self.mock_partial_reconcile = False

    def __eq__(self, other):
        if self is other:
            return True
        if isinstance(other, MockRecord):
            return self is other
        if isinstance(other, int):
            return self.id == other
        return False

    def __getattr__(self, name):
        if name == "partner_id":
            p_val = self._vals.get("partner_id", 1)
            if isinstance(p_val, MockRecord):
                return p_val
            if self._env and "res.partner" in self._env:
                existing = self._env["res.partner"].store.get(p_val)
                return existing or MockRecord({"name": "Partner"}, "res.partner", p_val, self._env)
            return MockRecord({"name": "Partner"}, "res.partner", p_val)
        if name in ("location_id", "location_dest_id"):
            l_val = self._vals.get(name)
            if isinstance(l_val, MockRecord):
                return l_val
            if self._env and "stock.location" in self._env and l_val:
                existing = self._env["stock.location"].store.get(l_val)
                if existing:
                    return existing
            return MockRecord({"name": "Location", "usage": "internal"}, "stock.location", l_val or 1, self._env)
        if name in self._vals:
            return self._vals[name]
        if name == "account_id":
            act_type = self._vals.get("account_type", "asset_receivable")
            return MockRecord({"account_type": act_type}, "account.account", 1, self._env)
        elif name == "company_id":
            return self._env.company if self._env else MockRecord({"name": "PT MDU"}, "res.company", 1)
        return False

    def __setattr__(self, name, value):
        valid_attrs = (
            "id", "state", "picking_ids", "line_ids", "reconciled",
            "scheduled_date", "mock_wizard_mode", "mock_partial_reconcile", "move_id",
        )
        if name.startswith("_") or name in valid_attrs:
            super().__setattr__(name, value)
        else:
            self._vals[name] = value

    def action_confirm(self):
        self.state = "sale"
        if self._model == "sale.order" and self._env and "stock.picking" in self._env:
            move_lines = []
            for item in self._vals.get("order_line", []):
                line_data = item[2] if isinstance(item, (list, tuple)) and len(item) == 3 else {}
                # Mock tidak meng-inject lot_id otomatis; lot harus dipetakan oleh adapter!
                move_lines.append(MockRecord({
                    "product_id": line_data.get("product_id"),
                    "lot_id": False,
                    "quantity": line_data.get("product_uom_qty", 0.0),
                    "qty_done": 0.0,
                }, "stock.move.line", len(move_lines) + 1, self._env))

            pick = self._env["stock.picking"].create({
                "origin": self._vals.get("client_order_ref", "SO"),
                "picking_type_code": "outgoing",
                "state": "assigned",
                "move_line_ids": MockRecordList(move_lines),
            })
            self.picking_ids = MockRecordList([pick])

    def button_confirm(self):
        self.state = "purchase"
        if self._model == "purchase.order" and self._env and "stock.picking" in self._env:
            move_lines = []
            for item in self._vals.get("order_line", []):
                line_data = item[2] if isinstance(item, (list, tuple)) and len(item) == 3 else {}
                # Mock tidak meng-inject lot_id otomatis; lot harus dipetakan oleh adapter!
                move_lines.append(MockRecord({
                    "product_id": line_data.get("product_id"),
                    "lot_id": False,
                    "quantity": line_data.get("product_qty", 0.0),
                    "qty_done": 0.0,
                }, "stock.move.line", len(move_lines) + 1, self._env))

            pick = self._env["stock.picking"].create({
                "origin": self._vals.get("origin", "PO"),
                "picking_type_code": "incoming",
                "state": "assigned",
                "move_line_ids": MockRecordList(move_lines),
            })
            self.picking_ids = MockRecordList([pick])

    def button_validate(self):
        if getattr(self, "mock_wizard_mode", False):
            return {
                "type": "ir.actions.act_window",
                "res_model": "stock.immediate.transfer",
            }
        self.state = "done"
        return True

    def action_post(self):
        self.state = "posted"
        if self._model == "account.move":
            m_type = self._vals.get("move_type", "entry")
            if m_type == "out_invoice":
                total_amt = sum(
                    inv_line[2].get("quantity", 0.0)
                    * inv_line[2].get("price_unit", 0.0)
                    * (1.0 - inv_line[2].get("discount", 0.0) / 100.0)
                    for inv_line in self._vals.get("invoice_line_ids", [])
                    if isinstance(inv_line, (list, tuple)) and len(inv_line) == 3
                )
                ar_line = MockRecord({
                    "name": self._vals.get("ref", "AR Invoice"),
                    "account_id": MockRecord({"account_type": "asset_receivable"}, "account.account", 1, self._env),
                    "debit": total_amt,
                    "credit": 0.0,
                    "reconciled": False,
                }, "account.move.line", 1, self._env)
                inc_line = MockRecord({
                    "name": "Sales Income",
                    "account_id": MockRecord({"account_type": "income"}, "account.account", 2, self._env),
                    "debit": 0.0,
                    "credit": total_amt,
                    "reconciled": False,
                }, "account.move.line", 2, self._env)
                self.line_ids = MockRecordList([ar_line, inc_line])
            elif m_type == "in_invoice":
                total_amt = sum(
                    inv_line[2].get("quantity", 1.0) * inv_line[2].get("price_unit", 0.0)
                    for inv_line in self._vals.get("invoice_line_ids", [])
                    if isinstance(inv_line, (list, tuple)) and len(inv_line) == 3
                )
                ap_line = MockRecord({
                    "name": self._vals.get("ref", "AP Bill"),
                    "account_id": MockRecord({"account_type": "liability_payable"}, "account.account", 3, self._env),
                    "debit": 0.0,
                    "credit": total_amt,
                    "reconciled": False,
                }, "account.move.line", 1, self._env)
                exp_line = MockRecord({
                    "name": "Expense Line",
                    "account_id": MockRecord({"account_type": "expense"}, "account.account", 4, self._env),
                    "debit": total_amt,
                    "credit": 0.0,
                    "reconciled": False,
                }, "account.move.line", 2, self._env)
                self.line_ids = MockRecordList([ap_line, exp_line])
            elif m_type == "entry":
                lines = []
                for idx, item in enumerate(self._vals.get("line_ids", []), start=1):
                    ldata = item[2] if isinstance(item, (list, tuple)) and len(item) == 3 else {}
                    acc_type = "asset_receivable" if "Piutang" in ldata.get("name", "") else "expense"
                    lines.append(MockRecord({
                        "name": ldata.get("name", "Journal Line"),
                        "account_id": MockRecord({"account_type": acc_type}, "account.account", 5, self._env),
                        "debit": ldata.get("debit", 0.0),
                        "credit": ldata.get("credit", 0.0),
                        "reconciled": False,
                    }, "account.move.line", idx, self._env))
                self.line_ids = MockRecordList(lines)
        elif self._model == "account.payment":
            self.state = "in_process"
            p_type = self._vals.get("payment_type", "inbound")
            amt = float(self._vals.get("amount", 0.0))
            pay_ref = self._vals.get("ref", self._vals.get("memo", ""))
            if p_type == "inbound":
                cash_line = MockRecord({
                    "name": pay_ref or "Cash In",
                    "account_id": MockRecord({"account_type": "asset_cash"}, "account.account", 6, self._env),
                    "debit": amt,
                    "credit": 0.0,
                    "reconciled": False,
                }, "account.move.line", 1, self._env)
                ar_line = MockRecord({
                    "name": pay_ref or "AR Payment",
                    "account_id": MockRecord({"account_type": "asset_receivable"}, "account.account", 1, self._env),
                    "debit": 0.0,
                    "credit": amt,
                    "reconciled": False,
                }, "account.move.line", 2, self._env)
                ar_line._payment = self
                self.line_ids = MockRecordList([cash_line, ar_line])
                if getattr(self, "mock_partial_reconcile", False):
                    self.line_ids.mock_partial_reconcile = True
            else:
                ap_line = MockRecord({
                    "name": pay_ref or "AP Payment",
                    "account_id": MockRecord({"account_type": "liability_payable"}, "account.account", 3, self._env),
                    "debit": amt,
                    "credit": 0.0,
                    "reconciled": False,
                }, "account.move.line", 1, self._env)
                cash_line = MockRecord({
                    "name": pay_ref or "Cash Out",
                    "account_id": MockRecord({"account_type": "asset_cash"}, "account.account", 6, self._env),
                    "debit": 0.0,
                    "credit": amt,
                    "reconciled": False,
                }, "account.move.line", 2, self._env)
                ap_line._payment = self
                self.line_ids = MockRecordList([ap_line, cash_line])
                if getattr(self, "mock_partial_reconcile", False):
                    self.line_ids.mock_partial_reconcile = True

            # Odoo 19: account.payment memiliki move_id relasional yang berstatus posted
            self.move_id = MockRecord({"state": "posted", "ref": pay_ref}, "account.move", self.id, self._env)
            self.move_id.line_ids = self.line_ids


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
                if op == "=":
                    if hasattr(rec_val, "id") and isinstance(val, int):
                        if rec_val.id != val:
                            match = False
                    elif hasattr(val, "id") and isinstance(rec_val, int):
                        if rec_val != val.id:
                            match = False
                    elif rec_val != val:
                        match = False
                elif op == "!=" and rec_val == val:
                    match = False
                elif op == "ilike" and (not rec_val or val.lower() not in str(rec_val).lower()):
                    match = False
                elif op in ("=like", "like"):
                    clean = str(val).replace("%", "")
                    if clean.lower() not in str(rec_val).lower():
                        match = False
            if match:
                results.append(rec)
                if limit == 1:
                    break
        if limit == 1:
            return results[0] if results else False
        return results

    def browse(self, ids):
        if isinstance(ids, (list, tuple)):
            return [self.store.get(i) for i in ids if self.store.get(i)]
        return self.store.get(ids) or MockRecord({}, self.name, ids, env=self.env)

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
    def __init__(self):
        self.committed = False
        self.rollbacked = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rollbacked = True


class MockEnv(dict):
    def __init__(self):
        super().__init__()
        self.cr = MockCursor()
        self.company = MockCompany()
        models = [
            "res.partner", "product.product", "res.users", "stock.quant", "stock.location",
            "stock.lot", "purchase.order", "sale.order", "account.move", "account.payment",
            "stock.picking", "account.account",
        ]
        for m in models:
            self[m] = MockModel(m, env=self)
        self.company.partner_id = self["res.partner"].create({"name": "PT MDU", "ref": "COMPANY"})

    def ref(self, xml_id, raise_if_not_found=False):
        return MockRecord({"name": xml_id}, "base", 1, self)


def setup_standard_mock_env():
    mock_env = MockEnv()

    # Prepopulate partners & products
    cust_rows = read_register_csv("customer_registry_354.csv")
    for c in cust_rows:
        mock_env["res.partner"].create({"name": c["name"], "ref": c["ref"]})

    principals = [
        "PT Sayapp Mas Utamma", "PT Santos Jaya Abadii", "PT Mayyora Indahh Tbk", "PT Unileverr Indonesia Tbk",
        "PRIN-WINGS", "PRIN-KAPALAPI", "PRIN-MAYORA", "PRIN-UNILEVER",
    ]
    for p in principals:
        mock_env["res.partner"].create({"name": p, "ref": p})

    # Prepopulate salesman users (CVS-01, CVS-02, MGT-01, SLS-01, SLS-02, SLS-03)
    salesmen = ["CVS-01", "CVS-02", "MGT-01", "SLS-01", "SLS-02", "SLS-03"]
    for s in salesmen:
        mock_env["res.users"].create({"name": s, "login": s.lower()})

    prod_rows = read_register_csv("initial_stock_20260701.csv")
    for pr in prod_rows:
        mock_env["product.product"].create({"name": pr["product_name"], "default_code": pr["sku_code"]})

    mock_env["stock.location"].create({"name": "WH/Stock", "usage": "internal"})
    return mock_env


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

    # -------------------------------------------------------------------------
    # Temuan 1: Opening stock tetap idempoten setelah pengurangan stok
    # -------------------------------------------------------------------------
    def test_opening_stock_idempotency_after_quantity_reduction(self):
        """Opening stock tidak boleh membuat quant baru ketika stok berkurang karena DO downstream."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        # Muat saldo awal pertama kali
        adapter.load_opening_stock()
        self.assertEqual(adapter.stats["opening_quants"], 150)
        self.assertEqual(adapter.stats["skipped_opening_quants"], 0)

        # Kurangi satu unit pada salah satu quant hasil mock
        first_quant = list(mock_env["stock.quant"].store.values())[0]
        initial_qty = first_quant.quantity
        first_quant.quantity -= 1.0
        first_quant.inventory_quantity -= 1.0

        # Jalankan load_opening_stock() lagi
        adapter.stats["opening_quants"] = 0
        adapter.stats["skipped_opening_quants"] = 0
        adapter.load_opening_stock()

        # Harus 0 quant baru, 150 skipped, dan tidak menduplikasi baris quant
        self.assertEqual(adapter.stats["opening_quants"], 0)
        self.assertEqual(adapter.stats["skipped_opening_quants"], 150)
        self.assertEqual(len(mock_env["stock.quant"].store), 150)
        self.assertEqual(first_quant.quantity, initial_qty - 1.0)

    # -------------------------------------------------------------------------
    # Temuan 2: Invoice net of rejection menutup selisih Rp 2.168.937,60 DPP
    # -------------------------------------------------------------------------
    def test_invoices_net_of_rejections_reconciliation(self):
        """Invoice harus memotong 9 retur transit sehingga total DPP persis sama dengan kanonikal."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        adapter.load_sales_deliveries_and_invoices()

        inv_store = mock_env["account.move"].store
        created_invoices = [m for m in inv_store.values() if m._vals.get("move_type") == "out_invoice"]
        self.assertEqual(len(created_invoices), 1324)

        # Hitung total DPP seluruh invoice yang terbentuk
        total_inv_dpp = Decimal("0.00")
        for inv in created_invoices:
            for item in inv._vals.get("invoice_line_ids", []):
                line_data = item[2]
                qty = Decimal(str(line_data["quantity"]))
                price = Decimal(str(line_data["price_unit"]))
                disc = Decimal(str(line_data.get("discount", 0.0)))
                line_net = qty * price * (Decimal("1.00") - disc / Decimal("100.00"))
                total_inv_dpp += line_net

        # Canonical total DPP di perpetual_invoices.csv adalah Rp 5.782.481.176,40
        canonical_inv_rows = read_register_csv("perpetual_invoices.csv")
        canonical_dpp_expected = sum(Decimal(r["dpp_amount"]) for r in canonical_inv_rows)
        self.assertEqual(canonical_dpp_expected, Decimal("5782481176.40"))
        self.assertEqual(round(total_inv_dpp, 2), canonical_dpp_expected)

        # Gross SO net sebelum retur adalah Rp 5.784.650.114,00
        # Selisih terhadap canonical adalah tepat Rp 2.168.937,60
        so_gross_net = Decimal("5784650114.00")
        self.assertEqual(so_gross_net - canonical_dpp_expected, Decimal("2168937.60"))

    # -------------------------------------------------------------------------
    # Temuan 3: Pergerakan stok, picking PO/SO, lot, dan move lines karantina
    # -------------------------------------------------------------------------
    def test_stock_movements_and_lot_mapping(self):
        """Picking PO, DO, dan retur karantina wajib memetakan lot dan move lines berstatus done."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        adapter.load_inbound_pos()
        adapter.load_sales_deliveries_and_invoices(limit_orders=5)
        adapter.load_rejections_quarantine(limit_orders=5)

        # Periksa picking PO
        po_picks = [
            p for p in mock_env["stock.picking"].store.values() if p._vals.get("picking_type_code") == "incoming"
        ]
        self.assertEqual(len(po_picks), 5)
        for pick in po_picks:
            self.assertEqual(pick.state, "done")
            move_lines = pick._vals.get("move_line_ids", [])
            self.assertGreater(len(move_lines), 0)
            # Pastikan lot_id terpetakan nyata oleh adapter, bukan False
            for ml in move_lines:
                self.assertTrue(ml.lot_id, "Setiap move line inbound PO wajib memiliki lot_id nyata!")
                self.assertGreater(ml.qty_done, 0.0)

        # Periksa picking DO
        so_picks = [
            p for p in mock_env["stock.picking"].store.values() if p._vals.get("picking_type_code") == "outgoing"
        ]
        self.assertEqual(len(so_picks), 5)
        for pick in so_picks:
            self.assertEqual(pick.state, "done")
            move_lines = pick._vals.get("move_line_ids", [])
            self.assertGreater(len(move_lines), 0)
            # Pastikan lot_id terpetakan nyata oleh adapter, bukan False
            for ml in move_lines:
                self.assertTrue(ml.lot_id, "Setiap move line delivery DO wajib memiliki lot_id nyata!")
                self.assertGreater(ml.qty_done, 0.0)

    # -------------------------------------------------------------------------
    # Temuan Supervisi: Validasi Wizard Tanpa State Done Wajib Fail-Fast
    # -------------------------------------------------------------------------
    def test_picking_validation_wizard_without_done_fails_fast(self):
        """Jika picking mengembalikan wizard dan tidak menjadi done, adapter wajib melempar RuntimeError."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        # Modifikasi create stock.picking agar mengembalikan wizard mode
        orig_create = mock_env["stock.picking"].create

        def create_wizard_pick(vals):
            rec = orig_create(vals)
            rec.mock_wizard_mode = True
            return rec

        mock_env["stock.picking"].create = create_wizard_pick

        with self.assertRaises(RuntimeError) as ctx:
            adapter.load_inbound_pos()
        self.assertIn("Validasi picking", str(ctx.exception))
        self.assertIn("gagal", str(ctx.exception))
        self.assertEqual(adapter.stats["do_validated"], 0)

    # -------------------------------------------------------------------------
    # Temuan Supervisi: Rekonsiliasi No-Op Wajib Fail-Fast dan Tolak Commit
    # -------------------------------------------------------------------------
    def test_reconciliation_noop_fails_fast_and_refuses_commit(self):
        """Jika reconcile() tidak menandai reconciled / residual nol, adapter wajib melempar RuntimeError."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        adapter.load_inbound_pos()
        adapter.load_sales_deliveries_and_invoices(limit_orders=1)

        # Pasang mock_noop_reconcile pada seluruh baris account.move.line
        for m in mock_env["account.move"].store.values():
            m.line_ids.mock_noop_reconcile = True

        with self.assertRaises(RuntimeError) as ctx:
            adapter.load_payments(limit_orders=1)
        self.assertIn("Rekonsiliasi AR gagal", str(ctx.exception))
        self.assertEqual(adapter.stats["ar_reconciled"], 0)

    # -------------------------------------------------------------------------
    # Temuan Supervisi: Karantina Tidak Menduplikasi Quant Saat Picking Ada
    # -------------------------------------------------------------------------
    def test_quarantine_does_not_duplicate_quants_when_picking_exists(self):
        """Validasi retur karantina via picking tidak boleh membuat quant manual duplikat."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        initial_quant_count = len(mock_env["stock.quant"].store)
        adapter.load_rejections_quarantine()

        # 9 picking transfer retur karantina dibuat dan divalidasi ke done
        quar_picks = [
            p for p in mock_env["stock.picking"].store.values()
            if p.origin and "REJ-" in str(p.origin)
        ]
        self.assertEqual(len(quar_picks), 9)
        for qp in quar_picks:
            self.assertEqual(qp.state, "done")

        # Quant manual TIDAK bertambah karena transfer dilakukan via stock.picking
        post_quant_count = len(mock_env["stock.quant"].store)
        self.assertEqual(post_quant_count, initial_quant_count)

    # -------------------------------------------------------------------------
    # Temuan 4: Rekonsiliasi pembayaran dan diskon pembayaran awal
    # -------------------------------------------------------------------------
    def test_payment_reconciliation_and_cash_discount(self):
        """Memverifikasi jurnal diskon pembayaran awal (160 transaksi) dan eksekusi rekonsiliasi."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        adapter.load_inbound_pos()
        adapter.load_sales_deliveries_and_invoices()
        adapter.load_payments()

        # 160 diskon pembayaran awal berhasil dibukukan via entri jurnal
        self.assertEqual(adapter.stats["discount_moves_created"], 160)
        self.assertEqual(adapter.stats["ar_reconciled"], 967)
        self.assertEqual(adapter.stats["ap_reconciled"], 4)

        # Seluruh pembayaran AR dan AP berstatus posted dan terhubung rekonsiliasi
        for pay in mock_env["account.payment"].store.values():
            self.assertIn(pay.state, ("paid", "in_process", "posted"))
            receivable_payable_lines = pay.line_ids.filtered(
                lambda ml: ml.account_id.account_type in ("asset_receivable", "liability_payable")
            )
            for line in receivable_payable_lines:
                self.assertTrue(line.reconciled)

    # -------------------------------------------------------------------------
    # Temuan 5: Kegagalan tidak disamarkan & rollback berfungsi sebelum commit
    # -------------------------------------------------------------------------
    def test_salesman_fail_fast_without_admin_fallback(self):
        """Salesman code tidak dikenal wajib melempar KeyError, tidak fallback ke admin."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        with self.assertRaises(KeyError):
            adapter.get_salesman_user("UNKNOWN-SALESMAN-99")

    def test_transaction_rollback_on_assertion_failure(self):
        """Jika terjadi anomali integritas data, commit tidak dipanggil dan rollback dieksekusi."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        # Paksa kegagalan pada tahap SO dengan limit tidak lengkap
        with self.assertRaises(AssertionError):
            adapter.run_all(limit_orders=999999)

        # Buktikan bahwa rollback terpanggil dan commit tidak pernah dipanggil
        self.assertTrue(mock_env.cr.rollbacked)
        self.assertFalse(mock_env.cr.committed)

    # -------------------------------------------------------------------------
    # Simulasi Rantai Transaksi Kecil (Disposable Seed Chain)
    # -------------------------------------------------------------------------
    def test_small_transaction_chain_simulation(self):
        """Membuktikan satu siklus transaksi kecil (1 SO) sebelum menjalankan 1.324 SO penuh."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        # Jalankan adapter dengan limit 1 SO
        adapter.run_all(limit_orders=1)

        self.assertEqual(adapter.stats["so_created"], 1)
        self.assertEqual(adapter.stats["invoices_created"], 1)
        self.assertEqual(adapter.stats["do_validated"], 6)  # 5 PO receipts + 1 SO delivery
        self.assertTrue(mock_env.cr.committed)
        self.assertFalse(mock_env.cr.rollbacked)

    # -------------------------------------------------------------------------
    # Idempotensi Penuh: Run 1 vs Run 2
    # -------------------------------------------------------------------------
    def test_adapter_full_idempotency_simulation_with_mock_environment(self):
        """Menguji CanonicalPerpetualAdapter secara nyata terhadap mock Odoo: Run 1 vs Run 2."""
        mock_env = setup_standard_mock_env()

        # RUN 1
        adapter_run1 = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)
        adapter_run1.run_all()

        self.assertEqual(adapter_run1.stats["so_created"], 1324)
        self.assertEqual(adapter_run1.stats["invoices_created"], 1324)
        self.assertEqual(adapter_run1.stats["ar_payments_created"], 967)
        self.assertEqual(adapter_run1.stats["ap_payments_created"], 4)
        self.assertEqual(adapter_run1.stats["opex_moves_created"], 30)
        self.assertEqual(adapter_run1.stats["opening_quants"], 150)
        self.assertEqual(adapter_run1.stats["po_created"], 5)
        self.assertEqual(adapter_run1.stats["quarantine_rejections"], 9)
        self.assertEqual(adapter_run1.stats["discount_moves_created"], 160)
        self.assertEqual(adapter_run1.stats["ar_reconciled"], 967)
        self.assertEqual(adapter_run1.stats["ap_reconciled"], 4)

        # RUN 2 (Idempotensi: 0 dibuat baru, seluruhnya dilewati)
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

    # -------------------------------------------------------------------------
    # Temuan Supervisi Terbaru (PR #15 review commit cc2276c):
    # 1. Partial reconciliation (hanya 2 baris diselesaikan pada transaksi diskon) wajib fail-fast
    # 2. Existing payment in draft & unreconciled wajib di-self-heal (post & reconcile), bukan diskip
    # 3. Karantina transfer wajib bersumber dari customer location (bukan internal) agar tidak double reduction
    # -------------------------------------------------------------------------

    def test_partial_reconciliation_two_lines_fails_fast_and_refuses_commit(self):
        """Jika rekonsiliasi hanya menyelesaikan 2 baris (diskon terbuka), adapter wajib fail-fast."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        # Muat SO & Invoice sampai ada faktur dengan diskon
        adapter.load_inbound_pos()
        adapter.load_sales_deliveries_and_invoices()

        # Modifikasi create account.payment agar menghasilkan lines dengan mock_partial_reconcile = True
        orig_payment_create = mock_env["account.payment"].create

        def patched_payment_create(vals):
            rec = orig_payment_create(vals)
            rec.mock_partial_reconcile = True
            return rec

        mock_env["account.payment"].create = patched_payment_create

        # Jalankan pemuatan payment: pada transaksi diskon 3 lines, rekonsiliasi partial 2 lines wajib gagal
        with self.assertRaises(RuntimeError) as ctx:
            adapter.load_payments()

        self.assertIn("Rekonsiliasi AR", str(ctx.exception))
        self.assertIn("Baris diskon atau piutang tertinggal", str(ctx.exception))

    def test_existing_draft_unreconciled_payment_self_heals_on_rerun(self):
        """Jika payment existing draft & unreconciled, rerun wajib memposting & merekonsiliasinya."""
        mock_env = setup_standard_mock_env()

        # Jalankan batch kecil 1 SO
        adapter_run1 = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)
        adapter_run1.run_all(limit_orders=1)
        self.assertTrue(mock_env.cr.committed)

        # Ambil payment yang terbuat
        pays = list(mock_env["account.payment"].store.values())
        self.assertTrue(len(pays) >= 1)
        target_pay = pays[0]
        self.assertIn(target_pay.state, ("paid", "in_process", "posted"))

        # Simulasikan situasi celah: payment diubah menjadi draft dan unreconciled
        target_pay.state = "draft"
        for line in target_pay.line_ids:
            line.reconciled = False

        # Reset flag DB commit
        mock_env.cr.committed = False
        mock_env.cr.rollbacked = False

        # Jalankan rerun adapter: adapter TIDAK boleh men-skip payment yang masih draft & unreconciled
        adapter_run2 = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)
        adapter_run2.run_all(limit_orders=1)

        # Buktikan self-healing: payment kembali aktif (paid/in_process/posted) dan baris piutang kembali reconciled
        self.assertIn(target_pay.state, ("posted", "in_process", "paid"))
        pay_rec_lines = target_pay.line_ids.filtered(
            lambda line: getattr(getattr(line, "account_id", None), "account_type", "") == "asset_receivable"
        )
        for pl in pay_rec_lines:
            self.assertTrue(pl.reconciled)

        self.assertTrue(mock_env.cr.committed)
        self.assertFalse(mock_env.cr.rollbacked)

    def test_quarantine_transfer_uses_customer_source_location_to_avoid_double_reduction(self):
        """Transfer retur karantina wajib bersumber dari lokasi customer, bukan internal gudang."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        adapter.load_rejections_quarantine()

        quar_picks = [
            p for p in mock_env["stock.picking"].store.values()
            if p.origin and "REJ-" in str(p.origin)
        ]
        self.assertEqual(len(quar_picks), 9)
        for qp in quar_picks:
            self.assertEqual(qp.state, "done")
            # Buktikan lokasi sumber adalah customer
            self.assertIsNotNone(qp.location_id)
            self.assertEqual(qp.location_id.usage, "customer")
            # Buktikan lokasi tujuan adalah Karantina FMCG Maumbi
            self.assertEqual(qp.location_dest_id.name, "Karantina FMCG Maumbi")

    def test_final_readback_fails_fast_when_canonical_payment_in_draft_state(self):
        """Jika payment kanonikal diubah menjadi draft sebelum commit, run_all wajib melempar AssertionError."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        original_load_opex = adapter.load_opex_payroll

        def corrupted_load_opex():
            original_load_opex()
            # Cari payment AR yang sudah terbuat dan ubah state menjadi draft
            for pay in mock_env["account.payment"].store.values():
                pref = getattr(pay, "ref", getattr(pay, "memo", ""))
                if str(pref).startswith("PAY-AR-"):
                    pay.state = "draft"
                    break

        adapter.load_opex_payroll = corrupted_load_opex

        with self.assertRaises(AssertionError) as ctx:
            adapter.run_all(limit_orders=1)

        self.assertIn("masih dalam state 'draft'", str(ctx.exception))
        self.assertTrue(mock_env.cr.rollbacked)
        self.assertFalse(mock_env.cr.committed)

    def test_final_readback_fails_fast_when_payment_receivable_unreconciled(self):
        """Jika baris piutang payment kanonikal unreconciled sebelum commit, run_all wajib melempar AssertionError."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        original_load_opex = adapter.load_opex_payroll

        def corrupted_load_opex():
            original_load_opex()
            for pay in mock_env["account.payment"].store.values():
                pref = getattr(pay, "ref", getattr(pay, "memo", ""))
                if str(pref).startswith("PAY-AR-"):
                    for line in pay.line_ids:
                        if getattr(getattr(line, "account_id", None), "account_type", "") == "asset_receivable":
                            line.reconciled = False
                            line.amount_residual = 500000.0
                    break

        adapter.load_opex_payroll = corrupted_load_opex

        with self.assertRaises(AssertionError) as ctx:
            adapter.run_all(limit_orders=1)

        self.assertIn("belum terekonsiliasi", str(ctx.exception))
        self.assertTrue(mock_env.cr.rollbacked)
        self.assertFalse(mock_env.cr.committed)

    def test_final_readback_fails_fast_when_discount_moves_missing(self):
        """Jika entri diskon pembayaran hilang atau berkurang, run_all wajib melempar AssertionError."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        original_load_payments = adapter.load_payments

        def corrupted_load_payments(*args, **kwargs):
            original_load_payments(*args, **kwargs)
            # Hapus jurnal diskon yang terbuat
            to_remove = [
                mid for mid, m in mock_env["account.move"].store.items()
                if getattr(m, "ref", "").startswith("DISC-")
            ]
            for mid in to_remove:
                del mock_env["account.move"].store[mid]

        adapter.load_payments = corrupted_load_payments

        with self.assertRaises(AssertionError) as ctx:
            adapter.run_all(limit_orders=1)

        err_msg = str(ctx.exception)
        self.assertTrue(
            "Jurnal diskon persis" in err_msg or "Jumlah jurnal diskon di database" in err_msg
        )
        self.assertTrue(mock_env.cr.rollbacked)
        self.assertFalse(mock_env.cr.committed)

    def test_final_readback_fails_fast_when_payment_has_no_move_id(self):
        """Jika payment tidak memiliki journal entry move_id (False/None), run_all wajib melempar AssertionError."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        original_load_opex = adapter.load_opex_payroll

        def corrupted_load_opex():
            original_load_opex()
            for pay in mock_env["account.payment"].store.values():
                pref = getattr(pay, "ref", getattr(pay, "memo", ""))
                if str(pref).startswith("PAY-AR-"):
                    pay.move_id = False
                    break

        adapter.load_opex_payroll = corrupted_load_opex

        with self.assertRaises(AssertionError) as ctx:
            adapter.run_all(limit_orders=1)

        self.assertIn("tidak memiliki journal entry move", str(ctx.exception))
        self.assertTrue(mock_env.cr.rollbacked)
        self.assertFalse(mock_env.cr.committed)

    def test_final_readback_fails_fast_when_discount_ref_is_unrelated(self):
        """Jika jurnal diskon diganti menjadi DISC-UNRELATED, run_all wajib menolak via pencocokan ID persis."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        original_load_payments = adapter.load_payments

        def corrupted_load_payments(limit_orders=None, target_so_numbers=None):
            original_load_payments(limit_orders=limit_orders, target_so_numbers=target_so_numbers)
            # Ganti ref jurnal diskon asli menjadi ref tidak dikenal (DISC-UNRELATED)
            for m in mock_env["account.move"].store.values():
                if getattr(m, "ref", "").startswith("DISC-"):
                    m._vals["ref"] = "DISC-UNRELATED"
                    break

        adapter.load_payments = corrupted_load_payments

        with self.assertRaises(AssertionError) as ctx:
            adapter.run_all(limit_orders=1)

        # Harus terdeteksi either pada pencocokan ID persis atau deteksi ref tidak dikenal
        err_msg = str(ctx.exception)
        self.assertTrue(
            "Jurnal diskon persis" in err_msg or "Ditemukan jurnal diskon dengan ref tidak dikenal" in err_msg
        )
        self.assertTrue(mock_env.cr.rollbacked)
        self.assertFalse(mock_env.cr.committed)

    def test_representative_slice_with_target_so_numbers_includes_quarantine_rejections(self):
        """Pemuatan slice target_so_numbers mencakup SO komersial, diskon kas, dan retur karantina secara utuh."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        target_slice = ["SO-202607-0001", "SO-202607-0063"]
        adapter.run_all(target_so_numbers=target_slice)

        self.assertTrue(mock_env.cr.committed)
        self.assertEqual(adapter.stats["so_created"], 2)
        self.assertEqual(adapter.stats["invoices_created"], 2)
        self.assertEqual(adapter.stats["quarantine_rejections"], 1)
        self.assertEqual(adapter.stats["discount_moves_created"], 1)
        self.assertGreaterEqual(adapter.stats["ar_payments_created"], 1)

        # Uji rerun idempoten sejati (Run 2)
        mock_env.cr.committed = False
        adapter_run2 = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)
        adapter_run2.run_all(target_so_numbers=target_slice)

        self.assertTrue(mock_env.cr.committed)
        self.assertEqual(adapter_run2.stats["so_created"], 0)
        self.assertEqual(adapter_run2.stats["invoices_created"], 0)
        self.assertEqual(adapter_run2.stats["quarantine_rejections"], 0)
        self.assertEqual(adapter_run2.stats["discount_moves_created"], 0)
        self.assertEqual(adapter_run2.stats["ar_payments_created"], 0)


if __name__ == "__main__":
    unittest.main()
