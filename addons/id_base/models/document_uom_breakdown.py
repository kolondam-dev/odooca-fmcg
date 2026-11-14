# Part of odooca-fmcg. License LGPL-3.
"""Read-only FMCG packaging breakdowns for invoices and native stock documents.

The transaction quantity and Odoo inventory UoM remain authoritative. This helper
only renders the already-converted quantity as carton/inner/base tiers.
"""

from math import floor

from odoo import api, fields, models


def _fmcg_packaging_breakdown(product, quantity, transaction_uom):
    """Return a display-only packaging breakdown for one product quantity."""
    if not product or not transaction_uom or not product.product_tmpl_id:
        return False

    template = product.product_tmpl_id
    base_label_uom = template.fmcg_base_uom_id
    carton_qty = template.carton_qty
    inner_qty = template.inner_qty
    if not base_label_uom or not carton_qty or carton_qty <= 0:
        return False

    base_qty = transaction_uom._compute_quantity(
        quantity,
        product.uom_id,
        round=False,
    )
    sign = -1 if base_qty < 0 else 1
    remaining = abs(base_qty)

    def fmt(value):
        rounded = round(value)
        if abs(value - rounded) < 1e-7:
            return str(int(rounded))
        return f"{value:.2f}".rstrip("0").rstrip(".")

    cartons = floor((remaining + 1e-7) / carton_qty)
    remaining -= cartons * carton_qty

    inners = 0
    if inner_qty and inner_qty > 1:
        inners = floor((remaining + 1e-7) / inner_qty)
        remaining -= inners * inner_qty

    parts = []
    if cartons:
        parts.append(f"{fmt(sign * cartons)} Karton")
    if inners:
        parts.append(f"{fmt(sign * inners)} Inner")
    if remaining > 1e-7:
        parts.append(f"{fmt(sign * remaining)} {base_label_uom.name}")
    if not parts:
        parts.append(f"0 {base_label_uom.name}")

    return " + ".join(parts) + f" ({fmt(base_qty)} {base_label_uom.name})"


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    fmcg_qty_breakdown = fields.Char(
        string="Rincian Kemasan",
        compute="_compute_fmcg_qty_breakdown",
        help="Tampilan turunan; tidak mengubah kuantitas faktur atau jurnal.",
    )

    @api.depends(
        "product_id",
        "quantity",
        "product_uom_id",
        "product_id.product_tmpl_id.inner_qty",
        "product_id.product_tmpl_id.carton_qty",
        "product_id.product_tmpl_id.fmcg_base_uom_id",
    )
    def _compute_fmcg_qty_breakdown(self):
        for line in self:
            line.fmcg_qty_breakdown = _fmcg_packaging_breakdown(
                line.product_id,
                line.quantity,
                line.product_uom_id,
            )


class StockMove(models.Model):
    _inherit = "stock.move"

    fmcg_qty_breakdown = fields.Char(
        string="Rincian Kemasan",
        compute="_compute_fmcg_qty_breakdown",
        help="Tampilan turunan; tidak mengubah demand, reservasi, atau kuantitas stok.",
    )

    @api.depends(
        "product_id",
        "product_uom_qty",
        "product_uom",
        "product_id.product_tmpl_id.inner_qty",
        "product_id.product_tmpl_id.carton_qty",
        "product_id.product_tmpl_id.fmcg_base_uom_id",
    )
    def _compute_fmcg_qty_breakdown(self):
        for move in self:
            move.fmcg_qty_breakdown = _fmcg_packaging_breakdown(
                move.product_id,
                move.product_uom_qty,
                move.product_uom,
            )


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    fmcg_qty_breakdown = fields.Char(
        string="Rincian Kemasan",
        compute="_compute_fmcg_qty_breakdown",
        help="Tampilan turunan; tidak mengubah kuantitas aktual move line.",
    )

    @api.depends(
        "product_id",
        "quantity",
        "product_uom_id",
        "product_id.product_tmpl_id.inner_qty",
        "product_id.product_tmpl_id.carton_qty",
        "product_id.product_tmpl_id.fmcg_base_uom_id",
    )
    def _compute_fmcg_qty_breakdown(self):
        for line in self:
            line.fmcg_qty_breakdown = _fmcg_packaging_breakdown(
                line.product_id,
                line.quantity,
                line.product_uom_id,
            )
