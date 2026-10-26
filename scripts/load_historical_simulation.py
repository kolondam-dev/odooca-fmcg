#!/usr/bin/env python3
"""Script loader simulasi transaksi historis FMCG ke Odoo 19 via Odoo shell.

PENTING:
Skrip ini telah dialihkan secara resmi ke scripts/load_canonical_perpetual.py untuk memuat
dataset perpetual kanonikal (1.324 SO single-prinsipal, 1.324 DO, 1.324 Faktur, 9 Retur Karantina,
AR/AP payments, OPEX & 5.741 event ledger) yang telah lulus seluruh acceptance & invariant gates.
Dilarang memuat atau fallback ke CSV simulasi lama (sales_orders_historical.csv).

Dijalankan via:
    odoo shell -c /tmp/odoo.conf -d <dbname> --no-http < scripts/load_historical_simulation.py
"""

import pathlib
import runpy
import sys

_root = pathlib.Path(__file__).resolve().parent
_canonical_script = _root / "load_canonical_perpetual.py"

if not _canonical_script.is_file():
    print(f"[hist_loader] FATAL: {_canonical_script} tidak ditemukan.", file=sys.stderr)
    sys.exit(1)

# Delegasikan eksekusi langsung ke adapter canonical dengan membawa objek env Odoo
_env = globals().get("env")
runpy.run_path(str(_canonical_script), init_globals={"env": _env} if _env else None, run_name="__main__")
