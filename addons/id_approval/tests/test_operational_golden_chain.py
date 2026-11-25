from datetime import timedelta

from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError, UserError, ValidationError
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
        cls.supervisor = cls.env["res.users"].sudo().create({
            "name": "Golden Chain Supervisor", "login": "golden_chain_supervisor",
            "group_ids": [Command.set(cls.env.ref("id_approval.group_fmcg_approval_supervisor").ids)],
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


    def test_tactical_line_stack_and_footer_to_reconciliation(self):
        product = self.product_a
        product.write({
            "type": "consu", "is_storable": True, "tracking": "lot", "invoice_policy": "delivery",
            "standard_price": 100_000, "taxes_id": [Command.clear()],
        })
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        lot = self.env["stock.lot"].create({
            "name": "COMMERCIAL-GOLDEN-LOT", "product_id": product.id, "company_id": self.company.id,
        })
        self.env["stock.quant"]._update_available_quantity(product, warehouse.lot_stock_id, 1, lot_id=lot)
        order = self.env["sale.order"].with_user(self.salesperson).with_context(install_mode=False).create({
            "partner_id": self.partner_a.id, "warehouse_id": warehouse.id,
            "order_line": [Command.create({
                "product_id": product.id, "product_uom_qty": 1, "price_unit": 1_000_000,
            })],
        })
        steps = {str(order.order_line.id): [5, 1]}
        with self.assertRaisesRegex(UserError, "footer melebihi"):
            order.action_apply_tactical_components(steps, 940_501)
        order.action_apply_tactical_components(steps, 40_500)
        self.assertEqual(order.order_line.discount, 10)
        self.assertEqual(order.amount_untaxed, 900_000)
        with self.assertRaises(UserError):
            order.action_confirm()
        with self.assertRaises(UserError):
            order.with_context(fmcg_seed_load=True).action_confirm()
        self.assertFalse(order.picking_ids)
        request = order._mobile_auto_request_approvals("Commercial golden chain")
        self.assertEqual(request.category_code, "tactical_discount")
        self.assertEqual(len(request.line_ids), 3)
        with self.assertRaises(AccessError):
            request.with_user(self.salesperson).action_approve()
        with self.assertRaises(AccessError):
            request.with_user(self.salesperson).write({"state": "approved"})
        with self.assertRaises(AccessError):
            request.line_ids[:1].with_user(self.salesperson).write({"state": "approved"})
        for approver in (self.supervisor, self.user_mgr):
            request.with_user(approver).action_approve()
            with self.assertRaises(UserError):
                order.action_confirm()
        request.with_user(self.user_dir).action_approve()
        # Changing the decomposition and compensating footer preserves the exact total.
        order.action_apply_tactical_components({str(order.order_line.id): [5]}, 50_000)
        self.assertEqual(order.amount_untaxed, 900_000)
        with self.assertRaisesRegex(UserError, "Komposisi komersial berubah"):
            order.action_confirm()
        order.action_apply_tactical_components(steps, 40_500)
        order.action_confirm()

        self._settle_commercial_sale(order, lot)

    def _settle_commercial_sale(self, order, lots, expected=900_000, expected_lines=None, expected_tax=0):
        picking = order.picking_ids.with_user(self.warehouse_user)
        picking.action_assign()
        self.assertEqual(picking.move_line_ids.lot_id, lots)
        picking.move_line_ids.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        invoice = order._create_invoices().with_user(self.accountant)
        invoice.action_post()
        self.assertEqual(invoice.invoice_line_ids.sale_line_ids, order.order_line)
        self.assertEqual(invoice.amount_residual, expected)
        if expected_lines is not None:
            self.assertEqual(
                {line.sale_line_ids.id: line.price_subtotal for line in invoice.invoice_line_ids},
                expected_lines,
            )
            self.assertEqual(invoice.amount_tax, expected_tax)
        receivable = invoice.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        self.assertEqual(receivable.balance, expected)
        bank = self.env["account.journal"].search([
            ("company_id", "=", self.company.id), ("type", "=", "bank"),
        ], limit=1)
        method = bank.inbound_payment_method_line_ids[:1]
        method.sudo().payment_account_id = bank.default_account_id
        payment = self.env["account.payment.register"].with_user(self.accountant).with_context(
            active_model="account.move", active_ids=invoice.ids,
        ).create({
            "journal_id": bank.id, "payment_method_line_id": method.id,
        })._create_payments()
        self.assertEqual(payment.reconciled_invoice_ids, invoice)
        self.assertEqual(invoice.amount_residual, 0)

    def test_governed_native_promo_requires_supervisor(self):
        if "loyalty.program" not in self.env:
            self.skipTest("Sale loyalty is not installed for this focused module run")
        principal = self.env.ref("id_base.principal_mayora")
        product = self.product_a
        product.write({"principal_id": principal.id, "taxes_id": [Command.clear()], "standard_price": 1})
        other_principal = self.env.ref("id_base.principal_kapalapi")
        self.product_b.write({
            "principal_id": other_principal.id, "taxes_id": [Command.clear()], "standard_price": 1,
        })
        program = self.env["loyalty.program"].sudo().create({
            "name": "Commercial golden programme", "program_type": "promotion",
            "trigger": "with_code", "applies_on": "current", "company_id": self.company.id,
            "principal_id": principal.id, "budget_source": "distributor",
            "rule_ids": [Command.create({
                "code": "GOLDEN-B-PROMO", "minimum_qty": 1,
                "product_ids": [Command.set(product.ids)], "reward_point_amount": 1,
            })],
            "reward_ids": [Command.create({
                "reward_type": "discount", "discount": 5, "discount_mode": "percent",
                "discount_applicability": "order", "required_points": 1,
            })],
        })
        order = self.env["sale.order"].with_user(self.salesperson).with_context(install_mode=False).create({
            "partner_id": self.partner_a.id,
            "order_line": [Command.create({
                "product_id": product.id, "product_uom_qty": 1, "price_unit": 1_000_000,
            })],
        })
        coupon = self.env["sale.loyalty.coupon.wizard"].with_user(self.salesperson).create({
            "order_id": order.id, "coupon_code": "GOLDEN-B-PROMO",
        })

        with self.assertRaises(ValidationError):
            coupon.action_apply()
        program.action_submit_approval()
        program.action_approve()
        program.action_activate()
        today = fields.Date.today()
        program.date_from = today + timedelta(days=2)
        with self.assertRaises(ValidationError):
            coupon.action_apply()
        program.date_from = False
        program.date_to = today - timedelta(days=2)
        with self.assertRaises(ValidationError):
            coupon.action_apply()
        program.date_to = False
        program.active = False
        with self.assertRaises(ValidationError):
            coupon.action_apply()
        program.active = True
        program.principal_id = self.env.ref("id_base.principal_kapalapi")
        with self.assertRaises(ValidationError):
            coupon.action_apply()
        program.principal_id = principal
        program.rule_ids.product_ids = self.product_b
        with self.assertRaises(ValidationError):
            coupon.action_apply()
        program.rule_ids.product_ids = product
        program.rule_ids.minimum_qty = 2
        with self.assertRaises(ValidationError):
            coupon.action_apply()
        program.rule_ids.minimum_qty = 1
        foreign_company = self.env["res.company"].sudo().create({"name": "Golden foreign promo company"})
        with self.env.cr.savepoint():
            program.company_id = foreign_company
            with self.assertRaises(ValidationError):
                coupon.action_apply()
            program.company_id = self.company
        order.write({"order_line": [Command.create({
            "product_id": self.product_b.id, "product_uom_qty": 1, "price_unit": 1_000_000,
        })]})
        with self.assertRaises(ValidationError):
            coupon.action_apply()
        order.order_line.filtered(lambda line: line.product_id == self.product_b).unlink()
        coupon.action_apply()
        reward = self.env["sale.loyalty.reward.wizard"].with_user(self.salesperson).create({
            "order_id": order.id, "selected_reward_id": program.reward_ids.id,
        })
        reward.action_apply()
        self.assertEqual(order.amount_untaxed, 950_000)
        with self.assertRaisesRegex(UserError, "one fixed order reward"):
            order.action_apply_tactical_components({}, 100)
        with self.assertRaises(UserError):
            order.action_confirm()
        action = order.action_request_promo_usage_approval()
        request = self.env["fmcg.approval.request"].browse(action["res_id"])
        self.assertEqual(request.category_code, "promo_program_usage")
        self.assertEqual(request.line_ids.group_id, self.env.ref("id_approval.group_fmcg_approval_supervisor"))
        request.with_user(self.supervisor).action_approve()
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.amount_untaxed, 950_000)

        other = program.copy({
            "name": "Separate principal promo", "principal_id": other_principal.id,
            "rule_ids": [Command.create({
                "code": "GOLDEN-B-SEPARATE", "minimum_qty": 1,
                "product_ids": [Command.set(self.product_b.ids)], "reward_point_amount": 1,
            })],
        })
        other.action_submit_approval()
        other.action_approve()
        other.action_activate()
        separate = self.env["sale.order"].with_user(self.salesperson).with_context(install_mode=False).create({
            "partner_id": self.partner_a.id,
            "order_line": [Command.create({
                "product_id": self.product_b.id, "product_uom_qty": 1, "price_unit": 1_000_000,
            })],
        })
        self.env["sale.loyalty.coupon.wizard"].with_user(self.salesperson).create({
            "order_id": separate.id, "coupon_code": "GOLDEN-B-SEPARATE",
        }).action_apply()
        self.env["sale.loyalty.reward.wizard"].with_user(self.salesperson).create({
            "order_id": separate.id, "selected_reward_id": other.reward_ids.id,
        }).action_apply()
        request = self.env["fmcg.approval.request"].browse(separate.action_request_promo_usage_approval()["res_id"])
        request.with_user(self.supervisor).action_approve()
        separate.action_confirm()
        self.assertEqual(separate.state, "sale")
        self.assertEqual(separate.order_line.reward_id.program_id, other)
        self.assertEqual(order.order_line.reward_id.program_id, program)

    def test_fixed_official_promo_before_tactical_stack_and_footer(self):
        self._run_fixed_official_promo_chain(multiple=False)

    def test_multi_sku_fixed_promo_rounding_and_stale_approval(self):
        self._run_fixed_official_promo_chain(multiple=True)

    def _run_fixed_official_promo_chain(self, multiple):
        if "loyalty.program" not in self.env:
            self.skipTest("Sale loyalty is not installed for this focused module run")
        principal = self.env.ref("id_base.principal_mayora")
        product = self.product_a
        products = (product | self.product_b) if multiple else product
        taxes = self.env["account.tax"]
        if multiple:
            taxes = self.tax_sale_a.copy({
                "name": "Golden Chain 10%", "amount_type": "percent", "amount": 10,
                "price_include_override": "tax_excluded",
            })
        products.write({
            "principal_id": principal.id, "type": "consu", "is_storable": True,
            "tracking": "lot", "invoice_policy": "delivery", "standard_price": 100_000,
            "taxes_id": [Command.set(taxes.ids)],
        })
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        lots = self.env["stock.lot"]
        for item in products:
            lot = self.env["stock.lot"].create({
                "name": f"MIXED-GOLDEN-LOT-{item.id}", "product_id": item.id, "company_id": self.company.id,
            })
            lots |= lot
            self.env["stock.quant"]._update_available_quantity(item, warehouse.lot_stock_id, 1, lot_id=lot)
        promo = 60_000 if multiple else 50_000
        program = self.env["loyalty.program"].sudo().create({
            "name": "Fixed official amount", "program_type": "promotion",
            "trigger": "with_code", "applies_on": "current", "company_id": self.company.id,
            "principal_id": principal.id, "budget_source": "distributor",
            "rule_ids": [Command.create({
                "code": "GOLDEN-B-FIXED", "minimum_qty": 1,
                "product_ids": [Command.set(products.ids)], "reward_point_amount": 1,
            })],
            "reward_ids": [Command.create({
                "reward_type": "discount", "discount": 66_000 if multiple else promo, "discount_mode": "per_order",
                "discount_applicability": "order", "required_points": 1,
            })],
        })
        program.action_submit_approval()
        program.action_approve()
        program.action_activate()
        order = self.env["sale.order"].with_user(self.salesperson).with_context(install_mode=False).create({
            "partner_id": self.partner_a.id, "warehouse_id": warehouse.id,
            "order_line": [Command.create({
                "product_id": item.id, "product_uom_qty": 1,
                "price_unit": 1_000_000 if item == product else 500_000,
            }) for item in products],
        })
        self.env["sale.loyalty.coupon.wizard"].with_user(self.salesperson).create({
            "order_id": order.id, "coupon_code": "GOLDEN-B-FIXED",
        }).action_apply()
        self.env["sale.loyalty.reward.wizard"].with_user(self.salesperson).create({
            "order_id": order.id, "selected_reward_id": program.reward_ids.id,
        }).action_apply()
        first = order.order_line.filtered(lambda item: item.product_id == product)
        reward = order.order_line.filtered("reward_id")
        expected_lines = None
        expected = 900_000
        expected_tax = 0
        if multiple:
            second = order.order_line.filtered(lambda item: item.product_id == self.product_b)
            self.assertEqual(order.amount_untaxed, 1_440_000)
            steps = {str(first.id): [5, 1], str(second.id): [2]}
            footer = 101.01
            # Fixed promo 40,000 / 20,000; post-stack 902,880 / 470,400.
            # Footer quotas 66.411... / 34.598..., with the last cent going to SKU B.
            expected = 1_373_178.99
            expected_tax = 137_317.90
            expected_lines = {first.id: 942_813.59, second.id: 490_365.40, reward.id: -60_000}
        else:
            self.assertEqual(order.amount_untaxed, 950_000)
            steps = {str(first.id): [1]}
            footer = 40_500
        order.action_apply_tactical_components(steps, footer)
        self.assertEqual(order.amount_untaxed, expected)
        if multiple:
            components = order.commercial_tactical_components
            self.assertEqual(components["promo_allocations"], {str(first.id): "40000.0", str(second.id): "20000.0"})
            self.assertEqual(components["allocations"], {str(first.id): "66.41", str(second.id): "34.60"})
            self.assertEqual({line.id: line.price_subtotal for line in order.order_line}, expected_lines)
        requests = order._mobile_auto_request_approvals("Combined golden chain")
        self.assertEqual(requests.mapped("category_code"), ["tactical_discount"])
        self.assertEqual(len(requests.line_ids), 3)
        with self.assertRaises(UserError):
            order.action_confirm()
        for approver in (self.supervisor, self.user_mgr, self.user_dir):
            requests.with_user(approver).action_approve()
        if multiple:
            fingerprint = requests.commercial_fingerprint
            with self.assertRaisesRegex(UserError, "Basis diskon bertingkat berubah"):
                with self.env.cr.savepoint():
                    program.rule_ids.minimum_qty = 3
                    order.action_confirm()
            for field in ("promo_allocations", "allocations"):
                with self.assertRaisesRegex(UserError, "Komposisi komersial berubah"):
                    with self.env.cr.savepoint():
                        changed = dict(order.commercial_tactical_components)
                        amounts = changed[field]
                        changed[field] = {
                            str(first.id): str(float(amounts[str(first.id)]) + 1),
                            str(second.id): str(float(amounts[str(second.id)]) - 1),
                        }
                        order.sudo().write({"commercial_tactical_components": changed})
                        self.assertEqual(order.amount_untaxed, expected)
                        self.assertEqual(reward.price_subtotal, -promo)
                        self.assertEqual(requests.commercial_fingerprint, fingerprint)
                        order.action_confirm()
            with self.assertRaisesRegex(UserError, "Komposisi komersial berubah"):
                with self.env.cr.savepoint():
                    # The order and reward totals stay fixed while 1.00 moves to SKU B.
                    first.discount += 0.0001
                    second.discount -= 0.0002
                    self.assertEqual(order.amount_untaxed, expected)
                    changed = dict(order.commercial_tactical_components)
                    changed["basis"] = {
                        str(line.id): [line.price_unit, line.product_uom_qty, line.discount]
                        for line in first | second
                    }
                    order.sudo().write({"commercial_tactical_components": changed})
                    self.assertEqual(requests.commercial_fingerprint, fingerprint)
                    order.action_confirm()
        order.action_confirm()
        self.assertEqual(order.order_line.filtered("reward_id").price_subtotal, -promo)
        self.assertEqual(order.amount_tax, expected_tax)
        total = order.currency_id.round(expected + expected_tax)
        self._settle_commercial_sale(order, lots, total, expected_lines, expected_tax)
