"""Server-side bounded models for FIN05-FIN09 AR/AP subledger reports."""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .ledger_subledger import (
    AGING_EDGES,
    build_aging,
    build_partner_ledger,
    reconstruct_open_items,
    resolve_partner_types,
    tie_subledger_to_gl,
)


class FinanceSubledgerMixin(models.AbstractModel):
    _name = "id.finance.subledger.mixin"
    _inherit = "id.finance.ledger.mixin"
    _description = "Finance AR/AP Subledger Bounded Query Mixin"

    def _partner_types(self, partner_type):
        try:
            return resolve_partner_types(partner_type)
        except ValueError as exc:
            raise UserError(
                _("Invalid partner type; choose customer, supplier or all.")
            ) from exc

    def _check_as_of(self, as_of_date):
        as_of = fields.Date.to_date(as_of_date)
        if not as_of:
            raise UserError(_("Select a single as-of date for AR/AP open items."))
        return as_of

    def _check_partner_filter(self, company, partner_ids):
        if not partner_ids:
            return
        unique_ids = list(dict.fromkeys(partner_ids))
        partners = self.env["res.partner"].with_context(active_test=False).browse(unique_ids)
        if any(not partner.exists() for partner in partners):
            raise UserError(_("Selected partner does not exist."))
        if any(partner.company_id and partner.company_id != company for partner in partners):
            raise AccessError(_("Selected partner belongs to another company."))

    def _control_accounts(self, company, partner_types):
        return self.env["account.account"].with_context(active_test=False).search([
            ("company_ids", "in", company.ids),
            ("account_type", "in", list(partner_types)),
        ])

    def _collect_control_lines(
        self, company, accounts, date_to, only_posted_moves, journal_ids,
        partner_ids, date_from=None,
    ):
        if not accounts:
            return self.env["account.move.line"]
        domain = [
            ("company_id", "=", company.id),
            ("account_id", "in", accounts.ids),
            ("date", "<=", date_to),
            ("display_type", "not in", ["line_note", "line_section", "line_subsection"]),
        ]
        if date_from:
            domain.append(("date", ">", date_from))
        if journal_ids:
            domain.append(("journal_id", "in", list(journal_ids)))
        if partner_ids:
            domain.append(("partner_id", "in", list(partner_ids)))
        states = ["posted"] if only_posted_moves else ["posted", "draft"]
        domain.append(("parent_state", "in", states))
        lines = self._bounded(
            "account.move.line", domain, order="date asc, move_id asc, id asc",
        )
        lines.check_access("read")
        return lines

    def _line_payload(self, company, line):
        round_amt = company.currency_id.round
        account = line.account_id.with_company(company)
        partner = line.partner_id
        return {
            "line_id": line.id,
            "move_id": line.move_id.id,
            "move_name": line.move_id.name or "",
            "date": line.date,
            "due_date": line.date_maturity or line.date,
            "partner_id": partner.id or 0,
            "partner_name": partner.display_name or "",
            "account_id": account.id,
            "account_code": account.code or "",
            "account_type": account.account_type,
            "debit": round_amt(line.debit),
            "credit": round_amt(line.credit),
            "balance": round_amt(line.balance),
            "currency_id": line.currency_id.id or company.currency_id.id,
            "amount_currency": line.amount_currency,
        }

    def _partial_payloads(self, company, line_ids, as_of):
        """Return dated partials whose *both* legs are inside the selection.

        ``journal_ids``/``date_from``/``partner_ids`` define the report slice
        and therefore also define which reconciliations may be consumed. A
        partial whose counterpart sits outside the slice must stay out of the
        reconstruction, otherwise a filtered invoice would look settled while
        ``gl_control_total`` still counts its full balance.
        """
        if not line_ids:
            return []
        selected = list(line_ids)
        domain = [
            ("company_id", "=", company.id),
            ("max_date", "<=", as_of),
            ("debit_move_id", "in", selected),
            ("credit_move_id", "in", selected),
        ]
        partials = self._bounded(
            "account.partial.reconcile", domain, order="max_date asc, id asc",
        )
        partials.check_access("read")
        return [{
            "partial_id": partial.id,
            "debit_line_id": partial.debit_move_id.id,
            "credit_line_id": partial.credit_move_id.id,
            "amount": partial.amount,
            "max_date": partial.max_date,
        } for partial in partials]

    def _open_items_result(
        self, company, partner_types, as_of, only_posted_moves, partner_ids,
        journal_ids, date_from=None,
    ):
        accounts = self._control_accounts(company, partner_types)
        lines = self._collect_control_lines(
            company, accounts, as_of, only_posted_moves, journal_ids,
            partner_ids, date_from=date_from,
        )
        payload = [self._line_payload(company, line) for line in lines]
        partials = self._partial_payloads(company, lines.ids, as_of)
        round_amt = company.currency_id.round
        result = reconstruct_open_items(
            payload, partials, as_of, round_amt, partner_types,
        )
        # Both legs of an applied partial always sit inside the same slice, so
        # their matched amounts cancel and sum(residual) == sum(balance).
        gl_control_total = round_amt(sum(item["balance"] for item in payload))
        result.update({
            "partial_scope": "both_legs_selected",
            "gl_control_total": gl_control_total,
            "gl_tie_out": tie_subledger_to_gl(
                result["total_residual"], gl_control_total, round_amt, label="open_items",
            ),
        })
        return result

    def _report_ids(self, partner_type, customer_id, supplier_id):
        if partner_type == "customer":
            return [customer_id]
        if partner_type == "supplier":
            return [supplier_id]
        return [customer_id, supplier_id]


