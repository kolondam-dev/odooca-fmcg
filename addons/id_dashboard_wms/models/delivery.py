# Part of odooca-fmcg. License LGPL-3.
"""Delivery fulfillment and rejection dashboards, read live from ``stock_picking``.

* ``id.wms.delivery`` - one row per outgoing delivery order with its delivered
  value and standard rejection reason.
* ``id.wms.delivery.summary`` - delivery rate per month.
* ``id.wms.reject`` - rejection breakdown per standard FMCG reason.

Delivered value uses the sales order line price when the move comes from a sale
order, and falls back to the product cost (``product.product.standard_price``,
stored per company) otherwise.
"""

from odoo import fields, models, tools

REJECT_SELECTION = [
    ("packaging_damaged", "Wet / Crushed Packaging in Transit"),
    ("near_expiry", "Product Close to Expiry"),
    ("wrong_sku_qty", "Wrong SKU / Quantity Delivered"),
    ("store_closed", "Store Closed / Refused the Delivery Note"),
    ("not_recorded", "Not Recorded"),
]

DELIVERY_SQL = """
CREATE OR REPLACE VIEW id_wms_delivery AS (
    SELECT sp.id AS id,
           sp.name AS picking_name,
           sp.partner_id AS partner_id,
           sp.scheduled_date AS scheduled_date,
           sp.date_done AS date_done,
           sp.state AS state,
           spt.code AS picking_type_code,
           COALESCE(sp.fmcg_reject_reason, 'not_recorded') AS reject_reason,
           sp.fmcg_vehicle_id AS vehicle_id,
           sp.sale_id AS sale_order_id,
           COALESCE(so.amount_total, 0) AS sale_order_amount,
           sp.company_id AS company_id,
           rc.currency_id AS currency_id,
           (sp.state = 'done') AS is_delivered,
           (sp.state = 'done'
            AND sp.date_done IS NOT NULL
            AND sp.scheduled_date IS NOT NULL
            AND sp.date_done > sp.scheduled_date) AS is_late,
           COALESCE((
               SELECT SUM(
                          CASE
                              WHEN sol.id IS NOT NULL
                                   AND sol.product_uom_qty <> 0
                                   AND solu.factor <> 0
                              THEN (sol.price_subtotal / sol.product_uom_qty)
                                   * (sm.quantity * su.factor / solu.factor)
                              ELSE sm.quantity
                                   * COALESCE((pp.standard_price ->> sm.company_id::text)::numeric, 0)
                          END
                      )
                 FROM stock_move sm
                 LEFT JOIN sale_order_line sol ON sol.id = sm.sale_line_id
                 LEFT JOIN uom_uom solu ON solu.id = sol.product_uom_id
                 LEFT JOIN uom_uom su ON su.id = sm.product_uom
                 JOIN product_product pp ON pp.id = sm.product_id
                WHERE sm.picking_id = sp.id
                  AND sm.state = 'done'
           ), 0) AS delivered_value
      FROM stock_picking sp
      JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
      LEFT JOIN sale_order so ON so.id = sp.sale_id
      JOIN res_company rc ON rc.id = sp.company_id
     WHERE spt.code = 'outgoing'
)
"""

DELIVERY_SUMMARY_SQL = """
CREATE OR REPLACE VIEW id_wms_delivery_summary AS (
    SELECT ROW_NUMBER() OVER (ORDER BY date_trunc('month', d.scheduled_date)) AS id,
           date_trunc('month', d.scheduled_date)::date AS period_month,
           d.company_id AS company_id,
           d.currency_id AS currency_id,
           COUNT(*) AS scheduled_count,
           SUM(CASE WHEN d.is_delivered THEN 1 ELSE 0 END) AS delivered_count,
           SUM(CASE WHEN d.is_delivered THEN 0 ELSE 1 END) AS undelivered_count,
           SUM(CASE WHEN d.is_late THEN 1 ELSE 0 END) AS late_count,
           CASE WHEN COUNT(*) > 0
                THEN ROUND(100.0 * SUM(CASE WHEN d.is_delivered THEN 1 ELSE 0 END) / COUNT(*), 2)
                ELSE 0
           END AS delivery_rate,
           SUM(CASE WHEN d.is_delivered THEN d.delivered_value ELSE 0 END) AS delivered_value,
           SUM(d.sale_order_amount) AS sale_order_value
      FROM id_wms_delivery d
     WHERE d.scheduled_date IS NOT NULL
     GROUP BY date_trunc('month', d.scheduled_date), d.company_id, d.currency_id
)
"""

