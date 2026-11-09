"""Enforce report boundaries without copying the OCA calculation engine."""

from odoo import _, models
from odoo.exceptions import AccessError


class TrialBalanceReport(models.AbstractModel):
    _inherit = "report.account_financial_report.trial_balance"

    def _check_finance_scope(self, company_id):
        user = self.env.user
        if not self.env.su and not any(user.has_group(group) for group in (
            "account.group_account_readonly", "account.group_account_user", "account.group_account_manager",
        )):
            raise AccessError(_("Trial Balance requires an authorized accounting role."))
        if not company_id or company_id not in self.env.companies.ids:
            raise AccessError(_("Select a company authorized in the active accounting context."))
        if not self.env.su and company_id not in user.company_ids.ids:
            raise AccessError(_("Select a company authorized in the active accounting context."))

    def _check_filter_company(self, company_id, journal_ids=None, account_ids=None):
        if journal_ids:
            journals = self.env["account.journal"].with_context(active_test=False).browse(journal_ids)
            if any(journal.company_id.id != company_id for journal in journals):
                raise AccessError(_("Selected journal belongs to another company."))
        if account_ids:
            accounts = self.env["account.account"].with_context(active_test=False).browse(account_ids)
            if any(company_id not in account.company_ids.ids for account in accounts):
                raise AccessError(_("Selected account belongs to another company."))

    def _get_data(
        self, account_ids, journal_ids, partner_ids, company_id, date_to, date_from,
        foreign_currency, only_posted_moves, show_partner_details, hide_account_at_0,
        unaffected_earnings_account, fy_start_date, grouped_by,
    ):
        self._check_finance_scope(company_id)
        self._check_filter_company(company_id, journal_ids, account_ids)
        return super()._get_data(
            account_ids, journal_ids, partner_ids, company_id, date_to, date_from,
            foreign_currency, only_posted_moves, show_partner_details, hide_account_at_0,
            unaffected_earnings_account, fy_start_date, grouped_by,
        )

    def _get_report_values(self, docids, data):
        payload = data or {}
        company_id = payload.get("company_id")
        self._check_finance_scope(company_id)
        self._check_filter_company(company_id, payload.get("journal_ids"), payload.get("account_ids"))
        return super()._get_report_values(docids, data)
