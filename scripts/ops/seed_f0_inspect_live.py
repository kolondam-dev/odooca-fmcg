#!/usr/bin/env python3
"""seed_f0_inspect_live.py - Read-only live database inspection for Phase F0.

Connects to Postgres using standard PG* variables with default_transaction_read_only=on.
Gathers inventory, accounting, and transactional state for F0 preflight.
"""

import json
import os
import sys

def inspect():
    try:
        import psycopg2
    except ImportError:
        print("psycopg2 is required", file=sys.stderr)
        sys.exit(1)

    host = os.environ.get("RAILWAY_TCP_PROXY_DOMAIN") or os.environ.get("GEO_PG_HOST") or os.environ.get("PGHOST")
    port = int(os.environ.get("RAILWAY_TCP_PROXY_PORT") or os.environ.get("GEO_PG_PORT") or os.environ.get("PGPORT", 5432))
    user = os.environ.get("PGUSER", "postgres")
    password = os.environ.get("PGPASSWORD", "")
    dbname = os.environ.get("PGDATABASE", "railway")

    conn = psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=dbname,
        sslmode="require",
        options="-c default_transaction_read_only=on -c statement_timeout=60000",
    )
    cur = conn.cursor()

    report = {}

    # 1. Company
    cur.execute("SELECT id, name, active, currency_id FROM res_company ORDER BY id")
    report["companies"] = [{"id": r[0], "name": r[1], "active": r[2], "currency_id": r[3]} for r in cur.fetchall()]

    # 2. Sale Orders
    cur.execute("""
        SELECT
            CASE
                WHEN client_order_ref LIKE 'SO-202607-%' THEN 'canonical_july'
                WHEN client_order_ref IS NULL THEN 'null_ref'
                ELSE 'other'
            END as category,
            count(*),
            min(date_order),
            max(date_order),
            sum(amount_untaxed),
            sum(amount_total)
        FROM sale_order
        GROUP BY 1
    """)
    report["sale_orders_by_ref"] = [
        {"category": r[0], "count": r[1], "min_date": str(r[2]), "max_date": str(r[3]), "amount_untaxed": float(r[4] or 0), "amount_total": float(r[5] or 0)}
        for r in cur.fetchall()
    ]

    cur.execute("""
        SELECT so.id, so.name, so.client_order_ref, so.date_order, so.state, so.amount_untaxed, so.amount_total, rp.name as partner_name, ru.login as user_login
        FROM sale_order so
        LEFT JOIN res_partner rp ON rp.id = so.partner_id
        LEFT JOIN res_users ru ON ru.id = so.user_id
        WHERE so.client_order_ref NOT LIKE 'SO-202607-%' OR so.client_order_ref IS NULL
        ORDER BY so.id
    """)
    report["extra_sale_orders"] = [
        {
            "id": r[0],
            "name": r[1],
            "client_order_ref": r[2],
            "date_order": str(r[3]),
            "state": r[4],
            "amount_untaxed": float(r[5] or 0),
            "amount_total": float(r[6] or 0),
            "partner_name": r[7],
            "user_login": r[8],
        }
        for r in cur.fetchall()
    ]

    # Check order lines of extra sale orders
    if report["extra_sale_orders"]:
        extra_ids = tuple(x["id"] for x in report["extra_sale_orders"])
        cur.execute("""
            SELECT sol.order_id, pt.name, sol.product_uom_qty, sol.price_unit, sol.price_subtotal
            FROM sale_order_line sol
            JOIN product_product pp ON pp.id = sol.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE sol.order_id IN %s
        """, (extra_ids,))
        report["extra_sale_order_lines"] = [
            {"order_id": r[0], "product": r[1], "qty": float(r[2]), "price_unit": float(r[3]), "subtotal": float(r[4])}
            for r in cur.fetchall()
        ]

    # 3. Purchase Orders
    cur.execute("""
        SELECT po.id, po.name, po.partner_ref, rp.name as vendor_name, po.date_order, po.state, po.amount_untaxed, po.amount_total
        FROM purchase_order po
        LEFT JOIN res_partner rp ON rp.id = po.partner_id
        ORDER BY po.id
    """)
    report["purchase_orders"] = [
        {"id": r[0], "name": r[1], "partner_ref": r[2], "vendor_name": r[3], "date_order": str(r[4]), "state": r[5], "amount_untaxed": float(r[6] or 0), "amount_total": float(r[7] or 0)}
        for r in cur.fetchall()
    ]

    # 4. Stock Quants & Locations
    cur.execute("""
        SELECT sl.complete_name, sl.usage, count(sq.id), sum(sq.quantity), sum(sq.reserved_quantity)
        FROM stock_quant sq
        JOIN stock_location sl ON sl.id = sq.location_id
        WHERE sq.quantity != 0 OR sq.reserved_quantity != 0
        GROUP BY sl.complete_name, sl.usage
        ORDER BY sl.complete_name
    """)
    report["stock_by_location"] = [
        {"location": r[0], "usage": r[1], "quant_count": r[2], "total_qty": float(r[3] or 0), "total_reserved": float(r[4] or 0)}
        for r in cur.fetchall()
    ]

    # Check WH/Stock total quantity
    cur.execute("""
        SELECT sum(sq.quantity), sum(sq.reserved_quantity), count(DISTINCT sq.product_id), count(DISTINCT sq.lot_id)
        FROM stock_quant sq
        JOIN stock_location sl ON sl.id = sq.location_id
        WHERE sl.complete_name = 'WH/Stock'
    """)
    r = cur.fetchone()
    report["wh_stock_totals"] = {
        "quantity": float(r[0] or 0),
        "reserved_quantity": float(r[1] or 0),
        "distinct_products": r[2],
        "distinct_lots": r[3],
    }

    # 5. Invoices / Account Moves
    cur.execute("""
        SELECT move_type, state, count(*), sum(amount_untaxed), sum(amount_total)
        FROM account_move
        GROUP BY move_type, state
        ORDER BY move_type, state
    """)
    report["account_moves_summary"] = [
        {"move_type": r[0], "state": r[1], "count": r[2], "amount_untaxed": float(r[3] or 0), "amount_total": float(r[4] or 0)}
        for r in cur.fetchall()
    ]

    # Check non-canonical account moves
    cur.execute("""
        SELECT id, name, move_type, date, state, amount_untaxed, amount_total
        FROM account_move
        WHERE name NOT LIKE 'INV-202607-%'
          AND name NOT LIKE 'BILL/2026/%'
          AND name NOT LIKE 'MISC/%'
          AND name NOT LIKE 'STJ/%'
          AND name NOT LIKE 'CSH1/%'
          AND name NOT LIKE 'BNK1/%'
        ORDER BY id
        LIMIT 20
    """)
    report["sample_other_account_moves"] = [
        {"id": r[0], "name": r[1], "move_type": r[2], "date": str(r[3]), "state": r[4], "amount_untaxed": float(r[5] or 0), "amount_total": float(r[6] or 0)}
        for r in cur.fetchall()
    ]

    # 6. Cash & Bank Accounts Balance via Journals
    cur.execute("""
        SELECT aj.id, aj.name, aj.code, aj.type, aj.default_account_id, aa.name as account_name,
               coalesce(sum(aml.debit), 0) as total_debit,
               coalesce(sum(aml.credit), 0) as total_credit,
               coalesce(sum(aml.balance), 0) as total_balance
        FROM account_journal aj
        JOIN account_account aa ON aa.id = aj.default_account_id
        LEFT JOIN account_move_line aml ON aml.account_id = aa.id
        LEFT JOIN account_move am ON am.id = aml.move_id AND am.state = 'posted'
        WHERE aj.type IN ('cash', 'bank')
        GROUP BY aj.id, aj.name, aj.code, aj.type, aj.default_account_id, aa.name
        ORDER BY aj.id
    """)
    report["cash_bank_balances"] = [
        {
            "journal_id": r[0],
            "journal_name": r[1],
            "journal_code": r[2],
            "type": r[3],
            "account_id": r[4],
            "account_name": str(r[5]),
            "debit": float(r[6]),
            "credit": float(r[7]),
            "balance": float(r[8]),
        }
        for r in cur.fetchall()
    ]

    # 6b. AR Open Residuals
    cur.execute("""
        SELECT
            count(*) as open_invoice_count,
            sum(amount_untaxed) as open_untaxed,
            sum(amount_total) as open_total,
            sum(amount_residual) as open_residual
        FROM account_move
        WHERE move_type = 'out_invoice' AND state = 'posted' AND payment_state IN ('not_paid', 'partial')
    """)
    r = cur.fetchone()
    report["ar_open_summary"] = {
        "open_invoice_count": r[0],
        "open_untaxed": float(r[1] or 0),
        "open_total": float(r[2] or 0),
        "open_residual": float(r[3] or 0),
    }

    # 6c. AP Open Residuals
    cur.execute("""
        SELECT
            count(*) as open_bill_count,
            sum(amount_untaxed) as open_untaxed,
            sum(amount_total) as open_total,
            sum(amount_residual) as open_residual
        FROM account_move
        WHERE move_type = 'in_invoice' AND state = 'posted' AND payment_state IN ('not_paid', 'partial')
    """)
    r = cur.fetchone()
    report["ap_open_summary"] = {
        "open_bill_count": r[0],
        "open_untaxed": float(r[1] or 0),
        "open_total": float(r[2] or 0),
        "open_residual": float(r[3] or 0),
    }

    # 6d. Payments Count and Totals
    cur.execute("""
        SELECT payment_type, state, count(*), sum(amount)
        FROM account_payment
        GROUP BY payment_type, state
    """)
    report["payments_summary"] = [
        {"payment_type": r[0], "state": r[1], "count": r[2], "total_amount": float(r[3] or 0)}
        for r in cur.fetchall()
    ]

    # 7. Total Journal Items (AML) count
    cur.execute("SELECT count(*) FROM account_move_line")
    report["total_aml_count"] = cur.fetchone()[0]

    # 8. Taxes
    cur.execute("""
        SELECT id, name, type_tax_use, amount, amount_type, active
        FROM account_tax
        WHERE active = true
        ORDER BY type_tax_use, id
    """)
    report["active_taxes"] = [
        {"id": r[0], "name": r[1], "type_tax_use": r[2], "amount": float(r[3]), "amount_type": r[4], "active": r[5]}
        for r in cur.fetchall()
    ]

    # 9. Stock Picking summary
    cur.execute("""
        SELECT picking_type_id, state, count(*)
        FROM stock_picking
        GROUP BY picking_type_id, state
        ORDER BY picking_type_id, state
    """)
    report["pickings_summary"] = [
        {"picking_type_id": r[0], "state": r[1], "count": r[2]}
        for r in cur.fetchall()
    ]

    # 10. Marks
    cur.execute("SELECT name, at FROM id_meta.marks ORDER BY at")
    report["marks"] = [{"name": r[0], "at": str(r[1])} for r in cur.fetchall()]

    out_path = os.path.join(os.path.dirname(__file__), "seed_f0_live_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Report written to {out_path} ({len(json.dumps(report))} bytes)")

if __name__ == "__main__":
    inspect()
