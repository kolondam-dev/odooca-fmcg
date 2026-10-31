from odoo.tests.common import TransactionCase


class TestPromoGovernance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.principal_myr = cls.env.ref("id_base.principal_myr")
        cls.program = cls.env["loyalty.program"].create({
            "name": "Promo Uji Coba Kopi Mayora",
            "program_type": "promotion",
            "trigger": "auto",
            "mou_number": "MOU/TEST/2026/001",
            "principal_id": cls.principal_myr.id,
            "budget_source": "principal",
        })
        cls.rule = cls.env["loyalty.rule"].create({
            "program_id": cls.program.id,
            "minimum_qty": 1,
            "reward_point_amount": 1,
        })
        cls.reward = cls.env["loyalty.reward"].create({
            "program_id": cls.program.id,
            "reward_type": "discount",
            "discount": 10.0,
            "discount_mode": "percent",
            "required_points": 1,
        })

    def test_01_approval_workflow(self):
        """Uji transisi state workflow approval promo FMCG."""
        self.assertEqual(self.program.governance_state, "draft")

        # Ajukan approval
        self.program.action_submit_approval()
        self.assertEqual(self.program.governance_state, "pending")

        # Setujui
        self.program.action_approve()
        self.assertEqual(self.program.governance_state, "approved")
        self.assertEqual(self.program.approver_id, self.env.user)
        self.assertTrue(self.program.approval_date)

        # Aktifkan
        self.program.action_activate()
        self.assertEqual(self.program.governance_state, "active")
        self.assertTrue(self.program.active)

    def test_02_sku_wizard_attachment(self):
        """Uji wizard seleksi SKU menempelkan produk ke loyalty.rule."""
        product = self.env["product.product"].create({
            "name": "Torabika Creamy Latte Test",
            "principal_id": self.principal_myr.id,
            "list_price": 15000.0,
            "sale_ok": True,
        })

        wizard = self.env["id.promo.sku.wizard"].create({
            "program_id": self.program.id,
            "principal_id": self.principal_myr.id,
        })
        wizard._onchange_filter_products()
        self.assertIn(product, wizard.product_ids)

        wizard.action_apply_skus_to_promo()
        self.assertIn(product, self.rule.product_ids)

    def test_03_claim_amount_calculation(self):
        """Uji kalkulasi nominal klaim ke prinsipal pada baris order."""
        partner = self.env["res.partner"].create({"name": "Outlet Mitra Test"})
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
        })
        product = self.env["product.product"].create({
            "name": "Produk Diskon Test",
            "list_price": 100000.0,
        })
        line = self.env["sale.order.line"].create({
            "order_id": order.id,
            "product_id": product.id,
            "product_uom_qty": 1.0,
            "price_unit": 100000.0,
            "discount": 10.0,
            "promo_program_id": self.program.id,
        })

        # Diskon 10% dari 100.000 = 10.000
        self.assertAlmostEqual(line.promo_discount_amount, 10000.0, places=2)
        # 100% beban prinsipal = 10.000
        self.assertAlmostEqual(line.promo_claim_amount, 10000.0, places=2)

        # Ubah budget source menjadi joint sharing (50:50)
        self.program.budget_source = "joint"
        line._compute_promo_claim_amount()
        self.assertAlmostEqual(line.promo_claim_amount, 5000.0, places=2)
