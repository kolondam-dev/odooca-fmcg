"""Offline counterexamples for the disposable FIN36 source/provenance spike."""

from datetime import date
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ops"))
import verify_finance_i2c_assets_spike as spike  # noqa: E402


class AssetSpikeOracleTest(unittest.TestCase):
    def setUp(self):
        self.company = object()
        self.expense = SimpleNamespace(id=3)
        self.contra = SimpleNamespace(id=4)
        self.asset = SimpleNamespace(company_id=self.company)
        self.move = SimpleNamespace(
            state="posted", company_id=self.company, date=date(2026, 7, 31),
            line_ids=[
                SimpleNamespace(account_id=self.expense, debit=33333.67,
                                credit=0.0, balance=33333.67),
                SimpleNamespace(account_id=self.contra, debit=0.0,
                                credit=33333.67, balance=-33333.67),
            ],
        )
        self.line = SimpleNamespace(
            move_id=self.move, move_check=True, type="depreciate",
            amount=33333.67, asset_id=self.asset, line_date=self.move.date,
        )

    def verify(self):
        spike.verify_posted_gl(self.move, self.line, self.expense, self.contra)

    def test_board_dates_order_and_remainder(self):
        spike.verify_board(spike.BOARD)
        for mutant in (
            spike.BOARD[::-1],
            spike.BOARD + [spike.BOARD[-1]],
            spike.BOARD[:2] + [("2026-10-31", 33333.0)],
            [spike.BOARD[0][:1] + (33332.67,),
             spike.BOARD[1][:1] + (33334.67,), spike.BOARD[2]],
        ):
            with self.subTest(mutant=mutant), self.assertRaisesRegex(
                AssertionError, "board mismatch",
            ):
                spike.verify_board(mutant)

    def test_posted_line_and_entire_journal(self):
        self.verify()
        self.move.state = "draft"
        with self.assertRaisesRegex(AssertionError, "not posted"):
            self.verify()
        self.move.state = "posted"
        self.move.line_ids.append(SimpleNamespace(
            account_id=SimpleNamespace(id=5), debit=1, credit=1, balance=0,
        ))
        with self.assertRaisesRegex(AssertionError, "GL posting mismatch"):
            self.verify()
        self.move.line_ids.pop()
        self.line.move_id = SimpleNamespace(id=99)
        with self.assertRaisesRegex(AssertionError, "provenance"):
            self.verify()

    def test_wrong_company_or_date_rejected(self):
        self.move.company_id = object()
        with self.assertRaisesRegex(AssertionError, "company"):
            self.verify()
        self.move.company_id = self.company
        self.move.date = date(2026, 8, 31)
        with self.assertRaisesRegex(AssertionError, "date"):
            self.verify()

    def test_every_period_amount_and_cutoff_coverage(self):
        from types import SimpleNamespace as Row

        second = Row(
            state="posted", company_id=self.company, date=date(2026, 8, 31),
            line_ids=[
                Row(account_id=self.expense, debit=33333.67, credit=0.0,
                    balance=33333.67),
                Row(account_id=self.contra, debit=0.0, credit=33333.67,
                    balance=-33333.67),
            ],
        )
        line2 = Row(move_id=second, move_check=True, type="depreciate",
                    amount=33333.67, asset_id=self.asset, line_date=second.date)
        # Stable IDs stand for ORM move IDs; the source does not supply the
        # expected totals or the actual posted AML list.
        self.move.id, second.id = 11, 12
        spike.verify_posted_gl(second, line2, self.expense, self.contra)

        def ledger_rows(moves):
            return [Row(move_id=move, **vars(row))
                    for move in moves for row in move.line_ids]

        source = [self.line, line2]
        rows = ledger_rows([self.move, second])
        spike.verify_cutoff_gl(rows, source, [33333.67, 33333.67],
                               self.expense, self.contra)
        for mutant in (rows[:-1], rows + rows[:2], rows + [Row(
            move_id=second, account_id=self.expense, debit=1.0,
            credit=1.0, balance=0.0,
        )]):
            with self.subTest(mutant=mutant), self.assertRaisesRegex(
                AssertionError, "cutoff GL coverage mismatch",
            ):
                spike.verify_cutoff_gl(mutant, source, [33333.67, 33333.67],
                                       self.expense, self.contra)
        line2.move_id = self.move
        with self.assertRaisesRegex(AssertionError, "reuse a journal move"):
            spike.verify_cutoff_gl(rows, source, [33333.67, 33333.67],
                                   self.expense, self.contra)


if __name__ == "__main__":
    unittest.main()
