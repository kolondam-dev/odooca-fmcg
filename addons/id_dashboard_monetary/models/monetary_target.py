# Part of odooca-fmcg. License LGPL-3.
"""Revenue target periods for the monetary funnel.

Targets are configuration, never code constants: every figure is dated and
editable by the finance manager so the funnel can be re-based without a
code change (AGENTS.md rule 3).
"""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MonetaryTarget(models.Model):
    _name = "id.monetary.target"
    _description = "FMCG Revenue Target Period"
    _order = "date_from desc, id desc"

    name = fields.Char(string="Target Period", required=True)
    date_from = fields.Date(string="Start Date", required=True)
    date_to = fields.Date(string="End Date", required=True)
    target_revenue = fields.Monetary(
        string="Revenue Target",
        currency_field="currency_id",
        help="Planned revenue for the period. Configured per period, never hardcoded in the view.",
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
    note = fields.Text(string="Notes")
    active = fields.Boolean(default=True)

    @api.constrains("date_from", "date_to")
    def _check_period(self):
        for target in self:
            if target.date_from and target.date_to and target.date_from > target.date_to:
                raise ValidationError("The target period must start on or before its end date.")
