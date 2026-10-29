#!/usr/bin/env python3
"""scripts/ops/verify_disposable_slice.py.

Skrip eksekusi dan verifikasi slice transaksi representatif pada Odoo 19 disposable DB.
Dijalankan via:
    odoo shell -c /tmp/odoo.conf -d fmcg --no-http < scripts/ops/verify_disposable_slice.py

Mencakup:
1. Introspeksi schema model aktual Odoo 19 (account.payment, stock.move.line, account.move)
2. Pemuatan slice representatif multi-domain (target_so_numbers=["SO-202607-0001", "SO-202607-0063", "SO-202607-0317"]):
   - Opening stock quant 150 SKU (1 Juli 2026)
   - 5 Inbound PO transit Juni dengan receipt & vendor bill (PO-2026-06-01 s/d PO-2026-06-05)
   - Outgoing SO dengan cash discount (SO-202607-0001 + INV-202607-0001 + PAY-AR-00098 + DISC-PAY-AR-00098)
   - Outgoing SO dengan partial rejection ke karantina (SO-202607-0063 + REJ-202607-001)
   - Outgoing SO dengan multi-lot split nyata (SO-202607-0317: 120 + 96 = 216 unit)
   - Outbound AP payment (PAY-AP-01 s/d PAY-AP-04) + Open AP (PO-2026-06-05)
   - 30 OPEX & Payroll roster
3. Verifikasi Oracle Kanonikal Ketat (Exact-Set & Multiset, Saldo Fisik/Saleable/Reserved/Karantina,
   Valuasi Stok & GL As-Of, Pasangan Akun Debit/Kredit, dan Tanggal Eksak per Dokumen)
4. Uji Mutasi Negatif Terisolasi (11 Mutasi Aktif: Lot Split, Extra Line, Substitusi SKU, Duplikasi Picking,
   Lokasi Retur Salah, DPP Palsu, Hilangnya Jurnal Native, GL Salah Akun/Nilai, Quant Drift +100.000,
   Tanggal Bergeser di Dalam Juli 2026, dan Tanggal Bocor ke Runtime)
5. Rerun kedua kali (uji idempotensi sejati) dengan deep snapshot comparison (quant + reserved_quantity,
   exact stock.move, stock.move.line, account.move, dan account.move.line IDs/dates/relations/balances)
"""

import os
from pathlib import Path
import sys

# Path root repositori (tangguh terhadap eksekusi langsung maupun via stdin di Odoo shell)
try:
    REPO_ROOT = Path(__file__).resolve().parent.parent.parent
except NameError:
    # Saat dieksekusi via stdin di Odoo shell (__file__ tidak terdefinisi)
    if Path("/opt/scripts/load_canonical_perpetual.py").exists():
        REPO_ROOT = Path("/opt")
    elif Path("scripts/load_canonical_perpetual.py").exists():
        REPO_ROOT = Path.cwd()
    else:
        REPO_ROOT = Path(os.environ.get("REPO_ROOT", "/opt"))

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Deteksi lokasi direktori data registers
REG_PATH = REPO_ROOT / "data" / "registers"
if not REG_PATH.exists() and Path("/opt/data/registers").exists():
    REG_PATH = Path("/opt/data/registers")

from scripts.load_canonical_perpetual import (  # noqa: E402
    OPEX_CATEGORY_ACCOUNT_MAP,
    OPEX_PAYMENT_PARTNER_MAP,
    CanonicalPerpetualAdapter,
    build_order_line_payload,
    build_so_header_payload,
    read_register_csv,
)


def introspect_odoo19_schema(env):
    """Melakukan introspeksi schema model aktual Odoo 19 sebelum eksekusi."""
    print("=" * 80)
    print("[schema_introspection] MEMULAI INTROSPEKSI SCHEMA MODEL ODOO AKTUAL")
    print("=" * 80)

    # 1. Introspeksi account.payment
    if "account.payment" in env:
        Payment = env["account.payment"]
        p_fields = getattr(Payment, "_fields", {})
        print(f" -> account.payment terdaftar dengan {len(p_fields)} fields.")
        print(f"    - 'memo' field: {'ADA' if 'memo' in p_fields else 'TIDAK ADA'}")
        print(f"    - 'ref' field: {'ADA' if 'ref' in p_fields else 'TIDAK ADA'}")
        print(f"    - 'move_id' field: {'ADA' if 'move_id' in p_fields else 'TIDAK ADA'}")
        if "state" in p_fields:
            state_selection = getattr(p_fields["state"], "selection", [])
            print(f"    - 'state' selection: {state_selection}")
    else:
        print(" -> account.payment TIDAK terpasang di env!")

    # 2. Introspeksi stock.move.line
    if "stock.move.line" in env:
        MoveLine = env["stock.move.line"]
        sml_fields = getattr(MoveLine, "_fields", {})
        print(f" -> stock.move.line terdaftar dengan {len(sml_fields)} fields.")
        print(f"    - 'quantity' field (Odoo 19): {'ADA' if 'quantity' in sml_fields else 'TIDAK ADA'}")
        print(f"    - 'qty_done' field (Legacy): {'ADA' if 'qty_done' in sml_fields else 'TIDAK ADA'}")
        print(f"    - 'lot_id' field: {'ADA' if 'lot_id' in sml_fields else 'TIDAK ADA'}")
    else:
        print(" -> stock.move.line TIDAK terpasang di env!")

    # 3. Introspeksi account.move
    if "account.move" in env:
        Move = env["account.move"]
        m_fields = getattr(Move, "_fields", {})
        print(f" -> account.move terdaftar dengan {len(m_fields)} fields.")
        print(f"    - 'line_ids' field: {'ADA' if 'line_ids' in m_fields else 'TIDAK ADA'}")
        print(f"    - 'amount_residual' field: {'ADA' if 'amount_residual' in m_fields else 'TIDAK ADA'}")

    print("=" * 80)


def _resolve_ml_sku(env, ml):
    prod = getattr(ml, "product_id", None)
    sku = getattr(prod, "default_code", None) if prod else None
    if not sku and isinstance(prod, int) and "product.product" in env:
        sku = getattr(env["product.product"].browse(prod), "default_code", None)
    return sku


def _resolve_ml_lot_name(env, ml):
    lot_rec = getattr(ml, "lot_id", None)
    lot_name = getattr(lot_rec, "name", None) if lot_rec else None
    if not lot_name and isinstance(lot_rec, int) and "stock.lot" in env:
        lot_name = getattr(env["stock.lot"].browse(lot_rec), "name", None)
    if not lot_name:
        lot_name = getattr(ml, "lot_name", None)
    return lot_name


def _resolve_loc(env, loc_val):
    if hasattr(loc_val, "usage") or hasattr(loc_val, "name"):
        return loc_val
    if isinstance(loc_val, int) and "stock.location" in env:
        return env["stock.location"].browse(loc_val)
    return None


def _iter_records(res) -> list:
    """Mengonversi hasil search/recordset Odoo maupun MockRecord/list menjadi list singleton record."""
    if not res:
        return []
    if hasattr(res, "__iter__"):
        return list(res)
    return [res]


def _assert_unique_record(res, label: str):
    """Memastikan hasil pencarian dokumen memiliki tepat 1 record (tanpa limit=1)."""
    recs = _iter_records(res)
    assert len(recs) == 1, (
        f"[canonical_oracle] Duplikasi atau kehilangan dokumen {label}: "
        f"expected tepat 1 record, got {len(recs)}!"
    )
    return recs[0]


def _get_reconciled_peer_move_ids(line) -> set:
    """Mengumpulkan move_id dari seluruh baris pasangan rekonsiliasi aktual pada account.move.line."""
    peer_ids = set()
    explicit_peers = getattr(line, "_reconciled_peer_move_ids", None)
    if explicit_peers:
        peer_ids.update(explicit_peers)

    if callable(getattr(line, "_reconciled_lines", None)):
        try:
            for rl in _iter_records(line._reconciled_lines()):
                mid = getattr(getattr(rl, "move_id", None), "id", getattr(rl, "move_id", None))
                if mid:
                    peer_ids.add(mid)
        except Exception:
            pass

    full_rec = getattr(line, "full_reconcile_id", None)
    if full_rec and hasattr(full_rec, "reconciled_line_ids"):
        for rl in _iter_records(full_rec.reconciled_line_ids):
            mid = getattr(getattr(rl, "move_id", None), "id", getattr(rl, "move_id", None))
            if mid:
                peer_ids.add(mid)

    for field_name, side_attr in (("matched_debit_ids", "debit_move_id"), ("matched_credit_ids", "credit_move_id")):
        partials = getattr(line, field_name, None)
        if partials:
            for pr in _iter_records(partials):
                target_aml = getattr(pr, side_attr, None)
                mid = getattr(getattr(target_aml, "move_id", None), "id", getattr(target_aml, "move_id", None))
                if mid:
                    peer_ids.add(mid)

    return peer_ids


def _verify_exact_reconciliation_pair(line_a, line_b, pair_label: str):
    """Memastikan dua baris AR/AP benar-benar berpasangan rekonsiliasi satu sama lain."""
    move_b_id = getattr(getattr(line_b, "move_id", None), "id", getattr(line_b, "move_id", None))
    move_a_id = getattr(getattr(line_a, "move_id", None), "id", getattr(line_a, "move_id", None))

    full_a = getattr(getattr(line_a, "full_reconcile_id", None), "id", getattr(line_a, "full_reconcile_id", None))
    full_b = getattr(getattr(line_b, "full_reconcile_id", None), "id", getattr(line_b, "full_reconcile_id", None))
    if full_a and full_b:
        assert full_a == full_b, (
            f"[canonical_oracle] Pasangan rekonsiliasi {pair_label} memiliki full_reconcile_id berbeda "
            f"({full_a} vs {full_b})!"
        )

    peers_a = _get_reconciled_peer_move_ids(line_a) - ({move_a_id} if move_a_id else set())
    peers_b = _get_reconciled_peer_move_ids(line_b) - ({move_b_id} if move_b_id else set())
    if peers_a:
        assert move_b_id in peers_a, (
            f"[canonical_oracle] Pasangan rekonsiliasi {pair_label} tidak cocok dengan ekspektasi! "
            f"move_b={move_b_id} tidak ditemukan pada peers_a={sorted(peers_a)}"
        )
    if peers_b:
        assert move_a_id in peers_b, (
            f"[canonical_oracle] Pasangan rekonsiliasi {pair_label} tidak cocok dengan ekspektasi! "
            f"move_a={move_a_id} tidak ditemukan pada peers_b={sorted(peers_b)}"
        )


def _resolve_stock_move_account_moves(env, sm):
    """Menemukan entri jurnal akuntansi native yang terhubung ke stock.move."""
    AccountMove = env["account.move"].sudo()
    found = []
    seen = set()

    def _add(am):
        if am and getattr(am, "id", None) not in seen:
            seen.add(getattr(am, "id", id(am)))
            found.append(am)

    if getattr(sm, "account_move_id", None):
        _add(sm.account_move_id)
    elif getattr(sm, "account_move_ids", None):
        for am in sm.account_move_ids:
            _add(am)

    am_fields = getattr(AccountMove, "_fields", {})
    has_sm_f = (
        am_fields
        and not isinstance(am_fields, bool)
        and hasattr(am_fields, "__contains__")
        and "stock_move_id" in am_fields
    )
    if has_sm_f:
        for am in (AccountMove.search([("stock_move_id", "=", sm.id)]) or []):
            _add(am)

    return found


def _verify_valuation_account_move_lines(
    am, doc_label: str, expected_date: str, expected_debit_code: str, expected_credit_code: str, expected_amount: float
):
    """Memverifikasi state, tanggal eksak, keseimbangan, pasangan akun debit/kredit, dan nominal jurnal."""
    assert getattr(am, "state", "") == "posted", (
        f"[canonical_oracle] Jurnal valuasi '{doc_label}' (ID {am.id}) belum posted! State: {getattr(am, 'state', '')}"
    )
    am_date = str(getattr(am, "date", ""))[:10]
    assert am_date == expected_date, (
        f"[canonical_oracle] Tanggal jurnal valuasi '{doc_label}' (ID {am.id}) salah! "
        f"Expected {expected_date}, got {am_date}"
    )

    lines = getattr(am, "line_ids", [])
    assert lines, f"[canonical_oracle] Jurnal valuasi '{doc_label}' (ID {am.id}) tidak memiliki line_ids!"

    debit_by_acc = {}
    credit_by_acc = {}
    for ln in lines:
        acc = getattr(ln, "account_id", None)
        code = str(getattr(acc, "code", "") or "").strip()
        d = round(float(getattr(ln, "debit", 0.0)), 2)
        c = round(float(getattr(ln, "credit", 0.0)), 2)
        if d > 0:
            debit_by_acc[code] = round(debit_by_acc.get(code, 0.0) + d, 2)
        if c > 0:
            credit_by_acc[code] = round(credit_by_acc.get(code, 0.0) + c, 2)

    tot_d = round(sum(debit_by_acc.values()), 2)
    tot_c = round(sum(credit_by_acc.values()), 2)
    assert abs(tot_d - tot_c) < 0.01, (
        f"[canonical_oracle] Jurnal valuasi '{doc_label}' (ID {am.id}) tidak berimbang! Debit={tot_d}, Credit={tot_c}"
    )
    assert abs(tot_d - expected_amount) < 1.0, (
        f"[canonical_oracle] Nominal jurnal valuasi '{doc_label}' (ID {am.id}) salah! "
        f"Expected {expected_amount}, got {tot_d}"
    )
    assert set(debit_by_acc.keys()) == {expected_debit_code}, (
        f"[canonical_oracle] Akun debit jurnal valuasi '{doc_label}' (ID {am.id}) salah! "
        f"Expected {{{expected_debit_code!r}}}, got {set(debit_by_acc.keys())}"
    )
    assert set(credit_by_acc.keys()) == {expected_credit_code}, (
        f"[canonical_oracle] Akun kredit jurnal valuasi '{doc_label}' (ID {am.id}) salah! "
        f"Expected {{{expected_credit_code!r}}}, got {set(credit_by_acc.keys())}"
    )


