"""Pure AR/AP subledger helpers for I2b, without ORM.

The production reports collect native ``account.move.line`` records and
``account.partial.reconcile`` records, then hand plain dictionaries to these
functions. Keeping the arithmetic here makes the oracle testable without a
database and prevents the report layer from silently falling back to current
residual balances when a historical as-of balance is requested.
"""

from collections import defaultdict
from datetime import date

AR_TYPE = "asset_receivable"
AP_TYPE = "liability_payable"
PARTNER_TYPES = {
    "customer": (AR_TYPE,),
    "supplier": (AP_TYPE,),
    "all": (AR_TYPE, AP_TYPE),
}
AGING_EDGES = (30, 60, 90, 120)


def _as_date(value):
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    return None


def resolve_partner_types(partner_type):
    """Return the control account types for a partner-ledger selection."""
    try:
        return PARTNER_TYPES[partner_type]
    except KeyError as exc:
        raise ValueError(
            f"Invalid partner type {partner_type!r}; choose customer, supplier or all."
        ) from exc


def _partner_key(partner_id, account_type):
    return partner_id or 0, account_type


def _initial_row(partner_id, partner_name, account_type):
    return {
        "partner_id": partner_id or 0,
        "partner_name": partner_name or "",
        "partnerless": not partner_id,
        "account_type": account_type,
        "opening_balance": 0.0,
        "debit": 0.0,
        "credit": 0.0,
        "movement_balance": 0.0,
        "closing_balance": 0.0,
        "line_ids": [],
        "move_ids": [],
    }


def build_partner_ledger(lines, date_from, date_to, round_amount, partner_types=(AR_TYPE, AP_TYPE)):
    """Aggregate posted control-account lines into opening/movement/closing rows.

    ``lines`` are plain dictionaries with ``date``, ``partner_id``,
    ``partner_name``, ``account_type``, ``debit``, ``credit``, ``balance``,
    ``line_id`` and ``move_id``. Rows are grouped by partner *and* account type
    so an ``all`` selection never nets receivable against payable.
    """
    start, end = _as_date(date_from), _as_date(date_to)
    if not start or not end or start > end:
        raise ValueError("Partner ledger requires an ordered period.")
    wanted = set(partner_types)
    rows = {}
    for line in lines:
        account_type = line.get("account_type")
        if account_type not in wanted:
            continue
        line_date = _as_date(line.get("date"))
        if not line_date or line_date > end:
            continue
        key = _partner_key(line.get("partner_id"), account_type)
        row = rows.setdefault(
            key,
            _initial_row(line.get("partner_id"), line.get("partner_name"), account_type),
        )
        if line.get("partner_name") and not row["partner_name"]:
            row["partner_name"] = line["partner_name"]
        if line_date < start:
            row["opening_balance"] = round_amount(row["opening_balance"] + line.get("balance", 0.0))
            continue
        row["debit"] = round_amount(row["debit"] + line.get("debit", 0.0))
        row["credit"] = round_amount(row["credit"] + line.get("credit", 0.0))
        row["movement_balance"] = round_amount(row["movement_balance"] + line.get("balance", 0.0))
        if line.get("line_id") is not None:
            row["line_ids"].append(line["line_id"])
        if line.get("move_id") is not None and line["move_id"] not in row["move_ids"]:
            row["move_ids"].append(line["move_id"])
    for row in rows.values():
        row["closing_balance"] = round_amount(
            row["opening_balance"] + row["movement_balance"]
        )
        row["line_ids"] = sorted(set(row["line_ids"]))
        row["move_ids"] = sorted(set(row["move_ids"]))
        row["line_count"] = len(row["line_ids"])
    ordered = sorted(
        rows.values(),
        key=lambda row: (
            row["account_type"],
            row["partner_id"] != 0,
            (row["partner_name"] or "").lower(),
            row["partner_id"],
        ),
    )
    totals = {
        "opening_balance": round_amount(sum(row["opening_balance"] for row in ordered)),
        "debit": round_amount(sum(row["debit"] for row in ordered)),
        "credit": round_amount(sum(row["credit"] for row in ordered)),
        "movement_balance": round_amount(sum(row["movement_balance"] for row in ordered)),
        "closing_balance": round_amount(sum(row["closing_balance"] for row in ordered)),
        "partner_count": len({row["partner_id"] for row in ordered}),
    }
    by_account_type = {}
    for account_type in sorted(wanted):
        type_rows = [row for row in ordered if row["account_type"] == account_type]
        by_account_type[account_type] = {
            "opening_balance": round_amount(sum(row["opening_balance"] for row in type_rows)),
            "debit": round_amount(sum(row["debit"] for row in type_rows)),
            "credit": round_amount(sum(row["credit"] for row in type_rows)),
            "closing_balance": round_amount(sum(row["closing_balance"] for row in type_rows)),
        }
    return {
        "rows": ordered,
        "totals": totals,
        "by_account_type": by_account_type,
    }


