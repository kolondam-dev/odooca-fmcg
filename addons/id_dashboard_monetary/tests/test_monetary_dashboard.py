# Part of odooca-fmcg. License LGPL-3.
from datetime import date, timedelta

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

BUCKETS = ["not_due", "overdue_1_7", "overdue_8_14", "overdue_15_30", "overdue_over_30"]


@tagged("post_install", "-at_install")
class TestMonetaryDashboard(TransactionCase):
    def test_module_installed(self):
        module = self.env["ir.module.module"].search([("name", "=", "id_dashboard_monetary")])
        self.assertEqual(module.state, "installed")

    def test_funnel_has_four_stages_per_target(self):
        target = self.env["id.monetary.target"].create(
            {
                "name": "Test target period",
                "date_from": date.today() - timedelta(days=30),
                "date_to": date.today(),
                "target_revenue": 1000000.0,
            }
        )
        stages = self.env["id.monetary.funnel.stage"].search([("target_id", "=", target.id)])
        self.assertEqual(
            sorted(stages.mapped("stage")),
            ["collection", "realized", "receivable", "target"],
        )
        target_stage = stages.filtered(lambda stage: stage.stage == "target")
        self.assertAlmostEqual(target_stage.amount, 1000000.0, places=2)
        self.assertAlmostEqual(target_stage.achievement_percent, 100.0, places=2)
        self.assertAlmostEqual(target_stage.target_amount, 1000000.0, places=2)

    def test_funnel_amounts_are_numeric(self):
        stages = self.env["id.monetary.funnel.stage"].search([])
        for stage in stages:
            self.assertIsInstance(stage.amount, float)
            self.assertIsInstance(stage.achievement_percent, float)

    def test_ar_aging_view_is_queryable(self):
        aging = self.env["id.ar.aging"]
        records = aging.search([])
        self.assertEqual({k for k, _label in aging._fields["bucket"].selection}, set(BUCKETS))
        for record in records:
            self.assertGreaterEqual(record.days_overdue, 0)
            self.assertIn(record.bucket, BUCKETS)

    def test_customer_balance_view_is_queryable(self):
        balances = self.env["id.ar.customer.balance"].search([], order="amount_residual desc")
        for balance in balances:
            self.assertGreaterEqual(balance.invoice_count, 1)
            self.assertGreaterEqual(balance.max_days_overdue, 0)

    def test_target_period_validation(self):
        with self.assertRaises(ValidationError):
            self.env["id.monetary.target"].create(
                {
                    "name": "Invalid period",
                    "date_from": date.today(),
                    "date_to": date.today() - timedelta(days=1),
                    "target_revenue": 1.0,
                }
            )