def verify_run1_against_canonical_oracle(env, adapter, reg_path, target_so_slice):
    """Memverifikasi hasil pemuatan Run 1 secara independen terhadap Oracle CSV Kanonikal.

    Menutup seluruh celah temuan supervisi:
    1. Fail-closed: menolak eksekusi tanpa model Odoo wajib atau dataset kosong.
    2. Exact-Set & Multiset: memvalidasi himpunan persis dokumen (PO, SO, Picking, Retur, Invoice, AP/AR)
       dan kesamaan penuh multiset baris `(sku, lot) -> qty`, menolak baris tambahan (extra lines),
       substitusi SKU, duplikasi picking, atau lokasi asal/tujuan retur yang salah.
    3. Saldo Absolut Stok & Valuasi As-Of: menghitung ekspektasi kuantitas fisik, saleable (WH/Stock),
       reserved (0.0), dan karantina (Karantina FMCG Maumbi) per `(sku, lot)` langsung dari CSV sumber
       dan membandingkannya secara eksak terhadap seluruh `stock.quant` internal di DB (menolak quant drift).
    4. Keberadaan & Pasangan Akun Jurnal Valuasi Native: membuktikan setiap event stok (150 opening,
       5 PO receipt, 3 SO delivery, 1 retur karantina) memiliki `account.move` posted dengan pasangan akun
       (`113000`/`113900`/`510000`), nominal eksak, dan tanggal historis eksak per event (menolak pergeseran
       tanggal di dalam bulan Juli 2026 maupun ke runtime).
    5. Rekonsiliasi Komersial AR & AP: memvalidasi 5 tagihan PO, 4 pembayaran AP lunas, 1 saldo AP terbuka
       (`PO-2026-06-05`), faktur penjualan net of rejection, diskon kas, dan saldo residual AR.
    """
    if not env:
        raise ValueError("[canonical_oracle] env (Odoo environment) wajib disediakan!")
    reg_path = Path(reg_path)
    if not reg_path.is_dir():
        raise FileNotFoundError(f"[canonical_oracle] Direktori register tidak ditemukan di: {reg_path}")

    REQUIRED_MODELS = [
        "stock.picking", "account.move", "account.payment", "stock.quant",
        "purchase.order", "sale.order", "stock.move", "stock.move.line", "stock.location",
    ]
    for m in REQUIRED_MODELS:
        if m not in env:
            raise RuntimeError(f"[canonical_oracle] Model Odoo '{m}' wajib terdaftar di env! Fail-closed.")

    if not target_so_slice:
        raise ValueError("[canonical_oracle] target_so_slice tidak boleh kosong!")
    target_so_set = set(target_so_slice)

    print("\n" + "=" * 80)
    print("[canonical_oracle] MEMULAI VERIFIKASI RUN 1 TERHADAP ORACLE REGISTER KANONIKAL")
    print("=" * 80)

    PurchaseOrder = env["purchase.order"].sudo()
    SaleOrder = env["sale.order"].sudo()
    StockPicking = env["stock.picking"].sudo()
    StockMove = env["stock.move"].sudo()
    StockQuant = env["stock.quant"].sudo()
    AccountMove = env["account.move"].sudo()
    AccountPayment = env["account.payment"].sudo()

    # Load seluruh CSV kanonikal sumber untuk perhitungan eksak
    init_rows = read_register_csv("initial_stock_20260701.csv", reg_path=reg_path)
    po_headers = read_register_csv("inbound_po_intransit_june_headers.csv", reg_path=reg_path)
    po_lines = read_register_csv("inbound_po_intransit_june_lines.csv", reg_path=reg_path)
    so_header_rows = read_register_csv("perpetual_sales_orders.csv", reg_path=reg_path)
    deliv_rows = read_register_csv("perpetual_deliveries.csv", reg_path=reg_path)
    order_line_rows = read_register_csv("perpetual_order_lines.csv", reg_path=reg_path)
    rej_rows = read_register_csv("perpetual_order_rejections.csv", reg_path=reg_path)
    inv_rows = read_register_csv("perpetual_invoices.csv", reg_path=reg_path)
    all_ar_rows = read_register_csv("perpetual_ar_collections.csv", reg_path=reg_path)
    ap_rows = read_register_csv("perpetual_ap_payments.csv", reg_path=reg_path)
    opex_rows = read_register_csv("perpetual_opex_payroll.csv", reg_path=reg_path)

    assert init_rows and len(init_rows) == 150, "[canonical_oracle] initial_stock_20260701.csv harus 150 baris!"
    assert po_headers and len(po_headers) == 5, "[canonical_oracle] inbound_po_intransit_june_headers.csv harus 5 PO!"

    unit_cost_by_sku = {r["sku_code"]: float(r["unit_cost_price"]) for r in init_rows}

    seed_comp_id = (
        getattr(getattr(adapter, "company", None), "id", None)
        or getattr(getattr(env, "company", None), "id", None)
    )
    wh_loc = getattr(adapter, "wh_stock_loc", None)
    quar_loc = getattr(adapter, "quarantine_loc", None)
    assert wh_loc, "[canonical_oracle] Lokasi gudang utama WH/Stock (adapter.wh_stock_loc) wajib terdefinisi!"
    assert quar_loc, "[canonical_oracle] Lokasi Karantina FMCG Maumbi (adapter.quarantine_loc) wajib terdefinisi!"
    assert getattr(wh_loc, "id", None) != getattr(quar_loc, "id", None), (
        "[canonical_oracle] Lokasi WH/Stock dan Karantina tidak boleh memiliki ID yang sama!"
    )
    for seed_loc_rec, seed_loc_lbl in ((wh_loc, "WH/Stock"), (quar_loc, "Karantina FMCG Maumbi")):
        l_comp = getattr(seed_loc_rec, "company_id", None)
        l_comp_id = getattr(l_comp, "id", l_comp) if l_comp else None
        if seed_comp_id and l_comp_id and l_comp_id != seed_comp_id:
            raise AssertionError(
                f"[canonical_oracle] Lokasi '{seed_loc_lbl}' (company_id={l_comp_id}) bukan milik company seed ({seed_comp_id})!"
            )

    # Ekspektasi saldo kuantitas fisik per (sku, lot) di WH/Stock dan Karantina
    expected_saleable_by_sku_lot = {}
    expected_quarantine_by_sku_lot = {}
    expected_opening_val = 0.0
    expected_po_val_total = 0.0
    expected_delivery_cogs_total = 0.0
    expected_rejection_cogs_total = 0.0

    for r in init_rows:
        sku = r["sku_code"]
        lot = r["lot_number"]
        units = float(r["qty_units_on_hand"])
        val = float(r["subtotal_dpp"])
        expected_saleable_by_sku_lot[(sku, lot)] = expected_saleable_by_sku_lot.get((sku, lot), 0.0) + units
        expected_opening_val += val

    # Track seluruh expected account.move IDs dan tanggal eksaknya untuk validasi himpunan jurnal GL
    verified_valuation_am_ids = set()
    expected_date_by_am_id = {}

    # --- 0. Verifikasi Opening Stock Moves & Jurnal Valuasi Native (150 SKU, 2026-07-01) ---
    opening_moves = StockMove.search([("origin", "=", "OPENING-20260701"), ("state", "=", "done")])
    opening_moves_list = _iter_records(opening_moves)
    assert len(opening_moves_list) == 150, (
        f"[canonical_oracle] Jumlah stock.move OPENING-20260701 harus tepat 150, got {len(opening_moves_list)}!"
    )

    init_by_sku = {r["sku_code"]: r for r in init_rows}
    seen_opening_skus = set()
    for om in opening_moves_list:
        sku = _resolve_ml_sku(env, om)
        assert sku in init_by_sku, f"[canonical_oracle] SKU opening move '{sku}' tidak dikenal di register!"
        seen_opening_skus.add(sku)
        init_row = init_by_sku[sku]
        exp_val = float(init_row["subtotal_dpp"])
        om_date = str(getattr(om, "date", ""))[:10]
        assert om_date == "2026-07-01", (
            f"[canonical_oracle] Tanggal stock.move opening {sku} harus 2026-07-01, got {om_date}!"
        )
        om_src = _resolve_loc(env, getattr(om, "location_id", None))
        om_dest = _resolve_loc(env, getattr(om, "location_dest_id", None))
        if om_src and getattr(om_src, "usage", None):
            assert om_src.usage == "inventory", (
                f"[canonical_oracle] Lokasi asal stock.move opening {sku} harus 'inventory', got '{om_src.usage}'!"
            )
        assert getattr(om_dest, "id", getattr(om, "location_dest_id", None)) == wh_loc.id, (
            f"[canonical_oracle] Lokasi tujuan stock.move opening {sku} harus WH/Stock (id={wh_loc.id}), "
            f"got {getattr(om_dest, 'id', getattr(om, 'location_dest_id', None))}!"
        )
        for oml in _iter_records(getattr(om, "move_line_ids", None)):
            oml_date = str(getattr(oml, "date", ""))[:10]
            assert oml_date == "2026-07-01", (
                f"[canonical_oracle] Tanggal stock.move.line opening {sku} harus 2026-07-01, got {oml_date}!"
            )
            oml_dest = _resolve_loc(env, getattr(oml, "location_dest_id", None))
            if oml_dest is not None:
                assert getattr(oml_dest, "id", getattr(oml, "location_dest_id", None)) == wh_loc.id, (
                    f"[canonical_oracle] Lokasi tujuan stock.move.line opening {sku} harus WH/Stock (id={wh_loc.id})!"
                )
        ams = _resolve_stock_move_account_moves(env, om)
        assert len(ams) == 1, (
            f"[canonical_oracle] Opening stock.move untuk SKU {sku} wajib memiliki tepat 1 jurnal valuasi native, "
            f"got {len(ams)}!"
        )
        _verify_valuation_account_move_lines(
            ams[0], f"OPENING-{sku}", "2026-07-01", "113000", "113900", exp_val
        )
        verified_valuation_am_ids.add(ams[0].id)
        expected_date_by_am_id[ams[0].id] = "2026-07-01"

    assert seen_opening_skus == set(init_by_sku.keys()), (
        "[canonical_oracle] Himpunan SKU opening stock.move tidak sama persis dengan 150 SKU register!"
    )

    # --- 1. Verifikasi Inbound PO Transit (Exact-Set, Multiplicity, Multiset, & Jurnal Valuasi Native) ---
    lines_by_po = {}
    for pline in po_lines:
        lines_by_po.setdefault(pline["po_number"], []).append(pline)

    expected_po_nums = {h["po_number"] for h in po_headers}
    all_pos = PurchaseOrder.search([])
    all_pos_list = _iter_records(all_pos)
    actual_po_nums = {getattr(p, "origin", None) or getattr(p, "name", None) for p in all_pos_list}
    assert actual_po_nums == expected_po_nums, (
        f"[canonical_oracle] Himpunan Purchase Order di DB ({sorted(actual_po_nums)}) != "
        f"register ({sorted(expected_po_nums)})!"
    )
    assert len(all_pos_list) == len(expected_po_nums), (
        f"[canonical_oracle] Duplikasi PurchaseOrder terdeteksi di DB! "
        f"Expected {len(expected_po_nums)} record unik, got {len(all_pos_list)}!"
    )

    for h in po_headers:
        po_num = h["po_number"]
        po_matches = _iter_records(PurchaseOrder.search([("origin", "=", po_num)]))
        if not po_matches:
            po_matches = _iter_records(PurchaseOrder.search([("name", "=", po_num)]))
        po = _assert_unique_record(po_matches, f"PurchaseOrder {po_num}")
        assert po.state in ("purchase", "done"), f"[canonical_oracle] PO {po_num} belum confirmed! State: {po.state}"

        po_picks_all = _iter_records(getattr(po, "picking_ids", None))
        if not po_picks_all:
            po_picks_all = _iter_records(StockPicking.search([("origin", "in", [getattr(po, "name", ""), po_num])]))
        po_picks = [p for p in po_picks_all if getattr(p, "state", "") != "cancel"]
        assert len(po_picks_all) == 1 and len(po_picks) == 1, (
            f"[canonical_oracle] Expected exactly 1 receipt picking untuk {po_num}, "
            f"got active={len(po_picks)}, total={len(po_picks_all)}"
        )
        po_pick = po_picks[0]
        assert po_pick.state == "done", f"[canonical_oracle] Receipt {po_num} belum done! State: {po_pick.state}"

        src_loc = _resolve_loc(env, getattr(po_pick, "location_id", None))
        dest_loc = _resolve_loc(env, getattr(po_pick, "location_dest_id", None))
        assert src_loc and getattr(src_loc, "usage", None) == "supplier", (
            f"[canonical_oracle] Lokasi asal receipt {po_num} harus 'supplier', got '{getattr(src_loc, 'usage', None)}'!"
        )
        assert dest_loc and getattr(dest_loc, "usage", None) == "internal" and getattr(dest_loc, "id", None) == wh_loc.id, (
            f"[canonical_oracle] Lokasi tujuan receipt {po_num} harus WH/Stock (id={wh_loc.id}, usage='internal'), "
            f"got id={getattr(dest_loc, 'id', None)} ('{getattr(dest_loc, 'name', '')}', usage='{getattr(dest_loc, 'usage', None)}')!"
        )

        exact_arrival = h["arrival_maumbi_date"]
        pick_date = str(
            getattr(po_pick, "date_done", getattr(po_pick, "scheduled_date", getattr(po_pick, "date", "")))
        )[:10]
        assert pick_date == exact_arrival, (
            f"[canonical_oracle] Tanggal receipt {po_num} ({pick_date}) != arrival_maumbi_date ({exact_arrival})!"
        )

        exp_lines = lines_by_po.get(po_num, [])
        assert exp_lines, f"[canonical_oracle] Lines untuk PO {po_num} kosong di register CSV!"
        expected_by_sku_lot = {}
        expected_val_by_sku = {}
        for el in exp_lines:
            sku = el["sku_code"]
            lot = el["lot_number"]
            units = float(el["qty_cartons"]) * float(el["carton_qty"])
            val = float(el["subtotal_dpp"])
            expected_by_sku_lot[(sku, lot)] = expected_by_sku_lot.get((sku, lot), 0.0) + units
            expected_val_by_sku[sku] = expected_val_by_sku.get(sku, 0.0) + val
            expected_saleable_by_sku_lot[(sku, lot)] = expected_saleable_by_sku_lot.get((sku, lot), 0.0) + units
            expected_po_val_total += val

        actual_mls = getattr(po_pick, "move_line_ids", [])
        assert actual_mls, f"[canonical_oracle] Move lines pada receipt {po_num} kosong!"
        assert len(actual_mls) == len(expected_by_sku_lot), (
            f"[canonical_oracle] Jumlah baris move line pada receipt {po_num} tidak cocok! "
            f"Expected {len(expected_by_sku_lot)}, got {len(actual_mls)}"
        )

        actual_by_sku_lot = {}
        for ml in actual_mls:
            sku = _resolve_ml_sku(env, ml)
            lot_name = _resolve_ml_lot_name(env, ml)
            assert sku, f"[canonical_oracle] Baris move line pada receipt {po_num} tidak memiliki SKU (product_id)!"
            assert lot_name, f"[canonical_oracle] Baris move line SKU {sku} pada receipt {po_num} tidak memiliki lot!"
            ml_date = str(getattr(ml, "date", ""))[:10]
            assert ml_date == exact_arrival, (
                f"[canonical_oracle] Tanggal stock.move.line receipt {po_num} ({ml_date}) != arrival_maumbi_date ({exact_arrival})!"
            )
            ml_src = _resolve_loc(env, getattr(ml, "location_id", None))
            ml_dest = _resolve_loc(env, getattr(ml, "location_dest_id", None))
            if ml_src is not None and getattr(ml_src, "usage", None):
                assert ml_src.usage == "supplier", (
                    f"[canonical_oracle] Lokasi asal stock.move.line receipt {po_num} harus 'supplier', got '{ml_src.usage}'!"
                )
            if ml_dest is not None:
                assert getattr(ml_dest, "id", None) == wh_loc.id, (
                    f"[canonical_oracle] Lokasi tujuan stock.move.line receipt {po_num} harus WH/Stock (id={wh_loc.id}), "
                    f"got {getattr(ml_dest, 'id', None)}!"
                )
            qty = float(getattr(ml, "quantity", getattr(ml, "qty_done", 0.0)))
            assert qty > 0.0, f"[canonical_oracle] Kuantitas line receipt {po_num} harus positif! Got {qty}"
            key = (sku, lot_name)
            actual_by_sku_lot[key] = actual_by_sku_lot.get(key, 0.0) + qty

        extra_po_keys = set(actual_by_sku_lot.keys()) - set(expected_by_sku_lot.keys())
        assert not extra_po_keys, (
            f"[canonical_oracle] Ditemukan baris ekstra/asing pada receipt {po_num}: {sorted(extra_po_keys)}!"
        )
        missing_po_keys = set(expected_by_sku_lot.keys()) - set(actual_by_sku_lot.keys())
        assert not missing_po_keys, (
            f"[canonical_oracle] Baris SKU/Lot hilang pada receipt {po_num}: {sorted(missing_po_keys)}!"
        )
        for (exp_sku, exp_lot), exp_qty in expected_by_sku_lot.items():
            act_qty = actual_by_sku_lot.get((exp_sku, exp_lot), 0.0)
            assert abs(act_qty - exp_qty) < 0.001, (
                f"[canonical_oracle] Kuantitas receipt {po_num} untuk SKU {exp_sku} Lot {exp_lot} salah! "
                f"Expected {exp_qty}, got {act_qty}"
            )

        # Verifikasi lokasi, tanggal efektif, dan jurnal valuasi native untuk setiap stock.move pada PO receipt
        po_moves = [
            mv for mv in getattr(po_pick, "move_ids", [])
            if getattr(mv, "state", "done") != "cancel"
        ]
        assert len(po_moves) == len(expected_val_by_sku), (
            f"[canonical_oracle] Jumlah stock.move aktif pada receipt {po_num} harus {len(expected_val_by_sku)}, "
            f"got {len(po_moves)}!"
        )
        po_am_groups = {}
        for mv in po_moves:
            mv_sku = _resolve_ml_sku(env, mv)
            assert mv_sku in expected_val_by_sku, (
                f"[canonical_oracle] stock.move SKU '{mv_sku}' pada {po_num} tidak ada di register!"
            )
            mv_date = str(getattr(mv, "date", ""))[:10]
            assert mv_date == exact_arrival, (
                f"[canonical_oracle] Tanggal stock.move receipt {po_num} ({mv_date}) != arrival_maumbi_date ({exact_arrival})!"
            )
            mv_src = _resolve_loc(env, getattr(mv, "location_id", None))
            mv_dest = _resolve_loc(env, getattr(mv, "location_dest_id", None))
            if mv_src is not None and getattr(mv_src, "usage", None):
                assert mv_src.usage == "supplier", (
                    f"[canonical_oracle] Lokasi asal stock.move receipt {po_num} harus 'supplier', got '{mv_src.usage}'!"
                )
            if mv_dest is not None:
                assert getattr(mv_dest, "id", None) == wh_loc.id, (
                    f"[canonical_oracle] Lokasi tujuan stock.move receipt {po_num} harus WH/Stock (id={wh_loc.id}), "
                    f"got {getattr(mv_dest, 'id', None)}!"
                )
            ams = _resolve_stock_move_account_moves(env, mv)
            assert len(ams) == 1, (
                f"[canonical_oracle] stock.move receipt {po_num} SKU {mv_sku} wajib memiliki tepat 1 jurnal valuasi, "
                f"got {len(ams)}!"
            )
            am = ams[0]
            po_am_groups.setdefault(am.id, {"am": am, "expected_val": 0.0, "skus": []})
            po_am_groups[am.id]["expected_val"] += expected_val_by_sku[mv_sku]
            po_am_groups[am.id]["skus"].append(mv_sku)

        for am_id, grp in po_am_groups.items():
            _verify_valuation_account_move_lines(
                grp["am"],
                f"RECEIPT-{po_num}",
                exact_arrival,
                "113000",
                "113900",
                grp["expected_val"],
            )
            verified_valuation_am_ids.add(am_id)
            expected_date_by_am_id[am_id] = exact_arrival

    print(
        f" -> [Oracle Inbound PO] {len(po_headers)} PO Receipts verified DONE "
        f"(exact multiset lines, move/move_line dates & locations, & native valuation journals)."
    )

    # --- 2. Verifikasi Outgoing SO Deliveries (Exact-Set, Multiplicity, Multiset, & Jurnal Valuasi Native) ---
    deliv_by_so = {d["so_number"]: d for d in deliv_rows if d["so_number"] in target_so_set}
    so_headers_by_num = {s["so_number"]: s for s in so_header_rows if s["so_number"] in target_so_set}
    lines_by_so = {}
    for ol in order_line_rows:
        if ol["so_number"] in target_so_set:
            lines_by_so.setdefault(ol["so_number"], []).append(ol)

    all_sos = SaleOrder.search([])
    all_sos_list = _iter_records(all_sos)
    actual_so_nums = {
        getattr(s, "client_order_ref", None) or getattr(s, "origin", None) or getattr(s, "name", None)
        for s in all_sos_list
    }
    assert actual_so_nums == target_so_set, (
        f"[canonical_oracle] Himpunan Sale Order di DB ({sorted(actual_so_nums)}) != "
        f"target slice ({sorted(target_so_set)})!"
    )
    assert len(all_sos_list) == len(target_so_set), (
        f"[canonical_oracle] Duplikasi SaleOrder terdeteksi di DB! "
        f"Expected {len(target_so_set)} record unik, got {len(all_sos_list)}!"
    )

    so_rec_by_num = {}
    for so_num in target_so_slice:
        so_matches = _iter_records(SaleOrder.search([("client_order_ref", "=", so_num)]))
        if not so_matches:
            so_matches = _iter_records(SaleOrder.search([("name", "=", so_num)]))
        if not so_matches:
            so_matches = _iter_records(SaleOrder.search([("origin", "=", so_num)]))
        so = _assert_unique_record(so_matches, f"SaleOrder {so_num}")
        assert so.state in ("sale", "done"), f"[canonical_oracle] Sale Order {so_num} belum confirmed!"
        so_rec_by_num[so_num] = so

        so_picks_rel = _iter_records(getattr(so, "picking_ids", None))
        so_picks_origin = _iter_records(StockPicking.search([("origin", "in", [getattr(so, "name", ""), so_num])]))

        seen_pick_ids = set()
        so_picks_all = []
        for p in list(so_picks_rel) + list(so_picks_origin):
            pid = getattr(p, "id", id(p))
            if pid not in seen_pick_ids:
                seen_pick_ids.add(pid)
                so_picks_all.append(p)
        so_picks = [p for p in so_picks_all if getattr(p, "state", "") != "cancel"]

        assert len(so_picks) == 1 and len(so_picks_all) == 1, (
            f"[canonical_oracle] Expected tepat 1 delivery picking untuk {so_num}, "
            f"got active={len(so_picks)}, total={len(so_picks_all)}! "
            f"(Duplikasi atau kehilangan picking ditolak)."
        )
        deliv = so_picks[0]
        assert deliv.state == "done", (
            f"[canonical_oracle] Delivery picking untuk {so_num} belum done! State: {deliv.state}"
        )

        src_loc = _resolve_loc(env, getattr(deliv, "location_id", None))
        dest_loc = _resolve_loc(env, getattr(deliv, "location_dest_id", None))
        assert src_loc and getattr(src_loc, "usage", None) == "internal" and getattr(src_loc, "id", None) == wh_loc.id, (
            f"[canonical_oracle] Lokasi asal delivery {so_num} harus WH/Stock (id={wh_loc.id}, usage='internal'), "
            f"got id={getattr(src_loc, 'id', None)} ('{getattr(src_loc, 'name', '')}', usage='{getattr(src_loc, 'usage', None)}')!"
        )
        assert dest_loc and getattr(dest_loc, "usage", None) == "customer", (
            f"[canonical_oracle] Lokasi tujuan delivery {so_num} harus 'customer', got '{getattr(dest_loc, 'usage', None)}'!"
        )

        expected_deliv = deliv_by_so.get(so_num)
        assert expected_deliv, f"[canonical_oracle] SO {so_num} tidak ada di perpetual_deliveries.csv!"
        exp_date = expected_deliv["scheduled_delivery_date"]
        actual_date = str(
            getattr(deliv, "date_done", getattr(deliv, "scheduled_date", getattr(deliv, "date", "")))
        )[:10]
        assert actual_date == exp_date, (
            f"[canonical_oracle] Tanggal delivery {so_num} salah! Expected {exp_date}, got {actual_date}"
        )

        expected_delivered = {}
        expected_cogs_by_sku = {}
        for ol in lines_by_so.get(so_num, []):
            sku = ol["sku_code"]
            lot = ol["lot_number"]
            units = float(ol["qty_cartons"]) * float(ol["carton_qty"])
            cogs = float(ol["cogs_subtotal"])
            expected_delivered[(sku, lot)] = expected_delivered.get((sku, lot), 0.0) + units
            expected_cogs_by_sku[sku] = expected_cogs_by_sku.get(sku, 0.0) + cogs
            expected_saleable_by_sku_lot[(sku, lot)] = expected_saleable_by_sku_lot.get((sku, lot), 0.0) - units
            expected_delivery_cogs_total += cogs

        actual_mls = getattr(deliv, "move_line_ids", [])
        assert actual_mls, f"[canonical_oracle] Move lines pada delivery {so_num} kosong!"

        actual_delivered = {}
        for ml in actual_mls:
            sku = _resolve_ml_sku(env, ml)
            lot_name = _resolve_ml_lot_name(env, ml)
            assert sku, f"[canonical_oracle] Baris move line pada delivery {so_num} tidak memiliki SKU!"
            assert lot_name, f"[canonical_oracle] Baris move line SKU {sku} pada delivery {so_num} tidak memiliki lot!"
            ml_date = str(getattr(ml, "date", ""))[:10]
            assert ml_date == exp_date, (
                f"[canonical_oracle] Tanggal stock.move.line delivery {so_num} salah! Expected {exp_date}, got {ml_date}"
            )
            ml_src = _resolve_loc(env, getattr(ml, "location_id", None))
            ml_dest = _resolve_loc(env, getattr(ml, "location_dest_id", None))
            if ml_src is not None:
                assert getattr(ml_src, "id", None) == wh_loc.id, (
                    f"[canonical_oracle] Lokasi asal stock.move.line delivery {so_num} harus WH/Stock (id={wh_loc.id}), "
                    f"got {getattr(ml_src, 'id', None)}!"
                )
            if ml_dest is not None and getattr(ml_dest, "usage", None):
                assert ml_dest.usage == "customer", (
                    f"[canonical_oracle] Lokasi tujuan stock.move.line delivery {so_num} harus 'customer', got '{ml_dest.usage}'!"
                )
            qty = float(getattr(ml, "quantity", getattr(ml, "qty_done", 0.0)))
            key = (sku, lot_name)
            actual_delivered[key] = actual_delivered.get(key, 0.0) + qty

        # Periksa terlebih dahulu kuantitas pada setiap lot yang diharapkan (agar pesan error lot split spesifik)
        for (exp_sku, exp_lot), exp_qty in expected_delivered.items():
            act_qty = actual_delivered.get((exp_sku, exp_lot), 0.0)
            assert abs(act_qty - exp_qty) < 0.001, (
                f"[canonical_oracle] Kuantitas Lot {exp_lot} salah pada {so_num} (SKU {exp_sku})! "
                f"Expected {exp_qty}, got {act_qty}"
            )

        # Tolak tegas jika ada baris/SKU/lot ekstra atau jumlah baris move line tidak cocok
        extra_deliv_keys = set(actual_delivered.keys()) - set(expected_delivered.keys())
        assert not extra_deliv_keys, (
            f"[canonical_oracle] Ditemukan baris ekstra/SKU asing pada delivery {so_num}: {sorted(extra_deliv_keys)}!"
        )
        assert len(actual_mls) == len(expected_delivered), (
            f"[canonical_oracle] Jumlah baris move line pada delivery {so_num} tidak cocok! "
            f"Expected {len(expected_delivered)}, got {len(actual_mls)}"
        )

        # Verifikasi lokasi, tanggal efektif, dan jurnal valuasi HPP native untuk setiap stock.move aktif pada delivery SO
        so_moves = [
            mv for mv in getattr(deliv, "move_ids", [])
            if getattr(mv, "state", "done") != "cancel"
            and (
                float(getattr(mv, "quantity", getattr(mv, "product_uom_qty", 0.0)) or 0.0) > 0
                or getattr(mv, "move_line_ids", None)
            )
        ]
        assert len(so_moves) >= len(expected_cogs_by_sku), (
            f"[canonical_oracle] Jumlah stock.move aktif pada delivery {so_num} minimal {len(expected_cogs_by_sku)}, "
            f"got {len(so_moves)}!"
        )
        so_am_groups = {}
        seen_so_move_skus = set()
        for mv in so_moves:
            mv_sku = _resolve_ml_sku(env, mv)
            assert mv_sku in expected_cogs_by_sku, (
                f"[canonical_oracle] stock.move SKU '{mv_sku}' pada delivery {so_num} tidak dikenal!"
            )
            mv_date = str(getattr(mv, "date", ""))[:10]
            assert mv_date == exp_date, (
                f"[canonical_oracle] Tanggal stock.move delivery {so_num} salah! Expected {exp_date}, got {mv_date}"
            )
            mv_src = _resolve_loc(env, getattr(mv, "location_id", None))
            mv_dest = _resolve_loc(env, getattr(mv, "location_dest_id", None))
            if mv_src is not None:
                assert getattr(mv_src, "id", None) == wh_loc.id, (
                    f"[canonical_oracle] Lokasi asal stock.move delivery {so_num} harus WH/Stock (id={wh_loc.id}), "
                    f"got {getattr(mv_src, 'id', None)}!"
                )
            if mv_dest is not None and getattr(mv_dest, "usage", None):
                assert mv_dest.usage == "customer", (
                    f"[canonical_oracle] Lokasi tujuan stock.move delivery {so_num} harus 'customer', got '{mv_dest.usage}'!"
                )
            seen_so_move_skus.add(mv_sku)
            ams = _resolve_stock_move_account_moves(env, mv)
            assert len(ams) == 1, (
                f"[canonical_oracle] stock.move delivery {so_num} SKU {mv_sku} wajib memiliki tepat 1 jurnal valuasi HPP, "
                f"got {len(ams)}!"
            )
            mv_mls = getattr(mv, "move_line_ids", None)
            if mv_mls:
                mv_qty = sum(float(getattr(ml, "quantity", getattr(ml, "qty_done", 0.0))) for ml in mv_mls)
            else:
                mv_qty = float(getattr(mv, "quantity", getattr(mv, "product_uom_qty", 0.0)) or 0.0)
            mv_expected_val = mv_qty * unit_cost_by_sku[mv_sku]
            am = ams[0]
            so_am_groups.setdefault(am.id, {"am": am, "expected_val": 0.0})
            so_am_groups[am.id]["expected_val"] += mv_expected_val

        assert seen_so_move_skus == set(expected_cogs_by_sku.keys()), (
            f"[canonical_oracle] Himpunan SKU stock.move pada delivery {so_num} tidak cocok! "
            f"Expected {sorted(expected_cogs_by_sku.keys())}, got {sorted(seen_so_move_skus)}"
        )

        for am_id, grp in so_am_groups.items():
            _verify_valuation_account_move_lines(
                grp["am"],
                f"DELIVERY-{so_num}",
                exp_date,
                "510000",
                "113000",
                grp["expected_val"],
            )
            verified_valuation_am_ids.add(am_id)
            expected_date_by_am_id[am_id] = exp_date

    print(
        f" -> [Oracle Delivery SO] {len(target_so_slice)} SO Deliveries verified DONE "
        f"(exact multiset lines, lot split, move/move_line dates & locations, & native HPP valuation journals)."
    )

    # --- 3. Verifikasi Retur Karantina (Exact-Set, Multiplicity, Source/Dest Usage, SKU+Lot+Qty, & Jurnal Valuasi Native) ---
    rejections = [r for r in rej_rows if r["so_number"] in target_so_set]
    expected_rej_ids = {r["rejection_id"] for r in rejections}
    all_rej_picks_raw = _iter_records(StockPicking.search([("origin", "=like", "REJ-%")]))
    all_rej_picks = [p for p in all_rej_picks_raw if getattr(p, "state", "") != "cancel"]
    actual_rej_ids = {getattr(p, "origin", "") for p in all_rej_picks}
    assert actual_rej_ids == expected_rej_ids, (
        f"[canonical_oracle] Himpunan picking retur karantina di DB ({sorted(actual_rej_ids)}) != "
        f"register ({sorted(expected_rej_ids)})!"
    )
    assert len(all_rej_picks_raw) == len(expected_rej_ids), (
        f"[canonical_oracle] Duplikasi picking retur karantina terdeteksi di DB! "
        f"Expected {len(expected_rej_ids)} record unik, got {len(all_rej_picks_raw)}!"
    )

    for rej in rejections:
        rej_id = rej["rejection_id"]
        rej_picks_raw = _iter_records(StockPicking.search([("origin", "=", rej_id)]))
        rej_pick = _assert_unique_record(rej_picks_raw, f"Picking Retur Karantina {rej_id}")
        assert rej_pick.state == "done", (
            f"[canonical_oracle] Picking karantina {rej_id} belum done! State: {rej_pick.state}"
        )

        # Verifikasi ketat lokasi sumber (wajib usage='customer') dan tujuan (wajib quar_loc.id, 'Karantina FMCG Maumbi', usage='internal')
        src_loc = _resolve_loc(env, getattr(rej_pick, "location_id", None))
        dest_loc = _resolve_loc(env, getattr(rej_pick, "location_dest_id", None))
        src_usage = str(getattr(src_loc, "usage", ""))
        dest_usage = str(getattr(dest_loc, "usage", ""))
        dest_name = str(getattr(dest_loc, "name", ""))

        assert src_usage == "customer", (
            f"[canonical_oracle] Lokasi sumber retur karantina {rej_id} wajib usage='customer', got '{src_usage}'!"
        )
        assert dest_usage == "internal" and dest_name == "Karantina FMCG Maumbi" and getattr(dest_loc, "id", None) == quar_loc.id, (
            f"[canonical_oracle] Lokasi tujuan retur karantina {rej_id} wajib 'Karantina FMCG Maumbi' (id={quar_loc.id}, usage='internal'), "
            f"got '{dest_name}' (id={getattr(dest_loc, 'id', None)}, usage='{dest_usage}')!"
        )

        rej_date = str(
            getattr(rej_pick, "date_done", getattr(rej_pick, "scheduled_date", getattr(rej_pick, "date", "")))
        )[:10]
        assert rej_date == rej["rejection_date"], (
            f"[canonical_oracle] Tanggal retur karantina {rej_id} harus {rej['rejection_date']}! Got {rej_date}"
        )

        expected_rej_sku = rej["sku_code"]
        expected_rej_lot = rej["lot_number"]
        expected_rej_qty = float(rej["qty_cartons"]) * float(rej["carton_qty"])
        expected_rej_cogs = float(rej["cogs_subtotal"])

        expected_quarantine_by_sku_lot[(expected_rej_sku, expected_rej_lot)] = (
            expected_quarantine_by_sku_lot.get((expected_rej_sku, expected_rej_lot), 0.0) + expected_rej_qty
        )
        expected_rejection_cogs_total += expected_rej_cogs

        rej_mls = getattr(rej_pick, "move_line_ids", [])
        assert len(rej_mls) == 1, (
            f"[canonical_oracle] Retur karantina {rej_id} wajib memiliki tepat 1 baris move line, got {len(rej_mls)}!"
        )
        ml0 = rej_mls[0]
        act_rej_sku = _resolve_ml_sku(env, ml0)
        act_rej_lot = _resolve_ml_lot_name(env, ml0)
        act_rej_qty = float(getattr(ml0, "quantity", getattr(ml0, "qty_done", 0.0)))
        ml0_date = str(getattr(ml0, "date", ""))[:10]
        assert ml0_date == rej["rejection_date"], (
            f"[canonical_oracle] Tanggal stock.move.line retur karantina {rej_id} harus {rej['rejection_date']}! Got {ml0_date}"
        )
        ml0_src = _resolve_loc(env, getattr(ml0, "location_id", None))
        ml0_dest = _resolve_loc(env, getattr(ml0, "location_dest_id", None))
        if ml0_src is not None and getattr(ml0_src, "usage", None):
            assert ml0_src.usage == "customer", (
                f"[canonical_oracle] Lokasi sumber stock.move.line retur karantina {rej_id} wajib usage='customer', got '{ml0_src.usage}'!"
            )
        if ml0_dest is not None:
            assert getattr(ml0_dest, "id", None) == quar_loc.id, (
                f"[canonical_oracle] Lokasi tujuan stock.move.line retur karantina {rej_id} wajib Karantina (id={quar_loc.id}), "
                f"got {getattr(ml0_dest, 'id', None)}!"
            )

        assert act_rej_sku == expected_rej_sku, (
            f"[canonical_oracle] SKU retur karantina {rej_id} salah! Expected '{expected_rej_sku}', got '{act_rej_sku}'"
        )
        assert act_rej_lot == expected_rej_lot, (
            f"[canonical_oracle] Lot retur karantina {rej_id} salah! Expected '{expected_rej_lot}', got '{act_rej_lot}'"
        )
        assert abs(act_rej_qty - expected_rej_qty) < 0.001, (
            f"[canonical_oracle] Kuantitas retur karantina {rej_id} salah! Expected {expected_rej_qty}, got {act_rej_qty}"
        )

        rej_moves = [mv for mv in getattr(rej_pick, "move_ids", []) if getattr(mv, "state", "done") != "cancel"]
        assert len(rej_moves) == 1, (
            f"[canonical_oracle] Picking karantina {rej_id} wajib memiliki tepat 1 stock.move, got {len(rej_moves)}!"
        )
        rmv0 = rej_moves[0]
        rmv0_date = str(getattr(rmv0, "date", ""))[:10]
        assert rmv0_date == rej["rejection_date"], (
            f"[canonical_oracle] Tanggal stock.move retur karantina {rej_id} harus {rej['rejection_date']}! Got {rmv0_date}"
        )
        rmv0_src = _resolve_loc(env, getattr(rmv0, "location_id", None))
        rmv0_dest = _resolve_loc(env, getattr(rmv0, "location_dest_id", None))
        if rmv0_src is not None and getattr(rmv0_src, "usage", None):
            assert rmv0_src.usage == "customer", (
                f"[canonical_oracle] Lokasi sumber stock.move retur karantina {rej_id} wajib usage='customer', got '{rmv0_src.usage}'!"
            )
        if rmv0_dest is not None:
            assert getattr(rmv0_dest, "id", None) == quar_loc.id, (
                f"[canonical_oracle] Lokasi tujuan stock.move retur karantina {rej_id} wajib Karantina (id={quar_loc.id}), "
                f"got {getattr(rmv0_dest, 'id', None)}!"
            )
        rej_ams = _resolve_stock_move_account_moves(env, rmv0)
        assert len(rej_ams) == 1, (
            f"[canonical_oracle] Retur karantina {rej_id} wajib memiliki tepat 1 jurnal valuasi native, got {len(rej_ams)}!"
        )
        _verify_valuation_account_move_lines(
            rej_ams[0], f"RETURN-{rej_id}", rej["rejection_date"], "113000", "510000", expected_rej_cogs
        )
        verified_valuation_am_ids.add(rej_ams[0].id)
        expected_date_by_am_id[rej_ams[0].id] = rej["rejection_date"]

        if hasattr(rmv0, "origin_returned_move_id") and rmv0.origin_returned_move_id:
            orig_m = rmv0.origin_returned_move_id
            if isinstance(orig_m, int) and "stock.move" in env:
                orig_m = env["stock.move"].browse(orig_m)
            assert orig_m.product_id == rmv0.product_id, (
                "[canonical_oracle] Produk origin_returned_move_id retur karantina tidak cocok!"
            )
            assert getattr(getattr(orig_m, "location_dest_id", None), "usage", "") == "customer", (
                "[canonical_oracle] Asal outbound origin_returned_move_id bukan customer delivery!"
            )
            print(
                f" -> [Oracle Karantina Binding] {rej_id} terbukti terikat relasional persisten ke "
                f"outbound move {getattr(orig_m, 'id', orig_m)}."
            )
        print(f" -> [Oracle Karantina] {rej_id} verified {act_rej_qty} unit {act_rej_sku} di lokasi {dest_name}.")

    # Verifikasi total seluruh StockPicking di DB (5 PO + N SO + M REJ tanpa ekstra/duplikat)
    all_picks_in_db = _iter_records(StockPicking.search([]))
    expected_total_picks = len(po_headers) + len(target_so_slice) + len(expected_rej_ids)
    assert len(all_picks_in_db) == expected_total_picks, (
        f"[canonical_oracle] Jumlah total StockPicking di DB ({len(all_picks_in_db)}) != "
        f"ekspektasi ({expected_total_picks})! Duplikasi atau picking ekstra terdeteksi."
    )

    # --- 4. Verifikasi Saldo Absolut Stok Fisik, Saleable, Reserved, & Karantina (StockQuant) ---
    actual_saleable_quants = {}
    actual_quarantine_quants = {}
    all_quants = StockQuant.search([])
    all_quants_list = _iter_records(all_quants)

    for q in all_quants_list:
        loc_rec = _resolve_loc(env, getattr(q, "location_id", None))
        loc_usage = str(getattr(loc_rec, "usage", "internal")) if loc_rec else "internal"
        if loc_usage != "internal":
            continue

        loc_id = getattr(loc_rec, "id", getattr(q, "location_id", None))
        loc_name = str(getattr(loc_rec, "name", ""))
        loc_comp = getattr(loc_rec, "company_id", None) if loc_rec else None
        loc_comp_id = getattr(loc_comp, "id", loc_comp) if loc_comp else None
        q_comp = getattr(q, "company_id", None)
        q_comp_id = getattr(q_comp, "id", q_comp) if q_comp else loc_comp_id
        sku = _resolve_ml_sku(env, q)
        lot_name = _resolve_ml_lot_name(env, q)
        qty = float(getattr(q, "quantity", 0.0))
        res_qty = float(getattr(q, "reserved_quantity", 0.0) or 0.0)

        assert abs(res_qty) < 0.001, (
            f"[canonical_oracle] Ditemukan reserved_quantity menggantung ({res_qty}) pada SKU {sku} Lot {lot_name}!"
        )
        assert qty >= -0.001, (
            f"[canonical_oracle] Ditemukan stok negatif ({qty}) pada SKU {sku} Lot {lot_name} di lokasi {loc_name}!"
        )
        if abs(qty) < 0.001:
            continue

        if seed_comp_id and loc_comp_id and loc_comp_id != seed_comp_id:
            raise AssertionError(
                f"[canonical_oracle] Lokasi quant '{loc_name}' (company_id={loc_comp_id}) bukan milik company seed ({seed_comp_id})!"
            )
        if seed_comp_id and q_comp_id and q_comp_id != seed_comp_id:
            raise AssertionError(
                f"[canonical_oracle] Quant SKU {sku} Lot {lot_name} berada pada company_id={q_comp_id}, bukan milik company seed ({seed_comp_id})!"
            )

        key = (sku, lot_name)
        if loc_id == quar_loc.id:
            actual_quarantine_quants[key] = actual_quarantine_quants.get(key, 0.0) + qty
        elif loc_id == wh_loc.id:
            actual_saleable_quants[key] = actual_saleable_quants.get(key, 0.0) + qty
        else:
            raise AssertionError(
                f"[canonical_oracle] Ditemukan quant pada lokasi internal tidak sah '{loc_name}' "
                f"(id={loc_id}, expected wh_loc={wh_loc.id} atau quar_loc={quar_loc.id}) untuk {key}: {qty}"
            )

    expected_nonzero_saleable = {k: v for k, v in expected_saleable_by_sku_lot.items() if abs(v) > 0.001}
    expected_nonzero_quarantine = {k: v for k, v in expected_quarantine_by_sku_lot.items() if abs(v) > 0.001}

    assert set(actual_saleable_quants.keys()) == set(expected_nonzero_saleable.keys()), (
        f"[canonical_oracle] Himpunan (SKU, Lot) saleable di WH/Stock tidak cocok dengan kalkulasi sumber! "
        f"Extra: {sorted(set(actual_saleable_quants.keys()) - set(expected_nonzero_saleable.keys()))}, "
        f"Missing: {sorted(set(expected_nonzero_saleable.keys()) - set(actual_saleable_quants.keys()))}"
    )
    for k, exp_q in expected_nonzero_saleable.items():
        act_q = actual_saleable_quants.get(k, 0.0)
        assert abs(act_q - exp_q) < 0.001, (
            f"[canonical_oracle] Saldo fisik/saleable WH/Stock untuk {k} salah (Quant Drift terdeteksi)! "
            f"Expected {exp_q}, got {act_q}"
        )

    assert set(actual_quarantine_quants.keys()) == set(expected_nonzero_quarantine.keys()), (
        f"[canonical_oracle] Himpunan (SKU, Lot) di Karantina tidak cocok dengan kalkulasi sumber! "
        f"Got {actual_quarantine_quants}, expected {expected_nonzero_quarantine}"
    )
    for k, exp_q in expected_nonzero_quarantine.items():
        act_q = actual_quarantine_quants.get(k, 0.0)
        assert abs(act_q - exp_q) < 0.001, (
            f"[canonical_oracle] Saldo fisik Karantina untuk {k} salah! Expected {exp_q}, got {act_q}"
        )

    actual_saleable_val = sum(qty * unit_cost_by_sku[sku] for (sku, _), qty in actual_saleable_quants.items())
    actual_quarantine_val = sum(qty * unit_cost_by_sku[sku] for (sku, _), qty in actual_quarantine_quants.items())
    expected_total_inv_val = (
        expected_opening_val + expected_po_val_total - expected_delivery_cogs_total + expected_rejection_cogs_total
    )
    assert abs((actual_saleable_val + actual_quarantine_val) - expected_total_inv_val) < 1.0, (
        f"[canonical_oracle] Nilai valuasi fisik persediaan (Rp {actual_saleable_val + actual_quarantine_val:,.2f}) "
        f"!= kalkulasi sumber (Rp {expected_total_inv_val:,.2f})!"
    )
    print(
        f" -> [Oracle Saldo Stok Absolut] {len(actual_saleable_quants)} saleable quants & "
        f"{len(actual_quarantine_quants)} quarantine quants cocok 100% (Total Valuasi: Rp {expected_total_inv_val:,.2f})."
    )

    # --- 5. Verifikasi Nominal & Baris Invoice Komersial (product_id, UoM, sale_line_ids, Net Qty, DPP, PPN) & Saldo AR ---
    invoices_data = {
        iv["so_number"]: iv
        for iv in inv_rows
        if iv["so_number"] in target_so_set
    }
    assert set(invoices_data.keys()) == target_so_set, (
        f"[canonical_oracle] Himpunan invoice di CSV untuk target slice tidak lengkap: {set(invoices_data.keys())}!"
    )

    rejections_by_so_line = {}
    for r in rej_rows:
        key = (r["so_number"], r["sku_code"], r.get("lot_number"))
        rejections_by_so_line[key] = rejections_by_so_line.get(key, 0.0) + float(r["qty_cartons"])

    expected_out_inv_refs = {iv["invoice_number"] for iv in invoices_data.values()}
    all_out_invs = AccountMove.search([("move_type", "=", "out_invoice")])
    all_out_invs_list = _iter_records(all_out_invs)
    actual_out_inv_refs = {getattr(m, "ref", None) for m in all_out_invs_list}
    assert actual_out_inv_refs == expected_out_inv_refs, (
        f"[canonical_oracle] Himpunan faktur out_invoice di DB ({sorted(actual_out_inv_refs)}) != "
        f"target slice ({sorted(expected_out_inv_refs)})!"
    )
    assert len(all_out_invs_list) == len(expected_out_inv_refs), (
        f"[canonical_oracle] Duplikasi faktur out_invoice terdeteksi di DB! "
        f"Expected {len(expected_out_inv_refs)} record unik, got {len(all_out_invs_list)}!"
    )

    inv_rec_by_num = {}
    for so_num, inv_row in invoices_data.items():
        inv_num = inv_row["invoice_number"]
        inv_rec = _assert_unique_record(
            AccountMove.search([("ref", "=", inv_num), ("move_type", "=", "out_invoice")]),
            f"out_invoice {inv_num}",
        )
        assert inv_rec.state == "posted", f"[canonical_oracle] Invoice {inv_num} belum posted!"
        inv_rec_by_num[inv_num] = inv_rec

        inv_date = str(getattr(inv_rec, "date", ""))[:10]
        assert inv_date == inv_row["date_invoice"], (
            f"[canonical_oracle] Tanggal faktur {inv_num} salah! Expected {inv_row['date_invoice']}, got {inv_date}"
        )
        expected_date_by_am_id[inv_rec.id] = inv_row["date_invoice"]

        # Pastikan out_invoice TIDAK menduplikasi baris COGS (display_type='cogs' atau akun 510000/113000)
        dup_cogs_lines = [
            ln for ln in _iter_records(getattr(inv_rec, "line_ids", None))
            if getattr(ln, "display_type", "") == "cogs"
            or str(getattr(getattr(ln, "account_id", None), "code", "")).strip() in ("113000", "510000")
        ]
        assert not dup_cogs_lines, (
            f"[canonical_oracle] Faktur {inv_num} memiliki baris COGS/persediaan duplikat pada jurnal faktur!"
        )

        # Verifikasi detail invoice_line_ids per SKU/produk, UoM, sale_line_ids, qty net of rejection, harga DPP, dan diskon
        so_header_p = build_so_header_payload(so_headers_by_num[so_num])
        exp_inv_line_specs = []
        for lrow in lines_by_so.get(so_num, []):
            line_p = build_order_line_payload(lrow)
            key = (so_num, line_p["sku_code"], line_p["lot_number"])
            rej_cartons = rejections_by_so_line.get(key, 0.0)
            net_cartons = line_p["qty_cartons"] - rej_cartons
            if net_cartons <= 0:
                continue
            net_units = net_cartons * line_p["carton_qty"]
            exp_inv_line_specs.append({
                "sku_code": line_p["sku_code"],
                "lot_number": line_p["lot_number"],
                "net_units": net_units,
                "unit_price_dpp": line_p["unit_price_dpp"],
                "discount_pct": so_header_p["discount_pct"],
            })

        actual_inv_lines = _iter_records(getattr(inv_rec, "invoice_line_ids", None))
        assert len(actual_inv_lines) == len(exp_inv_line_specs), (
            f"[canonical_oracle] Jumlah baris invoice_line_ids pada {inv_num} salah! "
            f"Expected {len(exp_inv_line_specs)}, got {len(actual_inv_lines)}"
        )

        so_rec = so_rec_by_num.get(so_num)
        so_order_line_ids = {
            getattr(sol, "id", None)
            for sol in _iter_records(getattr(so_rec, "order_line", None))
            if getattr(sol, "id", None) is not None
        }

        unmatched_specs = list(exp_inv_line_specs)
        for il in actual_inv_lines:
            il_prod = getattr(il, "product_id", None)
            il_sku = _resolve_ml_sku(env, il)
            assert il_prod and il_sku, (
                f"[canonical_oracle] Baris invoice {inv_num} kehilangan product_id / identitas SKU!"
            )
            exp_prod = adapter.product_by_code.get(il_sku)
            assert exp_prod and getattr(il_prod, "id", il_prod) == exp_prod.id, (
                f"[canonical_oracle] product_id baris invoice {inv_num} untuk SKU '{il_sku}' tidak cocok dengan katalog seed!"
            )
            il_uom = getattr(il, "product_uom_id", None) or getattr(il, "uom_id", None)
            exp_uom = getattr(exp_prod, "uom_id", None)
            if il_uom and exp_uom and getattr(exp_uom, "id", None):
                assert getattr(il_uom, "id", il_uom) == exp_uom.id, (
                    f"[canonical_oracle] UoM baris invoice {inv_num} SKU {il_sku} salah!"
                )
            il_sale_lines = _iter_records(getattr(il, "sale_line_ids", None))
            if so_order_line_ids:
                assert il_sale_lines, (
                    f"[canonical_oracle] Baris invoice {inv_num} SKU {il_sku} tidak memiliki relasi sale_line_ids ke SO {so_num}!"
                )
                for sl_item in il_sale_lines:
                    sl_id = getattr(sl_item, "id", sl_item)
                    assert sl_id in so_order_line_ids, (
                        f"[canonical_oracle] sale_line_ids ({sl_id}) pada baris invoice {inv_num} bukan milik SO {so_num}!"
                    )

            il_qty = float(getattr(il, "quantity", 0.0))
            il_price = float(getattr(il, "price_unit", 0.0))
            il_disc = float(getattr(il, "discount", 0.0) or 0.0)

            matched_idx = None
            for s_idx, spec in enumerate(unmatched_specs):
                if (
                    spec["sku_code"] == il_sku
                    and abs(spec["net_units"] - il_qty) < 0.001
                    and abs(spec["unit_price_dpp"] - il_price) < 0.01
                    and abs(spec["discount_pct"] - il_disc) < 0.001
                ):
                    matched_idx = s_idx
                    break
            assert matched_idx is not None, (
                f"[canonical_oracle] Baris invoice {inv_num} (SKU={il_sku}, qty={il_qty}, price={il_price}, disc={il_disc}) "
                f"tidak cocok dengan spesifikasi register {unmatched_specs}!"
            )
            unmatched_specs.pop(matched_idx)

        exp_dpp = float(inv_row["dpp_amount"])
        exp_ppn = float(inv_row["ppn_11_amount"])
        exp_total = float(inv_row["total_invoice_with_ppn"])

        assert abs(float(inv_rec.amount_untaxed) - exp_dpp) < 0.01, (
            f"[canonical_oracle] DPP {inv_num} salah! Expected {exp_dpp}, got {inv_rec.amount_untaxed}"
        )
        assert abs(float(inv_rec.amount_tax) - exp_ppn) < 0.01, (
            f"[canonical_oracle] PPN {inv_num} salah! Expected {exp_ppn}, got {inv_rec.amount_tax}"
        )
        assert abs(float(inv_rec.amount_total) - exp_total) < 0.01, (
            f"[canonical_oracle] Total {inv_num} salah! Expected {exp_total}, got {inv_rec.amount_total}"
        )

        matching_ar = [c for c in all_ar_rows if c.get("invoice_number") == inv_num]
        if matching_ar:
            total_paid = sum(
                float(c["net_cash_collected_total"]) + float(c.get("early_payment_discount", 0.0))
                for c in matching_ar
            )
            expected_residual = max(0.0, exp_total - total_paid)
        else:
            expected_residual = exp_total

        actual_residual = float(getattr(inv_rec, "amount_residual", 0.0))
        assert abs(actual_residual - expected_residual) < 0.01, (
            f"[canonical_oracle] Saldo residual {inv_num} salah! Expected {expected_residual}, got {actual_residual}"
        )
    print(
        " -> [Oracle Invoice] Invoices verified exact set, product_id, UoM, sale_line_ids, "
        "tanggal, DPP, PPN, dan saldo residual dinamis."
    )

    # --- 6. Verifikasi Jurnal Diskon, Rekonsiliasi AR, Tagihan PO, Pembayaran AP, & OPEX ---
    ar_collections = {
        c["invoice_number"]: c
        for c in all_ar_rows
        if c.get("invoice_number") in expected_out_inv_refs
    }

    expected_ar_pay_ids = {c["payment_id"] for c in ar_collections.values()}
    expected_ap_pay_ids = {r["ap_payment_id"] for r in ap_rows}
    expected_all_pay_ids = expected_ar_pay_ids | expected_ap_pay_ids
    all_payments_in_db = _iter_records(AccountPayment.search([]))
    actual_all_pay_ids = {
        str(getattr(p, "ref", None) or getattr(p, "memo", None) or "")
        for p in all_payments_in_db
    }
    assert actual_all_pay_ids == expected_all_pay_ids, (
        f"[canonical_oracle] Himpunan AccountPayment di DB ({sorted(actual_all_pay_ids)}) != "
        f"register ({sorted(expected_all_pay_ids)})!"
    )
    assert len(all_payments_in_db) == len(expected_all_pay_ids), (
        f"[canonical_oracle] Duplikasi AccountPayment terdeteksi di DB! "
        f"Expected {len(expected_all_pay_ids)}, got {len(all_payments_in_db)}!"
    )

    for inv_num, ar_row in ar_collections.items():
        disc_amt = float(ar_row.get("early_payment_discount", 0.0))
        pay_id = ar_row["payment_id"]
        inv_rec = inv_rec_by_num[inv_num]
        inv_ar_lines = [
            ln for ln in _iter_records(getattr(inv_rec, "line_ids", None))
            if getattr(getattr(ln, "account_id", None), "account_type", "") == "asset_receivable"
        ]
        assert inv_ar_lines, f"[canonical_oracle] Faktur {inv_num} tidak memiliki baris asset_receivable!"

        if disc_amt > 0:
            disc_ref = f"DISC-{pay_id}"
            disc_move = _assert_unique_record(
                AccountMove.search([("ref", "=", disc_ref)]),
                f"Jurnal Diskon {disc_ref}",
            )
            assert disc_move.state == "posted", (
                f"[canonical_oracle] Jurnal diskon {disc_ref} belum posted!"
            )
            disc_date = str(getattr(disc_move, "date", ""))[:10]
            assert disc_date == ar_row["payment_date"], (
                f"[canonical_oracle] Tanggal jurnal diskon {disc_ref} salah! "
                f"Expected {ar_row['payment_date']}, got {disc_date}"
            )
            expected_date_by_am_id[disc_move.id] = ar_row["payment_date"]
            disc_lines = getattr(disc_move, "line_ids", [])
            ar_disc_line = [
                line_item for line_item in disc_lines
                if getattr(getattr(line_item, "account_id", None), "account_type", "") == "asset_receivable"
            ]
            assert ar_disc_line, f"[canonical_oracle] Line piutang pada jurnal diskon {disc_ref} tidak ditemukan!"
            assert abs(float(getattr(ar_disc_line[0], "credit", 0.0)) - disc_amt) < 0.01, (
                f"[canonical_oracle] Nominal kredit diskon {disc_ref} salah! "
                f"Expected {disc_amt}, got {ar_disc_line[0].credit}"
            )
            _verify_exact_reconciliation_pair(inv_ar_lines[0], ar_disc_line[0], f"AR {inv_num} <-> {disc_ref}")

        exp_pay_amt = float(ar_row["net_cash_collected_total"])
        pay_matches = _iter_records(AccountPayment.search([("memo", "=", pay_id)]))
        if not pay_matches:
            pay_matches = _iter_records(AccountPayment.search([("ref", "=", pay_id)]))
        pay_rec = _assert_unique_record(pay_matches, f"AR Payment {pay_id}")
        assert getattr(pay_rec, "state", "") in ("posted", "in_process", "paid"), (
            f"[canonical_oracle] Payment {pay_id} state bukan posted/in_process/paid! Got: {getattr(pay_rec, 'state', '')}"
        )
        assert abs(float(getattr(pay_rec, "amount", 0.0)) - exp_pay_amt) < 0.01, (
            f"[canonical_oracle] Nominal payment {pay_id} salah! Expected {exp_pay_amt}, got {pay_rec.amount}"
        )
        if getattr(pay_rec, "move_id", None):
            expected_date_by_am_id[pay_rec.move_id.id] = ar_row["payment_date"]
            pay_ar_lines = [
                ln for ln in _iter_records(getattr(pay_rec.move_id, "line_ids", None))
                if getattr(getattr(ln, "account_id", None), "account_type", "") == "asset_receivable"
            ]
            assert pay_ar_lines, f"[canonical_oracle] Payment AR {pay_id} tidak memiliki baris asset_receivable!"
            _verify_exact_reconciliation_pair(inv_ar_lines[0], pay_ar_lines[0], f"AR {inv_num} <-> {pay_id}")

    # Verifikasi 5 Vendor Bills PO + 30 OPEX Bills dan 4 Pembayaran AP + 1 Open AP (PO-2026-06-05)
    ap_paid_by_po = {r["po_number"]: r for r in ap_rows}
    expected_opex_refs = {f"OPEX-2026-07-{idx:02d}" for idx in range(1, len(opex_rows) + 1)}
    expected_in_invoice_refs = expected_po_nums | expected_opex_refs
    all_in_invoices = AccountMove.search([("move_type", "=", "in_invoice")])
    all_in_list = _iter_records(all_in_invoices)
    actual_bill_refs = {str(getattr(m, "ref", "")) for m in all_in_list}
    assert actual_bill_refs == expected_in_invoice_refs, (
        f"[canonical_oracle] Set Vendor Bill (in_invoice) tidak persis sama dengan 5 PO + 30 OPEX kanonikal! "
        f"Expected: {sorted(expected_in_invoice_refs)}, Actual: {sorted(actual_bill_refs)}"
    )
    assert len(all_in_list) == len(expected_in_invoice_refs), (
        f"[canonical_oracle] Ditemukan Vendor Bill duplikat! "
        f"Expected {len(expected_in_invoice_refs)}, got {len(all_in_list)}"
    )

    for h in po_headers:
        po_num = h["po_number"]
        bill = _assert_unique_record(
            AccountMove.search([("ref", "=", po_num), ("move_type", "=", "in_invoice")]),
            f"Vendor Bill {po_num}",
        )
        assert bill.state == "posted", f"[canonical_oracle] Vendor Bill {po_num} tidak ditemukan/belum posted!"
        bill_date = str(getattr(bill, "date", ""))[:10]
        assert bill_date == h["arrival_maumbi_date"], (
            f"[canonical_oracle] Tanggal Vendor Bill {po_num} salah! "
            f"Expected {h['arrival_maumbi_date']}, got {bill_date}"
        )
        expected_date_by_am_id[bill.id] = h["arrival_maumbi_date"]

        exp_bill_dpp = float(h["total_dpp"])
        bill_ap_lines = [
            ln for ln in getattr(bill, "line_ids", [])
            if getattr(getattr(ln, "account_id", None), "account_type", "") == "liability_payable"
        ]
        assert bill_ap_lines, f"[canonical_oracle] Vendor Bill {po_num} tidak memiliki baris liability_payable!"
        act_bill_credit = sum(float(getattr(ln, "credit", 0.0)) for ln in bill_ap_lines)
        assert abs(act_bill_credit - exp_bill_dpp) < 1.0, (
            f"[canonical_oracle] Nominal hutang Vendor Bill {po_num} salah! Expected {exp_bill_dpp}, got {act_bill_credit}"
        )

        if po_num in ap_paid_by_po:
            ap_info = ap_paid_by_po[po_num]
            ap_id = ap_info["ap_payment_id"]
            ap_matches = _iter_records(AccountPayment.search([("memo", "=", ap_id)]))
            if not ap_matches:
                ap_matches = _iter_records(AccountPayment.search([("ref", "=", ap_id)]))
            ap_rec = _assert_unique_record(ap_matches, f"AP Payment {ap_id}")
            assert abs(float(getattr(ap_rec, "amount", 0.0)) - float(ap_info["amount_paid_dpp"])) < 0.01, (
                f"[canonical_oracle] Nominal AP Payment {ap_id} salah!"
            )
            if getattr(ap_rec, "move_id", None):
                expected_date_by_am_id[ap_rec.move_id.id] = ap_info["payment_date"]
                ap_pay_lines = [
                    ln for ln in _iter_records(getattr(ap_rec.move_id, "line_ids", None))
                    if getattr(getattr(ln, "account_id", None), "account_type", "") == "liability_payable"
                ]
                assert ap_pay_lines, f"[canonical_oracle] Payment AP {ap_id} tidak memiliki baris liability_payable!"
                _verify_exact_reconciliation_pair(bill_ap_lines[0], ap_pay_lines[0], f"AP {po_num} <-> {ap_id}")
            for ln in bill_ap_lines:
                assert adapter._is_reconciled(ln), (
                    f"[canonical_oracle] Vendor Bill {po_num} wajib lunas terekonsiliasi dengan {ap_id}!"
                )
        else:
            # PO-2026-06-05 wajib masih terbuka (Open AP) sebesar Rp 2.899.971.200
            for ln in bill_ap_lines:
                assert not getattr(ln, "reconciled", False), (
                    f"[canonical_oracle] Vendor Bill {po_num} seharusnya masih Open AP (belum jatuh tempo di Juli 2026)!"
                )

    expected_opex_gl_by_code = {}
    comp_partner_id = getattr(getattr(getattr(adapter, "company", None), "partner_id", None), "id", None)
    for idx, op in enumerate(opex_rows, start=1):
        ref_code = f"OPEX-2026-07-{idx:02d}"
        op_move = _assert_unique_record(
            AccountMove.search([("ref", "=", ref_code)]),
            f"OPEX {ref_code}",
        )
        assert op_move.state == "posted", f"[canonical_oracle] OPEX move {ref_code} belum posted!"
        op_date = str(getattr(op_move, "date", ""))[:10]
        assert op_date == op["date"], (
            f"[canonical_oracle] Tanggal OPEX {ref_code} salah! Expected {op['date']}, got {op_date}"
        )
        expected_date_by_am_id[op_move.id] = op["date"]

        exp_cat = str(op["category"]).strip()
        exp_desc = str(op["description"]).strip()
        exp_pay_type = str(op["payment_type"]).strip()
        exp_amt = float(op["amount"])
        exp_acc_code, _ = OPEX_CATEGORY_ACCOUNT_MAP[exp_cat]
        exp_p_ref, _ = OPEX_PAYMENT_PARTNER_MAP[exp_pay_type]
        expected_opex_gl_by_code[exp_acc_code] = expected_opex_gl_by_code.get(exp_acc_code, 0.0) + exp_amt

        op_partner = getattr(op_move, "partner_id", None)
        op_partner_id = getattr(op_partner, "id", op_partner)
        assert op_partner_id and op_partner_id != comp_partner_id, (
            f"[canonical_oracle] OPEX {ref_code} dilarang menggunakan partner company sendiri!"
        )
        assert getattr(op_partner, "ref", None) == exp_p_ref, (
            f"[canonical_oracle] Partner OPEX {ref_code} salah! Expected '{exp_p_ref}', got '{getattr(op_partner, 'ref', None)}'"
        )

        op_inv_lines = _iter_records(getattr(op_move, "invoice_line_ids", None))
        if op_inv_lines:
            line_name = str(getattr(op_inv_lines[0], "name", ""))
            assert exp_cat in line_name and exp_desc in line_name, (
                f"[canonical_oracle] Deskripsi baris OPEX {ref_code} ('{line_name}') tidak memuat '{exp_cat}: {exp_desc}'!"
            )

        op_jlines = _iter_records(getattr(op_move, "line_ids", None))
        assert op_jlines, f"[canonical_oracle] OPEX {ref_code} tidak memiliki line_ids!"
        op_debit_by_code = {}
        op_credit_payable = 0.0
        for jl in op_jlines:
            acc = getattr(jl, "account_id", None)
            code = str(getattr(acc, "code", "") or "").strip()
            acc_type = str(getattr(acc, "account_type", "") or "").strip()
            d = round(float(getattr(jl, "debit", 0.0)), 2)
            c = round(float(getattr(jl, "credit", 0.0)), 2)
            if d > 0:
                op_debit_by_code[code] = round(op_debit_by_code.get(code, 0.0) + d, 2)
            if c > 0:
                assert acc_type == "liability_payable", (
                    f"[canonical_oracle] Akun kredit lawan OPEX {ref_code} harus liability_payable, got '{acc_type}' (code='{code}')!"
                )
                op_credit_payable = round(op_credit_payable + c, 2)

        tot_op_debit = round(sum(op_debit_by_code.values()), 2)
        assert abs(tot_op_debit - exp_amt) < 0.01 and abs(op_credit_payable - exp_amt) < 0.01, (
            f"[canonical_oracle] Nominal beban {ref_code} salah! "
            f"Expected Rp {exp_amt:,.2f}, got debit=Rp {tot_op_debit:,.2f}, credit=Rp {op_credit_payable:,.2f}"
        )
        assert set(op_debit_by_code.keys()) == {exp_acc_code}, (
            f"[canonical_oracle] Akun debit beban {ref_code} salah! "
            f"Expected {{{exp_acc_code!r}}}, got {set(op_debit_by_code.keys())}"
        )

    # --- 7. Verifikasi Saldo Absolut GL As-Of (113000, 113900, 510000, & 610100-610400) & Tanggal Eksak Seluruh Jurnal ---
    all_moves = AccountMove.search([])
    all_moves_list = _iter_records(all_moves)
    assert len(all_moves_list) > 0, "[canonical_oracle] FATAL: Tidak ada entri jurnal yang terbentuk di GL!"

    gl_net_by_code = {}
    for m in all_moves_list:
        assert getattr(m, "state", "") == "posted", (
            f"[canonical_oracle] Entri jurnal '{getattr(m, 'name', m.id)}' belum posted!"
        )
        m_date = str(getattr(m, "date", ""))[:10]
        assert m_date.startswith("2026-07-"), (
            f"[canonical_oracle] FATAL: Entry jurnal '{getattr(m, 'ref', m.id)}' bocor dengan tanggal {m_date}! "
            f"Wajib selaras di bulan Juli 2026."
        )
        if m.id in expected_date_by_am_id:
            exp_m_date = expected_date_by_am_id[m.id]
            assert m_date == exp_m_date, (
                f"[canonical_oracle] Tanggal jurnal '{getattr(m, 'ref', m.id)}' (ID {m.id}) bergeser! "
                f"Expected {exp_m_date}, got {m_date}"
            )
        else:
            raise AssertionError(
                f"[canonical_oracle] Ditemukan entri jurnal asing/ekstra di luar ekspektasi oracle: "
                f"ID={m.id}, ref='{getattr(m, 'ref', '')}', date={m_date}"
            )

        lines = getattr(m, "line_ids", [])
        assert lines, f"[canonical_oracle] Jurnal '{getattr(m, 'ref', m.id)}' tidak memiliki baris line_ids!"
        tot_debit = sum(float(getattr(jline, "debit", 0.0)) for jline in lines)
        tot_credit = sum(float(getattr(jline, "credit", 0.0)) for jline in lines)
        assert abs(tot_debit - tot_credit) < 0.01, (
            f"[canonical_oracle] Jurnal '{getattr(m, 'name', m.id)}' tidak balance! Debit={tot_debit}, Credit={tot_credit}"
        )
        for jline in lines:
            acc = getattr(jline, "account_id", None)
            code = str(getattr(acc, "code", "") or "").strip()
            if code:
                d = float(getattr(jline, "debit", 0.0))
                c = float(getattr(jline, "credit", 0.0))
                gl_net_by_code[code] = gl_net_by_code.get(code, 0.0) + (d - c)

    expected_gl_113000 = expected_total_inv_val
    expected_gl_113900 = -(expected_opening_val + expected_po_val_total)
    expected_gl_510000 = expected_delivery_cogs_total - expected_rejection_cogs_total

    act_gl_113000 = gl_net_by_code.get("113000", 0.0)
    act_gl_113900 = gl_net_by_code.get("113900", 0.0)
    act_gl_510000 = gl_net_by_code.get("510000", 0.0)

    assert abs(act_gl_113000 - expected_gl_113000) < 1.0, (
        f"[canonical_oracle] Saldo absolut GL Persediaan (113000) salah! "
        f"Expected Rp {expected_gl_113000:,.2f}, got Rp {act_gl_113000:,.2f}"
    )
    assert abs(act_gl_113900 - expected_gl_113900) < 1.0, (
        f"[canonical_oracle] Saldo absolut GL Interim Penerimaan (113900) salah! "
        f"Expected Rp {expected_gl_113900:,.2f}, got Rp {act_gl_113900:,.2f}"
    )
    assert abs(act_gl_510000 - expected_gl_510000) < 1.0, (
        f"[canonical_oracle] Saldo absolut GL HPP (510000) salah! "
        f"Expected Rp {expected_gl_510000:,.2f}, got Rp {act_gl_510000:,.2f}"
    )

    total_actual_opex_gl = 0.0
    for opex_code, exp_opex_total in sorted(expected_opex_gl_by_code.items()):
        act_opex_val = gl_net_by_code.get(opex_code, 0.0)
        total_actual_opex_gl += act_opex_val
        assert abs(act_opex_val - exp_opex_total) < 1.0, (
            f"[canonical_oracle] Saldo GL Beban OPEX ({opex_code}) salah! "
            f"Expected Rp {exp_opex_total:,.2f}, got Rp {act_opex_val:,.2f}"
        )
    assert abs(total_actual_opex_gl - 394350000.0) < 1.0, (
        f"[canonical_oracle] Total agregat GL Beban OPEX 30 entri salah! "
        f"Expected Rp 394,350,000.00, got Rp {total_actual_opex_gl:,.2f}"
    )

    print(
        f" -> [Oracle Jurnal Stok & GL] Seluruh {len(all_moves_list)} journal entries terbukti posted, balance, "
        f"bertanggal eksak, dan saldo GL 113000/113900/510000 cocok 100%."
    )
    print("=" * 80)
    print("[canonical_oracle] SELURUH VERIFIKASI ORACLE REGISTER KANONIKAL LULUS 100%!")
    print("=" * 80)


