"""BE-20b: Surat Jalan Penagihan (SJP): generate dari AR terbuka, banyak SJP, unpaid kembali ke kandidat."""
import threading
import time
from datetime import timedelta

from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo import SUPERUSER_ID, Command, api, sql_db
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger

from odoo.addons.id_base.models.business_day import business_date


@tagged("post_install", "-at_install")
class TestCollectionSheet(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        currency = cls.env.ref("base.IDR")
        currency.active = True
        cls.company = cls.env["res.company"].create({"name": "SJP Co", "currency_id": currency.id})
        cls.foreign = cls.env["res.company"].create({"name": "SJP Foreign Co", "currency_id": currency.id})
        cls.acc_rec, cls.acc_inc, cls.journal = {}, {}, {}
        for idx, company in enumerate((cls.company, cls.foreign)):
            cls.acc_rec[company.id] = cls._account(company, f"1139{idx}1", "AR SJP Test", "asset_receivable")
            cls.acc_inc[company.id] = cls._account(company, f"4200{idx}1", "Income SJP Test", "income")
            cls.journal[company.id] = cls.env["account.journal"].create({
                "name": f"Sales SJP{idx}", "code": f"SJ{idx}", "type": "sale", "company_id": company.id,
            })
        cls.admin = new_test_user(
            cls.env, login="sjp-ar-admin", groups="id_ar_collection.group_ar_admin", company_id=cls.company.id)
        cls.collector = new_test_user(
            cls.env, login="sjp-collector", groups="id_mobile_api.group_mobile_sales", company_id=cls.company.id)
        cls.other = new_test_user(
            cls.env, login="sjp-other-collector", groups="id_mobile_api.group_mobile_sales",
            company_id=cls.company.id)
        cls.principal = cls.env["id.principal"].create({"name": "SJP Principal", "code": "SJP-TEST"})
        cls.product = cls.env["product.product"].create({
            "name": "SJP Product", "default_code": "SJP-SKU", "principal_id": cls.principal.id,
            "company_id": False, "uom_id": cls.env.ref("uom.product_uom_unit").id, "list_price": 1000,
            "carton_qty": 24, "inner_qty": 6, "type": "consu", "is_storable": True,
            "taxes_id": [Command.clear()],
        })
        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        if not cls.warehouse:
            cls.warehouse = cls.env["stock.warehouse"].create({
                "name": "SJP Stock", "code": "SJPW", "company_id": cls.company.id})
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "SJP IDR", "currency_id": cls.company.currency_id.id, "company_id": cls.company.id})

    @classmethod
    def _account(cls, company, code, name, account_type):
        return cls.env["account.account"].create({
            "name": name, "code": code, "account_type": account_type, "company_ids": [Command.set(company.ids)],
        })

    # ---- helpers -------------------------------------------------------------------------------
    def _partner(self, name, **vals):
        vals.setdefault("street", "SJP Street")
        partner = self.env["res.partner"].create({"name": name, **vals})
        for company in (self.company, self.foreign):
            partner.with_company(company).property_account_receivable_id = self.acc_rec[company.id]
        return partner

    def _invoice(self, partner, due, amount=100000.0, company=None, currency=None):
        company = company or self.company
        move = self.env["account.move"].with_company(company).create({
            "move_type": "out_invoice", "company_id": company.id, "journal_id": self.journal[company.id].id,
            "partner_id": partner.id, "invoice_date": due - timedelta(days=30), "invoice_date_due": due,
            **({"currency_id": currency.id} if currency else {}),
            "invoice_line_ids": [Command.create({
                "name": "SJP line", "quantity": 1.0, "price_unit": amount,
                "account_id": self.acc_inc[company.id].id,
            })],
        })
        move.action_post()
        return move

    def _settle(self, move, residual):
        state = "paid" if residual == 0 else "partial"
        self.env.cr.execute(
            "UPDATE account_move SET payment_state=%s, amount_residual=%s, amount_residual_signed=%s WHERE id=%s",
            (state, residual, residual, move.id))
        move.invalidate_recordset(["payment_state", "amount_residual", "amount_residual_signed"])

    def _assign(self, user, *outlets):
        self.env["id.mobile.workday"].create({
            "user_id": user.id, "company_id": self.company.id, "business_date": business_date(),
            "warehouse_id": self.warehouse.id, "pricelist_id": self.pricelist.id,
            "product_ids": [Command.set(self.product.ids)],
            "outlet_ids": [Command.set([o.id for o in outlets])],
        })

    def _wizard(self, **vals):
        vals.setdefault("company_id", self.company.id)
        return self.env["id.collection.sheet.generate"].with_user(self.admin).create(vals)

    def _generate(self, **vals):
        action = self._wizard(**vals).action_generate()
        return self.env["id.collection.sheet"].browse(action["res_id"])

    # ---- generate ------------------------------------------------------------------------------
    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_generate_by_due_date_includes_overdue_and_partial_excludes_paid_and_future(self):
        day = business_date()
        outlet = self._partner("SJP Outlet", is_company=True)
        late = self._invoice(outlet, day - timedelta(days=30), 1000)
        today = self._invoice(outlet, day, 2000)
        partial = self._invoice(outlet, day, 3000)
        self._settle(partial, 1200)
        paid = self._invoice(outlet, day, 4000)
        self._settle(paid, 0)
        future = self._invoice(outlet, day + timedelta(days=1), 5000)
        foreign = self._invoice(outlet, day, 6000, company=self.foreign)
        sheet = self._generate()
        self.assertEqual(sheet.state, "draft")
        self.assertTrue(sheet.name.startswith("SJP/"))
        self.assertEqual(set(sheet.line_ids.move_id.ids), {late.id, today.id, partial.id})
        self.assertNotIn(future.id, sheet.line_ids.move_id.ids)
        self.assertNotIn(foreign.id, sheet.line_ids.move_id.ids)
        self.assertEqual(sheet.line_ids.filtered(lambda line: line.move_id == partial).amount_due, 1200.0)
        self.assertEqual(sheet.amount_total, 4200.0)
        self.assertEqual(sheet.line_count, 3)

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_due_until_widens_the_window(self):
        day = business_date()
        outlet = self._partner("SJP Advance", is_company=True)
        self._invoice(outlet, day, 100)
        ahead = self._invoice(outlet, day + timedelta(days=5), 200)
        sheet = self._generate(due_until=day + timedelta(days=5))
        self.assertIn(ahead.id, sheet.line_ids.move_id.ids)
        self.assertEqual(sheet.line_count, 2)

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_many_sheets_never_share_an_active_invoice_and_cancel_releases(self):
        day = business_date()
        a = self._partner("SJP Many A", is_company=True, delivery_route="RT-A")
        b = self._partner("SJP Many B", is_company=True, delivery_route="RT-B")
        inv_a = self._invoice(a, day, 100)
        inv_b = self._invoice(b, day, 200)
        first = self._generate(route="RT-A")
        second = self._generate(route="RT-B")  # banyak SJP pada hari yang sama diperbolehkan
        self.assertEqual(first.line_ids.move_id, inv_a)
        self.assertEqual(second.line_ids.move_id, inv_b)
        # Faktur yang sudah pada SJP aktif tidak lagi jadi kandidat.
        with self.assertRaises(UserError):
            self._generate(route="RT-A")
        self.assertEqual(self._wizard(route="RT-A").candidate_count, 0)
        first.action_cancel()
        self.assertEqual(self._wizard(route="RT-A").candidate_count, 1)
        third = self._generate(route="RT-A")
        self.assertEqual(third.line_ids.move_id, inv_a)

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_unpaid_invoice_is_candidate_again_once_sheet_is_returned(self):
        day = business_date()
        outlet = self._partner("SJP Unpaid", is_company=True)
        move = self._invoice(outlet, day, 100)
        sheet = self._generate()
        sheet.collector_id = self.collector
        sheet.action_issue()
        sheet.line_ids._apply_outcome({"outcome": "unpaid", "unpaid_reason": "Pemilik tidak ada"})
        self.assertEqual(self._wizard().candidate_count, 0)
        sheet._apply_state("returned")  # seam internal; aksi publik menyusul di BE-20e
        wizard = self._wizard()
        self.assertEqual(wizard.candidate_count, 1)
        self.assertEqual(wizard._candidates()[0], move)

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_collector_filter_uses_assigned_outlets_with_commercial_parent(self):
        day = business_date()
        parent = self._partner("SJP Parent", is_company=True)
        child = self._partner("SJP Child", parent_id=parent.id, type="contact")
        elsewhere = self._partner("SJP Elsewhere", is_company=True)
        inv_parent = self._invoice(parent, day, 100)
        inv_child = self._invoice(child, day, 200)
        self._invoice(elsewhere, day, 300)
        self._assign(self.collector, child)
        sheet = self._generate(collector_id=self.collector.id)
        self.assertEqual(set(sheet.line_ids.move_id.ids), {inv_parent.id, inv_child.id})
        self.assertEqual(sheet.collector_id, self.collector)

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_collector_without_assignment_is_refused_with_message(self):
        self._invoice(self._partner("SJP NoPJP", is_company=True), business_date(), 100)
        wizard = self._wizard(collector_id=self.other.id)
        self.assertIn("penugasan", wizard.warning)
        self.assertEqual(wizard.candidate_count, 0)
        with self.assertRaises(UserError):
            wizard.action_generate()

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_empty_candidates_refused(self):
        with self.assertRaises(UserError):
            self._generate()

    # ---- transisi dan batasan ------------------------------------------------------------------
    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_issue_requires_collector_and_lines_and_cancel_flow(self):
        self._invoice(self._partner("SJP Flow", is_company=True), business_date(), 100)
        sheet = self._generate()
        with self.assertRaises(UserError):
            sheet.action_issue()  # tanpa kolektor
        sheet.collector_id = self.collector
        sheet.action_issue()
        self.assertEqual(sheet.state, "issued")
        with self.assertRaises(UserError):
            sheet.unlink()  # bukan draf
        sheet.action_cancel()
        self.assertEqual(sheet.state, "cancelled")
        sheet.action_draft()
        self.assertEqual(sheet.state, "draft")
        sheet.unlink()

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_same_invoice_cannot_be_forced_onto_two_active_sheets(self):
        move = self._invoice(self._partner("SJP Clash", is_company=True), business_date(), 100)
        first = self._generate()
        self.assertEqual(first.line_ids.move_id, move)
        other = self.env["id.collection.sheet"].create({"company_id": self.company.id})
        with self.assertRaises(ValidationError):
            self.env["id.collection.sheet.line"].create(
                {"sheet_id": other.id, "move_id": move.id, "amount_due": 100})

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_only_posted_customer_invoices_allowed(self):
        partner = self._partner("SJP Draft", is_company=True)
        draft = self.env["account.move"].create({
            "move_type": "out_invoice", "company_id": self.company.id,
            "journal_id": self.journal[self.company.id].id, "partner_id": partner.id,
            "invoice_date": business_date(),
            "invoice_line_ids": [Command.create({
                "name": "x", "quantity": 1, "price_unit": 5, "account_id": self.acc_inc[self.company.id].id})],
        })
        sheet = self.env["id.collection.sheet"].create({"company_id": self.company.id})
        with self.assertRaises(ValidationError):
            self.env["id.collection.sheet.line"].create(
                {"sheet_id": sheet.id, "move_id": draft.id, "amount_due": 5})

    # ---- keamanan ------------------------------------------------------------------------------
    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_collector_reads_only_own_sheet_and_cannot_write(self):
        day = business_date()
        a = self._partner("SJP Sec A", is_company=True)
        b = self._partner("SJP Sec B", is_company=True)
        self._invoice(a, day, 100)
        self._invoice(b, day, 200)
        self._assign(self.collector, a)
        self._assign(self.other, b)
        mine = self._generate(collector_id=self.collector.id)
        theirs = self._generate(collector_id=self.other.id)
        seen = self.env["id.collection.sheet"].with_user(self.collector).search([])
        self.assertEqual(seen, mine)
        self.assertEqual(self.env["id.collection.sheet.line"].with_user(self.collector).search([]).sheet_id, mine)
        with self.assertRaises(AccessError):
            mine.with_user(self.collector).write({"note": "ubah"})
        with self.assertRaises(AccessError):
            theirs.with_user(self.collector).read(["name"])
        with self.assertRaises(AccessError):
            self.env["id.collection.sheet.generate"].with_user(self.collector).create(
                {"company_id": self.company.id})

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_company_isolation(self):
        sheet = self.env["id.collection.sheet"].with_company(self.foreign).create(
            {"company_id": self.foreign.id})
        seen = self.env["id.collection.sheet"].with_user(self.admin).search([("id", "=", sheet.id)])
        self.assertFalse(seen)

    # ---- PDF -----------------------------------------------------------------------------------
    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_report_renders_sheet_lines(self):
        outlet = self._partner("SJP Report Outlet", is_company=True)
        move = self._invoice(outlet, business_date(), 12345)
        sheet = self._generate()
        html = self.env["ir.actions.report"]._render_qweb_html(
            "id_ar_collection.report_collection_sheet", sheet.ids)[0].decode()
        self.assertIn(sheet.name, html)
        self.assertIn("SJP Report Outlet", html)
        self.assertIn(move.name, html)
        self.assertIn("12,345", html.replace(".", ","))

    # ---- P1: satu faktur, satu SJP aktif (reaktivasi dan indeks DB) ----------------------------
    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_cancelled_sheet_cannot_be_reactivated_while_invoice_is_active_elsewhere(self):
        move = self._invoice(self._partner("SJP Reactivate", is_company=True), business_date(), 100)
        sheet_a = self._generate()
        sheet_a.action_cancel()
        sheet_b = self._generate()
        self.assertEqual(sheet_b.line_ids.move_id, move)
        with self.assertRaises(UserError):
            sheet_a.action_draft()
        # Atomik: A tetap dibatalkan, B tidak berubah, hanya satu klaim aktif.
        (sheet_a | sheet_b).invalidate_recordset()
        self.assertEqual(sheet_a.state, "cancelled")
        self.assertEqual(sheet_b.state, "draft")
        claims = self.env["id.collection.sheet.line"].search([("move_id", "=", move.id), ("active_claim", "=", True)])
        self.assertEqual(claims.sheet_id, sheet_b)
        # Setelah B dibatalkan, A boleh dipulihkan (jalur sah tetap PASS).
        sheet_b.action_cancel()
        sheet_a.action_draft()
        self.assertEqual(sheet_a.state, "draft")

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_inactive_sheet_cannot_gain_lines_or_be_reparented(self):
        move = self._invoice(self._partner("SJP Reparent", is_company=True), business_date(), 100)
        sheet_a = self._generate()
        sheet_a.action_cancel()
        sheet_b = self._generate()
        with self.assertRaises(UserError):  # tambah baris pada sheet tidak aktif
            self.env["id.collection.sheet.line"].create({"sheet_id": sheet_a.id, "move_id": move.id})
        with self.assertRaises(UserError):  # reparent baris lewat write langsung
            sheet_b.line_ids.write({"sheet_id": sheet_a.id})

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_database_partial_unique_index_blocks_second_active_claim(self):
        move = self._invoice(self._partner("SJP Index", is_company=True), business_date(), 100)
        sheet_a = self._generate()
        sheet_a.action_cancel()
        self._generate()  # B aktif untuk faktur yang sama
        line_a = sheet_a.line_ids
        self.env.flush_all()
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env.cr.execute(
                "UPDATE id_collection_sheet_line SET active_claim = TRUE WHERE id = %s", (line_a.id,))
        claims = self.env["id.collection.sheet.line"].search_count(
            [("move_id", "=", move.id), ("active_claim", "=", True)])
        self.assertEqual(claims, 1)

    # ---- P2: lifecycle dan immutability dijaga server ------------------------------------------
    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_direct_create_and_write_cannot_bypass_state_machine(self):
        Sheet = self.env["id.collection.sheet"].with_user(self.admin)
        with self.assertRaises(UserError):
            Sheet.create({"company_id": self.company.id, "state": "issued"})
        sheet = Sheet.create({"company_id": self.company.id})
        for state in ("issued", "returned", "reconciled", "cancelled"):
            with self.assertRaises(UserError):
                sheet.write({"state": state})
        for field in ("name", "generated_by"):
            with self.assertRaises(UserError):
                sheet.write({field: "x" if field == "name" else self.collector.id})
        self.assertEqual(sheet.state, "draft")

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_illegal_transitions_and_context_flags_do_not_bypass(self):
        self._invoice(self._partner("SJP Trans", is_company=True), business_date(), 100)
        sheet = self._generate()
        for new_state in ("returned", "reconciled", "draft"):
            with self.assertRaises(UserError):
                sheet._apply_state(new_state)
        with self.assertRaises(UserError):
            sheet.with_user(self.admin).with_context(force_state="issued", install_mode=True).write(
                {"state": "issued"})
        sheet.collector_id = self.collector
        sheet.action_issue()
        sheet._apply_state("returned")
        sheet._apply_state("reconciled")
        self.assertEqual(sheet.state, "reconciled")
        with self.assertRaises(UserError):
            sheet._apply_state("draft")

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_issued_sheet_is_frozen(self):
        day = business_date()
        first = self._invoice(self._partner("SJP Frozen A", is_company=True), day, 100)
        extra = self._invoice(self._partner("SJP Frozen B", is_company=True), day + timedelta(days=1), 200)
        sheet = self._generate(due_until=day)
        sheet.collector_id = self.collector
        sheet.action_issue()
        admin_sheet = sheet.with_user(self.admin)
        for vals in (
            {"collector_id": self.other.id}, {"route": "RT-X"}, {"due_until": day + timedelta(days=1)},
            {"collect_date": day + timedelta(days=1)}, {"company_id": self.foreign.id},
        ):
            with self.assertRaises(UserError):
                admin_sheet.write(vals)
        with self.assertRaises(UserError):
            admin_sheet.write({"line_ids": [Command.clear()]})
        admin_sheet.write({"note": "catatan boleh"})
        line = sheet.line_ids
        with self.assertRaises(UserError):
            self.env["id.collection.sheet.line"].with_user(self.admin).create(
                {"sheet_id": sheet.id, "move_id": extra.id})
        with self.assertRaises(UserError):
            line.with_user(self.admin).write({"amount_due": 1})
        with self.assertRaises(UserError):
            line.with_user(self.admin).write({"move_id": extra.id})
        with self.assertRaises(UserError):
            line.with_user(self.admin).unlink()
        self.assertEqual(line.move_id, first)
        self.assertEqual(line.amount_due, 100.0)

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_line_outcome_is_server_owned_and_amount_is_snapshot(self):
        move = self._invoice(self._partner("SJP Snapshot", is_company=True), business_date(), 500)
        sheet = self.env["id.collection.sheet"].with_user(self.admin).create({"company_id": self.company.id})
        line = self.env["id.collection.sheet.line"].with_user(self.admin).create({
            "sheet_id": sheet.id, "move_id": move.id, "amount_due": 1, "outcome": "paid",
            "collected_amount": 500, "document_return": "original"})
        self.assertEqual(line.amount_due, 500.0)
        self.assertEqual((line.outcome, line.collected_amount, line.document_return), ("pending", 0.0, "none"))
        with self.assertRaises(UserError):
            line.with_user(self.admin).write({"outcome": "paid"})

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_issue_validates_collector_and_invoice_state(self):
        day = business_date()
        move = self._invoice(self._partner("SJP Issue Check", is_company=True), day, 100)
        sheet = self._generate()
        portal = new_test_user(self.env, login="sjp-portal", groups="base.group_portal", company_id=self.company.id)
        foreign_user = new_test_user(
            self.env, login="sjp-foreign-user", groups="base.group_user", company_id=self.foreign.id)
        foreign_user.company_ids = [Command.set(self.foreign.ids)]
        inactive = new_test_user(self.env, login="sjp-inactive", groups="base.group_user", company_id=self.company.id)
        inactive.active = False
        for bad in (portal, foreign_user, inactive):
            sheet.collector_id = bad
            with self.assertRaises(UserError):
                sheet.action_issue()
        sheet.collector_id = self.collector
        self._settle(move, 0)  # faktur lunas sebelum terbit
        with self.assertRaises(ValidationError):
            sheet.action_issue()
        self._settle(move, 100)
        sheet.action_issue()
        self.assertEqual(sheet.state, "issued")

    # ---- P2: mata uang ---------------------------------------------------------------------------
    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_foreign_currency_invoices_are_excluded_and_never_summed_raw(self):
        usd = self.env.ref("base.USD")
        usd.active = True
        day = business_date()
        outlet = self._partner("SJP Multi Currency", is_company=True)
        idr_invoice = self._invoice(outlet, day, 100000)
        usd_invoice = self._invoice(outlet, day, 100, currency=usd)
        wizard = self._wizard()
        self.assertEqual(wizard._candidates()[0], idr_invoice)
        self.assertEqual(wizard.candidate_total, 100000.0)  # bukan 100100
        self.assertEqual(wizard.foreign_count, 1)
        sheet = self._generate()
        self.assertEqual(sheet.line_ids.move_id, idr_invoice)
        self.assertEqual(sheet.amount_total, 100000.0)
        with self.assertRaises(ValidationError):  # tidak bisa diselundupkan lewat create baris
            self.env["id.collection.sheet.line"].with_user(self.admin).create(
                {"sheet_id": sheet.id, "move_id": usd_invoice.id})
        self.assertEqual(sheet.amount_total, 100000.0)


