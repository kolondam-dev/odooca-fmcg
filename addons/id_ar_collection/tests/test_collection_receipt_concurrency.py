"""BE-20d: dua transaksi PostgreSQL nyata untuk handler penerimaan (urutan lock dan baca ulang saldo).

Kelas terpisah tanpa fixture tak ter-commit (kunci baris milik transaksi tes akan membuat cursor lain menunggu tanpa
akhir). Fixture BENAR-BENAR di-commit pada perusahaan utama dan dibersihkan penuh. Setiap tes menahan satu transaksi
terbuka, menjalankan transaksi kedua di thread, memastikan yang kedua MENUNGGU, lalu commit.
"""
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone

from odoo import SUPERUSER_ID, Command, api, sql_db
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.id_base.models.business_day import business_date

WAIT = 1.5  # detik: cukup bagi transaksi kedua untuk berhenti di lock
JOIN = 40


@tagged("post_install", "-at_install")
class TestCollectionReceiptConcurrency(TransactionCase):
    # ---- fixture ter-commit ----------------------------------------------------------------------
    def _commit_fixture(self, db):
        with db.cursor() as cr:
            cr.execute("SET LOCAL lock_timeout = '20s'")
            env = api.Environment(cr, SUPERUSER_ID, {})
            company = env.ref("base.main_company")
            env = env(context={**env.context, "allowed_company_ids": company.ids})
            receivable = env["account.account"].create({
                "name": "AR RCP Conc", "code": "999811", "account_type": "asset_receivable",
                "company_ids": [Command.set(company.ids)]})
            income = env["account.account"].create({
                "name": "Income RCP Conc", "code": "999812", "account_type": "income",
                "company_ids": [Command.set(company.ids)]})
            sales = env["account.journal"].create({
                "name": "Sales RCP Conc", "code": "RCC", "type": "sale", "company_id": company.id})
            general = env["account.journal"].create({
                "name": "General RCP Conc", "code": "RCG", "type": "general", "company_id": company.id})
            partner = env["res.partner"].create({"name": "RCP Conc Customer", "is_company": True})
            partner.with_company(company).property_account_receivable_id = receivable
            collector = new_test_user(
                env, login=f"rcp-conc-{uuid.uuid4().hex[:10]}", groups="id_mobile_api.group_mobile_sales",
                company_id=company.id)
            moves = env["account.move"]
            for _ in range(2):
                move = env["account.move"].create({
                    "move_type": "out_invoice", "company_id": company.id, "journal_id": sales.id,
                    "partner_id": partner.id, "invoice_date": business_date() - timedelta(days=30),
                    "invoice_date_due": business_date(),
                    "invoice_line_ids": [Command.create({
                        "name": "x", "quantity": 1, "price_unit": 1000, "account_id": income.id})]})
                move.action_post()
                moves |= move
            sheet = env["id.collection.sheet"].create({
                "company_id": company.id, "collector_id": collector.id, "collect_date": business_date(),
                "line_ids": [Command.create({"move_id": move.id}) for move in moves]})
            sheet.action_issue()
            return {
                "company": company.id, "receivable": receivable.id, "income": income.id, "general": general.id,
                "journals": (sales | general).ids, "accounts": (receivable | income).ids, "partner": partner.id,
                "collector": collector.id, "moves": sorted(moves.ids), "sheet": sheet.id,
                "lines": {line.move_id.id: line.id for line in sheet.line_ids},
            }

    def _cleanup_fixture(self, db, ids):
        """Hapus semua yang di-commit; kegagalan membersihkan SENGAJA tidak ditelan (mencemari langkah CI lain)."""
        with db.cursor() as cr:
            cr.execute("SET LOCAL lock_timeout = '20s'")
            cr.execute("DELETE FROM id_collection_receipt_line WHERE move_id = ANY(%s)", (ids["moves"],))
            cr.execute("DELETE FROM id_collection_receipt WHERE sheet_id = %s", (ids["sheet"],))
            cr.execute("DELETE FROM id_mobile_command WHERE user_id = %s", (ids["collector"],))
            cr.execute("DELETE FROM id_collection_sheet_line WHERE sheet_id = %s", (ids["sheet"],))
            cr.execute("DELETE FROM id_collection_sheet WHERE id = %s", (ids["sheet"],))
            cr.execute(
                "SELECT DISTINCT move_id FROM account_move_line WHERE partner_id = %s", (ids["partner"],))
            all_moves = [row[0] for row in cr.fetchall()]
            cr.execute(
                "DELETE FROM account_partial_reconcile WHERE debit_move_id IN "
                "(SELECT id FROM account_move_line WHERE move_id = ANY(%s)) OR credit_move_id IN "
                "(SELECT id FROM account_move_line WHERE move_id = ANY(%s))", (all_moves, all_moves))
            cr.execute("UPDATE account_move_line SET full_reconcile_id = NULL WHERE move_id = ANY(%s)", (all_moves,))
            cr.execute("DELETE FROM account_full_reconcile WHERE id NOT IN "
                       "(SELECT full_reconcile_id FROM account_move_line WHERE full_reconcile_id IS NOT NULL)")
            cr.execute("DELETE FROM account_move_line WHERE move_id = ANY(%s)", (all_moves,))
            cr.execute("DELETE FROM account_move WHERE id = ANY(%s)", (all_moves,))
            env = api.Environment(cr, SUPERUSER_ID, {})
            env["account.journal"].browse(ids["journals"]).unlink()
            cr.execute("UPDATE res_users SET active = FALSE WHERE id = %s", (ids["collector"],))  # arsip, tanpa hapus
            env["res.partner"].browse(ids["partner"]).unlink()  # sebelum akun: properti piutang menunjuk akun
            env["account.account"].browse(ids["accounts"]).unlink()

    def _setup(self):
        db = sql_db.db_connect(self.env.cr.dbname)
        ids = self._commit_fixture(db)
        self.addCleanup(self._cleanup_fixture, db, ids)
        return db, ids

    # ---- helpers transaksi -------------------------------------------------------------------------
    @staticmethod
    def _occurred():
        return (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()

    @staticmethod
    def _command(ids, order, client_uuid=None, amount_of=None):
        lines = [{
            "line_id": ids["lines"][move_id], "invoice_id": move_id, "outcome": "paid",
            "amount": 1000, "expected_balance": 1000,
        } for move_id in order]
        return {
            "client_uuid": client_uuid or str(uuid.uuid4()), "type": "collection.receipt.submit",
            "payload": {"sheet_id": ids["sheet"], "occurred_at": TestCollectionReceiptConcurrency._occurred(),
                        "lines": lines},
        }

    def _run_in_thread(self, db, work, outcome, uid):
        # Cursor dan Environment dibuat DI THREAD UTAMA: Registry._lock dipegang thread tes utama selama tes berjalan,
        # sehingga api.Environment(...) di thread lain menggantung (terbukti dari stack di CI).
        cr = db.cursor()
        cr.execute("SET LOCAL lock_timeout = '20s'")
        thread_env = api.Environment(cr, uid, {})

        def runner():
            try:
                outcome["result"] = work(thread_env)
                # Commit PostgreSQL mentah: hook postcommit ORM (signal_changes) membuka registry.cursor() yang pada
                # mode tes memakai satu cursor bersama berkunci milik thread tes utama dan menggantung thread ini.
                cr.precommit.clear()
                cr.postcommit.clear()
                cr._cnx.commit()
            except Exception as exc:  # noqa: BLE001
                outcome["error"] = exc
                cr._cnx.rollback()
            finally:
                cr.close()

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        return thread

    def _hang_report(self, db, thread):
        frame = sys._current_frames().get(thread.ident)
        stack = "".join(traceback.format_stack(frame)[-12:]) if frame else "(thread selesai)"
        with db.cursor() as cr:
            cr.execute(
                "SELECT pid, state, wait_event_type, wait_event, left(query, 120) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()")
            activity = cr.fetchall()
        return f"\n--- stack thread ---\n{stack}\n--- pg_stat_activity ---\n{activity}"

    def _db_state(self, db, ids):
        with db.cursor() as cr:
            cr.execute("SELECT count(*) FROM id_collection_receipt WHERE sheet_id = %s", (ids["sheet"],))
            receipts = cr.fetchone()[0]
            cr.execute("SELECT status, count(*) FROM id_mobile_command WHERE user_id = %s GROUP BY status",
                       (ids["collector"],))
            commands = dict(cr.fetchall())
            return receipts, commands

    # ---- (a) command vs command, urutan payload berlawanan ---------------------------------------------
    def test_two_commands_with_opposite_payload_order_serialize_without_deadlock(self):
        db, ids = self._setup()
        first, second = ids["moves"]
        cr1 = db.cursor()
        cr1.execute("SET LOCAL lock_timeout = '20s'")
        env1 = api.Environment(cr1, ids["collector"], {})
        outcome = {}
        try:
            first_result = env1["id.mobile.command"].process_command(self._command(ids, [second, first]))
            self.assertEqual(first_result["status"], "accepted")
            env1.flush_all()

            def other(env2):
                result = env2["id.mobile.command"].process_command(self._command(ids, [first, second]))
                env2.flush_all()
                return result

            thread = self._run_in_thread(db, other, outcome, ids["collector"])
            time.sleep(WAIT)
            self.assertTrue(thread.is_alive(), "transaksi kedua harus menunggu lock SJP")
            cr1.commit()
        finally:
            cr1.close()
        thread.join(JOIN)
        self.assertFalse(thread.is_alive(), "tidak boleh deadlock/menggantung" + self._hang_report(db, thread))
        self.assertNotIn("error", outcome, outcome.get("error"))
        self.assertEqual(outcome["result"]["status"], "rejected")  # baris sudah dilaporkan transaksi pertama
        receipts, commands = self._db_state(db, ids)
        self.assertEqual(receipts, 1)  # tepat satu yang menang
        self.assertEqual(commands, {"accepted": 1, "rejected": 1})

    # ---- (b) command vs rekonsiliasi native -------------------------------------------------------------
    def _native_reconcile(self, env, ids, amount):
        """Rekonsiliasi native Odoo (`account.move.line.reconcile`): jurnal umum mengkredit piutang, lalu parsial."""
        move = env["account.move"].browse(ids["moves"][0])
        entry = env["account.move"].create({
            "move_type": "entry", "journal_id": ids["general"], "date": business_date(),
            "line_ids": [
                Command.create({"account_id": ids["receivable"], "partner_id": ids["partner"],
                                "credit": amount, "debit": 0.0}),
                Command.create({"account_id": ids["income"], "debit": amount, "credit": 0.0}),
            ]})
        entry.action_post()
        lines = move.line_ids.filtered(lambda line: line.display_type == "payment_term")
        lines |= entry.line_ids.filtered(lambda line: line.account_id.id == ids["receivable"])
        lines.reconcile()
        env.flush_all()
        return move.amount_residual

    def test_command_waits_for_native_reconcile_then_rereads_balance(self):
        db, ids = self._setup()
        cr_native = db.cursor()
        cr_native.execute("SET LOCAL lock_timeout = '20s'")
        env_native = api.Environment(cr_native, SUPERUSER_ID, {})
        outcome = {}
        try:
            residual = self._native_reconcile(env_native, ids, 400.0)
            self.assertEqual(residual, 600.0)

            def command(env2):
                result = env2["id.mobile.command"].process_command(self._command(ids, [ids["moves"][0]]))
                env2.flush_all()
                return result

            thread = self._run_in_thread(db, command, outcome, ids["collector"])
            time.sleep(WAIT)
            self.assertTrue(thread.is_alive(), "command harus menunggu rekonsiliasi native yang belum commit")
            cr_native.commit()
        finally:
            cr_native.close()
        thread.join(JOIN)
        self.assertFalse(thread.is_alive(), "menggantung" + self._hang_report(db, thread))
        self.assertNotIn("error", outcome, outcome.get("error"))
        # Setelah menunggu, saldo dibaca ulang (600): expected_balance 1000 basi => ditolak, tanpa efek.
        self.assertEqual((outcome["result"]["status"], outcome["result"]["reference"]), ("rejected", "balance"))
        receipts, commands = self._db_state(db, ids)
        self.assertEqual((receipts, commands), (0, {"rejected": 1}))
        with db.cursor() as cr:
            cr.execute("SELECT outcome FROM id_collection_sheet_line WHERE id = %s", (ids["lines"][ids["moves"][0]],))
            self.assertEqual(cr.fetchone()[0], "pending")

    def test_native_reconcile_waits_for_command_lock(self):
        db, ids = self._setup()
        cr1 = db.cursor()
        cr1.execute("SET LOCAL lock_timeout = '20s'")
        env1 = api.Environment(cr1, ids["collector"], {})
        outcome = {}
        try:
            result = env1["id.mobile.command"].process_command(self._command(ids, [ids["moves"][0]]))
            self.assertEqual(result["status"], "accepted")
            env1.flush_all()

            def native(env_t):
                return self._native_reconcile(env_t, ids, 400.0)  # flush di dalam

            thread = self._run_in_thread(db, native, outcome, SUPERUSER_ID)
            time.sleep(WAIT)
            self.assertTrue(thread.is_alive(), "rekonsiliasi native harus menunggu lock command")
            cr1.commit()
        finally:
            cr1.close()
        thread.join(JOIN)
        self.assertFalse(thread.is_alive(), "menggantung" + self._hang_report(db, thread))
        self.assertNotIn("error", outcome, outcome.get("error"))
        self.assertEqual(outcome["result"], 600.0)
        receipts, commands = self._db_state(db, ids)
        # Penerimaan dicatat terhadap saldo yang terkunci (1000); 20e wajib memvalidasi ulang saldo saat posting.
        self.assertEqual((receipts, commands), (1, {"accepted": 1}))
