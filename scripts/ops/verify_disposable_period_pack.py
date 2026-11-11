#!/usr/bin/env python3
"""Dedicated Disposable Runtime Proof for FMCG Period Pack Continuation (Fase F4).

Validates that loading a monthly period pack (e.g. data/registers/periods/2026-08)
is a mathematically and operationally correct incremental continuation of July 2026:
1. Strict Safety Guard: Rejects non-disposable and production databases.
2. Continuity & Baseline Audit: Verifies July closing immutability (13,540 AMLs).
3. Scenario A: Baseline July -> Load August -> Re-run August (Zero Drift Proof).
4. Scenario B: Empty DB -> Load July -> Load August (Deterministic from Zero).
5. Comprehensive Runtime Oracle:
   - Document counts (16 PO, 1,240 SO, 1,240 DO, 1,240 INV, 1,202 AR, 1 AP, 48 OPEX).
   - Stock Quant vs Stock-to-GL tie-out (Account 113000).
   - AR aging & open invoices vs GL Accounts Receivable (Account 112000).
   - AP settlement: July Unilever bill (Rp2,899,971,200) strictly paid.
   - Tax Code 04 DPP Nilai Lain 11/12 and PPN 12% calculation integrity.
6. Fault-Injection Probes: Partial failure in savepoint recovers cleanly without duplicates.

Executed in Odoo shell:
    odoo shell -c /tmp/odoo.conf -d <dbname> --no-http < scripts/ops/verify_disposable_period_pack.py
"""

from __future__ import annotations

import argparse
import contextlib
from decimal import Decimal
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Tuple

_logger = logging.getLogger("verify_disposable_period_pack")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

try:
    REPO_ROOT = Path(__file__).resolve().parents[2]
except NameError:
    if Path("scripts/ops/load_period_pack.py").exists():
        REPO_ROOT = Path.cwd()
    elif Path("/opt/scripts/ops/load_period_pack.py").exists():
        REPO_ROOT = Path("/opt")
    else:
        REPO_ROOT = Path(os.environ.get("REPO_ROOT", "."))

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ops.load_period_pack import (  # noqa: E402
    GenericPeriodPackLoader,
    OPEX_CATEGORY_ACCOUNT_MAP,
    PeriodPackManifest,
    PeriodPackReader,
    PreflightContinuityError,
    StateInconsistencyError,
    _dec,
)

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def assert_disposable_database_name(db_name: str) -> str:
    """Safety guard: validates database name string against forbidden keywords and allowed patterns."""
    if not db_name:
        raise RuntimeError("[SAFETY-ABORT] Database name cannot be empty.")
    forbidden = ["prod", "production", "live", "railway", "master", "official", "main"]
    for f in forbidden:
        if f in db_name.lower():
            raise RuntimeError(
                f"[SAFETY-ABORT] Target database '{db_name}' contains forbidden word '{f}'! "
                "Execution aborted to protect operational integrity."
            )

    exact_allowed = {
        "fmcg_full_disposable",
        "ci_db",
        "test_disposable",
        "fmcg_period_disposable",
        "fmcg_period_disposable_b",
        "disposable_scenario_b",
    }
    is_pattern_allowed = (
        db_name.startswith("disposable_")
        or db_name.endswith("_disposable")
        or "_disposable_" in db_name
        or "test_" in db_name
    )
    if db_name not in exact_allowed and not is_pattern_allowed:
        raise RuntimeError(
            f"[SAFETY-ABORT] Target database '{db_name}' is not an authorized disposable DB."
        )
    return db_name


def assert_disposable_database(env: Any) -> str:
    """Safety guard: rejects any operational, live, or production database, and requires env."""
    if env is None:
        raise RuntimeError(
            "[SAFETY-ABORT] Live disposable Odoo environment required (env is None). "
            "verify_disposable_period_pack.py cannot run in offline/mock mode."
        )
    cr = getattr(env, "cr", None)
    db_name = getattr(cr, "dbname", "") or ""
    return assert_disposable_database_name(db_name)


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


class PeriodPackOracle:
    """Independent oracle deriving expected database states directly from pack files."""

    def __init__(self, pack_dir: Path):
        self.pack_dir = pack_dir.resolve()
        self.manifest = PeriodPackManifest(self.pack_dir)
        self.reader = PeriodPackReader(self.pack_dir)
        self.closing_state = self.reader.read_json(f"closing_state_{self.manifest.period.replace('-', '')}31.json") or {}

        # Derived expectations
        self.expected_po_count = len(self.reader.po_headers)
        self.expected_so_count = len(self.reader.sales_orders)
        self.expected_do_count = len(self.reader.deliveries)
        self.expected_inv_count = len(self.reader.invoices)
        self.expected_ar_count = len(self.reader.ar_collections)
        self.expected_ap_count = len(self.reader.ap_payments)
        self.expected_opex_count = len(self.reader.opex)

        # Expected financial totals
        self.expected_gross_dpp = sum(_dec(r.get("gross_dpp", 0)) for r in self.reader.sales_orders)
        self.expected_discount_dpp = sum(_dec(r.get("discount_dpp", 0)) for r in self.reader.sales_orders)
        self.expected_net_dpp = sum(_dec(r.get("net_dpp", 0)) for r in self.reader.sales_orders)
        self.expected_rejection_dpp = sum(_dec(r.get("rejection_dpp", 0)) for r in self.reader.rejections)

        # Invoices totals
        self.expected_inv_dpp = sum(_dec(r.get("commercial_dpp") or r.get("dpp_amount", 0)) for r in self.reader.invoices)
        self.expected_inv_ppn = sum(_dec(r.get("ppn_amount", 0)) for r in self.reader.invoices)
        self.expected_inv_total = sum(_dec(r.get("total_invoice_with_ppn", 0)) for r in self.reader.invoices)

        # AR collections total
        self.expected_ar_collected = sum(_dec(r.get("net_cash_collected_total", 0)) for r in self.reader.ar_collections)

        # AP payments total
        self.expected_ap_paid = sum(_dec(r.get("amount_paid_dpp", 0)) for r in self.reader.ap_payments)

        # Independent PO input tax derivation from pack po_lines.csv (11% PPN Masukan)
        self.expected_po_input_tax = sum(
            (
                _dec(pline.get("qty_cartons", 0))
                * _dec(pline.get("carton_qty", 0))
                * _dec(pline.get("unit_cost_price", 0))
                * Decimal("0.11")
            ).quantize(Decimal("0.01"))
            for pline in self.reader.po_lines
        )

        # Authoritative closing stock schema from closing_state JSON (keyed by "SKU||LOT")
        self.closing_stock = self.closing_state.get("stock", {})
        self.closing_summary = self.closing_state.get("summary", {})
        if not self.closing_stock:
            raise RuntimeError(
                f"Closing state JSON for period {self.manifest.period} missing required 'stock' schema or is empty"
            )

        # Build authoritative cost and UoM conversion mapping (carton_qty & unit_cost) from registers
        self.sku_conversion_map: Dict[str, Tuple[Decimal, Decimal]] = {}
        for row in self.reader.po_lines:
            sku = row.get("sku_code")
            if sku and sku not in self.sku_conversion_map:
                c_qty = _dec(row.get("carton_qty", 1))
                u_cost = _dec(row.get("unit_cost_price", 0))
                self.sku_conversion_map[sku] = (c_qty, u_cost)
        for row in self.reader.order_lines:
            sku = row.get("sku_code")
            if sku and sku not in self.sku_conversion_map:
                c_qty = _dec(row.get("carton_qty", 1))
                u_cost = _dec(row.get("unit_cost", 0))
                self.sku_conversion_map[sku] = (c_qty, u_cost)

        self.expected_total_physical_cartons = int(self.closing_summary.get("total_physical_cartons", 0))
        self.expected_total_reserved_cartons = int(self.closing_summary.get("total_reserved_cartons", 0))
        self.expected_total_quarantine_cartons = int(self.closing_summary.get("total_quarantine_cartons", 0))

        self.expected_closing_lots: Dict[str, Dict[str, Any]] = {}
        self.expected_sku_physical_pcs: Dict[str, Decimal] = {}
        self.expected_sku_reserved_pcs: Dict[str, Decimal] = {}
        self.expected_sku_quarantine_pcs: Dict[str, Decimal] = {}
        self.expected_closing_valuation = ZERO

        for key, entry in self.closing_stock.items():
            sku = entry.get("sku_code", "")
            lot = entry.get("lot_number", "")
            phys_cartons = _dec(entry.get("physical", 0))
            res_cartons = _dec(entry.get("reserved", 0))
            quar_cartons = _dec(entry.get("quarantine", 0))

            if sku not in self.sku_conversion_map:
                raise RuntimeError(
                    f"Unknown SKU '{sku}' in closing stock has no carton_qty conversion or unit cost in register pack!"
                )
            c_qty, u_cost = self.sku_conversion_map[sku]
            phys_pcs = phys_cartons * c_qty
            res_pcs = res_cartons * c_qty
            quar_pcs = quar_cartons * c_qty
            lot_val = phys_pcs * u_cost

            self.expected_closing_lots[key] = {
                "sku_code": sku,
                "lot_number": lot,
                "physical_cartons": phys_cartons,
                "reserved_cartons": res_cartons,
                "quarantine_cartons": quar_cartons,
                "physical_pcs": phys_pcs,
                "reserved_pcs": res_pcs,
                "quarantine_pcs": quar_pcs,
                "carton_qty": c_qty,
                "unit_cost": u_cost,
                "valuation": lot_val,
            }
            self.expected_sku_physical_pcs[sku] = self.expected_sku_physical_pcs.get(sku, ZERO) + phys_pcs
            self.expected_sku_reserved_pcs[sku] = self.expected_sku_reserved_pcs.get(sku, ZERO) + res_pcs
            self.expected_sku_quarantine_pcs[sku] = self.expected_sku_quarantine_pcs.get(sku, ZERO) + quar_pcs
            self.expected_closing_valuation += lot_val


