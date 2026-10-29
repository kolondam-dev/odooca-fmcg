import base64
import json

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from ..models.mobile_evidence import EvidenceRejected, MAX_PHOTO
from ..models.mobile_workday import MobileReadConflict
from .read_api import MobileReadApi


class MobileEvidenceApi(MobileReadApi):
    def _guard(self):
        if not request.session.uid or request.env.uid != request.session.uid:
            return self._response({"error": "not_authenticated"}, 401)
        try:
            request.env["id.mobile.evidence"]._actor()
        except AccessError:
            return self._response({"error": "forbidden"}, 403)
        origin = request.httprequest.headers.get("Origin")
        if (request.httprequest.args or request.httprequest.headers.get("Sec-Fetch-Site") == "cross-site"
                or (origin and origin != request.httprequest.host_url.rstrip("/"))):
            return self._response({"error": "invalid_request"}, 400)
        return None

    @http.route("/api/v1/evidence", type="http", auth="public", methods=["POST"], csrf=True)
    def capture(self, **kwargs):
        denied = self._guard()
        if denied is not None:
            return denied
        if not request.httprequest.content_length or request.httprequest.content_length > MAX_PHOTO + 32768:
            return self._response({"error": "photo_too_large"}, 413)
        if (set(request.httprequest.form) != {"csrf_token", "metadata"}
                or len(request.httprequest.form.getlist("metadata")) != 1
                or len(request.httprequest.form.getlist("csrf_token")) != 1
                or set(request.httprequest.files) != {"photo"}
                or len(request.httprequest.files.getlist("photo")) != 1):
            return self._response({"error": "invalid_request"}, 400)
        try:
            encoded = request.httprequest.form["metadata"]
            if len(encoded) > 4096:
                raise ValueError()
            metadata = json.loads(encoded)
            photo = request.httprequest.files["photo"].stream.read(MAX_PHOTO + 1)
            receipt, created = request.env["id.mobile.evidence"]._capture(metadata, photo)
            return self._response(receipt, 201 if created else 200)
        except (ValueError, TypeError):
            return self._response({"error": "invalid_metadata"}, 422)
        except AccessError:
            return self._response({"error": "forbidden"}, 403)
        except MobileReadConflict:
            return self._response({"error": "scope_changed_or_uuid_conflict"}, 409)
        except EvidenceRejected as error:
            return self._response({"error": error.code}, 422)
        except UserError:
            return self._response({"error": "configuration_unavailable"}, 422)

    @http.route("/api/v1/evidence/<uuid:client_uuid>/<string:variant>", type="http", auth="public",
                methods=["GET"], readonly=True)
    def photo(self, client_uuid, variant, **kwargs):
        denied = self._guard()
        if denied is not None:
            return denied
        if variant not in ("original", "watermarked"):
            return self._response({"error": "not_found"}, 404)
        record = request.env["id.mobile.evidence"]._owned(str(client_uuid))
        if not record:
            return self._response({"error": "not_found"}, 404)
        record.check_access("read")
        content = base64.b64decode(record[variant])
        content_type = "image/jpeg" if variant == "watermarked" or content.startswith(b"\xff\xd8") else "image/png"
        extension = "jpg" if content_type == "image/jpeg" else "png"
        return request.make_response(content, headers=[
            ("Content-Type", content_type), ("Content-Disposition", f'inline; filename="evidence.{extension}"'),
            ("Cache-Control", "no-store, private"), ("Vary", "Cookie"), ("X-Content-Type-Options", "nosniff"),
        ])
