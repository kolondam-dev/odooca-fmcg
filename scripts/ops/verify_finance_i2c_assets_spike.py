#!/usr/bin/env python3
"""Disposable lifecycle and register-rollforward proof for the FIN36 OCA source.

This is a technical prerequisite, not FIN36 acceptance.  It proves that the
pinned ``account_asset_management`` closure works in the project image and that
``account.asset.line`` retains an exact link to the posted move that created it
(acquisition), to every posted depreciation journal, and to the posted removal
journal.  A non-zero opening/closing asset and an early disposal additionally
reconcile the asset-source rollforward to independently queried posted GL.
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
ACQUISITION_DATE = "2026-07-01"
ACQUISITION_VALUE = 100_001.0
REMOVAL_DATE = "2026-10-31"
EARLY_ACQUISITION_VALUE = 120_000.0
EARLY_REMOVAL_DATE = "2026-08-16"
EARLY_REGULAR_DEPRECIATION = 10_000.0
EARLY_PARTIAL_DEPRECIATION = 4_838.71
EARLY_ACCUMULATED_DEPRECIATION = 14_838.71
EARLY_RESIDUAL_VALUE = 105_161.29
EARLY_SALE_VALUE = 100_000.0
EARLY_LOSS_VALUE = 5_161.29
OPENING_ACQUISITION_DATE = "2026-06-01"
OPENING_ACQUISITION_VALUE = 60_000.0
OPENING_MONTHLY_DEPRECIATION = 10_000.0


def verify_board(observed):
    """Pin dates, order, amounts and final remainder, not just the sum."""
    require(observed == BOARD, f"Asset depreciation board mismatch: {observed}")


def verify_depreciation_gl(move, first, expected_amount, expense, contra):
    """Tie one depreciation source line to its posted move and complete GL."""
    require(move.state == "posted", "Depreciation move is not posted")
    require(
        first.move_id == move and first.move_check and first.type == "depreciate",
        "Depreciation line lost posted move provenance",
    )
    require(first.amount == expected_amount, "Depreciation amount differs from board")
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


def verify_posted_gl(move, first, expense, contra):
    """Tie one standard-board source line to its posted move and complete GL."""
    expected_amount = dict(BOARD).get(first.line_date.isoformat())
    require(expected_amount is not None, "Depreciation date is outside the board")
    verify_depreciation_gl(move, first, expected_amount, expense, contra)


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


def verify_acquisition_gl(
    asset,
    bill,
    cost_account,
    payable_account,
    expected_value=ACQUISITION_VALUE,
    expected_date=ACQUISITION_DATE,
):
    """Tie the acquisition base line to a posted bill that capitalized it."""
    require(
        bill.state == "posted" and bill.move_type == "in_invoice",
        "Acquisition is not a posted vendor bill",
    )
    require(
        str(bill.date) == expected_date
        and str(bill.invoice_date) == expected_date,
        f"Acquisition bill date differs from {expected_date}",
    )
    require(
        bill.journal_id.type == "purchase",
        "Acquisition bill journal is not a purchase journal",
    )
    require(
        asset.state in ("open", "close"),
        f"Acquisition asset is not validated: {asset.state}",
    )
    create = [line for line in asset.depreciation_line_ids if line.type == "create"]
    require(len(create) == 1, f"Expected one acquisition base line: {create}")
    create = create[0]
    require(
        create.move_id == bill and create.init_entry,
        "Acquisition base line is not linked to the posted bill",
    )
    require(
        create.amount == asset.purchase_value == expected_value,
        "Acquisition base amount differs from the bill value",
    )
    require(
        str(create.line_date) == expected_date,
        "Acquisition base date differs from the bill date",
    )
    require(
        asset.code == bill.name and str(asset.date_start) == expected_date,
        "Asset identity/start date does not follow the acquisition bill",
    )
    require(
        asset.partner_id == bill.partner_id,
        "Acquisition asset partner differs from the bill",
    )
    linked = asset.account_move_line_ids
    require(
        len(linked) == 1,
        f"Asset is not capitalized by exactly one bill line: {linked}",
    )
    linked = linked[0]
    require(
        linked.move_id == bill,
        "Capitalizing bill line does not belong to the acquisition bill",
    )
    require(
        linked.parent_state == "posted" and linked.account_id == cost_account,
        "Acquisition bill line is not posted on the asset cost account",
    )
    require(
        linked.debit == expected_value
        and linked.credit == 0.0
        and linked.balance == expected_value,
        "Acquisition bill line does not debit the full asset value",
    )
    require(
        str(linked.date) == expected_date,
        "Capitalizing bill line date differs from the acquisition date",
    )
    lines = list(bill.line_ids)
    require(
        len(lines) == 2,
        f"Acquisition bill must have exactly two lines: {lines}",
    )
    cost_lines = [line for line in lines if line.account_id == cost_account]
    payable_lines = [line for line in lines if line.account_id == payable_account]
    require(
        len(cost_lines) == 1 and len(payable_lines) == 1,
        "Acquisition bill must debit cost and credit payable exactly once",
    )
    require(
        linked == cost_lines[0],
        "Asset capitalization line is not the bill's cost line",
    )
    payable = payable_lines[0]
    require(
        payable.debit == 0.0
        and payable.credit == expected_value
        and payable.balance == -expected_value,
        "Acquisition bill does not credit the payable for the full value",
    )
    require(
        str(payable.date) == expected_date,
        "Acquisition payable line date differs from the acquisition date",
    )
    require(
        bill.company_id == asset.company_id
        and bill.currency_id == asset.currency_id,
        "Acquisition bill company/currency differs from the asset",
    )
    require(
        bill.currency_id.round(sum(line.balance for line in lines)) == 0,
        f"Acquisition bill is not a balanced two-line journal: {lines}",
    )


def verify_disposal_gl(asset, removal, move, cost_account, accumulated_account):
    """Require the removal wizard's draft journal to be posted in full."""
    require(
        asset.state == "removed" and str(asset.date_remove) == REMOVAL_DATE,
        f"Asset is not removed on {REMOVAL_DATE}: {asset.state} / {asset.date_remove}",
    )
    require(
        removal.type == "remove" and removal.move_id == move and removal.move_check,
        "Removal line is not linked to its journal entry",
    )
    require(
        removal.amount == 0.0 and str(removal.line_date) == REMOVAL_DATE,
        "Removal line does not carry the zero residual on the removal date",
    )
    require(move.state == "posted", "Removal journal entry is not posted")
    require(
        str(move.date) == REMOVAL_DATE, "Removal journal date differs from the wizard"
    )
    require(
        move.company_id == asset.company_id,
        "Removal journal company differs from the asset",
    )
    require(
        move.journal_id == asset.profile_id.journal_id,
        "Removal journal differs from the asset profile journal",
    )
    gl = [
        (line.account_id.id, line.debit, line.credit, line.balance)
        for line in move.line_ids
    ]
    expected = [
        (accumulated_account.id, ACQUISITION_VALUE, 0.0, ACQUISITION_VALUE),
        (cost_account.id, 0.0, ACQUISITION_VALUE, -ACQUISITION_VALUE),
    ]
    require(
        len(gl) == 2 and sorted(gl) == sorted(expected),
        f"Removal GL posting mismatch: {gl}",
    )
    require(
        asset.currency_id.round(sum(line.balance for line in move.line_ids)) == 0,
        "Removal journal entry is unbalanced",
    )


