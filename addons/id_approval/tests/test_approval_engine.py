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

        # Payment terms Cash & Tempo
        cls.term_cash = cls.env["account.payment.term"].create({
            "name": "Tunai / Cash",
        })
        cls.term_tempo = cls.env["account.payment.term"].create({
            "name": "Tempo 14 Hari (Net 14)",
        })

        # Partner Cash & Tempo
        cls.partner_cash = cls.env["res.partner"].create({
            "name": "Kios Tunai Manado",
            "property_payment_term_id": cls.term_cash.id,
            "credit_limit": 0.0,
        })
        cls.partner_tempo = cls.env["res.partner"].create({
            "name": "Toko Tempo Minahasa",
            "property_payment_term_id": cls.term_tempo.id,
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

    def test_03b_mobile_auto_request_tactical_without_analytic(self):
        """BE-14: jalur lapangan membuat permintaan tanpa akun analitik, berjenjang, dan idempoten."""
        order = self.env["sale.order"].create({
            "partner_id": self.partner_tempo.id,
            "order_line": [
                (0, 0, {
                    "product_id": self.product.id,
                    "product_uom_qty": 5.0,
                    "price_unit": 12_000.0,
                    "discount": 5.0,
                }),
            ],
        })
        self.assertFalse(order.tactical_analytic_account_id)
        reqs = order._mobile_auto_request_approvals("Pesaing memberi harga serupa")
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs.category_id.code, "tactical_discount")
        self.assertEqual(reqs.state, "pending")
        self.assertEqual(reqs.discount_percent, 5.0)
        self.assertEqual(reqs.reason, "Pesaing memberi harga serupa")
        self.assertGreaterEqual(len(reqs.line_ids), 2)  # 5% > 3%: SPV lalu Branch Manager
        self.assertEqual(order.discount_approval_state, "pending")
        # Idempoten: panggilan kedua tidak membuat permintaan baru
        self.assertFalse(order._mobile_auto_request_approvals("ulang"))
        self.assertEqual(
            self.env["fmcg.approval.request"].search_count([
                ("res_model", "=", "sale.order"), ("res_id", "=", order.id)]), 1)

    def test_03c_mobile_auto_request_below_hpp(self):
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
        reqs = order._mobile_auto_request_approvals()
        self.assertIn("discount_below_hpp", reqs.mapped("category_id.code"))
        self.assertEqual(order.below_hpp_approval_state, "pending")

    def test_03d_mobile_auto_request_noop_without_discount(self):
        order = self.env["sale.order"].create({
            "partner_id": self.partner_cash.id,
            "order_line": [
                (0, 0, {
                    "product_id": self.product.id,
                    "product_uom_qty": 1.0,
                    "price_unit": 12_000.0,
                }),
            ],
        })
        self.assertFalse(order._mobile_auto_request_approvals())

    def _tactical_order(self, partner=None, product=None, qty=5.0, discount=5.0, extra_lines=()):
        lines = [(0, 0, {
            "product_id": (product or self.product).id,
            "product_uom_qty": qty,
            "price_unit": 12_000.0,
            "discount": discount,
        })]
        lines += list(extra_lines)
        return self.env["sale.order"].create({
            "partner_id": (partner or self.partner_tempo).id,
            "order_line": lines,
        })

    def _free_zone_rule(self):
        return self.env.ref("id_approval.rule_tactical_tier0")

    def test_07_tier0_default_zero_keeps_old_behaviour(self):
        """BE-15: Tier 0 tersedia, batas awal 0% sehingga diskon manual tetap perlu approval."""
        rule = self._free_zone_rule()
        self.assertTrue(rule.is_free_zone)
        self.assertEqual(rule.max_discount, 0.0)
        reqs = self._tactical_order(discount=1.0)._mobile_auto_request_approvals()
        self.assertEqual(reqs.category_id.code, "tactical_discount")
        self.assertEqual(reqs.state, "pending")
        # Tier 0 bukan langkah approver
        self.assertNotIn(rule, reqs.line_ids.mapped("rule_id"))

    def test_08_free_zone_skips_approval_and_above_limit_chains(self):
        self._free_zone_rule().max_discount = 4.0
        within = self._tactical_order(discount=4.0)
        self.assertFalse(within._mobile_auto_request_approvals())
        self.assertEqual(within.discount_approval_state, "none")
        above = self._tactical_order(discount=5.0)
        reqs = above._mobile_auto_request_approvals()
        self.assertEqual(reqs.state, "pending")
        self.assertEqual(len(reqs.line_ids), 2)  # SPV lalu Branch Manager, berjenjang

    def test_09_free_zone_via_form_button_auto_approves(self):
        self._free_zone_rule().max_discount = 4.0
        order = self._tactical_order(discount=3.0)
        order.tactical_analytic_account_id = self.analytic_account.id
        action = order.action_request_tactical_discount_approval(reason="Dalam zona bebas")
        req = self.env["fmcg.approval.request"].browse(action["res_id"])
        self.assertEqual(req.state, "approved")
        self.assertFalse(req.line_ids)
        self.assertEqual(order.discount_approval_state, "approved")

    def test_10_cumulative_includes_program_reward_lines(self):
        """Diskon baris + baris reward program resmi digabung berbobot nilai."""
        order = self._tactical_order(discount=5.0, extra_lines=[(0, 0, {
            "product_id": self.product.id,
            "product_uom_qty": 1.0,
            "price_unit": -3_000.0,
        })])
        # gross 60.000; diskon 3.000 (5%) + reward 3.000 = 6.000 -> 10%
        self.assertAlmostEqual(order._approval_cumulative_discount_pct("order"), 10.0, places=2)

    def test_11_principal_specific_free_zone_overrides_default(self):
        principal = self.env["id.principal"].create({"name": "Principal Uji", "code": "PRU"})
        product_p = self.env["product.product"].create({
            "name": "Produk Principal Uji", "standard_price": 10_000.0,
            "list_price": 12_000.0, "principal_id": principal.id,
        })
        category = self._free_zone_rule().category_id
        self.env["fmcg.approval.rule"].create({
            "category_id": category.id, "tier_sequence": 0, "name": "Zona bebas Principal Uji",
            "approver_type": "group", "group_id": self.grp_spv.id,
            "is_free_zone": True, "max_discount": 6.0, "principal_id": principal.id,
        })
        # Principal Uji: 5% masih zona bebas; default (0%) tetap perlu approval
        order_p = self._tactical_order(product=product_p, discount=5.0)
        self.assertEqual(order_p._approval_principal_id(), principal.id)
        self.assertFalse(order_p._mobile_auto_request_approvals())
        order_default = self._tactical_order(discount=5.0)
        self.assertTrue(order_default._mobile_auto_request_approvals())
        # Aturan khusus principal juga menimpa tier umum: di atas 6% tetap melalui rantai
        order_p2 = self._tactical_order(product=product_p, discount=8.0)
        self.assertTrue(order_p2._mobile_auto_request_approvals())

    def test_12_cumulative_scope_outlet_month_accumulates_orders(self):
        category = self._free_zone_rule().category_id
        category.cumulative_scope = "outlet_month"
        prior = self._tactical_order(qty=10.0, discount=0.0)  # bruto 120.000, tanpa diskon
        order = self._tactical_order(qty=5.0, discount=5.0)   # bruto 60.000, diskon 3.000
        self.assertNotEqual(prior, order)
        # 3.000 / (60.000 + 120.000) = 1,6667%
        self.assertAlmostEqual(order._approval_cumulative_discount_pct("outlet_month"), 1.6667, places=3)
        self.assertAlmostEqual(order._approval_cumulative_discount_pct("order"), 5.0, places=3)
        self._free_zone_rule().max_discount = 2.0
        self.assertFalse(order._mobile_auto_request_approvals())  # kumulatif 1,67% <= 2%

    def _principal_product(self, code):
        principal = self.env["id.principal"].create({"name": f"Principal {code}", "code": code})
        product = self.env["product.product"].create({
            "name": f"Produk {code}", "standard_price": 10_000.0,
            "list_price": 12_000.0, "principal_id": principal.id,
        })
        return principal, product

    def _dated_order(self, date_order, **kwargs):
        order = self._tactical_order(**kwargs)
        order.date_order = date_order
        return order

    def test_13_window_boundaries_follow_wita_not_utc(self):
        """Review PR #176: hari/bulan kerja WITA (UTC+8), bukan batas UTC."""
        category = self._free_zone_rule().category_id
        category.cumulative_scope = "salesman_day"
        # 20 Nov 2026 pukul 10.00 WITA
        order = self._dated_order("2026-11-20 02:00:00", qty=5.0, discount=5.0)
        # 20 Nov 04.00 WITA (UTC 19 Nov 20.00): hari WITA yang sama -> ikut
        self._dated_order("2026-11-19 20:00:00", qty=10.0, discount=0.0)
        # 19 Nov 20.00 WITA (UTC 19 Nov 12.00): hari WITA sebelumnya -> tidak ikut
        self._dated_order("2026-11-19 12:00:00", qty=100.0, discount=0.0)
        # gross 60.000 + 120.000; diskon 3.000 -> 1,6667% (bukan ~0,2% bila hari sebelumnya ikut)
        self.assertAlmostEqual(order._approval_cumulative_discount_pct("salesman_day"), 1.6667, places=3)

        category.cumulative_scope = "outlet_month"
        dec = self._dated_order("2026-12-01 05:00:00", qty=5.0, discount=5.0)
        self._dated_order("2026-11-30 17:00:00", qty=10.0, discount=0.0)   # 1 Des 01.00 WITA -> ikut
        self._dated_order("2026-11-30 10:00:00", qty=100.0, discount=0.0)  # 30 Nov 18.00 WITA -> tidak
        self.assertAlmostEqual(dec._approval_cumulative_discount_pct("outlet_month"), 1.6667, places=3)

    def test_14_window_excludes_other_company(self):
        category = self._free_zone_rule().category_id
        category.cumulative_scope = "outlet_month"
        order = self._tactical_order(qty=5.0, discount=5.0)
        other_company = self.env["res.company"].create({"name": "Perusahaan Lain Uji"})
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", other_company.id)], limit=1)
        other = self.env["sale.order"].with_company(other_company).create({
            "partner_id": self.partner_tempo.id,
            "company_id": other_company.id,
            "warehouse_id": warehouse.id,
            "order_line": [(0, 0, {"product_id": self.product.id, "product_uom_qty": 100.0,
                                   "price_unit": 12_000.0, "discount": 0.0})],
        })
        self.assertNotEqual(order.company_id, other.company_id)
        self.assertAlmostEqual(order._approval_cumulative_discount_pct("outlet_month"), 5.0, places=3)

    def test_15_multi_principal_evaluated_per_principal(self):
        """10% pada principal A tidak boleh larut oleh penjualan principal B tanpa diskon."""
        principal_a, product_a = self._principal_product("PRA")
        principal_b, product_b = self._principal_product("PRB")
        self._free_zone_rule().max_discount = 2.0
        order = self.env["sale.order"].create({
            "partner_id": self.partner_tempo.id,
            "order_line": [
                (0, 0, {"product_id": product_a.id, "product_uom_qty": 5.0,
                        "price_unit": 12_000.0, "discount": 10.0}),
                (0, 0, {"product_id": product_b.id, "product_uom_qty": 50.0,
                        "price_unit": 12_000.0, "discount": 0.0}),
            ],
        })
        by_principal = order._approval_cumulative_by_principal("order")
        self.assertAlmostEqual(by_principal[principal_a.id], 10.0, places=3)
        self.assertAlmostEqual(by_principal[principal_b.id], 0.0, places=3)
        reqs = order._mobile_auto_request_approvals()
        self.assertEqual(reqs.principal_id, principal_a)
        self.assertAlmostEqual(reqs.discount_percent, 10.0, places=3)
        self.assertEqual(len(reqs.line_ids), 3)  # 10% > 7%: SPV, Branch Manager, Direksi

    def test_16_multi_principal_chain_follows_highest_tier(self):
        principal_a, product_a = self._principal_product("PRC")
        principal_b, product_b = self._principal_product("PRD")
        order = self.env["sale.order"].create({
            "partner_id": self.partner_tempo.id,
            "order_line": [
                (0, 0, {"product_id": product_a.id, "product_uom_qty": 5.0,
                        "price_unit": 12_000.0, "discount": 2.0}),
                (0, 0, {"product_id": product_b.id, "product_uom_qty": 5.0,
                        "price_unit": 12_000.0, "discount": 8.0}),
            ],
        })
        reqs = order._mobile_auto_request_approvals()
        self.assertEqual(reqs.principal_id, principal_b)
        self.assertEqual(len(reqs.line_ids), 3)

    def test_17_free_zone_requires_every_principal_within_limit(self):
        principal_a, product_a = self._principal_product("PRE")
        principal_b, product_b = self._principal_product("PRF")
        self._free_zone_rule().max_discount = 4.0
        order = self.env["sale.order"].create({
            "partner_id": self.partner_tempo.id,
            "order_line": [
                (0, 0, {"product_id": product_a.id, "product_uom_qty": 5.0,
                        "price_unit": 12_000.0, "discount": 3.0}),
                (0, 0, {"product_id": product_b.id, "product_uom_qty": 5.0,
                        "price_unit": 12_000.0, "discount": 5.0}),
            ],
        })
        reqs = order._mobile_auto_request_approvals()
        self.assertTrue(reqs, "principal B (5%) melewati zona bebas 4%")
        self.assertEqual(reqs.principal_id, principal_b)

    def test_18_reward_line_attributed_to_its_own_principal(self):
        principal_a, product_a = self._principal_product("PRG")
        principal_b, product_b = self._principal_product("PRH")
        order = self.env["sale.order"].create({
            "partner_id": self.partner_tempo.id,
            "order_line": [
                (0, 0, {"product_id": product_a.id, "product_uom_qty": 5.0,
                        "price_unit": 12_000.0, "discount": 0.0}),
                (0, 0, {"product_id": product_b.id, "product_uom_qty": 5.0,
                        "price_unit": 12_000.0, "discount": 0.0}),
                (0, 0, {"product_id": product_b.id, "product_uom_qty": 1.0,
                        "price_unit": -6_000.0}),
            ],
        })
        by_principal = order._approval_cumulative_by_principal("order")
        self.assertAlmostEqual(by_principal[principal_a.id], 0.0, places=3)
        self.assertAlmostEqual(by_principal[principal_b.id], 10.0, places=3)

    def _reward_line(self):
        """Baris reward program (bernilai negatif) pada produk tanpa HPP agar tidak memicu 'di bawah HPP'."""
        reward = self.env["product.product"].create({
            "name": "Reward Program Uji", "standard_price": 0.0, "list_price": 0.0})
        return (0, 0, {"product_id": reward.id, "product_uom_qty": 1.0, "price_unit": -3_000.0})

    def test_19_no_principal_group_keeps_general_rules_on_submit(self):
        """Review PR #176 (P1): kelompok tanpa principal tidak boleh memakai batas principal pertama."""
        principal, product_p = self._principal_product("PRI")
        category = self._free_zone_rule().category_id
        self.env["fmcg.approval.rule"].create({
            "category_id": category.id, "tier_sequence": 0, "name": "Zona bebas Principal Uji",
            "approver_type": "group", "group_id": self.grp_spv.id,
            "is_free_zone": True, "max_discount": 6.0, "principal_id": principal.id,
        })
        for lines_reversed in (False, True):
            lines = [
                (0, 0, {"product_id": product_p.id, "product_uom_qty": 5.0,
                        "price_unit": 12_000.0, "discount": 0.0}),   # principal berbatas 6%
                (0, 0, {"product_id": self.product.id, "product_uom_qty": 5.0,
                        "price_unit": 12_000.0, "discount": 5.0}),   # tanpa principal, batas umum 0%
            ]
            if lines_reversed:
                lines.reverse()
            order = self.env["sale.order"].create({"partner_id": self.partner_tempo.id, "order_line": lines})
            reqs = order._mobile_auto_request_approvals()
            self.assertEqual(len(reqs), 1, f"reversed={lines_reversed}")
            self.assertEqual(reqs.state, "pending", f"reversed={lines_reversed}")
            self.assertTrue(reqs.principal_decided)
            self.assertFalse(reqs.principal_id)
            self.assertEqual(len(reqs.line_ids), 2)  # tier umum: SPV lalu Branch Manager

    def test_20_pure_official_promo_goes_to_supervisor_only(self):
        """Keputusan pemilik: pesanan murni promo resmi tetap approval, hanya hingga Supervisor."""
        category = self.env.ref("id_approval.cat_promo_program_usage")
        self.assertEqual(len(category.rule_ids), 1)
        order = self._tactical_order(discount=0.0, extra_lines=[self._reward_line()])
        self.assertFalse(order.has_tactical_discount)
        self.assertTrue(order._has_program_discount())
        reqs = order._mobile_auto_request_approvals()
        self.assertEqual(reqs.category_id.code, "promo_program_usage")
        self.assertEqual(reqs.state, "pending")
        self.assertEqual(len(reqs.line_ids), 1)
        self.assertEqual(reqs.line_ids.rule_id.group_id, self.env.ref("id_approval.group_fmcg_approval_supervisor"))
        # idempoten
        self.assertFalse(order._mobile_auto_request_approvals())

    def test_21_promo_with_manual_discount_uses_single_tactical_chain(self):
        order = self._tactical_order(discount=5.0, extra_lines=[self._reward_line()])
        reqs = order._mobile_auto_request_approvals()
        self.assertEqual(reqs.mapped("category_id.code"), ["tactical_discount"])

    def _promo_order(self):
        order = self._tactical_order(discount=0.0, extra_lines=[self._reward_line()])
        reqs = order._mobile_auto_request_approvals()
        self.assertEqual(reqs.category_id.code, "promo_program_usage")
        return order, reqs

    def test_22_promo_request_blocks_confirmation_until_supervisor_approves(self):
        """Review PR #176 (P1): pengajuan promo mengendalikan konfirmasi SO."""
        order, req = self._promo_order()
        with self.assertRaises(UserError):  # pending
            order.action_confirm()
        req.with_user(self.user_spv).action_approve(notes="Sesuai alokasi")
        self.assertEqual(req.state, "approved")
        order.action_confirm()
        self.assertEqual(order.state, "sale")

    def test_23_rejected_promo_request_blocks_confirmation(self):
        order, req = self._promo_order()
        req.with_user(self.user_spv).action_reject(notes="Melebihi alokasi")
        self.assertEqual(req.state, "rejected")
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_24_tactical_request_blocks_confirmation_while_pending(self):
        order = self._tactical_order(discount=5.0)
        req = order._mobile_auto_request_approvals()
        self.assertEqual(req.state, "pending")
        with self.assertRaises(UserError):
            order.action_confirm()

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

