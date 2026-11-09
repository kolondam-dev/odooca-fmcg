#!/usr/bin/env python3
"""Disposable-only I2b AR/AP subledger verification and counterexamples.

Covers FIN05 (Partner Ledger AR), FIN06 (Partner Ledger AP), FIN07 (Open Items
as of date), FIN08 (Aged Receivable) and FIN09 (Aged Payable).

The independent oracle reads posted ``account.move.line`` records and
``account.partial.reconcile`` records directly. It never calls the production
subledger helpers. OCA ``open_items`` and ``aged_partner_balance`` are rendered
from their real ``_get_report_values`` entry points and compared with the same
oracle. Everything runs inside a savepoint and is rolled back.
"""

from collections import defaultdict
from datetime import date
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent) if "__file__" in globals() else "/opt/scripts/ops")
import verify_finance_golden_ledger as golden  # noqa: E402
import verify_finance_i2_ledgers_core as i2a  # noqa: E402
import verify_finance_ledger_security as sec  # noqa: E402

AR_TYPE = "asset_receivable"
AP_TYPE = "liability_payable"
CONTROL_TYPES = (AR_TYPE, AP_TYPE)
BUCKET_KEYS = {
    "current": "current",
    "days_1_30": "30_days",
    "days_31_60": "60_days",
    "days_61_90": "90_days",
    "days_91_120": "120_days",
    "older": "older",
}


class RollbackI2b(Exception):
    pass


