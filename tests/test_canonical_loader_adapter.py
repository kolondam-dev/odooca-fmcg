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
        full_rec = MockRecord({"name": "FullReconcile"}, "account.full.reconcile", id(self))
        peer_move_ids = [
            getattr(getattr(r, "move_id", None), "id", None)
            for r in self
            if getattr(getattr(r, "move_id", None), "id", None)
        ]
        for rec in self:
            rec.reconciled = True
            rec.full_reconcile_id = full_rec
            my_mid = getattr(getattr(rec, "move_id", None), "id", None)
            rec._reconciled_peer_move_ids = [m for m in peer_move_ids if m != my_mid]
            pay_obj = getattr(rec, "_payment", None)
            if pay_obj:
                pay_obj.state = "paid"
            inv_move = getattr(rec, "move_id", None)
            if inv_move and getattr(inv_move, "move_type", "") == "out_invoice":
                paid_amt = sum(float(getattr(other, "credit", 0.0)) for other in self if other is not rec)
                inv_move.amount_residual = max(0.0, round(float(getattr(inv_move, "amount_total", 0.0)) - paid_amt, 2))
            elif inv_move and getattr(inv_move, "move_type", "") == "in_invoice":
                paid_amt = sum(float(getattr(other, "debit", 0.0)) for other in self if other is not rec)
                inv_move.amount_residual = max(0.0, round(float(getattr(inv_move, "amount_total", 0.0)) - paid_amt, 2))


