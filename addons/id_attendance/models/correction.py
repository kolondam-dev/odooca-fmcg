from datetime import datetime, time
from uuid import UUID

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .attendance_report import business_today, utc, utc_naive
from .mobile_command import WITA


MODEL = "id.attendance.correction"
CODE = "attendance_correction"
REQUEST = "fmcg.approval.request"
DIRECTOR = "id_approval.group_fmcg_approval_director"


class AttendanceCorrection(models.Model):
    _name = MODEL
    _description = "Attendance Correction"
    _order = "id desc"

    employee_id = fields.Many2one("hr.employee", required=True, readonly=True, index=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True, index=True)
    requester_id = fields.Many2one("res.users", required=True, readonly=True, index=True)
    business_date = fields.Date(required=True, index=True)
    start_hour = fields.Float(string="Corrected Check In (WITA)", required=True)
    end_hour = fields.Float(string="Corrected Check Out (WITA)", required=True)
    reason = fields.Text(required=True)
    client_key = fields.Char(readonly=True, copy=False)
    approval_id = fields.Many2one(REQUEST, readonly=True, copy=False, ondelete="restrict")
    state = fields.Selection(related="approval_id.state", readonly=True)
    check_in = fields.Datetime(readonly=True)
    check_out = fields.Datetime(readonly=True)

    _client_unique = models.Constraint("unique(requester_id, client_key)", "This submission already exists.")

    @api.model_create_multi
    def create(self, vals_list):
        user = self.env.user
        company = self.env.company
        employees = self.env["hr.employee"].sudo().search([
            ("user_id", "=", user.id), ("company_id", "=", company.id),
        ], limit=2)
        if len(employees) != 1:
            raise UserError(_("Your account must be linked to one employee in the current company."))
        coverage = employees.pwa_attendance_report_from
        if not coverage:
            raise UserError(_("Your PWA reporting coverage has not been configured."))
        prepared = []
        for vals in vals_list:
            day = fields.Date.to_date(vals.get("business_date"))
            if not day or day >= business_today() or day < coverage:
                raise UserError(_("Choose a closed date within your PWA reporting coverage."))
            start = float(vals.get("start_hour", 0))
            end = float(vals.get("end_hour", 0))
            reason = (vals.get("reason") or "").strip()
            if not 0 <= start < end < 24 or not reason or len(reason) > 1000:
                raise UserError(_("Provide ordered WITA times and a reason of up to 1,000 characters."))
            def stamp(hour):
                minute = round(hour * 60)
                if minute >= 1440:
                    raise UserError(_("Time must be within the chosen business date."))
                return utc_naive(datetime.combine(day, time(minute // 60, minute % 60), WITA))

            check_in, check_out = stamp(start), stamp(end)
            if check_in >= check_out:
                raise UserError(_("Check out must be after check in."))
            prepared.append({
                "employee_id": employees.id, "requester_id": user.id, "company_id": company.id,
                "business_date": day, "start_hour": start, "end_hour": end,
                "check_in": check_in, "check_out": check_out, "reason": reason,
                "client_key": str(UUID(vals["client_key"])) if vals.get("client_key") else False,
                "approval_id": False,
            })
        return super().create(prepared)

    def action_submit(self):
        self.ensure_one()
        self.check_access("read")
        if self.requester_id != self.env.user or self.company_id != self.env.company:
            raise AccessError(_("Only the requester can submit this correction."))
        self.env.cr.execute("SELECT id FROM id_attendance_correction WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset(["approval_id"])
        if self.approval_id:
            return
        supervisor = self.employee_id.sudo().parent_id
        manager = supervisor.parent_id
        chain = supervisor.user_id | manager.user_id
        if (len(chain) != 2 or self.env.user in chain
                or any(u.share or not u.active or self.company_id not in u.company_ids for u in chain)):
            raise UserError(_("Configure two distinct active WITA approvers in the employee hierarchy."))
        owners = self.env.ref(DIRECTOR).sudo().all_user_ids.filtered(
            lambda u: u.active and not u.share and self.company_id in u.company_ids
        ) - self.env.user - chain
        if not owners:
            raise UserError(_("Configure an eligible company owner who is outside the first two tiers."))
        category = self.env.ref("id_attendance.approval_category_attendance")
        approval = self.env[REQUEST].sudo().create({
            "category_id": category.id, "res_model": MODEL, "res_id": self.id,
            "reference_document": (f"{self.employee_id.sudo().name} · {self.business_date} · "
                                   f"{utc(self.check_in).astimezone(WITA):%H:%M}–"
                                   f"{utc(self.check_out).astimezone(WITA):%H:%M} WITA"),
            "requested_by": self.requester_id.id, "company_id": self.company_id.id,
            "reason": self.reason, "state": "pending", "current_tier_sequence": 1,
            "attendance_participant_ids": [fields.Command.set((chain | owners | self.requester_id).ids)],
            "line_ids": [
                fields.Command.create({"tier_sequence": 1, "tier_name": _("Line Supervisor"),
                                       "approver_type": "user", "user_id": supervisor.user_id.id,
                                       "state": "pending"}),
                fields.Command.create({"tier_sequence": 2, "tier_name": _("Line Manager"),
                                       "approver_type": "user", "user_id": manager.user_id.id}),
                fields.Command.create({"tier_sequence": 3, "tier_name": _("Owner"),
                                       "approver_type": "group", "group_id": self.env.ref(DIRECTOR).id}),
            ],
        })
        self.sudo().write({"approval_id": approval.id})

    def action_open_approval(self):
        self.ensure_one()
        self.check_access("read")
        self.approval_id.check_access("read")
        return {"type": "ir.actions.act_window", "res_model": REQUEST,
                "view_mode": "form", "res_id": self.approval_id.id}


class ApprovalCategory(models.Model):
    _inherit = "fmcg.approval.category"

    res_model = fields.Selection(selection_add=[(MODEL, "Attendance Correction")],
                                 ondelete={MODEL: "cascade"})

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(vals.get("code", self.env.context.get("default_code")) == CODE
                                   for vals in vals_list):
            raise AccessError(_("Attendance approval configuration is managed by the module."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and (vals.get("code") == CODE or CODE in self.mapped("code")):
            raise AccessError(_("Attendance approval configuration is managed by the module."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_attendance_category(self):
        if CODE in self.mapped("code"):
            raise AccessError(_("The attendance approval category cannot be removed."))


class ApprovalRequest(models.Model):
    _inherit = REQUEST

    attendance_participant_ids = fields.Many2many(
        "res.users", "fmcg_approval_attendance_participant_rel", readonly=True, copy=False,
    )

    @api.model
    def _server_owned_extra_fields(self):
        return super()._server_owned_extra_fields() | {
            "attendance_participant_ids", "reference_document", "reason", "company_id",
        }

    @api.model
    def _server_owned_category_codes(self):
        return (*super()._server_owned_category_codes(), CODE)

    @api.depends("state", "current_tier_sequence", "line_ids")
    @api.depends_context("uid")
    def _compute_is_current_user_approver(self):
        corrections = self.filtered(lambda req: req.category_code == CODE)
        super(ApprovalRequest, self - corrections)._compute_is_current_user_approver()
        for req in corrections:
            req.is_current_user_approver = req._correction_can_decide()

    def _correction_can_decide(self):
        self.ensure_one()
        user = self.env.user
        if self.state != "pending" or self.company_id not in self.env.companies or self.requested_by == user:
            return False
        lines = self.sudo().line_ids
        line = lines.filtered(lambda item: item.state == "pending"
                              and item.tier_sequence == self.current_tier_sequence)
        if not line or user in lines.actual_approver_id:
            return False
        return line.user_id == user if line.user_id else (
            user in self.sudo().attendance_participant_ids and user.has_group(DIRECTOR)
        )

    def _search_is_current_user_approver(self, operator, value):
        domain = super()._search_is_current_user_approver(operator, value)
        if not domain:
            return domain
        ids = set(domain[0][2])
        for req in self.search([("category_code", "=", CODE), ("state", "=", "pending")]):
            if req._correction_can_decide():
                ids.add(req.id)
            else:
                ids.discard(req.id)
        return [("id", domain[0][1], list(ids))]

    @api.model
    def _attendance_correction_page(self, queue, before):
        limit = 50
        domain = [
            ("category_code", "=", CODE),
            ("company_id", "=", self.env.company.id),
        ]
        if before is not None:
            domain.append(("id", "<", before))
        active = self.search([*domain, ("state", "=", "pending")]).filtered(
            lambda approval: approval._correction_can_decide()
        )
        domain.append(("id", "in" if queue == "actionable" else "not in", active.ids))
        records = self.search(domain, order="id desc", limit=limit + 1)
        page = records[:limit]
        return page, page[-1].id if len(records) > limit else None

    def _check_correction_decision(self, expected_tier=None):
        for req in self.filtered(lambda item: item.category_code == CODE):
            req.check_access("read")
            self.env.cr.execute("SELECT id FROM fmcg_approval_request WHERE id = %s FOR UPDATE", [req.id])
            req.invalidate_recordset(["state", "current_tier_sequence", "line_ids"])
            req.sudo().line_ids.invalidate_recordset(["state", "actual_approver_id"])
            if expected_tier is not None and expected_tier != req.current_tier_sequence:
                raise UserError(_("The approval tier changed. Refresh and review the request."))
            if not req._correction_can_decide():
                raise AccessError(_("This correction is not assigned to you at the active tier."))

    def action_approve(self, notes="", expected_tier=None):
        self._check_correction_decision(expected_tier)
        return super().action_approve(notes)

    def action_reject(self, notes="", expected_tier=None):
        self._check_correction_decision(expected_tier)
        return super().action_reject(notes)

    def action_submit(self):
        if any(req.category_code == CODE for req in self):
            raise AccessError(_("Submit the correction from its source record."))
        return super().action_submit()

    def action_cancel(self):
        if any(req.category_code == CODE for req in self):
            raise AccessError(_("Attendance corrections cannot be cancelled from the approval record."))
        return super().action_cancel()

    def action_open_correction_decision(self):
        self.ensure_one()
        self.check_access("read")
        if self.category_code != CODE or not self._correction_can_decide():
            raise AccessError(_("This correction is not assigned to you at the active tier."))
        return {
            "type": "ir.actions.act_window", "res_model": "id.attendance.correction.decision",
            "view_mode": "form", "target": "new",
            "context": {"default_approval_id": self.id, "default_tier": self.current_tier_sequence},
        }


class AttendanceCorrectionDecision(models.TransientModel):
    _name = "id.attendance.correction.decision"
    _description = "Attendance Correction Decision"

    approval_id = fields.Many2one(REQUEST, required=True, readonly=True)
    tier = fields.Integer(required=True, readonly=True)
    notes = fields.Text()

    def _decide(self, approved):
        self.ensure_one()
        self.check_access("read")
        self.approval_id.check_access("read")
        if self.approval_id.category_code != CODE:
            raise AccessError(_("This action only applies to attendance corrections."))
        notes = (self.notes or "").strip()
        if len(notes) > 1000:
            raise UserError(_("Provide a note of up to 1,000 characters."))
        method = self.approval_id.action_approve if approved else self.approval_id.action_reject
        method(notes=notes, expected_tier=self.tier)
        return {"type": "ir.actions.act_window_close"}

    def action_approve(self):
        return self._decide(True)

    def action_reject(self):
        return self._decide(False)
