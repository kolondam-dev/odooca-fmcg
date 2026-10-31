from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestApprovalEngine(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        # Grup wewenang
        cls.grp_user = cls.env.ref("id_approval.group_fmcg_approval_user")
        cls.grp_spv = cls.env.ref("id_approval.group_fmcg_approval_supervisor")
        cls.grp_mgr = cls.env.ref("id_approval.group_fmcg_approval_manager")
        cls.grp_dir = cls.env.ref("id_approval.group_fmcg_approval_director")

        # Buat user SPV, Manager, Director
        cls.user_spv = cls.env["res.users"].create({
            "name": "Supervisor Sales Uji",
            "login": "spv_test",
            "email": "spv@example.test",
            "group_ids": [(6, 0, [cls.grp_spv.id])],
        })
        cls.user_mgr = cls.env["res.users"].create({
            "name": "Branch Manager Uji",
            "login": "mgr_test",
            "email": "mgr@example.test",
            "group_ids": [(6, 0, [cls.grp_mgr.id])],
        })
        cls.user_dir = cls.env["res.users"].create({
            "name": "Owner Director Uji",
            "login": "dir_test",
            "email": "dir@example.test",
            "group_ids": [(6, 0, [cls.grp_dir.id])],
        })

        # Partner Cash & Tempo
        cls.partner_cash = cls.env["res.partner"].create({
            "name": "Kios Tunai Manado",
            "credit_mode": "cash",
            "credit_limit": 0.0,
        })
        cls.partner_tempo = cls.env["res.partner"].create({
            "name": "Toko Tempo Minahasa",
            "credit_mode": "limit",
            "credit_limit": 5_000_000.0,
        })

        # Product dengan HPP dan List Price
        cls.product = cls.env["product.product"].create({
            "name": "Kopi Susu Uji",
            "standard_price": 10_000.0,  # HPP = Rp 10.000
            "list_price": 12_000.0,      # Harga Jual Normal = Rp 12.000
        })

        # Akun Analitik untuk Diskon Taktikal
        cls.analytic_plan = cls.env["account.analytic.plan"].create({
            "name": "FMCG Commercial Plan",
        })
        cls.analytic_account = cls.env["account.analytic.account"].create({
            "name": "Beban Diskon Persaingan Lokal",
            "plan_id": cls.analytic_plan.id,
        })

    def test_01_credit_limit_cash_bypass_and_tempo_approval(self):
        """Pelanggan Cash tidak perlu approval, sedangkan Tempo memicu alur persetujuan."""
        # 1. Cash Partner: is_cash_customer harus True
        self.assertTrue(self.partner_cash.is_cash_customer)
        with self.assertRaises(UserError):
            self.partner_cash.action_request_credit_limit_approval()

        # 2. Tempo Partner: Ajukan approval kredit
        self.assertFalse(self.partner_tempo.is_cash_customer)
        action = self.partner_tempo.action_request_credit_limit_approval(reason="Permintaan limit Rp 5 jt outlet baru")
        req_id = action["res_id"]
        req = self.env["fmcg.approval.request"].browse(req_id)

        self.assertEqual(req.state, "pending")
        self.assertEqual(req.current_tier_sequence, 1)
        self.assertEqual(len(req.line_ids), 2)  # 2 tier: SPV lalu Manager
        self.assertEqual(self.partner_tempo.credit_approval_state, "pending")

        # Tier 1 (SPV) Approve
        req.with_user(self.user_spv).action_approve(notes="Verifikasi toko dan omset valid")
        self.assertEqual(req.state, "pending")
        self.assertEqual(req.current_tier_sequence, 2)

        # Tier 2 (Manager) Approve
        req.with_user(self.user_mgr).action_approve(notes="Plafon kredit disetujui")
        self.assertEqual(req.state, "approved")
        self.assertEqual(self.partner_tempo.credit_approval_state, "approved")

    def test_02_sale_order_below_hpp_blocks_confirmation(self):
        """Pesanan dengan harga net di bawah HPP diblokir dan wajib disetujui 2-line hingga Direksi."""
        # Buat order dengan harga rugi: Rp 8.000 < HPP Rp 10.000
        order = self.env["sale.order"].create({
            "partner_id": self.partner_tempo.id,
            "order_line": [
                (0, 0, {
                    "product_id": self.product.id,
                    "product_uom_qty": 10.0,
                    "price_unit": 8_000.0,
                }),
            ],
        })
        self.assertTrue(order.has_below_hpp)

        # Coba konfirmasi sebelum approval -> harus raise UserError
        with self.assertRaises(UserError):
            order.action_confirm()

        # Ajukan persetujuan 2-line ke Direksi
        action = order.action_request_below_hpp_approval(reason="Dumping cuci gudang stok mendekati ed")
        req = self.env["fmcg.approval.request"].browse(action["res_id"])
        self.assertEqual(req.state, "pending")
        self.assertEqual(req.current_tier_sequence, 1)

        # Tier 1: Branch Manager Approve
        req.with_user(self.user_mgr).action_approve(notes="Rekomendasi disetujui")
        self.assertEqual(req.state, "pending")
        self.assertEqual(req.current_tier_sequence, 2)

        # Masih belum bisa konfirmasi saat tier 2 belum approve
        with self.assertRaises(UserError):
            order.action_confirm()

        # Tier 2: Owner/Director Approve
        req.with_user(self.user_dir).action_approve(notes="Disetujui Owner")
        self.assertEqual(req.state, "approved")
        self.assertEqual(order.below_hpp_approval_state, "approved")

        # Sekarang bisa dikonfirmasi
        order.action_confirm()
        self.assertEqual(order.state, "sale")

    def test_03_tactical_discount_requires_analytic_account(self):
        """Diskon taktikal wajib mengisi akun analitik agar traceable."""
        order = self.env["sale.order"].create({
            "partner_id": self.partner_tempo.id,
            "order_line": [
                (0, 0, {
                    "product_id": self.product.id,
                    "product_uom_qty": 5.0,
                    "price_unit": 12_000.0,
                    "discount": 5.0,  # Diskon 5% manual
                }),
            ],
        })
        self.assertTrue(order.has_tactical_discount)

        # Coba ajukan tanpa akun analitik -> UserError
        with self.assertRaises(UserError):
            order.action_request_tactical_discount_approval()

        # Berikan akun analitik
        order.tactical_analytic_account_id = self.analytic_account.id
        action = order.action_request_tactical_discount_approval(reason="Pesaing memberi harga serupa")
        req = self.env["fmcg.approval.request"].browse(action["res_id"])
        self.assertEqual(req.state, "pending")
        self.assertEqual(req.analytic_account_id, self.analytic_account)

    def test_04_new_sku_activation_workflow(self):
        """SKU baru tidak aktif jual hingga disetujui manajemen."""
        prod_tmpl = self.env["product.template"].create({
            "name": "Biskuit Varian Baru",
            "fmcg_approval_state": "draft",
            "sale_ok": False,
        })
        self.assertFalse(prod_tmpl.sale_ok)

        # Ajukan aktivasi SKU
        action = prod_tmpl.action_request_new_sku_approval(reason="SKU baru dari Mayora")
        req = self.env["fmcg.approval.request"].browse(action["res_id"])
        self.assertEqual(prod_tmpl.fmcg_approval_state, "pending")

        # Manager approve
        req.with_user(self.user_mgr).action_approve(notes="Master data valid")
        self.assertEqual(prod_tmpl.fmcg_approval_state, "active")
        self.assertTrue(prod_tmpl.sale_ok)

    def test_05_rejection_workflow(self):
        """Penolakan pengajuan langsung membatalkan alur dan mengubah status ke rejected."""
        prod_tmpl = self.env["product.template"].create({
            "name": "SKU Gagal Lolos QC",
            "fmcg_approval_state": "draft",
            "sale_ok": False,
        })
        action = prod_tmpl.action_request_new_sku_approval(reason="SKU uji coba")
        req = self.env["fmcg.approval.request"].browse(action["res_id"])

        # Manager tolak
        req.with_user(self.user_mgr).action_reject(notes="Dokumen izin edar BPOM belum lengkap")
        self.assertEqual(req.state, "rejected")
        self.assertEqual(prod_tmpl.fmcg_approval_state, "rejected")
        self.assertFalse(prod_tmpl.sale_ok)

    def test_06_search_my_approval(self):
        """Memverifikasi pencarian filter is_current_user_approver berjalan tanpa error."""
        prod_tmpl = self.env["product.template"].create({
            "name": "SKU Search Test",
            "fmcg_approval_state": "draft",
            "sale_ok": False,
        })
        action = prod_tmpl.action_request_new_sku_approval(reason="Testing search filter")
        req = self.env["fmcg.approval.request"].browse(action["res_id"])

        # Sebagai user manager, request harus ditemukan saat mencari is_current_user_approver = True
        my_reqs = self.env["fmcg.approval.request"].with_user(self.user_mgr).search([
            ("is_current_user_approver", "=", True),
        ])
        self.assertIn(req, my_reqs)

