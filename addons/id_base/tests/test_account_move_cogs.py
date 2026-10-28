# Part of odooca-fmcg. License LGPL-3.
"""Odoo TransactionCase untuk ekstensi akuntansi perpetual FMCG account.move."""

from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "id_base")
class TestAccountMoveCogs(TransactionCase):
    """Pengujian integrasi Odoo ORM TransactionCase terhadap hook COGS dan predikat seed."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Seed company PT Salva Inti Mandiri
        cls.company_seed = cls.env["res.company"].search([("name", "=", "PT Salva Inti Mandiri")], limit=1)
        if not cls.company_seed:
            cls.company_seed = cls.env["res.company"].create({
                "name": "PT Salva Inti Mandiri",
            })

        # Foreign company yang mengandung "Salva" untuk menguji ketatnya batas company
        cls.company_foreign = cls.env["res.company"].search([("name", "=", "PT Salva Trading Indonesia")], limit=1)
        if not cls.company_foreign:
            cls.company_foreign = cls.env["res.company"].create({
                "name": "PT Salva Trading Indonesia",
            })

        # Partner
        cls.partner = cls.env["res.partner"].create({
            "name": "Toko Retail Uji FMCG",
            "company_id": cls.company_seed.id,
        })

        # Product
        cls.product = cls.env["product.product"].create({
            "name": "SKU FMCG Test",
            "standard_price": 25000.0,
            "list_price": 30000.0,
        })

        # Seed company accounts & journals (distinct codes ending in 1)
        cls.acc_rec_seed = cls._create_account(cls.company_seed, "112001", "AR Seed", "asset_receivable")
        cls.acc_pay_seed = cls._create_account(cls.company_seed, "211001", "AP Seed", "liability_payable")
        cls.acc_inc_seed = cls._create_account(cls.company_seed, "410001", "Inc Seed", "income")
        cls.acc_exp_seed = cls._create_account(cls.company_seed, "610001", "Exp Seed", "expense")
        cls.journal_sale_seed = cls._create_journal(cls.company_seed, "SJ1", "Sale Journal Seed", "sale")
        cls.journal_purchase_seed = cls._create_journal(cls.company_seed, "PJ1", "Purchase Journal Seed", "purchase")

        # Foreign company accounts & journals (distinct codes ending in 2)
        cls.acc_rec_foreign = cls._create_account(cls.company_foreign, "112002", "AR Foreign", "asset_receivable")
        cls.acc_pay_foreign = cls._create_account(cls.company_foreign, "211002", "AP Foreign", "liability_payable")
        cls.acc_inc_foreign = cls._create_account(cls.company_foreign, "410002", "Inc Foreign", "income")
        cls.acc_exp_foreign = cls._create_account(cls.company_foreign, "610002", "Exp Foreign", "expense")
        cls.journal_sale_foreign = cls._create_journal(cls.company_foreign, "SJ2", "Sale Journal Foreign", "sale")
        cls.journal_purchase_foreign = cls._create_journal(
            cls.company_foreign, "PJ2", "Purchase Journal Foreign", "purchase"
        )

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

    def _create_basic_invoice(self, company, is_seed=False, move_type="out_invoice"):
        """Helper untuk membuat faktur pengujian."""
        is_seed_comp = (company.id == self.company_seed.id)
        is_purchase = move_type in ("in_invoice", "in_refund")

        if is_seed_comp:
            journal = self.journal_purchase_seed if is_purchase else self.journal_sale_seed
            product_account = self.acc_exp_seed if is_purchase else self.acc_inc_seed
            rec_account = self.acc_rec_seed
            pay_account = self.acc_pay_seed
        else:
            journal = self.journal_purchase_foreign if is_purchase else self.journal_sale_foreign
            product_account = self.acc_exp_foreign if is_purchase else self.acc_inc_foreign
            rec_account = self.acc_rec_foreign
            pay_account = self.acc_pay_foreign

        PartnerModel = self.env["res.partner"]
        has_wc = hasattr(PartnerModel, "with_company")
        target_partner_model = PartnerModel.with_company(company) if has_wc else PartnerModel

        partner = target_partner_model.create({
            "name": f"Partner Test {company.id}",
            "company_id": company.id,
        })
        if hasattr(partner, "property_account_receivable_id"):
            partner.property_account_receivable_id = rec_account.id
        if hasattr(partner, "property_account_payable_id"):
            partner.property_account_payable_id = pay_account.id

        MoveModel = self.env["account.move"]
        target_model = MoveModel.with_company(company) if hasattr(MoveModel, "with_company") else MoveModel

        return target_model.create({
            "move_type": move_type,
            "partner_id": partner.id,
            "company_id": company.id,
            "journal_id": journal.id,
            "is_fmcg_seed_invoice": is_seed,
            "invoice_line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "account_id": product_account.id,
                    "quantity": 10.0,
                    "price_unit": 30000.0,
                }),
            ],
        })

    def test_non_seed_invoice_in_seed_company_calls_native(self):
        """Kasus 1: Invoice biasa tanpa penanda seed di seed company dilarang dianggap seed."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=False)
        self.assertFalse(inv.is_fmcg_seed_invoice)
        self.assertFalse(inv._is_seed_commercial_invoice_with_posted_delivery_cogs())
        # Native prepare out lines vals dapat dipanggil tanpa exception
        vals = inv._stock_account_prepare_realtime_out_lines_vals()
        self.assertIsInstance(vals, list)

    def test_unmarked_invoice_in_foreign_company_calls_native(self):
        """Kasus 2: Invoice biasa di company foreign bernama mirip tetap bernilai False."""
        inv = self._create_basic_invoice(self.company_foreign, is_seed=False)
        self.assertFalse(inv.is_fmcg_seed_invoice)
        self.assertFalse(inv._is_seed_commercial_invoice_with_posted_delivery_cogs())

    def test_marked_seed_in_foreign_company_raises_user_error(self):
        """Kasus 2b: Invoice yang ditandai seed tetapi pada foreign company wajib fail-closed."""
        inv = self._create_basic_invoice(self.company_foreign, is_seed=True)
        self.assertTrue(inv.is_fmcg_seed_invoice)
        with self.assertRaises(UserError) as ctx:
            inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
        self.assertIn("bukan perusahaan seed FMCG", str(ctx.exception))

    def test_marked_seed_without_delivery_moves_raises_user_error(self):
        """Kasus 3: Invoice bertanda seed tanpa link delivery move wajib ditolak fail-closed."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        # 3a: Tanpa relasi sale_line_ids
        with self.assertRaises(UserError) as ctx:
            inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
        self.assertIn("tidak memiliki relasi sale_line_ids", str(ctx.exception))

        # 3b: Dengan sale_line_ids tetapi tanpa pergerakan pengiriman (move_ids kosong)
        line = inv.invoice_line_ids[0]
        fake_sol_empty = SimpleNamespace(move_ids=[])
        with patch.object(type(line), "sale_line_ids", [fake_sol_empty], create=True):
            with self.assertRaises(UserError) as ctx:
                inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
            self.assertIn("tidak memiliki pergerakan pengiriman", str(ctx.exception))

    def test_marked_seed_with_unposted_cogs_journal_raises_user_error(self):
        """Kasus 4: Invoice bertanda seed dengan jurnal STJ belum posted wajib ditolak fail-closed."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]

        # Pasang mock pergerakan barang dengan jurnal valuasi draft
        bad_journal_am = SimpleNamespace(
            id=991,
            name="STJ/DRAFT/01",
            state="draft",
            company_id=self.company_seed,
            journal_id=SimpleNamespace(code="STJ"),
            line_ids=[],
        )
        fake_sm = SimpleNamespace(
            id=881,
            name="OUT/TEST/01",
            state="done",
            account_move_id=bad_journal_am,
        )
        fake_sol = SimpleNamespace(move_ids=[fake_sm])

        with patch.object(type(line), "sale_line_ids", [fake_sol], create=True):
            with self.assertRaises(UserError) as ctx:
                inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
            self.assertIn("belum berstatus 'posted'", str(ctx.exception))

    def test_marked_seed_with_wrong_journal_raises_user_error(self):
        """Kasus 4b: Jurnal valuasi bukan STJ wajib ditolak fail-closed."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]

        wrong_journal_am = SimpleNamespace(
            id=992,
            name="MISC/2026/01",
            state="posted",
            company_id=self.company_seed,
            journal_id=SimpleNamespace(code="MISC"),
            line_ids=[],
        )
        fake_sm = SimpleNamespace(
            id=882,
            name="OUT/TEST/02",
            state="done",
            account_move_id=wrong_journal_am,
        )
        fake_sol = SimpleNamespace(move_ids=[fake_sm])

        with patch.object(type(line), "sale_line_ids", [fake_sol], create=True):
            with self.assertRaises(UserError) as ctx:
                inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
            self.assertIn("diharapkan 'STJ'", str(ctx.exception))

    def test_positive_seed_invoice_suppresses_duplicate_cogs(self):
        """Kasus 5: Invoice seed valid dengan bukti HPP lengkap singular account_move_id STJ mengembalikan []."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]

        aml_debit = SimpleNamespace(
            account_id=SimpleNamespace(code="510000"),
            debit=250000.0,
            credit=0.0,
        )
        aml_credit = SimpleNamespace(
            account_id=SimpleNamespace(code="113000"),
            debit=0.0,
            credit=250000.0,
        )
        valid_stj_am = SimpleNamespace(
            id=993,
            name="STJ/2026/001",
            state="posted",
            company_id=self.company_seed,
            journal_id=SimpleNamespace(code="STJ"),
            line_ids=[aml_debit, aml_credit],
        )
        fake_sm = SimpleNamespace(
            id=883,
            name="OUT/TEST/03",
            state="done",
            account_move_id=valid_stj_am,
        )
        fake_sol = SimpleNamespace(move_ids=[fake_sm])

        with patch.object(type(line), "sale_line_ids", [fake_sol], create=True):
            self.assertTrue(inv._is_seed_commercial_invoice_with_posted_delivery_cogs())
            # COGS duplikat disupresi (mengembalikan [])
            out_vals = inv._stock_account_prepare_realtime_out_lines_vals()
            self.assertEqual(out_vals, [])

    def test_vendor_bill_and_refund_call_native(self):
        """Kasus 6: Vendor bill dan refund pelanggan tidak pernah disupresi oleh hook seed."""
        bill = self._create_basic_invoice(self.company_seed, is_seed=True, move_type="in_invoice")
        self.assertFalse(bill._is_seed_commercial_invoice_with_posted_delivery_cogs())

        refund = self._create_basic_invoice(self.company_seed, is_seed=True, move_type="out_refund")
        self.assertFalse(refund._is_seed_commercial_invoice_with_posted_delivery_cogs())

