"""Reconstructed AR subledger at accounting dates, using current reconciliation links."""
from collections import defaultdict
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

LIMIT = 50000
BUCKETS = ("not_due", "overdue_1_7", "overdue_8_14", "overdue_15_30", "overdue_over_30")


def bucket(day, maturity):
    late = (day - maturity).days if maturity else 0
    return BUCKETS[0 if late <= 0 else 1 if late <= 7 else 2 if late <= 14 else 3 if late <= 30 else 4]


class ArHistory(models.AbstractModel):
    _name = "id.ar.history"
    _description = "Historical Receivable Subledger"

    @api.model
    def _snapshot(self, as_of=None, comparison=None, area_ids=None, salesman_ids=None):
        user = self.env.user
        if not (user.has_group("account.group_account_user") or user.has_group("base.group_system")):
            return {"available": False, "reason": "accounting_role_required"}
        try:
            day = date.fromisoformat(as_of) if as_of else fields.Date.context_today(self)
            prior = date.fromisoformat(comparison) if comparison else day - timedelta(days=30)
        except (ValueError, TypeError) as exc:
            raise UserError(_("Invalid accounting snapshot date.")) from exc
        if prior > day or day > fields.Date.context_today(self):
            raise UserError(_("Comparison must precede the snapshot; future snapshots are not supported."))
        if len(self.env.companies.currency_id) != 1:
            raise UserError(_("Select companies with the same currency before aggregating monetary values."))
        domain = [("company_id", "in", self.env.companies.ids), ("parent_state", "=", "posted"),
                  ("account_id.account_type", "=", "asset_receivable"), ("date", "<=", day)]
        if area_ids:
            domain += [("partner_id.coverage_area_id", "in", area_ids)]
        if salesman_ids:
            domain += ["|", ("move_id.invoice_user_id", "in", salesman_ids), "&",
                       ("move_id.invoice_user_id", "=", False), ("partner_id.user_id", "in", salesman_ids)]
        Line = self.env["account.move.line"]
        if Line.search_count(domain, limit=LIMIT+1) > LIMIT:
            raise UserError(_("Too many ledger lines; narrow the scope."))
        lines = Line.search_fetch(domain, ["date", "date_maturity", "balance", "company_id", "partner_id", "move_id"])
        partial_domain = ["|", ("debit_move_id", "in", lines.ids), ("credit_move_id", "in", lines.ids)]
        Partial = self.env["account.partial.reconcile"]
        if Partial.search_count(partial_domain, limit=4*LIMIT+1) > 4*LIMIT:
            raise UserError(_("Too many reconciliations; narrow the scope."))
        partials = Partial.search_fetch(partial_domain, ["debit_move_id", "credit_move_id", "amount", "max_date"])
        adjustments = {prior: defaultdict(float), day: defaultdict(float)}
        for part in partials:
            for cutoff in adjustments:
                if part.max_date <= cutoff:
                    adjustments[cutoff][part.debit_move_id.id] -= part.amount
                    adjustments[cutoff][part.credit_move_id.id] += part.amount
        totals, positives, credits = defaultdict(float), defaultdict(float), defaultdict(float)
        migration = defaultdict(lambda: {"opening": 0.0, "closing": 0.0, "count": 0})
        opening_total = 0.0
        missing_maturity = 0
        open_count = 0
        # Rows are journal items (installment grain); credits never silently offset debit buckets.
        for line in lines:
            currency = line.company_id.currency_id
            before = line.balance + adjustments[prior][line.id] if line.date <= prior else 0.0
            after = line.balance + adjustments[day][line.id]
            before = 0.0 if currency.is_zero(before) else before
            after = 0.0 if currency.is_zero(after) else after
            opening_total += before
            if not before and not after:
                continue
            old = bucket(prior, line.date_maturity) if before > 0 else "credit" if before < 0 else "new"
            new = bucket(day, line.date_maturity) if after > 0 else "credit" if after < 0 else "settled"
            cell = migration[(old, new)]
            cell["opening"] += before
            cell["closing"] += after
            cell["count"] += 1
            if after:
                open_count += 1
                key = bucket(day, line.date_maturity)
                totals[key] += after
                positives[key] += max(after, 0)
                credits[key] += min(after, 0)
                missing_maturity += int(not line.date_maturity)
        net = sum(totals.values())
        return {"available": True, "as_of": str(day), "comparison": str(prior), "domain": domain,
                "basis": "current_posted_ledger_and_current_reconciliation_links",
                "net": net, "debit_open": sum(positives.values()), "credits": sum(credits.values()),
                "opening": opening_total, "movement": net-opening_total, "open_items": open_count,
                "missing_maturity": missing_maturity, "ledger_balance": sum(lines.mapped("balance")),
                "buckets": [{"key": key, "debit": positives[key], "credit": credits[key], "net": totals[key]}
                            for key in BUCKETS],
                "migration": [{"from": a, "to": b, **v} for (a, b), v in sorted(migration.items())]}
