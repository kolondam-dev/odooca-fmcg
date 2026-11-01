# Part of odooca-fmcg. License LGPL-3.
import base64
import importlib.util
import io
import json
import uuid
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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

        # Siapkan salesman dan outlet dengan ref kanonikal di pjp_july_2026_matrix.csv
        self.mobile.login = "sls-01"
        self.outlet.ref = "CUST-MT-04"
        self.outlet.pjp_call_day = "wednesday"
        self.outlet.pjp_frequency = "F1"
        self.outlet.partner_latitude = 1.518418
        self.outlet.partner_longitude = 124.906002

        # Jalankan loader produksi dengan batasan limit bukti dan commit=False
        loader.run_pjp_workdays_loader(self.env, max_evidence_limit=3, target_company=self.company, commit=False)

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

        # Verifikasi receipt JSON dan konsistensi timezone dengan waktu lokal WITA (UTC+8)
        receipt = json.loads(target_ev.receipt_json)
        self.assertTrue(receipt.get("is_historical_seed"))
        photo_utc_str = receipt["photo_selected_at"]
        self.assertTrue(photo_utc_str.endswith("Z"))
        dt_utc = datetime.fromisoformat(photo_utc_str.replace("Z", "+00:00"))
        dt_wita = dt_utc.astimezone(ZoneInfo("Asia/Makassar"))
        self.assertEqual(dt_wita.utcoffset().total_seconds(), 8 * 3600)

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

        # 3. Verifikasi perhitungan dashboard sales productivity
        SalesProd = self.env["id.sales.productivity"].with_company(self.company).sudo()
        # Query harian untuk tanggal target_ev (2026-07-01) -> completed: 1
        pjp_data_day = SalesProd._pjp(
            start=date(2026, 7, 1),
            end=date(2026, 8, 1),
            lo=target_ev.create_date.replace(hour=0, minute=0, second=0),
            hi=target_ev.create_date.replace(hour=23, minute=59, second=59),
            salesman_ids=[target_ev.user_id.id],
            channel_ids=[],
            order_info={},
        )
        self.assertTrue(pjp_data_day.get("status", {}).get("available"), "PJP status harian harus available.")
        self.assertEqual(pjp_data_day.get("total", {}).get("completed"), 1, "Completed visits hari ini harus tepat 1.")

        # Query bulanan untuk seluruh bulan Juli 2026 -> completed: 3 (sesuai max_evidence_limit=3)
        pjp_data_month = SalesProd._pjp(
            start=date(2026, 7, 1),
            end=date(2026, 8, 1),
            lo=datetime(2026, 7, 1, 0, 0, 0),
            hi=datetime(2026, 7, 31, 23, 59, 59),
            salesman_ids=[target_ev.user_id.id],
            channel_ids=[],
            order_info={},
        )
        self.assertTrue(pjp_data_month.get("status", {}).get("available"), "PJP status bulanan harus available.")
        self.assertEqual(
            pjp_data_month.get("total", {}).get("completed"),
            3,
            "Completed visits seluruh bulan Juli harus tepat 3.",
        )


