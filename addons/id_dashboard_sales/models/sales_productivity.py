"""Aggregation service for the Sales Productivity dashboard.

KPI definitions (source / formula / timezone / ACL), all read through the ORM so record rules apply:

* Period: Asia/Makassar (WITA) calendar day / ISO week / month, converted to UTC bounds.
* Gross revenue  = sum(price_subtotal + price_unit * qty * discount / 100) of confirmed SO lines (DPP, ex-tax).
* Discount given = sum(price_unit * qty * discount / 100) using the native line discount only.
* Net revenue    = sum(price_subtotal) of confirmed SO lines.
* DO delivered   = done outgoing pickings linked to a sale order, by ``date_done`` in the period.
* Lines per order (LPO) = distinct SKUs per confirmed SO, averaged over SOs. Target from system parameter.
* SKU penetration = distinct SKUs sold / saleable SKUs in the catalogue, per principal and per brand.
* Fulfillment-to-invoice = sum(line net * min(1, min(delivered, posted invoiced qty) / ordered qty))
  divided by sum(line net). Only POSTED invoice lines count (credit notes subtract).
* PJP compliance = planned (company, salesperson, WITA day, exact outlet) with an accepted check-in / planned.
  Assignment-bound photo evidence coverage is a separate quality metric. Effective call = accepted check-ins
  followed by a confirmed order at/after server check-in time for the same outlet/company/day / check-ins.
  Both are "unavailable" when the mobile
  models are not installed, not readable by the user, or hold no plan for the period. Nothing is estimated.
"""
import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError

TZ = ZoneInfo("Asia/Makassar")
MODES = ("day", "week", "month")
DEFAULT_PERIOD_MIN = "2026-07-01"
DEFAULT_PERIOD_MAX = "2026-10-31"
DEFAULT_LPO_TARGET = 4.0
MAX_ORDERS = 50000
CONFIRMED_STATES = ("sale", "done")


def _ratio(num, den):
    return (num / den) if den else None


def _to_utc(day):
    """Start of ``day`` in WITA as naive UTC datetime (Odoo storage format)."""
    return datetime.combine(day, time.min, tzinfo=TZ).astimezone(timezone.utc).replace(tzinfo=None)


def _local_date(value):
    """Naive UTC datetime -> WITA calendar date."""
    return value.replace(tzinfo=timezone.utc).astimezone(TZ).date()


def _bucket():
    return {"orders": set(), "lines": 0, "gross": 0.0, "discount": 0.0, "net": 0.0,
            "fulfilled": 0.0, "fulfillment_base": 0.0, "pickings": set(), "skus": set()}


