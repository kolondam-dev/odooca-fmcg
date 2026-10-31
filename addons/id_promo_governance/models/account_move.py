from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    promo_program_id = fields.Many2one(
        "loyalty.program",
        string="Program Promosi Prinsipal",
        index=True,
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
        currency_field="currency_id",
    )
    promo_claim_amount = fields.Monetary(
        string="Nilai Tagihan Klaim Prinsipal",
        currency_field="currency_id",
        help="Porsi rupiah diskon promosi yang ditagihkan kembali ke prinsipal",
    )

