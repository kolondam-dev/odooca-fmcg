#!/usr/bin/env python3
"""generate_period_pack.py - CLI Generator Pack Periode Transaksi FMCG (Fase F2).

Menghasilkan pack transaksi sintetis deterministik bulanan (misal 2026-08)
yang memenuhi seluruh kontrak invariant di SEED_INVARIANT_CONTRACT_V2.md,
divalidasi secara ketat (strict=True) oleh seed_v2_gates.py,
dan menghasilkan MANIFEST.json dengan checksum SHA-256 LF-kanonikal.
"""

import argparse
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ops.fmcg_calendar import get_next_working_day  # noqa: E402
from scripts.ops.generate_state_20260801 import verify_canonical_fingerprints  # noqa: E402
from scripts.ops.seed_planner import (  # noqa: E402
    PeriodConfig,
    SeedPlanner,
    extract_existing_numbers,
    prepare_gate_opening,
)
from scripts.ops.seed_v2_gates import replay_closing, validate_pack_report  # noqa: E402


def compute_sha256_lf(path: Path) -> str:
    """Menghitung SHA-256 dari konten file dengan normalisasi LF."""
    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(raw).hexdigest()


def get_git_head_commit() -> str:
    """Mengambil commit HEAD git repository saat ini."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "UNKNOWN_COMMIT"


def export_table_csv(table_name: str, rows: List[Dict[str, Any]], out_dir: Path) -> Path:
    """Mengekspor daftar dictionary ke CSV dengan LF canonical format."""
    csv_path = out_dir / f"{table_name}.csv"
    if not rows:
        csv_path.write_text("", encoding="utf-8", newline="\n")
        return csv_path

    headers = list(rows[0].keys())
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

    csv_path.write_text(buffer.getvalue(), encoding="utf-8", newline="\n")
    return csv_path


def export_table_json(table_name: str, data: Any, out_dir: Path) -> Path:
    """Mengekspor data ke JSON dengan format canonical indent 2."""
    json_path = out_dir / f"{table_name}.json"
    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    json_path.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    return json_path


def generate_period_pack(
    period: str = "2026-08",
    opening_state_path: Path = None,
    output_dir: Path = None,
    strict_validate: bool = True,
    opening_cash: Decimal = Decimal("5000000000.00"),
    tax_rate: Decimal = Decimal("0.11"),
) -> Dict[str, Any]:
    """Eksekusi generator pack untuk suatu periode dan menyimpannya ke disk."""
    reg_dir = REPO_ROOT / "data" / "registers"
    if opening_state_path is None:
        opening_state_path = reg_dir / "state_20260801.json"

    if output_dir is None:
        output_dir = reg_dir / "periods" / period
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Verifikasi fingerprint 15 register Juli kanonikal
    verify_canonical_fingerprints(reg_dir)
    with (reg_dir / "canonical_financial_reconciliation_july_2026.json").open("r", encoding="utf-8") as f:
        rec_data = json.load(f)
    july_fingerprints = rec_data.get("input_dataset_sha256", {})

    # 2. Baca Opening State
    with opening_state_path.open("r", encoding="utf-8") as f:
        raw_opening = json.load(f)

    # 3. Konfigurasi Periode
    year_str, month_str = period.split("-")
    year, month = int(year_str), int(month_str)

    # Hitung batas hari kalender
    import calendar as py_calendar
    _, last_day = py_calendar.monthrange(year, month)
    pack_start = f"{year:04d}-{month:02d}-01"
    pack_end = f"{year:04d}-{month:02d}-{last_day:02d}"

    config = PeriodConfig(
        pack_start=pack_start,
        pack_end=pack_end,
        opening_cash=opening_cash,
        tax_rate=tax_rate,
        target_net_dpp=Decimal("4235000000.00"),
        target_discount_pct=Decimal("2.50"),
        target_rejection_pct=Decimal("2.40"),
    )

    # 4. Eksekusi Perencanaan Transaksi FMCG Deterministik
    planner = SeedPlanner(config, root_dir=REPO_ROOT)
    result = planner.plan_period(raw_opening)

    pack = result["pack"]
    narrative_report = result["narrative_report"]
    last_sequences = result["last_sequences"]

    # 5. Persiapkan Opening untuk Gate & Validasi
    gate_opening = prepare_gate_opening(raw_opening)
    existing_numbers = extract_existing_numbers(gate_opening)

    # 6. Hitung Closing State periode ini dengan replay_closing
    gate_config = {
        "pack_start": pack_start,
        "pack_end": pack_end,
        "opening_cash": str(opening_cash),
        "min_lead_days": config.min_lead_days,
        "tax": {
            "rate": str(tax_rate),
            "source": "PMK 131/2024 & UU HPP No. 7/2021",
            "source_date": "2024-12-31",
            "effective_from": "2025-01-01",
        },
    }

    closing_raw = replay_closing(gate_opening, pack, gate_config)

    # Susun serializable closing state JSON
    non_zero_stock_closing = {}
    for (sku, lot), st in sorted(closing_raw["stock"].items()):
        if any(st[f] != Decimal("0") for f in ("physical", "reserved", "quarantine")):
            non_zero_stock_closing[f"{sku}||{lot}"] = {
                "sku_code": sku,
                "lot_number": lot,
                "physical": int(st["physical"]),
                "reserved": int(st["reserved"]),
                "quarantine": int(st["quarantine"]),
            }

    follow_day = get_next_working_day(py_calendar.datetime.date(year, month, last_day))
    closing_state = {
        "as_of_datetime": f"{follow_day.isoformat()}T00:00:00+08:00",
        "timezone": "Asia/Makassar (+08:00 WITA)",
        "period_closed": period,
        "description": f"Closing state after completing {period} transactions pack.",
        "summary": {
            "total_physical_cartons": sum(v["physical"] for v in non_zero_stock_closing.values()),
            "total_reserved_cartons": sum(v["reserved"] for v in non_zero_stock_closing.values()),
            "total_available_cartons": sum(v["physical"] - v["reserved"] for v in non_zero_stock_closing.values()),
            "total_quarantine_cartons": sum(v["quarantine"] for v in non_zero_stock_closing.values()),
            "open_invoices_count": len(closing_raw["open_invoices"]),
            "carry_invoices_count": len(closing_raw["carry_invoices"]),
            "open_po_count": len(closing_raw["open_po"]),
            "in_transit_po_count": len(closing_raw["in_transit"]),
            "pending_dos_count": len(closing_raw["pending_dos"]),
        },
        "last_sequences": last_sequences,
        "stock": non_zero_stock_closing,
        "open_invoices": closing_raw["open_invoices"],
        "carry_invoices": closing_raw["carry_invoices"],
        "open_po": closing_raw["open_po"],
        "in_transit": closing_raw["in_transit"],
        "pending_dos": closing_raw["pending_dos"],
    }

    # 7. Validasi Invariant Gates v2
    if strict_validate:
        bands = {
            "net_dpp": (Decimal("4000000000.00"), Decimal("4500000000.00")),
            "discount_pct": (Decimal("2.00"), Decimal("3.20")),
            "rejection_pct": (Decimal("1.80"), Decimal("3.00")),
            "active_outlets": (Decimal("200"), Decimal("215")),
        }
        report = validate_pack_report(
            pack=pack,
            opening=gate_opening,
            previous_closing=gate_opening,
            existing_numbers=existing_numbers,
            config=gate_config,
            bands=bands,
            strict=True,
        )
        if report.get("violations"):
            raise ValueError(f"Strict validation failed with violations: {report['violations']}")
        print(f"Gate validation PASSED (strict=True, gates run: {len(report.get('gates_run', []))}, 0 violations).")

    # 8. Ekspor Seluruh Tabel Pack (CSV & JSON)
    exported_files: List[Path] = []
    for table_name, rows in pack.items():
        exported_files.append(export_table_csv(table_name, rows, output_dir))
        exported_files.append(export_table_json(table_name, rows, output_dir))

    # Ekspor Laporan Naratif & Closing State
    exported_files.append(export_table_json("narrative_report", narrative_report, output_dir))
    closing_filename = f"closing_state_{pack_end.replace('-', '')}"
    exported_files.append(export_table_json(closing_filename, closing_state, output_dir))

    # 9. Buat MANIFEST.json dengan SHA-256 LF kanonikal
    file_manifest: Dict[str, str] = {}
    for p in sorted(exported_files, key=lambda x: x.name):
        file_manifest[p.name] = compute_sha256_lf(p)

    manifest_data = {
        "period": period,
        "pack_start": pack_start,
        "pack_end": pack_end,
        "generator_commit": get_git_head_commit(),
        "canonical_july_15_register_fingerprints": july_fingerprints,
        "configuration": {
            "target_net_dpp": str(config.target_net_dpp),
            "target_discount_pct": str(config.target_discount_pct),
            "target_rejection_pct": str(config.target_rejection_pct),
            "opening_cash": str(opening_cash),
            "tax": gate_config["tax"],
            "min_lead_days": config.min_lead_days,
            "narrative_bands": {
                k: [str(b[0]), str(b[1])] for k, b in config.bands.items()
            },
        },
        "metrics_summary": narrative_report["metrics"],
        "closing_summary": closing_state["summary"],
        "files_sha256": file_manifest,
    }

    manifest_path = export_table_json("MANIFEST", manifest_data, output_dir)
    print(f"Manifest written to {manifest_path}")

    return {
        "pack": pack,
        "narrative_report": narrative_report,
        "closing_state": closing_state,
        "manifest": manifest_data,
        "output_dir": output_dir,
    }


def main():
    parser = argparse.ArgumentParser(description="Generator FMCG Seed Pack Periode (Fase F2)")
    parser.add_argument("--period", default="2026-08", help="Periode pack (format YYYY-MM), default 2026-08")
    parser.add_argument("--opening-state", default=None, help="Path ke berkas JSON opening state")
    parser.add_argument("--output-dir", default=None, help="Path direktori output pack")
    parser.add_argument("--no-strict", action="store_true", help="Nonaktifkan validasi strict")
    args = parser.parse_args()

    op_path = Path(args.opening_state) if args.opening_state else None
    out_dir = Path(args.output_dir) if args.output_dir else None

    print(f"Generating period pack for {args.period}...")
    res = generate_period_pack(
        period=args.period,
        opening_state_path=op_path,
        output_dir=out_dir,
        strict_validate=not args.no_strict,
    )
    print("Period pack generation complete.")
    print("Summary:")
    for k, v in res["narrative_report"]["metrics"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

