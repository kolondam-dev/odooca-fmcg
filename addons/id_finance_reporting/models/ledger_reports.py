"""Server-side bounded models for FIN04, FIN51 and FIN57 in I2a."""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .ledger_compare import REGISTER_TYPES, combine_trial_balances, reconcile_register_to_gl

LIMIT = 20000


class FinanceLedgerMixin(models.AbstractModel):
    _name = "id.finance.ledger.mixin"
    _description = "Finance Ledger Bounded Query Mixin"

    def _check_scope(self, company_id, journal_ids=None, account_ids=None):
        tb = self.env["report.account_financial_report.trial_balance"]
        tb._check_finance_scope(company_id)
        tb._check_filter_company(company_id, journal_ids, account_ids)

    def _check_period(self, date_from, date_to):
        start, end = fields.Date.to_date(date_from), fields.Date.to_date(date_to)
        if not start or not end or start > end or (end - start).days > 366:
            raise UserError(_("Select an ordered period of at most 367 days."))
        return start, end

    def _bounded(self, model, domain, order="id"):
        records = self.env[model].search(domain, limit=LIMIT + 1, order=order)
        if len(records) > LIMIT:
            raise UserError(_("Too many journal items; narrow the report period or filters."))
        return records


class FinanceAuditTrail(models.AbstractModel):
    _name = "id.finance.audit.trail"
    _inherit = "id.finance.ledger.mixin"
    _description = "Journal Items Audit Trail (FIN04)"

    @api.model
    def _snapshot(
        self, company_id, date_from, date_to, only_posted_moves=True,
        journal_ids=None, account_ids=None,
    ):
        self._check_scope(company_id, journal_ids, account_ids)
        start, end = self._check_period(date_from, date_to)
        company = self.env["res.company"].browse(company_id)
        scoped = self.with_context(allowed_company_ids=[company_id]).with_company(company)
        return scoped._collect(company, start, end, only_posted_moves, journal_ids, account_ids)

    def _collect(self, company, start, end, only_posted_moves, journal_ids, account_ids):
        base = [
            ("company_id", "=", company.id),
            ("date", ">=", start),
            ("date", "<=", end),
            ("display_type", "not in", ["line_note", "line_section", "line_subsection"]),
        ]
        if journal_ids:
            base.append(("journal_id", "in", list(journal_ids)))
        if account_ids:
            base.append(("account_id", "in", list(account_ids)))
        states = ["posted"] if only_posted_moves else ["posted", "draft"]
        lines = self._bounded(
            "account.move.line",
            base + [("parent_state", "in", states)],
            order="date asc, move_id asc, id asc",
        )
        draft_lines = self._bounded(
            "account.move.line",
            base + [("parent_state", "=", "draft")],
            order="id asc",
        )
        lines.check_access("read")
        moves = lines.move_id
        moves.check_access("read")
        round_amt = company.currency_id.round
        rows = []
        partnerless_reconcilable_ids = []
        for line in lines:
            move = line.move_id
            if move.company_id != company:
                raise AccessError(_("Journal entry belongs to another company."))
            rev_origin = move.reversed_entry_id
            rev_children = move.reversal_move_ids
            if line.account_id.reconcile and not line.partner_id:
                partnerless_reconcilable_ids.append(line.id)
            rows.append({
                "aml_id": line.id,
                "move_id": move.id,
                "move_name": move.name,
                "move_type": move.move_type,
                "state": move.state,
                "date": str(line.date),
                "invoice_date": str(move.invoice_date) if move.invoice_date else None,
                "journal_id": line.journal_id.id,
                "journal_code": line.journal_id.code,
                "account_id": line.account_id.id,
                "account_code": line.account_id.code,
                "account_reconcile": bool(line.account_id.reconcile),
                "partner_id": line.partner_id.id or False,
                "partner_missing_on_reconcilable": bool(line.account_id.reconcile and not line.partner_id),
                "label": line.name or "",
                "ref": move.ref or "",
                "debit": round_amt(line.debit),
                "credit": round_amt(line.credit),
                "balance": round_amt(line.balance),
                "amount_currency": line.amount_currency,
                "currency_id": line.currency_id.id or company.currency_id.id,
                "matching_number": line.matching_number or False,
                "full_reconcile_id": line.full_reconcile_id.id or False,
                "reversed_entry_id": rev_origin.id or False,
                "reversal_move_ids": sorted(rev_children.ids),
                "is_reversal": bool(rev_origin),
                "is_reversed": bool(rev_children),
                "create_uid": line.create_uid.id,
                "create_date": fields.Datetime.to_string(line.create_date) if line.create_date else None,
                "write_uid": line.write_uid.id,
                "write_date": fields.Datetime.to_string(line.write_date) if line.write_date else None,
            })
        total_debit = round_amt(sum(r["debit"] for r in rows))
        total_credit = round_amt(sum(r["credit"] for r in rows))
        total_balance = round_amt(sum(r["balance"] for r in rows))
        return {
            "report_id": "FIN04",
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "date_from": str(start),
            "date_to": str(end),
            "only_posted_moves": bool(only_posted_moves),
            "journal_ids": sorted(journal_ids or []),
            "account_ids": sorted(account_ids or []),
            "move_count": len(moves),
            "aml_count": len(rows),
            "total_debit": total_debit,
            "total_credit": total_credit,
            "total_balance": total_balance,
            "partnerless_reconcilable_aml_ids": partnerless_reconcilable_ids,
            "draft_aml_ids_in_period": sorted(draft_lines.ids),
            "rows": rows,
        }


