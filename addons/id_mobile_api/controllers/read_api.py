import base64

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from ..models.mobile_workday import MobileReadConflict


class MobileReadApi(http.Controller):
    def _response(self, data, status=200):
        return request.make_json_response(data, status=status, headers=[
            ("Cache-Control", "no-store, private, max-age=0"), ("Pragma", "no-cache"),
            ("Expires", "0"), ("Vary", "Cookie"), ("X-Content-Type-Options", "nosniff"),
        ])

    def _gate(self):
        # auth=public allows an explicit JSON401 rather than an HTML login redirect.
        if not request.session.uid or request.env.uid != request.session.uid:
            return self._response({"error": "not_authenticated"}, 401)
        user = request.env.user
        if not user.active or user.share or not user.has_group("id_mobile_api.group_mobile_sales"):
            return self._response({"error": "forbidden"}, 403)
        origin = request.httprequest.headers.get("Origin")
        if (request.httprequest.args or request.httprequest.headers.get("Sec-Fetch-Site") == "cross-site"
                or (origin and origin != request.httprequest.host_url.rstrip("/"))):
            return self._response({"error": "invalid_request"}, 400)
        return None

    def _read(self, bootstrap):
        denied = self._gate()
        if denied is not None:
            return denied
        try:
            service = request.env["id.mobile.workday"]
            payload = service._bootstrap_payload() if bootstrap else service._snapshot_payload()
            if bootstrap:
                payload["csrfToken"] = request.csrf_token()
            return self._response(payload)
        except AccessError:
            return self._response({"error": "forbidden"}, 403)
        except MobileReadConflict:
            return self._response({"error": "scope_changed"}, 409)
        except UserError:
            return self._response({"error": "configuration_unavailable"}, 422)

    @http.route("/api/v1/me/bootstrap", type="http", auth="public", methods=["GET"], readonly=True)
    def bootstrap(self, **kwargs):
        return self._read(True)

    @http.route("/api/v1/sync/snapshot", type="http", auth="public", methods=["GET"], readonly=True)
    def snapshot(self, **kwargs):
        return self._read(False)

    @http.route("/api/v1/outlets/<int:outlet_id>/image", type="http", auth="public", methods=["GET"], readonly=True)
    def outlet_image(self, outlet_id, **kwargs):
        denied = self._gate()
        if denied is not None:
            return denied
        try:
            service = request.env["id.mobile.workday"]
            assignment, day = service._current_assignment()
            partner = assignment.outlet_ids.filtered(lambda p: p.id == outlet_id)
            if not partner or (partner.company_id and partner.company_id != assignment.company_id):
                return self._response({"error": "forbidden"}, 403)
            partner.check_access("read")
            if not partner.image_128:
                return self._response({"error": "not_found"}, 404)
            data = base64.b64decode(partner.image_128)
            mime = None
            if data.startswith(b"\x89PNG"):
                mime = "image/png"
            elif data.startswith(b"\xff\xd8"):
                mime = "image/jpeg"
            elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
                mime = "image/webp"
            if not mime:
                return self._response({"error": "invalid_image"}, 422)
            service._assert_day(day)
            return request.make_response(data, headers=[("Content-Type", mime),
                ("Cache-Control", "no-store, private, max-age=0"), ("Vary", "Cookie"),
                ("X-Content-Type-Options", "nosniff")])
        except AccessError:
            return self._response({"error": "forbidden"}, 403)
        except MobileReadConflict:
            return self._response({"error": "scope_changed"}, 409)