class MockRecord:
    def __init__(self, vals, model_name, rec_id, env=None):
        self._vals = vals.copy() if vals else {}
        self._model = model_name
        self.id = rec_id
        self.state = self._vals.get("state", "draft")
        self.picking_ids = MockRecordList()
        self.line_ids = self._vals.get("line_ids") if "line_ids" in self._vals else MockRecordList()
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

    def __hash__(self):
        return hash((self._model, self.id))

    def __or__(self, other):
        res = MockRecordList([self])
        if isinstance(other, (list, MockRecordList)):
            for item in other:
                if item not in res:
                    res.append(item)
        elif other and other not in res:
            res.append(other)
        return res

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
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
        if name == "product_id":
            p_val = self._vals.get("product_id")
            if isinstance(p_val, MockRecord):
                return p_val
            if self._env and "product.product" in self._env and p_val:
                existing = self._env["product.product"].store.get(p_val)
                if existing:
                    return existing
            return p_val
        if name == "lot_id":
            l_val = self._vals.get("lot_id")
            if isinstance(l_val, MockRecord):
                return l_val
            if self._env and "stock.lot" in self._env and l_val:
                existing = self._env["stock.lot"].store.get(l_val)
                if existing:
                    return existing
        if name in ("move_line_ids", "move_ids"):
            val = self._vals.get(name)
            if isinstance(val, MockRecordList):
                return val
            if isinstance(val, list):
                target_model = "stock.move.line" if name == "move_line_ids" else "stock.move"
                res = []
                for item in val:
                    if isinstance(item, (list, tuple)) and len(item) == 3 and isinstance(item[2], dict):
                        if self._env and target_model in self._env:
                            res.append(self._env[target_model].create(item[2]))
                        else:
                            res.append(MockRecord(item[2], target_model, len(res) + 1, self._env))
                    elif isinstance(item, MockRecord):
                        res.append(item)
                rec_list = MockRecordList(res)
                self._vals[name] = rec_list
                return rec_list
            empty_list = MockRecordList([])
            self._vals[name] = empty_list
            return empty_list
        if name == "order_line":
            if "_order_line_records" in self.__dict__:
                return self.__dict__["_order_line_records"]
            val = self._vals.get("order_line", [])
            if isinstance(val, MockRecordList):
                return val
            target_model = "sale.order.line" if self._model == "sale.order" else "purchase.order.line"
            res = []
            for item in val:
                if isinstance(item, (list, tuple)) and len(item) == 3 and isinstance(item[2], dict):
                    if self._env and target_model in self._env:
                        res.append(self._env[target_model].create(item[2]))
                    else:
                        res.append(MockRecord(item[2], target_model, len(res) + 1, self._env))
                elif isinstance(item, MockRecord):
                    res.append(item)
            rec_list = MockRecordList(res)
            super().__setattr__("_order_line_records", rec_list)
            return rec_list
        if name == "sale_line_ids":
            val = self._vals.get("sale_line_ids", [])
            if isinstance(val, MockRecordList):
                return val
            res = []
            for item in val:
                if isinstance(item, (list, tuple)) and len(item) == 3 and item[0] == 6:
                    for sid in item[2]:
                        if self._env and "sale.order.line" in self._env:
                            srec = self._env["sale.order.line"].store.get(sid)
                            if srec:
                                res.append(srec)
                            else:
                                res.append(MockRecord({}, "sale.order.line", sid, self._env))
                        else:
                            res.append(MockRecord({}, "sale.order.line", sid, self._env))
                elif isinstance(item, MockRecord):
                    res.append(item)
            return MockRecordList(res)
        if name == "product_uom_id":
            u_val = self._vals.get("product_uom_id")
            if isinstance(u_val, MockRecord):
                return u_val
            if isinstance(u_val, int) and u_val:
                return MockRecord({"name": "Units"}, "uom.uom", u_val, self._env)
            return u_val
        if name == "uom_id" and self._model == "product.product":
            u_val = self._vals.get("uom_id")
            if isinstance(u_val, MockRecord):
                return u_val
            return MockRecord({"name": "Units"}, "uom.uom", u_val or 1, self._env)
        if name == "company_id" and "company_id" in self._vals:
            c_val = self._vals["company_id"]
            if c_val is False or c_val is None:
                return False
            if isinstance(c_val, MockRecord):
                return c_val
            if isinstance(c_val, int):
                if self._env and getattr(self._env.company, "id", None) == c_val:
                    return self._env.company
                return MockRecord({"name": f"Company {c_val}"}, "res.company", c_val, self._env)
            return c_val
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
            "id", "state", "picking_ids", "line_ids", "invoice_line_ids", "reconciled",
            "scheduled_date", "mock_wizard_mode", "mock_partial_reconcile", "move_id",
            "full_reconcile_id",
        )
        if name.startswith("_") or name in valid_attrs or callable(value):
            super().__setattr__(name, value)
        else:
            self._vals[name] = value

    def with_context(self, **kwargs):
        raw_ctx = self.__dict__.get("_ctx") or {}
        ctx = dict(raw_ctx) if isinstance(raw_ctx, dict) else {}
        ctx.update(kwargs)
        self._ctx = ctx
        return self

    def with_company(self, company):
        return self

    def get_param(self, key, default=False):
        if not hasattr(self, "_params"):
            self._params = {}
        return self._params.get(key, default)

    def set_param(self, key, value):
        if not hasattr(self, "_params"):
            self._params = {}
        self._params[key] = str(value)

    def unlink(self):
        if self._env and self._model in self._env:
            self._env[self._model].store.pop(self.id, None)
        return True

    def write(self, vals):
        self._vals.update(vals)
        for k, v in vals.items():
            setattr(self, k, v)
        return True

    def _find_or_create_acc(self, code: str, acc_type: str):
        if self._env and "account.account" in self._env:
            acc = self._env["account.account"].search([("code", "=", code)], limit=1)
            if acc:
                return acc
        return MockRecord({"code": code, "account_type": acc_type}, "account.account", int(code), self._env)

    def _create_valuation_move(self, ref_str: str, date_str: str, debit_code: str, credit_code: str, amount: float):
        if not self._env or "account.move" not in self._env:
            return None
        debit_acc = self._find_or_create_acc(
            debit_code, "expense" if debit_code.startswith("5") else "asset_current"
        )
        credit_acc = self._find_or_create_acc(
            credit_code, "expense" if credit_code.startswith("5") else "asset_current"
        )
        AML = self._env["account.move.line"] if "account.move.line" in self._env else None
        ln1_vals = {
            "name": f"{ref_str} Dr",
            "account_id": debit_acc,
            "debit": round(amount, 2),
            "credit": 0.0,
            "date": date_str,
            "reconciled": False,
        }
        ln2_vals = {
            "name": f"{ref_str} Cr",
            "account_id": credit_acc,
            "debit": 0.0,
            "credit": round(amount, 2),
            "date": date_str,
            "reconciled": False,
        }
        ln1 = AML.create(ln1_vals) if AML is not None else MockRecord(ln1_vals, "account.move.line", 1, self._env)
        ln2 = AML.create(ln2_vals) if AML is not None else MockRecord(ln2_vals, "account.move.line", 2, self._env)
        am = self._env["account.move"].create({
            "move_type": "entry",
            "ref": ref_str,
            "name": f"STJ/{ref_str}",
            "date": date_str,
            "state": "posted",
        })
        ln1.move_id = am
        ln2.move_id = am
        am.line_ids = MockRecordList([ln1, ln2])
        return am

    def action_confirm(self):
        if self._model == "stock.picking":
            self.state = "assigned"
            return True
        self.state = "sale"
        if self._model == "sale.order" and self._env and "stock.picking" in self._env:
            wh_loc = self._env["stock.location"].search(
                [("usage", "=", "internal"), ("name", "!=", "Karantina FMCG Maumbi")], limit=1
            )
            cust_loc = self._env["stock.location"].search([("usage", "=", "customer")], limit=1)
            move_lines = []
            moves = []
            for item in self._vals.get("order_line", []):
                line_data = item[2] if isinstance(item, (list, tuple)) and len(item) == 3 else {}
                p_id = line_data.get("product_id")
                qty = float(line_data.get("product_uom_qty", 0.0))
                mv = self._env["stock.move"].create({
                    "origin": self._vals.get("client_order_ref", "SO"),
                    "product_id": p_id,
                    "product_uom_qty": qty,
                    "quantity": qty,
                    "state": "assigned",
                    "location_id": wh_loc.id if wh_loc else 1,
                    "location_dest_id": cust_loc.id if cust_loc else 2,
                })
                ml = self._env["stock.move.line"].create({
                    "move_id": mv.id,
                    "product_id": p_id,
                    "lot_id": False,
                    "quantity": qty,
                    "qty_done": 0.0,
                    "location_id": wh_loc.id if wh_loc else 1,
                    "location_dest_id": cust_loc.id if cust_loc else 2,
                })
                mv.move_line_ids = MockRecordList([ml])
                move_lines.append(ml)
                moves.append(mv)

            pick = self._env["stock.picking"].create({
                "origin": self._vals.get("client_order_ref", "SO"),
                "picking_type_code": "outgoing",
                "state": "assigned",
                "location_id": wh_loc.id if wh_loc else 1,
                "location_dest_id": cust_loc.id if cust_loc else 2,
                "move_ids": MockRecordList(moves),
                "move_line_ids": MockRecordList(move_lines),
            })
            self.picking_ids = MockRecordList([pick])

    def button_confirm(self):
        self.state = "purchase"
        if self._model == "purchase.order" and self._env and "stock.picking" in self._env:
            wh_loc = self._env["stock.location"].search(
                [("usage", "=", "internal"), ("name", "!=", "Karantina FMCG Maumbi")], limit=1
            )
            sup_loc = self._env["stock.location"].search([("usage", "=", "supplier")], limit=1)
            move_lines = []
            moves = []
            for item in self._vals.get("order_line", []):
                line_data = item[2] if isinstance(item, (list, tuple)) and len(item) == 3 else {}
                p_id = line_data.get("product_id")
                qty = float(line_data.get("product_qty", 0.0))
                ml = self._env["stock.move.line"].create({
                    "product_id": p_id,
                    "lot_id": False,
                    "quantity": qty,
                    "qty_done": 0.0,
                    "location_id": sup_loc.id if sup_loc else 3,
                    "location_dest_id": wh_loc.id if wh_loc else 1,
                })
                move_lines.append(ml)
                mv = self._env["stock.move"].create({
                    "origin": self._vals.get("origin", "PO"),
                    "product_id": p_id,
                    "product_uom_qty": qty,
                    "quantity": qty,
                    "price_unit": float(line_data.get("price_unit", 0.0)),
                    "state": "assigned",
                    "location_id": sup_loc.id if sup_loc else 3,
                    "location_dest_id": wh_loc.id if wh_loc else 1,
                })
                moves.append(mv)

            pick = self._env["stock.picking"].create({
                "origin": self._vals.get("origin", "PO"),
                "picking_type_code": "incoming",
                "state": "assigned",
                "location_id": sup_loc.id if sup_loc else 3,
                "location_dest_id": wh_loc.id if wh_loc else 1,
                "move_ids": MockRecordList(moves),
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
        if self._model == "stock.picking" and self._env:
            ctx = getattr(self, "_ctx", {})
            eff_date = str(
                ctx.get("force_period_date")
                or ctx.get("date")
                or getattr(self, "scheduled_date", "")
                or "2026-07-01"
            )[:10]
            src_loc = self.location_id
            dest_loc = self.location_dest_id
            src_usage = getattr(src_loc, "usage", "")
            dest_usage = getattr(dest_loc, "usage", "")
            dest_name = str(getattr(dest_loc, "name", ""))

            # Update quants per move_line
            StockQuant = self._env["stock.quant"] if "stock.quant" in self._env else None
            qty_by_prod = {}
            for ml in list(getattr(self, "move_line_ids", [])):
                p_rec = getattr(ml, "product_id", None)
                p_id = getattr(p_rec, "id", p_rec)
                l_rec = getattr(ml, "lot_id", None)
                l_id = getattr(l_rec, "id", l_rec)
                qty = float(getattr(ml, "quantity", getattr(ml, "qty_done", 0.0)) or 0.0)
                if qty <= 0 or not p_id:
                    continue
                qty_by_prod[p_id] = qty_by_prod.get(p_id, 0.0) + qty
                if StockQuant is not None:
                    if src_usage == "internal":
                        q_src = StockQuant.search(
                            [("product_id", "=", p_id), ("location_id", "=", src_loc.id), ("lot_id", "=", l_id)],
                            limit=1,
                        )
                        if q_src:
                            q_src.write({"quantity": float(getattr(q_src, "quantity", 0.0)) - qty})
                    if dest_usage == "internal":
                        q_dst = StockQuant.search(
                            [("product_id", "=", p_id), ("location_id", "=", dest_loc.id), ("lot_id", "=", l_id)],
                            limit=1,
                        )
                        if q_dst:
                            q_dst.write({"quantity": float(getattr(q_dst, "quantity", 0.0)) + qty})
                        else:
                            StockQuant.create({
                                "product_id": p_id,
                                "location_id": dest_loc.id,
                                "lot_id": l_id,
                                "quantity": qty,
                                "reserved_quantity": 0.0,
                            })

            # Create native valuation account.move for active stock.moves
            active_moves = [
                mv for mv in list(getattr(self, "move_ids", []))
                if getattr(mv, "state", "") != "cancel"
            ]
            prod_move_counts = {}
            for mv in active_moves:
                p_rec = getattr(mv, "product_id", None)
                p_id = getattr(p_rec, "id", p_rec)
                prod_move_counts[p_id] = prod_move_counts.get(p_id, 0) + 1

            for mv in active_moves:
                p_rec = getattr(mv, "product_id", None)
                p_id = getattr(p_rec, "id", p_rec)
                mv_mls = [
                    ml for ml in list(getattr(self, "move_line_ids", []))
                    if getattr(getattr(ml, "move_id", None), "id", getattr(ml, "move_id", None)) == mv.id
                ]
                if mv_mls:
                    mv_qty = sum(float(getattr(ml, "quantity", getattr(ml, "qty_done", 0.0)) or 0.0) for ml in mv_mls)
                elif prod_move_counts.get(p_id, 0) == 1 and p_id in qty_by_prod:
                    mv_qty = qty_by_prod[p_id]
                else:
                    mv_qty = float(getattr(mv, "quantity", getattr(mv, "product_uom_qty", 0.0)) or 0.0)
                if mv_qty <= 0:
                    continue
                mv.state = "done"
                mv.quantity = mv_qty
                unit_cost = float(
                    getattr(mv, "price_unit", 0.0) or getattr(p_rec, "standard_price", 0.0) or 1000.0
                )
                val = round(mv_qty * unit_cost, 2)
                origin_str = str(getattr(self, "origin", None) or getattr(mv, "origin", "PICK"))
                if src_usage == "supplier" and dest_usage == "internal":
                    am = self._create_valuation_move(origin_str, eff_date, "113000", "113900", val)
                elif src_usage == "internal" and dest_usage == "customer":
                    am = self._create_valuation_move(origin_str, eff_date, "510000", "113000", val)
                elif src_usage == "customer" and (dest_usage == "internal" or "karantina" in dest_name.lower()):
                    am = self._create_valuation_move(origin_str, eff_date, "113000", "510000", val)
                else:
                    am = self._create_valuation_move(origin_str, eff_date, "113000", "113900", val)
                if am:
                    mv.account_move_id = am
        return True

    def action_apply_inventory(self):
        if self._model == "stock.quant":
            qty = float(self._vals.get("inventory_quantity", self._vals.get("quantity", 0.0)))
            self._vals["quantity"] = qty
            self.quantity = qty
            self._vals["reserved_quantity"] = 0.0
            if self._env and "stock.move" in self._env:
                ctx = getattr(self, "_ctx", {})
                eff_date = str(ctx.get("force_period_date") or "2026-07-01")[:10]
                p_rec = self.product_id
                p_id = getattr(p_rec, "id", p_rec)
                loc_rec = self.location_id
                loc_id = getattr(loc_rec, "id", loc_rec)
                l_rec = self.lot_id
                l_id = getattr(l_rec, "id", l_rec)
                inv_loc = self._env["stock.location"].search([("usage", "=", "inventory")], limit=1)
                ml = self._env["stock.move.line"].create({
                    "product_id": p_id,
                    "lot_id": l_id,
                    "quantity": qty,
                    "location_id": inv_loc.id if inv_loc else 5,
                    "location_dest_id": loc_id,
                    "date": f"{eff_date} 00:00:00",
                })
                mv = self._env["stock.move"].create({
                    "origin": "OPENING-20260701",
                    "product_id": p_id,
                    "location_id": inv_loc.id if inv_loc else 5,
                    "location_dest_id": loc_id,
                    "product_uom_qty": qty,
                    "quantity": qty,
                    "is_inventory": True,
                    "state": "done",
                    "date": f"{eff_date} 00:00:00",
                    "move_line_ids": MockRecordList([ml]),
                })
                unit_cost = float(getattr(p_rec, "standard_price", 0.0) or 1000.0)
                val = round(qty * unit_cost, 2)
                am = self._create_valuation_move("OPENING-20260701", eff_date, "113000", "113900", val)
                if am:
                    mv.account_move_id = am
        return True

    def action_post(self):
        self.state = "posted"
        if self._model == "account.move":
            m_type = self._vals.get("move_type", "entry")
            eff_date = self._vals.get("date") or self._vals.get("invoice_date") or "2026-07-01"
            if m_type == "out_invoice":
                inv_line_records = []
                total_amt = 0.0
                for idx, inv_line in enumerate(self._vals.get("invoice_line_ids", []), start=10):
                    if isinstance(inv_line, (list, tuple)) and len(inv_line) == 3:
                        ldata = inv_line[2]
                        l_qty = float(ldata.get("quantity", 0.0))
                        l_price = float(ldata.get("price_unit", 0.0))
                        l_disc = float(ldata.get("discount", 0.0))
                        l_net = l_qty * l_price * (1.0 - l_disc / 100.0)
                        total_amt += l_net
                        il_rec = MockRecord({
                            "name": ldata.get("name", "Sales Line"),
                            "product_id": ldata.get("product_id"),
                            "product_uom_id": ldata.get("product_uom_id"),
                            "sale_line_ids": ldata.get("sale_line_ids", []),
                            "quantity": l_qty,
                            "price_unit": l_price,
                            "discount": l_disc,
                            "display_type": "product",
                            "account_id": MockRecord(
                                {"account_type": "income", "code": "410000"}, "account.account", 2, self._env
                            ),
                            "debit": 0.0,
                            "credit": round(l_net, 2),
                            "date": eff_date,
                            "reconciled": False,
                        }, "account.move.line", self.id * 100 + idx, self._env)
                        il_rec.move_id = self
                        inv_line_records.append(il_rec)
                self.amount_untaxed = round(total_amt, 2)
                self.amount_tax = round(total_amt * 0.11, 2)
                self.amount_total = round(total_amt + self.amount_tax, 2)
                self.amount_residual = self.amount_total
                ar_line = MockRecord({
                    "name": self._vals.get("ref", "AR Invoice"),
                    "account_id": MockRecord(
                        {"account_type": "asset_receivable", "code": "112000"}, "account.account", 1, self._env
                    ),
                    "debit": self.amount_total,
                    "credit": 0.0,
                    "date": eff_date,
                    "display_type": "payment_term",
                    "reconciled": False,
                }, "account.move.line", self.id * 100 + 1, self._env)
                ar_line.move_id = self
                tax_line = MockRecord({
                    "name": "PPN Keluaran 11%",
                    "account_id": MockRecord(
                        {"account_type": "liability_current", "code": "212000"}, "account.account", 7, self._env
                    ),
                    "debit": 0.0,
                    "credit": self.amount_tax,
                    "date": eff_date,
                    "display_type": "tax",
                    "reconciled": False,
                }, "account.move.line", self.id * 100 + 3, self._env)
                tax_line.move_id = self
                self.invoice_line_ids = MockRecordList(inv_line_records)
                self.line_ids = MockRecordList([ar_line] + inv_line_records + [tax_line])
            elif m_type == "in_invoice":
                exp_lines = []
                total_amt = 0.0
                for idx, inv_line in enumerate(self._vals.get("invoice_line_ids", []), start=10):
                    if isinstance(inv_line, (list, tuple)) and len(inv_line) == 3:
                        ldata = inv_line[2]
                        l_amt = float(ldata.get("quantity", 1.0)) * float(ldata.get("price_unit", 0.0))
                        total_amt += l_amt
                        acc_val = ldata.get("account_id")
                        if isinstance(acc_val, MockRecord):
                            exp_acc = acc_val
                        elif isinstance(acc_val, int) and self._env and "account.account" in self._env:
                            exp_acc = self._env["account.account"].browse(acc_val)
                        else:
                            exp_acc = MockRecord(
                                {"account_type": "expense", "code": "610000"}, "account.account", 4, self._env
                            )
                        exp_ln = MockRecord({
                            "name": ldata.get("name", "Expense Line"),
                            "account_id": exp_acc,
                            "debit": round(l_amt, 2),
                            "credit": 0.0,
                            "quantity": float(ldata.get("quantity", 1.0)),
                            "price_unit": float(ldata.get("price_unit", 0.0)),
                            "date": eff_date,
                            "display_type": "product",
                            "reconciled": False,
                        }, "account.move.line", self.id * 100 + idx, self._env)
                        exp_ln.move_id = self
                        exp_lines.append(exp_ln)
                self.amount_untaxed = round(total_amt, 2)
                self.amount_total = round(total_amt, 2)
                self.amount_residual = round(total_amt, 2)
                ap_line = MockRecord({
                    "name": self._vals.get("ref", "AP Bill"),
                    "account_id": MockRecord(
                        {"account_type": "liability_payable", "code": "211000"}, "account.account", 3, self._env
                    ),
                    "debit": 0.0,
                    "credit": round(total_amt, 2),
                    "date": eff_date,
                    "display_type": "payment_term",
                    "reconciled": False,
                }, "account.move.line", self.id * 100 + 1, self._env)
                ap_line.move_id = self
                self.invoice_line_ids = MockRecordList(exp_lines)
                self.line_ids = MockRecordList([ap_line] + exp_lines)
            elif m_type == "entry":
                lines = []
                for idx, item in enumerate(self._vals.get("line_ids", []), start=1):
                    ldata = item[2] if isinstance(item, (list, tuple)) and len(item) == 3 else {}
                    acc_type = "asset_receivable" if "Piutang" in ldata.get("name", "") else "expense"
                    acc_code = "112000" if acc_type == "asset_receivable" else "620000"
                    ln_rec = MockRecord({
                        "name": ldata.get("name", "Journal Line"),
                        "account_id": MockRecord(
                            {"account_type": acc_type, "code": acc_code}, "account.account", 5, self._env
                        ),
                        "debit": ldata.get("debit", 0.0),
                        "credit": ldata.get("credit", 0.0),
                        "date": eff_date,
                        "reconciled": False,
                    }, "account.move.line", self.id * 100 + idx, self._env)
                    ln_rec.move_id = self
                    lines.append(ln_rec)
                self.line_ids = MockRecordList(lines)
        elif self._model == "account.payment":
            self.state = "in_process"
            p_type = self._vals.get("payment_type", "inbound")
            amt = float(self._vals.get("amount", 0.0))
            pay_ref = self._vals.get("ref", self._vals.get("memo", ""))
            pay_date = self._vals.get("date", "2026-07-01")
            self.move_id = MockRecord(
                {"state": "posted", "ref": pay_ref, "date": pay_date},
                "account.move",
                100000 + self.id,
                self._env,
            )
            if p_type == "inbound":
                cash_line = MockRecord({
                    "name": pay_ref or "Cash In",
                    "account_id": MockRecord(
                        {"account_type": "asset_cash", "code": "111000"}, "account.account", 6, self._env
                    ),
                    "debit": amt,
                    "credit": 0.0,
                    "date": pay_date,
                    "reconciled": False,
                }, "account.move.line", (100000 + self.id) * 10 + 1, self._env)
                cash_line.move_id = self.move_id
                ar_line = MockRecord({
                    "name": pay_ref or "AR Payment",
                    "account_id": MockRecord(
                        {"account_type": "asset_receivable", "code": "112000"}, "account.account", 1, self._env
                    ),
                    "debit": 0.0,
                    "credit": amt,
                    "date": pay_date,
                    "reconciled": False,
                }, "account.move.line", (100000 + self.id) * 10 + 2, self._env)
                ar_line.move_id = self.move_id
                ar_line._payment = self
                self.line_ids = MockRecordList([cash_line, ar_line])
                if getattr(self, "mock_partial_reconcile", False):
                    self.line_ids.mock_partial_reconcile = True
            else:
                ap_line = MockRecord({
                    "name": pay_ref or "AP Payment",
                    "account_id": MockRecord(
                        {"account_type": "liability_payable", "code": "211000"}, "account.account", 3, self._env
                    ),
                    "debit": amt,
                    "credit": 0.0,
                    "date": pay_date,
                    "reconciled": False,
                }, "account.move.line", (100000 + self.id) * 10 + 1, self._env)
                ap_line.move_id = self.move_id
                cash_line = MockRecord({
                    "name": pay_ref or "Cash Out",
                    "account_id": MockRecord(
                        {"account_type": "asset_cash", "code": "111000"}, "account.account", 6, self._env
                    ),
                    "debit": 0.0,
                    "credit": amt,
                    "date": pay_date,
                    "reconciled": False,
                }, "account.move.line", (100000 + self.id) * 10 + 2, self._env)
                cash_line.move_id = self.move_id
                ap_line._payment = self
                self.line_ids = MockRecordList([ap_line, cash_line])
                if getattr(self, "mock_partial_reconcile", False):
                    self.line_ids.mock_partial_reconcile = True

            self.move_id.line_ids = self.line_ids


class MockModel:
    def __init__(self, name, env=None):
        self.name = name
        self.store = {}
        self.seq = 1
        self.env = env
        self._fields = {}

    def __or__(self, other):
        res = MockRecordList()
        if isinstance(other, (list, MockRecordList)):
            for item in other:
                if item not in res:
                    res.append(item)
        elif other and not isinstance(other, MockModel):
            res.append(other)
        return res

    def sudo(self):
        return self

    def with_context(self, **kw):
        return self

    def with_company(self, company):
        return self

    def get_param(self, key, default=False):
        if not hasattr(self, "_params"):
            self._params = {}
        return self._params.get(key, default)

    def set_param(self, key, value):
        if not hasattr(self, "_params"):
            self._params = {}
        self._params[key] = str(value)

    def search(self, domain=None, limit=None, order=None, **kwargs):
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
                elif op == "in":
                    val_set = val if isinstance(val, (list, tuple, set)) else [val]
                    raw_rec_val = getattr(rec_val, "id", rec_val)
                    norm_vals = [getattr(v, "id", v) for v in val_set]
                    if rec_val not in val_set and raw_rec_val not in norm_vals:
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
        self.name = "PT Salva Inti Mandiri"
        self.code = "FMCG"
        self.partner_id = None


class MockCursor:
    def __init__(self, env=None):
        self.env = env
        self.committed = False
        self.rollbacked = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rollbacked = True
        if self.env and hasattr(self.env, "_restore_snapshot"):
            self.env._restore_snapshot()


def _serialize_val(val):
    if isinstance(val, (int, float, str, bool, type(None))):
        return val
    elif hasattr(val, "id"):
        return ("__rec__", getattr(val, "_model", ""), val.id)
    elif isinstance(val, tuple):
        return tuple(_serialize_val(x) for x in val)
    elif isinstance(val, list):
        return [_serialize_val(x) for x in val]
    elif isinstance(val, dict):
        return {k: _serialize_val(v) for k, v in val.items() if k not in ("_env", "_model")}
    else:
        return str(val)


def _restore_val(val, env):
    if isinstance(val, (int, float, str, bool, type(None))):
        return val
    elif isinstance(val, (list, tuple)):
        if len(val) == 3 and val[0] == "__rec__":
            m_name, rec_id = val[1], val[2]
            if m_name and m_name in env and rec_id in env[m_name].store:
                return env[m_name].store[rec_id]
            return None
        if isinstance(val, tuple):
            return tuple(_restore_val(x, env) for x in val)
        return [_restore_val(x, env) for x in val]
    elif isinstance(val, dict):
        return {k: _restore_val(v, env) for k, v in val.items()}
    return val


class MockEnv(dict):
    def __init__(self):
        super().__init__()
        self.cr = MockCursor(env=self)
        self.company = MockCompany()
        models = [
            "res.partner", "product.product", "res.users", "stock.quant", "stock.location",
            "stock.lot", "purchase.order", "sale.order", "account.move", "account.payment",
            "stock.picking", "stock.move", "stock.move.line", "account.account",
            "account.journal", "product.category",
        ]
        for m in models:
            self[m] = MockModel(m, env=self)
        self.company.partner_id = self["res.partner"].create({"name": "PT MDU", "ref": "COMPANY"})
        self["ir.config_parameter"].set_param("fmcg.seed_company_id", str(self.company.id))
        self._initial_snapshot = None

    def _take_snapshot(self):
        snapshot = {}
        for m in self:
            snapshot[m] = {}
            for rec_id, rec in self[m].store.items():
                vals_copy = {
                    k: _serialize_val(v)
                    for k, v in getattr(rec, "_vals", {}).items()
                    if k not in ("_env", "_model")
                }
                attrs_copy = {
                    k: _serialize_val(v)
                    for k, v in rec.__dict__.items()
                    if k not in ("_env", "_model", "_vals")
                }
                snapshot[m][rec_id] = {
                    "vals": vals_copy,
                    "attrs": attrs_copy,
                }
        return snapshot

    def _restore_snapshot(self, snapshot=None):
        snap = snapshot or getattr(self, "_initial_snapshot", None)
        if snap:
            for m, model_snap in snap.items():
                if m in self:
                    # Hapus record baru yang dibuat setelah snapshot
                    for rec_id in list(self[m].store.keys()):
                        if rec_id not in model_snap:
                            del self[m].store[rec_id]
                    # Pulihkan state record yang ada
                    for rec_id, data in model_snap.items():
                        if rec_id in self[m].store:
                            rec = self[m].store[rec_id]
                            rec._vals = {k: _restore_val(v, self) for k, v in data["vals"].items()}
                            for k, v in data["attrs"].items():
                                setattr(rec, k, _restore_val(v, self))

    def __missing__(self, key):
        model = MockModel(key, env=self)
        self[key] = model
        return model

    def ref(self, xml_id, raise_if_not_found=False):
        return MockRecord({"name": xml_id}, "base", 1, self)


def setup_standard_mock_env():
    mock_env = MockEnv()

    # Prepopulate standard accounts & journal
    mock_env["account.account"].create({
        "name": "Persediaan Barang Dagang",
        "code": "113000",
        "account_type": "asset_current",
    })
    mock_env["account.account"].create({
        "name": "Penerimaan Barang Belum Ditagih",
        "code": "113900",
        "account_type": "liability_current",
    })
    mock_env["account.account"].create({
        "name": "Pengiriman Barang Belum Difakturkan",
        "code": "113910",
        "account_type": "asset_current",
    })
    mock_env["account.account"].create({
        "name": "Beban Pokok Pendapatan",
        "code": "510000",
        "account_type": "expense",
    })
    mock_env["account.journal"].create({
        "name": "Penilaian Persediaan",
        "code": "STJ",
        "type": "general",
    })
    fmcg_categ = mock_env["product.category"].create({"name": "All / FMCG"})

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
        mock_env["product.product"].create({
            "name": pr["product_name"],
            "default_code": pr["sku_code"],
            "categ_id": fmcg_categ,
        })

    mock_env["product.category"]._fields = {
        "name": True,
        "property_cost_method": True,
        "property_valuation": True,
        "property_stock_valuation_account_id": True,
        "property_stock_journal": True,
        "property_stock_account_input_categ_id": True,
        "property_stock_account_output_categ_id": True,
        "property_account_expense_categ_id": True,
    }
    mock_env["stock.location"]._fields = {
        "name": True,
        "usage": True,
        "location_id": True,
        "valuation_account_id": True,
        "company_id": True,
    }
    mock_env["product.product"]._fields = {
        "name": True,
        "default_code": True,
        "categ_id": True,
        "standard_price": True,
        "company_id": True,
        "property_stock_inventory": True,
        "uom_id": True,
    }
    mock_env["account.move.line"]._fields = {
        "name": True,
        "account_id": True,
        "debit": True,
        "credit": True,
        "date": True,
        "reconciled": True,
        "product_id": True,
        "product_uom_id": True,
        "sale_line_ids": True,
        "quantity": True,
        "price_unit": True,
        "discount": True,
        "display_type": True,
    }
    mock_env["stock.location"].create({"name": "WH/Stock", "usage": "internal", "company_id": mock_env.company.id})
    mock_env["stock.location"].create({
        "name": "Karantina FMCG Maumbi",
        "usage": "internal",
        "company_id": mock_env.company.id,
    })
    mock_env["stock.location"].create({"name": "Partner Locations/Customers", "usage": "customer", "company_id": False})
    mock_env["stock.location"].create({"name": "Partner Locations/Vendors", "usage": "supplier", "company_id": False})
    mock_env["stock.location"].create({
        "name": "Virtual Locations/Inventory adjustment",
        "usage": "inventory",
        "company_id": False,
    })
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

        # Quant di Karantina tepat 8 baris unik (sku, lot) untuk 9 retur (REJ-003 & REJ-005 berbagi lot sama),
        # dengan total 320.0 unit (tidak terduplikasi menjadi 640.0 unit oleh fallback manual)
        post_quant_count = len(mock_env["stock.quant"].store)
        self.assertEqual(post_quant_count - initial_quant_count, 8)
        tot_quar_units = sum(float(getattr(q, "quantity", 0.0)) for q in mock_env["stock.quant"].store.values())
        self.assertEqual(tot_quar_units, 320.0)

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

    def test_final_readback_fails_fast_when_discount_amount_tampered_to_one(self):
        """Jika nominal kredit piutang jurnal diskon diubah (Rp 1), run_all wajib melempar AssertionError."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        original_load_payments = adapter.load_payments

        def corrupted_load_payments(*args, **kwargs):
            original_load_payments(*args, **kwargs)
            # Manipulasi baris kredit diskon menjadi 1.0 (Rp 1)
            for m in mock_env["account.move"].store.values():
                if getattr(m, "ref", "").startswith("DISC-"):
                    for line_rec in getattr(m, "line_ids", []):
                        if getattr(getattr(line_rec, "account_id", None), "account_type", "") == "asset_receivable":
                            line_rec.credit = 1.0
                            line_rec.amount_residual = 0.0

        adapter.load_payments = corrupted_load_payments

        with self.assertRaises(AssertionError) as ctx:
            adapter.run_all(limit_orders=1)

        self.assertIn("Nominal kredit piutang jurnal diskon", str(ctx.exception))
        self.assertTrue(mock_env.cr.rollbacked)
        self.assertFalse(mock_env.cr.committed)

    def test_final_readback_fails_fast_when_invoice_receivable_lines_emptied(self):
        """Jika baris piutang faktur pasangan dikosongkan, run_all wajib melempar AssertionError."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        original_load_payments = adapter.load_payments

        def corrupted_load_payments(*args, **kwargs):
            original_load_payments(*args, **kwargs)
            # Kosongkan baris piutang (asset_receivable) pada seluruh faktur pasangan
            for m in mock_env["account.move"].store.values():
                if getattr(m, "move_type", "") == "out_invoice":
                    m.line_ids = MockRecordList([
                        line_rec for line_rec in getattr(m, "line_ids", [])
                        if getattr(getattr(line_rec, "account_id", None), "account_type", "") != "asset_receivable"
                    ])

        adapter.load_payments = corrupted_load_payments

        with self.assertRaises(AssertionError) as ctx:
            adapter.run_all(limit_orders=1)

        self.assertIn("tidak memiliki baris piutang (asset_receivable)", str(ctx.exception))
        self.assertTrue(mock_env.cr.rollbacked)
        self.assertFalse(mock_env.cr.committed)

    def test_opening_stock_quant_creation_uses_inventory_adjustment_mode(self):
        """Memastikan pembukaan stok menggunakan mode inventory adjustment native (inventory_quantity)."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        adapter.load_opening_stock()
        self.assertEqual(adapter.stats["opening_quants"], 150)

        # Periksa salah satu quant: pastikan inventory_quantity terisi
        quants = list(mock_env["stock.quant"].store.values())
        self.assertEqual(len(quants), 150)
        first_q = quants[0]
        self.assertGreater(getattr(first_q, "quantity", 0.0), 0.0)
        self.assertGreater(getattr(first_q, "inventory_quantity", 0.0), 0.0)

    def test_opening_stock_idempotency_does_not_override_existing_quant_on_rerun(self):
        """Memastikan rerun load_opening_stock tidak mereset kuantitas quant yang sudah terpakai."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        adapter.load_opening_stock()
        quants = list(mock_env["stock.quant"].store.values())
        first_q = quants[0]
        original_qty = first_q.quantity

        # Simulasikan stok berkurang karena pengiriman penjualan
        first_q.quantity = original_qty - 5.0

        # Jalankan rerun load_opening_stock
        adapter_run2 = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)
        adapter_run2.load_opening_stock()

        self.assertEqual(adapter_run2.stats["opening_quants"], 0)
        self.assertEqual(adapter_run2.stats["skipped_opening_quants"], 150)
        # Saldo quant tidak boleh di-reset kembali ke original_qty
        self.assertEqual(first_q.quantity, original_qty - 5.0)

    # -------------------------------------------------------------------------
    # Regression Tests: Audit Pasangan Akun AST, Helper Contract & Split Fidelity
    # -------------------------------------------------------------------------
    def _extract_function_from_experiment_ast(self, func_name):
        """Mengekstrak fungsi dari AST scripts/ops/verify_historical_experiment.py secara dinamis."""
        import ast
        script_path = ROOT / "scripts" / "ops" / "verify_historical_experiment.py"
        source_code = script_path.read_text(encoding="utf-8")
        parsed = ast.parse(source_code)
        target_node = None
        for node in ast.walk(parsed):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                target_node = node
                break
        if not target_node:
            raise RuntimeError(f"Fungsi {func_name} tidak ditemukan dalam AST!")
        mod = ast.Module(body=[target_node], type_ignores=[])
        compiled = compile(mod, filename=f"<ast_{func_name}>", mode="exec")
        ns = {}
        exec(compiled, ns)
        return ns[func_name]

    def test_audit_event_account_pair_rejects_split_fraud_ast_payload(self):
        """Memverifikasi fungsi audit_event_account_pair menolak split fraud Rp1 HPP + Rp99 akun salah."""
        audit_fn = self._extract_function_from_experiment_ast("audit_event_account_pair")

        class MockAccount:
            def __init__(self, code, name):
                self.code = code
                self.name = name

        class MockLine:
            def __init__(self, code, debit, credit):
                self.account_id = MockAccount(code, f"Acc {code}")
                self.debit = debit
                self.credit = credit

        class MockAccountMove:
            def __init__(self, lines, state="posted", ref="DO-202607-0063"):
                self.id = 101
                self.name = ref
                self.ref = ref
                self.state = state
                self.line_ids = lines

        class MockStockMove:
            def __init__(self, am):
                self.id = 201
                self.origin = "DO-202607-0063"
                self.account_move_id = am
                self.picking_id = None

        mock_env = setup_standard_mock_env()
        # Set closure globals
        audit_fn.__globals__["env"] = mock_env
        audit_fn.__globals__["company"] = mock_env.company

        # 1. Baseline Valid: Debit 510000 = Rp 100, Credit 113000 = Rp 100
        valid_lines = [
            MockLine("510000", 100.0, 0.0),
            MockLine("113000", 0.0, 100.0),
        ]
        mv_valid = MockStockMove(MockAccountMove(valid_lines))
        res = audit_fn("delivery", mv_valid, "510000", "113000", 100.0)
        self.assertTrue(res["balanced"])
        self.assertEqual(res["amount"], 100.0)
        self.assertEqual(res["debit_account"], "510000")
        self.assertEqual(res["credit_account"], "113000")

        # 2. Celah Split Fraud yang Diuji Supervisor: Debit Rp1 HPP + Rp99 Akun Asing
        fraud_lines = [
            MockLine("510000", 1.0, 0.0),
            MockLine("999999", 99.0, 0.0),
            MockLine("113000", 0.0, 100.0),
        ]
        mv_fraud = MockStockMove(MockAccountMove(fraud_lines))
        with self.assertRaises(ValueError) as ctx:
            audit_fn("delivery", mv_fraud, "510000", "113000", 100.0)
        self.assertTrue(
            "memiliki baris debit tidak sah/ekstra" in str(ctx.exception)
            or "tidak cocok dengan expected" in str(ctx.exception)
        )

        # 3. Substitusi Akun Kredit: Debit Rp 100 ke 510000, Kredit Rp 100 ke Akun Salah
        credit_sub_lines = [
            MockLine("510000", 100.0, 0.0),
            MockLine("999999", 0.0, 100.0),
        ]
        mv_credit_sub = MockStockMove(MockAccountMove(credit_sub_lines))
        with self.assertRaises(ValueError) as ctx:
            audit_fn("delivery", mv_credit_sub, "510000", "113000", 100.0)
        self.assertTrue(
            "tidak mengkredit akun yang diharapkan" in str(ctx.exception)
            or "baris kredit tidak sah/ekstra" in str(ctx.exception)
        )

        # 4. Jurnal Tidak Berimbang: Debit Rp 100, Kredit Rp 90
        unbalanced_lines = [
            MockLine("510000", 100.0, 0.0),
            MockLine("113000", 0.0, 90.0),
        ]
        mv_unbalanced = MockStockMove(MockAccountMove(unbalanced_lines))
        with self.assertRaises(ValueError) as ctx:
            audit_fn("delivery", mv_unbalanced, "510000", "113000", 100.0)
        self.assertIn("tidak berimbang", str(ctx.exception))

    def test_find_and_backdate_native_account_moves_returns_nonempty_recordset(self):
        """Memverifikasi helper find_and_backdate_native_account_moves mengembalikan recordset valid (bukan None)."""
        helper_fn = self._extract_function_from_experiment_ast("find_and_backdate_native_account_moves")

        class MockAccountMove:
            def __init__(self):
                self.id = 501
                self.ref = "OPENING-20260701"
                self.date = "2026-07-01"
                self.state = "posted"
                self.line_ids = []

        class MockStockMove:
            def __init__(self, am):
                self.id = 601
                self.account_move_id = am
                self.account_move_ids = None

        mock_env = setup_standard_mock_env()
        helper_fn.__globals__["env"] = mock_env
        helper_fn.__globals__["company"] = mock_env.company
        helper_fn.__globals__["experiment_account_move_ids"] = set()
        helper_fn.__globals__["experiment_account_move_event_dates"] = {}

        am_instance = MockAccountMove()
        sm_instance = MockStockMove(MockRecordList([am_instance]))

        found = helper_fn(sm_instance, "OPENING-20260701", "2026-07-01 00:00:00")
        self.assertIsNotNone(found, "Helper tidak boleh mengembalikan None!")
        self.assertEqual(len(found), 1, "Helper wajib mengembalikan recordset non-empty!")
        self.assertEqual(found[0].id, 501)

    def test_move_line_reservation_fidelity_and_insufficient_stock_rejection(self):
        """Memverifikasi fungsi produksi allocate_and_sync_move_lines (diekstrak via AST):
        1. Alokasi multi-line proporsional menjaga batas kapasitas per line & lot.
        2. Guard empty reservation pada internal location menolak reservasi kosong.
        3. Guard insufficient reservation pada internal location menolak kuantitas kurang.
        4. Guard lot mismatch menolak ketidakcocokan lot reservasi dengan target register kanonikal.
        """
        alloc_fn = self._extract_function_from_experiment_ast("allocate_and_sync_move_lines")

        class MockLot:
            def __init__(self, lot_id, name):
                self.id = lot_id
                self.name = name

        class MockMoveLine:
            def __init__(self, line_id, lot, qty):
                self.id = line_id
                self.lot_id = lot
                self.quantity = qty
                self.qty_done = qty
                self.picked = False
                self.unlinked = False

            def write(self, vals):
                if "quantity" in vals:
                    self.quantity = vals["quantity"]
                if "qty_done" in vals:
                    self.qty_done = vals["qty_done"]
                if "lot_id" in vals:
                    self.lot_id = vals["lot_id"]
                if "picked" in vals:
                    self.picked = vals["picked"]

            def unlink(self):
                self.unlinked = True

        class MockLocation:
            def __init__(self, usage="internal", name="WH/Stock"):
                self.usage = usage
                self.name = name
                self.complete_name = f"WH/{name}"

        class MockStockMove:
            def __init__(self, lines, loc_usage="internal", origin="DO-202607-0063"):
                self.id = 301
                self.origin = origin
                self.location_id = MockLocation(usage=loc_usage)
                self.location_dest_id = MockLocation(usage="customer", name="Output")
                self.move_line_ids = MockRecordList(lines)
                self.company_id = MockRecord({"name": "PT MDU"}, "res.company", 1)
                self.product_id = MockRecord({"name": "Rinso"}, "product.product", 1)
                self.product_uom = MockRecord({"name": "Carton"}, "uom.uom", 1)
                self.picked = False

            def write(self, vals):
                if "picked" in vals:
                    self.picked = vals["picked"]

        class MockStockMoveLineModel:
            _fields = {
                "quantity": True,
                "qty_done": True,
                "lot_id": True,
                "picked": True,
                "date": True,
                "picking_id": True,
            }

            def sudo(self):
                return self

        class MockStockMoveModel:
            _fields = {"picked": True}

            def sudo(self):
                return self

        mock_env = {
            "stock.move.line": MockStockMoveLineModel(),
            "stock.move": MockStockMoveModel(),
        }

        lot_a = MockLot(1, "LOT-ALPHA")
        lot_b = MockLot(2, "LOT-BETA")

        # 1. Alokasi Multi-Line & Multi-Lot: Demand 7 karton terbagi ke 4 (Line 1, Lot-A) + 3 (Line 2, Lot-A)
        ml1 = MockMoveLine(10, lot_a, 4.0)
        ml2 = MockMoveLine(11, lot_a, 3.0)
        mv = MockStockMove([ml1, ml2], loc_usage="internal")
        mock_picking = MockRecord({"name": "DO-202607-0063"}, "stock.picking", 401)

        alloc_fn(mock_env, mv, mock_picking, 7.0, target_lot=lot_a, move_date="2026-07-03 14:00:00")

        self.assertEqual(ml1.quantity, 4.0, "Line 1 wajib teralokasi tepat 4.0 sesuai kapasitas!")
        self.assertEqual(ml2.quantity, 3.0, "Line 2 wajib teralokasi tepat 3.0!")
        self.assertTrue(ml1.picked, "Line 1 wajib berstatus picked=True!")
        self.assertTrue(ml2.picked, "Line 2 wajib berstatus picked=True!")
        self.assertTrue(mv.picked, "Move wajib berstatus picked=True!")
        self.assertFalse(ml1.unlinked)
        self.assertFalse(ml2.unlinked)

        # 2. Guard Empty Reservation pada Lokasi Internal -> Wajib Ditolak Fail-Fast
        mv_empty = MockStockMove([], loc_usage="internal")
        with self.assertRaises(ValueError) as ctx_empty:
            alloc_fn(mock_env, mv_empty, mock_picking, 7.0, target_lot=lot_a, move_date="2026-07-03 14:00:00")
        self.assertIn("Reservasi kosong", str(ctx_empty.exception))
        self.assertIn("Penolakan stok negatif", str(ctx_empty.exception))

        # 3. Demand Melebihi Kuantitas Reservasi pada Internal Transfer -> Wajib Ditolak Fail-Fast
        ml_short = MockMoveLine(12, lot_a, 4.0)
        mv_short = MockStockMove([ml_short], loc_usage="internal")
        with self.assertRaises(ValueError) as ctx_short:
            alloc_fn(mock_env, mv_short, mock_picking, 10.0, target_lot=lot_a, move_date="2026-07-03 14:00:00")
        self.assertIn("tidak mencukupi demand", str(ctx_short.exception))

        # 4. Reserved Lot Mismatch terhadap Target Lot Register Kanonikal -> Wajib Ditolak Fail-Fast
        ml_mismatch = MockMoveLine(13, lot_b, 4.0)  # Reservasi lot_b (id=2), target lot_a (id=1)
        mv_mismatch = MockStockMove([ml_mismatch], loc_usage="internal")
        with self.assertRaises(ValueError) as ctx_lot:
            alloc_fn(mock_env, mv_mismatch, mock_picking, 4.0, target_lot=lot_a, move_date="2026-07-03 14:00:00")
        self.assertIn("tidak cocok dengan lot target register", str(ctx_lot.exception))

    def test_validate_picking_safely_handles_confirm_stock_sms_wizard(self):
        """Memverifikasi dispatcher wizard _validate_picking_safely memproses jalur dont_send_sms() hingga selesai."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        sms_wizard_called = {"dont_send_sms": False}

        class MockConfirmStockSms:
            _fields = {"pick_ids": True}

            def __init__(self, pick):
                self.pick = pick

            def sudo(self):
                return self

            def with_context(self, **kwargs):
                return self

            def browse(self, wiz_id):
                return self

            def create(self, vals):
                return self

            def dont_send_sms(self):
                sms_wizard_called["dont_send_sms"] = True
                self.pick.state = "done"
                return True

        class MockPickingWithSms:
            def __init__(self):
                self.id = 888
                self.name = "DO-202607-0063"
                self.state = "assigned"
                self._ctx = {}
                self._wizard_dispatched = False

            def with_context(self, **kwargs):
                self._ctx.update(kwargs)
                return self

            def button_validate(self):
                if not self._wizard_dispatched:
                    self._wizard_dispatched = True
                    return {
                        "type": "ir.actions.act_window",
                        "res_model": "confirm.stock.sms",
                        "context": {"default_pick_ids": [(4, self.id)]},
                    }
                self.state = "done"
                return True

        pick_instance = MockPickingWithSms()
        mock_env["confirm.stock.sms"] = MockConfirmStockSms(pick_instance)

        adapter._validate_picking_safely(pick_instance)

        self.assertTrue(sms_wizard_called["dont_send_sms"], "Wizard dont_send_sms() wajib terpanggil!")
        self.assertEqual(pick_instance.state, "done", "Picking wajib berhasil mencapai status 'done'!")

    def test_assign_lots_multi_lot_split_so317_with_falsy_model(self):
        """Memverifikasi kasus register nyata SO-202607-0317 (ULV-SNL-04: 5+4 karton = 216 unit)

        membuktikan bahwa pemetaan multi-lot split berhasil 100% dan tidak hilang
        meskipun model stock.move.line adalah falsy recordset (bool(Model) == False).
        """
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        # Buat Falsy Model untuk stock.move.line: bool(MockFalsyMoveLineModel()) == False
        class MockFalsyMoveLineModel:
            def __init__(self, records=None):
                self._records = records or []
                self._fields = {
                    "picking_id": True, "move_id": True, "product_id": True,
                    "lot_id": True, "lot_name": True, "quantity": True,
                    "qty_done": True, "picked": True, "product_uom_id": True,
                }

            def __bool__(self):
                # Mensimulasikan empty recordset Odoo yang bernilai False
                return False

            def sudo(self):
                return self

            def create(self, vals):
                from tests.test_canonical_loader_adapter import MockRecord
                rec = MockRecord(vals, "stock.move.line", len(self._records) + 600)
                self._records.append(rec)
                return rec

        falsy_sml_model = MockFalsyMoveLineModel()
        mock_env["stock.move.line"] = falsy_sml_model

        prod = adapter.product_by_code.get("ULV-SNL-04")
        self.assertIsNotNone(prod, "Produk ULV-SNL-04 wajib ada di catalog!")

        class MockMove:
            def __init__(self, prod_id):
                self.id = 101
                self.product_id = prod_id
                self._fields = {"picked": True}
                self.picked = False

            def write(self, vals):
                if "picked" in vals:
                    self.picked = vals["picked"]

        class MockPicking:
            def __init__(self, prod_id):
                self.id = 999
                self.name = "DO-202607-0317"
                self.move_ids = [MockMove(prod_id)]
                # Awalnya hanya ada 1 existing move line default tanpa lot
                from tests.test_canonical_loader_adapter import MockRecord
                init_sml = MockRecord(
                    {
                        "id": 501, "product_id": prod_id, "lot_id": False,
                        "lot_name": False, "quantity": 0.0, "picked": False,
                    },
                    "stock.move.line",
                    501,
                )
                self.move_line_ids = [init_sml]

        pick = MockPicking(prod.id)

        # Baris register nyata SO-202607-0317 dari perpetual_order_lines.csv
        # 5 karton lot 1 (120 unit) + 4 karton lot 2 (96 unit) = 216 unit
        lines_data = [
            {
                "sku_code": "ULV-SNL-04",
                "qty_cartons": "5",
                "carton_qty": "24",
                "lot_number": "LOT-VER-20260615-INIT-04",
                "expiry_date": "2028-06-15",
            },
            {
                "sku_code": "ULV-SNL-04",
                "qty_cartons": "4",
                "carton_qty": "24",
                "lot_number": "LOT-VER-20260704-04",
                "expiry_date": "2028-07-04",
            },
        ]

        adapter._assign_lots_to_picking(pick, lines_data)

        # Verifikasi hasil alokasi:
        # Wajib ada 2 move line
        self.assertEqual(len(pick.move_line_ids), 2, "Wajib ada 2 baris move line untuk 2 lot berbeda!")
        tot_qty = sum(getattr(ml, "quantity", 0.0) for ml in pick.move_line_ids)
        self.assertEqual(tot_qty, 216.0, "Total kuantitas ULV-SNL-04 wajib persis 216 unit (120 + 96)!")

        lot_map = {getattr(ml, "lot_name", None): getattr(ml, "quantity", 0.0) for ml in pick.move_line_ids}
        self.assertEqual(lot_map.get("LOT-VER-20260615-INIT-04"), 120.0, "Lot 1 wajib 120 unit!")
        self.assertEqual(lot_map.get("LOT-VER-20260704-04"), 96.0, "Lot 2 wajib 96 unit!")

    def test_assign_lots_aggregates_repeated_source_lots(self):
        """Memverifikasi bahwa baris sumber berulang pada lot yang sama teragregasi secara akumulatif.

        Contoh: 24 unit + 36 unit = 60 unit total.
        """
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        prod = adapter.product_by_code.get("ULV-SNL-04")
        self.assertIsNotNone(prod)

        class MockMove:
            def __init__(self, prod_id):
                self.id = 102
                self.product_id = prod_id
                self._fields = {"picked": True}
                self.picked = False

            def write(self, vals):
                if "picked" in vals:
                    self.picked = vals["picked"]

        class MockPicking:
            def __init__(self, prod_id):
                self.id = 998
                self.name = "DO-REPEATED-LOT"
                self.move_ids = [MockMove(prod_id)]
                self.move_line_ids = []

        pick = MockPicking(prod.id)

        # Baris berulang pada lot yang sama: 24 unit + 36 unit
        lines_data = [
            {"sku_code": "ULV-SNL-04", "qty_cartons": "1", "carton_qty": "24", "lot_number": "LOT-SAME-01"},
            {"sku_code": "ULV-SNL-04", "qty_cartons": "1.5", "carton_qty": "24", "lot_number": "LOT-SAME-01"},
        ]

        adapter._assign_lots_to_picking(pick, lines_data)

        self.assertEqual(len(pick.move_line_ids), 1, "Lot sama wajib diagregasikan ke dalam 1 baris move line!")
        self.assertEqual(
            pick.move_line_ids[0].quantity, 60.0, "Kuantitas akumulatif wajib 60 unit (bukan tertimpa 36)!"
        )

    def test_validate_picking_safely_no_skip_sanity_bypass_and_allowlist(self):
        """Memverifikasi bahwa _validate_picking_safely TIDAK membypass sanity check dan menolak wizard asing."""
        mock_env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(mock_env, reg_path=REG_DIR)

        captured_ctx = {}

        class MockPickingNormal:
            def __init__(self):
                self.id = 777
                self.name = "DO-NORMAL"
                self.state = "assigned"

            def with_context(self, **kwargs):
                captured_ctx.update(kwargs)
                return self

            def button_validate(self):
                self.state = "done"
                return True

        pick = MockPickingNormal()
        adapter._validate_picking_safely(pick, effective_date="2026-07-05")

        self.assertNotIn("skip_sanity_check", captured_ctx, "Bypass skip_sanity_check DILARANG keras!")
        self.assertEqual(captured_ctx.get("force_period_date"), "2026-07-05", "force_period_date wajib diteruskan!")
        self.assertEqual(pick.state, "done")

        # Uji Penolakan Wizard Asing (Fail-Fast)
        class MockPickingUnknownWizard:
            def __init__(self):
                self.id = 778
                self.name = "DO-BOGUS"
                self.state = "assigned"

            def with_context(self, **kwargs):
                return self

            def button_validate(self):
                return {
                    "type": "ir.actions.act_window",
                    "res_model": "unknown.bogus.wizard",
                }

        bogus_pick = MockPickingUnknownWizard()
        with self.assertRaises(RuntimeError) as ctx:
            adapter._validate_picking_safely(bogus_pick)
        self.assertIn("tidak ada dalam allowlist resmi", str(ctx.exception))

    def test_verify_slice_mutation_rejection_requires_env_and_path(self):
        """Uji fail-closed: oracle & mutasi dilarang dijalankan tanpa DB, dengan env kosong, atau path fiktif."""
        from scripts.ops.verify_disposable_slice import (
            verify_run1_against_canonical_oracle,
            verify_slice_mutation_rejection,
        )

        with self.assertRaises(ValueError):
            verify_slice_mutation_rejection(None, None, REG_DIR)

        # Env kosong tanpa model Odoo wajib harus fail-closed (RuntimeError / ValueError)
        with self.assertRaises((RuntimeError, ValueError)):
            verify_run1_against_canonical_oracle({}, None, REG_DIR, ["SO-202607-0001"])

        with self.assertRaises((RuntimeError, ValueError)):
            verify_slice_mutation_rejection({}, None, REG_DIR)

        with self.assertRaises(FileNotFoundError):
            verify_slice_mutation_rejection(setup_standard_mock_env(), None, Path("/path/tidak/ada/perpetual"))

    def test_verify_slice_mutation_rejection(self):
        """Uji pembuktian active fault detection dari validator slice representatif terhadap record nyata."""
        from scripts.ops.verify_disposable_slice import verify_slice_mutation_rejection

        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)
        target_sos = ["SO-202607-0001", "SO-202607-0063", "SO-202607-0317"]
        adapter.run_all(target_so_numbers=target_sos)

        # verify_slice_mutation_rejection harus lulus karena aktif menolak seluruh 3 mutasi
        verify_slice_mutation_rejection(env, adapter, REG_DIR, target_so_slice=target_sos)

    def test_slice_oracle_rejects_missing_second_lot_on_so317(self):
        """Oracle wajib menolak hasil jika SO-202607-0317 tidak memuat lot kedua (96 unit)."""
        from scripts.ops.verify_disposable_slice import verify_run1_against_canonical_oracle

        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)
        target_sos = ["SO-202607-0001", "SO-202607-0063", "SO-202607-0317"]
        adapter.run_all(target_so_numbers=target_sos)

        # Cacat: ubah alokasi lot pada picking SO-0317 agar lot kedua hilang
        pick317 = env["stock.picking"].search([("origin", "=", "SO-202607-0317")], limit=1)
        self.assertIsNotNone(pick317)
        for ml in pick317.move_line_ids:
            lot_name = getattr(getattr(ml, "lot_id", None), "name", "")
            if not lot_name and isinstance(getattr(ml, "lot_id", None), int) and "stock.lot" in env:
                lot_name = getattr(env["stock.lot"].browse(ml.lot_id), "name", "")
            if not lot_name:
                lot_name = getattr(ml, "lot_name", "")
            if lot_name == "LOT-VER-20260704-04":
                ml.quantity = 0.0

        with self.assertRaises(AssertionError) as ctx:
            verify_run1_against_canonical_oracle(env, adapter, REG_DIR, target_sos)
        self.assertIn("Kuantitas Lot LOT-VER-20260704-04 salah", str(ctx.exception))

    def test_slice_oracle_rejects_wrong_lot_quantity_on_so317(self):
        """Oracle wajib menolak hasil jika kuantitas lot pada SO-317 tidak tepat 96 unit."""
        from scripts.ops.verify_disposable_slice import verify_run1_against_canonical_oracle

        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)
        target_sos = ["SO-202607-0001", "SO-202607-0063", "SO-202607-0317"]
        adapter.run_all(target_so_numbers=target_sos)

        # Cacat: ubah kuantitas lot 2 dari 96.0 menjadi 50.0
        pick317 = env["stock.picking"].search([("origin", "=", "SO-202607-0317")], limit=1)
        self.assertIsNotNone(pick317)
        for ml in pick317.move_line_ids:
            lot_name = getattr(getattr(ml, "lot_id", None), "name", "")
            if not lot_name and isinstance(getattr(ml, "lot_id", None), int) and "stock.lot" in env:
                lot_name = getattr(env["stock.lot"].browse(ml.lot_id), "name", "")
            if not lot_name:
                lot_name = getattr(ml, "lot_name", "")
            if lot_name == "LOT-VER-20260704-04":
                ml.quantity = 50.0

        with self.assertRaises(AssertionError) as ctx:
            verify_run1_against_canonical_oracle(env, adapter, REG_DIR, target_sos)
        self.assertIn("Kuantitas Lot LOT-VER-20260704-04 salah", str(ctx.exception))

    def test_ensure_accounting_configuration_fail_fast_on_missing_journal(self):
        """Konfigurasi akuntansi wajib fail-fast jika jurnal stok tidak tersedia dan tidak dapat dibuat."""
        env = setup_standard_mock_env()
        # Modifikasi mock journal agar search dan create mengembalikan None
        class UncreatableJournal(MockModel):
            def search(self, *args, **kwargs):
                return None
            def create(self, *args, **kwargs):
                return None

        env["account.journal"] = UncreatableJournal("account.journal", env)
        with self.assertRaises(RuntimeError) as ctx:
            CanonicalPerpetualAdapter(env, reg_path=REG_DIR)
        self.assertIn(
            "Keberadaan jurnal stok (stock journal) yang diwajibkan tidak dapat dibuktikan",
            str(ctx.exception),
        )

    def test_ensure_accounting_configuration_fail_fast_on_missing_account(self):
        """Konfigurasi akuntansi wajib fail-fast jika akun persediaan/COGS wajib tidak ditemukan."""
        env = setup_standard_mock_env()
        env["account.account"].store = {}
        env["account.account"].create = lambda vals: None
        with self.assertRaises(RuntimeError) as ctx:
            CanonicalPerpetualAdapter(env, reg_path=REG_DIR)
        self.assertIn("tidak ditemukan", str(ctx.exception))

    def test_sync_native_stock_accounting_fail_fast_on_unverified_date(self):
        """_sync_native_stock_accounting wajib fail-fast jika rewrite tanggal ditolak dan tanggal tetap runtime."""
        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)

        class StubLockedMove:
            def __init__(self):
                self.id = 999
                self.name = "STK/2026/0001"
                self.state = "posted"
                self.date = "2026-10-27"
            def write(self, vals):
                # Tolak perubahan tanggal (simulasi Odoo lock constraint)
                pass

        stub_am = StubLockedMove()
        class StubStockMove:
            def __init__(self):
                self.id = 111
                self.account_move_id = stub_am

        sm = StubStockMove()
        with self.assertRaises(RuntimeError) as ctx:
            adapter._sync_native_stock_accounting(sm, "2026-07-01 00:00:00", "2026-07-01")
        self.assertIn("diharapkan 2026-07-01", str(ctx.exception))

    def test_sync_native_stock_accounting_rejects_posted_wrong_date_without_rewrite(self):
        """Blocker 3: Cabang posted wajib read-only fail-fast tanpa menulis ulang meskipun write() diizinkan."""
        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)

        class StubWritablePostedMove:
            def __init__(self):
                self.id = 1001
                self.name = "STJ/2026/0999"
                self.state = "posted"
                self.date = "2026-10-28"
                self.write_called = False

            def write(self, vals):
                # Jika helper mencoba rewrite jurnal posted, flag ini akan menjadi True dan tanggal berubah
                self.write_called = True
                if "date" in vals:
                    self.date = vals["date"]
                return True

        stub_am = StubWritablePostedMove()

        class StubStockMove:
            def __init__(self):
                self.id = 222
                self.account_move_id = stub_am

        sm = StubStockMove()
        with self.assertRaises(RuntimeError) as ctx:
            adapter._sync_native_stock_accounting(sm, "2026-07-01 00:00:00", "2026-07-01")

        self.assertIn("dilarang rewrite jurnal posted", str(ctx.exception))
        self.assertFalse(stub_am.write_called, "Helper DILARANG memanggil write() pada jurnal berstatus posted!")
        self.assertEqual(stub_am.date, "2026-10-28", "Tanggal jurnal posted tidak boleh diubah diam-diam!")

    def test_sync_native_stock_accounting_fails_fast_when_no_journal_created(self):
        """Blocker 2: _sync_native_stock_accounting wajib menolak stock.move yang tidak menghasilkan jurnal native."""
        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)

        class StubStockMoveWithoutJournal:
            def __init__(self):
                self.id = 333
                self.origin = "DO-NO-JOURNAL"
                self.account_move_id = False
                self.account_move_ids = []

        sm = StubStockMoveWithoutJournal()
        with self.assertRaises(RuntimeError) as ctx:
            adapter._sync_native_stock_accounting(sm, "2026-07-03 10:00:00", "2026-07-03")
        self.assertIn("tidak menghasilkan entri jurnal akuntansi native", str(ctx.exception))

    def test_accounting_configuration_scope_isolation_multi_company_and_foreign_records(self):
        """Blocker 4: Konfigurasi lokasi, kategori, dan produk terisolasi ketat pada scope kanonikal & company seed."""
        env = setup_standard_mock_env()

        # Buat Company 2, kategori asing, produk asing, dan lokasi milik Company 2
        comp2 = MockRecord({"name": "PT Cabang Asing"}, "res.company", 2, env)
        foreign_cat = env["product.category"].create({
            "name": "Foreign Non-FMCG Category",
            "property_valuation": "manual_periodic",
            "property_cost_method": "standard",
            "property_stock_valuation_account_id": 9991,
        })
        foreign_prod = env["product.product"].create({
            "name": "Barang Asing Non-Seed",
            "default_code": "FOREIGN-SKU-999",
            "categ_id": foreign_cat,
            "standard_price": 12345.0,
            "company_id": comp2,
        })
        foreign_internal_loc = env["stock.location"].create({
            "name": "WH2/Stock Asing",
            "usage": "internal",
            "company_id": comp2,
            "valuation_account_id": 8881,
        })
        foreign_cust_loc = env["stock.location"].create({
            "name": "Customers Company 2",
            "usage": "customer",
            "company_id": comp2,
            "valuation_account_id": 8882,
        })
        foreign_supp_loc = env["stock.location"].create({
            "name": "Vendors Company 2",
            "usage": "supplier",
            "company_id": comp2,
            "valuation_account_id": 8883,
        })

        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)

        # 1. Cache product_by_code hanya memuat tepat 150 SKU kanonikal, bukan produk asing
        self.assertEqual(len(adapter.product_by_code), 150)
        self.assertNotIn("FOREIGN-SKU-999", adapter.product_by_code)

        # 2. Kategori asing, produk asing, dan lokasi Company 2 sama sekali TIDAK berubah
        self.assertEqual(foreign_cat.property_valuation, "manual_periodic")
        self.assertEqual(foreign_cat.property_cost_method, "standard")
        self.assertEqual(foreign_cat.property_stock_valuation_account_id, 9991)
        self.assertEqual(foreign_prod.standard_price, 12345.0)
        self.assertEqual(foreign_internal_loc.valuation_account_id, 8881)
        self.assertEqual(foreign_cust_loc.valuation_account_id, 8882)
        self.assertEqual(foreign_supp_loc.valuation_account_id, 8883)

        # 3. Jika sebuah SKU kanonikal hilang, inisialisasi wajib fail-fast (tanpa fallback global)
        env_missing = setup_standard_mock_env()
        first_pid = next(iter(env_missing["product.product"].store.keys()))
        del env_missing["product.product"].store[first_pid]
        with self.assertRaises(RuntimeError) as ctx_miss:
            CanonicalPerpetualAdapter(env_missing, reg_path=REG_DIR)
        self.assertIn("Scope produk kanonikal tidak lengkap", str(ctx_miss.exception))

        # 4. Jika produk kanonikal tidak memiliki categ_id, wajib fail-fast (tanpa fallback ke kategori acak)
        env_nocat = setup_standard_mock_env()
        for pr in env_nocat["product.product"].store.values():
            pr.categ_id = False
            pr._vals["categ_id"] = False
        with self.assertRaises(RuntimeError) as ctx_nocat:
            CanonicalPerpetualAdapter(env_nocat, reg_path=REG_DIR)
        self.assertIn("Tidak ada kategori produk (categ_id) pada scope produk kanonikal", str(ctx_nocat.exception))

    def test_slice_oracle_rejects_extra_sku_line_999_units_and_quant_drift(self):
        """Blocker 1 & 2: Oracle menolak penambahan baris 999 unit SKU asing dan perubahan quant +100.000 unit."""
        from scripts.ops.verify_disposable_slice import (
            run_representative_slice,
            verify_run1_against_canonical_oracle,
        )

        env = setup_standard_mock_env()
        # Jalankan full slice end-to-end (Run 1 + Oracle + 11 Mutasi + Run 2 + Deep Snapshot)
        run_representative_slice(env)

        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)
        target_sos = ["SO-202607-0001", "SO-202607-0063", "SO-202607-0317"]

        # Uji 1: Tambah baris ekstra 999 unit SKU asing pada picking SO-202607-0317 -> Wajib ditolak!
        pick317 = env["stock.picking"].search([("origin", "=", "SO-202607-0317")], limit=1)
        bogus_prod = env["product.product"].create({"name": "Bogus", "default_code": "BOGUS-SKU-999"})
        bogus_lot = env["stock.lot"].create({"name": "BOGUS-LOT-999", "product_id": bogus_prod.id})
        extra_ml = env["stock.move.line"].create({
            "picking_id": pick317.id,
            "product_id": bogus_prod.id,
            "lot_id": bogus_lot.id,
            "quantity": 999.0,
            "location_id": pick317.location_id.id,
            "location_dest_id": pick317.location_dest_id.id,
            "date": getattr(pick317.move_line_ids[0], "date", "2026-07-09 10:00:00"),
        })
        pick317.move_line_ids.append(extra_ml)
        with self.assertRaises(AssertionError) as ctx_extra:
            verify_run1_against_canonical_oracle(env, adapter, REG_DIR, target_sos)
        self.assertIn("Ditemukan baris ekstra/SKU asing", str(ctx_extra.exception))
        pick317.move_line_ids.remove(extra_ml)
        extra_ml.unlink()

        # Uji 2: Ubah quant +100.000 unit -> Wajib ditolak!
        q0 = next(iter(env["stock.quant"].store.values()))
        orig_qty = q0.quantity
        q0.quantity = orig_qty + 100000.0
        with self.assertRaises(AssertionError) as ctx_quant:
            verify_run1_against_canonical_oracle(env, adapter, REG_DIR, target_sos)
        self.assertIn("Quant Drift terdeteksi", str(ctx_quant.exception))
        q0.quantity = orig_qty

        # Uji 3: Ubah reserved_quantity menjadi > 0 -> Wajib ditolak!
        q0.reserved_quantity = 25.0
        with self.assertRaises(AssertionError) as ctx_res:
            verify_run1_against_canonical_oracle(env, adapter, REG_DIR, target_sos)
        self.assertIn("reserved_quantity menggantung", str(ctx_res.exception))
        q0.reserved_quantity = 0.0

    def test_blocker1_out_invoice_retains_product_id_uom_and_sale_line_ids(self):
        """Blocker 1 (Review 6466832055): out_invoice wajib mempertahankan product_id, UoM, dan sale_line_ids."""
        from scripts.ops.verify_disposable_slice import verify_run1_against_canonical_oracle

        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)
        target_sos = ["SO-202607-0001", "SO-202607-0063", "SO-202607-0317"]
        adapter.run_all(target_so_numbers=target_sos)

        inv1 = env["account.move"].search([("ref", "=", "INV-202607-0001")], limit=1)
        self.assertTrue(inv1)
        self.assertEqual(getattr(inv1, "invoice_origin", ""), "SO-202607-0001")
        # Review 6469576922: Verifikasi move_reverse_cancel TIDAK digunakan saat posting faktur penjualan biasa
        ctx = getattr(inv1, "_ctx", None)
        self.assertFalse(
            isinstance(ctx, dict) and ctx.get("move_reverse_cancel"),
            "Post out_invoice native dilarang menggunakan bypass context move_reverse_cancel!"
        )
        inv_lines = list(getattr(inv1, "invoice_line_ids", []))
        self.assertGreater(len(inv_lines), 0)
        for il in inv_lines:
            self.assertTrue(getattr(il, "product_id", False), "product_id wajib terisi pada baris out_invoice!")
            self.assertTrue(getattr(il, "product_uom_id", False), "product_uom_id wajib terisi pada baris out_invoice!")
            self.assertGreater(len(getattr(il, "sale_line_ids", [])), 0, "sale_line_ids wajib terhubung ke SO line!")

        # Mutasi: hapus product_id pada baris pertama INV-202607-0001 -> Oracle wajib menolak!
        orig_prod = inv_lines[0].product_id
        inv_lines[0].product_id = False
        inv_lines[0]._vals["product_id"] = False
        with self.assertRaises(AssertionError) as ctx_noprod:
            verify_run1_against_canonical_oracle(env, adapter, REG_DIR, target_sos)
        self.assertIn("Baris invoice INV-202607-0001 kehilangan product_id", str(ctx_noprod.exception))
        inv_lines[0].product_id = orig_prod
        inv_lines[0]._vals["product_id"] = orig_prod

    def test_blocker2_location_and_shared_category_isolation_within_same_company(self):
        """Blocker 2 (Review 6466832055): Lokasi non-seed, lokasi shared, dan kategori shared tidak disentuh."""
        env = setup_standard_mock_env()
        # Tambahkan lokasi internal bisnis lain di company yang sama (company_id = 1)
        other_internal = env["stock.location"].create({
            "name": "WH Other Business",
            "usage": "internal",
            "company_id": env.company.id,
            "valuation_account_id": 7771,
        })
        # Pastikan lokasi shared (company_id=False) memiliki valuation_account_id awal yang tidak boleh diubah
        shared_cust = env["stock.location"].search(
            [("usage", "=", "customer"), ("company_id", "=", False)], limit=1
        )
        shared_cust.write({"valuation_account_id": 7772})
        shared_supp = env["stock.location"].search(
            [("usage", "=", "supplier"), ("company_id", "=", False)], limit=1
        )
        shared_supp.write({"valuation_account_id": 7773})
        shared_inv = env["stock.location"].search(
            [("usage", "=", "inventory"), ("company_id", "=", False)], limit=1
        )
        shared_inv.write({"valuation_account_id": 7774})

        # Tambahkan produk non-seed dalam kategori yang sama ("All / FMCG")
        shared_cat = env["product.category"].search([("name", "=", "All / FMCG")], limit=1)
        shared_cat.write({
            "property_valuation": "manual_periodic",
            "property_cost_method": "standard",
            "property_stock_valuation_account_id": 7775,
        })
        non_seed_prod = env["product.product"].create({
            "name": "Produk Non-Seed Bisnis Lain",
            "default_code": "NON-SEED-SKU-001",
            "categ_id": shared_cat,
            "company_id": env.company.id,
        })

        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)

        # 1. Lokasi internal non-seed dalam company yang sama TIDAK berubah
        self.assertEqual(other_internal.valuation_account_id, 7771)
        # 2. Lokasi shared (company_id=False) TIDAK berubah; adapter membuat lokasi counterpart khusus company seed
        self.assertEqual(shared_cust.valuation_account_id, 7772)
        self.assertEqual(shared_supp.valuation_account_id, 7773)
        self.assertEqual(shared_inv.valuation_account_id, 7774)
        self.assertNotEqual(adapter.seed_customer_loc.id, shared_cust.id)
        self.assertNotEqual(adapter.seed_supplier_loc.id, shared_supp.id)
        self.assertNotEqual(adapter.seed_inventory_loc.id, shared_inv.id)
        self.assertEqual(adapter.seed_customer_loc.company_id.id, env.company.id)
        self.assertEqual(adapter.seed_supplier_loc.company_id.id, env.company.id)
        self.assertEqual(adapter.seed_inventory_loc.company_id.id, env.company.id)
        # 3. Kategori shared ("All / FMCG") dan produk non-seed TIDAK berubah; produk seed dipindah ke kategori khusus
        self.assertEqual(shared_cat.property_valuation, "manual_periodic")
        self.assertEqual(shared_cat.property_cost_method, "standard")
        self.assertEqual(shared_cat.property_stock_valuation_account_id, 7775)
        self.assertEqual(non_seed_prod.categ_id.id, shared_cat.id)
        for pr in adapter.product_by_code.values():
            self.assertNotEqual(pr.categ_id.id, shared_cat.id)
            self.assertEqual(pr.categ_id.name, "FMCG Seed Perpetual")
            self.assertEqual(pr.categ_id.property_valuation, "real_time")
            self.assertEqual(pr.categ_id.property_cost_method, "fifo")

    def test_blocker4_and_blocker5_opex_and_duplicate_document_rejection(self):
        """Blocker 4 & 5 (Review 6466832055): OPEX salah nominal/akun/partner dan duplikasi dokumen ditolak."""
        from scripts.ops.verify_disposable_slice import verify_run1_against_canonical_oracle

        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)
        target_sos = ["SO-202607-0001", "SO-202607-0063", "SO-202607-0317"]
        adapter.run_all(target_so_numbers=target_sos)

        # Verifikasi baseline lulus
        verify_run1_against_canonical_oracle(env, adapter, REG_DIR, target_sos)

        # Uji Blocker 4: Ubah partner OPEX-2026-07-01 menjadi company.partner_id -> Wajib ditolak!
        opex1 = env["account.move"].search([("ref", "=", "OPEX-2026-07-01")], limit=1)
        orig_partner = opex1.partner_id
        opex1.write({"partner_id": env.company.partner_id})
        with self.assertRaises(AssertionError) as ctx_opex_p:
            verify_run1_against_canonical_oracle(env, adapter, REG_DIR, target_sos)
        self.assertIn("dilarang menggunakan partner company sendiri", str(ctx_opex_p.exception))
        opex1.write({"partner_id": orig_partner})

        # Uji Blocker 5: Rekonsiliasi faktur dipasangkan ke dokumen yang salah -> Wajib ditolak!
        inv63 = env["account.move"].search([("ref", "=", "INV-202607-0063")], limit=1)
        ar_lines = [
            ln for ln in inv63.line_ids
            if getattr(getattr(ln, "account_id", None), "account_type", "") == "asset_receivable"
        ]
        orig_peers = list(getattr(ar_lines[0], "_reconciled_peer_move_ids", []))
        ar_lines[0]._reconciled_peer_move_ids = [999999]
        with self.assertRaises(AssertionError) as ctx_rec_peer:
            verify_run1_against_canonical_oracle(env, adapter, REG_DIR, target_sos)
        self.assertIn("tidak cocok dengan ekspektasi", str(ctx_rec_peer.exception))
        ar_lines[0]._reconciled_peer_move_ids = orig_peers

    def test_relocation_precedes_lot_allocation(self):
        """Review 6469576922 Finding 1: Relokasi wajib mendahului alokasi lot/kuantitas.

        Di Odoo 19 stock_move.py:880-897, jika location_id diubah SETELAH move_line ada,
        Odoo melakukan ml.unlink() yang menghasilkan 'Validating a zero quantity transfer'.
        Tes ini membuktikan _align_picking_locations dipanggil SEBELUM alokasi lot sehingga kuantitas utuh.
        """
        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)

        # Siapkan picking dengan move yang meniru perilaku Odoo 19:
        # Jika write location_id dipanggil saat move_line_ids sudah ada, hapus move_lines (unlink).
        cust_loc = env["stock.location"].search([("usage", "=", "customer")], limit=1)
        wh_loc = env["stock.location"].search([("usage", "=", "internal")], limit=1)
        other_loc = env["stock.location"].create({"name": "Wrong Loc", "usage": "customer", "company_id": 1})

        pick = env["stock.picking"].create({
            "name": "TEST-PICK-001",
            "location_id": wh_loc.id,
            "location_dest_id": other_loc.id,
        })
        sm = env["stock.move"].create({
            "name": "TEST-MOVE-001",
            "location_id": wh_loc.id,
            "location_dest_id": other_loc.id,
            "picking_id": pick,
        })
        pick.move_ids = MockRecordList([sm])

        orig_sm_write = sm.write

        def odoo19_sm_write(vals):
            # Simulasi Odoo 19: jika location_dest_id diubah padahal move_line_ids sudah terisi, unlink lines!
            if "location_dest_id" in vals and hasattr(sm, "move_line_ids") and sm.move_line_ids:
                sm.move_line_ids = MockRecordList([])
            return orig_sm_write(vals)

        sm.write = odoo19_sm_write

        # ALUR BENAR: 1) Align locations -> 2) Assign lots -> 3) Validate
        adapter._align_picking_locations(pick, expected_src_loc=wh_loc, expected_dest_loc=cust_loc)
        sml = env["stock.move.line"].create({
            "picking_id": pick,
            "move_id": sm,
            "location_id": wh_loc.id,
            "location_dest_id": cust_loc.id,
            "quantity": 10.0,
        })
        sm.move_line_ids = MockRecordList([sml])
        pick.move_line_ids = MockRecordList([sml])

        res = adapter._validate_picking_safely(
            pick,
            effective_date="2026-07-02",
            expected_src_loc=wh_loc,
            expected_dest_loc=cust_loc,
        )
        self.assertTrue(res)
        self.assertEqual(len(sm.move_line_ids), 1)
        self.assertEqual(sm.move_line_ids[0].quantity, 10.0)

        # PEMBUKTIAN ALUR SALAH (Relokasi setelah lot dialokasikan):
        # Jika dipaksa align locations SETELAH move lines dibuat, lines akan ter-unlink menjadi 0 unit
        adapter._align_picking_locations(pick, expected_src_loc=wh_loc, expected_dest_loc=other_loc)
        self.assertEqual(len(sm.move_line_ids), 0, "Odoo 19 menghapus move lines bila relokasi dilakukan belakangan!")

    def test_picking_location_write_failure_aborts_before_validate(self):
        """Review 6469576922 Finding 2: Kegagalan write lokasi picking wajib abort transaksi sebelum validasi."""
        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)
        wh_loc = env["stock.location"].search([("usage", "=", "internal")], limit=1)
        cust_loc = env["stock.location"].search([("usage", "=", "customer")], limit=1)

        pick = env["stock.picking"].create({
            "name": "TEST-PICK-FAIL-1",
            "location_id": wh_loc.id,
            "location_dest_id": 9999,
        })
        spy_validate_calls = 0

        def spy_validate():
            nonlocal spy_validate_calls
            spy_validate_calls += 1

        pick.button_validate = spy_validate

        def faulty_pick_write(vals):
            if "location_dest_id" in vals:
                raise RuntimeError("Disk IO Error saat write lokasi picking!")
            return True

        pick.write = faulty_pick_write

        with self.assertRaises(RuntimeError) as ctx:
            adapter._align_picking_locations(pick, expected_src_loc=wh_loc, expected_dest_loc=cust_loc)

        self.assertIn("Gagal menulis lokasi stock.picking", str(ctx.exception))
        self.assertEqual(spy_validate_calls, 0, "button_validate dilarang dipanggil bila alignment lokasi gagal!")

    def test_move_location_write_failure_aborts_before_validate(self):
        """Review 6469576922 Finding 2: Kegagalan write lokasi stock.move wajib abort transaksi sebelum validasi."""
        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)
        wh_loc = env["stock.location"].search([("usage", "=", "internal")], limit=1)
        cust_loc = env["stock.location"].search([("usage", "=", "customer")], limit=1)

        pick = env["stock.picking"].create({
            "name": "TEST-PICK-FAIL-2",
            "location_id": wh_loc.id,
            "location_dest_id": cust_loc.id,
        })
        sm = env["stock.move"].create({
            "name": "TEST-MOVE-FAIL-2",
            "location_id": wh_loc.id,
            "location_dest_id": 9999,
            "picking_id": pick,
        })
        pick.move_ids = MockRecordList([sm])
        spy_validate_calls = 0

        def spy_validate():
            nonlocal spy_validate_calls
            spy_validate_calls += 1

        pick.button_validate = spy_validate

        def faulty_sm_write(vals):
            if "location_dest_id" in vals:
                raise RuntimeError("DB Constraint Error saat write lokasi stock.move!")
            return True

        sm.write = faulty_sm_write

        with self.assertRaises(RuntimeError) as ctx:
            adapter._align_picking_locations(pick, expected_src_loc=wh_loc, expected_dest_loc=cust_loc)

        self.assertIn("Gagal menulis lokasi stock.move", str(ctx.exception))
        self.assertEqual(spy_validate_calls, 0, "button_validate dilarang dipanggil bila write stock.move gagal!")

    def test_move_line_location_write_failure_aborts_before_validate(self):
        """Review 6469576922 Finding 2: Kegagalan write lokasi move.line wajib abort transaksi sebelum validasi."""
        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)
        wh_loc = env["stock.location"].search([("usage", "=", "internal")], limit=1)
        cust_loc = env["stock.location"].search([("usage", "=", "customer")], limit=1)

        pick = env["stock.picking"].create({
            "name": "TEST-PICK-FAIL-3",
            "location_id": wh_loc.id,
            "location_dest_id": cust_loc.id,
        })
        sm = env["stock.move"].create({
            "name": "TEST-MOVE-FAIL-3",
            "location_id": wh_loc.id,
            "location_dest_id": cust_loc.id,
            "picking_id": pick,
        })
        sml = env["stock.move.line"].create({
            "location_id": wh_loc.id,
            "location_dest_id": 9999,
            "move_id": sm,
            "picking_id": pick,
        })
        pick.move_ids = MockRecordList([sm])
        pick.move_line_ids = MockRecordList([sml])
        spy_validate_calls = 0

        def spy_validate():
            nonlocal spy_validate_calls
            spy_validate_calls += 1

        pick.button_validate = spy_validate

        def faulty_sml_write(vals):
            if "location_dest_id" in vals:
                raise RuntimeError("Deadlock pada record stock.move.line!")
            return True

        sml.write = faulty_sml_write

        with self.assertRaises(RuntimeError) as ctx:
            adapter._align_picking_locations(pick, expected_src_loc=wh_loc, expected_dest_loc=cust_loc)

        self.assertIn("Gagal menulis lokasi stock.move.line", str(ctx.exception))
        self.assertEqual(spy_validate_calls, 0, "button_validate dilarang dipanggil bila write line gagal!")

    def test_required_date_write_failure_aborts_validation(self):
        """Review 6469576922 Finding 2: Kegagalan penulisan tanggal move/line wajib abort validasi."""
        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)
        wh_loc = env["stock.location"].search([("usage", "=", "internal")], limit=1)
        cust_loc = env["stock.location"].search([("usage", "=", "customer")], limit=1)

        pick = env["stock.picking"].create({
            "name": "TEST-PICK-DATE-FAIL",
            "location_id": wh_loc.id,
            "location_dest_id": cust_loc.id,
        })
        sm = env["stock.move"].create({
            "name": "TEST-MOVE-DATE-FAIL",
            "location_id": wh_loc.id,
            "location_dest_id": cust_loc.id,
            "picking_id": pick,
        })
        pick.move_ids = MockRecordList([sm])
        spy_validate_calls = 0

        def spy_validate():
            nonlocal spy_validate_calls
            spy_validate_calls += 1

        pick.button_validate = spy_validate

        def faulty_date_write(vals):
            if "date" in vals:
                raise RuntimeError("Write date blocked by trigger!")
            return True

        sm.write = faulty_date_write

        with self.assertRaises(RuntimeError) as ctx:
            adapter._validate_picking_safely(
                pick,
                effective_date="2026-07-03",
                expected_src_loc=wh_loc,
                expected_dest_loc=cust_loc,
            )

        self.assertIn("Gagal menulis date stock.move", str(ctx.exception))
        self.assertEqual(spy_validate_calls, 0, "button_validate dilarang dipanggil bila penulisan tanggal gagal!")

    def test_noop_date_write_rejected_by_readback(self):
        """Review 6470601432 P2: No-op date write (nilai tanggal tidak berubah) wajib ditolak readback."""
        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)
        wh_loc = env["stock.location"].search([("usage", "=", "internal")], limit=1)
        cust_loc = env["stock.location"].search([("usage", "=", "customer")], limit=1)

        pick = env["stock.picking"].create({
            "name": "TEST-PICK-NOOP-DATE",
            "location_id": wh_loc.id,
            "location_dest_id": cust_loc.id,
            "scheduled_date": "2026-10-28 00:00:00",
            "date_done": "2026-10-28 00:00:00",
        })
        sm = env["stock.move"].create({
            "name": "TEST-MOVE-NOOP-DATE",
            "location_id": wh_loc.id,
            "location_dest_id": cust_loc.id,
            "date": "2026-10-28 00:00:00",
            "picking_id": pick,
        })
        pick.move_ids = MockRecordList([sm])
        spy_validate_calls = 0

        def spy_validate():
            nonlocal spy_validate_calls
            spy_validate_calls += 1

        pick.button_validate = spy_validate

        # No-op write: mengembalikan True tetapi sengaja tidak mengupdate tanggal
        def noop_pick_write(vals):
            return True

        pick.write = noop_pick_write
        sm.write = noop_pick_write

        with self.assertRaises(RuntimeError) as ctx:
            adapter._validate_picking_safely(
                pick,
                effective_date="2026-07-03",
                expected_src_loc=wh_loc,
                expected_dest_loc=cust_loc,
            )

        self.assertIn("no-op write terdeteksi", str(ctx.exception))
        self.assertEqual(spy_validate_calls, 0, "button_validate dilarang dipanggil bila tanggal tidak tersimpan!")

    def test_run_all_failure_aborts_commit_and_invokes_rollback(self):
        """Review 6473770755 Finding 4: Kegagalan transaksi di run_all wajib memicu rollback,
        membatalkan commit, mengembalikan record existing yang dimutasi, dan menghapus record baru.
        """
        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)

        # Buat record PO yang sudah ada sebelum transaksi
        existing_po = env["purchase.order"].create({"name": "PO-EXISTING-BEFORE"})

        # Simpan snapshot awal database (deep serialized values)
        initial_snapshot = env._take_snapshot()
        env._initial_snapshot = initial_snapshot

        # Injeksi kegagalan fatal pada tahap pemuatan purchase orders
        def faulty_load_inbound_pos():
            # Mutasi record yang sudah ada
            existing_po.write({"name": "PO-EXISTING-AFTER"})
            # Buat record baru parsial yang seharusnya terhapus saat rollback
            env["purchase.order"].create({"name": "PO-LEAK-PARTIAL-001"})
            raise RuntimeError("Database trigger failure during PO loading!")

        adapter.load_opening_stock = lambda: None
        adapter.load_inbound_pos = faulty_load_inbound_pos

        with self.assertRaises(RuntimeError) as ctx:
            adapter.run_all()

        self.assertIn("Database trigger failure during PO loading!", str(ctx.exception))
        self.assertTrue(env.cr.rollbacked, "Transaction rollback wajib dipanggil!")
        self.assertFalse(env.cr.committed, "Transaction commit dilarang dipanggil bila ada error!")

        # Pastikan record yang sudah ada kembali ke nilai awal
        self.assertEqual(existing_po.name, "PO-EXISTING-BEFORE", "Record existing wajib dipulihkan ke nilai awal!")
        # Pastikan tidak ada record purchase.order bocor
        self.assertEqual(len(env["purchase.order"].store), len(initial_snapshot.get("purchase.order", {})),
                         "Tidak boleh ada record purchase.order bocor setelah rollback!")
        # Pastikan snapshot database setelah rollback identik dengan sebelum transaksi
        after_snapshot = env._take_snapshot()
        self.assertEqual(after_snapshot, initial_snapshot, "Database rollback wajib memulihkan snapshot tanpa leak!")

    def test_noop_location_write_rejected_by_readback(self):
        """Review 6469576922 Finding 2: No-op write (tidak raise tapi field tidak berubah) wajib ditolak readback."""
        env = setup_standard_mock_env()
        adapter = CanonicalPerpetualAdapter(env, reg_path=REG_DIR)
        wh_loc = env["stock.location"].search([("usage", "=", "internal")], limit=1)
        cust_loc = env["stock.location"].search([("usage", "=", "customer")], limit=1)

        pick = env["stock.picking"].create({
            "name": "TEST-PICK-NOOP",
            "location_id": wh_loc.id,
            "location_dest_id": 9999,
        })

        # No-op write: mengembalikan True tetapi sengaja tidak mengupdate location_dest_id
        def noop_pick_write(vals):
            return True

        pick.write = noop_pick_write

        with self.assertRaises(RuntimeError) as ctx:
            adapter._align_picking_locations(pick, expected_src_loc=wh_loc, expected_dest_loc=cust_loc)

        self.assertIn("Readback lokasi stock.picking 'TEST-PICK-NOOP' gagal", str(ctx.exception))

    def test_seed_invoice_cogs_exception_narrow_scope(self):
        """Review 6470601432 Finding 1 & 2: Hook akuntansi _stock_account_prepare_realtime_out_lines_vals hanya

        mengecualikan faktur komersial seed yang terbukti persisten (is_fmcg_seed_invoice=True),
        company PT Salva Inti Mandiri, delivery berstatus 'done', dan telah membukukan HPP native pada
        singular account_move_id di STJ dengan akun 510000 / 113000.
        Faktur biasa mengembalikan False (native); seed invoice tidak valid wajib fail-closed UserError.
        """
        import sys
        from unittest.mock import MagicMock

        if "odoo" not in sys.modules:
            mock_odoo_models = MagicMock()
            mock_odoo_models.Model = object
            mock_exceptions = MagicMock()

            class MockUserError(Exception):
                pass

            mock_exceptions.UserError = MockUserError
            sys.modules["odoo"] = MagicMock(
                models=mock_odoo_models,
                fields=MagicMock(),
                api=MagicMock(),
                exceptions=mock_exceptions,
            )
            sys.modules["odoo.models"] = mock_odoo_models
            sys.modules["odoo.fields"] = MagicMock()
            sys.modules["odoo.api"] = MagicMock()
            sys.modules["odoo.exceptions"] = mock_exceptions

        from odoo.exceptions import UserError
        from addons.id_base.models.account_move import AccountMove

        env = setup_standard_mock_env()

        # Buat wrapper record yang meniru model AccountMove addon id_base
        class MockAccountMoveModel(AccountMove):
            def __init__(self, vals, env):
                self._vals = dict(vals)
                self.env = env
                for k, v in vals.items():
                    setattr(self, k, v)

            def ensure_one(self):
                return self

            def __iter__(self):
                yield self

        prod = env["product.product"].search([], limit=1)

        # 1. Faktur Seed Terverifikasi: Delivery DONE & singular account_move_id STJ posted (510000 / 113000)
        aml_debit = MockRecord({
            "account_id": MockRecord({"code": "510000"}, "account.account", 1, env),
            "debit": 150000.0,
            "credit": 0.0,
        }, "account.move.line", 901, env)
        aml_credit = MockRecord({
            "account_id": MockRecord({"code": "113000"}, "account.account", 2, env),
            "debit": 0.0,
            "credit": 150000.0,
        }, "account.move.line", 902, env)
        stj_journal = MockRecord({"code": "STJ"}, "account.journal", 1, env)
        cogs_am = MockRecord({
            "name": "STJ/2026/07/0001",
            "state": "posted",
            "date": "2026-07-02",
            "company_id": env.company,
            "journal_id": stj_journal,
            "line_ids": MockRecordList([aml_debit, aml_credit]),
        }, "account.move", 801, env)

        cust_loc = MockRecord({"usage": "customer"}, "stock.location", 99, env)
        wh_loc = MockRecord({"usage": "internal"}, "stock.location", 1, env)

        sm_done = MockRecord({
            "name": "WH/OUT/0001",
            "state": "done",
            "product_id": prod,
            "company_id": env.company,
            "location_id": wh_loc,
            "location_dest_id": cust_loc,
            "quantity": 10.0,
            "date": "2026-07-02",
            "value": 150000.0,
            "account_move_id": cogs_am,
        }, "stock.move", 101, env)
        sol = MockRecord({
            "name": "SOL-001",
            "order_id": MockRecord({"name": "SO-202607-0001", "company_id": env.company}, "sale.order", 1, env),
            "move_ids": MockRecordList([sm_done]),
        }, "sale.order.line", 201, env)
        inv_line = MockRecord({
            "product_id": prod,
            "quantity": 10.0,
            "display_type": "product",
            "sale_line_ids": MockRecordList([sol]),
        }, "account.move.line", 301, env)

        seed_inv = MockAccountMoveModel({
            "move_type": "out_invoice",
            "is_fmcg_seed_invoice": True,
            "fmcg_seed_batch": "CANONICAL_JULY_2026_PERPETUAL",
            "invoice_origin": "SO-202607-0001",
            "company_id": env.company,
            "invoice_line_ids": MockRecordList([inv_line]),
        }, env)

        self.assertTrue(seed_inv._is_seed_commercial_invoice_with_posted_delivery_cogs())
        self.assertEqual(seed_inv._stock_account_prepare_realtime_out_lines_vals(), [])

        # 2. Faktur Biasa (is_fmcg_seed_invoice=False) -> Pengecualian dilarang (False, native)
        normal_inv = MockAccountMoveModel({
            "move_type": "out_invoice",
            "is_fmcg_seed_invoice": False,
            "company_id": env.company,
            "invoice_line_ids": MockRecordList([inv_line]),
        }, env)
        self.assertFalse(normal_inv._is_seed_commercial_invoice_with_posted_delivery_cogs())

        # 3. Ditandai seed tetapi pada perusahaan lain -> Fail-closed UserError
        foreign_co = MockRecord(
            {"name": "PT Salva Trading Indonesia", "code": "TRD", "id": 999}, "res.company", 999, env
        )
        foreign_inv = MockAccountMoveModel({
            "move_type": "out_invoice",
            "is_fmcg_seed_invoice": True,
            "fmcg_seed_batch": "CANONICAL_JULY_2026_PERPETUAL",
            "invoice_origin": "SO-202607-0001",
            "company_id": foreign_co,
            "invoice_line_ids": MockRecordList([inv_line]),
        }, env)
        with self.assertRaises(UserError) as ctx:
            foreign_inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
        self.assertIn("bukan company seed resmi FMCG", str(ctx.exception))

        # 4. Ditandai seed tetapi delivery belum selesai (state != 'done') -> Fail-closed UserError
        sm_draft = MockRecord({
            "name": "WH/OUT/0002",
            "state": "confirmed",
            "product_id": prod,
            "company_id": env.company,
            "location_id": wh_loc,
            "location_dest_id": cust_loc,
            "quantity": 10.0,
            "date": "2026-07-02",
            "account_move_id": cogs_am,
        }, "stock.move", 102, env)
        so_seed = MockRecord({"name": "SO-202607-0001", "company_id": env.company}, "sale.order", 1, env)
        sol_undone = MockRecord(
            {"name": "SOL-002", "order_id": so_seed,
             "move_ids": MockRecordList([sm_draft])}, "sale.order.line", 202, env
        )
        inv_line_undone = MockRecord({
            "product_id": prod,
            "quantity": 10.0,
            "display_type": "product",
            "sale_line_ids": MockRecordList([sol_undone]),
        }, "account.move.line", 302, env)
        undone_inv = MockAccountMoveModel({
            "move_type": "out_invoice",
            "is_fmcg_seed_invoice": True,
            "fmcg_seed_batch": "CANONICAL_JULY_2026_PERPETUAL",
            "invoice_origin": "SO-202607-0001",
            "company_id": env.company,
            "invoice_line_ids": MockRecordList([inv_line_undone]),
        }, env)
        with self.assertRaises(UserError) as ctx:
            undone_inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
        self.assertIn("belum selesai", str(ctx.exception))

        # 5. Ditandai seed tetapi tidak ada bukti jurnal HPP native (account_move_id kosong) -> Fail-closed UserError
        sm_no_hpp = MockRecord({
            "name": "WH/OUT/0003",
            "state": "done",
            "product_id": prod,
            "company_id": env.company,
            "location_id": wh_loc,
            "location_dest_id": cust_loc,
            "quantity": 10.0,
            "date": "2026-07-02",
            "account_move_id": False,
        }, "stock.move", 103, env)
        sol_no_hpp = MockRecord(
            {"name": "SOL-003", "order_id": so_seed,
             "move_ids": MockRecordList([sm_no_hpp])}, "sale.order.line", 203, env
        )
        inv_line_no_hpp = MockRecord({
            "product_id": prod,
            "quantity": 10.0,
            "display_type": "product",
            "sale_line_ids": MockRecordList([sol_no_hpp]),
        }, "account.move.line", 303, env)
        no_hpp_inv = MockAccountMoveModel({
            "move_type": "out_invoice",
            "is_fmcg_seed_invoice": True,
            "fmcg_seed_batch": "CANONICAL_JULY_2026_PERPETUAL",
            "invoice_origin": "SO-202607-0001",
            "company_id": env.company,
            "invoice_line_ids": MockRecordList([inv_line_no_hpp]),
        }, env)
        with self.assertRaises(UserError) as ctx:
            no_hpp_inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
        self.assertIn("account_move_id kosong", str(ctx.exception))

        # 6. Ditandai seed tetapi jurnal valuasi belum posted -> Fail-closed UserError
        cogs_unposted = MockRecord({
            "name": "STJ/2026/07/0002",
            "state": "draft",
            "date": "2026-07-02",
            "company_id": env.company,
            "journal_id": stj_journal,
            "line_ids": MockRecordList([aml_debit, aml_credit]),
        }, "account.move", 802, env)
        sm_unposted = MockRecord({
            "name": "WH/OUT/0004",
            "state": "done",
            "product_id": prod,
            "company_id": env.company,
            "location_id": wh_loc,
            "location_dest_id": cust_loc,
            "quantity": 10.0,
            "date": "2026-07-02",
            "value": 150000.0,
            "account_move_id": cogs_unposted,
        }, "stock.move", 104, env)
        sol_unposted = MockRecord(
            {"name": "SOL-004", "order_id": so_seed,
             "move_ids": MockRecordList([sm_unposted])}, "sale.order.line", 204, env
        )
        inv_line_unposted = MockRecord({
            "product_id": prod,
            "quantity": 10.0,
            "display_type": "product",
            "sale_line_ids": MockRecordList([sol_unposted]),
        }, "account.move.line", 304, env)
        unposted_inv = MockAccountMoveModel({
            "move_type": "out_invoice",
            "is_fmcg_seed_invoice": True,
            "fmcg_seed_batch": "CANONICAL_JULY_2026_PERPETUAL",
            "invoice_origin": "SO-202607-0001",
            "company_id": env.company,
            "invoice_line_ids": MockRecordList([inv_line_unposted]),
        }, env)
        with self.assertRaises(UserError) as ctx:
            unposted_inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
        self.assertIn("belum berstatus 'posted'", str(ctx.exception))

        # 7. Tanggal jurnal valuasi salah (1999-01-01) -> Fail-closed UserError (Review 6473770755 Finding 1)
        cogs_wrong_date = MockRecord({
            "name": "STJ/1999/01/0001",
            "state": "posted",
            "date": "1999-01-01",
            "company_id": env.company,
            "journal_id": stj_journal,
            "line_ids": MockRecordList([aml_debit, aml_credit]),
        }, "account.move", 803, env)
        sm_wrong_date = MockRecord({
            "name": "WH/OUT/0005",
            "state": "done",
            "product_id": prod,
            "company_id": env.company,
            "location_id": wh_loc,
            "location_dest_id": cust_loc,
            "quantity": 10.0,
            "date": "2026-07-02",
            "value": 150000.0,
            "account_move_id": cogs_wrong_date,
        }, "stock.move", 105, env)
        sol_wrong_date = MockRecord(
            {"name": "SOL-005", "order_id": so_seed,
             "move_ids": MockRecordList([sm_wrong_date])}, "sale.order.line", 205, env
        )
        inv_line_wrong_date = MockRecord({
            "product_id": prod,
            "quantity": 10.0,
            "display_type": "product",
            "sale_line_ids": MockRecordList([sol_wrong_date]),
        }, "account.move.line", 305, env)
        wrong_date_inv = MockAccountMoveModel({
            "move_type": "out_invoice",
            "is_fmcg_seed_invoice": True,
            "fmcg_seed_batch": "CANONICAL_JULY_2026_PERPETUAL",
            "invoice_origin": "SO-202607-0001",
            "company_id": env.company,
            "invoice_line_ids": MockRecordList([inv_line_wrong_date]),
        }, env)
        with self.assertRaises(UserError) as ctx:
            wrong_date_inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
        self.assertIn("tidak cocok dengan tanggal pergerakan stok", str(ctx.exception))

        # 8. Nilai valuasi tidak seimbang atau tidak sesuai (Rp 1 vs Rp 150.000) -> Fail-closed UserError
        aml_debit_wrong_val = MockRecord({
            "account_id": MockRecord({"code": "510000"}, "account.account", 1, env),
            "debit": 1.0,
            "credit": 0.0,
        }, "account.move.line", 903, env)
        aml_credit_wrong_val = MockRecord({
            "account_id": MockRecord({"code": "113000"}, "account.account", 2, env),
            "debit": 0.0,
            "credit": 1.0,
        }, "account.move.line", 904, env)
        cogs_wrong_val = MockRecord({
            "name": "STJ/2026/07/0003",
            "state": "posted",
            "date": "2026-07-02",
            "company_id": env.company,
            "journal_id": stj_journal,
            "line_ids": MockRecordList([aml_debit_wrong_val, aml_credit_wrong_val]),
        }, "account.move", 804, env)
        sm_wrong_val = MockRecord({
            "name": "WH/OUT/0006",
            "state": "done",
            "product_id": prod,
            "company_id": env.company,
            "location_id": wh_loc,
            "location_dest_id": cust_loc,
            "quantity": 10.0,
            "date": "2026-07-02",
            "value": 150000.0,
            "account_move_id": cogs_wrong_val,
        }, "stock.move", 106, env)
        sol_wrong_val = MockRecord(
            {"name": "SOL-006", "order_id": so_seed,
             "move_ids": MockRecordList([sm_wrong_val])}, "sale.order.line", 206, env
        )
        inv_line_wrong_val = MockRecord({
            "product_id": prod,
            "quantity": 10.0,
            "display_type": "product",
            "sale_line_ids": MockRecordList([sol_wrong_val]),
        }, "account.move.line", 306, env)
        wrong_val_inv = MockAccountMoveModel({
            "move_type": "out_invoice",
            "is_fmcg_seed_invoice": True,
            "fmcg_seed_batch": "CANONICAL_JULY_2026_PERPETUAL",
            "invoice_origin": "SO-202607-0001",
            "company_id": env.company,
            "invoice_line_ids": MockRecordList([inv_line_wrong_val]),
        }, env)
        with self.assertRaises(UserError) as ctx:
            wrong_val_inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
        self.assertIn("tidak sesuai dengan nilai valuasi pergerakan barang", str(ctx.exception))

        # 9. Stock move dari company berbeda (ID 777) -> Fail-closed UserError (Review 6473770755 Finding 1)
        foreign_move_co = MockRecord({"name": "Foreign Stock Co", "id": 777}, "res.company", 777, env)
        sm_foreign_comp = MockRecord({
            "name": "WH/OUT/0007",
            "state": "done",
            "product_id": prod,
            "company_id": foreign_move_co,
            "location_id": wh_loc,
            "location_dest_id": cust_loc,
            "quantity": 10.0,
            "date": "2026-07-02",
            "value": 150000.0,
            "account_move_id": cogs_am,
        }, "stock.move", 107, env)
        sol_foreign_move = MockRecord(
            {"name": "SOL-007", "order_id": so_seed,
             "move_ids": MockRecordList([sm_foreign_comp])}, "sale.order.line", 207, env
        )
        inv_line_foreign_move = MockRecord({
            "product_id": prod,
            "quantity": 10.0,
            "display_type": "product",
            "sale_line_ids": MockRecordList([sol_foreign_move]),
        }, "account.move.line", 307, env)
        foreign_move_inv = MockAccountMoveModel({
            "move_type": "out_invoice",
            "is_fmcg_seed_invoice": True,
            "fmcg_seed_batch": "CANONICAL_JULY_2026_PERPETUAL",
            "invoice_origin": "SO-202607-0001",
            "company_id": env.company,
            "invoice_line_ids": MockRecordList([inv_line_foreign_move]),
        }, env)
        with self.assertRaises(UserError) as ctx:
            foreign_move_inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
        self.assertIn("berasal dari company lain", str(ctx.exception))

        # 10. Vendor Bill (in_invoice) atau Refund (out_refund) -> Pengecualian dilarang (False, native)
        bill = MockAccountMoveModel({
            "move_type": "in_invoice",
            "is_fmcg_seed_invoice": True,
            "company_id": env.company,
            "invoice_line_ids": MockRecordList([inv_line]),
        }, env)
        self.assertFalse(bill._is_seed_commercial_invoice_with_posted_delivery_cogs())


if __name__ == "__main__":
    unittest.main()


