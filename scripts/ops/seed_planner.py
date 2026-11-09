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

# Fixture Katalog Insiden Penolakan Pengiriman (Provenance & Causal Fixture)
# Menjamin integritas kausal: alasan penolakan berakar pada kondisi faktual serah terima barang di outlet.
REJECTION_INCIDENT_CATALOG = {
    "TRANSIT_ROUGH_ROAD": {
        "reason": "KEMASAN_RUSAK_TRANSIT",
        "evidence_type": "BATCH_REFERENCE",
        "evidence_photo_ref": "/evidence/batch/incident_transit_rough_road_202608.jpg",
        "incident_batch_ref": "BAP-TR-202608-01",
        "desc": "Kardus penyok/sobek akibat guncangan distribusi armada rute luar kota/jalan berlubang",
    },
    "FACTORY_SEAL_LEAK": {
        "reason": "SEGEL_PABRIK_BOCOR",
        "evidence_type": "ACTUAL",
        "evidence_photo_ref": "/evidence/actual/pod_rejection_seal_leak.jpg",
        "incident_batch_ref": "BAP-QA-202608-02",
        "desc": "Kebocoran segel botol/kemasan produk cair dari pabrik prinsipal",
    },
    "SLA_EXPIRY_REJECT": {
        "reason": "EXPIRY_DEKAT_DITOLAK",
        "evidence_type": "NONE",
        "evidence_photo_ref": None,
        "incident_batch_ref": "BAP-SLA-202608-03",
        "desc": "Sisa umur simpan di bawah SLA penerimaan outlet modern trade (< 6 bulan)",
    },
    "SYNTHETIC_CAN_DENT": {
        "reason": "DEFECT_KALENG_PENYOK",
        "evidence_type": "SYNTHETIC",
        "evidence_photo_ref": "/evidence/synthetic/sample_carton_damage_synthetic.jpg",
        "incident_batch_ref": "SIM-QA-202608-04",
        "desc": "Sampel kaleng penyok untuk pengujian kalibrasi visual PWA",
    },
}


