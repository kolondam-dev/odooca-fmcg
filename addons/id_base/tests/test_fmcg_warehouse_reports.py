import csv
from io import BytesIO, StringIO
import json

from odoo import Command
from odoo.tests.common import TransactionCase
from odoo.tools import file_open
from odoo.tools.translate import (
    TranslationImporter,
    get_base_langs,
    get_po_paths,
    load_language,
    trans_export,
    translation_file_reader,
)


class TestFMCGWarehouseReports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A fresh CI database may not have an active Indonesian language record.
        language = (
            cls.env["res.lang"]._activate_lang("id_ID")
            or cls.env["res.lang"]._create_lang("id_ID")
        )
        if not language.active:
            language.action_unarchive()
        cls.env["ir.module.module"].search(
            [("name", "=", "id_base")]
        )._update_translations(["id_ID"])
        # Install Indonesian in this disposable test database before rendering.
        # Loading the language activates it; refreshing this module then imports
        # id_base/i18n/id_ID.po for the QWeb templates under test.
        load_language(cls.env.cr, "id_ID")
        cls.env["ir.module.module"].search([
            ("name", "=", "id_base"),
        ])._update_translations(overwrite=False)
        cls.env.invalidate_all()
        # Translation imports update ir.ui.view.arch_db; invalidate the QWeb
        # view cache as well so report rendering observes the imported terms.
        cls.env["ir.ui.view"].clear_caches()
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

    def _render_html(self, xmlid, picking, lang=None):
        report = self.env.ref(xmlid)
        self.assertEqual(report.model, "stock.picking")
        if lang:
            report = report.with_context(lang=lang)
            picking = picking.with_context(lang=lang)
        html, _content_type = report._render_qweb_html(
            report.report_name, picking.ids
        )
        if isinstance(html, bytes):
            html = html.decode()
        return html

    def test_00_picklist_translation_importer_chain(self):
        # Prove one term end-to-end before investigating the three report labels.
        po_paths = list(get_po_paths("id_base", "id_ID"))
        po_path = next((path for path in po_paths if path.endswith("/id_ID.po")), None)
        self.assertTrue(
            po_path,
            f"id_ID PO not discovered by Odoo get_po_paths(): {po_paths}",
        )
        with file_open(po_path, mode="rb", env=self.env) as po_file:
            reader = translation_file_reader(po_file, fileformat="po")
            raw_entries = [
                entry for entry in reader.pofile
                if entry.msgid == "Picklist"
            ]
            parsed_rows = list(reader)
        expected_terms = {
            "Picklist": ("Daftar Pengambilan", ("report_fmcg_picklist",)),
            "Customer / Destination": ("Pelanggan / Tujuan", ("report_fmcg_picklist", "report_fmcg_packlist")),
            "Source Document": ("Dokumen Asal", ("report_fmcg_picklist", "report_fmcg_packlist")),
            "Scheduled": ("Dijadwalkan", ("report_fmcg_picklist", "report_fmcg_packlist")),
            "Ship To": ("Dikirim Kepada", ("report_fmcg_delivery_order",)),
        }
        raw_entries = [
            entry for entry in reader.pofile
            if entry.msgid in expected_terms
        ]
        parsed_rows = list(reader)
        source_rows = [
            row for row in parsed_rows if row.get("src") in expected_terms
        ]
        matches = [
            row for row in source_rows
            if row.get("src") == "Picklist"
            and row.get("type") == "model_terms"
            and row.get("value") == "Daftar Pengambilan"
        ]
        raw_diagnostics = [
            {
                "msgid": entry.msgid,
                "msgstr": entry.msgstr,
                "comment": entry.comment,
                "tcomment": entry.tcomment,
                "occurrences": entry.occurrences,
                "flags": entry.flags,
                "obsolete": entry.obsolete,
            }
            for entry in raw_entries
        ]
        parsed_term_diagnostics = {
            term: [
                {
                    "type": row.get("type"),
                    "value": row.get("value"),
                    "module": row.get("module"),
                    "imd_model": row.get("imd_model"),
                    "name": row.get("name"),
                    "imd_name": row.get("imd_name"),
                }
                for row in source_rows if row.get("src") == term
            ]
            for term in expected_terms
        }
        self.assertEqual(
            parsed_term_diagnostics,
            {
                term: [{
                    "type": "model_terms",
                    "value": value,
                    "module": "id_base",
                    "imd_model": "ir.ui.view",
                    "name": "ir.ui.view,arch_db",
                    "imd_name": xmlid,
                } for xmlid in xmlids]
                for term, (value, xmlids) in expected_terms.items()
            },
            "PO parser term matrix mismatch: " + json.dumps({
                "raw_po_entries": raw_diagnostics,
                "parsed_rows": parsed_term_diagnostics,
                "po_path": po_path,
            }, ensure_ascii=False, default=str),
        )
        self.assertEqual(
            len(matches), 1,
            "Picklist parser trace mismatch: "
            + json.dumps({
                "raw_po_entries": raw_diagnostics,
                "parsed_rows_with_src_picklist": source_rows,
                "parsed_row_count": len(parsed_rows),
                "po_entry_count": len(reader.pofile),
                "po_path": po_path,
            }, ensure_ascii=False, default=str),
        )
        row = matches[0]
        expected_metadata = {
            "module": "id_base",
            "imd_model": "ir.ui.view",
            "name": "ir.ui.view,arch_db",
            "imd_name": "report_fmcg_picklist",
        }
        actual_metadata = {key: row.get(key) for key in expected_metadata}
        self.assertEqual(actual_metadata, expected_metadata, actual_metadata)
        self.assertIn(row.get("lang", "id_ID"), get_base_langs("id_ID"))

        view = self.env.ref(
            "id_base.report_fmcg_picklist", raise_if_not_found=False
        )
        imd = self.env["ir.model.data"].search([
            ("module", "=", "id_base"),
            ("name", "=", "report_fmcg_picklist"),
            ("model", "=", "ir.ui.view"),
        ])
        field = self.env["ir.ui.view"]._fields.get("arch_db")
        self.assertTrue(view, "XML ID id_base.report_fmcg_picklist did not resolve")
        self.assertEqual(len(imd), 1, f"XML ID rows={imd.ids}")
        self.assertEqual(imd.res_id, view.id)
        self.assertTrue(field and callable(field.translate), "arch_db is not callable-translated")
        self.assertTrue(field.store, "arch_db is not stored")

        importer = TranslationImporter(self.env.cr, verbose=False)
        importer.load_file(po_path, "id_ID")
        imported_values = {
            term: {
                xmlid: importer.model_terms_translations
                .get("ir.ui.view", {}).get("arch_db", {})
                .get(f"id_base.{xmlid}", {}).get(term, {}).get("id_ID")
                for xmlid in xmlids
            }
            for term, (_value, xmlids) in expected_terms.items()
        }
        self.assertEqual(
            imported_values,
            {term: {xmlid: value for xmlid in xmlids}
             for term, (value, xmlids) in expected_terms.items()},
            "TranslationImporter term matrix mismatch: " + json.dumps({
                "imported_values": imported_values,
                "imported_langs": sorted(importer.imported_langs),
                "parsed_terms": parsed_term_diagnostics,
            }, ensure_ascii=False, default=str),
        )
        imported = imported_values["Picklist"]["report_fmcg_picklist"]
        if "id_ID" not in importer.imported_langs or imported != "Daftar Pengambilan":
            rejection_checks = {
                "value_present": bool(row.get("value")),
                "source_present": bool(row.get("src")),
                "type": row.get("type"),
                "language": row.get("lang", "id_ID"),
                "valid_languages": get_base_langs("id_ID"),
                "model_registered": row.get("imd_model") in self.env,
                "field_exists": bool(field),
                "field_translate_callable": bool(field and callable(field.translate)),
                "field_stored": bool(field and field.store),
                "xmlid_resolves": bool(view),
                "imported_langs": sorted(importer.imported_langs),
                "imported_value": imported,
            }
            self.fail(
                "TranslationImporter rejected Picklist or stored no value: "
                + json.dumps(rejection_checks, ensure_ascii=False, default=str)
            )

        importer.save(overwrite=True)
        self.env.invalidate_all()
        self.env["ir.ui.view"].clear_caches()
        exported_csv = BytesIO()
        self.assertTrue(
            trans_export("id_ID", ["id_base"], exported_csv, "csv", self.env)
        )
        exported_rows = list(csv.DictReader(
            StringIO(exported_csv.getvalue().decode("utf-8"))
        ))
        exported = [
            item for item in exported_rows
            if item["type"] == "model_terms"
            and item["name"] == "ir.ui.view,arch_db"
            and item["res_id"] == "id_base.report_fmcg_picklist"
            and item["src"] == "Picklist"
        ]
        self.assertEqual(len(exported), 1, f"Picklist export rows={exported}")
        self.assertEqual(exported[0]["value"], "Daftar Pengambilan")

        html = self._render_html(
            "id_base.action_report_fmcg_picklist",
            self.empty_picking,
            lang="id_ID",
        )
        self.assertIn("Daftar Pengambilan", html)
        self.assertIn("Pelanggan / Tujuan", html)

        delivery_html = self._render_html(
            "id_base.action_report_fmcg_delivery_order",
            self.empty_picking,
            lang="id_ID",
        )
        self.assertIn("Dikirim Kepada", delivery_html)

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

    def test_done_delivery_order_uses_partial_actual_quantity_and_templates(self):
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

    def test_qweb_indonesian_title_terms_match_odoo_export(self):
        # Export the installed view translations through Odoo 19 itself. This
        # checks the database's extracted QWeb terms, not just PO file text.
        exported_csv = BytesIO()
        self.assertTrue(
            trans_export("id_ID", ["id_base"], exported_csv, "csv", self.env)
        )
        exported_text = exported_csv.getvalue().decode("utf-8")
        rows = list(csv.DictReader(StringIO(exported_text)))
        expected = {
            "id_base.report_fmcg_picklist": (
                "Picklist", "Daftar Pengambilan",
            ),
            "id_base.report_fmcg_packlist": (
                "Packlist", "Daftar Pengepakan",
            ),
            "id_base.report_fmcg_delivery_order": (
                "Delivery Order", "Surat Jalan",
            ),
        }
        for xmlid, (msgid, msgstr) in expected.items():
            with self.subTest(xmlid=xmlid):
                matches = [
                    row for row in rows
                    if row["type"] == "model_terms"
                    and row["name"] == "ir.ui.view,arch_db"
                    and row["res_id"] == xmlid
                    and row["src"] == msgid
                ]
                self.assertEqual(
                    len(matches), 1,
                    f"Expected one exported QWeb term for {xmlid}",
                )
                self.assertEqual(matches[0]["src"], msgid)
                self.assertEqual(matches[0]["value"], msgstr)

    def test_all_warehouse_reports_render_indonesian_labels(self):
        picking, _lot = self._create_lot_picking("SO-FMCG-ID-REPORT", demand=2)
        cases = (
            ("id_base.action_report_fmcg_picklist", "Daftar Pengambilan",
             ("Pelanggan / Tujuan", "Dokumen Asal", "Dijadwalkan",
              "Lokasi Asal", "Lot / Nomor Seri", "Disiapkan oleh")),
            ("id_base.action_report_fmcg_packlist", "Daftar Pengepakan",
             ("Pelanggan / Tujuan", "Dokumen Asal", "Dijadwalkan",
              "Lot / Nomor Seri", "Lokasi Asal", "Kuantitas",
              "Kemasan Tujuan", "Petugas pengepakan")),
            ("id_base.action_report_fmcg_delivery_order", "Surat Jalan",
             ("Dikirim Kepada", "Penjualan / Pesanan Asal", "Tanggal Pengiriman",
              "Lot / Nomor Seri", "Kuantitas", "Rincian Kemasan",
              "Kemasan", "Diserahkan oleh")),
        )
        for xmlid, title, labels in cases:
            with self.subTest(report=xmlid):
                html = self._render_html(xmlid, picking, lang="id_ID")
                self.assertIn('data-oe-lang="id_ID"', html)
                for label in (title, *labels):
                    self.assertIn(label, html)
                self.assertNotIn("<h2>Picklist", html)
                self.assertNotIn("<h2>Packlist", html)
                self.assertNotIn("<h2>Delivery Order", html)

        # Keep transactional QWeb checks here; real wkhtmltopdf rendering runs
        # in a separate smoke against the started CI Odoo HTTP server.
        for xmlid in (
            "id_base.action_report_fmcg_picklist",
            "id_base.action_report_fmcg_packlist",
            "id_base.action_report_fmcg_delivery_order",
        ):
            report = self.env.ref(xmlid)
            self.assertEqual(report.report_type, "qweb-pdf")
            self.assertEqual(report.model, "stock.picking")
            rendered = self._render_html(xmlid, picking)
            self.assertTrue(rendered)
