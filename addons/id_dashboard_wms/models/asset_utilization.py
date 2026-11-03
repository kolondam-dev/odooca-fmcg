"""Scoped physical stock snapshot and frozen trip-cohort utilization."""
import json
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .asset_measure import measure
from .delivery_cohort import utc_start

LIMIT = 50000


class AssetUtilization(models.AbstractModel):
    _name = "id.asset.utilization"
    _description = "Physical Asset Utilization"

    @api.model
    def _data(self, start, end, vehicle=None):
        warehouses = self.env["stock.warehouse"].search([("company_id", "in", self.env.companies.ids)])
        stock_rows = []
        seen_quant_ids = set()
        for warehouse in warehouses:
            domain = [("company_id", "=", warehouse.company_id.id),
                      ("location_id", "child_of", warehouse.lot_stock_id.id),
                      ("location_id.usage", "=", "internal"), ("quantity", "!=", 0)]
            Quant = self.env["stock.quant"]
            if Quant.search_count(domain, limit=LIMIT+1) > LIMIT:
                raise UserError(_("Too many stock positions; narrow the company scope."))
            quants = Quant.search(domain)
            if seen_quant_ids.intersection(quants.ids):
                raise UserError(_("Warehouse storage roots overlap; correct the location master."))
            seen_quant_ids.update(quants.ids)
            volume, kg, missing_volume, missing_weight, negative = 0., 0., 0, 0, 0
            for quant in quants:
                if quant.quantity < 0:
                    negative += 1
                    continue
                vol, weight = measure(quant.product_id, quant.quantity)
                volume += vol or 0
                kg += weight or 0
                missing_volume += int(vol is None)
                missing_weight += int(weight is None)
            capacity = warehouse.usable_volume_cbm
            stock_rows.append({"id": warehouse.id, "name": warehouse.name, "volume": volume, "kg": kg,
                               "capacity": capacity or None, "missing_volume": missing_volume,
                               "missing_weight": missing_weight, "negative": negative, "positions": len(quants),
                               "occupancy": volume/capacity*100 if capacity > 0 and not missing_volume
                               and not negative else None, "domain": domain})
        lo, hi = date.fromisoformat(start), date.fromisoformat(end)
        domain = [("company_id", "in", self.env.companies.ids), ("state", "!=", "draft"),
                  ("departed_at", ">=", utc_start(lo)), ("departed_at", "<", utc_start(hi+timedelta(days=1)))]
        if vehicle:
            domain.append(("vehicle_id", "=", int(vehicle)))
        Trip = self.env["id.asset.trip"]
        if Trip.search_count(domain, limit=LIMIT+1) > LIMIT:
            raise UserError(_("Too many trips; narrow the period."))
        trips = Trip.search(domain)
        rows = []
        eligible_volume = capacity_volume = eligible_kg = capacity_kg = 0.
        closed_km = direct_cost = delivered_dpp = 0.
        volume_covered = weight_covered = closed = dpp_unknown = 0
        for trip in trips:
            snap = json.loads(trip.snapshot_json)
            vol = sum(line["volume"] or 0 for line in snap["lines"])
            kg = sum(line["kg"] or 0 for line in snap["lines"])
            vol_ok = snap["capacity_volume"] and all(line["volume"] is not None for line in snap["lines"])
            kg_ok = snap["capacity_kg"] and all(line["kg"] is not None for line in snap["lines"])
            if vol_ok:
                volume_covered += 1
                eligible_volume += vol
                capacity_volume += snap["capacity_volume"]
            if kg_ok:
                weight_covered += 1
                eligible_kg += kg
                capacity_kg += snap["capacity_kg"]
            distance = trip.odometer_end_km-trip.odometer_start_km if trip.state == "closed" else None
            if trip.state == "closed":
                closed += 1
                closed_km += distance
                direct_cost += trip.fuel_cost + trip.helper_cost + trip.other_delivery_cost
                dpp_unknown += int(snap.get("delivered_dpp") is None)
                delivered_dpp += snap.get("delivered_dpp") or 0
            rows.append({"id": trip.id, "name": trip.name, "state": trip.state, "volume": vol, "kg": kg,
                         "volume_pct": vol/snap["capacity_volume"]*100 if vol_ok else None,
                         "weight_pct": kg/snap["capacity_kg"]*100 if kg_ok else None, "km": distance})
        # Maintenance remains native period cost; never allocated a second time into trip costs.
        service_domain = [("company_id", "in", self.env.companies.ids), ("date", ">=", lo), ("date", "<=", hi),
                          ("state", "=", "done")]
        if vehicle:
            service_domain.append(("vehicle_id", "=", int(vehicle)))
        maintenance, maintenance_count = None, None
        try:
            grouped = self.env["fleet.vehicle.log.services"].with_context(active_test=False)._read_group(
                service_domain, [], ["amount:sum", "__count"])
            maintenance, maintenance_count = grouped[0]
        except AccessError:
            pass
        complete_cost = bool(trips) and closed == len(trips) and maintenance is not None
        return {"as_of": str(fields.Datetime.now()), "warehouses": stock_rows,
                "trips": rows[:100], "trip_count": len(trips), "trip_domain": domain,
                "volume_covered": volume_covered, "weight_covered": weight_covered,
                "volume_pct": eligible_volume/capacity_volume*100 if capacity_volume else None,
                "weight_pct": eligible_kg/capacity_kg*100 if capacity_kg else None,
                "closed_count": closed, "km": closed_km, "direct_cost": direct_cost,
                "maintenance": maintenance, "maintenance_count": maintenance_count,
                "maintenance_domain": service_domain if maintenance is not None else [],
                "cost_per_km": (direct_cost+maintenance)/closed_km if complete_cost and closed_km > 0 else None,
                "cost_per_delivered_dpp": (direct_cost+maintenance)/delivered_dpp*100 if complete_cost
                and not dpp_unknown and delivered_dpp > 0 else None}
