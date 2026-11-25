from odoo import models
from odoo.exceptions import AccessError


class MobileWorkday(models.Model):
    _inherit = "id.mobile.workday"

    def _bootstrap_payload(self):
        result = super()._bootstrap_payload()
        user = self.env.user
        if not user.has_group("id_mobile_api.group_mobile_evidence"):
            return result
        try:
            employee = self.env["hr.employee"]._pwa_attendance_employee(user, user.company_id)
        except AccessError:
            return result
        result["attendanceOffice"] = employee.pwa_attendance_office_id._map_payload()
        return result
