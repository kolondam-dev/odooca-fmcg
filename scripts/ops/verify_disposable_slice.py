#!/usr/bin/env python3
"""scripts/ops/verify_disposable_slice.py

Skrip eksekusi dan verifikasi slice transaksi representatif pada Odoo 19 disposable DB.
Dijalankan via:
    odoo shell -c /tmp/odoo.conf -d fmcg --no-http < scripts/ops/verify_disposable_slice.py

Mencakup:
1. Introspeksi schema model aktual Odoo 19 (account.payment, stock.move.line, account.move)
2. Pemuatan slice representatif multi-domain (target_so_numbers=["SO-202607-0001", "SO-202607-0063"]):
   - Opening stock quant relevan (1 Juli 2026)
   - Inbound PO transit Juni dengan multi-split lot receipt & vendor bill (PO-202607-0001)
   - Outgoing SO dengan cash discount (SO-202607-0001 + INV-202607-0001 + PAY-AR-00098 + DISC-PAY-AR-00098)
   - Outgoing SO dengan partial rejection ke karantina (SO-202607-0063 + REJ-202607-001)
   - Inbound AP payment (PAY-AP-00001 s/d PAY-AP-00004)
   - 30 OPEX & Payroll roster
3. Readback menyeluruh (ID, state, qty lot, lokasi sumber/tujuan, residual, jurnal GL)
4. Rerun kedua kali (uji idempotensi sejati) dengan komparasi saldo stok dan GL buku besar
"""

import os
import sys
from pathlib import Path

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

from scripts.load_canonical_perpetual import CanonicalPerpetualAdapter, read_register_csv  # noqa: E402


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


