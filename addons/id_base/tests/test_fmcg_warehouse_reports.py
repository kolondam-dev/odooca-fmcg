from odoo import Command
from odoo.tests.common import TransactionCase


class TestFMCGWarehouseReports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref("stock.warehouse0")
        cls.picking_type = cls.warehouse.out_type_id
        cls.source = cls.picking_type.default_location_src_id
        cls.destination = cls.picking_type.default_location_dest_id
        cls.partner = cls.env["res.partner"].create({
            "name": "FMCG Warehouse Report Customer",
        })
        cls.product = cls.env["product.product"].create({
            "name": "FMCG Warehouse Report Product",
            "is_storable": True,
            "uom_id": cls.env.ref("uom.product_uom_unit").id,
        })
        cls.empty_picking = cls._create_picking("SO-FMCG-EMPTY", 0)

    @classmethod
    def _create_picking(cls, origin, demand):
        return cls.env["stock.picking"].create({
            "picking_type_id": cls.picking_type.id,
            "location_id": cls.source.id,
            "location_dest_id": cls.destination.id,
            "partner_id": cls.partner.id,
            "origin": origin,
            "move_ids": [Command.create({
                "product_id": cls.product.id,
                "product_uom": cls.product.uom_id.id,
                "product_uom_qty": demand,
                "location_id": cls.source.id,
                "location_dest_id": cls.destination.id,
            })] if demand else [],
        })

    def _create_lot_picking(self, origin, demand=5):
        product = self.env["product.product"].create({
            "name": "FMCG Tracked Report Product",
            "is_storable": True,
            "tracking": "lot",
            "uom_id": self.env.ref("uom.product_uom_unit").id,
        })
        lot = self.env["stock.lot"].create({
            "name": "LOT-WMS-REPORT-001",
            "product_id": product.id,
            "company_id": self.env.company.id,
        })
        self.env["stock.quant"]._update_available_quantity(
            product, self.source, demand, lot_id=lot
        )
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.picking_type.id,
            "location_id": self.source.id,
            "location_dest_id": self.destination.id,
            "partner_id": self.partner.id,
            "origin": origin,
            "move_ids": [Command.create({
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": demand,
                "location_id": self.source.id,
                "location_dest_id": self.destination.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        self.assertEqual(picking.state, "assigned")
        self.assertEqual(
            sum(picking.move_ids.move_line_ids.mapped("quantity")), demand
        )
        return picking, lot

    def _render_html(self, xmlid, picking):
        report = self.env.ref(xmlid)
        self.assertEqual(report.model, "stock.picking")
        html, _content_type = report._render_qweb_html(
            report.report_name, picking.ids
        )
        if isinstance(html, bytes):
            html = html.decode()
        return html

    def _assert_pdf_download(self, xmlid, picking):
        report = self.env.ref(xmlid)
        pdf, _content_type = report._render_qweb_pdf(
            report.report_name, picking.ids
        )
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 1000)

    def test_empty_packlist_states_empty_without_fabricated_rows(self):
        html = self._render_html(
            "id_base.action_report_fmcg_packlist", self.empty_picking
        )
        self.assertIn(
            "No native operation or reservation lines are available", html
        )
        self.assertNotIn("FMCG Warehouse Report Product", html)
        self.assertNotIn("LOT-WMS-REPORT-001", html)
        self.assertFalse(self.empty_picking.move_ids.move_line_ids)

    def test_picklist_and_packlist_render_reserved_native_lot_and_package(self):
        picking, lot = self._create_lot_picking("SO-FMCG-RESERVED")
        package_type = self.env["stock.package.type"].create({
            "name": "FMCG Report Carton",
        })
        package = self.env["stock.package"].create({
            "name": "PACK-WMS-REPORT-001",
            "package_type_id": package_type.id,
        })
        operation = picking.move_ids.move_line_ids
        self.assertEqual(operation.mapped("lot_id"), lot)
        operation.write({"result_package_id": package.id})

        picklist = self._render_html(
            "id_base.action_report_fmcg_picklist", picking
        )
        packlist = self._render_html(
            "id_base.action_report_fmcg_packlist", picking
        )
        for html in (picklist, packlist):
            self.assertIn("FMCG Tracked Report Product", html)
            self.assertIn("LOT-WMS-REPORT-001", html)
        self.assertIn("PACK-WMS-REPORT-001", packlist)
        self.assertEqual(operation.mapped("result_package_id"), package)

    def test_done_delivery_order_uses_partial_actual_quantity_and_pdf(self):
        picking, lot = self._create_lot_picking(
            "SO-FMCG-PARTIAL-DONE", demand=5
        )
        operation = picking.move_ids.move_line_ids
        package_type = self.env["stock.package.type"].create({
            "name": "FMCG Delivery Carton",
        })
        package = self.env["stock.package"].create({
            "name": "PACK-WMS-DELIVERY-001",
            "package_type_id": package_type.id,
        })
        operation.write({
            "quantity": 3,
            "picked": True,
            "result_package_id": package.id,
        })
        result = picking.button_validate()
        if (
            isinstance(result, dict)
            and result.get("res_model") == "stock.backorder.confirmation"
        ):
            wizard_context = dict(self.env.context, **result.get("context", {}))
            wizard = self.env[result["res_model"]].with_context(
                wizard_context
            ).create({"pick_ids": [Command.set(picking.ids)]})
            wizard.process()
        picking.invalidate_recordset()
        self.assertEqual(picking.state, "done")
        self.assertEqual(
            sum(picking.move_ids.move_line_ids.mapped("quantity")), 3
        )
        # Native backorder confirmation splits the original demand: the done
        # picking keeps the fulfilled 3, while the remaining 2 move to a
        # separate backorder picking. Assert the complete demand across both.
        self.assertEqual(sum(picking.move_ids.mapped("product_uom_qty")), 3)
        backorders = picking.backorder_ids
        self.assertEqual(len(backorders), 1)
        self.assertEqual(
            sum(backorders.move_ids.mapped("product_uom_qty")), 2
        )
        self.assertEqual(
            sum(picking.move_ids.mapped("product_uom_qty"))
            + sum(backorders.move_ids.mapped("product_uom_qty")),
            5,
        )
        self.assertEqual(picking.move_ids.move_line_ids.mapped("lot_id"), lot)

        html = self._render_html(
            "id_base.action_report_fmcg_delivery_order", picking
        )
        self.assertIn("FMCG Tracked Report Product", html)
        self.assertIn("LOT-WMS-REPORT-001", html)
        self.assertIn("PACK-WMS-DELIVERY-001", html)
        self.assertRegex(html, r">\s*3(?:[.,]0+)?\s*<")
        self.assertNotRegex(html, r">\s*5(?:[.,]0+)?\s*<")

        for xmlid in (
            "id_base.action_report_fmcg_picklist",
            "id_base.action_report_fmcg_packlist",
            "id_base.action_report_fmcg_delivery_order",
        ):
            self._assert_pdf_download(xmlid, picking)
