"""BE-20c: snapshot SJP untuk kolektor sesi: kolektor, perusahaan, hari bisnis WITA, status terbit."""
from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.id_base.models.business_day import business_date

AFTER_WITA_MIDNIGHT_UTC = "2026-11-21 17:00:00"  # 01:00 WITA 22 November, tanggal UTC masih 21
BEFORE_WITA_MIDNIGHT_UTC = "2026-11-21 15:59:59"  # 23:59:59 WITA 21 November


@tagged("post_install", "-at_install")
class TestCollectionSnapshot(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        currency = cls.env.ref("base.IDR")
        currency.active = True
        cls.company = cls.env["res.company"].create({"name": "SJP Snap Co", "currency_id": currency.id})
        cls.foreign = cls.env["res.company"].create({"name": "SJP Snap Foreign Co", "currency_id": currency.id})
        cls.acc_rec, cls.acc_inc, cls.journal = {}, {}, {}
        for idx, company in enumerate((cls.company, cls.foreign)):
            cls.acc_rec[company.id] = cls._account(company, f"1149{idx}1", "AR Snap Test", "asset_receivable")
            cls.acc_inc[company.id] = cls._account(company, f"4300{idx}1", "Income Snap Test", "income")
            cls.journal[company.id] = cls.env["account.journal"].create({
                "name": f"Sales SNP{idx}", "code": f"SNP{idx}", "type": "sale", "company_id": company.id})
        cls.mobile = new_test_user(
            cls.env, login="sjp-snap-sales", groups="id_mobile_api.group_mobile_sales", company_id=cls.company.id)
        cls.other = new_test_user(
            cls.env, login="sjp-snap-other", groups="id_mobile_api.group_mobile_sales", company_id=cls.company.id)
        cls.principal = cls.env["id.principal"].create({"name": "SJP Snap Principal", "code": "SNP-TEST"})
        cls.product = cls.env["product.product"].create({
            "name": "SJP Snap Product", "default_code": "SNP-SKU", "principal_id": cls.principal.id,
            "company_id": False, "uom_id": cls.env.ref("uom.product_uom_unit").id, "list_price": 1000,
            "carton_qty": 24, "inner_qty": 6, "type": "consu", "is_storable": True,
            "taxes_id": [Command.clear()],
        })
        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        if not cls.warehouse:
            cls.warehouse = cls.env["stock.warehouse"].create({
                "name": "SJP Snap Stock", "code": "SNPW", "company_id": cls.company.id})
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "SJP Snap IDR", "currency_id": cls.company.currency_id.id, "company_id": cls.company.id})

    @classmethod
    def _account(cls, company, code, name, account_type):
        return cls.env["account.account"].create({
            "name": name, "code": code, "account_type": account_type, "company_ids": [Command.set(company.ids)]})

    # ---- helpers -------------------------------------------------------------------------------
    def _partner(self, name, **vals):
        vals.setdefault("partner_latitude", 1.465)
        vals.setdefault("partner_longitude", 124.833)
        vals.setdefault("street", "SJP Snap Street")
        partner = self.env["res.partner"].create({"name": name, **vals})
        for company in (self.company, self.foreign):
            partner.with_company(company).property_account_receivable_id = self.acc_rec[company.id]
        return partner

    def _assign(self, user, *outlets):
        self.env["id.mobile.workday"].create({
            "user_id": user.id, "company_id": self.company.id, "business_date": business_date(),
            "warehouse_id": self.warehouse.id, "pricelist_id": self.pricelist.id,
            "product_ids": [Command.set(self.product.ids)],
            "outlet_ids": [Command.set([o.id for o in outlets])],
        })

    def _service(self, user=None):
        user = user or self.mobile
        return self.env["id.mobile.workday"].with_user(user).with_context(allowed_company_ids=user.company_ids.ids)

    def _snapshot(self, user=None, **kwargs):
        return self._service(user)._snapshot_payload(**kwargs)

    def _sheets(self, user=None):
        return self._snapshot(user)["collection_sheets"]

    def _invoice(self, partner, due, amount=100000.0, company=None):
        company = company or self.company
        move = self.env["account.move"].with_company(company).create({
            "move_type": "out_invoice", "company_id": company.id, "journal_id": self.journal[company.id].id,
            "partner_id": partner.id, "invoice_date": due - timedelta(days=30), "invoice_date_due": due,
            "invoice_line_ids": [Command.create({
                "name": "Snap line", "quantity": 1.0, "price_unit": amount,
                "account_id": self.acc_inc[company.id].id})],
        })
        move.action_post()
        return move

    def _settle(self, move, residual):
        state = "paid" if residual == 0 else "partial"
        self.env.cr.execute(
            "UPDATE account_move SET payment_state=%s, amount_residual=%s, amount_residual_signed=%s WHERE id=%s",
            (state, residual, residual, move.id))
        move.invalidate_recordset(["payment_state", "amount_residual", "amount_residual_signed"])

    def _sheet(self, moves, collector=None, collect_date=None, company=None, state="issued", **vals):
        company = company or self.company
        sheet = self.env["id.collection.sheet"].create({
            "company_id": company.id,
            "collector_id": (collector or self.mobile).id,
            "collect_date": collect_date or business_date(),
            "line_ids": [Command.create({"move_id": move.id}) for move in moves],
            **vals,
        })
        if state == "issued" and company == self.company:
            sheet.action_issue()
        elif state != "draft":
            sheet._apply_state("issued")  # seam privat untuk perusahaan lain / fixture
            if state != "issued":
                sheet._apply_state(state)
        return sheet

    # ---- cakupan -------------------------------------------------------------------------------
    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_only_own_issued_sheet_for_today_and_company_is_included(self):
        day = business_date()
        outlet = self._partner("SJP Snap Outlet", is_company=True)
        self._assign(self.mobile, outlet)
        self._assign(self.other, outlet)
        mine = self._sheet([self._invoice(outlet, day, 100)])
        self._sheet([self._invoice(outlet, day, 110)], state="draft")
        self._sheet([self._invoice(outlet, day, 120)], state="returned")
        self._sheet([self._invoice(outlet, day, 130)], state="cancelled")
        self._sheet([self._invoice(outlet, day, 140)], collect_date=day - timedelta(days=1))
        self._sheet([self._invoice(outlet, day, 150)], collect_date=day + timedelta(days=1))
        self._sheet([self._invoice(outlet, day, 160)], collector=self.other)
        self._sheet([self._invoice(outlet, day, 170, company=self.foreign)], company=self.foreign)
        sheets = self._sheets()
        self.assertEqual(sheets["truncated"], False)
        self.assertEqual([sheet["id"] for sheet in sheets["sheets"]], [str(mine.id)])
        row = sheets["sheets"][0]
        self.assertEqual((row["name"], row["state"], row["line_count"], row["amount_total"]),
                         (mine.name, "issued", 1, 100.0))
        self.assertEqual(row["collect_date"], day.isoformat())
        # Kolektor lain hanya melihat SJP miliknya.
        self.assertEqual([s["name"] for s in self._sheets(self.other)["sheets"]],
                         [self.env["id.collection.sheet"].search([("collector_id", "=", self.other.id)]).name])

    @freeze_time(AFTER_WITA_MIDNIGHT_UTC, tick=False)
    def test_business_day_follows_wita_not_utc(self):
        day = business_date()
        self.assertEqual(day.isoformat(), "2026-11-22")
        outlet = self._partner("SJP Snap WITA", is_company=True)
        self._assign(self.mobile, outlet)
        today = self._sheet([self._invoice(outlet, day, 100)])
        self._sheet([self._invoice(outlet, day, 110)], collect_date=day - timedelta(days=1))  # tanggal UTC server
        self.assertEqual([s["id"] for s in self._sheets()["sheets"]], [str(today.id)])

    @freeze_time(BEFORE_WITA_MIDNIGHT_UTC, tick=False)
    def test_sheet_for_next_wita_day_is_not_visible_before_midnight(self):
        day = business_date()
        self.assertEqual(day.isoformat(), "2026-11-21")
        outlet = self._partner("SJP Snap Before", is_company=True)
        self._assign(self.mobile, outlet)
        self._sheet([self._invoice(outlet, day, 100)], collect_date=day + timedelta(days=1))
        self.assertEqual(self._sheets()["sheets"], [])

    # ---- isi baris -----------------------------------------------------------------------------
    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_lines_map_outlet_follow_balance_and_sort_by_due_date(self):
        day = business_date()
        parent = self._partner("SJP Snap Parent", is_company=True)
        child = self._partner("SJP Snap Child", parent_id=parent.id, type="contact")
        elsewhere = self._partner("SJP Snap Elsewhere", is_company=True)
        self._assign(self.mobile, child)
        late = self._invoice(child, day - timedelta(days=9), 1000)
        soon = self._invoice(parent, day, 2000)
        away = self._invoice(elsewhere, day + timedelta(days=3), 3000)
        self._sheet([away, soon, late])
        self._settle(soon, 500)  # sebagian dibayar setelah SJP terbit: amount_due tetap, balance berubah
        lines = self._sheets()["sheets"][0]["lines"]
        self.assertEqual([line["reference"] for line in lines], [late.name, soon.name, away.name])
        by_ref = {line["reference"]: line for line in lines}
        self.assertEqual(by_ref[late.name]["outlet_id"], str(child.id))
        self.assertEqual(by_ref[late.name]["partner_id"], str(parent.id))
        self.assertEqual(by_ref[soon.name]["outlet_id"], str(child.id))  # faktur parent, outlet ditugaskan anak
        self.assertIsNone(by_ref[away.name]["outlet_id"])  # di luar PJP hari ini
        self.assertEqual((by_ref[soon.name]["amount_due"], by_ref[soon.name]["balance"]), (2000.0, 500.0))
        self.assertEqual([line["overdue"] for line in lines], [True, False, False])
        self.assertEqual({line["outcome"] for line in lines}, {"pending"})
        self.assertEqual(lines[0]["due_date"], (day - timedelta(days=9)).isoformat())
        self.assertEqual(set(lines[0]), {
            "id", "reference", "partner", "partner_id", "outlet_id", "due_date", "overdue",
            "amount_due", "balance", "outcome", "document_return"})

    # ---- batas dan digest ----------------------------------------------------------------------
    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_caps_are_flagged_not_silently_truncated(self):
        day = business_date()
        outlet = self._partner("SJP Snap Caps", is_company=True)
        self._assign(self.mobile, outlet)
        first = self._sheet([self._invoice(outlet, day - timedelta(days=i), 100 + i) for i in range(3)])
        self._sheet([self._invoice(outlet, day, 999)])
        sheet_model = type(self.env["id.collection.sheet"])
        with patch.object(sheet_model, "MOBILE_LINE_CAP", 2), patch.object(sheet_model, "MOBILE_SHEET_CAP", 1):
            payload = self._sheets()
        self.assertTrue(payload["truncated"])
        self.assertEqual([s["id"] for s in payload["sheets"]], [str(first.id)])
        only = payload["sheets"][0]
        self.assertTrue(only["truncated"])
        self.assertEqual((only["line_count"], len(only["lines"])), (3, 2))
        self.assertEqual(only["amount_total"], first.amount_total)  # total dokumen, bukan subtotal terpotong

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_collection_sheets_are_outside_digest_and_commands(self):
        day = business_date()
        outlet = self._partner("SJP Snap Digest", is_company=True)
        self._assign(self.mobile, outlet)
        before = self._snapshot()
        self.assertEqual(before["collection_sheets"], {"sheets": [], "truncated": False})
        self._sheet([self._invoice(outlet, day, 100)])
        after = self._snapshot()
        self.assertEqual(after["version"], before["version"])  # digest tidak berubah
        self.assertEqual(len(after["collection_sheets"]["sheets"]), 1)
        self.assertNotIn("collection_sheets", self._snapshot(include_volatile=False))