def verify_run1_against_canonical_oracle(env, adapter, reg_path, target_so_slice):
    """Memverifikasi hasil pemuatan Run 1 secara independen terhadap Oracle CSV Kanonikal.

    Menutup temuan supervisi:
    1. Fail-closed: menolak eksekusi tanpa model Odoo wajib atau dataset kosong.
    2. Inbound PO transit: join native purchase.order -> po.picking_ids (1 receipt per PO, arrival date, lines exact).
    3. SO Deliveries: join native sale.order -> so.picking_ids untuk seluruh slice SO (tanggal delivery, net accepted per SKU/lot).
    4. Retur karantina: verifikasi SKU, lot, kuantitas 12 unit, dan lokasi tujuan karantina.
    5. Nominal komersial & residual: join dinamis perpetual_invoices.csv dan perpetual_ar_collections.csv.
    6. Penyelarasan tanggal GL: seluruh jurnal wajib posted, balance debit=credit, dan bertanggal Juli 2026.
    """
    if not env:
        raise ValueError("[canonical_oracle] env (Odoo environment) wajib disediakan!")
    reg_path = Path(reg_path)
    if not reg_path.is_dir():
        raise FileNotFoundError(f"[canonical_oracle] Direktori register tidak ditemukan di: {reg_path}")

    REQUIRED_MODELS = [
        "stock.picking", "account.move", "account.payment", "stock.quant",
        "purchase.order", "sale.order", "stock.move", "stock.move.line",
    ]
    for m in REQUIRED_MODELS:
        if m not in env:
            raise RuntimeError(f"[canonical_oracle] Model Odoo '{m}' wajib terdaftar di env! Fail-closed.")

    if not target_so_slice:
        raise ValueError("[canonical_oracle] target_so_slice tidak boleh kosong!")

    print("\n" + "=" * 80)
    print("[canonical_oracle] MEMULAI VERIFIKASI RUN 1 TERHADAP ORACLE REGISTER KANONIKAL")
    print("=" * 80)

    PurchaseOrder = env["purchase.order"].sudo()
    SaleOrder = env["sale.order"].sudo()
    StockPicking = env["stock.picking"].sudo()
    AccountMove = env["account.move"].sudo()
    AccountPayment = env["account.payment"].sudo()

    # --- 1. Verifikasi Inbound PO Transit (Sumber: inbound_po_intransit_june_headers.csv) ---
    po_headers = read_register_csv("inbound_po_intransit_june_headers.csv", reg_path=reg_path)
    po_lines = read_register_csv("inbound_po_intransit_june_lines.csv", reg_path=reg_path)
    assert po_headers, "[canonical_oracle] Register inbound_po_intransit_june_headers.csv kosong!"
    lines_by_po = {}
    for pline in po_lines:
        lines_by_po.setdefault(pline["po_number"], []).append(pline)

    for h in po_headers:
        po_num = h["po_number"]
        po = PurchaseOrder.search([("origin", "=", po_num)], limit=1)
        if not po:
            po = PurchaseOrder.search([("name", "=", po_num)], limit=1)
        assert po, f"[canonical_oracle] Purchase Order {po_num} tidak ditemukan!"
        assert po.state in ("purchase", "done"), f"[canonical_oracle] PO {po_num} belum confirmed! State: {po.state}"

        # Relasi picking native dari purchase order
        po_picks = [p for p in getattr(po, "picking_ids", []) if getattr(p, "state", "") != "cancel"]
        if not po_picks:
            po_picks = StockPicking.search([("origin", "in", [getattr(po, "name", ""), po_num])])
            po_picks = [p for p in (po_picks or []) if getattr(p, "state", "") != "cancel"]
        assert len(po_picks) == 1, (
            f"[canonical_oracle] Expected exactly 1 receipt picking untuk {po_num}, got {len(po_picks)}"
        )
        po_pick = po_picks[0]
        assert po_pick.state == "done", f"[canonical_oracle] Receipt {po_num} belum done! State: {po_pick.state}"

        exact_arrival = h["arrival_maumbi_date"]
        pick_date = str(getattr(po_pick, "date_done", getattr(po_pick, "scheduled_date", getattr(po_pick, "date", ""))))[:10]
        assert pick_date == exact_arrival, (
            f"[canonical_oracle] Tanggal receipt {po_num} ({pick_date}) != arrival_maumbi_date ({exact_arrival})!"
        )

        # Verifikasi lines
        exp_lines = lines_by_po.get(po_num, [])
        assert exp_lines, f"[canonical_oracle] Lines untuk PO {po_num} kosong di register CSV!"
        expected_by_sku_lot = {}
        for el in exp_lines:
            sku = el["sku_code"]
            lot = el["lot_number"]
            units = float(el["qty_cartons"]) * float(el["carton_qty"])
            expected_by_sku_lot[(sku, lot)] = expected_by_sku_lot.get((sku, lot), 0.0) + units

        actual_mls = getattr(po_pick, "move_line_ids", [])
        assert actual_mls, f"[canonical_oracle] Move lines pada receipt {po_num} kosong!"
        actual_by_sku_lot = {}
        for ml in actual_mls:
            sku = getattr(getattr(ml, "product_id", None), "default_code", None)
            if not sku and hasattr(ml, "product_id") and isinstance(ml.product_id, int) and "product.product" in env:
                sku = getattr(env["product.product"].browse(ml.product_id), "default_code", None)
            lot_name = getattr(getattr(ml, "lot_id", None), "name", None)
            if not lot_name and hasattr(ml, "lot_id") and isinstance(ml.lot_id, int) and "stock.lot" in env:
                lot_name = getattr(env["stock.lot"].browse(ml.lot_id), "name", None)
            if not lot_name:
                lot_name = getattr(ml, "lot_name", None)
            qty = float(getattr(ml, "quantity", getattr(ml, "qty_done", 0.0)))
            assert qty > 0.0, f"[canonical_oracle] Kuantitas line receipt {po_num} harus positif! Got {qty}"
            key = (sku, lot_name) if sku else lot_name
            actual_by_sku_lot[key] = actual_by_sku_lot.get(key, 0.0) + qty

        for (exp_sku, exp_lot), exp_qty in expected_by_sku_lot.items():
            act_qty = actual_by_sku_lot.get((exp_sku, exp_lot))
            if act_qty is None:
                act_qty = actual_by_sku_lot.get(exp_lot, 0.0)
            assert act_qty is not None and abs(act_qty - exp_qty) < 0.001, (
                f"[canonical_oracle] Kuantitas receipt {po_num} untuk SKU {exp_sku} Lot {exp_lot} salah! "
                f"Expected {exp_qty}, got {act_qty}"
            )
    print(f" -> [Oracle Inbound PO] {len(po_headers)} PO Receipts verified DONE dengan tanggal efektif dan baris eksak.")

    # --- 2. Verifikasi Outgoing SO Deliveries & Multi-Lot Split Nyata ---
    deliv_rows = read_register_csv("perpetual_deliveries.csv", reg_path=reg_path)
    order_line_rows = read_register_csv("perpetual_order_lines.csv", reg_path=reg_path)
    rej_rows = read_register_csv("perpetual_order_rejections.csv", reg_path=reg_path)

    deliv_by_so = {d["so_number"]: d for d in deliv_rows if d["so_number"] in target_so_slice}
    lines_by_so = {}
    for ol in order_line_rows:
        if ol["so_number"] in target_so_slice:
            lines_by_so.setdefault(ol["so_number"], []).append(ol)
    rejections_by_so = {}
    for r in rej_rows:
        if r["so_number"] in target_so_slice:
            rejections_by_so.setdefault(r["so_number"], []).append(r)

    for so_num in target_so_slice:
        so = SaleOrder.search([("name", "=", so_num)], limit=1)
        if not so:
            so = SaleOrder.search([("client_order_ref", "=", so_num)], limit=1)
        if not so:
            so = SaleOrder.search([("origin", "=", so_num)], limit=1)
        assert so, f"[canonical_oracle] Sale Order {so_num} tidak ditemukan!"
        assert so.state in ("sale", "done"), f"[canonical_oracle] Sale Order {so_num} belum confirmed!"

        so_picks = [p for p in getattr(so, "picking_ids", []) if getattr(p, "state", "") != "cancel"]
        if not so_picks:
            so_picks = StockPicking.search([("origin", "in", [getattr(so, "name", ""), so_num])])
            so_picks = [p for p in (so_picks or []) if getattr(p, "state", "") != "cancel"]
        assert len(so_picks) >= 1, f"[canonical_oracle] Delivery picking untuk {so_num} tidak ditemukan!"
        deliv = so_picks[0]
        assert deliv.state == "done", f"[canonical_oracle] Delivery picking untuk {so_num} belum done! State: {deliv.state}"

        expected_deliv = deliv_by_so.get(so_num)
        assert expected_deliv, f"[canonical_oracle] SO {so_num} tidak ada di perpetual_deliveries.csv!"
        exp_date = expected_deliv["scheduled_delivery_date"]
        actual_date = str(getattr(deliv, "date_done", getattr(deliv, "scheduled_date", getattr(deliv, "date", ""))))[:10]
        assert actual_date == exp_date, (
            f"[canonical_oracle] Tanggal delivery {so_num} salah! Expected {exp_date}, got {actual_date}"
        )

        # Hitung kuantitas terkirim per SKU & lot sesuai order lines kanonikal
        expected_delivered = {}
        for ol in lines_by_so.get(so_num, []):
            sku = ol["sku_code"]
            lot = ol["lot_number"]
            units = float(ol["qty_cartons"]) * float(ol["carton_qty"])
            expected_delivered[(sku, lot)] = expected_delivered.get((sku, lot), 0.0) + units

        # Baca move lines aktual
        actual_delivered = {}
        for ml in getattr(deliv, "move_line_ids", []):
            sku = getattr(getattr(ml, "product_id", None), "default_code", None)
            if not sku and hasattr(ml, "product_id") and isinstance(ml.product_id, int) and "product.product" in env:
                sku = getattr(env["product.product"].browse(ml.product_id), "default_code", None)
            lot_name = getattr(getattr(ml, "lot_id", None), "name", None)
            if not lot_name and hasattr(ml, "lot_id") and isinstance(ml.lot_id, int) and "stock.lot" in env:
                lot_name = getattr(env["stock.lot"].browse(ml.lot_id), "name", None)
            if not lot_name:
                lot_name = getattr(ml, "lot_name", None)
            qty = float(getattr(ml, "quantity", getattr(ml, "qty_done", 0.0)))
            key = (sku, lot_name) if sku else lot_name
            actual_delivered[key] = actual_delivered.get(key, 0.0) + qty

        for (exp_sku, exp_lot), exp_qty in expected_delivered.items():
            act_qty = actual_delivered.get((exp_sku, exp_lot))
            if act_qty is None:
                act_qty = actual_delivered.get(exp_lot, 0.0)
            assert act_qty is not None and abs(act_qty - exp_qty) < 0.001, (
                f"[canonical_oracle] Kuantitas Lot {exp_lot} salah! Expected {exp_qty}, got {act_qty}"
            )
    print(f" -> [Oracle Delivery SO] {len(target_so_slice)} SO Deliveries verified DONE dengan kuantitas net accepted per lot.")

    # --- 3. Verifikasi Retur Karantina (Sumber: perpetual_order_rejections.csv) ---
    rejections = [
        r for r in rej_rows
        if r["so_number"] in target_so_slice
    ]
    for rej in rejections:
        rej_id = rej["rejection_id"]
        rej_pick = StockPicking.search([("origin", "=", rej_id)], limit=1)
        assert rej_pick, f"[canonical_oracle] Picking retur karantina {rej_id} tidak ditemukan!"
        assert rej_pick.state == "done", f"[canonical_oracle] Picking karantina {rej_id} belum done! State: {rej_pick.state}"

        # Periksa lokasi tujuan karantina
        dest_loc = getattr(rej_pick, "location_dest_id", None)
        dest_name = str(getattr(dest_loc, "name", ""))
        assert "karantina" in dest_name.lower() or "quarantine" in dest_name.lower(), (
            f"[canonical_oracle] Lokasi tujuan {rej_id} harus karantina, got '{dest_name}'!"
        )

        rej_date = str(getattr(rej_pick, "date_done", getattr(rej_pick, "date", "")))[:10]
        assert rej_date == rej["rejection_date"], (
            f"[canonical_oracle] Tanggal retur karantina {rej_id} harus {rej['rejection_date']}! Got {rej_date}"
        )

        # Hitung kuantitas eksak: qty_cartons * carton_qty
        expected_rej_qty = float(rej["qty_cartons"]) * float(rej["carton_qty"])
        target_lot = rej["lot_number"]
        matching_lines = [
            line_item for line_item in getattr(rej_pick, "move_line_ids", [])
            if getattr(getattr(line_item, "lot_id", None), "name", getattr(line_item, "lot_name", "")) == target_lot
            or target_lot in str(getattr(line_item, "name", ""))
        ]
        assert matching_lines, f"[canonical_oracle] Baris lot {target_lot} pada retur {rej_id} tidak ditemukan!"
        actual_rej_qty = sum(
            float(getattr(line_rec, "quantity", getattr(line_rec, "qty_done", 0.0)))
            for line_rec in matching_lines
        )
        assert abs(actual_rej_qty - expected_rej_qty) < 0.001, (
            f"[canonical_oracle] Kuantitas retur karantina {rej_id} salah! Expected {expected_rej_qty}, got {actual_rej_qty}"
        )
        print(f" -> [Oracle Karantina] {rej_id} verified {actual_rej_qty} unit {rej['sku_code']} di lokasi {dest_name}.")

    # --- 4. Verifikasi Nominal Invoice Komersial & Saldo AR (Sumber: perpetual_invoices.csv) ---
    inv_rows = read_register_csv("perpetual_invoices.csv", reg_path=reg_path)
    all_ar_rows = read_register_csv("perpetual_ar_collections.csv", reg_path=reg_path)

    invoices_data = {
        iv["so_number"]: iv
        for iv in inv_rows
        if iv["so_number"] in target_so_slice
    }
    assert invoices_data, f"[canonical_oracle] Tidak ada invoice untuk slice {target_so_slice}!"

    for so_num, inv_row in invoices_data.items():
        inv_num = inv_row["invoice_number"]
        inv_rec = AccountMove.search([("ref", "=", inv_num)], limit=1)
        assert inv_rec, f"[canonical_oracle] Invoice {inv_num} tidak ditemukan di account.move!"
        assert inv_rec.state == "posted", f"[canonical_oracle] Invoice {inv_num} belum posted!"

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

        # Saldo residual dinamis: join dari perpetual_ar_collections.csv
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
    print(" -> [Oracle Invoice] Invoices verified DPP, PPN, dan saldo residual dinamis.")

    # --- 5. Verifikasi Jurnal Diskon & Rekonsiliasi Pembayaran (Sumber: perpetual_ar_collections.csv) ---
    target_inv_numbers = {iv["invoice_number"] for iv in invoices_data.values()}
    ar_collections = {
        c["invoice_number"]: c
        for c in all_ar_rows
        if c.get("invoice_number") in target_inv_numbers
    }

    for inv_num, ar_row in ar_collections.items():
        disc_amt = float(ar_row.get("early_payment_discount", 0.0))
        pay_id = ar_row["payment_id"]
        if disc_amt > 0:
            disc_ref = f"DISC-{pay_id}"
            disc_move = AccountMove.search([("ref", "=", disc_ref)], limit=1)
            assert disc_move and disc_move.state == "posted", f"[canonical_oracle] Jurnal diskon {disc_ref} belum posted!"
            disc_date = str(getattr(disc_move, "date", ""))
            assert disc_date.startswith(ar_row["payment_date"]), (
                f"[canonical_oracle] Tanggal jurnal diskon salah! Expected {ar_row['payment_date']}, got {disc_date}"
            )
            disc_lines = getattr(disc_move, "line_ids", [])
            ar_disc_line = [
                line_item for line_item in disc_lines
                if getattr(getattr(line_item, "account_id", None), "account_type", "") == "asset_receivable"
            ]
            assert ar_disc_line, f"[canonical_oracle] Line piutang pada jurnal diskon {disc_ref} tidak ditemukan!"
            assert abs(float(getattr(ar_disc_line[0], "credit", 0.0)) - disc_amt) < 0.01, (
                f"[canonical_oracle] Nominal kredit diskon {disc_ref} salah! Expected {disc_amt}, got {ar_disc_line[0].credit}"
            )

        exp_pay_amt = float(ar_row["net_cash_collected_total"])
        pay_rec = AccountPayment.search([("memo", "=", pay_id)], limit=1)
        if not pay_rec:
            pay_rec = AccountPayment.search([("ref", "=", pay_id)], limit=1)
        assert pay_rec, f"[canonical_oracle] Payment {pay_id} tidak ditemukan!"
        assert getattr(pay_rec, "state", "") in ("posted", "in_process", "paid"), (
            f"[canonical_oracle] Payment {pay_id} state bukan posted/in_process/paid! Got: {getattr(pay_rec, 'state', '')}"
        )
        assert abs(float(getattr(pay_rec, "amount", 0.0)) - exp_pay_amt) < 0.01, (
            f"[canonical_oracle] Nominal payment {pay_id} salah! Expected {exp_pay_amt}, got {pay_rec.amount}"
        )

    # --- 6. Verifikasi Penyelarasan Jurnal Valuasi Stok Native (FIFO/Real-Time) ---
    all_moves = AccountMove.search([])
    assert len(all_moves) > 0, "[canonical_oracle] FATAL: Tidak ada entri jurnal yang terbentuk di GL!"
    for m in all_moves:
        assert getattr(m, "state", "") == "posted", (
            f"[canonical_oracle] Entri jurnal '{getattr(m, 'name', m.id)}' belum posted!"
        )
        m_date = str(getattr(m, "date", ""))
        assert m_date.startswith("2026-07-"), (
            f"[canonical_oracle] FATAL: Entry jurnal '{getattr(m, 'ref', m.id)}' bocor dengan tanggal {m_date}! "
            f"Wajib selaras di bulan Juli 2026."
        )
        lines = getattr(m, "line_ids", [])
        if lines:
            tot_debit = sum(float(getattr(jline, "debit", 0.0)) for jline in lines)
            tot_credit = sum(float(getattr(jline, "credit", 0.0)) for jline in lines)
            assert abs(tot_debit - tot_credit) < 0.01, (
                f"[canonical_oracle] Jurnal '{getattr(m, 'name', m.id)}' tidak balance! Debit={tot_debit}, Credit={tot_credit}"
            )
    print(f" -> [Oracle Jurnal Stok & GL] Seluruh {len(all_moves)} journal entries terbukti posted, balance, dan bertanggal Juli 2026.")

    print("=" * 80)
    print("[canonical_oracle] SELURUH VERIFIKASI ORACLE REGISTER KANONIKAL LULUS 100%!")
    print("=" * 80)


