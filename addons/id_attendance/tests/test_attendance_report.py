from datetime import date, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAttendanceReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.day = date(2026, 11, 25)
        cls.closed_clock = datetime(2026, 11, 28, 4)
        cls.company = cls.env.company
        cls.calendar = cls._calendar("WITA Split Day", 17)
        cls.location = cls.env["hr.work.location"].create({
            "name": "Manado Pilot",
            "address_id": cls.company.partner_id.id,
            "company_id": cls.company.id,
        })
        cls.employee = cls.env["hr.employee"].create({
            "name": "Attendance Report Fixture",
            "tz": "Asia/Makassar",
            "company_id": cls.company.id,
            "resource_calendar_id": cls.calendar.id,
            "work_location_id": cls.location.id,
            "pwa_attendance_report_from": cls.day,
        })
        cls.employee.version_id.write({
            "date_version": cls.day - timedelta(days=2),
            "contract_date_start": cls.day - timedelta(days=2),
        })

    @classmethod
    def _calendar(cls, name, end):
        return cls.env["resource.calendar"].create({
            "name": name,
            "company_id": cls.company.id,
            "tz": "Asia/Makassar",
            "attendance_ids": [Command.create({
                "name": period, "dayofweek": str(day), "day_period": period,
                "hour_from": low, "hour_to": high,
            }) for day in range(5) for period, low, high in (
                ("morning", 8, 12), ("lunch", 12, 13), ("afternoon", 13, end),
            )],
        })

    def _attendance(self, day=None, completed=True):
        day = day or self.day

        # Reporting fixtures need valid model links, not actual photo contents.
        photo = "dGVzdA=="
        user = self.env.user
        evidence_model = self.env["id.mobile.evidence"].sudo()

        def evidence():
            return evidence_model.create({
                "client_uuid": str(uuid4()),
                "user_id": user.id,
                "company_id": self.company.id,
                "fingerprint": "report-fixture",
                "receipt_json": "{}",
                "original": photo,
                "watermarked": photo,
            })

        in_evidence = evidence()
        out_evidence = evidence() if completed else None
        return self.env["hr.attendance"].sudo().create({
            "employee_id": self.employee.id,
            "pwa_business_date": day,
            "check_in": datetime.combine(day, datetime.min.time()) + timedelta(minutes=17),
            "check_out": datetime.combine(day, datetime.min.time()) + timedelta(hours=8, minutes=40),
            "in_mode": "pwa",
            "out_mode": "pwa" if completed else "auto_check_out",
            "pwa_check_in_evidence_id": in_evidence.id,
            "pwa_check_out_evidence_id": out_evidence.id if completed else False,
        })

    def _generate(self, start=None, end=None, grace=0):
        report = self.env["id.attendance.report"].create({
            "company_id": self.company.id,
            "date_from": start or self.day,
            "date_to": end or self.day,
            "grace_minutes": grace,
            "employee_ids": [Command.set(self.employee.ids)],
        })
        with patch.object(fields.Datetime, "now", return_value=self.closed_clock):
            action = report.action_generate()
        self.assertEqual(action["res_id"], report.id)
        domain = report.action_open_details()["domain"]
        return report, {line.business_date: line for line in self.env["id.attendance.report.line"].search(domain)}

    def _holiday(self, kind, **values):
        return self.env["id.attendance.holiday"].create({
            "name": kind,
            "date_from": self.day,
            "date_to": self.day,
            "kind": kind,
            "source": "Fixture reference",
            "company_id": self.company.id,
            **values,
        })

    def test_split_calendar_minutes_coverage_and_totals(self):
        attendance = self._attendance()
        before = self.day - timedelta(days=1)
        missing = self.day + timedelta(days=1)
        report, rows = self._generate(before, missing)
        row = rows[self.day]
        self.assertEqual(row.attendance_id, attendance)
        self.assertEqual((row.planned_minutes, row.scheduled_minutes), (480, 443))
        self.assertEqual((row.late_minutes, row.early_minutes, row.outside_minutes), (17, 20, 60))
        self.assertEqual(rows[before].status, "not_covered")
        self.assertEqual(rows[missing].status, "absent")
        self.assertEqual((report.required_day_total, report.present_day_total, report.attendance_rate), (2, 1, 50))
        self.assertEqual(report.planned_minute_total, sum(row.planned_minutes for row in rows.values()))
        self.assertEqual(report.scheduled_minute_total, sum(row.scheduled_minutes for row in rows.values()))
        grouped = self.env["id.attendance.report.line"]._read_group(
            report.action_open_details()["domain"],
            ["employee_id"], ["planned_minutes:sum", "scheduled_minutes:sum", "absent_days:sum"],
        )
        self.assertEqual(grouped, [(self.employee, 1440, 443, 1)])
        _report, tolerated = self._generate(grace=17)
        self.assertEqual((tolerated[self.day].late_minutes, tolerated[self.day].early_minutes), (0, 20))

    def test_effective_schedule_and_overlapping_scoped_holidays(self):
        next_day = self.day + timedelta(days=1)
        other_location = self.location.copy({"name": "Other Branch"})
        self.employee.create_version({
            "date_version": next_day,
            "resource_calendar_id": self._calendar("Short Day", 16).id,
            "work_location_id": other_location.id,
        })
        self._holiday("national")
        self._holiday("regional", work_location_id=self.location.id)
        self._holiday("regional", date_from=next_day, date_to=next_day, work_location_id=self.location.id)
        self._attendance()
        _report, rows = self._generate(self.day, next_day)
        self.assertEqual((rows[self.day].status, rows[self.day].planned_minutes), ("unscheduled", 0))
        self.assertIn("national", rows[self.day].holiday_notes)
        self.assertIn("regional", rows[self.day].holiday_notes)
        self.assertEqual(rows[next_day].work_location_id, other_location)
        self.assertEqual(rows[next_day].planned_minutes, 420)

    def test_auto_checkout_does_not_supply_pwa_work_minutes(self):
        self._attendance(completed=False)
        _report, rows = self._generate()
        row = rows[self.day]
        self.assertEqual(row.status, "incomplete")
        self.assertFalse(row.check_out)
        self.assertEqual((row.actual_minutes, row.scheduled_minutes, row.incomplete_days), (0, 0, 1))

    def test_report_requires_hr_manager_and_own_company(self):
        ordinary = self.env["res.users"].create({
            "name": "Ordinary Report Test User", "login": "pwa_report_ordinary",
            "company_id": self.company.id, "company_ids": [Command.set(self.company.ids)],
            "group_ids": [Command.set([self.env.ref("base.group_user").id])],
        })
        with self.assertRaises(AccessError):
            self.env["id.attendance.report"].with_user(ordinary).create({})
        other = self.env["res.company"].create({"name": "Other Attendance Company"})
        report = self.env["id.attendance.report"].create({
            "company_id": self.company.id, "date_from": self.day, "date_to": self.day,
        })
        manager = self.env["res.users"].create({
            "name": "Attendance Manager", "login": "pwa_report_manager",
            "company_id": other.id, "company_ids": [Command.set(other.ids)],
            "group_ids": [Command.set([self.env.ref("hr.group_hr_manager").id])],
        })
        with self.assertRaises(AccessError):
            report.with_user(manager).with_context(allowed_company_ids=other.ids).action_generate()

    def test_native_partial_holiday_and_time_off_adjust_required_minutes(self):
        self.env["resource.calendar.leaves"].create({
            "name": "Native Partial Holiday",
            "company_id": self.company.id,
            "calendar_id": self.calendar.id,
            "date_from": datetime(2026, 11, 25, 8),
            "date_to": datetime(2026, 11, 25, 9),
        })
        sick_type = self.env["hr.leave.type"].create({
            "name": "Pilot Sick Leave", "company_id": self.company.id,
            "requires_allocation": False, "request_unit": "hour",
            "leave_validation_type": "hr", "pwa_report_category": "sick",
        })
        pending_type = self.env["hr.leave.type"].create({
            "name": "Pilot Permission", "company_id": self.company.id,
            "requires_allocation": False, "request_unit": "hour",
            "leave_validation_type": "hr", "pwa_report_category": "permission",
        })
        values = {
            "employee_id": self.employee.id,
            "request_date_from": self.day,
            "request_date_to": self.day,
            "request_unit_hours": True,
        }
        approved = self.env["hr.leave"].create({
            **values, "holiday_status_id": sick_type.id, "request_hour_from": 13, "request_hour_to": 14,
        })
        pending = self.env["hr.leave"].create({
            **values, "holiday_status_id": pending_type.id, "request_hour_from": 14, "request_hour_to": 15,
        })
        self.assertEqual((approved.date_from, approved.date_to), (
            datetime(2026, 11, 25, 5), datetime(2026, 11, 25, 6),
        ))
        self.assertGreater(approved.number_of_days, 0, (
            approved.resource_calendar_id, self.employee.resource_id.tz, self.employee.tz,
        ))
        approved.action_approve()
        self.assertEqual((approved.state, pending.state), ("validate", "confirm"))
        report, rows = self._generate()
        row = rows[self.day]
        self.assertEqual((row.planned_minutes, row.required_minutes), (420, 360))
        self.assertEqual((row.sick_minutes, row.permission_minutes, row.pending_minutes), (60, 0, 60))
        self.assertEqual((row.status, report.required_day_total, report.absent_day_total), ("pending", 0, 0))

    def test_wita_closure_excludes_open_day_from_absence(self):
        self.closed_clock = datetime(2026, 11, 25, 15, 59)
        report, rows = self._generate()
        self.assertEqual((rows[self.day].status, report.required_day_total), ("open", 0))
        self.closed_clock = datetime(2026, 11, 25, 16)
        report, rows = self._generate()
        self.assertEqual((rows[self.day].status, report.required_day_total), ("absent", 1))

    def test_manager_can_generate_and_colleague_cannot_read_report_lines(self):
        manager_group = self.env.ref("hr.group_hr_manager")
        managers = self.env["res.users"].create([{
            "name": name, "login": login,
            "company_id": self.company.id, "company_ids": [Command.set(self.company.ids)],
            "group_ids": [Command.set(manager_group.ids)],
        } for name, login in [
            ("Report Owner", "pwa_report_owner"),
            ("Other HR Manager", "pwa_report_colleague"),
        ]])
        owner, colleague = managers
        report = self.env["id.attendance.report"].with_user(owner).create({
            "company_id": self.company.id, "date_from": self.day, "date_to": self.day,
            "employee_ids": [Command.set(self.employee.ids)],
        })
        with patch.object(fields.Datetime, "now", return_value=self.closed_clock):
            report.action_generate()
        domain = report.action_open_details()["domain"]
        line = self.env["id.attendance.report.line"].with_user(owner).search(domain)
        self.assertEqual(line.status, "absent")
        self.assertFalse(line.with_user(colleague).search(domain))
