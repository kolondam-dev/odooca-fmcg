from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestOrderMargin(TransactionCase):
    def test_linked_posted_delivery_cost_and_missing_link(self):
        self.env.company.currency_id.active = True
        accounts = {}
        for key, kind, code in [("income", "income", "991501"), ("cost", "expense_direct_cost", "991502"),
                                 ("offset", "asset_current", "991503"), ("ar", "asset_receivable", "991504")]:
            accounts[key] = self.env["account.account"].create({"name": "Margin " + key, "code": code,
                "account_type": kind, "reconcile": kind == "asset_receivable",
                "company_ids": [(6, 0, self.env.company.ids)]})
        partner = self.env["res.partner"].create({"name": "Order margin customer",
            "property_account_receivable_id": accounts["ar"].id})
        product = self.env["product.product"].create({"name": "Margin physical SKU", "type": "consu",
            "is_storable": True, "invoice_policy": "delivery", "property_account_income_id": accounts["income"].id})
        order = self.env["sale.order"].create({"partner_id": partner.id,
            "pricelist_id": self.env["product.pricelist"].create({"name": "Margin currency",
                "currency_id": self.env.company.currency_id.id}).id,
            "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": 10,
                "price_unit": 100, "tax_ids": [(5, 0, 0)]})]})
        order.action_confirm()
        moves = order.order_line.move_ids
        moves.write({"quantity": 10, "state": "done"})
        invoices = order._create_invoices()
        invoices.invoice_date = "2025-07-15"
        invoices.action_post()
        journal = self.env["account.journal"].create({"name": "Margin COGS", "code": "OM3", "type": "general"})
        cost = self.env["account.move"].create({"journal_id": journal.id, "date": "2025-07-15",
            "line_ids": [(0, 0, {"account_id": accounts["cost"].id, "product_id": product.id, "debit": 600}),
                         (0, 0, {"account_id": accounts["offset"].id, "product_id": product.id, "credit": 600})]})
        cost.action_post()
        moves.account_move_id = cost
        result = self.env["id.sales.order.margin"]._for_orders([("id", "=", order.id)])
        self.assertEqual(result["covered"], 1)
        self.assertEqual((result["revenue"], result["cost"], result["margin"]), (1000, 600, 400))
        self.assertEqual(result["rows"][0]["journal_ids"], cost.ids)
        cost_line = cost.line_ids.filtered(lambda line: line.account_id == accounts["cost"])
        cost_line.product_id = False
        ambiguous = self.env["id.sales.order.margin"]._for_orders([("id", "=", order.id)])
        self.assertEqual(ambiguous["covered"], 0)
        self.assertIsNone(ambiguous["margin"])
        cost_line.product_id = product
        moves.account_move_id = False
        missing = self.env["id.sales.order.margin"]._for_orders([("id", "=", order.id)])
        self.assertEqual(missing["covered"], 0)
        self.assertIsNone(missing["margin"])
        self.assertEqual(missing["rows"][0]["reason"], "missing_cogs_link")

    def test_sales_role_has_no_cost_payload(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Margin salesman", "login": "margin_salesman",
            "group_ids": [(6, 0, [self.env.ref("sales_team.group_sale_salesman").id])]})
        result = self.env["id.sales.order.margin"].with_user(user)._for_orders([])
        self.assertFalse(result["available"])
        self.assertEqual(result["rows"], [])
        self.assertNotIn("cost", result)
