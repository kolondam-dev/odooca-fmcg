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
