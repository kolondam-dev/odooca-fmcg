from uuid import UUID

from psycopg2.errors import UniqueViolation

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from ..models.attendance_report import business_today
from ..models.correction import CODE, MODEL, REQUEST


def response(data, status=200):
    return request.make_json_response(data, status=status, headers=[("Cache-Control", "no-store")])


def approval_data(approval):
    return {
        "id": approval.id or 0,
        "reference": approval.reference_document,
        "reason": approval.reason,
        "state": approval.state or "draft",
        "tier": approval.current_tier_sequence or 0,
        "canDecide": bool(approval and approval.is_current_user_approver),
        "mine": not approval or approval.requested_by == request.env.user,
        "steps": [{"name": line.tier_name, "state": line.state,
                   "actor": line.actual_approver_id.name or "", "notes": line.notes or ""}
                  for line in approval.line_ids],
    }


class AttendanceCorrectionController(http.Controller):
    @http.route("/api/v1/attendance/corrections/session", type="http", auth="user", methods=["GET"])
    def correction_session(self):
        user = request.env.user
        if not user._is_internal():
            return response({"error": "Forbidden"}, 403)
        return response({
            "id": str(user.id), "companyId": str(request.env.company.id),
            "name": user.name, "businessDate": str(business_today()), "roles": [], "title": "",
            "capabilities": ["attendance.approval_only"], "csrfToken": request.csrf_token(),
        })

    @http.route("/api/v1/attendance/corrections", type="http", auth="user", methods=["GET"])
    def list_corrections(self, queue="all", before=None):
        if not request.env.user._is_internal():
            return response({"error": "Forbidden"}, 403)
        try:
            cursor = int(before) if before is not None else None
            if (queue not in ("all", "actionable", "history")
                    or (cursor is not None and (not 0 < cursor <= 2_147_483_647 or queue == "all"))):
                raise ValueError
        except (TypeError, ValueError):
            return response({"error": "Invalid approval queue or cursor."}, 422)
        approvals = request.env[REQUEST]
        if queue == "all":
            # Compatibility for clients predating pagination.
            active, _ = approvals._attendance_correction_page("actionable", None)
            history, _ = approvals._attendance_correction_page("history", None)
            page, next_before = active + history, None
        else:
            page, next_before = approvals._attendance_correction_page(queue, cursor)
        return response({"items": [approval_data(approval) for approval in page],
                         "nextBefore": next_before, "csrfToken": request.csrf_token()})

    @http.route("/api/v1/attendance/corrections", type="http", auth="user", methods=["POST"], csrf=True)
    def submit_correction(self, business_date="", start_hour="", end_hour="", reason="", client_key="", **kwargs):
        if not request.env.user._is_internal():
            return response({"error": "Forbidden"}, 403)
        try:
            key = str(UUID(client_key))
            values = {
                "business_date": business_date, "start_hour": float(start_hour),
                "end_hour": float(end_hour), "reason": reason.strip(), "client_key": key,
            }
            with request.env.cr.savepoint():
                model = request.env[MODEL]
                correction = model.search([("requester_id", "=", request.env.uid),
                                           ("client_key", "=", key)], limit=1)
                if correction and (str(correction.business_date), correction.start_hour,
                                   correction.end_hour, correction.reason) != (
                                       business_date, values["start_hour"], values["end_hour"], values["reason"]
                                   ):
                    return response({"error": "Submission ID already used for different values."}, 409)
                correction = correction or model.create(values)
                correction.action_submit()
            return response(approval_data(correction.approval_id))
        except UniqueViolation as error:
            if error.diag.constraint_name != "id_attendance_correction_client_unique":
                raise
            return response({"error": "Submission in progress. Retry using the same form."}, 409)
        except AccessError:
            return response({"error": "Forbidden"}, 403)
        except (UserError, ValueError) as error:
            return response({"error": str(error)}, 422)

    @http.route("/api/v1/attendance/corrections/decision", type="http", auth="user", methods=["POST"], csrf=True)
    def decide_correction(self, approval_id="", tier="", decision="", notes="", **kwargs):
        if not request.env.user._is_internal():
            return response({"error": "Forbidden"}, 403)
        if decision not in ("approve", "reject") or len(notes) > 1000:
            return response({"error": "Invalid decision or note."}, 422)
        try:
            approval = request.env[REQUEST].search([
                ("id", "=", int(approval_id)), ("category_code", "=", CODE),
                ("company_id", "=", request.env.company.id),
            ], limit=1)
            if not approval:
                return response({"error": "Not found"}, 404)
            with request.env.cr.savepoint():
                action = approval.action_approve if decision == "approve" else approval.action_reject
                action(notes=notes.strip(), expected_tier=int(tier))
            return response(approval_data(approval))
        except AccessError:
            return response({"error": "Forbidden"}, 403)
        except (UserError, ValueError) as error:
            return response({"error": str(error)}, 422)