# Independent scale=1 control figures for July 2026.
I2B_JULY_AR = (0.0, 110.0, 82.0, 28.0)
I2B_JULY_AP = (0.0, 53.0, 100.0, -47.0)
I2B_JULY_AP_PARTNER = (0.0, 41.0, 88.0, -47.0)
I2B_JULY_AP_PARTNERLESS = (0.0, 12.0, 12.0, 0.0)
I2B_AUGUST_AR = (28.0, 0.0, 28.0, 0.0)
I2B_AUGUST_AP = (-47.0, 47.0, 0.0, 0.0)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def _cutoff(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _bucket(due_date, as_of):
    """Independent aging bucket, deliberately not importing the production helper."""
    cutoff = _cutoff(as_of)
    due = _cutoff(due_date) if due_date else None
    if not due or due >= cutoff:
        return "current"
    days = (cutoff - due).days
    for edge, name in (
        (30, "days_1_30"), (60, "days_31_60"), (90, "days_61_90"),
        (120, "days_91_120"),
    ):
        if days <= edge:
            return name
    return "older"


def _posted_lines(env, company, accounts, date_to, date_from=None):
    domain = [
        ("company_id", "=", company.id),
        ("account_id", "in", accounts.ids),
        ("parent_state", "=", "posted"),
        ("date", "<=", _cutoff(date_to)),
        ("display_type", "not in", ["line_note", "line_section", "line_subsection"]),
    ]
    if date_from:
        domain.append(("date", ">", _cutoff(date_from)))
    return env["account.move.line"].search(domain, order="date asc, move_id asc, id asc")


def independent_partner_ledger(env, company, accounts, date_from, date_to):
    """Aggregate raw posted AML balances by (partner, account type)."""
    start, end = _cutoff(date_from), _cutoff(date_to)
    round_amt = company.currency_id.round
    rows = {}
    for line in _posted_lines(env, company, accounts, end):
        account_type = line.account_id.account_type
        if account_type not in CONTROL_TYPES:
            continue
        partner_id = line.partner_id.id or 0
        key = (partner_id, account_type)
        row = rows.setdefault(key, {
            "partner_id": partner_id,
            "partner_name": line.partner_id.display_name or "",
            "account_type": account_type,
            "opening_balance": 0.0,
            "debit": 0.0,
            "credit": 0.0,
            "closing_balance": 0.0,
        })
        if line.date < start:
            row["opening_balance"] = round_amt(row["opening_balance"] + line.balance)
        else:
            row["debit"] = round_amt(row["debit"] + line.debit)
            row["credit"] = round_amt(row["credit"] + line.credit)
    for row in rows.values():
        row["closing_balance"] = round_amt(
            row["opening_balance"] + row["debit"] - row["credit"]
        )
    totals = {
        "opening_balance": round_amt(sum(row["opening_balance"] for row in rows.values())),
        "debit": round_amt(sum(row["debit"] for row in rows.values())),
        "credit": round_amt(sum(row["credit"] for row in rows.values())),
        "closing_balance": round_amt(sum(row["closing_balance"] for row in rows.values())),
    }
    return {"rows": rows, "totals": totals}


def independent_open_items(env, company, accounts, as_of):
    """Reconstruct residuals only from partials whose max_date <= as_of."""
    cutoff = _cutoff(as_of)
    round_amt = company.currency_id.round
    lines = _posted_lines(env, company, accounts, cutoff)
    line_by_id = {line.id: line for line in lines}
    partials = env["account.partial.reconcile"].search([
        ("company_id", "=", company.id),
        ("max_date", "<=", cutoff),
        "|",
        ("debit_move_id", "in", list(line_by_id)),
        ("credit_move_id", "in", list(line_by_id)),
    ], order="max_date asc, id asc") if line_by_id else env["account.partial.reconcile"]
    matched = defaultdict(float)
    for partial in partials:
        if partial.debit_move_id.id in line_by_id:
            matched[partial.debit_move_id.id] -= partial.amount
        if partial.credit_move_id.id in line_by_id:
            matched[partial.credit_move_id.id] += partial.amount
    rows = {}
    for line_id, line in line_by_id.items():
        residual = round_amt(line.balance + matched[line_id])
        if residual == 0:
            continue
        rows[line_id] = {
            "line_id": line_id,
            "move_id": line.move_id.id,
            "date": line.date,
            "due_date": line.date_maturity or line.date,
            "partner_id": line.partner_id.id or 0,
            "partner_name": line.partner_id.display_name or "",
            "account_id": line.account_id.id,
            "account_type": line.account_id.account_type,
            "balance": round_amt(line.balance),
            "matched_amount": round_amt(matched[line_id]),
            "residual": residual,
        }
    account_totals = defaultdict(float)
    partner_rows = {}
    for row in rows.values():
        account_totals[row["account_type"]] = round_amt(
            account_totals[row["account_type"]] + row["residual"]
        )
        key = (row["partner_id"], row["account_type"])
        partner = partner_rows.setdefault(key, {
            "partner_id": row["partner_id"],
            "partner_name": row["partner_name"],
            "account_type": row["account_type"],
            "residual": 0.0,
            "line_ids": [],
        })
        partner["residual"] = round_amt(partner["residual"] + row["residual"])
        partner["line_ids"].append(row["line_id"])
    return {
        "rows": rows,
        "partner_rows": partner_rows,
        "account_totals": dict(account_totals),
        "total_residual": round_amt(sum(row["residual"] for row in rows.values())),
        "partnerless_residual": round_amt(
            sum(row["residual"] for row in rows.values() if not row["partner_id"])
        ),
    }


def assert_partner_ledger(snapshot, oracle):
    observed = {
        (row["partner_id"], row["account_type"]): (
            row["opening_balance"], row["debit"], row["credit"], row["closing_balance"],
        )
        for row in snapshot["rows"]
    }
    expected = {
        key: (
            row["opening_balance"], row["debit"], row["credit"], row["closing_balance"],
        )
        for key, row in oracle["rows"].items()
    }
    require(observed == expected, f"FIN05/FIN06 partner ledger mismatch: {observed} != {expected}")
    for name in ("opening_balance", "debit", "credit", "closing_balance"):
        require(
            snapshot["totals"][name] == oracle["totals"][name],
            f"FIN05/FIN06 total {name} mismatch: "
            f"{snapshot['totals'][name]} != {oracle['totals'][name]}",
        )
    require(snapshot["gl_tie_out"]["balanced"], f"FIN05/FIN06 GL tie-out failed: {snapshot['gl_tie_out']}")


def assert_open_items(snapshot, oracle):
    observed = {row["line_id"]: row["residual"] for row in snapshot["rows"]}
    expected = {line_id: row["residual"] for line_id, row in oracle["rows"].items()}
    require(observed == expected, f"FIN07 open item mismatch: {observed} != {expected}")
    observed_totals = {row["account_type"]: row["residual"] for row in snapshot["account_totals"]}
    expected_totals = {
        account_type: round(sum(
            row["residual"] for row in oracle["rows"].values()
            if row["account_type"] == account_type
        ), 2)
        for account_type in set(row["account_type"] for row in oracle["rows"].values())
    }
    require(
        observed_totals == expected_totals,
        f"FIN07 account totals mismatch: {observed_totals} != {expected_totals}",
    )
    require(
        snapshot["total_residual"] == oracle["total_residual"],
        f"FIN07 total residual mismatch: {snapshot['total_residual']} != {oracle['total_residual']}",
    )
    require(
        snapshot["partnerless_residual"] == oracle["partnerless_residual"],
        "FIN07 partnerless residual mismatch",
    )
    require(snapshot["gl_tie_out"]["balanced"], f"FIN07 GL tie-out failed: {snapshot['gl_tie_out']}")


def _expected_aging(oracle, as_of):
    buckets = defaultdict(float)
    partner_buckets = defaultdict(lambda: defaultdict(float))
    account_buckets = defaultdict(lambda: defaultdict(float))
    for row in oracle["rows"].values():
        bucket = _bucket(row["due_date"], as_of)
        buckets[bucket] += row["residual"]
        partner_buckets[(row["partner_id"], row["account_type"])][bucket] += row["residual"]
        account_buckets[row["account_type"]][bucket] += row["residual"]
    return buckets, partner_buckets, account_buckets


def assert_aging(snapshot, oracle, as_of):
    buckets, partner_buckets, _account_buckets = _expected_aging(oracle, as_of)
    for bucket in BUCKET_KEYS:
        expected = round(buckets.get(bucket, 0.0), 2)
        require(
            snapshot["buckets"][bucket] == expected,
            f"FIN08/FIN09 bucket {bucket}: {snapshot['buckets'][bucket]} != {expected}",
        )
    require(snapshot["balanced"], f"FIN08/FIN09 buckets do not tie: {snapshot}")
    require(
        snapshot["total_residual"] == oracle["total_residual"],
        "FIN08/FIN09 total residual does not match open items",
    )
    observed_partners = {
        (row["partner_id"], row["account_type"]): row for row in snapshot["partners"]
    }
    require(
        set(observed_partners) == set(partner_buckets),
        f"FIN08/FIN09 partner coverage mismatch: {observed_partners} vs {partner_buckets}",
    )
    for key, expected_buckets in partner_buckets.items():
        row = observed_partners[key]
        require(
            row["residual"] == round(sum(expected_buckets.values()), 2),
            f"FIN08/FIN09 partner residual mismatch for {key}",
        )
        for bucket in BUCKET_KEYS:
            require(
                row["buckets"][bucket] == round(expected_buckets.get(bucket, 0.0), 2),
                f"FIN08/FIN09 partner bucket mismatch for {key}/{bucket}",
            )


def render_oca_open_items(env, company, accounts, as_of):
    wizard = env["open.items.report.wizard"].with_company(company).create({
        "company_id": company.id,
        "date_at": as_of,
        "date_from": False,
        "target_move": "posted",
        "account_ids": [(6, 0, accounts.ids)],
        "partner_ids": [(6, 0, [])],
        "hide_account_at_0": False,
        "show_partner_details": True,
        "grouped_by": "partners",
        "foreign_currency": False,
    })
    data = wizard._prepare_report_data()
    return env["report.account_financial_report.open_items"].with_company(company)._get_report_values(
        [wizard.id], data,
    )


def assert_oca_open_items(values, oracle):
    observed = {}
    for account_id, partners in values["Open_Items"].items():
        for partner_id, lines in partners.items():
            for line in lines:
                observed[line["id"]] = (account_id, partner_id, round(line["amount_residual"], 2))
    expected = {
        line_id: (row["account_id"], row["partner_id"], row["residual"])
        for line_id, row in oracle["rows"].items()
    }
    require(observed == expected, f"OCA open_items mismatch: {observed} != {expected}")
    for account_id, row in values["total_amount"].items():
        expected_total = round(sum(
            item["residual"] for item in oracle["rows"].values()
            if item["account_id"] == account_id
        ), 2)
        require(
            row["residual"] == expected_total,
            f"OCA open_items account {account_id} mismatch: {row['residual']} != {expected_total}",
        )


def render_oca_aged_partner_balance(env, company, accounts, as_of, suffix):
    config = env["account.age.report.configuration"].with_company(company).create({
        "name": f"I2B age config {suffix}",
        "company_id": company.id,
        "line_ids": [
            (0, 0, {"name": "30", "inferior_limit": 30}),
            (0, 0, {"name": "60", "inferior_limit": 60}),
            (0, 0, {"name": "90", "inferior_limit": 90}),
            (0, 0, {"name": "120", "inferior_limit": 120}),
        ],
    })
    wizard = env["aged.partner.balance.report.wizard"].with_company(company).create({
        "company_id": company.id,
        "date_at": as_of,
        "date_from": False,
        "target_move": "posted",
        "account_ids": [(6, 0, accounts.ids)],
        "partner_ids": [(6, 0, [])],
        "show_move_line_details": False,
        "age_partner_config_id": config.id,
    })
    data = wizard._prepare_report_data()
    # Direct (in-process) rendering bypasses the report-action serializer that
    # normally turns date objects into strings for the OCA report entry point.
    data["date_at"] = as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of)
    return env["report.account_financial_report.aged_partner_balance"].with_company(
        company,
    )._get_report_values([wizard.id], data)


