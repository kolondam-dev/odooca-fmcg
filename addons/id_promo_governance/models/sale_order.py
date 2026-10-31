from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    promo_program_id = fields.Many2one(
        "loyalty.program",
        string="Program Promosi Prinsipal",
        index=True,
        help="Program promosi terdaftar yang diterapkan pada baris penjualan ini",
    )
    promo_mou_number = fields.Char(
        string="No. MoU Promosi",
        related="promo_program_id.mou_number",
        store=True,
        index=True,
    )
    promo_budget_source = fields.Selection(
        related="promo_program_id.budget_source",
        string="Sumber Beban Promo",
        store=True,
    )
    promo_principal_id = fields.Many2one(
        "id.principal",
        related="promo_program_id.principal_id",
        string="Prinsipal Promo",
        store=True,
        index=True,
    )
    promo_discount_amount = fields.Monetary(
        string="Nilai Potongan Promosi",
        compute="_compute_promo_discount_amount",
        store=True,
        currency_field="currency_id",
    )
    promo_claim_amount = fields.Monetary(
        string="Nilai Klaim Prinsipal",
        compute="_compute_promo_claim_amount",
        store=True,
        currency_field="currency_id",
        help="Porsi rupiah diskon yang ditagihkan kembali ke prinsipal",
    )

    @api.depends("discount", "price_unit", "product_uom_qty", "reward_id", "promo_program_id")
    def _compute_promo_discount_amount(self):
        for line in self:
            # 1. Direct discount percentage on line
            if line.discount > 0:
                gross = line.price_unit * line.product_uom_qty
                line.promo_discount_amount = gross * (line.discount / 100.0)
            # 2. Reward lines with negative subtotal
            elif line.price_subtotal < 0:
                line.promo_discount_amount = abs(line.price_subtotal)
            else:
                line.promo_discount_amount = 0.0

    @api.depends("promo_discount_amount", "promo_budget_source", "promo_program_id")
    def _compute_promo_claim_amount(self):
        for line in self:
            if not line.promo_program_id or not line.promo_discount_amount:
                line.promo_claim_amount = 0.0
                continue

            src = line.promo_budget_source
            if src == "principal":
                line.promo_claim_amount = line.promo_discount_amount
            elif src == "joint":
                line.promo_claim_amount = line.promo_discount_amount * 0.5
            else:
                line.promo_claim_amount = 0.0

    def _prepare_invoice_line(self, **optional_values):
        res = super()._prepare_invoice_line(**optional_values)
        if self.promo_program_id:
            res.update({
                "promo_program_id": self.promo_program_id.id,
                "promo_discount_amount": self.promo_discount_amount,
                "promo_claim_amount": self.promo_claim_amount,
            })
        return res

