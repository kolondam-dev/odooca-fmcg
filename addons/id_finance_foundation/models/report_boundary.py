"""Render guards before OCA report queries; no copy of report calculations."""

from odoo import models


def check_scope(report, data):
    payload = data or {}
    company_id = payload.get("company_id")
    tb = report.env["report.account_financial_report.trial_balance"]
    tb._check_finance_scope(company_id)
    tb._check_filter_company(company_id, payload.get("journal_ids"), payload.get("account_ids"))


class GeneralLedger(models.AbstractModel):
    _inherit = "report.account_financial_report.general_ledger"

    def _get_report_values(self, docids, data):
        check_scope(self, data)
        payload = dict(data or {})
        if payload.get("journal_ids"):
            payload["domain"] = list(payload.get("domain") or []) + [
                ("journal_id", "in", list(payload["journal_ids"])),
            ]
        return super()._get_report_values(docids, payload)


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