class RollbackSentinel(Exception):
    """Sentinel internal untuk memicu rollback savepoint tanpa dianggap kegagalan tes."""

    pass


def verify_slice_mutation_rejection(env, adapter, reg_path, target_so_slice=None):
    """Membuktikan daya uji aktif (active fault detection) dari oracle secara terisolasi.

    Menjalankan 11 mutasi nyata dalam savepoint database dengan unconditional rollback:
      1. Kuantitas lot split dirusak (lot kedua hilang/0 unit pada SO-202607-0317).
      2. Penambahan baris ekstra 999 unit SKU asing pada picking SO-202607-0317.
      3. Substitusi SKU pada move line delivery SO-202607-0001.
      4. Duplikasi picking delivery pada SO-202607-0001.
      5. Lokasi asal/tujuan retur karantina REJ-202607-001 diubah menjadi salah.
      6. Nilai nominal DPP invoice dipalsukan (INV-202607-0317).
      7. Hilangnya jurnal valuasi native pada stock.move delivery SO-202607-0063.
      8. Jurnal valuasi GL seimbang tetapi salah akun / salah nilai.
      9. Perubahan quant langsung (+100.000 unit drift) pada stock.quant.
     10. Tanggal jurnal bergeser ke tanggal lain di dalam bulan Juli 2026 (2026-07-01 -> 2026-07-15).
     11. Tanggal jurnal bocor ke tanggal runtime di luar Juli 2026 (2026-10-27).
    """
    if env is None:
        raise ValueError("[mutation_rejection] FATAL: env (Odoo environment) wajib disediakan!")
    reg_path = Path(reg_path)
    if not reg_path.is_dir():
        raise FileNotFoundError(f"[mutation_rejection] FATAL: Direktori register tidak valid: {reg_path}")

    REQUIRED_MODELS = [
        "stock.picking", "account.move", "account.payment", "stock.quant",
        "purchase.order", "sale.order", "stock.move", "stock.move.line", "stock.location",
    ]
    for m in REQUIRED_MODELS:
        if m not in env:
            raise RuntimeError(f"[mutation_rejection] Model Odoo '{m}' wajib terdaftar di env! Fail-closed.")

    if target_so_slice is None:
        target_so_slice = ["SO-202607-0001", "SO-202607-0063", "SO-202607-0317"]

    print("\n" + "=" * 80)
    print("[mutation_rejection] Phase 0: Verifikasi baseline oracle sebelum mutasi...")
    print("=" * 80)
    verify_run1_against_canonical_oracle(env, adapter, reg_path, target_so_slice)
    print(" -> [Baseline Oracle] Terbukti PASS 100%.")

    def _snapshot_mock_env():
        store_backups = {}
        rec_backups = []

        def _backup_rec(r, seen_ids):
            if id(r) in seen_ids or not hasattr(r, "__dict__"):
                return
            seen_ids.add(id(r))
            vals_cp = dict(getattr(r, "_vals", {})) if hasattr(r, "_vals") else None
            dict_cp = dict(r.__dict__)
            for list_attr in ("move_line_ids", "move_ids", "line_ids", "invoice_line_ids", "picking_ids", "order_line"):
                if list_attr in dict_cp and isinstance(dict_cp[list_attr], list):
                    lst_cls = type(dict_cp[list_attr])
                    dict_cp[list_attr] = lst_cls(dict_cp[list_attr])
                if vals_cp and list_attr in vals_cp and isinstance(vals_cp[list_attr], list):
                    lst_cls = type(vals_cp[list_attr])
                    vals_cp[list_attr] = lst_cls(vals_cp[list_attr])
            rec_backups.append((r, vals_cp, dict_cp))
            for list_attr in ("move_line_ids", "move_ids", "line_ids", "invoice_line_ids", "picking_ids", "order_line"):
                sub_list = getattr(r, list_attr, None)
                if isinstance(sub_list, (list, tuple)):
                    for sub_r in sub_list:
                        _backup_rec(sub_r, seen_ids)

        seen = set()
        for m in list(env.keys()):
            if hasattr(env[m], "store") and isinstance(env[m].store, dict):
                store_backups[m] = (dict(env[m].store), getattr(env[m], "seq", 1))
                for rec in env[m].store.values():
                    _backup_rec(rec, seen)
        return store_backups, rec_backups

    def _restore_mock_env(backup_tuple):
        store_backups, rec_backups = backup_tuple
        for m, (st_dict, seq_val) in store_backups.items():
            env[m].store.clear()
            env[m].store.update(st_dict)
            env[m].seq = seq_val
        for rec, vals_copy, dict_copy in rec_backups:
            rec.__dict__.clear()
            rec.__dict__.update(dict_copy)
            if vals_copy is not None:
                rec._vals = dict(vals_copy)

    def _execute_isolated_mutation(mutator_fn, expected_error_substring, mutation_name):
        print(f"\n[mutation_rejection] Menjalankan {mutation_name}...")
        has_cr = hasattr(env, "cr") and hasattr(env.cr, "savepoint")
        oracle_rejected = False
        caught_error = None

        mock_backup = None if has_cr else _snapshot_mock_env()

        if has_cr:
            try:
                with env.cr.savepoint():
                    mutator_fn()
                    if hasattr(env, "invalidate_all"):
                        env.invalidate_all()

                    try:
                        verify_run1_against_canonical_oracle(env, adapter, reg_path, target_so_slice)
                    except AssertionError as ae:
                        caught_error = str(ae)
                        if expected_error_substring in caught_error:
                            oracle_rejected = True
                        else:
                            raise RuntimeError(
                                f"[mutation_rejection] Mutasi '{mutation_name}' ditolak karena alasan yang SALAH!\n"
                                f"Expected substring: '{expected_error_substring}'\n"
                                f"Actual error: '{caught_error}'"
                            ) from ae
                    raise RollbackSentinel()
            except RollbackSentinel:
                pass
            if hasattr(env, "invalidate_all"):
                env.invalidate_all()
        else:
            try:
                mutator_fn()
                try:
                    verify_run1_against_canonical_oracle(env, adapter, reg_path, target_so_slice)
                except AssertionError as ae:
                    caught_error = str(ae)
                    if expected_error_substring in caught_error:
                        oracle_rejected = True
                    else:
                        raise RuntimeError(
                            f"[mutation_rejection] Mutasi '{mutation_name}' ditolak karena alasan salah: '{caught_error}'"
                        ) from ae
            finally:
                if mock_backup:
                    _restore_mock_env(mock_backup)

        if not oracle_rejected:
            raise AssertionError(f"[mutation_rejection] FATAL: Oracle gagal menolak mutasi '{mutation_name}'!")

        print(f" -> [{mutation_name} PASSED] Oracle produksi berhasil menolak: {caught_error}")

        verify_run1_against_canonical_oracle(env, adapter, reg_path, target_so_slice)
        print(f" -> [Post-{mutation_name}] Oracle PASS kembali (rollback terbukti bersih & terisolasi).")

    def _find_so_picking(so_num: str):
        SaleOrder = env["sale.order"].sudo()
        StockPicking = env["stock.picking"].sudo()
        so = SaleOrder.search([("client_order_ref", "=", so_num)], limit=1) or SaleOrder.search(
            [("name", "=", so_num)], limit=1
        )
        picks = [p for p in getattr(so, "picking_ids", []) if getattr(p, "state", "") != "cancel"] if so else []
        return picks[0] if picks else StockPicking.search([("origin", "=", so_num)], limit=1)

    # --- Mutasi 1: Cacat Lot Split pada SO-202607-0317 ---
    def mutate_lot_split():
        pick317 = _find_so_picking("SO-202607-0317")
        assert pick317, "[mutation_rejection] Picking SO-202607-0317 harus tersedia!"
        found = False
        for ml in getattr(pick317, "move_line_ids", []):
            if _resolve_ml_lot_name(env, ml) == "LOT-VER-20260704-04":
                if hasattr(env, "cr") and hasattr(env.cr, "execute"):
                    env.cr.execute("UPDATE stock_move_line SET quantity = 0.0 WHERE id = %s", (ml.id,))
                    if hasattr(ml, "invalidate_recordset"):
                        ml.invalidate_recordset()
                elif callable(getattr(ml, "write", None)):
                    ml.write({"quantity": 0.0})
                else:
                    setattr(ml, "quantity", 0.0)
                found = True
                break
        assert found, "[mutation_rejection] Lot LOT-VER-20260704-04 tidak ditemukan pada SO-202607-0317!"

    _execute_isolated_mutation(
        mutate_lot_split,
        "Kuantitas Lot LOT-VER-20260704-04",
        "Mutation 1 (Cacat Lot Split)",
    )

    # --- Mutasi 2: Penambahan Baris Ekstra 999 Unit SKU Asing pada SO-202607-0317 ---
    def mutate_extra_line_bogus_sku():
        pick317 = _find_so_picking("SO-202607-0317")
        Product = env["product.product"].sudo()
        StockLot = env["stock.lot"].sudo()
        StockMoveLine = env["stock.move.line"].sudo()
        bogus_prod = Product.create({"name": "Bogus Foreign Product", "default_code": "BOGUS-SKU-999"})
        bogus_lot = StockLot.create({
            "name": "BOGUS-LOT-999",
            "product_id": bogus_prod.id,
            "company_id": env.company.id,
        })
        sml_fields = getattr(StockMoveLine, "_fields", {})
        ref_ml_date = (
            getattr(pick317.move_line_ids[0], "date", None)
            if getattr(pick317, "move_line_ids", None)
            else None
        ) or "2026-07-09 10:00:00"
        ml_vals = {
            "picking_id": pick317.id,
            "product_id": bogus_prod.id,
            "lot_id": bogus_lot.id,
            "quantity": 999.0,
            "location_id": getattr(pick317.location_id, "id", 1),
            "location_dest_id": getattr(pick317.location_dest_id, "id", 1),
            "date": ref_ml_date,
        }
        if sml_fields and not isinstance(sml_fields, bool) and hasattr(sml_fields, "__contains__"):
            if "product_uom_id" in sml_fields and getattr(bogus_prod, "uom_id", None):
                ml_vals["product_uom_id"] = bogus_prod.uom_id.id
            if "uom_id" in sml_fields and getattr(bogus_prod, "uom_id", None):
                ml_vals["uom_id"] = bogus_prod.uom_id.id
            if "company_id" in sml_fields and getattr(env, "company", None):
                ml_vals["company_id"] = env.company.id
            ml_vals = {k: v for k, v in ml_vals.items() if k in sml_fields}
        extra_ml = StockMoveLine.create(ml_vals)
        if hasattr(pick317, "move_line_ids") and hasattr(pick317.move_line_ids, "append"):
            pick317.move_line_ids.append(extra_ml)

    _execute_isolated_mutation(
        mutate_extra_line_bogus_sku,
        "baris ekstra/SKU asing pada delivery SO-202607-0317",
        "Mutation 2 (Baris Ekstra 999 Unit SKU Asing)",
    )

    # --- Mutasi 3: Substitusi SKU pada Move Line Delivery SO-202607-0001 ---
    def mutate_sku_substitution():
        pick1 = _find_so_picking("SO-202607-0001")
        other_prod = adapter.product_by_code.get("ULV-RNS-03")
        ml0 = pick1.move_line_ids[0]
        if hasattr(env, "cr") and hasattr(env.cr, "execute"):
            env.cr.execute("UPDATE stock_move_line SET product_id = %s WHERE id = %s", (other_prod.id, ml0.id))
            if hasattr(ml0, "invalidate_recordset"):
                ml0.invalidate_recordset()
        else:
            ml0.write({"product_id": other_prod.id})

    _execute_isolated_mutation(
        mutate_sku_substitution,
        "salah pada SO-202607-0001",
        "Mutation 3 (Substitusi SKU pada Move Line)",
    )

    # --- Mutasi 4: Duplikasi Picking Delivery pada SO-202607-0001 ---
    def mutate_duplicate_picking():
        pick1 = _find_so_picking("SO-202607-0001")
        StockPicking = env["stock.picking"].sudo()
        sp_fields = getattr(StockPicking, "_fields", {})
        dup_vals = {
            "origin": "SO-202607-0001",
            "location_id": getattr(pick1.location_id, "id", 1),
            "location_dest_id": getattr(pick1.location_dest_id, "id", 1),
            "picking_type_id": getattr(getattr(pick1, "picking_type_id", None), "id", False),
        }
        if sp_fields and not isinstance(sp_fields, bool) and hasattr(sp_fields, "__contains__"):
            if "company_id" in sp_fields and getattr(env, "company", None):
                dup_vals["company_id"] = env.company.id
            dup_vals = {k: v for k, v in dup_vals.items() if k in sp_fields}
        dup_pick = StockPicking.create(dup_vals)
        SaleOrder = env["sale.order"].sudo()
        so1 = SaleOrder.search([("client_order_ref", "=", "SO-202607-0001")], limit=1)
        if so1 and hasattr(so1, "picking_ids") and hasattr(so1.picking_ids, "append"):
            so1.picking_ids.append(dup_pick)

    _execute_isolated_mutation(
        mutate_duplicate_picking,
        "Expected tepat 1 delivery picking untuk SO-202607-0001",
        "Mutation 4 (Duplikasi Picking Delivery)",
    )

    # --- Mutasi 5: Lokasi Sumber Retur Karantina REJ-202607-001 Salah ---
    def mutate_quarantine_wrong_location():
        StockPicking = env["stock.picking"].sudo()
        rej_pick = StockPicking.search([("origin", "=", "REJ-202607-001")], limit=1)
        wh_loc = getattr(adapter, "wh_stock_loc", None)
        if hasattr(env, "cr") and hasattr(env.cr, "execute"):
            env.cr.execute("UPDATE stock_picking SET location_id = %s WHERE id = %s", (wh_loc.id, rej_pick.id))
            if hasattr(rej_pick, "invalidate_recordset"):
                rej_pick.invalidate_recordset()
        else:
            rej_pick.write({"location_id": wh_loc})

    _execute_isolated_mutation(
        mutate_quarantine_wrong_location,
        "Lokasi sumber retur karantina REJ-202607-001 wajib usage='customer'",
        "Mutation 5 (Lokasi Sumber Retur Karantina Salah)",
    )

    # --- Mutasi 6: Pemalsuan DPP Invoice INV-202607-0317 ---
    def mutate_invoice_dpp():
        AccountMove = env["account.move"].sudo()
        inv317 = AccountMove.search([("ref", "=", "INV-202607-0317")], limit=1)
        if hasattr(env, "cr") and hasattr(env.cr, "execute"):
            env.cr.execute("UPDATE account_move SET amount_untaxed = 9999999.0 WHERE id = %s", (inv317.id,))
            if hasattr(inv317, "invalidate_recordset"):
                inv317.invalidate_recordset()
        else:
            setattr(inv317, "amount_untaxed", 9999999.0)

    _execute_isolated_mutation(
        mutate_invoice_dpp,
        "DPP INV-202607-0317 salah",
        "Mutation 6 (Pemalsuan DPP Invoice)",
    )

    # --- Mutasi 7: Hilangnya Jurnal Valuasi Native pada Stock Move Delivery ---
    def mutate_missing_native_journal():
        pick63 = _find_so_picking("SO-202607-0063")
        mv0 = pick63.move_ids[0]
        if hasattr(env, "cr") and hasattr(env.cr, "execute"):
            env.cr.execute("UPDATE stock_move SET account_move_id = NULL WHERE id = %s", (mv0.id,))
            if hasattr(mv0, "invalidate_recordset"):
                mv0.invalidate_recordset()
        else:
            mv0.write({"account_move_id": False})

    _execute_isolated_mutation(
        mutate_missing_native_journal,
        "wajib memiliki tepat 1 jurnal valuasi HPP",
        "Mutation 7 (Hilangnya Jurnal Valuasi Native)",
    )

    # --- Mutasi 8: Jurnal Valuasi GL Seimbang tapi Salah Nilai / Salah Akun ---
    def mutate_balanced_wrong_gl_value():
        pick63 = _find_so_picking("SO-202607-0063")
        mv0 = pick63.move_ids[0]
        ams = _resolve_stock_move_account_moves(env, mv0)
        am0 = ams[0]
        for ln in am0.line_ids:
            if float(getattr(ln, "debit", 0.0)) > 0:
                if hasattr(env, "cr") and hasattr(env.cr, "execute"):
                    env.cr.execute("UPDATE account_move_line SET debit = debit + 500000.0 WHERE id = %s", (ln.id,))
                else:
                    ln.write({"debit": float(ln.debit) + 500000.0})
            elif float(getattr(ln, "credit", 0.0)) > 0:
                if hasattr(env, "cr") and hasattr(env.cr, "execute"):
                    env.cr.execute("UPDATE account_move_line SET credit = credit + 500000.0 WHERE id = %s", (ln.id,))
                else:
                    ln.write({"credit": float(ln.credit) + 500000.0})

    _execute_isolated_mutation(
        mutate_balanced_wrong_gl_value,
        "Nominal jurnal valuasi 'DELIVERY-SO-202607-0063'",
        "Mutation 8 (Jurnal Valuasi Seimbang Salah Nilai)",
    )

    # --- Mutasi 9: Perubahan Quant Langsung (+100.000 Unit Drift) ---
    def mutate_quant_drift():
        StockQuant = env["stock.quant"].sudo()
        wh_loc = getattr(adapter, "wh_stock_loc", None)
        q0 = StockQuant.search([("location_id", "=", wh_loc.id)], limit=1)
        if hasattr(env, "cr") and hasattr(env.cr, "execute"):
            env.cr.execute("UPDATE stock_quant SET quantity = quantity + 100000.0 WHERE id = %s", (q0.id,))
            if hasattr(q0, "invalidate_recordset"):
                q0.invalidate_recordset()
        else:
            q0.write({"quantity": float(q0.quantity) + 100000.0})

    _execute_isolated_mutation(
        mutate_quant_drift,
        "Quant Drift terdeteksi",
        "Mutation 9 (Perubahan Quant +100.000 Unit)",
    )

    # --- Mutasi 10: Tanggal Jurnal Bergeser di Dalam Bulan Juli 2026 ---
    def mutate_date_within_july():
        AccountMove = env["account.move"].sudo()
        inv1 = AccountMove.search([("ref", "=", "INV-202607-0001")], limit=1)
        if hasattr(env, "cr") and hasattr(env.cr, "execute"):
            env.cr.execute("UPDATE account_move SET date = '2026-07-15' WHERE id = %s", (inv1.id,))
            if hasattr(inv1, "invalidate_recordset"):
                inv1.invalidate_recordset()
        else:
            setattr(inv1, "date", "2026-07-15")

    _execute_isolated_mutation(
        mutate_date_within_july,
        "Tanggal faktur INV-202607-0001 salah! Expected 2026-07-02, got 2026-07-15",
        "Mutation 10 (Pergeseran Tanggal di Dalam Juli 2026)",
    )

    # --- Mutasi 11: Kebocoran Tanggal Jurnal ke Runtime (Di Luar Juli 2026) ---
    def mutate_invoice_date_runtime():
        AccountMove = env["account.move"].sudo()
        inv1 = AccountMove.search([("ref", "=", "INV-202607-0001")], limit=1)
        if hasattr(env, "cr") and hasattr(env.cr, "execute"):
            env.cr.execute("UPDATE account_move SET date = '2026-10-27' WHERE id = %s", (inv1.id,))
            if hasattr(inv1, "invalidate_recordset"):
                inv1.invalidate_recordset()
        else:
            setattr(inv1, "date", "2026-10-27")

    _execute_isolated_mutation(
        mutate_invoice_date_runtime,
        "Expected 2026-07-02, got 2026-10-27",
        "Mutation 11 (Kebocoran Tanggal Runtime)",
    )

    # --- Mutasi 12: Penghapusan product_id pada Baris Faktur out_invoice ---
    def mutate_remove_invoice_line_product():
        AccountMove = env["account.move"].sudo()
        inv1 = AccountMove.search([("ref", "=", "INV-202607-0001")], limit=1)
        inv_lines = [
            ln for ln in (getattr(inv1, "invoice_line_ids", None) or getattr(inv1, "line_ids", []))
            if getattr(ln, "display_type", "product") in ("product", False, None)
        ]
        assert inv_lines, "[mutation_rejection] Baris produk INV-202607-0001 harus tersedia!"
        il0 = inv_lines[0]
        if hasattr(env, "cr") and hasattr(env.cr, "execute"):
            env.cr.execute("UPDATE account_move_line SET product_id = NULL WHERE id = %s", (il0.id,))
            if hasattr(il0, "invalidate_recordset"):
                il0.invalidate_recordset()
            if hasattr(inv1, "invalidate_recordset"):
                inv1.invalidate_recordset()
        else:
            setattr(il0, "product_id", False)
            if hasattr(il0, "_vals"):
                il0._vals["product_id"] = False

    _execute_isolated_mutation(
        mutate_remove_invoice_line_product,
        "Baris invoice INV-202607-0001 kehilangan product_id",
        "Mutation 12 (Penghapusan product_id pada Baris Faktur)",
    )

    # --- Mutasi 13: Lokasi Gudang Salah dalam Company yang Sama (WH Other Business) ---
    def mutate_wrong_warehouse_location_same_company():
        StockLocation = env["stock.location"].sudo()
        StockQuant = env["stock.quant"].sudo()
        sl_fields = getattr(StockLocation, "_fields", {})
        loc_vals = {
            "name": "WH Other Business",
            "usage": "internal",
            "company_id": env.company.id,
        }
        if sl_fields and not isinstance(sl_fields, bool) and hasattr(sl_fields, "__contains__"):
            loc_vals = {k: v for k, v in loc_vals.items() if k in sl_fields}
        other_wh_loc = StockLocation.create(loc_vals)
        wh_loc = getattr(adapter, "wh_stock_loc", None)
        q0 = StockQuant.search([("location_id", "=", wh_loc.id)], limit=1)
        if hasattr(env, "cr") and hasattr(env.cr, "execute"):
            env.cr.execute("UPDATE stock_quant SET location_id = %s WHERE id = %s", (other_wh_loc.id, q0.id))
            if hasattr(q0, "invalidate_recordset"):
                q0.invalidate_recordset()
        else:
            q0.write({"location_id": other_wh_loc})

    _execute_isolated_mutation(
        mutate_wrong_warehouse_location_same_company,
        "lokasi internal tidak sah 'WH Other Business'",
        "Mutation 13 (Lokasi Gudang Salah dalam Company yang Sama)",
    )

    # --- Mutasi 14: Lokasi Milik Company Lain pada StockQuant ---
    def mutate_location_other_company():
        StockLocation = env["stock.location"].sudo()
        StockQuant = env["stock.quant"].sudo()
        if "res.company" in env:
            other_comp = env["res.company"].sudo().create({"name": "PT Luar Seed Temporer"})
        else:
            class _ForeignCo:
                id = 999
                name = "PT Luar Seed Temporer"

            other_comp = _ForeignCo()
        sl_fields = getattr(StockLocation, "_fields", {})
        loc_vals = {
            "name": getattr(adapter.wh_stock_loc, "name", "Stock"),
            "usage": "internal",
            "company_id": other_comp.id,
        }
        if sl_fields and not isinstance(sl_fields, bool) and hasattr(sl_fields, "__contains__"):
            loc_vals = {k: v for k, v in loc_vals.items() if k in sl_fields}
        other_comp_loc = StockLocation.create(loc_vals)
        wh_loc = getattr(adapter, "wh_stock_loc", None)
        q0 = StockQuant.search([("location_id", "=", wh_loc.id)], limit=1)
        if hasattr(env, "cr") and hasattr(env.cr, "execute"):
            env.cr.execute(
                "UPDATE stock_quant SET location_id = %s, company_id = %s WHERE id = %s",
                (other_comp_loc.id, other_comp.id, q0.id),
            )
            if hasattr(q0, "invalidate_recordset"):
                q0.invalidate_recordset()
        else:
            q0.write({"location_id": other_comp_loc, "company_id": other_comp})

    _execute_isolated_mutation(
        mutate_location_other_company,
        "bukan milik company seed",
        "Mutation 14 (Lokasi Milik Company Lain pada StockQuant)",
    )

    # --- Mutasi 15: Tanggal stock.move Saja Bergeser (Tanpa Mengubah stock.move.line.date) ---
    def mutate_stock_move_date_only():
        pick1 = _find_so_picking("SO-202607-0001")
        mv0 = pick1.move_ids[0]
        if hasattr(env, "cr") and hasattr(env.cr, "execute"):
            env.cr.execute("UPDATE stock_move SET date = '2026-10-28 10:00:00' WHERE id = %s", (mv0.id,))
            if hasattr(mv0, "invalidate_recordset"):
                mv0.invalidate_recordset()
        else:
            mv0.write({"date": "2026-10-28 10:00:00"})

    _execute_isolated_mutation(
        mutate_stock_move_date_only,
        "Tanggal stock.move delivery SO-202607-0001 salah! Expected 2026-07-02, got 2026-10-28",
        "Mutation 15 (Pergeseran Tanggal stock.move Saja)",
    )

    # --- Mutasi 16: Tanggal stock.move.line Saja Bergeser (Tanpa Mengubah stock.move.date) ---
    def mutate_stock_move_line_date_only():
        pick1 = _find_so_picking("SO-202607-0001")
        ml0 = pick1.move_line_ids[0]
        if hasattr(env, "cr") and hasattr(env.cr, "execute"):
            env.cr.execute("UPDATE stock_move_line SET date = '2026-10-28 10:00:00' WHERE id = %s", (ml0.id,))
            if hasattr(ml0, "invalidate_recordset"):
                ml0.invalidate_recordset()
        else:
            ml0.write({"date": "2026-10-28 10:00:00"})

    _execute_isolated_mutation(
        mutate_stock_move_line_date_only,
        "Tanggal stock.move.line delivery SO-202607-0001 salah! Expected 2026-07-02, got 2026-10-28",
        "Mutation 16 (Pergeseran Tanggal stock.move.line Saja)",
    )

    # --- Mutasi 17: OPEX Seimbang tetapi Salah Nominal (+Rp 1.000.000) ---
    def mutate_opex_balanced_wrong_amount():
        AccountMove = env["account.move"].sudo()
        opex1 = AccountMove.search([("ref", "=", "OPEX-2026-07-01")], limit=1)
        if hasattr(env, "cr") and hasattr(env.cr, "execute"):
            env.cr.execute(
                "UPDATE account_move SET amount_untaxed = amount_untaxed + 1000000.0, "
                "amount_total = amount_total + 1000000.0 WHERE id = %s",
                (opex1.id,),
            )
            if hasattr(opex1, "invalidate_recordset"):
                opex1.invalidate_recordset()
        else:
            setattr(opex1, "amount_untaxed", float(getattr(opex1, "amount_untaxed", 0.0)) + 1000000.0)
            setattr(opex1, "amount_total", float(getattr(opex1, "amount_total", 0.0)) + 1000000.0)
        for ln in getattr(opex1, "line_ids", []):
            if float(getattr(ln, "debit", 0.0)) > 0:
                if hasattr(env, "cr") and hasattr(env.cr, "execute"):
                    env.cr.execute("UPDATE account_move_line SET debit = debit + 1000000.0 WHERE id = %s", (ln.id,))
                    if hasattr(ln, "invalidate_recordset"):
                        ln.invalidate_recordset()
                else:
                    ln.write({"debit": float(ln.debit) + 1000000.0})
            elif float(getattr(ln, "credit", 0.0)) > 0:
                if hasattr(env, "cr") and hasattr(env.cr, "execute"):
                    env.cr.execute("UPDATE account_move_line SET credit = credit + 1000000.0 WHERE id = %s", (ln.id,))
                    if hasattr(ln, "invalidate_recordset"):
                        ln.invalidate_recordset()
                else:
                    ln.write({"credit": float(ln.credit) + 1000000.0})

    _execute_isolated_mutation(
        mutate_opex_balanced_wrong_amount,
        "Nominal beban OPEX-2026-07-01 salah",
        "Mutation 17 (OPEX Seimbang tetapi Salah Nominal)",
    )

    # --- Mutasi 18: OPEX Salah Akun Beban (610100 -> 610400) ---
    def mutate_opex_wrong_expense_account():
        AccountMove = env["account.move"].sudo()
        opex1 = AccountMove.search([("ref", "=", "OPEX-2026-07-01")], limit=1)
        wrong_acc = getattr(adapter, "opex_accounts", {}).get("Sewa & Utilitas")
        assert wrong_acc, "[mutation_rejection] Akun Sewa & Utilitas (610400) harus tersedia!"
        for ln in getattr(opex1, "line_ids", []):
            if float(getattr(ln, "debit", 0.0)) > 0:
                if hasattr(env, "cr") and hasattr(env.cr, "execute"):
                    env.cr.execute(
                        "UPDATE account_move_line SET account_id = %s WHERE id = %s",
                        (wrong_acc.id, ln.id),
                    )
                    if hasattr(ln, "invalidate_recordset"):
                        ln.invalidate_recordset()
                else:
                    ln.write({"account_id": wrong_acc})

    _execute_isolated_mutation(
        mutate_opex_wrong_expense_account,
        "Akun debit beban OPEX-2026-07-01 salah",
        "Mutation 18 (OPEX Salah Akun Beban)",
    )

    # --- Mutasi 19: Duplikasi Dokumen PurchaseOrder dengan origin Sama ---
    def mutate_duplicate_po():
        PurchaseOrder = env["purchase.order"].sudo()
        po1 = PurchaseOrder.search([("origin", "=", "PO-2026-06-01")], limit=1)
        po_fields = getattr(PurchaseOrder, "_fields", {})
        dup_vals = {
            "origin": "PO-2026-06-01",
            "partner_id": getattr(getattr(po1, "partner_id", None), "id", po1.partner_id),
            "company_id": env.company.id,
        }
        if po_fields and not isinstance(po_fields, bool) and hasattr(po_fields, "__contains__"):
            dup_vals = {k: v for k, v in dup_vals.items() if k in po_fields}
        PurchaseOrder.create(dup_vals)

    _execute_isolated_mutation(
        mutate_duplicate_po,
        "Duplikasi PurchaseOrder",
        "Mutation 19 (Duplikasi PurchaseOrder)",
    )

    # --- Mutasi 20: Duplikasi Dokumen SaleOrder dengan client_order_ref Sama ---
    def mutate_duplicate_so():
        SaleOrder = env["sale.order"].sudo()
        so1 = SaleOrder.search([("client_order_ref", "=", "SO-202607-0001")], limit=1)
        so_fields = getattr(SaleOrder, "_fields", {})
        dup_vals = {
            "client_order_ref": "SO-202607-0001",
            "partner_id": getattr(getattr(so1, "partner_id", None), "id", so1.partner_id),
            "company_id": env.company.id,
        }
        if so_fields and not isinstance(so_fields, bool) and hasattr(so_fields, "__contains__"):
            dup_vals = {k: v for k, v in dup_vals.items() if k in so_fields}
        SaleOrder.create(dup_vals)

    _execute_isolated_mutation(
        mutate_duplicate_so,
        "Duplikasi SaleOrder",
        "Mutation 20 (Duplikasi SaleOrder)",
    )

    print("\n" + "=" * 80)
    print("[mutation_rejection] SELURUH 20 UJI MUTASI NEGATIF BERHASIL DITOLAK (ORACLE TERBUKTI AKTIF & TERISOLASI)")
    print("=" * 80)