class FinancePartnerLedger(models.AbstractModel):
    _name = "id.finance.partner.ledger"
    _inherit = "id.finance.subledger.mixin"
    _description = "Partner Ledger AR/AP (FIN05/FIN06)"

    @api.model
    def _snapshot(
        self, company_id, date_from, date_to, partner_type="customer",
        only_posted_moves=True, partner_ids=None, journal_ids=None,
    ):
        partner_types = self._partner_types(partner_type)
        start, end = self._check_period(date_from, date_to)
        company = self.env["res.company"].browse(company_id)
        self._check_partner_filter(company, partner_ids)
        accounts = self._control_accounts(company, partner_types)
        self._check_scope(company_id, journal_ids, accounts.ids)
        scoped = self.with_context(allowed_company_ids=[company_id]).with_company(company)
        return scoped._snapshot_partner_ledger(
            company, partner_types, partner_type, start, end,
            only_posted_moves, partner_ids, journal_ids, accounts,
        )

    def _snapshot_partner_ledger(
        self, company, partner_types, partner_type, start, end,
        only_posted_moves, partner_ids, journal_ids, accounts,
    ):
        lines = self._collect_control_lines(
            company, accounts, end, only_posted_moves, journal_ids, partner_ids,
        )
        payload = [self._line_payload(company, line) for line in lines]
        round_amt = company.currency_id.round
        ledger = build_partner_ledger(
            payload, start, end, round_amt, partner_types,
        )
        gl_control_total = round_amt(sum(item["balance"] for item in payload))
        report_ids = self._report_ids(partner_type, "FIN05", "FIN06")
        return {
            "report_id": "+".join(report_ids),
            "report_ids": report_ids,
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "date_from": str(start),
            "date_to": str(end),
            "partner_type": partner_type,
            "only_posted_moves": bool(only_posted_moves),
            "journal_ids": sorted(journal_ids or []),
            "partner_ids": sorted(partner_ids or []),
            **ledger,
            "gl_control_total": gl_control_total,
            "gl_tie_out": tie_subledger_to_gl(
                ledger["totals"]["closing_balance"], gl_control_total,
                round_amt, label="partner_ledger",
            ),
        }


