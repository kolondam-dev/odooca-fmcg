import io
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from PIL import Image

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from odoo.addons.id_attendance.models.mobile_command import WITA
from odoo.addons.id_mobile_api.models.mobile_evidence import EvidenceRejected
from odoo.addons.id_mobile_api.models.mobile_workday import MobileReadConflict


@tagged("post_install", "-at_install")
class TestPwaAttendance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        office = cls.env["id.mobile.office"].create({
            "name": "Attendance test office",
            "company_id": company.id,
            "latitude": 1.493,
            "longitude": 124.841,
            "coordinate_status": "verified",
            "coordinate_note": "Test fixture",
        })
        cls.actor = cls.env["res.users"].create({
            "name": "Attendance test user",
            "login": "pwa_attendance_fixture",
            "company_id": company.id,
            "company_ids": [Command.set(company.ids)],
            "group_ids": [Command.set([cls.env.ref("id_mobile_api.group_mobile_evidence").id])],
        })
        cls.employee = cls.env["hr.employee"].create({
            "name": "Attendance test employee",
            "company_id": company.id,
            "user_id": cls.actor.id,
            "pwa_attendance_office_id": office.id,
        })
        cls.evidence = cls.env["id.mobile.evidence"].with_user(cls.actor)
        cls.commands = cls.env["id.mobile.command"].with_user(cls.actor)
        stream = io.BytesIO()
        Image.new("RGB", (64, 64), "white").save(stream, "PNG")
        cls.photo = stream.getvalue()

    def _metadata(self, hour, event):
        now = datetime(2026, 11, 25, hour, tzinfo=timezone.utc)
        return now, {
            "client_uuid": str(uuid4()),
            "attendance_event": event,
            "business_date": now.astimezone(WITA).date().isoformat(),
            "photo_selected_at": now.isoformat(),
            "device_recorded_at": now.isoformat(),
            "fix_sampled_at": now.isoformat(),
            "latitude": 1.493,
            "longitude": 124.841,
            "accuracy": 2,
        }

    def _command(self, metadata, new_uuid=False):
        return {
            "type": "hris.attendance.capture",
            "client_uuid": str(uuid4()) if new_uuid else metadata["client_uuid"],
            "payload": {"evidence_uuid": metadata["client_uuid"]},
        }

    def _capture(self, now, metadata):
        with patch("odoo.addons.id_attendance.models.mobile_evidence.utc_now", return_value=now):
            return self.evidence._capture(metadata, self.photo)

    def _submit(self, now, command):
        with patch("odoo.addons.id_attendance.models.mobile_command.utc_now", return_value=now):
            return self.commands.process_command(command)

    def test_posts_and_replays_one_session_without_sales_assignment(self):
        start, check_in = self._metadata(0, "check_in")
        end, check_out = self._metadata(9, "check_out")
        self.assertTrue(self._capture(start, check_in)[1])
        self.assertFalse(self._capture(start, check_in)[1])
        command = self._command(check_in)
        receipt = self._submit(start, command)
        self.assertEqual(self._submit(end, command), receipt)
        self._capture(end, check_out)
        self.assertEqual(self._submit(end, self._command(check_out))["reference"], receipt["reference"])
        session = self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)])
        self.assertEqual(len(session), 1)
        self.assertEqual(session.check_in, start.replace(tzinfo=None))
        self.assertEqual(session.check_out, end.replace(tzinfo=None))
        self.assertEqual(session.in_mode, "pwa")
        self.assertEqual(session.out_mode, "pwa")
        self.assertEqual(session.pwa_check_out_evidence_id.client_uuid, check_out["client_uuid"])
        with self.assertRaises(MobileReadConflict):
            self._submit(end, self._command(check_out, new_uuid=True))

    def test_demo_outside_office_and_fabricated_receipts_are_rejected(self):
        now, check_in = self._metadata(0, "check_in")
        for metadata in ({**check_in, "mode": "demo"}, {**check_in, "latitude": 0}):
            with self.assertRaises(EvidenceRejected):
                self._capture(now, metadata)
        with self.assertRaises(AccessError):
            self._submit(now, self._command(check_in))
        with self.assertRaises(AccessError):
            self.commands.create({"command_type": "hris.attendance.capture"})
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)]))

    def test_check_out_without_check_in_and_foreign_evidence_are_rejected(self):
        now, check_out = self._metadata(9, "check_out")
        self._capture(now, check_out)
        with self.assertRaises(MobileReadConflict):
            self._submit(now, self._command(check_out))

        other = self.actor.copy({
            "login": "pwa_attendance_other",
            "group_ids": [Command.set(self.actor.group_ids.ids)],
        })
        self.env["hr.employee"].create({
            "name": "Other attendance employee",
            "company_id": self.employee.company_id.id,
            "user_id": other.id,
            "pwa_attendance_office_id": self.employee.pwa_attendance_office_id.id,
        })
        self.assertTrue(other.has_group("id_mobile_api.group_mobile_evidence"))
        with self.assertRaises(AccessError):
            self.commands.with_user(other).process_command(self._command(check_out))
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)]))

    def test_unposted_evidence_expires_after_window_or_wita_rollover(self):
        for hour, delay in ((0, timedelta(seconds=301)), (15, timedelta(minutes=1))):
            now, metadata = self._metadata(hour, "check_in")
            if hour == 15:
                now += timedelta(minutes=59)
                for key in ("photo_selected_at", "device_recorded_at", "fix_sampled_at"):
                    metadata[key] = now.isoformat()
            self._capture(now, metadata)
            command = self._command(metadata)
            with self.assertRaises(EvidenceRejected) as error:
                self._submit(now + delay, command)
            self.assertEqual(error.exception.code, "attendance_evidence_expired")
            self.assertFalse(self.env["id.mobile.command"].search([
                ("client_uuid", "=", command["client_uuid"]),
            ]))
        self.assertFalse(self.env["hr.attendance"].search([("employee_id", "=", self.employee.id)]))