def verify_native_cogs_and_seed_suppression_real_orm(env):
    """Review 6473770755 Finding 3: Membuktikan supresi seed vs native COGS pada real ORM Odoo 19."""
    print("\n" + "=" * 80)
    print("[real_orm_cogs] MEMULAI VERIFIKASI SUPRESI SEED VS NATIVE COGS PADA REAL ODOO ORM")
    print("=" * 80)
    AccountMove = env["account.move"].sudo()

    # 1. Verifikasi faktur seed nyata dari slice (INV-202607-0001)
    seed_inv = AccountMove.search([("ref", "=", "INV-202607-0001")], limit=1)
    if not seed_inv:
        print(" -> [real_orm_cogs] SKIP: Faktur INV-202607-0001 tidak ditemukan.")
        return

    fn = getattr(seed_inv, "_is_seed_commercial_invoice_with_posted_delivery_cogs", None)
    if not callable(fn):
        print(" -> [real_orm_cogs] SKIP: Bukan real Odoo ORM (metode hook id_base tidak terikat pada record).")
        return
    assert seed_inv, "[real_orm_cogs] Faktur seed INV-202607-0001 wajib ada di database!"
    assert seed_inv.is_fmcg_seed_invoice, "[real_orm_cogs] is_fmcg_seed_invoice wajib True pada INV-202607-0001!"
    assert seed_inv.fmcg_seed_batch == "CANONICAL_JULY_2026_PERPETUAL", (
        "[real_orm_cogs] fmcg_seed_batch wajib terisi eksak 'CANONICAL_JULY_2026_PERPETUAL'!"
    )
    assert seed_inv._is_seed_commercial_invoice_with_posted_delivery_cogs() is True, (
        "[real_orm_cogs] Predikat seed wajib True untuk INV-202607-0001!"
    )

    # Panggil langsung hook COGS pada faktur seed murni -> wajib mengembalikan [] (supresi duplikasi)
    seed_cogs = seed_inv._stock_account_prepare_realtime_out_lines_vals()
    assert seed_cogs == [], f"[real_orm_cogs] Faktur seed wajib mengembalikan [] tapi dapat {seed_cogs}!"
    print(" -> [Seed Invoice INV-202607-0001]: Supresi HPP duplikat terbukti 100% (mengembalikan []).")

    # 2. Uji faktur non-seed dan mixed recordset dalam boundary terisolasi
    class InjectedSavepointRollback(Exception):
        pass

    orig_val = None
    created_records = []
    try:
        so1 = env["sale.order"].sudo().search([("client_order_ref", "=", "SO-202607-0001")], limit=1)
        assert so1 and so1.order_line, "[real_orm_cogs] SO-202607-0001 dan order_line wajib ada!"
        sol = so1.order_line[0]
        prod = sol.product_id

        # Pastikan category produk menggunakan automated valuation dan simpan nilai asli untuk pemulihan fixture
        orig_val = None
        orig_price = None
        if hasattr(prod.categ_id, "property_valuation"):
            orig_val = prod.categ_id.property_valuation
            prod.categ_id.property_valuation = "real_time"
        if hasattr(prod, "standard_price"):
            orig_price = prod.standard_price
            if not prod.standard_price:
                prod.standard_price = sol.price_unit or 25000.0

        ord_inv_vals = {
            "move_type": "out_invoice",
            "partner_id": so1.partner_id.id,
            "invoice_date": "2026-07-20",
            "date": "2026-07-20",
            "is_fmcg_seed_invoice": False,
            "fmcg_seed_batch": False,
            "invoice_line_ids": [
                (0, 0, {
                    "product_id": prod.id,
                    "quantity": sol.product_uom_qty or 1.0,
                    "price_unit": sol.price_unit,
                    "sale_line_ids": [(6, 0, [sol.id])],
                })
            ],
        }
        ord_inv = AccountMove.create(ord_inv_vals)
        created_records.append(ord_inv)

        assert ord_inv.is_fmcg_seed_invoice is False
        assert ord_inv._is_seed_commercial_invoice_with_posted_delivery_cogs() is False, (
            "[real_orm_cogs] Faktur ordinary dilarang dianggap seed!"
        )

        # 3. Panggil hook COGS pada faktur ordinary -> parent native dipanggil
        ord_cogs = ord_inv._stock_account_prepare_realtime_out_lines_vals()
        print(
            f" -> [Ordinary Non-Seed Invoice]: Panggilan native berhasil (tipe: {type(ord_cogs)}, "
            f"jumlah: {len(ord_cogs)} baris)."
        )
        assert isinstance(ord_cogs, list) and len(ord_cogs) >= 2, (
            f"[real_orm_cogs] Native COGS harus menghasilkan minimal 2 baris (debit & credit), got: {ord_cogs}"
        )
        total_debit = sum(
            float(ln.get("debit") or (ln.get("balance") if (ln.get("balance") or 0.0) > 0 else 0.0) or 0.0)
            for ln in ord_cogs
        )
        total_credit = sum(
            float(ln.get("credit") or (-ln.get("balance") if (ln.get("balance") or 0.0) < 0 else 0.0) or 0.0)
            for ln in ord_cogs
        )
        total_amount = total_debit or sum(
            abs(float(ln.get("balance") or ln.get("price_unit") or 0.0)) for ln in ord_cogs
        )
        assert total_amount > 0.0, f"[real_orm_cogs] Nilai baris COGS native harus > 0, got {ord_cogs}"
        if total_debit > 0.0 and total_credit > 0.0:
            assert abs(total_debit - total_credit) < 0.01, (
                f"[real_orm_cogs] Debit ({total_debit}) != Credit ({total_credit}) pada COGS native!"
            )
        for l_val in ord_cogs:
            assert l_val.get("account_id"), f"[real_orm_cogs] Baris COGS native wajib memiliki account_id: {l_val}"
            assert l_val.get("product_id") == prod.id, (
                f"[real_orm_cogs] Baris COGS native harus terikat produk {prod.id}, got: {l_val.get('product_id')}"
            )
            if l_val.get("company_id") is not None:
                assert l_val.get("company_id") == ord_inv.company_id.id, (
                    f"[real_orm_cogs] Baris COGS native harus terikat company {ord_inv.company_id.id}, "
                    f"got: {l_val.get('company_id')}"
                )

        # 4. Mixed Recordset (seed | ordinary)
        mixed = seed_inv | ord_inv
        mixed_cogs = mixed._stock_account_prepare_realtime_out_lines_vals()
        assert mixed_cogs == ord_cogs, (
            f"[real_orm_cogs] Mixed recordset harus tepat menghasilkan baris non-seed! "
            f"(got {len(mixed_cogs)} vs {len(ord_cogs)})"
        )
        assert len(mixed_cogs) == len(ord_cogs), (
            f"[real_orm_cogs] Jumlah baris mixed ({len(mixed_cogs)}) != ordinary ({len(ord_cogs)})"
        )
        print(" -> [Mixed Recordset (Seed | Non-Seed)]: Supresi selektif terbukti (hanya seed yang disupresi).")

        # 5. Vendor Bill & Customer Refund Nyata (dengan invoice_line_ids produk)
        bill = AccountMove.create({
            "move_type": "in_invoice",
            "partner_id": so1.partner_id.id,
            "invoice_date": "2026-07-20",
            "date": "2026-07-20",
            "is_fmcg_seed_invoice": True,
            "fmcg_seed_batch": "CANONICAL_JULY_2026_PERPETUAL",
            "invoice_line_ids": [
                (0, 0, {
                    "product_id": prod.id,
                    "quantity": 1.0,
                    "price_unit": sol.price_unit,
                })
            ],
        })
        created_records.append(bill)
        assert bill._is_seed_commercial_invoice_with_posted_delivery_cogs() is False, (
            "[real_orm_cogs] Vendor Bill dilarang disupresi oleh hook seed!"
        )

        refund = AccountMove.create({
            "move_type": "out_refund",
            "partner_id": so1.partner_id.id,
            "invoice_date": "2026-07-20",
            "date": "2026-07-20",
            "is_fmcg_seed_invoice": True,
            "fmcg_seed_batch": "CANONICAL_JULY_2026_PERPETUAL",
            "invoice_line_ids": [
                (0, 0, {
                    "product_id": prod.id,
                    "quantity": 1.0,
                    "price_unit": sol.price_unit,
                })
            ],
        })
        created_records.append(refund)
        assert refund._is_seed_commercial_invoice_with_posted_delivery_cogs() is False, (
            "[real_orm_cogs] Customer Refund dilarang disupresi oleh hook seed!"
        )
        refund_cogs = refund._stock_account_prepare_realtime_out_lines_vals()
        print(
            f" -> [Real Customer Refund & Vendor Bill]: Kebal dari supresi seed terbukti "
            f"(Refund cogs: {type(refund_cogs)})."
        )

        # 6. Verifikasi posting native dalam savepoint terisolasi
        if hasattr(env, "cr") and hasattr(env.cr, "savepoint"):
            try:
                with env.cr.savepoint():
                    if hasattr(ord_inv, "action_post"):
                        ord_inv.action_post()
                        assert ord_inv.state == "posted", "[real_orm_cogs] Ord invoice gagal action_post!"
                    raise InjectedSavepointRollback("Savepoint isolation unwind")
            except InjectedSavepointRollback:
                pass
    finally:
        for rec in created_records:
            if hasattr(rec, "exists") and rec.exists():
                try:
                    rec.unlink()
                except Exception:
                    pass
        if orig_val is not None and hasattr(prod.categ_id, "property_valuation"):
            prod.categ_id.property_valuation = orig_val
        if orig_price is not None and hasattr(prod, "standard_price"):
            prod.standard_price = orig_price
        if hasattr(env, "invalidate_all"):
            env.invalidate_all()

    print("=" * 80)
    print("[real_orm_cogs] VERIFIKASI SUPRESI SEED VS NATIVE COGS SELESAI (SUKSES 100%)")
    print("=" * 80)