def assert_oca_aged_partner_balance(values, oracle, as_of):
    _buckets, partner_buckets, account_buckets = _expected_aging(oracle, as_of)
    observed_accounts = {row["id"]: row for row in values["aged_partner_balance"]}
    expected_account_ids = {row["account_id"] for row in oracle["rows"].values()}
    require(
        set(observed_accounts) == expected_account_ids,
        f"OCA aged account coverage mismatch: {set(observed_accounts)} != {expected_account_ids}",
    )
    for account_id in expected_account_ids:
        observed = observed_accounts[account_id]
        expected = account_buckets[account_id]
        require(
            round(observed["residual"], 2) == round(sum(expected.values()), 2),
            f"OCA aged account {account_id} residual mismatch",
        )
        for bucket, oca_key in BUCKET_KEYS.items():
            require(
                round(observed[oca_key], 2) == round(expected.get(bucket, 0.0), 2),
                f"OCA aged account {account_id}/{oca_key} mismatch",
            )
    observed_partners = {}
    for account_id, row in observed_accounts.items():
        for partner in row["partners"]:
            observed_partners[(account_id, partner["name"])] = partner
    expected_partners = {}
    for (partner_id, account_type), buckets in partner_buckets.items():
        account_ids = {
            item["account_id"] for item in oracle["rows"].values()
            if item["partner_id"] == partner_id and item["account_type"] == account_type
        }
        name = next(
            (item["partner_name"] for item in oracle["rows"].values()
             if item["partner_id"] == partner_id and item["account_type"] == account_type),
            "",
        )
        for account_id in account_ids:
            expected_partners[(account_id, name)] = buckets
    require(
        set(observed_partners) == set(expected_partners),
        f"OCA aged partner coverage mismatch: {set(observed_partners)} != {set(expected_partners)}",
    )
    for key, expected in expected_partners.items():
        partner = observed_partners[key]
        require(
            round(partner["residual"], 2) == round(sum(expected.values()), 2),
            f"OCA aged partner residual mismatch for {key}",
        )
        for bucket, oca_key in BUCKET_KEYS.items():
            require(
                round(partner[oca_key], 2) == round(expected.get(bucket, 0.0), 2),
                f"OCA aged partner bucket mismatch for {key}/{oca_key}",
            )


