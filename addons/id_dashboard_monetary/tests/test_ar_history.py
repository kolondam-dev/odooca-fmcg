from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestArHistory(TransactionCase):
    def test_installments_credits_and_later_reconciliation_reconstruct_cutoff(self):
        self.env.company.currency_id.active = True
        ar = self.env["account.account"].create({"name": "History receivable", "code": "991401",
            "account_type": "asset_receivable", "reconcile": True,
            "company_ids": [(6, 0, self.env.company.ids)]})
        offset = self.env["account.account"].create({"name": "History offset", "code": "991402",
            "account_type": "asset_current", "company_ids": [(6, 0, self.env.company.ids)]})
        partner = self.env["res.partner"].create({"name": "AR history installment customer"})
        journal = self.env["account.journal"].create({"name": "History test", "code": "AH3", "type": "general"})

        def entry(day, amount, due=None):
            move = self.env["account.move"].create({"date": day, "journal_id": journal.id,
                "line_ids": [(0, 0, {"account_id": ar.id, "partner_id": partner.id,
                    "date_maturity": due or day, "debit": max(amount, 0), "credit": max(-amount, 0)}),
                    (0, 0, {"account_id": offset.id, "debit": max(-amount, 0), "credit": max(amount, 0)})]})
            move.action_post()
            return move.line_ids.filtered(lambda line: line.account_id == ar)

        first = entry("2025-01-01", 100, "2025-01-05")
        entry("2025-01-01", 200, "2025-02-05")
        paid = entry("2025-01-20", -80)
        (first | paid).reconcile()
        entry("2025-01-25", -30)
        # Full current reconciliation must not erase the 20 still open at January cutoff.
        later = entry("2025-02-10", -20)
        (first | later).reconcile()
        self.assertTrue(first.reconciled)
        service = self.env["id.ar.history"]
        result = service._snapshot("2025-01-31", "2025-01-10")
        self.assertEqual(result["opening"], 300)
        self.assertEqual((result["debit_open"], result["credits"], result["net"]), (220, -30, 190))
        self.assertEqual(result["ledger_balance"], result["net"])
        self.assertEqual(sum(cell["opening"] for cell in result["migration"]), 300)
        self.assertEqual(sum(cell["closing"] for cell in result["migration"]), 190)
        by_bucket = {row["key"]: row for row in result["buckets"]}
        self.assertEqual(by_bucket["overdue_15_30"]["debit"], 20)
        self.assertEqual(by_bucket["not_due"]["debit"], 200)
        self.assertEqual(service._snapshot("2025-01-10", "2025-01-01")["net"], 300)
        with self.assertRaises(UserError):
            service._snapshot("2025-01-01", "2025-02-01")

    def test_invoice_only_role_gets_no_historical_cost_or_ledger_data(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "History invoice only", "login": "history_invoice_only",
            "group_ids": [(6, 0, [self.env.ref("account.group_account_invoice").id])]})
        result = self.env["id.ar.history"].with_user(user)._snapshot()
        self.assertEqual(result, {"available": False, "reason": "accounting_role_required"})
