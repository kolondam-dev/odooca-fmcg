"""Operator event clocks tied to native ready/completed warehouse operations."""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.float_utils import float_compare

PROTECTED = {"state", "started_at", "ended_at", "started_by", "ended_by", "duration_minutes"}


class WarehouseClock(models.Model):
    _name = "id.warehouse.clock"
    _description = "Warehouse Operation Event Clock"
    _check_company_auto = True
    _order = "id desc"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    picking_id = fields.Many2one("stock.picking", required=True, check_company=True, ondelete="restrict")
    completion_picking_id = fields.Many2one("stock.picking", check_company=True, ondelete="restrict")
    warehouse_id = fields.Many2one(related="picking_id.picking_type_id.warehouse_id", store=True)
    kind = fields.Selection([("picking", "Picking"), ("putaway", "Putaway"),
                             ("receiving_dwell", "Receiving to Storage Dwell")], required=True)
    state = fields.Selection([("draft", "Draft"), ("running", "Running"), ("done", "Completed"),
                              ("cancelled", "Cancelled")], default="draft", readonly=True, copy=False)
    started_at = fields.Datetime(readonly=True, copy=False)
    ended_at = fields.Datetime(readonly=True, copy=False)
    started_by = fields.Many2one("res.users", readonly=True, copy=False)
    ended_by = fields.Many2one("res.users", readonly=True, copy=False)
    duration_minutes = fields.Float(compute="_compute_duration")
    note = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if PROTECTED.intersection(vals) - ({"state"} if vals.get("state") == "draft" else set()):
                raise AccessError(_("Warehouse clock facts are recorded by event actions only."))
            vals.update(state="draft", started_at=False, ended_at=False, started_by=False, ended_by=False)
        return super().create(vals_list)

    def write(self, vals):
        if PROTECTED.intersection(vals):
            raise AccessError(_("Warehouse clock facts are recorded by event actions only."))
        for rec in self:
            if rec.state in ("done", "cancelled") or (rec.state == "running" and set(vals)-{
                    "completion_picking_id", "note"}):
                raise AccessError(_("Started warehouse event identity and completed clocks are immutable."))
        return super().write(vals)

    def unlink(self):
        if any(rec.state != "draft" for rec in self):
            raise AccessError(_("Started warehouse clocks cannot be deleted."))
        return super().unlink()

    @api.depends("state", "started_at", "ended_at")
    def _compute_duration(self):
        for rec in self:
            rec.duration_minutes = ((rec.ended_at-rec.started_at).total_seconds()/60
                                    if rec.state == "done" and rec.started_at and rec.ended_at else 0)

    def _lock(self):
        self.check_access("write")
        for rec in self.sorted("id"):
            self.env.cr.execute("UPDATE id_warehouse_clock SET write_date=write_date WHERE id=%s", [rec.id])

    def _worker_access(self):
        if self.started_by != self.env.user and not (self.env.user.has_group("stock.group_stock_manager")
                                                     or self.env.user.has_group("base.group_system")):
            raise AccessError(_("Only the starting worker or warehouse manager can finish this clock."))

    def action_start(self):
        self._lock()
        for rec in self:
            if rec.state == "running":
                continue
            pick, warehouse = rec.picking_id, rec.warehouse_id
            if rec.state != "draft" or pick.state != "assigned" or not warehouse:
                raise UserError(_("Start a draft clock on a ready warehouse operation."))
            if rec.kind == "receiving_dwell" and pick.picking_type_code != "incoming":
                raise UserError(_("Receiving dwell starts with an incoming operation."))
            if rec.kind == "picking" and pick.location_id.usage != "internal":
                raise UserError(_("Picking starts from an internal stock location."))
            if rec.kind == "putaway" and not self.env["stock.location"].search_count([
                    ("id", "=", pick.location_dest_id.id), ("id", "child_of", warehouse.lot_stock_id.id)]):
                raise UserError(_("Putaway must lead into the warehouse storage root."))
            self.env.cr.execute("UPDATE stock_picking SET write_date=write_date WHERE id=%s", [pick.id])
            if self.search_count([("picking_id", "=", pick.id), ("kind", "=", rec.kind),
                                  ("state", "in", ["running", "done"]), ("id", "!=", rec.id)]):
                raise UserError(_("This operation already has a running or completed clock of this kind."))
            super(WarehouseClock, rec).write({"state": "running", "started_at": fields.Datetime.now(),
                                              "started_by": self.env.uid})
        return True

    def action_complete(self):
        self._lock()
        for rec in self:
            if rec.state == "done":
                continue
            rec._worker_access()
            end = rec.completion_picking_id or rec.picking_id
            if rec.state != "running" or end.state != "done" or end.company_id != rec.company_id:
                raise UserError(_("Complete the linked native operation before stopping the clock."))
            if rec.kind != "receiving_dwell" and end != rec.picking_id:
                raise UserError(_("Picking and putaway clocks finish on their starting operation."))
            if rec.kind == "receiving_dwell":
                rec._validate_receiving_storage(end)
            now = fields.Datetime.now()
            if now < rec.started_at:
                raise UserError(_("Clock end cannot precede its start."))
            super(WarehouseClock, rec).write({"state": "done", "ended_at": now, "ended_by": self.env.uid})
        return True

    def _validate_receiving_storage(self, end):
        """Prove first storage arrival for every actually received quantity branch.

        A receipt backorder is a separate receipt/clock. Shared downstream origins
        cannot be allocated safely here and require operational follow-up.
        """
        self.ensure_one()
        if self.picking_id.state != "done":
            raise UserError(_("Complete the native receipt before closing receiving dwell."))
        storage = self.env["stock.location"].search([
            ("id", "child_of", self.warehouse_id.lot_stock_id.id),
            ("usage", "=", "internal"), ("company_id", "=", self.company_id.id)])
        storage_ids = set(storage.ids)
        roots = self.picking_id.move_ids.filtered(lambda m: m.state != "cancel" and m.quantity > 0)
        if not roots:
            raise UserError(_("Receiving dwell needs a positive completed receipt quantity."))
        pending, seen, arrived_pickings = list(roots), set(), set()
        line_count = 0
        while pending:
            move = pending.pop()
            if move.id in seen or len(seen) >= 5000:
                raise UserError(_("Receiving chain is cyclic, shared or too large to attribute safely."))
            seen.add(move.id)
            if move.state != "done" or move.company_id != self.company_id:
                raise UserError(_("Complete every received quantity branch before closing receiving dwell."))
            lines = move.move_line_ids.filtered(lambda line: line.quantity > 0)
            line_count += len(lines)
            if not lines or line_count > 50000 or any(
                    line.product_id != move.product_id or line.company_id != self.company_id
                    or line.location_id != move.location_id
                    or (line.location_dest_id != move.location_dest_id and not (
                        move.location_dest_id.id in storage_ids
                        and line.location_dest_id.id in storage_ids
                        and move.location_dest_id.parent_path
                        and (line.location_dest_id.parent_path or "").startswith(move.location_dest_id.parent_path)))
                    for line in lines):
                raise UserError(_("Receiving movement evidence is missing, mixed or exceeds the query limit."))
            if move.location_dest_id.id in storage_ids:
                arrived_pickings.add(move.picking_id.id)
                continue  # first storage arrival; later shipment/return is a separate operation
            children = move.move_dest_ids.filtered(lambda m: m.state != "cancel" and m.quantity > 0)
            if not children or any(
                    child.state != "done" or child.company_id != self.company_id
                    or child.product_id != move.product_id or child.location_id != move.location_dest_id
                    or child.move_orig_ids != move for child in children):
                raise UserError(_("Every received branch needs unambiguous completed onward storage movements."))
            # Reject an uncompleted zero-done-quantity backorder too, rather than
            # silently dropping it from the graph because quantity is still zero.
            if any(child.state not in ("done", "cancel") for child in move.move_dest_ids):
                raise UserError(_("Complete every received quantity branch before closing receiving dwell."))
            unit = move.product_id.uom_id
            received = move.product_uom._compute_quantity(move.quantity, unit, round=False)
            forwarded = sum(child.product_uom._compute_quantity(child.quantity, unit, round=False)
                            for child in children)
            if float_compare(received, forwarded, precision_rounding=unit.rounding):
                raise UserError(_("Onward quantities must exactly cover the received branch."))
            pending.extend(children)
        if end.id not in arrived_pickings or end.location_dest_id.id not in storage_ids:
            raise UserError(_("Completion must be a first-storage operation from the fully covered receipt chain."))
        return True

    def action_cancel(self):
        self._lock()
        for rec in self:
            if rec.state == "cancelled":
                continue
            if rec.state != "running" or not (rec.note or "").strip():
                raise UserError(_("Record a reason to cancel a running clock."))
            rec._worker_access()
            if rec.picking_id.state != "cancel" and not (self.env.user.has_group("stock.group_stock_manager")
                                                          or self.env.user.has_group("base.group_system")):
                raise AccessError(_("A manager must cancel a clock on an operation that is not cancelled."))
            super(WarehouseClock, rec).write({"state": "cancelled", "ended_at": fields.Datetime.now(),
                                              "ended_by": self.env.uid})
        return True
