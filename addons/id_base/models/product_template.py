from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    principal_id = fields.Many2one("id.principal", string="Principal", index=True)
    brand_id = fields.Many2one("id.brand", string="Brand", index=True, domain="[('principal_id', '=?', principal_id)]")
    sub_brand_id = fields.Many2one(
        "id.sub.brand",
        string="Sub-Brand",
        index=True,
        domain="[('brand_id', '=?', brand_id)]",
    )
    carton_qty = fields.Integer(
        string="Pcs per Karton",
        default=1,
        help="Konversi kemasan sekunder: jumlah satuan dasar per dus/karton.",
    )