def _control_accounts(env, company, accounts):
    return (accounts["ar"] | accounts["ap"]).with_company(company)


def check_fixture(env, fixture, evidence, check_hard_coded=False):
    company, accounts, journals, partner, scale, docs = fixture
    control = _control_accounts(env, company, accounts)
    round_amt = company.currency_id.round
    models = env.with_context(allowed_company_ids=[company.id]).with_company(company)

    for label, date_from, date_to in (
        ("july", "2026-07-01", "2026-07-31"),
        ("august", "2026-08-01", "2026-08-31"),
    ):
        for partner_type, account_type in (("customer", AR_TYPE), ("supplier", AP_TYPE)):
            oracle = independent_partner_ledger(
                env, company, accounts["ar" if partner_type == "customer" else "ap"],
                date_from, date_to,
            )
            snapshot = models["id.finance.partner.ledger"]._snapshot(
                company.id, date_from, date_to, partner_type=partner_type,
            )
            assert_partner_ledger(snapshot, oracle)
            evidence["cases"].append({
                "company": company.name, "scale": scale, "report": snapshot["report_id"],
                "period": label, "partner_type": partner_type, "result": "PASS",
            })
        if check_hard_coded and label == "july":
            ar_rows = models["id.finance.partner.ledger"]._snapshot(
                company.id, date_from, date_to, partner_type="customer",
            )["rows"]
            ap_rows = models["id.finance.partner.ledger"]._snapshot(
                company.id, date_from, date_to, partner_type="supplier",
            )["rows"]
            require(
                (ar_rows[0]["opening_balance"], ar_rows[0]["debit"],
                 ar_rows[0]["credit"], ar_rows[0]["closing_balance"]) == I2B_JULY_AR,
                "FIN05 July control figures mismatch",
            )
            ap_by_partner = {row["partner_id"]: row for row in ap_rows}
            require(
                (ap_by_partner[partner.id]["opening_balance"], ap_by_partner[partner.id]["debit"],
                 ap_by_partner[partner.id]["credit"], ap_by_partner[partner.id]["closing_balance"])
                == I2B_JULY_AP_PARTNER,
                "FIN06 July named partner control figures mismatch",
            )
            require(
                (ap_by_partner[0]["opening_balance"], ap_by_partner[0]["debit"],
                 ap_by_partner[0]["credit"], ap_by_partner[0]["closing_balance"])
                == I2B_JULY_AP_PARTNERLESS,
                "FIN06 July partnerless control figures mismatch",
            )
            ap_total = models["id.finance.partner.ledger"]._snapshot(
                company.id, date_from, date_to, partner_type="supplier",
            )["totals"]
            require(
                (ap_total["opening_balance"], ap_total["debit"],
                 ap_total["credit"], ap_total["closing_balance"]) == I2B_JULY_AP,
                "FIN06 July total control figures mismatch",
            )
        if check_hard_coded and label == "august":
            ar_total = models["id.finance.partner.ledger"]._snapshot(
                company.id, date_from, date_to, partner_type="customer",
            )["totals"]
            ap_total = models["id.finance.partner.ledger"]._snapshot(
                company.id, date_from, date_to, partner_type="supplier",
            )["totals"]
            require(
                (ar_total["opening_balance"], ar_total["debit"],
                 ar_total["credit"], ar_total["closing_balance"]) == I2B_AUGUST_AR,
                "FIN05 August control figures mismatch",
            )
            require(
                (ap_total["opening_balance"], ap_total["debit"],
                 ap_total["credit"], ap_total["closing_balance"]) == I2B_AUGUST_AP,
                "FIN06 August control figures mismatch",
            )

    for as_of in ("2026-07-14", "2026-07-25", "2026-07-31", "2026-08-31"):
        for partner_type, account_key in (("customer", "ar"), ("supplier", "ap")):
            oracle = independent_open_items(
                env, company, accounts[account_key], as_of,
            )
            snapshot = models["id.finance.open.items"]._snapshot(
                company.id, as_of, partner_type=partner_type,
            )
            assert_open_items(snapshot, oracle)
            evidence["cases"].append({
                "company": company.name, "scale": scale, "report": "FIN07",
                "as_of": as_of, "partner_type": partner_type, "result": "PASS",
            })
            if check_hard_coded and partner_type == "supplier" and as_of == "2026-07-25":
                require(
                    snapshot["partnerless_residual"] == round_amt(-12 * scale),
                    "FIN07 must expose the open partnerless AP accrual explicitly",
                )
                require(
                    set(snapshot["partnerless_line_ids"]) == {docs["accrual"].line_ids.filtered(
                        lambda line: line.account_id == accounts["ap"]
                    ).id},
                    "FIN07 partnerless line coverage mismatch",
                )
            if check_hard_coded and as_of == "2026-07-14":
                expected = 110 * scale if partner_type == "customer" else -88 * scale
                require(
                    snapshot["total_residual"] == round_amt(expected),
                    f"FIN07 as-of before settlement must use dated partials, got {snapshot['total_residual']}",
                )

    for as_of in ("2026-07-14", "2026-07-25", "2026-07-31"):
        for partner_type, account_key in (("customer", "ar"), ("supplier", "ap")):
            oracle = independent_open_items(
                env, company, accounts[account_key], as_of,
            )
            snapshot = models["id.finance.aged.partner.balance"]._snapshot(
                company.id, as_of, partner_type=partner_type,
            )
            assert_aging(snapshot, oracle, as_of)
            evidence["cases"].append({
                "company": company.name, "scale": scale, "report": snapshot["report_id"],
                "as_of": as_of, "partner_type": partner_type, "result": "PASS",
            })

    for as_of in ("2026-07-14", "2026-07-31"):
        oracle = independent_open_items(env, company, control, as_of)
        assert_oca_open_items(
            render_oca_open_items(env, company, control, as_of), oracle,
        )
        evidence["cases"].append({
            "company": company.name, "scale": scale, "report": "OCA open_items",
            "as_of": as_of, "result": "PASS",
        })
    for as_of in ("2026-07-25", "2026-07-31"):
        oracle = independent_open_items(env, company, control, as_of)
        assert_oca_aged_partner_balance(
            render_oca_aged_partner_balance(env, company, control, as_of, f"{company.id}-{as_of}"),
            oracle, as_of,
        )
        evidence["cases"].append({
            "company": company.name, "scale": scale, "report": "OCA aged_partner_balance",
            "as_of": as_of, "result": "PASS",
        })

    if check_hard_coded:
        at_july_end = independent_open_items(env, company, accounts["ar"], "2026-07-31")
        require(
            at_july_end["account_totals"].get(AR_TYPE) == I2B_JULY_AR[3],
            "FIN07 July AR total must equal the partner ledger closing",
        )
        at_july_end_ap = independent_open_items(env, company, accounts["ap"], "2026-07-31")
        require(
            at_july_end_ap["account_totals"].get(AP_TYPE) == I2B_JULY_AP[3],
            "FIN07 July AP total must equal the partner ledger closing",
        )
        aging = models["id.finance.aged.partner.balance"]._snapshot(
            company.id, "2026-07-31", partner_type="customer",
        )
        require(aging["buckets"]["days_1_30"] == 28.0, "FIN08 July AR 30-day bucket mismatch")
        aging_ap = models["id.finance.aged.partner.balance"]._snapshot(
            company.id, "2026-07-31", partner_type="supplier",
        )
        require(aging_ap["buckets"]["days_1_30"] == -47.0, "FIN09 July AP 30-day bucket mismatch")
        require(
            models["id.finance.open.items"]._snapshot(
                company.id, "2026-07-31", partner_type="customer",
            )["gl_tie_out"]["balanced"],
            "FIN07 AR subledger must tie to the control GL",
        )
        require(
            models["id.finance.partner.ledger"]._snapshot(
                company.id, "2026-07-01", "2026-07-31", partner_type="all",
            )["by_account_type"][AP_TYPE]["closing_balance"] == -47.0,
            "FIN05/FIN06 all selection must keep AR and AP separate",
        )

    return company, accounts, journals, partner, scale, docs


