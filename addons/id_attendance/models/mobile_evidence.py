import base64
import hashlib
import json

from psycopg2 import IntegrityError

from odoo import _, fields, models
from odoo.addons.id_mobile_api.models.mobile_evidence import (
    KEYS, MAX_PHOTO, EvidenceRejected, distance_m, iso, parse_metadata, render_photo, utc_now,
)
from odoo.addons.id_mobile_api.models.mobile_workday import MobileReadConflict

from .mobile_command import WITA

ATTENDANCE_KEYS = (KEYS - {"outlet_id", "snapshot_version"}) | {"attendance_event"}


class MobileEvidence(models.Model):
    _inherit = "id.mobile.evidence"

    outlet_id = fields.Many2one(required=False)
    attendance_office_id = fields.Many2one("id.mobile.office", readonly=True, ondelete="restrict")
    attendance_employee_id = fields.Many2one("hr.employee", readonly=True, ondelete="restrict")
    attendance_event = fields.Selection(
        [("check_in", "Check In"), ("check_out", "Check Out")], readonly=True,
    )

    def _capture(self, metadata, source):
        if not isinstance(metadata, dict) or "attendance_event" not in metadata:
            return super()._capture(metadata, source)

        user = self._actor()
        company = user.company_id
        employee = self.env["hr.employee"]._pwa_attendance_employee(user, company)
        office = employee.pwa_attendance_office_id
        times = parse_metadata(metadata, ATTENDANCE_KEYS, set())
        event = metadata["attendance_event"]
        if event not in ("check_in", "check_out"):
            raise EvidenceRejected("invalid_metadata")
        if not source or len(source) > MAX_PHOTO:
            raise EvidenceRejected("invalid_photo")

        original_hash = hashlib.sha256(source).hexdigest()
        fingerprint = hashlib.sha256(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode() + bytes.fromhex(original_hash)
        ).hexdigest()
        existing = self._owned(metadata["client_uuid"])
        if existing:
            if existing.fingerprint != fingerprint or existing.attendance_employee_id != employee:
                raise MobileReadConflict(_("Evidence UUID cannot be reused for different content."))
            return json.loads(existing.receipt_json), False

        received = utc_now()
        recorded = times["device_recorded_at"]
        day = received.astimezone(WITA).date()
        if (
            metadata["business_date"] != day.isoformat()
            or recorded.astimezone(WITA).date() != day
            or not -5 <= (received - recorded).total_seconds() <= 60
            or not 0 <= (recorded - times["photo_selected_at"]).total_seconds() <= 300
            or not 0 <= (recorded - times["fix_sampled_at"]).total_seconds() <= 60
        ):
            raise EvidenceRejected("stale_location_or_photo")

        distance = distance_m(metadata["latitude"], metadata["longitude"], office.latitude, office.longitude)
        if distance + metadata["accuracy"] >= office.radius:
            code = "geofence_outside" if distance - metadata["accuracy"] > office.radius else "geofence_uncertain"
            raise EvidenceRejected(code)

        rendered = render_photo(source, metadata, received)
        uuid = metadata["client_uuid"]
        receipt = {
            **metadata,
            "user_id": str(user.id),
            "company_id": str(company.id),
            "office_id": str(office.id),
            "received_at": iso(received),
            "distance_m": distance,
            "radius_m": office.radius,
            "original_sha256": original_hash,
            "watermarked_sha256": hashlib.sha256(rendered).hexdigest(),
            "original_url": f"/api/v1/evidence/{uuid}/original",
            "watermarked_url": f"/api/v1/evidence/{uuid}/watermarked",
        }
        try:
            with self.env.cr.savepoint():
                self.sudo().create({
                    "user_id": user.id,
                    "company_id": company.id,
                    "attendance_employee_id": employee.id,
                    "attendance_office_id": office.id,
                    "attendance_event": event,
                    "client_uuid": uuid,
                    "fingerprint": fingerprint,
                    "receipt_json": json.dumps(receipt),
                    "original": base64.b64encode(source),
                    "watermarked": base64.b64encode(rendered),
                })
        except IntegrityError as error:
            if error.pgcode != "23505":
                raise
            raise MobileReadConflict(_("Evidence submission raced; retry the same UUID.")) from None
        return receipt, True
