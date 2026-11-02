# Part of odooca-fmcg. License LGPL-3.
"""Financial funnel: target, realized revenue, receivable balance, and cash collection.

The funnel is a read-only SQL view so the numbers always come from the live
tables (``account_move`` and ``account_payment``), never from stored copies.
"""

from odoo import api, fields, models, tools

FUNNEL_SQL = """
CREATE OR REPLACE VIEW id_monetary_funnel_stage AS (
    WITH target AS (
        SELECT t.id, t.name, t.date_from, t.date_to, t.company_id, t.target_revenue
          FROM id_monetary_target t
         WHERE t.active
    )
    SELECT t.id * 10 + 1 AS id,
           1 AS sequence,
           'target' AS stage,
           t.id AS target_id,
           t.name AS period_name,
           t.date_from AS date_from,
           t.date_to AS date_to,
           t.company_id AS company_id,
           rc.currency_id AS currency_id,
           t.target_revenue AS amount,
           t.target_revenue AS target_amount
      FROM target t
      JOIN res_company rc ON rc.id = t.company_id
    UNION ALL
    SELECT t.id * 10 + 2,
           2,
           'realized',
           t.id,
           t.name,
           t.date_from,
           t.date_to,
           t.company_id,
           rc.currency_id,
           COALESCE((
               SELECT SUM(am.amount_untaxed_signed)
                 FROM account_move am
                WHERE am.state = 'posted'
                  AND am.move_type IN ('out_invoice', 'out_refund')
                  AND am.company_id = t.company_id
                  AND am.invoice_date >= t.date_from
                  AND am.invoice_date <= t.date_to
           ), 0) AS amount,
           t.target_revenue AS target_amount
      FROM target t
      JOIN res_company rc ON rc.id = t.company_id
    UNION ALL
    SELECT t.id * 10 + 3,
           3,
           'receivable',
           t.id,
           t.name,
           t.date_from,
           t.date_to,
           t.company_id,
           rc.currency_id,
           COALESCE((
               SELECT SUM(am.amount_residual_signed)
                 FROM account_move am
                WHERE am.state = 'posted'
                  AND am.move_type IN ('out_invoice', 'out_refund')
                  AND am.company_id = t.company_id
                  AND am.payment_state IN ('not_paid', 'partial')
           ), 0) AS amount,
           t.target_revenue AS target_amount
      FROM target t
      JOIN res_company rc ON rc.id = t.company_id
    UNION ALL
    SELECT t.id * 10 + 4,
           4,
           'collection',
           t.id,
           t.name,
           t.date_from,
           t.date_to,
           t.company_id,
           rc.currency_id,
           COALESCE((
               SELECT SUM(ap.amount_company_currency_signed)
                 FROM account_payment ap
                WHERE ap.state IN ('paid', 'in_process')
                  AND ap.payment_type = 'inbound'
                  AND ap.company_id = t.company_id
                  AND ap.date >= t.date_from
                  AND ap.date <= t.date_to
           ), 0) AS amount,
           t.target_revenue AS target_amount
      FROM target t
      JOIN res_company rc ON rc.id = t.company_id
)
"""


class MonetaryFunnelStage(models.Model):
    _name = "id.monetary.funnel.stage"
    _description = "FMCG Financial Funnel Stage"
    _auto = False
    _rec_name = "period_name"
    _order = "target_id, sequence"

    sequence = fields.Integer(string="Sequence")
    stage = fields.Selection(
        [
            ("target", "Revenue Target"),
            ("realized", "Realized Revenue"),
            ("receivable", "Total Receivable (AR)"),
            ("collection", "Cash Collection"),
        ],
        string="Funnel Stage",
    )
    target_id = fields.Many2one("id.monetary.target", string="Target Period")
    period_name = fields.Char(string="Period")
    date_from = fields.Date(string="Start Date")
    date_to = fields.Date(string="End Date")
    company_id = fields.Many2one("res.company", string="Company")
    currency_id = fields.Many2one("res.currency", string="Currency")
    amount = fields.Monetary(string="Amount", currency_field="currency_id")
    target_amount = fields.Monetary(string="Revenue Target", currency_field="currency_id")
    achievement_percent = fields.Float(
        string="Achieved (%)",
        compute="_compute_achievement_percent",
        help="Stage amount expressed as a percentage of the period revenue target.",
    )

    @api.depends("amount", "target_amount")
    def _compute_achievement_percent(self):
        for stage in self:
            stage.achievement_percent = (
                100.0 * stage.amount / stage.target_amount if stage.target_amount else 0.0
            )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(FUNNEL_SQL)
