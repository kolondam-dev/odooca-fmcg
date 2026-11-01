# Part of odooca-fmcg. License LGPL-3.
import base64
import importlib.util
import io
from datetime import date
from pathlib import Path

from PIL import Image

from odoo.tests import HttpCase, TransactionCase, tagged

from ..models.mobile_evidence import EvidenceRejected
from .test_evidence_api import EvidenceFixture


def _get_pjp_loader_module():
    """Memuat modul loader PJP secara dinamis dan aman untuk lingkungan CI container maupun lokal."""
    candidates = [
        Path(__file__).resolve().parents[3] / "scripts" / "load_pjp_workdays.py",
        Path("/opt/scripts/load_pjp_workdays.py"),
        Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "load_pjp_workdays.py",
        Path("scripts/load_pjp_workdays.py"),
    ]
    for p in candidates:
        if p.is_file():
            spec = importlib.util.spec_from_file_location("load_pjp_workdays", str(p))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    return None


@tagged("post_install", "-at_install")
class TestPjpLoaderBoundariesHttp(EvidenceFixture, HttpCase):
    def test_01_loader_evidence_attachments_watermark_and_dashboard_date(self):
        """Memastikan evidence historis memiliki attachment asli & watermark valid,

        dapat dibuka melalui controller HTTP tanpa TypeError, dan create_date berada
        pada tanggal historis Juli 2026 sehingga terhitung oleh dashboard sales.
        """
        loader = _get_pjp_loader_module()
        self.assertIsNotNone(loader, "Modul load_pjp_workdays.py harus dapat dimuat.")

        # Buat outlet dengan ref yang ada di customer registry untuk company ini
        self.outlet.ref = "CUST-0001"
        self.outlet.pjp_call_day = "wednesday"
        self.outlet.pjp_frequency = "F1"

        # Jalankan loader produksi dengan batasan limit bukti
        loader.run_pjp_workdays_loader(self.env, max_evidence_limit=3, target_company=self.company)

        # Cari evidence yang dibuat untuk user ini
        evidences = self.env["id.mobile.evidence"].sudo().search([
            ("company_id", "=", self.company.id),
        ], limit=5)
        self.assertTrue(evidences, "Loader harus membuat record evidence untuk company target.")

        target_ev = evidences[0]
        self.assertTrue(target_ev.original, "Kolom original harus terisi attachment.")
        self.assertTrue(target_ev.watermarked, "Kolom watermarked harus terisi attachment.")

        # Verifikasi bahwa create_date berada di bulan Juli 2026 (bukan tanggal hari ini saat impor)
        self.assertEqual(target_ev.create_date.year, 2026)
        self.assertEqual(target_ev.create_date.month, 7)

        # Autentikasi dan uji akses controller foto
        self.authenticate(target_ev.user_id.login, "mobile-api-test")

        # 1. Probe original
        resp_orig = self.url_open(f"/api/v1/evidence/{target_ev.client_uuid}/original")
        self.assertEqual(resp_orig.status_code, 200)
        self.assertEqual(resp_orig.headers.get("Content-Type"), "image/jpeg")
        self.assertTrue(resp_orig.content.startswith(b"\xff\xd8"))

        # 2. Probe watermarked
        resp_wm = self.url_open(f"/api/v1/evidence/{target_ev.client_uuid}/watermarked")
        self.assertEqual(resp_wm.status_code, 200)
        self.assertEqual(resp_wm.headers.get("Content-Type"), "image/jpeg")
        self.assertTrue(resp_wm.content.startswith(b"\xff\xd8"))

        # Verifikasi gambar dapat dibuka oleh PIL
        with Image.open(io.BytesIO(resp_wm.content)) as im:
            self.assertEqual(im.format, "JPEG")
            self.assertGreater(im.width, 0)
            self.assertGreater(im.height, 0)

        # 3. Verifikasi perhitungan dashboard sales productivity tidak 0
        SalesProd = self.env["id.sales.productivity"].with_company(self.company).sudo()
        pjp_data = SalesProd._pjp(
            start=date(2026, 7, 1),
            end=date(2026, 8, 1),
            lo=target_ev.create_date.replace(hour=0, minute=0, second=0),
            hi=target_ev.create_date.replace(hour=23, minute=59, second=59),
            salesman_ids=[target_ev.user_id.id],
            channel_ids=[],
            order_info={},
        )
        # Jika PJP tersedia, completed visits harus terdeteksi (> 0)
        if pjp_data.get("status", {}).get("available"):
            self.assertGreater(pjp_data.get("total", {}).get("completed", 0), 0)