def check_security(env, fixture_a, fixture_b, evidence):
    comp_a, acc_a, jnl_a, _partner_a, _scale_a, _docs_a = fixture_a
    comp_b, _acc_b, jnl_b, partner_b, _scale_b, _docs_b = fixture_b
    _reader_user, reader = sec.actor(
        env, "i2b.reader", comp_a, ["id_finance_foundation.group_finance_reader"],
    )
    _sales_user, sales = sec.actor(env, "i2b.sales", comp_a, ["sales_team.group_sale_salesman"])
    _driver_user, driver = sec.actor(env, "i2b.driver", comp_a, ["id_mobile_api.group_mobile_evidence"])
    calls = (
        ("id.finance.partner.ledger", lambda env_obj, cid: env_obj["id.finance.partner.ledger"]._snapshot(
            cid, "2026-07-01", "2026-07-31",
        )),
        ("id.finance.open.items", lambda env_obj, cid: env_obj["id.finance.open.items"]._snapshot(
            cid, "2026-07-31",
        )),
        ("id.finance.aged.partner.balance", lambda env_obj, cid: env_obj["id.finance.aged.partner.balance"]._snapshot(
            cid, "2026-07-31",
        )),
    )
    for label, callback in calls:
        callback(reader, comp_a.id)
        evidence["cases"].append({"case": f"reader_allowed_{label}", "result": "PASS"})
        evidence["counterexamples"].append(sec.denied(
            env, lambda cb=callback: cb(reader, comp_b.id), f"reader_foreign_company_{label}",
        ))
    evidence["counterexamples"].append(sec.denied(
        env,
        lambda: reader["id.finance.partner.ledger"]._snapshot(
            comp_a.id, "2026-07-01", "2026-07-31", journal_ids=[jnl_b["sale"].id],
        ),
        "reader_foreign_journal_fin05",
    ))
    evidence["counterexamples"].append(sec.denied(
        env,
        lambda: reader["id.finance.open.items"]._snapshot(
            comp_a.id, "2026-07-31", journal_ids=[jnl_b["sale"].id],
        ),
        "reader_foreign_journal_fin07",
    ))
    evidence["counterexamples"].append(sec.denied(
        env,
        lambda: reader["id.finance.aged.partner.balance"]._snapshot(
            comp_a.id, "2026-07-31", journal_ids=[jnl_b["sale"].id],
        ),
        "reader_foreign_journal_fin08",
    ))
    evidence["counterexamples"].append(sec.denied(
        env,
        lambda: reader["id.finance.partner.ledger"]._snapshot(
            comp_a.id, "2026-07-01", "2026-07-31", partner_ids=[partner_b.id],
        ),
        "reader_cross_company_partner",
    ))
    for role_label, role_env in (("sales", sales), ("driver", driver)):
        for label, callback in calls:
            evidence["counterexamples"].append(sec.denied(
                env, lambda cb=callback, e=role_env: cb(e, comp_a.id),
                f"{role_label}_denied_{label}",
            ))
    return reader