def verify_real_database_transaction_rollback(env, reg_path):
    """Review 6473770755 Finding 4: Membuktikan rollback nyata pada PostgreSQL database level."""
    has_cr = hasattr(env, "cr") and hasattr(env.cr, "savepoint")
    if not has_cr:
        print(" -> [real_db_rollback] SKIP: Bukan database cursor PostgreSQL nyata (savepoint tidak tersedia).")
        return

    print("\n" + "=" * 80)
    print("[real_db_rollback] MEMULAI VERIFIKASI ROLLBACK TRANSAKSI DATABASE NYATA")
    print("=" * 80)

    PurchaseOrder = env["purchase.order"].sudo()
    Partner = env["res.partner"].sudo()

    initial_po_count = len(PurchaseOrder.search([]))
    target_partner = Partner.search([], limit=1)
    assert target_partner, "[real_db_rollback] Partner awal wajib ada di database!"
    orig_partner_name = target_partner.name

    # 1. Uji rollback savepoint database nyata: mutasi record existing + create record baru
    class InjectedDatabaseFailure(Exception):
        pass

    try:
        with env.cr.savepoint():
            # Mutasi in-place pada record existing di database
            target_partner.write({"name": "MUTATED_PARTNER_NAME_FOR_ROLLBACK_TEST"})
            assert target_partner.name == "MUTATED_PARTNER_NAME_FOR_ROLLBACK_TEST"

            # Create record baru di database
            leaked_po = PurchaseOrder.create({
                "origin": "PO-TEST-ROLLBACK-LEAK",
                "partner_id": target_partner.id,
                "company_id": env.company.id,
            })
            assert leaked_po.id
            assert len(PurchaseOrder.search([("origin", "=", "PO-TEST-ROLLBACK-LEAK")])) == 1

            # Injeksi kegagalan transaksi
            raise InjectedDatabaseFailure("Kegagalan yang memicu ROLLBACK PostgreSQL nyata!")
    except InjectedDatabaseFailure:
        pass

    # Invalidate cache ORM agar membaca ulang data dari disk PostgreSQL
    if hasattr(env, "invalidate_all"):
        env.invalidate_all()

    # 2. Verifikasi readback dari PostgreSQL:
    # a. Mutasi dibatalkan
    re_read_partner = Partner.browse(target_partner.id)
    assert re_read_partner.name == orig_partner_name, (
        f"[real_db_rollback] Mutasi partner bocor! Expected '{orig_partner_name}', got '{re_read_partner.name}'"
    )

    # b. Record baru tidak pernah ter-commit
    leaked_count = len(PurchaseOrder.search([("origin", "=", "PO-TEST-ROLLBACK-LEAK")]))
    assert leaked_count == 0, f"[real_db_rollback] Record PO bocor di database nyata! ({leaked_count} record)"

    # c. Total count tabel tetap utuh
    final_po_count = len(PurchaseOrder.search([]))
    assert final_po_count == initial_po_count, (
        f"[real_db_rollback] Total PO berubah! Expected {initial_po_count}, got {final_po_count}"
    )

    print(" -> [Database Savepoint Rollback]: Invalidation cache & PostgreSQL rollback 100% bersih.")
    print(" -> [Zero Leak Verification]: Record existing pulih, record baru 0, count tabel konsisten.")
    print("=" * 80)
    print("[real_db_rollback] VERIFIKASI ROLLBACK DATABASE POSTGRESQL SUKSES 100%")
    print("=" * 80)

    # 3. Verifikasi rollback transaksi pada loader boundary CanonicalPerpetualAdapter.run_all()
    verify_loader_boundary_transaction_rollback(env, reg_path)


