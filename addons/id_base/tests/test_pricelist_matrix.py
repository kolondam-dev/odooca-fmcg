from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestPricelistMatrix(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.channel_mt = cls.env.ref("id_base.channel_mt")
        cls.channel_gt = cls.env.ref("id_base.channel_gt")
        cls.cov_urban = cls.env["id.coverage.area"].search([("category", "=", "urban")], limit=1)
        if not cls.cov_urban:
            cls.cov_urban = cls.env["id.coverage.area"].create({
                "name": "Manado Kota Test",
                "code": "MND-TEST",
                "category": "urban",
            })

        cls.product = cls.env["product.product"].create({
            "name": "Kopi Test Sachet",
            "list_price": 10000.0,
            "standard_price": 7500.0,
            "type": "consu",
        })

    def test_01_pricelist_expiry_state_computation(self):
        """Uji perhitungan dinamis expiry_state: active, near_expiry, expired."""
        today = fields.Date.context_today(self.env.user)
        pl = self.env["product.pricelist"].create({
            "name": "Test PL Expiry",
            "is_fmcg_matrix": True,
            "channel_id": self.channel_mt.id,
            "date_start": today - timedelta(days=30),
            "date_end": today + timedelta(days=5),
            "alert_days_before": 14,
        })
        self.assertEqual(pl.expiry_state, "near_expiry")

        # Uji expired
        pl.date_end = today - timedelta(days=1)
        self.assertEqual(pl.expiry_state, "expired")

        # Uji active
        pl.date_end = today + timedelta(days=60)
        self.assertEqual(pl.expiry_state, "active")

    def test_02_partner_matrix_pricelist_resolution(self):
        """Uji resolusi otomatis pricelist berdasarkan channel dan coverage partner."""
        partner = self.env["res.partner"].create({
            "name": "Toko Retail Manado Test",
            "channel_id": self.channel_mt.id,
            "coverage_area_id": self.cov_urban.id,
        })
        pl = partner._get_matrix_pricelist()
        self.assertTrue(pl)
        self.assertEqual(pl.channel_id, self.channel_mt)

        partner.action_assign_matrix_pricelist()
        self.assertEqual(partner.property_product_pricelist, pl)

    def test_03_price_computation_formula(self):
        """Uji kalkulasi harga dengan formula diskon MT (-5%)."""
        pl_mt = self.env.ref("id_base.pricelist_fmcg_mt")
        calculated_price = pl_mt._get_product_price(self.product, 1.0)
        # 10.000 diskon 5% = 9.500
        self.assertAlmostEqual(calculated_price, 9500.0, places=2)

