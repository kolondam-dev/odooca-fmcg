"""Scheduled root DO cohorts, retaining backlog/cancellation and backorder chains."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from math import ceil
from zoneinfo import ZoneInfo

from odoo import _, api, fields, models
from odoo.exceptions import UserError

TZ = ZoneInfo("Asia/Makassar")
LIMIT = 50000


def local_day(value):
    return value.replace(tzinfo=timezone.utc).astimezone(TZ).date()


def utc_start(day):
    return datetime.combine(day, time.min, tzinfo=TZ).astimezone(timezone.utc).replace(tzinfo=None)


class DeliveryCohort(models.AbstractModel):
    _name = "id.delivery.cohort"
    _description = "Scheduled Delivery Cohort"

    @api.model
    def _data(self, start=None, end=None, vehicle=None):
        now = fields.Datetime.now()
        today = local_day(now)
        try:
            lo = date.fromisoformat(start) if start else today.replace(day=1)
            hi = date.fromisoformat(end) if end else today
        except (TypeError, ValueError) as exc:
            raise UserError(_("Invalid delivery cohort dates.")) from exc
        if lo > hi or hi > today:
            raise UserError(_("The delivery cohort must end on or before today."))
        domain = [("company_id", "in", self.env.companies.ids), ("picking_type_code", "=", "outgoing"),
                  ("location_dest_id.usage", "=", "customer"), ("backorder_id", "=", False),
                  ("scheduled_date", ">=", utc_start(lo)),
                  ("scheduled_date", "<", utc_start(hi+timedelta(days=1))), ("state", "!=", "draft")]
        if vehicle:
            domain.append(("fmcg_vehicle_id", "=", int(vehicle)))
        Picking = self.env["stock.picking"]
        if Picking.search_count(domain, limit=LIMIT+1) > LIMIT:
            raise UserError(_("Too many deliveries; narrow the cohort."))
        roots = Picking.search(domain)
        all_pickings, frontier = roots, roots
        root_by_id = {p.id: p.id for p in roots}
        # Only readable chains; no sudo. Bounded breadth-first traversal.
        while frontier:
            children = Picking.search([("backorder_id", "in", frontier.ids),
                                       ("company_id", "in", self.env.companies.ids),
                                       ("picking_type_code", "=", "outgoing"), ("id", "not in", all_pickings.ids)])
            if len(all_pickings) + len(children) > LIMIT:
                raise UserError(_("Too many backorders; narrow the cohort."))
            for child in children:
                root_by_id[child.id] = root_by_id[child.backorder_id.id]
            all_pickings |= children
            frontier = children
        chains = defaultdict(lambda: self.env["stock.picking"])
        for picking in all_pickings:
            chains[root_by_id[picking.id]] |= picking
        rows, leads, ages = [], [], []
        h1_ok = h1_due = h2_ok = h2_due = cancelled = backlog = unknown = 0
        reasons = defaultdict(set)
        for root in roots:
            chain = chains[root.id]
            planned, delivered, delivered_on_time = defaultdict(float), defaultdict(float), defaultdict(float)
            completions = []
            for picking in chain:
                for move in picking.move_ids:
                    qty = move.product_uom._compute_quantity(move.product_uom_qty, move.product_id.uom_id, round=False)
                    planned[move.product_id.id] += qty
                    if move.state == "done" and move.date <= now:
                        actual = move.product_uom._compute_quantity(move.quantity, move.product_id.uom_id, round=False)
                        delivered[move.product_id.id] += actual
                        if move.date <= root.scheduled_date:
                            delivered_on_time[move.product_id.id] += actual
                        completions.append(move.date)
                if picking.fmcg_reject_reason:
                    reasons[picking.fmcg_reject_reason].add(root.id)
            valid = bool(planned) and any(qty > 0 for qty in planned.values())
            full = valid and all(delivered[k] + 1e-6 >= qty for k, qty in planned.items())
            on_time_full = valid and all(delivered_on_time[k] + 1e-6 >= qty for k, qty in planned.items())
            closed = all(p.state in ("done", "cancel") for p in chain)
            is_cancelled = any(p.state == "cancel" for p in chain)
            cancelled += int(is_cancelled)
            unknown += int(not valid)
            due = local_day(root.scheduled_date)
            completed = max(completions) if full and closed and completions else None
            elapsed = (local_day(completed)-due).days if completed else None
            lead_hours = (completed-root.scheduled_date).total_seconds()/3600 if completed else None
            if lead_hours is not None:
                leads.append(lead_hours)
            if not (full and closed) and not closed:
                backlog += 1
                ages.append(max((today-due).days, 0))
            if due+timedelta(days=1) < today:
                h1_due += 1
                h1_ok += int(elapsed is not None and elapsed <= 1 and not is_cancelled)
            if due+timedelta(days=2) < today:
                h2_due += 1
                h2_ok += int(elapsed is not None and elapsed <= 2 and not is_cancelled)
            rows.append({"id": root.id, "name": root.name, "scheduled": str(root.scheduled_date),
                         "completed": str(completed) if completed else None, "full": bool(full and closed),
                         "on_time_full": bool(on_time_full and closed),
                         "cancelled": is_cancelled, "backlog": not closed, "demand_known": valid})
        def percentile(values, fraction):
            return sorted(values)[max(ceil(len(values)*fraction)-1, 0)] if values else None
        # All cohort dates up to today are due only if the scheduled timestamp has passed.
        due_count = sum(p.scheduled_date <= now for p in roots)
        otif_due = sum(int(p.scheduled_date <= now and row["on_time_full"] and not row["cancelled"])
                       for p, row in zip(roots, rows))
        return {"start": str(lo), "end": str(hi), "as_of": str(now), "count": len(roots),
                "domain": domain, "source_ids": all_pickings.ids, "backlog": backlog, "cancelled": cancelled,
                "cancel_rate": cancelled/len(roots)*100 if roots else None,
                "otif": otif_due/due_count*100 if due_count else None, "otif_due": due_count,
                "h1": h1_ok/h1_due*100 if h1_due else None, "h1_due": h1_due,
                "h2": h2_ok/h2_due*100 if h2_due else None, "h2_due": h2_due,
                "lead_median_hours": percentile(leads, .5), "lead_p90_hours": percentile(leads, .9),
                "backlog_p90_days": percentile(ages, .9), "unknown_demand": unknown,
                "reasons": [{"reason": k, "count": len(v)} for k, v in sorted(reasons.items())],
                "rows": rows[:100], "rows_total": len(rows)}
