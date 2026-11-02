# Part of odooca-fmcg. License LGPL-3.
"""Delivery cost per vehicle compared with the value delivered.

``id.delivery.trip.cost`` is the only input model: fuel and helper cost per trip,
entered by logistics. ``id.wms.fleet.cost`` aggregates it per vehicle and month
and divides it by the delivered value of the delivery orders assigned to that
vehicle, so the ratio is always recomputed from live deliveries.
"""

from odoo import api, fields, models, tools

FLEET_COST_SQL = """
CREATE OR REPLACE VIEW id_wms_fleet_cost AS (
    WITH monthly_cost AS (
        SELECT c.vehicle_id,
               date_trunc('month', c.date)::date AS period_month,
               c.company_id,
               rc.currency_id,
               SUM(c.fuel_cost) AS fuel_cost,
               SUM(c.helper_cost) AS helper_cost,
               SUM(c.fuel_cost + c.helper_cost) AS total_cost
          FROM id_delivery_trip_cost c
          JOIN res_company rc ON rc.id = c.company_id
         GROUP BY c.vehicle_id, date_trunc('month', c.date)::date, c.company_id, rc.currency_id
    ),
    monthly_delivery AS (
        SELECT d.vehicle_id, d.company_id,
               date_trunc('month', d.date_done)::date AS period_month,
               SUM(d.delivered_value) AS delivered_value
          FROM id_wms_delivery d
         WHERE d.is_delivered AND d.vehicle_id IS NOT NULL AND d.date_done IS NOT NULL
         GROUP BY d.vehicle_id, d.company_id, date_trunc('month', d.date_done)::date
    )
    SELECT ROW_NUMBER() OVER (ORDER BY mc.vehicle_id, mc.period_month) AS id,
           mc.vehicle_id AS vehicle_id,
           mc.period_month AS period_month,
           mc.company_id AS company_id,
           mc.currency_id AS currency_id,
           mc.fuel_cost AS fuel_cost,
           mc.helper_cost AS helper_cost,
           mc.total_cost AS total_cost,
           COALESCE(md.delivered_value, 0) AS delivered_value
      FROM monthly_cost mc
      LEFT JOIN monthly_delivery md ON md.vehicle_id = mc.vehicle_id
           AND md.period_month = mc.period_month AND md.company_id = mc.company_id
)
"""


class DeliveryTripCost(models.Model):
    _name = "id.delivery.trip.cost"
    _description = "FMCG Delivery Trip Cost"
    _order = "date desc, id desc"

    date = fields.Date(
        string="Trip Date",
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    vehicle_id = fields.Many2one("fleet.vehicle", string="Vehicle", required=True, index=True)
    fuel_cost = fields.Monetary(string="Fuel Cost", currency_field="currency_id")
    helper_cost = fields.Monetary(string="Helper Cost", currency_field="currency_id")
    total_cost = fields.Monetary(
        string="Total Cost",
        currency_field="currency_id",
        compute="_compute_total_cost",
        help="Fuel plus helper cost for this trip.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    note = fields.Char(string="Notes")

    @api.depends("fuel_cost", "helper_cost")
    def _compute_total_cost(self):
        for cost in self:
            cost.total_cost = (cost.fuel_cost or 0.0) + (cost.helper_cost or 0.0)


class WmsFleetCost(models.Model):
    _name = "id.wms.fleet.cost"
    _description = "FMCG Delivery Cost Ratio per Vehicle"
    _auto = False
    _rec_name = "vehicle_id"
    _order = "period_month desc, total_cost desc"

    vehicle_id = fields.Many2one("fleet.vehicle", string="Vehicle", readonly=True)
    period_month = fields.Date(string="Period", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    fuel_cost = fields.Monetary(string="Fuel Cost", currency_field="currency_id", readonly=True)
    helper_cost = fields.Monetary(string="Helper Cost", currency_field="currency_id", readonly=True)
    total_cost = fields.Monetary(string="Total Cost", currency_field="currency_id", readonly=True)
    delivered_value = fields.Monetary(
        string="Delivered Value", currency_field="currency_id", readonly=True
    )
    cost_ratio_percent = fields.Float(
        string="Cost Ratio (%)",
        compute="_compute_cost_ratio_percent",
        help="Fuel and helper cost divided by the value delivered by the same vehicle in the month.",
    )

    @api.depends("total_cost", "delivered_value")
    def _compute_cost_ratio_percent(self):
        for cost in self:
            cost.cost_ratio_percent = (
                100.0 * cost.total_cost / cost.delivered_value if cost.delivered_value else 0.0
            )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(FLEET_COST_SQL)
