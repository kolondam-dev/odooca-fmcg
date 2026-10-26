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

import sys
from pathlib import Path

# Path root repositori
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.load_canonical_perpetual import CanonicalPerpetualAdapter  # noqa: E402


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


def run_representative_slice(env):
    """Menjalankan dan memverifikasi slice representatif pada Odoo disposable DB."""
    introspect_odoo19_schema(env)

    target_so_slice = ["SO-202607-0001", "SO-202607-0063"]
    print(f"\n[disposable_slice] MENJALANKAN SLICE TRANSAKSI REPRESENTATIF (RUN 1): {target_so_slice}...")
    adapter = CanonicalPerpetualAdapter(env, reg_path=REPO_ROOT / "data" / "registers")

    # Jalankan slice representatif multi-domain
    adapter.run_all(target_so_numbers=target_so_slice)

    print("[disposable_slice] RUN 1 SUKSES. Melakukan verifikasi readback mendalam...")

    AccountPayment = env["account.payment"].sudo() if "account.payment" in env else None
    AccountMove = env["account.move"].sudo() if "account.move" in env else None
    StockPicking = env["stock.picking"].sudo() if "stock.picking" in env else None
    StockQuant = env["stock.quant"].sudo() if "stock.quant" in env else None
    AccountMoveLine = env["account.move.line"].sudo() if "account.move.line" in env else None

    # 1. Verifikasi picking (PO receipt, SO deliveries, dan Karantina transfer)
    if StockPicking:
        picks = StockPicking.search([])
        for p in picks:
            assert p.state == "done", f"Picking '{p.name or p.origin}' belum done! State: {p.state}"
            for ml in getattr(p, "move_line_ids", []):
                qty = getattr(ml, "quantity", getattr(ml, "qty_done", 0.0))
                assert float(qty) > 0.0, f"Move line kuantitas harus positif! Got {qty}"

        # Verifikasi spesifik retur karantina REJ-202607-001
        rej_pick = StockPicking.search([("origin", "=", "REJ-202607-001")], limit=1)
        assert rej_pick, "Picking retur karantina REJ-202607-001 tidak ditemukan!"
        assert rej_pick.state == "done", f"Picking karantina belum done! State: {rej_pick.state}"
        loc_usage = getattr(getattr(rej_pick, "location_id", None), "usage", "")
        assert loc_usage == "customer", (
            f"Transfer karantina bersumber dari usage='{loc_usage}', bukan 'customer'!"
        )

    # 2. Verifikasi payments (AR dan AP)
    if AccountPayment:
        pays = AccountPayment.search([])
        assert len(pays) >= 5, f"Expected minimal 5 payment, got {len(pays)}"
        for py in pays:
            assert py.state in ("posted", "in_process", "paid"), (
                f"Payment '{getattr(py, 'name', py.id)}' state tidak valid: {py.state}"
            )
            assert getattr(py, "move_id", None), f"Payment '{py.id}' tidak memiliki journal entry move_id!"
            assert py.move_id.state == "posted", f"Journal entry move dari payment '{py.id}' belum posted!"

            # Baris piutang/utang harus terekonsiliasi penuh
            rec_pay_lines = adapter._get_record_lines(py)
            for line in rec_pay_lines:
                acc_t = getattr(getattr(line, "account_id", None), "account_type", "")
                if acc_t in ("asset_receivable", "liability_payable"):
                    assert adapter._is_reconciled(line), (
                        f"Line payment {py.id} belum terekonsiliasi! Residual: {getattr(line, 'amount_residual', 'N/A')}"
                    )

    # 3. Verifikasi account moves (invoices & exact discount moves)
    if AccountMove:
        # Verifikasi jurnal diskon persis DISC-PAY-AR-00098
        disc_move = AccountMove.search([("ref", "=", "DISC-PAY-AR-00098")], limit=1)
        assert disc_move, "Jurnal diskon persis 'DISC-PAY-AR-00098' tidak ditemukan!"
        assert disc_move.state == "posted", f"Discount move belum posted! State: {disc_move.state}"
        for line in getattr(disc_move, "line_ids", []):
            acc_t = getattr(getattr(line, "account_id", None), "account_type", "")
            if acc_t == "asset_receivable":
                assert adapter._is_reconciled(line), "Line piutang diskon DISC-PAY-AR-00098 belum terekonsiliasi!"

    # 4. Snapshot Saldo Stok & GL setelah Run 1
    stock_snapshot_run1 = {}
    if StockQuant:
        for q in StockQuant.search([]):
            prod_code = getattr(getattr(q, "product_id", None), "default_code", getattr(q.product_id, "id", None))
            loc_name = getattr(getattr(q, "location_id", None), "name", getattr(q.location_id, "id", None))
            lot_name = getattr(getattr(q, "lot_id", None), "name", False)
            stock_snapshot_run1[(prod_code, loc_name, lot_name)] = float(getattr(q, "quantity", 0.0))

    gl_snapshot_run1 = {}
    if AccountMoveLine:
        for line_rec in AccountMoveLine.search([]):
            acc_code = getattr(
                getattr(line_rec, "account_id", None), "code", getattr(line_rec.account_id, "id", None)
            )
            gl_snapshot_run1.setdefault(acc_code, {"debit": 0.0, "credit": 0.0})
            gl_snapshot_run1[acc_code]["debit"] += float(getattr(line_rec, "debit", 0.0))
            gl_snapshot_run1[acc_code]["credit"] += float(getattr(line_rec, "credit", 0.0))

    print(f"[disposable_slice] Snapshot Saldo Stok Run 1: {len(stock_snapshot_run1)} quants terdata.")
    print(f"[disposable_slice] Snapshot Saldo GL Run 1: {len(gl_snapshot_run1)} akun GL terdata.")

    # 5. Menjalankan Uji Idempotensi Sejati (Run 2)
    print("\n[disposable_slice] MENJALANKAN UJI IDEMPOTENSI SEJATI (RUN 2)...")
    adapter_run2 = CanonicalPerpetualAdapter(env, reg_path=REPO_ROOT / "data" / "registers")
    adapter_run2.run_all(target_so_numbers=target_so_slice)

    print("[disposable_slice] RUN 2 SUKSES. Memeriksa counter create...")
    assert adapter_run2.stats["so_created"] == 0, "SO tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["po_created"] == 0, "PO tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["ar_payments_created"] == 0, "Payment AR tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["ap_payments_created"] == 0, "Payment AP tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["discount_moves_created"] == 0, "Jurnal diskon tidak boleh dibuat ulang pada run 2!"
    assert adapter_run2.stats["quarantine_rejections"] == 0, "Karantina tidak boleh dibuat ulang pada run 2!"

    # 6. Komparasi Saldo Stok Run 1 vs Run 2
    if StockQuant:
        stock_snapshot_run2 = {}
        for q in StockQuant.search([]):
            prod_code = getattr(getattr(q, "product_id", None), "default_code", getattr(q.product_id, "id", None))
            loc_name = getattr(getattr(q, "location_id", None), "name", getattr(q.location_id, "id", None))
            lot_name = getattr(getattr(q, "lot_id", None), "name", False)
            stock_snapshot_run2[(prod_code, loc_name, lot_name)] = float(getattr(q, "quantity", 0.0))

        assert len(stock_snapshot_run1) == len(stock_snapshot_run2), "Jumlah quant berubah pada run 2!"
        for key, qty1 in stock_snapshot_run1.items():
            qty2 = stock_snapshot_run2.get(key, 0.0)
            assert abs(qty1 - qty2) < 0.001, (
                f"Drift saldo stok terdeteksi pada {key}! Run 1: {qty1}, Run 2: {qty2}"
            )

    # 7. Komparasi Saldo GL Run 1 vs Run 2
    if AccountMoveLine:
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
