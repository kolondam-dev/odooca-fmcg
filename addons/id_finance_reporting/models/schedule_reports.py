"""Server-side bounded models for FIN37 accrual schedules and FIN38 FX revaluation."""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

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

    def _check_partner_filter(self, company, partner_ids):
        """Reject partners that do not exist or belong to another company."""
        if not partner_ids:
            return
        unique_ids = list(dict.fromkeys(partner_ids))
        partners = self.env["res.partner"].with_context(active_test=False).browse(unique_ids)
        if any(not partner.exists() for partner in partners):
            raise UserError(_("Selected partner does not exist."))
        if any(partner.company_id and partner.company_id != company for partner in partners):
            raise AccessError(_("Selected partner belongs to another company."))

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
        scoped._check_partner_filter(company, partner_ids)
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
        scoped._check_partner_filter(company, partner_ids)
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
        # Two maps on purpose:
        # - all_leg_by_id holds every in-scope line, including functional
        #   currency, so a partial leg inside the filter can be classified.
        # - payload holds only foreign-currency, non-exchange lines, which is the
        #   unrealized base.
        all_leg_by_id = {}
        for line in lines:
            account = line.account_id.with_company(company)
            all_leg_by_id[line.id] = {
                "line_id": line.id,
                "move_id": line.move_id.id,
                "account_id": account.id,
                "account_code": account.code or "",
                "account_type": account.account_type,
                "partner_id": line.partner_id.id or 0,
                "partner_name": line.partner_id.display_name or "",
                "currency_id": line.currency_id.id or company.currency_id.id,
                "company_currency_id": company.currency_id.id,
                "balance": line.balance,
                "amount_currency": line.amount_currency,
            }
        for row in all_leg_by_id.values():
            if row["account_id"] in exchange_ids:
                continue
            # FIN38 is a foreign-currency report: functional-currency lines carry
            # no exchange difference and are not part of the unrealized base.
            if row["currency_id"] == company.currency_id.id:
                continue
            payload.append(row)

        partials = self._partials(company, as_of, all_leg_by_id)
        partials = self._resolve_out_of_filter_legs(company, partials)
        report = build_fx_revaluation(
            payload, partials, as_of, round_amt, self._rate_lookup(company),
            exchange_account_ids=exchange_ids,
        )
        scope_limited = bool(journal_ids or partner_ids or account_ids)
        gl_balance = self._exchange_gl_balance(
            company, as_of, exchange_ids, round_amt,
            exchange_move_ids=report["tied_exchange_move_ids"] if scope_limited else None,
        )
        tie_out = tie_fx_to_gl(report, gl_balance, round_amt)
        tie_out["scope_limited"] = scope_limited
        tie_out["scope_note"] = (
            "filtered: comparator restricted to exchange moves reachable from the "
            "in-scope partials" if scope_limited
            else "company-wide: every posted exchange line is compared"
        )
        if scope_limited and report["realized_posted_total"] and not gl_balance:
            # A filtered report that realises FX but finds no exchange evidence
            # must fail loudly instead of balancing against an empty comparator.
            tie_out["balanced"] = False
            tie_out["issues"] = sorted(set(tie_out["issues"]) | {"missing_exchange_evidence"})
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

    def _resolve_out_of_filter_legs(self, company, partials):
        """Load counterpart legs that the report filters excluded.

        A partial can touch a selected line while its other leg sits in a journal
        excluded by ``journal_ids``. Treating a missing leg as a functional-currency
        counterpart silently zeroed realized FX and left an empty comparator that
        balanced vacuously. The counterpart is fetched here for classification
        only; it never enters the unrealized base.
        """
        missing = set()
        for partial in partials:
            for side in ("debit_leg", "credit_leg"):
                if not partial.get(side):
                    line_id = partial.get(f"{side[:-4]}_line_id")
                    if line_id:
                        missing.add(line_id)
        if not missing:
            return partials
        lines = self.env["account.move.line"].with_company(company).browse(sorted(missing))
        lines.check_access("read")
        resolved = {}
        for line in lines:
            if not line.exists() or line.company_id != company:
                continue
            account = line.account_id.with_company(company)
            resolved[line.id] = {
                "line_id": line.id,
                "move_id": line.move_id.id,
                "account_id": account.id,
                "account_code": account.code or "",
                "account_type": account.account_type,
                "partner_id": line.partner_id.id or 0,
                "partner_name": line.partner_id.display_name or "",
                "currency_id": line.currency_id.id or company.currency_id.id,
                "company_currency_id": company.currency_id.id,
                "balance": line.balance,
                "amount_currency": line.amount_currency,
            }
        for partial in partials:
            debit_leg = partial.get("debit_leg") or resolved.get(partial.get("debit_line_id"))
            credit_leg = partial.get("credit_leg") or resolved.get(partial.get("credit_line_id"))
            partial["debit_leg"] = debit_leg or {}
            partial["credit_leg"] = credit_leg or {}
            partial["functional_counterpart"] = self._is_functional_counterpart(
                debit_leg, credit_leg, company,
            )
        return partials

    @staticmethod
    def _is_functional_counterpart(debit_leg, credit_leg, company):
        """True only when one real leg is denominated in the company currency."""
        if not debit_leg or not credit_leg:
            return False
        company_currency = company.currency_id.id
        currencies = {debit_leg.get("currency_id"), credit_leg.get("currency_id")}
        return company_currency in currencies and len(currencies) > 1

    def _partials(self, company, as_of, all_leg_by_id):
        """Load partials that touch any selected line, from either side.

        The domain must stay an ``OR`` on the two legs here, and that is
        deliberate: a partial whose counterpart sits outside the report filters
        still reduces the selected line's residual. Restricting to partials whose
        *both* legs are selected would make a July invoice look open again as soon
        as a bank payment is filtered out by ``journal_ids``. This is the opposite
        of FIN07's slice rule, because FIN07 reports on a slice while FIN38
        reconstructs the true position of the lines it selected.
        """
        if not all_leg_by_id:
            return []
        selected = list(all_leg_by_id)
        records = self._bounded(
            "account.partial.reconcile",
            [
                ("company_id", "=", company.id),
                ("max_date", "<=", as_of),
                "|",
                ("debit_move_id", "in", selected),
                ("credit_move_id", "in", selected),
            ],
            order="max_date asc, id asc",
        )
        records.check_access("read")
        payloads = []
        for record in records:
            debit_leg = all_leg_by_id.get(record.debit_move_id.id)
            credit_leg = all_leg_by_id.get(record.credit_move_id.id)
            if not debit_leg and not credit_leg:
                continue
            debit_move = record.debit_move_id.move_id
            credit_move = record.credit_move_id.move_id
            payloads.append({
                "partial_id": record.id,
                "amount": record.amount,
                "debit_amount_currency": record.debit_amount_currency,
                "credit_amount_currency": record.credit_amount_currency,
                "max_date": record.max_date,
                "exchange_move_id": record.exchange_move_id.id or None,
                "debit_line_id": record.debit_move_id.id,
                "credit_line_id": record.credit_move_id.id,
                "debit_leg": debit_leg or {},
                "credit_leg": credit_leg or {},
                "move_id": debit_move.id,
                "move_ids": sorted({debit_move.id, credit_move.id}),
                "reversed_entry_id": debit_move.reversed_entry_id.id
                or credit_move.reversed_entry_id.id or None,
                "is_reversal": bool(debit_move.reversal_move_ids or credit_move.reversal_move_ids),
                # Classification is finalised after out-of-filter counterparts are
                # resolved; a missing leg is NOT a functional counterpart.
                "functional_counterpart": False,
                "write_off": self._is_write_off_move(debit_move) or self._is_write_off_move(credit_move),
            })
        return payloads

    def _is_write_off_move(self, move):
        """True when a plain entry mixes a monetary line with a non-monetary one.

        In Odoo a write-off reconciles AR against AR: the expense lives on a
        separate line of the same entry, so looking for an expense *leg* on the
        partial never matches. The signal is the counterpart move itself.
        """
        if move.move_type != "entry":
            return False
        account_types = move.line_ids.mapped("account_id.account_type")
        monetary = {
            "asset_receivable", "liability_payable", "asset_cash",
            "liability_credit_card", "asset_current", "liability_current",
            "asset_non_current", "liability_non_current",
        }
        return any(t and t not in monetary for t in account_types) and any(
            t in monetary for t in account_types
        )


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

    def _exchange_gl_balance(self, company, as_of, exchange_ids, round_amt,
                             exchange_move_ids=None):
        """Sum posted exchange gain/loss balances.

        ``exchange_move_ids`` restricts the comparator when the report is
        filtered. Without it the comparator stays company-wide, which is correct
        for an unfiltered report but would compare a filtered realized total
        against every exchange move in the company.
        """
        if not exchange_ids:
            return {}
        domain = [
            ("company_id", "=", company.id),
            ("account_id", "in", list(exchange_ids)),
            ("date", "<=", as_of),
            ("parent_state", "=", "posted"),
            ("display_type", "not in", ["line_note", "line_section", "line_subsection"]),
        ]
        if exchange_move_ids is not None:
            if not exchange_move_ids:
                return {}
            domain.append(("move_id", "in", list(exchange_move_ids)))
        lines = self.env["account.move.line"].search(domain)
        lines.check_access("read")
        totals = {}
        for line in lines:
            currency_id = line.currency_id.id or company.currency_id.id
            totals[currency_id] = round_amt(totals.get(currency_id, 0.0) + line.balance)
        return totals
