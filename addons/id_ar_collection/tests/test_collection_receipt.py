"""BE-20d: command `collection.receipt.submit` melalui dispatcher produksi (`process_command`)."""
import uuid
from datetime import timedelta

from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo import Command, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger

from odoo.addons.id_base.models.business_day import business_date
from odoo.addons.id_mobile_api.models.mobile_workday import MobileReadConflict

from ..models.collection_receipt import ONE_PENDING_PER_MOVE, ONE_PER_SHEET_LINE, COMMAND_METHOD_INDEX

NOW_UTC = "2026-11-24 02:00:00"  # 10:00 WITA, 24 November 2026
OCCURRED = "2026-11-24T10:00:00+08:00"
CUTOFF_UTC = "2026-11-24 16:00:00"  # 00:00 WITA 25 November


@tagged("post_install", "-at_install")
class TestCollectionReceipt(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        currency = cls.env.ref("base.IDR")
        currency.active = True
        cls.company = cls.env["res.company"].create({"name": "RCP Co", "currency_id": currency.id})
        cls.receivable = cls._account("1159901", "AR RCP Test", "asset_receivable")
        cls.income = cls._account("4400901", "Income RCP Test", "income")
        cls.journal = cls.env["account.journal"].create({
            "name": "Sales RCP", "code": "RCP", "type": "sale", "company_id": cls.company.id})
        cls.collector = new_test_user(
            cls.env, login="rcp-collector", groups="id_mobile_api.group_mobile_sales", company_id=cls.company.id)
        cls.other = new_test_user(
            cls.env, login="rcp-other", groups="id_mobile_api.group_mobile_sales", company_id=cls.company.id)
        cls.admin = new_test_user(
            cls.env, login="rcp-admin", groups="id_ar_collection.group_ar_admin", company_id=cls.company.id)

    @classmethod
    def _account(cls, code, name, account_type):
        return cls.env["account.account"].create({
            "name": name, "code": code, "account_type": account_type,
            "company_ids": [Command.set(cls.company.ids)]})

    def setUp(self):
        super().setUp()
        self.frozen = freeze_time(NOW_UTC, tick=False)
        self.clock = self.frozen.start()
        self.addCleanup(self.frozen.stop)
        self.partner = self.env["res.partner"].create({"name": "RCP Outlet", "street": "RCP Street"})
        self.partner.with_company(self.company).property_account_receivable_id = self.receivable

    # ---- helpers -------------------------------------------------------------------------------
    def _invoice(self, amount=100000.0):
        day = business_date()
        move = self.env["account.move"].with_company(self.company).create({
            "move_type": "out_invoice", "company_id": self.company.id, "journal_id": self.journal.id,
            "partner_id": self.partner.id, "invoice_date": day - timedelta(days=30), "invoice_date_due": day,
            "invoice_line_ids": [Command.create({
                "name": "RCP line", "quantity": 1.0, "price_unit": amount, "account_id": self.income.id})],
        })
        move.action_post()
        return move

    def _sheet(self, moves, collector=None):
        sheet = self.env["id.collection.sheet"].create({
            "company_id": self.company.id, "collector_id": (collector or self.collector).id,
            "collect_date": business_date(),
            "line_ids": [Command.create({"move_id": move.id}) for move in moves],
        })
        sheet.action_issue()
        return sheet

    def _line_of(self, sheet, move):
        return sheet.line_ids.filtered(lambda line: line.move_id == move)

    def _entry(self, sheet, move, outcome="paid", amount=None, **extra):
        balance = move.amount_residual
        if amount is None:
            amount = {"paid": balance, "partial": balance / 2, "unpaid": 0}[outcome]
        entry = {
            "line_id": self._line_of(sheet, move).id, "invoice_id": move.id, "outcome": outcome,
            "amount": amount, "expected_balance": balance, **extra,
        }
        if outcome == "unpaid":
            entry.setdefault("unpaid_reason", "closed")
        return entry

    def _command(self, sheet, entries, occurred=OCCURRED, client_uuid=None):
        return {
            "client_uuid": client_uuid or str(uuid.uuid4()), "type": "collection.receipt.submit",
            "payload": {"sheet_id": sheet.id, "occurred_at": occurred, "lines": entries},
        }

    def _submit(self, command, user=None):
        user = user or self.collector
        return self.env["id.mobile.command"].with_user(user).process_command(command)

    def _receipts(self, sheet):
        return self.env["id.collection.receipt"].sudo().search([("sheet_id", "=", sheet.id)])

    def _logged(self, command):
        return self.env["id.mobile.command"].sudo().search([
            ("client_uuid", "=", command["client_uuid"]), ("user_id", "=", self.collector.id)])

    def _payments(self):
        return self.env["account.payment"].sudo().search_count([("partner_id", "=", self.partner.id)])

    # ---- sukses --------------------------------------------------------------------------------
    def test_paid_partial_unpaid_create_one_posted_receipt_without_any_payment(self):
        paid, partial, unpaid = self._invoice(100000), self._invoice(100000), self._invoice(100000)
        sheet = self._sheet([paid, partial, unpaid])
        payments_before = self._payments()
        command = self._command(sheet, [
            self._entry(sheet, paid, "paid"), self._entry(sheet, partial, "partial", 40000),
            self._entry(sheet, unpaid, "unpaid"),
        ])
        result = self._submit(command)
        self.assertEqual(result["status"], "accepted")
        receipt = self._receipts(sheet)
        self.assertEqual((len(receipt), receipt.state, receipt.method, receipt.source), (1, "posted", "cash", "mobile"))
        self.assertEqual(result["reference"], receipt.name)
        self.assertEqual(receipt.amount_total, 140000.0)
        by_move = {line.move_id: line for line in receipt.line_ids}
        self.assertEqual(by_move[paid].document_return, "copy")
        self.assertEqual(by_move[unpaid].document_return, "original")
        self.assertEqual(self._line_of(sheet, partial).outcome, "partial")
        self.assertEqual(self._line_of(sheet, partial).collected_amount, 40000.0)
        self.assertFalse(by_move[unpaid].holds_invoice)  # unpaid nol: tanpa proteksi pending
        self.assertTrue(by_move[unpaid].holds_line)
        self.assertTrue(by_move[paid].holds_invoice and by_move[partial].holds_invoice)
        # 20d tidak membuat pembayaran dan tidak mengubah saldo faktur.
        self.assertEqual(self._payments(), payments_before)
        self.assertEqual((paid.amount_residual, partial.amount_residual), (100000.0, 100000.0))

    def test_retry_same_uuid_returns_same_result_and_one_receipt(self):
        move = self._invoice()
        sheet = self._sheet([move])
        command = self._command(sheet, [self._entry(sheet, move)])
        first = self._submit(command)
        self.assertEqual(self._submit(command), first)
        self.assertEqual(len(self._receipts(sheet)), 1)
        with self.assertRaises(MobileReadConflict):  # UUID sama, payload berbeda = konflik
            self._submit({**command, "payload": {**command["payload"], "lines": []}})

    def test_outlet_id_hint_is_ignored(self):
        move = self._invoice()
        sheet = self._sheet([move])
        entry = self._entry(sheet, move, outlet_id=999999)
        self.assertEqual(self._submit(self._command(sheet, [entry]))["status"], "accepted")

    # ---- rollback atomik dan penolakan persisten -----------------------------------------------
    def test_second_line_stale_balance_rejects_everything_and_logs_once(self):
        first, second = self._invoice(), self._invoice()
        sheet = self._sheet([first, second])
        stale = self._entry(sheet, second, "paid", expected_balance=1.0)
        command = self._command(sheet, [self._entry(sheet, first), stale])
        result = self._submit(command)
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(self._receipts(sheet))
        self.assertEqual(set(sheet.line_ids.mapped("outcome")), {"pending"})  # tidak ada outcome tersisa
        self.assertEqual(len(self._logged(command)), 1)
        self.assertEqual(self._submit(command), result)  # retry identik: hasil sama

    def test_new_uuid_for_reported_line_is_rejected_with_single_active_receipt(self):
        move = self._invoice()
        sheet = self._sheet([move])
        self.assertEqual(self._submit(self._command(sheet, [self._entry(sheet, move)]))["status"], "accepted")
        result = self._submit(self._command(sheet, [self._entry(sheet, move)]))
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(len(self._receipts(sheet)), 1)

    @mute_logger("odoo.sql_db")
    def test_database_indexes_are_the_last_guard(self):
        move, other_move = self._invoice(), self._invoice()
        sheet = self._sheet([move, other_move])
        self._submit(self._command(sheet, [self._entry(sheet, move)]))
        receipt = self._receipts(sheet)
        line = receipt.line_ids
        cr = self.env.cr
        columns = (
            "receipt_id, sheet_line_id, move_id, outcome, allocation_state, document_return, company_id, "
            "amount, holds_line, holds_invoice"
        )
        insert = (
            f"INSERT INTO id_collection_receipt_line ({columns}) "
            "VALUES (%s, %s, %s, 'paid', 'allocated', 'copy', %s, 5, %s, %s)"
        )
        # satu penerimaan aktif per baris SJP
        with self.assertRaises(IntegrityError) as clash:
            with cr.savepoint():
                cr.execute(insert, (receipt.id, line.sheet_line_id.id, other_move.id, self.company.id, True, False))
        self.assertEqual(clash.exception.diag.constraint_name, ONE_PER_SHEET_LINE)
        # satu penerimaan pending per faktur lintas baris/SJP
        with self.assertRaises(IntegrityError) as pending:
            with cr.savepoint():
                cr.execute(
                    insert,
                    (receipt.id, self._line_of(sheet, other_move).id, move.id, self.company.id, True, True),
                )
        self.assertEqual(pending.exception.diag.constraint_name, ONE_PENDING_PER_MOVE)
        # satu receipt per (kolektor, UUID command, metode)
        cr.execute(
            "SELECT collector_id, command_uuid, method FROM id_collection_receipt WHERE id = %s", (receipt.id,))
        collector_id, command_uuid, method = cr.fetchone()
        with self.assertRaises(IntegrityError) as dup:
            with cr.savepoint():
                cr.execute(
                    "INSERT INTO id_collection_receipt (name, sheet_id, company_id, collector_id, command_uuid,"
                    " method, source, state) VALUES ('X', %s, %s, %s, %s, %s, 'mobile', 'posted')",
                    (sheet.id, self.company.id, collector_id, command_uuid, method))
        self.assertEqual(dup.exception.diag.constraint_name, COMMAND_METHOD_INDEX)

    # ---- identitas dan otorisasi ---------------------------------------------------------------
    def test_identity_is_loaded_from_server(self):
        move, other_move = self._invoice(), self._invoice()
        sheet = self._sheet([move])
        other_sheet = self._sheet([other_move], collector=self.other)
        with self.assertRaises(AccessError):  # SJP kolektor lain: generik, tidak dicatat
            command = self._command(other_sheet, [self._entry(other_sheet, other_move)])
            self._submit(command)
        self.assertFalse(self._logged(command))
        with self.assertRaises(UserError):  # baris dari SJP lain
            self._submit(self._command(sheet, [{**self._entry(other_sheet, other_move)}]))
        with self.assertRaises(UserError):  # invoice_id tidak cocok dengan baris
            self._submit(self._command(sheet, [{**self._entry(sheet, move), "invoice_id": other_move.id}]))
        with self.assertRaises(UserError):  # line_id duplikat
            entry = self._entry(sheet, move)
            self._submit(self._command(sheet, [entry, dict(entry)]))
        self.assertFalse(self._receipts(sheet))

    def test_malformed_payloads_are_not_logged(self):
        move = self._invoice()
        sheet = self._sheet([move])
        base = self._entry(sheet, move)
        bad_commands = [
            self._command(sheet, [base], occurred="2026-11-24T10:00:00"),  # tanpa zona waktu
            self._command(sheet, []),
            self._command(sheet, [{**base, "outcome": "refund"}]),
            self._command(sheet, [{**base, "amount": True}]),
            self._command(sheet, [{**base, "amount": "NaN"}]),
            self._command(sheet, [{**base, "amount": -5}]),
            self._command(sheet, [{**base, "method": "crypto"}]),
            self._command(sheet, [{**base, "outcome": "partial", "amount": 100000.0}]),  # partial = saldo
            self._command(sheet, [{**base, "outcome": "paid", "amount": 1.0}]),  # paid != saldo
            self._command(sheet, [{**base, "outcome": "unpaid", "amount": 5, "unpaid_reason": "closed"}]),
            self._command(sheet, [{**base, "outcome": "unpaid", "amount": 0}]),  # alasan wajib
            self._command(sheet, [{**base, "amount": 100000.5}]),  # presisi mata uang
        ]
        for command in bad_commands:
            with self.assertRaises(UserError):
                self._submit(command)
            self.assertFalse(self._logged(command))
        self.assertFalse(self._receipts(sheet))

    # ---- saldo, status SJP, hari -----------------------------------------------------------------
    def test_balance_changed_by_another_channel_is_rejected_without_effect(self):
        move = self._invoice()
        sheet = self._sheet([move])
        command = self._command(sheet, [self._entry(sheet, move)])
        self.env.cr.execute(
            "UPDATE account_move_line SET amount_residual = 30000 WHERE move_id = %s AND display_type = 'payment_term'",
            (move.id,))
        result = self._submit(command)
        self.assertEqual((result["status"], result["reference"]), ("rejected", "balance"))
        self.assertFalse(self._receipts(sheet))
        self.assertEqual(self._line_of(sheet, move).outcome, "pending")

    def test_non_issued_sheet_is_rejected(self):
        move = self._invoice()
        sheet = self._sheet([move])
        command = self._command(sheet, [self._entry(sheet, move)])
        sheet.action_cancel()
        self.assertEqual(self._submit(command)["reference"], "sheet_state")
        self.assertFalse(self._receipts(sheet))

    def test_after_midnight_wita_command_is_rejected_even_without_cron(self):
        move = self._invoice()
        sheet = self._sheet([move])
        command = self._command(sheet, [self._entry(sheet, move)])
        self.clock.move_to(CUTOFF_UTC)
        result = self._submit(command)
        self.assertEqual((result["status"], result["reference"]), ("rejected", "cutoff"))
        self.assertFalse(self._receipts(sheet))
        self.assertEqual(self._submit(command), result)  # retry: hasil sama, tidak loop

    def test_just_before_cutoff_is_accepted(self):
        move = self._invoice()
        sheet = self._sheet([move])
        self.clock.move_to("2026-11-24 15:59:59")
        command = self._command(sheet, [self._entry(sheet, move)], occurred="2026-11-24T23:59:00+08:00")
        self.assertEqual(self._submit(command)["status"], "accepted")

    def test_occurred_at_must_be_on_collect_day_and_not_future(self):
        move = self._invoice()
        sheet = self._sheet([move])
        for occurred in ("2026-11-23T23:59:00+08:00", "2026-11-24T10:30:00+08:00"):  # kemarin; di masa depan
            result = self._submit(self._command(sheet, [self._entry(sheet, move)], occurred=occurred))
            self.assertEqual((result["status"], result["reference"]), ("rejected", "occurred_at"))
        self.assertFalse(self._receipts(sheet))

    # ---- metode ------------------------------------------------------------------------------------
    def test_mixed_methods_split_into_one_receipt_per_method_atomically(self):
        cash, transfer, giro, unpaid = (self._invoice() for _ in range(4))
        sheet = self._sheet([cash, transfer, giro, unpaid])
        entries = [
            self._entry(sheet, giro, "paid", method="giro",
                        giro={"number": "G-1", "bank": "BCA", "due_date": "2026-12-05"}),
            self._entry(sheet, transfer, "paid", method="transfer", transfer={"reference": "TRF-9"}),
            self._entry(sheet, cash, "paid"),
            self._entry(sheet, unpaid, "unpaid"),
        ]
        result = self._submit(self._command(sheet, entries))
        receipts = self._receipts(sheet).sorted("id")
        self.assertEqual(receipts.mapped("method"), ["cash", "transfer", "giro"])  # urutan tetap
        self.assertEqual(result["reference"], ",".join(receipts.mapped("name")))
        self.assertEqual(len(receipts.filtered(lambda r: r.method == "cash").line_ids), 2)  # cash + unpaid

    def test_invalid_method_data_creates_nothing(self):
        good, bad = self._invoice(), self._invoice()
        sheet = self._sheet([good, bad])
        for broken in (
            self._entry(sheet, bad, "paid", method="transfer"),  # tanpa referensi/bukti
            self._entry(sheet, bad, "paid", method="giro", giro={"number": "G-1"}),  # bank/jatuh tempo hilang
            self._entry(sheet, bad, "unpaid", method="transfer"),  # unpaid tidak memakai transfer
        ):
            with self.assertRaises(UserError):
                self._submit(self._command(sheet, [self._entry(sheet, good), broken]))
        self.assertFalse(self._receipts(sheet))

    # ---- pending lintas SJP ---------------------------------------------------------------------
    def test_pending_receipt_protects_invoice_across_sheets_until_released(self):
        move = self._invoice()
        sheet = self._sheet([move])
        self._submit(self._command(sheet, [self._entry(sheet, move, "partial", 40000)]))
        with self.assertRaises(UserError):  # tidak dapat dibatalkan/didraf selama ada uang pending
            sheet.action_cancel()
        sheet._apply_state("returned")  # `returned` tidak melepas proteksi
        with self.assertRaises(ValidationError):  # faktur tidak boleh masuk SJP lain
            self._sheet([move], collector=self.other)
        wizard = self.env["id.collection.sheet.generate"].with_user(self.admin).create({
            "company_id": self.company.id, "due_until": business_date() + timedelta(days=1)})
        self.assertNotIn(move.id, wizard._candidates()[0].ids)
        # Dilepas hanya oleh status receipt (seam 20e): rejected -> faktur kembali menjadi kandidat.
        models.Model.write(self._receipts(sheet), {"state": "rejected"})
        self.env.flush_all()
        self.assertEqual(self._receipts(sheet).line_ids.mapped("holds_invoice"), [False])
        self.assertIn(move.id, wizard._candidates()[0].ids)

    # ---- akses ------------------------------------------------------------------------------------
    def test_receipts_are_read_only_for_everyone_and_scoped_for_collectors(self):
        move = self._invoice()
        sheet = self._sheet([move])
        self._submit(self._command(sheet, [self._entry(sheet, move)]))
        receipt = self._receipts(sheet)
        with self.assertRaises(UserError):
            receipt.write({"state": "accounting_validated"})
        with self.assertRaises(UserError):
            receipt.unlink()
        with self.assertRaises(UserError):
            receipt.line_ids.write({"amount": 1})
        with self.assertRaises(AccessError):
            self.env["id.collection.receipt"].with_user(self.collector).create({
                "sheet_id": sheet.id, "company_id": self.company.id, "collector_id": self.collector.id,
                "method": "cash"})
        self.assertEqual(receipt.with_user(self.collector).name, receipt.name)
        self.assertFalse(self.env["id.collection.receipt"].with_user(self.other).search([("id", "=", receipt.id)]))
        admin_view = self.env["id.collection.receipt"].with_user(self.admin).search([("id", "=", receipt.id)])
        self.assertEqual(admin_view, receipt)

    def test_unsupported_without_valid_payload_fails_closed(self):
        with self.assertRaises(UserError):
            self._submit({"client_uuid": str(uuid.uuid4()), "type": "collection.receipt.submit", "payload": {}})

    # ---- penutupan akhir hari (D10-Q5a, 8.13-4) -----------------------------------------------------
    def _lock_free_candidate(self, move):
        """Faktur kembali kandidat: dapat dimasukkan ke SJP baru tanpa bentrok klaim atau pending."""
        sheet = self.env["id.collection.sheet"].create({
            "company_id": self.company.id, "collector_id": self.other.id, "collect_date": business_date(),
            "line_ids": [Command.create({"move_id": move.id})]})
        return sheet

    def test_closing_before_cutoff_is_noop(self):
        move = self._invoice()
        sheet = self._sheet([move])
        self.clock.move_to("2026-11-24 15:59:59")
        self.assertFalse(sheet._close_settlement_day())
        self.assertEqual((sheet.state, self._line_of(sheet, move).outcome), ("issued", "pending"))

    def test_closing_without_any_receipt_expires_sheet_and_frees_invoices(self):
        first, second = self._invoice(), self._invoice()
        sheet = self._sheet([first, second])
        with self.assertRaises(ValidationError):  # selama aktif, faktur terklaim
            self._lock_free_candidate(first)
        self.clock.move_to(CUTOFF_UTC)
        self.assertEqual(sheet._close_settlement_day(), sheet)
        self.assertEqual(sheet.state, "expired")
        self.assertEqual({line.outcome for line in sheet.line_ids}, {"lapsed"})
        self.assertFalse(any(sheet.line_ids.mapped("active_claim")))
        self._lock_free_candidate(first)  # kembali kandidat: tanpa lubang atau loop
        self.assertFalse(sheet._close_settlement_day())  # idempoten
        with self.assertRaises(UserError):  # terminal
            sheet.action_cancel()
        command = self._command(sheet, [self._entry(sheet, second)])
        self.assertEqual(self._submit(command)["status"], "rejected")
        self.assertFalse(self._receipts(sheet))

    def test_closing_keeps_reported_lines_and_lapses_only_the_rest(self):
        reported, silent = self._invoice(), self._invoice()
        sheet = self._sheet([reported, silent])
        self.assertEqual(self._submit(self._command(sheet, [self._entry(sheet, reported)]))["status"], "accepted")
        self.clock.move_to(CUTOFF_UTC)
        self.assertEqual(sheet._close_settlement_day(), sheet)
        self.assertEqual(sheet.state, "issued")  # penerimaan pending lanjut ke validasi (20e)
        self.assertEqual(self._line_of(sheet, reported).outcome, "paid")
        self.assertTrue(self._line_of(sheet, reported).active_claim)
        self.assertEqual(self._line_of(sheet, silent).outcome, "lapsed")
        self.assertFalse(self._line_of(sheet, silent).active_claim)
        self._lock_free_candidate(silent)
        with self.assertRaises(ValidationError):  # faktur dengan uang pending tetap terproteksi
            self._lock_free_candidate(reported)
        self.assertFalse(sheet._close_settlement_day())  # idempoten
        self.assertEqual(self._line_of(sheet, reported).outcome, "paid")

    def test_cron_catches_up_idempotently_and_skips_fully_reported_sheets(self):
        silent_move, reported_move = self._invoice(), self._invoice()
        silent = self._sheet([silent_move])
        reported = self._sheet([reported_move], collector=self.other)
        self.assertEqual(
            self._submit(self._command(reported, [self._entry(reported, reported_move)]), user=self.other)["status"],
            "accepted")
        self.env["id.collection.sheet"]._cron_close_settlement_day()  # sebelum cutoff: SJP uji tidak tersentuh
        self.assertEqual((silent.state, silent.line_ids.outcome), ("issued", "pending"))
        self.clock.move_to("2026-11-25 02:00:00")  # 10:00 WITA hari berikutnya
        self.assertGreaterEqual(self.env["id.collection.sheet"]._cron_close_settlement_day(), 1)
        self.assertEqual((silent.state, reported.state), ("expired", "issued"))
        self.assertEqual(self.env["id.collection.sheet"]._cron_close_settlement_day(), 0)

    # ---- command setelah cutoff menutup SJP di bawah lock walau cron belum berjalan (§8.13-4) ------------
    def _residual(self, move):
        self.env.flush_all()
        self.env.cr.execute("SELECT amount_residual FROM account_move WHERE id = %s", (move.id,))
        return self.env.cr.fetchone()[0]

    def _logs(self, command):
        return self.env["id.mobile.command"].sudo().search([("client_uuid", "=", command["client_uuid"])])

    def test_command_after_cutoff_before_cron_persists_rejection_and_closes_sheet(self):
        first, second = self._invoice(), self._invoice()
        sheet = self._sheet([first, second])
        balances = (self._residual(first), self._residual(second))
        command = self._command(sheet, [self._entry(sheet, first)])
        self.clock.move_to(CUTOFF_UTC)
        result = self._submit(command)  # cron belum berjalan
        self.assertEqual((result["status"], result["reference"]), ("rejected", "cutoff"))
        self.assertFalse(self._receipts(sheet))
        self.assertEqual((self._residual(first), self._residual(second)), balances)
        self.assertEqual(sheet.state, "expired")
        self.assertEqual({line.outcome for line in sheet.line_ids}, {"lapsed"})
        self.assertFalse(any(sheet.line_ids.mapped("active_claim")))
        self._lock_free_candidate(first)  # klaim terlepas: kembali kandidat tanpa menunggu cron
        self.assertEqual(len(self._logs(command)), 1)
        # Replay UUID: hasil sama, tidak ada log baru, tidak ada efek ganda.
        self.assertEqual(self._submit(command), result)
        self.assertEqual(len(self._logs(command)), 1)
        self.assertEqual(self.env["id.mobile.command"].sudo().search_count([
            ("client_uuid", "=", command["client_uuid"]), ("status", "=", "rejected")]), 1)
        self.assertFalse(sheet._close_settlement_day())  # cron sesudahnya: idempoten

    def test_command_after_cutoff_on_mixed_sheet_lapses_only_unreported_lines(self):
        reported, silent = self._invoice(), self._invoice()
        sheet = self._sheet([reported, silent])
        self.assertEqual(self._submit(self._command(sheet, [self._entry(sheet, reported)]))["status"], "accepted")
        pending_receipts = self._receipts(sheet)
        self.clock.move_to(CUTOFF_UTC)
        late = self._command(sheet, [self._entry(sheet, silent)])
        self.assertEqual(self._submit(late)["reference"], "cutoff")
        self.assertEqual(self._receipts(sheet), pending_receipts)  # uang pending tidak tersentuh
        self.assertEqual(sheet.state, "issued")
        self.assertEqual((self._line_of(sheet, reported).outcome, self._line_of(sheet, reported).active_claim),
                         ("paid", True))
        self.assertEqual((self._line_of(sheet, silent).outcome, self._line_of(sheet, silent).active_claim),
                         ("lapsed", False))
        self._lock_free_candidate(silent)
        with self.assertRaises(ValidationError):
            self._lock_free_candidate(reported)

    # ---- custody exception (rancangan 8.12) ------------------------------------------------------------------
    CUSTODY_OCCURRED = "2026-11-24T22:00:00+08:00"

    def _control(self):
        return new_test_user(
            self.env, login=f"rcp-control-{uuid.uuid4().hex[:6]}", groups="id_ar_collection.group_ar_control",
            company_id=self.company.id)

    def _custody(self, sheet, move, token="TOK-1", user=None, reason="Setoran terlambat", **entry_extra):
        line = self._line_of(sheet, move)
        entry = {"line_id": line.id, "invoice_id": move.id, "outcome": "paid", "amount": move.amount_residual,
                 "expected_balance": move.amount_residual, **entry_extra}
        model = self.env["id.collection.receipt"].with_user(user or self._control())
        return model.record_custody_exception(sheet.id, token, reason, self.CUSTODY_OCCURRED, [entry])

    def test_custody_after_close_is_recorded_allocated_and_idempotent(self):
        move = self._invoice()
        sheet = self._sheet([move])
        balance = self._residual(move)
        self.clock.move_to(CUTOFF_UTC)  # cron belum berjalan: custody menormalkan SJP lebih dulu
        control = self._control()
        receipt = self._custody(sheet, move, user=control)
        self.assertEqual((receipt.source, receipt.exception, receipt.state, receipt.exception_reason),
                         ("cashier_desk", True, "posted", "Setoran terlambat"))
        line = receipt.line_ids
        self.assertEqual((line.allocation_state, line.holds_invoice, line.amount), ("allocated", True, balance))
        self.assertEqual((sheet.state, self._line_of(sheet, move).outcome), ("expired", "lapsed"))
        self.assertEqual(self._residual(move), balance)  # pembayaran/rekonsiliasi baru di 20e
        with self.assertRaises(ValidationError):  # alokasi memegang proteksi pending
            self._lock_free_candidate(move)
        self.assertEqual(self._custody(sheet, move, user=control), receipt)  # retry token sama: hasil sama
        self.assertEqual(self.env["id.collection.receipt"].sudo().search_count([("sheet_id", "=", sheet.id)]), 1)
        other = self._invoice()
        other_sheet = self._sheet([other])
        with self.assertRaises(UserError):  # token milik SJP lain
            self._custody(other_sheet, other, user=control)

    def test_custody_requires_control_cutoff_reason_and_method_proof(self):
        move = self._invoice()
        sheet = self._sheet([move])
        with self.assertRaises(UserError):  # sebelum cutoff: pakai jalur biasa
            self._custody(sheet, move)
        self.clock.move_to(CUTOFF_UTC)
        with self.assertRaises(AccessError):
            self._custody(sheet, move, user=self.admin)  # group_ar_admin saja tidak cukup
        with self.assertRaises(UserError):
            self._custody(sheet, move, reason="")
        with self.assertRaises(UserError):
            self._custody(sheet, move, method="transfer")  # transfer wajib referensi/bukti
        with self.assertRaises(UserError):
            self._custody(sheet, move, outcome="unpaid", amount=0, unpaid_reason="closed")
        self.assertTrue(self._custody(sheet, move, method="transfer", transfer={"reference": "TRX-9"}))

    def test_custody_is_held_when_invoice_is_in_another_sheet_then_reassigned(self):
        move = self._invoice()
        sheet = self._sheet([move])
        self.clock.move_to(CUTOFF_UTC)
        sheet._close_settlement_day()
        other_sheet = self._sheet([move], collector=self.other)  # B menagih faktur yang sama
        other_line = self._line_of(other_sheet, move)
        control = self._control()
        receipt = self._custody(sheet, move, user=control)
        line = receipt.line_ids
        self.assertEqual((line.allocation_state, line.holds_invoice, line.holds_line), ("held", False, True))
        self.assertTrue(other_line.active_claim)  # klaim B utuh; indeks pending tidak diambil baris held
        line.with_user(control).resolve_held("reassign", "B belum menagih")
        self.assertEqual((line.allocation_state, line.holds_invoice, line.resolution_by), ("allocated", True, control))
        self.assertEqual((other_line.outcome, other_line.active_claim), ("lapsed", False))
        self.assertIn(receipt.name, other_line.unpaid_reason)
        with self.assertRaises(UserError):  # sudah tidak held
            line.with_user(control).resolve_held("release", "lagi")

    def test_custody_held_against_pending_receipt_can_only_be_released(self):
        move = self._invoice()
        sheet = self._sheet([move])
        self.clock.move_to(CUTOFF_UTC)
        sheet._close_settlement_day()
        other_sheet = self._sheet([move], collector=self.other)
        self.assertEqual(self._submit(self._command(
            other_sheet, [self._entry(other_sheet, move)], occurred="2026-11-25T00:00:00+08:00"),
            user=self.other)["status"], "accepted")
        control = self._control()
        receipt = self._custody(sheet, move, user=control)
        line = receipt.line_ids
        self.assertEqual(line.allocation_state, "held")
        with self.assertRaises(UserError):
            line.with_user(control).resolve_held("reassign", "coba")
        line.with_user(control).resolve_held("release", "faktur sudah dibayar lewat SJP lain")
        self.assertEqual((line.allocation_state, line.holds_invoice, line.holds_line), ("released", False, True))
        pending = self.env["id.collection.receipt.line"].sudo().search([
            ("move_id", "=", move.id), ("holds_invoice", "=", True)])
        self.assertEqual(len(pending), 1)  # satu alokasi sah per faktur: milik B
        self.assertEqual(pending.receipt_id.sheet_id, other_sheet)

    def _pay_elsewhere(self, move, amount):
        """Pelunasan lewat jalur lain: jurnal umum mengkredit piutang lalu rekonsiliasi native."""
        general = self.env["account.journal"].search([("code", "=", "RCPG"), ("company_id", "=", self.company.id)]) \
            or self.env["account.journal"].create({
                "name": "RCP General", "code": "RCPG", "type": "general", "company_id": self.company.id})
        entry = self.env["account.move"].with_company(self.company).create({
            "move_type": "entry", "journal_id": general.id, "date": business_date(),
            "line_ids": [
                Command.create({"account_id": self.receivable.id, "partner_id": self.partner.id,
                                "credit": amount, "debit": 0.0}),
                Command.create({"account_id": self.income.id, "debit": amount, "credit": 0.0}),
            ]})
        entry.action_post()
        lines = move.line_ids.filtered(lambda line: line.display_type == "payment_term")
        lines |= entry.line_ids.filtered(lambda line: line.account_id == self.receivable)
        lines.reconcile()

    def test_custody_is_recorded_held_when_invoice_is_already_paid_or_balance_changed(self):
        paid, changed, fresh = self._invoice(1000), self._invoice(1000), self._invoice(1000)
        sheet = self._sheet([paid, changed, fresh])
        self.clock.move_to(CUTOFF_UTC)
        control = self._control()
        entries = [{
            "line_id": self._line_of(sheet, move).id, "invoice_id": move.id, "outcome": "paid", "amount": 1000.0,
            "expected_balance": 1000.0, "method": method, **extra,
        } for move, method, extra in [
            (paid, "cash", {}), (changed, "transfer", {"transfer": {"reference": "TRX-7"}}), (fresh, "cash", {})]]
        self._pay_elsewhere(paid, 1000)  # lunas lewat jalur lain
        self._pay_elsewhere(changed, 400)  # saldo berubah menjadi 600
        residuals = [self._residual(move) for move in (paid, changed, fresh)]
        receipts = self.env["id.collection.receipt"].with_user(control).record_custody_exception(
            sheet.id, "TOK-MIX", "Setoran terlambat", self.CUSTODY_OCCURRED, entries)
        self.assertEqual(sorted(receipts.mapped("method")), ["cash", "transfer"])  # uang tercatat utuh, tanpa penolakan
        states = {line.move_id: line.allocation_state for line in receipts.line_ids}
        self.assertEqual(states, {paid: "held", changed: "held", fresh: "allocated"})
        self.assertEqual(receipts.line_ids.filtered(lambda line: line.move_id == paid).amount, 1000.0)  # nominal utuh
        self.assertEqual([self._residual(move) for move in (paid, changed, fresh)], residuals)  # saldo tak diubah
        self.assertFalse(receipts.line_ids.filtered(lambda line: line.allocation_state == "held").mapped(
            "holds_invoice").count(True))
        with self.assertRaises(UserError):  # reassign tidak mungkin: saldo tidak cukup; hanya release
            receipts.line_ids.filtered(lambda line: line.move_id == changed).with_user(control).resolve_held(
                "reassign", "coba")
        receipts.line_ids.filtered(lambda line: line.move_id == changed).with_user(control).resolve_held(
            "release", "saldo sudah berubah")

    def test_custody_token_binds_the_whole_operation_and_payload(self):
        move = self._invoice(1000)
        sheet = self._sheet([move])
        self.clock.move_to(CUTOFF_UTC)
        control = self._control()
        receipt = self._custody(sheet, move, token="TOK-BIND", user=control)
        self.assertEqual(self._custody(sheet, move, token="TOK-BIND", user=control), receipt)  # replay identik
        with self.assertRaises(UserError):  # nominal berbeda, token sama: bukan permintaan baru
            self._custody(sheet, move, token="TOK-BIND", user=control, outcome="partial", amount=400.0)
        with self.assertRaises(UserError):  # alasan berbeda, token sama
            self._custody(sheet, move, token="TOK-BIND", user=control, reason="alasan lain")
        self.assertEqual(self.env["id.collection.receipt"].sudo().search_count([("desk_token", "=", "TOK-BIND")]), 1)

    # ---- BE-20e 1/n: kasir tunai (8.11) ----------------------------------------------------------------------
    def _cashier(self):
        return new_test_user(
            self.env, login=f"rcp-cashier-{uuid.uuid4().hex[:6]}", groups="id_ar_collection.group_ar_cashier",
            company_id=self.company.id)

    def _desk(self, sheet, moves, token="DESK-1", user=None, occurred="2026-11-24T10:00:00+08:00", **extra):
        entries = [self._entry(sheet, move, **extra) for move in moves]
        model = self.env["id.collection.receipt"].with_user(user or self._cashier())
        return model.record_desk_cash(sheet.id, token, occurred, entries)

    def test_cashier_desk_cash_is_cashier_validated_allocated_and_idempotent(self):
        move = self._invoice()
        sheet = self._sheet([move])
        cashier = self._cashier()
        receipt = self._desk(sheet, [move], user=cashier)
        self.assertEqual((receipt.source, receipt.exception, receipt.state, receipt.method),
                         ("cashier_desk", False, "cashier_validated", "cash"))
        self.assertEqual((receipt.cashier_id, bool(receipt.cashier_validated_at)), (cashier, True))
        line = receipt.line_ids
        self.assertEqual((line.allocation_state, line.holds_invoice, line.counted_amount, line.difference),
                         ("allocated", True, line.amount, 0.0))
        sheet_line = self._line_of(sheet, move)
        self.assertEqual((sheet_line.outcome, sheet_line.collected_amount), ("paid", line.amount))
        self.assertEqual(sheet.state, "issued")
        with self.assertRaises(ValidationError):  # proteksi pending
            self._lock_free_candidate(move)
        self.assertEqual(self._desk(sheet, [move], user=cashier), receipt)  # token sama, payload sama
        self.assertEqual(self.env["id.collection.receipt"].sudo().search_count([("sheet_id", "=", sheet.id)]), 1)
        self.clock.move_to(CUTOFF_UTC)  # penutupan tidak menyentuh baris yang sudah dilaporkan
        sheet._close_settlement_day()
        self.assertEqual((sheet.state, sheet_line.outcome), ("issued", "paid"))

    def test_cashier_desk_rejects_wrong_actor_method_stale_balance_and_existing_claim_atomically(self):
        first, second = self._invoice(), self._invoice()
        sheet = self._sheet([first, second])
        with self.assertRaises(AccessError):
            self._desk(sheet, [first], user=self.admin)
        with self.assertRaises(UserError):  # transfer/giro tidak memakai jalan pintas kasir
            self._desk(sheet, [first], method="transfer", transfer={"reference": "TRX-1"})
        stale = self._entry(sheet, second)
        stale["expected_balance"] += 1
        model = self.env["id.collection.receipt"].with_user(self._cashier())
        with self.assertRaises(UserError):  # satu baris basi menolak seluruh operasi
            model.record_desk_cash(
                sheet.id, "DESK-ATOM", "2026-11-24T10:00:00+08:00", [self._entry(sheet, first), stale])
        self.assertFalse(self._receipts(sheet))
        self.assertEqual(self._line_of(sheet, first).outcome, "pending")  # tak ada efek sebagian
        self.assertEqual(self._submit(self._command(sheet, [self._entry(sheet, first)]))["status"], "accepted")
        with self.assertRaises(UserError):  # sudah ada klaim mobile: validasi, bukan buat baru
            self._desk(sheet, [first], token="DESK-2")
        self.clock.move_to(CUTOFF_UTC)
        with self.assertRaises(UserError):  # sesudah penutupan: custody
            self._desk(sheet, [second], token="DESK-3", occurred="2026-11-24T23:00:00+08:00")

    def test_cashier_validates_mobile_cash_claim_with_recorded_difference(self):
        move = self._invoice()
        sheet = self._sheet([move])
        self.assertEqual(self._submit(self._command(sheet, [self._entry(sheet, move)]))["status"], "accepted")
        receipt = self._receipts(sheet)
        line = receipt.line_ids
        claim = line.amount
        cashier = self._cashier()
        model = receipt.with_user(cashier)
        with self.assertRaises(AccessError):
            receipt.with_user(self.admin).validate_cash({line.id: claim})
        with self.assertRaises(UserError):  # hitungan harus memuat seluruh baris
            model.validate_cash({})
        with self.assertRaises(UserError):  # selisih wajib catatan
            model.validate_cash({line.id: claim - 50})
        model.validate_cash({line.id: claim - 50}, "Kurang 50 rb, diakui kolektor")
        self.assertEqual((receipt.state, receipt.cashier_id), ("cashier_validated", cashier))
        self.assertEqual((line.amount, line.counted_amount, line.difference), (claim, claim - 50, -50.0))
        self.assertEqual(line.difference_note, "Kurang 50 rb, diakui kolektor")
        self.assertTrue(line.holds_invoice)  # klaim tetap utuh dan terproteksi
        with self.assertRaises(UserError):  # tidak dapat divalidasi dua kali
            model.validate_cash({line.id: claim})

    def test_cashier_cannot_validate_non_cash_claims(self):
        move = self._invoice()
        sheet = self._sheet([move])
        entry = self._entry(sheet, move, method="transfer", transfer={"reference": "TRX-5"})
        self.assertEqual(self._submit(self._command(sheet, [entry]))["status"], "accepted")
        receipt = self._receipts(sheet)
        with self.assertRaises(UserError):
            receipt.with_user(self._cashier()).validate_cash({receipt.line_ids.id: receipt.line_ids.amount})

    def test_sheet_cannot_be_returned_before_cashier_counts_cash(self):
        move = self._invoice()
        sheet = self._sheet([move])
        self.assertEqual(self._submit(self._command(sheet, [self._entry(sheet, move)]))["status"], "accepted")
        receipt = self._receipts(sheet)
        with self.assertRaises(UserError):
            sheet.sudo()._apply_state("returned")
        receipt.with_user(self._cashier()).validate_cash({receipt.line_ids.id: receipt.line_ids.amount})
        sheet.sudo()._apply_state("returned")
        self.assertEqual(sheet.state, "returned")