@tagged("post_install", "-at_install")
class TestPjpLoaderBoundariesTransaction(EvidenceFixture, TransactionCase):
    def test_02_loader_multi_company_partner_and_self_healing_isolation(self):
        """Memastikan eksekusi loader produksi menjaga isolasi multi-company partner dan evidence,

        tanpa menghapus atau mengubah data milik company lain.
        """
        loader = _get_pjp_loader_module()
        self.assertIsNotNone(loader)

        Partner = self.env["res.partner"].sudo()
        Evidence = self.env["id.mobile.evidence"].sudo()

        shared_ref = "CUST-MT-04"

        # Partner di target company (company 1)
        self.mobile.login = "sls-01"
        self.outlet.ref = shared_ref
        self.outlet.pjp_call_day = "monday"

        # Partner di foreign company (company 2) dengan ref sama
        partner_foreign = Partner.create({
            "name": "Outlet Foreign Company",
            "ref": shared_ref,
            "company_id": self.foreign.id,
            "pjp_call_day": "monday",
            "pjp_frequency": "F1",
        })

        # Evidence di foreign company dengan UUID tertentu
        foreign_uuid = "11111111-2222-3333-4444-555555555555"
        foreign_evidence = Evidence.create({
            "user_id": self.other.id,
            "company_id": self.foreign.id,
            "outlet_id": partner_foreign.id,
            "client_uuid": foreign_uuid,
            "fingerprint": "fprint_foreign",
            "receipt_json": json.dumps({"client_uuid": foreign_uuid, "is_historical_seed": True}),
            "original": base64.b64encode(self.source),
            "watermarked": base64.b64encode(self.source),
        })

        # Jalankan loader jalur produksi utuh untuk target company
        loader.run_pjp_workdays_loader(self.env, max_evidence_limit=1, target_company=self.company, commit=False)

        partner_foreign.invalidate_recordset()
        foreign_evidence.invalidate_recordset()

        # Partner dan evidence foreign company TIDAK BOLEH dimutasi
        self.assertEqual(partner_foreign.pjp_call_day, "monday", "Partner company lain tidak boleh terupdate!")
        self.assertTrue(foreign_evidence.exists(), "Evidence foreign company tidak boleh dihapus!")
        self.assertEqual(foreign_evidence.company_id.id, self.foreign.id)

    def test_03_workday_preservation_ordinary_workdays_not_overwritten(self):
        """Memastikan ordinary workday collision terdeteksi sebelum partial write,

        menjaga snapshot workday biasa identik dan membatalkan pemuatan evidence inkonsisten.
        """
        loader = _get_pjp_loader_module()
        self.assertIsNotNone(loader)

        Workday = self.env["id.mobile.workday"].sudo().with_company(self.company)
        Partner = self.env["res.partner"].sudo()

        self.mobile.login = "sls-01"
        self.outlet.ref = "CUST-MT-04"

        # Buat outlet khusus di luar matriks PJP
        outlet_custom = Partner.create({
            "name": "Outlet Operasional Khusus",
            "company_id": self.company.id,
            "partner_latitude": 1.48,
            "partner_longitude": 124.84,
        })

        target_date = "2026-07-01"
        # Buat workday awal untuk mobile user pada target_date hanya berisi outlet khusus
        existing_wd = Workday.create({
            "active": True,
            "business_date": target_date,
            "user_id": self.mobile.id,
            "company_id": self.company.id,
            "warehouse_id": self.warehouse.id,
            "pricelist_id": self.pricelist.id,
            "outlet_ids": [(6, 0, [outlet_custom.id])],
        })

        # Jalankan loader untuk company ini: HARUS melempar RuntimeError karena kolisi workday biasa
        with self.assertRaises(RuntimeError) as cm:
            loader.run_pjp_workdays_loader(self.env, max_evidence_limit=1, target_company=self.company, commit=False)

        self.assertIn("Kolisi Workday Biasa", str(cm.exception))

        existing_wd.invalidate_recordset()
        # Snapshot workday biasa HARUS tetap identik (tidak bertambah atau berkurang outlet)
        self.assertEqual(
            existing_wd.outlet_ids.ids,
            [outlet_custom.id],
            "Workday operasional yang sudah ada harus terjaga 100% identik tanpa partial write!",
        )

        # Verifikasi tidak ada evidence parsial yang dibuat untuk self.outlet
        ev_count = self.env["id.mobile.evidence"].sudo().search_count([
            ("user_id", "=", self.mobile.id),
            ("company_id", "=", self.company.id),
            ("outlet_id", "=", self.outlet.id),
        ])
        self.assertEqual(ev_count, 0, "Evidence di luar assignment tidak boleh dibuat saat ada kolisi workday!")

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

    def test_06_non_seed_evidence_not_backdated_or_deleted(self):
        """Memastikan kolisi evidence non-seed (operasional riil) terdeteksi saat preflight,

        tidak dibackdate, tidak dihapus, dan loader membatalkan pemuatan dengan error.
        """
        loader = _get_pjp_loader_module()
        self.assertIsNotNone(loader)

        self.mobile.login = "sls-01"
        self.outlet.ref = "CUST-MT-04"

        Evidence = self.env["id.mobile.evidence"].sudo()

        # Generate UUID persis sesuai pola loader untuk kombinasi salesman & outlet ini
        target_date = "2026-07-01"
        cuuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"fmcg-visit-{self.mobile.id}-{self.outlet.id}-{target_date}"))

        # Buat evidence non-seed (transaksi riil di masa kini)
        non_seed = Evidence.create({
            "user_id": self.mobile.id,
            "company_id": self.company.id,
            "outlet_id": self.outlet.id,
            "client_uuid": cuuid,
            "fingerprint": "fprint_live_transaction",
            "receipt_json": json.dumps({
                "client_uuid": cuuid,
                "is_historical_seed": False,
            }),
            "original": base64.b64encode(self.source),
            "watermarked": base64.b64encode(self.source),
        })

        initial_create_date = non_seed.create_date

        # Jalankan loader tanpa commit: HARUS gagal karena kolisi non-seed
        with self.assertRaises(RuntimeError) as cm:
            loader.run_pjp_workdays_loader(self.env, max_evidence_limit=5, target_company=self.company, commit=False)

        self.assertIn("Kolisi Evidence Non-Seed", str(cm.exception))

        non_seed.invalidate_recordset()
        # create_date non-seed tidak boleh di-backdate ke Juli 2026
        self.assertEqual(
            non_seed.create_date,
            initial_create_date,
            "Evidence non-seed operasional tidak boleh dibackdate oleh loader!",
        )
        self.assertTrue(non_seed.exists(), "Evidence non-seed operasional tidak boleh dihapus oleh loader!")

    def test_07_receipt_timestamp_utc_matches_wita_local_time(self):
        """Memastikan perbandingan instant receipt, timestamp DB, dan input WITA selaras tepat 8 jam."""
        loader = _get_pjp_loader_module()
        self.assertIsNotNone(loader)

        self.mobile.login = "sls-01"
        self.outlet.ref = "CUST-MT-04"

        loader.run_pjp_workdays_loader(self.env, max_evidence_limit=2, target_company=self.company, commit=False)

        evidences = self.env["id.mobile.evidence"].sudo().search([
            ("company_id", "=", self.company.id),
        ], limit=1)
        self.assertTrue(evidences, "Evidence seed historis harus terbentuk.")

        target_ev = evidences[0]
        receipt = json.loads(target_ev.receipt_json)
        photo_utc_str = receipt["photo_selected_at"]
        self.assertTrue(photo_utc_str.endswith("Z"), "Timestamp receipt harus berformat ISO UTC ('Z').")

        dt_utc = datetime.fromisoformat(photo_utc_str.replace("Z", "+00:00"))
        dt_wita = dt_utc.astimezone(ZoneInfo("Asia/Makassar"))

        # Verifikasi instant receipt sama persis dengan timestamp DB Odoo
        self.assertEqual(target_ev.create_date.hour, dt_utc.hour)
        self.assertEqual(target_ev.create_date.minute, dt_utc.minute)
        self.assertEqual(target_ev.create_date.second, dt_utc.second)

        # Verifikasi selisih WITA vs UTC tepat 8 jam
        self.assertEqual(dt_wita.hour - dt_utc.hour, 8)
        self.assertEqual(dt_wita.utcoffset().total_seconds(), 8 * 3600)

        # Verifikasi jam kerja: WITA 08:00-16:00, UTC 00:00-08:00 (mencegah regresi bug 08:10Z lama)
        self.assertIn(dt_wita.hour, range(8, 17))
        self.assertLess(dt_utc.hour, 9, "Jam UTC harus berada di 00:00-08:00 UTC, bukan jam WITA dengan akhiran Z!")

    def test_08_legacy_repair_and_atomic_migration(self):
        """Memastikan record legacy (timestamp lama / foto kosong) dimigrasikan secara atomik dan konsisten."""
        loader = _get_pjp_loader_module()
        self.assertIsNotNone(loader)

        self.mobile.login = "sls-01"
        self.outlet.ref = "CUST-MT-04"

        Evidence = self.env["id.mobile.evidence"].sudo()
        target_date = "2026-07-01"
        cuuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"fmcg-visit-{self.mobile.id}-{self.outlet.id}-{target_date}"))

        # Buat legacy record versi awal dengan timestamp lama (08:10Z)
        Evidence.create({
            "user_id": self.mobile.id,
            "company_id": self.company.id,
            "outlet_id": self.outlet.id,
            "client_uuid": cuuid,
            "fingerprint": "fprint_legacy_initial",
            "receipt_json": json.dumps({
                "client_uuid": cuuid,
                "snapshot_version": "v1-canonical-july-2026",
                "photo_selected_at": f"{target_date}T08:10:00Z",
                "seed_batch": "pjp_workdays_july_2026_v1",
                "is_historical_seed": True,
            }),
            "original": base64.b64encode(self.source),
            "watermarked": base64.b64encode(self.source),
        })

        # Jalankan loader untuk memicu atomic repair
        loader.run_pjp_workdays_loader(self.env, max_evidence_limit=1, target_company=self.company, commit=False)

        repaired = Evidence.search([
            ("client_uuid", "=", cuuid),
            ("company_id", "=", self.company.id),
        ], limit=1)
        self.assertTrue(repaired, "Record yang diperbaiki harus tetap ada.")

        rep_receipt = json.loads(repaired.receipt_json)
        # Timestamp lama 08:10Z harus telah dimigrasikan ke 00:10:10Z (UTC yang sinkron dengan WITA)
        self.assertTrue(rep_receipt["photo_selected_at"].startswith(f"{target_date}T00:10:"))
        self.assertEqual(repaired.create_date.year, 2026)
        self.assertEqual(repaired.create_date.month, 7)
        self.assertTrue(repaired.original)
        self.assertTrue(repaired.watermarked)

    def test_09_foreign_batch_collision_rejected(self):
        """Memastikan evidence milik batch lain ditolak saat preflight dan tidak dimutasi."""
        loader = _get_pjp_loader_module()
        self.assertIsNotNone(loader)

        self.mobile.login = "sls-01"
        self.outlet.ref = "CUST-MT-04"

        Evidence = self.env["id.mobile.evidence"].sudo()
        target_date = "2026-07-01"
        cuuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"fmcg-visit-{self.mobile.id}-{self.outlet.id}-{target_date}"))

        foreign_batch_ev = Evidence.create({
            "user_id": self.mobile.id,
            "company_id": self.company.id,
            "outlet_id": self.outlet.id,
            "client_uuid": cuuid,
            "fingerprint": "fprint_foreign_batch",
            "receipt_json": json.dumps({
                "client_uuid": cuuid,
                "is_historical_seed": True,
                "seed_batch": "OTHER_BATCH_2026",
            }),
            "original": base64.b64encode(self.source),
            "watermarked": base64.b64encode(self.source),
        })

        initial_create_date = foreign_batch_ev.create_date

        with self.assertRaises(RuntimeError) as cm:
            loader.run_pjp_workdays_loader(self.env, max_evidence_limit=1, target_company=self.company, commit=False)

        self.assertIn("Kolisi Batch Lain", str(cm.exception))

        foreign_batch_ev.invalidate_recordset()
        self.assertEqual(foreign_batch_ev.create_date, initial_create_date, "Record batch lain tidak boleh dibackdate!")
        self.assertTrue(foreign_batch_ev.exists(), "Record batch lain tidak boleh dihapus!")