REJECT_SQL = """
CREATE OR REPLACE VIEW id_wms_reject AS (
    SELECT ROW_NUMBER() OVER (ORDER BY d.reject_reason) AS id,
           d.reject_reason AS reason,
           d.company_id AS company_id,
           d.currency_id AS currency_id,
           COUNT(*) AS picking_count,
           SUM(d.sale_order_amount) AS rejected_value
      FROM id_wms_delivery d
     WHERE d.reject_reason <> 'not_recorded'
        OR d.state = 'cancel'
     GROUP BY d.reject_reason, d.company_id, d.currency_id
)
"""


class WmsDelivery(models.Model):
    _name = "id.wms.delivery"
    _description = "FMCG Delivery Order Fulfillment"
    _auto = False
    _rec_name = "picking_name"
    _order = "scheduled_date desc"

    picking_name = fields.Char(string="Delivery Order", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    scheduled_date = fields.Datetime(string="Scheduled Date", readonly=True)
    date_done = fields.Datetime(string="Delivered Date", readonly=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("waiting", "Waiting Another Operation"),
            ("confirmed", "Waiting"),
            ("assigned", "Ready"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        readonly=True,
    )
    picking_type_code = fields.Char(string="Operation Type", readonly=True)
    reject_reason = fields.Selection(REJECT_SELECTION, string="Rejection Reason", readonly=True)
    vehicle_id = fields.Many2one("fleet.vehicle", string="Delivery Vehicle", readonly=True)
    sale_order_id = fields.Many2one("sale.order", string="Sales Order", readonly=True)
    sale_order_amount = fields.Monetary(
        string="Sales Order Amount", currency_field="currency_id", readonly=True
    )
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    is_delivered = fields.Boolean(string="Delivered", readonly=True)
    is_late = fields.Boolean(string="Delivered Late", readonly=True)
    delivered_value = fields.Monetary(
        string="Delivered Value", currency_field="currency_id", readonly=True
    )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(DELIVERY_SQL)


class WmsDeliverySummary(models.Model):
    _name = "id.wms.delivery.summary"
    _description = "FMCG Delivery Rate per Period"
    _auto = False
    _rec_name = "period_month"
    _order = "period_month desc"

    period_month = fields.Date(string="Period", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    scheduled_count = fields.Integer(string="Scheduled Deliveries", readonly=True)
    delivered_count = fields.Integer(string="Delivered", readonly=True)
    undelivered_count = fields.Integer(string="Not Delivered", readonly=True)
    late_count = fields.Integer(string="Delivered Late", readonly=True)
    delivery_rate = fields.Float(string="Delivery Rate (%)", readonly=True)
    delivered_value = fields.Monetary(
        string="Delivered Value", currency_field="currency_id", readonly=True
    )
    sale_order_value = fields.Monetary(
        string="Scheduled Sales Value", currency_field="currency_id", readonly=True
    )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(DELIVERY_SUMMARY_SQL)


class WmsReject(models.Model):
    _name = "id.wms.reject"
    _description = "FMCG Delivery Rejection Breakdown"
    _auto = False
    _rec_name = "reason"
    _order = "picking_count desc"

    reason = fields.Selection(REJECT_SELECTION, string="Rejection Reason", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    picking_count = fields.Integer(string="Rejected Deliveries", readonly=True)
    rejected_value = fields.Monetary(
        string="Rejected Order Value", currency_field="currency_id", readonly=True
    )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(REJECT_SQL)
