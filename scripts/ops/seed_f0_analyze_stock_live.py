#!/usr/bin/env python3
"""seed_f0_analyze_stock_live.py - Deep stock & picking inspection on live DB."""

import json
import os
import psycopg2

def main():
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

    # 1. Picking dates
    cur.execute("""
        SELECT date_done::date, state, count(*)
        FROM stock_picking
        WHERE picking_type_id = 2
        GROUP BY 1, 2
        ORDER BY 1 NULLS LAST
    """)
    pickings = [{"date": str(r[0]), "state": r[1], "count": r[2]} for r in cur.fetchall()]

    # 2. Check 48 carry-forward pickings
    cur.execute("""
        SELECT sp.id, sp.name, sp.origin, sp.date_done, sp.state
        FROM stock_picking sp
        WHERE sp.date_done >= '2026-08-01' OR sp.state != 'done'
        ORDER BY sp.id
    """)
    cf_pickings = [{"id": r[0], "name": r[1], "origin": r[2], "date_done": str(r[3]), "state": r[4]} for r in cur.fetchall()]

    # 3. Check stock moves and quants
    cur.execute("""
        SELECT
            sum(case when sm.date < '2026-08-01' then sm.product_uom_qty else 0 end) as qty_before_aug,
            sum(case when sm.date >= '2026-08-01' then sm.product_uom_qty else 0 end) as qty_after_aug
        FROM stock_move sm
        WHERE sm.state = 'done'
    """)
    r = cur.fetchone()
    moves_summary = {"qty_before_aug": float(r[0] or 0), "qty_after_aug": float(r[1] or 0)}

    # 4. Check if 100 cartons x 150 SKU fixture from mobile demo exists
    # Look for moves or quants from mobile demo
    cur.execute("""
        SELECT count(*), sum(product_uom_qty)
        FROM stock_move
        WHERE origin LIKE '%demo%' OR origin LIKE '%fixture%' OR origin LIKE '%staging%'
    """)
    r = cur.fetchone()
    fixture_moves = {"count": r[0], "qty": float(r[1] or 0)}

    # 5. Stock quants in WH/Stock grouped by product to cartons conversion
    # In Odoo, uom_id on product_template or product_uom
    cur.execute("""
        SELECT pt.name, pt.default_code, uom.name as uom_name, sq.quantity, sq.reserved_quantity
        FROM stock_quant sq
        JOIN product_product pp ON pp.id = sq.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        JOIN uom_uom uom ON uom.id = pt.uom_id
        JOIN stock_location sl ON sl.id = sq.location_id
        WHERE sl.complete_name = 'WH/Stock'
        LIMIT 10
    """)
    sample_quants = [
        {"name": r[0], "code": r[1], "uom": r[2], "quantity": float(r[3]), "reserved": float(r[4])}
        for r in cur.fetchall()
    ]

    out = {
        "pickings_by_date": pickings,
        "carry_forward_or_open_pickings_count": len(cf_pickings),
        "sample_cf_pickings": cf_pickings[:10],
        "moves_summary": moves_summary,
        "fixture_moves": fixture_moves,
        "sample_quants": sample_quants,
    }

    out_path = os.path.join(os.path.dirname(__file__), "seed_f0_stock_details.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"Written stock details to {out_path}")

if __name__ == "__main__":
    main()
