#!/usr/bin/env python3
"""F0b: rekonsiliasi stok live (WH/Stock) vs state_20260801.json per SKU dan lot.

READ-ONLY (default_transaction_read_only). Tidak menyesuaikan stok apa pun.
Basis rekonsiliasi: AVAILABLE-VS-AVAILABLE (stok tersedia = physical - reserved)
setelah 48 DO carry-forward 1 Agustus terkirim:
- Sisi kanonikal (`state_20260801.json`): `physical - reserved` per (sku, lot).
- Sisi live (`stock_quant` pada `WH/Stock` internal SATU perusahaan eksplisit):
  `SUM(sq.quantity) - SUM(sq.reserved_quantity)`.

Cakupan perusahaan WAJIB eksplisit (`--company-id`). State kanonikal merepresentasikan
satu entitas (`PT Salva Inti Mandiri`), sehingga stok perusahaan aktif lain tidak boleh
ikut dijumlahkan. ID perusahaan divalidasi terhadap nama entitas kanonikal (fail-closed)
dan setiap baris live harus membawa `company_id` yang sama dengan cakupan.

Tujuan: menguji hipotesis selisih 15.000 karton = fixture mobile 100 karton x 150 SKU
(gap G-05). Hasil: JSON diff per SKU/lot, tanpa kredensial.

Pakai: python scripts/ops/seed_f0b_stock_reconcile_live.py --company-id <ID> --out /tmp/f0b.json
(env PG* / RAILWAY_TCP_PROXY_* seperti seed_f0_analyze_stock_live.py)
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from decimal import Decimal
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "registers" / "state_20260801.json"
INITIAL = ROOT / "data" / "registers" / "initial_stock_20260701.csv"

CANONICAL_COMPANY_NAME = "PT Salva Inti Mandiri"

COMPANY_SQL = """
SELECT id, name, active
FROM res_company
WHERE id = %(company_id)s
"""

LIVE_STOCK_SQL = """
SELECT
    sq.company_id,
    pt.default_code,
    spl.name,
    SUM(sq.quantity) AS physical_qty,
    SUM(sq.reserved_quantity) AS reserved_qty
FROM stock_quant sq
JOIN product_product pp ON pp.id = sq.product_id
JOIN product_template pt ON pt.id = pp.product_tmpl_id
JOIN stock_location sl ON sl.id = sq.location_id
JOIN res_company rc ON rc.id = sq.company_id
LEFT JOIN stock_lot spl ON spl.id = sq.lot_id
WHERE sq.company_id = %(company_id)s
  AND sl.complete_name = 'WH/Stock'
  AND sl.usage = 'internal'
  AND rc.active = TRUE
  AND pt.default_code IS NOT NULL
GROUP BY 1, 2, 3
HAVING SUM(sq.quantity) <> 0 OR SUM(sq.reserved_quantity) <> 0
"""


def check_company_row(row, company_id: int, expected_name: str = CANONICAL_COMPANY_NAME) -> str:
    """Validasi perusahaan target terhadap entitas kanonikal; fail-closed."""
    if row is None:
        raise ValueError(f"Company id {company_id} does not exist; refusing to reconcile.")
    row_id, name, active = row
    if int(row_id) != int(company_id):
        raise ValueError(f"Company lookup returned id {row_id}, expected {company_id}.")
    if not active:
        raise ValueError(f"Company id {company_id} ({name!r}) is inactive; refusing to reconcile.")
    if name != expected_name:
        raise ValueError(
            f"Company id {company_id} is {name!r}, but the canonical state represents "
            f"{expected_name!r}; refusing to compare against another entity."
        )
    return name


def load_canonical_state(path: Path = STATE) -> dict:
    """Muat berkas state kanonikal dengan pesan error eksplisit bila tidak tersedia."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Required canonical state fixture not found at {path}. "
            "Ensure PR #94 (data/registers/state_20260801.json) is present in the checkout."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_available(state: dict) -> dict[tuple[str, str], int]:
    """Stok tersedia kanonikal per (sku, lot) setelah 48 DO carry-forward terkirim."""
    out = {}
    for v in state["stock"].values():
        qty = int(v["physical"]) - int(v["reserved"])
        if qty:
            out[(v["sku_code"], v["lot_number"])] = qty
    return out


def carton_sizes(path: Path = INITIAL) -> dict[str, int]:
    if not path.is_file():
        raise FileNotFoundError(f"Required initial stock register not found at {path}.")
    with path.open(newline="", encoding="utf-8") as fh:
        return {r["sku_code"]: int(r["carton_qty"]) for r in csv.DictReader(fh)}


