"""Pure comparison and aggregation helpers for I2a ledgers, without ORM."""

from collections import defaultdict

REGISTER_TYPES = ("out_invoice", "out_refund", "in_invoice", "in_refund")


def _resolve_coa_target(company_id, row, account_map):
    code = (row.get("code") or "").strip()
    name = (row.get("name") or "").strip()
    acc_type = (row.get("account_type") or "").strip()
    if not code or not name or not acc_type:
        raise ValueError(
            "Combined Trial Balance requires non-empty code, name, and account_type on every row."
        )
    if account_map is None:
        return code, name, acc_type
    mapped = account_map.get((company_id, code)) or account_map.get(code)
    if not mapped:
        raise ValueError(f"Missing explicit COA mapping for company {company_id} account {code}.")
    if isinstance(mapped, dict):
        target_code = (mapped.get("code") or "").strip()
        target_name = (mapped.get("name") or "").strip()
        target_type = (mapped.get("account_type") or "").strip()
    else:
        target_code, target_name, target_type = (str(part).strip() for part in mapped)
    if not target_code or not target_name or not target_type:
        raise ValueError(f"Incomplete explicit COA mapping for account {code}.")
    if target_type != acc_type:
        raise ValueError(
            f"Cross-company COA mapping for code {code} cannot change account_type "
            f"({acc_type!r} -> {target_type!r})."
        )
    return target_code, target_name, target_type


def combine_trial_balances(entities, round_amount, account_map=None):
    """Combine translated entity Trial Balances without intercompany eliminations.

    entities: list of dicts with company_id, company_name, currency_id,
    currency_name, rate_to_presentation, rate_date, rows (list of dicts with
    account_id, code, name, account_type, initial_balance, debit, credit,
    balance, ending_balance).
    """
    if not entities:
        raise ValueError("Combined Trial Balance requires at least one entity.")
    by_code = {}
    entity_summaries = []
    for entity in entities:
        rate = entity["rate_to_presentation"]
        if rate <= 0:
            raise ValueError("Conversion rate must be positive.")
        ent_debit = ent_credit = ent_init = ent_end = 0.0
        translated_rows = []
        for row in sorted(entity["rows"], key=lambda item: (item["code"], item["account_id"])):
            target_code, target_name, target_type = _resolve_coa_target(
                entity["company_id"], row, account_map,
            )
            init_bal = round_amount(row["initial_balance"] * rate)
            debit = round_amount(row["debit"] * rate)
            credit = round_amount(row["credit"] * rate)
            balance = round_amount(debit - credit)
            end_bal = round_amount(init_bal + balance)
            ent_init = round_amount(ent_init + init_bal)
            ent_debit = round_amount(ent_debit + debit)
            ent_credit = round_amount(ent_credit + credit)
            ent_end = round_amount(ent_end + end_bal)
            translated_rows.append({
                "account_id": row["account_id"],
                "code": row["code"],
                "name": row["name"],
                "account_type": row.get("account_type"),
                "functional_initial_balance": row["initial_balance"],
                "functional_debit": row["debit"],
                "functional_credit": row["credit"],
                "functional_balance": row["balance"],
                "functional_ending_balance": row["ending_balance"],
                "translated_initial_balance": init_bal,
                "translated_debit": debit,
                "translated_credit": credit,
                "translated_balance": balance,
                "translated_ending_balance": end_bal,
            })
            if target_code in by_code:
                slot = by_code[target_code]
                if (slot["name"], slot["account_type"]) != (target_name, target_type):
                    raise ValueError(
                        f"Ambiguous cross-company COA mapping for code {target_code}: "
                        f"({slot['name']!r}, {slot['account_type']!r}) vs "
                        f"({target_name!r}, {target_type!r})."
                    )
                if entity["company_id"] in slot["entity_breakdown"]:
                    raise ValueError(
                        f"Duplicate account mapping for company {entity['company_id']} "
                        f"on code {target_code}."
                    )
            else:
                slot = by_code.setdefault(target_code, {
                    "code": target_code,
                    "name": target_name,
                    "account_type": target_type,
                    "initial_balance": 0.0,
                    "debit": 0.0,
                    "credit": 0.0,
                    "balance": 0.0,
                    "ending_balance": 0.0,
                    "entity_breakdown": {},
                })
            slot["initial_balance"] = round_amount(slot["initial_balance"] + init_bal)
            slot["debit"] = round_amount(slot["debit"] + debit)
            slot["credit"] = round_amount(slot["credit"] + credit)
            slot["balance"] = round_amount(slot["balance"] + balance)
            slot["ending_balance"] = round_amount(slot["ending_balance"] + end_bal)
            slot["entity_breakdown"][entity["company_id"]] = {
                "account_id": row["account_id"],
                "functional_currency_id": entity["currency_id"],
                "rate_to_presentation": rate,
                "functional_ending_balance": row["ending_balance"],
                "translated_initial_balance": init_bal,
                "translated_debit": debit,
                "translated_credit": credit,
                "translated_balance": balance,
                "translated_ending_balance": end_bal,
            }
        entity_summaries.append({
            "company_id": entity["company_id"],
            "company_name": entity["company_name"],
            "functional_currency_id": entity["currency_id"],
            "functional_currency_name": entity["currency_name"],
            "rate_to_presentation": rate,
            "rate_date": entity["rate_date"],
            "rate_source": entity.get("rate_source", "res.currency._get_conversion_rate"),
            "translated_initial_balance": ent_init,
            "translated_debit": ent_debit,
            "translated_credit": ent_credit,
            "translated_ending_balance": ent_end,
            "rows": translated_rows,
        })
    combined_rows = [by_code[code] for code in sorted(by_code)]
    return {
        "scope": "combined_multi_entity_trial_balance_not_consolidated",
        "eliminations_applied": False,
        "entities": entity_summaries,
        "combined_rows": combined_rows,
        "totals": {
            "initial_balance": round_amount(sum(r["initial_balance"] for r in combined_rows)),
            "debit": round_amount(sum(r["debit"] for r in combined_rows)),
            "credit": round_amount(sum(r["credit"] for r in combined_rows)),
            "balance": round_amount(sum(r["balance"] for r in combined_rows)),
            "ending_balance": round_amount(sum(r["ending_balance"] for r in combined_rows)),
        },
    }


