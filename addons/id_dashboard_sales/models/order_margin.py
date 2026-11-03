"""Closed order invoice/COGS bridge. No standard-price or pro-rata cost fallback."""
from collections import defaultdict

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class OrderMargin(models.AbstractModel):
    _name = "id.sales.order.margin"
    _description = "Traceable Closed Order Margin"

    @api.model
    def _for_orders(self, domain):
        user = self.env.user
        if not (user.has_group("account.group_account_user") or user.has_group("base.group_system")):
            return {"available": False, "reason": "accounting_role_required", "rows": []}
        Order = self.env["sale.order"]
        if Order.search_count(domain, limit=5001) > 5000:
            raise UserError(_("Too many orders for cost attribution; narrow the period."))
        orders = Order.search(domain)
        lines = self.env["sale.order.line"].search([
            ("order_id", "in", orders.ids), ("display_type", "=", False)])
        by_order = defaultdict(lambda: self.env["sale.order.line"])
        for line in lines:
            by_order[line.order_id.id] |= line
        rows, complete, revenue_sum, cost_sum = [], 0, 0.0, 0.0
        for order in orders:
            row = {"id": order.id, "name": order.name, "available": False, "reason": "incomplete_quantity",
                   "revenue": None, "cost": None, "margin": None, "rate": None, "invoice_ids": [], "journal_ids": []}
            order_lines = by_order[order.id]
            # Deliberately narrow: no downpayment, service, adjustment, partial, or returned-order approximation.
            valid = bool(order_lines) and all(
                line.product_id.is_storable and line.product_uom_qty > 0 and line.price_subtotal > 0
                and not line.is_downpayment
                and float_compare(line.qty_delivered, line.product_uom_qty,
                                  precision_rounding=line.product_uom_id.rounding) == 0
                for line in order_lines)
            if valid:
                invoice_lines = self.env["account.move.line"].search([
                    ("sale_line_ids", "in", order_lines.ids), ("parent_state", "=", "posted"),
                    ("display_type", "=", "product"), ("move_id.move_type", "in", ["out_invoice", "out_refund"])])
                quantities = defaultdict(float)
                ambiguous = False
                for inv_line in invoice_lines:
                    if (len(inv_line.sale_line_ids) != 1 or inv_line.company_id != order.company_id
                            or inv_line.account_id.account_type != "income"
                            or inv_line.product_id != inv_line.sale_line_ids.product_id
                            or inv_line.move_id.move_type == "out_refund"):
                        ambiguous = True
                        continue
                    sol = inv_line.sale_line_ids
                    quantities[sol.id] += inv_line.product_uom_id._compute_quantity(
                        inv_line.quantity, sol.product_uom_id, round=False)
                valid = not ambiguous and all(float_compare(quantities[line.id], line.product_uom_qty,
                    precision_rounding=line.product_uom_id.rounding) == 0 for line in order_lines)
                if valid:
                    row["reason"] = "missing_cogs_link"
                    moves = self.env["stock.move"].search([
                        ("sale_line_id", "in", order_lines.ids), ("state", "=", "done")])
                    returned = self.env["stock.move"].search_count([
                        ("origin_returned_move_id", "in", moves.ids), ("state", "!=", "cancel")])
                    valid = bool(moves) and not returned and all(
                        m.location_dest_id.usage == "customer" and m.location_id.usage != "customer"
                        and m.company_id == order.company_id and m.account_move_id
                        and m.account_move_id.state == "posted" and m.account_move_id.company_id == order.company_id
                        for m in moves)
                    journals = moves.account_move_id if valid else self.env["account.move"]
                    if valid:
                        # Reject shared valuation journals outside this order instead of charging them twice.
                        linked = self.env["stock.move"].search([("account_move_id", "in", journals.ids)])
                        valid = set(linked.ids) == set(moves.ids)
                    costs = self.env["account.move.line"].search([
                        ("move_id", "in", journals.ids), ("account_id.account_type", "=", "expense_direct_cost")])
                    expected_pairs = ({(move.account_move_id.id, move.product_id.id) for move in moves}
                                      if valid else set())
                    cost_pairs = {(line.move_id.id, line.product_id.id) for line in costs}
                    covered = bool(expected_pairs) and cost_pairs == expected_pairs
                    # A hidden/deleted cost source is unavailable. Never substitute product standard_price.
                    if valid and covered and journals:
                        revenue = -sum(invoice_lines.mapped("balance"))
                        cost = sum(costs.mapped("balance"))
                        if revenue > 0 and cost >= 0:
                            complete += 1
                            revenue_sum += revenue
                            cost_sum += cost
                            row.update(available=True, reason=None, revenue=revenue, cost=cost,
                                       margin=revenue-cost, rate=(revenue-cost)/revenue*100,
                                       invoice_ids=invoice_lines.move_id.ids, journal_ids=journals.ids)
            rows.append(row)
        return {"available": True, "count": len(orders), "covered": complete,
                "revenue": revenue_sum if complete else None, "cost": cost_sum if complete else None,
                "margin": revenue_sum-cost_sum if complete else None,
                "rate": (revenue_sum-cost_sum)/revenue_sum*100 if revenue_sum > 0 else None,
                "rows": rows[:100], "rows_total": len(rows), "domain": domain}
