import base64
import hashlib
import io
import json
from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch

from PIL import Image
from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger

from ..models.mobile_evidence import EvidenceRejected, MAX_PHOTO, utc_now
from ..models.mobile_workday import MobileReadConflict
from .test_read_api import MobileFixture


class EvidenceFixture(MobileFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mobile.group_ids = [Command.link(cls.env.ref("id_mobile_api.group_mobile_evidence").id)]
        stream = io.BytesIO()
        Image.new("RGB", (80, 100), "red").save(stream, "PNG")
        cls.source = stream.getvalue()

    def api(self, user=None):
        actor = user or self.mobile
        return self.env["id.mobile.evidence"].with_user(actor).with_context(allowed_company_ids=actor.company_ids.ids)

    def metadata(self):
        now = utc_now().isoformat()
        snapshot = self.env["id.mobile.workday"].with_user(self.mobile).with_context(
            allowed_company_ids=self.mobile.company_ids.ids)._snapshot_payload()
        return {"client_uuid": str(uuid4()), "outlet_id": str(self.outlet.id),
                "business_date": snapshot["scope"]["business_date"], "snapshot_version": snapshot["version"],
                "photo_selected_at": now, "device_recorded_at": now, "fix_sampled_at": now,
                "latitude": self.outlet.partner_latitude, "longitude": self.outlet.partner_longitude, "accuracy": 1}


@tagged("post_install", "-at_install")
class TestEvidenceCapture(EvidenceFixture, TransactionCase):
    def test_original_derivative_receipt_and_idempotency_are_immutable(self):
        metadata = self.metadata()
        receipt, created = self.api()._capture(metadata, self.source)
        self.assertTrue(created)
        row = self.api()._owned(metadata["client_uuid"])
        self.assertEqual(base64.b64decode(row.original), self.source)
        derivative = base64.b64decode(row.watermarked)
        self.assertNotEqual(derivative, self.source)
        self.assertEqual(receipt["original_sha256"], hashlib.sha256(self.source).hexdigest())
        self.assertEqual(receipt["watermarked_sha256"], hashlib.sha256(derivative).hexdigest())
        with Image.open(io.BytesIO(derivative)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertGreater(image.height, 100)
        self.assertEqual(receipt["radius_m"], self.assignment.outlet_radius)
        self.assertEqual(receipt["master_latitude"], self.outlet.partner_latitude)
        self.assertAlmostEqual(receipt["distance_m"], 0)
        attachment = self.env["ir.attachment"].sudo().search([
            ("res_model", "=", "id.mobile.evidence"), ("res_id", "=", row.id), ("res_field", "=", "original"),
        ])
        self.assertEqual(len(attachment), 1)
        self.assertFalse(attachment.public)
        self.assertFalse(attachment.access_token)
        with self.assertRaises(AccessError):
            attachment.with_user(self.mobile).write({"datas": base64.b64encode(b"tampered")})
        self.assertEqual(base64.b64decode(row.original), self.source)

        again, created = self.api()._capture(metadata, self.source)
        self.assertFalse(created)
        self.assertEqual(receipt, again)
        with self.assertRaises(MobileReadConflict):
            self.api()._capture({**metadata, "accuracy": 2}, self.source)
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env["id.mobile.evidence"].sudo().create({
                "user_id": self.mobile.id, "company_id": self.company.id, "outlet_id": self.outlet.id,
                "client_uuid": metadata["client_uuid"], "fingerprint": row.fingerprint,
                "receipt_json": row.receipt_json, "original": row.original, "watermarked": row.watermarked,
            })
        self.assertEqual(self.api().search_count([]), 1)
        with self.assertRaises(AccessError):
            row.write({"receipt_json": "{}"})
        with self.assertRaises(AccessError):
            self.api().create({"client_uuid": str(uuid4())})
        with self.assertRaises(AccessError):
            row.unlink()

    def test_roles_owner_company_and_business_writes_stay_restricted(self):
        for user in (self.other, self.internal, self.portal):
            with self.assertRaises(AccessError):
                self.api(user)._capture(self.metadata(), self.source)
        receipt, _ = self.api()._capture(self.metadata(), self.source)
        self.other.group_ids = [Command.link(self.env.ref("id_mobile_api.group_mobile_evidence").id)]
        self.assertFalse(self.api(self.other)._owned(receipt["client_uuid"]))
        row = self.api()._owned(receipt["client_uuid"])
        with self.assertRaises(AccessError):
            row.with_user(self.other).read(["original"])
        self.mobile.company_ids = [Command.link(self.foreign.id)]
        self.mobile.company_id = self.foreign
        self.assertFalse(self.api()._owned(receipt["client_uuid"]))
        with self.assertRaises(AccessError):
            self.env["sale.order"].with_user(self.mobile).create({"partner_id": self.outlet.id})

    def test_server_master_scope_and_uncertainty_not_client_radius(self):
        metadata = self.metadata()
        for changes, code in [({"latitude": 2}, "geofence_outside"), ({"accuracy": 100}, "geofence_uncertain"),
                              ({"radius": 999}, "invalid_metadata")]:
            with self.assertRaises(EvidenceRejected) as caught:
                self.api()._capture({**metadata, **changes}, self.source)
            self.assertEqual(caught.exception.code, code)
        with self.assertRaises(AccessError):
            self.api()._capture({**metadata, "outlet_id": str(self.internal.partner_id.id)}, self.source)
        self.outlet.partner_latitude += .001
        with self.assertRaises(MobileReadConflict):
            self.api()._capture(metadata, self.source)
        self.assertFalse(self.api().search([]))

    def test_stale_future_invalid_and_oversized_inputs_leave_no_rows(self):
        metadata = self.metadata()
        for key, value in [("accuracy", float("nan")), ("latitude", True), ("client_uuid", "bad"),
                           ("fix_sampled_at", (utc_now() - timedelta(seconds=70)).isoformat()),
                           ("fix_sampled_at", (utc_now() + timedelta(seconds=30)).isoformat())]:
            with self.assertRaises(EvidenceRejected):
                self.api()._capture({**metadata, key: value}, self.source)
        for source in (b"<svg></svg>", b"broken", b"x" * (MAX_PHOTO + 1)):
            with self.assertRaises(EvidenceRejected):
                self.api()._capture(metadata, source)
        self.assertFalse(self.api().search([]))

    def test_gps_time_boundaries_follow_server_clock(self):
        now = utc_now()
        for seconds, accepted in [(60, True), (60.001, False), (-1, True), (-1.001, False)]:
            metadata = self.metadata()
            metadata["fix_sampled_at"] = (now - timedelta(seconds=seconds)).isoformat()
            with patch("odoo.addons.id_mobile_api.models.mobile_evidence.utc_now", return_value=now):
                if accepted:
                    receipt, created = self.api()._capture(metadata, self.source)
                    self.assertTrue(created)
                    self.assertEqual(receipt["user_id"], str(self.mobile.id))
                    self.assertEqual(receipt["company_id"], str(self.company.id))
                else:
                    with self.assertRaises(EvidenceRejected):
                        self.api()._capture(metadata, self.source)

    def test_midnight_rollover_rolls_back_evidence_and_attachments(self):
        metadata = self.metadata()
        before = self.env["ir.attachment"].search_count([])
        with patch.object(type(self.assignment), "_assert_day",
                          side_effect=[None, None, MobileReadConflict("rollover")]):
            with self.assertRaises(MobileReadConflict):
                self.api()._capture(metadata, self.source)
        self.assertFalse(self.api().search([]))
        self.assertEqual(before, self.env["ir.attachment"].search_count([]))


@tagged("post_install", "-at_install")
class TestEvidenceHttp(EvidenceFixture, HttpCase):
    def test_csrf_upload_replay_private_photos_and_idor(self):
        self.authenticate(self.mobile.login, "mobile-api-test")
        bootstrap = self.url_open("/api/v1/me/bootstrap").json()
        self.assertIn("evidence.capture", bootstrap["capabilities"])
        metadata = self.metadata()
        # HttpCase's opener is a requests.Session; use multipart requests, not JSON-RPC.
        url = self.base_url() + "/api/v1/evidence"
        response = self.opener.post(url, data={"metadata": json.dumps(metadata)},
                                    files={"photo": ("photo.png", self.source, "image/png")},
                                    timeout=20)
        self.assertEqual(response.status_code, 400)
        fields = {"metadata": json.dumps(metadata), "csrf_token": bootstrap["csrfToken"]}
        response = self.opener.post(url, data=fields, files={"photo": ("photo.png", self.source, "image/png")},
                                    timeout=20)
        self.assertEqual(response.status_code, 201, response.text)
        receipt = response.json()
        self.assertIn("no-store", response.headers["Cache-Control"])
        original = self.url_open(receipt["original_url"])
        self.assertEqual(original.content, self.source)
        self.assertIn("no-store", original.headers["Cache-Control"])
        repeat = self.opener.post(url, data=fields, files={"photo": ("photo.png", self.source, "image/png")},
                                    timeout=20)
        self.assertEqual(repeat.status_code, 200, repeat.text)
        self.assertEqual(repeat.json(), receipt)
        cross = self.opener.post(url, data=fields, files={"photo": ("photo.png", self.source, "image/png")},
                                 headers={"Origin": "https://attacker.invalid"}, timeout=20)
        self.assertEqual(cross.status_code, 400)
        self.authenticate(self.other.login, "mobile-api-other")
        self.assertEqual(self.url_open(receipt["original_url"]).status_code, 403)
        self.other.group_ids = [Command.link(self.env.ref("id_mobile_api.group_mobile_evidence").id)]
        self.assertEqual(self.url_open(receipt["original_url"]).status_code, 404)
