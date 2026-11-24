#!/usr/bin/env python3
"""Disposable install/upgrade and posting proof for the FIN36 OCA source.

This is a technical prerequisite, not FIN36 acceptance.  It proves that the
pinned ``account_asset_management`` closure works in the project image and that
``account.asset.line`` retains an exact link to its posted depreciation move.
The fixture is created inside a savepoint and always rolled back.
"""

import json
from pathlib import Path
import sys

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent)
    if "__file__" in globals()
    else "/opt/scripts/ops",
)
import verify_finance_golden_ledger as golden  # noqa: E402


class RollbackAssetSpike(Exception):
    pass


def require(condition, message):
    if not condition:
        raise AssertionError(message)


BOARD = [
    ("2026-07-31", 33_333.67),
    ("2026-08-31", 33_333.67),
    ("2026-09-30", 33_333.66),
]


def verify_board(observed):
    """Pin dates, order, amounts and final remainder, not just the sum."""
    require(observed == BOARD, f"Asset depreciation board mismatch: {observed}")


def verify_posted_gl(move, first, expense, contra):
    """Tie one source line to its *posted* move and every journal line."""
    require(move.state == "posted", "Depreciation move is not posted")
    require(
        first.move_id == move and first.move_check and first.type == "depreciate",
        "Depreciation line lost posted move provenance",
    )
    expected_amount = dict(BOARD).get(first.line_date.isoformat())
    require(expected_amount is not None and first.amount == expected_amount,
            "Depreciation amount differs from board")
    gl = [(line.account_id.id, line.debit, line.credit, line.balance)
          for line in move.line_ids]
    expected = [
        (expense.id, expected_amount, 0.0, expected_amount),
        (contra.id, 0.0, expected_amount, -expected_amount),
    ]
    require(len(gl) == 2 and sorted(gl) == sorted(expected),
            f"Depreciation GL posting mismatch: {gl}")
    require(move.company_id == first.asset_id.company_id,
            "Depreciation journal company differs from asset")
    require(move.date == first.line_date,
            "Depreciation journal date differs from asset line")


def verify_cutoff_gl(lines, source, expected_amounts, expense, contra):
    """Reject missing, duplicated, or unrelated posted AML at each cutoff."""
    require(len(source) == len(expected_amounts),
            f"Depreciation source coverage mismatch: {len(source)}")
    require(len({line.move_id.id for line in source}) == len(source),
            "Depreciation sources reuse a journal move")
    expected = []
    for line, amount in zip(source, expected_amounts):
        require(line.move_id and line.amount == amount,
                "Depreciation source amount or posted move missing")
        expected.extend([
            (line.move_id.id, expense.id, amount, 0.0, amount),
            (line.move_id.id, contra.id, 0.0, amount, -amount),
        ])
    observed = [(row.move_id.id, row.account_id.id, row.debit,
                 row.credit, row.balance) for row in lines]
    require(len(observed) == len(expected) and sorted(observed) == sorted(expected),
            f"Depreciation cutoff GL coverage mismatch: {observed} != {expected}")