def verify_loader_boundary_transaction_rollback(env, reg_path):
    """Review 6483144753 Finding 4: Membuktikan rollback transaksi pada loader boundary CanonicalPerpetualAdapter.run_all()."""
    has_cr = hasattr(env, "cr") and hasattr(env.cr, "rollback") and hasattr(env.cr, "commit")
    if not has_cr:
        print(" -> [loader_rollback] SKIP: Bukan database cursor PostgreSQL nyata.")
        return

    print("\n" + "=" * 80)
    print("[loader_rollback] MEMULAI VERIFIKASI ROLLBACK TRANSAKSI LOADER BOUNDARY")
    print("=" * 80)

    class InjectedLoaderFailure(Exception):
        pass

    pre_snap = _capture_deep_snapshot(env)

    adapter = CanonicalPerpetualAdapter(env, reg_path=reg_path)

    orig_commit = env.cr.commit
    orig_rollback = env.cr.rollback
    commit_called = []
    rollback_called = []

    def spy_commit(*args, **kwargs):
        commit_called.append(True)
        return orig_commit(*args, **kwargs)

    def spy_rollback(*args, **kwargs):
        rollback_called.append(True)
        return orig_rollback(*args, **kwargs)

    env.cr.commit = spy_commit
    env.cr.rollback = spy_rollback

    partial_ids = {}
    orig_run_step = adapter.load_rejections_quarantine

    def failing_step(*args, **kwargs):
        prod = env["product.product"].sudo().search([], limit=1)
        wh_loc = env.ref("stock.stock_location_stock", raise_if_not_found=False)
        if not wh_loc:
            wh_loc = env["stock.location"].sudo().search([("usage", "=", "internal")], limit=1)

        quant = env["stock.quant"].sudo().create({
            "product_id": prod.id,
            "location_id": wh_loc.id,
            "quantity": 888.0,
            "inventory_quantity": 888.0,
        })
        partial_ids["quant_id"] = quant.id

        partner = env["res.partner"].sudo().search([], limit=1)
        po = env["purchase.order"].sudo().create({
            "origin": "PO-FAIL-INJECTED-TEST",
            "partner_id": partner.id,
            "company_id": env.company.id,
        })
        partial_ids["po_id"] = po.id

        picking_type = env["stock.picking.type"].sudo().search([("code", "=", "incoming")], limit=1)
        supp_loc = env.ref("stock.stock_location_suppliers", raise_if_not_found=False)
        if not supp_loc:
            supp_loc = env["stock.location"].sudo().search([("usage", "=", "supplier")], limit=1)

        picking = env["stock.picking"].sudo().create({
            "picking_type_id": picking_type.id if picking_type else False,
            "location_id": supp_loc.id if supp_loc else wh_loc.id,
            "location_dest_id": wh_loc.id,
            "origin": "PICK-FAIL-INJECTED-TEST",
        })
        partial_ids["picking_id"] = picking.id

        journal = env["account.journal"].sudo().search([("type", "=", "general")], limit=1)
        acc_debit = env["account.account"].sudo().search([("code", "=", "510000")], limit=1)
        acc_credit = env["account.account"].sudo().search([("code", "=", "113000")], limit=1)
        if not acc_debit or not acc_credit:
            acc_debit = env["account.account"].sudo().search([], limit=1)
            acc_credit = acc_debit

        am = env["account.move"].sudo().create({
            "journal_id": journal.id if journal else False,
            "date": "2026-07-28",
            "ref": "FAIL-AML-INJECTED-TEST",
            "line_ids": [
                (0, 0, {
                    "name": "Partial debit write",
                    "account_id": acc_debit.id,
                    "debit": 555000.0,
                    "credit": 0.0,
                }),
                (0, 0, {
                    "name": "Partial credit write",
                    "account_id": acc_credit.id,
                    "debit": 0.0,
                    "credit": 555000.0,
                }),
            ],
        })
        partial_ids["am_id"] = am.id
        partial_ids["aml_ids"] = am.line_ids.ids

        assert env["stock.quant"].sudo().search([("id", "=", quant.id)]), "Quant harus ada dalam transaksi aktif!"
        assert env["purchase.order"].sudo().search([("id", "=", po.id)]), "PO harus ada dalam transaksi aktif!"
        assert env["stock.picking"].sudo().search([("id", "=", picking.id)]), "Picking harus ada dalam transaksi aktif!"
        assert env["account.move"].sudo().search([("id", "=", am.id)]), "AccountMove harus ada dalam transaksi aktif!"
        assert len(am.line_ids) >= 2, "AML harus ada dalam transaksi aktif!"

        raise InjectedLoaderFailure("Simulated unhandled exception during loader execution after partial writes")

    adapter.load_rejections_quarantine = failing_step

    error_caught = False
    try:
        adapter.run_all(target_so_numbers=["SO-202607-0001"])
    except InjectedLoaderFailure:
        error_caught = True
    finally:
        adapter.load_rejections_quarantine = orig_run_step
        env.cr.commit = orig_commit
        env.cr.rollback = orig_rollback

    assert error_caught, "[loader_rollback] InjectedLoaderFailure wajib dilempar oleh adapter.run_all()!"

    assert len(commit_called) == 0, (
        f"[loader_rollback] Loader transaction DILARANG commit saat error! (commit_called: {commit_called})"
    )
    assert len(rollback_called) >= 1, (
        "[loader_rollback] CanonicalPerpetualAdapter.run_all() WAJIB memanggil self.cr.rollback() saat error!"
    )
    print(" -> [Loader Transaction Boundary]: cr.commit() tidak dipanggil, self.cr.rollback() terbukti dipanggil.")

    if hasattr(env, "invalidate_all"):
        env.invalidate_all()

    if "quant_id" in partial_ids:
        q_cnt = env["stock.quant"].sudo().search_count([("id", "=", partial_ids["quant_id"])])
        assert q_cnt == 0, f"[loader_rollback] Partial stock.quant bocor di database! (count: {q_cnt})"

    if "po_id" in partial_ids:
        po_cnt = env["purchase.order"].sudo().search_count([("id", "=", partial_ids["po_id"])])
        assert po_cnt == 0, f"[loader_rollback] Partial purchase.order bocor di database! (count: {po_cnt})"

    if "picking_id" in partial_ids:
        pk_cnt = env["stock.picking"].sudo().search_count([("id", "=", partial_ids["picking_id"])])
        assert pk_cnt == 0, f"[loader_rollback] Partial stock.picking bocor di database! (count: {pk_cnt})"

    if "am_id" in partial_ids:
        am_cnt = env["account.move"].sudo().search_count([("id", "=", partial_ids["am_id"])])
        assert am_cnt == 0, f"[loader_rollback] Partial account.move bocor di database! (count: {am_cnt})"

    if "aml_ids" in partial_ids:
        aml_cnt = env["account.move.line"].sudo().search_count([("id", "in", partial_ids["aml_ids"])])
        assert aml_cnt == 0, f"[loader_rollback] Partial account.move.line bocor di database! (count: {aml_cnt})"

    print(" -> [Zero Record Leakage Across Models]: stock.quant, documents, dan AML 100% ter-rollback.")

    post_snap = _capture_deep_snapshot(env)
    assert pre_snap["quants"] == post_snap["quants"], "Drift quants setelah loader rollback!"
    assert pre_snap["moves"] == post_snap["moves"], "Drift moves setelah loader rollback!"
    assert pre_snap["move_lines"] == post_snap["move_lines"], "Drift move_lines setelah loader rollback!"
    assert pre_snap["account_moves"] == post_snap["account_moves"], "Drift account_moves setelah loader rollback!"
    assert pre_snap["aml_records"] == post_snap["aml_records"], "Drift aml_records setelah loader rollback!"
    assert pre_snap["gl_by_acc"] == post_snap["gl_by_acc"], "Drift gl_by_acc setelah loader rollback!"

    print(" -> [Deep Snapshot Identity]: pre_snap == post_snap 100% identik tanpa perubahan!")
    print("=" * 80)
    print("[loader_rollback] VERIFIKASI ROLLBACK TRANSAKSI LOADER BOUNDARY SUKSES 100%")
    print("=" * 80)


