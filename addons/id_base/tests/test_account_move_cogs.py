# Part of odooca-fmcg. License LGPL-3.
"""Odoo TransactionCase untuk ekstensi akuntansi perpetual FMCG account.move."""

import copy
from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


class MockRecordSet(list):
    """Mock recordset yang mendukung traversal Many2one/Many2many untuk kompatibilitas sale_stock."""
    def __getattr__(self, name):
        vals = [getattr(x, name, None) for x in self if getattr(x, name, None) is not None]
        flat = []
        for v in vals:
            if isinstance(v, list):
                flat.extend(v)
            else:
                flat.append(v)
        return MockRecordSet(flat)

    def mapped(self, field_name):
        return [getattr(x, field_name, False) for x in self]

    def filtered(self, func):
        return MockRecordSet([x for x in self if func(x)])


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

        # Daftarkan ID company seed secara eksak pada ir.config_parameter fmcg.seed_company_id
        cls.env["ir.config_parameter"].sudo().set_param("fmcg.seed_company_id", str(cls.company_seed.id))

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
        cls.product_alt = cls.env["product.product"].create({
            "name": "SKU Foreign Test",
            "standard_price": 50000.0,
            "list_price": 60000.0,
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

        vals = {
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
        }
        if is_seed:
            vals["fmcg_seed_batch"] = "CANONICAL_JULY_2026_PERPETUAL"
            vals["invoice_origin"] = "SO-202607-0001"

        return target_model.create(vals)

    def _build_valid_stj_and_sm(self):
        """Helper untuk membuat pasangan valid stock move dan STJ account.move."""
        aml_debit = SimpleNamespace(
            account_id=SimpleNamespace(code="510000"),
            debit=250000.0,
            credit=0.0,
            product_id=self.product,
        )
        aml_credit = SimpleNamespace(
            account_id=SimpleNamespace(code="113000"),
            debit=0.0,
            credit=250000.0,
            product_id=self.product,
        )
        valid_stj_am = SimpleNamespace(
            id=993,
            name="STJ/2026/001",
            state="posted",
            date="2026-07-02",
            company_id=self.company_seed,
            journal_id=SimpleNamespace(code="STJ"),
            line_ids=[aml_debit, aml_credit],
        )
        fake_sm = SimpleNamespace(
            id=883,
            name="OUT/TEST/03",
            state="done",
            date="2026-07-02",
            quantity=10.0,
            value=250000.0,
            product_id=self.product,
            company_id=self.company_seed,
            location_dest_id=SimpleNamespace(usage="customer"),
            location_id=SimpleNamespace(usage="internal"),
            account_move_id=valid_stj_am,
        )
        fake_sol = SimpleNamespace(
            name="SO Line 1",
            order_id=SimpleNamespace(
                name="SO-202607-0001",
                company_id=self.company_seed,
                fmcg_seed_batch="CANONICAL_JULY_2026_PERPETUAL",
                incoterm_location=False,
            ),
            move_ids=[fake_sm],
        )
        return fake_sol, fake_sm, valid_stj_am

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
        self.assertIn("bukan company seed resmi FMCG", str(ctx.exception))

    def test_marked_seed_without_delivery_moves_raises_user_error(self):
        """Kasus 3: Invoice bertanda seed tanpa link delivery move wajib ditolak fail-closed."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        # 3a: Tanpa relasi sale_line_ids
        with self.assertRaises(UserError) as ctx:
            inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
        self.assertIn("tidak memiliki relasi sale_line_ids", str(ctx.exception))

        # 3b: Dengan sale_line_ids tetapi tanpa pergerakan pengiriman (move_ids kosong)
        line = inv.invoice_line_ids[0]
        fake_sol_empty = SimpleNamespace(
            name="Empty SOL",
            order_id=SimpleNamespace(
                name="SO-202607-0001",
                company_id=self.company_seed,
                fmcg_seed_batch="CANONICAL_JULY_2026_PERPETUAL",
                incoterm_location=False,
            ),
            move_ids=[],
        )
        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol_empty]), create=True):
            with self.assertRaises(UserError) as ctx:
                inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
            self.assertIn("tidak memiliki pergerakan pengiriman", str(ctx.exception))

    def test_marked_seed_with_unposted_cogs_journal_raises_user_error(self):
        """Kasus 4: Invoice bertanda seed dengan jurnal STJ belum posted wajib ditolak fail-closed."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]

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
            company_id=self.company_seed,
            product_id=self.product,
            location_dest_id=SimpleNamespace(usage="customer"),
            location_id=SimpleNamespace(usage="internal"),
            quantity=10.0,
            date="2026-07-02",
        )
        fake_sol = SimpleNamespace(
            order_id=SimpleNamespace(name="SO-202607-0001", company_id=self.company_seed),
            move_ids=[fake_sm],
        )

        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
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
            company_id=self.company_seed,
            product_id=self.product,
            location_dest_id=SimpleNamespace(usage="customer"),
            location_id=SimpleNamespace(usage="internal"),
            quantity=10.0,
            date="2026-07-02",
        )
        fake_sol = SimpleNamespace(
            order_id=SimpleNamespace(name="SO-202607-0001", company_id=self.company_seed),
            move_ids=[fake_sm],
        )

        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
            with self.assertRaises(UserError) as ctx:
                inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
            self.assertIn("diharapkan 'STJ'", str(ctx.exception))

    def test_positive_seed_invoice_suppresses_duplicate_cogs(self):
        """Kasus 5: Invoice seed valid dengan bukti HPP lengkap singular account_move_id STJ mengembalikan []."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]
        fake_sol, _, _ = self._build_valid_stj_and_sm()

        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
            self.assertTrue(inv._is_seed_commercial_invoice_with_posted_delivery_cogs())
            # COGS duplikat disupresi (mengembalikan [])
            out_vals = inv._stock_account_prepare_realtime_out_lines_vals()
            self.assertEqual(out_vals, [])

    def test_wrong_journal_date_rejected(self):
        """Kasus P1: Jurnal STJ dengan tanggal beda (e.g. 1999-01-01) wajib ditolak fail-closed."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]
        fake_sol, _, valid_stj_am = self._build_valid_stj_and_sm()
        valid_stj_am.date = "1999-01-01"

        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
            with self.assertRaises(UserError) as ctx:
                inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
            self.assertIn("Tanggal jurnal valuasi '1999-01-01' tidak cocok", str(ctx.exception))

    def test_wrong_valuation_value_rejected(self):
        """Kasus P1: Jurnal STJ dengan nilai tidak cocok (e.g. 1.0 vs 250000.0) wajib ditolak fail-closed."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]
        fake_sol, _, valid_stj_am = self._build_valid_stj_and_sm()
        # Modifikasi nilai debit/credit di STJ menjadi 1.0 padahal move.value = 250000.0
        for aml in valid_stj_am.line_ids:
            if aml.debit > 0:
                aml.debit = 1.0
            if aml.credit > 0:
                aml.credit = 1.0

        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
            with self.assertRaises(UserError) as ctx:
                inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
            self.assertIn("tidak sesuai dengan nilai valuasi pergerakan barang", str(ctx.exception))

    def test_wrong_product_on_move_rejected(self):
        """Kasus P1: Pergerakan stok produk beda dengan baris faktur wajib ditolak."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]
        fake_sol, fake_sm, _ = self._build_valid_stj_and_sm()
        fake_sm.product_id = self.product_alt

        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
            with self.assertRaises(UserError) as ctx:
                inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
            self.assertIn("tidak cocok dengan produk baris faktur", str(ctx.exception))

    def test_wrong_move_company_rejected(self):
        """Kasus P1: Pergerakan stok dari company lain wajib ditolak fail-closed."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]
        fake_sol, fake_sm, _ = self._build_valid_stj_and_sm()
        fake_sm.company_id = self.company_foreign

        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
            with self.assertRaises(UserError) as ctx:
                inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
            self.assertIn("berasal dari company lain", str(ctx.exception))

    def test_missing_seed_batch_rejected(self):
        """Kasus P1: Invoice bertanda is_fmcg_seed_invoice tanpa batch persisten ditolak."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        inv.fmcg_seed_batch = False
        with self.assertRaises(UserError) as ctx:
            inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
        self.assertIn("tidak memiliki batch identitas seed resmi", str(ctx.exception))

    def test_missing_singular_account_move_id_rejected(self):
        """Kasus P1: Stock move tanpa singular account_move_id wajib ditolak fail-closed."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]
        fake_sol, fake_sm, _ = self._build_valid_stj_and_sm()
        fake_sm.account_move_id = False

        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
            with self.assertRaises(UserError) as ctx:
                inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
            self.assertIn("account_move_id kosong", str(ctx.exception))

    def test_mixed_recordset_suppresses_only_seed(self):
        """Kasus P1: Recordset campuran (seed + ordinary) hanya mensupresi seed dan memanggil native untuk non-seed."""
        inv_seed = self._create_basic_invoice(self.company_seed, is_seed=True)
        inv_ordinary = self._create_basic_invoice(self.company_seed, is_seed=False)

        line_seed = inv_seed.invoice_line_ids[0]
        fake_sol, _, _ = self._build_valid_stj_and_sm()

        mixed_moves = inv_seed | inv_ordinary

        # Mock parent native call pada class AccountMove
        with patch.object(type(line_seed), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
            # inv_seed adalah seed valid
            self.assertTrue(inv_seed._is_seed_commercial_invoice_with_posted_delivery_cogs())
            # inv_ordinary adalah non-seed
            self.assertFalse(inv_ordinary._is_seed_commercial_invoice_with_posted_delivery_cogs())

            patch_target = (
                "odoo.addons.stock_account.models.account_move.AccountMove"
                "._stock_account_prepare_realtime_out_lines_vals"
            )
            with patch(patch_target, return_value=[{"account_id": 510000, "debit": 99000.0}], create=True):
                mixed_res = mixed_moves._stock_account_prepare_realtime_out_lines_vals()
                # Hasil parent native HANYA dipanggil untuk non-seed moves
                self.assertEqual(mixed_res, [{"account_id": 510000, "debit": 99000.0}])

    def test_vendor_bill_and_refund_call_native(self):
        """Kasus 6: Vendor bill dan refund pelanggan tidak pernah disupresi oleh hook seed."""
        bill = self._create_basic_invoice(self.company_seed, is_seed=True, move_type="in_invoice")
        self.assertFalse(bill._is_seed_commercial_invoice_with_posted_delivery_cogs())

        refund = self._create_basic_invoice(self.company_seed, is_seed=True, move_type="out_refund")
        self.assertFalse(refund._is_seed_commercial_invoice_with_posted_delivery_cogs())

    def test_two_moves_sharing_single_aml_rejected(self):
        """Review 6483144753: Dua stock move bernilai 500k dengan hanya 1 AML 250k wajib ditolak."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]
        line.quantity = 20.0
        fake_sol, fake_sm, valid_stj_am = self._build_valid_stj_and_sm()
        fake_sm2 = copy.copy(fake_sm)
        fake_sm2.id = 884
        fake_sol.move_ids = [fake_sm, fake_sm2]

        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
            with self.assertRaises(UserError) as ctx:
                inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
            self.assertIn("tidak sesuai dengan nilai valuasi pergerakan barang", str(ctx.exception))

    def test_two_moves_with_two_amls_accepted(self):
        """Review 6483144753: Dua stock move dengan dua AML (500k vs 500k) wajib diterima."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]
        line.quantity = 20.0
        fake_sol, fake_sm, valid_stj_am = self._build_valid_stj_and_sm()
        fake_sm2 = copy.copy(fake_sm)
        fake_sm2.id = 884
        fake_sol.move_ids = [fake_sm, fake_sm2]

        aml_debit2 = SimpleNamespace(
            account_id=SimpleNamespace(code="510000"),
            debit=250000.0,
            credit=0.0,
            product_id=self.product,
        )
        aml_credit2 = SimpleNamespace(
            account_id=SimpleNamespace(code="113000"),
            debit=0.0,
            credit=250000.0,
            product_id=self.product,
        )
        valid_stj_am.line_ids.extend([aml_debit2, aml_credit2])

        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
            self.assertTrue(inv._is_seed_commercial_invoice_with_posted_delivery_cogs())

    def test_direction_supplier_rejected(self):
        """Review 6483144753: Stock move dengan tujuan supplier wajib ditolak fail-closed."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]
        fake_sol, fake_sm, _ = self._build_valid_stj_and_sm()
        fake_sm.location_dest_id = SimpleNamespace(usage="supplier")

        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
            with self.assertRaises(UserError) as ctx:
                inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
            self.assertIn("Arah pergerakan stok", str(ctx.exception))

    def test_direction_source_customer_rejected(self):
        """Review 6483144753: Outbound stock move dengan asal bukan internal wajib ditolak."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]
        fake_sol, fake_sm, _ = self._build_valid_stj_and_sm()
        fake_sm.location_id = SimpleNamespace(usage="customer")

        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
            with self.assertRaises(UserError) as ctx:
                inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
            self.assertIn("Arah pergerakan stok", str(ctx.exception))

    def test_order_without_seed_batch_rejected(self):
        """Review 6483144753: SO tanpa fmcg_seed_batch resmi wajib ditolak fail-closed."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]
        fake_sol, _, _ = self._build_valid_stj_and_sm()
        fake_sol.order_id.fmcg_seed_batch = False

        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
            with self.assertRaises(UserError) as ctx:
                inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
            self.assertIn("memiliki batch identitas", str(ctx.exception))

    def test_uom_conversion_quantity_mismatch_rejected(self):
        """Review 6483144753: Invoice 2 karton @144 unit vs delivery 10 unit wajib ditolak."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]
        line.quantity = 2.0
        line.product_uom_id = SimpleNamespace(name="Karton", factor_inv=144.0, factor=1.0 / 144.0)
        fake_sol, fake_sm, _ = self._build_valid_stj_and_sm()
        fake_sm.quantity = 10.0

        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
            with self.assertRaises(UserError) as ctx:
                inv._is_seed_commercial_invoice_with_posted_delivery_cogs()
            self.assertIn("tidak cocok dengan kuantitas baris faktur", str(ctx.exception))

    def test_partial_rejection_scenario_accepted(self):
        """Review 6483144753: Rekonsiliasi eksplisit 84 dikirim - 12 retur = 72 ditagih."""
        inv = self._create_basic_invoice(self.company_seed, is_seed=True)
        line = inv.invoice_line_ids[0]
        line.quantity = 72.0
        fake_sol, fake_sm, valid_stj_am = self._build_valid_stj_and_sm()
        fake_sm.quantity = 84.0
        fake_sm.value = 84.0 * 25000.0

        valid_stj_am.line_ids[0].debit = fake_sm.value
        valid_stj_am.line_ids[1].credit = fake_sm.value

        return_sm = SimpleNamespace(
            id=885,
            name="RET/TEST/01",
            state="done",
            date="2026-07-02",
            quantity=12.0,
            product_id=self.product,
            company_id=self.company_seed,
            location_id=SimpleNamespace(usage="customer"),
            location_dest_id=SimpleNamespace(usage="internal"),
        )
        fake_sol.move_ids = [fake_sm, return_sm]

        with patch.object(type(line), "sale_line_ids", MockRecordSet([fake_sol]), create=True):
            self.assertTrue(inv._is_seed_commercial_invoice_with_posted_delivery_cogs())