def audit_period_database(env: Any, oracle: PeriodPackOracle) -> Dict[str, Any]:
    """Execute comprehensive mathematical and accounting audit against oracle."""
    if env is None:
        raise RuntimeError(
            "[SAFETY-ABORT] Live disposable Odoo environment required for audit_period_database (env is None)."
        )

    report = {
        "status": "PASS",
        "period": oracle.manifest.period,
        "checks": {},
        "violations": [],
    }

    Company = env["res.company"].sudo()
    company = None
    if "ir.config_parameter" in env:
        try:
            param_val = env["ir.config_parameter"].sudo().get_param("fmcg.seed_company_id")
            if param_val:
                cand = Company.browse(int(param_val))
                if cand.exists():
                    company = cand
        except Exception:
            pass
    if not company and hasattr(env, "ref"):
        try:
            cand = env.ref("id_base.fmcg_seed_company", raise_if_not_found=False)
            if cand and cand.exists():
                company = cand
        except Exception:
            pass
    if not company:
        company = Company.search(
            ["|", ("name", "ilike", "PT Salva Inti Mandiri"), ("name", "ilike", "Manado")], limit=1
        ) or getattr(env, "company", None) or Company.search([], limit=1)
    if not company or not company.exists():
        raise RuntimeError("Canonical FMCG Company not found during audit")

    SaleOrder = env["sale.order"].sudo()
    AccountMove = env["account.move"].sudo()
    AccountMoveLine = env["account.move.line"].sudo()
    AccountAccount = env["account.account"].sudo()
    PurchaseOrder = env["purchase.order"].sudo()
    AccountPayment = env["account.payment"].sudo()
    StockPicking = env["stock.picking"].sudo()
    StockQuant = env["stock.quant"].sudo()

    period_str = oracle.manifest.period.replace("-", "")

    # 1. Purchase Orders Count
    po_count = PurchaseOrder.search_count(
        [("company_id", "=", company.id), ("name", "=like", f"PO-{oracle.manifest.period}-%")]
    )
    report["checks"]["po_count"] = {"expected": oracle.expected_po_count, "actual": po_count}
    if po_count != oracle.expected_po_count:
        report["violations"].append(f"PO count mismatch: expected {oracle.expected_po_count}, found {po_count}")

    # 2. Sales Orders Count & Net DPP
    so_recs = SaleOrder.search(
        [("company_id", "=", company.id), ("client_order_ref", "=like", f"SO-{period_str}-%")]
    )
    so_count = len(so_recs)
    act_net_dpp = sum(_dec(s.amount_untaxed) for s in so_recs)
    report["checks"]["so_count"] = {"expected": oracle.expected_so_count, "actual": so_count}
    report["checks"]["so_net_dpp"] = {"expected": str(oracle.expected_net_dpp), "actual": str(act_net_dpp)}
    if so_count != oracle.expected_so_count:
        report["violations"].append(f"SO count mismatch: expected {oracle.expected_so_count}, found {so_count}")
    if abs(act_net_dpp - oracle.expected_net_dpp) > Decimal("1.00"):
        report["violations"].append(f"SO Net DPP mismatch: expected {oracle.expected_net_dpp}, found {act_net_dpp}")

    # 3. Outbound Deliveries (DO Picking) Count & Status Done
    pickings = StockPicking.search(
        [
            ("company_id", "=", company.id),
            ("picking_type_id.code", "=", "outgoing"),
            ("origin", "=like", f"SO-{period_str}-%"),
            ("state", "=", "done"),
        ]
    )
    do_count = len(pickings)
    report["checks"]["delivery_orders_done"] = {"expected": oracle.expected_do_count, "actual": do_count}
    if do_count != oracle.expected_do_count:
        report["violations"].append(
            f"Delivery orders done mismatch: expected {oracle.expected_do_count}, found {do_count}"
        )

    # 4. Invoices Count, Net DPP, PPN 12% on DPP Nilai Lain 11/12, and Seed Flag
    inv_recs = AccountMove.search(
        [
            ("company_id", "=", company.id),
            ("move_type", "=", "out_invoice"),
            ("payment_reference", "=like", f"INV-{period_str}-%"),
            ("state", "=", "posted"),
        ]
    )
    inv_count = len(inv_recs)
    act_inv_dpp = sum(_dec(m.amount_untaxed) for m in inv_recs)
    act_inv_ppn = sum(_dec(m.amount_tax) for m in inv_recs)
    act_inv_total = sum(_dec(m.amount_total) for m in inv_recs)

    report["checks"]["invoice_count"] = {"expected": oracle.expected_inv_count, "actual": inv_count}
    report["checks"]["invoice_dpp"] = {"expected": str(oracle.expected_inv_dpp), "actual": str(act_inv_dpp)}
    report["checks"]["invoice_ppn"] = {"expected": str(oracle.expected_inv_ppn), "actual": str(act_inv_ppn)}
    report["checks"]["invoice_total"] = {"expected": str(oracle.expected_inv_total), "actual": str(act_inv_total)}

    if inv_count != oracle.expected_inv_count:
        report["violations"].append(f"Invoice count mismatch: expected {oracle.expected_inv_count}, found {inv_count}")
    if abs(act_inv_dpp - oracle.expected_inv_dpp) > Decimal("1.00"):
        report["violations"].append(f"Invoice DPP mismatch: expected {oracle.expected_inv_dpp}, found {act_inv_dpp}")
    if abs(act_inv_ppn - oracle.expected_inv_ppn) > Decimal("1.00"):
        report["violations"].append(f"Invoice PPN mismatch: expected {oracle.expected_inv_ppn}, found {act_inv_ppn}")
    if abs(act_inv_total - oracle.expected_inv_total) > Decimal("1.00"):
        report["violations"].append(f"Invoice Total mismatch: expected {oracle.expected_inv_total}, found {act_inv_total}")

    # Tax Account 211200 (PPN Keluaran) - Mandatory and exact
    tax_out_acc = AccountAccount.search(
        [("code", "=", "211200"), ("company_id", "in", [company.id, False])], limit=1
    )
    if not tax_out_acc:
        report["violations"].append("Mandatory GL account '211200' (PPN Keluaran) not found in database")
    else:
        # Per-invoice check for Tax Code 04 & DPP Nilai Lain calculation
        inv_tax_violations = 0
        for inv_m in inv_recs:
            inv_ref = getattr(inv_m, "payment_reference", "") or getattr(inv_m, "name", "")
            dpp_c = _dec(inv_m.amount_untaxed)
            ppn_act = _dec(inv_m.amount_tax)
            tot_act = _dec(inv_m.amount_total)

            dpp_nl = (dpp_c * Decimal(11) / Decimal(12)).quantize(Decimal("0.01"))
            ppn_exp_nl = (dpp_nl * Decimal("0.12")).quantize(Decimal("0.01"))
            ppn_exp_eff = (dpp_c * Decimal("0.11")).quantize(Decimal("0.01"))

            if abs(ppn_act - ppn_exp_eff) > Decimal("1.00") and abs(ppn_act - ppn_exp_nl) > Decimal("1.00"):
                inv_tax_violations += 1
                if inv_tax_violations <= 5:
                    report["violations"].append(
                        f"Invoice {inv_ref} Tax Code 04 calculation mismatch: commercial DPP {dpp_c}, actual PPN {ppn_act}, expected ~{ppn_exp_eff}"
                    )
            if abs(tot_act - (dpp_c + ppn_act)) > Decimal("1.00"):
                inv_tax_violations += 1
                if inv_tax_violations <= 5:
                    report["violations"].append(
                        f"Invoice {inv_ref} total mismatch: commercial DPP {dpp_c} + PPN {ppn_act} != total {tot_act}"
                    )

            t_lines = [
                m_line
                for m_line in getattr(inv_m, "line_ids", [])
                if getattr(getattr(m_line, "account_id", None), "code", "") == "211200"
            ]
            if not t_lines:
                inv_tax_violations += 1
                if inv_tax_violations <= 5:
                    report["violations"].append(
                        f"Invoice {inv_ref} missing mandatory PPN Keluaran move lines on account 211200"
                    )
            t_credit = sum(_dec(getattr(m_line, "credit", 0)) for m_line in t_lines)
            if abs(t_credit - ppn_act) > Decimal("1.00"):
                inv_tax_violations += 1
                if inv_tax_violations <= 5:
                    report["violations"].append(
                        f"Invoice {inv_ref} AML PPN Keluaran credit mismatch on 211200: expected {ppn_act}, found {t_credit}"
                    )

            # Strict Tax Code 04 verification: tax_base_amount must match DPP Nilai Lain (fail-closed on 0/missing)
            tot_tb = sum(_dec(getattr(t_line, "tax_base_amount", 0)) for t_line in t_lines)
            if dpp_c > ZERO:
                if tot_tb <= ZERO:
                    inv_tax_violations += 1
                    if inv_tax_violations <= 5:
                        report["violations"].append(
                            f"Invoice {inv_ref} TAX-SOURCE fail-open: tax_base_amount is zero or missing ({tot_tb}); expected DPP Nilai Lain {dpp_nl}"
                        )
                elif abs(tot_tb - dpp_c) <= Decimal("1.00") and abs(tot_tb - dpp_nl) > Decimal("1.00"):
                    inv_tax_violations += 1
                    if inv_tax_violations <= 5:
                        report["violations"].append(
                            f"Invoice {inv_ref} TAX-SOURCE fail-open: tax_base_amount {tot_tb} matches commercial DPP {dpp_c} instead of DPP Nilai Lain {dpp_nl}"
                        )
                elif abs(tot_tb - dpp_nl) > Decimal("2.00"):
                    inv_tax_violations += 1
                    if inv_tax_violations <= 5:
                        report["violations"].append(
                            f"Invoice {inv_ref} tax_base_amount mismatch: expected DPP Nilai Lain {dpp_nl}, found {tot_tb}"
                        )

            # Assert configured tax rate and Tax Code 04 contract on tax lines (FAIL-CLOSED)
            for t_line in t_lines:
                tax_rec = getattr(t_line, "tax_line_id", None)
                if not tax_rec:
                    inv_tax_violations += 1
                    if inv_tax_violations <= 5:
                        report["violations"].append(
                            f"Invoice {inv_ref} tax line missing configured tax record (tax_line_id is empty/None)"
                        )
                    continue

                t_rate = _dec(getattr(tax_rec, "amount", 0))
                # Strictly require configured rate 12.00% for DPP Nilai Lain; reject 0%, 11% legacy, or absent rate
                if abs(t_rate - Decimal("12.00")) > Decimal("0.01"):
                    inv_tax_violations += 1
                    if inv_tax_violations <= 5:
                        report["violations"].append(
                            f"Invoice {inv_ref} tax configuration mismatch: tax rate is {t_rate}% (strictly requires 12.00% DPP Nilai Lain configuration; legacy 11% or zero rejected)"
                        )

                # Check tax code / description semantics (STRICT: must explicitly carry Code 04 / DPP Nilai Lain identity)
                tax_name = str(getattr(tax_rec, "name", "") or "")
                tax_desc = str(getattr(tax_rec, "description", "") or "")
                tax_code_trans = str(getattr(tax_rec, "l10n_id_tax_transaction_code", "") or "")
                tax_combined = f"{tax_name} {tax_desc}".lower()

                # Strict authoritative identity requires explicit 04 / Nilai Lain semantic tag
                # (Generic 'PPN 12%' or regular same-rate tax without 04/Nilai Lain is strictly rejected)
                is_ppn_04 = (
                    tax_code_trans == "04"
                    or any(term in tax_combined for term in ("04", "nilai lain", "kode 04", "kode_04"))
                )
                if not is_ppn_04:
                    inv_tax_violations += 1
                    if inv_tax_violations <= 5:
                        report["violations"].append(
                            f"Invoice {inv_ref} wrong-code same-rate tax: tax '{tax_name}' has rate {t_rate}% "
                            f"but lacks authoritative Tax Code 04 / DPP Nilai Lain identifier (generic PPN 12% without 04 rejected)"
                        )

            # Assert invoice-level transaction code if model supports l10n_id_tax_transaction_code
            inv_code = getattr(inv_m, "l10n_id_tax_transaction_code", "") or ""
            fields_dict = getattr(inv_m, "_fields", None) or {}
            if "l10n_id_tax_transaction_code" in fields_dict and inv_code != "04":
                inv_tax_violations += 1
                if inv_tax_violations <= 5:
                    report["violations"].append(
                        f"Invoice {inv_ref} l10n_id_tax_transaction_code is '{inv_code}', expected '04'"
                    )

        if inv_tax_violations > 5:
            report["violations"].append(
                f"Total per-invoice Tax Code 04 / PPN Keluaran violations: {inv_tax_violations}"
            )

        # GL Tie-out for PPN Keluaran
        aml_tax_out = AccountMoveLine.search(
            [
                ("company_id", "=", company.id),
                ("account_id", "=", tax_out_acc.id),
                ("parent_state", "=", "posted"),
                ("date", ">=", oracle.manifest.pack_start),
                ("date", "<=", oracle.manifest.pack_end),
            ]
        )
        gl_tax_out_balance = sum(
            _dec(getattr(m_line, "credit", 0)) - _dec(getattr(m_line, "debit", 0)) for m_line in aml_tax_out
        )
        report["checks"]["gl_ppn_keluaran_211200"] = {
            "expected": str(oracle.expected_inv_ppn),
            "actual": str(gl_tax_out_balance),
        }
        if abs(gl_tax_out_balance - oracle.expected_inv_ppn) > Decimal("1.00"):
            report["violations"].append(
                f"GL PPN Keluaran (211200) balance mismatch: expected {oracle.expected_inv_ppn}, found {gl_tax_out_balance}"
            )

    # Tax Account 114100 (PPN Masukan) - Mandatory and independently derived from pack po_lines.csv
    tax_in_acc = AccountAccount.search(
        [("code", "=", "114100"), ("company_id", "in", [company.id, False])], limit=1
    )
    if not tax_in_acc:
        report["violations"].append("Mandatory GL account '114100' (PPN Masukan) not found in database")
    else:
        # Strictly scope vendor bills to August POs (persis 16 PO)
        po_bills = AccountMove.search(
            [
                ("company_id", "=", company.id),
                ("move_type", "=", "in_invoice"),
                ("state", "=", "posted"),
                "|",
                ("ref", "=like", f"PO-{oracle.manifest.period}-%"),
                ("invoice_origin", "=like", f"PO-{oracle.manifest.period}-%"),
            ]
        )
        po_bills_count = len(po_bills)
        report["checks"]["august_po_bills_count"] = {
            "expected": oracle.expected_po_count,
            "actual": po_bills_count,
        }
        if po_bills_count != oracle.expected_po_count:
            report["violations"].append(
                f"August PO vendor bills count mismatch: expected {oracle.expected_po_count}, found {po_bills_count}"
            )

        db_po_bill_tax = sum(_dec(getattr(b, "amount_tax", 0)) for b in po_bills)
        if abs(db_po_bill_tax - oracle.expected_po_input_tax) > Decimal("1.00"):
            report["violations"].append(
                f"August PO vendor bills tax ({db_po_bill_tax}) deviates from independent pack PO tax ({oracle.expected_po_input_tax})"
            )

        aml_tax_in = AccountMoveLine.search(
            [
                ("company_id", "=", company.id),
                ("account_id", "=", tax_in_acc.id),
                ("parent_state", "=", "posted"),
                ("date", ">=", oracle.manifest.pack_start),
                ("date", "<=", oracle.manifest.pack_end),
            ]
        )
        gl_tax_in_balance = sum(
            _dec(getattr(m_line, "debit", 0)) - _dec(getattr(m_line, "credit", 0)) for m_line in aml_tax_in
        )
        report["checks"]["gl_ppn_masukan_114100"] = {
            "expected_po_input_tax": str(oracle.expected_po_input_tax),
            "actual_gl_balance": str(gl_tax_in_balance),
        }
        if abs(gl_tax_in_balance - oracle.expected_po_input_tax) > Decimal("1.00"):
            report["violations"].append(
                f"GL PPN Masukan (114100) balance mismatch: expected {oracle.expected_po_input_tax} (derived from pack po_lines.csv), found {gl_tax_in_balance}"
            )

    # Effective tax rate formula check (11% effective on commercial DPP)
    if act_inv_dpp > ZERO:
        eff_tax_rate = (act_inv_ppn / act_inv_dpp).quantize(Decimal("0.01"))
        report["checks"]["effective_tax_rate"] = {"expected": "0.11", "actual": str(eff_tax_rate)}
        if eff_tax_rate != Decimal("0.11"):
            report["violations"].append(
                f"Effective tax rate mismatch: expected 0.11, found {eff_tax_rate}"
            )

    # 5. Unilever July Bill Settlement Status & Residual (Strict PO-2026-06-05)
    Partner = env["res.partner"].sudo()
    unilever_partner = Partner.search([("ref", "=", "PRIN-UNILEVER")], limit=1)
    if not unilever_partner:
        unilever_partner = Partner.search([("ref", "=", "PRIN-002")], limit=1)
    if not unilever_partner:
        unilever_partner = Partner.search([("name", "=", "PT Unilevr Indonezia Tbk")], limit=1)
    if not unilever_partner:
        unilever_partner = Partner.search([("name", "=", "PT Unilever Indonesia Tbk")], limit=1)
    if not unilever_partner:
        unilever_partner = Partner.search([("name", "=", "PT Unilever Enterprise Indonesia")], limit=1)
    if not unilever_partner:
        unilever_partner = Partner.search([("name", "=", "PT Unilever Indonesia")], limit=1)
    if not unilever_partner:
        unilever_partner = Partner.search([("name", "ilike", "%Unilever%")], limit=1)

    bill_domain = [
        ("company_id", "=", company.id),
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
            ("company_id", "=", company.id),
            ("move_type", "=", "in_invoice"),
            ("state", "=", "posted"),
            ("ref", "=", "PO-2026-06-05"),
        ]))
        origin_bills = list(AccountMove.search([
            ("company_id", "=", company.id),
            ("move_type", "=", "in_invoice"),
            ("state", "=", "posted"),
            ("invoice_origin", "=", "PO-2026-06-05"),
        ]))
        all_unilever_bills = list({b.id: b for b in (ref_bills + origin_bills)}.values())

    if len(all_unilever_bills) > 1:
        report["violations"].append(
            f"Ambiguous July Unilever vendor bills found ({len(all_unilever_bills)}) for exact PO-2026-06-05"
        )
    elif not all_unilever_bills:
        report["violations"].append("July Unilever vendor bill PO-2026-06-05 not found in database")
    else:
        unilever_bill = all_unilever_bills[0]
        res_val = _dec(getattr(unilever_bill, "amount_residual", 0))
        is_paid = (unilever_bill.payment_state in ("paid", "in_payment") and res_val <= Decimal("1.00"))
        report["checks"]["unilever_july_bill_paid"] = is_paid
        report["checks"]["unilever_july_bill_residual"] = str(res_val)
        if not is_paid:
            report["violations"].append(
                f"July Unilever bill PO-2026-06-05 is not settled: payment_state is '{unilever_bill.payment_state}', residual is {res_val}"
            )

        AccountPayment = env["account.payment"].sudo()
        matching_ap_pay = _find_payment(
            AccountPayment,
            company.id,
            ["PAY-AP-05", "AP-202608-0001"],
            payment_type="outbound",
        )
        if not matching_ap_pay:
            report["violations"].append("Reconciled AP payment (PAY-AP-05 / AP-202608-0001) for July Unilever bill not found")
        else:
            if hasattr(matching_ap_pay, "reconciled_bill_ids") and matching_ap_pay.reconciled_bill_ids:
                if unilever_bill.id not in [b.id for b in matching_ap_pay.reconciled_bill_ids]:
                    report["violations"].append(
                        f"AP payment {matching_ap_pay.ref} is not reconciled to target July Unilever bill {unilever_bill.name}"
                    )
            elif hasattr(matching_ap_pay, "is_reconciled") and not matching_ap_pay.is_reconciled:
                report["violations"].append(f"AP payment {matching_ap_pay.ref} is not reconciled")

    # 6. AR Collections Count & Collected Total
    ar_payments = AccountPayment.search(
        [
            ("company_id", "=", company.id),
            ("payment_type", "=", "inbound"),
            ("ref", "=like", "PAY-AR-%"),
            ("date", ">=", oracle.manifest.pack_start),
            ("date", "<=", oracle.manifest.pack_end),
        ]
    )
    ar_count = len(ar_payments)
    act_ar_collected = sum(_dec(p.amount) for p in ar_payments)
    report["checks"]["ar_collections_count"] = {"expected": oracle.expected_ar_count, "actual": ar_count}
    report["checks"]["ar_collected_total"] = {"expected": str(oracle.expected_ar_collected), "actual": str(act_ar_collected)}
    if ar_count != oracle.expected_ar_count:
        report["violations"].append(f"AR collections count mismatch: expected {oracle.expected_ar_count}, found {ar_count}")
    if abs(act_ar_collected - oracle.expected_ar_collected) > Decimal("1.00"):
        report["violations"].append(
            f"AR collected total mismatch: expected {oracle.expected_ar_collected}, found {act_ar_collected}"
        )

    # 7. AP Payments Count & Paid Total
    ap_payments = AccountPayment.search(
        [
            ("company_id", "=", company.id),
            ("payment_type", "=", "outbound"),
            ("ref", "=like", "PAY-AP-%"),
            ("date", ">=", oracle.manifest.pack_start),
            ("date", "<=", oracle.manifest.pack_end),
        ]
    )
    ap_count = len(ap_payments)
    act_ap_paid = sum(_dec(p.amount) for p in ap_payments)
    report["checks"]["ap_payments_count"] = {"expected": oracle.expected_ap_count, "actual": ap_count}
    report["checks"]["ap_paid_total"] = {"expected": str(oracle.expected_ap_paid), "actual": str(act_ap_paid)}
    if ap_count != oracle.expected_ap_count:
        report["violations"].append(f"AP payments count mismatch: expected {oracle.expected_ap_count}, found {ap_count}")
    if abs(act_ap_paid - oracle.expected_ap_paid) > Decimal("1.00"):
        report["violations"].append(
            f"AP paid total mismatch: expected {oracle.expected_ap_paid}, found {act_ap_paid}"
        )

    # 8. OPEX Entries Scoped by Source Reference & Account Mapping
    opex_recs = oracle.reader.opex
    opex_posted_count = 0
    opex_total_debit = ZERO
    for op_row in opex_recs:
        op_desc = op_row["description"]
        op_date = op_row["date"]
        op_cat = op_row.get("category", "").strip()
        op_amt = _dec(op_row.get("amount", 0))
        exp_code = OPEX_CATEGORY_ACCOUNT_MAP.get(op_cat, "")

        matching_entry = AccountMove.search(
            [
                ("company_id", "=", company.id),
                ("move_type", "=", "entry"),
                ("date", "=", op_date),
                ("ref", "=", op_desc),
                ("state", "=", "posted"),
            ],
            limit=1,
        )
        if not matching_entry:
            report["violations"].append(
                f"OPEX entry missing or unposted: ref='{op_desc}', date='{op_date}', amount={op_amt}"
            )
        else:
            opex_posted_count += 1
            d_lines = [line for line in getattr(matching_entry, "line_ids", []) if _dec(getattr(line, "debit", 0)) > ZERO]
            entry_debit = sum(_dec(getattr(line, "debit", 0)) for line in d_lines)
            opex_total_debit += entry_debit
            if abs(entry_debit - op_amt) > CENT:
                report["violations"].append(
                    f"OPEX debit mismatch on '{op_desc}': expected {op_amt}, found {entry_debit}"
                )
            if d_lines and exp_code:
                d_acc = getattr(getattr(d_lines[0], "account_id", None), "code", "")
                if d_acc and d_acc != exp_code:
                    report["violations"].append(
                        f"OPEX account mismatch on '{op_desc}': expected {exp_code}, found {d_acc}"
                    )

    report["checks"]["opex_entries_count"] = {
        "expected": oracle.expected_opex_count,
        "actual": opex_posted_count,
    }
    report["checks"]["opex_total_debit"] = str(opex_total_debit)

    # 9. Stock-to-GL Audit (Account 113000 vs Internal Quants Monetary Valuation)
    stock_acc = AccountAccount.search(
        [("code", "=", "113000"), ("company_id", "in", [company.id, False])], limit=1
    )
    if not stock_acc:
        report["violations"].append("Mandatory GL account '113000' (Persediaan Barang Dagang) not found in database")
    else:
        aml_stock = AccountMoveLine.search(
            [
                ("company_id", "=", company.id),
                ("account_id", "=", stock_acc.id),
                ("parent_state", "=", "posted"),
                ("date", "<=", oracle.manifest.pack_end),
            ]
        )
        gl_stock_balance = sum(_dec(getattr(line, "debit", 0)) - _dec(getattr(line, "credit", 0)) for line in aml_stock)
        quants = StockQuant.search(
            [
                ("company_id", "=", company.id),
                ("location_id.usage", "=", "internal"),
            ]
        )
        quant_valuation = sum(
            _dec(getattr(q, "quantity", 0)) * _dec(getattr(getattr(q, "product_id", None), "standard_price", 0))
            for q in quants
        )
        report["checks"]["stock_to_gl"] = {
            "account_code": stock_acc.code,
            "gl_stock_balance": str(gl_stock_balance),
            "internal_quants_valuation": str(quant_valuation),
        }
        if abs(quant_valuation - gl_stock_balance) > Decimal("100.00"):
            report["violations"].append(
                f"Stock-to-GL mismatch: internal quants valuation={quant_valuation}, GL {stock_acc.code} balance={gl_stock_balance}"
            )

        # 9b. Closing Inventory Valuation, SKU Quantities, Lot Breakdown, and Quarantine Audit
        if not oracle.expected_sku_physical_pcs:
            report["violations"].append("Closing state missing stock expectations (expected_sku_physical_pcs is empty)")
        else:
            inv_quant_violations = 0
            actual_sku_physical: Dict[str, Decimal] = {}
            actual_sku_reserved: Dict[str, Decimal] = {}
            actual_sku_quarantine: Dict[str, Decimal] = {}

            actual_lot_physical: Dict[str, Decimal] = {}
            actual_lot_reserved: Dict[str, Decimal] = {}
            actual_lot_quarantine: Dict[str, Decimal] = {}

            for q in quants:
                p_code = getattr(getattr(q, "product_id", None), "default_code", "")
                if not p_code:
                    continue
                q_qty = _dec(getattr(q, "quantity", 0))
                q_res = _dec(getattr(q, "reserved_quantity", 0))
                lot_name = getattr(getattr(q, "lot_id", None), "name", "")
                loc_name = str(getattr(getattr(q, "location_id", None), "name", "") or "").lower()
                is_quarantine = "quarantine" in loc_name or "karantina" in loc_name

                if is_quarantine:
                    actual_sku_quarantine[p_code] = actual_sku_quarantine.get(p_code, ZERO) + q_qty
                    if lot_name:
                        key = f"{p_code}||{lot_name}"
                        actual_lot_quarantine[key] = actual_lot_quarantine.get(key, ZERO) + q_qty
                else:
                    actual_sku_physical[p_code] = actual_sku_physical.get(p_code, ZERO) + q_qty
                    actual_sku_reserved[p_code] = actual_sku_reserved.get(p_code, ZERO) + q_res
                    if lot_name:
                        key = f"{p_code}||{lot_name}"
                        actual_lot_physical[key] = actual_lot_physical.get(key, ZERO) + q_qty
                        actual_lot_reserved[key] = actual_lot_reserved.get(key, ZERO) + q_res

            # Audit physical quantities across union of all SKUs
            all_sku_keys = set(oracle.expected_sku_physical_pcs.keys()) | set(actual_sku_physical.keys())
            sku_violations = 0
            for sku in sorted(all_sku_keys):
                exp_pcs = oracle.expected_sku_physical_pcs.get(sku, ZERO)
                act_pcs = actual_sku_physical.get(sku, ZERO)
                if abs(act_pcs - exp_pcs) > Decimal("0.001"):
                    inv_quant_violations += 1
                    sku_violations += 1
                    if sku_violations <= 5:
                        report["violations"].append(
                            f"Closing stock quantity mismatch for {sku}: expected {exp_pcs} pcs, found {act_pcs} pcs"
                        )

            # Audit physical, reserved, and quarantine quantities across UNION of all lots (fail-closed on missing or unexpected)
            all_lot_keys = (
                set(oracle.expected_closing_lots.keys())
                | set(actual_lot_physical.keys())
                | set(actual_lot_reserved.keys())
                | set(actual_lot_quarantine.keys())
            )
            lot_phys_violations = 0
            lot_res_violations = 0
            lot_quar_violations = 0
            for key in sorted(all_lot_keys):
                lot_exp = oracle.expected_closing_lots.get(key)
                if not lot_exp:
                    act_p = actual_lot_physical.get(key, ZERO)
                    act_r = actual_lot_reserved.get(key, ZERO)
                    act_q = actual_lot_quarantine.get(key, ZERO)
                    if act_p > ZERO or act_r > ZERO or act_q > ZERO:
                        inv_quant_violations += 1
                        if inv_quant_violations <= 10:
                            report["violations"].append(
                                f"Unexpected closing lot found in database '{key}': physical={act_p}, reserved={act_r}, quarantine={act_q}"
                            )
                    continue

                exp_lot_phys = lot_exp["physical_pcs"]
                exp_lot_res = lot_exp["reserved_pcs"]
                exp_lot_quar = lot_exp["quarantine_pcs"]

                act_lot_phys = actual_lot_physical.get(key, ZERO)
                act_lot_res = actual_lot_reserved.get(key, ZERO)
                act_lot_quar = actual_lot_quarantine.get(key, ZERO)

                if abs(act_lot_phys - exp_lot_phys) > Decimal("0.001"):
                    inv_quant_violations += 1
                    lot_phys_violations += 1
                    if lot_phys_violations <= 5:
                        report["violations"].append(
                            f"Closing lot physical mismatch on '{key}': expected {exp_lot_phys} pcs, found {act_lot_phys} pcs"
                        )
                if abs(act_lot_res - exp_lot_res) > Decimal("0.001"):
                    inv_quant_violations += 1
                    lot_res_violations += 1
                    if lot_res_violations <= 5:
                        report["violations"].append(
                            f"Closing lot reserved mismatch on '{key}': expected {exp_lot_res} pcs, found {act_lot_res} pcs"
                        )
                if abs(act_lot_quar - exp_lot_quar) > Decimal("0.001"):
                    inv_quant_violations += 1
                    lot_quar_violations += 1
                    if lot_quar_violations <= 5:
                        report["violations"].append(
                            f"Closing lot quarantine mismatch on '{key}': expected {exp_lot_quar} pcs, found {act_lot_quar} pcs"
                        )

            if inv_quant_violations > 15:
                report["violations"].append(f"Total closing stock quantity SKU/lot mismatches: {inv_quant_violations}")

            # Audit cartons conversions: Physical, Reserved, and Quarantine
            act_total_cartons = sum(
                actual_sku_physical.get(sku, ZERO) / oracle.sku_conversion_map[sku][0]
                for sku in all_sku_keys
                if sku in oracle.sku_conversion_map
            )
            act_total_reserved_cartons = sum(
                actual_sku_reserved.get(sku, ZERO) / oracle.sku_conversion_map[sku][0]
                for sku in all_sku_keys
                if sku in oracle.sku_conversion_map
            )
            act_total_quarantine_cartons = sum(
                actual_sku_quarantine.get(sku, ZERO) / oracle.sku_conversion_map[sku][0]
                for sku in all_sku_keys
                if sku in oracle.sku_conversion_map
            )

            report["checks"]["closing_total_physical_cartons"] = {
                "expected": oracle.expected_total_physical_cartons,
                "actual": int(act_total_cartons),
            }
            report["checks"]["closing_total_reserved_cartons"] = {
                "expected": oracle.expected_total_reserved_cartons,
                "actual": int(act_total_reserved_cartons),
            }
            report["checks"]["closing_total_quarantine_cartons"] = {
                "expected": oracle.expected_total_quarantine_cartons,
                "actual": int(act_total_quarantine_cartons),
            }

            if abs(act_total_cartons - Decimal(oracle.expected_total_physical_cartons)) > Decimal("0.01"):
                report["violations"].append(
                    f"Closing stock total physical cartons mismatch: expected {oracle.expected_total_physical_cartons}, found {int(act_total_cartons)}"
                )
            if abs(act_total_reserved_cartons - Decimal(oracle.expected_total_reserved_cartons)) > Decimal("0.01"):
                report["violations"].append(
                    f"Closing stock total reserved cartons mismatch: expected {oracle.expected_total_reserved_cartons}, found {int(act_total_reserved_cartons)}"
                )
            if abs(act_total_quarantine_cartons - Decimal(oracle.expected_total_quarantine_cartons)) > Decimal("0.01"):
                report["violations"].append(
                    f"Closing stock total quarantine cartons mismatch: expected {oracle.expected_total_quarantine_cartons}, found {int(act_total_quarantine_cartons)}"
                )

            # Audit total stock valuation
            report["checks"]["closing_stock_valuation"] = {
                "expected": str(oracle.expected_closing_valuation),
                "actual": str(quant_valuation),
            }
            if abs(quant_valuation - oracle.expected_closing_valuation) > Decimal("100.00"):
                report["violations"].append(
                    f"Closing stock valuation mismatch: expected {oracle.expected_closing_valuation} (from closing_state), found {quant_valuation}"
                )

    # 10. AR-to-GL Audit (Account 112000 vs Open Invoices Residual)
    ar_acc = AccountAccount.search(
        [("code", "=", "112000"), ("company_id", "in", [company.id, False])], limit=1
    )
    if not ar_acc:
        report["violations"].append("Mandatory GL account '112000' (Piutang Usaha) not found in database")
    else:
        aml_ar = AccountMoveLine.search(
            [
                ("company_id", "=", company.id),
                ("account_id", "=", ar_acc.id),
                ("parent_state", "=", "posted"),
                ("date", "<=", oracle.manifest.pack_end),
            ]
        )
        gl_ar_balance = sum(_dec(getattr(line, "debit", 0)) - _dec(getattr(line, "credit", 0)) for line in aml_ar)
        open_invoices = AccountMove.search(
            [
                ("company_id", "=", company.id),
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "in", ["not_paid", "partial"]),
                ("date", "<=", oracle.manifest.pack_end),
            ]
        )
        open_inv_residual = sum(_dec(getattr(inv, "amount_residual", 0)) for inv in open_invoices)
        report["checks"]["ar_to_gl"] = {
            "account_code": ar_acc.code,
            "gl_ar_balance": str(gl_ar_balance),
            "open_invoice_residual": str(open_inv_residual),
        }
        if abs(gl_ar_balance - open_inv_residual) > Decimal("50.00"):
            report["violations"].append(
                f"AR-to-GL mismatch: open invoice residual={open_inv_residual}, GL {ar_acc.code} balance={gl_ar_balance}"
            )

    # 11. AP-to-GL Audit (Account 211000 vs Open Bills Residual)
    ap_acc = AccountAccount.search(
        [("code", "=", "211000"), ("company_id", "in", [company.id, False])], limit=1
    )
    if not ap_acc:
        report["violations"].append("Mandatory GL account '211000' (Utang Usaha) not found in database")
    else:
        aml_ap = AccountMoveLine.search(
            [
                ("company_id", "=", company.id),
                ("account_id", "=", ap_acc.id),
                ("parent_state", "=", "posted"),
                ("date", "<=", oracle.manifest.pack_end),
            ]
        )
        gl_ap_balance = sum(_dec(getattr(line, "credit", 0)) - _dec(getattr(line, "debit", 0)) for line in aml_ap)
        open_bills = AccountMove.search(
            [
                ("company_id", "=", company.id),
                ("move_type", "=", "in_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "in", ["not_paid", "partial"]),
                ("date", "<=", oracle.manifest.pack_end),
            ]
        )
        open_bill_residual = sum(_dec(getattr(b, "amount_residual", 0)) for b in open_bills)
        report["checks"]["ap_to_gl"] = {
            "account_code": ap_acc.code,
            "gl_ap_balance": str(gl_ap_balance),
            "open_bill_residual": str(open_bill_residual),
        }
        if abs(gl_ap_balance - open_bill_residual) > Decimal("50.00"):
            report["violations"].append(
                f"AP-to-GL mismatch: open bill residual={open_bill_residual}, GL {ap_acc.code} balance={gl_ap_balance}"
            )

    if report["violations"]:
        report["status"] = "FAIL"

    return report


def capture_period_state_snapshot(env: Any) -> Dict[str, Any]:
    """Capture comprehensive deterministic SHA-256 digest of database transactional and GL state."""
    if env is None:
        return {"snapshot": "mock_snapshot_hash", "digest": "mock_digest"}

    PurchaseOrder = env["purchase.order"].sudo()
    SaleOrder = env["sale.order"].sudo()
    AccountMove = env["account.move"].sudo()
    AccountMoveLine = env["account.move.line"].sudo()
    AccountPayment = env["account.payment"].sudo()
    StockMove = env["stock.move"].sudo()
    StockMoveLine = env["stock.move.line"].sudo()
    StockQuant = env["stock.quant"].sudo()
    PartialReconcile = env["account.partial.reconcile"].sudo()

    # 1. Purchase Orders and Lines
    po_hashes = []
    for p in PurchaseOrder.search([]):
        if not getattr(p, "name", None):
            continue
        po_hashes.append(f"PO:{p.name}:{getattr(p, 'amount_total', 0)}:{getattr(p, 'state', '')}")
        for poline in getattr(p, "order_line", []):
            po_hashes.append(
                f"POL:{p.name}:{getattr(getattr(poline, 'product_id', None), 'default_code', '')}:"
                f"{getattr(poline, 'product_qty', 0)}:{getattr(poline, 'price_unit', 0)}"
            )
    po_hashes.sort()

    # 2. Sales Orders and Lines
    so_hashes = []
    for s in SaleOrder.search([]):
        if not getattr(s, "client_order_ref", None):
            continue
        so_hashes.append(
            f"SO:{s.client_order_ref}:{getattr(s, 'amount_untaxed', 0)}:{getattr(s, 'amount_total', 0)}:{getattr(s, 'state', '')}"
        )
        for soline in getattr(s, "order_line", []):
            so_hashes.append(
                f"SOL:{s.client_order_ref}:{getattr(getattr(soline, 'product_id', None), 'default_code', '')}:"
                f"{getattr(soline, 'product_uom_qty', 0)}:{getattr(soline, 'price_unit', 0)}:{getattr(soline, 'discount', 0)}"
            )
    so_hashes.sort()

    # 3. Invoices and Lines
    inv_hashes = []
    for m in AccountMove.search([]):
        ref_id = getattr(m, "payment_reference", "") or getattr(m, "ref", "") or getattr(m, "name", "")
        if not ref_id:
            continue
        inv_hashes.append(
            f"INV:{getattr(m, 'move_type', '')}:{ref_id}:{getattr(m, 'amount_untaxed', 0)}:"
            f"{getattr(m, 'amount_total', 0)}:{getattr(m, 'amount_residual', 0)}:"
            f"{getattr(m, 'payment_state', '')}:{getattr(m, 'state', '')}"
        )
        for invline in getattr(m, "invoice_line_ids", []):
            inv_hashes.append(
                f"INVL:{ref_id}:{getattr(getattr(invline, 'product_id', None), 'default_code', '')}:"
                f"{getattr(invline, 'quantity', 0)}:{getattr(invline, 'price_unit', 0)}:{getattr(invline, 'price_subtotal', 0)}"
            )
    inv_hashes.sort()

    # 4. Payments
    pay_hashes = []
    for p in AccountPayment.search([]):
        if not getattr(p, "ref", None):
            continue
        p_ref = p.ref
        p_partner = getattr(getattr(p, "partner_id", None), "ref", "") or getattr(getattr(p, "partner_id", None), "name", "")
        p_journal = getattr(getattr(p, "journal_id", None), "code", "")
        p_date = getattr(p, "date", "")
        p_amt = getattr(p, "amount", 0)
        p_type = getattr(p, "payment_type", "")
        p_state = getattr(p, "state", "")
        pay_hashes.append(f"PAY:{p_ref}:{p_partner}:{p_journal}:{p_date}:{p_amt}:{p_type}:{p_state}")
    pay_hashes.sort()

    # 5. Stock Moves & Stock Move Lines (Lot Allocation)
    stock_hashes = sorted([
        f"SM:{m.reference}:{getattr(getattr(m, 'product_id', None), 'default_code', '')}:{getattr(m, 'product_qty', 0)}:{getattr(m, 'state', '')}"
        for m in StockMove.search([]) if getattr(m, "reference", None)
    ])
    sml_hashes = sorted([
        f"SML:{getattr(sml, 'reference', '') or getattr(getattr(sml, 'move_id', None), 'reference', '')}:"
        f"{getattr(getattr(sml, 'product_id', None), 'default_code', '')}:"
        f"{getattr(getattr(sml, 'lot_id', None), 'name', '')}:{getattr(sml, 'quantity', 0)}:"
        f"{getattr(getattr(sml, 'location_id', None), 'complete_name', '')}:"
        f"{getattr(getattr(sml, 'location_dest_id', None), 'complete_name', '')}"
        for sml in StockMoveLine.search([])
    ])

    # 6. Quants
    quant_hashes = sorted([
        f"SQ:{getattr(getattr(q, 'product_id', None), 'default_code', '')}:{getattr(getattr(q, 'location_id', None), 'complete_name', '')}:{getattr(q, 'quantity', 0)}"
        for q in StockQuant.search([("location_id.usage", "=", "internal")])
    ])

    # 7. Account Move Lines
    aml_hashes = []
    for mline in AccountMoveLine.search([]):
        m_name = getattr(getattr(mline, "move_id", None), "name", "")
        m_ref = getattr(getattr(mline, "move_id", None), "ref", "")
        a_code = getattr(getattr(mline, "account_id", None), "code", "")
        p_ref = getattr(getattr(mline, "partner_id", None), "ref", "") or getattr(getattr(mline, "partner_id", None), "name", "")
        m_date = getattr(mline, "date", "")
        deb = getattr(mline, "debit", 0)
        crd = getattr(mline, "credit", 0)
        rec = getattr(mline, "reconciled", False)
        p_state = getattr(mline, "parent_state", "")
        aml_hashes.append(f"AML:{m_name}:{m_ref}:{p_ref}:{m_date}:{a_code}:{deb}:{crd}:{rec}:{p_state}")
    aml_hashes.sort()

    # 8. Reconciliation Edges
    reconcile_hashes = []
    for pr in PartialReconcile.search([]):
        deb_line = getattr(pr, "debit_move_id", None)
        crd_line = getattr(pr, "credit_move_id", None)
        deb_doc = getattr(getattr(deb_line, "move_id", None), "name", "") or getattr(getattr(deb_line, "move_id", None), "ref", "")
        deb_acc = getattr(getattr(deb_line, "account_id", None), "code", "")
        crd_doc = getattr(getattr(crd_line, "move_id", None), "name", "") or getattr(getattr(crd_line, "move_id", None), "ref", "")
        crd_acc = getattr(getattr(crd_line, "account_id", None), "code", "")
        amt = getattr(pr, "amount", 0)
        reconcile_hashes.append(f"REC:{deb_doc}:{deb_acc}:{crd_doc}:{crd_acc}:{amt}")
    reconcile_hashes.sort()

    all_components = (
        po_hashes
        + so_hashes
        + inv_hashes
        + pay_hashes
        + stock_hashes
        + sml_hashes
        + quant_hashes
        + aml_hashes
        + reconcile_hashes
    )
    raw = "\n".join(all_components).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()

    return {
        "po_count": len(po_hashes),
        "so_count": len(so_hashes),
        "invoice_count": len(inv_hashes),
        "payment_count": len(pay_hashes),
        "stock_move_count": len(stock_hashes),
        "stock_move_line_count": len(sml_hashes),
        "quant_count": len(quant_hashes),
        "aml_count": len(aml_hashes),
        "partial_reconcile_count": len(reconcile_hashes),
        "digest": digest,
    }


def run_period_pack_fault_injection_probes(env: Any, pack_dir: Path) -> Dict[str, Any]:
    """Execute in-database savepoint probes simulating partial transactional failures.

    Verifies that:
    1. A failure in the middle of a batch triggers a clean savepoint rollback.
    2. Re-running the loader after failure resumes cleanly and achieves exact target state.
    3. No orphan records or duplicates are produced.
    """
    if env is None:
        raise RuntimeError(
            "[SAFETY-ABORT] Live disposable Odoo environment required for fault-injection probes (env is None)."
        )

    _logger.info("--- Running Fault-Injection Recovery Probes ---")
    results = {"status": "PASS", "probes": {}}
    cr = env.cr

    has_sp = cr and hasattr(cr, "savepoint") and callable(getattr(cr, "savepoint"))

    class _ProbeRollbackSignal(Exception):
        """Internal signal to cleanly roll back savepoint after fault injection validation."""
        def __init__(self, data=None):
            self.data = data

    @contextlib.contextmanager
    def _db_savepoint():
        if has_sp:
            with cr.savepoint():
                yield
        else:
            cr.execute("SAVEPOINT probe_sp")
            try:
                yield
                cr.execute("RELEASE SAVEPOINT probe_sp")
            except Exception:
                cr.execute("ROLLBACK TO SAVEPOINT probe_sp")
                raise

    snap_before = capture_period_state_snapshot(env)

    # Probe 1: Real Batch SO Mutation with Injected Corrupted SKU -> Rollback -> Clean Recovery
    loader_probe = None
    try:
        loader_probe = GenericPeriodPackLoader(env=env, pack_dir=pack_dir, dry_run=False, strict=True)
        loader_probe.verify_preflight()
        SaleOrder = env["sale.order"].with_context(fmcg_seed_load=True).sudo()

        # Derive valid customer and valid SKU directly from pack fixtures to guarantee validity
        valid_cust = (
            loader_probe.reader.sales_orders[0].get("customer", "CUST-RTL-006")
            if loader_probe.reader.sales_orders
            else "CUST-RTL-006"
        )
        valid_sku = (
            loader_probe.reader.order_lines[0].get("sku_code", "MYR-CND-02")
            if loader_probe.reader.order_lines
            else "MYR-CND-02"
        )
        corrupt_sku = "SKU-NONEXISTENT-FAULT-INJECTION"

        valid_so_num = "SO-202608-PROBE-VALID-01"
        corrupt_so_num = "SO-202608-PROBE-CORRUPT-02"

        # Record 1 (valid) will be written first in batch; Record 2 (corrupt) will trigger exception
        probe_sos = [
            {
                "so_number": valid_so_num,
                "customer": valid_cust,
                "date_order": "2026-08-15",
                "gross_dpp": "50000.00",
                "discount_dpp": "0.00",
                "net_dpp": "50000.00",
            },
            {
                "so_number": corrupt_so_num,
                "customer": valid_cust,
                "date_order": "2026-08-15",
                "gross_dpp": "100000.00",
                "discount_dpp": "0.00",
                "net_dpp": "100000.00",
            },
        ]
        probe_lines = [
            {
                "so_number": valid_so_num,
                "sku_code": valid_sku,
                "qty_cartons": "1",
                "carton_qty": "10",
                "unit_price_dpp": "5000.00",
                "discount_pct": "0.0",
            },
            {
                "so_number": corrupt_so_num,
                "sku_code": corrupt_sku,
                "qty_cartons": "1",
                "carton_qty": "1",
                "unit_price_dpp": "100000.00",
                "discount_pct": "0.0",
            },
        ]
        loader_probe.reader.set_override("sales_orders.csv", probe_sos)
        loader_probe.reader.set_override("order_lines.csv", probe_lines)

        real_write_proven = False
        exception_caught = None

        try:
            with _db_savepoint():
                try:
                    loader_probe._apply_sales_orders_and_deliveries()
                    results["probes"]["probe_batch_interruption"] = {
                        "outcome": "FAIL",
                        "detail": "FAILED_UNRESOLVED_SKU_NOT_REJECTED",
                        "digest_matched": False,
                    }
                except StateInconsistencyError as e:
                    pre_written = SaleOrder.search([("client_order_ref", "=", valid_so_num)], limit=1)
                    real_write_proven = bool(pre_written and pre_written.id)
                    exception_caught = e
                    raise _ProbeRollbackSignal(e)
        except _ProbeRollbackSignal:
            pass

        if hasattr(env, "invalidate_all") and callable(env.invalidate_all):
            env.invalidate_all()

        post_rollback_so = SaleOrder.search([("client_order_ref", "=", valid_so_num)], limit=1)
        rollback_clean = (post_rollback_so is None or not post_rollback_so.exists())

        snap_after = capture_period_state_snapshot(env)
        digest_matched = (snap_before["digest"] == snap_after["digest"])

        if exception_caught and "Unresolved SKU" in str(exception_caught) and real_write_proven and rollback_clean and digest_matched:
            loader_probe.reader.clear_overrides()
            results["probes"]["probe_batch_interruption"] = {
                "outcome": "PASS",
                "detail": (
                    f"Real batch write proven before fault (SO {valid_so_num} created in Odoo DB), "
                    f"rolled back cleanly without dirty state (digest verified), "
                    f"and reader overrides cleared for recovery"
                ),
                "digest_matched": True,
            }
        elif not real_write_proven:
            results["probes"]["probe_batch_interruption"] = {
                "outcome": "FAIL",
                "detail": "FAILED_NO_REAL_WRITE_BEFORE_INJECTED_ERROR",
                "digest_matched": digest_matched,
            }
        elif not rollback_clean or not digest_matched:
            results["probes"]["probe_batch_interruption"] = {
                "outcome": "FAIL",
                "detail": "FAILED_STATE_DIRTY_AFTER_ROLLBACK",
                "digest_matched": False,
            }
        else:
            results["probes"]["probe_batch_interruption"] = {
                "outcome": "FAIL",
                "detail": f"FAILED_WRONG_MESSAGE: {exception_caught}",
                "digest_matched": digest_matched,
            }
    except Exception as e:
        results["probes"]["probe_batch_interruption"] = {
            "outcome": "FAIL",
            "detail": f"FAILED_SETUP_ERROR: {e}",
            "digest_matched": False,
        }
    finally:
        if loader_probe and hasattr(loader_probe, "reader"):
            loader_probe.reader.clear_overrides()
        if hasattr(env, "invalidate_all") and callable(env.invalidate_all):
            env.invalidate_all()

    # Probe 2: Mismatched AP Payment Target & Residual Tampering -> Rollback -> Real AP Recovery
    try:
        loader_ap = GenericPeriodPackLoader(env=env, pack_dir=pack_dir, dry_run=False, strict=True)
        loader_ap.verify_preflight()
        company = loader_ap.company
        AccountMove = env["account.move"].sudo()
        bill = AccountMove.search(
            [
                ("company_id", "=", company.id if company else 1),
                ("move_type", "=", "in_invoice"),
                ("state", "=", "posted"),
                "|",
                ("ref", "=", "PO-2026-06-05"),
                ("invoice_origin", "=", "PO-2026-06-05"),
            ],
            limit=1,
        )
        if bill:
            exception_caught2 = None
            try:
                with _db_savepoint():
                    cr.execute("UPDATE account_move SET amount_residual = 500.00 WHERE id = %s", [bill.id])
                    if hasattr(env, "invalidate_all") and callable(env.invalidate_all):
                        env.invalidate_all()
                    try:
                        loader_ap._apply_ap_payments()
                        results["probes"]["probe_ap_bill_mismatch"] = {
                            "outcome": "FAIL",
                            "detail": "FAILED_ACCEPTED_TAMPERED",
                            "digest_matched": False,
                        }
                    except (PreflightContinuityError, StateInconsistencyError) as e:
                        exception_caught2 = e
                        raise _ProbeRollbackSignal(e)
            except _ProbeRollbackSignal:
                pass

            if hasattr(env, "invalidate_all") and callable(env.invalidate_all):
                env.invalidate_all()

            snap_after2 = capture_period_state_snapshot(env)
            digest_matched2 = (snap_before["digest"] == snap_after2["digest"])
            err_msg = str(exception_caught2).lower() if exception_caught2 else ""
            is_expected_error = (
                "residual" in err_msg
                or "not match" in err_msg
                or "not found" in err_msg
                or "mismatch" in err_msg
            )
            if is_expected_error and digest_matched2:
                results["probes"]["probe_ap_bill_mismatch"] = {
                    "outcome": "PASS",
                    "detail": (
                        f"Tampered residual rejected cleanly ({exception_caught2}), rollback zero drift verified, "
                        f"and baseline residual fully restored"
                    ),
                    "digest_matched": True,
                }
            elif not digest_matched2:
                results["probes"]["probe_ap_bill_mismatch"] = {
                    "outcome": "FAIL",
                    "detail": "FAILED_STATE_DIRTY_AFTER_ROLLBACK",
                    "digest_matched": False,
                }
            else:
                results["probes"]["probe_ap_bill_mismatch"] = {
                    "outcome": "FAIL",
                    "detail": f"FAILED_NON_SPECIFIC_ERROR: {exception_caught2}",
                    "digest_matched": digest_matched2,
                }
        else:
            results["probes"]["probe_ap_bill_mismatch"] = {
                "outcome": "FAIL",
                "detail": "FAILED_NO_UNILEVER_BILL_FOUND",
                "digest_matched": False,
            }
    except Exception as e:
        results["probes"]["probe_ap_bill_mismatch"] = {
            "outcome": "FAIL",
            "detail": f"FAILED_SETUP_ERROR: {e}",
            "digest_matched": False,
        }
    finally:
        if hasattr(env, "invalidate_all") and callable(env.invalidate_all):
            env.invalidate_all()

    all_probes_passed = True
    for p_name, p_res in results["probes"].items():
        if isinstance(p_res, dict):
            if p_res.get("outcome") != "PASS" or not p_res.get("digest_matched", False):
                all_probes_passed = False
        else:
            if not str(p_res).startswith("PASS") or "_BUT_DIRTY_STATE" in str(p_res):
                all_probes_passed = False

    # Execute Real Loader Apply Recovery to Target State across all documents (including SOs and AP settlement)
    if all_probes_passed:
        _logger.info("--- Executing Real Loader Apply Recovery To Target State ---")
        try:
            if "res.currency" in env:
                idr = env["res.currency"].sudo().search([("name", "=", "IDR")], limit=1)
                if idr and not idr.active:
                    idr.write({"active": True})
            loader_recovery = GenericPeriodPackLoader(env=env, pack_dir=pack_dir, dry_run=False, strict=True)
            rec_summary = loader_recovery.execute_apply()
            results["recovery_summary"] = rec_summary
            results["recovery_status"] = "PASS"
        except Exception as rec_err:
            results["recovery_summary"] = None
            results["recovery_status"] = f"FAIL: {rec_err}"
            all_probes_passed = False

    results["status"] = "PASS" if all_probes_passed else "FAIL"

    _logger.info(f"Fault-Injection Probes Results: {json.dumps(results, indent=2)}")
    return results


def run_scenario_b_from_empty_database(
    env: Any, pack_dir: Path, expected_digest: Optional[str] = None
) -> Dict[str, Any]:
    """Execute Scenario B: Prove deterministic initialization from empty DB -> July -> August."""
    assert_disposable_database(env)
    _logger.info("=== Executing Scenario B: Empty DB -> July -> August ===")
    if "res.currency" in env:
        idr = env["res.currency"].sudo().search([("name", "=", "IDR")], limit=1)
        if idr and not idr.active:
            idr.write({"active": True})
    res = {
        "scenario": "B",
        "july_status": "PENDING",
        "august_status": "PENDING",
        "status": "PENDING",
        "snapshot_digest": None,
    }

    SaleOrder = env["sale.order"].sudo()
    AccountMove = env["account.move"].sudo()

    so_count = SaleOrder.search_count([])
    move_count = AccountMove.search_count([])

    if so_count > 0 or move_count > 0:
        raise PreflightContinuityError(
            f"Scenario B strictly requires an empty disposable database! "
            f"Found {so_count} existing sales orders and {move_count} existing account moves."
        )

    _logger.info("Database confirmed 100% empty. Bootstrapping canonical July baseline...")
    try:
        from scripts.load_canonical_perpetual import CanonicalPerpetualAdapter
        adapter = CanonicalPerpetualAdapter(env)
        adapter.run_all()
        res["july_status"] = "LOADED_SUCCESSFULLY"
    except Exception as e:
        res["july_status"] = f"FAILED: {e}"
        res["status"] = "FAIL"
        raise RuntimeError(f"Scenario B failed during July loading: {e}") from e

    # Load August incrementally in Scenario B
    _logger.info("Loading August period pack incrementally in Scenario B...")
    loader = GenericPeriodPackLoader(env=env, pack_dir=pack_dir, dry_run=False, strict=True)
    loader.execute_apply()
    res["august_status"] = "LOADED_SUCCESSFULLY"

    # Capture snapshot and audit August
    oracle = PeriodPackOracle(pack_dir)
    audit = audit_period_database(env, oracle)
    res["audit"] = audit
    snap_b = capture_period_state_snapshot(env)
    res["snapshot_digest"] = snap_b.get("digest")

    if expected_digest:
        if snap_b.get("digest") == expected_digest:
            res["digest_comparison"] = "MATCH"
        else:
            res["digest_comparison"] = f"MISMATCH: expected {expected_digest}, got {snap_b.get('digest')}"
            audit["violations"].append(f"Scenario B digest mismatch against expected: {res['digest_comparison']}")

    if (
        audit.get("status") == "PASS"
        and not audit.get("violations")
        and (not expected_digest or res.get("digest_comparison") == "MATCH")
    ):
        res["status"] = "PASS"
    else:
        res["status"] = "FAIL"
        res["audit_violations"] = audit.get("violations", [])

    return res


def run_full_disposable_period_verification(
    env: Any,
    pack_dir: Path,
    scenario: str = "all",
    expected_digest: Optional[str] = None,
    env_b: Optional[Any] = None,
) -> Dict[str, Any]:
    """Execute complete Scenario A, Scenario B, Oracle audit, and Fault-Injection verification."""
    assert_disposable_database(env)

    oracle = PeriodPackOracle(pack_dir)
    report = {
        "period": oracle.manifest.period,
        "oracle_summary": {
            "expected_po": oracle.expected_po_count,
            "expected_so": oracle.expected_so_count,
            "expected_do": oracle.expected_do_count,
            "expected_invoices": oracle.expected_inv_count,
            "expected_ar": oracle.expected_ar_count,
            "expected_ap": oracle.expected_ap_count,
            "expected_opex": oracle.expected_opex_count,
        },
        "scenario_a_zero_drift": "NOT_RUN",
        "scenario_b_continuation": {"status": "NOT_RUN"},
        "fault_injection": {"status": "NOT_RUN"},
        "audit": {"status": "NOT_RUN"},
    }

    # 1. Fault-Injection Recovery Probes on Baseline July (Batch write, tamper, rollback, real apply recovery)
    if scenario in ("all", "A"):
        _logger.info("Executing Fault-Injection Recovery Probes on Baseline July...")
        if "res.currency" in env:
            idr = env["res.currency"].sudo().search([("name", "=", "IDR")], limit=1)
            if idr and not idr.active:
                idr.write({"active": True})
        report["fault_injection"] = run_period_pack_fault_injection_probes(env, pack_dir)
        snap1 = capture_period_state_snapshot(env)
        report["scenario_a_digest"] = snap1["digest"]

        _logger.info("Executing Scenario A: Re-running period pack for zero-drift replay proof...")
        loader_rerun = GenericPeriodPackLoader(env=env, pack_dir=pack_dir, dry_run=False, strict=True)
        loader_rerun.execute_apply()
        snap2 = capture_period_state_snapshot(env)

        if snap1["digest"] == snap2["digest"]:
            report["scenario_a_zero_drift"] = "PASS"
        else:
            report["scenario_a_zero_drift"] = "FAIL_DRIFT_DETECTED"

    # 2. Run Scenario B (Empty DB -> July -> August)
    if scenario in ("all", "B"):
        target_env = env_b if scenario == "all" else (env_b or env)
        if scenario == "all" and env_b is None:
            report["scenario_b_continuation"] = {
                "status": "FAIL_SEPARATE_DB_REQUIRED",
                "error": "Scenario B strictly requires an independent empty disposable database connection (--db-b) when scenario=all",
            }
        else:
            assert_disposable_database(target_env)
            if env_b and getattr(getattr(env, "cr", None), "dbname", None) == getattr(getattr(target_env, "cr", None), "dbname", None):
                raise RuntimeError(
                    f"Scenario B target database '{getattr(target_env.cr, 'dbname', '')}' must be distinct from Scenario A database"
                )
            exp_dig = expected_digest or report.get("scenario_a_digest")
            report["scenario_b_continuation"] = run_scenario_b_from_empty_database(
                target_env, pack_dir, expected_digest=exp_dig
            )

    # 3. Comprehensive Oracle Audit
    if scenario in ("all", "A"):
        report["audit"] = audit_period_database(env, oracle)

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Verify FMCG period pack runtime execution on disposable database."
    )
    parser.add_argument(
        "--pack",
        default=os.environ.get("PERIOD_PACK_DIR", "data/registers/periods/2026-08"),
        help="Path to period pack directory (default: data/registers/periods/2026-08)",
    )
    parser.add_argument(
        "--scenario",
        choices=["all", "A", "B"],
        default=os.environ.get("PERIOD_SCENARIO", "all"),
        help="Execution scenario to prove: A (continuation & replay), B (empty to August), or all",
    )
    parser.add_argument(
        "--db-b",
        default=os.environ.get("PERIOD_DB_B", None),
        help="Separate disposable database name for Scenario B empty-database verification",
    )
    parser.add_argument(
        "--expected-digest",
        default=os.environ.get("PERIOD_EXPECTED_DIGEST", None),
        help="Expected snapshot SHA-256 digest to verify cross-scenario equivalence",
    )
    parser.add_argument(
        "--out",
        default=os.environ.get("PERIOD_OUT", "period_pack_runtime_report.json"),
        help="Path to save verification JSON report",
    )
    raw_args = sys.argv[1:]
    if "--" in raw_args:
        args = parser.parse_args(raw_args[raw_args.index("--") + 1:])
    else:
        args, _ = parser.parse_known_args(raw_args)

    pack_path = Path(args.pack)
    env = globals().get("env")

    env_b = None
    if args.db_b:
        assert_disposable_database_name(args.db_b)
        try:
            import odoo
            from odoo.modules.registry import Registry

            if hasattr(odoo, "registry") and callable(getattr(odoo, "registry")):
                registry_b = odoo.registry(args.db_b)
            else:
                registry_b = Registry(args.db_b)
            cr_b = registry_b.cursor()
            env_b = odoo.api.Environment(cr_b, odoo.SUPERUSER_ID, {})
        except Exception as e:
            print(f"[FATAL] Failed to initialize connection to --db-b '{args.db_b}': {e}", file=sys.stderr)
            sys.exit(1)

    try:
        report = run_full_disposable_period_verification(
            env=env,
            pack_dir=pack_path,
            scenario=args.scenario,
            expected_digest=args.expected_digest,
            env_b=env_b,
        )
        print("\n" + "=" * 60)
        print(f"DISPOSABLE RUNTIME PROOF FOR PERIOD {report['period']}")
        print("=" * 60)
        print(json.dumps(report, indent=2))
        print("=" * 60)

        out_path = Path(args.out)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report saved to {out_path.resolve()}")

        # Mandatory non-zero exit on any scenario, probe, or audit failure
        sc_a_pass = report.get("scenario_a_zero_drift") in ("PASS", "NOT_RUN")
        sc_b_status = report.get("scenario_b_continuation", {}).get("status")
        sc_b_pass = sc_b_status in ("PASS", "NOT_RUN")
        fi_status = report.get("fault_injection", {}).get("status")
        fi_pass = fi_status in ("PASS", "NOT_RUN")
        audit_pass = report.get("audit", {}).get("status") == "PASS" and not bool(report.get("audit", {}).get("violations"))

        if not (sc_a_pass and sc_b_pass and fi_pass and audit_pass):
            print("[FATAL] Runtime verification checks failed!", file=sys.stderr)
            sys.exit(2)
        print("STATUS: RUNTIME VERIFICATION COMPLETED SUCCESSFULLY.")
    except Exception as e:
        print(f"[FATAL] Runtime verification failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if env_b and getattr(env_b, "cr", None):
            try:
                env_b.cr.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
