from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    principal_id = fields.Many2one("id.principal", string="Principal", index=True)
    fmcg_category = fields.Selection(
        [
            ("biscuit_wafer", "Biscuit & Wafer"),
            ("confectionery", "Chocolate & Confectionery"),
            ("coffee_powder", "Coffee & Powdered Beverage"),
            ("coffee_hot", "Coffee & Hot Beverages"),
            ("noodles_food", "Instant Noodles & Foods"),
            ("beverages_rtd", "Ready to Drink (RTD) & Beverage"),
            ("coffee_wings", "Coffee"),
            ("foods_savory", "Foods & Savory"),
            ("home_care", "Home Care & Hygiene"),
            ("personal_care", "Personal Care & Beauty"),
            ("food", "Food & Grocery"),
            ("rtd", "Ready-To-Drink"),
            ("dairy", "Dairy"),
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
