from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    fmcg_seed_batch = fields.Char(
        string="FMCG Seed Source Batch",
        default=False,
        copy=False,
        index=True,
        help="Penanda batch persisten untuk Sales Order seed FMCG kanonikal.",
    )
