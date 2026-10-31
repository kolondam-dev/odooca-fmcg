from odoo import api, fields, models


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
    base_weight_g = fields.Float(
        string="Gramasi Base (g)",
        compute="_compute_base_weight_g",
        inverse="_inverse_base_weight_g",
        store=True,
        digits=(12, 1),
        help="Berat bersih satuan dasar dalam satuan gram (terkoneksi dua arah dengan weight dalam kg).",
    )
    carton_length_cm = fields.Float(string="Panjang Karton (cm)", digits=(12, 1))
    carton_width_cm = fields.Float(string="Lebar Karton (cm)", digits=(12, 1))
    carton_height_cm = fields.Float(string="Tinggi Karton (cm)", digits=(12, 1))
    carton_volume_cbm = fields.Float(
        string="Volume Karton (m³)",
        compute="_compute_carton_volume_cbm",
        store=True,
        digits=(12, 4),
        help="Kubikasi kemasan karton m³ (dihitung otomatis dari P x L x T / 1.000.000).",
    )
    carton_weight_kg = fields.Float(string="Berat Karton (kg)", digits=(12, 2))
    carton_barcode = fields.Char(string="Barcode Karton", copy=False, index=True)

    @api.depends("weight")
    def _compute_base_weight_g(self):
        for record in self:
            record.base_weight_g = (record.weight or 0.0) * 1000.0

    def _inverse_base_weight_g(self):
        for record in self:
            record.weight = (record.base_weight_g or 0.0) / 1000.0

    @api.depends("carton_length_cm", "carton_width_cm", "carton_height_cm")
    def _compute_carton_volume_cbm(self):
        for record in self:
            if record.carton_length_cm and record.carton_width_cm and record.carton_height_cm:
                record.carton_volume_cbm = round(
                    (record.carton_length_cm * record.carton_width_cm * record.carton_height_cm) / 1_000_000.0,
                    4,
                )
            else:
                record.carton_volume_cbm = 0.0