class SalesProductivity(models.AbstractModel):
    _name = "id.sales.productivity"
    _description = "Sales Productivity Dashboard Service"

    # ------------------------------------------------------------------ helpers
    @api.model
    def _check_access(self):
        if not self.env.user.has_group("sales_team.group_sale_salesman"):
            raise AccessError(_("Sales dashboards require the Sales / User role."))

    @api.model
    def _param(self, key, default):
        return self.env["ir.config_parameter"].sudo().get_param(f"id_dashboard_sales.{key}", default)

    @api.model
    def _period(self, mode, anchor):
        if mode not in MODES:
            raise UserError(_("Unknown period mode."))
        try:
            day = date.fromisoformat(anchor)
        except (TypeError, ValueError) as exc:
            raise UserError(_("Invalid date.")) from exc
        if mode == "day":
            return day, day + timedelta(days=1)
        if mode == "week":
            start = day - timedelta(days=day.weekday())
            return start, start + timedelta(days=7)
        start = day.replace(day=1)
        nxt = (start + timedelta(days=32)).replace(day=1)
        return start, nxt

    @api.model
    def _parse_ids(self, values):
        return [int(v) for v in (values or []) if str(v).isdigit() or isinstance(v, int)]

    # ------------------------------------------------------------------ filters
    @api.model
    def get_filters(self):
        self._check_access()
        pmin = self._param("period_min", DEFAULT_PERIOD_MIN)
        pmax = self._param("period_max", DEFAULT_PERIOD_MAX)
        lo = _to_utc(date.fromisoformat(pmin))
        hi = _to_utc(date.fromisoformat(pmax) + timedelta(days=1))
        groups = self.env["sale.order"]._read_group(
            [("state", "in", CONFIRMED_STATES), ("date_order", ">=", lo), ("date_order", "<", hi),
             ("user_id", "!=", False)],
            ["user_id"], ["__count"])
        salesmen = sorted(({"id": user.id, "name": user.name} for user, _count in groups),
                          key=lambda s: s["name"])
        channels = self.env["id.channel"].search_read([], ["code", "name"], order="code")
        return {
            "salesmen": salesmen,
            "channels": [{"id": c["id"], "code": c["code"], "name": c["name"]} for c in channels],
            "period_min": pmin,
            "period_max": pmax,
            "lpo_target": float(self._param("lpo_target", DEFAULT_LPO_TARGET)),
        }

    # ------------------------------------------------------------------ main entry
    @api.model
    def get_data(self, mode="month", anchor=None, salesman_ids=None, channel_ids=None):
        self._check_access()
        salesman_ids, channel_ids = self._parse_ids(salesman_ids), self._parse_ids(channel_ids)
        data = self._compute(mode, anchor, salesman_ids, channel_ids)
        start = date.fromisoformat(data["period"]["start"])
        previous_anchor = (start - timedelta(days=1)).isoformat() if mode == "month" else (
            start - timedelta(days=1 if mode == "day" else 7)).isoformat()
        previous = self._compute(mode, previous_anchor, salesman_ids, channel_ids, light=True)
        data["previous"] = previous["total"]
        data["previous_period"] = previous["period"]
        current = set(data.pop("outlet_keys"))
        prior = set(previous.get("outlet_keys", []))
        data["outlet_activity"] = {"current": len(current), "previous": len(prior),
            "retained": len(current & prior), "entered": len(current - prior), "exited": len(prior - current),
            "retention": _ratio(len(current & prior), len(prior))}
        data["segment_targets"] = self._segment_targets(data["period"], data.pop("segment_amounts"),
                                                        salesman_ids or [], channel_ids or [])
        return data

    @api.model
    def _compute(self, mode, anchor, salesman_ids, channel_ids, light=False):
        anchor = anchor or self._param("period_min", DEFAULT_PERIOD_MIN)
        start, end = self._period(mode, anchor)
        lo, hi = _to_utc(start), _to_utc(end)
        salesman_ids = self._parse_ids(salesman_ids)
        channel_ids = self._parse_ids(channel_ids)
        company_ids = self.env.companies.ids
        if len(self.env.companies.currency_id) != 1:
            raise UserError(_("Select companies with the same currency before aggregating sales."))
        lpo_target = float(self._param("lpo_target", DEFAULT_LPO_TARGET))

        order_domain = [("state", "in", CONFIRMED_STATES), ("company_id", "in", company_ids),
                        ("date_order", ">=", lo), ("date_order", "<", hi)]
        picking_domain = [("picking_type_code", "=", "outgoing"), ("state", "=", "done"),
                          ("company_id", "in", company_ids), ("sale_id", "!=", False),
                          ("date_done", ">=", lo), ("date_done", "<", hi)]
        if salesman_ids:
            order_domain.append(("user_id", "in", salesman_ids))
            picking_domain.append(("sale_id.user_id", "in", salesman_ids))
        if channel_ids:
            order_domain.append(("partner_id.channel_id", "in", channel_ids))
            picking_domain.append(("sale_id.partner_id.channel_id", "in", channel_ids))

        Order = self.env["sale.order"]
        if Order.search_count(order_domain) > MAX_ORDERS:
            raise UserError(_("Too many orders for one query; narrow the period or filters."))
        orders = Order.search_fetch(order_domain, ["user_id", "partner_id", "date_order", "company_id", "currency_id"])
        order_info = {}
        for order in orders:
            partner = order.partner_id
            order_info[order.id] = (order.user_id.id, partner.channel_id.id,
                                    partner.id, _local_date(order.date_order), order.date_order, order.company_id.id)

        lines = self.env["sale.order.line"].search_fetch(
            [("order_id", "in", orders.ids), ("display_type", "=", False), ("product_id", "!=", False)],
            ["order_id", "product_id", "price_unit", "product_uom_qty", "discount", "price_subtotal",
             "qty_delivered", "product_uom_id"])
        invoiced = self._posted_invoiced_qty(lines)
        product_dims = {p.id: (p.principal_id.id, p.brand_id.id) for p in lines.product_id}

        keys_by_dim = {"salesman": defaultdict(_bucket), "channel": defaultdict(_bucket), "total": defaultdict(_bucket)}
        order_skus = defaultdict(set)
        dim_skus = {"salesman": defaultdict(lambda: {"principal": defaultdict(set), "brand": defaultdict(set)}),
                    "channel": defaultdict(lambda: {"principal": defaultdict(set), "brand": defaultdict(set)})}
        fx_cache = {}
        conversion = {o.id: self._conversion(o, fx_cache) for o in orders}
        segment_amounts = defaultdict(float)
        outlet_keys = {(o.company_id.id, o.partner_id.id) for o in orders}
        for order in orders:
            uid, channel, _outlet, _day, _at, _company = order_info[order.id]
            for dim, key in (("salesman", uid), ("channel", channel), ("total", 0)):
                keys_by_dim[dim][key]["orders"].add(order.id)
        for line in lines:
            qty = line.product_uom_qty
            oid = line.order_id.id
            user_id, channel_id, _outlet, _day, _time, company_id = order_info[oid]
            discount = line.price_unit * qty * line.discount / 100.0 * conversion[oid]
            net = line.price_subtotal * conversion[oid]
            done_qty = min(line.qty_delivered, invoiced.get(line.id, 0.0), qty) if qty > 0 else 0
            fulfilled = net * max(done_qty, 0.0) / qty if qty > 0 and net > 0 else 0.0
            pid = line.product_id.id
            if qty > 0:
                order_skus[oid].add(pid)
            principal_id, brand_id = product_dims[pid]
            for dimension, ident in (("salesman", user_id), ("channel", channel_id),
                                      ("area", line.order_id.partner_id.coverage_area_id.id),
                                      ("principal", principal_id)):
                segment_amounts[(company_id, dimension, ident)] += net
            for dim, key in (("salesman", user_id), ("channel", channel_id), ("total", 0)):
                b = keys_by_dim[dim][key]
                b["orders"].add(oid)
                b["lines"] += 1
                b["gross"] += net + discount
                b["discount"] += discount
                b["net"] += net
                b["fulfilled"] += fulfilled
                b["fulfillment_base"] += net if qty > 0 and net > 0 else 0.0
                if qty > 0:
                    b["skus"].add(pid)
                if dim != "total" and qty > 0:
                    dim_skus[dim][key]["principal"][principal_id].add(pid)
                    dim_skus[dim][key]["brand"][brand_id].add(pid)

        pickings = self.env["stock.picking"].search_fetch(picking_domain, ["sale_id"])
        for picking in pickings:
            sale = picking.sale_id
            channel_id = sale.partner_id.channel_id.id
            keys_by_dim["salesman"][sale.user_id.id]["pickings"].add(picking.id)
            keys_by_dim["channel"][channel_id]["pickings"].add(picking.id)
            keys_by_dim["total"][0]["pickings"].add(picking.id)

        def finish(b, key_name=None):
            n_orders = len(b["orders"])
            lpo_sum = sum(len(order_skus[o]) for o in b["orders"])
            lpo = _ratio(lpo_sum, n_orders)
            return {
                "orders": n_orders,
                "lines": b["lines"],
                "gross": b["gross"],
                "discount": b["discount"],
                "net": b["net"],
                "do_count": len(b["pickings"]),
                "lpo": lpo,
                "lpo_ok": None if lpo is None else lpo >= lpo_target,
                "sku_sold": len(b["skus"]),
                "fulfillment": _ratio(b["fulfilled"], b["fulfillment_base"]),
            }

        if light:
            return {"period": {"mode": mode, "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat()},
                    "total": finish(keys_by_dim["total"][0]), "outlet_keys": list(outlet_keys)}

        for ident in salesman_ids:
            keys_by_dim["salesman"][ident]
        for ident in channel_ids:
            keys_by_dim["channel"][ident]
        pjp = self._pjp(start, end, lo, hi, salesman_ids, channel_ids, order_info)
        catalog = self._catalog()

        def rows(dim, model, unknown):
            ids = [k for k in keys_by_dim[dim] if k] + [k for k in pjp["keys"][dim] if k and k not in keys_by_dim[dim]]
            names = {r.id: r.display_name for r in self.env[model].browse(ids).exists()}
            out = []
            for key in sorted(set(keys_by_dim[dim]) | set(pjp["keys"][dim]), key=lambda k: names.get(k, "~")):
                row = finish(keys_by_dim[dim][key]) if key in keys_by_dim[dim] else finish(_bucket())
                row.update({"id": key, "name": names.get(key, unknown), "pjp": pjp["by"][dim].get(key)})
                out.append(row)
            return out

        salesman_rows = rows("salesman", "res.users", _("(No salesman)"))
        channel_rows = rows("channel", "id.channel", _("(No channel)"))
        total = finish(keys_by_dim["total"][0])
        total["pjp"] = pjp["total"]

        return {
            "period": {"mode": mode, "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat()},
            "currency": self.env.company.currency_id.name,
            "currency_digits": self.env.company.currency_id.decimal_places,
            "outlet_keys": list(outlet_keys), "segment_amounts": dict(segment_amounts),
            "lpo_target": lpo_target,
            "total": total,
            "salesmen": salesman_rows,
            "channels": channel_rows,
            "pjp_status": pjp["status"],
            "assortment_basis": "current_active_readable_catalog",
            "penetration": self._penetration(dim_skus, catalog, salesman_rows, channel_rows),
            "trend": self._trend(mode, start, end, salesman_ids, channel_ids, company_ids),
            "domains": {"orders": self._json_domain(order_domain), "pickings": self._json_domain(picking_domain)},
        }

    @staticmethod
    def _json_domain(domain):
        return [[t[0], t[1], t[2].strftime("%Y-%m-%d %H:%M:%S") if isinstance(t[2], datetime) else t[2]]
                for t in domain]

    # ------------------------------------------------------------------ invoices
    @api.model
    def _posted_invoiced_qty(self, lines):
        """Posted invoiced quantity per SO line id, in the SO line UoM (credit notes subtract)."""
        result = defaultdict(float)
        if not lines:
            return result
        amls = self.env["account.move.line"].search_fetch(
            [("sale_line_ids", "in", lines.ids), ("parent_state", "=", "posted"),
             ("move_id.move_type", "in", ("out_invoice", "out_refund"))],
            ["quantity", "sale_line_ids", "product_uom_id", "move_id"])
        for aml in amls:
            sign = -1.0 if aml.move_id.move_type == "out_refund" else 1.0
            for sol in aml.sale_line_ids:
                if sol.id not in lines._ids:
                    continue
                qty = aml.quantity
                if aml.product_uom_id and sol.product_uom_id and aml.product_uom_id != sol.product_uom_id:
                    qty = aml.product_uom_id._compute_quantity(qty, sol.product_uom_id)
                result[sol.id] += sign * qty
        return result

    # ------------------------------------------------------------------ catalogue / penetration
    @api.model
    def _catalog(self):
        products = self.env["product.product"].search([("sale_ok", "=", True)])
        principal = defaultdict(set)
        brand = defaultdict(set)
        for p in products:
            principal[p.principal_id.id or 0].add(p.id)
            brand[p.brand_id.id or 0].add(p.id)
        return {"principal": principal, "brand": brand}

    @api.model
    def _penetration(self, dim_skus, catalog, salesman_rows, channel_rows):
        result = {}
        for dim, rows in (("salesman", salesman_rows), ("channel", channel_rows)):
            result[dim] = {}
            for kind, model in (("principal", "id.principal"), ("brand", "id.brand")):
                ids = set(catalog[kind]) | {i or 0 for key in dim_skus[dim] for i in dim_skus[dim][key][kind]}
                names = {r.id: r.display_name for r in self.env[model].browse([i for i in ids if i]).exists()}
                items = []
                for item_id in sorted(ids, key=lambda i: names.get(i, "~")):
                    eligible = catalog[kind].get(item_id, set())
                    cells = {}
                    for row in rows:
                        sold = dim_skus[dim].get(row["id"], {}).get(kind, {}).get(item_id, set())
                        cells[str(row["id"])] = {"sold": len(sold), "eligible_sold": len(sold & eligible),
                            "outside_catalog": len(sold - eligible),
                            "penetration": _ratio(len(sold & eligible), len(eligible))}
                    items.append({"id": item_id, "name": names.get(item_id, _("(Unassigned)")),
                                  "catalog": len(eligible), "cells": cells})
                result[dim][kind] = items
        return result

    @api.model
    def _conversion(self, order, cache=None):
        company, currency = order.company_id, order.currency_id
        if currency == company.currency_id:
            return 1.0
        day = _local_date(order.date_order)
        key = (company.id, currency.id, day)
        if cache is not None and key in cache:
            return cache[key]
        for cur in currency | company.currency_id:
            if not self.env["res.currency.rate"].search_count([
                ("currency_id", "=", cur.id), ("name", "<=", day),
                ("company_id", "in", [False, company.id])]):
                raise UserError(_("An explicit exchange rate is required for foreign-currency sales."))
        factor = currency._convert(1.0, company.currency_id, company, day, round=False)
        if cache is not None:
            cache[key] = factor
        return factor

    @api.model
    def _segment_targets(self, period, amounts, salesman_ids, channel_ids):
        Target = self.env["id.sales.segment.target"]
        records = Target.search([("company_id", "in", self.env.companies.ids), ("active", "=", True),
                                 ("date_from", "=", period["start"]), ("date_to", "=", period["end"])])
        result = []
        for target in records:
            ident = target.segment_id
            selected = salesman_ids if target.dimension == "salesman" else channel_ids
            if target.dimension in ("salesman", "channel") and selected and ident not in selected:
                continue
            partial = bool(channel_ids if target.dimension == "salesman" else
                           salesman_ids if target.dimension == "channel" else salesman_ids or channel_ids)
            amount = None if partial else amounts.get((target.company_id.id, target.dimension, ident), 0.0)
            result.append({"id": target.id, "name": target.name, "company": target.company_id.name,
                "dimension": target.dimension, "segment": target.segment_name, "target": target.target_amount,
                "actual": amount, "achievement": _ratio(amount, target.target_amount) if amount is not None else None,
                "scope_complete": not partial})
        return result

    # ------------------------------------------------------------------ trend
    @api.model
    def _trend(self, mode, start, end, salesman_ids, channel_ids, company_ids):
        if mode == "day":
            t_start, t_end = start - timedelta(days=6), end
        else:
            t_start, t_end = start, end
        domain = [("state", "in", CONFIRMED_STATES), ("company_id", "in", company_ids),
                  ("date_order", ">=", _to_utc(t_start)), ("date_order", "<", _to_utc(t_end))]
        if salesman_ids:
            domain.append(("user_id", "in", salesman_ids))
        if channel_ids:
            domain.append(("partner_id.channel_id", "in", channel_ids))
        Order = self.env["sale.order"]
        if Order.search_count(domain) > MAX_ORDERS:
            raise UserError(_("Too many orders for one query; narrow the period or filters."))
        found = defaultdict(lambda: [0.0, 0])
        fx_cache = {}
        orders = Order.search_fetch(domain, ["date_order", "company_id", "currency_id"])
        subtotals = {order.id: amount for order, amount in self.env["sale.order.line"]._read_group(
            [("order_id", "in", orders.ids), ("display_type", "=", False), ("product_id", "!=", False)],
            ["order_id"], ["price_subtotal:sum"])}
        for order in orders:
            point = found[_local_date(order.date_order)]
            point[0] += subtotals.get(order.id, 0.0) * self._conversion(order, fx_cache)
            point[1] += 1
        points = []
        day = t_start
        while day < t_end:
            amount, count = found.get(day, (0.0, 0))
            points.append({"date": day.isoformat(), "net": amount, "orders": count})
            day += timedelta(days=1)
        return points

    # ------------------------------------------------------------------ PJP / effective call
    @api.model
    def _pjp_unavailable(self, reason):
        empty = {"salesman": {}, "channel": {}}
        return {"status": {"available": False, "reason": reason, "scope": None},
                "total": {"available": False}, "by": empty, "keys": {"salesman": set(), "channel": set()}}

    @api.model
    def _pjp(self, start, end, lo, hi, salesman_ids, channel_ids, order_info):
        registry = self.env.registry
        if "id.mobile.workday" not in registry or "id.mobile.evidence" not in registry:
            return self._pjp_unavailable(_("The mobile API module (PJP plan and visit evidence) is not installed."))
        Workday = self.env["id.mobile.workday"].with_context(active_test=False)
        Evidence = self.env["id.mobile.evidence"]
        try:
            Workday.check_access("read")
            Evidence.check_access("read")
        except AccessError:
            return self._pjp_unavailable(_("Your role cannot read PJP plans and visit evidence."))
        user = self.env.user
        scope = "all" if user.has_group("base.group_system") else "own"
        company_ids = self.env.companies.ids
        wd_domain = [("business_date", ">=", start), ("business_date", "<", end),
                     ("company_id", "in", company_ids)]
        ev_domain = [("create_date", ">=", lo), ("create_date", "<", hi), ("company_id", "in", company_ids)]
        if scope == "own":
            wd_domain.append(("user_id", "=", user.id))
            ev_domain.append(("user_id", "=", user.id))
        if salesman_ids:
            wd_domain.append(("user_id", "in", salesman_ids))
            ev_domain.append(("user_id", "in", salesman_ids))
        workdays = Workday.search(wd_domain)
        if not workdays:
            return self._pjp_unavailable(_("No PJP plan (workday assignment) exists for this period and filter."))

        if Evidence.search_count(ev_domain) > MAX_ORDERS:
            raise UserError(_("Too much visit evidence; narrow the period or filters."))
        evidence = Evidence.search_fetch(
            ev_domain, ["user_id", "company_id", "outlet_id", "create_date", "receipt_json"])
        outlets = workdays.outlet_ids | evidence.outlet_id
        channel_of = {p.id: p.channel_id.id for p in outlets}

        def in_channel(outlet_id):
            return not channel_ids or channel_of.get(outlet_id) in channel_ids

        planned = set()
        assignments = {}
        for wd in workdays:
            for outlet in wd.outlet_ids:
                if in_channel(outlet.id):
                    key = (wd.company_id.id, wd.user_id.id, wd.business_date, outlet.id)
                    planned.add(key)
                    assignments[key] = (str(wd.id), str(wd.warehouse_id.id))
                    if len(planned) > 200000:
                        raise UserError(_("Too many planned visit slots; narrow the period or filters."))
        proof_keys = set()
        invalid_proofs = 0
        for ev in evidence:
            if not in_channel(ev.outlet_id.id):
                continue
            key = (ev.company_id.id, ev.user_id.id, _local_date(ev.create_date), ev.outlet_id.id)
            try:
                receipt = json.loads(ev.receipt_json)
                binding = assignments.get(key)
                valid = binding and all((
                    str(receipt.get("assignment_id")) == binding[0],
                    str(receipt.get("warehouse_id")) == binding[1],
                    str(receipt.get("company_id")) == str(key[0]), str(receipt.get("user_id")) == str(key[1]),
                    receipt.get("business_date") == key[2].isoformat(),
                    str(receipt.get("outlet_id")) == str(key[3])))
            except (ValueError, TypeError, AttributeError):
                valid = False
            if valid:
                proof_keys.add(key)
            else:
                invalid_proofs += 1

        command_available = "id.mobile.command" in registry
        Command = self.env["id.mobile.command"] if command_available else None
        if command_available:
            try:
                Command.check_access("read")
            except AccessError:
                command_available = False
        visit_times = {}
        ignored_commands = 0
        if command_available:
            cmd_domain = [("company_id", "in", company_ids), ("create_date", ">=", lo), ("create_date", "<", hi),
                          ("status", "=", "accepted"), ("command_type", "=", "sales.visit.check_in")]
            if scope == "own":
                cmd_domain.append(("user_id", "=", user.id))
            if salesman_ids:
                cmd_domain.append(("user_id", "in", salesman_ids))
            if Command.search_count(cmd_domain) > MAX_ORDERS:
                raise UserError(_("Too many visit commands; narrow the period or filters."))
            for cmd in Command.search_fetch(cmd_domain, ["user_id", "company_id", "payload_json", "create_date"]):
                try:
                    envelope = json.loads(cmd.payload_json)
                    payload = envelope.get("payload", envelope)
                    outlet_id = int(payload["outlet_id"])
                    if not in_channel(outlet_id):
                        continue
                    day = _local_date(cmd.create_date)
                    key = (cmd.company_id.id, cmd.user_id.id, day, outlet_id)
                    if key not in planned or payload.get("business_date", day.isoformat()) != day.isoformat():
                        raise ValueError("unassigned")
                    visit_times[key] = min(visit_times.get(key, cmd.create_date), cmd.create_date)
                except (ValueError, TypeError, KeyError, AttributeError):
                    ignored_commands += 1

        # A call is effective only after an accepted check-in, for the exact outlet/company/WITA day.
        effective = set()
        for uid, _channel, outlet_id, day, confirmed_at, company_id in order_info.values():
            key = (company_id, uid, day, outlet_id)
            if key in visit_times and confirmed_at >= visit_times[key]:
                effective.add(key)
        by = {"salesman": defaultdict(lambda: {"planned": 0, "completed": 0, "visits": 0,
                                                "effective": 0, "proof_completed": 0}),
              "channel": defaultdict(lambda: {"planned": 0, "completed": 0, "visits": 0,
                                               "effective": 0, "proof_completed": 0})}
        total = {"planned": 0, "completed": 0, "visits": 0, "effective": 0, "proof_completed": 0}

        def add(key, field):
            _company, uid, _day, outlet_id = key
            for target in (by["salesman"][uid], by["channel"][channel_of.get(outlet_id, 0)], total):
                target[field] += 1

        for key in planned:
            add(key, "planned")
        for key in proof_keys:
            add(key, "proof_completed")
        for key in visit_times:
            add(key, "completed")
            add(key, "visits")
        for key in effective:
            add(key, "effective")

        def final(c):
            return {"available": command_available, "planned": c["planned"],
                    "proof_completed": c["proof_completed"],
                    "proof_compliance": _ratio(c["proof_completed"], c["planned"]),
                    "completed": c["completed"] if command_available else None,
                    "compliance": _ratio(c["completed"], c["planned"]) if command_available else None,
                    "visits": c["visits"] if command_available else None,
                    "effective": c["effective"] if command_available else None,
                    "ec_ratio": _ratio(c["effective"], c["visits"]) if command_available else None}

        return {"status": {"available": command_available,
                           "reason": None if command_available else _("Accepted visit commands are not readable."),
                           "scope": scope, "source": "accepted_checkin_server_time", "invalid_proofs": invalid_proofs,
                           "ignored_commands": ignored_commands},
                "total": final(total),
                "by": {dim: {k: final(v) for k, v in values.items()} for dim, values in by.items()},
                "keys": {dim: set(by[dim]) for dim in by}}