class FinanceOpenItems(models.AbstractModel):
    _name = "id.finance.open.items"
    _inherit = "id.finance.subledger.mixin"
    _description = "AR/AP Open Items as of Date (FIN07)"

    @api.model
    def _snapshot(
        self, company_id, as_of_date, partner_type="customer",
        only_posted_moves=True, partner_ids=None, journal_ids=None,
        date_from=None,
    ):
        partner_types = self._partner_types(partner_type)
        as_of = self._check_as_of(as_of_date)
        start = fields.Date.to_date(date_from) if date_from else None
        if start and start > as_of:
            raise UserError(
                _("The as-of date must be on or after the optional start date.")
            )
        company = self.env["res.company"].browse(company_id)
        self._check_partner_filter(company, partner_ids)
        accounts = self._control_accounts(company, partner_types)
        self._check_scope(company_id, journal_ids, accounts.ids)
        scoped = self.with_context(allowed_company_ids=[company_id]).with_company(company)
        result = scoped._open_items_result(
            company, partner_types, as_of, only_posted_moves, partner_ids,
            journal_ids, date_from=start,
        )
        report_ids = ["FIN07"]
        return {
            "report_id": "FIN07",
            "report_ids": report_ids,
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "as_of_date": str(as_of),
            "date_from": str(start) if start else None,
            "partner_type": partner_type,
            "only_posted_moves": bool(only_posted_moves),
            "journal_ids": sorted(journal_ids or []),
            "partner_ids": sorted(partner_ids or []),
            **result,
        }


class FinanceAgedPartnerBalance(models.AbstractModel):
    _name = "id.finance.aged.partner.balance"
    _inherit = "id.finance.subledger.mixin"
    _description = "Aged Receivable/Payable (FIN08/FIN09)"

    @api.model
    def _snapshot(
        self, company_id, as_of_date, partner_type="customer",
        only_posted_moves=True, partner_ids=None, journal_ids=None,
        date_from=None, bucket_edges=None,
    ):
        partner_types = self._partner_types(partner_type)
        as_of = self._check_as_of(as_of_date)
        start = fields.Date.to_date(date_from) if date_from else None
        if start and start > as_of:
            raise UserError(
                _("The as-of date must be on or after the optional start date.")
            )
        edges = tuple(int(edge) for edge in (bucket_edges or AGING_EDGES))
        if not edges or any(edge <= 0 for edge in edges) or list(edges) != sorted(set(edges)):
            raise UserError(
                _("Aging bucket edges must be positive and strictly increasing.")
            )
        company = self.env["res.company"].browse(company_id)
        self._check_partner_filter(company, partner_ids)
        accounts = self._control_accounts(company, partner_types)
        self._check_scope(company_id, journal_ids, accounts.ids)
        scoped = self.with_context(allowed_company_ids=[company_id]).with_company(company)
        result = scoped._open_items_result(
            company, partner_types, as_of, only_posted_moves, partner_ids,
            journal_ids, date_from=start,
        )
        aging = build_aging(result, as_of, company.currency_id.round, edges)
        report_ids = self._report_ids(partner_type, "FIN08", "FIN09")
        return {
            "report_id": "+".join(report_ids),
            "report_ids": report_ids,
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "as_of_date": str(as_of),
            "date_from": str(start) if start else None,
            "partner_type": partner_type,
            "only_posted_moves": bool(only_posted_moves),
            "journal_ids": sorted(journal_ids or []),
            "partner_ids": sorted(partner_ids or []),
            "open_items_total_residual": result["total_residual"],
            "partnerless_residual": result["partnerless_residual"],
            "partnerless_line_ids": result["partnerless_line_ids"],
            "partial_scope": result["partial_scope"],
            "gl_control_total": result["gl_control_total"],
            "gl_tie_out": result["gl_tie_out"],
            **aging,
        }
