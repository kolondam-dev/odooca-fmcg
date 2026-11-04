from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestOrderMargin(TransactionCase):
    def _source(self, actual=10, cost_amount=600):
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
        moves.write({"quantity": actual, "state": "done"})
        invoices = order._create_invoices()
        invoices.invoice_date = "2025-07-15"
        invoices.action_post()
        journal = self.env["account.journal"].create({"name": "Margin COGS", "code": "OM3", "type": "general"})
        cost = self.env["account.move"].create({"journal_id": journal.id, "date": "2025-07-15",
            "line_ids": [(0, 0, {"account_id": accounts["cost"].id, "product_id": product.id, "debit": cost_amount}),
                         (0, 0, {"account_id": accounts["offset"].id, "product_id": product.id,
                                     "credit": cost_amount})]})
        cost.action_post()
        moves.account_move_id = cost
        return order, moves, invoices, cost, product, accounts, journal

    def test_linked_posted_delivery_cost_and_missing_link(self):
        order, moves, invoices, cost, product, accounts, journal = self._source()
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

    def test_partial_and_return_credit_net_quantities_and_cost(self):
        order, moves, invoices, cost, product, accounts, journal = self._source(actual=6, cost_amount=360)
        service = self.env["id.sales.order.margin"]
        partial = service._for_orders([("id", "=", order.id)])
        self.assertEqual((partial["revenue"], partial["cost"], partial["margin"]), (600, 360, 240))
        returned = self.env["stock.move"].create({"product_id": product.id, "product_uom": product.uom_id.id,
            "product_uom_qty": 2, "quantity": 2, "state": "done", "origin_returned_move_id": moves.id,
            "sale_line_id": order.order_line.id, "location_id": moves.location_dest_id.id,
            "location_dest_id": moves.location_id.id})
        reverse_cost = self.env["account.move"].create({"journal_id": journal.id, "date": "2025-07-16",
            "line_ids": [(0, 0, {"account_id": accounts["cost"].id, "product_id": product.id, "credit": 120}),
                         (0, 0, {"account_id": accounts["offset"].id, "product_id": product.id, "debit": 120})]})
        reverse_cost.action_post()
        returned.account_move_id = reverse_cost
        credit = self.env["account.move"].create({"move_type": "out_refund", "partner_id": order.partner_id.id,
            "invoice_date": "2025-07-16", "invoice_line_ids": [(0, 0, {"product_id": product.id,
                "quantity": 2, "price_unit": 100, "account_id": accounts["income"].id,
                "sale_line_ids": [(6, 0, order.order_line.ids)], "tax_ids": [(5, 0, 0)]})]})
        credit.action_post()
        net = service._for_orders([("id", "=", order.id)])
        self.assertEqual((net["revenue"], net["cost"], net["margin"]), (400, 240, 160))
        returned.account_move_id = False
        self.assertIsNone(service._for_orders([("id", "=", order.id)])["margin"])