def run(env):
    require(
        env.cr.dbname == "finance_i0_assets_disposable",
        "FIN36 asset spike requires the exact disposable assets database",
    )

    installed = {
        row.name
        for row in env["ir.module.module"].search([
            ("name", "in", [
                "account_asset_management", "report_xlsx_helper", "account_asset",
            ]),
            ("state", "=", "installed"),
        ])
    }
    require(
        {"account_asset_management", "report_xlsx_helper"} <= installed,
        f"FIN36 OCA closure is incomplete: installed={sorted(installed)}",
    )
    require(
        "account_asset" not in installed,
        "Conflicting account_asset module must not be installed",
    )

    asset_fields = env["account.asset"]._fields
    line_fields = env["account.asset.line"]._fields
    require(
        {"purchase_value", "depreciation_line_ids", "value_residual"} <= set(asset_fields),
        "Pinned account.asset contract is incomplete",
    )
    require(
        {"type", "amount", "move_id", "move_check", "parent_state"} <= set(line_fields),
        "Pinned account.asset.line provenance contract is incomplete",
    )

    evidence = {
        "scope": "FIN36 OCA source install/upgrade and posting spike; not FIN36 acceptance",
        "module_closure": sorted(installed),
        "cases": [],
    }
    company_name = "FIN36 ASSET SPIKE"
    try:
        with env.cr.savepoint():
            company, accounts, journal, _partner, _scale = golden.build_fixture(
                env, "ASSET", 1, events=(), draft_noise=False,
            )
            company.name = company_name
            profile = env["account.asset.profile"].with_company(company).create({
                "name": "FIN36 disposable profile",
                "company_id": company.id,
                "account_asset_id": accounts["cash"].id,
                "account_depreciation_id": accounts["tax_input"].id,
                "account_expense_depreciation_id": accounts["expense"].id,
                "journal_id": journal.id,
                "method": "linear",
                "method_time": "number",
                "method_number": 3,
                "method_period": "month",
            })
            asset = env["account.asset"].with_company(company).create({
                "name": "FIN36 disposable asset",
                "code": "FIN36-SPIKE",
                "company_id": company.id,
                "profile_id": profile.id,
                "purchase_value": 100_001,
                "date_start": "2026-07-01",
            })

            create_lines = asset.depreciation_line_ids.filtered(
                lambda line: line.type == "create",
            )
            require(
                len(create_lines) == 1 and create_lines.amount == 100_001,
                "Asset depreciation base line mismatch (not an acquisition GL proof)",
            )
            require(not create_lines.move_id,
                    "Fixture base line unexpectedly linked to an acquisition journal")
            asset.compute_depreciation_board()
            asset.invalidate_recordset()
            depreciation = asset.depreciation_line_ids.filtered(
                lambda line: line.type == "depreciate",
            ).sorted(key=lambda line: (line.line_date, line.id))
            observed_board = [
                (line.line_date.isoformat(), line.amount) for line in depreciation
            ]
            verify_board(observed_board)
            require(
                company.currency_id.round(sum(depreciation.mapped("amount"))) == 100_001,
                "Asset depreciation board does not absorb its rounding remainder",
            )

            asset.validate()
            expected_residuals = (66_667.33, 33_333.66, 0.0)
            postings = []
            for index, line in enumerate(depreciation):
                move_ids = line.create_move()
                require(len(move_ids) == 1,
                        f"Expected one depreciation move for period {index}: {move_ids}")
                asset.invalidate_recordset()
                line.invalidate_recordset()
                move = env["account.move"].browse(move_ids[0])
                verify_posted_gl(move, line, accounts["expense"], accounts["tax_input"])
                require(
                    company.currency_id.round(sum(row.balance for row in move.line_ids)) == 0,
                    f"Depreciation journal {move.id} is unbalanced",
                )
                total = company.currency_id.round(sum(amount for _, amount in BOARD[:index + 1]))
                require(
                    asset.value_depreciated == total
                    and asset.value_residual == expected_residuals[index]
                    and asset.state == ("close" if index == 2 else "open"),
                    f"Period {index} posted/residual/state mismatch: {asset.read(['state', 'value_residual', 'value_depreciated'])}",
                )
                postings.append({"line_id": line.id, "move_id": move.id,
                                 "date": BOARD[index][0], "amount": line.amount})

            # Search the fixture's actual posted ledger, not only source-linked
            # moves: an unrelated or duplicate depreciation entry must fail.
            for index, (cutoff, _amount) in enumerate(BOARD):
                source = depreciation[:index + 1]
                aml = env["account.move.line"].with_company(company).search([
                    ("company_id", "=", company.id),
                    ("journal_id", "=", journal.id),
                    ("date", "<=", cutoff),
                    ("parent_state", "=", "posted"),
                    ("account_id", "in", [accounts["expense"].id,
                                          accounts["tax_input"].id]),
                ])
                verify_cutoff_gl(aml, source, [amount for _, amount in BOARD[:index + 1]],
                                 accounts["expense"], accounts["tax_input"])
            require(not asset.depreciation_line_ids.filtered(
                lambda line: line.type == "depreciate" and not line.move_check,
            ),
                "Unposted depreciation line remains after complete lifecycle")
            evidence["cases"].extend([
                {"case": "monthly_board_with_final_remainder", "result": "PASS",
                 "periods": observed_board},
                {"case": "all_posted_lines_to_gl_provenance", "result": "PASS",
                 "postings": postings},
                {"case": "posted_depreciation_gl_cutoffs", "result": "PASS",
                 "totals": [33_333.67, 66_667.34, 100_001.0],
                 "final_residual": 0.0},
            ])
            raise RollbackAssetSpike()
    except RollbackAssetSpike:
        env.invalidate_all()

    require(
        not env["res.company"].search_count([("name", "=", company_name)]),
        "FIN36 disposable fixture leaked after rollback",
    )
    evidence["fixture_rollback"] = "PASS"
    print("FINANCE_I2C_ASSETS_SPIKE=" + json.dumps(evidence, sort_keys=True))
    print("FINANCE_I2C_ASSETS_SPIKE=PASS")
    return evidence


if "env" in globals():
    run(globals()["env"])
