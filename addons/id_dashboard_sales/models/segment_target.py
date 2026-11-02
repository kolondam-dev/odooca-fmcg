"""Independent SO targets by segment; never summed across dimensions."""
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SalesSegmentTarget(models.Model):
    _name = "id.sales.segment.target"
    _description = "Net SO Segment Target"
    _order = "date_from desc, company_id, dimension, id"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    date_from = fields.Date(required=True, index=True)
    date_to = fields.Date(required=True)
    active = fields.Boolean(default=True)
    dimension = fields.Selection([("salesman", "Salesperson"), ("channel", "Channel"),
                                  ("area", "Coverage area"), ("principal", "Principal")], required=True)
    salesman_id = fields.Many2one("res.users")
    channel_id = fields.Many2one("id.channel")
    area_id = fields.Many2one("id.coverage.area")
    principal_id = fields.Many2one("id.principal")
    target_amount = fields.Monetary(required=True, currency_field="currency_id")
    note = fields.Text()

    @property
    def segment_id(self):
        self.ensure_one()
        return self[f"{self.dimension}_id"].id

    @property
    def segment_name(self):
        self.ensure_one()
        return self[f"{self.dimension}_id"].display_name

    @api.onchange("dimension")
    def _onchange_dimension(self):
        for dimension in ("salesman", "channel", "area", "principal"):
            if dimension != self.dimension:
                self[f"{dimension}_id"] = False

    @api.constrains("company_id", "date_from", "date_to", "dimension", "salesman_id", "channel_id",
                    "area_id", "principal_id", "target_amount", "active")
    def _check_target(self):
        for record in self:
            if record.date_from > record.date_to or record.target_amount <= 0:
                raise ValidationError(_("A target requires a valid date range and a positive amount."))
            if record.salesman_id and record.company_id not in record.salesman_id.company_ids:
                raise ValidationError(_("The salesperson must belong to the target company."))
            selected = [d for d in ("salesman", "channel", "area", "principal") if record[f"{d}_id"]]
            if selected != [record.dimension]:
                raise ValidationError(_("Select exactly one segment matching the target dimension."))
        # A no-value-change write serializes config at company scope. Under repeatable-read,
        # a concurrent writer receives a serialization failure and Odoo retries with a fresh snapshot.
        # Advisory locks alone would keep the stale transaction snapshot and miss a concurrent insert.
        for company_id in sorted(self.company_id.ids):
            self.env.cr.execute("UPDATE res_company SET write_date=write_date WHERE id=%s", [company_id])
        for record in self.filtered("active"):
            if self.search_count([("id", "!=", record.id), ("active", "=", True),
                                  ("company_id", "=", record.company_id.id), ("dimension", "=", record.dimension),
                                  (f"{record.dimension}_id", "=", record.segment_id),
                                  ("date_from", "<=", record.date_to), ("date_to", ">=", record.date_from)]):
                raise ValidationError(_("Active target periods for the same company and segment must not overlap."))
