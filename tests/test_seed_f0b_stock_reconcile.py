import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ops"))
import seed_f0b_stock_reconcile_live as f0b  # noqa: E402


def _canon_rows(canon, carton):
    return [(s, lot, q * carton[s]) for (s, lot), q in canon.items()]


class F0bTests(unittest.TestCase):
    def setUp(self):
        import json

        self.canon = f0b.canonical_available(json.loads(f0b.STATE.read_text(encoding="utf-8")))
        self.carton = f0b.carton_sizes()

    def test_canonical_total_matches_state(self):
        self.assertEqual(sum(self.canon.values()), 52799)
        self.assertEqual(len(self.canon), 236)

    def test_identical_live_has_no_diff(self):
        r = f0b.compare(_canon_rows(self.canon, self.carton), self.canon, self.carton)
        self.assertEqual(r["lot_diffs_count"], 0)
        self.assertFalse(r["hypothesis_100x150_proven"])

    def test_lotless_100_per_sku_proves_hypothesis(self):
        rows = _canon_rows(self.canon, self.carton)
        rows += [(s, None, 100 * c) for s, c in self.carton.items()]
        r = f0b.compare(rows, self.canon, self.carton)
        self.assertTrue(r["hypothesis_100x150_proven"])
        self.assertEqual(r["per_sku_diff_total"], "15000")

    def test_100_in_existing_lots_counts_as_per_sku(self):
        rows = _canon_rows(self.canon, self.carton)
        first = {}
        for i, (s, lot, q) in enumerate(rows):
            first.setdefault(s, i)
        for s, i in first.items():
            rows[i] = (rows[i][0], rows[i][1], rows[i][2] + 100 * self.carton[s])
        r = f0b.compare(rows, self.canon, self.carton)
        self.assertTrue(r["hypothesis_100x150_proven"])

    def test_partial_or_uneven_is_not_proven(self):
        rows = _canon_rows(self.canon, self.carton)
        s = next(iter(self.carton))
        rows.append((s, None, 99 * self.carton[s]))
        r = f0b.compare(rows, self.canon, self.carton)
        self.assertFalse(r["hypothesis_100x150_proven"])


if __name__ == "__main__":
    unittest.main()
