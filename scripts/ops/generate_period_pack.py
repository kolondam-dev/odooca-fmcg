#!/usr/bin/env python3
"""generate_period_pack.py - CLI Generator Pack Periode Transaksi FMCG (Fase F2).

Menghasilkan pack transaksi sintetis deterministik bulanan (misal 2026-08)
yang memenuhi seluruh kontrak invariant di SEED_INVARIANT_CONTRACT_V2.md,
divalidasi secara ketat (strict=True) oleh seed_v2_gates.py,
dan menghasilkan MANIFEST.json dengan checksum SHA-256 LF-kanonikal
serta pengikatan hash sumber generator.
"""

import argparse
import csv
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional

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
from scripts.ops.seed_v2_gates import load_pack, replay_closing, validate_pack_report  # noqa: E402


def compute_sha256_lf(path: Path) -> str:
    """Menghitung SHA-256 dari konten file dengan normalisasi LF."""
    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(raw).hexdigest()


def get_git_head_commit(override_commit: Optional[str] = None) -> str:
    """Mengambil commit HEAD git repository saat ini atau override yang diberikan."""
    if override_commit:
        return override_commit
    env_commit = os.environ.get("GENERATOR_COMMIT")
    if env_commit:
        return env_commit
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


def verify_pack_manifest(pack_dir: Path) -> Dict[str, Any]:
    """Memverifikasi integritas manifest dan checksum SHA-256 LF seluruh berkas dalam pack."""
    manifest_path = pack_dir / "MANIFEST.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Pack manifest untuk periode sebelumnya tidak ditemukan di {manifest_path}"
        )
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    files_sha = manifest.get("files_sha256", {})
    if not files_sha:
        raise ValueError(f"MANIFEST.json di {manifest_path} tidak memuat entri files_sha256.")

    for fname, expected_hash in files_sha.items():
        fpath = pack_dir / fname
        if not fpath.exists():
            raise FileNotFoundError(f"Berkas '{fname}' yang terdaftar pada MANIFEST tidak ditemukan di {pack_dir}")
        actual_hash = compute_sha256_lf(fpath)
        if actual_hash != expected_hash:
            raise ValueError(
                f"Integritas file {fname} pada pack {pack_dir.name} tidak valid menurut MANIFEST: "
                f"aktual {actual_hash} != expected {expected_hash}"
            )

    return manifest


def get_verified_previous_closing(period: str, reg_dir: Path) -> Dict[str, Any]:
    """Menghitung penutupan periode sebelumnya secara independen dan terverifikasi."""
    year_str, month_str = period.split("-")
    year, month = int(year_str), int(month_str)
    if month == 1:
        prev_period = f"{year - 1:04d}-12"
    else:
        prev_period = f"{year:04d}-{month - 1:02d}"

    if prev_period == "2026-07":
        # Verifikasi 15 register kanonikal Juli sebelum replay
        verify_canonical_fingerprints(reg_dir)
        july_pack = load_pack(
            reg_dir,
            dict(
                sales_orders="perpetual_sales_orders.csv",
                deliveries="perpetual_deliveries.csv",
                invoices="perpetual_invoices.csv",
                ar_collections="perpetual_ar_collections.csv",
                po_headers="inbound_po_intransit_june_headers.csv",
                ap_payments="perpetual_ap_payments.csv",
                opex="perpetual_opex_payroll.csv",
                rejections="perpetual_order_rejections.csv",
                stock_events="perpetual_stock_event_ledger.csv",
            ),
        )
        july_config = dict(pack_start="2026-07-01", pack_end="2026-07-31")
        opening_zero = dict(
            stock={}, open_invoices={}, carry_invoices={}, open_po={}, in_transit={}, pending_dos={}
        )
        return replay_closing(opening_zero, july_pack, july_config)
    else:
        # Untuk periode setelah Agustus (misal 2026-09):
        # Penutupan periode sebelumnya diverifikasi dari manifes pack periode sebelumnya
        prev_pack_dir = reg_dir / "periods" / prev_period
        verify_pack_manifest(prev_pack_dir)
        prev_closing_files = sorted(prev_pack_dir.glob("closing_state_*.json"))
        if not prev_closing_files:
            raise FileNotFoundError(f"closing_state berkas tidak ditemukan di {prev_pack_dir}")
        with prev_closing_files[-1].open("r", encoding="utf-8") as f:
            prev_closing_data = json.load(f)
        return prepare_gate_opening(prev_closing_data)


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


