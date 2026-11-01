# Part of odooca-fmcg. License LGPL-3.
"""Aggregation service for the Monetary and AR Executive Dashboard."""

from collections import defaultdict
from datetime import date

from odoo import _, api, models
from odoo.exceptions import AccessError

BUCKET_ORDER = ["not_due", "overdue_1_7", "overdue_8_14", "overdue_15_30", "overdue_over_30"]
BUCKET_LABELS = {
    "not_due": _("Belum Jatuh Tempo (< 0 Hari)"),
    "overdue_1_7": _("Jatuh Tempo 1–7 Hari (Peringatan Awal)"),
    "overdue_8_14": _("Jatuh Tempo 8–14 Hari (Credit Hold)"),
    "overdue_15_30": _("Jatuh Tempo 15–30 Hari (Audit SPV)"),
    "overdue_over_30": _("Jatuh Tempo > 30 Hari (Risiko Macet)"),
}


class MonetaryDashboard(models.AbstractModel):
    _name = "id.monetary.dashboard"
    _description = "Monetary and AR Executive Dashboard Service"

    @api.model
    def _check_access(self):
        user = self.env.user
        if not (user.has_group("account.group_account_invoice")
                or user.has_group("sales_team.group_sale_salesman")
                or user.has_group("base.group_system")):
            raise AccessError(_("Akses dashboard moneter memerlukan hak akses Faktur atau Sales."))

    @api.model
    def get_filters(self):
        self._check_access()
        company_ids = self.env.companies.ids

        # Coverage areas
        areas = self.env["id.coverage.area"].search_read([], ["id", "name", "code"], order="name")

        # Salesmen from users who have sales roles or manage partners
        users = self.env["res.users"].search_read(
            [("share", "=", False), ("company_ids", "in", company_ids)],
            ["id", "name"],
            order="name",
        )

        return {
            "areas": areas,
            "salesmen": users,
            "today": date.today().isoformat(),
        }

    @api.model
    def get_data(self, area_ids=None, salesman_ids=None):
        self._check_access()
        company_ids = self.env.companies.ids

        area_ids = [int(x) for x in (area_ids or []) if x]
        salesman_ids = [int(x) for x in (salesman_ids or []) if x]

        # ----------------------------------------------------------- AR Aging Records
        aging_domain = [("company_id", "in", company_ids)]
        if area_ids:
            aging_domain.append(("area_id", "in", area_ids))
        if salesman_ids:
            aging_domain.append(("salesman_id", "in", salesman_ids))

        Aging = self.env["id.ar.aging"]
        aging_records = Aging.search_read(
            aging_domain,
            ["id", "move_id", "invoice_number", "partner_id", "salesman_id", "area_id",
             "invoice_date", "invoice_date_due", "amount_total", "amount_residual",
             "bucket", "days_overdue", "currency_id"]
        )

        total_ar = 0.0
        overdue_ar = 0.0
        bad_debt = 0.0

        bucket_data = {
            b: {"key": b, "label": BUCKET_LABELS.get(b, b), "amount": 0.0, "count": 0, "percent": 0.0}
            for b in BUCKET_ORDER
        }

        area_totals = defaultdict(lambda: {"total": 0.0, "overdue": 0.0, "count": 0})
        salesman_totals = defaultdict(lambda: {"total": 0.0, "overdue": 0.0, "count": 0})

        for r in aging_records:
            residual = float(r["amount_residual"] or 0.0)
            bucket = r["bucket"]
            total_ar += residual

            if bucket != "not_due":
                overdue_ar += residual
            if bucket == "overdue_over_30":
                bad_debt += residual

            if bucket in bucket_data:
                bucket_data[bucket]["amount"] += residual
                bucket_data[bucket]["count"] += 1

            a_id = r["area_id"][0] if r["area_id"] else 0
            area_totals[a_id]["total"] += residual
            area_totals[a_id]["count"] += 1
            if bucket != "not_due":
                area_totals[a_id]["overdue"] += residual

            s_id = r["salesman_id"][0] if r["salesman_id"] else 0
            salesman_totals[s_id]["total"] += residual
            salesman_totals[s_id]["count"] += 1
            if bucket != "not_due":
                salesman_totals[s_id]["overdue"] += residual

        # Calculate percentages
        for b in bucket_data.values():
            b["percent"] = (b["amount"] / total_ar * 100.0) if total_ar > 0 else 0.0

        # Area breakdown list
        area_names = {a.id: a.name for a in self.env["id.coverage.area"].browse(list(area_totals.keys())).exists()}
        area_list = []
        for aid, val in area_totals.items():
            area_list.append({
                "id": aid,
                "name": area_names.get(aid, _("(Tanpa Area)") if not aid else _("Area #%s") % aid),
                "total_ar": val["total"],
                "overdue_ar": val["overdue"],
                "count": val["count"],
                "overdue_ratio": (val["overdue"] / val["total"] * 100.0) if val["total"] > 0 else 0.0,
            })
        area_list.sort(key=lambda x: x["total_ar"], reverse=True)

        # Salesman breakdown list
        salesman_names = {u.id: u.name for u in self.env["res.users"].browse(list(salesman_totals.keys())).exists()}
        salesman_list = []
        for sid, val in salesman_totals.items():
            salesman_list.append({
                "id": sid,
                "name": salesman_names.get(sid, _("(Tanpa Salesman)") if not sid else _("User #%s") % sid),
                "total_ar": val["total"],
                "overdue_ar": val["overdue"],
                "count": val["count"],
                "overdue_ratio": (val["overdue"] / val["total"] * 100.0) if val["total"] > 0 else 0.0,
            })
        salesman_list.sort(key=lambda x: x["total_ar"], reverse=True)

        # ----------------------------------------------------------- Top 10 Customers
        cust_domain = [("company_id", "in", company_ids)]
        if area_ids:
            cust_domain.append(("area_id", "in", area_ids))
        if salesman_ids:
            cust_domain.append(("salesman_id", "in", salesman_ids))

        top_customers = self.env["id.ar.customer.balance"].search_read(
            cust_domain,
            ["partner_id", "salesman_id", "area_id", "channel_id", "open_invoices_count",
             "total_open_balance", "overdue_balance", "worst_bucket", "credit_limit",
             "is_credit_hold", "credit_limit_utilization"],
            order="total_open_balance desc",
            limit=10,
        )
        top_cust_list = []
        for c in top_customers:
            top_cust_list.append({
                "id": c["partner_id"][0] if c["partner_id"] else 0,
                "name": c["partner_id"][1] if c["partner_id"] else "-",
                "salesman": c["salesman_id"][1] if c["salesman_id"] else "-",
                "area": c["area_id"][1] if c["area_id"] else "-",
                "channel": c["channel_id"][1] if c["channel_id"] else "-",
                "open_count": c["open_invoices_count"],
                "total_balance": float(c["total_open_balance"] or 0.0),
                "overdue_balance": float(c["overdue_balance"] or 0.0),
                "credit_limit": float(c["credit_limit"] or 0.0),
                "credit_hold": bool(c["is_credit_hold"]),
                "utilization": float(c["credit_limit_utilization"] or 0.0),
            })

        # ----------------------------------------------------------- Financial Funnel & Target
        funnel_stages = self.env["id.monetary.funnel.stage"].search_read(
            [("company_id", "in", company_ids)],
            ["stage", "period_name", "amount", "target_amount", "achievement_ratio"],
            order="sequence asc",
        )
        funnel_dict = {s["stage"]: float(s["amount"] or 0.0) for s in funnel_stages}
        target_val = funnel_dict.get("target", 0.0)
        realized_val = funnel_dict.get("realized", 0.0)
        cash_val = funnel_dict.get("cash", 0.0)

        achievement_rate = (realized_val / target_val * 100.0) if target_val > 0 else 0.0

        return {
            "kpi": {
                "total_ar": total_ar,
                "overdue_ar": overdue_ar,
                "overdue_ratio": (overdue_ar / total_ar * 100.0) if total_ar > 0 else 0.0,
                "bad_debt": bad_debt,
                "bad_debt_ratio": (bad_debt / total_ar * 100.0) if total_ar > 0 else 0.0,
                "target_revenue": target_val,
                "realized_revenue": realized_val,
                "achievement_rate": achievement_rate,
                "cash_collected": cash_val,
                "invoices_count": len(aging_records),
            },
            "buckets": [bucket_data[b] for b in BUCKET_ORDER],
            "top_customers": top_cust_list,
            "areas": area_list,
            "salesmen": salesman_list,
        }

