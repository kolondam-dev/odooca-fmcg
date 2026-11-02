"""Period book margin from posted operating-income/direct-cost ledger accounts."""
from odoo import api, models


class MonetaryBookMargin(models.AbstractModel):
    _name = "id.monetary.book.margin"
    _description = "Posted Ledger Gross Margin"

    @api.model
    def _for_period(self, period):
        user = self.env.user
        base = {"available": False, "revenue": None, "direct_cost": None, "margin": None, "rate": None,
                "basis": "posted_accounting_date", "domain": []}
        if not (user.has_group("account.group_account_user") or user.has_group("base.group_system")):
            return dict(base, reason="accounting_role_required")
        if not period:
            return dict(base, reason="period_required")
        domain = [("company_id", "in", period["companies"]), ("parent_state", "=", "posted"),
                  ("date", ">=", period["key"].split("/")[0]), ("date", "<=", period["key"].split("/")[1]),
                  ("account_id.account_type", "in", ["income", "expense_direct_cost"])]
        grouped = self.env["account.move.line"]._read_group(domain, ["account_id"], ["balance:sum", "__count"])
        revenue, cost, income_count, cost_count = 0.0, 0.0, 0, 0
        for account, balance, count in grouped:
            if account.account_type == "income":
                revenue -= balance
                income_count += count
            else:
                cost += balance
                cost_count += count
        if not income_count or not cost_count:
            return dict(base, reason="incomplete_ledger_coverage", revenue=revenue if income_count else None,
                        direct_cost=cost if cost_count else None, domain=domain)
        return {"available": True, "reason": None, "revenue": revenue, "direct_cost": cost,
                "margin": revenue-cost, "rate": (revenue-cost)/revenue if revenue else None,
                "basis": "posted_accounting_date", "domain": domain,
                "income_lines": income_count, "cost_lines": cost_count}