def _capture_deep_snapshot(env):
    """Merekam snapshot mendalam untuk komparasi idempotensi Run 1 vs Run 2."""
    StockQuant = env["stock.quant"].sudo() if "stock.quant" in env else None
    StockMove = env["stock.move"].sudo() if "stock.move" in env else None
    StockMoveLine = env["stock.move.line"].sudo() if "stock.move.line" in env else None
    AccountMove = env["account.move"].sudo() if "account.move" in env else None
    AccountMoveLine = env["account.move.line"].sudo() if "account.move.line" in env else None

    quants = {}
    stock_totals = {}
    if StockQuant is not None:
        for q in (StockQuant.search([]) or []):
            sku = _resolve_ml_sku(env, q)
            loc_rec = _resolve_loc(env, getattr(q, "location_id", None))
            loc_name = getattr(loc_rec, "name", getattr(q, "location_id", None))
            lot_name = _resolve_ml_lot_name(env, q)
            qty = float(getattr(q, "quantity", 0.0))
            res_qty = float(getattr(q, "reserved_quantity", 0.0) or 0.0)
            quants[q.id] = {
                "product_code": sku,
                "location_name": loc_name,
                "lot_name": lot_name,
                "quantity": qty,
                "reserved_quantity": res_qty,
            }
            key = (sku, loc_name, lot_name)
            stock_totals[key] = stock_totals.get(key, 0.0) + qty

    moves = {}
    if StockMove is not None:
        for mv in (StockMove.search([]) or []):
            am_id = getattr(getattr(mv, "account_move_id", None), "id", getattr(mv, "account_move_id", False))
            moves[mv.id] = {
                "sku": _resolve_ml_sku(env, mv),
                "origin": getattr(mv, "origin", ""),
                "state": getattr(mv, "state", ""),
                "date": str(getattr(mv, "date", ""))[:10],
                "account_move_id": am_id,
            }

    move_lines = {}
    if StockMoveLine is not None:
        for ml in (StockMoveLine.search([]) or []):
            move_lines[ml.id] = {
                "sku": _resolve_ml_sku(env, ml),
                "lot": _resolve_ml_lot_name(env, ml),
                "qty": float(getattr(ml, "quantity", getattr(ml, "qty_done", 0.0))),
                "date": str(getattr(ml, "date", ""))[:10],
            }

    account_moves = {}
    if AccountMove is not None:
        for am in (AccountMove.search([]) or []):
            account_moves[am.id] = {
                "ref": getattr(am, "ref", ""),
                "state": getattr(am, "state", ""),
                "date": str(getattr(am, "date", ""))[:10],
                "move_type": getattr(am, "move_type", ""),
            }

    aml_records = {}
    gl_by_acc = {}
    if AccountMoveLine is not None:
        for ln in (AccountMoveLine.search([]) or []):
            acc = getattr(ln, "account_id", None)
            acc_code = getattr(acc, "code", getattr(acc, "id", None))
            d = float(getattr(ln, "debit", 0.0))
            c = float(getattr(ln, "credit", 0.0))
            aml_records[ln.id] = {
                "account_code": acc_code,
                "debit": round(d, 2),
                "credit": round(c, 2),
                "date": str(getattr(ln, "date", ""))[:10],
                "move_id": getattr(getattr(ln, "move_id", None), "id", getattr(ln, "move_id", False)),
            }
            gl_by_acc.setdefault(acc_code, {"debit": 0.0, "credit": 0.0})
            gl_by_acc[acc_code]["debit"] += d
            gl_by_acc[acc_code]["credit"] += c

    return {
        "quants": quants,
        "stock_totals": stock_totals,
        "moves": moves,
        "move_lines": move_lines,
        "account_moves": account_moves,
        "aml_records": aml_records,
        "gl_by_acc": gl_by_acc,
    }


