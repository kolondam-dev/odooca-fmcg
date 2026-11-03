"""Operator event clocks tied to native ready/completed warehouse operations."""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

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
                if rec.picking_id.state != "done":
                    raise UserError(_("Complete the native receipt before closing receiving dwell."))
                frontier, seen = rec.picking_id.move_ids, set()
                while frontier:
                    active = frontier.filtered(lambda m: m.state != "cancel")
                    if any(m.state != "done" for m in active):
                        raise UserError(_("Complete the active native receipt and putaway chain first."))
                    seen.update(frontier.ids)
                    frontier = active.move_dest_ids.filtered(lambda m: m.id not in seen)
                    if len(seen) > 5000:
                        raise UserError(_("Operation chain is too large."))
                if not self.env["stock.location"].search_count([
                        ("id", "=", end.location_dest_id.id), ("id", "child_of", rec.warehouse_id.lot_stock_id.id)]):
                    raise UserError(_("Receiving dwell ends only when goods reach warehouse storage."))
                if end != rec.picking_id:
                    frontier, seen, linked = end.move_ids, set(), False
                    while frontier:
                        if set(frontier.ids).intersection(rec.picking_id.move_ids.ids):
                            linked = True
                            break
                        seen.update(frontier.ids)
                        frontier = frontier.move_orig_ids.filtered(lambda m: m.id not in seen)
                        if len(seen) > 5000:
                            raise UserError(_("Operation chain is too large."))
                    if not linked:
                        raise UserError(_("Completion must belong to the same native receipt chain."))
            now = fields.Datetime.now()
            if now < rec.started_at:
                raise UserError(_("Clock end cannot precede its start."))
            super(WarehouseClock, rec).write({"state": "done", "ended_at": now, "ended_by": self.env.uid})
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
