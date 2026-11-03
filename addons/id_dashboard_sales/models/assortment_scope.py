"""Explicit period eligibility; observed SO turnover weights, never market-share proxies."""
from collections import defaultdict
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class AssortmentScope(models.Model):
    _name = "id.sales.assortment.scope"
    _description = "Period Outlet and SKU Eligibility"
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    product_ids = fields.Many2many("product.product", required=True, check_company=True)
    outlet_ids = fields.Many2many("res.partner", required=True, check_company=True)
    source = fields.Char(required=True)
    published = fields.Boolean(readonly=True, copy=False)
    frozen_json = fields.Text(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if {"published", "frozen_json"}.intersection(vals):
                raise AccessError(_("Publish eligibility through the action."))
            vals.update(published=False, frozen_json=False)
        return super().create(vals_list)

    def write(self, vals):
        if {"published", "frozen_json"}.intersection(vals) or any(r.published for r in self):
            raise AccessError(_("Published eligibility is immutable."))
        return super().write(vals)

    def unlink(self):
        if any(r.published for r in self):
            raise AccessError(_("Published eligibility cannot be deleted."))
        return super().unlink()

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for rec in self:
            if rec.date_from > rec.date_to:
                raise ValidationError(_("Eligibility period is invalid."))

    def action_publish(self):
        self.check_access("write")
        for rec in self:
            if rec.published or not rec.product_ids or not rec.outlet_ids:
                raise UserError(_("Select eligible outlets and SKUs before publishing."))
            facts = {"outlets": rec.outlet_ids.ids, "products": rec.product_ids.ids, "actor": self.env.uid,
                     "at": str(fields.Datetime.now()), "source": rec.source}
            super(AssortmentScope, rec).write({"published": True, "frozen_json": json.dumps(facts)})
        return True

    @api.model
    def _distribution(self, period, filtered):
        if not self.env.user.has_group("sales_team.group_sale_manager") or filtered:
            return {"available": False, "reason": "manager_unfiltered_scope_required", "rows": []}
        scopes = self.search([("company_id", "in", self.env.companies.ids), ("published", "=", True),
                              ("date_from", "=", period["start"]), ("date_to", "=", period["end"])], limit=101)
        if len(scopes) > 100:
            raise UserError(_("Too many eligibility scopes; narrow the company selection."))
        rows = []
        from .sales_productivity import _to_utc
        from datetime import date, timedelta
        for scope in scopes:
            frozen = json.loads(scope.frozen_json)
            outlets = self.env["res.partner"].search([("id", "in", frozen["outlets"])]).ids
            products = self.env["product.product"].with_context(active_test=False).search([
                ("id", "in", frozen["products"])]).ids
            if len(outlets) != len(frozen["outlets"]) or len(products) != len(frozen["products"]):
                continue  # ACL-incomplete universe cannot form a trustworthy denominator.
            lines = self.env["sale.order.line"].search([("order_id.company_id", "=", scope.company_id.id),
                ("order_id.state", "in", ["sale", "done"]), ("order_id.partner_id", "in", outlets),
                ("order_id.date_order", ">=", _to_utc(scope.date_from)),
                ("order_id.date_order", "<", _to_utc(date.fromisoformat(period["end"])+timedelta(days=1))),
                ("display_type", "=", False), ("product_id", "!=", False)])
            if len(lines) > 100000:
                raise UserError(_("Too many distribution lines; narrow the period."))
            weights, buyers, fx = defaultdict(float), defaultdict(set), {}
            service = self.env["id.sales.productivity"]
            for line in lines:
                factor = service._conversion(line.order_id, fx)
                outlet = line.order_id.partner_id.id
                weights[outlet] += line.price_subtotal*factor
                if line.product_uom_qty > 0 and line.price_subtotal > 0 and line.product_id.id in products:
                    buyers[line.product_id.id].add(outlet)
            denominator = sum(max(value, 0) for value in weights.values())
            for product in self.env["product.product"].browse(products):
                sold = buyers[product.id]
                rows.append({"key": "%s:%s" % (scope.id, product.id), "scope": scope.name,
                    "sku": product.display_name, "selling": len(sold), "eligible": len(outlets),
                    "numeric": len(sold)/len(outlets)*100 if outlets else None,
                    "weighted": sum(max(weights[p], 0) for p in sold)/denominator*100 if denominator > 0 else None})
        return {"available": True, "rows": rows, "scope_count": len(scopes),
                "basis": "published_eligibility_and_positive_net_observed_company_SO_turnover"}