def verify_early_disposal_gl(
    asset,
    removal,
    move,
    cost_account,
    accumulated_account,
    sale_account,
    loss_account,
):
    """Tie an early removal with residual value and loss to its complete GL."""
    require(
        asset.state == "removed" and str(asset.date_remove) == EARLY_REMOVAL_DATE,
        "Early-disposal asset state/date mismatch",
    )
    require(
        removal.type == "remove" and removal.move_id == move and removal.move_check,
        "Early-removal line lost posted move provenance",
    )
    require(
        removal.amount == EARLY_RESIDUAL_VALUE
        and str(removal.line_date) == EARLY_REMOVAL_DATE,
        "Early-removal line residual/date mismatch",
    )
    require(move.state == "posted", "Early-removal journal entry is not posted")
    require(
        str(move.date) == EARLY_REMOVAL_DATE
        and move.company_id == asset.company_id
        and move.journal_id == asset.profile_id.journal_id,
        "Early-removal journal date/company/profile journal mismatch",
    )
    gl = [
        (line.account_id.id, line.debit, line.credit, line.balance)
        for line in move.line_ids
    ]
    expected = [
        (
            accumulated_account.id,
            EARLY_ACCUMULATED_DEPRECIATION,
            0.0,
            EARLY_ACCUMULATED_DEPRECIATION,
        ),
        (
            cost_account.id,
            0.0,
            EARLY_ACQUISITION_VALUE,
            -EARLY_ACQUISITION_VALUE,
        ),
        (sale_account.id, EARLY_SALE_VALUE, 0.0, EARLY_SALE_VALUE),
        (loss_account.id, EARLY_LOSS_VALUE, 0.0, EARLY_LOSS_VALUE),
    ]
    require(
        len(gl) == 4 and sorted(gl) == sorted(expected),
        f"Early-removal GL posting mismatch: {gl}",
    )
    require(
        asset.currency_id.round(sum(line.balance for line in move.line_ids)) == 0,
        "Early-removal journal entry is unbalanced",
    )


