#!/usr/bin/env python3
"""test_seed_planner.py - Unit & Reproducibility Tests for Phase F2 Seed Planner."""

import copy
import datetime as dt
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from scripts.ops.fmcg_calendar import count_working_days, is_working_day
from scripts.ops.generate_period_pack import (
    compute_sha256_lf,
    get_verified_previous_closing,
    resolve_opening_state_path,
)
from scripts.ops.seed_planner import (
    PeriodConfig,
    SeedPlanner,
    deterministic_seed,
    extract_existing_numbers,
    prepare_gate_opening,
)
from scripts.ops.seed_v2_gates import validate_pack_report

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestSeedPlannerF2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg_dir = REPO_ROOT / "data" / "registers"
        cls.opening_path = cls.reg_dir / "state_20260801.json"
        with cls.opening_path.open("r", encoding="utf-8") as f:
            cls.raw_opening = json.load(f)

        cls.config = PeriodConfig(
            pack_start="2026-08-01",
            pack_end="2026-08-31",
            opening_cash=Decimal("5000000000.00"),
            tax_rate=Decimal("0.11"),
            target_net_dpp=Decimal("4235000000.00"),
            target_discount_pct=Decimal("2.50"),
            target_rejection_pct=Decimal("2.40"),
        )
        cls.planner = SeedPlanner(cls.config, root_dir=REPO_ROOT)
        cls.res = cls.planner.plan_period(cls.raw_opening)
        cls.pack = cls.res["pack"]
        cls.narrative = cls.res["narrative_report"]
        cls.last_seq = cls.res["last_sequences"]

        cls.gate_opening = prepare_gate_opening(cls.raw_opening)
        cls.existing = extract_existing_numbers(cls.gate_opening)

    def test_deterministic_seed_is_consistent(self):
        s1 = deterministic_seed("42", "call_order", "2026-08-01")
        s2 = deterministic_seed("42", "call_order", "2026-08-01")
        self.assertEqual(s1, s2)
        s3 = deterministic_seed("42", "call_order", "2026-08-03")
        self.assertNotEqual(s1, s3)

    def test_full_pack_passes_seed_v2_gates_in_strict_mode(self):
        bands = {
            "net_dpp": (Decimal("4000000000.00"), Decimal("4500000000.00")),
            "discount_pct": (Decimal("2.00"), Decimal("3.20")),
            "rejection_pct": (Decimal("1.80"), Decimal("3.00")),
            "active_outlets": (Decimal("200"), Decimal("215")),
        }
        gate_config = {
            "pack_start": "2026-08-01",
            "pack_end": "2026-08-31",
            "opening_cash": "5000000000.00",
            "min_lead_days": self.config.min_lead_days,
            "tax": {
                "rate": "0.11",
                "source": "PMK 131/2024 & UU HPP No. 7/2021",
                "source_date": "2024-12-31",
                "effective_from": "2025-01-01",
            },
        }
        verified_prev = get_verified_previous_closing("2026-08", self.reg_dir)
        report = validate_pack_report(
            pack=self.pack,
            opening=self.gate_opening,
            previous_closing=verified_prev,
            existing_numbers=self.existing,
            config=gate_config,
            bands=bands,
            strict=True,
        )
        self.assertEqual(report.get("violations"), [])
        self.assertEqual(report.get("gates_skipped"), [])
        self.assertGreaterEqual(len(report.get("gates_run", [])), 11)

    def test_continuity_gate_rejects_quarantine_mutation(self):
        mutated_opening = copy.deepcopy(self.gate_opening)
        first_key = next(iter(mutated_opening["stock"]))
        mutated_opening["stock"][first_key]["quarantine"] += Decimal("1")

        gate_config = {
            "pack_start": "2026-08-01",
            "pack_end": "2026-08-31",
            "opening_cash": "5000000000.00",
            "min_lead_days": self.config.min_lead_days,
            "tax": {
                "rate": "0.11",
                "source": "PMK 131/2024 & UU HPP No. 7/2021",
                "source_date": "2024-12-31",
                "effective_from": "2025-01-01",
            },
        }
        verified_prev = get_verified_previous_closing("2026-08", self.reg_dir)
        report = validate_pack_report(
            pack=self.pack,
            opening=mutated_opening,
            previous_closing=verified_prev,
            existing_numbers=self.existing,
            config=gate_config,
            strict=True,
        )
        violations = [v for v in report.get("violations", []) if v.get("invariant") == "PERIOD-CONTINUITY"]
        self.assertGreaterEqual(
            len(violations), 1, "Mutating quarantine carton must trigger PERIOD-CONTINUITY violation"
        )

    def test_every_so_has_matching_delivery_and_invoice(self):
        so_numbers = {so["so_number"] for so in self.pack["sales_orders"]}
        do_so_numbers = {do["so_number"] for do in self.pack["deliveries"]}
        inv_so_numbers = {inv["so_number"] for inv in self.pack["invoices"]}

        self.assertEqual(len(self.pack["sales_orders"]), 1240)
        self.assertEqual(len(self.pack["deliveries"]), 1240)
        self.assertEqual(len(self.pack["invoices"]), 1240)

        self.assertEqual(so_numbers, do_so_numbers, "Every SO must have an associated Delivery Order")
        self.assertEqual(so_numbers, inv_so_numbers, "Every SO must have an associated Invoice")

        # 50 SO tanggal 31 Agustus harus terjadwal delivery 2026-09-01 dan tercatat di pending_dos
        aug_31_sos = {so["so_number"] for so in self.pack["sales_orders"] if so["date_order"] == "2026-08-31"}
        self.assertEqual(len(aug_31_sos), 50)

        pending_dos = {
            do["do_number"]: do["scheduled_delivery_date"]
            for do in self.pack["deliveries"]
            if do["so_number"] in aug_31_sos
        }
        self.assertEqual(len(pending_dos), 50)
        for sched_date in pending_dos.values():
            self.assertEqual(sched_date, "2026-09-01")

    def test_po_lead_time_in_working_days(self):
        for po in self.pack["po_headers"]:
            po_num = po["po_number"]
            order_dt = dt.date.fromisoformat(po["order_date"])
            arrival_dt = dt.date.fromisoformat(po["arrival_maumbi_date"])
            prin = po["principal_code"]
            min_lead = self.config.min_lead_days[prin]

            work_days = count_working_days(order_dt, arrival_dt)
            self.assertGreaterEqual(
                work_days,
                min_lead,
                f"PO {po_num} ({prin}) lead time {work_days} working days < minimum {min_lead}",
            )
            self.assertTrue(
                is_working_day(arrival_dt),
                f"PO {po_num} arrival {arrival_dt} is not a valid working day",
            )

    def test_august_to_september_chained_generation(self):
        pack_dir = self.reg_dir / "periods" / "2026-08"
        aug_closing_path = pack_dir / "closing_state_20260831.json"
        self.assertTrue(aug_closing_path.exists())

        with aug_closing_path.open("r", encoding="utf-8") as f:
            aug_closing_raw = json.load(f)

        # 1. Pastikan PO di closing Agustus memuat objek lengkap (nominal + tanggal jatuh tempo)
        self.assertGreater(len(aug_closing_raw.get("open_po", {})), 0)
        first_open_po = next(iter(aug_closing_raw["open_po"].values()))
        self.assertIsInstance(first_open_po, dict)
        self.assertIn("payment_due_date", first_open_po)
        self.assertIn("total_amount_dpp", first_open_po)

        # 2. Inisialisasi September Planner menggunakan closing Agustus
        sep_config = PeriodConfig(
            pack_start="2026-09-01",
            pack_end="2026-09-30",
            opening_cash=Decimal("5000000000.00"),
            tax_rate=Decimal("0.11"),
            target_net_dpp=Decimal("4235000000.00"),
        )
        sep_planner = SeedPlanner(sep_config, root_dir=REPO_ROOT)
        sep_res = sep_planner.plan_period(aug_closing_raw)
        sep_pack = sep_res["pack"]

        # Nomor PO di September harus menggunakan prefix PO-2026-09- (bukan hardcoded Agustus)
        first_sep_po = sep_pack["po_headers"][0]["po_number"]
        self.assertEqual(first_sep_po, "PO-2026-09-01")

        # Garis pesanan carry-forward dari 31 Agustus harus dikirim (stock event dispatch) pada 1 September
        sep_1_events = [e for e in sep_pack["stock_events"] if e["date"] == "2026-09-01"]
        self.assertGreaterEqual(len(sep_1_events), 50)

        # Faktur carry-forward Agustus harus terlunasi di September saat jatuh tempo
        carry_inv_nums = set(aug_closing_raw.get("carry_invoices", {}).keys())
        paid_invs = {a["invoice_number"] for a in sep_pack["ar_collections"]}
        paid_carry = carry_inv_nums.intersection(paid_invs)
        self.assertGreaterEqual(len(paid_carry), 30)

        # PO Agustus yang jatuh tempo di September harus terlunasi dengan sequence AP berlanjut
        first_ap = sep_pack["ap_payments"][0]
        self.assertEqual(first_ap["ap_payment_id"], "PAY-AP-06")
        self.assertTrue(first_ap["po_number"].startswith("PO-2026-08-"))

        # Validasi gerbang kontinuitas dan invariansi untuk September dari closing Agustus
        sep_opening = prepare_gate_opening(aug_closing_raw)
        verified_prev = get_verified_previous_closing("2026-09", self.reg_dir)
        sep_existing = extract_existing_numbers(sep_opening)

        gate_config = {
            "pack_start": "2026-09-01",
            "pack_end": "2026-09-30",
            "opening_cash": "5000000000.00",
            "min_lead_days": sep_config.min_lead_days,
            "tax": {
                "rate": "0.11",
                "source": "PMK 131/2024 & UU HPP No. 7/2021",
                "source_date": "2024-12-31",
                "effective_from": "2025-01-01",
            },
        }
        report = validate_pack_report(
            pack=sep_pack,
            opening=sep_opening,
            previous_closing=verified_prev,
            existing_numbers=sep_existing,
            config=gate_config,
            strict=False,
        )
        # Gerbang kontinuitas, double spend, link AR/AP, dan saldo stok tidak boleh ada pelanggaran
        for v in report.get("violations", []):
            self.assertNotEqual(v.get("invariant"), "PERIOD-CONTINUITY")
            self.assertNotEqual(v.get("invariant"), "STOCK-BALANCE")
            self.assertNotEqual(v.get("invariant"), "DOUBLE-SPEND")
            self.assertNotEqual(v.get("invariant"), "AR-PAYMENT-LINK")
            self.assertNotEqual(v.get("invariant"), "AP-PAYMENT-LINK")

    def test_carry_forward_rejection_consistency(self):
        # 1. Pastikan ada item carry-forward yang mengalami rejection (misal DO-202608-1223)
        rej_dos = [
            d for d in self.pack["deliveries"]
            if d["scheduled_delivery_date"] == "2026-09-01" and Decimal(d["rejection_dpp"]) > Decimal("0")
        ]
        self.assertGreater(len(rej_dos), 0, "Harus ada DO carry-forward yang memiliki rejection")

        target_do = rej_dos[0]
        do_num = target_do["do_number"]
        so_num = target_do["so_number"]
        rej_dpp = Decimal(target_do["rejection_dpp"])

        # 2. Cek bahwa faktur untuk DO tersebut memiliki net DPP komersial yang dikurangi nilai tolakan
        matching_inv = next(i for i in self.pack["invoices"] if i["do_number"] == do_num)
        matching_so = next(s for s in self.pack["sales_orders"] if s["so_number"] == so_num)
        so_net = Decimal(matching_so["net_dpp"])
        inv_comm = Decimal(matching_inv["commercial_dpp"])
        self.assertEqual(inv_comm, so_net - rej_dpp, "Faktur DO carry-forward harus dikurangi nilai tolakan")
        expected_tax_base = (inv_comm * Decimal(11) / Decimal(12)).quantize(Decimal("0.01"))
        self.assertEqual(Decimal(matching_inv["dpp_amount"]), expected_tax_base)

        # 3. Cek bahwa rejections.csv memiliki baris untuk DO tersebut bertanggal 2026-09-01
        matching_rej = [r for r in self.pack["rejections"] if r["do_number"] == do_num]
        self.assertEqual(len(matching_rej), 1)
        self.assertEqual(matching_rej[0]["rejection_date"], "2026-09-01")
        self.assertEqual(Decimal(matching_rej[0]["rejection_dpp"]), rej_dpp)

        # 4. Cek bahwa carry_forward_lines pada closing_state membawa flag is_rejected dan nominalnya
        pack_dir = self.reg_dir / "periods" / "2026-08"
        with (pack_dir / "closing_state_20260831.json").open("r", encoding="utf-8") as f:
            closing = json.load(f)
        cf_rejected = [
            row for row in closing.get("carry_forward_lines", [])
            if row.get("do_number") == do_num and row.get("is_rejected")
        ]
        self.assertEqual(len(cf_rejected), 1)
        self.assertEqual(Decimal(cf_rejected[0]["rejection_dpp"]), rej_dpp)

        # 5. Eksekusi September dari closing Agustus: pastikan stock_events 2026-09-01 memuat event karantina
        sep_config = PeriodConfig(
            pack_start="2026-09-01",
            pack_end="2026-09-30",
            opening_cash=Decimal("5000000000.00"),
            target_net_dpp=Decimal("4235000000.00"),
        )
        sep_planner = SeedPlanner(sep_config, root_dir=REPO_ROOT)
        sep_res = sep_planner.plan_period(closing)

        sku = cf_rejected[0]["sku_code"]
        lot = cf_rejected[0]["lot_number"]
        qty = cf_rejected[0]["qty_cartons"]

        q_events = [
            e for e in sep_res["pack"]["stock_events"]
            if e["date"] == "2026-09-01"
            and e["sku_code"] == sku
            and e["lot_number"] == lot
            and e["quarantine_impact"] == qty
        ]
        self.assertEqual(
            len(q_events), 1, "Stock events September harus mencatat event karantina untuk carry-forward rejected"
        )

    def test_calendar_working_days_strict_dispatch(self):
        # 17 Aug (Proklamasi) & 25 Aug (Maulid Nabi) must not contain SOs or deliveries
        for so in self.pack["sales_orders"]:
            d_str = so["date_order"]
            d = dt.date.fromisoformat(d_str)
            self.assertTrue(is_working_day(d), f"SO on non-working day: {d_str}")
            self.assertNotIn(d_str, ("2026-08-17", "2026-08-25"))

        for deliv in self.pack["deliveries"]:
            d_str = deliv["scheduled_delivery_date"]
            d = dt.date.fromisoformat(d_str)
            self.assertTrue(is_working_day(d), f"Delivery on non-working day: {d_str}")
            self.assertNotIn(d_str, ("2026-08-17", "2026-08-25"))

    def test_numbering_sequences_start_from_1_for_monthly_documents(self):
        first_so = self.pack["sales_orders"][0]["so_number"]
        self.assertEqual(first_so, "SO-202608-0001")

        first_do = self.pack["deliveries"][0]["do_number"]
        self.assertEqual(first_do, "DO-202608-0001")

        first_inv = self.pack["invoices"][0]["invoice_number"]
        self.assertEqual(first_inv, "INV-202608-0001")

        first_rej = self.pack["rejections"][0]["rejection_id"]
        self.assertEqual(first_rej, "REJ-202608-001")

        first_po = self.pack["po_headers"][0]["po_number"]
        self.assertEqual(first_po, "PO-2026-08-01")

    def test_global_numbering_continues_from_july_baseline(self):
        first_ar = self.pack["ar_collections"][0]["payment_id"]
        self.assertEqual(first_ar, "PAY-AR-00968")

        first_ap = self.pack["ap_payments"][0]["ap_payment_id"]
        self.assertEqual(first_ap, "PAY-AP-05")

        first_evt = self.pack["stock_events"][0]["event_id"]
        self.assertEqual(first_evt, "EVT-005742")

    def test_narrative_metrics_within_authorized_bands(self):
        m = self.narrative["metrics"]
        net_dpp = Decimal(m["net_dpp"])
        self.assertTrue(
            Decimal("4000000000.00") <= net_dpp <= Decimal("4500000000.00"),
            f"net_dpp {net_dpp} out of band",
        )

        disc_pct = Decimal(m["discount_pct"])
        self.assertTrue(Decimal("2.00") <= disc_pct <= Decimal("3.20"), f"discount_pct {disc_pct} out of band")

        rej_pct = Decimal(m["rejection_pct"])
        self.assertTrue(Decimal("1.80") <= rej_pct <= Decimal("3.00"), f"rejection_pct {rej_pct} out of band")

        active_outlets = m["active_outlets"]
        self.assertTrue(200 <= active_outlets <= 215, f"active_outlets {active_outlets} out of band")

    def test_ap_unilever_june_paid_on_due_date_august_8(self):
        ap_payments = self.pack["ap_payments"]
        self.assertEqual(len(ap_payments), 1)
        p = ap_payments[0]
        self.assertEqual(p["po_number"], "PO-2026-06-05")
        self.assertEqual(p["payment_date"], "2026-08-08")
        self.assertEqual(p["amount_paid_dpp"], "2899971200.00")

    def test_pack_manifest_sha256_integrity(self):
        pack_dir = self.reg_dir / "periods" / "2026-08"
        manifest_file = pack_dir / "MANIFEST.json"
        self.assertTrue(manifest_file.exists(), "MANIFEST.json must exist in pack directory")

        with manifest_file.open("r", encoding="utf-8") as f:
            manifest = json.load(f)

        files_sha = manifest["files_sha256"]
        self.assertGreaterEqual(len(files_sha), 20)

        for filename, recorded_hash in files_sha.items():
            fpath = pack_dir / filename
            self.assertTrue(fpath.exists(), f"File {filename} in manifest missing on disk")
            computed_hash = compute_sha256_lf(fpath)
            self.assertEqual(computed_hash, recorded_hash, f"Hash mismatch for {filename}")

    def test_pack_manifest_generator_sources_and_fingerprints(self):
        pack_dir = self.reg_dir / "periods" / "2026-08"
        manifest_file = pack_dir / "MANIFEST.json"
        with manifest_file.open("r", encoding="utf-8") as f:
            manifest = json.load(f)

        # 0. Generator commit provenance
        gen_commit = manifest.get("generator_commit")
        self.assertTrue(gen_commit, "generator_commit must be present in manifest")
        self.assertNotEqual(gen_commit, "UNKNOWN_COMMIT")

        # 1. Generator source binding
        sources = manifest.get("generator_sources_sha256", {})
        self.assertGreaterEqual(len(sources), 4)
        for rel_path, expected_hash in sources.items():
            fpath = REPO_ROOT / rel_path
            self.assertTrue(fpath.exists(), f"Source file {rel_path} must exist on disk")
            computed = compute_sha256_lf(fpath)
            self.assertEqual(computed, expected_hash, f"Source hash mismatch for {rel_path}")

        # 2. Canonical July 15 fingerprints
        canonical = manifest.get("canonical_july_15_register_fingerprints", {})
        self.assertEqual(len(canonical), 15)
        for fname, exp_hash in canonical.items():
            fpath = self.reg_dir / fname
            self.assertTrue(fpath.exists(), f"Canonical register {fname} must exist on disk")
            computed = compute_sha256_lf(fpath)
            self.assertEqual(computed, exp_hash, f"Canonical hash mismatch for {fname}")

    def test_default_opening_state_resolution_august(self):
        """Periode default 2026-08 otomatis memakai register state_20260801.json."""
        resolved = resolve_opening_state_path("2026-08", self.reg_dir)
        expected = self.reg_dir / "state_20260801.json"
        self.assertEqual(resolved, expected)
        self.assertTrue(resolved.exists())

    def test_default_opening_state_resolution_september_finds_august_closing(self):
        """Periode 2026-09 otomatis mencari dan menemukan closing_state dari pack 2026-08."""
        resolved = resolve_opening_state_path("2026-09", self.reg_dir)
        expected = self.reg_dir / "periods" / "2026-08" / "closing_state_20260831.json"
        self.assertEqual(resolved, expected)
        self.assertTrue(resolved.exists())

    def test_default_opening_state_resolution_missing_previous_fails_closed(self):
        """Periode non-Agustus tanpa closing periode sebelumnya wajib menolak dan meminta --opening-state."""
        with self.assertRaises(ValueError) as cm:
            resolve_opening_state_path("2027-05", self.reg_dir)
        self.assertIn("--opening-state", str(cm.exception))
        self.assertIn("2027-04", str(cm.exception))

    def test_explicit_opening_state_resolution(self):
        """Path opening_state eksplisit dihormati jika ada, dan memicu FileNotFoundError jika tidak ada."""
        explicit_path = self.reg_dir / "state_20260801.json"
        resolved = resolve_opening_state_path("2026-09", self.reg_dir, opening_state_path=explicit_path)
        self.assertEqual(resolved, explicit_path)

        with self.assertRaises(FileNotFoundError):
            resolve_opening_state_path("2026-09", self.reg_dir, opening_state_path=Path("non_existent_state.json"))

    def test_default_opening_state_resolution_missing_manifest_fails_fast(self):
        """Auto-resolve periode non-Agustus menolak jika MANIFEST.json periode sebelumnya tidak ada."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_reg = Path(tmp_dir)
            prev_dir = temp_reg / "periods" / "2026-08"
            prev_dir.mkdir(parents=True)
            closing_file = prev_dir / "closing_state_20260831.json"
            closing_file.write_text("{}", encoding="utf-8")

            with self.assertRaises(FileNotFoundError) as cm:
                resolve_opening_state_path("2026-09", temp_reg)
            self.assertIn("Pack manifest", str(cm.exception))

    def test_default_opening_state_resolution_closing_missing_from_manifest_fails_fast(self):
        """Auto-resolve periode non-Agustus menolak jika berkas closing tidak terdaftar di MANIFEST.json."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_reg = Path(tmp_dir)
            prev_dir = temp_reg / "periods" / "2026-08"
            prev_dir.mkdir(parents=True)
            closing_file = prev_dir / "closing_state_20260831.json"
            closing_file.write_text("{}", encoding="utf-8")
            other_file = prev_dir / "other.csv"
            other_file.write_text("dummy\n", encoding="utf-8")
            other_hash = compute_sha256_lf(other_file)
            manifest_file = prev_dir / "MANIFEST.json"
            manifest_file.write_text(json.dumps({"files_sha256": {"other.csv": other_hash}}), encoding="utf-8")

            with self.assertRaises(ValueError) as cm:
                resolve_opening_state_path("2026-09", temp_reg)
            self.assertIn("tidak terdaftar pada MANIFEST.json", str(cm.exception))

    def test_default_opening_state_resolution_checksum_mismatch_fails_fast(self):
        """Auto-resolve periode non-Agustus menolak jika hash closing tidak cocok dengan MANIFEST.json."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_reg = Path(tmp_dir)
            prev_dir = temp_reg / "periods" / "2026-08"
            prev_dir.mkdir(parents=True)
            closing_file = prev_dir / "closing_state_20260831.json"
            closing_file.write_text("{}", encoding="utf-8")
            manifest_file = prev_dir / "MANIFEST.json"
            manifest_file.write_text(
                json.dumps({"files_sha256": {"closing_state_20260831.json": "0" * 64}}),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as cm:
                resolve_opening_state_path("2026-09", temp_reg)
            self.assertIn("tidak valid menurut MANIFEST", str(cm.exception))

    def test_explicit_opening_state_checksum_mismatch_with_manifest_fails_fast(self):
        """Opening state eksplisit yang berada di direktori pack ber-MANIFEST menolak jika checksum tidak cocok."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_reg = Path(tmp_dir)
            prev_dir = temp_reg / "periods" / "2026-08"
            prev_dir.mkdir(parents=True)
            closing_file = prev_dir / "closing_state_20260831.json"
            closing_file.write_text("{}", encoding="utf-8")
            manifest_file = prev_dir / "MANIFEST.json"
            manifest_file.write_text(
                json.dumps({"files_sha256": {"closing_state_20260831.json": "bad_hash_value"}}),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as cm:
                resolve_opening_state_path("2026-09", temp_reg, opening_state_path=closing_file)
            self.assertIn("tidak cocok dengan MANIFEST", str(cm.exception))

    def test_explicit_opening_state_missing_from_manifest_fails_fast(self):
        """Opening state eksplisit dalam direktori pack ber-MANIFEST menolak jika tidak terdaftar di files_sha256."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_reg = Path(tmp_dir)
            pack_dir = temp_reg / "periods" / "2026-08"
            pack_dir.mkdir(parents=True)
            unregistered_file = pack_dir / "unregistered_state.json"
            unregistered_file.write_text("{}", encoding="utf-8")
            manifest_file = pack_dir / "MANIFEST.json"
            manifest_file.write_text(
                json.dumps({"files_sha256": {"other_file.csv": "0" * 64}}),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as cm:
                resolve_opening_state_path("2026-09", temp_reg, opening_state_path=unregistered_file)
            self.assertIn("tidak terdaftar pada MANIFEST.json", str(cm.exception))

    def test_explicit_opening_state_manifest_missing_files_sha256_fails_fast(self):
        """Opening state eksplisit dalam direktori pack ber-MANIFEST menolak jika files_sha256 hilang/kosong."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_reg = Path(tmp_dir)
            pack_dir = temp_reg / "periods" / "2026-08"
            pack_dir.mkdir(parents=True)
            state_file = pack_dir / "custom_state.json"
            state_file.write_text("{}", encoding="utf-8")
            manifest_file = pack_dir / "MANIFEST.json"
            manifest_file.write_text(
                json.dumps({"period": "2026-08"}),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as cm:
                resolve_opening_state_path("2026-09", temp_reg, opening_state_path=state_file)
            self.assertIn("tidak memuat entri files_sha256", str(cm.exception))

    def test_explicit_opening_state_outside_pack_without_manifest_accepted(self):
        """Opening state eksplisit di luar direktori ber-MANIFEST diterima langsung jika berkas ada."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            standalone_file = Path(tmp_dir) / "standalone_opening.json"
            standalone_file.write_text("{}", encoding="utf-8")

            resolved = resolve_opening_state_path(
                "2026-09",
                Path(tmp_dir),
                opening_state_path=standalone_file,
            )
            self.assertEqual(resolved, standalone_file)

    def test_commercial_invoices_tax_metadata(self):
        """Memverifikasi faktur komersial memuat commercial_dpp, dpp_amount 11/12, ppn 12%, dan tax_code 04."""
        invoices = self.pack["invoices"]
        self.assertGreater(len(invoices), 0)
        sample_inv = invoices[0]
        self.assertIn("commercial_dpp", sample_inv)
        self.assertIn("dpp_amount", sample_inv)
        self.assertIn("ppn_amount", sample_inv)
        self.assertIn("tax_rate", sample_inv)
        self.assertIn("customer_tax_id", sample_inv)
        self.assertIn("buyer_id_type", sample_inv)
        self.assertIn("is_pkp", sample_inv)
        self.assertIn("tax_invoice_type", sample_inv)
        self.assertIn("tax_code", sample_inv)
        self.assertEqual(sample_inv["tax_invoice_type"], "DPP_NILAI_LAIN")
        self.assertEqual(sample_inv["tax_code"], "04")

        # Coretax: periksa pemisahan PKP vs Non-PKP dan tipe identitas pembeli
        pkp_invs = [i for i in invoices if i["is_pkp"] == "True"]
        non_pkp_invs = [i for i in invoices if i["is_pkp"] == "False"]
        self.assertGreater(len(pkp_invs), 0)
        self.assertGreater(len(non_pkp_invs), 0)

        # Muat fixture profil identitas untuk memverifikasi konsistensi deklaratif 100%
        fixture_path = REPO_ROOT / "data" / "registers" / "customer_tax_profile_fixture.json"
        self.assertTrue(fixture_path.is_file(), "customer_tax_profile_fixture.json wajib ada di disk")
        import json
        profiles = json.loads(fixture_path.read_text(encoding="utf-8"))

        for i in invoices:
            cust_code = i["customer"].split(" - ")[0]
            self.assertIn(cust_code, profiles, f"Customer {cust_code} wajib terdaftar di profil pajak")
            prof = profiles[cust_code]
            self.assertEqual(i["is_pkp"], str(prof["is_pkp"]))
            self.assertEqual(i["buyer_id_type"], prof["buyer_id_type"])
            self.assertEqual(i["customer_tax_id"], prof["customer_tax_id"])
            self.assertEqual(i.get("tax_id_status"), prof.get("tax_id_status"))
            self.assertIn(i.get("tax_id_status"), {"SYNTHETIC_TEST_IDENTITY", "UNREGISTERED_ZERO_IDENTITY"})

        # PKP wajib ber-NPWP 16 digit
        for i in pkp_invs:
            self.assertEqual(i["buyer_id_type"], "NPWP16")
            self.assertEqual(len(i["customer_tax_id"]), 16)

        # Non-PKP memiliki NIK atau TIN_0 (bukan sekadar diasumsikan satu kategori)
        nik_invs = [i for i in non_pkp_invs if i["buyer_id_type"] == "NIK"]
        tin0_invs = [i for i in non_pkp_invs if i["buyer_id_type"] == "TIN_0"]
        self.assertGreater(len(nik_invs), 0)
        self.assertGreater(len(tin0_invs), 0)
        for i in nik_invs:
            self.assertTrue(i["customer_tax_id"].startswith("7171"))
        for i in tin0_invs:
            self.assertEqual(i["customer_tax_id"], "0000000000000000")

    def test_pmk131_tax_code_04_arithmetic_precision(self):
        """Memverifikasi presisi aritmetika PMK 131/2024: DPP Nilai Lain = 11/12 x komersial, PPN = 12% x DPP."""
        invoices = self.pack["invoices"]
        for inv in invoices:
            comm = Decimal(inv["commercial_dpp"])
            dpp = Decimal(inv["dpp_amount"])
            ppn = Decimal(inv["ppn_amount"])
            tot = Decimal(inv["total_invoice_with_ppn"])

            # 1. DPP Nilai Lain wajib 11/12 dari harga jual komersial netto
            expected_dpp = (comm * Decimal(11) / Decimal(12)).quantize(Decimal("0.01"))
            self.assertEqual(dpp, expected_dpp)

            # 2. PPN dihitung 12% atas DPP Nilai Lain
            expected_ppn = (dpp * Decimal("0.12")).quantize(Decimal("0.01"))
            self.assertEqual(ppn, expected_ppn)

            # 3. Total faktur komersial yang ditagih = komersial + PPN
            self.assertEqual(tot, comm + ppn)

            # 4. Rasio efektif PPN terhadap nilai komersial netto berada di 11% (toleransi 1 sen)
            effective_ppn_nominal = (comm * Decimal("0.11")).quantize(Decimal("0.01"))
            self.assertLessEqual(abs(ppn - effective_ppn_nominal), Decimal("0.02"))

    def test_line_discounts_and_promos(self):
        """Memverifikasi baris order memuat discount_pct, discount_dpp, line_net_dpp, dan promo selektif."""
        lines = self.pack["order_lines"]
        self.assertGreater(len(lines), 0)
        sample_line = lines[0]
        self.assertIn("discount_pct", sample_line)
        self.assertIn("discount_dpp", sample_line)
        self.assertIn("line_net_dpp", sample_line)
        self.assertIn("promo_id", sample_line)

        # Pastikan ada lini promo Mayora dan Santos yang terpicu secara deterministik
        promo_lines = [row for row in lines if row["promo_id"]]
        self.assertGreater(len(promo_lines), 0)

    def test_pod_rejection_reasons_and_evidence(self):
        """Memverifikasi tabel rejections memuat provenance simulasi jujur dan evidence terverifikasi."""
        rejections = self.pack["rejections"]
        self.assertGreater(len(rejections), 0)
        valid_reasons = {
            "KEMASAN_RUSAK_TRANSIT",
            "SEGEL_PABRIK_BOCOR",
            "EXPIRY_DEKAT_DITOLAK",
        }
        valid_evidence_types = {"SYNTHETIC", "NONE"}

        for r in rejections:
            self.assertIn("rejection_reason", r)
            self.assertIn("incident_batch_ref", r)
            self.assertIn("evidence_type", r)
            self.assertIn("evidence_photo_ref", r)
            self.assertIn(r["rejection_reason"], valid_reasons)
            self.assertIn(r["evidence_type"], valid_evidence_types)

            # Semantic consistency: Tolakan expiry tidak boleh dipasangkan dengan bukti kerusakan kardus
            if r["rejection_reason"] == "EXPIRY_DEKAT_DITOLAK":
                self.assertEqual(r["evidence_type"], "NONE")
                self.assertEqual(r["evidence_photo_ref"], "")

            # Bukti sintetis wajib ditandai SYNTHETIC dan file bukti fisik wajib ada di repositori
            if r["evidence_type"] == "SYNTHETIC":
                self.assertIn("synthetic", r["evidence_photo_ref"])
                photo_file = REPO_ROOT / r["evidence_photo_ref"]
                self.assertTrue(
                    photo_file.is_file(),
                    f"File bukti penolakan {r['evidence_photo_ref']} wajib tersedia secara fisik di git tree"
                )
                # Pastikan file non-kosong dan valid
                self.assertGreater(photo_file.stat().st_size, 100)

    def test_po_headers_input_vat(self):
        """Memverifikasi po_headers memuat tax_dpp 11/12, ppn_amount 12%, dan total_with_ppn."""
        pos = self.pack["po_headers"]
        self.assertGreater(len(pos), 0)
        for p in pos:
            self.assertIn("tax_dpp", p)
            self.assertIn("tax_code", p)
            self.assertIn("tax_rate", p)
            self.assertIn("ppn_amount", p)
            self.assertIn("total_with_ppn", p)
            self.assertEqual(p["tax_code"], "04")
            self.assertEqual(p["tax_rate"], "0.12")
            comm = Decimal(p["total_dpp"])
            tax_dpp = Decimal(p["tax_dpp"])
            ppn = Decimal(p["ppn_amount"])
            tot = Decimal(p["total_with_ppn"])
            expected_tax_dpp = (comm * Decimal(11) / Decimal(12)).quantize(Decimal("0.01"))
            expected_ppn = (expected_tax_dpp * Decimal("0.12")).quantize(Decimal("0.01"))
            self.assertEqual(tax_dpp, expected_tax_dpp)
            self.assertEqual(ppn, expected_ppn)
            self.assertEqual(tot, comm + ppn)

    def test_daily_logistics_metrics_and_ritase(self):
        """Memverifikasi tabel daily_logistics_metrics dan deteksi ritase ke-2 L300."""
        metrics = self.pack["daily_logistics_metrics"]
        self.assertGreater(len(metrics), 0)
        sample = metrics[0]
        self.assertIn("code", sample)
        self.assertTrue(sample["code"].startswith("DB "))
        self.assertIn("est_mileage_km", sample)

        # Cek adanya entri ritase ke-2 pada OPEX
        ritase_opex = [o for o in self.pack["opex"] if o["category"] == "Uang Jalan Ritase"]
        self.assertGreater(len(ritase_opex), 0)
        for o in ritase_opex:
            self.assertEqual(o["amount"], "100000.00")

    def test_warehouse_layout_simulation_in_closing_state(self):
        """Memverifikasi closing state memuat simulasi seksi gudang Maumbi dan 1.287 palet."""
        pack_dir = self.reg_dir / "periods" / "2026-08"
        closing_file = pack_dir / "closing_state_20260831.json"
        if closing_file.exists():
            with closing_file.open("r", encoding="utf-8") as f:
                closing = json.load(f)
            self.assertIn("warehouse_layout_simulation", closing)
            layout = closing["warehouse_layout_simulation"]
            self.assertEqual(layout["total_storage_pallets"], 1287)
            self.assertIn("GD-MND/UTAMA", layout["sections"])


if __name__ == "__main__":
    unittest.main()
