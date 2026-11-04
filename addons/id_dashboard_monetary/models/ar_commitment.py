"""Immutable capture evidence and customer payment promises; no financial posting."""
import hashlib
import json
from math import isfinite

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


def finance(env):
    if not (env.user.has_group("account.group_account_user") or env.user.has_group("base.group_system")):
        raise AccessError(_("Accounting access is required."))


class ArAuditSnapshot(models.Model):
    _name = "id.ar.audit.snapshot"
    _description = "Immutable AR Evidence Capture"
    _order = "id desc"

    name = fields.Char(readonly=True)
    company_id = fields.Many2one("res.company", readonly=True, required=True)
    captured_by = fields.Many2one("res.users", readonly=True)
    captured_at = fields.Datetime(readonly=True)
    as_of = fields.Date(readonly=True)
    kind = fields.Selection([("ledger", "Ledger"), ("promise", "Promise Assessment")], readonly=True)
    payload_json = fields.Text(readonly=True)
    digest = fields.Char(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_("Use the capture action to create immutable evidence."))

    def write(self, vals):
        raise AccessError(_("Captured evidence cannot be changed."))

    def unlink(self):
        raise AccessError(_("Captured evidence cannot be deleted."))

    @api.model
    def _capture(self, payload, kind, as_of):
        finance(self.env)
        at = fields.Datetime.now()
        payload = dict(payload, company_id=self.env.company.id, company_name=self.env.company.name,
                       currency=self.env.company.currency_id.name,
                       currency_digits=self.env.company.currency_id.decimal_places,
                       captured_at=str(at), captured_by=self.env.uid)
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, allow_nan=False)
        return super().create({"name": "%s / %s / %s" % (kind, as_of, at), "kind": kind,
            "company_id": self.env.company.id, "captured_at": at, "captured_by": self.env.uid, "as_of": as_of,
            "payload_json": encoded, "digest": hashlib.sha256(encoded.encode()).hexdigest()})

    @api.model
    def capture_ledger(self, as_of=None, comparison=None, area_ids=None, salesman_ids=None):
        finance(self.env)
        if len(self.env.companies) != 1:
            raise UserError(_("Select exactly one company before freezing AR evidence."))
        scoped = self.with_context(allowed_company_ids=[self.env.company.id])
        payload = scoped.env["id.ar.history"]._snapshot(as_of, comparison, area_ids, salesman_ids, include_sources=True)
        return scoped._capture(payload, "ledger", payload["as_of"]).id

    def action_verify(self):
        self.check_access("read")
        for rec in self:
            if hashlib.sha256(rec.payload_json.encode()).hexdigest() != rec.digest:
                raise UserError(_("Evidence integrity check failed."))
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"message": _("Evidence digest verified."), "type": "success"}}


