"""Server-side bounded models for FIN37 accrual schedules and FIN38 FX revaluation."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .ledger_schedules import (
    build_accrual_schedules,
    build_fx_revaluation,
    tie_fx_to_gl,
)

LIMIT = 20000


class FinanceScheduleMixin(models.AbstractModel):
    _name = "id.finance.schedule.mixin"
    _inherit = "id.finance.ledger.mixin"
    _description = "Finance I2c Schedule Bounded Query Mixin"

    def _check_as_of(self, as_of_date):
        as_of = fields.Date.to_date(as_of_date)
        if not as_of:
            raise UserError(_("Select a single as-of date for schedule reports."))
        return as_of

    def _has_start_end_dates(self):
        """True when account.move.line exposes the OCA schedule metadata."""
        return "start_date" in self.env["account.move.line"]._fields and (
            "end_date" in self.env["account.move.line"]._fields
        )


class FinanceAccrualSchedule(models.AbstractModel):
    _name = "id.finance.accrual.schedule"
    _inherit = "id.finance.schedule.mixin"
    _description = "Accrual / Prepayment / Deferred Schedules (FIN37)"

    @api.model
    def _snapshot(
        self, company_id, as_of_date, account_ids=None, journal_ids=None,
        partner_ids=None, only_posted_moves=True,
    ):
        as_of = self._check_as_of(as_of_date)
        company = self.env["res.company"].browse(company_id)
        self._check_scope(company_id, journal_ids, account_ids)
        scoped = self.with_context(allowed_company_ids=[company_id]).with_company(company)
        return scoped._build(
            company, as_of, account_ids, journal_ids, partner_ids, only_posted_moves,
        )

    def _collect(self, company, as_of, account_ids, journal_ids, partner_ids, only_posted_moves):
        domain = [
            ("company_id", "=", company.id),
            ("date", "<=", as_of),
            ("display_type", "not in", ["line_note", "line_section", "line_subsection"]),
        ]
        if account_ids:
            domain.append(("account_id", "in", list(account_ids)))
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

    def _build(self, company, as_of, account_ids, journal_ids, partner_ids, only_posted_moves):
        lines = self._collect(
            company, as_of, account_ids, journal_ids, partner_ids, only_posted_moves,
        )
        metadata = self._has_start_end_dates()
        payload = []
        for line in lines:
            account = line.account_id.with_company(company)
            payload.append({
                "line_id": line.id,
                "move_id": line.move_id.id,
                "move_name": line.move_id.name or "",
                "date": line.date,
                "account_id": account.id,
                "account_code": account.code or "",
                "account_type": account.account_type,
                "partner_id": line.partner_id.id or 0,
                "partner_name": line.partner_id.display_name or "",
                "balance": company.currency_id.round(line.balance),
                # Undefined when the OCA metadata module is not installed, which
                # makes every row an explicit exception instead of an assumed
                # schedule.
                "start_date": getattr(line, "start_date", None) if metadata else None,
                "end_date": getattr(line, "end_date", None) if metadata else None,
            })
        result = build_accrual_schedules(payload, as_of, company.currency_id.round)
        return {
            "report_id": "FIN37",
            "report_ids": ["FIN37"],
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "as_of_date": str(as_of),
            "only_posted_moves": bool(only_posted_moves),
            "schedule_metadata_available": metadata,
            "journal_ids": sorted(journal_ids or []),
            "partner_ids": sorted(partner_ids or []),
            "account_ids": sorted(account_ids or []),
            **result,
        }


class FinanceFxRevaluation(models.AbstractModel):
    _name = "id.finance.fx.revaluation"
    _inherit = "id.finance.schedule.mixin"
    _description = "Foreign Currency / FX Revaluation (FIN38)"

    @api.model
    def _snapshot(
        self, company_id, as_of_date, account_ids=None, journal_ids=None,
        partner_ids=None, only_posted_moves=True,
    ):
        as_of = self._check_as_of(as_of_date)
        company = self.env["res.company"].browse(company_id)
        self._check_scope(company_id, journal_ids, account_ids)
        scoped = self.with_context(allowed_company_ids=[company_id]).with_company(company)
        return scoped._build(
            company, as_of, account_ids, journal_ids, partner_ids, only_posted_moves,
        )

    def _monetary_lines(self, company, as_of, account_ids, journal_ids, partner_ids,
                        only_posted_moves):
        domain = [
            ("company_id", "=", company.id),
            ("date", "<=", as_of),
            ("account_id.account_type", "in", [
                "asset_receivable", "liability_payable", "asset_cash", "liability_credit_card",
                "asset_current", "liability_current", "asset_non_current",
                "liability_non_current",
            ]),
            ("display_type", "not in", ["line_note", "line_section", "line_subsection"]),
        ]
        if account_ids:
            domain.append(("account_id", "in", list(account_ids)))
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

    def _exchange_accounts(self, company):
        ids = set()
        for company_field in (
            "income_currency_exchange_account_id",
            "expense_currency_exchange_account_id",
        ):
            account = getattr(company, company_field, None)
            if account:
                ids.add(account.id)
        return ids

    def _build(self, company, as_of, account_ids, journal_ids, partner_ids, only_posted_moves):
        round_amt = company.currency_id.round
        lines = self._monetary_lines(
            company, as_of, account_ids, journal_ids, partner_ids, only_posted_moves,
        )
        exchange_ids = self._exchange_accounts(company)
        payload = []
        leg_by_id = {}
        for line in lines:
            account = line.account_id.with_company(company)
            currency_id = line.currency_id.id or company.currency_id.id
            # FIN38 is a foreign-currency report. Functional-currency lines carry
            # no exchange difference and must not enter the partial scope, or a
            # same-currency settlement would be reported as unposted FX evidence.
            if currency_id == company.currency_id.id:
                continue
            row = {
                "line_id": line.id,
                "move_id": line.move_id.id,
                "account_id": account.id,
                "account_code": account.code or "",
                "account_type": account.account_type,
                "partner_id": line.partner_id.id or 0,
                "partner_name": line.partner_id.display_name or "",
                "currency_id": currency_id,
                "company_currency_id": company.currency_id.id,
                "balance": line.balance,
                "amount_currency": line.amount_currency,
                "amount_residual": line.amount_residual,
                "amount_residual_currency": line.amount_residual_currency,
            }
            leg_by_id[line.id] = row
            if account.id in exchange_ids:
                continue
            if not round_amt(row["amount_residual"]) and not round_amt(
                row["amount_residual_currency"]
            ):
                continue
            payload.append(row)

        partials = self._partials(company, as_of, leg_by_id)
        report = build_fx_revaluation(
            payload, partials, as_of, round_amt, self._rate_lookup(company),
            exchange_account_ids=exchange_ids,
        )
        gl_balance = self._exchange_gl_balance(company, as_of, exchange_ids, round_amt)
        tie_out = tie_fx_to_gl(report, gl_balance, round_amt)
        return {
            "report_id": "FIN38",
            "report_ids": ["FIN38"],
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "as_of_date": str(as_of),
            "only_posted_moves": bool(only_posted_moves),
            "journal_ids": sorted(journal_ids or []),
            "partner_ids": sorted(partner_ids or []),
            "account_ids": sorted(account_ids or []),
            "exchange_account_ids": sorted(exchange_ids),
            **report,
            "gl_tie_out": tie_out,
        }

    def _partials(self, company, as_of, leg_by_id):
        if not leg_by_id:
            return []
        selected = list(leg_by_id)
        records = self._bounded(
            "account.partial.reconcile",
            [
                ("company_id", "=", company.id),
                ("max_date", "<=", as_of),
                ("debit_move_id", "in", selected),
                ("credit_move_id", "in", selected),
            ],
            order="max_date asc, id asc",
        )
        records.check_access("read")
        payloads = []
        for record in records:
            debit_leg = leg_by_id.get(record.debit_move_id.id)
            credit_leg = leg_by_id.get(record.credit_move_id.id)
            # Defensive: both legs must be foreign-currency lines inside the
            # FIN38 scope. A same-currency counterpart has no exchange
            # difference and must not be reported as unposted FX evidence.
            if not debit_leg or not credit_leg:
                continue
            payloads.append({
                "partial_id": record.id,
                "amount": record.amount,
                "debit_amount_currency": record.debit_amount_currency,
                "credit_amount_currency": record.credit_amount_currency,
                "max_date": record.max_date,
                "exchange_move_id": record.exchange_move_id.id or None,
                "debit_line_id": record.debit_move_id.id,
                "credit_line_id": record.credit_move_id.id,
                "debit_leg": debit_leg,
                "credit_leg": credit_leg,
            })
        return payloads

    def _rate_lookup(self, company):
        currency_model = self.env["res.currency"]

        def lookup(currency_id, as_of):
            currency = currency_model.browse(currency_id)
            if not currency:
                return None
            return currency._get_conversion_rate(
                currency, company.currency_id, company, as_of,
            )

        return lookup

    def _exchange_gl_balance(self, company, as_of, exchange_ids, round_amt):
        if not exchange_ids:
            return {}
        lines = self.env["account.move.line"].search([
            ("company_id", "=", company.id),
            ("account_id", "in", list(exchange_ids)),
            ("date", "<=", as_of),
            ("parent_state", "=", "posted"),
            ("display_type", "not in", ["line_note", "line_section", "line_subsection"]),
        ])
        lines.check_access("read")
        totals = {}
        for line in lines:
            currency_id = line.currency_id.id or company.currency_id.id
            totals[currency_id] = round_amt(totals.get(currency_id, 0.0) + line.balance)
        return totals
