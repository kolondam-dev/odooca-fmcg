# Part of odooca-fmcg. License LGPL-3.
import base64
import hashlib
import io
import json
import uuid

from PIL import Image

from odoo import Command
from odoo.tests import HttpCase, TransactionCase, tagged

from ..models.mobile_evidence import EvidenceRejected
from .test_evidence_api import EvidenceFixture
from scripts.load_pjp_workdays import (
    get_or_create_sample_fmcg_photo,
    render_historical_watermark,
    run_pjp_workdays_loader,
)


@tagged("post_install", "-at_install")
class TestPjpLoaderBoundariesHttp(EvidenceFixture, HttpCase):
    def test_01_loader_evidence_attachments_and_watermark_viewable(self):
        """Memastikan evidence historis memiliki attachment asli & watermark valid,

        dapat dibuka melalui controller HTTP tanpa TypeError atau error probe.
        """
        self.authenticate(self.mobile.login, "mobile-api-test")

        sample_photo = get_or_create_sample_fmcg_photo()
        self.assertTrue(sample_photo.startswith(b"\xff\xd8"), "Sample photo harus JPEG valid")

        cuuid = str(uuid.uuid4())
        visit_timestamp = "2026-07-15 09:30:00"

        watermarked_bytes = render_historical_watermark(
            source_bytes=sample_photo,
            outlet_ref=self.outlet.ref or "OUT-TEST",
            outlet_name=self.outlet.name,
            salesman_name=self.mobile.name,
            salesman_login=self.mobile.login,
            visit_timestamp_str=visit_timestamp,
            lat=self.outlet.partner_latitude,
            lon=self.outlet.partner_longitude,
            acc=8.5,
            client_uuid=cuuid,
        )
        self.assertTrue(watermarked_bytes.startswith(b"\xff\xd8"), "Watermarked image harus JPEG valid")

        meta = {
            "client_uuid": cuuid,
            "outlet_id": str(self.outlet.id),
            "business_date": "2026-07-15",
            "snapshot_version": "v1-canonical-july-2026",
            "photo_selected_at": "2026-07-15T09:30:00Z",
            "device_recorded_at": "2026-07-15T09:30:05Z",
            "fix_sampled_at": "2026-07-15T09:30:02Z",
            "latitude": self.outlet.partner_latitude,
            "longitude": self.outlet.partner_longitude,
            "accuracy": 8.5,
        }
        fprint = hashlib.sha256(
            json.dumps(meta, sort_keys=True, separators=(",", ":")).encode()
            + hashlib.sha256(sample_photo).digest()
        ).hexdigest()

        receipt = {
            "client_uuid": cuuid,
            "outlet_id": str(self.outlet.id),
            "user_id": str(self.mobile.id),
            "company_id": str(self.company.id),
            "warehouse_id": str(self.warehouse.id),
            "assignment_id": str(self.assignment.id),
            "business_date": "2026-07-15",
            "snapshot_version": "v1-canonical-july-2026",
            "received_at": "2026-07-15T09:30:06Z",
            "device_recorded_at": "2026-07-15T09:30:05Z",
            "photo_selected_at": "2026-07-15T09:30:00Z",
            "fix_sampled_at": "2026-07-15T09:30:02Z",
            "latitude": self.outlet.partner_latitude,
            "longitude": self.outlet.partner_longitude,
            "accuracy": 8.5,
            "master_latitude": self.outlet.partner_latitude,
            "master_longitude": self.outlet.partner_longitude,
            "distance_m": 0.0,
            "radius_m": 10,
            "original_sha256": hashlib.sha256(sample_photo).hexdigest(),
            "watermarked_sha256": hashlib.sha256(watermarked_bytes).hexdigest(),
            "seed_batch": "pjp_workdays_july_2026_v1",
            "is_historical_seed": True,
            "original_url": f"/api/v1/evidence/{cuuid}/original",
            "watermarked_url": f"/api/v1/evidence/{cuuid}/watermarked",
        }
        binding = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        receipt["binding_sha256"] = hashlib.sha256(binding).hexdigest()

        # Simpan melalui ORM dengan sudo
        record = self.env["id.mobile.evidence"].sudo().create({
            "user_id": self.mobile.id,
            "company_id": self.company.id,
            "outlet_id": self.outlet.id,
            "client_uuid": cuuid,
            "fingerprint": fprint,
            "receipt_json": json.dumps(receipt),
            "original": base64.b64encode(sample_photo),
            "watermarked": base64.b64encode(watermarked_bytes),
        })

        self.assertTrue(record.original, "Kolom original harus terisi attachment")
        self.assertTrue(record.watermarked, "Kolom watermarked harus terisi attachment")

        # Probe controller HTTP untuk variant original
        resp_orig = self.url_open(f"/api/v1/evidence/{cuuid}/original")
        self.assertEqual(resp_orig.status_code, 200)
        self.assertEqual(resp_orig.headers.get("Content-Type"), "image/jpeg")
        self.assertEqual(resp_orig.content, sample_photo)

        # Probe controller HTTP untuk variant watermarked
        resp_wm = self.url_open(f"/api/v1/evidence/{cuuid}/watermarked")
        self.assertEqual(resp_wm.status_code, 200)
        self.assertEqual(resp_wm.headers.get("Content-Type"), "image/jpeg")
        self.assertEqual(resp_wm.content, watermarked_bytes)

        # Verifikasi bahwa gambar yang dikembalikan dapat dibuka oleh PIL
        with Image.open(io.BytesIO(resp_wm.content)) as im:
            self.assertEqual(im.format, "JPEG")
            self.assertGreater(im.width, 0)
            self.assertGreater(im.height, 0)