class ArPromise(models.Model):
    _name = "id.ar.promise"
    _description = "Customer Payment Promise"
    _check_company_auto = True
    _order = "due_date, id"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    line_id = fields.Many2one("account.move.line", required=True, check_company=True, ondelete="restrict")
    partner_id = fields.Many2one(related="line_id.partner_id")
    owner_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user)
    amount = fields.Monetary(required=True)
    due_date = fields.Date(required=True)
    source = fields.Char(required=True, string="Customer Agreement Reference")
    state = fields.Selection([("draft", "Draft"), ("committed", "Committed")], default="draft", readonly=True)
    committed_date = fields.Date(readonly=True)
    baseline_json = fields.Text(readonly=True)
    outcome = fields.Selection([("draft", "Draft"), ("open", "Open"), ("kept", "Kept"), ("broken", "Broken")],
                               compute="_compute_outcome")
    settled_amount = fields.Monetary(compute="_compute_outcome")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if set(vals).intersection({"state", "committed_date", "baseline_json"}) - (
                    {"state"} if vals.get("state") == "draft" else set()):
                raise AccessError(_("Promise commitment facts are protected."))
            vals.update(state="draft", committed_date=False, baseline_json=False)
        return super().create(vals_list)

    def write(self, vals):
        if set(vals).intersection({"state", "committed_date", "baseline_json"}) or any(
                rec.state == "committed" for rec in self):
            raise AccessError(_("Committed promises cannot be changed; record a new agreement."))
        return super().write(vals)

    def unlink(self):
        if any(rec.state == "committed" for rec in self):
            raise AccessError(_("Committed promises cannot be deleted."))
        return super().unlink()

    @api.constrains("amount", "line_id", "company_id", "owner_id")
    def _check_promise(self):
        for rec in self:
            if not isfinite(rec.amount) or rec.amount <= 0:
                raise ValidationError(_("Promised amount must be positive and finite."))
            if (rec.line_id.account_id.account_type != "asset_receivable" or rec.line_id.parent_state != "posted"
                    or rec.line_id.balance <= 0 or rec.company_id not in rec.owner_id.company_ids):
                raise ValidationError(_("Choose a posted debit receivable and an owner in its company."))

    def action_commit(self):
        finance(self.env)
        self.check_access("write")
        for rec in self.sorted("line_id"):
            if rec.state != "draft" or rec.due_date < fields.Date.context_today(rec):
                raise UserError(_("Use a draft promise with a current or future due date."))
            self.env.cr.execute("UPDATE account_move_line SET write_date=write_date WHERE id=%s", [rec.line_id.id])
            others = self.search([("line_id", "=", rec.line_id.id), ("state", "=", "committed"),
                                  ("due_date", ">=", fields.Date.context_today(rec))])
            if any(p.currency_id.compare_amounts(p.amount, p.settled_amount) > 0 for p in others):
                raise UserError(_("This receivable already has an unfulfilled current promise."))
            outstanding = sum(max(p.amount-p.settled_amount, 0) for p in others)
            if rec.amount + outstanding > rec.line_id.amount_residual + rec.currency_id.rounding/2:
                raise UserError(_("Promises exceed the currently open receivable."))
            ids = self.env["account.partial.reconcile"].search([("debit_move_id", "=", rec.line_id.id)]).ids
            super(ArPromise, rec).write({"state": "committed", "committed_date": fields.Date.context_today(rec),
                                         "baseline_json": json.dumps(ids)})
        return True

    def _assessment(self):
        self.ensure_one()
        if self.state != "committed":
            return {"outcome": "draft", "settled": 0, "sources": []}
        baseline = set(json.loads(self.baseline_json))
        parts = self.env["account.partial.reconcile"].search([("debit_move_id", "=", self.line_id.id),
            ("id", "not in", list(baseline)), ("max_date", ">=", self.committed_date),
            ("max_date", "<=", self.due_date)])
        sources, settled = [], 0.
        for part in parts:
            move = part.credit_move_id.move_id
            payment = move.origin_payment_id
            if (move.state == "posted" and payment and payment.move_id == move and payment.payment_type == "inbound"
                    and payment.state == "paid" and payment.is_matched
                    and self.committed_date <= payment.date <= self.due_date):
                settled += part.amount
                sources.append({"partial_id": part.id, "payment_id": payment.id, "amount": part.amount,
                                "payment_date": str(payment.date)})
        outcome = ("kept" if self.currency_id.compare_amounts(settled, self.amount) >= 0 else
                   "broken" if fields.Date.context_today(self) > self.due_date else "open")
        return {"outcome": outcome, "settled": settled, "sources": sources,
                "basis": "new_allocations_current_paid_and_bank_matched_accounting_dates",
                "promise_id": self.id, "amount": self.amount, "due_date": str(self.due_date)}

    @api.depends("state", "amount", "due_date", "line_id.matched_credit_ids",
                 "line_id.matched_credit_ids.amount", "line_id.matched_credit_ids.max_date",
                 "line_id.matched_credit_ids.credit_move_id.move_id.origin_payment_id.state",
                 "line_id.matched_credit_ids.credit_move_id.move_id.origin_payment_id.is_matched")
    def _compute_outcome(self):
        for rec in self:
            result = rec._assessment()
            rec.outcome, rec.settled_amount = result["outcome"], result["settled"]

    def action_capture_assessment(self):
        finance(self.env)
        self.ensure_one()
        scoped = self.with_context(allowed_company_ids=[self.company_id.id])
        snap = scoped.env["id.ar.audit.snapshot"]._capture(
            scoped._assessment(), "promise", fields.Date.context_today(self))
        return {"type": "ir.actions.act_window", "res_model": "id.ar.audit.snapshot", "res_id": snap.id,
                "views": [[False, "form"]]}
