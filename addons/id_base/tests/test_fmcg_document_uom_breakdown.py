from odoo.tests.common import TransactionCase


class TestFMCGDocumentUoMBreakdown(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.inventory_uom = cls.env.ref("uom.product_uom_unit")
        cls.base_uom = cls.env.ref("id_base.uom_pcs")
        cls.product = cls.env["product.template"].create({
            "name": "FMCG Document UoM Breakdown Test",
            "default_code": "TEST-DOC-UOM-BREAKDOWN",
            "uom_id": cls.inventory_uom.id,
            "is_storable": True,
        })
        cls.product.configure_fmcg_packaging_uoms(
            cls.base_uom,
            inner_qty=10,
            carton_qty=120,
        )
        cls.variant = cls.product.product_variant_id

    def _assert_breakdown(self, model_name, values):
        record = self.env[model_name].new(values)
        record._compute_fmcg_qty_breakdown()
        self.assertEqual(
            record.fmcg_qty_breakdown,
            "2 Karton + 1 Inner + 3 Pieces (253 Pieces)",
        )

    def test_invoice_line_breakdown_is_display_only(self):
        self._assert_breakdown("account.move.line", {
            "product_id": self.variant.id,
            "quantity": 253,
            "product_uom_id": self.base_uom.id,
        })

    def test_stock_move_demand_breakdown_is_display_only(self):
        self._assert_breakdown("stock.move", {
            "product_id": self.variant.id,
            "product_uom_qty": 253,
            "product_uom": self.base_uom.id,
        })

    def test_stock_move_line_actual_quantity_breakdown_is_display_only(self):
        self._assert_breakdown("stock.move.line", {
            "product_id": self.variant.id,
            "quantity": 253,
            "product_uom_id": self.base_uom.id,
        })

    def test_carton_uom_converts_to_canonical_inventory_quantity(self):
        record = self.env["stock.move"].new({
            "product_id": self.variant.id,
            "product_uom_qty": 2,
            "product_uom": self.product.fmcg_carton_uom_id.id,
        })
        record._compute_fmcg_qty_breakdown()
        self.assertEqual(record.fmcg_qty_breakdown, "2 Karton (240 Pieces)")

    def test_non_fmcg_product_has_no_packaging_breakdown(self):
        product = self.env["product.product"].create({
            "name": "Ordinary Product Without FMCG Packaging",
            "uom_id": self.inventory_uom.id,
            "is_storable": True,
        })
        record = self.env["stock.move"].new({
            "product_id": product.id,
            "product_uom_qty": 5,
            "product_uom": self.inventory_uom.id,
        })
        record._compute_fmcg_qty_breakdown()
        self.assertFalse(record.fmcg_qty_breakdown)
