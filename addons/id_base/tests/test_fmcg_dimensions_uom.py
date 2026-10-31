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

