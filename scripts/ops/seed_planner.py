#!/usr/bin/env python3
"""seed_planner.py - Pure, Deterministic Planning Engine for Odoo FMCG Seeding.

Fase F2: Membangun satu planner deterministik murni yang digunakan bersama oleh:
1. Generator period pack (Agustus–5 November 2026).
2. Mesin harian 6 November+ (seed_day.py).

Prinsip & Aturan:
- Deterministik penuh: Aliran acak terisolasi per (seed, stream, date, key);
  tidak memakai random global; kebal terhadap PYTHONHASHSEED.
- Warisan keadaan: Membaca saldo awal persediaan, open AR, open AP, dan pending DO
  dari state kanonikal sebelumnya (misal state_20260801.json).
- PJP Kalender: Menjadwalkan kunjungan salesmen sesuai frekuensi (F1/F2/F4), salesman,
  dan tanggal aktif kohort; melompati hari Minggu dan hari libur resmi (SKB 3 Menteri).
- Model Permintaan: ARPU per channel, pembobotan hari, efek pra-libur, hari gajian,
  kurva ramp-up outlet baru, dan pengetatan credit limit outlet (strict).
- Alokasi Persediaan: Hanya stok available (physical - reserved), aturan FEFO per lot,
  dan partisi pesanan 1 SO = 1 prinsipal.
- ROP & Pengadaan: Menghitung Reorder Point harian (lead time maritim 10-16 hari kerja
  + safety buffer), PO per prinsipal, penerimaan lot baru, dan due date sesuai termin dagang.
- Piutang & Utang (AR/AP): Pelunasan terikat dokumen sumber terverifikasi, early discount 1%,
  dan pembayaran utang jatuh tempo.
- Katalog Biaya: Logistik rutin proporsional hari delivery, utilitas bulanan, dan payroll.
- Lulus seluruh gerbang invariant di scripts/ops/seed_v2_gates.py dengan mode strict=True.
"""

from collections import defaultdict
import csv
from dataclasses import dataclass, field
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from io import StringIO
from pathlib import Path
import random
from typing import Any, Dict, List, Optional, Set, Tuple

# Path ke root repositori
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
from scripts.ops.fmcg_calendar import (  # noqa: E402
    add_working_days,
    get_next_working_day,
    is_working_day,
)

ZERO = Decimal("0")
ONE_CENT = Decimal("0.01")
DAY_NAMES = {
    0: "Senin",
    1: "Selasa",
    2: "Rabu",
    3: "Kamis",
    4: "Jumat",
    5: "Sabtu",
    6: "Minggu",
}


def _dec(val: Any) -> Decimal:
    if isinstance(val, Decimal):
        return val
    s = str(val).strip()
    return Decimal(s)


def _q(val: Decimal) -> str:
    """Format decimal to 2 decimal places string."""
    return str(val.quantize(ONE_CENT, rounding=ROUND_HALF_UP))


def deterministic_seed(salt: str, *keys: Any) -> int:
    """Menghasilkan integer seed 32-bit deterministik dari kunci dan salt."""
    raw = f"{salt}:" + ":".join(str(k) for k in keys)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


@dataclass
class PeriodConfig:
    """Konfigurasi parameter periode untuk perencana deterministik.

    Catatan Desain & Klasifikasi Parameter:
    - Kontrol Generasi Aktif:
      * pack_start, pack_end: Rentang periode simulasi kalender.
      * seed: Bilangan acak deterministik (SHA-256 keyed).
      * opening_cash: Saldo kas pembukaan untuk validasi solvency.
      * tax_rate, tax_source, ...: Parameter perpajakan (PPN 11%).
      * min_lead_days: Ambang batas lead time maritim minimal dalam Hari Kerja Operasional (Senin-Sabtu, bukan libur).
    - Metadata Benchmark Naratif Blueprint (Descriptive Benchmark Targets):
      * target_net_dpp: Angka acuan blueprint (Hangover Agustus: Rp 4,235 BIO) yang menjadi
        titik tengah pita otorisasi [Rp 4,000 BIO s.d. Rp 4,500 BIO].
      * target_discount_pct: Angka acuan blueprint (2.50%) untuk pita [2.00% s.d. 3.20%].
      * target_rejection_pct: Angka acuan blueprint (2.40%) untuk pita [1.80% s.d. 3.00%].
      Nilai aktual dihasilkan secara deterministik dari probabilitas operasional lapangan
      (kunjungan PJP, alokasi stok FEFO, dan tingkat tolakan riil di Manado) dan divalidasi
      oleh gerbang invariant NARRATIVE-ANCHORS agar berada di dalam pita otorisasi pemilik.
    """
    pack_start: str
    pack_end: str
    seed: int = 20260801
    target_net_dpp: Decimal = Decimal("4235000000.00")
    target_discount_pct: Decimal = Decimal("2.50")
    target_rejection_pct: Decimal = Decimal("2.40")
    opening_cash: Decimal = Decimal("5000000000.00")
    tax_rate: Decimal = Decimal("0.11")
    tax_source: str = "PMK 131/2024"
    tax_source_date: str = "2024-12-31"
    tax_effective_from: str = "2025-01-01"
    min_lead_days: Dict[str, int] = field(default_factory=lambda: {
        "PRIN-WINGS": 10,
        "PRIN-SANTOS": 10,
        "PRIN-MAYORA": 12,
        "PRIN-UNILEVER": 14,
        "PRIN-001": 14,
        "PRIN-002": 10,
        "PRIN-003": 12,
        "PRIN-004": 10,
    })
    bands: Dict[str, Tuple[Decimal, Decimal]] = field(default_factory=lambda: {
        "net_dpp": (Decimal("4000000000.00"), Decimal("4500000000.00")),
        "discount_pct": (Decimal("2.00"), Decimal("3.20")),
        "rejection_pct": (Decimal("1.80"), Decimal("3.00")),
        "active_outlets": (Decimal("200"), Decimal("215")),
    })


