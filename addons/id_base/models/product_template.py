from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    principal_id = fields.Many2one("id.principal", string="Principal", index=True)
    fmcg_category = fields.Selection(
        [
            ("food", "Food"),
            ("rtd", "RTD (Ready-To-Drink)"),
            ("home_care", "Home Care"),
            ("personal_care", "Personal Care"),
            ("dairy", "Dairy"),
            ("confectionery", "Confectionery"),
            ("other", "Other"),
        ],
        string="Principal Category / Divisi",
        index=True,
    )
    brand_id = fields.Many2one("id.brand", string="Brand", index=True, domain="[('principal_id', '=?', principal_id)]")
    sub_brand_id = fields.Many2one(
        "id.sub.brand",
        string="Sub-Brand",
        index=True,
        domain="[('brand_id', '=?', brand_id)]",
    )
    inner_qty = fields.Integer(
        string="Pcs per Inner / Renceng / Pack",
        default=1,
        help="Fraksi kemasan menengah (Inner / Renceng / Pack) sebelum tingkat Karton.",
    )
    carton_qty = fields.Integer(
        string="Pcs per Karton",
        default=1,
        help="Konversi kemasan sekunder: jumlah satuan dasar per dus/karton.",
    )

