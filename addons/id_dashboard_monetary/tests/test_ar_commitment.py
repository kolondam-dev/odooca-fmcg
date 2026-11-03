import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestArCommitment(TransactionCase):
    def _ledger(self):
        self.env.company.currency_id.active = True
        accounts = {}
        for key, kind, code in [("ar", "asset_receivable", "992001"), ("offset", "asset_current", "992002"),
                                 ("bank", "asset_cash", "992003"), ("outstanding", "asset_current", "992004")]:
            accounts[key] = self.env["account.account"].create({"name": "Commitment " + key, "code": code,
                "account_type": kind, "reconcile": key in ("ar", "outstanding"),
                "company_ids": [(6, 0, self.env.company.ids)]})
        partner = self.env["res.partner"].create({"name": "Promise customer",
            "property_account_receivable_id": accounts["ar"].id})
        journal = self.env["account.journal"].create({"name": "Promise ledger", "code": "PC3", "type": "general"})
        def entry(amount):
            move = self.env["account.move"].create({"journal_id": journal.id, "date": fields.Date.context_today(self),
                "line_ids": [(0, 0, {"account_id": accounts["ar"].id, "partner_id": partner.id,
                    "date_maturity": fields.Date.context_today(self), "debit": max(amount, 0),
                    "credit": max(-amount, 0)}),
                    (0, 0, {"account_id": accounts["offset"].id, "debit": max(-amount, 0), "credit": max(amount, 0)})]})
            move.action_post()
            return move.line_ids.filtered(lambda line: line.account_id == accounts["ar"])
        line = entry(100)
        return accounts, partner, line, entry

    def _promise(self, line, amount=40):
        promise = self.env["id.ar.promise"].create({"name": "Customer agreement", "line_id": line.id,
            "amount": amount, "due_date": fields.Date.context_today(self)+timedelta(days=1),
            "source": "Recorded agreement"})
        promise.action_commit()
        return promise

    def test_frozen_ledger_survives_reconciliation_and_rejects_mutation(self):
        accounts, partner, line, entry = self._ledger()
        Snapshot = self.env["id.ar.audit.snapshot"]
        snap = Snapshot.browse(Snapshot.capture_ledger())
        payload, digest = snap.payload_json, snap.digest
        (line | entry(-20)).reconcile()
        self.assertEqual(json.loads(snap.payload_json)["net"], 100)
        self.assertEqual((snap.payload_json, snap.digest), (payload, digest))
        self.assertTrue(snap.action_verify())
        self.assertTrue(json.loads(payload)["sources"]["ledger_items"])
        with self.assertRaises(AccessError):
            snap.write({"payload_json": "spoof"})
        with self.assertRaises(AccessError):
            snap.unlink()
        with self.assertRaises(AccessError):
            Snapshot.with_context(default_payload_json="spoof").create({"company_id": self.env.company.id})

    def test_credit_is_not_cash_and_overdue_assessment_is_frozen(self):
        accounts, partner, line, entry = self._ledger()
        promise = self._promise(line)
        (line | entry(-40)).reconcile()
        self.assertEqual(promise._assessment()["settled"], 0)
        self.assertEqual(promise._assessment()["outcome"], "open")
        future = promise.due_date+timedelta(days=1)
        with patch.object(fields.Date, "context_today", return_value=future):
            action = promise.action_capture_assessment()
        snap = self.env["id.ar.audit.snapshot"].browse(action["res_id"])
        self.assertEqual(json.loads(snap.payload_json)["outcome"], "broken")
        with self.assertRaises(AccessError):
            promise.write({"due_date": future})
        with self.assertRaises(AccessError):
            promise.unlink()

    def test_paid_and_bank_matched_allocation_fulfils_promise(self):
        accounts, partner, line, entry = self._ledger()
        promise = self._promise(line)
        journal = self.env["account.journal"].create({"name": "Promise bank", "code": "PB3", "type": "bank",
            "default_account_id": accounts["bank"].id, "suspense_account_id": accounts["outstanding"].id,
            "inbound_payment_method_line_ids": [(0, 0, {
                "payment_method_id": self.env.ref("account.account_payment_method_manual_in").id,
                "payment_account_id": accounts["outstanding"].id})]})
        payment = self.env["account.payment"].create({"journal_id": journal.id, "amount": 40,
            "payment_type": "inbound", "partner_type": "customer", "partner_id": partner.id,
            "payment_method_line_id": journal.inbound_payment_method_line_ids[:1].id,
            "currency_id": self.env.company.currency_id.id, "date": fields.Date.context_today(self)})
        payment.action_post()
        receivable = payment.move_id.line_ids.filtered(lambda item: item.account_id == accounts["ar"])
        (line | receivable).reconcile()
        self.assertEqual(promise._assessment()["settled"], 0)
        statement = self.env["account.bank.statement.line"].create({"journal_id": journal.id, "amount": 40,
            "date": fields.Date.context_today(self), "payment_ref": "Promise actual receipt", "partner_id": partner.id})
        source = payment.move_id.line_ids.filtered(lambda item: item.account_id == accounts["outstanding"])
        counterpart = statement.move_id.line_ids.filtered(lambda item: item.account_id == accounts["outstanding"])
        (source | counterpart).reconcile()
        self.env.flush_all()
        payment.invalidate_recordset()
        self.assertTrue(payment.is_matched)
        self.assertEqual(payment.state, "paid")
        result = promise._assessment()
        self.assertEqual((result["outcome"], result["settled"]), ("kept", 40))
        self.assertEqual(result["sources"][0]["payment_id"], payment.id)

    def test_invoice_only_role_cannot_capture_or_read_promises(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({"name": "Commitment invoice only",
            "login": "commitment_invoice_only", "group_ids": [(6, 0, [
                self.env.ref("account.group_account_invoice").id])]})
        with self.assertRaises(AccessError):
            self.env["id.ar.audit.snapshot"].with_user(user).capture_ledger()
        with self.assertRaises(AccessError):
            self.env["id.ar.promise"].with_user(user).search([])