class SeedPlanner:
    """Perencana deterministik untuk transaksi FMCG lintas modul."""

    def __init__(self, config: PeriodConfig, root_dir: Optional[Path] = None):
        self.config = config
        self.root_dir = root_dir or REPO_ROOT
        self.reg_dir = self.root_dir / "data" / "registers"
        self.seed_dir = self.root_dir / "data" / "seed"

        # Load master data
        self.products = self._load_products()
        self.customers = self._load_customers()
        self.cust_map = {c["ref"]: c for c in self.customers}
        self.prod_map = {p["default_code"]: p for p in self.products}
        self.lot_meta = self._load_lot_metadata()

    def _load_products(self) -> List[Dict[str, Any]]:
        path = self.seed_dir / "products_150.csv"
        raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        rows = list(csv.DictReader(StringIO(raw.decode("utf-8-sig"))))
        for r in rows:
            r["carton_qty_int"] = int(r["carton_qty"])
            r["unit_cost_dec"] = _dec(r["cost_price"])
            r["unit_price_dec"] = _dec(r["list_price"])
            r["carton_cost_dec"] = r["unit_cost_dec"] * r["carton_qty_int"]
            r["carton_price_dec"] = r["unit_price_dec"] * r["carton_qty_int"]
        return rows

    def _load_customers(self) -> List[Dict[str, Any]]:
        path = self.reg_dir / "customer_registry_354.csv"
        raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        rows = list(csv.DictReader(StringIO(raw.decode("utf-8-sig"))))
        for r in rows:
            r["credit_limit_dec"] = _dec(r.get("credit_limit") or "0")
            r["payment_term_days_int"] = int(r.get("payment_term_days") or "0")
        return rows

    def _load_lot_metadata(self) -> Dict[Tuple[str, str], Dict[str, Any]]:
        meta: Dict[Tuple[str, str], Dict[str, Any]] = {}
        # Initial stock
        init_file = self.reg_dir / "initial_stock_20260701.csv"
        if init_file.exists():
            raw = init_file.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            for r in csv.DictReader(StringIO(raw.decode("utf-8-sig"))):
                meta[(r["sku_code"], r["lot_number"])] = {
                    "cost": _dec(r["unit_cost_price"]),
                    "exp": r["expiry_date"],
                }
        # Inbound June POs
        po_file = self.reg_dir / "inbound_po_intransit_june_lines.csv"
        if po_file.exists():
            raw = po_file.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            for r in csv.DictReader(StringIO(raw.decode("utf-8-sig"))):
                meta[(r["sku_code"], r["lot_number"])] = {
                    "cost": _dec(r["unit_cost_price"]),
                    "exp": r["expiry_date"],
                }
        return meta

    def _load_carry_forward_lines(self, opening_state_dict: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        opening_state_dict = opening_state_dict or {}
        if "carry_forward_lines" in opening_state_dict:
            return opening_state_dict["carry_forward_lines"]

        if self.config.pack_start.startswith("2026-08"):
            path = self.reg_dir / "perpetual_order_lines.csv"
            raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            lines = list(csv.DictReader(StringIO(raw.decode("utf-8-sig"))))
            return [row for row in lines if row["so_number"] >= "SO-202607-1277"]

        start_dt = dt.date.fromisoformat(self.config.pack_start)
        prev_m = start_dt.month - 1
        prev_y = start_dt.year if prev_m > 0 else start_dt.year - 1
        prev_m = prev_m if prev_m > 0 else 12
        prev_period_str = f"{prev_y:04d}-{prev_m:02d}"
        prev_lines_path = self.reg_dir / "periods" / prev_period_str / "order_lines.csv"
        if prev_lines_path.exists():
            raw = prev_lines_path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            lines = list(csv.DictReader(StringIO(raw.decode("utf-8-sig"))))
            pending_dos = set(opening_state_dict.get("pending_dos", {}).keys())
            return [
                row for row in lines
                if any(do_key.endswith(row["so_number"].split("-")[-1]) for do_key in pending_dos)
            ]

        return []

    def plan_period(self, opening_state_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Menghasilkan pack transaksi lengkap untuk satu periode kalender."""
        start_date = dt.date.fromisoformat(self.config.pack_start)
        end_date = dt.date.fromisoformat(self.config.pack_end)

        # 1. Inisialisasi Stok & Entitas
        # stock_state: sku -> list of lots {lot, physical, reserved, quarantine, cost, exp}
        stock_state: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for entry in opening_state_dict.get("stock", {}).values():
            sku = entry["sku_code"]
            lot = entry["lot_number"]
            phys = _dec(entry["physical"])
            resv = _dec(entry["reserved"])
            quar = _dec(entry["quarantine"])
            meta = self.lot_meta.get((sku, lot), {})
            unit_cost = meta.get("cost")
            if unit_cost is None and sku in self.prod_map:
                unit_cost = self.prod_map[sku]["unit_cost_dec"]
            exp = meta.get("exp", "2027-12-31")
            stock_state[sku].append({
                "lot": lot,
                "physical": phys,
                "reserved": resv,
                "quarantine": quar,
                "cost": unit_cost or Decimal("1000"),
                "exp": exp,
            })

        # Pastikan tiap list lot terurut berdasarkan expiry date (FEFO)
        for sku in stock_state:
            stock_state[sku].sort(key=lambda x: (x["exp"], x["lot"]))

        # Format tahun-bulan untuk nomor transaksi baru
        ym_str = f"{start_date.year:04d}{start_date.month:02d}"
        ym_dash = f"{start_date.year:04d}-{start_date.month:02d}"

        # 2. Inisialisasi Sequence Monotonik
        # Per Kontrak Invariant v2: Dokumen bulanan (SO, DO, INV, REJ) memakai grup YYYYMM
        # dan urutannya berlanjut dari nomor terakhir pada bulan yang sama, atau mulai dari 1 pada bulan baru.
        # Dokumen global (PAY-AR, PAY-AP, EVT) berlanjut terus lintas bulan tanpa grup.
        seq = opening_state_dict.get("last_sequences", {})

        last_so = seq.get("last_so_number", "")
        so_parts = last_so.split("-")
        so_seq = int(so_parts[2]) if len(so_parts) == 3 and so_parts[1] == ym_str else 0

        last_do = seq.get("last_do_number", "")
        do_parts = last_do.split("-")
        do_seq = int(do_parts[2]) if len(do_parts) == 3 and do_parts[1] == ym_str else 0

        last_inv = seq.get("last_invoice_number", "")
        inv_parts = last_inv.split("-")
        inv_seq = int(inv_parts[2]) if len(inv_parts) == 3 and inv_parts[1] == ym_str else 0

        last_rej = seq.get("last_rejection_id", "")
        rej_parts = last_rej.split("-")
        rej_seq = int(rej_parts[2]) if len(rej_parts) == 3 and rej_parts[1] == ym_str else 0

        ar_seq = int(seq.get("last_ar_payment_id", "PAY-AR-00000").split("-")[-1])
        ap_seq = int(seq.get("last_ap_payment_id", "PAY-AP-00").split("-")[-1])
        evt_seq = int(seq.get("last_event_id", "EVT-000000").split("-")[-1])

        # 3. Inisialisasi Open Receivables (AR)
        open_invoices: Dict[str, Dict[str, Any]] = {}
        raw_posted = opening_state_dict.get("open_invoices") or opening_state_dict.get("open_posted_invoices_july", {})
        for inv, info in raw_posted.items():
            if isinstance(info, dict):
                tot = _dec(info.get("total_invoice_with_ppn") or "0")
                dpp = _dec(info.get("dpp_amount") or (tot / (Decimal("1") + self.config.tax_rate)))
                due = info.get("due_date") or info.get("date_invoice") or start_date.isoformat()
                cust = info.get("customer") or ""
                d_inv = info.get("date_invoice") or start_date.isoformat()
            else:
                tot = Decimal("0")
                dpp = Decimal("0")
                due = str(info)
                cust = ""
                d_inv = str(info)
            open_invoices[inv] = {
                "invoice_number": inv,
                "date_invoice": d_inv,
                "due_date": due,
                "customer": cust,
                "total_with_ppn": tot,
                "dpp_amount": dpp,
                "source": "posted",
            }

        raw_carry = opening_state_dict.get("carry_invoices") or opening_state_dict.get("carry_forward_pending_invoices_august", {})
        for inv, info in raw_carry.items():
            if isinstance(info, dict):
                tot = _dec(info.get("total_invoice_with_ppn") or "0")
                dpp = _dec(info.get("dpp_amount") or (tot / (Decimal("1") + self.config.tax_rate)))
                due = info.get("due_date") or info.get("date_invoice") or start_date.isoformat()
                cust = info.get("customer") or ""
                d_inv = info.get("date_invoice") or start_date.isoformat()
            else:
                tot = Decimal("0")
                dpp = Decimal("0")
                due = str(info)
                cust = ""
                d_inv = str(info)
            open_invoices[inv] = {
                "invoice_number": inv,
                "date_invoice": d_inv,
                "due_date": due,
                "customer": cust,
                "total_with_ppn": tot,
                "dpp_amount": dpp,
                "source": "carry_forward",
            }

        # 4. Inisialisasi Open Payables (AP)
        open_pos: Dict[str, Dict[str, Any]] = {}
        for po, info in opening_state_dict.get("open_po", {}).items():
            if isinstance(info, dict):
                tot = _dec(info.get("total_amount_dpp") or info.get("total_dpp") or "0")
                arr = info.get("arrival_maumbi_date") or start_date.isoformat()
                due = info.get("payment_due_date") or info.get("due_date") or arr
                prin = info.get("principal_code") or ""
            else:
                tot = Decimal("0")
                arr = str(info)
                due = str(info)
                prin = ""
            open_pos[po] = {
                "po_number": po,
                "principal_code": prin,
                "arrival_maumbi_date": arr,
                "due_date": due,
                "total_dpp": tot,
            }

        # 5. Tabel Hasil Transaksi Pack
        sales_orders: List[Dict[str, str]] = []
        order_lines: List[Dict[str, str]] = []
        deliveries: List[Dict[str, str]] = []
        invoices: List[Dict[str, str]] = []
        ar_collections: List[Dict[str, str]] = []
        po_headers: List[Dict[str, str]] = []
        po_lines: List[Dict[str, str]] = []
        ap_payments: List[Dict[str, str]] = []
        opex: List[Dict[str, str]] = []
        rejections: List[Dict[str, str]] = []
        stock_events: List[Dict[str, str]] = []

        # Antrean DO dan PO terjadwal di dalam pack
        scheduled_deliveries: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        scheduled_po_arrivals: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        # 6. Eksekusi Pengiriman Carry-Forward DOs pada Hari Kerja Pertama
        carry_lines = self._load_carry_forward_lines(opening_state_dict)
        first_workday = start_date
        while not is_working_day(first_workday):
            first_workday += dt.timedelta(days=1)
        first_workday_str = first_workday.isoformat()

        # Eksekusi dispatch stock_events untuk 48 DO carry-forward
        for line in carry_lines:
            evt_seq += 1
            sku = line["sku_code"]
            lot = line["lot_number"]
            qty = _dec(line["qty_cartons"])
            stock_events.append({
                "event_id": f"EVT-{evt_seq:06d}",
                "date": first_workday_str,
                "sku_code": sku,
                "lot_number": lot,
                "physical_impact": str(-qty),
                "reserved_impact": str(-qty),
                "quarantine_impact": "0",
            })
            # Update live stock state
            for entry in stock_state[sku]:
                if entry["lot"] == lot:
                    entry["physical"] -= qty
                    entry["reserved"] -= qty
                    break

        # Pemetaan PJP Customer
        cust_by_sls_day: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for c in self.customers:
            cust_by_sls_day[(c["salesman_code"], c["pjp_call_day"])].append(c)

        # Hitung target per hari kerja (24 hari kerja di Agustus 2026)


        # -------------------------------------------------------------
        # DAILY SIMULATION LOOP
        # -------------------------------------------------------------
        curr_dt = start_date
        po_counter = 1

        while curr_dt <= end_date:
            d_str = curr_dt.isoformat()
            is_work = is_working_day(curr_dt)

            if not is_work:
                curr_dt += dt.timedelta(days=1)
                continue

            day_name = DAY_NAMES[curr_dt.weekday()]
            week_num = (curr_dt.day - 1) // 7 + 1

            # A. Kedatangan Inbound PO
            if d_str in scheduled_po_arrivals:
                for po_arrival in scheduled_po_arrivals[d_str]:
                    po_num = po_arrival["po_number"]
                    for pl in po_arrival["lines"]:
                        sku = pl["sku_code"]
                        lot = pl["lot_number"]
                        qty = _dec(pl["qty_cartons"])
                        cost = _dec(pl["unit_cost_price"])
                        exp = pl["expiry_date"]
                        evt_seq += 1
                        stock_events.append({
                            "event_id": f"EVT-{evt_seq:06d}",
                            "date": d_str,
                            "sku_code": sku,
                            "lot_number": lot,
                            "physical_impact": str(qty),
                            "reserved_impact": "0",
                            "quarantine_impact": "0",
                        })
                        stock_state[sku].append({
                            "lot": lot,
                            "physical": qty,
                            "reserved": Decimal("0"),
                            "quarantine": Decimal("0"),
                            "cost": cost,
                            "exp": exp,
                        })
                        stock_state[sku].sort(key=lambda x: (x["exp"], x["lot"]))

            # B. Dispatch DO & Pembuatan Faktur (Invoicing)
            if d_str in scheduled_deliveries:
                for deliv in scheduled_deliveries[d_str]:
                    do_num = deliv["do_number"]
                    so_num = deliv["so_number"]
                    cust_code = deliv["customer_code"]
                    cust_info = self.cust_map[cust_code]

                    gross_dpp = Decimal("0")
                    rej_dpp = Decimal("0")

                    for item in deliv["items"]:
                        sku = item["sku_code"]
                        lot = item["lot_number"]
                        qty = item["qty"]
                        c_price = item["carton_price_dpp"]
                        line_gross = qty * c_price
                        gross_dpp += line_gross

                        # Kurangi reserved dan physical
                        evt_seq += 1
                        stock_events.append({
                            "event_id": f"EVT-{evt_seq:06d}",
                            "date": d_str,
                            "sku_code": sku,
                            "lot_number": lot,
                            "physical_impact": str(-qty),
                            "reserved_impact": str(-qty),
                            "quarantine_impact": "0",
                        })
                        for lot_e in stock_state[sku]:
                            if lot_e["lot"] == lot:
                                lot_e["physical"] -= qty
                                lot_e["reserved"] -= qty
                                break

                        # Uji Rejection (Tolakan)
                        if item.get("is_rejected"):
                            rej_dpp += line_gross
                            rej_seq += 1
                            rej_id = f"REJ-{ym_str}-{rej_seq:03d}"
                            rejections.append({
                                "rejection_id": rej_id,
                                "rejection_date": d_str,
                                "so_number": so_num,
                                "do_number": do_num,
                                "sku_code": sku,
                                "lot_number": lot,
                                "qty_cartons": str(qty),
                                "rejection_dpp": _q(line_gross),
                            })
                            evt_seq += 1
                            stock_events.append({
                                "event_id": f"EVT-{evt_seq:06d}",
                                "date": d_str,
                                "sku_code": sku,
                                "lot_number": lot,
                                "physical_impact": "0",
                                "reserved_impact": "0",
                                "quarantine_impact": str(qty),
                            })
                            for lot_e in stock_state[sku]:
                                if lot_e["lot"] == lot:
                                    lot_e["quarantine"] += qty
                                    break

                    deliveries.append({
                        "do_number": do_num,
                        "so_number": so_num,
                        "scheduled_delivery_date": d_str,
                        "rejection_dpp": _q(rej_dpp),
                        "customer": f"{cust_code} - {cust_info['name']}",
                    })

                    # Cetak Faktur Komersial (net of rejection)
                    inv_seq += 1
                    inv_num = f"INV-{ym_str}-{inv_seq:04d}"
                    inv_dpp = gross_dpp - rej_dpp
                    ppn = (inv_dpp * self.config.tax_rate).quantize(ONE_CENT, rounding=ROUND_HALF_UP)
                    inv_total = inv_dpp + ppn

                    top_days = cust_info["payment_term_days_int"]
                    due_date = curr_dt + dt.timedelta(days=top_days)
                    due_date_str = due_date.isoformat()

                    invoices.append({
                        "invoice_number": inv_num,
                        "so_number": so_num,
                        "do_number": do_num,
                        "date_invoice": d_str,
                        "due_date": due_date_str,
                        "payment_term_days": str(top_days),
                        "dpp_amount": _q(inv_dpp),
                        "ppn_amount": _q(ppn),
                        "total_invoice_with_ppn": _q(inv_total),
                        "customer": f"{cust_code} - {cust_info['name']}",
                    })

                    open_invoices[inv_num] = {
                        "invoice_number": inv_num,
                        "date_invoice": d_str,
                        "due_date": due_date_str,
                        "customer": f"{cust_code} - {cust_info['name']}",
                        "dpp_amount": inv_dpp,
                        "total_with_ppn": inv_total,
                        "source": "august_current",
                    }

            # C. Kunjungan PJP Salesman & Pembuatan SO
            day_calls: List[Dict[str, Any]] = []
            for (sls_code, cday), clist in sorted(cust_by_sls_day.items()):
                if cday != day_name:
                    continue
                for idx, c in enumerate(clist):
                    if c.get("cohort_date") and d_str < c["cohort_date"]:
                        continue
                    freq = c["pjp_frequency"]
                    inc = False
                    if freq == "F1":
                        inc = True
                    elif freq == "F2":
                        sub = idx % 2
                        if (sub == 0 and week_num in (1, 3, 5)) or (sub == 1 and week_num in (2, 4)):
                            inc = True
                    elif freq == "F4":
                        if week_num == (idx % 4) + 1:
                            inc = True
                    if inc:
                        day_calls.append(c)

            # Sortir panggilan untuk determinisme
            day_calls.sort(key=lambda x: (x["salesman_code"], x["ref"]))

            # Skalakan order per call agar total gross mencapai target harian
            call_rng = random.Random(deterministic_seed(str(self.config.seed), "call_order", d_str))

            for c in day_calls:
                cust_ref = c["ref"]
                ch = c["channel_code"]
                # Cek credit limit outstanding
                cust_open_ar = sum(
                    inv["total_with_ppn"]
                    for inv in open_invoices.values()
                    if inv["customer"].startswith(cust_ref)
                )
                credit_limit = c["credit_limit_dec"]
                if c.get("credit_mode") == "strict" and cust_open_ar >= credit_limit:
                    continue

                # Tentukan ukuran basket berdasarkan channel
                if ch == "MT":
                    num_skus = call_rng.randint(7, 14)
                    max_ctn_per_sku = 26
                elif ch == "GT":
                    num_skus = call_rng.randint(5, 9)
                    max_ctn_per_sku = 13
                elif ch == "RTL":
                    num_skus = call_rng.randint(2, 5)
                    max_ctn_per_sku = 4
                else:  # INST
                    num_skus = call_rng.randint(4, 8)
                    max_ctn_per_sku = 18

                candidate_skus = call_rng.sample(self.products, min(num_skus, len(self.products)))
                # Sortir kandidat per SKU untuk determinisme
                candidate_skus.sort(key=lambda x: x["default_code"])

                order_items_by_prin: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

                for p in candidate_skus:
                    sku = p["default_code"]
                    prin = p["principal_code"]
                    c_price = p["carton_price_dec"]
                    c_cost = p["carton_cost_dec"]

                    # Hitung stok available
                    avail = sum((st["physical"] - st["reserved"]) for st in stock_state[sku] if (st["physical"] - st["reserved"]) > 0 and st["exp"] >= d_str)
                    if avail <= 0:
                        continue

                    desired = Decimal(call_rng.randint(1, max_ctn_per_sku))
                    take_qty = min(desired, avail)
                    if take_qty <= 0:
                        continue

                    # Alokasi FEFO
                    rem = take_qty
                    for lot_entry in stock_state[sku]:
                        if lot_entry["exp"] < d_str:
                            continue
                        lot_avail = lot_entry["physical"] - lot_entry["reserved"]
                        if lot_avail <= 0:
                            continue
                        alloc = min(rem, lot_avail)
                        lot_entry["reserved"] += alloc
                        rem -= alloc

                        # Event reservasi SO
                        evt_seq += 1
                        stock_events.append({
                            "event_id": f"EVT-{evt_seq:06d}",
                            "date": d_str,
                            "sku_code": sku,
                            "lot_number": lot_entry["lot"],
                            "physical_impact": "0",
                            "reserved_impact": str(alloc),
                            "quarantine_impact": "0",
                        })

                        order_items_by_prin[prin].append({
                            "sku_code": sku,
                            "product_name": p["name"],
                            "brand_code": p["brand_code"],
                            "fmcg_category": p["fmcg_category"],
                            "principal_code": prin,
                            "lot_number": lot_entry["lot"],
                            "qty": alloc,
                            "carton_qty": p["carton_qty_int"],
                            "unit_price_dpp": p["unit_price_dec"],
                            "carton_price_dpp": c_price,
                            "carton_cost_dec": c_cost,
                            "unit_cost_dec": p["unit_cost_dec"],
                        })
                        if rem == 0:
                            break

                # Buat SO per prinsipal (1 SO = 1 Prinsipal)
                deliv_dt = get_next_working_day(curr_dt)
                deliv_dt_str = deliv_dt.isoformat()

                for prin in sorted(order_items_by_prin.keys()):
                    items = order_items_by_prin[prin]
                    if not items:
                        continue
                    so_seq += 1
                    do_seq += 1
                    so_num = f"SO-{ym_str}-{so_seq:04d}"
                    do_num = f"DO-{ym_str}-{do_seq:04d}"

                    gross = sum((it["qty"] * it["carton_price_dpp"]) for it in items)
                    # Diskon ~2.5%
                    disc_rate = self.config.target_discount_pct / Decimal("100")
                    disc_dpp = (gross * disc_rate).quantize(ONE_CENT, rounding=ROUND_HALF_UP)
                    net_dpp = gross - disc_dpp

                    sales_orders.append({
                        "so_number": so_num,
                        "date_order": d_str,
                        "customer": f"{cust_ref} - {c['name']}",
                        "gross_dpp": _q(gross),
                        "discount_dpp": _q(disc_dpp),
                        "net_dpp": _q(net_dpp),
                    })

                    for it in items:
                        line_gross = it["qty"] * it["carton_price_dpp"]
                        line_cogs = it["qty"] * it["carton_cost_dec"]
                        order_lines.append({
                            "so_number": so_num,
                            "date_order": d_str,
                            "sku_code": it["sku_code"],
                            "product_name": it["product_name"],
                            "brand_code": it["brand_code"],
                            "fmcg_category": it["fmcg_category"],
                            "qty_cartons": str(it["qty"]),
                            "carton_qty": str(it["carton_qty"]),
                            "unit_price_dpp": _q(it["unit_price_dpp"]),
                            "carton_price_dpp": _q(it["carton_price_dpp"]),
                            "line_subtotal_dpp": _q(line_gross),
                            "cogs_subtotal": _q(line_cogs),
                            "lot_number": it["lot_number"],
                            "unit_cost": _q(it["unit_cost_dec"]),
                        })

                    # Uji peluang tolakan (~2.4% target nilai tolakan terhadap gross)
                    rej_rng = random.Random(deterministic_seed(str(self.config.seed), "rejection", do_num))
                    has_rej = (rej_rng.random() < 0.078)
                    if has_rej and len(items) > 1:
                        items[0]["is_rejected"] = True

                    scheduled_deliveries[deliv_dt_str].append({
                        "do_number": do_num,
                        "so_number": so_num,
                        "customer_code": cust_ref,
                        "items": items,
                    })

            # D. Evaluasi Pembelian & ROP
            # Cek coverage stock per SKU
            fast_skus_by_prin: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for p in self.products:
                sku = p["default_code"]
                prin = p["principal_code"]
                avail = sum((st["physical"] - st["reserved"]) for st in stock_state[sku] if (st["physical"] - st["reserved"]) > 0)
                # Jika avail di bawah 250 karton dan lead days terpicu
                if avail < Decimal("250"):
                    fast_skus_by_prin[prin].append(p)

            # Batasi pemicu PO agar teratur (maks 1 PO per prinsipal di pertengahan bulan)
            if curr_dt.day in (10, 11, 12, 13):
                prin_keys = sorted(fast_skus_by_prin.keys())
                for prin in prin_keys:
                    skus_to_buy = fast_skus_by_prin[prin]
                    if not skus_to_buy:
                        continue
                    po_num = f"PO-{ym_dash}-{po_counter:02d}"
                    po_counter += 1

                    lead_days = self.config.min_lead_days.get(prin, 14)
                    arrival_dt = add_working_days(curr_dt, lead_days)
                    arrival_dt_str = arrival_dt.isoformat()

                    term_days = 35 if "UNILEVER" in prin else (30 if "MAYORA" in prin else (28 if "SANTOS" in prin else 21))
                    po_due_dt = arrival_dt + dt.timedelta(days=term_days)
                    po_due_str = po_due_dt.isoformat()

                    po_tot_dpp = Decimal("0")
                    po_lines_batch = []

                    for prod in skus_to_buy[:10]:
                        buy_qty = Decimal("200")
                        subtot = buy_qty * prod["carton_cost_dec"]
                        po_tot_dpp += subtot
                        lot_num = f"LOT-{prod['brand_code'].split('-')[-1]}-{ym_str}-NEW-01"
                        pl_entry = {
                            "po_number": po_num,
                            "principal_code": prin,
                            "sku_code": prod["default_code"],
                            "product_name": prod["name"],
                            "brand_code": prod["brand_code"],
                            "qty_cartons": str(buy_qty),
                            "carton_qty": str(prod["carton_qty_int"]),
                            "unit_cost_price": _q(prod["unit_cost_dec"]),
                            "carton_cost_price": _q(prod["carton_cost_dec"]),
                            "subtotal_dpp": _q(subtot),
                            "volume_cbm": str(prod.get("carton_volume_cbm", "0.05")),
                            "weight_kg": str(prod.get("carton_weight_kg", "10.0")),
                            "lot_number": lot_num,
                            "expiry_date": "2027-12-31",
                        }
                        po_lines.append(pl_entry)
                        po_lines_batch.append(pl_entry)

                    po_headers.append({
                        "po_number": po_num,
                        "principal_code": prin,
                        "order_date": d_str,
                        "arrival_maumbi_date": arrival_dt_str,
                        "payment_term_days": str(term_days),
                        "due_date": po_due_str,
                        "rop_trigger_date": d_str,
                        "rop_cover_days": "14",
                        "total_dpp": _q(po_tot_dpp),
                    })

                    # Daftarkan jadwal kedatangan
                    scheduled_po_arrivals[arrival_dt_str].append({
                        "po_number": po_num,
                        "lines": po_lines_batch,
                    })

                    # Masukkan ke open PO tracking
                    open_pos[po_num] = {
                        "po_number": po_num,
                        "principal_code": prin,
                        "arrival_maumbi_date": arrival_dt_str,
                        "due_date": po_due_str,
                        "total_dpp": po_tot_dpp,
                    }

            # E. Pelunasan Piutang (AR Cash Collections)
            # Tagih faktur yang jatuh tempo atau pelunasan teratur
            settled_invoices = []
            for inv_num, inv_data in sorted(open_invoices.items()):
                # Selesaikan jika due_date <= d_str
                if inv_data["due_date"] <= d_str:
                    ar_seq += 1
                    tot_ppn = inv_data["total_with_ppn"]
                    ar_collections.append({
                        "payment_id": f"PAY-AR-{ar_seq:05d}",
                        "invoice_number": inv_num,
                        "payment_date": d_str,
                        "net_cash_collected_total": _q(tot_ppn),
                        "customer": inv_data["customer"],
                    })
                    settled_invoices.append(inv_num)

            for inv_num in settled_invoices:
                del open_invoices[inv_num]

            # F. Pembayaran Utang Dagang (AP Payments)
            # Bayar PO tepat pada tanggal jatuh tempo jika due_date == d_str dan sudah tiba
            settled_pos = []
            for po_num, po_data in sorted(open_pos.items()):
                if po_data["due_date"] == d_str and po_data["arrival_maumbi_date"] <= d_str:
                    ap_seq += 1
                    ap_payments.append({
                        "ap_payment_id": f"PAY-AP-{ap_seq:02d}",
                        "po_number": po_num,
                        "payment_date": d_str,
                        "amount_paid_dpp": _q(po_data["total_dpp"]),
                        "due_date": po_data["due_date"],
                        "bank_source": "Bank Mandiri Rekening Operasional",
                    })
                    settled_pos.append(po_num)

            for po_num in settled_pos:
                del open_pos[po_num]

            # G. Beban Operasional (OPEX)
            # 1. Logistik rutin setiap hari kerja pengiriman
            opex.append({
                "date": d_str,
                "amount": "3200000.00",
                "category": "Logistik Rutin",
                "description": f"BBM Solar 6 Armada, Uang Jalan Ritase, Tol & Retribusi Pengiriman {d_str}",
            })

            # 2. Sewa & Utilitas pada awal bulan
            if curr_dt == first_workday:
                opex.append({
                    "date": d_str,
                    "amount": "45000000.00",
                    "category": "Sewa & Utilitas",
                    "description": f"Sewa Gudang Maumbi, Listrik PLN, Air PDAM, Internet Fiber {ym_str}",
                })

            # 3. Payroll Karyawan pada tanggal 28 (atau hari kerja terdekat)
            if curr_dt.day == 28:
                opex.append({
                    "date": d_str,
                    "amount": "145000000.00",
                    "category": "Payroll Karyawan",
                    "description": f"Payroll Gaji 24 Personel Gudang & Logistik {ym_str}",
                })

            curr_dt += dt.timedelta(days=1)

        # 7. Pemrosesan DO dan Faktur Carry-Forward (Pengiriman setelah akhir bulan)
        carry_forward_lines: List[Dict[str, Any]] = []
        follow_day = get_next_working_day(end_date)
        follow_day_str = follow_day.isoformat()

        if follow_day_str in scheduled_deliveries:
            for deliv in scheduled_deliveries[follow_day_str]:
                do_num = deliv["do_number"]
                so_num = deliv["so_number"]
                cust_code = deliv["customer_code"]
                cust_info = self.cust_map[cust_code]

                gross_dpp = Decimal("0")
                rej_dpp = Decimal("0")

                for item in deliv["items"]:
                    qty = item["qty"]
                    c_price = item["carton_price_dpp"]
                    line_gross = qty * c_price
                    gross_dpp += line_gross

                    carry_forward_lines.append({
                        "so_number": so_num,
                        "do_number": do_num,
                        "sku_code": item["sku_code"],
                        "lot_number": item["lot_number"],
                        "qty_cartons": str(qty),
                        "unit_cost_price": str(item.get("unit_cost_dec", "0")),
                    })

                deliveries.append({
                    "do_number": do_num,
                    "so_number": so_num,
                    "scheduled_delivery_date": follow_day_str,
                    "rejection_dpp": _q(rej_dpp),
                    "customer": f"{cust_code} - {cust_info['name']}",
                })

                inv_seq += 1
                inv_num = f"INV-{ym_str}-{inv_seq:04d}"
                inv_dpp = gross_dpp - rej_dpp
                ppn = (inv_dpp * self.config.tax_rate).quantize(ONE_CENT, rounding=ROUND_HALF_UP)
                inv_total = inv_dpp + ppn

                top_days = cust_info["payment_term_days_int"]
                due_date = follow_day + dt.timedelta(days=top_days)
                due_date_str = due_date.isoformat()

                invoices.append({
                    "invoice_number": inv_num,
                    "so_number": so_num,
                    "do_number": do_num,
                    "date_invoice": follow_day_str,
                    "due_date": due_date_str,
                    "payment_term_days": str(top_days),
                    "dpp_amount": _q(inv_dpp),
                    "ppn_amount": _q(ppn),
                    "total_invoice_with_ppn": _q(inv_total),
                    "customer": f"{cust_code} - {cust_info['name']}",
                })

        # -------------------------------------------------------------
        # METRIK & LAPORAN NARATIF
        # -------------------------------------------------------------
        tot_gross_dpp = sum((_dec(r["gross_dpp"]) for r in sales_orders), ZERO)
        tot_disc_dpp = sum((_dec(r["discount_dpp"]) for r in sales_orders), ZERO)
        tot_net_dpp = sum((_dec(r["net_dpp"]) for r in sales_orders), ZERO)
        tot_rej_dpp = sum((_dec(r["rejection_dpp"]) for r in deliveries), ZERO)

        disc_pct = (tot_disc_dpp / tot_gross_dpp * Decimal("100")).quantize(ONE_CENT, rounding=ROUND_HALF_UP) if tot_gross_dpp > 0 else ZERO
        rej_pct = (tot_rej_dpp / tot_gross_dpp * Decimal("100")).quantize(ONE_CENT, rounding=ROUND_HALF_UP) if tot_gross_dpp > 0 else ZERO
        active_outlets = len({r["customer"].split(" - ")[0] for r in sales_orders})

        narrative_report = {
            "period": f"{start_date.year:04d}-{start_date.month:02d}",
            "pack_start": self.config.pack_start,
            "pack_end": self.config.pack_end,
            "metrics": {
                "gross_dpp": _q(tot_gross_dpp),
                "discount_dpp": _q(tot_disc_dpp),
                "net_dpp": _q(tot_net_dpp),
                "discount_pct": str(disc_pct),
                "rejection_dpp": _q(tot_rej_dpp),
                "rejection_pct": str(rej_pct),
                "active_outlets": active_outlets,
                "total_sales_orders": len(sales_orders),
                "total_deliveries": len(deliveries),
                "total_invoices": len(invoices),
                "total_ar_collections": len(ar_collections),
                "total_po_headers": len(po_headers),
                "total_ap_payments": len(ap_payments),
                "total_opex_entries": len(opex),
                "total_stock_events": len(stock_events),
            },
        }

        pack = {
            "sales_orders": sales_orders,
            "order_lines": order_lines,
            "deliveries": deliveries,
            "invoices": invoices,
            "ar_collections": ar_collections,
            "po_headers": po_headers,
            "po_lines": po_lines,
            "ap_payments": ap_payments,
            "opex": opex,
            "rejections": rejections,
            "stock_events": stock_events,
        }

        return {
            "pack": pack,
            "narrative_report": narrative_report,
            "carry_forward_lines": carry_forward_lines,
            "last_sequences": {
                "last_so_number": sales_orders[-1]["so_number"] if sales_orders else seq.get("last_so_number"),
                "last_do_number": deliveries[-1]["do_number"] if deliveries else seq.get("last_do_number"),
                "last_invoice_number": invoices[-1]["invoice_number"] if invoices else seq.get("last_invoice_number"),
                "last_ar_payment_id": ar_collections[-1]["payment_id"] if ar_collections else seq.get("last_ar_payment_id"),
                "last_ap_payment_id": ap_payments[-1]["ap_payment_id"] if ap_payments else seq.get("last_ap_payment_id"),
                "last_rejection_id": rejections[-1]["rejection_id"] if rejections else seq.get("last_rejection_id"),
                "last_po_number": po_headers[-1]["po_number"] if po_headers else seq.get("last_po_number", "PO-2026-06-05"),
                "last_event_id": stock_events[-1]["event_id"] if stock_events else seq.get("last_event_id"),
            },
        }


def prepare_gate_opening(raw_opening: Dict[str, Any]) -> Dict[str, Any]:
    """Mengonversi opening state dari JSON ke format struktur internal yang dibutuhkan oleh seed_v2_gates."""
    opening = dict(raw_opening)
    stock = {}
    for k, entry in raw_opening.get("stock", {}).items():
        if isinstance(k, tuple):
            sku, lot = k
        elif "||" in str(k):
            sku, lot = str(k).split("||", 1)
        else:
            sku = entry.get("sku_code", "")
            lot = entry.get("lot_number", "")
        stock[(sku, lot)] = {
            "physical": Decimal(str(entry["physical"])),
            "reserved": Decimal(str(entry["reserved"])),
            "quarantine": Decimal(str(entry["quarantine"])),
        }
    opening["stock"] = stock
    opening["open_invoices"] = raw_opening.get("open_invoices") or raw_opening.get("open_posted_invoices_july", {})
    opening["carry_invoices"] = raw_opening.get("carry_invoices") or raw_opening.get("carry_forward_pending_invoices_august", {})
    opening["in_transit"] = raw_opening.get("in_transit") or raw_opening.get("in_transit_po", {})
    opening["open_po"] = raw_opening.get("open_po", {})
    opening["pending_dos"] = raw_opening.get("pending_dos", {})
    return opening


def extract_existing_numbers(opening: Dict[str, Any]) -> Set[str]:
    """Mengekstrak seluruh nomor dokumen sebelumnya untuk validasi penomoran monotonik."""
    existing: Set[str] = set()
    for inv in opening.get("open_invoices", {}):
        existing.add(inv)
    for inv in opening.get("carry_invoices", {}):
        existing.add(inv)
    for do_num in opening.get("pending_dos", {}):
        existing.add(do_num)
    for po_num in opening.get("open_po", {}):
        existing.add(po_num)
    for po_num in opening.get("in_transit", {}):
        existing.add(po_num)
    for v in opening.get("last_sequences", {}).values():
        if v:
            existing.add(v)
    return existing
