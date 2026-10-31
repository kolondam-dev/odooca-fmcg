# Part of odooca-fmcg. License LGPL-3.
"""Inventory status per FMCG category, read live from ``stock_quant``.

The distributor reports five merchandising groups. Each ``fmcg_category`` from
``id_base`` is mapped to exactly one group; unmapped categories fall into
``other`` so no quantity disappears from the totals.
"""

from odoo import fields, models, tools

CATEGORY_GROUP_SQL = """
            CASE pt.fmcg_category
                WHEN 'food' THEN 'food'
                WHEN 'foods_savory' THEN 'food'
                WHEN 'noodles_food' THEN 'food'
                WHEN 'biscuit_wafer' THEN 'food'
                WHEN 'beverages_rtd' THEN 'rtd_beverage'
                WHEN 'rtd' THEN 'rtd_beverage'
                WHEN 'coffee_powder' THEN 'rtd_beverage'
                WHEN 'coffee_hot' THEN 'rtd_beverage'
                WHEN 'coffee_wings' THEN 'rtd_beverage'
                WHEN 'dairy' THEN 'rtd_beverage'
                WHEN 'home_care' THEN 'home_care'
                WHEN 'personal_care' THEN 'personal_care'
                WHEN 'confectionery' THEN 'confectionery'
                ELSE 'other'
            END
"""

STOCK_CATEGORY_SQL = f"""
CREATE OR REPLACE VIEW id_wms_stock_category AS (
    SELECT ROW_NUMBER() OVER (ORDER BY pt.fmcg_category, sq.company_id) AS id,
           pt.fmcg_category AS fmcg_category,
           {CATEGORY_GROUP_SQL} AS category_group,
           sq.company_id AS company_id,
           rc.currency_id AS currency_id,
           COUNT(DISTINCT sq.product_id) AS product_count,
           COUNT(DISTINCT sq.lot_id) AS lot_count,
           SUM(sq.quantity) AS qty_on_hand,
           SUM(sq.reserved_quantity) AS qty_reserved,
           SUM(sq.quantity * COALESCE((pp.standard_price ->> sq.company_id::text)::numeric, 0))
               AS stock_value
      FROM stock_quant sq
      JOIN product_product pp ON pp.id = sq.product_id
      JOIN product_template pt ON pt.id = pp.product_tmpl_id
      JOIN stock_location sl ON sl.id = sq.location_id
      JOIN res_company rc ON rc.id = sq.company_id
     WHERE sl.usage = 'internal'
     GROUP BY pt.fmcg_category, sq.company_id, rc.currency_id
)
"""

CATEGORY_GROUP_SELECTION = [
    ("food", "Food"),
    ("rtd_beverage", "RTD / Beverage"),
    ("home_care", "Home Care"),
    ("personal_care", "Personal Care"),
    ("confectionery", "Confectionery"),
    ("other", "Other / Unmapped"),
]


class WmsStockCategory(models.Model):
    _name = "id.wms.stock.category"
    _description = "FMCG Inventory Status per Category"
    _auto = False
    _rec_name = "category_group"
    _order = "category_group, fmcg_category"

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
        string="FMCG Category",
        readonly=True,
    )
    category_group = fields.Selection(
        CATEGORY_GROUP_SELECTION, string="Merchandising Group", readonly=True
    )
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    product_count = fields.Integer(string="Products", readonly=True)
    lot_count = fields.Integer(string="Lots", readonly=True)
    qty_on_hand = fields.Float(string="Quantity On Hand", readonly=True)
    qty_reserved = fields.Float(string="Quantity Reserved", readonly=True)
    stock_value = fields.Monetary(string="Stock Value", currency_field="currency_id", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(STOCK_CATEGORY_SQL)
