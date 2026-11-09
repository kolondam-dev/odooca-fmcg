#!/usr/bin/env python3
"""Disposable-only I2a core ledger verification and counterexamples.

Covers FIN01 (General Ledger), FIN02 (Trial Balance), FIN03 (Journal Ledger),
FIN04 (Journal items audit / audit trail), FIN51 (Multi-company combined Trial
Balance; combined != consolidated), and FIN57 (Sales and purchase register).
Never runs outside finance_i0_reports_disposable; rolls back all fixtures.
"""

from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent) if "__file__" in globals() else "/opt/scripts/ops")
import verify_finance_golden_ledger as golden  # noqa: E402
import verify_finance_ledger_security as sec  # noqa: E402


class RollbackI2a(Exception):
    pass


# Independent expected figures per account (opening, debit, credit, closing) at scale=1:
# Events:
# - 2026-06-30 opening (general): cash +100, equity -100
# - 2026-07-01 out_invoice (sale): ar +110, revenue -100, tax_output -10
# - 2026-07-02 in_invoice (purchase): expense +80, tax_input +8, ap -88
# - 2026-07-10 partnerless entry (general): cash +15, revenue -15
# - 2026-07-15 customer receipt (cash): cash +60, ar -60
# - 2026-07-16 supplier payment (cash): ap +30, cash -30
# - 2026-07-20 out_refund (sale): revenue +20, tax_output +2, ar -22
# - 2026-07-21 in_refund (purchase): ap +11, expense -10, tax_input -1
# - 2026-07-25 accrual entry + 2026-07-26 reversal (general):
#     orig: expense +12, ap -12 (partnerless on AP!)
#     rev:  ap +12, expense -12 (partnerless on AP!)
# - 2026-08-01 customer final receipt (cash): cash +28, ar -28
# - 2026-08-02 supplier final payment (cash): ap +47, cash -47
I2A_JULY = {
    "cash": (100, 75, 30, 145),
    "ar": (0, 110, 82, 28),
    "ap": (0, 53, 100, -47),
    "revenue": (0, 20, 115, -95),
    "tax_output": (0, 2, 10, -8),
    "expense": (0, 92, 22, 70),
    "tax_input": (0, 8, 1, 7),
    "equity": (-100, 0, 0, -100),
    "unaffected_earnings": (0, 0, 0, 0),
}
I2A_AUGUST = {
    "cash": (145, 28, 47, 126),
    "ar": (28, 0, 28, 0),
    "ap": (-47, 47, 0, 0),
    "revenue": (-95, 0, 0, -95),
    "tax_output": (-8, 0, 0, -8),
    "expense": (70, 0, 0, 70),
    "tax_input": (7, 0, 0, 7),
    "equity": (-100, 0, 0, -100),
    "unaffected_earnings": (0, 0, 0, 0),
}
I2A_EMPTY_MAY = {key: (0, 0, 0, 0) for key in I2A_JULY}