def reconcile_register_to_gl(documents, gl_lines, tracked_accounts, round_amount):
    """Tie invoice/bill/refund register lines to GL without duplicate lines.

    documents: list of dicts with move_id, move_name, move_type, date,
    partner_id, state, lines (list of dicts: line_id, account_id,
    display_type, tax_line_id, tax_ids, debit, credit, balance).
    gl_lines: list of tuples (line_id, move_id, account_id, balance) for all
    posted GL lines in period on tracked_accounts.
    """
    seen_moves = set()
    seen_lines = set()
    duplicate_move_ids = []
    duplicate_line_ids = []
    doc_rows = []
    register_by_account = defaultdict(float)
    register_line_ids_by_account = defaultdict(list)

    for doc in sorted(documents, key=lambda item: (str(item["date"]), item["move_id"])):
        move_id = doc["move_id"]
        move_type = doc["move_type"]
        if move_type not in REGISTER_TYPES:
            continue
        if move_id in seen_moves:
            duplicate_move_ids.append(move_id)
            continue
        seen_moves.add(move_id)
        base_balance = 0.0
        tax_balance = 0.0
        control_balance = 0.0
        doc_line_ids = []
        for line in doc["lines"]:
            line_id = line["line_id"]
            if line_id in seen_lines:
                duplicate_line_ids.append(line_id)
                continue
            seen_lines.add(line_id)
            doc_line_ids.append(line_id)
            acc_id = line["account_id"]
            bal = line["balance"]
            if acc_id in tracked_accounts:
                register_by_account[acc_id] = round_amount(register_by_account[acc_id] + bal)
                register_line_ids_by_account[acc_id].append(line_id)
            dtype = line.get("display_type") or "product"
            if dtype == "tax" or line.get("tax_line_id"):
                tax_balance = round_amount(tax_balance + bal)
            elif dtype == "payment_term" or line.get("is_control"):
                control_balance = round_amount(control_balance + bal)
            else:
                base_balance = round_amount(base_balance + bal)
        is_sale = move_type in ("out_invoice", "out_refund")
        doc_rows.append({
            "move_id": move_id,
            "move_name": doc["move_name"],
            "move_type": move_type,
            "category": "sale" if is_sale else "purchase",
            "date": str(doc["date"]),
            "invoice_date": str(doc.get("invoice_date") or doc["date"]),
            "partner_id": doc["partner_id"],
            "state": doc["state"],
            "base_balance_gl": base_balance,
            "tax_balance_gl": tax_balance,
            "control_balance_gl": control_balance,
            "net_signed_amount": round_amount(-base_balance if is_sale else base_balance),
            "tax_signed_amount": round_amount(-tax_balance if is_sale else tax_balance),
            "gross_signed_amount": round_amount(control_balance if is_sale else -control_balance),
            "aml_ids": sorted(doc_line_ids),
        })

    gl_by_account = defaultdict(float)
    gl_lines_by_account = defaultdict(list)
    non_register_gl_lines = []
    for line_id, move_id, account_id, balance in gl_lines:
        if account_id not in tracked_accounts:
            continue
        gl_by_account[account_id] = round_amount(gl_by_account[account_id] + balance)
        gl_lines_by_account[account_id].append(line_id)
        if line_id not in seen_lines:
            non_register_gl_lines.append({
                "line_id": line_id,
                "move_id": move_id,
                "account_id": account_id,
                "balance": round_amount(balance),
            })

    tie_out_rows = []
    for account_id in sorted(set(tracked_accounts) | set(register_by_account) | set(gl_by_account)):
        reg_bal = round_amount(register_by_account.get(account_id, 0.0))
        gl_bal = round_amount(gl_by_account.get(account_id, 0.0))
        non_reg_bal = round_amount(sum(
            item["balance"] for item in non_register_gl_lines if item["account_id"] == account_id
        ))
        unexplained = round_amount(gl_bal - reg_bal - non_reg_bal)
        issues = []
        if non_reg_bal or any(item["account_id"] == account_id for item in non_register_gl_lines):
            issues.append("non_register_gl_activity")
        if unexplained:
            issues.append("unexplained_register_gl_difference")
        tie_out_rows.append({
            "account_id": account_id,
            "register_balance": reg_bal,
            "gl_balance": gl_bal,
            "non_register_gl_balance": non_reg_bal,
            "unexplained_difference": unexplained,
            "register_line_ids": sorted(register_line_ids_by_account.get(account_id, [])),
            "gl_line_ids": sorted(gl_lines_by_account.get(account_id, [])),
            "issues": issues,
        })

    return {
        "documents": doc_rows,
        "duplicate_move_ids": duplicate_move_ids,
        "duplicate_line_ids": duplicate_line_ids,
        "non_register_gl_lines": non_register_gl_lines,
        "gl_tie_out": tie_out_rows,
    }
