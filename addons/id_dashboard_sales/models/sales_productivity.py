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
* PJP compliance = planned (salesman, day, outlet) in ``id.mobile.workday`` that have an
  ``id.mobile.evidence`` the same day / planned. Effective call = evidence visits followed by a confirmed
  order for that outlet by that salesman the same day / visits. Both are "unavailable" when the mobile
  models are not installed, not readable by the user, or hold no plan for the period. Nothing is estimated.
"""
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
            "fulfilled": 0.0, "pickings": set(), "skus": set()}


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
    def _ids(self, values):
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
        anchor = anchor or self._param("period_min", DEFAULT_PERIOD_MIN)
        start, end = self._period(mode, anchor)
        lo, hi = _to_utc(start), _to_utc(end)
        salesman_ids = self._ids(salesman_ids)
        channel_ids = self._ids(channel_ids)
        company_ids = self.env.companies.ids
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
        orders = Order.search_fetch(order_domain, ["user_id", "partner_id", "date_order"])
        order_info = {}
        for order in orders:
            partner = order.partner_id
            order_info[order.id] = (order.user_id.id, partner.channel_id.id,
                                    partner.commercial_partner_id.id, _local_date(order.date_order))

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
        for line in lines:
            qty = line.product_uom_qty
            if qty <= 0:
                continue
            oid = line.order_id.id
            user_id, channel_id, _cp, _day = order_info[oid]
            discount = line.price_unit * qty * line.discount / 100.0
            net = line.price_subtotal
            done_qty = min(line.qty_delivered, invoiced.get(line.id, 0.0), qty)
            fulfilled = net * max(done_qty, 0.0) / qty
            pid = line.product_id.id
            order_skus[oid].add(pid)
            principal_id, brand_id = product_dims[pid]
            for dim, key in (("salesman", user_id), ("channel", channel_id), ("total", 0)):
                b = keys_by_dim[dim][key]
                b["orders"].add(oid)
                b["lines"] += 1
                b["gross"] += net + discount
                b["discount"] += discount
                b["net"] += net
                b["fulfilled"] += fulfilled
                b["skus"].add(pid)
                if dim != "total":
                    dim_skus[dim][key]["principal"][principal_id].add(pid)
                    dim_skus[dim][key]["brand"][brand_id].add(pid)

        pickings = self.env["stock.picking"].search_fetch(picking_domain, ["sale_id"])
        for picking in pickings:
            sale = picking.sale_id
            channel_id = sale.partner_id.channel_id.id
            keys_by_dim["salesman"][sale.user_id.id]["pickings"].add(picking.id)
            keys_by_dim["channel"][channel_id]["pickings"].add(picking.id)
            keys_by_dim["total"][0]["pickings"].add(picking.id)

        pjp = self._pjp(start, end, lo, hi, salesman_ids, channel_ids, order_info)
        catalog = self._catalog()

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
                "fulfillment": _ratio(b["fulfilled"], b["net"]),
            }

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
            "lpo_target": lpo_target,
            "total": total,
            "salesmen": salesman_rows,
            "channels": channel_rows,
            "pjp_status": pjp["status"],
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
        principal = defaultdict(int)
        brand = defaultdict(int)
        for p in products:
            principal[p.principal_id.id] += 1
            brand[p.brand_id.id] += 1
        return {"principal": principal, "brand": brand}

    @api.model
    def _penetration(self, dim_skus, catalog, salesman_rows, channel_rows):
        result = {}
        for dim, rows in (("salesman", salesman_rows), ("channel", channel_rows)):
            result[dim] = {}
            for kind, model in (("principal", "id.principal"), ("brand", "id.brand")):
                ids = {i for key in dim_skus[dim] for i in dim_skus[dim][key][kind]}
                names = {r.id: r.display_name for r in self.env[model].browse([i for i in ids if i]).exists()}
                items = []
                for item_id in sorted(ids, key=lambda i: names.get(i, "~")):
                    catalog_n = catalog[kind].get(item_id, 0)
                    cells = {}
                    for row in rows:
                        sold = len(dim_skus[dim][row["id"]][kind].get(item_id, ())) if row["id"] in dim_skus[dim] else 0
                        cells[str(row["id"])] = {"sold": sold, "penetration": _ratio(sold, catalog_n)}
                    items.append({"id": item_id, "name": names.get(item_id, _("(Unassigned)")),
                                  "catalog": catalog_n, "cells": cells})
                result[dim][kind] = items
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
        groups = self.env["sale.order"].with_context(tz="Asia/Makassar")._read_group(
            domain, ["date_order:day"], ["amount_untaxed:sum", "__count"])
        found = {(d.date() if isinstance(d, datetime) else d): (amount, count) for d, amount, count in groups}
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
        Workday = self.env["id.mobile.workday"]
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

        evidence = Evidence.search_fetch(ev_domain, ["user_id", "outlet_id", "create_date"])
        outlets = workdays.outlet_ids | evidence.outlet_id
        channel_of = {p.id: p.channel_id.id for p in outlets}
        commercial_of = {p.id: p.commercial_partner_id.id for p in outlets}

        def in_channel(outlet_id):
            return not channel_ids or channel_of.get(outlet_id) in channel_ids

        planned = {(w.user_id.id, w.business_date, o.id) for w in workdays for o in w.outlet_ids if in_channel(o.id)}
        visits = {(e.user_id.id, _local_date(e.create_date), e.outlet_id.id)
                  for e in evidence
                  if in_channel(e.outlet_id.id)}
        ordered = {(uid, day, cp) for uid, _ch, cp, day in order_info.values()}
        by = {"salesman": defaultdict(lambda: {"planned": 0, "completed": 0, "visits": 0, "effective": 0}),
              "channel": defaultdict(lambda: {"planned": 0, "completed": 0, "visits": 0, "effective": 0})}
        total = {"planned": 0, "completed": 0, "visits": 0, "effective": 0}

        def add(key_user, outlet_id, field):
            for target in (by["salesman"][key_user], by["channel"][channel_of.get(outlet_id, 0)], total):
                target[field] += 1

        for uid, day, outlet_id in planned:
            add(uid, outlet_id, "planned")
            if (uid, day, outlet_id) in visits:
                add(uid, outlet_id, "completed")
        for uid, day, outlet_id in visits:
            add(uid, outlet_id, "visits")
            if (uid, day, commercial_of.get(outlet_id)) in ordered:
                add(uid, outlet_id, "effective")

        def final(c):
            return {"available": True, "planned": c["planned"], "completed": c["completed"],
                    "compliance": _ratio(c["completed"], c["planned"]), "visits": c["visits"],
                    "effective": c["effective"], "ec_ratio": _ratio(c["effective"], c["visits"])}

        return {"status": {"available": True, "reason": None, "scope": scope},
                "total": final(total),
                "by": {dim: {k: final(v) for k, v in by[dim].items()} for dim in by},
                "keys": {dim: set(by[dim]) for dim in by}}
