"""BE-19: kebijakan kredit efektif dan tunggakan faktur pada snapshot, dibuktikan dengan faktur nyata."""
from datetime import timedelta

from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user

from ..models.mobile_workday import business_date

# Minggu 2026-11-22 01:00 WITA = Sabtu 2026-11-21 17:00 UTC (tanggal UTC server masih 21).
AFTER_WITA_MIDNIGHT_UTC = "2026-11-21 17:00:00"
BEFORE_WITA_MIDNIGHT_UTC = "2026-11-21 15:59:59"  # 23:59:59 WITA 21 November
EIGHT_WITA_UTC = "2026-11-22 00:00:00"  # 08:00 WITA 22 November


@tagged("post_install", "-at_install")
class TestMobileCreditSnapshot(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        currency = cls.env.ref("base.IDR")
        currency.active = True  # kontrak mobile mensyaratkan IDR
        cls.company = cls.env["res.company"].create({"name": "Credit Snapshot Co", "currency_id": currency.id})
        cls.foreign = cls.env["res.company"].create({"name": "Credit Foreign Co", "currency_id": currency.id})
        cls.acc_rec, cls.acc_inc, cls.journal = {}, {}, {}
        for idx, company in enumerate((cls.company, cls.foreign)):
            cls.acc_rec[company.id] = cls._account(company, f"1129{idx}1", "AR Credit Test", "asset_receivable")
            cls.acc_inc[company.id] = cls._account(company, f"4100{idx}1", "Income Credit Test", "income")
            cls.journal[company.id] = cls._journal(company, f"CRD{idx}")
        cls.mobile = new_test_user(
            cls.env, login="credit-snapshot-sales", groups="id_mobile_api.group_mobile_sales",
            company_id=cls.company.id,
        )
        cls.principal = cls.env["id.principal"].create({"name": "Credit Principal", "code": "CRD-TEST"})
        cls.product = cls.env["product.product"].create({
            "name": "Credit Product", "default_code": "CRD-SKU", "principal_id": cls.principal.id,
            "company_id": False, "uom_id": cls.env.ref("uom.product_uom_unit").id, "list_price": 1000,
            "carton_qty": 24, "inner_qty": 6, "type": "consu", "is_storable": True,
            "taxes_id": [Command.clear()],
        })
        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        if not cls.warehouse:
            cls.warehouse = cls.env["stock.warehouse"].create({
                "name": "Credit Stock", "code": "CRDW", "company_id": cls.company.id,
            })
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Credit IDR", "currency_id": cls.company.currency_id.id, "company_id": cls.company.id,
        })

    @classmethod
    def _account(cls, company, code, name, account_type):
        return cls.env["account.account"].create({
            "name": name, "code": code, "account_type": account_type, "company_ids": [Command.set(company.ids)],
        })

    @classmethod
    def _journal(cls, company, code):
        return cls.env["account.journal"].create({
            "name": f"Sales {code}", "code": code, "type": "sale", "company_id": company.id,
        })

    # ---- helpers -------------------------------------------------------------------------------
    def _partner(self, name, **vals):
        vals.setdefault("partner_latitude", 1.465)
        vals.setdefault("partner_longitude", 124.833)
        vals.setdefault("street", "Credit Street")
        partner = self.env["res.partner"].create({"name": name, **vals})
        for company in (self.company, self.foreign):
            partner.with_company(company).property_account_receivable_id = self.acc_rec[company.id]
        return partner

    def _assign(self, *outlets):
        """Satu assignment per user/hari (unique); panggilan berikutnya mengganti daftar outlet."""
        Workday = self.env["id.mobile.workday"]
        vals = {"outlet_ids": [Command.set([o.id for o in outlets])], "active": True}
        existing = Workday.with_context(active_test=False).search([
            ("user_id", "=", self.mobile.id), ("company_id", "=", self.company.id),
            ("business_date", "=", business_date())])
        if existing:
            existing.write(vals)
            return
        Workday.create({
            "user_id": self.mobile.id, "company_id": self.company.id, "business_date": business_date(),
            "warehouse_id": self.warehouse.id, "pricelist_id": self.pricelist.id,
            "product_ids": [Command.set(self.product.ids)], **vals,
        })

    def _service(self):
        return self.env["id.mobile.workday"].with_user(self.mobile).with_context(
            allowed_company_ids=self.mobile.company_ids.ids)

    def _invoice(self, partner, due, amount=100000.0, company=None, post=True):
        company = company or self.company
        move = self.env["account.move"].with_company(company).create({
            "move_type": "out_invoice", "company_id": company.id, "journal_id": self.journal[company.id].id,
            "partner_id": partner.id, "invoice_date": due - timedelta(days=30), "invoice_date_due": due,
            "invoice_line_ids": [Command.create({
                "name": "Credit test line", "quantity": 1.0, "price_unit": amount,
                "account_id": self.acc_inc[company.id].id,
            })],
        })
        if post:
            move.action_post()
        return move

    def _settle(self, move, residual):
        """Simulasi pembayaran lewat SQL: perusahaan uji tidak punya jurnal bank/metode bayar."""
        state = "paid" if residual == 0 else "partial"
        self.env.cr.execute(
            "UPDATE account_move SET payment_state=%s, amount_residual=%s, amount_residual_signed=%s WHERE id=%s",
            (state, residual, residual, move.id))
        move.invalidate_recordset(["payment_state", "amount_residual", "amount_residual_signed"])

    def _order(self, partner):
        return self.env["sale.order"].create({
            "partner_id": partner.id,
            "order_line": [Command.create({"product_id": self.product.id, "product_uom_qty": 1, "price_unit": 1000})],
        })

    def _snapshot(self, **kwargs):
        return self._service()._snapshot_payload(**kwargs)

    def _credit(self, outlet):
        return self._snapshot()["outlet_credit"].get(str(outlet.id))

    def _mode(self, snapshot, outlet):
        return next(o for o in snapshot["outlets"] if o["id"] == str(outlet.id))["commercial"]["credit_mode"]

    # ---- kebijakan efektif (parent/anak) -------------------------------------------------------
    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_effective_credit_mode_follows_commercial_parent_both_directions(self):
        parent = self._partner("Credit Parent Strict", is_company=True, credit_mode="strict")
        child = self._partner("Credit Child Default", parent_id=parent.id, type="contact")
        self.assertEqual(child.commercial_partner_id, parent)
        self.assertEqual(child.credit_mode, "limit", "anak tetap default; kebijakan efektif ada di parent")
        self._assign(child)
        self._invoice(parent, business_date() - timedelta(days=3))
        self.assertEqual(self._mode(self._snapshot(), child), "strict")
        self.assertTrue(self._order(child).credit_limit_exceeded, "server menerapkan strict dari parent")

        parent.credit_mode = "limit"
        child.credit_mode = "strict"
        self.assertEqual(self._mode(self._snapshot(), child), "limit")
        order = self._order(child)
        self.assertFalse(order.credit_limit_exceeded, "server memakai parent (limit, tanpa limit nominal)")

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_parent_policy_change_changes_child_snapshot_version(self):
        parent = self._partner("Credit Parent Version", is_company=True, credit_mode="limit")
        child = self._partner("Credit Child Version", parent_id=parent.id, type="contact")
        self._assign(child)
        before = self._snapshot()
        parent.credit_mode = "strict"
        after = self._snapshot()
        self.assertEqual(self._mode(after, child), "strict")
        self.assertNotEqual(before["version"], after["version"])

    # ---- agregat tunggakan: isolasi dan hasil ORM nyata ----------------------------------------
    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_overdue_aggregate_exact_and_isolated(self):
        day = business_date()
        parent = self._partner("Credit Parent Agg", is_company=True, credit_mode="strict")
        child = self._partner("Credit Child Agg", parent_id=parent.id, type="contact")
        sibling = self._partner("Credit Sibling Unassigned", parent_id=parent.id, type="contact")
        unrelated = self._partner("Credit Unrelated Parent", is_company=True)
        self._assign(child)

        self._invoice(child, day - timedelta(days=20), 100000)
        self._invoice(sibling, day - timedelta(days=5), 50000)  # sibling parent yang sama ikut (perimeter parent)
        partial = self._invoice(parent, day - timedelta(days=2), 80000)
        self._settle(partial, 30000)
        paid = self._invoice(parent, day - timedelta(days=9), 70000)
        self._settle(paid, 0)
        self._invoice(parent, day, 999999)  # jatuh tempo hari ini bukan overdue
        self._invoice(parent, day - timedelta(days=4), 777777, post=False)  # draft
        self._invoice(unrelated, day - timedelta(days=4), 555555)  # parent lain
        self._invoice(parent, day - timedelta(days=4), 444444, company=self.foreign)  # company lain

        credit = self._credit(child)
        self.assertEqual(credit, {
            "overdue_count": 3, "overdue_total": 180000.0,
            "oldest_due": (day - timedelta(days=20)).isoformat(),
        })
        self.assertEqual(set(credit), {"overdue_count", "overdue_total", "oldest_due"}, "tanpa detail faktur")
        self.assertNotIn(str(sibling.id), self._snapshot()["outlet_credit"], "hanya outlet yang ditugaskan")
        self.assertNotIn(str(unrelated.id), self._snapshot()["outlet_credit"])

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_mobile_user_cannot_read_invoices_but_gets_aggregate(self):
        self.assertFalse(self.env["account.move"].with_user(self.mobile).has_access("read"))
        outlet = self._partner("Credit ACL Outlet", is_company=True, credit_mode="strict")
        self._assign(outlet)
        self._invoice(outlet, business_date() - timedelta(days=1), 12345)
        self.assertEqual(self._credit(outlet)["overdue_total"], 12345.0)

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_payment_changes_aggregate_not_version_and_block_is_not_in_commands(self):
        outlet = self._partner("Credit Payment Outlet", is_company=True, credit_mode="strict")
        self._assign(outlet)
        invoice = self._invoice(outlet, business_date() - timedelta(days=1), 100000)
        before = self._snapshot()
        self.assertEqual(before["outlet_credit"][str(outlet.id)]["overdue_count"], 1)
        self._settle(invoice, 0)
        after = self._snapshot()
        self.assertEqual(after["outlet_credit"], {})
        self.assertEqual(before["version"], after["version"])
        self.assertNotIn("outlet_credit", self._snapshot(include_volatile=False))

    # ---- BE-7: piutang berjalan dan daftar faktur terbuka ----------------------------------------
    def _receivables(self, outlet):
        return self._snapshot()["outlet_receivables"].get(str(outlet.id))

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_receivables_totals_list_order_and_isolation(self):
        day = business_date()
        parent = self._partner("Credit Parent Recv", is_company=True, credit_mode="strict")
        child = self._partner("Credit Child Recv", parent_id=parent.id, type="contact")
        sibling = self._partner("Credit Sibling Recv", parent_id=parent.id, type="contact")
        unrelated = self._partner("Credit Unrelated Recv", is_company=True)
        self._assign(child)
        oldest = self._invoice(child, day - timedelta(days=20), 100000)
        self._invoice(sibling, day - timedelta(days=5), 50000)
        partial = self._invoice(parent, day - timedelta(days=2), 80000)
        self._settle(partial, 30000)
        self._settle(self._invoice(parent, day - timedelta(days=9), 70000), 0)  # lunas: tidak ikut
        self._invoice(parent, day, 999999)  # terbuka, belum overdue
        self._invoice(parent, day - timedelta(days=4), 777777, post=False)  # draft
        self._invoice(unrelated, day - timedelta(days=4), 555555)  # parent lain
        self._invoice(parent, day - timedelta(days=4), 444444, company=self.foreign)  # perusahaan lain

        recv = self._receivables(child)
        self.assertEqual(recv["outstanding_total"], 1179999.0)  # 100000 + 50000 + 30000 + 999999
        self.assertEqual((recv["open_count"], recv["overdue_count"], recv["overdue_total"]), (4, 3, 180000.0))
        self.assertEqual(recv["oldest_due"], (day - timedelta(days=20)).isoformat())
        self.assertFalse(recv["truncated"])
        invoices = recv["invoices"]
        self.assertEqual([i["due_date"] for i in invoices], sorted(i["due_date"] for i in invoices),
                         "urut jatuh tempo tertua dulu")
        self.assertEqual(invoices[0]["reference"], oldest.name)
        self.assertEqual(invoices[0]["partner"], child.display_name)
        self.assertEqual([i["overdue"] for i in invoices], [True, True, True, False])
        self.assertEqual({i["balance"] for i in invoices if i["reference"] == partial.name}, {30000.0})
        self.assertEqual(
            {i["reference"]: i["total"] for i in invoices if i["reference"] == partial.name}, {partial.name: 80000.0})
        for invoice in invoices:
            self.assertEqual(set(invoice), {
                "reference", "partner", "invoice_date", "due_date", "total", "balance", "overdue"})
        self.assertNotIn(str(sibling.id), self._snapshot()["outlet_receivables"], "hanya outlet ditugaskan")
        # Konsisten dengan blok BE-19 untuk fakta overdue yang sama.
        credit = self._credit(child)
        self.assertEqual(
            (credit["overdue_count"], credit["overdue_total"]), (recv["overdue_count"], recv["overdue_total"]))

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_receivables_list_is_capped_but_totals_are_complete(self):
        day = business_date()
        outlet = self._partner("Credit Cap Outlet", is_company=True)
        self._assign(outlet)
        for offset in (10, 8, 6, 4):
            self._invoice(outlet, day - timedelta(days=offset), 1000)
        with patch.object(type(self.env["id.mobile.workday"]), "RECEIVABLE_INVOICE_CAP", 2):
            recv = self._receivables(outlet)
        self.assertTrue(recv["truncated"])
        self.assertEqual(len(recv["invoices"]), 2)
        self.assertEqual((recv["open_count"], recv["outstanding_total"]), (4, 4000.0))
        self.assertEqual(recv["invoices"][0]["due_date"], (day - timedelta(days=10)).isoformat())

    @freeze_time("2026-11-16 01:00:00", tick=True)
    def test_receivables_outside_digest_and_follow_payments(self):
        outlet = self._partner("Credit Pay Recv", is_company=True)
        self._assign(outlet)
        self.assertEqual(self._snapshot()["outlet_receivables"], {})
        invoice = self._invoice(outlet, business_date() + timedelta(days=5), 100000)  # belum jatuh tempo
        before = self._snapshot()
        recv = before["outlet_receivables"][str(outlet.id)]
        self.assertEqual((recv["outstanding_total"], recv["overdue_count"]), (100000.0, 0))
        self.assertNotIn(str(outlet.id), before["outlet_credit"], "belum overdue: bukan tunggakan BE-19")
        self._settle(invoice, 40000)
        after = self._snapshot()
        self.assertEqual(after["outlet_receivables"][str(outlet.id)]["outstanding_total"], 40000.0)
        self.assertEqual(before["version"], after["version"])
        self.assertNotIn("outlet_receivables", self._snapshot(include_volatile=False))

    # ---- tanggal overdue: satu definisi hari bisnis WITA dengan server -------------------------
    def _consistency(self, utc_now, due_offset_from_wita_day):
        """Snapshot dan server memberi kesimpulan sama untuk faktur strict pada waktu beku tertentu."""
        with freeze_time(utc_now, tick=False):
            day = business_date()
            outlet = self._partner(f"Credit TZ {utc_now}", is_company=True, credit_mode="strict")
            self._assign(outlet)
            self._invoice(outlet, day + timedelta(days=due_offset_from_wita_day), 10000)
            snapshot_overdue = str(outlet.id) in self._snapshot()["outlet_credit"]
            server_exceeded = self._order(outlet).credit_limit_exceeded
            return day, snapshot_overdue, server_exceeded

    def test_overdue_date_is_wita_for_snapshot_and_server(self):
        # 01:00 WITA 22 Nov (UTC masih 21 Nov): jatuh tempo 21 Nov = kemarin → overdue; 22 Nov = hari ini → belum.
        day, snap, server = self._consistency(AFTER_WITA_MIDNIGHT_UTC, -1)
        self.assertEqual(day.isoformat(), "2026-11-22")
        self.assertEqual((snap, server), (True, True))
        _day, snap, server = self._consistency(AFTER_WITA_MIDNIGHT_UTC, 0)
        self.assertEqual((snap, server), (False, False))

    def test_overdue_date_boundaries_before_midnight_and_at_eight_wita(self):
        day, snap, server = self._consistency(BEFORE_WITA_MIDNIGHT_UTC, 0)  # 23:59:59 WITA, due hari ini
        self.assertEqual(day.isoformat(), "2026-11-21")
        self.assertEqual((snap, server), (False, False))
        _day, snap, server = self._consistency(BEFORE_WITA_MIDNIGHT_UTC, -1)  # due kemarin
        self.assertEqual((snap, server), (True, True))
        day, snap, server = self._consistency(EIGHT_WITA_UTC, -1)  # 08:00 WITA 22 Nov, due 21 Nov
        self.assertEqual(day.isoformat(), "2026-11-22")
        self.assertEqual((snap, server), (True, True))