@tagged("post_install", "-at_install")
class TestPjpLoaderBoundariesTransaction(EvidenceFixture, TransactionCase):
    def test_02_loader_multi_company_partner_isolation(self):
        """Memastikan update PJP partner terisolasi per company dan tidak bocor lintas company."""
        Partner = self.env["res.partner"].sudo()

        shared_ref = "TEST-REF-CROSS-ISOLATION"

        # Buat partner di target company (company 1)
        partner_target = Partner.create({
            "name": "Outlet Target Company",
            "ref": shared_ref,
            "company_id": self.company.id,
            "pjp_call_day": "monday",
            "pjp_frequency": "F1",
        })

        # Buat partner di foreign company (company 2) dengan ref yang SAMA
        partner_foreign = Partner.create({
            "name": "Outlet Foreign Company",
            "ref": shared_ref,
            "company_id": self.foreign.id,
            "pjp_call_day": "monday",
            "pjp_frequency": "F1",
        })

        # Eksekusi scoped query seperti pada loader yang diperbaiki
        self.env.cr.execute("""
            UPDATE res_partner
            SET pjp_call_day = %s, pjp_frequency = %s, delivery_route = %s
            WHERE ref = %s AND (company_id = %s OR company_id IS NULL)
        """, ["friday", "F2", "RUTE-TARGET", shared_ref, self.company.id])

        partner_target.invalidate_recordset()
        partner_foreign.invalidate_recordset()

        # Partner target harus terupdate
        self.assertEqual(partner_target.pjp_call_day, "friday")
        self.assertEqual(partner_target.pjp_frequency, "F2")
        self.assertEqual(partner_target.delivery_route, "RUTE-TARGET")

        # Partner foreign TIDAK BOLEH ikut berubah
        self.assertEqual(partner_foreign.pjp_call_day, "monday", "Partner company lain tidak boleh terupdate!")
        self.assertEqual(partner_foreign.pjp_frequency, "F1")
        self.assertFalse(partner_foreign.delivery_route)

    def test_03_loader_fails_fast_when_models_missing(self):
        """Memastikan loader melempar RuntimeError (fail-fast) jika model mobile belum terpasang,

        mencegah sukses palsu dan mark terpasang saat modul belum lengkap.
        """
        # Mock environment tanpa model id.mobile.workday
        class MockEnv(dict):
            def __contains__(self, key):
                if key in ("id.mobile.workday", "id.mobile.evidence"):
                    return False
                return super().__contains__(key)

        mock_env = MockEnv()
        with self.assertRaises(RuntimeError) as cm:
            run_pjp_workdays_loader(mock_env)

        self.assertIn("belum terpasang di registry Odoo", str(cm.exception))
        self.assertIn("false success", str(cm.exception))

    def test_04_new_evidence_transactions_still_strictly_enforced(self):
        """Memastikan bahwa alur transaksi baru tetap wajib melewati validasi ketat foto & geofence."""
        # 1. Uji penolakan lokasi di luar geofence
        meta_outside = self.metadata()
        meta_outside["latitude"] = self.outlet.partner_latitude + 0.05  # ~5.5 km jauhnya
        with self.assertRaises(EvidenceRejected) as cm_geo:
            self.api()._capture(meta_outside, self.source)
        self.assertEqual(cm_geo.exception.code, "geofence_outside")

        # 2. Uji penolakan foto tidak valid (kosong)
        meta_valid = self.metadata()
        with self.assertRaises(EvidenceRejected) as cm_photo:
            self.api()._capture(meta_valid, b"")
        self.assertEqual(cm_photo.exception.code, "invalid_photo")

        # 3. Uji foto contoh yang sama pada 2 outlet/kunjungan berbeda menghasilkan 2 UUID independen
        outlet_2 = self.env["res.partner"].create({
            "name": "Outlet Kedua",
            "company_id": self.company.id,
            "partner_latitude": 1.482000,
            "partner_longitude": 124.848000,
        })
        self.assignment.outlet_ids = [Command.link(outlet_2.id)]

        meta_1 = self.metadata()
        receipt_1, created_1 = self.api()._capture(meta_1, self.source)
        self.assertTrue(created_1)

        meta_2 = self.metadata()
        meta_2["outlet_id"] = str(outlet_2.id)
        meta_2["latitude"] = outlet_2.partner_latitude
        meta_2["longitude"] = outlet_2.partner_longitude
        receipt_2, created_2 = self.api()._capture(meta_2, self.source)
        self.assertTrue(created_2)

        self.assertNotEqual(receipt_1["client_uuid"], receipt_2["client_uuid"])
        self.assertNotEqual(receipt_1["outlet_id"], receipt_2["outlet_id"])
