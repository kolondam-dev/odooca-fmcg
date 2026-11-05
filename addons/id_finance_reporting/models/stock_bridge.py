"""Read-only source inventory; never a historical valuation or full COGS oracle."""

from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

LIMIT = 20000


class FinanceStockBridge(models.AbstractModel):
    _name = "id.finance.stock.bridge"
    _description = "Finance Stock Source Diagnostics"

    def _bounded(self, model, domain):
        records = self.env[model].search(domain, limit=LIMIT + 1, order="id")
        if len(records) > LIMIT:
            raise UserError(_("Too many stock sources; narrow the diagnostic scope."))
        return records

    @api.model
    def _snapshot(self, company_id, date_from, date_to):
        # Private API: no RPC exposure, sudo, SQL, or synthetic valuation fallback.
        self.env["report.account_financial_report.trial_balance"]._check_finance_scope(company_id)
        start, end = fields.Date.to_date(date_from), fields.Date.to_date(date_to)
        if not start or not end or start > end or (end - start).days > 366:
            raise UserError(_("Select an ordered period of at most 367 days."))
        company = self.env["res.company"].browse(company_id)
        scoped = self.with_context(allowed_company_ids=[company_id]).with_company(company)
        return scoped._collect(company, start, end)

    def _collect(self, company, start, end):
        # Manado/WITA is fixed UTC+08. GL dates are dates, not shifted datetimes.
        lower = datetime.combine(start, time.min) - timedelta(hours=8)
        upper = datetime.combine(end + timedelta(days=1), time.min) - timedelta(hours=8)
        domain = [("company_id", "=", company.id), ("state", "=", "done"), "|",
                  "&", ("date", ">=", lower), ("date", "<", upper),
                  "&", ("account_move_id.date", ">=", start), ("account_move_id.date", "<=", end)]
        moves = self._bounded("stock.move", domain)
        self._bounded("stock.move.line", [("move_id", "in", moves.ids)])
        quants = self._bounded("stock.quant", [
            ("company_id", "=", company.id), ("location_id.usage", "=", "internal"),
            ("quantity", "!=", 0),
        ])
        categories = self._bounded("product.category", [])
        policies = [{"category_id": category.id,
                     "cost_method": category.property_cost_method,
                     "valuation": category.property_valuation,
                     "stock_account_id": category.property_stock_valuation_account_id.id}
                    for category in categories]
        rows = []
        for move in moves:
            move.check_access("read")
            lines = move.move_line_ids
            lines.check_access("read")
            product = move.product_id
            journal = move.account_move_id
            if journal and journal.company_id != company:
                raise AccessError(_("Stock journal belongs to another company."))
            journal.check_access("read")
            issues = []
            if move.is_valued and not journal:
                issues.append("no_direct_stock_journal_not_necessarily_error")
            if journal and journal.state != "posted":
                issues.append("linked_journal_not_posted")
            physical_day = (move.date + timedelta(hours=8)).date()
            if journal and physical_day != journal.date:
                issues.append("physical_posting_date_difference")
            rows.append({
                "move_id": move.id, "product_id": product.id, "category_id": product.categ_id.id,
                "physical_utc": fields.Datetime.to_string(move.date), "physical_wita": str(physical_day),
                "in_physical_period": start <= physical_day <= end,
                "account_move_id": journal.id, "posting_date": str(journal.date) if journal else None,
                "in_posting_period": bool(journal and start <= journal.date <= end),
                "is_in": move.is_in, "is_out": move.is_out, "value": move.value,
                "effective_cost_method_now": product.cost_method, "valuation_now": product.valuation,
                "stock_account_id_now": product._get_product_accounts()["stock_valuation"].id,
                "lines": [{"line_id": line.id, "owner_id": line.owner_id.id,
                           "quantity_product_uom": line.quantity_product_uom,
                           "location_id": line.location_id.id, "location_dest_id": line.location_dest_id.id,
                           "lot_id": line.lot_id.id} for line in lines],
                "issues": issues,
            })
        groups = []
        for journal in moves.account_move_id:
            # A journal may cover several stock moves: never compare each move
            # with the entire journal, or divide journal values pro rata.
            siblings = self._bounded("stock.move", [("account_move_id", "=", journal.id)])
            if any(move.company_id != company for move in siblings):
                raise AccessError(_("Stock journal belongs to another company."))
            expected = defaultdict(float)
            actual = defaultdict(float)
            for move in siblings:
                account = move.product_id._get_product_accounts()["stock_valuation"]
                expected[(account.id, move.product_id.id)] += move.value * (int(move.is_in) - int(move.is_out))
            journal_lines = self._bounded("account.move.line", [("move_id", "=", journal.id)])
            journal.line_ids.check_access("read")
            for line in journal_lines:
                key = (line.account_id.id, line.product_id.id)
                if key in expected:
                    actual[key] += line.balance
            groups.append({"account_move_id": journal.id, "sibling_move_ids": siblings.ids,
                           "state": journal.state, "posting_date": str(journal.date),
                           "comparisons_current_mapping": [
                               {"account_id": key[0], "product_id": key[1], "move_value_signed": value,
                                "gl_balance": actual[key], "difference": company.currency_id.round(actual[key] - value)}
                               for key, value in sorted(expected.items())]})
        stock_accounts = {row["stock_account_id_now"] for row in rows}
        stock_accounts.update(row["stock_account_id"] for row in policies)
        stock_accounts.add(company.account_stock_valuation_id.id)
        ledger = self._bounded("account.move.line", [
            ("company_id", "=", company.id), ("parent_state", "=", "posted"),
            ("date", ">=", start), ("date", "<=", end),
            ("account_id", "in", [account for account in stock_accounts if account]),
        ])
        linked_ids = set(moves.account_move_id.ids)
        ownership = [{"quant_id": quant.id, "product_id": quant.product_id.id,
                      "location_id": quant.location_id.id, "lot_id": quant.lot_id.id,
                      "owner_id": quant.owner_id.id, "quantity": quant.quantity,
                      "reserved_quantity": quant.reserved_quantity,
                      "ownership": "explicit_owner" if quant.owner_id else "company_unassigned_owner"}
                     for quant in quants]
        return {"scope": "user_visible_sources_only_not_full_stock_cogs_gl_acceptance",
                "company_id": company.id, "currency_id": company.currency_id.id,
                "date_from": str(start), "date_to": str(end), "physical_timezone": "Asia/Makassar",
                "policy_basis": "current_effective_not_historical", "quant_basis": "current_not_as_of",
                "company_cost_method": company.cost_method, "company_valuation": company.inventory_valuation,
                "policies": policies, "moves": rows, "journal_groups": groups, "ownership": ownership,
                "gl_stock_lines_current_mapping": [
                    {"line_id": line.id, "account_move_id": line.move_id.id, "account_id": line.account_id.id,
                     "product_id": line.product_id.id, "date": str(line.date), "balance": line.balance}
                    for line in ledger],
                "gl_without_selected_stock_link": sorted(set(ledger.move_id.ids) - linked_ids)}
