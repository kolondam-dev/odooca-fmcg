"""BE-20b: Surat Jalan Penagihan (SJP): generate dari AR terbuka, banyak SJP, unpaid kembali ke kandidat."""
from datetime import timedelta

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user

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

    def _invoice(self, partner, due, amount=100000.0, company=None):
        company = company or self.company
        move = self.env["account.move"].with_company(company).create({
            "move_type": "out_invoice", "company_id": company.id, "journal_id": self.journal[company.id].id,
            "partner_id": partner.id, "invoice_date": due - timedelta(days=30), "invoice_date_due": due,
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
        sheet.line_ids.write({"outcome": "unpaid", "unpaid_reason": "Pemilik tidak ada"})
        sheet.collector_id = self.collector
        sheet.action_issue()
        self.assertEqual(self._wizard().candidate_count, 0)
        sheet.write({"state": "returned"})  # transisi resmi menyusul di BE-20e
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
