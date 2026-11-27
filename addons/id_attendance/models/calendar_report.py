from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AttendanceHoliday(models.Model):
    _name = "id.attendance.holiday"
    _description = "Attendance Reporting Holiday"
    _order = "date_from desc, id"
    _check_company_auto = True

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    calendar_id = fields.Many2one("resource.calendar", check_company=True, ondelete="restrict")
    work_location_id = fields.Many2one("hr.work.location", check_company=True, ondelete="restrict")
    date_from = fields.Date(required=True, index=True)
    date_to = fields.Date(required=True, index=True)
    kind = fields.Selection(
        [("national", "National Holiday"), ("joint", "Collective Leave"),
         ("regional", "Regional Holiday"), ("internal", "Company Holiday")],
        required=True,
    )
    source = fields.Char(required=True, help="Document number, decision reference, or official URL.")

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for holiday in self:
            if holiday.date_to < holiday.date_from:
                raise ValidationError(_("The end date must be on or after the start date."))


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    pwa_report_category = fields.Selection(
        [("leave", "Time Off"), ("sick", "Sick Leave"), ("permission", "Permission")],
        default="leave", required=True,
        help="Category used in the PWA attendance report for this time off type.",
    )


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    pwa_attendance_report_from = fields.Date(
        string="PWA Reporting Coverage Start",
        groups="hr.group_hr_manager",
        help="First date with reliable PWA coverage. Missing entries before this date are not counted as absent.",
    )
