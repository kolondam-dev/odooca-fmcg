# Part of odooca-fmcg. License LGPL-3.
"""Monetary & AR Executive Dashboard aggregator service."""

from collections import defaultdict
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

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
    def _periods(self):
        targets = self.env["id.monetary.target"].search_read(
            [("company_id", "in", self.env.companies.ids), ("active", "=", True)],
            ["date_from", "date_to", "company_id", "currency_id"], order="date_to desc, date_from desc, id desc")
        periods = {}
        company_currencies = {c.id: c.currency_id.id for c in self.env.companies}
        for target in targets:
            if target["currency_id"][0] != company_currencies[target["company_id"][0]]:
                raise UserError(_("Target currency must match its company currency."))
            key = f"{target['date_from']}/{target['date_to']}"
            period = periods.setdefault(key, {"key": key, "label": key.replace("/", " → "),
                                               "target_ids": [], "companies": []})
            company = target["company_id"][0]
            if company in period["companies"]:
                raise UserError(_("More than one active target exists for the same company and period."))
            period["companies"].append(company)
            period["target_ids"].append(target["id"])
        return list(periods.values())

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
            "periods": self._periods(),
        }

    @api.model
    def get_data(self, area_id=None, salesman_id=None, **kwargs):
        self._check_access()
        company_ids = self.env.companies.ids
        if len(self.env.companies.currency_id) != 1:
            raise UserError(_("Select companies with the same currency before aggregating monetary values."))

        raw_areas = kwargs.get('area_ids') or (area_id and [area_id]) or []
        if isinstance(raw_areas, (int, str)):
            raw_areas = [raw_areas]
        area_ids = [int(a) for a in raw_areas if str(a).isdigit() or isinstance(a, int)]

        raw_salesmen = kwargs.get('salesman_ids') or (salesman_id and [salesman_id]) or []
        if isinstance(raw_salesmen, (int, str)):
            raw_salesmen = [raw_salesmen]
        salesman_ids = [int(s) for s in raw_salesmen if str(s).isdigit() or isinstance(s, int)]

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
             "bucket", "days_overdue", "currency_id", "company_id"]
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

        # Customer totals use the SAME filtered invoice population as the KPI.
        customers = {}
        for invoice in aging_records:
            pid = invoice["partner_id"][0]
            cid = invoice["company_id"][0]
            c = customers.setdefault((cid, pid), {"id": pid, "company_id": cid,
                "key": f"{cid}:{pid}", "name": invoice["partner_id"][1], "balance": 0.0,
                "overdue": 0.0, "count": 0, "bucket": "not_due", "salesmen": set(), "areas": set()})
            amount = float(invoice["amount_residual"] or 0)
            c["balance"] += amount
            c["count"] += 1
            if invoice["bucket"] != "not_due":
                c["overdue"] += amount
            if BUCKET_ORDER.index(invoice["bucket"]) > BUCKET_ORDER.index(c["bucket"]):
                c["bucket"] = invoice["bucket"]
            if invoice["salesman_id"]:
                c["salesmen"].add(invoice["salesman_id"][1])
            if invoice["area_id"]:
                c["areas"].add(invoice["area_id"][1])
        selected = sorted(customers.values(), key=lambda c: (-c["balance"], c["key"]))[:10]
        partners = {p.id: p for p in self.env["res.partner"].browse([c["id"] for c in selected]).exists()}
        top_cust_list = []
        for c in selected:
            partner = partners.get(c["id"])
            partner = partner.with_company(c["company_id"]) if partner else partner
            limit = float(partner.credit_limit or 0) if partner else 0.0
            top_cust_list.append({
                "id": c["id"], "company_id": c["company_id"], "key": c["key"], "name": c["name"],
                "salesman": ", ".join(sorted(c["salesmen"])) or "-",
                "area": ", ".join(sorted(c["areas"])) or "-",
                "channel": partner.channel_id.name if partner and partner.channel_id else "-",
                "open_count": c["count"], "total_balance": c["balance"], "overdue_balance": c["overdue"],
                "credit_limit": limit,
                "credit_hold": c["bucket"] in ("overdue_8_14", "overdue_15_30", "overdue_over_30") or
                               (limit > 0 and c["balance"] > limit),
                "utilization": round(c["balance"] / limit * 100, 1) if limit > 0 else None,
            })

        # ----------------------------------------------------------- Financial Funnel & Target
        periods = self._periods()
        key = kwargs.get("period_key") or (periods[0]["key"] if periods else None)
        period = next((p for p in periods if p["key"] == key), None)
        if key and not period:
            raise UserError(_("The selected target period is not available in these companies."))
        funnel_domain = [("company_id", "in", company_ids),
                         ("target_id", "in", period["target_ids"] if period else [])]
        funnel_stages = self.env["id.monetary.funnel.stage"].search_read(
            funnel_domain, ["stage", "amount"], order="sequence asc")
        funnel = defaultdict(float)
        for stage in funnel_stages:
            funnel[stage["stage"]] += float(stage["amount"] or 0)
        target_val = funnel.get("target")
        realized_val = funnel.get("realized")
        cash_val = funnel.get("collection")
        achievement_rate = realized_val / target_val * 100 if target_val else None

        self.env.cr.execute("SELECT CURRENT_DATE")
        aging_date = str(self.env.cr.fetchone()[0])
        return {
            "currency": self.env.company.currency_id.name,
            "period": period,
            "domains": {"aging": aging_domain, "funnel": funnel_domain},
            "as_of": aging_date,
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