@tagged("post_install", "-at_install")
class TestCollectionConcurrency(TransactionCase):
    """Dua transaksi PostgreSQL nyata. Kelas terpisah tanpa fixture tak ter-commit supaya tidak ada kunci baris
    milik transaksi tes yang membuat cursor lain menunggu tanpa akhir. PDF diuji oleh
    scripts/ui/collection_sheet_pdf_smoke.py terhadap server HTTP hidup (wkhtmltopdf butuh server)."""

    def test_two_real_transactions_leave_a_single_active_claim(self):
        """Dua transaksi PostgreSQL nyata: pemulihan SJP B (SQL) menunggu transaksi A, lalu ditolak indeks unik."""
        db = sql_db.db_connect(self.env.cr.dbname)
        ids = self._commit_fixture(db)
        self.addCleanup(self._cleanup_fixture, db, ids)
        cr1 = db.cursor()
        env1 = api.Environment(cr1, SUPERUSER_ID, {})
        outcome = {}

        def second_transaction():
            cr2 = db.cursor()
            try:
                cr2.execute("SET LOCAL lock_timeout = '15s'")
                # Setara pemulihan SJP B: mengaktifkan klaim baris B untuk faktur yang sama.
                cr2.execute(
                    "UPDATE id_collection_sheet_line SET active_claim = TRUE WHERE id = %s", (ids["line_b"],))
                cr2.commit()
                outcome["ok"] = True
            except Exception as exc:  # noqa: BLE001
                outcome["error"] = exc
                cr2.rollback()
            finally:
                cr2.close()

        thread = threading.Thread(target=second_transaction, daemon=True)
        try:
            env1["id.collection.sheet.line"].create({"sheet_id": ids["sheet_a"], "move_id": ids["move"]})
            env1.flush_all()
            thread.start()
            time.sleep(1.5)
            self.assertTrue(thread.is_alive(), "transaksi kedua harus menunggu transaksi pertama")
            cr1.commit()
        finally:
            cr1.close()
        thread.join(30)
        self.assertFalse(thread.is_alive())
        self.assertNotIn("ok", outcome)
        self.assertIsInstance(outcome.get("error"), IntegrityError)
        with db.cursor() as cr:
            cr.execute(
                "SELECT sheet_id FROM id_collection_sheet_line WHERE move_id = %s AND active_claim",
                (ids["move"],))
            self.assertEqual([row[0] for row in cr.fetchall()], [ids["sheet_a"]])
            cr.execute("SELECT active_claim FROM id_collection_sheet_line WHERE id = %s", (ids["line_b"],))
            self.assertFalse(cr.fetchone()[0])  # B tidak berubah, tidak ada state setengah jadi

    def _commit_fixture(self, db):
        """Fixture yang BENAR-BENAR di-commit supaya terlihat oleh transaksi lain."""
        with db.cursor() as cr:
            cr.execute("SET LOCAL lock_timeout = '20s'")  # gagal cepat, bukan menggantung
            env = api.Environment(cr, SUPERUSER_ID, {})
            currency = env.ref("base.main_company").currency_id  # sudah aktif dan ter-commit
            company = env["res.company"].create({"name": "SJP Concurrency Co", "currency_id": currency.id})
            env = env(context={**env.context, "allowed_company_ids": company.ids})
            receivable = env["account.account"].create({
                "name": "AR SJP Conc", "code": "113901", "account_type": "asset_receivable",
                "company_ids": [Command.set(company.ids)]})
            income = env["account.account"].create({
                "name": "Income SJP Conc", "code": "420901", "account_type": "income",
                "company_ids": [Command.set(company.ids)]})
            journal = env["account.journal"].create({
                "name": "Sales SJP Conc", "code": "SJC", "type": "sale", "company_id": company.id})
            partner = env["res.partner"].create({"name": "SJP Conc Customer", "is_company": True})
            partner.with_company(company).property_account_receivable_id = receivable
            move = env["account.move"].create({
                "move_type": "out_invoice", "company_id": company.id, "journal_id": journal.id,
                "partner_id": partner.id, "invoice_date": business_date() - timedelta(days=30),
                "invoice_date_due": business_date(),
                "invoice_line_ids": [Command.create({
                    "name": "x", "quantity": 1, "price_unit": 777, "account_id": income.id})]})
            move.action_post()
            sheets = env["id.collection.sheet"].create([{"company_id": company.id}, {"company_id": company.id}])
            # B pernah memuat faktur lalu dibatalkan: barisnya tidak aktif dan siap "dipulihkan".
            line_b = env["id.collection.sheet.line"].create({"sheet_id": sheets[1].id, "move_id": move.id})
            sheets[1].action_cancel()
            return {
                "company": company.id, "move": move.id, "partner": partner.id, "journal": journal.id,
                "accounts": (receivable | income).ids, "sheet_a": sheets[0].id, "sheet_b": sheets[1].id,
                "line_b": line_b.id,
            }

    def _cleanup_fixture(self, db, ids):
        """Best-effort pada DB uji sekali pakai: hapus data yang sengaja di-commit."""
        try:
            with db.cursor() as cr:
                sheets = [ids["sheet_a"], ids["sheet_b"]]
                cr.execute("DELETE FROM id_collection_sheet_line WHERE sheet_id = ANY(%s)", (sheets,))
                cr.execute("DELETE FROM id_collection_sheet WHERE id = ANY(%s)", (sheets,))
                env = api.Environment(cr, SUPERUSER_ID, {})
                for model, key in (("account.move", "move"), ("account.journal", "journal")):
                    try:
                        with cr.savepoint():
                            rec = env[model].browse(ids[key]).exists()
                            if model == "account.move":
                                rec.button_draft()
                            rec.unlink()
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass
