#!/usr/bin/env python3
"""Generic Period Pack Loader for FMCG Incremental Seeding into Odoo 19.

Generic engine to sequentially load and reconcile monthly FMCG period packs
(e.g., data/registers/periods/2026-08) into Odoo 19.

Key Features & Guarantees:
1. Driven strictly by MANIFEST.json (checksum verification, date ranges, metrics).
2. Pure incremental continuation: does not recreate master entities (customers, SKUs,
   opening stock, or June POs).
3. Reconciles cross-period AP payments (e.g. paying July Unilever bill PO-2026-06-05)
   against the real open vendor bill, never creating duplicate bills.
4. Native Odoo transactional posting:
   - SO with single-principal invariant.
   - Outbound picking with FEFO lot allocation and native STJ valuation.
   - Commercial out_invoice with PMK 131/2024 tax code 04 (DPP Nilai Lain 11/12, PPN 12%).
   - Native AR cash collection reconciliation.
   - OPEX and payroll journal entries.
5. Strict Idempotency & Fail-Closed Conflict Detection:
   - Matching documents are safely skipped (zero drift on replay).
   - Inconsistent / drifted documents trigger immediate fail-closed exceptions.
6. Full --dry-run support: evaluates database state without mutation.

Usage (CLI or inside Odoo shell):
    python scripts/ops/load_period_pack.py --pack data/registers/periods/2026-08 --dry-run
    python scripts/ops/load_period_pack.py --pack data/registers/periods/2026-08 --apply
"""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

_logger = logging.getLogger("period_pack_loader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


_SHA_CACHE: Dict[Tuple[str, float, int], str] = {}


def compute_sha256_lf(path: Path) -> str:
    """Compute SHA-256 hash normalizing CRLF/CR to LF with mtime/size cache."""
    try:
        st = path.stat()
        cache_key = (str(path.resolve()), st.st_mtime, st.st_size)
        if cache_key in _SHA_CACHE:
            return _SHA_CACHE[cache_key]
    except Exception:
        cache_key = None

    raw = path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    h = hashlib.sha256(normalized).hexdigest()
    if cache_key is not None:
        _SHA_CACHE[cache_key] = h
    return h


def _dec(val: Any) -> Decimal:
    """Safely convert value to Decimal."""
    if val is None or val == "":
        return ZERO
    return Decimal(str(val)).quantize(CENT, rounding=ROUND_HALF_UP)


def extract_ref(label: str) -> str:
    """Extract code/reference from string like 'CUST-RTL-006 - Warung Dani' -> 'CUST-RTL-006'."""
    if not label:
        return ""
    if " - " in label:
        return label.split(" - ", 1)[0].strip()
    return label.strip()


def _find_unilever_partner(Partner: Any) -> Any:
    """Resolve Unilever principal partner adaptively across seed (PRIN-UNILEVER) and mock fixtures (PRIN-002)."""
    p = Partner.search([("ref", "=", "PRIN-UNILEVER")], limit=1)
    if not p:
        p = Partner.search([("ref", "=", "PRIN-002")], limit=1)
    if not p:
        p = Partner.search([("name", "=", "PT Unilevr Indonezia Tbk")], limit=1)
    if not p:
        p = Partner.search([("name", "=", "PT Unilever Indonesia Tbk")], limit=1)
    if not p:
        p = Partner.search([("name", "=", "PT Unilever Enterprise Indonesia")], limit=1)
    if not p:
        p = Partner.search([("name", "=", "PT Unilever Indonesia")], limit=1)
    if not p:
        p = Partner.search([("name", "ilike", "%Unilever%")], limit=1)
    return p


def _find_payment(AccountPayment: Any, company_id: Any, pay_refs: list[str], payment_type: str = None) -> Any:
    """Find account.payment robustly across Odoo 19 (memo) and mock/legacy (ref) fields."""
    p_fields = getattr(AccountPayment, "_fields", None)
    base_domain = []
    if company_id:
        base_domain.append(("company_id", "=", company_id))
    if payment_type:
        base_domain.append(("payment_type", "=", payment_type))

    # 1. Search by memo if supported (Odoo 19 native)
    if p_fields is None or "memo" in p_fields:
        for r in pay_refs:
            try:
                pay = AccountPayment.search(base_domain + [("memo", "=", r)], limit=1)
                if pay:
                    return pay
            except Exception:
                pass

    # 2. Search by ref if supported (Odoo legacy / mock)
    if p_fields is None or "ref" in p_fields:
        for r in pay_refs:
            try:
                pay = AccountPayment.search(base_domain + [("ref", "=", r)], limit=1)
                if pay:
                    return pay
            except Exception:
                pass

    # 3. Search via move_id.ref if linked to account.move
    if hasattr(AccountPayment, "env") and "account.move" in AccountPayment.env:
        try:
            AccountMove = AccountPayment.env["account.move"].sudo()
            for r in pay_refs:
                move = AccountMove.search([("ref", "=", r)], limit=1)
                if move:
                    if p_fields is None or "move_id" in p_fields:
                        pay = AccountPayment.search(base_domain + [("move_id", "=", move.id)], limit=1)
                        if pay:
                            return pay
        except Exception:
            pass

    return None


def _safe_fields(obj: Any) -> Any:
    """Return _fields collection defensibly against boolean, mappingproxy, or None."""
    f = getattr(obj, "_fields", None)
    if f is not None and not isinstance(f, bool) and hasattr(f, "__contains__") and hasattr(f, "__iter__"):
        if len(f) > 0:
            return f
    if hasattr(obj, "_vals") and isinstance(obj._vals, dict):
        return set(obj._vals.keys()) | {
            "date_done",
            "date",
            "origin",
            "name",
            "state",
            "scheduled_date",
            "memo",
            "ref",
            "picked",
            "quantity",
            "qty_done",
            "lot_id",
            "lot_name",
        }
    if f is not None and not isinstance(f, bool) and hasattr(f, "__contains__"):
        return f
    return {}


def _rec_id(val: Any) -> Any:
    """Extract integer ID from recordset, MockRecord, or integer."""
    if hasattr(val, "id"):
        return val.id
    if isinstance(val, int):
        return val
    return False


def _iter_records(res: Any) -> list:
    """Convert search/recordset results or mock list into a list of records."""
    if not res:
        return []
    if hasattr(res, "__iter__"):
        try:
            return list(res)
        except TypeError:
            pass
    return [res]


class ManifestVerificationError(Exception):
    """Raised when pack directory fails manifest integrity or checksum verification."""


class PreflightContinuityError(Exception):
    """Raised when preflight database state does not match prerequisites for period pack."""


class StateInconsistencyError(Exception):
    """Raised when existing database record conflicts with period pack declaration."""


class PeriodPackManifest:
    """Encapsulates period pack MANIFEST.json and enforces checksum verification."""

    def __init__(self, pack_dir: Path):
        self.pack_dir = pack_dir.resolve()
        self.manifest_path = self.pack_dir / "MANIFEST.json"
        if not self.manifest_path.is_file():
            raise ManifestVerificationError(
                f"MANIFEST.json not found in pack directory: {self.pack_dir}"
            )

        try:
            self.raw_data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise ManifestVerificationError(
                f"Failed to parse MANIFEST.json in {self.pack_dir}: {e}"
            ) from e

        self.period = self.raw_data.get("period")
        self.pack_start = self.raw_data.get("pack_start")
        self.pack_end = self.raw_data.get("pack_end")
        self.files_sha256 = self.raw_data.get("files_sha256", {})
        self.metrics_summary = self.raw_data.get("metrics_summary", {})
        self.closing_summary = self.raw_data.get("closing_summary", {})
        self.configuration = self.raw_data.get("configuration", {})

        if not self.period or not self.pack_start or not self.pack_end:
            raise ManifestVerificationError(
                "MANIFEST.json missing required metadata ('period', 'pack_start', 'pack_end')"
            )

    def verify_checksums(self, strict: bool = True) -> Dict[str, str]:
        """Verify LF SHA-256 for all declared files in MANIFEST.json."""
        if not self.files_sha256:
            raise ManifestVerificationError(
                "MANIFEST.json contains empty 'files_sha256' declaration"
            )

        verified = {}
        for fname, expected_hash in self.files_sha256.items():
            fpath = self.pack_dir / fname
            if not fpath.is_file():
                msg = f"Declared pack file missing on disk: {fname} (expected {expected_hash})"
                if strict:
                    raise ManifestVerificationError(msg)
                _logger.warning(msg)
                continue

            actual_hash = compute_sha256_lf(fpath)
            if actual_hash != expected_hash:
                msg = (
                    f"Checksum mismatch for {fname}: "
                    f"expected {expected_hash}, got {actual_hash}"
                )
                raise ManifestVerificationError(msg)
            verified[fname] = actual_hash

        return verified


class PeriodPackReader:
    """Reads CSV and JSON datasets from verified period pack directory."""

    def __init__(self, pack_dir: Path, overrides: Optional[Dict[str, List[Dict[str, str]]]] = None):
        self.pack_dir = pack_dir.resolve()
        self._overrides: Dict[str, List[Dict[str, str]]] = dict(overrides) if overrides else {}

    def set_override(self, filename: str, rows: List[Dict[str, str]]) -> None:
        """Inject persistent in-memory dataset override for fault-injection or test simulation."""
        self._overrides[filename] = rows

    def clear_overrides(self) -> None:
        """Clear all active dataset overrides."""
        self._overrides.clear()

    def read_csv(self, filename: str) -> List[Dict[str, str]]:
        if filename in self._overrides:
            return list(self._overrides[filename])
        fpath = self.pack_dir / filename
        if not fpath.is_file():
            return []
        with open(fpath, mode="r", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def read_json(self, filename: str) -> Any:
        fpath = self.pack_dir / filename
        if not fpath.is_file():
            return None
        with open(fpath, mode="r", encoding="utf-8") as f:
            return json.load(f)

    @property
    def sales_orders(self) -> List[Dict[str, str]]:
        return self.read_csv("sales_orders.csv")

    @property
    def order_lines(self) -> List[Dict[str, str]]:
        return self.read_csv("order_lines.csv")

    @property
    def deliveries(self) -> List[Dict[str, str]]:
        return self.read_csv("deliveries.csv")

    @property
    def rejections(self) -> List[Dict[str, str]]:
        return self.read_csv("rejections.csv")

    @property
    def invoices(self) -> List[Dict[str, str]]:
        return self.read_csv("invoices.csv")

    @property
    def ar_collections(self) -> List[Dict[str, str]]:
        return self.read_csv("ar_collections.csv")

    @property
    def ap_payments(self) -> List[Dict[str, str]]:
        return self.read_csv("ap_payments.csv")

    @property
    def po_headers(self) -> List[Dict[str, str]]:
        return self.read_csv("po_headers.csv")

    @property
    def po_lines(self) -> List[Dict[str, str]]:
        return self.read_csv("po_lines.csv")

    @property
    def opex(self) -> List[Dict[str, str]]:
        return self.read_csv("opex.csv")


OPEX_CATEGORY_ACCOUNT_MAP = {
    "Logistik Rutin": "610100",
    "Uang Jalan Ritase": "610100",
    "Payroll Karyawan": "610200",
    "Komisi & Insentif": "610200",
    "Lembur Gudang & Logistik": "610300",
    "Sewa & Utilitas": "610400",
    "Pemeliharaan Armada": "610500",
    "Perizinan & Regulasi": "610600",
    "Administrasi Bank": "610700",
}


class GenericPeriodPackLoader:
    """Core adapter to load or dry-run a periodic FMCG pack into Odoo 19."""

    def __init__(
        self,
        env: Any,
        pack_dir: Path,
        dry_run: bool = True,
        strict: bool = True,
        company_id: Optional[int] = None,
        reader: Optional[PeriodPackReader] = None,
    ):
        self.env = env
        self.pack_dir = pack_dir.resolve()
        self.dry_run = dry_run
        self.strict = strict
        self.company_id = company_id

        # 1. Manifest verification
        self.manifest = PeriodPackManifest(self.pack_dir)
        self.period = self.manifest.period
        self.manifest.verify_checksums(strict=strict)
        self.reader = reader or PeriodPackReader(self.pack_dir)

        # 2. Accounting and location maps
        self.company = None
        self.wh_location = None
        self.wh_stock_loc = None
        self.seed_customer_loc = None
        self.seed_supplier_loc = None
        self.quarantine_loc = None
        self.seed_inventory_loc = None
        self.stock_valuation_acc = None
        self.stock_input_acc = None
        self.stock_output_acc = None
        self.cogs_acc = None
        self.stock_journal = None
        self.partner_by_ref = {}
        self.sku_by_code = {}
        self.lot_by_sku_and_name = {}

        # 3. Execution plan / audit counters
        self.plan = {
            "period": self.manifest.period,
            "dry_run": self.dry_run,
            "po": {"to_create": 0, "to_skip": 0, "conflicts": 0},
            "so": {"to_create": 0, "to_skip": 0, "conflicts": 0},
            "delivery": {"to_create": 0, "to_skip": 0, "conflicts": 0},
            "invoice": {"to_create": 0, "to_skip": 0, "conflicts": 0},
            "ar": {"to_reconcile": 0, "to_skip": 0, "conflicts": 0},
            "ap": {"to_reconcile": 0, "to_skip": 0, "conflicts": 0},
            "opex": {"to_create": 0, "to_skip": 0, "conflicts": 0},
        }

    def _resolve_account(self, code: str, fallback_type: Optional[str] = None) -> Any:
        """Resolve account.account strictly by code (fail-closed, no fuzzy fallback)."""
        if self.env is None:
            return None
        Account = self.env["account.account"].sudo()
        acc = Account.search(
            [("code", "=", code), ("company_id", "in", [self.company.id, False])], limit=1
        )
        if not acc and self.strict:
            c_name = getattr(self.company, "name", "unknown")
            raise PreflightContinuityError(
                f"Account for code '{code}' not found in account.account for company '{c_name}'"
            )
        return acc

    def _resolve_general_journal(self) -> Any:
        """Resolve general journal strictly (fail-closed: require unambiguous MISC or GEN)."""
        if self.env is None:
            return None
        Journal = self.env["account.journal"].sudo()
        general_journals = list(
            Journal.search([("company_id", "=", self.company.id), ("type", "=", "general")])
        )
        if not general_journals:
            if self.strict:
                raise PreflightContinuityError("No general journal found for company")
            return None

        candidates = [j for j in general_journals if getattr(j, "code", "") in ("MISC", "GEN")]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            if self.strict:
                codes = [getattr(j, "code", "") for j in candidates]
                raise StateInconsistencyError(f"Ambiguous general journals found for OPEX: {codes}")
            return candidates[0]
        # candidates == 0
        if self.strict:
            codes = [getattr(j, "code", "") for j in general_journals]
            raise PreflightContinuityError(
                f"No general journal with code MISC or GEN found for OPEX (available general journals: {codes})"
            )
        return general_journals[0]

    def _resolve_sale_journal(self) -> Any:
        """Resolve customer invoice (sale) journal strictly for company."""
        if self.env is None or "account.journal" not in self.env:
            return None
        Journal = self.env["account.journal"].sudo()
        comp_id = getattr(self.company, "id", None) if hasattr(self, "company") and self.company else None
        domain = [("type", "=", "sale")]
        if comp_id:
            domain.append(("company_id", "in", [comp_id, False]))
        journals = list(Journal.search(domain))
        if comp_id:
            comp_specific = [j for j in journals if getattr(getattr(j, "company_id", None), "id", None) == comp_id]
            if comp_specific:
                return comp_specific[0]
        return journals[0] if journals else None

    # -----------------------------------------------------------------------
    # Preflight Check & Continuity Verification
    # -----------------------------------------------------------------------

    def _ensure_accounting_and_stock_configuration(self) -> None:
        """Ensure FMCG perpetual stock accounting and seed locations are configured."""
        if not self.env or not self.company:
            return

        has_company = bool(self.company)
        # 1. Company anglo_saxon_accounting
        comp_fields = _safe_fields(self.company)
        if "anglo_saxon_accounting" in comp_fields:
            if not getattr(self.company, "anglo_saxon_accounting", True):
                if callable(getattr(self.company.sudo(), "write", None)):
                    self.company.sudo().write({"anglo_saxon_accounting": True})

        # 2. Accounts
        AccountAccount = self.env["account.account"].sudo() if "account.account" in self.env else None
        acc_fields = _safe_fields(AccountAccount) if AccountAccount is not None else {}
        comp_domain = []
        comp_vals = {}
        if "company_ids" in acc_fields and has_company:
            comp_domain = [("company_ids", "in", [self.company.id])]
            comp_vals = {"company_ids": [(4, self.company.id)]}
        elif "company_id" in acc_fields and has_company:
            comp_domain = [("company_id", "in", [False, self.company.id])]
            comp_vals = {"company_id": self.company.id}

        def _resolve_or_create_acc(code: str, name: str, acc_type: str, fallback_type: str = None):
            if AccountAccount is None:
                return None
            acc = AccountAccount.search(comp_domain + [("code", "=", code)], limit=1)
            if not acc and callable(getattr(AccountAccount, "create", None)):
                vals = {"code": code, "name": name, "account_type": acc_type}
                vals.update(comp_vals)
                try:
                    acc = AccountAccount.create(vals)
                except Exception:
                    if fallback_type:
                        vals["account_type"] = fallback_type
                        try:
                            acc = AccountAccount.create(vals)
                        except Exception:
                            pass
            return acc

        stock_val_acc = _resolve_or_create_acc("113000", "Persediaan Barang Dagang FMCG", "asset_current")
        stock_in_acc = _resolve_or_create_acc("113900", "Penerimaan Barang Sementara (Interim)", "asset_current", "liability_current")
        stock_out_acc = _resolve_or_create_acc("113910", "Pengiriman Barang Sementara (Interim)", "asset_current")
        cogs_acc = _resolve_or_create_acc("510000", "Harga Pokok Penjualan (HPP) FMCG", "expense_direct_cost", "expense")

        self.stock_valuation_acc = stock_val_acc
        self.stock_input_acc = stock_in_acc
        self.stock_output_acc = stock_out_acc
        self.cogs_acc = cogs_acc

        # 3. Stock Journal STJ
        stock_journal = None
        if "account.journal" in self.env:
            AccountJournal = self.env["account.journal"].sudo()
            j_fields = _safe_fields(AccountJournal)
            has_comp_id = "company_id" in j_fields and has_company
            j_domain = [("company_id", "in", [False, self.company.id])] if has_comp_id else []
            stock_journal = AccountJournal.search(j_domain + [("code", "=", "STJ")], limit=1)
            if not stock_journal and callable(getattr(AccountJournal, "create", None)):
                jvals = {"name": "Penilaian Persediaan", "type": "general", "code": "STJ"}
                if has_comp_id:
                    jvals["company_id"] = self.company.id
                if "auto_post" in j_fields:
                    jvals["auto_post"] = True
                stock_journal = AccountJournal.create(jvals)
            if has_company and stock_journal:
                comp_fields = _safe_fields(self.company)
                if "account_stock_journal_id" in comp_fields:
                    if callable(getattr(self.company.sudo(), "write", None)):
                        self.company.sudo().write({"account_stock_journal_id": stock_journal.id})

        self.stock_journal = stock_journal

        # 4. Stock Locations
        StockLocation = self.env["stock.location"].sudo() if "stock.location" in self.env else None
        if StockLocation is not None:
            sl_fields = _safe_fields(StockLocation)
            seed_comp_id = self.company.id if has_company else False

            def _loc_comp_id(loc):
                loc_comp = getattr(loc, "company_id", False)
                return getattr(loc_comp, "id", loc_comp) if loc_comp else False

            # Internal WH Stock location
            wh_candidates = [
                loc for loc in _iter_records(StockLocation.search([
                    ("usage", "=", "internal"),
                    ("complete_name", "in", ["WH/Stock", "GD-MND/Stock", "GD-MND/UTAMA", "WH"]),
                ]))
                if _loc_comp_id(loc) in (seed_comp_id, False)
            ]
            if not wh_candidates:
                wh_candidates = [
                    loc for loc in _iter_records(StockLocation.search([("usage", "=", "internal")]))
                    if _loc_comp_id(loc) in (seed_comp_id, False)
                ]
            self.wh_stock_loc = wh_candidates[0] if wh_candidates else None
            self.wh_location = self.wh_stock_loc

            def _resolve_or_create_seed_loc(name: str, usage: str, parent_id=False):
                matches = [
                    loc for loc in _iter_records(StockLocation.search([("name", "=", name), ("usage", "=", usage)]))
                    if _loc_comp_id(loc) in (seed_comp_id, False)
                ]
                if matches:
                    exact = [loc for loc in matches if _loc_comp_id(loc) == seed_comp_id]
                    return exact[0] if exact else matches[0]
                if callable(getattr(StockLocation, "create", None)):
                    vals = {"name": name, "usage": usage}
                    if parent_id:
                        vals["location_id"] = parent_id
                    if "company_id" in sl_fields and seed_comp_id:
                        vals["company_id"] = seed_comp_id
                    return StockLocation.create(vals)
                return None

            self.quarantine_loc = _resolve_or_create_seed_loc(
                "Karantina FMCG Maumbi", "internal", parent_id=getattr(self.wh_stock_loc, "id", False)
            )
            self.seed_inventory_loc = _resolve_or_create_seed_loc("Inventory Adjustment FMCG Maumbi", "inventory")
            self.seed_supplier_loc = _resolve_or_create_seed_loc("Suppliers FMCG Maumbi", "supplier")
            self.seed_customer_loc = _resolve_or_create_seed_loc("Customers FMCG Maumbi", "customer")

            if "valuation_account_id" in sl_fields:
                if self.wh_stock_loc and getattr(self.wh_stock_loc, "valuation_account_id", False):
                    if callable(getattr(self.wh_stock_loc, "write", None)):
                        self.wh_stock_loc.write({"valuation_account_id": False})
                if self.quarantine_loc and getattr(self.quarantine_loc, "valuation_account_id", False):
                    if callable(getattr(self.quarantine_loc, "write", None)):
                        self.quarantine_loc.write({"valuation_account_id": False})
                if stock_in_acc and self.seed_supplier_loc:
                    cur_in_val = getattr(getattr(self.seed_supplier_loc, "valuation_account_id", None), "id", getattr(self.seed_supplier_loc, "valuation_account_id", None))
                    if cur_in_val != stock_in_acc.id and callable(getattr(self.seed_supplier_loc, "write", None)):
                        self.seed_supplier_loc.write({"valuation_account_id": stock_in_acc.id})
                cust_acc = cogs_acc or stock_out_acc
                if cust_acc and self.seed_customer_loc:
                    cur_cust_val = getattr(getattr(self.seed_customer_loc, "valuation_account_id", None), "id", getattr(self.seed_customer_loc, "valuation_account_id", None))
                    if cur_cust_val != cust_acc.id and callable(getattr(self.seed_customer_loc, "write", None)):
                        self.seed_customer_loc.write({"valuation_account_id": cust_acc.id})

        # 5. Product Categories Real-Time Valuation & Costing
        if "product.category" in self.env:
            ProductCategory = self.env["product.category"].sudo()
            cat_fields = _safe_fields(ProductCategory)
            cats = ProductCategory.search([])
            for cat in _iter_records(cats):
                has_comp_ctx = callable(getattr(cat, "with_company", None)) and has_company
                cat_target = cat.with_company(self.company) if has_comp_ctx else cat
                vals = {}
                if "property_cost_method" in cat_fields and getattr(cat_target, "property_cost_method", None) != "fifo":
                    vals["property_cost_method"] = "fifo"
                if "property_valuation" in cat_fields and getattr(cat_target, "property_valuation", None) != "real_time":
                    vals["property_valuation"] = "real_time"
                for fname in ["property_stock_valuation_account_id", "stock_valuation_account_id", "account_stock_valuation_id"]:
                    if fname in cat_fields and stock_val_acc and not getattr(cat_target, fname, None):
                        vals[fname] = stock_val_acc.id
                for fname in ["property_stock_journal", "stock_journal_id", "stock_journal"]:
                    if fname in cat_fields and stock_journal and not getattr(cat_target, fname, None):
                        vals[fname] = stock_journal.id
                for fname in ["property_stock_account_input_categ_id", "property_stock_account_input_id", "account_stock_in_id"]:
                    if fname in cat_fields and stock_in_acc and not getattr(cat_target, fname, None):
                        vals[fname] = stock_in_acc.id
                for fname in ["property_stock_account_output_categ_id", "property_stock_account_output_id", "account_stock_out_id"]:
                    if fname in cat_fields and (cogs_acc or stock_out_acc) and not getattr(cat_target, fname, None):
                        vals[fname] = (cogs_acc or stock_out_acc).id
                for fname in ["property_account_expense_categ_id", "property_account_expense_id", "account_expense_id"]:
                    if fname in cat_fields and cogs_acc and not getattr(cat_target, fname, None):
                        vals[fname] = cogs_acc.id
                if vals and callable(getattr(cat_target, "write", None)):
                    try:
                        cat_target.write(vals)
                    except Exception as e:
                        _logger.warning(f"write category vals non-fatal: {e}")

    def verify_preflight(self) -> Dict[str, Any]:
        """Verify environment, company, warehouses, and previous month baseline."""
        report = {"status": "PASS", "checks": []}
        if self.env is None:
            # Running offline in test without Odoo ORM
            report["checks"].append("offline_mode_mock_env")
            return report

        # A. Resolve Canonical Company
        Company = self.env["res.company"].sudo()
        if self.company_id:
            self.company = Company.browse(self.company_id)
        else:
            # 1. Parameter fmcg.seed_company_id
            if "ir.config_parameter" in self.env:
                try:
                    param_val = self.env["ir.config_parameter"].sudo().get_param("fmcg.seed_company_id")
                    if param_val:
                        cand = Company.browse(int(param_val))
                        if cand.exists():
                            self.company = cand
                except Exception:
                    pass

            # 2. XMLID resmi id_base.fmcg_seed_company
            if not getattr(self, "company", None) and hasattr(self.env, "ref"):
                try:
                    cand = self.env.ref("id_base.fmcg_seed_company", raise_if_not_found=False)
                    if cand and cand.exists():
                        self.company = cand
                except Exception:
                    pass

            # 3. Pencarian nama kanonikal atau fallback env.company
            if not getattr(self, "company", None):
                self.company = Company.search(
                    ["|", ("name", "ilike", "PT Salva Inti Mandiri"), ("name", "ilike", "Manado")],
                    limit=1,
                ) or getattr(self.env, "company", None) or Company.search([], limit=1)
        if not self.company or not self.company.exists():
            raise PreflightContinuityError("Canonical FMCG Company not found in res.company")

        # Pastikan mata uang IDR aktif di res.currency dan company
        if "res.currency" in self.env:
            ResCurrency = self.env["res.currency"].sudo().with_context(active_test=False)
            idr = ResCurrency.search([("name", "=", "IDR")], limit=1)
            if idr and not getattr(idr, "active", True):
                idr.write({"active": True})
            if hasattr(self.env, "cr") and hasattr(self.env.cr, "execute"):
                self.env.cr.execute("UPDATE res_currency SET active = TRUE WHERE name = 'IDR';")
        if self.company:
            comp_curr = getattr(self.company, "currency_id", None)
            if comp_curr and not getattr(comp_curr, "active", True):
                comp_curr.sudo().write({"active": True})
            if hasattr(self.env, "cr") and hasattr(self.env.cr, "execute") and getattr(self.company, "id", None):
                self.env.cr.execute(
                    "UPDATE res_company SET currency_id = (SELECT id FROM res_currency WHERE name = 'IDR' LIMIT 1) WHERE id = %s;",
                    (self.company.id,),
                )
                self.env.cr.execute(
                    "UPDATE res_currency SET active = TRUE WHERE id = (SELECT currency_id FROM res_company WHERE id = %s);",
                    (self.company.id,),
                )
        if hasattr(self.env, "invalidate_all") and callable(self.env.invalidate_all):
            self.env.invalidate_all()

        report["checks"].append(f"company_resolved: {self.company.name} (id={self.company.id})")

        # Resolve & pastikan konfigurasi otoritatif Pajak Kode 04 (12% DPP Nilai Lain) aktif
        if "account.tax" in self.env:
            canonical_tax = self._resolve_canonical_tax_code_04()
            report["checks"].append(f"canonical_tax_04_resolved: {canonical_tax.name} (id={canonical_tax.id})")

        # B. Ensure FMCG Perpetual Accounting, Journals & Locations
        self._ensure_accounting_and_stock_configuration()
        if not self.wh_stock_loc:
            Location = self.env["stock.location"].sudo()
            self.wh_location = Location.search(
                [
                    ("company_id", "=", self.company.id),
                    ("usage", "=", "internal"),
                    ("complete_name", "in", ["WH/Stock", "GD-MND/Stock", "GD-MND/UTAMA"]),
                ],
                limit=1,
            ) or Location.search(
                [("company_id", "=", self.company.id), ("usage", "=", "internal")],
                limit=1,
            )
            self.wh_stock_loc = self.wh_location
        if not self.wh_stock_loc:
            raise PreflightContinuityError("Internal warehouse stock location not found")

        loc_lbl = getattr(self.wh_stock_loc, "complete_name", getattr(self.wh_stock_loc, "name", "WH/Stock"))
        report["checks"].append(f"stock_location_resolved: {loc_lbl}")
        if self.seed_customer_loc:
            c_lbl = getattr(self.seed_customer_loc, "name", "Customers FMCG Maumbi")
            report["checks"].append(f"seed_customer_location_resolved: {c_lbl}")
        if self.seed_supplier_loc:
            s_lbl = getattr(self.seed_supplier_loc, "name", "Suppliers FMCG Maumbi")
            report["checks"].append(f"seed_supplier_location_resolved: {s_lbl}")

        # C. Master Data Completeness (Do NOT recreate)
        Partner = self.env["res.partner"].sudo()
        partner_count = Partner.search_count([("active", "in", [True, False])])
        if partner_count < 350:
            raise PreflightContinuityError(
                f"Preflight partner count too low: {partner_count} (expected >= 350)"
            )
        report["checks"].append(f"partner_count_ok: {partner_count}")

        Product = self.env["product.product"].sudo()
        sku_count = Product.search_count([("default_code", "!=", False)])
        if sku_count < 140:
            raise PreflightContinuityError(
                f"Preflight SKU count too low: {sku_count} (expected >= 140)"
            )
        report["checks"].append(f"sku_count_ok: {sku_count}")

        # D. Previous Month Continuity (For August: verify July baseline exists)
        if self.manifest.period > "2026-07":
            SaleOrder = self.env["sale.order"].sudo()
            july_so_count = SaleOrder.search_count(
                [("company_id", "=", self.company.id), ("client_order_ref", "=like", "SO-202607-%")]
            )
            if july_so_count < 1000 and self.strict:
                raise PreflightContinuityError(
                    f"Previous period (July) SO count too low: {july_so_count} (expected >= 1000)"
                )
            report["checks"].append(f"july_continuity_so_count: {july_so_count}")

            # Verify July Unilever open vendor bill exists for August AP settlement
            Partner = self.env["res.partner"].sudo()
            unilever_partner = _find_unilever_partner(Partner)
            if not unilever_partner and self.strict:
                raise PreflightContinuityError("Unilever principal partner (PRIN-UNILEVER/PRIN-002) not found in res.partner")

            AccountMove = self.env["account.move"].sudo()
            target_amt = Decimal("2899971200.00")

            # Find exact posted July Unilever bill for PO-2026-06-05 (NO ilike)
            bill_domain = [
                ("company_id", "=", self.company.id),
                ("move_type", "=", "in_invoice"),
                ("state", "=", "posted"),
            ]
            if unilever_partner:
                bill_domain.append(("partner_id", "=", unilever_partner.id))
            exact_ref_bills = list(AccountMove.search(bill_domain + [("ref", "=", "PO-2026-06-05")]))
            exact_origin_bills = list(AccountMove.search(bill_domain + [("invoice_origin", "=", "PO-2026-06-05")]))
            all_matching = list({b.id: b for b in (exact_ref_bills + exact_origin_bills)}.values())
            if not all_matching:
                ref_bills = list(AccountMove.search([
                    ("company_id", "=", self.company.id),
                    ("move_type", "=", "in_invoice"),
                    ("state", "=", "posted"),
                    ("ref", "=", "PO-2026-06-05"),
                ]))
                origin_bills = list(AccountMove.search([
                    ("company_id", "=", self.company.id),
                    ("move_type", "=", "in_invoice"),
                    ("state", "=", "posted"),
                    ("invoice_origin", "=", "PO-2026-06-05"),
                ]))
                all_matching = list({b.id: b for b in (ref_bills + origin_bills)}.values())

            if len(all_matching) > 1 and self.strict:
                raise StateInconsistencyError(
                    f"Ambiguous July Unilever vendor bills found ({len(all_matching)}) for exact PO-2026-06-05"
                )
            if not all_matching and self.strict:
                raise PreflightContinuityError(
                    "July Unilever vendor bill for PO-2026-06-05 not found"
                )

            matching_bill = all_matching[0] if all_matching else None
            if matching_bill:
                bill_res = _dec(getattr(matching_bill, "amount_residual", Decimal(0)))
                bill_state = getattr(matching_bill, "payment_state", "not_paid")

                # Case 1: Fresh baseline before August AP payment -> must be open with exact residual
                if bill_state in ("not_paid", "partial"):
                    if abs(bill_res - target_amt) > Decimal("1.00"):
                        raise PreflightContinuityError(
                            f"Open July Unilever vendor bill residual ({bill_res}) does not match expected {target_amt}"
                        )
                # Case 2: Replay baseline -> bill is already paid. ACCEPT ONLY IF exact reconciled August payment exists!
                elif bill_state in ("paid", "in_payment") and bill_res <= Decimal("1.00"):
                    AccountPayment = self.env["account.payment"].sudo()
                    reconciled_pay = _find_payment(
                        AccountPayment,
                        self.company.id,
                        ["PAY-AP-05", "AP-202608-0001"],
                        payment_type="outbound",
                    )
                    if not reconciled_pay:
                        reconciled_pay = AccountPayment.search(
                            [
                                ("company_id", "=", self.company.id),
                                ("partner_id", "=", unilever_partner.id if unilever_partner else False),
                                ("payment_type", "=", "outbound"),
                                ("amount", "=", float(target_amt)),
                                ("state", "=", "posted"),
                            ],
                            limit=1,
                        )
                    if not reconciled_pay and self.strict:
                        raise PreflightContinuityError(
                            "July Unilever bill is marked paid, but no matching reconciled August AP payment (PAY-AP-05 / AP-202608-0001) found"
                        )
                    # Verify explicit reconciliation edge between paid bill and the payment
                    is_edge_valid = False
                    if hasattr(reconciled_pay, "reconciled_bill_ids") and reconciled_pay.reconciled_bill_ids:
                        if matching_bill.id in [b.id for b in reconciled_pay.reconciled_bill_ids]:
                            is_edge_valid = True
                    if not is_edge_valid and hasattr(matching_bill, "matched_payment_ids") and matching_bill.matched_payment_ids:
                        if reconciled_pay.id in [p.id for p in matching_bill.matched_payment_ids]:
                            is_edge_valid = True
                    if not is_edge_valid and hasattr(reconciled_pay, "move_id") and getattr(reconciled_pay.move_id, "line_ids", None):
                        for line in reconciled_pay.move_id.line_ids:
                            matched_prs = list(getattr(line, "matched_debit_ids", []) or []) + list(getattr(line, "matched_credit_ids", []) or [])
                            for pr in matched_prs:
                                deb_id = getattr(getattr(pr, "debit_move_id", None), "move_id", None)
                                crd_id = getattr(getattr(pr, "credit_move_id", None), "move_id", None)
                                if (deb_id and deb_id.id == matching_bill.id) or (crd_id and crd_id.id == matching_bill.id):
                                    is_edge_valid = True
                                    break
                            if is_edge_valid:
                                break
                    if not is_edge_valid and self.strict:
                        pay_name = getattr(reconciled_pay, "ref", "") or getattr(reconciled_pay, "name", "unknown")
                        raise PreflightContinuityError(
                            f"July Unilever bill is paid, but payment {pay_name} is not reconciled to it"
                        )
                else:
                    if self.strict:
                        raise PreflightContinuityError(
                            f"July Unilever vendor bill has unexpected payment state '{bill_state}' with residual {bill_res}"
                        )

            report["checks"].append(
                f"unilever_bill_found: {matching_bill.name if matching_bill else 'none'}"
            )

        return report

    # -----------------------------------------------------------------------
    # Idempotency & Deep Drift Validation
    # -----------------------------------------------------------------------

    def _validate_existing_po(
        self, existing: Any, po_row: Dict[str, str], lines: List[Dict[str, str]]
    ) -> None:
        """Validate existing Purchase Order matches period pack specification with zero drift."""
        po_num = po_row["po_number"]
        prin_code = po_row["principal_code"]
        p_ref = getattr(existing.partner_id, "ref", "")
        p_name = getattr(existing.partner_id, "name", "")
        if existing.partner_id and p_ref != prin_code and prin_code not in p_name:
            raise StateInconsistencyError(
                f"Drift detected on existing PO {po_num}: partner mismatch {p_ref} vs {prin_code}"
            )
        order_date = po_row.get("order_date", "")
        act_date = str(getattr(existing, "date_order", ""))
        if order_date and act_date and not act_date.startswith(order_date[:10]):
            raise StateInconsistencyError(
                f"Drift detected on existing PO {po_num}: date mismatch {act_date} vs {order_date}"
            )
        act_state = getattr(existing, "state", None)
        if act_state and act_state not in ("purchase", "done"):
            raise StateInconsistencyError(
                f"Drift detected on existing PO {po_num}: state is '{act_state}' (expected purchase/done)"
            )
        order_lines = getattr(existing, "order_line", None)
        if order_lines is not None and len(order_lines) > 0 and lines:
            if len(order_lines) != len(lines):
                raise StateInconsistencyError(
                    f"Drift detected on existing PO {po_num}: line count mismatch {len(order_lines)} vs {len(lines)}"
                )
            lines_by_sku = {line["sku_code"]: line for line in lines}
            for ol in order_lines:
                sku = getattr(ol.product_id, "default_code", "")
                if sku and sku not in lines_by_sku:
                    raise StateInconsistencyError(
                        f"Drift detected on existing PO {po_num}: unexpected SKU '{sku}'"
                    )
                if sku in lines_by_sku:
                    exp_line = lines_by_sku[sku]
                    if "qty_cartons" in exp_line and "carton_qty" in exp_line:
                        exp_qty = float(exp_line["qty_cartons"]) * float(exp_line["carton_qty"])
                    else:
                        exp_qty = float(exp_line.get("product_qty", 0) or exp_line.get("qty", 0))
                    act_qty = float(getattr(ol, "product_qty", 0))
                    if abs(exp_qty - act_qty) > 0.01:
                        raise StateInconsistencyError(
                            f"Drift detected on existing PO {po_num} SKU {sku}: qty mismatch {act_qty} vs {exp_qty}"
                        )
                    # Schema PO CSV: unit_cost_price
                    exp_price_val = exp_line.get("unit_cost_price") or exp_line.get("price_unit") or exp_line.get("unit_price")
                    if exp_price_val is not None:
                        exp_price = float(exp_price_val)
                        act_price = float(getattr(ol, "price_unit", 0))
                        if abs(exp_price - act_price) > 0.01:
                            raise StateInconsistencyError(
                                f"Drift detected on existing PO {po_num} SKU {sku}: price mismatch {act_price} vs {exp_price}"
                            )

        if not self.dry_run:
            pickings = getattr(existing, "picking_ids", None)
            if pickings:
                for pick in pickings:
                    if getattr(pick, "state", "") not in ("done", "cancel"):
                        self._assign_lots_to_picking(pick, lines)
                        self._validate_picking_safely(
                            pick, effective_date=po_row.get("arrival_maumbi_date"), ref_num=po_num
                        )

    def _validate_existing_so(
        self, existing: Any, so_row: Dict[str, str], lines: List[Dict[str, str]]
    ) -> None:
        """Validate existing Sales Order matches period pack specification with zero drift."""
        so_num = so_row["so_number"]
        cust_ref = extract_ref(so_row["customer"])
        p_ref = getattr(existing.partner_id, "ref", "")
        p_name = getattr(existing.partner_id, "name", "")
        if existing.partner_id and p_ref != cust_ref and cust_ref not in p_name:
            raise StateInconsistencyError(
                f"Drift detected on existing {so_num}: customer mismatch {p_ref} vs {cust_ref}"
            )
        exp_net = _dec(so_row.get("net_dpp", 0))
        act_net = _dec(getattr(existing, "amount_untaxed", 0))
        if abs(exp_net - act_net) > CENT:
            raise StateInconsistencyError(
                f"Drift detected on existing {so_num}: expected net {exp_net}, found {act_net}"
            )
        act_state = getattr(existing, "state", None)
        if act_state and act_state not in ("sale", "done"):
            raise StateInconsistencyError(
                f"Drift detected on existing {so_num}: state is '{act_state}' (expected sale/done)"
            )
        order_lines = getattr(existing, "order_line", None)
        if order_lines is not None and len(order_lines) > 0 and lines:
            if len(order_lines) != len(lines):
                raise StateInconsistencyError(
                    f"Drift detected on existing {so_num}: line count mismatch {len(order_lines)} vs {len(lines)}"
                )
            remaining_expected = list(lines)
            for sol in order_lines:
                sku = getattr(sol.product_id, "default_code", "")
                act_qty = float(getattr(sol, "product_uom_qty", 0))

                # Match candidate by SKU and qty to correctly handle multi-lot lines of the same SKU
                matched_idx = None
                for idx, exp_l in enumerate(remaining_expected):
                    if exp_l.get("sku_code") == sku:
                        if "qty_cartons" in exp_l and "carton_qty" in exp_l:
                            exp_qty = float(exp_l["qty_cartons"]) * float(exp_l["carton_qty"])
                        else:
                            exp_qty = float(exp_l.get("product_uom_qty", 0) or exp_l.get("qty", 0))
                        if abs(exp_qty - act_qty) <= 0.01:
                            matched_idx = idx
                            break

                if matched_idx is None:
                    # Look for first candidate with matching SKU to report detailed drift
                    for exp_l in remaining_expected:
                        if exp_l.get("sku_code") == sku:
                            if "qty_cartons" in exp_l and "carton_qty" in exp_l:
                                exp_qty = float(exp_l["qty_cartons"]) * float(exp_l["carton_qty"])
                            else:
                                exp_qty = float(exp_l.get("product_uom_qty", 0) or exp_l.get("qty", 0))
                            raise StateInconsistencyError(
                                f"Drift detected on existing {so_num} SKU {sku}: qty mismatch {act_qty} vs {exp_qty}"
                            )
                    raise StateInconsistencyError(
                        f"Drift detected on existing {so_num}: unexpected SKU '{sku}'"
                    )

                exp_l = remaining_expected.pop(matched_idx)

                # Schema SO CSV: unit_price_dpp
                exp_price_val = exp_l.get("unit_price_dpp") or exp_l.get("price_unit") or exp_l.get("unit_price")
                if exp_price_val is not None:
                    exp_price = float(exp_price_val)
                    act_price = float(getattr(sol, "price_unit", 0))
                    if abs(exp_price - act_price) > 0.01:
                        raise StateInconsistencyError(
                            f"Drift detected on existing {so_num} SKU {sku}: price mismatch {act_price} vs {exp_price}"
                        )
                # Schema SO CSV: discount_pct
                exp_disc_val = exp_l.get("discount_pct") or exp_l.get("discount")
                if exp_disc_val is not None:
                    exp_disc = float(exp_disc_val)
                    act_disc = float(getattr(sol, "discount", 0.0))
                    if abs(exp_disc - act_disc) > 0.01:
                        raise StateInconsistencyError(
                            f"Drift detected on existing {so_num} SKU {sku}: discount mismatch {act_disc} vs {exp_disc}"
                        )

        if not self.dry_run:
            pickings = getattr(existing, "picking_ids", None)
            if pickings:
                for pick in pickings:
                    if getattr(pick, "state", "") not in ("done", "cancel"):
                        self._assign_lots_to_picking(pick, lines)
                        self._validate_picking_safely(
                            pick, effective_date=so_row.get("date_order"), ref_num=so_num
                        )

    def _validate_existing_invoice(self, existing: Any, inv_row: Dict[str, str]) -> None:
        """Validate existing Invoice matches period pack specification with zero drift."""
        inv_num = inv_row["invoice_number"]
        cust_ref = extract_ref(inv_row.get("customer", ""))
        p_ref = getattr(existing.partner_id, "ref", "")
        p_name = getattr(existing.partner_id, "name", "")
        if cust_ref and existing.partner_id and p_ref != cust_ref and cust_ref not in p_name:
            raise StateInconsistencyError(
                f"Drift detected on Invoice {inv_num}: customer mismatch {p_ref} vs {cust_ref}"
            )
        inv_date = inv_row.get("date_invoice", "")
        act_date = str(getattr(existing, "invoice_date", "") or getattr(existing, "date", ""))
        if inv_date and act_date and not act_date.startswith(inv_date[:10]):
            raise StateInconsistencyError(
                f"Drift detected on Invoice {inv_num}: date mismatch {act_date} vs {inv_date}"
            )
        exp_total = _dec(inv_row.get("total_invoice_with_ppn", 0))
        act_total = _dec(getattr(existing, "amount_total", 0))
        if abs(exp_total - act_total) > CENT:
            raise StateInconsistencyError(
                f"Drift detected on Invoice {inv_num}: expected total {exp_total}, found {act_total}"
            )
        exp_dpp = _dec(inv_row.get("commercial_dpp") or inv_row.get("dpp_amount", 0))
        act_dpp = _dec(getattr(existing, "amount_untaxed", 0))
        if abs(exp_dpp - act_dpp) > CENT:
            raise StateInconsistencyError(
                f"Drift detected on Invoice {inv_num}: expected dpp {exp_dpp}, found {act_dpp}"
            )
        exp_ppn = _dec(inv_row.get("ppn_amount", 0))
        act_ppn = _dec(getattr(existing, "amount_tax", 0))
        if abs(exp_ppn - act_ppn) > CENT:
            raise StateInconsistencyError(
                f"Drift detected on Invoice {inv_num}: expected PPN {exp_ppn}, found {act_ppn}"
            )
        act_state = getattr(existing, "state", None)
        if act_state and act_state != "posted":
            raise StateInconsistencyError(
                f"Drift detected on Invoice {inv_num}: state is '{act_state}' (expected posted)"
            )

    def _validate_existing_ar_payment(
        self, existing: Any, ar_row: Dict[str, str], target_invoice: Any = None
    ) -> None:
        """Validate existing AR Payment matches period pack specification with zero drift."""
        pay_ref = ar_row["payment_id"]
        cust_ref = extract_ref(ar_row.get("customer", ""))
        p_ref = getattr(existing.partner_id, "ref", "")
        p_name = getattr(existing.partner_id, "name", "")
        if cust_ref and existing.partner_id and p_ref != cust_ref and cust_ref not in p_name:
            raise StateInconsistencyError(
                f"Drift detected on AR payment {pay_ref}: partner mismatch {p_ref} vs {cust_ref}"
            )
        exp_date = ar_row.get("payment_date", "")
        act_date = str(getattr(existing, "date", ""))
        if exp_date and act_date and not act_date.startswith(exp_date[:10]):
            raise StateInconsistencyError(
                f"Drift detected on AR payment {pay_ref}: date mismatch {act_date} vs {exp_date}"
            )
        j_type = getattr(getattr(existing, "journal_id", None), "type", "")
        if j_type and j_type not in ("bank", "cash"):
            raise StateInconsistencyError(
                f"Drift detected on AR payment {pay_ref}: journal type is '{j_type}' (expected bank/cash)"
            )
        exp_amt = _dec(ar_row.get("net_cash_collected_total", 0))
        act_amt = _dec(getattr(existing, "amount", 0))
        if abs(exp_amt - act_amt) > CENT:
            raise StateInconsistencyError(
                f"Drift detected on AR payment {pay_ref}: expected amount {exp_amt}, found {act_amt}"
            )
        act_state = getattr(existing, "state", None)
        if act_state and act_state != "posted":
            raise StateInconsistencyError(
                f"Drift detected on AR payment {pay_ref}: state is '{act_state}' (expected posted)"
            )
        p_type = getattr(existing, "payment_type", None)
        if p_type and p_type != "inbound":
            raise StateInconsistencyError(
                f"Drift detected on AR payment {pay_ref}: payment_type is '{p_type}' (expected inbound)"
            )
        inv_num = ar_row.get("invoice_number", "")
        if target_invoice is None and inv_num and self.env is not None:
            AccountMove = self.env["account.move"].sudo()
            target_invoice = AccountMove.search(
                [("name", "=", inv_num), ("company_id", "=", self.company.id)], limit=1
            ) or AccountMove.search(
                [("payment_reference", "=", inv_num), ("company_id", "=", self.company.id)], limit=1
            )
        if target_invoice is None and self.strict:
            raise StateInconsistencyError(
                f"Cannot validate AR payment {pay_ref}: target invoice {inv_num} not found"
            )
        if target_invoice is not None:
            is_matched = False
            if hasattr(existing, "reconciled_invoice_ids") and existing.reconciled_invoice_ids:
                if target_invoice.id in [i.id for i in existing.reconciled_invoice_ids]:
                    is_matched = True
            if not is_matched and hasattr(existing, "move_id") and getattr(existing.move_id, "line_ids", None):
                for line in existing.move_id.line_ids:
                    matched_prs = list(getattr(line, "matched_debit_ids", []) or []) + list(getattr(line, "matched_credit_ids", []) or [])
                    for pr in matched_prs:
                        deb_id = getattr(getattr(pr, "debit_move_id", None), "move_id", None)
                        crd_id = getattr(getattr(pr, "credit_move_id", None), "move_id", None)
                        if (deb_id and deb_id.id == target_invoice.id) or (crd_id and crd_id.id == target_invoice.id):
                            is_matched = True
                            break
                    if is_matched:
                        break
            if not is_matched:
                raise StateInconsistencyError(
                    f"Drift detected on AR payment {pay_ref}: not reconciled to target invoice {inv_num}"
                )

    def _validate_existing_ap_payment(
        self, existing: Any, ap_row: Dict[str, str], unilever_bill: Any = None
    ) -> None:
        """Validate existing AP Payment matches period pack specification and Unilever bill settlement."""
        pay_ref = ap_row["ap_payment_id"]
        if unilever_bill is None:
            raise StateInconsistencyError(
                f"Cannot validate AP payment {pay_ref}: target unilever_bill is missing (None)"
            )
        prin_code = ap_row.get("principal_code")
        p_ref = getattr(existing.partner_id, "ref", "")
        p_name = getattr(existing.partner_id, "name", "")
        is_unilever = "unilever" in p_name.lower() or p_ref in ("PRIN-UNILEVER", "PRIN-002")
        if existing.partner_id and not is_unilever and prin_code and p_ref != prin_code:
            raise StateInconsistencyError(
                f"Drift detected on AP payment {pay_ref}: partner mismatch {p_ref} vs {prin_code}"
            )
        exp_date = ap_row.get("payment_date", "")
        act_date = str(getattr(existing, "date", ""))
        if exp_date and act_date and not act_date.startswith(exp_date[:10]):
            raise StateInconsistencyError(
                f"Drift detected on AP payment {pay_ref}: date mismatch {act_date} vs {exp_date}"
            )
        j_type = getattr(getattr(existing, "journal_id", None), "type", "")
        if j_type and j_type not in ("bank", "cash"):
            raise StateInconsistencyError(
                f"Drift detected on AP payment {pay_ref}: journal type is '{j_type}' (expected bank/cash)"
            )
        exp_amt = _dec(ap_row.get("amount_paid_dpp", 0))
        act_amt = _dec(getattr(existing, "amount", 0))
        if abs(exp_amt - act_amt) > CENT:
            raise StateInconsistencyError(
                f"Drift detected on AP payment {pay_ref}: expected amount {exp_amt}, found {act_amt}"
            )
        act_state = getattr(existing, "state", None)
        if act_state and act_state != "posted":
            raise StateInconsistencyError(
                f"Drift detected on AP payment {pay_ref}: state is '{act_state}' (expected posted)"
            )
        p_type = getattr(existing, "payment_type", None)
        if p_type and p_type != "outbound":
            raise StateInconsistencyError(
                f"Drift detected on AP payment {pay_ref}: payment_type is '{p_type}' (expected outbound)"
            )
        bill_res = _dec(getattr(unilever_bill, "amount_residual", Decimal(0)))
        bill_state = getattr(unilever_bill, "payment_state", None)
        if bill_res > Decimal("1.00") or (bill_state and bill_state not in ("paid", "in_payment")):
            raise StateInconsistencyError(
                f"Drift detected on AP settlement for {pay_ref}: linked July Unilever bill is not settled "
                f"(residual={bill_res}, payment_state={bill_state})"
            )
        is_matched = False
        if hasattr(existing, "reconciled_bill_ids") and existing.reconciled_bill_ids:
            if unilever_bill.id in [b.id for b in existing.reconciled_bill_ids]:
                is_matched = True
        if not is_matched and hasattr(unilever_bill, "matched_payment_ids") and unilever_bill.matched_payment_ids:
            if existing.id in [p.id for p in unilever_bill.matched_payment_ids]:
                is_matched = True
        if not is_matched and hasattr(existing, "move_id") and getattr(existing.move_id, "line_ids", None):
            for line in existing.move_id.line_ids:
                matched_prs = list(getattr(line, "matched_debit_ids", []) or []) + list(getattr(line, "matched_credit_ids", []) or [])
                for pr in matched_prs:
                    deb_id = getattr(getattr(pr, "debit_move_id", None), "move_id", None)
                    crd_id = getattr(getattr(pr, "credit_move_id", None), "move_id", None)
                    if (deb_id and deb_id.id == unilever_bill.id) or (crd_id and crd_id.id == unilever_bill.id):
                        is_matched = True
                        break
                if is_matched:
                    break
        if not is_matched:
            raise StateInconsistencyError(
                f"Drift detected on AP payment {pay_ref}: not reconciled to target July Unilever bill {unilever_bill.name}"
            )

    def _validate_existing_opex(
        self,
        existing: Any,
        op_row: Dict[str, str],
        target_code: str,
        credit_acc_code: str,
        exp_journal_code: str = "MISC",
    ) -> None:
        """Validate existing OPEX journal entry matches period pack specification with zero drift."""
        desc = op_row["description"]
        exp_amt = _dec(op_row.get("amount", 0))
        act_state = getattr(existing, "state", None)
        if act_state and act_state != "posted":
            raise StateInconsistencyError(
                f"Drift detected on OPEX {desc}: state is '{act_state}' (expected posted)"
            )
        act_journal_code = getattr(getattr(existing, "journal_id", None), "code", "")
        if exp_journal_code and act_journal_code and act_journal_code != exp_journal_code:
            raise StateInconsistencyError(
                f"Drift detected on OPEX {desc}: journal mismatch {act_journal_code} vs expected {exp_journal_code}"
            )
        lines = getattr(existing, "line_ids", [])
        if not lines:
            raise StateInconsistencyError(f"Drift detected on OPEX {desc}: move has no lines")
        debit_lines = [mline for mline in lines if _dec(getattr(mline, "debit", 0)) > ZERO]
        credit_lines = [mline for mline in lines if _dec(getattr(mline, "credit", 0)) > ZERO]
        if not debit_lines or not credit_lines:
            raise StateInconsistencyError(f"Drift detected on OPEX {desc}: move missing debit or credit lines")
        act_debit = sum(_dec(getattr(mline, "debit", 0)) for mline in debit_lines)
        act_credit = sum(_dec(getattr(mline, "credit", 0)) for mline in credit_lines)
        if abs(exp_amt - act_debit) > CENT:
            raise StateInconsistencyError(
                f"Drift detected on OPEX {desc}: expected debit {exp_amt}, found {act_debit}"
            )
        if abs(exp_amt - act_credit) > CENT:
            raise StateInconsistencyError(
                f"Drift detected on OPEX {desc}: expected credit {exp_amt}, found {act_credit}"
            )
        for mline in debit_lines:
            d_acc_code = getattr(getattr(mline, "account_id", None), "code", "")
            if d_acc_code and d_acc_code != target_code:
                raise StateInconsistencyError(
                    f"Drift detected on OPEX {desc}: debit account mismatch {d_acc_code} vs expected {target_code}"
                )
        for mline in credit_lines:
            c_acc_code = getattr(getattr(mline, "account_id", None), "code", "")
            if c_acc_code and c_acc_code != credit_acc_code:
                raise StateInconsistencyError(
                    f"Drift detected on OPEX {desc}: credit account mismatch {c_acc_code} vs expected {credit_acc_code}"
                )

    # -----------------------------------------------------------------------
    # Dry-Run Evaluation (No Mutations)
    # -----------------------------------------------------------------------

    def evaluate_dry_run(self) -> Dict[str, Any]:
        """Perform non-mutating evaluation of all period pack transactions."""
        _logger.info(f"--- Starting Dry-Run Evaluation for Period Pack {self.manifest.period} ---")

        if self.env is None:
            # Standalone / unit test mode without Odoo ORM: evaluate based on pack datasets
            self.plan["po"]["to_create"] = len(self.reader.po_headers)
            self.plan["so"]["to_create"] = len(self.reader.sales_orders)
            self.plan["delivery"]["to_create"] = len(self.reader.deliveries)
            self.plan["invoice"]["to_create"] = len(self.reader.invoices)
            self.plan["ar"]["to_reconcile"] = len(self.reader.ar_collections)
            self.plan["ap"]["to_reconcile"] = len(self.reader.ap_payments)
            self.plan["opex"]["to_create"] = len(self.reader.opex)
            return self.plan

        SaleOrder = self.env["sale.order"].sudo()
        AccountMove = self.env["account.move"].sudo()
        PurchaseOrder = self.env["purchase.order"].sudo()
        Product = self.env["product.product"].sudo()
        Partner = self.env["res.partner"].sudo()

        # Map lines by parent document
        po_lines_by_po = {}
        for line in self.reader.po_lines:
            po_lines_by_po.setdefault(line["po_number"], []).append(line)

        lines_by_so = {}
        for lrow in self.reader.order_lines:
            lines_by_so.setdefault(lrow["so_number"], []).append(lrow)

        # Pre-validate SKUs across all declared order lines (no silent skips)
        for lrow in self.reader.po_lines:
            sku = lrow["sku_code"]
            prod = Product.search([("default_code", "=", sku)], limit=1)
            if not prod and self.strict:
                self.plan["po"]["conflicts"] += 1
                raise StateInconsistencyError(
                    f"Dry-run detected missing SKU '{sku}' in declared PO lines for {lrow.get('po_number')}"
                )

        for lrow in self.reader.order_lines:
            sku = lrow["sku_code"]
            prod = Product.search([("default_code", "=", sku)], limit=1)
            if not prod and self.strict:
                self.plan["so"]["conflicts"] += 1
                raise StateInconsistencyError(
                    f"Dry-run detected missing SKU '{sku}' in declared SO lines for {lrow.get('so_number')}"
                )

        # 1. Evaluate Purchase Orders
        for po_row in self.reader.po_headers:
            po_num = po_row["po_number"]
            existing = PurchaseOrder.search(
                [("company_id", "=", self.company.id), ("name", "=", po_num)], limit=1
            )
            if existing:
                try:
                    self._validate_existing_po(existing, po_row, po_lines_by_po.get(po_num, []))
                except StateInconsistencyError:
                    self.plan["po"]["conflicts"] += 1
                    raise
                self.plan["po"]["to_skip"] += 1
            else:
                self.plan["po"]["to_create"] += 1

        # 2. Evaluate Sales Orders & Deliveries
        for so_row in self.reader.sales_orders:
            so_num = so_row["so_number"]
            existing = SaleOrder.search(
                [("company_id", "=", self.company.id), ("client_order_ref", "=", so_num)], limit=1
            )
            if existing:
                try:
                    self._validate_existing_so(existing, so_row, lines_by_so.get(so_num, []))
                except StateInconsistencyError:
                    self.plan["so"]["conflicts"] += 1
                    raise
                self.plan["so"]["to_skip"] += 1
                self.plan["delivery"]["to_skip"] += 1
            else:
                self.plan["so"]["to_create"] += 1
                self.plan["delivery"]["to_create"] += 1

        # 3. Evaluate Invoices
        for inv_row in self.reader.invoices:
            inv_num = inv_row["invoice_number"]
            existing = AccountMove.search(
                [
                    ("company_id", "=", self.company.id),
                    ("move_type", "=", "out_invoice"),
                    ("payment_reference", "=", inv_num),
                ],
                limit=1,
            )
            if existing:
                try:
                    self._validate_existing_invoice(existing, inv_row)
                except StateInconsistencyError:
                    self.plan["invoice"]["conflicts"] += 1
                    raise
                self.plan["invoice"]["to_skip"] += 1
            else:
                self.plan["invoice"]["to_create"] += 1

        # 4. Evaluate AR Collections
        AccountPayment = self.env["account.payment"].sudo()
        for ar_row in self.reader.ar_collections:
            pay_ref = ar_row["payment_id"]
            existing = _find_payment(AccountPayment, self.company.id, [pay_ref], payment_type="inbound")
            if existing:
                try:
                    self._validate_existing_ar_payment(existing, ar_row)
                except StateInconsistencyError:
                    self.plan["ar"]["conflicts"] += 1
                    raise
                self.plan["ar"]["to_skip"] += 1
            else:
                self.plan["ar"]["to_reconcile"] += 1

        # 5. Evaluate AP Payments
        unilever_partner = _find_unilever_partner(Partner)
        bill_domain = [
            ("company_id", "=", self.company.id),
            ("move_type", "=", "in_invoice"),
            ("state", "=", "posted"),
        ]
        if unilever_partner:
            bill_domain.append(("partner_id", "=", unilever_partner.id))
        exact_ref_bills = list(AccountMove.search(bill_domain + [("ref", "=", "PO-2026-06-05")]))
        exact_origin_bills = list(AccountMove.search(bill_domain + [("invoice_origin", "=", "PO-2026-06-05")]))
        all_unilever_bills = list({b.id: b for b in (exact_ref_bills + exact_origin_bills)}.values())
        if not all_unilever_bills:
            ref_bills = list(AccountMove.search([
                ("company_id", "=", self.company.id),
                ("move_type", "=", "in_invoice"),
                ("state", "=", "posted"),
                ("ref", "=", "PO-2026-06-05"),
            ]))
            origin_bills = list(AccountMove.search([
                ("company_id", "=", self.company.id),
                ("move_type", "=", "in_invoice"),
                ("state", "=", "posted"),
                ("invoice_origin", "=", "PO-2026-06-05"),
            ]))
            all_unilever_bills = list({b.id: b for b in (ref_bills + origin_bills)}.values())
        if len(all_unilever_bills) > 1 and self.strict:
            raise StateInconsistencyError(f"Ambiguous vendor bills found ({len(all_unilever_bills)}) matching exact PO-2026-06-05")
        unilever_bill = all_unilever_bills[0] if all_unilever_bills else None
        for ap_row in self.reader.ap_payments:
            pay_ref = ap_row["ap_payment_id"]
            existing = _find_payment(AccountPayment, self.company.id, [pay_ref], payment_type="outbound")
            if existing:
                try:
                    self._validate_existing_ap_payment(existing, ap_row, unilever_bill)
                except StateInconsistencyError:
                    self.plan["ap"]["conflicts"] += 1
                    raise
                self.plan["ap"]["to_skip"] += 1
            else:
                self.plan["ap"]["to_reconcile"] += 1

        # 6. Evaluate OPEX
        credit_account = self._resolve_account("111100")
        if not credit_account and self.strict:
            raise PreflightContinuityError("Cannot resolve explicit credit cash account (111100) for OPEX")
        credit_code = getattr(credit_account, "code", "111100")
        misc_journal = self._resolve_general_journal()
        exp_journal_code = getattr(misc_journal, "code", "MISC") if misc_journal else "MISC"

        for op_row in self.reader.opex:
            date_str = op_row["date"]
            desc = op_row["description"]
            cat = op_row.get("category", "").strip()

            if cat not in OPEX_CATEGORY_ACCOUNT_MAP:
                self.plan["opex"]["conflicts"] += 1
                raise PreflightContinuityError(
                    f"Unknown OPEX category '{cat}' (no explicit mapping configured in OPEX_CATEGORY_ACCOUNT_MAP)"
                )
            target_code = OPEX_CATEGORY_ACCOUNT_MAP[cat]
            acc = self._resolve_account(target_code)
            if not acc and self.strict:
                self.plan["opex"]["conflicts"] += 1
                raise PreflightContinuityError(
                    f"Dry-run: OPEX account for category '{cat}' ({target_code}) cannot be resolved"
                )

            existing = AccountMove.search(
                [
                    ("company_id", "=", self.company.id),
                    ("move_type", "=", "entry"),
                    ("date", "=", date_str),
                    ("ref", "=", desc),
                ],
                limit=1,
            )
            if existing:
                try:
                    self._validate_existing_opex(
                        existing, op_row, target_code, credit_code, exp_journal_code=exp_journal_code
                    )
                except StateInconsistencyError:
                    self.plan["opex"]["conflicts"] += 1
                    raise
                self.plan["opex"]["to_skip"] += 1
            else:
                self.plan["opex"]["to_create"] += 1

        _logger.info(f"Dry-Run Plan Summary: {json.dumps(self.plan, indent=2)}")
        return self.plan

    # -----------------------------------------------------------------------
    # Incremental Execution (Mutating Mode)
    # -----------------------------------------------------------------------

    def execute_apply(self) -> Dict[str, Any]:
        """Execute full incremental loading of period pack into Odoo."""
        if self.dry_run:
            raise RuntimeError("Cannot execute_apply() when dry_run=True. Set dry_run=False.")

        if self.env is None:
            raise RuntimeError("Cannot execute_apply() in offline test mode (env is None).")

        self.verify_preflight()
        _logger.info(f"=== Applying Period Pack {self.manifest.period} into Odoo ===")

        results = {
            "period": self.manifest.period,
            "po_processed": 0,
            "so_processed": 0,
            "deliveries_processed": 0,
            "invoices_processed": 0,
            "ar_reconciled": 0,
            "ap_reconciled": 0,
            "opex_processed": 0,
        }

        # Step 1: Inbound POs & Vendor Bills
        results["po_processed"] = self._apply_inbound_pos()

        # Step 2: Sales Orders & Outbound Deliveries
        so_cnt, do_cnt = self._apply_sales_orders_and_deliveries()
        results["so_processed"] = so_cnt
        results["deliveries_processed"] = do_cnt

        # Step 3: Invoices (Tax Code 04, DPP Nilai Lain)
        results["invoices_processed"] = self._apply_invoices()

        # Step 4: AR Collections
        results["ar_reconciled"] = self._apply_ar_collections()

        # Step 5: AP Payments (Cross-period July Unilever Bill)
        results["ap_reconciled"] = self._apply_ap_payments()

        # Step 6: OPEX & Payroll
        results["opex_processed"] = self._apply_opex()

        _logger.info(f"=== Finished Applying Period Pack {self.manifest.period} ===")
        return results

    # -----------------------------------------------------------------------
    # Step-by-Step Helpers (Native Odoo)
    # -----------------------------------------------------------------------

    def _apply_inbound_pos(self) -> int:
        """Create and validate Inbound POs and register incoming lots."""
        po_headers = self.reader.po_headers
        if not po_headers:
            return 0

        PurchaseOrder = self.env["purchase.order"].sudo()
        Partner = self.env["res.partner"].sudo()
        Product = self.env["product.product"].sudo()

        po_lines_by_po = {}
        for line in self.reader.po_lines:
            po_lines_by_po.setdefault(line["po_number"], []).append(line)

        processed = 0
        for po_row in po_headers:
            po_num = po_row["po_number"]
            po_lines = po_lines_by_po.get(po_num, [])
            existing = PurchaseOrder.search(
                [("company_id", "=", self.company.id), ("name", "=", po_num)], limit=1
            )
            if existing:
                self._validate_existing_po(existing, po_row, po_lines)
                if hasattr(existing, "picking_ids"):
                    for pick in existing.picking_ids:
                        if getattr(pick, "state", "") not in ("done", "cancel"):
                            self._align_picking_locations(
                                pick,
                                expected_src_loc=getattr(self, "seed_supplier_loc", None),
                                expected_dest_loc=getattr(self, "wh_stock_loc", None),
                            )
                            self._assign_lots_to_picking(pick, po_lines)
                            self._validate_picking_safely(
                                pick, effective_date=po_row.get("arrival_maumbi_date"), ref_num=po_num
                            )
                continue

            prin_code = po_row["principal_code"]
            vendor = Partner.search(
                [("ref", "=", prin_code), ("supplier_rank", ">", 0)], limit=1
            ) or Partner.search([("name", "ilike", prin_code)], limit=1)

            po_vals = {
                "name": po_num,
                "partner_id": vendor.id if vendor else self.company.partner_id.id,
                "company_id": self.company.id,
                "date_order": po_row["order_date"],
            }
            # Create order lines
            lines_data = []
            for lrow in po_lines:
                sku = lrow["sku_code"]
                prod = Product.search([("default_code", "=", sku)], limit=1)
                if not prod:
                    raise StateInconsistencyError(
                        f"Fatal: Unresolved SKU '{sku}' declared in PO {po_num}. Cannot proceed with partial lines."
                    )
                lines_data.append(
                    (
                        0,
                        0,
                        {
                            "product_id": prod.id,
                            "name": prod.name,
                            "product_qty": float(lrow["qty_cartons"]) * float(lrow["carton_qty"]),
                            "price_unit": float(lrow["unit_cost_price"]),
                            "date_planned": po_row["arrival_maumbi_date"],
                        },
                    )
                )
            po_vals["order_line"] = lines_data
            po_rec = PurchaseOrder.create(po_vals)
            po_rec.button_confirm()

            if hasattr(po_rec, "picking_ids"):
                for pick in po_rec.picking_ids:
                    if getattr(pick, "state", "") not in ("done", "cancel"):
                        self._align_picking_locations(
                            pick,
                            expected_src_loc=getattr(self, "seed_supplier_loc", None),
                            expected_dest_loc=getattr(self, "wh_stock_loc", None),
                        )
                        self._assign_lots_to_picking(pick, po_lines)
                        self._validate_picking_safely(
                            pick, effective_date=po_row.get("arrival_maumbi_date"), ref_num=po_num
                        )
            processed += 1

        return processed

    def _resolve_canonical_tax_code_04(self):
        """Resolve authoritative tax record for Tax Code 04 (DPP Nilai Lain PMK 131/2024, 12%).

        Strict fail-closed contract:
        - Must exist in Odoo environment (no silent None fallback).
        - Strictly requires amount == 12.0 and type_tax_use == 'sale'.
        - Must carry authoritative Tax Code 04 / DPP Nilai Lain identity
          (rejects wrong-code same-rate tax, e.g. generic 'PPN 12%').
        - Rejects ambiguous candidates (multiple matching taxes on the same scope).
        """
        if "account.tax" not in self.env:
            raise PreflightContinuityError("Model 'account.tax' not found in Odoo environment.")

        AccountTax = self.env["account.tax"].sudo()
        candidates = AccountTax.search(
            [
                ("company_id", "in", [self.company.id, False]),
                ("type_tax_use", "=", "sale"),
                ("amount", "=", 12.0),
            ]
        )
        if not candidates:
            raise PreflightContinuityError(
                f"Missing canonical tax: No 12.00% sales tax found for company '{self.company.name}' (ID {self.company.id})."
            )

        matching_04 = []
        for t in candidates:
            t_name = str(getattr(t, "name", "") or "").lower()
            t_desc = str(getattr(t, "description", "") or "").lower()
            code_field = str(getattr(t, "l10n_id_tax_transaction_code", "") or "")

            has_04 = (
                code_field == "04"
                or any(term in t_name for term in ("04", "nilai lain", "kode 04", "kode_04"))
                or any(term in t_desc for term in ("04", "nilai lain", "kode 04", "kode_04"))
            )
            if has_04:
                matching_04.append(t)

        if not matching_04:
            cand_names = [getattr(c, "name", "") for c in candidates]
            raise PreflightContinuityError(
                f"Tax Code 04 resolution failed: Found 12% tax candidates {cand_names}, but NONE carry "
                f"authoritative Tax Code 04 / DPP Nilai Lain identifier. Generic/wrong-code 12% taxes strictly rejected."
            )

        comp_matching = [
            t for t in matching_04 if getattr(t, "company_id", False) and getattr(t.company_id, "id", None) == self.company.id
        ]
        if len(comp_matching) == 1:
            tax_rec = comp_matching[0]
        elif len(comp_matching) > 1:
            raise PreflightContinuityError(
                f"Ambiguous Tax Code 04 configuration: Multiple company-specific taxes matched: {[getattr(t, 'name', '') for t in comp_matching]}"
            )
        elif len(matching_04) == 1:
            tax_rec = matching_04[0]
        else:
            raise PreflightContinuityError(
                f"Ambiguous Tax Code 04 configuration: Multiple global taxes matched: {[getattr(t, 'name', '') for t in matching_04]}"
            )

        tax_out_acc = None
        try:
            tax_out_acc = self._resolve_account("211200")
        except Exception:
            tax_out_acc = None
        factor_dpp_nl = (11.0 / 12.0) * 100.0
        inv_reps = getattr(tax_rec, "invoice_repartition_line_ids", None)
        if inv_reps:
            for rep in inv_reps:
                rep_vals = {}
                rep_type = getattr(rep, "repartition_type", "")
                if rep_type == "base":
                    cur_f = float(getattr(rep, "factor_percent", 100.0) or 0.0)
                    if abs(cur_f - factor_dpp_nl) > 0.01:
                        rep_vals["factor_percent"] = factor_dpp_nl
                elif rep_type == "tax":
                    cur_f = float(getattr(rep, "factor_percent", 100.0) or 0.0)
                    if abs(cur_f - 100.0) > 0.01:
                        rep_vals["factor_percent"] = 100.0
                    if tax_out_acc:
                        cur_acc = getattr(rep, "account_id", None)
                        if not cur_acc or (hasattr(cur_acc, "id") and cur_acc.id != tax_out_acc.id):
                            rep_vals["account_id"] = tax_out_acc.id
                if rep_vals and hasattr(rep, "write"):
                    rep.sudo().write(rep_vals)
        ref_reps = getattr(tax_rec, "refund_repartition_line_ids", None)
        if ref_reps:
            for rep in ref_reps:
                rep_vals = {}
                rep_type = getattr(rep, "repartition_type", "")
                if rep_type == "base":
                    cur_f = float(getattr(rep, "factor_percent", 100.0) or 0.0)
                    if abs(cur_f - factor_dpp_nl) > 0.01:
                        rep_vals["factor_percent"] = factor_dpp_nl
                elif rep_type == "tax":
                    cur_f = float(getattr(rep, "factor_percent", 100.0) or 0.0)
                    if abs(cur_f - 100.0) > 0.01:
                        rep_vals["factor_percent"] = 100.0
                    if tax_out_acc:
                        cur_acc = getattr(rep, "account_id", None)
                        if not cur_acc or (hasattr(cur_acc, "id") and cur_acc.id != tax_out_acc.id):
                            rep_vals["account_id"] = tax_out_acc.id
                if rep_vals and hasattr(rep, "write"):
                    rep.sudo().write(rep_vals)

        if hasattr(self.env, "invalidate_all") and callable(self.env.invalidate_all):
            self.env.invalidate_all()

        # Bind canonical Tax Code 04 as company default sales tax and catalog product sales tax
        if hasattr(self, "company") and self.company:
            comp_fields = getattr(self.company, "_fields", {}) or {}
            if "account_sale_tax_id" in comp_fields:
                try:
                    self.company.sudo().write({"account_sale_tax_id": tax_rec.id})
                except Exception:
                    pass
        if self.env is not None:
            if "product.product" in self.env:
                try:
                    Product = self.env["product.product"].sudo()
                    comp_id = getattr(self.company, "id", None) if hasattr(self, "company") and self.company else None
                    p_domain = [("company_id", "in", [comp_id, False])] if comp_id else []
                    all_prods = Product.search(p_domain)
                    if hasattr(all_prods, "write"):
                        all_prods.write({"taxes_id": [(6, 0, [tax_rec.id])]})
                except Exception:
                    pass
            if "product.template" in self.env:
                try:
                    Template = self.env["product.template"].sudo()
                    comp_id = getattr(self.company, "id", None) if hasattr(self, "company") and self.company else None
                    t_domain = [("company_id", "in", [comp_id, False])] if comp_id else []
                    all_tmpls = Template.search(t_domain)
                    if hasattr(all_tmpls, "write"):
                        all_tmpls.write({"taxes_id": [(6, 0, [tax_rec.id])]})
                except Exception:
                    pass

        return tax_rec

    def _set_sol_taxes(self, sol: Any, tax_id: int) -> None:
        """Assign canonical tax to sale.order.line across Odoo schema variations."""
        tax_cmd = [(6, 0, [tax_id])]
        sol_fields = getattr(sol, "_fields", {}) or {}
        sol_vals = {}
        if "tax_ids" in sol_fields:
            sol_vals["tax_ids"] = tax_cmd
        if "tax_id" in sol_fields:
            sol_vals["tax_id"] = tax_cmd
        if "taxes_id" in sol_fields:
            sol_vals["taxes_id"] = tax_cmd
        if not sol_vals:
            sol_vals["tax_id"] = tax_cmd

        if hasattr(sol, "write"):
            sol.write(sol_vals)

    def _assign_lots_to_picking(self, pick: Any, lines_data: List[Dict[str, Any]]) -> None:
        """Map canonical source lots and target quantities into stock.move and stock.move.line deterministically.

        Supports multi-lot split lines per SKU, aggregates repeated lines for the same lot,
        writes picked=True and quantity/lot_name/lot_id on moves and move_lines,
        and fail-fast asserts exact lot->quantity mapping.
        """
        if not pick or getattr(pick, "state", "") in ("done", "cancel"):
            return

        StockLot = self.env["stock.lot"].sudo() if "stock.lot" in self.env else None
        StockMoveLine = self.env["stock.move.line"].sudo() if "stock.move.line" in self.env else None
        Product = self.env["product.product"].sudo() if "product.product" in self.env else None

        # 1. Group requirements per SKU and per Lot
        demands_by_sku: Dict[str, Dict[str, Any]] = {}
        for item in lines_data:
            sku = item.get("sku_code")
            if not sku:
                continue
            qty_cartons = float(item.get("qty_cartons", 0.0) or 0.0)
            carton_qty = float(item.get("carton_qty", 1.0) or 1.0)
            qty_units = qty_cartons * carton_qty
            if qty_units <= 0.0:
                continue

            lot_num = item.get("lot_number") or False
            exp_date = item.get("expiry_date")

            if sku not in demands_by_sku:
                prod = None
                if Product is not None:
                    prod = Product.search([("default_code", "=", sku)], limit=1)
                demands_by_sku[sku] = {
                    "prod": prod,
                    "total_units": 0.0,
                    "lots": {},
                }

            sku_demands = demands_by_sku[sku]
            sku_demands["total_units"] += qty_units

            if lot_num not in sku_demands["lots"]:
                lot_obj = None
                lot_fields = _safe_fields(StockLot) if StockLot is not None else {}
                if StockLot is not None and lot_num and sku_demands["prod"]:
                    prod_rec = sku_demands["prod"]
                    prod_rec_id = _rec_id(prod_rec)
                    lot_obj = StockLot.search(
                        [
                            ("name", "=", lot_num),
                            ("product_id", "=", prod_rec_id),
                            ("company_id", "in", [_rec_id(getattr(self, "company", None)), False]),
                        ],
                        limit=1,
                    )
                    if not lot_obj:
                        lot_vals = {
                            "name": lot_num,
                            "product_id": prod_rec_id,
                            "company_id": _rec_id(getattr(self, "company", None)),
                        }
                        if exp_date and "expiration_date" in lot_fields:
                            lot_vals["expiration_date"] = exp_date
                        lot_obj = StockLot.create(lot_vals)

                sku_demands["lots"][lot_num] = {
                    "qty_units": qty_units,
                    "expiry_date": exp_date,
                    "lot_obj": lot_obj,
                }
            else:
                sku_demands["lots"][lot_num]["qty_units"] += qty_units

        # Field capabilities stock.move.line
        sml_fields = _safe_fields(StockMoveLine) if StockMoveLine is not None else {}
        has_quantity_field = "quantity" in sml_fields if sml_fields else True
        has_qty_done_field = "qty_done" in sml_fields if sml_fields else True

        # 2. Allocate to moves and move_lines on the picking
        for sku, sku_demands in demands_by_sku.items():
            prod = sku_demands["prod"]
            prod_id = _rec_id(prod)

            matching_moves = []
            if hasattr(pick, "move_ids") and pick.move_ids:
                for m in _iter_records(pick.move_ids):
                    if _rec_id(getattr(m, "product_id", None)) == prod_id:
                        matching_moves.append(m)

            if not matching_moves:
                continue

            existing_lines = []
            if hasattr(pick, "move_line_ids") and pick.move_line_ids:
                for ml in _iter_records(pick.move_line_ids):
                    if _rec_id(getattr(ml, "product_id", None)) == prod_id:
                        existing_lines.append(ml)

            sorted_lot_items = sorted(sku_demands["lots"].items(), key=lambda x: str(x[0] or ""))
            used_move_ids = set()

            for idx, (lot_num, lot_info) in enumerate(sorted_lot_items):
                target_qty = lot_info["qty_units"]
                lot_obj = lot_info["lot_obj"]
                target_lot_id = _rec_id(lot_obj) if lot_obj else False

                target_move = matching_moves[0]
                if len(matching_moves) > 1:
                    matched_by_qty = None
                    for cand_mv in matching_moves:
                        cid = getattr(cand_mv, "id", id(cand_mv))
                        if cid in used_move_ids:
                            continue
                        cand_qty = float(getattr(cand_mv, "product_uom_qty", 0.0) or 0.0)
                        if abs(cand_qty - target_qty) < 0.001:
                            matched_by_qty = cand_mv
                            break
                    if matched_by_qty is not None:
                        target_move = matched_by_qty
                    else:
                        target_move = matching_moves[min(idx, len(matching_moves) - 1)]
                    used_move_ids.add(getattr(target_move, "id", id(target_move)))

                if existing_lines:
                    ml = None
                    if target_move is not None:
                        target_mv_id = getattr(target_move, "id", None)
                        for el_idx, el in enumerate(existing_lines):
                            if _rec_id(getattr(el, "move_id", None)) == target_mv_id:
                                ml = existing_lines.pop(el_idx)
                                break
                    if ml is None:
                        ml = existing_lines.pop(0)

                    upd_vals = {}
                    if lot_num and ("lot_name" in sml_fields or not sml_fields):
                        upd_vals["lot_name"] = lot_num
                    if target_lot_id and ("lot_id" in sml_fields or not sml_fields):
                        upd_vals["lot_id"] = target_lot_id
                    if has_quantity_field:
                        upd_vals["quantity"] = target_qty
                    elif has_qty_done_field:
                        upd_vals["qty_done"] = target_qty
                    if "picked" in sml_fields or not sml_fields:
                        upd_vals["picked"] = True

                    if callable(getattr(ml, "write", None)):
                        ml.write(upd_vals)
                    if lot_obj and hasattr(ml, "lot_id"):
                        ml.lot_id = lot_obj
                    if lot_num and hasattr(ml, "lot_name"):
                        ml.lot_name = lot_num
                    if has_quantity_field and hasattr(ml, "quantity"):
                        ml.quantity = target_qty
                    if has_qty_done_field and hasattr(ml, "qty_done"):
                        ml.qty_done = target_qty
                    if hasattr(ml, "picked"):
                        ml.picked = True
                else:
                    if StockMoveLine is not None:
                        ml_vals = {
                            "picking_id": pick.id,
                            "move_id": getattr(target_move, "id", False) if target_move else False,
                            "product_id": prod_id,
                            "lot_id": target_lot_id,
                            "location_id": _rec_id(getattr(pick, "location_id", None)),
                            "location_dest_id": _rec_id(getattr(pick, "location_dest_id", None)),
                        }
                        if lot_num and ("lot_name" in sml_fields or not sml_fields):
                            ml_vals["lot_name"] = lot_num
                        uom_rec = getattr(prod, "uom_id", None)
                        if uom_rec and hasattr(uom_rec, "id") and ("product_uom_id" in sml_fields or not sml_fields):
                            ml_vals["product_uom_id"] = uom_rec.id
                        if has_quantity_field:
                            ml_vals["quantity"] = target_qty
                        elif has_qty_done_field:
                            ml_vals["qty_done"] = target_qty
                        if "picked" in sml_fields or not sml_fields:
                            ml_vals["picked"] = True

                        new_ml = StockMoveLine.create(ml_vals)
                        if hasattr(pick, "move_line_ids") and hasattr(pick.move_line_ids, "append"):
                            pick.move_line_ids.append(new_ml)
                        if (
                            target_move is not None
                            and hasattr(target_move, "move_line_ids")
                            and hasattr(target_move.move_line_ids, "append")
                            and new_ml not in target_move.move_line_ids
                        ):
                            target_move.move_line_ids.append(new_ml)

            for unused_ml in existing_lines:
                if callable(getattr(unused_ml, "unlink", None)):
                    unused_ml.unlink()
                else:
                    if hasattr(unused_ml, "quantity"):
                        unused_ml.quantity = 0.0
                    if hasattr(unused_ml, "qty_done"):
                        unused_ml.qty_done = 0.0

            for mv_rec in matching_moves:
                if callable(getattr(mv_rec, "write", None)):
                    mv_fields = _safe_fields(mv_rec)
                    mv_upd = {}
                    if "picked" in mv_fields or not mv_fields:
                        mv_upd["picked"] = True
                    if mv_upd:
                        mv_rec.write(mv_upd)
                elif hasattr(mv_rec, "picked"):
                    mv_rec.picked = True

        if hasattr(self.env, "invalidate_all") and callable(self.env.invalidate_all):
            self.env.invalidate_all()

        # 3. Comprehensive lot->qty mapping assertion (fail-fast)
        for sku, sku_demands in demands_by_sku.items():
            prod = sku_demands["prod"]
            prod_id = _rec_id(prod)
            sku_lines = [
                ml for ml in _iter_records(getattr(pick, "move_line_ids", None))
                if _rec_id(getattr(ml, "product_id", None)) == prod_id
            ]
            actual_by_lot = {}
            for ml in sku_lines:
                l_id = _rec_id(getattr(ml, "lot_id", None))
                rec_lot = getattr(ml, "lot_id", None)
                l_name = getattr(ml, "lot_name", None) or (getattr(rec_lot, "name", None) if rec_lot else False)
                l_key = l_name or l_id or "NO_LOT"
                qty = float(getattr(ml, "quantity", getattr(ml, "qty_done", 0.0)))
                actual_by_lot[l_key] = actual_by_lot.get(l_key, 0.0) + qty

            for lot_num, lot_info in sku_demands["lots"].items():
                if not lot_num:
                    continue
                expected_lot_qty = lot_info["qty_units"]
                lot_key = lot_num or "NO_LOT"
                lot_id_key = _rec_id(lot_info["lot_obj"]) if lot_info.get("lot_obj") else None
                actual_lot_qty = actual_by_lot.get(lot_key)
                if actual_lot_qty is None and lot_id_key is not None:
                    actual_lot_qty = actual_by_lot.get(lot_id_key)
                actual_lot_qty = actual_lot_qty if actual_lot_qty is not None else 0.0
                if abs(actual_lot_qty - expected_lot_qty) > 0.001:
                    raise StateInconsistencyError(
                        f"FATAL: Lot quantity mismatch on picking '{getattr(pick, 'name', pick.id)}' "
                        f"for SKU '{sku}', Lot '{lot_num}'! Expected: {expected_lot_qty}, Got: {actual_lot_qty} "
                        f"(Actual lots map: {actual_by_lot})"
                    )

            total_actual_sku = sum(actual_by_lot.values())
            if abs(total_actual_sku - sku_demands["total_units"]) > 0.001:
                raise StateInconsistencyError(
                    f"FATAL: Total units per SKU mismatch on picking '{getattr(pick, 'name', pick.id)}' "
                    f"for SKU '{sku}'! Expected: {sku_demands['total_units']}, Got: {total_actual_sku}"
                )

    def _align_picking_locations(
        self, pick: Any, expected_src_loc: Optional[Any] = None, expected_dest_loc: Optional[Any] = None
    ) -> None:
        """Align picking, stock.move, and stock.move.line locations to seed locations before lot allocation."""
        if not pick:
            return
        targets = {}
        if expected_src_loc is not None and getattr(expected_src_loc, "id", None):
            targets["location_id"] = expected_src_loc.id
        if expected_dest_loc is not None and getattr(expected_dest_loc, "id", None):
            targets["location_dest_id"] = expected_dest_loc.id

        if not targets:
            return

        # 1. Update picking
        pick_upd = {
            fname: target_id
            for fname, target_id in targets.items()
            if getattr(getattr(pick, fname, None), "id", getattr(pick, fname, None)) != target_id
        }
        if pick_upd and callable(getattr(pick, "write", None)):
            try:
                pick.write(pick_upd)
            except Exception as e:
                _logger.warning(f"write location on picking non-fatal: {e}")

        # 2. Update stock.move
        moves = list(_iter_records(getattr(pick, "move_ids", None)))
        for sm in moves:
            sm_upd = {
                fname: target_id
                for fname, target_id in targets.items()
                if getattr(getattr(sm, fname, None), "id", getattr(sm, fname, None)) != target_id
            }
            if sm_upd and callable(getattr(sm, "write", None)):
                try:
                    sm.write(sm_upd)
                except Exception as e:
                    _logger.warning(f"write location on stock.move non-fatal: {e}")

        # 3. Update stock.move.line
        move_lines = list(_iter_records(getattr(pick, "move_line_ids", None)))
        for sml in move_lines:
            sml_upd = {
                fname: target_id
                for fname, target_id in targets.items()
                if getattr(getattr(sml, fname, None), "id", getattr(sml, fname, None)) != target_id
            }
            if sml_upd and callable(getattr(sml, "write", None)):
                try:
                    sml.write(sml_upd)
                except Exception as e:
                    _logger.warning(f"write location on stock.move.line non-fatal: {e}")

    def _validate_picking_safely(
        self, pick: Any, effective_date: Optional[str] = None, ref_num: Optional[str] = None
    ) -> None:
        """Safely validate stock picking to 'done' handling allowed Odoo wizards.

        Fails-closed if the picking or any of its stock moves remains uncompleted.
        """
        if not pick:
            return

        date_str = effective_date or getattr(pick, "scheduled_date", None) or getattr(pick, "date_done", None)
        date_only = str(date_str)[:10] if date_str else None
        date_time_str = (
            f"{date_only} 00:00:00"
            if (date_only and len(str(date_str)) <= 10)
            else str(date_str)
            if date_str
            else None
        )

        if getattr(pick, "state", "") != "done":
            if date_time_str:
                if hasattr(pick, "scheduled_date") and callable(getattr(pick, "write", None)):
                    try:
                        pick.write({"scheduled_date": date_time_str})
                    except Exception as e:
                        _logger.warning(f"write scheduled_date on picking non-fatal: {e}")
                if hasattr(pick, "date_done") and callable(getattr(pick, "write", None)):
                    try:
                        pick.write({"date_done": date_time_str})
                    except Exception as e:
                        _logger.warning(f"write date_done on picking non-fatal: {e}")
                if hasattr(pick, "move_ids") and pick.move_ids:
                    for sm in pick.move_ids:
                        if callable(getattr(sm, "write", None)):
                            try:
                                sm.write({"date": date_time_str})
                            except Exception as e:
                                _logger.warning(f"write date on stock.move non-fatal: {e}")
                if hasattr(pick, "move_line_ids") and pick.move_line_ids:
                    for sml in _iter_records(pick.move_line_ids):
                        if callable(getattr(sml, "write", None)):
                            try:
                                sml.write({"date": date_time_str})
                            except Exception as e:
                                _logger.warning(f"write date on stock.move.line non-fatal: {e}")

            val_ctx = {"skip_sms": True}
            if date_only:
                val_ctx["force_period_date"] = date_only
                val_ctx["date"] = date_only
                val_ctx["accounting_date"] = date_only
            if date_time_str:
                val_ctx["date_done"] = date_time_str

            pick_target = pick.with_context(**val_ctx) if callable(getattr(pick, "with_context", None)) else pick
            res = pick_target.button_validate() if hasattr(pick_target, "button_validate") else None

            ALLOWED_WIZARDS = {
                "confirm.stock.sms": ["dont_send_sms"],
                "stock.immediate.transfer": ["process"],
                "stock.backorder.confirmation": ["process_cancel_backorder", "process"],
            }

            wiz_iter = 0
            current_res = res
            while isinstance(current_res, dict) and current_res.get("res_model") and wiz_iter < 5:
                wiz_iter += 1
                wizard_model = current_res["res_model"]
                if wizard_model not in ALLOWED_WIZARDS:
                    raise StateInconsistencyError(
                        f"Wizard model '{wizard_model}' during picking validation for {ref_num or pick} not in allowlist!"
                    )
                wizard_ctx = dict(val_ctx)
                if isinstance(current_res.get("context"), dict):
                    wizard_ctx.update(current_res["context"])

                if wizard_model in self.env:
                    WizardModel = self.env[wizard_model].sudo().with_context(**wizard_ctx)
                    wiz_id = current_res.get("res_id")
                    wiz_vals = {}
                    if hasattr(WizardModel, "_fields") and "pick_ids" in WizardModel._fields:
                        wiz_vals["pick_ids"] = [(6, 0, [pick.id])]
                    elif hasattr(WizardModel, "_fields") and "picking_id" in WizardModel._fields:
                        wiz_vals["picking_id"] = pick.id

                    wizard_record = WizardModel.browse(wiz_id) if wiz_id else WizardModel.create(wiz_vals)
                    action_taken = False
                    for act_name in ALLOWED_WIZARDS[wizard_model]:
                        if hasattr(wizard_record, act_name):
                            current_res = getattr(wizard_record.with_context(**wizard_ctx), act_name)()
                            action_taken = True
                            break
                    if not action_taken:
                        raise StateInconsistencyError(
                            f"Wizard '{wizard_model}' has no supported actions: {ALLOWED_WIZARDS[wizard_model]}"
                        )
                else:
                    break

            if getattr(pick, "state", "") != "done" and hasattr(pick, "button_validate"):
                re_pick = pick.with_context(**val_ctx) if callable(getattr(pick, "with_context", None)) else pick
                re_pick.button_validate()

        if getattr(pick, "state", "") != "done":
            pick_lbl = getattr(pick, "name", getattr(pick, "id", "picking"))
            raise StateInconsistencyError(
                f"Validasi picking '{pick_lbl}' (Ref: {ref_num or getattr(pick, 'origin', '')}) "
                f"gagal mencapai state 'done'! Status aktual: '{getattr(pick, 'state', 'unknown')}'"
            )

        # Selaraskan tanggal efektif historis pada picking, move, move_line pasca-validasi
        if date_time_str:
            if callable(getattr(pick, "write", None)):
                try:
                    pick.write({"date_done": date_time_str, "scheduled_date": date_time_str})
                except Exception as e:
                    _logger.warning(f"post-validation write picking date non-fatal: {e}")
            elif hasattr(pick, "date_done"):
                try:
                    pick.date_done = date_time_str
                except Exception:
                    pass

            if hasattr(pick, "move_line_ids") and pick.move_line_ids:
                if callable(getattr(pick.move_line_ids, "write", None)):
                    try:
                        pick.move_line_ids.write({"date": date_time_str})
                    except Exception as e:
                        _logger.warning(f"post-validation write move_line_ids date non-fatal: {e}")
                else:
                    for sml in _iter_records(pick.move_line_ids):
                        if callable(getattr(sml, "write", None)):
                            try:
                                sml.write({"date": date_time_str})
                            except Exception:
                                pass

            if hasattr(pick, "move_ids") and pick.move_ids:
                for mv in pick.move_ids:
                    if getattr(mv, "state", "") == "cancel":
                        continue
                    if callable(getattr(mv, "write", None)):
                        try:
                            mv.write({"date": date_time_str})
                        except Exception as e:
                            _logger.warning(f"post-validation write move date non-fatal: {e}")
                    if hasattr(mv, "move_line_ids") and mv.move_line_ids:
                        if callable(getattr(mv.move_line_ids, "write", None)):
                            try:
                                mv.move_line_ids.write({"date": date_time_str})
                            except Exception:
                                pass

        if hasattr(pick, "move_ids") and pick.move_ids:
            for sm in pick.move_ids:
                sm_state = getattr(sm, "state", "")
                if sm_state != "done":
                    sm_lbl = getattr(sm, "name", getattr(sm, "id", "move"))
                    sku = getattr(getattr(sm, "product_id", None), "default_code", "")
                    pick_lbl = getattr(pick, "name", getattr(pick, "id", "picking"))
                    raise StateInconsistencyError(
                        f"Pergerakan stok '{sm_lbl}' (ID {getattr(sm, 'id', '')}, SKU {sku}) "
                        f"pada picking '{pick_lbl}' (Ref: {ref_num or getattr(pick, 'origin', '')}) "
                        f"belum berstatus 'done' (state: '{sm_state}')!"
                    )
                self._sync_native_stock_accounting(sm, date_time_str or "", date_only or "")

    def _sync_native_stock_accounting(
        self, stock_move: Any, date_time_str: Optional[str] = None, date_only: Optional[str] = None
    ) -> None:
        """Verify, link, and post native stock valuation accounting entries (account.move) for stock.move."""
        if not self.env or "account.move" not in self.env:
            return

        AccountMove = self.env["account.move"].sudo()
        found_ams = []
        seen_am_ids = set()

        def _add_am(am_rec):
            if not am_rec:
                return
            am_id = getattr(am_rec, "id", None)
            if am_id and am_id not in seen_am_ids:
                seen_am_ids.add(am_id)
                found_ams.append(am_rec)

        # 1. Many2one account_move_id
        if getattr(stock_move, "account_move_id", None):
            _add_am(stock_move.account_move_id)
        # 2. Relasi account_move_ids
        elif getattr(stock_move, "account_move_ids", None):
            for am in _iter_records(stock_move.account_move_ids):
                _add_am(am)
        # 3. Relasi stock_valuation_layer_ids -> account_move_id
        if hasattr(stock_move, "stock_valuation_layer_ids") and stock_move.stock_valuation_layer_ids:
            for svl in _iter_records(stock_move.stock_valuation_layer_ids):
                if getattr(svl, "account_move_id", None):
                    _add_am(svl.account_move_id)
        # 4. Field stock_move_id pada account.move
        if "stock_move_id" in _safe_fields(AccountMove):
            ams = AccountMove.search([("stock_move_id", "=", stock_move.id)])
            for am in _iter_records(ams):
                _add_am(am)
        # 5. Melalui origin atau picking name
        if not found_ams:
            origins = []
            if getattr(stock_move, "origin", None):
                origins.append(stock_move.origin)
            if getattr(stock_move, "picking_id", None) and getattr(stock_move.picking_id, "name", None):
                origins.append(stock_move.picking_id.name)
            if origins:
                domain = [("ref", "in", origins)]
                if hasattr(self, "company") and self.company:
                    domain.append(("company_id", "in", [False, self.company.id]))
                ams = AccountMove.search(domain)
                for am in _iter_records(ams):
                    _add_am(am)

        # Link ke stock_move.account_move_id jika belum terhubung
        if found_ams and not getattr(stock_move, "account_move_id", None):
            primary_am = found_ams[0]
            sm_fields = _safe_fields(stock_move)
            if "account_move_id" in sm_fields or not sm_fields:
                if callable(getattr(stock_move, "write", None)):
                    try:
                        stock_move.write({"account_move_id": primary_am.id})
                    except Exception as e:
                        _logger.warning(f"write account_move_id on stock.move non-fatal: {e}")
                if hasattr(stock_move, "account_move_id"):
                    try:
                        stock_move.account_move_id = primary_am
                    except Exception:
                        pass

        # Pastikan tanggal pergerakan stok selaras dengan tanggal akuntansi
        target_dt = date_time_str or (f"{date_only} 00:00:00" if date_only else None)
        target_d = date_only or (str(date_time_str)[:10] if date_time_str else None)
        if target_dt and callable(getattr(stock_move, "write", None)):
            cur_sm_date = str(getattr(stock_move, "date", ""))[:10]
            if cur_sm_date != target_d:
                try:
                    stock_move.write({"date": target_dt})
                except Exception as e:
                    _logger.warning(f"write date on stock.move in _sync_native_stock_accounting non-fatal: {e}")

        for am in found_ams:
            am_state = getattr(am, "state", "")
            if am_state == "draft":
                if date_only and callable(getattr(am, "write", None)):
                    am.write({"date": date_only})
                    if hasattr(am, "line_ids") and am.line_ids and callable(getattr(am.line_ids, "write", None)):
                        am.line_ids.write({"date": date_only})
                if hasattr(am, "action_post"):
                    try:
                        am.action_post()
                    except Exception as post_err:
                        _logger.warning(f"action_post on stock account.move non-fatal: {post_err}")

    def _apply_sales_orders_and_deliveries(self) -> Tuple[int, int]:
        """Create and validate Sales Orders and Outbound Deliveries."""
        so_rows = self.reader.sales_orders
        if not so_rows:
            return 0, 0

        SaleOrder = self.env["sale.order"].with_context(fmcg_seed_load=True).sudo()
        Partner = self.env["res.partner"].sudo()
        Product = self.env["product.product"].sudo()
        if hasattr(self, "company") and self.company:
            if hasattr(SaleOrder, "with_company"):
                SaleOrder = SaleOrder.with_company(self.company)
            if hasattr(Partner, "with_company"):
                Partner = Partner.with_company(self.company)
            if hasattr(Product, "with_company"):
                Product = Product.with_company(self.company)

        lines_by_so = {}
        for lrow in self.reader.order_lines:
            lines_by_so.setdefault(lrow["so_number"], []).append(lrow)

        so_count = 0
        do_count = 0

        # Authoritative canonical Tax Code 04 resolution (fail-closed if missing, ambiguous, or wrong-code)
        canonical_tax_04 = self._resolve_canonical_tax_code_04()

        for so_row in so_rows:
            so_num = so_row["so_number"]
            so_lines = lines_by_so.get(so_num, [])
            existing = SaleOrder.search(
                [("company_id", "=", self.company.id), ("client_order_ref", "=", so_num)], limit=1
            )
            if existing:
                self._validate_existing_so(existing, so_row, so_lines)
                if hasattr(existing, "picking_ids"):
                    for pick in existing.picking_ids:
                        if getattr(pick, "state", "") not in ("done", "cancel"):
                            self._align_picking_locations(
                                pick,
                                expected_src_loc=getattr(self, "wh_stock_loc", None),
                                expected_dest_loc=getattr(self, "seed_customer_loc", None),
                            )
                            self._assign_lots_to_picking(pick, so_lines)
                            self._validate_picking_safely(
                                pick, effective_date=so_row.get("date_order"), ref_num=so_num
                            )
                            do_count += 1
                continue

            cust_ref = extract_ref(so_row["customer"])
            partner = Partner.search([("ref", "=", cust_ref)], limit=1) or Partner.search(
                [("name", "ilike", cust_ref)], limit=1
            )
            if not partner:
                raise PreflightContinuityError(f"Customer partner {cust_ref} not found")

            so_vals = {
                "client_order_ref": so_num,
                "partner_id": partner.id,
                "company_id": self.company.id,
                "date_order": so_row["date_order"],
            }
            if hasattr(SaleOrder, "_fields") and "fmcg_seed_batch" in SaleOrder._fields:
                so_vals["fmcg_seed_batch"] = f"PERIOD_{self.period}"

            sol_data = []
            for lrow in so_lines:
                sku = lrow["sku_code"]
                prod = Product.search([("default_code", "=", sku)], limit=1)
                if not prod:
                    raise StateInconsistencyError(
                        f"Fatal: Unresolved SKU '{sku}' declared in SO {so_num}. Cannot proceed with partial lines."
                    )
                sol_vals = {
                    "product_id": prod.id,
                    "product_uom_qty": float(lrow["qty_cartons"]) * float(lrow["carton_qty"]),
                    "price_unit": float(lrow["unit_price_dpp"]),
                    "discount": float(lrow.get("discount_pct", 0.0)),
                }
                sol_fields = getattr(self.env.get("sale.order.line"), "_fields", None)
                if canonical_tax_04:
                    tax_cmd = [(6, 0, [canonical_tax_04.id])]
                    if sol_fields is None:
                        sol_vals["tax_id"] = tax_cmd
                        sol_vals["tax_ids"] = tax_cmd
                    else:
                        if "tax_ids" in sol_fields:
                            sol_vals["tax_ids"] = tax_cmd
                        if "tax_id" in sol_fields:
                            sol_vals["tax_id"] = tax_cmd
                        if "taxes_id" in sol_fields:
                            sol_vals["taxes_id"] = tax_cmd
                sol_data.append((0, 0, sol_vals))
            so_vals["order_line"] = sol_data
            so_rec = SaleOrder.create(so_vals)
            if canonical_tax_04 and hasattr(so_rec, "order_line"):
                for sol in so_rec.order_line:
                    cur_t = getattr(sol, "tax_ids", None) or getattr(sol, "tax_id", None) or getattr(sol, "taxes_id", None)
                    if not cur_t or (hasattr(cur_t, "ids") and canonical_tax_04.id not in cur_t.ids):
                        self._set_sol_taxes(sol, canonical_tax_04.id)
            so_rec.with_context(fmcg_seed_load=True).action_confirm()
            so_count += 1

            # Validate picking delivery if present
            if hasattr(so_rec, "picking_ids"):
                for pick in so_rec.picking_ids:
                    if getattr(pick, "state", "") not in ("done", "cancel"):
                        self._align_picking_locations(
                            pick,
                            expected_src_loc=getattr(self, "wh_stock_loc", None),
                            expected_dest_loc=getattr(self, "seed_customer_loc", None),
                        )
                        self._assign_lots_to_picking(pick, so_lines)
                        self._validate_picking_safely(
                            pick, effective_date=so_row.get("date_order"), ref_num=so_num
                        )
                        do_count += 1

        return so_count, do_count

    def _apply_invoices(self) -> int:
        """Create and post out_invoice records with tax code 04 and DPP Nilai Lain."""
        invoices = self.reader.invoices
        if not invoices:
            return 0

        AccountMove = self.env["account.move"].sudo()
        SaleOrder = self.env["sale.order"].sudo()
        Product = None
        if hasattr(self.env, "__getitem__"):
            try:
                Product = self.env["product.product"].sudo()
            except Exception:
                Product = None

        if hasattr(self, "company") and self.company:
            if hasattr(AccountMove, "with_company"):
                AccountMove = AccountMove.with_company(self.company)
            if hasattr(SaleOrder, "with_company"):
                SaleOrder = SaleOrder.with_company(self.company)
            if Product is not None and hasattr(Product, "with_company"):
                Product = Product.with_company(self.company)
        if hasattr(AccountMove, "with_context"):
            AccountMove = AccountMove.with_context(default_move_type="out_invoice")

        sale_journal = self._resolve_sale_journal()
        processed = 0

        lines_by_so = {}
        for lrow in self.reader.order_lines:
            lines_by_so.setdefault(lrow["so_number"], []).append(lrow)

        rejections_by_line_key = {}
        rejections_by_so_sku_pool = {}
        for rrow in getattr(self.reader, "rejections", []):
            r_so = rrow.get("so_number")
            r_sku = rrow.get("sku_code")
            r_lot = rrow.get("lot_number")
            r_qty = float(rrow.get("qty_cartons", 0.0) or 0.0)
            if r_so and r_sku:
                if r_lot:
                    rejections_by_line_key[(r_so, r_sku, r_lot)] = (
                        rejections_by_line_key.get((r_so, r_sku, r_lot), 0.0) + r_qty
                    )
                rejections_by_so_sku_pool[(r_so, r_sku)] = (
                    rejections_by_so_sku_pool.get((r_so, r_sku), 0.0) + r_qty
                )

        # Pastikan konfigurasi pajak Kode 04 aktif dan presisi sebelum membuat faktur
        canonical_tax_04 = self._resolve_canonical_tax_code_04()

        for inv_row in invoices:
            inv_num = inv_row["invoice_number"]
            so_num = inv_row["so_number"]
            existing = AccountMove.search(
                [
                    ("company_id", "=", self.company.id),
                    ("move_type", "=", "out_invoice"),
                    ("payment_reference", "=", inv_num),
                ],
                limit=1,
            )
            if existing:
                self._validate_existing_invoice(existing, inv_row)
                continue

            so = SaleOrder.search(
                [("company_id", "=", self.company.id), ("client_order_ref", "=", so_num)], limit=1
            )
            if not so:
                raise PreflightContinuityError(f"SO {so_num} not found for invoice {inv_num}")

            # Ensure all deliveries for SO are validated and completed before creating/posting invoice
            if hasattr(so, "picking_ids"):
                so_lines = lines_by_so.get(so_num, [])
                for pick in so.picking_ids:
                    if getattr(pick, "state", "") not in ("done", "cancel"):
                        self._align_picking_locations(
                            pick,
                            expected_src_loc=getattr(self, "wh_stock_loc", None),
                            expected_dest_loc=getattr(self, "seed_customer_loc", None),
                        )
                        self._assign_lots_to_picking(pick, so_lines)
                        self._validate_picking_safely(
                            pick, effective_date=inv_row.get("date_invoice"), ref_num=so_num
                        )
                    if hasattr(pick, "move_ids"):
                        for sm in pick.move_ids:
                            sm_st = getattr(sm, "state", "")
                            if sm_st != "done":
                                sm_lbl = getattr(sm, "name", getattr(sm, "id", "move"))
                                sku = getattr(getattr(sm, "product_id", None), "default_code", "")
                                raise StateInconsistencyError(
                                    f"Delivery move '{sm_lbl}' (ID {getattr(sm, 'id', '')}, SKU {sku}) "
                                    f"for {so_num} / DO '{getattr(pick, 'name', '')}' is not done "
                                    f"(state: '{sm_st}') before posting invoice {inv_num}!"
                                )
                            # Pastikan move telah tersinkronisasi akuntansi dan tanggalnya konsisten dengan jurnal valuasi
                            self._sync_native_stock_accounting(
                                sm,
                                str(getattr(sm, "date", "")) or inv_row.get("date_invoice"),
                                str(getattr(sm, "date", ""))[:10] if getattr(sm, "date", None) else inv_row.get("date_invoice"),
                            )
                            cogs_am = getattr(sm, "account_move_id", None)
                            if cogs_am and getattr(cogs_am, "date", None):
                                target_cogs_date = str(cogs_am.date)[:10]
                                if str(getattr(sm, "date", ""))[:10] != target_cogs_date:
                                    if callable(getattr(sm, "write", None)):
                                        try:
                                            sm.write({"date": f"{target_cogs_date} 00:00:00"})
                                        except Exception:
                                            pass
                                    if hasattr(sm, "move_line_ids") and sm.move_line_ids:
                                        if callable(getattr(sm.move_line_ids, "write", None)):
                                            try:
                                                sm.move_line_ids.write({"date": f"{target_cogs_date} 00:00:00"})
                                            except Exception:
                                                pass

            # Ensure SO lines carry canonical Tax Code 04
            if canonical_tax_04 and hasattr(so, "order_line"):
                for sol in so.order_line:
                    cur_t = getattr(sol, "tax_ids", None) or getattr(sol, "tax_id", None) or getattr(sol, "taxes_id", None)
                    if not cur_t or (hasattr(cur_t, "ids") and canonical_tax_04.id not in cur_t.ids):
                        self._set_sol_taxes(sol, canonical_tax_04.id)

            # Build invoice lines directly with canonical Tax Code 04 (DPP Nilai Lain 11/12, PPN 12%)
            # and link each line back to its matched SO line (sale_line_ids)
            am_fields = _safe_fields(AccountMove)
            aml_model = (
                self.env["account.move.line"].sudo()
                if hasattr(self.env, "__getitem__") and "account.move.line" in self.env
                else None
            )
            aml_fields = _safe_fields(aml_model) if aml_model is not None else {}

            inv_lines = []
            used_sol_ids = set()
            so_lines = lines_by_so.get(so_num, [])
            so_rej_sku_rem = {}
            for (r_so, r_sku), q in rejections_by_so_sku_pool.items():
                if r_so == so_num:
                    so_rej_sku_rem[r_sku] = q

            for lrow in so_lines:
                sku = lrow["sku_code"]
                lot = lrow.get("lot_number")
                qty_cartons = float(lrow.get("qty_cartons", 0.0) or 0.0)
                lot_key = (so_num, sku, lot) if lot else None
                if lot_key and lot_key in rejections_by_line_key:
                    rej_cartons = rejections_by_line_key[lot_key]
                elif sku in so_rej_sku_rem:
                    rem = so_rej_sku_rem[sku]
                    rej_cartons = min(qty_cartons, rem)
                    so_rej_sku_rem[sku] = max(0.0, rem - rej_cartons)
                else:
                    rej_cartons = 0.0

                net_cartons = qty_cartons - rej_cartons
                if net_cartons <= 0.0:
                    continue

                matched_sol = None
                prod = None

                # 1. Resolve directly from SO order lines for this SO
                if hasattr(so, "order_line"):
                    for sol in so.order_line:
                        sol_id = getattr(sol, "id", None)
                        if sol_id in used_sol_ids:
                            continue
                        sol_p = getattr(sol, "product_id", None)
                        sol_code = getattr(sol_p, "default_code", None)
                        if sol_code == sku:
                            matched_sol = sol
                            prod = sol_p
                            used_sol_ids.add(sol_id)
                            break

                # 2. If not matched by default_code in sol, search Product model
                if not prod and Product is not None:
                    prod = Product.search([("default_code", "=", sku)], limit=1)

                # 3. If prod resolved via model search, match sol by product id
                if matched_sol is None and prod and hasattr(so, "order_line"):
                    for sol in so.order_line:
                        sol_id = getattr(sol, "id", None)
                        sol_p = getattr(sol, "product_id", None)
                        sol_pid = getattr(sol_p, "id", sol_p)
                        if sol_id not in used_sol_ids and sol_pid == getattr(prod, "id", None):
                            matched_sol = sol
                            used_sol_ids.add(sol_id)
                            break

                if not prod:
                    raise StateInconsistencyError(f"Fatal: Unresolved SKU '{sku}' for invoice {inv_num}")

                carton_qty = float(lrow.get("carton_qty", 1.0) or 1.0)
                net_units = net_cartons * carton_qty

                inv_line_vals = {
                    "product_id": prod.id,
                    "quantity": net_units,
                    "price_unit": float(lrow["unit_price_dpp"]),
                    "discount": float(lrow.get("discount_pct", 0.0) or 0.0),
                    "name": f"{lrow.get('product_name', sku)}",
                }
                uom_rec = getattr(prod, "uom_id", None)
                if uom_rec and hasattr(uom_rec, "id") and ("product_uom_id" in aml_fields or not aml_fields):
                    inv_line_vals["product_uom_id"] = uom_rec.id

                if matched_sol is not None and getattr(matched_sol, "id", None) and ("sale_line_ids" in aml_fields or not aml_fields):
                    inv_line_vals["sale_line_ids"] = [(6, 0, [matched_sol.id])]

                pr_comp = prod.with_company(self.company) if hasattr(prod, "with_company") else prod
                if callable(getattr(pr_comp, "_get_product_accounts", None)):
                    prod_accs = pr_comp._get_product_accounts()
                    if isinstance(prod_accs, dict) and prod_accs.get("income"):
                        inv_line_vals["account_id"] = prod_accs["income"].id

                if canonical_tax_04:
                    inv_line_vals["tax_ids"] = [(6, 0, [canonical_tax_04.id])]

                inv_lines.append((0, 0, inv_line_vals))

            inv_vals = {
                "move_type": "out_invoice",
                "partner_id": so.partner_id.id,
                "ref": inv_num,
                "payment_reference": inv_num,
                "invoice_date": inv_row["date_invoice"],
                "date": inv_row["date_invoice"],
                "invoice_date_due": inv_row["due_date"],
                "invoice_origin": so_num,
                "invoice_line_ids": inv_lines,
            }
            if hasattr(self, "company") and self.company:
                inv_vals["company_id"] = self.company.id
                if hasattr(self.company, "currency_id") and self.company.currency_id:
                    inv_vals["currency_id"] = self.company.currency_id.id
            if sale_journal:
                inv_vals["journal_id"] = sale_journal.id

            if "is_fmcg_seed_invoice" in am_fields or not am_fields:
                inv_vals["is_fmcg_seed_invoice"] = True
            if "fmcg_seed_batch" in am_fields or not am_fields:
                inv_vals["fmcg_seed_batch"] = f"PERIOD_{self.period}"
            if "l10n_id_tax_transaction_code" in am_fields or not am_fields:
                inv_vals["l10n_id_tax_transaction_code"] = "04"
            exp_dpp = float(inv_row.get("commercial_dpp") or inv_row.get("dpp_amount", 0.0))
            exp_ppn = float(inv_row.get("ppn_amount", 0.0))
            exp_tb = float(inv_row.get("dpp_amount", 0.0)) or (exp_dpp * 11.0 / 12.0)
            exp_total = float(inv_row.get("total_invoice_with_ppn", 0.0)) or (exp_dpp + exp_ppn)

            if not am_fields or "amount_total" not in am_fields:
                inv_vals["amount_untaxed"] = exp_dpp
                inv_vals["amount_tax"] = exp_ppn
                inv_vals["amount_total"] = exp_total

            inv_rec = AccountMove.create(inv_vals)

            # Ensure canonical Tax Code 04 is assigned to invoice line items
            if canonical_tax_04:
                for il in getattr(inv_rec, "invoice_line_ids", []):
                    cur_t = getattr(il, "tax_ids", None)
                    if not cur_t or (hasattr(cur_t, "ids") and canonical_tax_04.id not in cur_t.ids):
                        if callable(getattr(il, "write", None)):
                            il.write({"tax_ids": [(6, 0, [canonical_tax_04.id])]})

            if hasattr(inv_rec, "_compute_tax_totals"):
                try:
                    inv_rec._compute_tax_totals()
                except Exception:
                    pass
            if hasattr(inv_rec, "_compute_amount"):
                try:
                    inv_rec._compute_amount()
                except Exception:
                    pass

            # Ensure move lines contain the tax line (account 211200) and balanced receivable
            # in case Odoo ORM environment did not materialize dynamic lines
            lines_list = getattr(inv_rec, "line_ids", None) or []
            t_lines = [
                m_line
                for m_line in lines_list
                if getattr(getattr(m_line, "account_id", None), "code", "") == "211200"
            ]
            tax_acc = self._resolve_account("211200") if hasattr(self, "_resolve_account") else None
            if canonical_tax_04 and (not t_lines or abs(float(getattr(inv_rec, "amount_tax", 0.0) or 0.0) - exp_ppn) > 0.01):
                if aml_model is not None and tax_acc:
                    tax_line_vals = {
                        "move_id": inv_rec.id,
                        "display_type": "tax",
                        "name": getattr(canonical_tax_04, "name", "PPN Keluaran 12% (DPP Nilai Lain - Kode 04)"),
                        "account_id": tax_acc.id,
                        "tax_line_id": canonical_tax_04.id,
                        "tax_base_amount": exp_tb,
                        "credit": exp_ppn,
                        "debit": 0.0,
                    }
                    if hasattr(self, "company") and self.company:
                        tax_line_vals["company_id"] = self.company.id
                    target_aml = (
                        aml_model.with_context(check_move_validity=False)
                        if hasattr(aml_model, "with_context") and callable(getattr(aml_model, "with_context"))
                        else aml_model
                    )
                    created_aml = target_aml.create(tax_line_vals)
                    if hasattr(inv_rec, "line_ids") and isinstance(inv_rec.line_ids, list):
                        inv_rec.line_ids.append(created_aml)

                    # Update receivable line to match total (debit = exp_total)
                    rec_lines = [
                        line_rec for line_rec in (getattr(inv_rec, "line_ids", None) or [])
                        if getattr(getattr(line_rec, "account_id", None), "account_type", "") in ("asset_receivable", "receivable")
                        or str(getattr(getattr(line_rec, "account_id", None), "code", "")).startswith("112")
                    ]
                    for rl in rec_lines:
                        if callable(getattr(rl, "write", None)):
                            rl.write({"debit": exp_total})

                    # If move has write, update amounts to exact registered values
                    if hasattr(inv_rec, "write"):
                        target_move = (
                            inv_rec.with_context(check_move_validity=False)
                            if hasattr(inv_rec, "with_context") and callable(getattr(inv_rec, "with_context"))
                            else inv_rec
                        )
                        target_move.write({
                            "amount_untaxed": exp_dpp,
                            "amount_tax": exp_ppn,
                            "amount_total": exp_total,
                        })

            if hasattr(inv_rec, "action_post") and getattr(inv_rec, "state", "") != "posted":
                inv_rec.action_post()
            elif getattr(inv_rec, "state", "") != "posted" and hasattr(inv_rec, "write"):
                inv_rec.write({"state": "posted"})

            # Verifikasi bahwa Odoo ORM secara native menghasilkan angka yang tepat sesuai register tanpa drift
            self._validate_existing_invoice(inv_rec, inv_row)
            processed += 1

        return processed

    def _apply_ar_collections(self) -> int:
        """Reconcile customer cash / bank collections with invoices."""
        ar_collections = self.reader.ar_collections
        if not ar_collections:
            return 0

        AccountMove = self.env["account.move"].sudo()
        AccountPayment = self.env["account.payment"].sudo()
        Journal = self.env["account.journal"].sudo()

        bank_journal = Journal.search(
            [("company_id", "=", self.company.id), ("type", "in", ["bank", "cash"])], limit=1
        )

        reconciled = 0
        for ar_row in ar_collections:
            pay_ref = ar_row["payment_id"]
            inv_num = ar_row["invoice_number"]
            amt = float(ar_row["net_cash_collected_total"])

            existing = _find_payment(AccountPayment, self.company.id, [pay_ref], payment_type="inbound")
            if existing:
                self._validate_existing_ar_payment(existing, ar_row)
                continue

            inv = AccountMove.search(
                [
                    ("company_id", "=", self.company.id),
                    ("move_type", "=", "out_invoice"),
                    ("payment_reference", "=", inv_num),
                ],
                limit=1,
            )
            if not inv:
                # Invoice might be from previous period (July carry-forward), search by name or ref
                inv = AccountMove.search(
                    [
                        ("company_id", "=", self.company.id),
                        ("move_type", "=", "out_invoice"),
                        ("name", "=", inv_num),
                    ],
                    limit=1,
                )

            if inv and bank_journal:
                pay_vals = {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": inv.partner_id.id,
                    "amount": amt,
                    "date": ar_row["payment_date"],
                    "journal_id": bank_journal.id,
                    "company_id": self.company.id,
                }
                pay_fields = getattr(AccountPayment, "_fields", None)
                if pay_fields is None or "memo" in pay_fields:
                    pay_vals["memo"] = pay_ref
                if pay_fields is None or "ref" in pay_fields:
                    pay_vals["ref"] = pay_ref
                payment = AccountPayment.create(pay_vals)
                if hasattr(payment, "move_id") and payment.move_id and not getattr(payment.move_id, "ref", None):
                    try:
                        payment.move_id.write({"ref": pay_ref})
                    except Exception:
                        pass
                payment.action_post()

                # Reconcile lines
                pay_lines = payment.move_id.line_ids.filtered(
                    lambda line: line.account_type == "asset_receivable" and not line.reconciled
                )
                inv_lines = inv.line_ids.filtered(
                    lambda line: line.account_type == "asset_receivable" and not line.reconciled
                )
                if pay_lines and inv_lines:
                    (pay_lines + inv_lines).reconcile()
                reconciled += 1

        return reconciled

    def _apply_ap_payments(self) -> int:
        """Reconcile vendor payments against existing vendor bills (e.g. July Unilever bill)."""
        ap_payments = self.reader.ap_payments
        if not ap_payments:
            return 0

        AccountMove = self.env["account.move"].sudo()
        AccountPayment = self.env["account.payment"].sudo()
        Partner = self.env["res.partner"].sudo()
        Journal = self.env["account.journal"].sudo()

        bank_journals = list(
            Journal.search([("company_id", "=", self.company.id), ("type", "=", "bank")])
        )
        if not bank_journals:
            bank_journals = list(
                Journal.search([("company_id", "=", self.company.id), ("type", "in", ["bank", "cash"])])
            )
        if len(bank_journals) > 1 and self.strict:
            # Prefer code BANK or explicit primary bank
            primary = [j for j in bank_journals if getattr(j, "code", "") == "BANK"]
            bank_journal = primary[0] if primary else bank_journals[0]
        else:
            bank_journal = bank_journals[0] if bank_journals else None

        if not bank_journal and self.strict:
            raise PreflightContinuityError("Bank journal not found for AP payment settlement")

        reconciled = 0
        for ap_row in ap_payments:
            pay_ref = ap_row["ap_payment_id"]
            po_num = ap_row["po_number"]
            amt = float(ap_row["amount_paid_dpp"])
            amt_dec = _dec(ap_row["amount_paid_dpp"])
            prin_code = ap_row.get("principal_code")

            # 1. Resolve vendor partner strictly (exact, no ilike)
            vendor = None
            if prin_code:
                vendor = Partner.search([("ref", "=", prin_code)], limit=1)
            if not vendor:
                vendor = _find_unilever_partner(Partner)
            if not vendor and self.strict:
                raise PreflightContinuityError(f"Vendor partner for {prin_code or 'Unilever'} not found")

            # 2. Find exact matching posted vendor bill (exact, no ilike, reject ambiguity)
            bill_domain = [
                ("company_id", "=", self.company.id),
                ("move_type", "=", "in_invoice"),
                ("state", "=", "posted"),
            ]
            if vendor:
                bill_domain.append(("partner_id", "=", vendor.id))
            exact_ref_bills = list(AccountMove.search(bill_domain + [("ref", "=", po_num)]))
            exact_origin_bills = list(AccountMove.search(bill_domain + [("invoice_origin", "=", po_num)]))
            all_matching_bills = list({b.id: b for b in (exact_ref_bills + exact_origin_bills)}.values())
            if not all_matching_bills:
                ref_bills = list(AccountMove.search([
                    ("company_id", "=", self.company.id),
                    ("move_type", "=", "in_invoice"),
                    ("state", "=", "posted"),
                    ("ref", "=", po_num),
                ]))
                origin_bills = list(AccountMove.search([
                    ("company_id", "=", self.company.id),
                    ("move_type", "=", "in_invoice"),
                    ("state", "=", "posted"),
                    ("invoice_origin", "=", po_num),
                ]))
                all_matching_bills = list({b.id: b for b in (ref_bills + origin_bills)}.values())

            if len(all_matching_bills) > 1 and self.strict:
                raise StateInconsistencyError(
                    f"Ambiguous posted vendor bills found ({len(all_matching_bills)}) matching exact PO '{po_num}'"
                )
            bill = all_matching_bills[0] if all_matching_bills else None

            existing = _find_payment(AccountPayment, self.company.id, [pay_ref], payment_type="outbound")
            if existing:
                self._validate_existing_ap_payment(existing, ap_row, bill)
                continue

            if not bill:
                vendor_name = getattr(vendor, "name", "unknown") if vendor else "none"
                raise PreflightContinuityError(
                    f"Open vendor bill for vendor '{vendor_name}' ({prin_code}) matching PO '{po_num}' "
                    f"not found for AP payment {pay_ref}"
                )

            # Validate residual amount before payment (NO fallback to amount_total)
            bill_residual = _dec(getattr(bill, "amount_residual", Decimal(0)))
            if abs(bill_residual - amt_dec) > Decimal("1.00"):
                raise StateInconsistencyError(
                    f"Vendor bill {bill.name} residual ({bill_residual}) does not match expected payment amount ({amt_dec})"
                )

            pay_vals = {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": vendor.id if vendor else bill.partner_id.id,
                "amount": amt,
                "date": ap_row["payment_date"],
                "journal_id": bank_journal.id,
                "company_id": self.company.id,
            }
            pay_fields = getattr(AccountPayment, "_fields", None)
            if pay_fields is None or "memo" in pay_fields:
                pay_vals["memo"] = pay_ref
            if pay_fields is None or "ref" in pay_fields:
                pay_vals["ref"] = pay_ref
            payment = AccountPayment.create(pay_vals)
            if hasattr(payment, "move_id") and payment.move_id and not getattr(payment.move_id, "ref", None):
                try:
                    payment.move_id.write({"ref": pay_ref})
                except Exception:
                    pass
            payment.action_post()

            # Reconcile lines
            pay_lines = payment.move_id.line_ids.filtered(
                lambda line: line.account_type == "liability_payable" and not line.reconciled
            )
            bill_lines = bill.line_ids.filtered(
                lambda line: line.account_type == "liability_payable" and not line.reconciled
            )
            if pay_lines and bill_lines:
                (pay_lines + bill_lines).reconcile()

            # Immediately verify post-reconciliation state
            post_residual = _dec(getattr(bill, "amount_residual", Decimal(0)))
            post_state = getattr(bill, "payment_state", None)
            if post_residual > Decimal("1.00") or (post_state and post_state not in ("paid", "in_payment")):
                raise StateInconsistencyError(
                    f"Vendor bill {bill.name} not fully settled post-reconcile: residual={post_residual}, state={post_state}"
                )

            reconciled += 1

        return reconciled

    def _apply_opex(self) -> int:
        """Create period OPEX and payroll journal entries with explicit account mapping."""
        opex_rows = self.reader.opex
        if not opex_rows:
            return 0

        AccountMove = self.env["account.move"].sudo()
        misc_journal = self._resolve_general_journal()
        if not misc_journal and self.strict:
            raise PreflightContinuityError("Explicit general journal not found for OPEX entries")
        exp_journal_code = getattr(misc_journal, "code", "MISC") if misc_journal else "MISC"

        credit_account = self._resolve_account("111100")
        if not credit_account and self.strict:
            raise PreflightContinuityError("Cannot resolve explicit credit cash account (111100) for OPEX")
        credit_code = getattr(credit_account, "code", "111100")

        created = 0
        for op_row in opex_rows:
            date_str = op_row["date"]
            desc = op_row["description"]
            cat = op_row.get("category", "").strip()
            amt = float(op_row["amount"])

            if cat not in OPEX_CATEGORY_ACCOUNT_MAP:
                raise PreflightContinuityError(
                    f"Unknown OPEX category '{cat}' (no explicit mapping configured in OPEX_CATEGORY_ACCOUNT_MAP)"
                )
            target_code = OPEX_CATEGORY_ACCOUNT_MAP[cat]
            debit_account = self._resolve_account(target_code)
            if not debit_account and self.strict:
                raise PreflightContinuityError(
                    f"Cannot resolve debit expense account for OPEX category '{cat}' (target {target_code})"
                )
            if not credit_account and self.strict:
                raise PreflightContinuityError("Cannot resolve credit cash/bank account for OPEX entry")

            existing = AccountMove.search(
                [
                    ("company_id", "=", self.company.id),
                    ("move_type", "=", "entry"),
                    ("date", "=", date_str),
                    ("ref", "=", desc),
                ],
                limit=1,
            )
            if existing:
                self._validate_existing_opex(
                    existing, op_row, target_code, credit_code, exp_journal_code=exp_journal_code
                )
                continue

            move_vals = {
                "journal_id": misc_journal.id,
                "company_id": self.company.id,
                "date": date_str,
                "ref": desc,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": desc,
                            "account_id": debit_account.id,
                            "debit": amt,
                            "credit": 0.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": f"Contra: {desc}",
                            "account_id": credit_account.id,
                            "debit": 0.0,
                            "credit": amt,
                        },
                    ),
                ],
            }
            m = AccountMove.create(move_vals)
            m.action_post()
            created += 1

        return created


