from math import floor

from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    fmcg_qty_breakdown = fields.Char(
        string="Rincian Kemasan",
        compute="_compute_fmcg_qty_breakdown",
        help="Rincian turunan dari satu kuantitas kanonis; tidak menambah kuantitas stok.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Default new FMCG sales lines to the SKU's readable base-unit label."""
        prepared = [dict(vals) for vals in vals_list]
        Product = self.env["product.product"]
        for vals in prepared:
            if vals.get("product_id") and not vals.get("product_uom_id"):
                product = Product.browse(vals["product_id"])
                base_uom = product.product_tmpl_id.fmcg_base_uom_id
                if base_uom:
                    vals["product_uom_id"] = base_uom.id
        return super().create(prepared)

    @api.onchange("product_id")
    def _onchange_fmcg_base_uom(self):
        for line in self:
            product = line.product_id
            base_uom = product.product_tmpl_id.fmcg_base_uom_id if product else False
            if not base_uom:
                continue
            allowed_uoms = product.uom_id | product.uom_ids
            if (
                not line.product_uom_id
                or line.product_uom_id == product.uom_id
                or line.product_uom_id not in allowed_uoms
            ):
                line.product_uom_id = base_uom

    @api.depends(
        "product_id",
        "product_uom_qty",
        "product_uom_id",
        "product_id.product_tmpl_id.inner_qty",
        "product_id.product_tmpl_id.carton_qty",
        "product_id.product_tmpl_id.fmcg_base_uom_id",
        "product_id.product_tmpl_id.fmcg_inner_uom_id",
        "product_id.product_tmpl_id.fmcg_carton_uom_id",
    )
    def _compute_fmcg_qty_breakdown(self):
        def fmt(value):
            rounded = round(value)
            if abs(value - rounded) < 1e-7:
                return str(int(rounded))
            return f"{value:.2f}".rstrip("0").rstrip(".")

        for line in self:
            product = line.product_id.product_tmpl_id if line.product_id else False
            if (
                not product
                or not product.fmcg_base_uom_id
                or not line.product_uom_id
                or not product.carton_qty
            ):
                line.fmcg_qty_breakdown = False
                continue

            base_qty = line.product_uom_id._compute_quantity(
                line.product_uom_qty,
                product.uom_id,
                round=False,
            )
            sign = -1 if base_qty < 0 else 1
            remaining = abs(base_qty)
            carton_count = floor((remaining + 1e-7) / product.carton_qty)
            remaining -= carton_count * product.carton_qty

            inner_count = 0
            if product.inner_qty > 1:
                inner_count = floor((remaining + 1e-7) / product.inner_qty)
                remaining -= inner_count * product.inner_qty

            parts = []
            if carton_count:
                parts.append(f"{fmt(sign * carton_count)} Karton")
            if inner_count:
                parts.append(f"{fmt(sign * inner_count)} Inner")
            if remaining > 1e-7:
                parts.append(f"{fmt(sign * remaining)} {product.fmcg_base_uom_id.name}")
            if not parts:
                parts.append(f"0 {product.fmcg_base_uom_id.name}")

            line.fmcg_qty_breakdown = (
                " + ".join(parts)
                + f" ({fmt(base_qty)} {product.fmcg_base_uom_id.name})"
            )
