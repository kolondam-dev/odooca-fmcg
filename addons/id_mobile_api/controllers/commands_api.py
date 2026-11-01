import json
import logging
from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from .read_api import MobileReadApi
from ..models.mobile_workday import MobileReadConflict

_logger = logging.getLogger(__name__)


class MobileCommandsApi(MobileReadApi):

    @http.route("/api/v1/sync/commands", type="http", auth="public", methods=["POST"], csrf=False)
    def submit_command(self, **kwargs):
        denied = self._gate()
        if denied is not None:
            return denied

        # Validate X-CSRF-Token header against server session token
        csrf_token = request.httprequest.headers.get("X-CSRF-Token")
        if not csrf_token:
            return self._response({"error": "invalid_or_missing_csrf_token"}, 400)

        if hasattr(request, "validate_csrf"):
            try:
                request.validate_csrf(csrf_token)
            except Exception:
                return self._response({"error": "invalid_or_missing_csrf_token"}, 400)

        try:
            body = request.httprequest.get_data()
            if not body:
                return self._response({"error": "empty_body"}, 400)
            command_data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self._response({"error": "invalid_json"}, 400)

        if not isinstance(command_data, dict):
            return self._response({"error": "command_must_be_object"}, 400)

        client_uuid = command_data.get("client_uuid")
        if not client_uuid:
            return self._response({"error": "missing_client_uuid"}, 422)

        try:
            CommandModel = request.env["id.mobile.command"]
            receipt = CommandModel.process_command(command_data)
            return self._response(receipt, 200)
        except MobileReadConflict as e:
            return self._response({"error": str(e) or "conflict"}, 409)
        except AccessError as e:
            return self._response({"error": str(e) or "forbidden"}, 403)
        except UserError as e:
            return self._response({"error": str(e)}, 422)
        except Exception as e:
            _logger.exception("Error processing mobile command %s: %s", client_uuid, e)
            return self._response({"error": "server_error"}, 500)
