from odoo import _, fields, models
from odoo.exceptions import AccessError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    pwa_attendance_office_id = fields.Many2one(
        "id.mobile.office",
        string="PWA Attendance Office",
        check_company=True,
        ondelete="restrict",
        groups="hr.group_hr_manager",
        help="Set a verified office to enable PWA attendance for this employee.",
    )

    def _pwa_attendance_employee(self, user, company):
        employees = self.sudo().with_company(company).search([
            ("user_id", "=", user.id),
            ("company_id", "=", company.id),
        ], limit=2)
        if len(employees) != 1:
            raise AccessError(_("An active employee mapping is required for PWA attendance."))
        office = employees.pwa_attendance_office_id
        if not office.active or office.company_id != company or office.coordinate_status != "verified":
            raise AccessError(_("A verified attendance office is required."))
        return employees
