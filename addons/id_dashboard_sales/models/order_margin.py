"""Actual posted invoice/refund and COGS bridge, including matched partial quantities."""
from collections import defaultdict

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class OrderMargin(models.AbstractModel):
    _name = "id.sales.order.margin"
    _description = "Traceable Recognized Order Margin"

    @api.model
    def _for_orders(self, domain):
        user = self.env.user
        if not (user.has_group("account.group_account_user") or user.has_group("base.group_system")):
            return {"available": False, "reason": "accounting_role_required", "rows": []}
        Order = self.env["sale.order"]
        if Order.search_count(domain, limit=5001) > 5000:
            raise UserError(_("Too many orders for cost attribution; narrow the period."))
        rows = [self._recognized_order(order) for order in Order.search(domain)]
        covered = [row for row in rows if row["available"]]
        revenue = sum(r["revenue"] for r in covered)
        cost = sum(r["cost"] for r in covered)
        return {"available": True, "count": len(rows), "covered": len(covered),
                "revenue": revenue if covered else None, "cost": cost if covered else None,
                "margin": revenue-cost if covered else None,
                "rate": (revenue-cost)/revenue*100 if revenue > 0 else None,
                "rows": rows[:100], "rows_total": len(rows), "domain": domain}

    def _recognized_order(self, order):
        row = {"id": order.id, "name": order.name, "available": False, "reason": "incomplete_quantity",
               "revenue": None, "cost": None, "margin": None, "rate": None, "invoice_ids": [], "journal_ids": []}
        lines = self.env["sale.order.line"].search([("order_id", "=", order.id), ("display_type", "=", False)])
        if not lines or any(not line.product_id.is_storable or line.is_downpayment for line in lines):
            return row
        invoices = self.env["account.move.line"].search([("sale_line_ids", "in", lines.ids),
            ("parent_state", "=", "posted"), ("display_type", "=", "product"),
            ("move_id.move_type", "in", ["out_invoice", "out_refund"])])
        if not invoices:
            return row
        invoiced = defaultdict(float)
        for inv in invoices:
            if (len(inv.sale_line_ids) != 1 or inv.company_id != order.company_id
                    or inv.account_id.account_type != "income" or inv.product_id != inv.sale_line_ids.product_id):
                return row
            sol = inv.sale_line_ids
            sign = -1 if inv.move_id.move_type == "out_refund" else 1
            invoiced[sol.id] += sign*inv.product_uom_id._compute_quantity(inv.quantity, sol.product_uom_id, round=False)
        Move = self.env["stock.move"]
        moves = Move.search([("sale_line_id", "in", lines.ids), ("state", "=", "done")])
        mapping = {m.id: m.sale_line_id.id for m in moves}
        frontier = moves
        while frontier:
            children = Move.search([("origin_returned_move_id", "in", frontier.ids), ("state", "=", "done"),
                                    ("id", "not in", moves.ids)])
            if len(moves)+len(children) > 50000:
                raise UserError(_("Too many return movements; narrow the scope."))
            for child in children:
                mapping[child.id] = mapping[child.origin_returned_move_id.id]
            moves |= children
            frontier = children
        actual = defaultdict(float)
        physical = self.env["stock.move"]
        for move in moves:
            if move.company_id != order.company_id:
                return row
            outward = move.location_dest_id.usage == "customer" and move.location_id.usage != "customer"
            inward = move.location_id.usage == "customer" and move.location_dest_id.usage != "customer"
            if not outward and not inward:
                continue  # internal pick/pack is not a customer delivery or return
            physical |= move
            sol = self.env["sale.order.line"].browse(mapping[move.id])
            if sol not in lines or move.product_id != sol.product_id:
                return row
            actual[sol.id] += (1 if outward else -1)*move.product_uom._compute_quantity(
                move.quantity, sol.product_uom_id, round=False)
        if not physical or any(float_compare(actual[line.id], invoiced[line.id],
                              precision_rounding=line.product_uom_id.rounding) for line in lines):
            return row
        row["reason"] = "missing_cogs_link"
        cost_lines = self.env["account.move.line"]
        # Route A: explicitly linked delivery/return journals, including shared product journals
        # only when the product has one unambiguous sale-line owner across all linked moves.
        route_a = all(m.account_move_id and m.account_move_id.state == "posted"
                      and m.account_move_id.company_id == order.company_id for m in physical)
        if route_a:
            journals = physical.account_move_id
            linked = Move.search([("account_move_id", "in", journals.ids)])
            owners = defaultdict(set)
            for move in linked:
                owner = mapping.get(move.id) or move.sale_line_id.id
                owners[(move.account_move_id.id, move.product_id.id)].add(owner)
            costs = self.env["account.move.line"].search([("move_id", "in", journals.ids),
                ("account_id.account_type", "=", "expense_direct_cost")])
            pairs = {(m.account_move_id.id, m.product_id.id) for m in physical}
            matched = costs.filtered(lambda c: (c.move_id.id, c.product_id.id) in pairs)
            if (pairs != {(c.move_id.id, c.product_id.id) for c in matched}
                    or any(len(owners[p]) != 1 or next(iter(owners[p])) not in lines.ids for p in pairs)):
                return row
            cost_lines |= matched
        # Route B: native invoice/refund COGS; explicit sale-line links or unique product ownership.
        native = self.env["account.move.line"].search([("move_id", "in", invoices.move_id.ids),
            ("display_type", "=", "cogs"), ("account_id.account_type", "=", "expense_direct_cost")])
        if cost_lines and all(order.company_id.currency_id.is_zero(c.balance) for c in native):
            native = self.env["account.move.line"]
        if native:
            for cost in native:
                candidates = cost.sale_line_ids or cost.move_id.invoice_line_ids.filtered(
                    lambda item: item.product_id == cost.product_id).sale_line_ids
                if len(candidates) != 1 or candidates not in lines:
                    return row
            if cost_lines and set(native.ids) != set(cost_lines.ids):
                return row  # two distinct cost postings are an exception, never summed twice
            cost_lines |= native
            expected_native = {(inv.move_id.id, inv.product_id.id) for inv in invoices if inv.quantity}
            if expected_native != {(cost.move_id.id, cost.product_id.id) for cost in native}:
                return row
            observed = self.env["account.move.line"].search([
                ("move_id", "in", physical.account_move_id.filtered(lambda j: j.state == "posted").ids),
                ("product_id", "in", physical.product_id.ids), ("account_id.account_type", "=", "expense_direct_cost")])
            if observed and set(observed.ids) != set(native.ids):
                return row
            if set(native.product_id.ids) != set(physical.product_id.ids):
                return row
        if not cost_lines:
            return row
        revenue, cost = -sum(invoices.mapped("balance")), sum(cost_lines.mapped("balance"))
        row.update(available=True, reason=None, revenue=revenue, cost=cost, margin=revenue-cost,
                   rate=(revenue-cost)/revenue*100 if revenue > 0 else None,
                   invoice_ids=invoices.move_id.ids, journal_ids=cost_lines.move_id.ids,
                   recognized_quantities=dict(invoiced), basis="posted_net_invoice_and_matched_customer_movements")
        return row
