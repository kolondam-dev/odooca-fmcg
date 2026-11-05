#!/usr/bin/env python3
"""F0b: rekonsiliasi stok live (WH/Stock) vs state_20260801.json per SKU dan lot.

READ-ONLY (default_transaction_read_only). Tidak menyesuaikan stok apa pun.
Tujuan: membuktikan atau membantah hipotesis selisih 15.000 karton = fixture
mobile 100 karton x 150 SKU (gap G-05). Hasil: JSON diff per SKU/lot, tanpa kredensial.

Pakai: python scripts/ops/seed_f0b_stock_reconcile_live.py --out /tmp/f0b.json
(env PG* / RAILWAY_TCP_PROXY_* seperti seed_f0_analyze_stock_live.py)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "registers" / "state_20260801.json"
INITIAL = ROOT / "data" / "registers" / "initial_stock_20260701.csv"


def canonical_available(state: dict) -> dict[tuple[str, str], int]:
    """Stok tersedia kanonikal per (sku, lot) setelah 48 DO carry-forward terkirim."""
    out = {}
    for v in state["stock"].values():
        qty = int(v["physical"]) - int(v["reserved"])
        if qty:
            out[(v["sku_code"], v["lot_number"])] = qty
    return out


def carton_sizes(path: Path = INITIAL) -> dict[str, int]:
    with path.open(newline="", encoding="utf-8") as fh:
        return {r["sku_code"]: int(r["carton_qty"]) for r in csv.DictReader(fh)}


def compare(live_rows, canon: dict, carton: dict[str, int]) -> dict:
    """live_rows: iterable (sku, lot_or_None, qty_units). Mengembalikan ringkasan diff dalam karton."""
    live = defaultdict(Decimal)
    lotless = defaultdict(Decimal)
    for sku, lot, qty in live_rows:
        cartons = Decimal(str(qty)) / Decimal(carton[sku])
        if lot:
            live[(sku, lot)] += cartons
        else:
            lotless[sku] += cartons
    diffs = {}
    for key in set(live) | set(canon):
        d = live.get(key, Decimal(0)) - Decimal(canon.get(key, 0))
        if d:
            diffs[key] = d
    per_sku = defaultdict(Decimal)
    for (sku, _lot), d in diffs.items():
        per_sku[sku] += d
    for sku, q in lotless.items():
        per_sku[sku] += q
    uniform_100 = bool(per_sku) and all(v == 100 for v in per_sku.values()) and len(per_sku) == 150
    return {
        "live_total_cartons": str(sum(live.values()) + sum(lotless.values())),
        "canonical_total_cartons": sum(canon.values()),
        "lot_diffs_count": len(diffs),
        "lot_diffs_sample": {f"{k[0]}||{k[1]}": str(v) for k, v in list(diffs.items())[:10]},
        "lotless_cartons_total": str(sum(lotless.values())),
        "lotless_skus": len(lotless),
        "per_sku_diff_cartons": {k: str(v) for k, v in sorted(per_sku.items()) if v},
        "per_sku_diff_total": str(sum(per_sku.values())),
        "hypothesis_100x150_proven": uniform_100,
    }


def fetch_live_rows():
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ.get("RAILWAY_TCP_PROXY_DOMAIN") or os.environ.get("GEO_PG_HOST") or os.environ.get("PGHOST"),
        port=int(os.environ.get("RAILWAY_TCP_PROXY_PORT") or os.environ.get("GEO_PG_PORT") or os.environ.get("PGPORT", 5432)),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", ""),
        dbname=os.environ.get("PGDATABASE", "railway"),
        sslmode="require",
        options="-c default_transaction_read_only=on -c statement_timeout=60000",
    )
    cur = conn.cursor()
    cur.execute(
        """
        SELECT pt.default_code, spl.name, sum(sq.quantity)
        FROM stock_quant sq
        JOIN product_product pp ON pp.id = sq.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        JOIN stock_location sl ON sl.id = sq.location_id
        LEFT JOIN stock_lot spl ON spl.id = sq.lot_id
        WHERE sl.complete_name = 'WH/Stock'
        GROUP BY 1, 2
        HAVING sum(sq.quantity) <> 0
        """
    )
    return [(r[0], r[1], r[2]) for r in cur.fetchall()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    state = json.loads(STATE.read_text(encoding="utf-8"))
    result = compare(fetch_live_rows(), canonical_available(state), carton_sizes())
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"ditulis {args.out}; hypothesis_100x150_proven={result['hypothesis_100x150_proven']}")


if __name__ == "__main__":
    main()