def _unpack_live_row(row, company_id: int) -> tuple[str, str | None, Decimal, Decimal]:
    """Terima 5-tuple (company_id, sku, lot, physical_units, reserved_units) dari SQL live.

    Baris dari perusahaan selain `company_id` ditolak (tidak diabaikan diam-diam) agar
    stok perusahaan lain tidak mengontaminasi rekonsiliasi.
    """
    if len(row) != 5:
        raise ValueError(
            f"Expected 5-tuple (company_id, sku, lot, physical, reserved) live row, got {len(row)} elements."
        )
    row_company, sku, lot, physical_qty, reserved_qty = row
    if int(row_company) != int(company_id):
        raise ValueError(
            f"Live stock row for SKU {sku} belongs to company {row_company}, "
            f"outside the reconciliation scope company {company_id}."
        )
    phys = Decimal(str(physical_qty))
    resv = Decimal(str(reserved_qty))
    if resv < 0:
        raise ValueError(f"Negative reserved_quantity ({resv}) is invalid for SKU {sku}.")
    return sku, lot, phys, resv


def compare(live_rows, canon: dict, carton: dict[str, int], company_id: int) -> dict:
    """Bandingkan stok tersedia live (physical - reserved) terhadap kanonikal dalam karton.

    `company_id` adalah cakupan eksplisit; semua `live_rows` harus milik perusahaan itu.
    """
    live = defaultdict(Decimal)
    lotless = defaultdict(Decimal)
    total_physical = Decimal(0)
    total_reserved = Decimal(0)
    for row in live_rows:
        sku, lot, phys_units, resv_units = _unpack_live_row(row, company_id)
        c_size = Decimal(carton[sku])
        phys_cartons = phys_units / c_size
        resv_cartons = resv_units / c_size
        avail_cartons = (phys_units - resv_units) / c_size
        total_physical += phys_cartons
        total_reserved += resv_cartons
        if lot:
            live[(sku, lot)] += avail_cartons
        else:
            lotless[sku] += avail_cartons
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
    avail_total = sum(live.values()) + sum(lotless.values())
    return {
        "reconciliation_basis": "available_vs_available",
        "company_id": int(company_id),
        "live_physical_total_cartons": str(total_physical),
        "live_reserved_total_cartons": str(total_reserved),
        "live_available_total_cartons": str(avail_total),
        "live_total_cartons": str(avail_total),
        "canonical_total_cartons": sum(canon.values()),
        "lot_diffs_count": len(diffs),
        "lot_diffs_sample": {f"{k[0]}||{k[1]}": str(v) for k, v in list(diffs.items())[:10]},
        "lotless_cartons_total": str(sum(lotless.values())),
        "lotless_skus": len(lotless),
        "per_sku_diff_cartons": {k: str(v) for k, v in sorted(per_sku.items()) if v},
        "per_sku_diff_total": str(sum(per_sku.values())),
        "hypothesis_100x150_proven": uniform_100,
    }


def fetch_live_rows(company_id: int):
    import psycopg2

    host = (
        os.environ.get("RAILWAY_TCP_PROXY_DOMAIN")
        or os.environ.get("GEO_PG_HOST")
        or os.environ.get("PGHOST")
    )
    port = int(
        os.environ.get("RAILWAY_TCP_PROXY_PORT")
        or os.environ.get("GEO_PG_PORT")
        or os.environ.get("PGPORT", 5432)
    )
    conn = psycopg2.connect(
        host=host,
        port=port,
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", ""),
        dbname=os.environ.get("PGDATABASE", "railway"),
        sslmode="require",
        options="-c default_transaction_read_only=on -c statement_timeout=60000",
    )
    try:
        with conn, conn.cursor() as cur:
            cur.execute(COMPANY_SQL, {"company_id": company_id})
            check_company_row(cur.fetchone(), company_id)
            cur.execute(LIVE_STOCK_SQL, {"company_id": company_id})
            return [(r[0], r[1], r[2], r[3], r[4]) for r in cur.fetchall()]
    finally:
        conn.close()


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--company-id", type=int, required=True,
        help="ID res_company yang setara dengan entitas kanonikal (wajib; tidak ada default).",
    )
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
    state = load_canonical_state(STATE)
    live_rows = fetch_live_rows(args.company_id)
    result = compare(live_rows, canonical_available(state), carton_sizes(), args.company_id)
    result["company_name"] = CANONICAL_COMPANY_NAME
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"ditulis {args.out}; hypothesis_100x150_proven={result['hypothesis_100x150_proven']}")


if __name__ == "__main__":
    main()