def check_tamper_and_unreconcile(env, fixture, evidence):
    company, accounts, journals, partner, scale, docs = fixture
    control = _control_accounts(env, company, accounts)
    models = env.with_context(allowed_company_ids=[company.id]).with_company(company)
    baseline_oracle = independent_open_items(env, company, control, "2026-07-31")
    baseline_ledger = independent_partner_ledger(
        env, company, control, "2026-07-01", "2026-07-31",
    )
    try:
        with env.cr.savepoint():
            golden.make_entry(
                env, (company, accounts, journals["general"], partner, scale),
                "i2b_tamper", "2026-07-30", {"ar": 9, "cash": -9},
            )
            checks = (
                ("FIN05/FIN06", lambda: assert_partner_ledger(
                    models["id.finance.partner.ledger"]._snapshot(
                        company.id, "2026-07-01", "2026-07-31", partner_type="all",
                    ),
                    baseline_ledger,
                )),
                ("FIN07", lambda: assert_open_items(
                    models["id.finance.open.items"]._snapshot(
                        company.id, "2026-07-31", partner_type="all",
                    ),
                    baseline_oracle,
                )),
                ("FIN08/FIN09", lambda: assert_aging(
                    models["id.finance.aged.partner.balance"]._snapshot(
                        company.id, "2026-07-31", partner_type="all",
                    ),
                    baseline_oracle, "2026-07-31",
                )),
            )
            for label, check in checks:
                try:
                    check()
                except AssertionError:
                    evidence["counterexamples"].append({
                        "case": f"tamper_rejected_{label}", "result": "REJECTED",
                    })
                else:
                    raise AssertionError(f"Tampered ledger unexpectedly accepted by {label}")
            raise RollbackI2b()
    except RollbackI2b:
        env.invalidate_all()

    after_rollback_ledger = independent_partner_ledger(
        env, company, control, "2026-07-01", "2026-07-31",
    )
    assert_partner_ledger(
        models["id.finance.partner.ledger"]._snapshot(
            company.id, "2026-07-01", "2026-07-31", partner_type="all",
        ),
        after_rollback_ledger,
    )
    evidence["counterexamples"].append({"case": "baseline_restored_after_tamper", "result": "PASS"})

    # Unreconcile probe: dated reconstruction must expose the reopened lines,
    # while the partner ledger control balance stays unchanged.
    try:
        with env.cr.savepoint():
            sec.control_line(docs["invoice"], accounts["ar"]).remove_move_reconcile()
            oracle = independent_open_items(env, company, accounts["ar"], "2026-07-31")
            snapshot = models["id.finance.open.items"]._snapshot(
                company.id, "2026-07-31", partner_type="customer",
            )
            assert_open_items(snapshot, oracle)
            require(
                len(oracle["rows"]) == 3,
                f"Unreconcile must reopen invoice, receipt and refund lines: {sorted(oracle['rows'])}",
            )
            require(
                oracle["total_residual"] == 28 * scale,
                "Unreconcile must preserve the AR control total",
            )
            evidence["counterexamples"].append({
                "case": "unreconcile_reopens_dated_lines", "result": "PASS",
            })
            raise RollbackI2b()
    except RollbackI2b:
        env.invalidate_all()
    require(docs["invoice"].amount_residual == 0, "Unreconcile rollback failed")

    # Counterexample: current amount_residual would report 0 for the 14 July
    # as-of query even though the invoice was still fully open then.
    as_of_oracle = independent_open_items(env, company, accounts["ar"], "2026-07-14")
    require(
        as_of_oracle["account_totals"].get(AR_TYPE) == 110 * scale,
        "Dated oracle must not use the current residual",
    )
    require(docs["invoice"].amount_residual == 0, "Fixture invoice must be settled now")
    evidence["counterexamples"].append({
        "case": "current_residual_would_report_0_instead_of_110", "result": "REJECTED",
    })


