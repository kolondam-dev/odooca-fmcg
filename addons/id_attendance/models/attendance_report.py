from collections import defaultdict
from datetime import datetime, time, timedelta, timezone

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

from .mobile_command import WITA
from .report_intervals import intersect, minutes, subtract, union

DAY = timedelta(days=1)
CATEGORY_ORDER = ("sick", "permission", "leave")
PENDING = {"confirm", "validate1"}


def day_start(day):
    return datetime.combine(day, time.min, WITA)


def business_today():
    return utc(fields.Datetime.now()).astimezone(WITA).date()


def utc(value):
    return value.replace(tzinfo=timezone.utc)


def utc_naive(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class AttendanceReport(models.TransientModel):
    _name = "id.attendance.report"
    _description = "PWA Attendance Report"
    _transient_max_hours = 4

    date_from = fields.Date(required=True, default=lambda self: business_today().replace(day=1))
    date_to = fields.Date(required=True, default=lambda self: business_today())
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    employee_ids = fields.Many2many("hr.employee", domain="[('company_id', '=', company_id)]")
    grace_minutes = fields.Integer(string="Grace Period (Minutes)", default=0)

    generated = fields.Boolean(readonly=True)
    attendance_rate = fields.Float(string="Attendance Rate (%)", readonly=True)
    required_day_total = fields.Integer(string="Closed Required Days", readonly=True)
    present_day_total = fields.Integer(string="Present on Closed Required Days", readonly=True)
    planned_minute_total = fields.Float(string="Planned Minutes", readonly=True)
    scheduled_minute_total = fields.Float(string="Recorded Within Required Schedule (Minutes)", readonly=True)
    absent_day_total = fields.Integer(string="Absent Days", readonly=True)
    incomplete_day_total = fields.Integer(string="Incomplete Days", readonly=True)

    def action_generate(self):
        self.ensure_one()
        self.check_access("write")
        if not self.env.user.has_group("hr.group_hr_manager") or self.company_id not in self.env.companies:
            raise AccessError(_("You cannot report attendance for this company."))
        if not self.date_from or not self.date_to or not 0 <= (self.date_to - self.date_from).days < 92:
            raise UserError(_("Select a valid period of at most 92 days."))
        if not 0 <= self.grace_minutes <= 1440:
            raise UserError(_("The grace period must be between 0 and 1440 minutes."))

        selected = self.employee_ids
        if selected and any(employee.company_id != self.company_id for employee in selected):
            raise AccessError(_("All selected employees must belong to the report company."))
        report = self.with_company(self.company_id)
        domain = [("company_id", "=", self.company_id.id)]
        if selected:
            domain.append(("id", "in", selected.ids))
        day_count = (self.date_to - self.date_from).days + 1
        max_employees = 20000 // day_count
        employees = report.env["hr.employee"].with_context(active_test=False).search(
            domain, limit=max_employees + 1,
        )
        if len(employees) > max_employees:
            raise UserError(_("Shorten the period or select employees to keep the report below 20,000 rows."))

        lines = report.env["id.attendance.report.line"]
        lines.search([("report_id", "=", self.id)]).unlink()
        values = report._report_values(employees)
        lines.create(values)
        required = sum(row["required_days"] for row in values)
        present = sum(row["present_days"] for row in values)
        self.write({
            "generated": True,
            "attendance_rate": 100 * present / required if required else 0,
            "required_day_total": required,
            "present_day_total": present,
            "planned_minute_total": sum(row["planned_minutes"] for row in values),
            "scheduled_minute_total": sum(row["scheduled_minutes"] for row in values),
            "absent_day_total": sum(row["absent_days"] for row in values),
            "incomplete_day_total": sum(row["incomplete_days"] for row in values),
        })
        action = self.env["ir.actions.actions"]._for_xml_id("id_attendance.action_attendance_report")
        action["res_id"] = self.id
        return action

    def action_open_details(self):
        self.ensure_one()
        self.check_access("read")
        action = self.env["ir.actions.actions"]._for_xml_id("id_attendance.action_attendance_report_lines")
        action["domain"] = [("report_id", "=", self.id)]
        return action

    def _report_values(self, employees):
        start = day_start(self.date_from)
        stop = day_start(self.date_to + DAY)
        today = business_today()
        env = self.env
        # The caller has HR manager rights and has already restricted employees and company.
        # Only derived minutes and state are returned from private Time Off records.
        leave_by_employee = defaultdict(list)
        for leave in env["hr.leave"].sudo().search([
            ("employee_id", "in", employees.ids), ("company_id", "=", self.company_id.id),
            ("state", "in", ["validate", *sorted(PENDING)]),
            ("date_from", "<", utc_naive(stop)), ("date_to", ">", utc_naive(start)),
        ]):
            leave_by_employee[leave.employee_id.id].append((
                (utc(leave.date_from), utc(leave.date_to)),
                leave.state,
                leave.holiday_status_id.pwa_report_category,
            ))

        attendances = {
            (a.employee_id.id, a.pwa_business_date): a
            for a in env["hr.attendance"].sudo().search([
                ("employee_id", "in", employees.ids),
                ("pwa_business_date", ">=", self.date_from),
                ("pwa_business_date", "<=", self.date_to),
                ("in_mode", "=", "pwa"), ("pwa_check_in_evidence_id", "!=", False),
            ])
        }
        native_holidays = env["resource.calendar.leaves"].sudo().search([
            ("resource_id", "=", False), ("time_type", "=", "leave"),
            ("company_id", "in", [False, self.company_id.id]),
            ("date_from", "<", utc_naive(stop)), ("date_to", ">", utc_naive(start)),
        ])
        holidays = env["id.attendance.holiday"].search([
            ("company_id", "=", self.company_id.id),
            ("date_from", "<=", self.date_to), ("date_to", ">=", self.date_from),
        ])
        result = []
        schedules = {}
        day_count = (self.date_to - self.date_from).days + 1
        for employee in employees:
            versions = iter(employee.sudo().version_ids.filtered("active").sorted("date_version"))
            next_version = next(versions, None)
            version = env["hr.version"]
            for offset in range(day_count):
                day = self.date_from + offset * DAY
                while next_version and next_version.date_version <= day:
                    version, next_version = next_version, next(versions, None)
                attendance = attendances.get((employee.id, day))
                in_employment = bool(version) and (
                    (not version.contract_date_start or day >= version.contract_date_start)
                    and (not version.contract_date_end or day <= version.contract_date_end)
                    and (not employee.departure_date or day <= employee.departure_date)
                )
                if not attendance and not in_employment:
                    continue

                window = [(day_start(day), day_start(day + DAY))]
                planned, calendar_known, holiday_notes = [], False, []
                if in_employment:
                    calendar = version.resource_calendar_id
                    location = version.work_location_id
                    key = (calendar.id, location.id, day)
                    if key not in schedules:
                        schedules[key] = self._schedule(calendar, location, day, window, native_holidays, holidays)
                    planned, calendar_known, holiday_notes = schedules[key]
                result.append(self._day_values(
                    employee, version, day, today, attendance, planned, calendar_known,
                    holiday_notes, leave_by_employee[employee.id], window,
                ))
        return result

    def _schedule(self, calendar, location, day, window, native_holidays, holidays):
        start, stop = window[0]
        calendar_known = bool(calendar and not calendar.flexible_hours and not calendar.duration_based)
        scheduled = union(
            (low, high) for low, high, _line in calendar._attendance_intervals_batch(start, stop)[False]
        ) if calendar_known else []
        native = native_holidays.filtered(lambda h: (
            not h.calendar_id or h.calendar_id == calendar
        ) and utc(h.date_from) < stop and utc(h.date_to) > start)
        scoped = holidays.filtered(lambda h: h.date_from <= day <= h.date_to
            and (not h.calendar_id or h.calendar_id == calendar)
            and (not h.work_location_id or h.work_location_id == location))
        holiday_time = window if scoped else union((utc(h.date_from), utc(h.date_to)) for h in native)
        notes = [h.name for h in native] + [f"{h.name} ({h.source})" for h in scoped]
        return subtract(scheduled, holiday_time), calendar_known, notes

    def _day_values(self, employee, version, day, today, attendance, planned, calendar_known,
                    holiday_notes, leaves, window):
        closed = day < today
        coverage = employee.pwa_attendance_report_from
        departure = employee.departure_date
        covered = bool(coverage and day >= coverage and (employee.active or departure)
                       and (not departure or day <= departure))
        verified_out = bool(attendance and attendance.check_out and attendance.out_mode == "pwa"
                            and attendance.pwa_check_out_evidence_id)
        check_in = utc(attendance.check_in) if attendance else None
        check_out = utc(attendance.check_out) if verified_out else None
        actual = intersect([(check_in, check_out)], window) if check_out else []

        # Overlapping Time Off records count once, with a stable category precedence.
        required = planned
        leave_minutes = {}
        for category in CATEGORY_ORDER:
            approved = union(interval for interval, state, kind in leaves if state == "validate" and kind == category)
            leave_minutes[category] = minutes(intersect(required, approved))
            required = subtract(required, approved)
        pending = intersect(required, union(interval for interval, state, _kind in leaves if state in PENDING))
        in_schedule = intersect(actual, required)
        outside = subtract(actual, planned)
        overlap = minutes(intersect(actual, planned)) - minutes(in_schedule)
        late = early = 0
        if check_in and required:
            if check_in > required[0][0]:
                late = minutes(subtract(required, [(check_in, window[0][1])]))
            if check_out and check_out < required[-1][1]:
                early = minutes(subtract(required, [(window[0][0], check_out)]))
        late = late if late > self.grace_minutes else 0
        early = early if early > self.grace_minutes else 0

        if attendance:
            status = "incomplete" if not verified_out else "present" if required else "unscheduled"
        elif not calendar_known:
            status = "no_calendar"
        elif not planned:
            status = "holiday" if holiday_notes else "rest"
        elif not required:
            status = "time_off"
        elif not covered:
            status = "not_covered"
        elif pending:
            status = "pending"
        elif not closed:
            status = "open"
        else:
            status = "absent"

        # Unconfirmed pending days remain outside the closed-day rate denominator.
        required_day = int(bool(covered and closed and required and (attendance or not pending)))
        return {
            "report_id": self.id,
            "employee_id": employee.id,
            "company_id": self.company_id.id,
            "department_id": version.department_id.id if version else False,
            "work_location_id": version.work_location_id.id if version else False,
            "calendar_id": version.resource_calendar_id.id if version else False,
            "business_date": day,
            "status": status,
            "covered": covered,
            "holiday_notes": "\n".join(holiday_notes),
            "check_in": attendance.check_in if attendance else False,
            "check_out": attendance.check_out if verified_out else False,
            "attendance_id": attendance.id if attendance else False,
            "planned_minutes": minutes(planned),
            "required_minutes": minutes(required),
            "actual_minutes": minutes(actual),
            "scheduled_minutes": minutes(in_schedule),
            "outside_minutes": minutes(outside),
            "overlap_minutes": max(0, overlap),
            "late_minutes": late,
            "early_minutes": early,
            "leave_minutes": leave_minutes["leave"],
            "sick_minutes": leave_minutes["sick"],
            "permission_minutes": leave_minutes["permission"],
            "pending_minutes": minutes(pending),
            "planned_days": int(bool(planned)),
            "recorded_days": int(bool(attendance)),
            "required_days": required_day,
            "present_days": required_day * int(bool(attendance)),
            "absent_days": int(status == "absent"),
            "incomplete_days": int(status == "incomplete"),
            "late_days": int(bool(late)),
        }


class AttendanceReportLine(models.TransientModel):
    _name = "id.attendance.report.line"
    _description = "PWA Attendance by Employee and Day"
    _order = "business_date desc, employee_id"
    _transient_max_hours = 4

    report_id = fields.Many2one("id.attendance.report", required=True, ondelete="cascade", index=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, index=True)
    department_id = fields.Many2one("hr.department")
    work_location_id = fields.Many2one("hr.work.location")
    calendar_id = fields.Many2one("resource.calendar")
    business_date = fields.Date(required=True, index=True)
    status = fields.Selection([
        ("present", "Present"), ("unscheduled", "Present Outside Required Schedule"),
        ("incomplete", "Missing PWA Check-out"), ("holiday", "Holiday"), ("rest", "Rest Day"),
        ("time_off", "Approved Time Off"), ("not_covered", "Outside PWA Coverage"),
        ("pending", "Pending Time Off"), ("open", "Day Not Closed"),
        ("absent", "Absent"), ("no_calendar", "No Fixed Working Schedule"),
    ], required=True)
    covered = fields.Boolean(string="PWA Coverage")
    holiday_notes = fields.Text()
    check_in = fields.Datetime()
    check_out = fields.Datetime()
    attendance_id = fields.Many2one("hr.attendance", ondelete="cascade")
    planned_minutes = fields.Float()
    required_minutes = fields.Float()
    actual_minutes = fields.Float()
    scheduled_minutes = fields.Float(string="Recorded Within Required Schedule (Minutes)")
    outside_minutes = fields.Float()
    overlap_minutes = fields.Float(string="Attendance and Time Off Overlap (Minutes)")
    late_minutes = fields.Float()
    early_minutes = fields.Float()
    leave_minutes = fields.Float()
    sick_minutes = fields.Float()
    permission_minutes = fields.Float()
    pending_minutes = fields.Float()
    planned_days = fields.Integer()
    recorded_days = fields.Integer()
    required_days = fields.Integer(string="Closed Required Days")
    present_days = fields.Integer(string="Present on Closed Required Days")
    absent_days = fields.Integer()
    incomplete_days = fields.Integer()
    late_days = fields.Integer()
