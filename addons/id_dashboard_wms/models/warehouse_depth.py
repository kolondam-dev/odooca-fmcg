"""Location capacity, native movement flows, event clocks and stock-risk diagnostics."""
from collections import Counter, defaultdict
from datetime import date, timedelta
from math import ceil, isfinite
from statistics import median

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .asset_measure import measure
from .delivery_cohort import local_day, utc_start

LIMIT = 50000


def p90(values):
    return sorted(values)[ceil(len(values)*.9)-1] if values else None


class WarehouseDepth(models.AbstractModel):
    _name = "id.warehouse.depth"
    _description = "Warehouse Detail Read Model"

    def _bounded(self, model, domain, limit=LIMIT):
        if model.search_count(domain, limit=limit+1) > limit:
            raise UserError(_("Warehouse detail exceeds the query limit; narrow the warehouse or company scope."))
        return model.search(domain)

    def _pallet(self, package):
        seen, pallet = set(), None
        while package and package.id not in seen:
            seen.add(package.id)
            if package.package_type_id.is_fmcg_pallet:
                pallet = package.id
            package = package.parent_package_id
        return pallet if not package else None

    @api.model
    def _data(self, start, end, warehouse_id=None, category=None):
        lo, hi, now = date.fromisoformat(start), date.fromisoformat(end), fields.Datetime.now()
        wh_domain = [("company_id", "in", self.env.companies.ids)]
        if warehouse_id:
            wh_domain += [("id", "=", int(warehouse_id))]
        warehouses = self.env["stock.warehouse"].search(wh_domain)
        if warehouse_id and not warehouses:
            raise UserError(_("Warehouse is not available in the selected company scope."))
        locations = self._bounded(self.env["stock.location"], [("id", "child_of", warehouses.view_location_id.ids),
            ("company_id", "in", self.env.companies.ids)], limit=1000)
        internal = locations.filtered(lambda loc: loc.usage == "internal")
        Quant = self.env["stock.quant"]
        quant_domain = [("location_id", "in", internal.ids), ("company_id", "in", self.env.companies.ids),
                        ("quantity", "!=", 0)]
        quants = self._bounded(Quant, quant_domain)
        q_by_location, pallet_locations = defaultdict(list), defaultdict(set)
        pallets = {}
        for quant in quants:
            q_by_location[quant.location_id.id].append(quant)
            if quant.quantity > 0:
                pallets[quant.id] = self._pallet(quant.package_id)
                if pallets[quant.id]:
                    pallet_locations[pallets[quant.id]].add(quant.location_id.id)
        kg_unit = self.env.ref("uom.product_uom_kgm")
        native_weight_unit = self.env["product.template"]._get_weight_uom_id_from_ir_config_parameter()
        location_rows, spatial_frames = [], set()
        for loc in locations.filtered(lambda item: item.usage in ("internal", "view")):
            if not loc.parent_path:
                raise UserError(_("Storage hierarchy is incomplete; refresh the location master."))
            path = loc.parent_path
            below = locations.filtered(lambda item: (item.parent_path or "").startswith(path))
            subset = [q for child in below for q in q_by_location[child.id]]
            if not subset and not loc.fmcg_storage_kind and not loc.fmcg_usable_cbm and not loc.storage_category_id:
                continue
            volume = weight = 0.
            missing_v = missing_w = negative = unclassified = 0
            used = set()
            for quant in subset:
                if quant.quantity < 0:
                    negative += 1
                    continue
                vol, kg = measure(quant.product_id, quant.quantity)
                volume += vol or 0
                weight += kg or 0
                missing_v += int(vol is None)
                missing_w += int(kg is None)
                pallet = pallets.get(quant.id)
                if not pallet or len(pallet_locations[pallet]) != 1:
                    unclassified += 1
                else:
                    used.add(pallet)
            cap = loc.fmcg_usable_cbm
            category_weight = loc.storage_category_id.max_weight
            max_kg = (native_weight_unit._compute_quantity(category_weight, kg_unit, round=False)
                      if category_weight else 0)
            rules = loc.storage_category_id.package_capacity_ids.filtered(lambda r: r.package_type_id.is_fmcg_pallet)
            slots = loc.fmcg_pallet_slots
            if not slots and len(rules) == 1 and isfinite(rules.quantity) and float(rules.quantity).is_integer():
                slots = int(rules.quantity)
            if loc.fmcg_spatial_verified:
                spatial_frames.add((loc.warehouse_id.id, loc.fmcg_frame))
            location_rows.append({"id": loc.id, "warehouse": loc.warehouse_id.name, "name": loc.complete_name,
                "role": loc.fmcg_storage_kind or "unclassified", "volume": volume, "kg": weight,
                "capacity": cap or None, "max_kg": max_kg or None, "pallets": len(used), "slots": slots or None,
                "volume_pct": volume/cap*100 if cap > 0 and not missing_v and not negative else None,
                "weight_pct": weight/max_kg*100 if max_kg > 0 and not missing_w and not negative else None,
                "slot_pct": len(used)/slots*100 if slots > 0 and not unclassified and not negative else None,
                "missing_volume": missing_v, "missing_weight": missing_w, "negative": negative,
                "unclassified_pallets": unclassified, "verified": loc.fmcg_spatial_verified,
                "frame": loc.fmcg_frame, "source": loc.fmcg_capacity_source or loc.storage_category_id.display_name,
                "geometry": {key: loc[key] for key in ("fmcg_x_m", "fmcg_y_m", "fmcg_z_m",
                    "fmcg_length_m", "fmcg_width_m", "fmcg_height_m")} if loc.fmcg_spatial_verified else None,
                "quant_domain": [("company_id", "=", loc.company_id.id), ("location_id", "child_of", loc.id),
                                 ("quantity", "!=", 0)]})
        selected = quants.filtered(lambda q: not category or q.product_id.fmcg_category == category)
        sku_rows, ages, risk = [], [], Counter()
        for warehouse in warehouses:
            wh_quants = selected.filtered(lambda q: q.location_id.warehouse_id == warehouse)
            lookback = warehouse.dead_stock_days
            if not 1 <= warehouse.slow_stock_days <= lookback <= 3650:
                raise UserError(_("Configure valid stock observation thresholds on the warehouse."))
            warehouse_locations = internal.filtered(lambda loc: loc.warehouse_id == warehouse)
            out_domain = [("company_id", "=", warehouse.company_id.id), ("state", "=", "done"),
                ("location_id", "in", warehouse_locations.ids), ("location_dest_id.usage", "=", "customer"),
                ("date", ">=", now-timedelta(days=lookback)), ("date", "<=", now), ("quantity", ">", 0)]
            last = {product.id: when for product, when in self.env["stock.move"]._read_group(
                out_domain, ["product_id"], ["date:max"])}
            by_product = defaultdict(list)
            for quant in wh_quants:
                by_product[quant.product_id.id].append(quant)
                if quant.quantity <= 0:
                    risk["negative_positions"] += 1
                    continue
                if quant.in_date and quant.in_date <= now:
                    ages.append((now-quant.in_date).total_seconds()/86400)
                else:
                    risk["unknown_age"] += 1
                expiration = quant.lot_id.expiration_date
                if expiration:
                    days = (local_day(expiration)-local_day(now)).days
                    if days < 0:
                        risk["expired_positions"] += 1
                    elif days <= 30:
                        risk["expiry_30_positions"] += 1
                elif quant.product_id.use_expiration_date:
                    risk["missing_expected_expiry"] += 1
            for pid, positions in by_product.items():
                product = positions[0].product_id
                qty = sum(q.quantity for q in positions)
                reserved = sum(q.reserved_quantity for q in positions)
                positive = [q for q in positions if q.quantity > 0]
                old = [(now-q.in_date).days for q in positive if q.in_date and q.in_date <= now]
                oldest = max(old) if old else None
                last_day = (now-last[pid]).days if pid in last else None
                slow = (oldest is not None and oldest >= warehouse.slow_stock_days
                        and (last_day is None or last_day >= warehouse.slow_stock_days))
                inactive = (oldest is not None and oldest >= warehouse.dead_stock_days and last_day is None)
                risk["slow_skus"] += int(slow and not inactive)
                risk["inactive_skus"] += int(inactive)
                sku_rows.append({"key": "%s:%s" % (warehouse.id, pid), "product_id": pid,
                    "name": product.display_name, "warehouse": warehouse.name, "quantity": qty,
                    "reserved": reserved, "available": qty-reserved, "unit": product.uom_id.name,
                    "oldest_age": oldest, "last_outbound": str(last[pid]) if pid in last else None,
                    "lookback_days": lookback, "slow": slow, "inactive": inactive,
                    "domain": [("company_id", "=", warehouse.company_id.id),
                               ("location_id", "in", warehouse_locations.ids), ("product_id", "=", pid)]})
        movement_domain = [("company_id", "in", self.env.companies.ids), ("state", "=", "done"),
            ("date", ">=", utc_start(lo)), ("date", "<", utc_start(hi+timedelta(days=1))),
            ("quantity", ">", 0), "|", ("location_id", "in", locations.ids), ("location_dest_id", "in", locations.ids)]
        if category:
            movement_domain.append(("product_id.fmcg_category", "=", category))
        moves = self._bounded(self.env["stock.move.line"], movement_domain)
        storage = self.env["stock.location"].search([("id", "child_of", warehouses.lot_stock_id.ids)])
        storage_ids, loc_ids = set(storage.ids), set(locations.ids)
        daily = defaultdict(Counter)
        for line in moves:
            src, dst = line.location_id, line.location_dest_id
            if src.usage in ("supplier", "transit") and dst.id in loc_ids:
                kind = "received"
            elif src.id in loc_ids and dst.usage == "customer":
                kind = "shipped"
            elif src.id not in storage_ids and dst.id in storage_ids and src.usage == "internal":
                kind = "putaway"
            elif src.id in storage_ids and dst.id not in storage_ids and dst.usage == "internal":
                kind = "picking"
            else:
                kind = "other_transfer_or_adjustment"
            daily[str(local_day(line.date))][kind] += 1
        clock_domain = [("company_id", "in", self.env.companies.ids), ("warehouse_id", "in", warehouses.ids),
                        ("state", "!=", "draft"), "|", ("state", "=", "running"), "&",
                        ("ended_at", ">=", utc_start(lo)), ("ended_at", "<", utc_start(hi+timedelta(days=1)))]
        clocks = self._bounded(self.env["id.warehouse.clock"], clock_domain)
        durations = defaultdict(list)
        for task in clocks:
            if task.state == "done" and utc_start(lo) <= task.ended_at < utc_start(hi+timedelta(days=1)):
                durations[task.kind].append(task.duration_minutes)
        ledger = self._valuation_control()
        return {"as_of": str(now), "start": start, "end": end, "locations": location_rows[:200],
                "locations_total": len(location_rows), "verified_locations": sum(r["verified"] for r in location_rows),
                "frame_conflicts": sum(
                    len({frame for wid, frame in spatial_frames if wid == w.id}) > 1 for w in warehouses),
                "stock_positions": len(selected), "skus": sorted(sku_rows, key=lambda r: (
                    not r["inactive"], not r["slow"], -(r["oldest_age"] or 0)))[:200], "skus_total": len(sku_rows),
                "risk": dict(risk), "quant_age_median_days": median(ages) if ages else None,
                "quant_age_p90_days": p90(ages), "movement_domain": movement_domain,
                "daily": [{"date": day, **dict(counts)} for day, counts in sorted(daily.items())],
                "flow_counts": dict(sum(daily.values(), Counter())),
                "clocks": [{"kind": kind, "count": len(durations[kind]),
                    "median_minutes": median(durations[kind]) if durations[kind] else None,
                    "p90_minutes": p90(durations[kind])} for kind in ("picking", "putaway", "receiving_dwell")],
                "running_clocks": len(clocks.filtered(lambda c: c.state == "running")),
                "cancelled_clocks": len(clocks.filtered(lambda c: c.state == "cancelled")),
                "clock_domain": clock_domain, "ledger": ledger}

    def _valuation_control(self):
        if not (self.env.user.has_group("account.group_account_user") or self.env.user.has_group("base.group_system")):
            return {"available": False, "reason": "accounting_role_required", "rows": []}
        rows = []
        for company in self.env.companies:
            env = self.with_company(company).with_context(allowed_company_ids=company.ids).env
            products = self._bounded(env["product.product"].with_context(active_test=False),
                [("is_storable", "=", True), ("company_id", "in", [False, company.id])], limit=10000)
            mapping = company.with_env(env)._get_accounts_by_product(products)
            missing = sum(not v["valuation"] for v in mapping.values())
            if not mapping or missing:
                rows.append({"company_id": company.id, "company": company.name,
                             "available": False, "missing_accounts": missing})
                continue
            value = sum(products.with_context(warehouse_id=False, location=False,
                                               to_date=False, at_date=False).mapped("total_value"))
            accounting = company.with_env(env).stock_accounting_value(mapping, fields.Date.context_today(self))
            ledger_value = sum(accounting.values())
            accounts = {record["valuation"].id for record in mapping.values()}
            rows.append({"company_id": company.id, "company": company.name, "available": True, "native_value": value,
                "ledger_value": ledger_value, "gap": value-ledger_value,
                "domain": [("company_id", "=", company.id), ("parent_state", "=", "posted"),
                           ("account_id", "in", list(accounts)), ("date", "<=", fields.Date.context_today(self))]})
        return {"available": True, "rows": rows}
