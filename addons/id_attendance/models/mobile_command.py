import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.id_mobile_api.models.mobile_evidence import utc_now
from odoo.addons.id_mobile_api.models.mobile_workday import MobileReadConflict

WITA = ZoneInfo("Asia/Makassar")
ATTENDANCE_COMMAND = "hris.attendance.capture"


class MobileCommand(models.Model):
    _inherit = "id.mobile.command"

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(vals.get("command_type") == ATTENDANCE_COMMAND for vals in vals_list):
            raise AccessError(_("PWA attendance receipts can only be created by the dispatcher."))
        return super().create(vals_list)

    def _supported_commands(self):
        return super()._supported_commands() | {ATTENDANCE_COMMAND}

    def _dispatch_extra_command(self, cmd_type, payload, client_uuid):
        if cmd_type != ATTENDANCE_COMMAND:
            return super()._dispatch_extra_command(cmd_type, payload, client_uuid)
        user, company = self._actor()
        employee = self.env["hr.employee"]._pwa_attendance_employee(user, company)
        evidence_uuid = payload.get("evidence_uuid")
        if set(payload) != {"evidence_uuid"} or not isinstance(evidence_uuid, str) or len(evidence_uuid) != 36:
            raise UserError(_("An attendance evidence reference is required."))

        evidence = self.env["id.mobile.evidence"]._owned(evidence_uuid)
        if (
            not evidence
            or not evidence.attendance_event
            or evidence.attendance_employee_id.id != employee.id
            or evidence.attendance_office_id.id != employee.pwa_attendance_office_id.id
        ):
            raise AccessError(_("The evidence is not valid for this employee and office."))

        receipt = json.loads(evidence.receipt_json)
        received = datetime.fromisoformat(receipt["received_at"])
        recorded = datetime.fromisoformat(receipt["device_recorded_at"])
        day = recorded.astimezone(WITA).date()
        now = utc_now()
        if now.astimezone(WITA).date() != day or not 0 <= (now - received).total_seconds() <= 300:
            raise UserError(_("Attendance evidence expired before posting."))

        # Serialize actions for the same employee across multiple devices.
        self.env.cr.execute("SELECT id FROM hr_employee WHERE id = %s FOR UPDATE", [employee.id])
        Attendance = self.env["hr.attendance"].sudo().with_company(company)
        session = Attendance.search([
            ("employee_id", "=", employee.id),
            ("pwa_business_date", "=", day),
        ], limit=1)
        stamp = recorded.astimezone(timezone.utc).replace(tzinfo=None)
        if evidence.attendance_event == "check_in":
            if session:
                raise MobileReadConflict(_("PWA check-in already exists for this day."))
            if Attendance.search_count([
                ("employee_id", "=", employee.id), ("check_out", "=", False),
            ], limit=1):
                raise MobileReadConflict(_("An earlier attendance is still open. Contact HR."))
            session = Attendance.create({
                "employee_id": employee.id,
                "check_in": stamp,
                "in_mode": "pwa",
                "pwa_business_date": day,
                "pwa_check_in_evidence_id": evidence.id,
            })
        else:
            if not session or (session.check_out and session.out_mode != "auto_check_out"):
                raise MobileReadConflict(_("No open PWA attendance for this day."))
            if stamp <= session.check_in:
                raise UserError(_("Check-out must be later than check-in."))
            session.write({
                "check_out": stamp,
                "out_mode": "pwa",
                "pwa_check_out_evidence_id": evidence.id,
            })
        return "accepted", _("PWA attendance recorded."), f"hr.attendance:{session.id}"
