from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    in_mode = fields.Selection(selection_add=[("pwa", "PWA")], ondelete={"pwa": "set default"})
    out_mode = fields.Selection(selection_add=[("pwa", "PWA")], ondelete={"pwa": "set default"})

    pwa_check_in_evidence_id = fields.Many2one(
        "id.mobile.evidence", readonly=True, copy=False, index=True, ondelete="restrict",
        groups="hr.group_hr_manager",
    )
    pwa_check_out_evidence_id = fields.Many2one(
        "id.mobile.evidence", readonly=True, copy=False, ondelete="restrict",
        groups="hr.group_hr_manager",
    )
    pwa_business_date = fields.Date(readonly=True, copy=False, index=True)

    _unique_pwa_day = models.Constraint(
        "UNIQUE(employee_id, pwa_business_date)",
        "Only one PWA attendance session is allowed per employee and business day.",
    )
    _unique_pwa_in = models.Constraint(
        "UNIQUE(pwa_check_in_evidence_id)",
        "PWA check-in evidence can only be used once.",
    )
    _unique_pwa_out = models.Constraint(
        "UNIQUE(pwa_check_out_evidence_id)",
        "PWA check-out evidence can only be used once.",
    )

    def _check_pwa_provenance_write(self, vals):
        provenance = {"pwa_business_date", "pwa_check_in_evidence_id", "pwa_check_out_evidence_id"}
        if not self.env.su and (provenance.intersection(vals) or "pwa" in (vals.get("in_mode"), vals.get("out_mode"))):
            raise AccessError(_("PWA attendance provenance can only be set by the dispatcher."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_pwa_provenance_write(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._check_pwa_provenance_write(vals)
        return super().write(vals)
