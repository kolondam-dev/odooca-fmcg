"""Offline counterexamples for the disposable FIN36 lifecycle/register oracle."""

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

    def test_acquisition_requires_posted_bill_and_single_cost_line(self):
        currency = SimpleNamespace(round=lambda value: round(value, 2))
        cost = SimpleNamespace(id=7)
        payable = SimpleNamespace(id=8)
        revenue = SimpleNamespace(id=9)
        acquired_on = date(2026, 7, 1)
        cost_line = SimpleNamespace(
            account_id=cost, debit=100001.0, credit=0.0, balance=100001.0,
            date=acquired_on, move_id=None, parent_state="posted",
        )
        payable_line = SimpleNamespace(
            account_id=payable, debit=0.0, credit=100001.0, balance=-100001.0,
            date=acquired_on,
        )
        bill = SimpleNamespace(
            state="posted", move_type="in_invoice", company_id=self.company,
            currency_id=currency, name="BILL/2026/07/0001",
            date=acquired_on, invoice_date=acquired_on, partner_id=object(),
            journal_id=SimpleNamespace(type="purchase"),
            line_ids=[cost_line, payable_line],
        )
        cost_line.move_id = bill
        create = SimpleNamespace(
            type="create", move_id=bill, move_check=True, init_entry=True,
            amount=100001.0, line_date=acquired_on,
        )
        asset = SimpleNamespace(
            state="open", depreciation_line_ids=[create], purchase_value=100001.0,
            code=bill.name, date_start=acquired_on, partner_id=bill.partner_id,
            account_move_line_ids=[cost_line], company_id=self.company,
            currency_id=currency,
        )
        spike.verify_acquisition_gl(asset, bill, cost, payable)

        bill.state = "draft"
        with self.assertRaisesRegex(AssertionError, "posted vendor bill"):
            spike.verify_acquisition_gl(asset, bill, cost, payable)
        bill.state = "posted"
        bill.move_type = "entry"
        with self.assertRaisesRegex(AssertionError, "posted vendor bill"):
            spike.verify_acquisition_gl(asset, bill, cost, payable)
        bill.move_type = "in_invoice"

        bill.date = date(2026, 8, 31)
        with self.assertRaisesRegex(AssertionError, "bill date"):
            spike.verify_acquisition_gl(asset, bill, cost, payable)
        bill.date = acquired_on
        bill.invoice_date = date(2026, 8, 31)
        with self.assertRaisesRegex(AssertionError, "bill date"):
            spike.verify_acquisition_gl(asset, bill, cost, payable)
        bill.invoice_date = acquired_on

        bill.journal_id.type = "sale"
        with self.assertRaisesRegex(AssertionError, "purchase journal"):
            spike.verify_acquisition_gl(asset, bill, cost, payable)
        bill.journal_id.type = "purchase"

        payable_line.account_id = revenue
        with self.assertRaisesRegex(AssertionError, "credit payable exactly once"):
            spike.verify_acquisition_gl(asset, bill, cost, payable)
        payable_line.account_id = payable

        payable_line.credit = 99999.0
        payable_line.balance = -99999.0
        with self.assertRaisesRegex(AssertionError, "credit the payable"):
            spike.verify_acquisition_gl(asset, bill, cost, payable)
        payable_line.credit = 100001.0
        payable_line.balance = -100001.0

        payable_line.date = date(2026, 8, 31)
        with self.assertRaisesRegex(AssertionError, "payable line date"):
            spike.verify_acquisition_gl(asset, bill, cost, payable)
        payable_line.date = acquired_on

        cost_line.date = date(2026, 8, 31)
        with self.assertRaisesRegex(AssertionError, "Capitalizing bill line date"):
            spike.verify_acquisition_gl(asset, bill, cost, payable)
        cost_line.date = acquired_on

        create.move_id = None
        with self.assertRaisesRegex(AssertionError, "not linked to the posted bill"):
            spike.verify_acquisition_gl(asset, bill, cost, payable)
        create.move_id = bill

        cost_line.debit = 99999.0
        cost_line.balance = 99999.0
        with self.assertRaisesRegex(AssertionError, "full asset value"):
            spike.verify_acquisition_gl(asset, bill, cost, payable)
        cost_line.debit = 100001.0
        cost_line.balance = 100001.0

        asset.account_move_line_ids = [cost_line, cost_line]
        with self.assertRaisesRegex(AssertionError, "exactly one bill line"):
            spike.verify_acquisition_gl(asset, bill, cost, payable)
        asset.account_move_line_ids = [cost_line]

        asset.state = "draft"
        with self.assertRaisesRegex(AssertionError, "not validated"):
            spike.verify_acquisition_gl(asset, bill, cost, payable)

    def test_disposal_requires_posted_removal_journal(self):
        currency = SimpleNamespace(round=lambda value: round(value, 2))
        cost = SimpleNamespace(id=7)
        accumulated = SimpleNamespace(id=8)
        move = SimpleNamespace(
            state="posted", date=date(2026, 10, 31), company_id=self.company,
            journal_id=object(),
            line_ids=[
                SimpleNamespace(account_id=accumulated, debit=100001.0,
                                credit=0.0, balance=100001.0),
                SimpleNamespace(account_id=cost, debit=0.0, credit=100001.0,
                                balance=-100001.0),
            ],
        )
        removal = SimpleNamespace(
            type="remove", move_id=move, move_check=True, amount=0.0,
            line_date=move.date,
        )
        asset = SimpleNamespace(
            state="removed", date_remove=move.date, company_id=self.company,
            currency_id=currency,
            profile_id=SimpleNamespace(journal_id=move.journal_id),
            purchase_value=100001.0,
        )
        spike.verify_disposal_gl(asset, removal, move, cost, accumulated)

        move.state = "draft"
        with self.assertRaisesRegex(AssertionError, "not posted"):
            spike.verify_disposal_gl(asset, removal, move, cost, accumulated)
        move.state = "posted"

        removal.amount = 0.01
        with self.assertRaisesRegex(AssertionError, "zero residual"):
            spike.verify_disposal_gl(asset, removal, move, cost, accumulated)
        removal.amount = 0.0

        asset.state = "close"
        with self.assertRaisesRegex(AssertionError, "not removed"):
            spike.verify_disposal_gl(asset, removal, move, cost, accumulated)
        asset.state = "removed"

        move.line_ids.append(SimpleNamespace(
            account_id=accumulated, debit=1.0, credit=1.0, balance=0.0,
        ))
        with self.assertRaisesRegex(AssertionError, "GL posting mismatch"):
            spike.verify_disposal_gl(asset, removal, move, cost, accumulated)
        move.line_ids.pop()

        move.journal_id = object()
        with self.assertRaisesRegex(AssertionError, "profile journal"):
            spike.verify_disposal_gl(asset, removal, move, cost, accumulated)

    def test_early_disposal_requires_residual_sale_and_loss_gl(self):
        currency = SimpleNamespace(round=lambda value: round(value, 2))
        cost = SimpleNamespace(id=7)
        accumulated = SimpleNamespace(id=8)
        sale = SimpleNamespace(id=9)
        loss = SimpleNamespace(id=10)
        journal = object()
        removed_on = date(2026, 8, 16)
        move = SimpleNamespace(
            state="posted", date=removed_on, company_id=self.company,
            journal_id=journal,
            line_ids=[
                SimpleNamespace(
                    account_id=accumulated, debit=14838.71,
                    credit=0.0, balance=14838.71,
                ),
                SimpleNamespace(
                    account_id=cost, debit=0.0,
                    credit=120000.0, balance=-120000.0,
                ),
                SimpleNamespace(
                    account_id=sale, debit=100000.0,
                    credit=0.0, balance=100000.0,
                ),
                SimpleNamespace(
                    account_id=loss, debit=5161.29,
                    credit=0.0, balance=5161.29,
                ),
            ],
        )
        removal = SimpleNamespace(
            type="remove", move_id=move, move_check=True,
            amount=105161.29, line_date=removed_on,
        )
        asset = SimpleNamespace(
            state="removed", date_remove=removed_on, company_id=self.company,
            currency_id=currency,
            profile_id=SimpleNamespace(journal_id=journal),
        )
        spike.verify_early_disposal_gl(
            asset, removal, move, cost, accumulated, sale, loss,
        )

        removal.amount = 0.0
        with self.assertRaisesRegex(AssertionError, "residual/date mismatch"):
            spike.verify_early_disposal_gl(
                asset, removal, move, cost, accumulated, sale, loss,
            )
        removal.amount = 105161.29

        move.line_ids[-1].debit = 5160.29
        move.line_ids[-1].balance = 5160.29
        move.line_ids.append(SimpleNamespace(
            account_id=loss, debit=1.0, credit=0.0, balance=1.0,
        ))
        with self.assertRaisesRegex(AssertionError, "GL posting mismatch"):
            spike.verify_early_disposal_gl(
                asset, removal, move, cost, accumulated, sale, loss,
            )
        move.line_ids.pop()
        move.line_ids[-1].debit = 5161.29
        move.line_ids[-1].balance = 5161.29

        move.state = "draft"
        with self.assertRaisesRegex(AssertionError, "not posted"):
            spike.verify_early_disposal_gl(
                asset, removal, move, cost, accumulated, sale, loss,
            )

    def test_register_rollforward_rejects_balanced_bucket_tamper(self):
        currency = SimpleNamespace(round=lambda value: round(value, 2))
        expected = {
            "opening": 50000.0,
            "additions": 220001.0,
            "disposals": 105161.29,
            "depreciation": 124839.71,
            "closing": 40000.0,
        }
        spike.verify_register_rollforward(expected, dict(expected), currency)

        for bucket in ("opening", "additions", "disposals", "depreciation", "closing"):
            mutant = dict(expected)
            mutant[bucket] += 1.0
            with self.subTest(bucket=bucket), self.assertRaisesRegex(
                AssertionError, f"Register {bucket} source/GL mismatch",
            ):
                spike.verify_register_rollforward(expected, mutant, currency)

        # This mutation keeps the arithmetic equation closed but shifts one
        # unit from additions to depreciation. Per-bucket provenance must fail.
        balanced = dict(expected)
        balanced["additions"] += 1.0
        balanced["depreciation"] += 1.0
        with self.assertRaisesRegex(AssertionError, "Register additions"):
            spike.verify_register_rollforward(expected, balanced, currency)

        source_bad = dict(expected)
        source_bad["closing"] = 1.0
        with self.assertRaisesRegex(AssertionError, "source rollforward"):
            spike.verify_register_rollforward(source_bad, source_bad, currency)

    def test_population_row_excludes_draft_and_post_cutoff_sources(self):
        company = SimpleNamespace(id=41)
        asset = SimpleNamespace(id=51, company_id=company)

        def source(source_id, source_type, amount, source_date, posted=True):
            move = SimpleNamespace(
                id=source_id + 100,
                state="posted" if posted else "draft",
                date=source_date,
            )
            return SimpleNamespace(
                id=source_id,
                type=source_type,
                amount=amount,
                line_date=source_date,
                move_check=posted,
                move_id=move,
                asset_id=asset,
                company_id=company,
            )

        asset.depreciation_line_ids = [
            source(1, "create", 60_000.0, date(2026, 6, 1)),
            source(2, "depreciate", 10_000.0, date(2026, 6, 30)),
            source(3, "depreciate", 10_000.0, date(2026, 7, 31)),
            source(4, "depreciate", 10_000.0, date(2026, 8, 31), posted=False),
            source(5, "depreciate", 10_000.0, date(2026, 11, 30)),
            source(6, "remove", 40_000.0, date(2026, 11, 15)),
        ]
        row = spike.register_population_row(asset, "2026-07-01", "2026-10-31")
        self.assertEqual(
            {key: row[key] for key in spike.REGISTER_KEYS},
            {
                "opening": 50_000.0,
                "additions": 0.0,
                "disposals": 0.0,
                "depreciation": 10_000.0,
                "closing": 40_000.0,
            },
        )
        self.assertEqual(row["source_line_ids"], (1, 2, 3))

    def test_population_requires_exact_assets_company_and_unique_sources(self):
        currency = SimpleNamespace(round=lambda value: round(value, 2))
        expected = {
            11: {
                "opening": 50_000.0, "additions": 0.0,
                "disposals": 0.0, "depreciation": 10_000.0,
                "closing": 40_000.0, "source_count": 3,
            },
            12: {
                "opening": 0.0, "additions": 120_000.0,
                "disposals": 105_161.29, "depreciation": 14_838.71,
                "closing": 0.0, "source_count": 4,
            },
        }
        rows = [
            {
                "asset_id": 11, "company_id": 7,
                "opening": 50_000.0, "additions": 0.0,
                "disposals": 0.0, "depreciation": 10_000.0,
                "closing": 40_000.0,
                "source_line_ids": (1, 2, 3),
                "source_move_ids": (101, 102, 103),
            },
            {
                "asset_id": 12, "company_id": 7,
                "opening": 0.0, "additions": 120_000.0,
                "disposals": 105_161.29, "depreciation": 14_838.71,
                "closing": 0.0,
                "source_line_ids": (4, 5, 6, 7),
                "source_move_ids": (104, 105, 106, 107),
            },
        ]
        totals = spike.verify_register_population(rows, expected, 7, currency)
        self.assertEqual(totals["closing"], 40_000.0)

        with self.assertRaisesRegex(AssertionError, "coverage mismatch"):
            spike.verify_register_population(rows[:1], expected, 7, currency)
        with self.assertRaisesRegex(AssertionError, "duplicate assets"):
            spike.verify_register_population(rows + [dict(rows[0])], expected, 7, currency)

        cross_company = [dict(row) for row in rows]
        cross_company[1]["company_id"] = 8
        with self.assertRaisesRegex(AssertionError, "crosses company"):
            spike.verify_register_population(cross_company, expected, 7, currency)

        reused = [dict(row) for row in rows]
        reused[1]["source_line_ids"] = (3, 5, 6, 7)
        with self.assertRaisesRegex(AssertionError, "reuses a source line"):
            spike.verify_register_population(reused, expected, 7, currency)

    def test_population_rejects_correct_aggregate_with_wrong_asset_composition(self):
        currency = SimpleNamespace(round=lambda value: round(value, 2))
        expected = {
            11: {
                "opening": 50.0, "additions": 0.0, "disposals": 0.0,
                "depreciation": 10.0, "closing": 40.0, "source_count": 1,
            },
            12: {
                "opening": 0.0, "additions": 100.0, "disposals": 20.0,
                "depreciation": 30.0, "closing": 50.0, "source_count": 1,
            },
        }
        rows = [
            {
                "asset_id": 11, "company_id": 7,
                "opening": 50.0, "additions": 1.0, "disposals": 0.0,
                "depreciation": 11.0, "closing": 40.0,
                "source_line_ids": (1,), "source_move_ids": (101,),
            },
            {
                "asset_id": 12, "company_id": 7,
                "opening": 0.0, "additions": 99.0, "disposals": 20.0,
                "depreciation": 29.0, "closing": 50.0,
                "source_line_ids": (2,), "source_move_ids": (102,),
            },
        ]
        # Aggregate additions/depreciation and both closing values still match.
        with self.assertRaisesRegex(AssertionError, "asset 11 additions mismatch"):
            spike.verify_register_population(rows, expected, 7, currency)


if __name__ == "__main__":
    unittest.main()
