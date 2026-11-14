from odoo import Command
from odoo.tests.common import TransactionCase


class TestFMCGWarehouseReports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref("stock.warehouse0")
        cls.picking_type = cls.warehouse.out_type_id
        cls.partner = cls.env["res.partner"].create({
            "name": "FMCG Warehouse Report Customer",
        })
        cls.product = cls.env["product.product"].create({
            "name": "FMCG Warehouse Report Product",
            "is_storable": True,
            "uom_id": cls.env.ref("uom.product_uom_unit").id,
        })
        cls.picking = cls.env["stock.picking"].create({
            "picking_type_id": cls.picking_type.id,
            "location_id": cls.picking_type.default_location_src_id.id,
            "location_dest_id": cls.picking_type.default_location_dest_id.id,
            "partner_id": cls.partner.id,
            "origin": "SO-FMCG-REPORT-TEST",
            "move_ids": [
                Command.create({
                    "product_id": cls.product.id,
                    "product_uom": cls.product.uom_id.id,
                    "product_uom_qty": 2.0,
                    "location_id": cls.picking_type.default_location_src_id.id,
                    "location_dest_id": cls.picking_type.default_location_dest_id.id,
                }),
            ],
        })

    def _render_report(self, xmlid, expect_product=True):
        report = self.env.ref(xmlid)
        self.assertEqual(report.model, "stock.picking")
        html, _content_type = report._render_qweb_html(
            report.report_name,
            self.picking.ids,
        )
        if isinstance(html, bytes):
            html = html.decode()
        if expect_product:
            self.assertIn("FMCG Warehouse Report Product", html)
        self.assertIn("SO-FMCG-REPORT-TEST", html)

    def test_picklist_renders_native_demand(self):
        self._render_report("id_base.action_report_fmcg_picklist")

    def test_packlist_does_not_fabricate_operation_lines(self):
        self._render_report(
            "id_base.action_report_fmcg_packlist",
            expect_product=False,
        )

    def test_delivery_order_renders_native_demand(self):
        self._render_report("id_base.action_report_fmcg_delivery_order")
