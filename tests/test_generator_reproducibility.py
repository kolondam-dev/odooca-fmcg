"""Pengujian Reproduksibilitas Lintas Proses Generator Transaksi.

Menjalankan generator transaksi perpetual dengan dua nilai PYTHONHASHSEED berbeda
(misal: PYTHONHASHSEED=1 dan PYTHONHASHSEED=2) pada subproses terpisah ke direktori
temporary terisolasi, lalu memverifikasi:
1. Hasil kedua subproses identik 100% (Determinisme).
2. Hasil generator identik 100% dengan committed snapshot di data/registers/ (Integritas Repo).
Semua perbandingan menggunakan normalisasi newline LF untuk portabilitas lintas OS.
"""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REG_DIR = ROOT / "data" / "registers"

DATASETS = [
    "perpetual_sales_orders.csv",
    "perpetual_sales_orders.json",
    "perpetual_order_lines.csv",
    "perpetual_order_lines.json",
    "perpetual_deliveries.csv",
    "perpetual_deliveries.json",
    "perpetual_order_rejections.csv",
    "perpetual_order_rejections.json",
    "perpetual_invoices.csv",
    "perpetual_invoices.json",
    "perpetual_ar_collections.csv",
    "perpetual_ar_collections.json",
    "perpetual_ap_payments.csv",
    "perpetual_ap_payments.json",
    "perpetual_opex_payroll.csv",
    "perpetual_opex_payroll.json",
    "perpetual_daily_stock_cards.csv",
    "perpetual_daily_stock_cards.json",
    "perpetual_stock_event_ledger.csv",
    "perpetual_stock_event_ledger.json",
]


def canonical_file_hash(path: Path) -> str:
    """Menghitung SHA-256 kanonikal dengan menormalisasi newline CRLF/CR ke LF."""
    data = path.read_bytes()
    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


class GeneratorReproducibilityTests(unittest.TestCase):
    def test_cross_process_reproducibility_and_snapshot_match(self):
        script_path = ROOT / "scripts" / "ops" / "generate_perpetual_transactions.py"

        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            dir1 = Path(tmp1)
            dir2 = Path(tmp2)

            # Jalankan proses 1 dengan PYTHONHASHSEED=1 ke tempdir 1
            env1 = os.environ.copy()
            env1["PYTHONHASHSEED"] = "1"
            res1 = subprocess.run(
                [sys.executable, str(script_path), "--output-dir", str(dir1)],
                env=env1,
                capture_output=True,
                text=True,
            )
            self.assertEqual(res1.returncode, 0, f"Process 1 failed: {res1.stderr}")

            # Jalankan proses 2 dengan PYTHONHASHSEED=2 ke tempdir 2
            env2 = os.environ.copy()
            env2["PYTHONHASHSEED"] = "2"
            res2 = subprocess.run(
                [sys.executable, str(script_path), "--output-dir", str(dir2)],
                env=env2,
                capture_output=True,
                text=True,
            )
            self.assertEqual(res2.returncode, 0, f"Process 2 failed: {res2.stderr}")

            # Bandingkan hash seluruh artefak antara tmp1, tmp2, dan committed snapshot di data/registers
            for filename in DATASETS:
                p1 = dir1 / filename
                p2 = dir2 / filename
                p_committed = REG_DIR / filename

                self.assertTrue(p1.exists(), f"File {filename} missing in process 1 output")
                self.assertTrue(p2.exists(), f"File {filename} missing in process 2 output")
                self.assertTrue(p_committed.exists(), f"File {filename} missing in committed repo")

                h1 = canonical_file_hash(p1)
                h2 = canonical_file_hash(p2)
                h_committed = canonical_file_hash(p_committed)

                self.assertEqual(
                    h1,
                    h2,
                    f"Non-deterministic output detected in {filename} across different PYTHONHASHSEED!",
                )
                self.assertEqual(
                    h1,
                    h_committed,
                    f"Drift detected between fresh generator output and committed snapshot in {filename}!",
                )


if __name__ == "__main__":
    unittest.main()
