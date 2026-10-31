from datetime import timedelta
import base64
import csv
import io
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestCreditLimitApproval(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        # Siapkan akun piutang dan pendapatan untuk DB kosong/testing
        cls.acc_rec = cls._create_account(cls.company, "112099", "AR Test", "asset_receivable")
        cls.acc_inc = cls._create_account(cls.company, "410099", "Income Test", "income")
        cls.sale_journal = cls._create_journal(cls.company, "STEST", "Sale Test Journal", "sale")

        cls.partner = cls.env["res.partner"].create({
            "name": "Toko Berkat Manado Test",
            "credit_mode": "limit",
            "credit_limit": 1_000_000.0,
            "property_account_receivable_id": cls.acc_rec.id,
        })
        cls.product = cls.env["product.product"].create({
            "name": "Biskuit Uji Coba",
            "list_price": 500_000.0,
            "standard_price": 400_000.0,
            "property_account_income_id": cls.acc_inc.id,
        })

    @classmethod
    def _create_account(cls, company, code, name, acc_type):
        AccountModel = cls.env["account.account"]
        account = AccountModel.search([("code", "=", code)], limit=1)
        if not account:
            vals = {
                "name": name,
                "code": code,
                "account_type": acc_type,
            }
            acc_fields = AccountModel._fields if hasattr(AccountModel, "_fields") else {}
            if "company_ids" in acc_fields:
                vals["company_ids"] = [(6, 0, [company.id])]
            elif "company_id" in acc_fields:
                vals["company_id"] = company.id
            account = AccountModel.create(vals)
        return account

    @classmethod
    def _create_journal(cls, company, code, name, j_type):
        JournalModel = cls.env["account.journal"]
        j_fields = JournalModel._fields if hasattr(JournalModel, "_fields") else {}
        domain = [("type", "=", j_type)]
        if "company_id" in j_fields:
            domain.append(("company_id", "=", company.id))
        elif "company_ids" in j_fields:
            domain.append(("company_ids", "in", [company.id]))

        journal = JournalModel.search(domain, limit=1)
        if not journal:
            vals = {
                "name": name,
                "code": code,
                "type": j_type,
            }
            if "company_id" in j_fields:
                vals["company_id"] = company.id
            elif "company_ids" in j_fields:
                vals["company_ids"] = [(6, 0, [company.id])]
            journal = JournalModel.create(vals)
        return journal

    def test_01_normal_order_within_credit_limit(self):
        """Order dalam batas limit dapat langsung dikonfirmasi."""
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [
                (0, 0, {
                    "product_id": self.product.id,
                    "product_uom_qty": 1.0,
                    "price_unit": 500_000.0,
                }),
            ],
        })
        self.assertFalse(order.credit_limit_exceeded)
        order.action_confirm()
        self.assertEqual(order.state, "sale")

    def test_02_order_exceeding_credit_limit_blocks_confirmation(self):
        """Order melebihi batas limit harus diblokir dan membutuhkan persetujuan."""
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [
                (0, 0, {
                    "product_id": self.product.id,
                    "product_uom_qty": 3.0,
                    "price_unit": 500_000.0,
                }),
            ],
        })
        # Total Rp 1.500.000 > Limit Rp 1.000.000
        self.assertTrue(order.credit_limit_exceeded)

        # Coba konfirmasi sebelum approval -> harus raise UserError
        with self.assertRaises(UserError):
            order.action_confirm()

        # Alur Pengajuan Approval
        order.action_request_credit_approval()
        self.assertEqual(order.credit_approval_state, "pending")

        # Masih belum bisa konfirmasi saat pending
        with self.assertRaises(UserError):
            order.action_confirm()

        # Branch Manager menyetujui
        order.action_approve_credit()
        self.assertEqual(order.credit_approval_state, "approved")
        self.assertEqual(order.credit_approved_by, self.env.user)

        # Sekarang bisa dikonfirmasi
        order.action_confirm()
        self.assertEqual(order.state, "sale")

    def test_03_strict_credit_mode_with_overdue_invoice(self):
        """Partner mode strict dengan faktur jatuh tempo otomatis terblokir."""
        strict_partner = self.env["res.partner"].create({
            "name": "Toko Strict Overdue Test",
            "credit_mode": "strict",
            "credit_limit": 5_000_000.0,
            "property_account_receivable_id": self.acc_rec.id,
        })

        # Buat faktur jatuh tempo kemarin
        past_date = fields.Date.today() - timedelta(days=5)
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "journal_id": self.sale_journal.id,
            "partner_id": strict_partner.id,
            "invoice_date": past_date,
            "invoice_date_due": past_date,
            "invoice_line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "quantity": 1.0,
                    "price_unit": 200_000.0,
                    "account_id": self.acc_inc.id,
                }),
            ],
        })
        move.action_post()

        # Buat order baru meskipun nominalnya kecil (Rp 100.000)
        order = self.env["sale.order"].create({
            "partner_id": strict_partner.id,
            "order_line": [
                (0, 0, {
                    "product_id": self.product.id,
                    "product_uom_qty": 1.0,
                    "price_unit": 100_000.0,
                }),
            ],
        })

        self.assertTrue(order.credit_limit_exceeded, "Partner strict dengan overdue invoice wajib terdeteksi exceeded!")
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_04_coretax_nsfp_generation_and_csv_export(self):
        """Verifikasi pembuatan NSFP otomatis dan ekspor berkas CoreTax CSV."""
        inv = self.env["account.move"].create({
            "move_type": "out_invoice",
            "journal_id": self.sale_journal.id,
            "partner_id": self.partner.id,
            "invoice_date": fields.Date.today(),
            "l10n_id_tax_transaction_code": "01",
            "invoice_line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "quantity": 2.0,
                    "price_unit": 500_000.0,
                    "account_id": self.acc_inc.id,
                }),
            ],
        })
        inv.action_post()

        # Generate NSFP
        inv.action_generate_nsfp()
        self.assertTrue(inv.l10n_id_tax_invoice_number)
        self.assertTrue(inv.l10n_id_tax_invoice_number.startswith("010.000-26."))

        # Ekspor via wizard
        wizard = self.env["coretax.export.wizard"].create({
            "date_from": fields.Date.today() - timedelta(days=1),
            "date_to": fields.Date.today() + timedelta(days=1),
        })
        res = wizard.action_generate_coretax_csv()
        self.assertEqual(res["res_id"], wizard.id)
        self.assertEqual(wizard.state, "done")
        self.assertGreaterEqual(wizard.total_invoices, 1)
        self.assertTrue(wizard.export_file)

        # Parse CSV
        raw_csv = base64.b64decode(wizard.export_file).decode("utf-8")
        reader = csv.reader(io.StringIO(raw_csv))
        rows = list(reader)
        self.assertEqual(rows[0][0], "KD_JENIS_TRANSAKSI")
        self.assertEqual(rows[0][2], "NOMOR_FAKTUR")
