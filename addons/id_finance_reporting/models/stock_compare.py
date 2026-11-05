"""Compare the union of stock-move and mapped-account GL keys, without ORM."""

from collections import defaultdict


def compare_stock_gl(expected, lines, stock_accounts, round_amount):
    """lines: (line ID, account ID, product ID or False, signed balance).

    A linked journal is not proof that every stock GL key has a stock move.
    Preserve unmatched keys even when their GL lines net to zero.
    """
    mapped_accounts = set(stock_accounts) | {key[0] for key in expected}
    actual = defaultdict(float)
    line_ids = defaultdict(list)
    for line_id, account_id, product_id, balance in lines:
        if account_id not in mapped_accounts:
            continue
        key = (account_id, product_id)
        actual[key] += balance
        line_ids[key].append(line_id)
    rows = []
    for key in sorted(set(expected) | set(actual)):
        issues = []
        if key not in expected:
            issues.append("gl_without_stock_move")
        if key not in actual:
            issues.append("stock_move_without_gl")
        value, balance = expected.get(key, 0), actual.get(key, 0)
        rows.append({"account_id": key[0], "product_id": key[1], "move_value_signed": value,
                     "gl_balance": balance, "difference": round_amount(balance - value),
                     "gl_line_ids": line_ids.get(key, []), "issues": issues})
    return rows
