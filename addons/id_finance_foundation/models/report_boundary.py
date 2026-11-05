"""Render guards before OCA report queries; no copy of report calculations."""

from odoo import models


def check_scope(report, data):
    report.env["report.account_financial_report.trial_balance"]._check_finance_scope((data or {}).get("company_id"))


class GeneralLedger(models.AbstractModel):
    _inherit = "report.account_financial_report.general_ledger"

    def _get_report_values(self, docids, data):
        check_scope(self, data)
        return super()._get_report_values(docids, data)


class JournalLedger(models.AbstractModel):
    _inherit = "report.account_financial_report.journal_ledger"

    def _get_report_values(self, docids, data):
        check_scope(self, data)
        return super()._get_report_values(docids, data)


class OpenItems(models.AbstractModel):
    _inherit = "report.account_financial_report.open_items"

    def _get_report_values(self, docids, data):
        check_scope(self, data)
        return super()._get_report_values(docids, data)


class AgedPartnerBalance(models.AbstractModel):
    _inherit = "report.account_financial_report.aged_partner_balance"

    def _get_report_values(self, docids, data):
        check_scope(self, data)
        return super()._get_report_values(docids, data)
