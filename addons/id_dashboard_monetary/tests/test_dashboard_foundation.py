from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMonetaryFoundation(TransactionCase):
    def test_customer_overdue_reconciles_filtered_invoices(self):
        partner = self.env["res.partner"].create({"name": "Mixed aging customer"})
        common = {"partner_id": [partner.id, partner.name], "company_id": [self.env.company.id, "Company"],
                  "salesman_id": [self.env.uid, "Owner"], "area_id": False}
        rows = [dict(common, amount_residual=10000000, bucket="not_due"),
                dict(common, amount_residual=1000000, bucket="overdue_1_7")]
        aging = self.env["id.ar.aging"]
        with patch.object(type(aging), "search_read", return_value=rows):
            result = self.env["id.monetary.dashboard"].get_data()
        self.assertEqual(result["kpi"]["overdue_ar"], 1000000)
        customer = result["top_customers"][0]
        self.assertEqual(customer["total_balance"], 11000000)
        self.assertEqual(customer["overdue_balance"], 1000000)
        self.assertEqual(customer["open_count"], 2)

    def test_exact_period_combines_company_targets_without_overwrite(self):
        other = self.env["res.company"].create({
            "name": "Budget company B", "currency_id": self.env.company.currency_id.id})
        for company, amount in [(self.env.company, 10000000), (other, 20000000)]:
            self.env["id.monetary.target"].create({"name": "Comparable budget", "date_from": "2025-01-01",
                "date_to": "2025-01-31", "target_revenue": amount, "company_id": company.id,
                "currency_id": company.currency_id.id})
        service = self.env["id.monetary.dashboard"].with_context(allowed_company_ids=[self.env.company.id, other.id])
        data = service.get_data(period_key="2025-01-01/2025-01-31")
        self.assertEqual(data["kpi"]["target_revenue"], 30000000)
        self.assertEqual(len(data["period"]["target_ids"]), 2)
        with self.assertRaises(UserError):
            service.get_data(period_key="1900-01-01/1900-01-31")

    def test_direct_view_reads_require_finance_role_and_company(self):
        other = self.env["res.company"].create({"name": "Restricted budget B"})
        foreign = self.env["id.monetary.target"].create({"name": "Foreign budget", "date_from": "2025-02-01",
            "date_to": "2025-02-28", "target_revenue": 50000000, "company_id": other.id,
            "currency_id": other.currency_id.id})
        basic = self.env["res.users"].with_context(no_reset_password=True).create({"name": "Basic dashboard probe",
            "login": "basic_dashboard_probe", "company_id": self.env.company.id,
            "company_ids": [(6, 0, [self.env.company.id])],
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])]})
        for model in ["id.ar.aging", "id.ar.customer.balance", "id.monetary.funnel.stage", "id.monetary.target"]:
            with self.assertRaises(AccessError):
                self.env[model].with_user(basic).search([])
        basic.group_ids = [(4, self.env.ref("account.group_account_invoice").id)]
        view = self.env["id.monetary.funnel.stage"]
        self.assertEqual(view.sudo().search_count([("target_id", "=", foreign.id)]), 4)
        self.assertFalse(view.with_user(basic).search([("target_id", "=", foreign.id)]))
        self.assertFalse(self.env["id.monetary.target"].with_user(basic).search([("id", "=", foreign.id)]))


    def test_book_margin_uses_posted_accounting_date_and_signed_ledger(self):
        accounts = {}
        for key, kind, code in [("income", "income", "990101"), ("cost", "expense_direct_cost", "990102"),
                                 ("offset", "asset_current", "990103")]:
            accounts[key] = self.env["account.account"].create({
                "name": "Book margin " + key, "code": code, "account_type": kind,
                "company_ids": [(6, 0, [self.env.company.id])]})
        journal = self.env["account.journal"].create({"name": "Book margin test", "code": "BM3", "type": "general"})
        def entry(day, revenue, cost, posted=True):
            move = self.env["account.move"].create({"date": day, "journal_id": journal.id, "move_type": "entry",
                "line_ids": [(0, 0, {"account_id": accounts["income"].id, "credit": max(revenue, 0),
                                      "debit": max(-revenue, 0)}),
                             (0, 0, {"account_id": accounts["cost"].id, "debit": max(cost, 0),
                                      "credit": max(-cost, 0)}),
                             (0, 0, {"account_id": accounts["offset"].id, "debit": max(revenue-cost, 0),
                                      "credit": max(cost-revenue, 0)})]})
            if posted:
                move.action_post()
        entry("2025-01-15", 2000, 1200)
        entry("2025-01-16", -100, -60)
        entry("2025-01-17", 500, 100, posted=False)
        entry("2025-02-01", 9999, 1)
        self.env.flush_all()
        period = {"key": "2025-01-01/2025-01-31", "companies": [self.env.company.id]}
        margin = self.env["id.monetary.book.margin"]._for_period(period)
        self.assertTrue(margin["available"])
        self.assertEqual((margin["revenue"], margin["direct_cost"], margin["margin"]), (1900, 1140, 760))
        self.assertEqual(margin["rate"], 0.4)
        empty = self.env["id.monetary.book.margin"]._for_period({
            "key": "1900-01-01/1900-01-31", "companies": [self.env.company.id]})
        self.assertFalse(empty["available"])
        self.assertIsNone(empty["margin"])

    def test_book_margin_does_not_expose_cost_to_invoice_only_role(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Invoice only", "login": "margin_invoice_only",
            "group_ids": [(6, 0, [self.env.ref("account.group_account_invoice").id])]})
        result = self.env["id.monetary.book.margin"].with_user(user)._for_period({
            "key": "2025-01-01/2025-01-31", "companies": [self.env.company.id]})
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "accounting_role_required")
        self.assertIsNone(result["direct_cost"])
        self.assertEqual(result["domain"], [])