def resolve_opening_state_path(
    period: str,
    reg_dir: Path,
    opening_state_path: Optional[Path] = None,
) -> Path:
    """Menentukan path opening state untuk periode tertentu secara fail-closed dan konsisten.

    Aturan kontinuitas:
    1. Jika opening_state_path diberikan secara eksplisit:
       * Pastikan berkas ada.
       * Jika direktori berkas memuat MANIFEST.json: wajibkan files_sha256 valid,
         wajibkan berkas terdaftar di files_sha256 (jika tidak terdaftar raise ValueError),
         dan verifikasi kesesuaian hash SHA-256 LF secara fail-closed.
       * Jika berkas di luar direktori pack ber-MANIFEST: diterima langsung jika berkas ada.
    2. Jika opening_state_path tidak diberikan:
       * Periode '2026-08': default ke data/registers/state_20260801.json.
       * Periode non-Agustus (misal '2026-09'): otomatis mencari berkas closing_state
         pada direktori pack periode sebelumnya (data/registers/periods/<prev_period>/closing_state_*.json).
         Wajib memverifikasi MANIFEST.json dan checksum berkas closing state tersebut
         secara fail-closed via verify_pack_manifest. Jika berkas closing, manifest, atau
         hash tidak cocok/hilang, proses menolak dengan FileNotFoundError/ValueError.
    """
    if opening_state_path is not None:
        p = Path(opening_state_path)
        if not p.exists():
            raise FileNotFoundError(f"Opening state berkas tidak ditemukan: {p}")
        manifest_path = p.parent / "MANIFEST.json"
        if manifest_path.exists():
            with manifest_path.open("r", encoding="utf-8") as f:
                manifest = json.load(f)
            files_sha = manifest.get("files_sha256")
            if not isinstance(files_sha, dict) or not files_sha:
                raise ValueError(
                    f"MANIFEST.json pada {p.parent} tidak memuat entri files_sha256 yang valid."
                )
            if p.name not in files_sha:
                raise ValueError(
                    f"Opening state eksplisit '{p.name}' tidak terdaftar pada MANIFEST.json di {p.parent}."
                )
            expected_hash = files_sha[p.name]
            actual_hash = compute_sha256_lf(p)
            if actual_hash != expected_hash:
                raise ValueError(
                    f"Integritas opening state eksplisit '{p.name}' tidak cocok dengan MANIFEST: "
                    f"aktual {actual_hash} != diharapkan {expected_hash}"
                )
        return p

    if period == "2026-08":
        default_august = reg_dir / "state_20260801.json"
        if not default_august.exists():
            raise FileNotFoundError(f"Default opening state Agustus tidak ditemukan di {default_august}")
        return default_august

    year_str, month_str = period.split("-")
    year, month = int(year_str), int(month_str)
    if month == 1:
        prev_period = f"{year - 1:04d}-12"
    else:
        prev_period = f"{year:04d}-{month - 1:02d}"

    prev_pack_dir = reg_dir / "periods" / prev_period
    if not prev_pack_dir.exists():
        raise ValueError(
            f"Opening state untuk periode non-Agustus '{period}' wajib disertakan via --opening-state "
            f"karena closing state periode sebelumnya '{prev_period}' tidak ditemukan di {prev_pack_dir}."
        )

    closing_candidates = sorted(prev_pack_dir.glob("closing_state_*.json"))
    if not closing_candidates:
        raise FileNotFoundError(
            f"Closing state periode sebelumnya '{prev_period}' tidak ditemukan di {prev_pack_dir}."
        )
    closing_file = closing_candidates[-1]

    # Validasi provenance dan checksum closing state terhadap MANIFEST periode sebelumnya
    manifest = verify_pack_manifest(prev_pack_dir)
    files_sha = manifest.get("files_sha256", {})
    if closing_file.name not in files_sha:
        raise ValueError(
            f"Closing state '{closing_file.name}' tidak terdaftar pada MANIFEST.json periode '{prev_period}'."
        )

    return closing_file