class FinanceCombinedTrialBalance(models.AbstractModel):
    _name = "id.finance.combined.trial.balance"
    _inherit = "id.finance.ledger.mixin"
    _description = "Multi-Company Combined Trial Balance (FIN51)"

    @api.model
    def _snapshot(
        self, company_ids, date_from, date_to, presentation_currency_id=None,
        rate_date=None, only_posted_moves=True, hide_account_at_0=False,
        fy_start_date=None, account_map=None,
    ):
        if not company_ids:
            raise AccessError(_("Select a company authorized in the active accounting context."))
        unique_company_ids = list(dict.fromkeys(company_ids))
        for cid in unique_company_ids:
            self._check_scope(cid)
        start, end = self._check_period(date_from, date_to)
        conv_date = fields.Date.to_date(rate_date) if rate_date else end
        fy_start = str(fields.Date.to_date(fy_start_date) or start.replace(month=1, day=1))
        companies = self.env["res.company"].browse(unique_company_ids)
        pres_currency = (
            self.env["res.currency"].browse(presentation_currency_id)
            if presentation_currency_id
            else companies[0].currency_id
        )
        entities_input = []
        for company in companies:
            tb_report = self.env["report.account_financial_report.trial_balance"].with_context(
                allowed_company_ids=unique_company_ids,
            ).with_company(company)
            unaffected = company.get_unaffected_earnings_account()
            totals, accounts_data, _partners = tb_report._get_data(
                account_ids=[],
                journal_ids=[],
                partner_ids=[],
                company_id=company.id,
                date_to=str(end),
                date_from=str(start),
                foreign_currency=False,
                only_posted_moves=only_posted_moves,
                show_partner_details=False,
                hide_account_at_0=hide_account_at_0,
                unaffected_earnings_account=unaffected.id if unaffected else False,
                fy_start_date=fy_start,
                grouped_by=False,
            )
            acc_types = {
                acc.id: acc.account_type
                for acc in self.env["account.account"].with_context(active_test=False).browse(list(totals))
            }
            rate = (
                1.0
                if company.currency_id == pres_currency
                else self.env["res.currency"]._get_conversion_rate(
                    company.currency_id, pres_currency, company, conv_date,
                )
            )
            rows = []
            for acc_id, vals in totals.items():
                meta = accounts_data.get(acc_id, {})
                rows.append({
                    "account_id": acc_id,
                    "code": meta.get("code", ""),
                    "name": meta.get("name", ""),
                    "account_type": acc_types.get(acc_id),
                    "initial_balance": vals["initial_balance"],
                    "debit": vals["debit"],
                    "credit": vals["credit"],
                    "balance": vals["balance"],
                    "ending_balance": vals["ending_balance"],
                })
            entities_input.append({
                "company_id": company.id,
                "company_name": company.display_name,
                "currency_id": company.currency_id.id,
                "currency_name": company.currency_id.name,
                "rate_to_presentation": rate,
                "rate_date": str(conv_date),
                "rate_source": "res.currency._get_conversion_rate",
                "rows": rows,
            })
        try:
            combined = combine_trial_balances(
                entities_input, pres_currency.round, account_map=account_map,
            )
        except ValueError as exc:
            raise UserError(
                _("Ambiguous cross-company Chart of Accounts mapping: %s", exc)
            ) from exc
        combined.update({
            "report_id": "FIN51",
            "company_ids": unique_company_ids,
            "presentation_currency_id": pres_currency.id,
            "presentation_currency_name": pres_currency.name,
            "date_from": str(start),
            "date_to": str(end),
            "fy_start_date": fy_start,
            "only_posted_moves": bool(only_posted_moves),
        })
        return combined


