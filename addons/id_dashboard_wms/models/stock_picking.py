# Part of odooca-fmcg. License LGPL-3.
"""Operational fields the logistics dashboards read from delivery orders."""

from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    fmcg_reject_reason = fields.Selection(
        [
            ("packaging_damaged", "Wet / Crushed Packaging in Transit"),
            ("near_expiry", "Product Close to Expiry"),
            ("wrong_sku_qty", "Wrong SKU / Quantity Delivered"),
            ("store_closed", "Store Closed / Refused the Delivery Note"),
        ],
        string="FMCG Rejection Reason",
        copy=False,
        index=True,
        help="Standard FMCG rejection reason recorded when the outlet refuses the delivery. "
             "Empty means the delivery was accepted.",
    )
    fmcg_vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Delivery Vehicle",
        copy=False,
        index=True,
        help="Vehicle that performed the delivery. Used to compare fuel and helper cost "
             "against the value delivered by that vehicle.",
    )
