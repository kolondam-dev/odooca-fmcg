"""D1 read service: confirmed SO amounts and separately labelled posted refunds.

No SQL/sudo and no change to the legacy service, posting or mobile workflows.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from collections import defaultdict
from datetime import date, timedelta
from calendar import monthrange

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.addons.id_dashboard_sales.models.sales_productivity import (
    CONFIRMED_STATES, MAX_ORDERS, _local_date, _ratio, _to_utc,
)

# A dimension is always an ORM field, never a caller-supplied domain/expression.
DIMENSIONS = {
    "salesman": ("order_id.user_id", "res.users"),
    "channel": ("order_id.partner_id.channel_id", "id.channel"),
    "area": ("order_id.partner_id.coverage_area_id", "id.coverage.area"),
    "city": ("order_id.partner_id.district_id.city_id", "id.city"),
    "principal": ("product_id.principal_id", "id.principal"),
    "brand": ("product_id.brand_id", "id.brand"),
    "sku": ("product_id", "product.product"),
}
@lru_cache(maxsize=2)
def _geo_boundaries(filename):
    root = Path(__file__).resolve().parents[3]
    for folder in (root / "data" / "geo", Path("/opt/data/geo")):
        source = folder / filename
        if source.is_file():
            groups = defaultdict(list)
            for feature in json.loads(source.read_text(encoding="utf-8"))["features"]:
                info = feature["properties"]
                if feature["geometry"]:
                    groups[info["parent_code"]].append({
                        "code": info["code"], "name": info["name"], "geometry": feature["geometry"],
                    })
            return groups
    raise UserError(_("Geographic boundaries are unavailable."))


PRODUCT_DIMENSIONS = {"principal", "brand", "sku"}


def parse_range(period):
    allowed = {"from", "to", "preset", "compare", "compareMode", "align", "customFrom", "customTo"}
    if (not isinstance(period, dict) or set(period) - allowed
            or any(key in period and type(period[key]) is not bool for key in ("compare", "align"))):
        raise UserError(_("A period is required."))
    try:
        start = date.fromisoformat(period["from"])
        finish = date.fromisoformat(period["to"])
    except (KeyError, TypeError, ValueError) as exc:
        raise UserError(_("Invalid dashboard dates.")) from exc
    if finish < start or (finish - start).days > 365:
        raise UserError(_("Select an ordered date range of at most 366 days."))
    # No guessed Mon-Sat calendar: comparable workdays need an authoritative company calendar.
    if period.get("align"):
        raise UserError(_("Working-day alignment requires an approved company calendar. Turn alignment off."))
    return start, finish + timedelta(days=1)


def comparison_range(period, start, end):
    if not period.get("compare"):
        return None
    mode = period.get("compareMode", "previous")
    if mode == "custom":
        return parse_range({"from": period.get("customFrom"), "to": period.get("customTo")})
    def shift(day, months):
        month_index = day.year * 12 + day.month - 1 + months
        year, month = divmod(month_index, 12)
        month += 1
        return date(year, month, min(day.day, monthrange(year, month)[1]))
    months = None
    if mode == "year":
        months = -12
    elif mode == "quarter":
        months = -3
    elif mode == "previous":
        months = {"mtd": -1, "lastmonth": -1, "ytd": -12, "last3": -3}.get(period.get("preset"))
        if months is None:
            return start - (end - start), start
    if months is not None:
        return shift(start, months), shift(end - timedelta(days=1), months) + timedelta(days=1)
    raise UserError(_("Unknown comparison mode."))


class DashboardBridge(models.AbstractModel):
    _name = "id.dashboard.redesign"
    _description = "D1 Sales Performance Dashboard"

    def _service(self, dashboard):
        if dashboard != "D1":
            raise UserError(_("Only D1 is enabled in this release."))
        service = self.env["id.sales.productivity"]
        service._check_access()
        if len(self.env.companies.currency_id) != 1:
            raise UserError(_("Select companies with the same currency before aggregating sales."))
        return service

    @api.model
    def get_filters(self, dashboard):
        service = self._service(dashboard)
        filters = service.get_filters()
        users = self.env["res.users"].search([("company_ids", "in", self.env.companies.ids),
            ("all_group_ids", "in", self.env.ref("sales_team.group_sale_salesman").ids)])
        by_id = {row["id"]: row for row in filters["salesmen"]}
        by_id.update({user.id: {"id": user.id, "name": user.name} for user in users})
        filters["salesmen"] = sorted(by_id.values(), key=lambda row: row["name"])
        filters["dimensions"] = {}
        for dimension, (_path, model) in DIMENSIONS.items():
            if dimension in ("salesman", "channel"):
                rows = filters["salesmen" if dimension == "salesman" else "channels"]
            else:
                # Catalogue is readable scope only. Product lists are bounded and never silently truncated.
                obj = self.env[model]
                domain = [("sale_ok", "=", True)] if dimension == "sku" else []
                if obj.search_count(domain) > 10000:
                    raise UserError(_("The filter catalogue exceeds 10,000 entries; narrow the company scope."))
                rows = [{"id": r.id, "name": r.display_name,
                         "principal": r.principal_id.id if dimension in ("brand", "sku") else False,
                         "brand": r.brand_id.id if dimension == "sku" else False} for r in obj.search(domain)]
            filters["dimensions"][dimension] = rows
        return {"filters": filters, "scope": {
            "company_ids": self.env.companies.ids, "company_names": self.env.companies.mapped("name"),
            "user_id": self.env.uid, "role_label": _("Sales / User"),
        }}

    def _filters(self, filters):
        if not isinstance(filters, dict) or set(filters) - set(DIMENSIONS):
            raise UserError(_("Unknown dashboard filter."))
        domain = []
        for dimension, spec in filters.items():
            if (not isinstance(spec, dict) or set(spec) - {"mode", "ids"}
                    or spec.get("mode") not in ("in", "out") or not isinstance(spec.get("ids"), list)
                    or len(spec["ids"]) > 10000):
                raise UserError(_("Invalid filter selection."))
            ids = spec["ids"]
            if any(type(i) is not int or i <= 0 for i in ids):
                raise UserError(_("Filter identifiers must be positive integers."))
            if not ids:
                continue
            path, model = DIMENSIONS[dimension]
            # Archived selected values remain valid; deleted/inaccessible values fail explicitly.
            readable = self.env[model].with_context(active_test=False).search([("id", "in", ids)])
            if set(readable.ids) != set(ids):
                raise UserError(_("A selected filter is no longer accessible. Review the selection."))
            domain.append((path, "in" if spec["mode"] == "in" else "not in", ids))
        return domain

    @api.model
    def get_geo_boundaries(self, dashboard, parent):
        self._service(dashboard)
        if isinstance(parent, str) and re.fullmatch(r"71\.\d{2}(?:\.\d{2})?", parent):
            filename = "sulut_districts.geojson" if parent.count(".") == 1 else "sulut_villages.geojson"
            return _geo_boundaries(filename).get(parent, [])
        raise UserError(_("Invalid geographic region."))

    @api.model
    def get_data(self, dashboard, params=None):
        service = self._service(dashboard)
        if not isinstance(params, dict) or set(params) - {"query"}:
            raise UserError(_("Expected a D1 query."))
        query = params.get("query")
        if not isinstance(query, dict) or set(query) - {"period", "filters"}:
            raise UserError(_("Invalid D1 query."))
        start, end = parse_range(query.get("period"))
        line_filter = self._filters(query.get("filters", {}))
        source = self._aggregate(service, start, end, line_filter, query.get("filters", {}))
        # Context chart: five calendar months through the selected end date, same dimension filters.
        last_month = (end - timedelta(days=1)).replace(day=1)
        month_index = last_month.year * 12 + last_month.month - 1 - 4
        year, month = divmod(month_index, 12)
        history_start = date(year, month + 1, 1)
        history = self._aggregate(service, history_start, end, line_filter, query.get("filters", {}), details=False)
        source["monthly"] = history["monthly"]
        source["monthly_period"] = history["period"]
        prior = comparison_range(query["period"], start, end)
        if prior:
            previous = self._aggregate(service, *prior, line_filter, query.get("filters", {}), details=False)
            source["previous"] = previous["total"]
            source["previous_period"] = previous["period"]
            source["previous_trend"] = previous["trend"]
        return {"dashboard": dashboard, "source": source, "read_at": str(fields.Datetime.now())}

    def _aggregate(self, service, start, end, line_filter, filters, details=True):
        company_ids = self.env.companies.ids
        order_domain = [("state", "in", CONFIRMED_STATES), ("company_id", "in", company_ids),
                        ("date_order", ">=", _to_utc(start)), ("date_order", "<", _to_utc(end))]
        domain = [("order_id.state", "in", CONFIRMED_STATES), ("company_id", "in", company_ids),
                  ("order_id.date_order", ">=", _to_utc(start)), ("order_id.date_order", "<", _to_utc(end)),
                  ("display_type", "=", False), ("product_id", "!=", False), *line_filter]
        Line = self.env["sale.order.line"]
        if Line.search_count(domain) > MAX_ORDERS * 10:
            raise UserError(_("Too many sales lines; narrow the period or filters."))
        lines = Line.search(domain)
        orders = lines.order_id
        if len(orders) > MAX_ORDERS:
            raise UserError(_("Too many orders; narrow the period or filters."))
        total = {"gross": 0., "net": 0., "discount": 0., "orders": len(orders)}
        buckets = {key: defaultdict(float) for key in ("principal", "channel", "area", "city", "salesman")}
        geo = defaultdict(lambda: defaultdict(float))
        daily = defaultdict(lambda: {"net": 0., "gross": 0., "discount": 0.})
        daily_orders = defaultdict(int)
        for order in orders:
            daily_orders[_local_date(order.date_order)] += 1
        monthly = defaultdict(lambda: {"net": 0., "gross": 0., "discount": 0.})
        fx = {}
        for line in lines:
            order = line.order_id
            factor = service._conversion(order, fx)
            net = line.price_subtotal * factor
            discount = line.price_unit * line.product_uom_qty * line.discount / 100 * factor
            for key, amount in (("net", net), ("gross", net + discount), ("discount", discount)):
                total[key] += amount
            day = _local_date(order.date_order)
            daily[day]["net"] += net
            daily[day]["gross"] += net + discount
            daily[day]["discount"] += discount
            for key, amount in (("net", net), ("gross", net + discount), ("discount", discount)):
                monthly[day.strftime("%Y-%m")][key] += amount
            if details:
                partner = order.partner_id
                district = partner.district_id
                city = district.city_id
                city_code = city.kode_kemendagri or city.code
                if city_code and len(city_code) == 4:
                    city_code = city_code[:2] + "." + city_code[2:]
                district_code = district.kode_kemendagri
                village = partner.subdistrict_id
                if city_code:
                    geo[city_code][district_code or ""] += net
                if district_code:
                    village_code = village.kode_kemendagri if village.district_id == district else ""
                    geo[district_code][village_code or ""] += net
            for key in buckets:
                path = DIMENSIONS[key][0]
                record = line.mapped(path)
                buckets[key][record.id if record else 0] += net
        total["aov"] = _ratio(total["net"], total["orders"])
        total["discount_ratio"] = _ratio(total["discount"], total["gross"])
        period = {"mode": "custom", "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat()}
        trend = [{"date": (start + timedelta(days=i)).isoformat(), **daily[start + timedelta(days=i)],
                  "orders": daily_orders[start + timedelta(days=i)]} for i in range((end - start).days)]
        result = {"period": period, "currency": self.env.company.currency_id.name,
                  "total": total, "trend": trend, "domains": {"orders": service._json_domain(order_domain)},
                  "line_domain": service._json_domain(domain), "line_filtered": bool(line_filter)}
        month = start.replace(day=1)
        result["monthly"] = []
        while month < end:
            values = monthly[month.strftime("%Y-%m")]
            following = (month + timedelta(days=32)).replace(day=1)
            result["monthly"].append({"month": month.strftime("%Y-%m"), **values,
                "discount_ratio": _ratio(values["discount"], values["gross"]),
                "drill": {"model": "sale.order.line", "domain": service._json_domain([
                    *domain, ("order_id.date_order", ">=", _to_utc(month)),
                    ("order_id.date_order", "<", _to_utc(following))])}})
            month = following
        if not details:
            return result
        # A product slice has no matching planned-call denominator. Never reuse an unfiltered EC.
        pjp = service._pjp_unavailable(_("Call metrics are unavailable for product or geographic slices."))
        if not any(filters.get(k, {}).get("ids") for k in ("principal", "brand", "sku", "area", "city")):
            def included(key, catalogue):
                spec = filters.get(key, {})
                ids = spec.get("ids", [])
                if not ids:
                    return []
                if spec["mode"] == "in":
                    return ids
                return catalogue.search([("id", "not in", ids)]).ids
            # Empty complement must remain empty, never become the legacy service's "all".
            selected_salesmen = included("salesman", self.env["res.users"])
            selected_channels = included("channel", self.env["id.channel"])
            empty_complement = any(filters.get(k, {}).get("mode") == "out" and filters[k]["ids"] and not ids
                                   for k, ids in (("salesman", selected_salesmen), ("channel", selected_channels)))
            if not empty_complement:
                info = {o.id: (o.user_id.id, o.partner_id.channel_id.id, o.partner_id.id,
                               _local_date(o.date_order), o.date_order, o.company_id.id) for o in orders}
                pjp = service._pjp(start, end, _to_utc(start), _to_utc(end),
                                   selected_salesmen, selected_channels, info)
        assigned = defaultdict(set)
        if pjp["total"].get("available") and "id.mobile.workday" in self.env.registry:
            Workday = self.env["id.mobile.workday"].with_context(active_test=False)
            wd_domain = [("company_id", "in", company_ids), ("business_date", ">=", start),
                         ("business_date", "<", end)]
            if pjp["status"].get("scope") == "own":
                wd_domain.append(("user_id", "=", self.env.uid))
            for wd in Workday.search(wd_domain):
                if selected_salesmen and wd.user_id.id not in selected_salesmen:
                    continue
                assigned[wd.user_id.id].add((wd.company_id.id, wd.business_date))
        denominator = sum(len(days) for days in assigned.values())
        total["calls_per_day"] = (_ratio(pjp["total"].get("visits", 0), denominator)
                                  if pjp["total"].get("available") else None)
        total["pjp"] = pjp["total"]
        result["pjp_status"] = pjp["status"]
        for key in ("salesman", "channel"):
            for ident in pjp["by"][key]:
                buckets[key][ident] += 0  # Planned users with no sales remain explicit zero-sales rows.
        for key, amounts in buckets.items():
            model = self.env[DIMENSIONS[key][1]].with_context(active_test=False)
            names = {r.id: r.display_name for r in model.browse([i for i in amounts if i]).exists()}
            rows = []
            for ident, amount in sorted(amounts.items(), key=lambda item: -item[1]):
                path = DIMENSIONS[key][0]
                row_domain = [*domain, (path, "=", ident or False)]
                row = {"id": ident, "name": names.get(ident, _("Unassigned")), "net": amount,
                       "drill": {"model": "sale.order.line", "domain": service._json_domain(row_domain)}}
                if key == "city" and ident:
                    city = model.browse(ident)
                    row["code"] = city.kode_kemendagri or (city.code[:2] + "." + city.code[2:]
                                                        if city.code and len(city.code) == 4 else city.code)
                if key == "salesman":
                    own_orders = orders.filtered(lambda o: o.user_id.id == ident)
                    row.update({"orders": len(own_orders), "outlets": len(own_orders.partner_id),
                                "teams": own_orders.team_id.mapped("display_name"),
                                "pjp": pjp["by"]["salesman"].get(ident, {}),
                                "calls_per_day": _ratio(pjp["by"]["salesman"].get(ident, {}).get("visits", 0),
                                                        len(assigned.get(ident, set())))})
                rows.append(row)
            result["salesmen" if key == "salesman" else key] = rows
        # Reconcile targets only when their exact dated, independent partition covers the selected scope.
        result["geo"] = {parent: dict(amounts) for parent, amounts in geo.items()}
        result["target"] = self._target(start, end, orders, filters, total["net"])
        # Refund revenue is a separate accounting-date amount. It is not subtracted from SO net.
        result["refund"] = self._refund(start, end, line_filter)
        by_salesman = result["target"].pop("by_salesman", {})
        for row in result["salesmen"]:
            row["achievement"] = _ratio(row["net"], by_salesman.get(row["id"], 0))
        return result

    def _target(self, start, end, orders, filters, actual):
        unavailable = {"available": False, "reason": _("No complete target partition for this exact scope and period.")}
        if any(spec.get("ids") for dim, spec in filters.items() if dim != "salesman"):
            return unavailable
        user_domain = [("company_ids", "in", self.env.companies.ids), ("active", "=", True),
                       ("all_group_ids", "in", self.env.ref("sales_team.group_sale_salesman").ids)]
        if not self.env.user.has_group("sales_team.group_sale_salesman_all_leads"):
            user_domain.append(("id", "=", self.env.uid))
        spec = filters.get("salesman", {})
        if spec.get("ids"):
            user_domain.append(("id", "in" if spec["mode"] == "in" else "not in", spec["ids"]))
        # Explicit target universe = all active readable Sales users, including zero-sales users.
        users = self.env["res.users"].search(user_domain)
        expected = {(company.id, user.id) for user in users for company in user.company_ids & self.env.companies}
        if not expected or any((o.company_id.id, o.user_id.id) not in expected for o in orders):
            return unavailable
        targets = self.env["id.sales.segment.target"].search([
            ("company_id", "in", self.env.companies.ids), ("dimension", "=", "salesman"),
            ("date_from", "=", start), ("date_to", "=", end - timedelta(days=1)),
            ("salesman_id", "in", users.ids)])
        keys = {(t.company_id.id, t.salesman_id.id) for t in targets}
        if keys != expected or len(targets) != len(expected):
            return unavailable
        target = sum(targets.mapped("target_amount"))
        by_salesman = defaultdict(float)
        for record in targets:
            by_salesman[record.salesman_id.id] += record.target_amount
        return {"available": True, "amount": target, "achievement": _ratio(actual, target),
                "by_salesman": dict(by_salesman)}

    def _refund(self, start, end, line_filter):
        Line = self.env["account.move.line"]
        try:
            Line.check_access("read")
        except AccessError:
            return {"available": False, "reason": _("Refunds require accounting read access.")}
        domain = [("company_id", "in", self.env.companies.ids), ("move_id.state", "=", "posted"),
                  ("move_id.move_type", "=", "out_refund"), ("move_id.invoice_date", ">=", start),
                  ("move_id.invoice_date", "<", end), ("display_type", "=", "product")]
        # Direct accounting dimensions are kept explicit; relation filters must match one SO line together.
        sale_conditions = []
        for path, operator, ids in line_filter:
            if path.startswith("product_id"):
                domain.append((path, operator, ids))
            else:
                sale_conditions.append((path, operator, ids))
        if sale_conditions:
            domain.append(("sale_line_ids", "any", sale_conditions))
        if Line.search_count(domain) > MAX_ORDERS * 10:
            raise UserError(_("Too many refund lines; narrow the period or filters."))
        lines = Line.search(domain)
        daily = defaultdict(float)
        for line in lines:
            daily[line.move_id.invoice_date] += line.balance
        return {"available": True, "amount": sum(lines.mapped("balance")),
                "trend": [daily[start + timedelta(days=i)] for i in range((end - start).days)],
                "drill": {"model": "account.move.line",
                          "domain": self.env["id.sales.productivity"]._json_domain(domain)}}