class FinanceSalesPurchaseRegister(models.AbstractModel):
    _name = "id.finance.sales.purchase.register"
    _inherit = "id.finance.ledger.mixin"
    _description = "Sales and Purchase Register (FIN57)"

    @api.model
    def _snapshot(
        self, company_id, date_from, date_to, register_type="all",
        only_posted_moves=True, journal_ids=None,
    ):
        self._check_scope(company_id, journal_ids)
        if register_type not in ("all", "sale", "purchase"):
            raise UserError(_("Invalid register type; choose all, sale or purchase."))
        start, end = self._check_period(date_from, date_to)
        company = self.env["res.company"].browse(company_id)
        scoped = self.with_context(allowed_company_ids=[company_id]).with_company(company)
        return scoped._collect(company, start, end, register_type, only_posted_moves, journal_ids)

    def _collect(self, company, start, end, register_type, only_posted_moves, journal_ids):
        if register_type == "sale":
            move_types = ("out_invoice", "out_refund")
        elif register_type == "purchase":
            move_types = ("in_invoice", "in_refund")
        else:
            move_types = REGISTER_TYPES
        states = ["posted"] if only_posted_moves else ["posted", "draft"]
        move_domain = [
            ("company_id", "=", company.id),
            ("move_type", "in", list(move_types)),
            ("state", "in", states),
            ("date", ">=", start),
            ("date", "<=", end),
        ]
        if journal_ids:
            move_domain.append(("journal_id", "in", list(journal_ids)))
        moves = self._bounded("account.move", move_domain, order="date asc, id asc")
        moves.check_access("read")
        move_lines = self._bounded(
            "account.move.line",
            [
                ("move_id", "in", moves.ids),
                ("display_type", "not in", ["line_note", "line_section", "line_subsection"]),
            ],
            order="move_id asc, id asc",
        )
        move_lines.check_access("read")
        lines_by_move = {}
        tracked_accounts = set()
        for line in move_lines:
            is_control = line.account_id.account_type in ("asset_receivable", "liability_payable")
            if not is_control:
                tracked_accounts.add(line.account_id.id)
            lines_by_move.setdefault(line.move_id.id, []).append({
                "line_id": line.id,
                "account_id": line.account_id.id,
                "display_type": line.display_type,
                "tax_line_id": line.tax_line_id.id or False,
                "tax_ids": sorted(line.tax_ids.ids),
                "is_control": is_control,
                "debit": line.debit,
                "credit": line.credit,
                "balance": line.balance,
            })
        # Also include income/expense/tax accounts from company chart that have GL activity in period.
        gl_domain = [
            ("company_id", "=", company.id),
            ("parent_state", "in", states),
            ("date", ">=", start),
            ("date", "<=", end),
            ("display_type", "not in", ["line_note", "line_section", "line_subsection"]),
        ]
        if journal_ids:
            gl_domain.append(("journal_id", "in", list(journal_ids)))
        period_lines = self._bounded("account.move.line", gl_domain, order="id asc")
        period_lines.check_access("read")
        for line in period_lines:
            if line.account_id.account_type in ("income", "income_other", "expense", "expense_direct_cost"):
                if register_type == "sale" and not line.account_id.account_type.startswith("income"):
                    continue
                if register_type == "purchase" and not line.account_id.account_type.startswith("expense"):
                    continue
                tracked_accounts.add(line.account_id.id)
            elif line.tax_line_id:
                tracked_accounts.add(line.account_id.id)
        docs_input = [{
            "move_id": move.id,
            "move_name": move.name,
            "move_type": move.move_type,
            "date": str(move.date),
            "invoice_date": str(move.invoice_date or move.date),
            "partner_id": move.partner_id.id or False,
            "state": move.state,
            "lines": lines_by_move.get(move.id, []),
        } for move in moves]
        gl_tuples = [
            (line.id, line.move_id.id, line.account_id.id, line.balance)
            for line in period_lines
            if line.account_id.id in tracked_accounts
        ]
        reconciled = reconcile_register_to_gl(
            docs_input, gl_tuples, tracked_accounts, company.currency_id.round,
        )
        reconciled.update({
            "report_id": "FIN57",
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "date_from": str(start),
            "date_to": str(end),
            "register_type": register_type,
            "only_posted_moves": bool(only_posted_moves),
            "tracked_account_ids": sorted(tracked_accounts),
        })
        return reconciled
