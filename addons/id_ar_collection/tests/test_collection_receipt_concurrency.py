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

from psycopg2 import errors

from odoo import SUPERUSER_ID, Command, api, sql_db
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger

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
            cash_account = env["account.account"].create({
                "name": "Kas RCP Conc", "code": "999813", "account_type": "asset_cash",
                "company_ids": [Command.set(company.ids)]})
            outstanding = env["account.account"].create({
                "name": "Outstanding RCP Conc", "code": "999814", "account_type": "asset_current",
                "company_ids": [Command.set(company.ids)]})
            cash = env["account.journal"].create({
                "name": "Kas RCP Conc", "code": "RCH", "type": "cash", "company_id": company.id,
                "default_account_id": cash_account.id})
            cash.inbound_payment_method_line_ids.payment_account_id = outstanding
            partner = env["res.partner"].create({"name": "RCP Conc Customer", "is_company": True})
            partner.with_company(company).property_account_receivable_id = receivable
            collector = new_test_user(
                env, login=f"rcp-conc-{uuid.uuid4().hex[:10]}", groups="id_mobile_api.group_mobile_sales",
                company_id=company.id)
            control = new_test_user(
                env, login=f"rcp-ctl-{uuid.uuid4().hex[:10]}", groups="id_ar_collection.group_ar_control",
                company_id=company.id)
            accountants = [new_test_user(
                env, login=f"rcp-acc-{uuid.uuid4().hex[:10]}", groups="id_ar_collection.group_ar_accounting",
                company_id=company.id) for _ in range(2)]
            moves = env["account.move"]
            for _ in range(3):
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
                "line_ids": [Command.create({"move_id": move.id}) for move in moves[:2]]})
            sheet.action_issue()
            sheet2 = env["id.collection.sheet"].create({
                "company_id": company.id, "collector_id": collector.id, "collect_date": business_date(),
                "line_ids": [Command.create({"move_id": moves[2].id})]})
            sheet2.action_issue()
            return {
                "company": company.id, "receivable": receivable.id, "income": income.id, "general": general.id,
                "journals": (sales | general | cash).ids, "cash_journal": cash.id,
                "accounts": (receivable | income | cash_account | outstanding).ids, "partner": partner.id,
                "accountants": [user.id for user in accountants],
                "collector": collector.id, "control": control.id, "moves": sorted(moves.ids)[:2], "sheet": sheet.id,
                "lines": {line.move_id.id: line.id for line in sheet.line_ids},
                "sheet2": sheet2.id, "move2": moves[2].id, "line2": sheet2.line_ids.id,
                "all_moves_fixture": sorted(moves.ids),
            }

    def _cleanup_fixture(self, db, ids):
        """Hapus semua yang di-commit; kegagalan membersihkan SENGAJA tidak ditelan (mencemari langkah CI lain)."""
        with db.cursor() as cr:
            cr.execute("SET LOCAL lock_timeout = '20s'")
            sheets = [ids["sheet"], ids["sheet2"]]
            cr.execute("DELETE FROM id_collection_receipt_line WHERE move_id = ANY(%s)", (ids["all_moves_fixture"],))
            cr.execute("DELETE FROM account_payment WHERE partner_id = %s", (ids["partner"],))
            cr.execute("DELETE FROM id_collection_receipt WHERE sheet_id = ANY(%s)", (sheets,))
            cr.execute("DELETE FROM id_mobile_command WHERE user_id = %s", (ids["collector"],))
            cr.execute("DELETE FROM id_collection_sheet_line WHERE sheet_id = ANY(%s)", (sheets,))
            cr.execute("DELETE FROM id_collection_sheet WHERE id = ANY(%s)", (sheets,))
            cr.execute(
                "SELECT DISTINCT move_id FROM account_move_line WHERE partner_id = %s", (ids["partner"],))
            all_moves = [row[0] for row in cr.fetchall()]
            cr.execute(
                "DELETE FROM account_partial_reconcile WHERE debit_move_id IN "
                "(SELECT id FROM account_move_line WHERE move_id = ANY(%s)) OR credit_move_id IN "
                "(SELECT id FROM account_move_line WHERE move_id = ANY(%s))", (all_moves, all_moves))
            cr.execute("SELECT DISTINCT full_reconcile_id FROM account_move_line "
                       "WHERE move_id = ANY(%s) AND full_reconcile_id IS NOT NULL", (all_moves,))
            full_ids = [row[0] for row in cr.fetchall()]
            cr.execute("UPDATE account_move_line SET full_reconcile_id = NULL WHERE move_id = ANY(%s)", (all_moves,))
            cr.execute("DELETE FROM account_full_reconcile WHERE id = ANY(%s)", (full_ids,))
            cr.execute("DELETE FROM account_move_line WHERE move_id = ANY(%s)", (all_moves,))
            cr.execute("DELETE FROM account_move WHERE id = ANY(%s)", (all_moves,))
            env = api.Environment(cr, SUPERUSER_ID, {})
            env["account.journal"].browse(ids["journals"]).unlink()
            cr.execute("UPDATE res_users SET active = FALSE WHERE id = ANY(%s)",
                       ([ids["collector"], ids["control"], *ids["accountants"]],))  # arsip, tanpa hapus
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

        outcome["pid"] = cr._cnx.get_backend_pid()

        def runner():
            try:
                # Meniru Odoo `service.model.retrying`: cursor REPEATABLE READ yang menunggu lock baris lalu melihat
                # baris itu diubah transaksi lain gagal SerializationFailure dan permintaan diulang utuh.
                for attempt in range(3):
                    try:
                        # SerializationFailure yang diharapkan dicatat odoo.sql_db sebagai ERROR; gerbang "log harus
                        # bersih" CI menolaknya, jadi dibisukan hanya di sini.
                        with mute_logger("odoo.sql_db"):
                            outcome["result"] = work(thread_env)
                        break
                    except errors.SerializationFailure:
                        outcome["retries"] = attempt + 1
                        cr._cnx.rollback()
                        thread_env.invalidate_all()
                        cr.execute("SET LOCAL lock_timeout = '20s'")
                else:
                    raise AssertionError("serialization failure berulang")
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

    def _assert_blocked_by(self, db, waiter_pid, holder_pid):
        """Bukti di database: sesi penunggu benar-benar diblokir sesi pemegang lock (bukan sekadar lambat)."""
        with db.cursor() as cr:
            cr.execute("SELECT wait_event_type, pg_blocking_pids(%s) FROM pg_stat_activity WHERE pid = %s",
                       (waiter_pid, waiter_pid))
            wait_type, blockers = cr.fetchone()
        self.assertEqual(wait_type, "Lock", "sesi harus menunggu lock PostgreSQL")
        self.assertIn(holder_pid, blockers, "pemblokir harus sesi pemegang lock")

    def _sheet_row(self, db, ids):
        with db.cursor() as cr:
            cr.execute("SELECT state FROM id_collection_sheet WHERE id = %s", (ids["sheet"],))
            return cr.fetchone()[0]

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

    # ---- (c) pembatalan/kembali-ke-draf SJP vs submit penerimaan -------------------------------------------
    def test_submit_wins_then_cancel_is_rejected_and_sheet_stays_issued(self):
        db, ids = self._setup()
        cr1 = db.cursor()
        cr1.execute("SET LOCAL lock_timeout = '20s'")
        env1 = api.Environment(cr1, ids["collector"], {})
        outcome = {}
        try:
            result = env1["id.mobile.command"].process_command(self._command(ids, [ids["moves"][0]]))
            self.assertEqual(result["status"], "accepted")
            env1.flush_all()

            def cancel(env_t):
                env_t["id.collection.sheet"].browse(ids["sheet"]).action_cancel()
                env_t.flush_all()

            thread = self._run_in_thread(db, cancel, outcome, SUPERUSER_ID)
            time.sleep(WAIT)
            self.assertTrue(thread.is_alive(), "pembatalan harus menunggu submit yang belum commit")
            self._assert_blocked_by(db, outcome["pid"], cr1._cnx.get_backend_pid())
            cr1.commit()
        finally:
            cr1.close()
        thread.join(JOIN)
        self.assertFalse(thread.is_alive(), "menggantung" + self._hang_report(db, thread))
        self.assertGreaterEqual(outcome.get("retries", 0), 1, "menunggu pada snapshot lama harus diulang ala Odoo")
        self.assertIsInstance(outcome.get("error"), UserError, "pembatalan harus ditolak: ada penerimaan pending")
        self.assertEqual(self._sheet_row(db, ids), "issued")
        receipts, commands = self._db_state(db, ids)
        self.assertEqual((receipts, commands), (1, {"accepted": 1}))

    def test_cancel_wins_then_submit_is_rejected_without_receipt(self):
        db, ids = self._setup()
        cr1 = db.cursor()
        cr1.execute("SET LOCAL lock_timeout = '20s'")
        env1 = api.Environment(cr1, SUPERUSER_ID, {})
        outcome = {}
        try:
            env1["id.collection.sheet"].browse(ids["sheet"]).action_cancel()
            env1.flush_all()

            def submit(env2):
                result = env2["id.mobile.command"].process_command(self._command(ids, [ids["moves"][0]]))
                env2.flush_all()
                return result

            thread = self._run_in_thread(db, submit, outcome, ids["collector"])
            time.sleep(WAIT)
            self.assertTrue(thread.is_alive(), "submit harus menunggu pembatalan yang belum commit")
            self._assert_blocked_by(db, outcome["pid"], cr1._cnx.get_backend_pid())
            cr1.commit()
        finally:
            cr1.close()
        thread.join(JOIN)
        self.assertFalse(thread.is_alive(), "menggantung" + self._hang_report(db, thread))
        self.assertNotIn("error", outcome, outcome.get("error"))
        self.assertEqual((outcome["result"]["status"], outcome["result"]["reference"]), ("rejected", "sheet_state"))
        self.assertEqual(self._sheet_row(db, ids), "cancelled")
        receipts, commands = self._db_state(db, ids)
        self.assertEqual((receipts, commands), (0, {"rejected": 1}))

    # ---- (d) cron penutupan akhir hari vs submit setelah cutoff ----------------------------------------------
    def _setup_past_cutoff(self):
        db, ids = self._setup()
        with db.cursor() as cr:  # mundurkan hari SJP: cutoff (00:00 WITA hari berikutnya) sudah lewat
            cr.execute("UPDATE id_collection_sheet SET collect_date = collect_date - 1 WHERE id = ANY(%s)",
                       ([ids["sheet"], ids["sheet2"]],))
        return db, ids

    def _closed_state(self, db, ids):
        with db.cursor() as cr:
            cr.execute("SELECT state FROM id_collection_sheet WHERE id = %s", (ids["sheet"],))
            state = cr.fetchone()[0]
            cr.execute(
                "SELECT outcome, active_claim FROM id_collection_sheet_line WHERE sheet_id = %s", (ids["sheet"],))
            lines = cr.fetchall()
        return state, lines

    def test_cron_holds_lock_then_late_submit_waits_and_is_rejected_without_receipt(self):
        db, ids = self._setup_past_cutoff()
        cr1 = db.cursor()
        cr1.execute("SET LOCAL lock_timeout = '20s'")
        env1 = api.Environment(cr1, SUPERUSER_ID, {})
        outcome = {}
        try:
            self.assertEqual(len(env1["id.collection.sheet"].browse(ids["sheet"])._close_settlement_day()), 1)
            env1.flush_all()

            def submit(env2):
                result = env2["id.mobile.command"].process_command(self._command(ids, [ids["moves"][0]]))
                env2.flush_all()
                return result

            thread = self._run_in_thread(db, submit, outcome, ids["collector"])
            time.sleep(WAIT)
            self.assertTrue(thread.is_alive(), "submit harus menunggu cron yang belum commit")
            self._assert_blocked_by(db, outcome["pid"], cr1._cnx.get_backend_pid())
            cr1.commit()
        finally:
            cr1.close()
        thread.join(JOIN)
        self.assertFalse(thread.is_alive(), "menggantung" + self._hang_report(db, thread))
        self.assertNotIn("error", outcome, outcome.get("error"))
        self.assertEqual(outcome["result"]["status"], "rejected")
        self.assertGreaterEqual(outcome.get("retries", 0), 1)
        self.assertEqual(self._closed_state(db, ids), ("expired", [("lapsed", False), ("lapsed", False)]))
        self.assertEqual(self._db_state(db, ids), (0, {"rejected": 1}))

    def test_late_submit_holds_lock_then_cron_waits_and_is_idempotent(self):
        db, ids = self._setup_past_cutoff()
        cr1 = db.cursor()
        cr1.execute("SET LOCAL lock_timeout = '20s'")
        env1 = api.Environment(cr1, ids["collector"], {})
        outcome = {}
        try:
            result = env1["id.mobile.command"].process_command(self._command(ids, [ids["moves"][0]]))
            self.assertEqual((result["status"], result["reference"]), ("rejected", "cutoff"))
            env1.flush_all()

            def cron(env_t):
                closed = env_t["id.collection.sheet"].browse(ids["sheet"])._close_settlement_day()
                env_t.flush_all()
                return len(closed)

            thread = self._run_in_thread(db, cron, outcome, SUPERUSER_ID)
            time.sleep(WAIT)
            self.assertTrue(thread.is_alive(), "cron harus menunggu submit yang belum commit")
            self._assert_blocked_by(db, outcome["pid"], cr1._cnx.get_backend_pid())
            cr1.commit()
        finally:
            cr1.close()
        thread.join(JOIN)
        self.assertFalse(thread.is_alive(), "menggantung" + self._hang_report(db, thread))
        self.assertNotIn("error", outcome, outcome.get("error"))
        self.assertEqual(outcome["result"], 0, "cron tidak boleh menutup dua kali")
        self.assertEqual(self._closed_state(db, ids), ("expired", [("lapsed", False), ("lapsed", False)]))
        self.assertEqual(self._db_state(db, ids), (0, {"rejected": 1}))

    # ---- (e) custody exception: token sama paralel dan custody vs submit setelah cutoff ---------------------
    @staticmethod
    def _custody_args(ids, token):
        return (ids["sheet"], token, "Setoran terlambat", datetime.now(timezone.utc).isoformat(), [{
            "line_id": ids["lines"][ids["moves"][0]], "invoice_id": ids["moves"][0], "outcome": "paid",
            "amount": 1000, "expected_balance": 1000}])

    def test_same_custody_token_in_parallel_creates_one_receipt(self):
        db, ids = self._setup_past_cutoff()
        cr1 = db.cursor()
        cr1.execute("SET LOCAL lock_timeout = '20s'")
        env1 = api.Environment(cr1, ids["control"], {})
        outcome = {}
        args = self._custody_args(ids, "TOK-PAR")  # payload identik (termasuk waktu) pada kedua permintaan
        try:
            first = env1["id.collection.receipt"].record_custody_exception(*args)
            env1.flush_all()

            def again(env2):
                receipts = env2["id.collection.receipt"].record_custody_exception(*args)
                env2.flush_all()
                return receipts.ids

            thread = self._run_in_thread(db, again, outcome, ids["control"])
            time.sleep(WAIT)
            self.assertTrue(thread.is_alive(), "token kedua harus menunggu yang pertama")
            self._assert_blocked_by(db, outcome["pid"], cr1._cnx.get_backend_pid())
            first_ids = first.ids
            cr1.commit()
        finally:
            cr1.close()
        thread.join(JOIN)
        self.assertFalse(thread.is_alive(), "menggantung" + self._hang_report(db, thread))
        self.assertNotIn("error", outcome, outcome.get("error"))
        self.assertEqual(outcome["result"], first_ids, "retry token sama mengembalikan receipt yang sama")
        self.assertEqual(self._db_state(db, ids)[0], 1)

    def test_custody_vs_late_submit_serialize_to_one_allocation(self):
        db, ids = self._setup_past_cutoff()
        cr1 = db.cursor()
        cr1.execute("SET LOCAL lock_timeout = '20s'")
        env1 = api.Environment(cr1, ids["control"], {})
        outcome = {}
        try:
            receipts = env1["id.collection.receipt"].record_custody_exception(*self._custody_args(ids, "TOK-RACE"))
            self.assertEqual(receipts.line_ids.allocation_state, "allocated")
            env1.flush_all()

            def submit(env2):
                result = env2["id.mobile.command"].process_command(self._command(ids, [ids["moves"][0]]))
                env2.flush_all()
                return result

            thread = self._run_in_thread(db, submit, outcome, ids["collector"])
            time.sleep(WAIT)
            self.assertTrue(thread.is_alive(), "submit harus menunggu custody yang belum commit")
            self._assert_blocked_by(db, outcome["pid"], cr1._cnx.get_backend_pid())
            cr1.commit()
        finally:
            cr1.close()
        thread.join(JOIN)
        self.assertFalse(thread.is_alive(), "menggantung" + self._hang_report(db, thread))
        self.assertNotIn("error", outcome, outcome.get("error"))
        self.assertEqual(outcome["result"]["status"], "rejected")
        self.assertEqual(self._db_state(db, ids), (1, {"rejected": 1}))  # satu receipt (custody), tanpa ganda

    def test_same_token_across_sheets_and_methods_cannot_both_win(self):
        db, ids = self._setup_past_cutoff()
        cr1 = db.cursor()
        cr1.execute("SET LOCAL lock_timeout = '20s'")
        env1 = api.Environment(cr1, ids["control"], {})
        outcome = {}
        occurred = datetime.now(timezone.utc).isoformat()
        try:
            first = env1["id.collection.receipt"].record_custody_exception(*self._custody_args(ids, "TOK-X"))
            self.assertEqual(first.method, "cash")
            env1.flush_all()

            def other_sheet(env2):  # SJP dan metode berbeda, token sama
                env2["id.collection.receipt"].record_custody_exception(
                    ids["sheet2"], "TOK-X", "Setoran terlambat", occurred, [{
                        "line_id": ids["line2"], "invoice_id": ids["move2"], "outcome": "paid", "amount": 1000,
                        "expected_balance": 1000, "method": "transfer", "transfer": {"reference": "TRX-1"}}])
                env2.flush_all()

            thread = self._run_in_thread(db, other_sheet, outcome, ids["control"])
            time.sleep(WAIT)
            self.assertTrue(thread.is_alive(), "operasi kedua harus menunggu pemegang token pertama")
            self._assert_blocked_by(db, outcome["pid"], cr1._cnx.get_backend_pid())
            cr1.commit()
        finally:
            cr1.close()
        thread.join(JOIN)
        self.assertFalse(thread.is_alive(), "menggantung" + self._hang_report(db, thread))
        self.assertIsInstance(outcome.get("error"), UserError, "token tidak boleh mengikat dua operasi")
        with db.cursor() as cr:
            cr.execute("SELECT count(*) FROM id_collection_receipt WHERE desk_token = 'TOK-X'")
            self.assertEqual(cr.fetchone()[0], 1)

    # ---- (f) meja kasir tunai vs command mobile pada faktur yang sama: satu menang ------------------------
    def _desk_args(self, ids, token="DESK-RACE"):
        return (ids["sheet"], token, datetime.now(timezone.utc).isoformat(), [{
            "line_id": ids["lines"][ids["moves"][0]], "invoice_id": ids["moves"][0], "outcome": "paid",
            "amount": 1000, "expected_balance": 1000}])

    def test_cashier_desk_holds_lock_then_mobile_command_waits_and_is_rejected(self):
        db, ids = self._setup()
        cr1 = db.cursor()
        cr1.execute("SET LOCAL lock_timeout = '20s'")
        env1 = api.Environment(cr1, ids["control"], {})
        outcome = {}
        try:
            receipt = env1["id.collection.receipt"].record_desk_cash(*self._desk_args(ids))
            self.assertEqual(receipt.state, "cashier_validated")
            env1.flush_all()

            def submit(env2):
                result = env2["id.mobile.command"].process_command(self._command(ids, [ids["moves"][0]]))
                env2.flush_all()
                return result

            thread = self._run_in_thread(db, submit, outcome, ids["collector"])
            time.sleep(WAIT)
            self.assertTrue(thread.is_alive(), "command mobile harus menunggu meja kasir yang belum commit")
            self._assert_blocked_by(db, outcome["pid"], cr1._cnx.get_backend_pid())
            cr1.commit()
        finally:
            cr1.close()
        thread.join(JOIN)
        self.assertFalse(thread.is_alive(), "menggantung" + self._hang_report(db, thread))
        self.assertNotIn("error", outcome, outcome.get("error"))
        self.assertEqual(outcome["result"]["status"], "rejected")
        self.assertEqual(self._db_state(db, ids), (1, {"rejected": 1}))  # satu menang: receipt meja kasir

    def test_mobile_command_holds_lock_then_cashier_desk_waits_and_is_rejected(self):
        db, ids = self._setup()
        cr1 = db.cursor()
        cr1.execute("SET LOCAL lock_timeout = '20s'")
        env1 = api.Environment(cr1, ids["collector"], {})
        outcome = {}
        try:
            result = env1["id.mobile.command"].process_command(self._command(ids, [ids["moves"][0]]))
            self.assertEqual(result["status"], "accepted")
            env1.flush_all()

            def desk(env2):
                env2["id.collection.receipt"].record_desk_cash(*self._desk_args(ids))
                env2.flush_all()

            thread = self._run_in_thread(db, desk, outcome, ids["control"])
            time.sleep(WAIT)
            self.assertTrue(thread.is_alive(), "meja kasir harus menunggu command mobile yang belum commit")
            self._assert_blocked_by(db, outcome["pid"], cr1._cnx.get_backend_pid())
            cr1.commit()
        finally:
            cr1.close()
        thread.join(JOIN)
        self.assertFalse(thread.is_alive(), "menggantung" + self._hang_report(db, thread))
        self.assertIsInstance(outcome.get("error"), UserError, "baris sudah punya klaim mobile: validasi, bukan baru")
        self.assertEqual(self._db_state(db, ids), (1, {"accepted": 1}))


    # ---- (g) validasi accounting vs penolakan / validasi ganda (BE-20e 2/n) ----------------------------------
    def _desk_receipt(self, db, ids):
        """Receipt tunai meja kasir ter-commit (state cashier_validated); kembalikan id."""
        with db.cursor() as cr:
            env = api.Environment(cr, ids["control"], {})
            receipt = env["id.collection.receipt"].record_desk_cash(*self._desk_args(ids))
            env.flush_all()
            receipt_id = receipt.id
            cr.commit()
        return receipt_id

    def _accounting_state(self, db, ids, receipt_id):
        with db.cursor() as cr:
            cr.execute("SELECT state FROM id_collection_receipt WHERE id = %s", (receipt_id,))
            state = cr.fetchone()[0]
            cr.execute("SELECT count(*) FROM account_payment WHERE partner_id = %s", (ids["partner"],))
            payments = cr.fetchone()[0]
            cr.execute("SELECT COALESCE(SUM(amount_residual), 0) FROM account_move_line "
                       "WHERE move_id = %s AND display_type = 'payment_term'", (ids["moves"][0],))
            residual = float(cr.fetchone()[0])
            cr.execute("SELECT count(*) FROM id_collection_receipt_line WHERE receipt_id = %s AND holds_invoice",
                       (receipt_id,))
            holds = cr.fetchone()[0]
        return state, payments, residual, holds

    def _race_accounting(self, first, second, expect_state, expect_payments, expect_residual, expect_holds):
        """`first` ditahan terbuka oleh transaksi 1; `second` berjalan di thread dan harus MENUNGGU lalu gagal."""
        db, ids = self._setup()
        receipt_id = self._desk_receipt(db, ids)
        cr1 = db.cursor()
        cr1.execute("SET LOCAL lock_timeout = '20s'")
        env1 = api.Environment(cr1, ids["accountants"][0], {})
        outcome = {}
        try:
            first(env1, ids, receipt_id)
            env1.flush_all()

            def work(env2):
                second(env2, ids, receipt_id)
                env2.flush_all()

            thread = self._run_in_thread(db, work, outcome, ids["accountants"][1])
            time.sleep(WAIT)
            self.assertTrue(thread.is_alive(), "transaksi kedua harus menunggu yang belum commit")
            self._assert_blocked_by(db, outcome["pid"], cr1._cnx.get_backend_pid())
            cr1.commit()
        finally:
            cr1.close()
        thread.join(JOIN)
        self.assertFalse(thread.is_alive(), "menggantung" + self._hang_report(db, thread))
        self.assertIsInstance(outcome.get("error"), UserError, outcome)  # yang kalah ditolak setelah baca ulang
        self.assertEqual(
            self._accounting_state(db, ids, receipt_id), (expect_state, expect_payments, expect_residual, expect_holds))

    @staticmethod
    def _validate(env, ids, receipt_id):
        env["id.collection.receipt"].browse(receipt_id).accounting_validate(ids["cash_journal"])

    @staticmethod
    def _reject(env, ids, receipt_id):
        env["id.collection.receipt"].browse(receipt_id).reject_receipt("Uang tidak diterima")

    def test_validation_wins_then_reject_waits_and_is_refused_with_exactly_one_payment(self):
        self._race_accounting(self._validate, self._reject, "accounting_validated", 1, 0.0, 0)

    def test_reject_wins_then_validation_waits_and_posts_no_payment(self):
        self._race_accounting(self._reject, self._validate, "rejected", 0, 1000.0, 0)

    def test_double_validation_posts_exactly_one_payment(self):
        self._race_accounting(self._validate, self._validate, "accounting_validated", 1, 0.0, 0)