def verify_register_rollforward(source, gl, currency):
    """Reconcile independently-derived source and GL rollforward buckets."""
    keys = ("opening", "additions", "disposals", "depreciation", "closing")
    require(set(source) == set(keys), f"Register source buckets mismatch: {source}")
    require(set(gl) == set(keys), f"Register GL buckets mismatch: {gl}")
    for key in keys:
        require(
            currency.round(source[key]) == currency.round(gl[key]),
            f"Register {key} source/GL mismatch: {source[key]} != {gl[key]}",
        )
    source_equation = currency.round(
        source["opening"]
        + source["additions"]
        - source["disposals"]
        - source["depreciation"]
    )
    gl_equation = currency.round(
        gl["opening"] + gl["additions"] - gl["disposals"] - gl["depreciation"]
    )
    require(
        source_equation == currency.round(source["closing"]),
        f"Register source rollforward does not close: {source_equation}",
    )
    require(
        gl_equation == currency.round(gl["closing"]),
        f"Register GL rollforward does not close: {gl_equation}",
    )


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
        "scope": (
            "FIN36 OCA lifecycle/register rollforward spike; "
            "not FIN36 acceptance"
        ),
        "module_closure": sorted(installed),
        "cases": [],
    }
    company_name = "FIN36 ASSET SPIKE"
    try:
        with env.cr.savepoint():
            company, accounts, journal, partner, _scale = golden.build_fixture(
                env, "ASSET", 1, events=(), draft_noise=False,
            )
            company.name = company_name
            partner.with_company(company).write({
                "property_account_receivable_id": accounts["ar"].id,
                "property_account_payable_id": accounts["ap"].id,
            })
            cost_account = env["account.account"].with_company(company).create({
                "name": "FIN36 asset cost", "code": "F36AC",
                "account_type": "asset_fixed",
                "company_ids": [(6, 0, company.ids)],
            })
            purchase_journal = env["account.journal"].with_company(company).create({
                "name": "FIN36 purchase", "code": "F36P",
                "type": "purchase", "company_id": company.id,
            })
            profile = env["account.asset.profile"].with_company(company).create({
                "name": "FIN36 disposable profile",
                "company_id": company.id,
                "account_asset_id": cost_account.id,
                "account_depreciation_id": accounts["tax_input"].id,
                "account_expense_depreciation_id": accounts["expense"].id,
                "journal_id": journal.id,
                "method": "linear",
                "method_time": "number",
                "method_number": 3,
                "method_period": "month",
            })
            bill = env["account.move"].with_company(company).create({
                "move_type": "in_invoice",
                "partner_id": partner.id,
                "invoice_date": ACQUISITION_DATE,
                "date": ACQUISITION_DATE,
                "journal_id": purchase_journal.id,
                "invoice_line_ids": [(0, 0, {
                    "name": "FIN36 disposable acquisition",
                    "account_id": cost_account.id,
                    "quantity": 1.0,
                    "price_unit": ACQUISITION_VALUE,
                })],
            })
            bill.invoice_line_ids.write({"asset_profile_id": profile.id})
            bill.action_post()

            created = env["account.asset"].with_company(company).search([
                ("company_id", "=", company.id),
                ("profile_id", "=", profile.id),
            ])
            require(len(created) == 1,
                    f"Posting the acquisition bill must create exactly one asset: {created}")
            asset = created
            asset.validate()
            asset.invalidate_recordset()
            verify_acquisition_gl(asset, bill, cost_account, accounts["ap"])

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
            require(asset.state == "close" and asset.value_residual == 0.0,
                    "Asset must be fully depreciated before disposal")

            # Disposal: the OCA wizard only creates a draft journal, so the
            # oracle must post it and tie the removal line to the posted GL.
            action = asset.remove()
            require("early_removal" not in action["context"],
                    "Fully depreciated asset must be removed without early removal")
            wizard = env["account.asset.remove"].with_company(company).with_context(
                **action["context"],
            ).create({
                "date_remove": REMOVAL_DATE,
                "posting_regime": "residual_value",
                "company_id": company.id,
            })
            wizard.remove()
            asset.invalidate_recordset()
            removal = asset.depreciation_line_ids.filtered(
                lambda line: line.type == "remove",
            )
            require(len(removal) == 1,
                    f"Expected one removal line after disposal: {removal}")
            removal_move = removal.move_id
            require(removal_move.state == "draft",
                    "OCA removal wizard is expected to leave its journal in draft")
            removal_move.with_context(
                allow_asset=True, allow_asset_removal=True,
            ).action_post()
            asset.invalidate_recordset()
            removal.invalidate_recordset()
            removal_move.invalidate_recordset()
            verify_disposal_gl(
                asset, removal, removal_move, cost_account, accounts["tax_input"],
            )

            # A third asset provides a non-zero opening and closing net book
            # value. Its June acquisition and depreciation precede the report
            # period; only July depreciation is a period movement.
            opening_profile = env["account.asset.profile"].with_company(company).create({
                "name": "FIN36 opening-balance profile",
                "company_id": company.id,
                "account_asset_id": cost_account.id,
                "account_depreciation_id": accounts["tax_input"].id,
                "account_expense_depreciation_id": accounts["expense"].id,
                "journal_id": journal.id,
                "method": "linear",
                "method_time": "number",
                "method_number": 6,
                "method_period": "month",
            })
            opening_bill = env["account.move"].with_company(company).create({
                "move_type": "in_invoice",
                "partner_id": partner.id,
                "invoice_date": OPENING_ACQUISITION_DATE,
                "date": OPENING_ACQUISITION_DATE,
                "journal_id": purchase_journal.id,
                "invoice_line_ids": [(0, 0, {
                    "name": "FIN36 opening-balance acquisition",
                    "account_id": cost_account.id,
                    "quantity": 1.0,
                    "price_unit": OPENING_ACQUISITION_VALUE,
                })],
            })
            opening_bill.invoice_line_ids.write({
                "asset_profile_id": opening_profile.id,
            })
            opening_bill.action_post()
            opening_assets = env["account.asset"].with_company(company).search([
                ("company_id", "=", company.id),
                ("profile_id", "=", opening_profile.id),
            ])
            require(
                len(opening_assets) == 1,
                f"Opening bill must create exactly one asset: {opening_assets}",
            )
            opening_asset = opening_assets
            opening_asset.validate()
            opening_asset.invalidate_recordset()
            verify_acquisition_gl(
                opening_asset,
                opening_bill,
                cost_account,
                accounts["ap"],
                expected_value=OPENING_ACQUISITION_VALUE,
                expected_date=OPENING_ACQUISITION_DATE,
            )
            opening_board = opening_asset.depreciation_line_ids.filtered(
                lambda line: line.type == "depreciate",
            ).sorted(key=lambda line: (line.line_date, line.id))
            require(
                len(opening_board) == 6
                and [line.amount for line in opening_board[:2]]
                == [OPENING_MONTHLY_DEPRECIATION] * 2
                and [str(line.line_date) for line in opening_board[:2]]
                == ["2026-06-30", "2026-07-31"],
                f"Opening asset board mismatch: {opening_board[:2]}",
            )
            for opening_line in opening_board[:2]:
                opening_move_ids = opening_line.create_move()
                require(
                    len(opening_move_ids) == 1,
                    "Expected one posted move per opening-asset depreciation",
                )
                opening_line.invalidate_recordset()
                verify_depreciation_gl(
                    opening_line.move_id,
                    opening_line,
                    OPENING_MONTHLY_DEPRECIATION,
                    accounts["expense"],
                    accounts["tax_input"],
                )
            opening_asset.invalidate_recordset()
            require(
                opening_asset.value_residual == 40_000.0,
                "Opening asset must retain 40,000 closing net book value",
            )

            # A zero-residual removal cannot prove how an in-period disposal
            # affects net book value.  Create a second asset with a 12-month
            # board, post July, then remove it mid-August for less than its
            # residual value.  OCA must post the prorated final depreciation
            # and preserve the residual/loss in the separate removal journal.
            early_profile = env["account.asset.profile"].with_company(company).create({
                "name": "FIN36 early-disposal profile",
                "company_id": company.id,
                "account_asset_id": cost_account.id,
                "account_depreciation_id": accounts["tax_input"].id,
                "account_expense_depreciation_id": accounts["expense"].id,
                "journal_id": journal.id,
                "method": "linear",
                "method_time": "number",
                "method_number": 12,
                "method_period": "month",
            })
            early_bill = env["account.move"].with_company(company).create({
                "move_type": "in_invoice",
                "partner_id": partner.id,
                "invoice_date": ACQUISITION_DATE,
                "date": ACQUISITION_DATE,
                "journal_id": purchase_journal.id,
                "invoice_line_ids": [(0, 0, {
                    "name": "FIN36 early-disposal acquisition",
                    "account_id": cost_account.id,
                    "quantity": 1.0,
                    "price_unit": EARLY_ACQUISITION_VALUE,
                })],
            })
            early_bill.invoice_line_ids.write({"asset_profile_id": early_profile.id})
            early_bill.action_post()
            early_assets = env["account.asset"].with_company(company).search([
                ("company_id", "=", company.id),
                ("profile_id", "=", early_profile.id),
            ])
            require(
                len(early_assets) == 1,
                f"Early-disposal bill must create exactly one asset: {early_assets}",
            )
            early_asset = early_assets
            early_asset.validate()
            early_asset.invalidate_recordset()
            verify_acquisition_gl(
                early_asset,
                early_bill,
                cost_account,
                accounts["ap"],
                expected_value=EARLY_ACQUISITION_VALUE,
            )
            early_board = early_asset.depreciation_line_ids.filtered(
                lambda line: line.type == "depreciate",
            ).sorted(key=lambda line: (line.line_date, line.id))
            require(
                len(early_board) == 12
                and early_board[0].amount == EARLY_REGULAR_DEPRECIATION
                and str(early_board[0].line_date) == "2026-07-31",
                f"Early-disposal board first period mismatch: {early_board[:1]}",
            )
            july_move_ids = early_board[0].create_move()
            require(len(july_move_ids) == 1, "Expected one July depreciation move")
            early_asset.invalidate_recordset()
            require(
                early_asset.value_residual == 110_000.0,
                "Early-disposal asset residual after July must be 110,000",
            )

            early_action = early_asset.remove()
            require(
                early_action["context"].get("early_removal") is True,
                "Open asset removal must enter the early-removal path",
            )
            early_wizard = (
                env["account.asset.remove"]
                .with_company(company)
                .with_context(**early_action["context"])
                .create({
                    "date_remove": EARLY_REMOVAL_DATE,
                    "sale_value": EARLY_SALE_VALUE,
                    "posting_regime": "gain_loss_on_sale",
                    "account_sale_id": accounts["cash"].id,
                    "account_plus_value_id": accounts["revenue"].id,
                    "account_min_value_id": accounts["expense"].id,
                    "company_id": company.id,
                })
            )
            early_wizard.remove()
            early_asset.invalidate_recordset()
            early_depreciation = early_asset.depreciation_line_ids.filtered(
                lambda line: line.type == "depreciate",
            ).sorted(key=lambda line: (line.line_date, line.id))
            require(
                len(early_depreciation) == 2
                and [line.amount for line in early_depreciation]
                == [EARLY_REGULAR_DEPRECIATION, EARLY_PARTIAL_DEPRECIATION]
                and [str(line.line_date) for line in early_depreciation]
                == ["2026-07-31", "2026-08-15"]
                and all(line.move_check for line in early_depreciation),
                f"Early-removal prorated depreciation mismatch: {early_depreciation}",
            )
            for early_line, expected_amount in zip(
                early_depreciation,
                [EARLY_REGULAR_DEPRECIATION, EARLY_PARTIAL_DEPRECIATION],
            ):
                verify_depreciation_gl(
                    early_line.move_id,
                    early_line,
                    expected_amount,
                    accounts["expense"],
                    accounts["tax_input"],
                )
            early_removal = early_asset.depreciation_line_ids.filtered(
                lambda line: line.type == "remove",
            )
            require(len(early_removal) == 1, "Expected one early-removal line")
            early_removal_move = early_removal.move_id
            require(
                early_removal_move.state == "draft",
                "Early-removal wizard must leave the removal journal in draft",
            )
            early_removal_move.with_context(
                allow_asset=True, allow_asset_removal=True,
            ).action_post()
            early_asset.invalidate_recordset()
            early_removal.invalidate_recordset()
            early_removal_move.invalidate_recordset()
            verify_early_disposal_gl(
                early_asset,
                early_removal,
                early_removal_move,
                cost_account,
                accounts["tax_input"],
                accounts["cash"],
                accounts["expense"],
            )

            period_start, period_end = "2026-07-01", REMOVAL_DATE
            fixture_assets = asset | early_asset | opening_asset
            fixture_lines = fixture_assets.depreciation_line_ids
            before_period = fixture_lines.filtered(
                lambda line: line.move_check and str(line.line_date) < period_start,
            )
            create_in_period = fixture_lines.filtered(
                lambda line: line.type == "create"
                and period_start <= str(line.line_date) <= period_end,
            )
            depreciation_in_period = fixture_lines.filtered(
                lambda line: line.type == "depreciate"
                and line.move_check
                and period_start <= str(line.line_date) <= period_end,
            )
            removals_in_period = fixture_lines.filtered(
                lambda line: line.type == "remove"
                and line.move_check
                and period_start <= str(line.line_date) <= period_end,
            )
            require(
                len(create_in_period) == 2
                and all(
                    line.move_id.state == "posted"
                    and line.move_id.move_type == "in_invoice"
                    and line.move_id.date == line.line_date
                    and line.asset_id.company_id == company
                    for line in create_in_period
                ),
                "Register additions lost posted bill/date/company provenance",
            )
            require(
                len(depreciation_in_period) == 6
                and all(
                    line.move_id.state == "posted"
                    and line.move_id.date == line.line_date
                    and line.asset_id.company_id == company
                    for line in depreciation_in_period
                ),
                "Register depreciation lost posted move/date/company provenance",
            )
            require(
                len(removals_in_period) == 2
                and all(
                    line.move_id.state == "posted"
                    and line.move_id.date == line.line_date
                    and line.asset_id.company_id == company
                    for line in removals_in_period
                ),
                "Register disposals lost posted move/date/company provenance",
            )
            source_rollforward = {
                "opening": company.currency_id.round(
                    sum(
                        line.amount if line.type == "create" else -line.amount
                        for line in before_period
                        if line.type in ("create", "depreciate", "remove")
                    ),
                ),
                "additions": company.currency_id.round(
                    sum(create_in_period.mapped("amount")),
                ),
                "disposals": company.currency_id.round(
                    sum(removals_in_period.mapped("amount")),
                ),
                "depreciation": company.currency_id.round(
                    sum(depreciation_in_period.mapped("amount")),
                ),
                "closing": company.currency_id.round(
                    sum(fixture_assets.mapped("value_residual")),
                ),
            }
            account_domain = [
                ("company_id", "=", company.id),
                ("parent_state", "=", "posted"),
                ("account_id", "in", [cost_account.id, accounts["tax_input"].id]),
            ]
            opening_aml = env["account.move.line"].with_company(company).search(
                account_domain + [("date", "<", period_start)],
            )
            posted_aml = env["account.move.line"].with_company(company).search([
                *account_domain,
                ("date", ">=", period_start),
                ("date", "<=", period_end),
            ])
            closing_aml = env["account.move.line"].with_company(company).search(
                account_domain + [("date", "<=", period_end)],
            )
            cost_rows = posted_aml.filtered(lambda row: row.account_id == cost_account)
            accumulated_rows = posted_aml.filtered(
                lambda row: row.account_id == accounts["tax_input"],
            )
            gl_rollforward = {
                "opening": sum(opening_aml.mapped("balance")),
                "additions": sum(cost_rows.mapped("debit")),
                "disposals": sum(cost_rows.mapped("credit"))
                - sum(accumulated_rows.mapped("debit")),
                "depreciation": sum(accumulated_rows.mapped("credit")),
                "closing": sum(closing_aml.mapped("balance")),
            }
            expected_rollforward = {
                "opening": 50_000.0,
                "additions": 220_001.0,
                "disposals": EARLY_RESIDUAL_VALUE,
                "depreciation": 124_839.71,
                "closing": 40_000.0,
            }
            require(
                source_rollforward == expected_rollforward,
                f"Register source expected values mismatch: {source_rollforward}",
            )
            verify_register_rollforward(
                source_rollforward, gl_rollforward, company.currency_id,
            )

            evidence["cases"].extend([
                {"case": "monthly_board_with_final_remainder", "result": "PASS",
                 "periods": observed_board},
                {"case": "acquisition_bill_to_asset_gl", "result": "PASS",
                 "bill_id": bill.id, "purchase_value": asset.purchase_value,
                 "cost_debit": ACQUISITION_VALUE, "create_move_id": bill.id},
                {"case": "all_posted_lines_to_gl_provenance", "result": "PASS",
                 "postings": postings},
                {"case": "posted_depreciation_gl_cutoffs", "result": "PASS",
                 "totals": [33_333.67, 66_667.34, 100_001.0],
                 "final_residual": 0.0},
                {"case": "disposal_wizard_to_posted_gl", "result": "PASS",
                 "removal_move_id": removal_move.id,
                 "cost_credit": ACQUISITION_VALUE,
                 "accumulated_debit": ACQUISITION_VALUE,
                 "residual": 0.0},
                {"case": "early_disposal_residual_and_loss_to_posted_gl",
                 "result": "PASS",
                 "removal_move_id": early_removal_move.id,
                 "partial_depreciation": EARLY_PARTIAL_DEPRECIATION,
                 "residual": EARLY_RESIDUAL_VALUE,
                 "sale_value": EARLY_SALE_VALUE,
                 "loss": EARLY_LOSS_VALUE},
                {"case": "fixed_asset_register_rollforward_to_gl",
                 "result": "PASS", "period": [period_start, period_end],
                 **source_rollforward},
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
