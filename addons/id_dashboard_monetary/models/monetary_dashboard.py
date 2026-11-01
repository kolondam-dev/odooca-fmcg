# Part of odooca-fmcg. License LGPL-3.
"""Monetary & AR Executive Dashboard aggregator service."""

from collections import defaultdict
from odoo import api, fields, models, _
from odoo.exceptions import AccessError

BUCKET_ORDER = ["not_due", "overdue_1_7", "overdue_8_14", "overdue_15_30", "overdue_over_30"]
BUCKET_LABELS = {
    "not_due": _("Belum Jatuh Tempo"),
    "overdue_1_7": _("Overdue 1–7 Hari (Peringatan Awal)"),
    "overdue_8_14": _("Overdue 8–14 Hari (Credit Hold)"),
    "overdue_15_30": _("Overdue 15–30 Hari (Audit SPV)"),
    "overdue_over_30": _("Overdue > 30 Hari (Potensi Macet)"),
}


class MonetaryDashboard(models.TransientModel):
    _name = "id.monetary.dashboard"
    _description = "Monetary & AR Dashboard Service"

    name = fields.Char(default="Monetary Dashboard Service", readonly=True)

    def _check_access(self):
        user = self.env.user
        if not (
            user.has_group("account.group_account_invoice")
            or user.has_group("account.group_account_user")
            or user.has_group("account.group_account_manager")
            or user.has_group("base.group_system")
        ):
            raise AccessError(_("Anda tidak memiliki izin untuk melihat Dashboard Moneter & Piutang."))

    @api.model
    def get_filters(self):
        self._check_access()
        # Coverage areas
        areas = []
        if "id.coverage.area" in self.env:
            area_recs = self.env["id.coverage.area"].search_read([], ["id", "name"], order="name")
            areas = [{"id": a["id"], "name": a["name"]} for a in area_recs]

        # Salesmen
        salesmen = []
        sales_group = self.env.ref("sales_team.group_sale_salesman", raise_if_not_found=False)
        if sales_group and getattr(sales_group, "users", None):
            salesmen = [{"id": u.id, "name": u.name} for u in sales_group.users if not u.share]
        if not salesmen:
            user_recs = self.env["res.users"].search_read(
                [("share", "=", False)], ["id", "name"], order="name", limit=20
            )
            salesmen = [{"id": u["id"], "name": u["name"]} for u in user_recs]

        return {
            "areas": areas,
            "salesmen": salesmen,
        }

    @api.model
    def get_data(self, area_id=None, salesman_id=None):
        self._check_access()
        company_ids = self.env.companies.ids

        area_ids = [int(area_id)] if area_id else []
        salesman_ids = [int(salesman_id)] if salesman_id else []

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
             "invoice_date", "date_due", "amount_residual",
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
            ["partner_id", "salesman_id", "area_id", "invoice_count",
             "amount_residual", "max_days_overdue", "worst_bucket"],
            order="amount_residual desc",
            limit=10,
        )
        partner_ids = [c["partner_id"][0] for c in top_customers if c["partner_id"]]
        partners = {
            p.id: p for p in self.env["res.partner"].browse(partner_ids).exists()
        }
        top_cust_list = []
        for c in top_customers:
            pid = c["partner_id"][0] if c["partner_id"] else None
            partner = partners.get(pid)
            credit_limit = float(partner.credit_limit) if partner and hasattr(partner, "credit_limit") else 0.0
            channel_name = (
                partner.channel_id.name
                if partner and hasattr(partner, "channel_id") and partner.channel_id
                else "-"
            )
            balance = float(c["amount_residual"] or 0.0)
            utilization = (balance / credit_limit * 100.0) if credit_limit > 0 else 0.0
            worst_b = c["worst_bucket"]
            is_credit_hold = worst_b in ("overdue_8_14", "overdue_15_30", "overdue_over_30") or (
                credit_limit > 0 and balance > credit_limit
            )

            top_cust_list.append({
                "id": pid or 0,
                "name": c["partner_id"][1] if c["partner_id"] else "-",
                "salesman": c["salesman_id"][1] if c["salesman_id"] else "-",
                "area": c["area_id"][1] if c["area_id"] else "-",
                "channel": channel_name,
                "open_count": c["invoice_count"],
                "total_balance": balance,
                "overdue_balance": balance if worst_b != "not_due" else 0.0,
                "credit_limit": credit_limit,
                "credit_hold": is_credit_hold,
                "utilization": round(utilization, 1),
            })

        # ----------------------------------------------------------- Financial Funnel & Target
        funnel_stages = self.env["id.monetary.funnel.stage"].search_read(
            [("company_id", "in", company_ids)],
            ["stage", "period_name", "amount", "target_amount", "achievement_percent"],
            order="sequence asc",
        )
        funnel_dict = {s["stage"]: float(s["amount"] or 0.0) for s in funnel_stages}
        target_val = funnel_dict.get("target", 0.0)
        realized_val = funnel_dict.get("realized", 0.0)
        cash_val = funnel_dict.get("collection", 0.0)

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
