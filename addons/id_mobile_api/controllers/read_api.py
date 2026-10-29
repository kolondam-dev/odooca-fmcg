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

    def _read(self, bootstrap):
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
