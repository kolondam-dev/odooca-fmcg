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
