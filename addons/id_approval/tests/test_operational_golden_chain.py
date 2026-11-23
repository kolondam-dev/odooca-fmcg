from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestFmcgOperationalGoldenChain(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        actors = []
        for role in ("manager", "director"):
            group = cls.env.ref(f"id_approval.group_fmcg_approval_{role}")
            if role == "manager":
                group |= cls.env.ref("sales_team.group_sale_manager")
            actors.append(cls.env["res.users"].sudo().create({
                "name": f"Golden Chain {role}", "login": f"golden_chain_{role}",
                "group_ids": [Command.set(group.ids)], "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
            }))
        cls.user_mgr, cls.user_dir = actors
        cls.salesperson = cls.env["res.users"].sudo().create({
            "name": "Golden Chain Sales", "login": "golden_chain_sales",
            "group_ids": [Command.set((
                cls.env.ref("sales_team.group_sale_salesman") | cls.env.ref("id_approval.group_fmcg_approval_user")
            ).ids)],
            "company_id": cls.company.id, "company_ids": [Command.set(cls.company.ids)],
        })
        cls.accountant = cls.env["res.users"].sudo().create({
            "name": "Golden Chain Accountant", "login": "golden_chain_accountant",
            "group_ids": [Command.set((
                cls.env.ref("account.group_account_manager") | cls.env.ref("purchase.group_purchase_user")
            ).ids)],
            "company_id": cls.company.id, "company_ids": [Command.set(cls.company.ids)],
        })
        cls.buyer = cls.env["res.users"].sudo().create({
            "name": "Golden Chain Buyer", "login": "golden_chain_buyer",
            "group_ids": [Command.set(cls.env.ref("purchase.group_purchase_manager").ids)],
            "company_id": cls.company.id, "company_ids": [Command.set(cls.company.ids)],
        })
        cls.warehouse_user = cls.env["res.users"].sudo().create({
            "name": "Golden Chain Warehouse", "login": "golden_chain_warehouse",
            "group_ids": [Command.set(cls.env.ref("stock.group_stock_user").ids)],
            "company_id": cls.company.id, "company_ids": [Command.set(cls.company.ids)],
        })

    def test_golden_order_to_cash_enforces_credit_and_approval(self):
        product = self.product_a
        product.write({
            "type": "consu", "is_storable": True, "tracking": "lot", "invoice_policy": "delivery",
            "standard_price": 10_000, "taxes_id": [Command.clear()],
        })
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        lot = self.env["stock.lot"].create({
            "name": "GOLDEN-CHAIN-LOT", "product_id": product.id, "company_id": self.company.id,
        })
        self.assertEqual(
            self.env["stock.quant"]._get_available_quantity(product, warehouse.lot_stock_id, lot_id=lot), 0,
        )
        purchase = self.env["purchase.order"].with_user(self.buyer).create({
            "partner_id": self.partner_b.id,
            "picking_type_id": warehouse.in_type_id.id,
            "order_line": [Command.create({
                "product_id": product.id, "product_qty": 10, "price_unit": 10_000,
                "tax_ids": [Command.clear()],
            })],
        })
        purchase.button_confirm()
        receipt = purchase.picking_ids.with_user(self.warehouse_user)
        receipt.move_ids.quantity = 10
        receipt.move_line_ids.lot_id = lot
        receipt.move_line_ids.picked = True
        receipt.button_validate()
        self.assertEqual(receipt.state, "done")
        self.assertEqual(purchase.order_line.qty_received, 10)
        self.assertEqual(receipt.move_ids.purchase_line_id, purchase.order_line)
        purchase.with_user(self.accountant).action_create_invoice()
        bill = purchase.with_user(self.accountant).invoice_ids
        bill.invoice_date = fields.Date.today()
        bill.action_post()
        self.assertEqual(bill.invoice_line_ids.purchase_line_id, purchase.order_line)
        self.assertEqual(bill.amount_residual, 100_000)
        partner = self.partner_a
        partner.write({"credit_mode": "limit", "credit_limit": 1_000})

        order = self.env["sale.order"].with_user(self.salesperson).with_context(install_mode=False).create({
            "partner_id": partner.id,
            "warehouse_id": warehouse.id,
            "order_line": [Command.create({
                "product_id": product.id, "product_uom_qty": 2, "price_unit": 8_000,
            })],
        })
        self.assertFalse(order.fmcg_seed_batch)
        self.assertFalse(order.env.context.get("fmcg_seed_load"))
        self.assertTrue(order.credit_limit_exceeded)
        self.assertTrue(order.has_below_hpp)
        with self.assertRaisesRegex(UserError, "DI BAWAH HPP"):
            order.action_confirm()
        self.assertFalse(order.picking_ids)
        rejected_id = order.action_request_below_hpp_approval(reason="Golden chain rejection")["res_id"]
        rejected = self.env["fmcg.approval.request"].browse(rejected_id)
        rejected.with_user(self.user_mgr).action_reject(notes="Reject test request")
        self.assertEqual(rejected.state, "rejected")
        with self.assertRaisesRegex(UserError, "DI BAWAH HPP"):
            order.action_confirm()
        self.assertFalse(order.picking_ids)
        request_id = order.action_request_below_hpp_approval(reason="Golden chain test")["res_id"]
        request = self.env["fmcg.approval.request"].browse(request_id)
        request.with_user(self.user_mgr).action_approve(notes="Tier 1")
        with self.assertRaisesRegex(UserError, "DI BAWAH HPP"):
            order.action_confirm()
        request.with_user(self.user_dir).action_approve(notes="Tier 2")
        self.assertEqual(request.state, "approved")
        with self.assertRaisesRegex(UserError, "melebihi batas kredit"):
            order.action_confirm()
        order.action_request_credit_approval()
        with self.assertRaisesRegex(UserError, "melebihi batas kredit"):
            order.action_confirm()
        with self.assertRaises(AccessError):
            order.action_approve_credit()
        with self.assertRaises(AccessError):
            order.action_reject_credit()
        order.with_user(self.user_mgr).action_reject_credit()
        self.assertEqual(order.credit_approval_state, "rejected")
        with self.assertRaisesRegex(UserError, "melebihi batas kredit"):
            order.action_confirm()
        order.action_request_credit_approval()
        order.with_user(self.user_mgr).action_approve_credit()
        self.assertEqual(order.credit_approved_by, self.user_mgr)
        order.action_confirm()

        picking = order.picking_ids.with_user(self.warehouse_user)
        picking.action_assign()
        self.assertEqual(picking.state, "assigned")
        self.assertEqual(picking.move_line_ids.lot_id, lot)
        picking.move_line_ids.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        self.assertEqual(order.order_line.qty_delivered, 2)
        self.assertEqual(
            self.env["stock.quant"]._get_available_quantity(product, warehouse.lot_stock_id, lot_id=lot),
            8,
        )

        invoice = order._create_invoices().with_user(self.accountant)
        invoice.action_post()
        self.assertEqual(invoice.invoice_line_ids.sale_line_ids, order.order_line)
        self.assertFalse(invoice.is_fmcg_seed_invoice)
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.amount_total, 16_000)
        self.assertEqual(invoice.amount_residual, 16_000)
        bank = self.env["account.journal"].search([
            ("company_id", "=", self.company.id), ("type", "=", "bank"),
        ], limit=1)
        supplier_method = bank.outbound_payment_method_line_ids[:1]
        supplier_method.sudo().payment_account_id = bank.default_account_id
        supplier_payment = self.env["account.payment.register"].with_user(self.accountant).with_context(
            active_model="account.move", active_ids=bill.ids,
        ).create({
            "journal_id": bank.id, "payment_method_line_id": supplier_method.id,
        })._create_payments()
        self.assertEqual(supplier_payment.reconciled_bill_ids, bill)
        self.assertEqual(bill.amount_residual, 0)

        method = bank.inbound_payment_method_line_ids[:1]
        method.sudo().payment_account_id = bank.default_account_id
        payment = self.env["account.payment.register"].with_user(self.accountant).with_context(
            active_model="account.move", active_ids=invoice.ids,
        ).create({
            "journal_id": bank.id, "payment_method_line_id": method.id,
        })._create_payments()
        self.assertIn(invoice, payment.reconciled_invoice_ids)
        self.assertEqual(invoice.amount_residual, 0)
