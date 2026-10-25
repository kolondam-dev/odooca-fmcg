"""Pengujian Reproduksibilitas Lintas Proses Generator Transaksi.

Menjalankan generator transaksi perpetual dengan dua nilai PYTHONHASHSEED berbeda
(misal: PYTHONHASHSEED=1 dan PYTHONHASHSEED=2) pada subproses terpisah,
lalu memverifikasi bahwa seluruh file artefak di data/registers/ menghasilkan
checksum SHA256 yang identik 100%.
"""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
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


def compute_hashes():
    hashes = {}
    for filename in DATASETS:
        p = REG_DIR / filename
        hashes[filename] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


class GeneratorReproducibilityTests(unittest.TestCase):
    def test_cross_process_reproducibility(self):
        script_path = ROOT / "scripts" / "ops" / "generate_perpetual_transactions.py"

        # Jalankan proses 1 dengan PYTHONHASHSEED=1
        env1 = os.environ.copy()
        env1["PYTHONHASHSEED"] = "1"
        res1 = subprocess.run([sys.executable, str(script_path)], env=env1, capture_output=True, text=True)
        self.assertEqual(res1.returncode, 0, f"Process 1 failed: {res1.stderr}")
        hashes_seed1 = compute_hashes()

        # Jalankan proses 2 dengan PYTHONHASHSEED=2
        env2 = os.environ.copy()
        env2["PYTHONHASHSEED"] = "2"
        res2 = subprocess.run([sys.executable, str(script_path)], env=env2, capture_output=True, text=True)
        self.assertEqual(res2.returncode, 0, f"Process 2 failed: {res2.stderr}")
        hashes_seed2 = compute_hashes()

        # Bandingkan hash seluruh artefak
        for filename in DATASETS:
            self.assertEqual(
                hashes_seed1[filename],
                hashes_seed2[filename],
                f"Non-deterministic output detected in {filename} across different PYTHONHASHSEED!",
            )


if __name__ == "__main__":
    unittest.main()
