# Part of odooca-fmcg. License LGPL-3.

from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    fmcg_seed_rejection_delivery_id = fields.Many2one(
        "stock.picking", string="Source Delivery", check_company=True, copy=False, ondelete="restrict",
    )
    fmcg_seed_rejection_do_ref = fields.Char(string="Source DO Reference", copy=False)
    fmcg_seed_rejection_reason = fields.Char(string="Source Rejection Reason", copy=False)
    fmcg_seed_rejection_incident_ref = fields.Char(string="Source Incident Reference", copy=False)
    fmcg_seed_rejection_evidence_type = fields.Char(string="Source Evidence Type", copy=False)
    fmcg_seed_rejection_evidence_ref = fields.Char(string="Source Evidence Reference", copy=False)
