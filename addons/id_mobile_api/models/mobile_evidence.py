import base64
import hashlib
import io
import json
import math
import warnings
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from psycopg2 import IntegrityError

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

from .mobile_workday import MobileReadConflict

MAX_PHOTO = 5 * 1024 * 1024
MAX_PIXELS = 12_000_000
KEYS = {"client_uuid", "outlet_id", "business_date", "snapshot_version", "photo_selected_at",
        "device_recorded_at", "fix_sampled_at", "latitude", "longitude", "accuracy"}


class EvidenceRejected(UserError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def utc_now():
    return datetime.now(timezone.utc)


def iso(value):
    return value.isoformat().replace("+00:00", "Z")


def parse_metadata(value):
    if not isinstance(value, dict) or set(value) != KEYS:
        raise EvidenceRejected("invalid_metadata")
    try:
        if str(UUID(value["client_uuid"])) != value["client_uuid"]:
            raise ValueError()
        if not isinstance(value["outlet_id"], str) or not value["outlet_id"].isdigit():
            raise ValueError()
        if not isinstance(value["snapshot_version"], str) or len(value["snapshot_version"]) > 128:
            raise ValueError()
        datetime.strptime(value["business_date"], "%Y-%m-%d")
        times = {}
        for key in ("photo_selected_at", "device_recorded_at", "fix_sampled_at"):
            stamp = datetime.fromisoformat(value[key].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError()
            times[key] = stamp.astimezone(timezone.utc)
        for key, low, high in (("latitude", -90, 90), ("longitude", -180, 180), ("accuracy", 0, 10000)):
            number = value[key]
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
                raise ValueError()
            if not low <= number <= high or (key == "accuracy" and number <= 0):
                raise ValueError()
        return times
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise EvidenceRejected("invalid_metadata") from None


def distance_m(lat, lon, anchor_lat, anchor_lon):
    a, b = math.radians(lat), math.radians(anchor_lat)
    h = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(math.radians(anchor_lon - lon) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def render_photo(source, metadata, received):
    if not source or len(source) > MAX_PHOTO:
        raise EvidenceRejected("invalid_photo")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(source)) as probe:
                if probe.format not in ("JPEG", "PNG") or probe.width * probe.height > MAX_PIXELS:
                    raise ValueError()
                if getattr(probe, "n_frames", 1) != 1:
                    raise ValueError()
                probe.verify()
            with Image.open(io.BytesIO(source)) as photo:
                photo = ImageOps.exif_transpose(photo).convert("RGB")
                photo.thumbnail((1280, 1280))
                canvas = Image.new("RGB", (max(640, photo.width), photo.height + 120), "#102746")
                canvas.paste(photo, ((canvas.width - photo.width) // 2, 0))
                draw = ImageDraw.Draw(canvas)
                device = datetime.fromisoformat(metadata["device_recorded_at"].replace("Z", "+00:00"))
                rows = [
                    "DEVICE RECORD: " + device.astimezone(ZoneInfo("Asia/Makassar")).strftime("%Y-%m-%d %H:%M:%S WITA"),
                    "SERVER RECEIPT: " + received.astimezone(ZoneInfo("Asia/Makassar")).strftime(
                        "%Y-%m-%d %H:%M:%S WITA"),
                    f"GPS {metadata['latitude']:.6f}, {metadata['longitude']:.6f} +/- {metadata['accuracy']:.1f} m",
                    "GPS/shutter authenticity not verified | evidence v1",
                ]
                try:
                    font = ImageFont.load_default(size=16)
                except TypeError:
                    font = ImageFont.load_default()
                for i, text in enumerate(rows):
                    draw.text((12, photo.height + 10 + i * 25), text, fill="white", font=font)
                result = io.BytesIO()
                canvas.save(result, "JPEG", quality=85)
                return result.getvalue()
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise EvidenceRejected("invalid_photo") from None


class MobileEvidence(models.Model):
    _name = "id.mobile.evidence"
    _description = "Mobile Location and Photo Evidence"
    _order = "id desc"
    _rec_name = "client_uuid"

    user_id = fields.Many2one("res.users", required=True, index=True, ondelete="restrict")
    company_id = fields.Many2one("res.company", required=True, index=True, ondelete="restrict")
    outlet_id = fields.Many2one("res.partner", required=True, ondelete="restrict")
    client_uuid = fields.Char(required=True, index=True)
    fingerprint = fields.Char(required=True)
    receipt_json = fields.Text(required=True)
    original = fields.Binary(required=True, attachment=True)
    watermarked = fields.Binary(required=True, attachment=True)
    _unique_uuid = models.Constraint("UNIQUE(user_id, client_uuid)", "Evidence UUID already exists for this user.")

    def write(self, vals):
        raise AccessError(_("Captured evidence is immutable."))

    @api.model
    def _actor(self):
        user = self.env.user
        if user.share or not user.active or not user.has_group("id_mobile_api.group_mobile_evidence"):
            raise AccessError(_("Mobile evidence access is not enabled."))
        if user.company_id not in user.company_ids:
            raise AccessError(_("Company access is not available."))
        return user

    @api.model
    def _owned(self, client_uuid):
        user = self._actor()
        return self.with_company(user.company_id).search([
            ("client_uuid", "=", client_uuid), ("user_id", "=", user.id), ("company_id", "=", user.company_id.id),
        ], limit=1)

    @api.model
    def _capture(self, metadata, source):
        user = self._actor()
        times = parse_metadata(metadata)
        if not source or len(source) > MAX_PHOTO:
            raise EvidenceRejected("invalid_photo")
        fingerprint = hashlib.sha256(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
                                     + hashlib.sha256(source).digest()).hexdigest()
        existing = self._owned(metadata["client_uuid"])
        if existing:
            if existing.fingerprint != fingerprint:
                raise MobileReadConflict(_("Evidence UUID cannot be reused for different content."))
            return json.loads(existing.receipt_json), False
        assignment, day = self.env["id.mobile.workday"]._current_assignment()
        snapshot = self.env["id.mobile.workday"]._snapshot_payload()
        if metadata["business_date"] != day.isoformat() or metadata["snapshot_version"] != snapshot["version"]:
            raise MobileReadConflict(_("The assignment changed; synchronize again."))
        outlet = assignment.outlet_ids.filtered(lambda row: str(row.id) == metadata["outlet_id"])
        if not outlet:
            raise AccessError(_("Outlet is not assigned to this user."))
        outlet.check_access("read")
        received = utc_now()
        if (not -1 <= (received - times["fix_sampled_at"]).total_seconds() <= 60
                or not -5 <= (received - times["photo_selected_at"]).total_seconds() <= 300
                or not -5 <= (received - times["device_recorded_at"]).total_seconds() <= 60
                or times["photo_selected_at"] > times["device_recorded_at"]):
            raise EvidenceRejected("stale_location_or_photo")
        distance = distance_m(metadata["latitude"], metadata["longitude"],
                              outlet.partner_latitude, outlet.partner_longitude)
        if distance > assignment.outlet_radius:
            if distance - metadata["accuracy"] > assignment.outlet_radius:
                raise EvidenceRejected("geofence_outside")
            elif metadata["accuracy"] > 100:
                raise EvidenceRejected("geofence_uncertain")
        rendered = render_photo(source, metadata, received)
        receipt = {
            "client_uuid": metadata["client_uuid"], "outlet_id": str(outlet.id),
            "user_id": str(user.id), "company_id": str(assignment.company_id.id),
            "warehouse_id": str(assignment.warehouse_id.id), "assignment_id": str(assignment.id),
            "business_date": day.isoformat(), "snapshot_version": snapshot["version"],
            "received_at": iso(received), "device_recorded_at": iso(times["device_recorded_at"]),
            "photo_selected_at": iso(times["photo_selected_at"]), "fix_sampled_at": iso(times["fix_sampled_at"]),
            "latitude": metadata["latitude"], "longitude": metadata["longitude"], "accuracy": metadata["accuracy"],
            "master_latitude": outlet.partner_latitude, "master_longitude": outlet.partner_longitude,
            "distance_m": distance, "radius_m": assignment.outlet_radius,
            "original_sha256": hashlib.sha256(source).hexdigest(),
            "watermarked_sha256": hashlib.sha256(rendered).hexdigest(),
        }
        binding = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        receipt["binding_sha256"] = hashlib.sha256(binding).hexdigest()
        receipt["original_url"] = f"/api/v1/evidence/{metadata['client_uuid']}/original"
        receipt["watermarked_url"] = f"/api/v1/evidence/{metadata['client_uuid']}/watermarked"
        assignment._assert_day(day)
        try:
            with self.env.cr.savepoint():
                # Narrow elevation: no business write grants. All scope/media checks
                # precede creation of this immutable, owner-bound evidence only.
                self.sudo().create({
                    "user_id": user.id, "company_id": assignment.company_id.id, "outlet_id": outlet.id,
                    "client_uuid": metadata["client_uuid"], "fingerprint": fingerprint,
                    "receipt_json": json.dumps(receipt), "original": base64.b64encode(source),
                    "watermarked": base64.b64encode(rendered),
                })
                assignment._assert_day(day)
        except IntegrityError as error:
            if error.pgcode != "23505":
                raise
            raise MobileReadConflict(_("Evidence submission raced; retry the same UUID.")) from None
        return receipt, True
