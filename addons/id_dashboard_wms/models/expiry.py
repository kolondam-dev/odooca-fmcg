# Part of odooca-fmcg. License LGPL-3.
"""FEFO expiry monitoring read live from ``stock_quant`` and ``stock.lot``.

Buckets follow the distributor shelf-life policy:

* ``critical`` - fewer than 30 days to expiry: return to principal.
* ``warning``  - 30 to 90 days: priority bundling / discount program.
* ``good``     - more than 90 days: normal rotation.

Lots without an expiration date are excluded; the dashboard reports only stock
that can actually be prioritised by FEFO.
"""

from odoo import api, fields, models, tools

EXPIRY_SQL = """
CREATE OR REPLACE VIEW id_wms_expiry AS (
    SELECT ROW_NUMBER() OVER (
               ORDER BY lot.expiration_date, sq.product_id, sq.lot_id, sq.company_id
           ) AS id,
           sq.product_id AS product_id,
           sq.lot_id AS lot_id,
           lot.name AS lot_name,
           lot.expiration_date::date AS expiration_date,
           (lot.expiration_date::date - CURRENT_DATE) AS days_to_expiry,
           CASE
               WHEN (lot.expiration_date::date - CURRENT_DATE) < 30 THEN 'critical'
               WHEN (lot.expiration_date::date - CURRENT_DATE) <= 90 THEN 'warning'
               ELSE 'good'
           END AS bucket,
           pt.fmcg_category AS fmcg_category,
           sq.company_id AS company_id,
           rc.currency_id AS currency_id,
           SUM(sq.quantity) AS qty_on_hand,
           SUM(sq.quantity * COALESCE((pp.standard_price ->> sq.company_id::text)::numeric, 0))
               AS stock_value
      FROM stock_quant sq
      JOIN stock_lot lot ON lot.id = sq.lot_id
      JOIN product_product pp ON pp.id = sq.product_id
      JOIN product_template pt ON pt.id = pp.product_tmpl_id
      JOIN stock_location sl ON sl.id = sq.location_id
      JOIN res_company rc ON rc.id = sq.company_id
     WHERE sl.usage = 'internal'
       AND lot.expiration_date IS NOT NULL
       AND sq.quantity > 0
     GROUP BY sq.product_id, sq.lot_id, lot.name, lot.expiration_date,
              pt.fmcg_category, sq.company_id, rc.currency_id
)
"""

BUCKET_SELECTION = [
    ("critical", "Critical (< 30 Days)"),
    ("warning", "Warning (30-90 Days)"),
    ("good", "Good Stock (> 90 Days)"),
]

RECOMMENDED_ACTION = {
    "critical": "Return to principal",
    "warning": "Priority bundling / discount program",
    "good": "Normal rotation",
}


class WmsExpiry(models.Model):
    _name = "id.wms.expiry"
    _description = "FMCG FEFO Expiry Monitoring"
    _auto = False
    _rec_name = "lot_name"
    _order = "days_to_expiry asc, stock_value desc"

    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    lot_id = fields.Many2one("stock.lot", string="Lot / Batch", readonly=True)
    lot_name = fields.Char(string="Lot Number", readonly=True)
    expiration_date = fields.Date(string="Expiry Date", readonly=True)
    days_to_expiry = fields.Integer(string="Days to Expiry", readonly=True)
    bucket = fields.Selection(BUCKET_SELECTION, string="Expiry Bucket", readonly=True)
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
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    qty_on_hand = fields.Float(string="Quantity On Hand", readonly=True)
    stock_value = fields.Monetary(string="Stock Value", currency_field="currency_id", readonly=True)
    recommended_action = fields.Char(
        string="Recommended Action",
        compute="_compute_recommended_action",
        help="Operational follow-up implied by the expiry bucket.",
    )

    @api.depends("bucket")
    def _compute_recommended_action(self):
        for record in self:
            record.recommended_action = RECOMMENDED_ACTION.get(record.bucket, "")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(EXPIRY_SQL)
