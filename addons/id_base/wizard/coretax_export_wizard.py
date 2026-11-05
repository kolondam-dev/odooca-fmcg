from odoo import _, fields, models
from odoo.exceptions import UserError


class CoreTaxExportWizard(models.TransientModel):
    _name = "coretax.export.wizard"
    _description = "Legacy Tax CSV (Unverified)"

    # Preserve schema and existing transient records during upgrade. No migration
    # may convert the old exported flag or generated reference into acceptance.
    date_from = fields.Date(
        string="From Date", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(string="To Date", required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, default=lambda self: self.env.company,
    )
    partner_ids = fields.Many2many(
        "res.partner", string="Customers", domain="[('customer_rank', '>', 0)]",
    )
    export_file = fields.Binary(string="Legacy CSV (Unverified)", readonly=True)
    export_filename = fields.Char(string="Filename", readonly=True)
    total_invoices = fields.Integer(string="Invoice Count", readonly=True)
    total_dpp = fields.Float(string="Tax Base", readonly=True)
    total_ppn = fields.Float(string="Tax Amount", readonly=True)
    state = fields.Selection([("draft", "Draft"), ("done", "Done")], default="draft", string="Status")

    def action_generate_coretax_csv(self):
        """Block direct RPC calls as well as the removed UI generation button."""
        raise UserError(_(
            "Legacy tax CSV generation is disabled. Use the native Indonesian "
            "Coretax workflow; an export is not proof of official acceptance."
        ))