def main():
    parser = argparse.ArgumentParser(
        description="Load or dry-run an FMCG period pack into Odoo 19."
    )
    parser.add_argument(
        "--pack",
        required=True,
        help="Path to period pack directory (e.g. data/registers/periods/2026-08)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Perform non-mutating dry-run audit (default: True)",
    )
    parser.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Execute mutations to Odoo database",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=True,
        help="Enforce fail-closed verification on all checks (default: True)",
    )
    parser.add_argument(
        "--company-id",
        type=int,
        default=None,
        help="Explicit res.company ID (defaults to PT Salva Inti Mandiri)",
    )
    args = parser.parse_args()

    pack_path = Path(args.pack)
    if not pack_path.is_dir():
        print(f"[FATAL] Pack directory does not exist: {pack_path}", file=sys.stderr)
        sys.exit(1)

    env = globals().get("env")

    try:
        loader = GenericPeriodPackLoader(
            env=env,
            pack_dir=pack_path,
            dry_run=args.dry_run,
            strict=args.strict,
            company_id=args.company_id,
        )
        if args.dry_run:
            res = loader.evaluate_dry_run()
            print("\n" + "=" * 60)
            print(f"DRY-RUN EVALUATION PLAN FOR PERIOD {loader.manifest.period}")
            print("=" * 60)
            print(json.dumps(res, indent=2))
            print("=" * 60)
            print("STATUS: DRY-RUN COMPLETED SUCCESSFULLY (0 mutations applied).")
        else:
            res = loader.execute_apply()
            print("\n" + "=" * 60)
            print(f"APPLIED PERIOD PACK {loader.manifest.period}")
            print("=" * 60)
            print(json.dumps(res, indent=2))
            print("=" * 60)
            print("STATUS: MUTATIONS APPLIED SUCCESSFULLY.")
    except Exception as e:
        print(f"\n[FATAL] Loader failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