def reconstruct_open_items(lines, partials, as_of, round_amount, partner_types=(AR_TYPE, AP_TYPE)):
    """Reconstruct open residuals from dated partial reconciliations.

    A matched amount only reduces a line when ``partial.max_date <= as_of``.
    That is the key difference from reading the current ``amount_residual``:
    a payment received after the as-of date must not close an invoice early.

    A partial is only consumed when *both* legs are part of ``lines``. Callers
    may pass a filtered slice (journal, partner or start date); a counterpart
    outside that slice must not silently settle a line, otherwise the residual
    total and the control-account total would describe different scopes. With
    this rule the matched amounts always cancel, so ``total_residual`` equals
    the summed balance of the selected lines.
    """
    cutoff = _as_date(as_of)
    if not cutoff:
        raise ValueError("Open items require an as-of date.")
    wanted = set(partner_types)
    selected = {}
    for line in lines:
        if line.get("account_type") not in wanted:
            continue
        line_date = _as_date(line.get("date"))
        if not line_date or line_date > cutoff:
            continue
        selected[line.get("line_id")] = line
    matched = defaultdict(float)
    matched_partials = defaultdict(list)
    for partial in partials:
        max_date = _as_date(partial.get("max_date"))
        if not max_date or max_date > cutoff:
            continue
        amount = partial.get("amount") or 0.0
        debit_id = partial.get("debit_line_id")
        credit_id = partial.get("credit_line_id")
        if debit_id not in selected or credit_id not in selected:
            continue
        matched[debit_id] = round_amount(matched[debit_id] - amount)
        matched_partials[debit_id].append(partial.get("partial_id"))
        matched[credit_id] = round_amount(matched[credit_id] + amount)
        matched_partials[credit_id].append(partial.get("partial_id"))
    rows = []
    closed_line_ids = []
    for line_id, line in selected.items():
        balance = line.get("balance", 0.0)
        residual = round_amount(balance + matched.get(line_id, 0.0))
        if residual == 0:
            closed_line_ids.append(line_id)
            continue
        due_date = _as_date(line.get("due_date")) or _as_date(line.get("date"))
        rows.append({
            "line_id": line_id,
            "move_id": line.get("move_id"),
            "move_name": line.get("move_name") or "",
            "date": _as_date(line.get("date")).isoformat(),
            "due_date": due_date.isoformat() if due_date else None,
            "partner_id": line.get("partner_id") or 0,
            "partner_name": line.get("partner_name") or "",
            "partnerless": not line.get("partner_id"),
            "account_id": line.get("account_id"),
            "account_code": line.get("account_code") or "",
            "account_type": line.get("account_type"),
            "balance": round_amount(balance),
            "matched_amount": round_amount(matched.get(line_id, 0.0)),
            "residual": residual,
            "debit": round_amount(line.get("debit", 0.0)),
            "credit": round_amount(line.get("credit", 0.0)),
            "currency_id": line.get("currency_id"),
            "amount_currency": line.get("amount_currency", 0.0),
            "matched_partial_ids": sorted(set(matched_partials.get(line_id, []))),
        })
    rows.sort(key=lambda row: (row["date"], row["line_id"]))
    partner_rows = {}
    account_totals = defaultdict(float)
    for row in rows:
        key = _partner_key(row["partner_id"], row["account_type"])
        partner = partner_rows.setdefault(key, {
            "partner_id": row["partner_id"],
            "partner_name": row["partner_name"],
            "partnerless": row["partnerless"],
            "account_type": row["account_type"],
            "residual": 0.0,
            "line_ids": [],
        })
        if row["partner_name"] and not partner["partner_name"]:
            partner["partner_name"] = row["partner_name"]
        partner["residual"] = round_amount(partner["residual"] + row["residual"])
        partner["line_ids"].append(row["line_id"])
        account_totals[row["account_type"]] = round_amount(
            account_totals[row["account_type"]] + row["residual"]
        )
    partners = sorted(
        partner_rows.values(),
        key=lambda row: (
            row["account_type"],
            row["partner_id"] != 0,
            (row["partner_name"] or "").lower(),
            row["partner_id"],
        ),
    )
    for partner in partners:
        partner["line_count"] = len(partner["line_ids"])
        partner["line_ids"] = sorted(partner["line_ids"])
    total_residual = round_amount(sum(row["residual"] for row in rows))
    return {
        "rows": rows,
        "partners": partners,
        "account_totals": [
            {"account_type": account_type, "residual": account_totals[account_type]}
            for account_type in sorted(account_totals)
        ],
        "total_residual": total_residual,
        "partnerless_residual": round_amount(
            sum(row["residual"] for row in rows if row["partnerless"])
        ),
        "partnerless_line_ids": sorted(row["line_id"] for row in rows if row["partnerless"]),
        "closed_line_ids": sorted(closed_line_ids),
        "line_count": len(rows),
    }