def run(env):
    require(
        env.cr.dbname == "finance_i0_reports_disposable",
        "I2b subledger verification requires exact disposable reports database",
    )
    for addon in ("account_financial_report", "id_finance_reporting", "id_finance_foundation"):
        require(
            env["ir.module.module"].search_count([
                ("name", "=", addon), ("state", "=", "installed"),
            ]) == 1,
            f"Required addon {addon} is not installed",
        )

    companies_before = set(env["res.company"].search([]).ids)
    users_before = set(env["res.users"].with_context(active_test=False).search([]).ids)
    evidence = {
        "scope": "I2b AR/AP subledger/open-items/aging disposable native oracle; not FIN01-58 acceptance",
        "reports_verified": ["FIN05", "FIN06", "FIN07", "FIN08", "FIN09"],
        "cases": [],
        "counterexamples": [],
    }

    try:
        with env.cr.savepoint():
            fix_a = i2a.build_i2a_fixture(env, "A", 1)
            fix_b = i2a.build_i2a_fixture(env, "B", 7)
            check_fixture(env, fix_a, evidence, check_hard_coded=True)
            evidence["cases"].append({"case": "scale_1_control_figures", "result": "PASS"})
            check_fixture(env, fix_b, evidence, check_hard_coded=False)
            evidence["cases"].append({"case": "scale_7_company_isolation", "result": "PASS"})
            check_security(env, fix_a, fix_b, evidence)
            check_tamper_and_unreconcile(env, fix_a, evidence)
            raise RollbackI2b()
    except RollbackI2b:
        env.invalidate_all()

    require(
        set(env["res.company"].search([]).ids) == companies_before,
        "Company fixture leaked in I2b",
    )
    require(
        set(env["res.users"].with_context(active_test=False).search([]).ids) == users_before,
        "User fixture leaked in I2b",
    )
    evidence["fixture_rollback"] = "PASS"
    print("FINANCE_I2B_ARAP_SUBLEDGER=" + json.dumps(evidence, sort_keys=True))
    print("FINANCE_I2B_ARAP_SUBLEDGER=PASS")
    return evidence


if "env" in globals():
    run(globals()["env"])
