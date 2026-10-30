import math

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MobileOffice(models.Model):
    _name = "id.mobile.office"
    _description = "Mobile Office Location"
    _check_company_auto = True

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    latitude = fields.Float(required=True, digits=(10, 7))
    longitude = fields.Float(required=True, digits=(10, 7))
    radius = fields.Integer(string="Office Radius (m)", default=50, required=True)
    coordinate_status = fields.Selection(
        [
            ("test", "Test Coordinates"),
            ("unverified", "Unverified Coordinates"),
            ("verified", "Verified Coordinates"),
        ],
        required=True,
        default="unverified",
    )
    coordinate_note = fields.Char(string="Coordinate Source / Verification Note", required=True)

    @api.constrains("latitude", "longitude", "radius", "coordinate_status", "coordinate_note")
    def _check_coordinates(self):
        for office in self:
            if (
                not math.isfinite(office.latitude)
                or not math.isfinite(office.longitude)
                or not -90 <= office.latitude <= 90
                or not -180 <= office.longitude <= 180
                or (office.latitude == 0 and office.longitude == 0)
                or not 5 <= office.radius <= 500
                or not (office.coordinate_note or "").strip()
            ):
                raise ValidationError(
                    _("Office requires valid coordinates, a source note and radius between 5 and 500 metres.")
                )

    def _map_payload(self):
        self.ensure_one()
        self.check_access("read")
        self._check_coordinates()
        if not self.active:
            raise ValidationError(_("The assigned office is inactive."))
        return {
            "id": str(self.id),
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "radius": self.radius,
            "coordinate_status": self.coordinate_status,
        }
