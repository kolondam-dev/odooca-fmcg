from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _fmcg_governed_promo_domain(self, prefix=""):
        """Limit governed programmes to their company and the order principal."""
        self.ensure_one()
        products = self.order_line.filtered(
            lambda line: not line.display_type and not line.reward_id
        ).product_id
        principals = products.principal_id
        principal = principals.id if len(principals) == 1 else False
        historical = self.env.su and (self.fmcg_seed_batch or "").startswith("PERIOD_")
        generic = (prefix + "principal_id", "=", False)
        components = getattr(self, "commercial_tactical_components", False) or {}
        promo_basis = components.get("promo_basis") or []
        if historical or (components and not promo_basis) or not principal or any(
            not product.principal_id for product in products
        ):
            return [generic]
        governed = [
            "&", "&", (prefix + "principal_id", "=", principal),
            (prefix + "company_id", "=", self.company_id.id),
            (prefix + "governance_state", "in", ("approved", "active")),
        ]
        if promo_basis:
            governed = ["&", (prefix + "id", "=", promo_basis[0]), *governed]
        return ["|", generic, *governed]

    def _get_program_domain(self):
        return super()._get_program_domain() + self._fmcg_governed_promo_domain()

    def _get_trigger_domain(self):
        return super()._get_trigger_domain() + self._fmcg_governed_promo_domain("program_id.")

    def action_confirm(self):
        for order in self:
            programs = order.order_line.reward_id.program_id.filtered("principal_id")
            if programs and programs - programs.filtered_domain(order._get_program_domain()):
                raise UserError("Program promo pada pesanan sudah tidak memenuhi eligibility.")
        return super().action_confirm()

    def _get_program_timezone(self):
        return "Asia/Makassar"


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    promo_program_id = fields.Many2one(
        "loyalty.program",
        string="Program Promosi Prinsipal",
        index=True,
        help="Program promosi terdaftar yang diterapkan pada baris penjualan ini",
    )
    promo_mou_number = fields.Char(
        string="No. MoU Promosi",
        related="promo_program_id.mou_number",
        store=True,
        index=True,
    )
    promo_budget_source = fields.Selection(
        related="promo_program_id.budget_source",
        string="Sumber Beban Promo",
        store=True,
    )
    promo_principal_id = fields.Many2one(
        "id.principal",
        related="promo_program_id.principal_id",
        string="Prinsipal Promo",
        store=True,
        index=True,
    )
    promo_discount_amount = fields.Monetary(
        string="Nilai Potongan Promosi",
        compute="_compute_promo_discount_amount",
        store=True,
        currency_field="currency_id",
    )
    promo_claim_amount = fields.Monetary(
        string="Nilai Klaim Prinsipal",
        compute="_compute_promo_claim_amount",
        store=True,
        currency_field="currency_id",
        help="Porsi rupiah diskon yang ditagihkan kembali ke prinsipal",
    )

    @api.depends("discount", "price_unit", "product_uom_qty", "reward_id", "promo_program_id")
    def _compute_promo_discount_amount(self):
        for line in self:
            # 1. Direct discount percentage on line
            if line.discount > 0:
                gross = line.price_unit * line.product_uom_qty
                line.promo_discount_amount = gross * (line.discount / 100.0)
            # 2. Reward lines with negative subtotal
            elif line.price_subtotal < 0:
                line.promo_discount_amount = abs(line.price_subtotal)
            else:
                line.promo_discount_amount = 0.0

    @api.depends("promo_discount_amount", "promo_budget_source", "promo_program_id")
    def _compute_promo_claim_amount(self):
        for line in self:
            if not line.promo_program_id or not line.promo_discount_amount:
                line.promo_claim_amount = 0.0
                continue

            src = line.promo_budget_source
            if src == "principal":
                line.promo_claim_amount = line.promo_discount_amount
            elif src == "joint":
                line.promo_claim_amount = line.promo_discount_amount * 0.5
            else:
                line.promo_claim_amount = 0.0

    def _prepare_invoice_line(self, **optional_values):
        res = super()._prepare_invoice_line(**optional_values)
        if self.promo_program_id:
            res.update({
                "promo_program_id": self.promo_program_id.id,
                "promo_discount_amount": self.promo_discount_amount,
                "promo_claim_amount": self.promo_claim_amount,
            })
        return res