def run_representative_slice(env):
    """Menjalankan dan memverifikasi slice representatif pada Odoo disposable DB."""
    introspect_odoo19_schema(env)

    target_so_slice = ["SO-202607-0001", "SO-202607-0063", "SO-202607-0317"]
    print(f"\n[disposable_slice] MENJALANKAN SLICE TRANSAKSI REPRESENTATIF (RUN 1): {target_so_slice}...")
    adapter = CanonicalPerpetualAdapter(env, reg_path=REG_PATH)

    adapter.run_all(target_so_numbers=target_so_slice)

    print("[disposable_slice] RUN 1 SELESAI. Mengeksekusi verifikasi Oracle Kanonikal...")
    verify_run1_against_canonical_oracle(env, adapter, REG_PATH, target_so_slice)

    verify_slice_mutation_rejection(env, adapter, REG_PATH, target_so_slice=target_so_slice)

    verify_native_cogs_and_seed_suppression_real_orm(env)
    verify_real_database_transaction_rollback(env, REG_PATH)

    snap1 = _capture_deep_snapshot(env)
    print(
        f"[disposable_slice] Deep Snapshot Run 1: "
        f"{len(snap1['quants'])} quants, {len(snap1['moves'])} stock.moves, "
        f"{len(snap1['move_lines'])} move.lines, {len(snap1['account_moves'])} account.moves, "
        f"{len(snap1['aml_records'])} AMLs."
    )

    print("\n[disposable_slice] MENJALANKAN UJI IDEMPOTENSI SEJATI (RUN 2)...")
    adapter_run2 = CanonicalPerpetualAdapter(env, reg_path=REG_PATH)
    adapter_run2.run_all(target_so_numbers=target_so_slice)

    print("[disposable_slice] RUN 2 SUKSES. Memeriksa counter create & deep snapshots...")
    assert adapter_run2.stats["opening_quants"] == 0, "Opening quants tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["so_created"] == 0, "SO tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["po_created"] == 0, "PO tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["ar_payments_created"] == 0, "Payment AR tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["ap_payments_created"] == 0, "Payment AP tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["discount_moves_created"] == 0, "Jurnal diskon tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["quarantine_rejections"] == 0, "Karantina tidak boleh dibuat ulang pada run 2!"

    snap2 = _capture_deep_snapshot(env)

    assert snap1["quants"] == snap2["quants"], "Drift terdeteksi pada stock.quant (ID, qty, atau reserved_quantity)!"
    assert snap1["moves"] == snap2["moves"], "Drift terdeteksi pada stock.move (ID, tanggal, atau relasi jurnal)!"
    assert snap1["move_lines"] == snap2["move_lines"], "Drift terdeteksi pada stock.move.line!"
    assert snap1["account_moves"] == snap2["account_moves"], "Drift terdeteksi pada account.move!"
    assert snap1["aml_records"] == snap2["aml_records"], "Drift terdeteksi pada account.move.line!"

    for acc_code, b1 in snap1["gl_by_acc"].items():
        b2 = snap2["gl_by_acc"].get(acc_code, {"debit": 0.0, "credit": 0.0})
        assert abs(b1["debit"] - b2["debit"]) < 0.01, f"Drift GL Debit pada akun {acc_code}!"
        assert abs(b1["credit"] - b2["credit"]) < 0.01, f"Drift GL Credit pada akun {acc_code}!"

    verify_run1_against_canonical_oracle(env, adapter_run2, REG_PATH, target_so_slice)

    print("=" * 80)
    print("[disposable_slice] VERIFIKASI RUNTIME ODOO DISPOSABLE SUKSES 100%!")
    print("  - Schema Introspection: PASSED")
    print(f"  - Representative Slice Run 1 ({target_so_slice}): PASSED")
    print("  - Canonical CSV Exact-Set & Valuation Oracle Verification: PASSED")
    print("  - Multi-Lot Split SO-202607-0317 (120 + 96 = 216 unit): PASSED")
    print("  - Negative Mutation Rejection (11 Active Fault Detection Tests): PASSED")
    print("  - Retur Karantina Customer -> Quarantine: PASSED")
    print("  - Deep Readback (Exact Discount Ref, Move IDs, Residuals, Native Valuation): PASSED")
    print("  - True Idempotency Rerun 2 (0 created, 100% skipped): PASSED")
    print("  - Zero Stock & Reserved Drift (Run 1 == Run 2): PASSED")
    print("  - Zero GL & Journal Relation Drift (Run 1 == Run 2): PASSED")
    print("  - Real ORM Native COGS vs Seed Suppression (Realtime Out Lines): PASSED")
    print("  - Real Database Transaction Rollback & Zero Leakage: PASSED")
    print("=" * 80)


if __name__ == "__main__" or "env" in globals():
    env_obj = globals().get("env")
    if env_obj:
        run_representative_slice(env_obj)
    else:
        print("[disposable_slice] Skrip ini dirancang untuk dijalankan di dalam Odoo shell.")
        print("Penggunaan: odoo shell -c /tmp/odoo.conf -d fmcg --no-http < scripts/ops/verify_disposable_slice.py")
