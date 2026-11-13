from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestFMCGDimensionsUoM(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.principal = cls.env["id.principal"].create({
            "name": "PT Mayora Indah",
            "code": "PRIN-MAYORA",
        })
        cls.brand = cls.env["id.brand"].create({
            "name": "Roma",
            "code": "BRD-RMA",
            "principal_id": cls.principal.id,
        })
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")

    def test_01_product_dimensions_and_weight_computation(self):
        """Verifikasi bahwa 14 kolom FMCG dan komputasi dua arah bobot/kubikasi berjalan presisi."""
        product = self.env["product.template"].create({
            "name": "Roma Kelapa 300g",
            "default_code": "MYR-RMA-01",
            "principal_id": self.principal.id,
            "brand_id": self.brand.id,
            "fmcg_category": "biscuit_wafer",
            "uom_id": self.uom_unit.id,
            "weight": 0.3,
            "inner_qty": 1,
            "carton_qty": 30,
            "carton_length_cm": 39.3,
            "carton_width_cm": 28.3,
            "carton_height_cm": 40.1,
            "carton_weight_kg": 9.45,
            "carton_barcode": "1899275310001",
            "standard_price": 7500.0,
            "list_price": 8500.0,
        })

        # Cek konversi otomatis kg -> g
        self.assertAlmostEqual(product.base_weight_g, 300.0, places=1)

        # Cek komputasi kubikasi karton (39.3 * 28.3 * 40.1 / 1000000 = 0.0446 m3)
        self.assertAlmostEqual(product.carton_volume_cbm, 0.0446, places=4)

        # Cek inverse gramasi g -> kg
        product.write({"base_weight_g": 250.0})
        self.assertAlmostEqual(product.weight, 0.25, places=2)

    def test_02_native_uom_records_exist(self):
        """Verifikasi bahwa satuan-satuan native FMCG tersedia di registry."""
        uom_pcs = self.env.ref("id_base.uom_pcs", raise_if_not_found=False)
        self.assertTrue(uom_pcs, "id_base.uom_pcs wajib ada!")
        self.assertEqual(uom_pcs.name, "Pieces")

        uom_sch = self.env.ref("id_base.uom_sch", raise_if_not_found=False)
        self.assertTrue(uom_sch, "id_base.uom_sch wajib ada!")

        uom_karton = self.env.ref("id_base.uom_karton", raise_if_not_found=False)
        self.assertTrue(uom_karton, "id_base.uom_karton wajib ada!")


    def test_04_native_per_sku_packaging_uom_hierarchy(self):
        """SKU packaging uses Odoo 19 UoMs while preserving the inventory UoM."""
        product = self.env["product.template"].create({
            "name": "Coffee Sachet Test",
            "default_code": "TEST-UOM-SACHET",
            "principal_id": self.principal.id,
            "brand_id": self.brand.id,
            "uom_id": self.uom_unit.id,
            "standard_price": 1000.0,
            "list_price": 1500.0,
        })
        base_uom = self.env.ref("id_base.uom_sch")
        product.configure_fmcg_packaging_uoms(base_uom, inner_qty=10, carton_qty=120)

        self.assertEqual(product.uom_id, self.uom_unit)
        self.assertEqual(product.fmcg_base_uom_id, base_uom)
        self.assertTrue(product.fmcg_inner_uom_id)
        self.assertTrue(product.fmcg_carton_uom_id)
        self.assertIn(base_uom, product.uom_ids)
        self.assertIn(product.fmcg_inner_uom_id, product.uom_ids)
        self.assertIn(product.fmcg_carton_uom_id, product.uom_ids)
        self.assertEqual(
            product.fmcg_inner_uom_id._compute_quantity(1, product.uom_id),
            10,
        )
        self.assertEqual(
            product.fmcg_carton_uom_id._compute_quantity(1, product.uom_id),
            120,
        )

        inner_id = product.fmcg_inner_uom_id.id
        carton_id = product.fmcg_carton_uom_id.id
        product.configure_fmcg_packaging_uoms(base_uom, inner_qty=10, carton_qty=120)
        self.assertEqual(product.fmcg_inner_uom_id.id, inner_id)
        self.assertEqual(product.fmcg_carton_uom_id.id, carton_id)

    def test_05_native_packaging_without_inner_tier(self):
        """Products with inner_qty=1 expose carton and base UoM only."""
        product = self.env["product.template"].create({
            "name": "Bottled Coffee Test",
            "default_code": "TEST-UOM-BOTTLE",
            "principal_id": self.principal.id,
            "brand_id": self.brand.id,
            "uom_id": self.uom_unit.id,
            "standard_price": 5000.0,
            "list_price": 6000.0,
        })
        base_uom = self.env.ref("id_base.uom_btl")
        product.configure_fmcg_packaging_uoms(base_uom, inner_qty=1, carton_qty=24)

        self.assertFalse(product.fmcg_inner_uom_id)
        self.assertEqual(
            product.fmcg_carton_uom_id._compute_quantity(1, product.uom_id),
            24,
        )

    def test_06_invalid_packaging_ratio_is_rejected(self):
        product = self.env["product.template"].create({
            "name": "Invalid Ratio Test",
            "default_code": "TEST-UOM-INVALID",
            "principal_id": self.principal.id,
            "brand_id": self.brand.id,
            "uom_id": self.uom_unit.id,
            "standard_price": 1000.0,
            "list_price": 1500.0,
        })
        with self.assertRaises(ValidationError):
            product.configure_fmcg_packaging_uoms(
                self.env.ref("id_base.uom_sch"),
                inner_qty=10,
                carton_qty=125,
            )

    def test_03_partner_coverage_and_matrix_pricelist(self):
        """Verifikasi bahwa partner dengan coverage area dan channel otomatis mendapat matriks harga."""
        channel_mt = self.env.ref("id_base.channel_mt")
        area_mnd = self.env.ref("id_base.area_mnd_urban")

        partner = self.env["res.partner"].create({
            "name": "FreshMart Bahu Test",
            "channel_id": channel_mt.id,
            "coverage_area_id": area_mnd.id,
        })

        pl = partner._get_matrix_pricelist()
        self.assertTrue(pl, "Partner MT di Manado Urban wajib mendapat matriks daftar harga!")
        self.assertEqual(pl.channel_id.id, channel_mt.id)

        # Action assign matrix
        partner.action_assign_matrix_pricelist()
        self.assertEqual(partner.property_product_pricelist.id, pl.id)