# Sale-journal-only subset in July (out_invoice + out_refund):
I2A_JULY_SALE_JOURNAL = {
    "cash": (0, 0, 0, 0),
    "ar": (0, 110, 22, 88),
    "ap": (0, 0, 0, 0),
    "revenue": (0, 20, 100, -80),
    "tax_output": (0, 2, 10, -8),
    "expense": (0, 0, 0, 0),
    "tax_input": (0, 0, 0, 0),
    "equity": (0, 0, 0, 0),
    "unaffected_earnings": (0, 0, 0, 0),
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def make_tax(env, company, accounts, suffix, kind, rate=10.0):
    is_sale = kind == "sale"
    tax_account = accounts["tax_output" if is_sale else "tax_input"]
    group = env["account.tax.group"].with_company(company).create({
        "name": f"I2A Tax Group {suffix} {kind}",
        "company_id": company.id,
    })
    return env["account.tax"].with_company(company).create({
        "name": f"I2A VAT {rate:.0f}% {suffix} {kind}",
        "description": f"VAT{suffix}{kind[:1].upper()}",
        "amount_type": "percent",
        "amount": rate,
        "type_tax_use": kind,
        "tax_group_id": group.id,
        "company_id": company.id,
        "price_include_override": "tax_excluded",
        "invoice_repartition_line_ids": [
            (0, 0, {"repartition_type": "base", "factor_percent": 100.0}),
            (0, 0, {
                "repartition_type": "tax",
                "factor_percent": 100.0,
                "account_id": tax_account.id,
            }),
        ],
        "refund_repartition_line_ids": [
            (0, 0, {"repartition_type": "base", "factor_percent": 100.0}),
            (0, 0, {
                "repartition_type": "tax",
                "factor_percent": 100.0,
                "account_id": tax_account.id,
            }),
        ],
    })


def make_taxed_document(env, fixture, kind, journal, tax, amount, when):
    company, accounts, _gen_journal, partner, scale = fixture
    is_sale = kind.startswith("out_")
    move = env["account.move"].with_company(company).create({
        "move_type": kind,
        "company_id": company.id,
        "journal_id": journal.id,
        "partner_id": partner.id,
        "invoice_date": when,
        "date": when,
        "invoice_date_due": when,
        "invoice_line_ids": [(0, 0, {
            "name": f"I2A taxed line {kind}",
            "quantity": 1,
            "price_unit": amount * scale,
            "tax_ids": [(6, 0, [tax.id])],
            "account_id": accounts["revenue" if is_sale else "expense"].id,
        })],
    })
    move.action_post()
    require(move.state == "posted", f"Document {kind} failed to post")
    return move


def build_i2a_fixture(env, suffix, scale):
    fixture = golden.build_fixture(env, suffix, scale, events=(), draft_noise=False)
    company, accounts, gen_journal, partner, _scale = fixture
    # OCA trial.balance.report.wizard computes unaffected_earnings_account via
    # company.get_unaffected_earnings_account(), which creates an equity_unaffected
    # account when the company has none. Odoo 19 stores account.code per company
    # (code_store is company_dependent), so the account must be created and read
    # under the fixture company, never under the shell's default company.
    accounts["unaffected_earnings"] = company.with_company(company).get_unaffected_earnings_account()
    require(
        accounts["unaffected_earnings"].account_type == "equity_unaffected",
        "Expected equity_unaffected account from get_unaffected_earnings_account()",
    )
    company_account_ids = set(
        env["account.account"].with_context(active_test=False).search([
            ("company_ids", "in", company.ids),
        ]).ids
    )
    require(
        company_account_ids == {acc.id for acc in accounts.values()},
        f"Unexpected company COA accounts on {company.name}: {company_account_ids}",
    )
    partner.with_company(company).write({
        "property_account_receivable_id": accounts["ar"].id,
        "property_account_payable_id": accounts["ap"].id,
    })
    journals = {"general": gen_journal}
    for kind in ("sale", "purchase", "cash"):
        journals[kind] = env["account.journal"].with_company(company).create({
            "name": f"I2A {suffix} {kind}",
            "code": f"I2{suffix}{kind[:1].upper()}",
            "type": kind,
            "company_id": company.id,
            **({"default_account_id": accounts["cash"].id} if kind == "cash" else {}),
        })
    sale_tax = make_tax(env, company, accounts, suffix, "sale", 10.0)
    purchase_tax = make_tax(env, company, accounts, suffix, "purchase", 10.0)

    # 1. Opening on 2026-06-30
    opening = golden.make_entry(env, fixture, "opening", "2026-06-30", {"cash": 100, "equity": -100})
    # 2. Taxed customer invoice & vendor bill
    invoice = make_taxed_document(env, fixture, "out_invoice", journals["sale"], sale_tax, 100, "2026-07-01")
    bill = make_taxed_document(env, fixture, "in_invoice", journals["purchase"], purchase_tax, 80, "2026-07-02")
    # 3. Partnerless manual revenue entry in general journal
    partnerless_rev = golden.make_entry(
        env, fixture, "partnerless_rev", "2026-07-10", {"cash": 15, "revenue": -15},
    )
    # 4. Partial payments in July
    receipt = sec.payment(env, fixture, journals["cash"], 60, "2026-07-15", True)
    outgoing = sec.payment(env, fixture, journals["cash"], 30, "2026-07-16", False)
    # 5. Taxed customer refund & vendor refund
    refund = make_taxed_document(env, fixture, "out_refund", journals["sale"], sale_tax, 20, "2026-07-20")
    vendor_refund = make_taxed_document(
        env, fixture, "in_refund", journals["purchase"], purchase_tax, 10, "2026-07-21",
    )
    # Reconcile July partials + credits
    ar_line = sec.control_line(invoice, accounts["ar"])
    ap_line = sec.control_line(bill, accounts["ap"])
    (ar_line | sec.control_line(refund, accounts["ar"]) | sec.control_line(receipt.move_id, accounts["ar"])).reconcile()
    (
        ap_line
        | sec.control_line(vendor_refund, accounts["ap"])
        | sec.control_line(outgoing.move_id, accounts["ap"])
    ).reconcile()
    require(invoice.amount_residual == 28 * scale, "Invoice July residual mismatch")
    require(bill.amount_residual == 47 * scale, "Bill July residual mismatch")

    # 6. Accrual on reconcilable AP WITHOUT partner, reversed next day via _reverse_moves
    accrual = env["account.move"].with_company(company).create({
        "company_id": company.id,
        "journal_id": journals["general"].id,
        "date": "2026-07-25",
        "ref": f"I2A-ACCRUAL-{suffix}",
        "move_type": "entry",
        "line_ids": [
            (0, 0, {
                "name": "Accrued expense",
                "account_id": accounts["expense"].id,
                "debit": 12 * scale,
                "credit": 0,
            }),
            (0, 0, {
                "name": "Partnerless AP accrual",
                "account_id": accounts["ap"].id,
                "partner_id": False,
                "debit": 0,
                "credit": 12 * scale,
            }),
        ],
    })
    accrual.action_post()
    reversal = accrual._reverse_moves(
        default_values_list=[{
            "date": date(2026, 7, 26),
            "journal_id": journals["general"].id,
            "ref": f"I2A-REV-{suffix}",
        }],
        cancel=False,
    )
    reversal.action_post()
    require(reversal.reversed_entry_id == accrual, "Reversal provenance missing on reversal move")
    require(reversal in accrual.reversal_move_ids, "Reversal provenance missing on original move")

    # 7. Unposted draft noise in July (must be excluded when only_posted_moves=True)
    draft_move = golden.make_entry(
        env, fixture, "draft_noise", "2026-07-28", {"cash": 500, "equity": -500}, posted=False,
    )

    # 8. August final settlements
    aug_receipt = sec.payment(env, fixture, journals["cash"], 28, "2026-08-01", True)
    aug_outgoing = sec.payment(env, fixture, journals["cash"], 47, "2026-08-02", False)
    (ar_line | sec.control_line(aug_receipt.move_id, accounts["ar"])).reconcile()
    (ap_line | sec.control_line(aug_outgoing.move_id, accounts["ap"])).reconcile()
    require(invoice.amount_residual == bill.amount_residual == 0, "August settlement incomplete")

    docs = {
        "opening": opening,
        "invoice": invoice,
        "bill": bill,
        "partnerless_rev": partnerless_rev,
        "receipt": receipt.move_id,
        "outgoing": outgoing.move_id,
        "refund": refund,
        "vendor_refund": vendor_refund,
        "accrual": accrual,
        "reversal": reversal,
        "draft": draft_move,
        "aug_receipt": aug_receipt.move_id,
        "aug_outgoing": aug_outgoing.move_id,
    }
    return company, accounts, journals, partner, scale, docs


def independent_aml_oracle(env, company, accounts, date_from, date_to, journal_ids=None, fy_start="2026-01-01"):
    """Compute opening, debit, credit, closing and AML IDs directly from account.move.line."""
    round_amt = company.currency_id.round
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    fy_date = date.fromisoformat(fy_start)
    base = [
        ("company_id", "=", company.id),
        ("parent_state", "=", "posted"),
        ("display_type", "not in", ["line_note", "line_section", "line_subsection"]),
    ]
    if journal_ids:
        base.append(("journal_id", "in", list(journal_ids)))
    all_lines = env["account.move.line"].search(base, order="date asc, move_id asc, id asc")
    by_account = {}
    for key, acc in accounts.items():
        acc_lines = all_lines.filtered(lambda line, a=acc: line.account_id == a)
        if acc.include_initial_balance:
            init_lines = acc_lines.filtered(lambda line: line.date < start)
        else:
            init_lines = acc_lines.filtered(lambda line: fy_date <= line.date < start)
        period_lines = acc_lines.filtered(lambda line: start <= line.date <= end)
        opening = round_amt(sum(init_lines.mapped("balance")))
        debit = round_amt(sum(period_lines.mapped("debit")))
        credit = round_amt(sum(period_lines.mapped("credit")))
        closing = round_amt(opening + debit - credit)
        by_account[acc.id] = {
            "key": key,
            "initial_balance": opening,
            "debit": debit,
            "credit": credit,
            "ending_balance": closing,
            "period_aml_ids": sorted(period_lines.ids),
        }
    period_all = all_lines.filtered(lambda line: start <= line.date <= end)
    by_journal = {}
    for jnl_id in sorted(set(period_all.journal_id.ids)):
        jlines = period_all.filtered(lambda line, j=jnl_id: line.journal_id.id == j)
        by_journal[jnl_id] = {
            "debit": round_amt(sum(jlines.mapped("debit"))),
            "credit": round_amt(sum(jlines.mapped("credit"))),
            "aml_ids": sorted(jlines.ids),
            "move_ids": sorted(set(jlines.move_id.ids)),
        }
    return {
        "by_account": by_account,
        "by_journal": by_journal,
        "period_aml_ids": sorted(period_all.ids),
        "total_debit": round_amt(sum(period_all.mapped("debit"))),
        "total_credit": round_amt(sum(period_all.mapped("credit"))),
    }


def render_oca_tb(env, company, date_from, date_to, journal_ids=None, only_posted=True, fy_start="2026-01-01"):
    wiz = env["trial.balance.report.wizard"].with_company(company).create({
        "company_id": company.id,
        "date_from": date_from,
        "date_to": date_to,
        "target_move": "posted" if only_posted else "all",
        "hide_account_at_0": False,
        "journal_ids": [(6, 0, list(journal_ids or []))],
    })
    data = wiz._prepare_report_data()
    data["fy_start_date"] = fy_start
    return env["report.account_financial_report.trial_balance"].with_company(company)._get_report_values(
        [wiz.id], data,
    )


def render_oca_gl(
    env, company, date_from, date_to, journal_ids=None, grouped_by="partners",
    centralize=False, only_posted=True,
):
    wiz = env["general.ledger.report.wizard"].with_company(company).create({
        "company_id": company.id,
        "date_from": date_from,
        "date_to": date_to,
        "target_move": "posted" if only_posted else "all",
        "hide_account_at_0": False,
        "centralize": centralize,
        "grouped_by": grouped_by,
        "account_journal_ids": [(6, 0, list(journal_ids or []))],
    })
    data = wiz._prepare_report_data()
    return env["report.account_financial_report.general_ledger"].with_company(company)._get_report_values(
        [wiz.id], data,
    )


def render_oca_jl(env, company, date_from, date_to, journal_ids=None, only_posted=True):
    wiz = env["journal.ledger.report.wizard"].with_company(company).create({
        "company_id": company.id,
        "date_from": date_from,
        "date_to": date_to,
        "move_target": "posted" if only_posted else "all",
        "journal_ids": [(6, 0, list(journal_ids or []))],
    })
    data = wiz._prepare_report_data()
    return env["report.account_financial_report.journal_ledger"].with_company(company)._get_report_values(
        [wiz.id], data,
    )


def extract_gl_summary(gl_values):
    """Extract per-account balances, AML IDs, and partner-grouped IDs from OCA GL output."""
    summary = {}
    all_aml_ids = []
    for item in gl_values["general_ledger"]:
        acc_id = item["id"]
        aml_ids = []
        partner_groups = {}
        if "list_grouped" in item:
            for grp in item["list_grouped"]:
                grp_aml_ids = [ml["id"] for ml in grp["move_lines"] if ml.get("id")]
                aml_ids.extend(grp_aml_ids)
                partner_groups[grp["id"]] = {
                    "init_balance": grp["init_bal"]["balance"],
                    "fin_balance": grp["fin_bal"]["balance"],
                    "aml_ids": sorted(grp_aml_ids),
                }
        else:
            aml_ids = [ml["id"] for ml in item.get("move_lines", []) if ml.get("id")]
        all_aml_ids.extend(aml_ids)
        summary[acc_id] = {
            "init_balance": item["init_bal"]["balance"],
            "fin_balance": item["fin_bal"]["balance"],
            "debit_cumul": item["fin_bal"]["debit"],
            "credit_cumul": item["fin_bal"]["credit"],
            "period_debit": item["fin_bal"]["debit"] - item["init_bal"]["debit"],
            "period_credit": item["fin_bal"]["credit"] - item["init_bal"]["credit"],
            "aml_ids": sorted(aml_ids),
            "partner_groups": partner_groups,
        }
    return summary, sorted(all_aml_ids)


def assert_fin01_gl(gl_values, oracle, accounts, expected_table, scale):
    summary, all_aml_ids = extract_gl_summary(gl_values)
    require(
        all_aml_ids == oracle["period_aml_ids"],
        f"FIN01 AML ID mismatch: {all_aml_ids} != {oracle['period_aml_ids']}",
    )
    for key, figures in expected_table.items():
        acc_id = accounts[key].id
        want_open, want_deb, want_cred, want_close = (v * scale for v in figures)
        orc = oracle["by_account"][acc_id]
        require(
            (orc["initial_balance"], orc["debit"], orc["credit"], orc["ending_balance"])
            == (want_open, want_deb, want_cred, want_close),
            f"Oracle mismatch on {key}",
        )
        if (want_open, want_deb, want_cred, want_close) == (0, 0, 0, 0) and acc_id not in summary:
            continue
        got = summary[acc_id]
        require(
            (got["init_balance"], got["period_debit"], got["period_credit"], got["fin_balance"])
            == (want_open, want_deb, want_cred, want_close),
            f"FIN01 {key} mismatch: got {got}, expected {(want_open, want_deb, want_cred, want_close)}",
        )
        require(got["aml_ids"] == orc["period_aml_ids"], f"FIN01 {key} AML IDs mismatch")


def assert_fin02_tb(tb_values, oracle, accounts, expected_table, scale):
    totals = tb_values["total_amount"]
    golden.assert_figures(totals, expected_table, accounts, scale)
    for acc_id, orc in oracle["by_account"].items():
        row = totals[acc_id]
        require(
            (row["initial_balance"], row["debit"], row["credit"], row["ending_balance"])
            == (orc["initial_balance"], orc["debit"], orc["credit"], orc["ending_balance"]),
            f"FIN02 vs AML oracle mismatch on account {acc_id}",
        )


def assert_fin03_jl(jl_values, oracle):
    observed_aml_ids = []
    for move in jl_values["Moves"]:
        for line in move["report_move_lines"]:
            observed_aml_ids.append(line["move_line_id"])
    require(
        sorted(observed_aml_ids) == oracle["period_aml_ids"],
        f"FIN03 AML IDs mismatch: {sorted(observed_aml_ids)} != {oracle['period_aml_ids']}",
    )
    require(
        len(observed_aml_ids) == len(set(observed_aml_ids)),
        "FIN03 produced duplicate AML lines",
    )
    by_jnl = {row["id"]: row for row in jl_values["Journal_Ledgers"] if row["debit"] or row["credit"]}
    require(set(by_jnl) == set(oracle["by_journal"]), "FIN03 active journal set mismatch")
    for jnl_id, orc_jnl in oracle["by_journal"].items():
        got = by_jnl[jnl_id]
        require(
            (got["debit"], got["credit"]) == (orc_jnl["debit"], orc_jnl["credit"]),
            f"FIN03 journal {jnl_id} totals mismatch: {got} != {orc_jnl}",
        )
        move_ids = sorted(m["move_id"] for m in got["report_moves"])
        require(move_ids == orc_jnl["move_ids"], f"FIN03 journal {jnl_id} move IDs mismatch")


def assert_fin04_audit(snapshot, oracle, docs):
    require(snapshot["report_id"] == "FIN04", "Wrong FIN04 report_id")
    aml_ids = [r["aml_id"] for r in snapshot["rows"]]
    require(aml_ids == oracle["period_aml_ids"], "FIN04 AML IDs do not match oracle")
    require(snapshot["total_debit"] == oracle["total_debit"], "FIN04 total_debit mismatch")
    require(snapshot["total_credit"] == oracle["total_credit"], "FIN04 total_credit mismatch")
    require(snapshot["total_balance"] == 0, "FIN04 posted ledger unbalanced")
    if docs:
        by_move = defaultdict(list)
        for row in snapshot["rows"]:
            by_move[row["move_id"]].append(row)
        accrual_rows = by_move[docs["accrual"].id]
        reversal_rows = by_move[docs["reversal"].id]
        require(all(r["is_reversed"] and docs["reversal"].id in r["reversal_move_ids"] for r in accrual_rows),
                "FIN04 missing is_reversed provenance on accrual")
        require(all(r["is_reversal"] and r["reversed_entry_id"] == docs["accrual"].id for r in reversal_rows),
                "FIN04 missing reversed_entry_id provenance on reversal")
        require(len(snapshot["partnerless_reconcilable_aml_ids"]) == 2,
                "FIN04 must flag partnerless lines on reconcilable AP account")
        require(set(snapshot["draft_aml_ids_in_period"]) == set(docs["draft"].line_ids.ids),
                "FIN04 must identify unposted draft AMLs in period separately")


def fin51_combined_code(index):
    """Shared synthetic code for the index-th key of the I2a expected tables."""
    return f"I2ACOMB{index:02d}"


def assert_fin51_combined_rows(combined_rows, expected_table, multiplier):
    """Strict FIN51 coverage contract, including explicit zero-activity accounts.

    Every expected account (also the all-zero ``unaffected_earnings`` row, which
    the OCA Trial Balance always materializes as the company's equity_unaffected
    account) must appear exactly once under its aligned code, and no unexpected
    combined code may appear. Missing and extra codes fail with a readable
    message instead of a bare KeyError, and non-zero accounts stay value-checked.
    """
    expected_codes = {fin51_combined_code(idx): key for idx, key in enumerate(expected_table)}
    by_code = {}
    for row in combined_rows:
        require(row["code"] not in by_code, f"FIN51 duplicate combined code {row['code']}")
        by_code[row["code"]] = row
    missing = sorted(set(expected_codes) - set(by_code))
    extra = sorted(set(by_code) - set(expected_codes))
    require(
        not missing and not extra,
        f"FIN51 combined account coverage mismatch: missing={missing}, extra={extra}",
    )
    for code, key in expected_codes.items():
        row = by_code[code]
        wanted = tuple(v * multiplier for v in expected_table[key])
        got = (row["initial_balance"], row["debit"], row["credit"], row["ending_balance"])
        require(got == wanted, f"FIN51 combined {key}: expected {wanted}, got {got}")


def assert_fin57_register(snapshot, scale, expected_non_register_moves=1):
    require(snapshot["report_id"] == "FIN57", "Wrong FIN57 report_id")
    require(not snapshot["duplicate_move_ids"], f"FIN57 duplicate moves: {snapshot['duplicate_move_ids']}")
    require(not snapshot["duplicate_line_ids"], f"FIN57 duplicate lines: {snapshot['duplicate_line_ids']}")
    by_type = {row["move_type"]: row for row in snapshot["documents"]}
    require(set(by_type) == {"out_invoice", "out_refund", "in_invoice", "in_refund"}, "FIN57 missing document types")
    require(by_type["out_invoice"]["net_signed_amount"] == 100 * scale, "FIN57 out_invoice base mismatch")
    require(by_type["out_invoice"]["tax_signed_amount"] == 10 * scale, "FIN57 out_invoice tax mismatch")
    require(by_type["out_refund"]["net_signed_amount"] == -20 * scale, "FIN57 out_refund base mismatch")
    require(by_type["out_refund"]["tax_signed_amount"] == -2 * scale, "FIN57 out_refund tax mismatch")
    require(by_type["in_invoice"]["net_signed_amount"] == 80 * scale, "FIN57 in_invoice base mismatch")
    require(by_type["in_invoice"]["tax_signed_amount"] == 8 * scale, "FIN57 in_invoice tax mismatch")
    require(by_type["in_refund"]["net_signed_amount"] == -10 * scale, "FIN57 in_refund base mismatch")
    require(by_type["in_refund"]["tax_signed_amount"] == -1 * scale, "FIN57 in_refund tax mismatch")
    for tie in snapshot["gl_tie_out"]:
        require(tie["unexplained_difference"] == 0, f"FIN57 unexplained GL diff: {tie}")
    # In July, partnerless_rev (-15) and accrual/reversal (+12/-12) hit revenue/expense via general journal:
    non_reg_moves = {item["move_id"] for item in snapshot["non_register_gl_lines"]}
    require(len(non_reg_moves) == expected_non_register_moves,
            f"FIN57 non-register GL move count mismatch: {non_reg_moves}")


def run(env):
    require(env.cr.dbname == "finance_i0_reports_disposable",
            "I2a ledger verification requires exact disposable reports database")
    for addon in ("account_financial_report", "id_finance_reporting", "id_finance_foundation"):
        require(
            env["ir.module.module"].search_count([("name", "=", addon), ("state", "=", "installed")]) == 1,
            f"Required addon {addon} is not installed",
        )

    companies_before = set(env["res.company"].search([]).ids)
    users_before = set(env["res.users"].with_context(active_test=False).search([]).ids)
    evidence = {
        "scope": "I2a core ledgers/registers disposable native oracle; not full FIN01-58 acceptance",
        "reports_verified": ["FIN01", "FIN02", "FIN03", "FIN04", "FIN51", "FIN57"],
        "cases": [],
        "counterexamples": [],
    }

    try:
        with env.cr.savepoint():
            fix_a = build_i2a_fixture(env, "A", 1)
            fix_b = build_i2a_fixture(env, "B", 7)
            for fixture in (fix_a, fix_b):
                company, accounts, journals, partner, scale, docs = fixture
                for period_name, d_from, d_to, expected_table in (
                    ("empty_may", "2026-05-01", "2026-05-31", I2A_EMPTY_MAY),
                    ("july", "2026-07-01", "2026-07-31", I2A_JULY),
                    ("august", "2026-08-01", "2026-08-31", I2A_AUGUST),
                ):
                    oracle = independent_aml_oracle(env, company, accounts, d_from, d_to)
                    tb_val = render_oca_tb(env, company, d_from, d_to)
                    gl_val = render_oca_gl(env, company, d_from, d_to, grouped_by="partners")
                    gl_none = render_oca_gl(env, company, d_from, d_to, grouped_by="none")
                    jl_val = render_oca_jl(env, company, d_from, d_to)
                    audit_val = env["id.finance.audit.trail"]._snapshot(company.id, d_from, d_to)

                    assert_fin02_tb(tb_val, oracle, accounts, expected_table, scale)
                    assert_fin01_gl(gl_val, oracle, accounts, expected_table, scale)
                    assert_fin01_gl(gl_none, oracle, accounts, expected_table, scale)
                    assert_fin03_jl(jl_val, oracle)
                    assert_fin04_audit(audit_val, oracle, docs if period_name == "july" else None)

                    if period_name == "july":
                        # Verify partnerless group id == 0 on AP in FIN01 grouped_by='partners'
                        gl_summary, _ = extract_gl_summary(gl_val)
                        ap_groups = gl_summary[accounts["ap"].id]["partner_groups"]
                        require(0 in ap_groups and partner.id in ap_groups,
                                "FIN01 must separate Missing Partner (0) from named partner on AP")
                        require(len(ap_groups[0]["aml_ids"]) == 2 and ap_groups[0]["fin_balance"] == 0,
                                "FIN01 partnerless AP accrual+reversal group mismatch")
                        # Verify FIN57 Sales & Purchase Register in July
                        reg_val = env["id.finance.sales.purchase.register"]._snapshot(
                            company.id, d_from, d_to,
                        )
                        assert_fin57_register(reg_val, scale, expected_non_register_moves=3)
                        # Verify journal filter consistency across FIN01, FIN02, FIN03, FIN04
                        sale_jnl = [journals["sale"].id]
                        sale_oracle = independent_aml_oracle(
                            env, company, accounts, d_from, d_to, journal_ids=sale_jnl,
                        )
                        assert_fin02_tb(
                            render_oca_tb(env, company, d_from, d_to, journal_ids=sale_jnl),
                            sale_oracle, accounts, I2A_JULY_SALE_JOURNAL, scale,
                        )
                        assert_fin01_gl(
                            render_oca_gl(env, company, d_from, d_to, journal_ids=sale_jnl),
                            sale_oracle, accounts, I2A_JULY_SALE_JOURNAL, scale,
                        )
                        assert_fin03_jl(
                            render_oca_jl(env, company, d_from, d_to, journal_ids=sale_jnl),
                            sale_oracle,
                        )
                        assert_fin04_audit(
                            env["id.finance.audit.trail"]._snapshot(
                                company.id, d_from, d_to, journal_ids=sale_jnl,
                            ),
                            sale_oracle, None,
                        )

                # Unreconcile probe + rollback: GL/TB/JL/FIN04 unchanged when reconciliation is undone
                try:
                    with env.cr.savepoint():
                        sec.control_line(docs["invoice"], accounts["ar"]).remove_move_reconcile()
                        require(docs["invoice"].amount_residual == 110 * scale, "Unreconcile residual mismatch")
                        oracle_unrec = independent_aml_oracle(env, company, accounts, "2026-07-01", "2026-07-31")
                        assert_fin02_tb(
                            render_oca_tb(env, company, "2026-07-01", "2026-07-31"),
                            oracle_unrec, accounts, I2A_JULY, scale,
                        )
                        assert_fin01_gl(
                            render_oca_gl(env, company, "2026-07-01", "2026-07-31"),
                            oracle_unrec, accounts, I2A_JULY, scale,
                        )
                        raise RollbackI2a()
                except RollbackI2a:
                    env.invalidate_all()
                require(docs["invoice"].amount_residual == 0, "Unreconcile rollback failed")
                evidence["cases"].append({"company": company.name, "scale": scale, "result": "PASS"})

            # FIN51 Multi-company combined Trial Balance (1x + 7x = 8x in IDR, plus foreign currency translation)
            comp_a, acc_a, jnl_a, _, _, docs_a = fix_a
            comp_b, acc_b, jnl_b, _, _, _ = fix_b
            # Align account codes and names so combined TB validates COA equivalence (code, name, type)
            for idx, key in enumerate(I2A_JULY):
                code = fin51_combined_code(idx)
                label = f"I2A Combined {key}"
                # account.code is company-dependent in Odoo 19: write it under each owning company.
                for comp, acc in ((comp_a, acc_a[key]), (comp_b, acc_b[key])):
                    acc.with_company(comp).write({"code": code, "name": label})
            env.flush_all()
            env.invalidate_all()
            for comp, accs in ((comp_a, acc_a), (comp_b, acc_b)):
                for idx, key in enumerate(I2A_JULY):
                    require(
                        accs[key].with_company(comp).code == fin51_combined_code(idx),
                        f"FIN51 fixture code alignment failed for {comp.name} {key}",
                    )
            both_env = env["id.finance.combined.trial.balance"].with_context(
                allowed_company_ids=[comp_a.id, comp_b.id],
            )
            combined = both_env._snapshot([comp_a.id, comp_b.id], "2026-07-01", "2026-07-31")
            require(
                combined["scope"] == "combined_multi_entity_trial_balance_not_consolidated"
                and combined["eliminations_applied"] is False,
                "FIN51 must explicitly state combined != consolidated",
            )
            assert_fin51_combined_rows(combined["combined_rows"], I2A_JULY, 8)
            require(combined["totals"]["debit"] == combined["totals"]["credit"], "FIN51 combined debit != credit")

            # FIN51 Counterexample: same code with different name or account_type must fail closed
            from odoo.exceptions import UserError

            try:
                with env.cr.savepoint():
                    acc_b["cash"].with_company(comp_b).name = "Mismatched Cross-Company Account Name"
                    env.flush_all()
                    try:
                        both_env._snapshot([comp_a.id, comp_b.id], "2026-07-01", "2026-07-31")
                    except UserError:
                        evidence["counterexamples"].append({
                            "case": "fin51_ambiguous_coa_name_rejected",
                            "result": "REJECTED",
                        })
                    else:
                        raise AssertionError("FIN51 accepted ambiguous cross-company account name")
                    raise RollbackI2a()
            except RollbackI2a:
                env.invalidate_all()

            try:
                with env.cr.savepoint():
                    acc_b["cash"].with_company(comp_b).account_type = "asset_current"
                    env.flush_all()
                    try:
                        both_env._snapshot([comp_a.id, comp_b.id], "2026-07-01", "2026-07-31")
                    except UserError:
                        evidence["counterexamples"].append({
                            "case": "fin51_ambiguous_coa_type_rejected",
                            "result": "REJECTED",
                        })
                    else:
                        raise AssertionError("FIN51 accepted ambiguous cross-company account_type")
                    raise RollbackI2a()
            except RollbackI2a:
                env.invalidate_all()

            # FIN51 Currency translation check (present IDR companies in USD at explicit 1 IDR = 0.5 USD test rate)
            try:
                with env.cr.savepoint():
                    usd = env.ref("base.USD")
                    usd.active = True
                    env["res.currency.rate"].create({
                        "name": "2026-07-01",
                        "currency_id": usd.id,
                        "rate": 0.5,
                        "company_id": comp_a.id,
                    })
                    translated = both_env._snapshot(
                        [comp_a.id], "2026-07-01", "2026-07-31",
                        presentation_currency_id=usd.id, rate_date="2026-07-31",
                    )
                    require(translated["presentation_currency_id"] == usd.id, "FIN51 presentation currency mismatch")
                    require(translated["entities"][0]["rate_to_presentation"] == 0.5, "FIN51 rate mismatch")
                    cash_row = next(r for r in translated["combined_rows"] if r["code"] == fin51_combined_code(0))
                    require(cash_row["ending_balance"] == 72.5, f"FIN51 translated cash mismatch: {cash_row}")
                    raise RollbackI2a()
            except RollbackI2a:
                env.invalidate_all()
            evidence["cases"].append({"case": "FIN51_combined_and_translated", "result": "PASS"})

            # FIN51 Regression: Company C resolves unaffected earnings under its own company context while default env is Company A
            try:
                with env.cr.savepoint():
                    env_comp_a = env["id.finance.combined.trial.balance"].with_company(comp_a).with_context(
                        allowed_company_ids=[comp_a.id, comp_b.id],
                    )
                    comp_fresh = env["res.company"].with_company(comp_a).create({
                        "name": "I2A Fresh Entity C Without Unaffected",
                        "currency_id": comp_a.currency_id.id,
                    })
                    existing = env["account.account"].with_context(active_test=False).search([
                        ("company_ids", "in", [comp_fresh.id]),
                        ("account_type", "=", "equity_unaffected"),
                    ])
                    require(not existing, "Fresh company should not have unaffected earnings account yet")
                    _snap = env_comp_a.with_context(
                        allowed_company_ids=[comp_a.id, comp_fresh.id],
                    )._snapshot([comp_fresh.id], "2026-07-01", "2026-07-31")
                    unaffected_fresh = comp_fresh.with_company(comp_fresh).get_unaffected_earnings_account()
                    require(bool(unaffected_fresh), "FIN51 must resolve unaffected earnings for fresh entity")
                    require(
                        comp_fresh.id in unaffected_fresh.company_ids.ids,
                        "Unaffected earnings must belong to fresh entity",
                    )
                    code_fresh = unaffected_fresh.with_company(comp_fresh).code
                    require(bool(code_fresh), "Unaffected earnings must have valid code in entity context")
                    require(
                        comp_a.id not in unaffected_fresh.with_company(comp_a).company_ids.ids,
                        "Unaffected earnings must not pollute Company A",
                    )
                    evidence["cases"].append({
                        "case": "fin51_unaffected_earnings_created_in_target_company_context",
                        "result": "PASS",
                    })
                    raise RollbackI2a()
            except RollbackI2a:
                env.invalidate_all()

            # Counterexample 1: Role & company isolation across all 6 reports (FIN01, FIN02, FIN03, FIN04, FIN51, FIN57)
            _u_reader, reader = sec.actor(
                env, "i2a.reader", comp_a, ["id_finance_foundation.group_finance_reader"],
            )
            _u_sales, sales = sec.actor(env, "i2a.sales", comp_a, ["sales_team.group_sale_salesman"])
            _u_driver, driver = sec.actor(env, "i2a.driver", comp_a, ["id_mobile_api.group_mobile_evidence"])

            # Reader allowed on comp_a for all single-company reports
            assert_fin04_audit(
                reader["id.finance.audit.trail"]._snapshot(comp_a.id, "2026-07-01", "2026-07-31"),
                independent_aml_oracle(env, comp_a, acc_a, "2026-07-01", "2026-07-31"),
                docs_a,
            )
            assert_fin57_register(
                reader["id.finance.sales.purchase.register"]._snapshot(comp_a.id, "2026-07-01", "2026-07-31"),
                1, expected_non_register_moves=3,
            )
            # Reader denied on comp_b (foreign company) and on FIN51 when comp_b is requested
            for rpt_name in ("trial_balance", "general_ledger", "journal_ledger"):
                evidence["counterexamples"].append(sec.denied(
                    env,
                    lambda r=rpt_name: reader[f"report.account_financial_report.{r}"]._get_report_values(
                        [], {"company_id": comp_b.id},
                    ),
                    f"reader_foreign_{rpt_name}",
                ))
                evidence["counterexamples"].append(sec.denied(
                    env,
                    lambda r=rpt_name: reader[f"report.account_financial_report.{r}"]._get_report_values(
                        [], {"company_id": comp_a.id, "journal_ids": [jnl_b["sale"].id]},
                    ),
                    f"reader_foreign_journal_{rpt_name}",
                ))
            evidence["counterexamples"].append(sec.denied(
                env,
                lambda: reader["id.finance.audit.trail"]._snapshot(comp_b.id, "2026-07-01", "2026-07-31"),
                "reader_foreign_fin04",
            ))
            evidence["counterexamples"].append(sec.denied(
                env,
                lambda: reader["id.finance.audit.trail"]._snapshot(
                    comp_a.id, "2026-07-01", "2026-07-31", journal_ids=[jnl_b["sale"].id],
                ),
                "reader_foreign_journal_fin04",
            ))
            evidence["counterexamples"].append(sec.denied(
                env,
                lambda: reader["id.finance.combined.trial.balance"]._snapshot(
                    [comp_a.id, comp_b.id], "2026-07-01", "2026-07-31",
                ),
                "reader_unauthorized_second_company_fin51",
            ))
            evidence["counterexamples"].append(sec.denied(
                env,
                lambda: reader["id.finance.sales.purchase.register"]._snapshot(
                    comp_b.id, "2026-07-01", "2026-07-31",
                ),
                "reader_foreign_fin57",
            ))

            # Sales and Driver denied on all 6 reports
            for role_label, actor_env in (("sales", sales), ("driver", driver)):
                for rpt_name in ("trial_balance", "general_ledger", "journal_ledger"):
                    evidence["counterexamples"].append(sec.denied(
                        env,
                        lambda e=actor_env, r=rpt_name: e[
                            f"report.account_financial_report.{r}"
                        ]._get_report_values([], {"company_id": comp_a.id}),
                        f"{role_label}_denied_{rpt_name}",
                    ))
                evidence["counterexamples"].append(sec.denied(
                    env,
                    lambda e=actor_env: e["id.finance.audit.trail"]._snapshot(
                        comp_a.id, "2026-07-01", "2026-07-31",
                    ),
                    f"{role_label}_denied_fin04",
                ))
                evidence["counterexamples"].append(sec.denied(
                    env,
                    lambda e=actor_env: e["id.finance.combined.trial.balance"]._snapshot(
                        [comp_a.id], "2026-07-01", "2026-07-31",
                    ),
                    f"{role_label}_denied_fin51",
                ))
                evidence["counterexamples"].append(sec.denied(
                    env,
                    lambda e=actor_env: e["id.finance.sales.purchase.register"]._snapshot(
                        comp_a.id, "2026-07-01", "2026-07-31",
                    ),
                    f"{role_label}_denied_fin57",
                ))

            # Counterexample 2: Balanced ledger mutation rejected by FIN01/FIN02/FIN03/FIN04/FIN57 oracles + rollback
            baseline_oracle = independent_aml_oracle(env, comp_a, acc_a, "2026-07-01", "2026-07-31")
            try:
                with env.cr.savepoint():
                    golden.make_entry(
                        env, (comp_a, acc_a, jnl_a["general"], fix_a[3], 1),
                        "tamper_balanced", "2026-07-30", {"cash": 9, "revenue": -9},
                    )
                    # Reports now include the tampered entry; baseline expected figures must reject it!
                    for label, check_fn in (
                        ("FIN01", lambda: assert_fin01_gl(
                            render_oca_gl(env, comp_a, "2026-07-01", "2026-07-31"),
                            baseline_oracle, acc_a, I2A_JULY, 1,
                        )),
                        ("FIN02", lambda: assert_fin02_tb(
                            render_oca_tb(env, comp_a, "2026-07-01", "2026-07-31"),
                            baseline_oracle, acc_a, I2A_JULY, 1,
                        )),
                        ("FIN03", lambda: assert_fin03_jl(
                            render_oca_jl(env, comp_a, "2026-07-01", "2026-07-31"),
                            baseline_oracle,
                        )),
                        ("FIN04", lambda: assert_fin04_audit(
                            env["id.finance.audit.trail"]._snapshot(comp_a.id, "2026-07-01", "2026-07-31"),
                            baseline_oracle, docs_a,
                        )),
                        ("FIN57", lambda: assert_fin57_register(
                            env["id.finance.sales.purchase.register"]._snapshot(
                                comp_a.id, "2026-07-01", "2026-07-31",
                            ),
                            1, expected_non_register_moves=3,
                        )),
                    ):
                        try:
                            check_fn()
                        except AssertionError:
                            evidence["counterexamples"].append({
                                "case": f"tamper_rejected_{label}",
                                "result": "REJECTED",
                            })
                        else:
                            raise AssertionError(f"Tampered ledger unexpectedly accepted by {label}")
                    raise RollbackI2a()
            except RollbackI2a:
                env.invalidate_all()

            # Verify baseline restored after tamper rollback
            restored_oracle = independent_aml_oracle(env, comp_a, acc_a, "2026-07-01", "2026-07-31")
            assert_fin01_gl(
                render_oca_gl(env, comp_a, "2026-07-01", "2026-07-31"),
                restored_oracle, acc_a, I2A_JULY, 1,
            )
            assert_fin02_tb(
                render_oca_tb(env, comp_a, "2026-07-01", "2026-07-31"),
                restored_oracle, acc_a, I2A_JULY, 1,
            )
            assert_fin03_jl(render_oca_jl(env, comp_a, "2026-07-01", "2026-07-31"), restored_oracle)
            assert_fin04_audit(
                env["id.finance.audit.trail"]._snapshot(comp_a.id, "2026-07-01", "2026-07-31"),
                restored_oracle, docs_a,
            )
            assert_fin57_register(
                env["id.finance.sales.purchase.register"]._snapshot(comp_a.id, "2026-07-01", "2026-07-31"),
                1, expected_non_register_moves=3,
            )
            evidence["counterexamples"].append({"case": "baseline_restored_after_tamper", "result": "PASS"})
            raise RollbackI2a()
    except RollbackI2a:
        env.invalidate_all()

    require(set(env["res.company"].search([]).ids) == companies_before, "Company fixture leaked in I2a")
    require(
        set(env["res.users"].with_context(active_test=False).search([]).ids) == users_before,
        "User fixture leaked in I2a",
    )
    evidence["fixture_rollback"] = "PASS"
    print("FINANCE_I2A_LEDGERS_CORE=" + json.dumps(evidence, sort_keys=True))
    print("FINANCE_I2A_LEDGERS_CORE=PASS")
    return evidence


if "env" in globals():
    run(globals()["env"])