def bucket_for_due_date(due_date, as_of, edges=AGING_EDGES):
    """Return the signed-aging bucket name for a single due date."""
    cutoff = _as_date(as_of)
    if not cutoff:
        raise ValueError("Aging requires an as-of date.")
    due = _as_date(due_date)
    if not due or due >= cutoff:
        return "current"
    days = (cutoff - due).days
    previous = 0
    for edge in edges:
        if days <= edge:
            return f"days_{previous + 1}_{edge}"
        previous = edge
    return "older"


def _bucket_names(edges):
    names = ["current"]
    previous = 0
    for edge in edges:
        names.append(f"days_{previous + 1}_{edge}")
        previous = edge
    names.append("older")
    return names


def build_aging(open_items, as_of, round_amount, edges=AGING_EDGES):
    """Bucket open residuals by due date while preserving receivable/payable sign."""
    rows = open_items["rows"] if isinstance(open_items, dict) else list(open_items)
    total_residual = (
        open_items["total_residual"]
        if isinstance(open_items, dict)
        else round_amount(sum(row["residual"] for row in rows))
    )
    names = _bucket_names(edges)
    buckets = {name: 0.0 for name in names}
    partner_rows = {}
    account_totals = defaultdict(float)
    detail = []
    for row in rows:
        bucket = bucket_for_due_date(row.get("due_date") or row.get("date"), as_of, edges)
        residual = row["residual"]
        buckets[bucket] = round_amount(buckets[bucket] + residual)
        account_totals[row["account_type"]] = round_amount(
            account_totals[row["account_type"]] + residual
        )
        key = _partner_key(row["partner_id"], row["account_type"])
        partner = partner_rows.setdefault(key, {
            "partner_id": row["partner_id"],
            "partner_name": row.get("partner_name") or "",
            "partnerless": row.get("partnerless", not row["partner_id"]),
            "account_type": row["account_type"],
            "residual": 0.0,
            "buckets": {name: 0.0 for name in names},
            "line_ids": [],
        })
        partner["residual"] = round_amount(partner["residual"] + residual)
        partner["buckets"][bucket] = round_amount(partner["buckets"][bucket] + residual)
        partner["line_ids"].append(row["line_id"])
        detail.append({**row, "bucket": bucket})
    partners = sorted(
        partner_rows.values(),
        key=lambda row: (
            row["account_type"],
            row["partner_id"] != 0,
            (row["partner_name"] or "").lower(),
            row["partner_id"],
        ),
    )
    for partner in partners:
        partner["line_count"] = len(partner["line_ids"])
        partner["line_ids"] = sorted(partner["line_ids"])
    bucket_sum = round_amount(sum(buckets.values()))
    difference = round_amount(bucket_sum - total_residual)
    return {
        "bucket_order": names,
        "edges": list(edges),
        "buckets": buckets,
        "partners": partners,
        "account_totals": [
            {"account_type": account_type, "residual": account_totals[account_type]}
            for account_type in sorted(account_totals)
        ],
        "rows": detail,
        "total_residual": round_amount(total_residual),
        "bucket_sum": bucket_sum,
        "unexplained_difference": difference,
        "balanced": difference == 0,
    }


def tie_subledger_to_gl(subledger_total, gl_control_total, round_amount, label="control"):
    """Compare a subledger total with the control-account GL total."""
    subledger_total = round_amount(subledger_total)
    gl_control_total = round_amount(gl_control_total)
    difference = round_amount(subledger_total - gl_control_total)
    return {
        "subledger_total": subledger_total,
        "gl_control_total": gl_control_total,
        "difference": difference,
        "balanced": difference == 0,
        "issues": [] if difference == 0 else [f"{label}_mismatch"],
    }