def generate_period_pack(
    period: str = "2026-08",
    opening_state_path: Path = None,
    output_dir: Path = None,
    strict_validate: bool = True,
    opening_cash: Decimal = Decimal("5000000000.00"),
    tax_rate: Decimal = Decimal("0.11"),
    generator_commit: Optional[str] = None,
) -> Dict[str, Any]:
    """Eksekusi generator pack untuk suatu periode dan menyimpannya ke disk."""
    reg_dir = REPO_ROOT / "data" / "registers"
    opening_state_path = resolve_opening_state_path(period, reg_dir, opening_state_path)

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
    carry_forward_lines = result.get("carry_forward_lines", [])

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

    # Susun metadata kaya untuk entitas open agar dapat dipakai sebagai opening periode berikutnya
    po_header_map = {row["po_number"]: row for row in pack.get("po_headers", [])}
    rich_open_po = {}
    for po_num, arr_date in closing_raw["open_po"].items():
        if po_num in po_header_map:
            h = po_header_map[po_num]
            rich_open_po[po_num] = {
                "principal_code": h["principal_code"],
                "arrival_maumbi_date": h["arrival_maumbi_date"],
                "payment_due_date": h["due_date"],
                "total_amount_dpp": h["total_dpp"],
            }
        elif po_num in raw_opening.get("open_po", {}):
            rich_open_po[po_num] = raw_opening["open_po"][po_num]
        elif po_num in raw_opening.get("in_transit", {}):
            rich_open_po[po_num] = raw_opening["in_transit"][po_num]
        elif po_num in raw_opening.get("in_transit_po", {}):
            rich_open_po[po_num] = raw_opening["in_transit_po"][po_num]
        else:
            rich_open_po[po_num] = {"arrival_maumbi_date": arr_date}

    rich_in_transit = {}
    for po_num, arr_date in closing_raw["in_transit"].items():
        if po_num in po_header_map:
            h = po_header_map[po_num]
            rich_in_transit[po_num] = {
                "principal_code": h["principal_code"],
                "arrival_maumbi_date": h["arrival_maumbi_date"],
                "payment_due_date": h["due_date"],
                "total_amount_dpp": h["total_dpp"],
            }
        elif po_num in raw_opening.get("in_transit", {}):
            rich_in_transit[po_num] = raw_opening["in_transit"][po_num]
        elif po_num in raw_opening.get("in_transit_po", {}):
            rich_in_transit[po_num] = raw_opening["in_transit_po"][po_num]
        else:
            rich_in_transit[po_num] = {"arrival_maumbi_date": arr_date}

    inv_map = {row["invoice_number"]: row for row in pack.get("invoices", [])}
    so_cust_map = {row["so_number"]: row["customer"] for row in pack.get("sales_orders", [])}

    rich_open_invoices = {}
    for inv_num, inv_date in closing_raw["open_invoices"].items():
        if inv_num in inv_map:
            r = inv_map[inv_num]
            rich_open_invoices[inv_num] = {
                "date_invoice": r["date_invoice"],
                "status_at_cutoff": "posted",
                "due_date": r["due_date"],
                "customer": r.get("customer") or so_cust_map.get(r.get("so_number"), ""),
                "dpp_amount": r["dpp_amount"],
                "total_invoice_with_ppn": r["total_invoice_with_ppn"],
            }
        elif inv_num in raw_opening.get("open_invoices", {}):
            rich_open_invoices[inv_num] = raw_opening["open_invoices"][inv_num]
        elif inv_num in raw_opening.get("open_posted_invoices_july", {}):
            rich_open_invoices[inv_num] = raw_opening["open_posted_invoices_july"][inv_num]
        else:
            rich_open_invoices[inv_num] = {"date_invoice": inv_date}

    rich_carry_invoices = {}
    for inv_num, inv_date in closing_raw["carry_invoices"].items():
        if inv_num in inv_map:
            r = inv_map[inv_num]
            rich_carry_invoices[inv_num] = {
                "date_invoice": r["date_invoice"],
                "status_at_cutoff": "carry_forward_pending",
                "due_date": r["due_date"],
                "customer": r.get("customer") or so_cust_map.get(r.get("so_number"), ""),
                "dpp_amount": r["dpp_amount"],
                "total_invoice_with_ppn": r["total_invoice_with_ppn"],
            }
        elif inv_num in raw_opening.get("carry_invoices", {}):
            rich_carry_invoices[inv_num] = raw_opening["carry_invoices"][inv_num]
        elif inv_num in raw_opening.get("carry_forward_pending_invoices_august", {}):
            rich_carry_invoices[inv_num] = raw_opening["carry_forward_pending_invoices_august"][inv_num]
        else:
            rich_carry_invoices[inv_num] = {"date_invoice": inv_date}

    do_map = {row["do_number"]: row for row in pack.get("deliveries", [])}
    rich_pending_dos = {}
    for do_num, deliv_date in closing_raw["pending_dos"].items():
        if do_num in do_map:
            r = do_map[do_num]
            rich_pending_dos[do_num] = {
                "so_number": r["so_number"],
                "scheduled_delivery_date": r["scheduled_delivery_date"],
                "rejection_dpp": r.get("rejection_dpp", "0.00"),
                "customer": r.get("customer", ""),
            }
        elif do_num in raw_opening.get("pending_dos", {}):
            rich_pending_dos[do_num] = raw_opening["pending_dos"][do_num]
        else:
            rich_pending_dos[do_num] = {"scheduled_delivery_date": deliv_date}

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
            "open_invoices_count": len(rich_open_invoices),
            "carry_invoices_count": len(rich_carry_invoices),
            "open_po_count": len(rich_open_po),
            "in_transit_po_count": len(rich_in_transit),
            "pending_dos_count": len(rich_pending_dos),
        },
        "last_sequences": last_sequences,
        "stock": non_zero_stock_closing,
        "open_invoices": rich_open_invoices,
        "carry_invoices": rich_carry_invoices,
        "open_po": rich_open_po,
        "in_transit": rich_in_transit,
        "pending_dos": rich_pending_dos,
        "carry_forward_lines": carry_forward_lines,
        "warehouse_layout_simulation": {
            "warehouse_code": "GD-MND",
            "location_name": "Gudang Utama Maumbi (Minahasa Utara / Manado)",
            "total_storage_pallets": 1287,
            "racking_type": "Selective Pallet Racking (3-4 Tier) & Floor Staging",
            "sections": {
                "GD-MND/UTAMA": {
                    "description": "Penyimpanan Stok Fisik Siap Jual (Fast & Medium Moving)",
                    "pallets_allocated": 1152,
                    "tiering": "Tier 1-4 Selective Racking",
                },
                "GD-MND/STAGING": {
                    "description": "Area Buffer & Staging Dispatch Pengiriman Harian",
                    "pallets_allocated": 110,
                    "tiering": "Hamparan Lantai (Floor Staging)",
                },
                "GD-MND/BAD-STOCK": {
                    "description": "Area Karantina Terisolasi Barang Rusak & Tolakan POD",
                    "pallets_allocated": 25,
                    "tiering": "Hamparan Lantai Tersegel (Floor Dedicated Quarantine)",
                },
            },
        },
    }

    # 7. Validasi Invariant Gates v2 dengan Previous Closing Terverifikasi Independen
    if strict_validate:
        verified_prev_closing = get_verified_previous_closing(period, reg_dir)
        bands = {
            "net_dpp": (Decimal("4000000000.00"), Decimal("4500000000.00")),
            "discount_pct": (Decimal("2.00"), Decimal("3.20")),
            "rejection_pct": (Decimal("1.80"), Decimal("3.00")),
            "active_outlets": (Decimal("200"), Decimal("215")),
        }
        report = validate_pack_report(
            pack=pack,
            opening=gate_opening,
            previous_closing=verified_prev_closing,
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

    # 9. Buat MANIFEST.json dengan SHA-256 LF kanonikal & Pengikatan Source Generator
    generator_sources = {
        "scripts/ops/seed_planner.py": compute_sha256_lf(REPO_ROOT / "scripts" / "ops" / "seed_planner.py"),
        "scripts/ops/generate_period_pack.py": compute_sha256_lf(
            REPO_ROOT / "scripts" / "ops" / "generate_period_pack.py"
        ),
        "scripts/ops/seed_v2_gates.py": compute_sha256_lf(REPO_ROOT / "scripts" / "ops" / "seed_v2_gates.py"),
        "scripts/ops/fmcg_calendar.py": compute_sha256_lf(REPO_ROOT / "scripts" / "ops" / "fmcg_calendar.py"),
    }

    file_manifest: Dict[str, str] = {}
    for p in sorted(exported_files, key=lambda x: x.name):
        file_manifest[p.name] = compute_sha256_lf(p)

    manifest_data = {
        "period": period,
        "pack_start": pack_start,
        "pack_end": pack_end,
        "generator_commit": get_git_head_commit(generator_commit),
        "generator_sources_sha256": generator_sources,
        "canonical_july_15_register_fingerprints": july_fingerprints,
        "configuration": {
            "target_net_dpp": str(config.target_net_dpp),
            "target_discount_pct": str(config.target_discount_pct),
            "target_rejection_pct": str(config.target_rejection_pct),
            "opening_cash": str(opening_cash),
            "tax": gate_config["tax"],
            "min_lead_days": config.min_lead_days,
            "narrative_bands": {k: [str(b[0]), str(b[1])] for k, b in config.bands.items()},
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
    parser.add_argument("--generator-commit", default=None, help="Override commit hash generator untuk manifest")
    args = parser.parse_args()

    op_path = Path(args.opening_state) if args.opening_state else None
    out_dir = Path(args.output_dir) if args.output_dir else None

    print(f"Generating period pack for {args.period}...")
    res = generate_period_pack(
        period=args.period,
        opening_state_path=op_path,
        output_dir=out_dir,
        strict_validate=not args.no_strict,
        generator_commit=args.generator_commit,
    )
    print("Period pack generation complete.")
    print("Summary:")
    for k, v in res["narrative_report"]["metrics"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