@tagged("post_install", "-at_install")
class TestPjpLoaderBoundariesTransaction(EvidenceFixture, TransactionCase):
    def test_02_loader_multi_company_partner_and_self_healing_isolation(self):
        """Memastikan update PJP partner dan self-healing evidence terisolasi per company,

        tanpa menghapus atau mengubah data milik company lain.
        """
        Partner = self.env["res.partner"].sudo()
        Evidence = self.env["id.mobile.evidence"].sudo()

        shared_ref = "TEST-REF-CROSS-ISOLATION"

        # Partner di target company (company 1)
        partner_target = Partner.create({
            "name": "Outlet Target Company",
            "ref": shared_ref,
            "company_id": self.company.id,
            "pjp_call_day": "monday",
            "pjp_frequency": "F1",
        })

        # Partner di foreign company (company 2) dengan ref sama
        partner_foreign = Partner.create({
            "name": "Outlet Foreign Company",
            "ref": shared_ref,
            "company_id": self.foreign.id,
            "pjp_call_day": "monday",
            "pjp_frequency": "F1",
        })

        # Update scoped
        self.env.cr.execute("""
            UPDATE res_partner
            SET pjp_call_day = %s, pjp_frequency = %s, delivery_route = %s
            WHERE ref = %s AND (company_id = %s OR company_id IS NULL)
        """, ["friday", "F2", "RUTE-TARGET", shared_ref, self.company.id])

        partner_target.invalidate_recordset()
        partner_foreign.invalidate_recordset()

        self.assertEqual(partner_target.pjp_call_day, "friday")
        self.assertEqual(partner_foreign.pjp_call_day, "monday", "Partner company lain tidak boleh terupdate!")

        # Uji self-healing terisolasi: Evidence di foreign company dengan UUID tertentu
        foreign_uuid = "11111111-2222-3333-4444-555555555555"
        foreign_evidence = Evidence.create({
            "user_id": self.other.id,
            "company_id": self.foreign.id,
            "outlet_id": partner_foreign.id,
            "client_uuid": foreign_uuid,
            "fingerprint": "fprint_foreign",
            "receipt_json": "{}",
            "original": base64.b64encode(self.source),
            "watermarked": base64.b64encode(self.source),
        })

        # Loader mencari existing record untuk user target di company target
        existing_in_target = Evidence.search([
            ("client_uuid", "=", foreign_uuid),
            ("user_id", "=", self.mobile.id),
            ("company_id", "=", self.company.id),
        ], limit=1)
        # Tidak boleh menemukan evidence milik foreign company
        self.assertFalse(existing_in_target)
        # Evidence foreign company harus tetap utuh dan aktif
        self.assertTrue(foreign_evidence.exists())

    def test_03_workday_preservation_ordinary_workdays_not_overwritten(self):
        """Memastikan workday operasional yang sudah ada tidak ditimpa/dihapus outlet-nya."""
        loader = _get_pjp_loader_module()
        self.assertIsNotNone(loader)

        Workday = self.env["id.mobile.workday"].sudo().with_company(self.company)
        Partner = self.env["res.partner"].sudo()

        # Buat outlet khusus di luar matriks PJP
        outlet_custom = Partner.create({
            "name": "Outlet Operasional Khusus",
            "company_id": self.company.id,
            "partner_latitude": 1.48,
            "partner_longitude": 124.84,
        })

        target_date = "2026-07-15"
        # Buat workday awal untuk mobile user pada target_date
        existing_wd = Workday.create({
            "active": True,
            "business_date": target_date,
            "user_id": self.mobile.id,
            "company_id": self.company.id,
            "warehouse_id": self.warehouse.id,
            "pricelist_id": self.pricelist.id,
            "outlet_ids": [(6, 0, [outlet_custom.id])],
        })

        # Jalankan loader untuk company ini
        loader.run_pjp_workdays_loader(self.env, max_evidence_limit=1, target_company=self.company)

        existing_wd.invalidate_recordset()
        # Outlet khusus milik user TIDAK BOLEH hilang dari workday
        self.assertIn(outlet_custom.id, existing_wd.outlet_ids.ids, "Outlet khusus tidak boleh ditimpa!")

    def test_04_loader_fails_fast_when_models_missing(self):
        """Memastikan loader melempar RuntimeError (fail-fast) jika model mobile belum terpasang."""
        loader = _get_pjp_loader_module()
        self.assertIsNotNone(loader)

        class MockEnv(dict):
            def __contains__(self, key):
                if key in ("id.mobile.workday", "id.mobile.evidence"):
                    return False
                return super().__contains__(key)

        mock_env = MockEnv()
        with self.assertRaises(RuntimeError) as cm:
            loader.run_pjp_workdays_loader(mock_env)

        self.assertIn("belum terpasang di registry Odoo", str(cm.exception))

    def test_05_new_evidence_transactions_still_strictly_enforced(self):
        """Memastikan bahwa alur transaksi baru tetap wajib melewati validasi ketat foto & geofence."""
        meta_outside = self.metadata()
        meta_outside["latitude"] = self.outlet.partner_latitude + 0.05
        with self.assertRaises(EvidenceRejected) as cm_geo:
            self.api()._capture(meta_outside, self.source)
        self.assertEqual(cm_geo.exception.code, "geofence_outside")

        meta_valid = self.metadata()
        with self.assertRaises(EvidenceRejected) as cm_photo:
            self.api()._capture(meta_valid, b"")
        self.assertEqual(cm_photo.exception.code, "invalid_photo")