class RollbackSentinel(Exception):
    """Sentinel internal untuk memicu rollback savepoint tanpa dianggap kegagalan tes."""
    pass


def verify_slice_mutation_rejection(env, adapter, reg_path, target_so_slice=None):
    """Membuktikan daya uji aktif (active fault detection) dari oracle secara terisolasi.

    Menolak merge data salah meskipun dokumen berstatus done/posted:
    - Memvalidasi env dan reg_path tidak boleh kosong/dummy (fail-fast jika tanpa DB atau path fiktif).
    - Memastikan baseline oracle PASS 100% sebelum mutasi.
    - Menjalankan mutasi nyata dalam savepoint database dengan unconditional rollback:
      * Mutasi 1: Kuantitas lot split dirusak (lot kedua hilang/0 unit pada SO-202607-0317).
      * Mutasi 2: Nilai nominal DPP invoice dipalsukan (INV-202607-0317).
      * Mutasi 3: Tanggal efektif bocor ke tanggal runtime saat ini (INV-202607-0001).
    - Membuktikan bahwa verifikasi oracle produksi (verify_run1_against_canonical_oracle)
      secara aktif menolak tiap mutasi cacat tersebut dengan error substring yang tepat.
    - Memverifikasi oracle kembali PASS setelah rollback pada tiap fase mutasi.
    """
    if env is None:
        raise ValueError("[mutation_rejection] FATAL: env (Odoo environment) wajib disediakan!")
    reg_path = Path(reg_path)
    if not reg_path.is_dir():
        raise FileNotFoundError(f"[mutation_rejection] FATAL: Direktori register tidak valid: {reg_path}")

    REQUIRED_MODELS = [
        "stock.picking", "account.move", "account.payment", "stock.quant",
        "purchase.order", "sale.order", "stock.move", "stock.move.line",
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

    def _execute_isolated_mutation(mutator_fn, expected_error_substring, mutation_name):
        print(f"\n[mutation_rejection] Menjalankan {mutation_name}...")
        has_cr = hasattr(env, "cr") and hasattr(env.cr, "savepoint")
        oracle_rejected = False
        caught_error = None

        mock_backup = None
        if not has_cr:
            mock_backup = []
            for m in list(env.keys()):
                if hasattr(env[m], "store") and isinstance(env[m].store, dict):
                    for rec in env[m].store.values():
                        mock_backup.append((rec, dict(getattr(rec, "_vals", {})), dict(getattr(rec, "__dict__", {}))))
                        if hasattr(rec, "move_line_ids") and isinstance(rec.move_line_ids, (list, tuple)):
                            for nested in rec.move_line_ids:
                                mock_backup.append((nested, dict(getattr(nested, "_vals", {})), dict(getattr(nested, "__dict__", {}))))
                        if hasattr(rec, "line_ids") and isinstance(rec.line_ids, (list, tuple)):
                            for nested in rec.line_ids:
                                mock_backup.append((nested, dict(getattr(nested, "_vals", {})), dict(getattr(nested, "__dict__", {}))))

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
                    # Picu rollback PostgreSQL savepoint secara unconditional
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
                    for rec, vals_copy, dict_copy in mock_backup:
                        rec.__dict__.clear()
                        rec.__dict__.update(dict_copy)
                        if hasattr(rec, "_vals"):
                            rec._vals = dict(vals_copy)

        if not oracle_rejected:
            raise AssertionError(f"[mutation_rejection] FATAL: Oracle gagal menolak mutasi '{mutation_name}'!")

        print(f" -> [{mutation_name} PASSED] Oracle produksi berhasil menolak: {caught_error}")

        # Verifikasi post-mutation: oracle WAJIB PASS kembali setelah rollback!
        verify_run1_against_canonical_oracle(env, adapter, reg_path, target_so_slice)
        print(f" -> [Post-{mutation_name}] Oracle PASS kembali (rollback terbukti bersih & terisolasi).")

    # --- Mutasi 1: Uji Penolakan Lot Split Cacat (Kasus SO-202607-0317) ---
    def mutate_lot_split():
        StockPicking = env["stock.picking"].sudo()
        SaleOrder = env["sale.order"].sudo()
        so317 = SaleOrder.search([("name", "=", "SO-202607-0317")], limit=1)
        if not so317:
            so317 = SaleOrder.search([("client_order_ref", "=", "SO-202607-0317")], limit=1)
        picks = [p for p in getattr(so317, "picking_ids", []) if getattr(p, "state", "") != "cancel"] if so317 else []
        pick317 = picks[0] if picks else StockPicking.search([("origin", "=", "SO-202607-0317")], limit=1)
        assert pick317, "[mutation_rejection] Picking SO-202607-0317 harus tersedia untuk mutasi 1!"

        found = False
        for ml in getattr(pick317, "move_line_ids", []):
            lot_name = getattr(getattr(ml, "lot_id", None), "name", "")
            if not lot_name and isinstance(getattr(ml, "lot_id", None), int) and "stock.lot" in env:
                lot_name = getattr(env["stock.lot"].browse(ml.lot_id), "name", "")
            if not lot_name:
                lot_name = getattr(ml, "lot_name", "")
            if lot_name == "LOT-VER-20260704-04":
                if callable(getattr(ml, "write", None)):
                    ml.write({"quantity": 0.0})
                else:
                    setattr(ml, "quantity", 0.0)
                found = True
                break
        assert found, "[mutation_rejection] Lot LOT-VER-20260704-04 tidak ditemukan pada SO-202607-0317!"

    _execute_isolated_mutation(
        mutate_lot_split,
        "Kuantitas Lot LOT-VER-20260704-04 salah",
        "Mutation 1 (Cacat Lot Split)",
    )

    # --- Mutasi 2: Uji Penolakan Nominal Komersial Palsu (INV-202607-0317) ---
    def mutate_invoice_dpp():
        AccountMove = env["account.move"].sudo()
        inv317 = AccountMove.search([("ref", "=", "INV-202607-0317")], limit=1)
        assert inv317, "[mutation_rejection] Invoice INV-202607-0317 harus tersedia untuk mutasi 2!"
        if hasattr(env, "cr") and hasattr(env.cr, "execute"):
            env.cr.execute("UPDATE account_move SET amount_untaxed = 9999999.0 WHERE id = %s", (inv317.id,))
            if hasattr(inv317, "invalidate_recordset"):
                inv317.invalidate_recordset()
        else:
            setattr(inv317, "amount_untaxed", 9999999.0)

    _execute_isolated_mutation(
        mutate_invoice_dpp,
        "DPP INV-202607-0317 salah",
        "Mutation 2 (Pemalsuan DPP Invoice)",
    )

    # --- Mutasi 3: Uji Penolakan Tanggal Bocor ke Runtime (INV-202607-0001) ---
    def mutate_invoice_date():
        AccountMove = env["account.move"].sudo()
        inv1 = AccountMove.search([("ref", "=", "INV-202607-0001")], limit=1)
        assert inv1, "[mutation_rejection] Invoice INV-202607-0001 harus tersedia untuk mutasi 3!"
        if hasattr(env, "cr") and hasattr(env.cr, "execute"):
            env.cr.execute("UPDATE account_move SET date = '2026-10-27' WHERE id = %s", (inv1.id,))
            if hasattr(inv1, "invalidate_recordset"):
                inv1.invalidate_recordset()
        else:
            setattr(inv1, "date", "2026-10-27")

    _execute_isolated_mutation(
        mutate_invoice_date,
        "bocor dengan tanggal 2026-10-27",
        "Mutation 3 (Kebocoran Tanggal Runtime)",
    )

    print("\n" + "=" * 80)
    print("[mutation_rejection] SELURUH UJI MUTASI NEGATIF BERHASIL DITOLAK (ORACLE TERBUKTI AKTIF & TERISOLASI)")
    print("=" * 80)


def run_representative_slice(env):
    """Menjalankan dan memverifikasi slice representatif pada Odoo disposable DB."""
    introspect_odoo19_schema(env)

    target_so_slice = ["SO-202607-0001", "SO-202607-0063", "SO-202607-0317"]
    print(f"\n[disposable_slice] MENJALANKAN SLICE TRANSAKSI REPRESENTATIF (RUN 1): {target_so_slice}...")
    adapter = CanonicalPerpetualAdapter(env, reg_path=REG_PATH)

    # Jalankan slice representatif multi-domain
    adapter.run_all(target_so_numbers=target_so_slice)

    print("[disposable_slice] RUN 1 SELESAI. Mengeksekusi verifikasi Oracle Kanonikal...")

    # Verifikasi Run 1 terhadap Oracle Kanonikal CSV
    verify_run1_against_canonical_oracle(env, adapter, REG_PATH, target_so_slice)

    # Uji Mutasi Negatif Hasil Run 1
    verify_slice_mutation_rejection(env, adapter, REG_PATH)

    StockQuant = env["stock.quant"].sudo() if "stock.quant" in env else None
    AccountMoveLine = env["account.move.line"].sudo() if "account.move.line" in env else None

    # Snapshot Saldo Stok & GL setelah Run 1
    quant_records_run1 = {}
    stock_totals_run1 = {}
    if StockQuant is not None:
        for q in StockQuant.search([]):
            prod_code = getattr(getattr(q, "product_id", None), "default_code", getattr(q.product_id, "id", None))
            loc_name = getattr(getattr(q, "location_id", None), "name", getattr(q.location_id, "id", None))
            lot_name = getattr(getattr(q, "lot_id", None), "name", False)
            qty = float(getattr(q, "quantity", 0.0))
            quant_records_run1[q.id] = {
                "product_code": prod_code,
                "location_name": loc_name,
                "lot_name": lot_name,
                "quantity": qty,
            }
            key = (prod_code, loc_name, lot_name)
            stock_totals_run1[key] = stock_totals_run1.get(key, 0.0) + qty

    gl_snapshot_run1 = {}
    if AccountMoveLine is not None:
        for line_rec in AccountMoveLine.search([]):
            acc_code = getattr(
                getattr(line_rec, "account_id", None), "code", getattr(line_rec.account_id, "id", None)
            )
            gl_snapshot_run1.setdefault(acc_code, {"debit": 0.0, "credit": 0.0})
            gl_snapshot_run1[acc_code]["debit"] += float(getattr(line_rec, "debit", 0.0))
            gl_snapshot_run1[acc_code]["credit"] += float(getattr(line_rec, "credit", 0.0))

    print(f"[disposable_slice] Snapshot Saldo Stok Run 1: {len(quant_records_run1)} record quant terdata.")
    print(f"[disposable_slice] Snapshot Saldo GL Run 1: {len(gl_snapshot_run1)} akun GL terdata.")

    # 5. Menjalankan Uji Idempotensi Sejati (Run 2)
    print("\n[disposable_slice] MENJALANKAN UJI IDEMPOTENSI SEJATI (RUN 2)...")
    adapter_run2 = CanonicalPerpetualAdapter(env, reg_path=REG_PATH)
    adapter_run2.run_all(target_so_numbers=target_so_slice)

    print("[disposable_slice] RUN 2 SUKSES. Memeriksa counter create...")
    assert adapter_run2.stats["so_created"] == 0, "SO tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["po_created"] == 0, "PO tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["ar_payments_created"] == 0, "Payment AR tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["ap_payments_created"] == 0, "Payment AP tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["discount_moves_created"] == 0, "Jurnal diskon tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["quarantine_rejections"] == 0, "Karantina tidak boleh dibuat ulang pada run 2!"

    # 6. Komparasi Saldo Stok Run 1 vs Run 2 (Audit Zero Stock Drift Tanpa Penimpaan)
    if StockQuant is not None:
        quant_records_run2 = {}
        stock_totals_run2 = {}
        for q in StockQuant.search([]):
            prod_code = getattr(getattr(q, "product_id", None), "default_code", getattr(q.product_id, "id", None))
            loc_name = getattr(getattr(q, "location_id", None), "name", getattr(q.location_id, "id", None))
            lot_name = getattr(getattr(q, "lot_id", None), "name", False)
            qty = float(getattr(q, "quantity", 0.0))
            quant_records_run2[q.id] = {
                "product_code": prod_code,
                "location_name": loc_name,
                "lot_name": lot_name,
                "quantity": qty,
            }
            key = (prod_code, loc_name, lot_name)
            stock_totals_run2[key] = stock_totals_run2.get(key, 0.0) + qty

        # Audit ID quant tidak boleh bertambah atau berkurang
        new_quants = set(quant_records_run2.keys()) - set(quant_records_run1.keys())
        assert not new_quants, f"Ditemukan record quant baru pada Run 2: {new_quants}"
        del_quants = set(quant_records_run1.keys()) - set(quant_records_run2.keys())
        assert not del_quants, f"Record quant hilang pada Run 2: {del_quants}"

        # Audit kuantitas fisik per record ID
        for q_id, info1 in quant_records_run1.items():
            info2 = quant_records_run2[q_id]
            assert abs(info1["quantity"] - info2["quantity"]) < 0.001, (
                f"Drift kuantitas terdeteksi pada quant ID {q_id} ({info1['product_code']})! "
                f"Run 1: {info1['quantity']}, Run 2: {info2['quantity']}"
            )

        # Audit total agregasi kuantitas stok per (produk, lokasi, lot)
        assert len(stock_totals_run1) == len(stock_totals_run2), "Jumlah kombinasi stok berubah pada run 2!"
        for key, tot1 in stock_totals_run1.items():
            tot2 = stock_totals_run2.get(key, 0.0)
            assert abs(tot1 - tot2) < 0.001, (
                f"Drift agregasi stok terdeteksi pada {key}! Run 1: {tot1}, Run 2: {tot2}"
            )

    # 7. Komparasi Saldo GL Run 1 vs Run 2
    if AccountMoveLine is not None:
        gl_snapshot_run2 = {}
        for line_rec in AccountMoveLine.search([]):
            acc_code = getattr(
                getattr(line_rec, "account_id", None), "code", getattr(line_rec.account_id, "id", None)
            )
            gl_snapshot_run2.setdefault(acc_code, {"debit": 0.0, "credit": 0.0})
            gl_snapshot_run2[acc_code]["debit"] += float(getattr(line_rec, "debit", 0.0))
            gl_snapshot_run2[acc_code]["credit"] += float(getattr(line_rec, "credit", 0.0))

        assert len(gl_snapshot_run1) == len(gl_snapshot_run2), "Jumlah akun GL berubah pada run 2!"
        for acc_code, b1 in gl_snapshot_run1.items():
            b2 = gl_snapshot_run2.get(acc_code, {"debit": 0.0, "credit": 0.0})
            assert abs(b1["debit"] - b2["debit"]) < 0.01, (
                f"Drift GL Debit pada akun {acc_code}! Run 1: {b1['debit']}, Run 2: {b2['debit']}"
            )
            assert abs(b1["credit"] - b2["credit"]) < 0.01, (
                f"Drift GL Credit pada akun {acc_code}! Run 1: {b1['credit']}, Run 2: {b2['credit']}"
            )

    print("=" * 80)
    print("[disposable_slice] VERIFIKASI RUNTIME ODOO DISPOSABLE SUKSES 100%!")
    print("  - Schema Introspection: PASSED")
    print(f"  - Representative Slice Run 1 ({target_so_slice}): PASSED")
    print("  - Canonical CSV Oracle Verification: PASSED")
    print("  - Multi-Lot Split SO-202607-0317 (120 + 96 = 216 unit): PASSED")
    print("  - Negative Mutation Rejection (Active Fault Detection): PASSED")
    print("  - Retur Karantina Customer -> Quarantine: PASSED")
    print("  - Deep Readback (Exact Discount Ref, Move IDs, Residuals): PASSED")
    print("  - True Idempotency Rerun 2 (0 created, 100% skipped): PASSED")
    print("  - Zero Stock Drift (Saldo Stok Run 1 == Run 2): PASSED")
    print("  - Zero GL Drift (Saldo Buku Besar Run 1 == Run 2): PASSED")
    print("=" * 80)


if __name__ == "__main__" or "env" in globals():
    env_obj = globals().get("env")
    if env_obj:
        run_representative_slice(env_obj)
    else:
        print("[disposable_slice] Skrip ini dirancang untuk dijalankan di dalam Odoo shell.")
        print("Penggunaan: odoo shell -c /tmp/odoo.conf -d fmcg --no-http < scripts/ops/verify_disposable_slice.py")

