"""Regresi F4 (PR #110): scope cek DO done pada verifier runtime."""
import unittest
from pathlib import Path

VERIFIER = Path(__file__).resolve().parents[1] / "scripts" / "ops" / "verify_disposable_period_pack.py"


class TestVerifierDoScope(unittest.TestCase):
    def test_do_scope_uses_client_order_ref_not_picking_origin(self):
        """picking.origin berisi nama SO Odoo (S0xxxx); nomor SO pack ada di client_order_ref."""
        src = VERIFIER.read_text(encoding="utf-8")
        self.assertIn('("sale_id.client_order_ref", "=like", f"SO-{period_str}-%")', src)
        self.assertNotIn('("origin", "=like", f"SO-{period_str}-%")', src)


if __name__ == "__main__":
    unittest.main()