def resolve_rejection_incident(sku: str, lot: str, ch: str, vehicle_plate: str) -> Dict[str, Any]:
    """Menentukan insiden penolakan secara kausal dan deterministik berdasarkan konteks transaksi."""
    # 1. Modern Trade (MT) memiliki kebijakan ketat SLA sisa shelf-life (penolakan administratif tanpa kerusakan fisik)
    if ch == "MT":
        return REJECTION_INCIDENT_CATALOG["SLA_EXPIRY_REJECT"]

    # 2. Rute luar kota / armada antar-kota dengan guncangan jalan (Minahasa/Bitung: DB 8910 TK, dsb)
    if vehicle_plate in ("DB 8910 TK", "DB 8567 TR"):
        return REJECTION_INCIDENT_CATALOG["TRANSIT_ROUGH_ROAD"]

    # 3. Produk cair / botol / RTD yang rentan bocor segel pabrikan
    if any(k in sku for k in ("KAPAL", "ABC", "WINGS")):
        return REJECTION_INCIDENT_CATALOG["FACTORY_SEAL_LEAK"]

    # 4. Default penolakan handling umum
    return REJECTION_INCIDENT_CATALOG["SYNTHETIC_CAN_DENT"]


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
            r["carton_volume_cbm"] = _dec(r.get("carton_volume_cbm") or "0.05")
            r["carton_weight_kg"] = _dec(r.get("carton_weight_kg") or "10.0")
        return rows

    def _load_customers(self) -> List[Dict[str, Any]]:
        path = self.reg_dir / "customer_registry_354.csv"
        raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        rows = list(csv.DictReader(StringIO(raw.decode("utf-8-sig"))))
        for idx, r in enumerate(rows):
            r["credit_limit_dec"] = _dec(r.get("credit_limit") or "0")
            r["payment_term_days_int"] = int(r.get("payment_term_days") or "0")
            vat_raw = r.get("vat") or ""
            vat_clean = "".join(ch for ch in vat_raw if ch.isdigit())
            vat_16 = vat_clean[:16] if len(vat_clean) >= 16 else vat_clean.zfill(16)
            ch = r.get("channel_code", "")
            is_comp = str(r.get("is_company", "")).strip().lower() == "true"

            # Pisahkan status PKP dari jenis identitas perpajakan (Coretax Architecture)
            if is_comp and len(vat_clean) >= 15:
                # Badan Usaha PKP (Modern Trade DC & Superstore, Grosir Berbadan Usaha, Institusi)
                r["is_pkp"] = True
                r["buyer_id_type"] = "NPWP16"
                r["customer_tax_id"] = vat_16
                r["customer_vat"] = vat_16
            elif ch in ("MT", "INST") or (ch == "GT" and is_comp):
                # Cadangan PKP untuk channel korporat bila format awal bukan 16 digit
                r["is_pkp"] = True
                r["buyer_id_type"] = "NPWP16"
                r["customer_tax_id"] = vat_16 if vat_clean else f"0123456789{idx+1:06d}"
                r["customer_vat"] = r["customer_tax_id"]
            else:
                # Retail Warung/Kios Perorangan (Non-PKP karena omzet di bawah threshold pengusaha kecil)
                r["is_pkp"] = False
                # Di sistem Coretax DJP, WPOP pemilik warung retail didaftarkan dengan NIK KTP Manado (kode 7171).
                # Sebagian kecil outlet retail (sekitar 10%) belum terdata NIK-nya dicatat dengan TIN_0 (0000000000000000).
                if idx % 10 == 0:
                    r["buyer_id_type"] = "TIN_0"
                    r["customer_tax_id"] = "0000000000000000"
                    r["customer_vat"] = "0000000000000000"
                else:
                    r["buyer_id_type"] = "NIK"
                    nik_id = f"717101{((idx * 7) % 28 + 1):02d}08{80 + (idx % 20):02d}{idx+1:04d}"
                    r["customer_tax_id"] = nik_id
                    r["customer_vat"] = nik_id
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
        so_lookup: Dict[str, Dict[str, Any]] = {}
        daily_vehicle_load: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(lambda: defaultdict(lambda: {
            "orders": 0,
            "cartons": Decimal("0"),
            "weight_kg": Decimal("0"),
            "volume_cbm": Decimal("0"),
        }))

        # 6. Eksekusi Pengiriman Carry-Forward DOs pada Hari Kerja Pertama
        carry_lines = self._load_carry_forward_lines(opening_state_dict)
        first_workday = start_date
        while not is_working_day(first_workday):
            first_workday += dt.timedelta(days=1)
        first_workday_str = first_workday.isoformat()

        # Eksekusi dispatch stock_events untuk carry-forward
        for line in carry_lines:
            evt_seq += 1
            sku = line["sku_code"]
            lot = line["lot_number"]
            qty = _dec(line["qty_cartons"])
            is_rej = str(line.get("is_rejected", "")).lower() in ("true", "1")

            # 1. Dispatch pelepasan reserved dan physical
            stock_events.append({
                "event_id": f"EVT-{evt_seq:06d}",
                "date": first_workday_str,
                "sku_code": sku,
                "lot_number": lot,
                "physical_impact": str(-qty),
                "reserved_impact": str(-qty),
                "quarantine_impact": "0",
            })
            for entry in stock_state[sku]:
                if entry["lot"] == lot:
                    entry["physical"] -= qty
                    entry["reserved"] -= qty
                    break

            # 2. Jika item ditolak, masukkan kuantitas ke karantina
            if is_rej:
                evt_seq += 1
                stock_events.append({
                    "event_id": f"EVT-{evt_seq:06d}",
                    "date": first_workday_str,
                    "sku_code": sku,
                    "lot_number": lot,
                    "physical_impact": "0",
                    "reserved_impact": "0",
                    "quarantine_impact": str(qty),
                })
                for entry in stock_state[sku]:
                    if entry["lot"] == lot:
                        entry["quarantine"] += qty
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
                    so_info = so_lookup[so_num]

                    gross_dpp = Decimal("0")
                    rej_net_dpp = Decimal("0")

                    for item in deliv["items"]:
                        sku = item["sku_code"]
                        lot = item["lot_number"]
                        qty = item["qty"]
                        c_price = item["carton_price_dpp"]
                        line_gross = qty * c_price
                        line_disc = item.get("discount_dpp", Decimal("0"))
                        line_net_rej = line_gross - line_disc
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

                        # Uji Rejection (Tolakan Pengiriman dihitung Netto Diskon)
                        if item.get("is_rejected"):
                            rej_net_dpp += line_net_rej
                            rej_seq += 1
                            rej_id = f"REJ-{ym_str}-{rej_seq:03d}"
                            inc = resolve_rejection_incident(
                                sku,
                                lot,
                                cust_info.get("channel_code", ""),
                                cust_info.get("delivery_vehicle", ""),
                            )
                            rejections.append({
                                "rejection_id": rej_id,
                                "rejection_date": d_str,
                                "so_number": so_num,
                                "do_number": do_num,
                                "sku_code": sku,
                                "lot_number": lot,
                                "qty_cartons": str(qty),
                                "line_gross_dpp": _q(line_gross),
                                "line_disc_dpp": _q(line_disc),
                                "rejection_dpp": _q(line_net_rej),
                                "rejection_reason": inc["reason"],
                                "incident_batch_ref": inc["incident_batch_ref"],
                                "evidence_type": inc["evidence_type"],
                                "evidence_photo_ref": inc["evidence_photo_ref"] or "",
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
                        "rejection_dpp": _q(rej_net_dpp),
                        "customer": f"{cust_code} - {cust_info['name']}",
                    })

                    # Cetak Faktur Komersial (net of rejection & net of discount)
                    # Sesuai PMK 131/2024: DPP Nilai Lain = 11/12 x Nilai Jual Komersial Netto, PPN 12%
                    inv_seq += 1
                    inv_num = f"INV-{ym_str}-{inv_seq:04d}"
                    inv_comm_dpp = so_info["net_dpp"] - rej_net_dpp
                    inv_tax_base = (inv_comm_dpp * Decimal(11) / Decimal(12)).quantize(ONE_CENT, rounding=ROUND_HALF_UP)
                    statutory_rate = Decimal("0.12")
                    ppn = (inv_tax_base * statutory_rate).quantize(ONE_CENT, rounding=ROUND_HALF_UP)
                    inv_total = inv_comm_dpp + ppn

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
                        "commercial_dpp": _q(inv_comm_dpp),
                        "dpp_amount": _q(inv_tax_base),
                        "tax_rate": "0.12",
                        "ppn_amount": _q(ppn),
                        "total_invoice_with_ppn": _q(inv_total),
                        "customer": f"{cust_code} - {cust_info['name']}",
                        "is_pkp": str(cust_info["is_pkp"]),
                        "buyer_id_type": cust_info["buyer_id_type"],
                        "customer_tax_id": cust_info["customer_tax_id"],
                        "customer_vat": cust_info["customer_vat"],
                        "tax_invoice_type": "DPP_NILAI_LAIN",
                        "tax_code": "04",
                    })

                    open_invoices[inv_num] = {
                        "invoice_number": inv_num,
                        "date_invoice": d_str,
                        "due_date": due_date_str,
                        "customer": f"{cust_code} - {cust_info['name']}",
                        "commercial_dpp": inv_comm_dpp,
                        "dpp_amount": inv_tax_base,
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
                            "carton_volume_cbm": p["carton_volume_cbm"],
                            "carton_weight_kg": p["carton_weight_kg"],
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

                    # Hitung line discount deterministik berbasis pricelist tier & selektif promo
                    base_ch_disc = {
                        "MT": Decimal("2.20"),
                        "GT": Decimal("1.60"),
                        "INST": Decimal("1.50"),
                        "RTL": Decimal("1.20"),
                    }
                    base_pct = base_ch_disc.get(ch, Decimal("1.00"))

                    total_so_gross = Decimal("0")
                    total_so_disc = Decimal("0")

                    for it in items:
                        line_gross = it["qty"] * it["carton_price_dpp"]
                        line_cogs = it["qty"] * it["carton_cost_dec"]

                        pct = base_pct
                        h = deterministic_seed(str(self.config.seed), "promo_line_v4", so_num, it["sku_code"])
                        promo_id = ""
                        prin_code = it["principal_code"]
                        if ("MAYORA" in prin_code or "003" in prin_code) and (h % 100 < 35):
                            pct += Decimal("2.50")
                            promo_id = "PROMO-2026-MAYORA-FMCG"
                        elif ("SANTOS" in prin_code or "002" in prin_code) and (h % 100 < 30):
                            pct += Decimal("2.00")
                            promo_id = "PROMO-2026-SANTOS-KOPI"
                        elif ("WINGS" in prin_code or "004" in prin_code) and it["qty"] >= 10:
                            pct += Decimal("1.20")
                            promo_id = "TIER-VOL-WINGS-10"
                        elif ("UNILEVER" in prin_code or "001" in prin_code) and it["qty"] >= 8:
                            pct += Decimal("1.20")
                            promo_id = "TIER-VOL-UNILEVER-8"

                        line_disc = (line_gross * pct / Decimal("100")).quantize(ONE_CENT, rounding=ROUND_HALF_UP)
                        line_net = line_gross - line_disc

                        it["discount_pct"] = pct
                        it["discount_dpp"] = line_disc
                        it["line_net_dpp"] = line_net
                        it["promo_id"] = promo_id

                        total_so_gross += line_gross
                        total_so_disc += line_disc

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
                            "discount_pct": _q(pct),
                            "discount_dpp": _q(line_disc),
                            "line_net_dpp": _q(line_net),
                            "promo_id": promo_id,
                            "cogs_subtotal": _q(line_cogs),
                            "lot_number": it["lot_number"],
                            "unit_cost": _q(it["unit_cost_dec"]),
                        })

                    total_so_net = total_so_gross - total_so_disc

                    sales_orders.append({
                        "so_number": so_num,
                        "date_order": d_str,
                        "customer": f"{cust_ref} - {c['name']}",
                        "gross_dpp": _q(total_so_gross),
                        "discount_dpp": _q(total_so_disc),
                        "net_dpp": _q(total_so_net),
                    })

                    so_lookup[so_num] = {
                        "gross_dpp": total_so_gross,
                        "discount_dpp": total_so_disc,
                        "net_dpp": total_so_net,
                    }

                    # Catat muatan armada pengiriman untuk load balancing & metrik
                    deliv_veh_raw = c.get("delivery_vehicle") or "DB 8234 QX (Gran Max Box)"
                    veh_plate = deliv_veh_raw.split(" (")[0]
                    daily_vehicle_load[deliv_dt_str][veh_plate]["orders"] += 1
                    for it in items:
                        daily_vehicle_load[deliv_dt_str][veh_plate]["cartons"] += it["qty"]
                        daily_vehicle_load[deliv_dt_str][veh_plate]["weight_kg"] += it["qty"] * it["carton_weight_kg"]
                        daily_vehicle_load[deliv_dt_str][veh_plate]["volume_cbm"] += it["qty"] * it["carton_volume_cbm"]

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

                    po_tax_base = (po_tot_dpp * Decimal(11) / Decimal(12)).quantize(ONE_CENT, rounding=ROUND_HALF_UP)
                    po_ppn = (po_tax_base * Decimal("0.12")).quantize(ONE_CENT, rounding=ROUND_HALF_UP)
                    po_total_with_ppn = po_tot_dpp + po_ppn

                    po_headers.append({
                        "po_number": po_num,
                        "principal_code": prin,
                        "order_date": d_str,
                        "arrival_maumbi_date": arrival_dt_str,
                        "payment_term_days": str(term_days),
                        "due_date": po_due_str,
                        "rop_trigger_date": d_str,
                        "rop_cover_days": "14",
                        "commercial_dpp": _q(po_tot_dpp),
                        "total_dpp": _q(po_tot_dpp),
                        "tax_dpp": _q(po_tax_base),
                        "tax_code": "04",
                        "tax_rate": "0.12",
                        "ppn_amount": _q(po_ppn),
                        "total_with_ppn": _q(po_total_with_ppn),
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
                "description": f"BBM Solar 6 Armada, Tol & Retribusi Pengiriman {d_str}",
            })

            # 1b. Uang jalan ritase ke-2 armada yang over-capacity (> 5.4 CBM untuk L300 FB DB 8456 FB)
            l300_vol = daily_vehicle_load.get(d_str, {}).get("DB 8456 FB", {}).get("volume_cbm", ZERO)
            if l300_vol > Decimal("5.40"):
                opex.append({
                    "date": d_str,
                    "amount": "100000.00",
                    "category": "Uang Jalan Ritase",
                    "description": f"Uang jalan ritase ke-2 pengiriman Manado Barat - Mitsubishi L300 FB DB 8456 FB (Driver: Eko Prasetyo, volume {_q(l300_vol)} CBM)",
                })

            # 2. Sewa & Utilitas pada awal bulan
            if curr_dt == first_workday:
                opex.append({
                    "date": d_str,
                    "amount": "45000000.00",
                    "category": "Sewa & Utilitas",
                    "description": f"Sewa Gudang Maumbi, Listrik PLN, Air PDAM, Internet Fiber {ym_str}",
                })

            # 2b. Servis Rutin Berkala & Ganti Oli 6 Armada Bengkel Resmi pada pertengahan bulan
            if curr_dt.day == 15:
                opex.append({
                    "date": d_str,
                    "amount": "18500000.00",
                    "category": "Pemeliharaan Armada",
                    "description": f"Servis berkala & ganti oli mesin/transmisi 6 armada logistik bengkel resmi Manado {ym_str}",
                })

            # 2c. Uji Berkala KIR Armada Dishub Kota Manado
            if curr_dt.day == 18:
                opex.append({
                    "date": d_str,
                    "amount": "600000.00",
                    "category": "Perizinan & Regulasi",
                    "description": "Biaya retribusi uji berkala KIR Dishub Kota Manado Mitsubishi L300 FB DB 8456 FB",
                })

            # 3. Payroll Karyawan pada tanggal 28 (atau hari kerja terdekat)
            if curr_dt.day == 28:
                opex.append({
                    "date": d_str,
                    "amount": "145000000.00",
                    "category": "Payroll Karyawan",
                    "description": f"Payroll Gaji 24 Personel Gudang & Logistik {ym_str}",
                })
                # 3b. Insentif & Komisi Sales Lapangan atas pencapaian target kunjungan PJP
                opex.append({
                    "date": d_str,
                    "amount": "12000000.00",
                    "category": "Komisi & Insentif",
                    "description": f"Insentif & komisi penjualan salesman lapangan PJP periode {ym_str}",
                })

            # 4. Administrasi & Kliring Bank Operasional pada akhir bulan
            if curr_dt.day == 31:
                opex.append({
                    "date": d_str,
                    "amount": "1200000.00",
                    "category": "Administrasi Bank",
                    "description": f"Biaya administrasi rekening giro operasional dan kliring SKN/BI-FAST Bank Mandiri {ym_str}",
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
                so_info = so_lookup[so_num]

                gross_dpp = Decimal("0")
                rej_net_dpp = Decimal("0")

                for item in deliv["items"]:
                    qty = item["qty"]
                    c_price = item["carton_price_dpp"]
                    line_gross = qty * c_price
                    line_disc = item.get("discount_dpp", Decimal("0"))
                    line_net_rej = line_gross - line_disc
                    gross_dpp += line_gross

                    is_rej = bool(item.get("is_rejected", False))
                    if is_rej:
                        rej_net_dpp += line_net_rej
                        rej_seq += 1
                        rej_id = f"REJ-{ym_str}-{rej_seq:03d}"
                        inc = resolve_rejection_incident(
                            item["sku_code"],
                            item["lot_number"],
                            cust_info.get("channel_code", ""),
                            cust_info.get("delivery_vehicle", ""),
                        )
                        rejections.append({
                            "rejection_id": rej_id,
                            "rejection_date": follow_day_str,
                            "so_number": so_num,
                            "do_number": do_num,
                            "sku_code": item["sku_code"],
                            "lot_number": item["lot_number"],
                            "qty_cartons": str(qty),
                            "line_gross_dpp": _q(line_gross),
                            "line_disc_dpp": _q(line_disc),
                            "rejection_dpp": _q(line_net_rej),
                            "rejection_reason": inc["reason"],
                            "incident_batch_ref": inc["incident_batch_ref"],
                            "evidence_type": inc["evidence_type"],
                            "evidence_photo_ref": inc["evidence_photo_ref"] or "",
                        })

                    carry_forward_lines.append({
                        "so_number": so_num,
                        "do_number": do_num,
                        "sku_code": item["sku_code"],
                        "lot_number": item["lot_number"],
                        "qty_cartons": str(qty),
                        "unit_cost_price": str(item.get("unit_cost_dec", "0")),
                        "is_rejected": is_rej,
                        "rejection_dpp": _q(line_net_rej) if is_rej else "0.00",
                    })

                deliveries.append({
                    "do_number": do_num,
                    "so_number": so_num,
                    "scheduled_delivery_date": follow_day_str,
                    "rejection_dpp": _q(rej_net_dpp),
                    "customer": f"{cust_code} - {cust_info['name']}",
                })

                inv_seq += 1
                inv_num = f"INV-{ym_str}-{inv_seq:04d}"
                inv_comm_dpp = so_info["net_dpp"] - rej_net_dpp
                inv_tax_base = (inv_comm_dpp * Decimal(11) / Decimal(12)).quantize(ONE_CENT, rounding=ROUND_HALF_UP)
                statutory_rate = Decimal("0.12")
                ppn = (inv_tax_base * statutory_rate).quantize(ONE_CENT, rounding=ROUND_HALF_UP)
                inv_total = inv_comm_dpp + ppn

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
                    "commercial_dpp": _q(inv_comm_dpp),
                    "dpp_amount": _q(inv_tax_base),
                    "tax_rate": "0.12",
                    "ppn_amount": _q(ppn),
                    "total_invoice_with_ppn": _q(inv_total),
                    "customer": f"{cust_code} - {cust_info['name']}",
                    "is_pkp": str(cust_info["is_pkp"]),
                    "buyer_id_type": cust_info["buyer_id_type"],
                    "customer_tax_id": cust_info["customer_tax_id"],
                    "customer_vat": cust_info["customer_vat"],
                    "tax_invoice_type": "DPP_NILAI_LAIN",
                    "tax_code": "04",
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

        # Kompilasi tabel metrik logistik & ritase armada harian
        vehicle_meta = {
            "DB 8345 MK": {"name": "Mitsubishi Canter CDD", "driver": "Meidy Palit", "capacity_cbm": Decimal("16.00"), "capacity_kg": Decimal("4000.00"), "route": "Modern Trade & Key Accounts"},
            "DB 8456 FB": {"name": "Mitsubishi L300 FB", "driver": "Eko Prasetyo", "capacity_cbm": Decimal("5.40"), "capacity_kg": Decimal("1250.00"), "route": "Manado Barat & Sario"},
            "DB 8567 TR": {"name": "Isuzu Traga Pick Up", "driver": "Stenly Sumampouw", "capacity_cbm": Decimal("6.80"), "capacity_kg": Decimal("1500.00"), "route": "Manado Selatan & Malalayang"},
            "DB 8234 QX": {"name": "Daihatsu Gran Max Box", "driver": "Jemmy Rondonuwu", "capacity_cbm": Decimal("4.20"), "capacity_kg": Decimal("1000.00"), "route": "Manado Timur & Tikala"},
            "DB 8123 QA": {"name": "Daihatsu Gran Max BV", "driver": "Hendra Tendean", "capacity_cbm": Decimal("4.20"), "capacity_kg": Decimal("1000.00"), "route": "Manado Utara & Tuminting"},
            "DB 8910 TK": {"name": "Isuzu Elf NLR 55", "driver": "Michael Pangemanan", "capacity_cbm": Decimal("8.50"), "capacity_kg": Decimal("2500.00"), "route": "Luar Kota Minahasa & Bitung"},
        }

        daily_logistics_metrics: List[Dict[str, str]] = []
        for date_k in sorted(daily_vehicle_load.keys()):
            for plate, meta in sorted(vehicle_meta.items()):
                load = daily_vehicle_load[date_k].get(plate, {"orders": 0, "cartons": ZERO, "weight_kg": ZERO, "volume_cbm": ZERO})
                orders = load["orders"]
                cartons = load["cartons"]
                weight_kg = load["weight_kg"]
                volume_cbm = load["volume_cbm"]
                cap_cbm = meta["capacity_cbm"]
                util_pct = (volume_cbm / cap_cbm * Decimal("100")).quantize(ONE_CENT, rounding=ROUND_HALF_UP) if cap_cbm > ZERO else ZERO
                ritase_count = 2 if volume_cbm > cap_cbm else (1 if orders > 0 else 0)

                # Mileage harian
                if orders == 0:
                    mileage = Decimal("0.0")
                elif plate == "DB 8910 TK":
                    mileage = Decimal("95.0") + (Decimal(str(orders)) * Decimal("1.5"))
                elif ritase_count == 2:
                    mileage = Decimal("45.0") + (Decimal(str(orders)) * Decimal("2.0")) + Decimal("25.0")
                else:
                    mileage = Decimal("40.0") + (Decimal(str(orders)) * Decimal("2.0"))

                daily_logistics_metrics.append({
                    "date": date_k,
                    "entity_type": "ARMADA_DELIVERY",
                    "code": plate,
                    "name": meta["name"],
                    "personnel_name": meta["driver"],
                    "route_name": meta["route"],
                    "stops_count": str(orders),
                    "cartons_delivered": str(cartons),
                    "weight_kg": _q(weight_kg),
                    "volume_cbm": _q(volume_cbm),
                    "capacity_cbm": _q(cap_cbm),
                    "utilization_cbm_pct": str(util_pct),
                    "ritase_count": str(ritase_count),
                    "est_mileage_km": _q(mileage),
                })

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
                "total_daily_logistics_entries": len(daily_logistics_metrics),
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
            "daily_logistics_metrics": daily_logistics_metrics,
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
