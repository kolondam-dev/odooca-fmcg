# Part of odooca-fmcg. License LGPL-3.

from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestAccountTaxDpp(AccountTestInvoicingCommon):
    def test_code_04_posts_native_tax_and_keeps_commercial_base(self):
        tax = self.tax_sale_a.copy({
            "name": "PPN Keluaran 12% (DPP Nilai Lain - Kode 04)",
            "amount_type": "percent",
            "amount": 12,
            "price_include_override": "tax_excluded",
        })
        repartition = tax.invoice_repartition_line_ids.filtered(
            lambda line: line.repartition_type == "tax"
        )
        repartition.ensure_one()
        output_account = repartition.account_id
        self.assertTrue(output_account)

        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner_a.id,
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [Command.create({
                "product_id": self.product_a.id,
                "quantity": 1,
                "price_unit": 1200,
                "tax_ids": [Command.set(tax.ids)],
            })],
        })
        invoice.action_post()

        tax_line = invoice.line_ids.filtered(lambda line: line.display_type == "tax")
        self.assertEqual(tax_line.tax_line_id, tax)
        self.assertEqual(tax_line.tax_repartition_line_id, repartition)
        self.assertEqual(tax_line.account_id, output_account)
        self.assertAlmostEqual(tax_line.tax_base_amount, -1100)
        self.assertAlmostEqual(tax_line.credit, 132)
        self.assertAlmostEqual(invoice.amount_untaxed, 1200)
        self.assertAlmostEqual(invoice.amount_total, 1332)
        self.assertAlmostEqual(invoice.amount_residual, 1332)
        self.assertAlmostEqual(sum(invoice.line_ids.mapped("balance")), 0)
