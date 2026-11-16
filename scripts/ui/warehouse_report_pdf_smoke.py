"""Render the three FMCG warehouse PDFs against the running CI Odoo server."""

# Executed by ``odoo shell``, which injects ``env`` into the script namespace.
# ruff: noqa: F821

from odoo import Command


# The PDF smoke runs in a separate process after TransactionCase rollback.
# Activate the locale and explicitly load this addon's translated QWeb terms.
language = (
    env["res.lang"]._activate_lang("id_ID")
    or env["res.lang"]._create_lang("id_ID")
)
if not language.active:
    language.action_unarchive()
env["ir.module.module"].search(
    [("name", "=", "id_base")]
)._update_translations(["id_ID"])


# wkhtmltopdf fetches report assets over HTTP. This script runs only after the
# CI job has started the disposable Odoo web server and confirmed /web/login.
env["ir.config_parameter"].sudo().set_param(
    "report.url", "http://127.0.0.1:8069"
)

warehouse = env.ref("stock.warehouse0")
picking_type = warehouse.out_type_id
source = picking_type.default_location_src_id
destination = picking_type.default_location_dest_id
partner = env["res.partner"].create({"name": "CI Warehouse PDF Smoke"})
product = env["product.product"].create({
    "name": "CI Warehouse PDF Smoke Product",
    "is_storable": True,
    "tracking": "lot",
    "uom_id": env.ref("uom.product_uom_unit").id,
})
lot = env["stock.lot"].create({
    "name": "LOT-CI-WAREHOUSE-PDF",
    "product_id": product.id,
    "company_id": env.company.id,
})
env["stock.quant"]._update_available_quantity(
    product, source, 4, lot_id=lot
)
picking = env["stock.picking"].create({
    "picking_type_id": picking_type.id,
    "location_id": source.id,
    "location_dest_id": destination.id,
    "partner_id": partner.id,
    "origin": "CI-WAREHOUSE-PDF-SMOKE",
    "move_ids": [Command.create({
        "product_id": product.id,
        "product_uom": product.uom_id.id,
        "product_uom_qty": 4,
        "location_id": source.id,
        "location_dest_id": destination.id,
    })],
})
picking.action_confirm()
picking.action_assign()
assert picking.state == "assigned", picking.state
assert sum(picking.move_ids.move_line_ids.mapped("quantity")) == 4

for xmlid in (
    "id_base.action_report_fmcg_picklist",
    "id_base.action_report_fmcg_packlist",
    "id_base.action_report_fmcg_delivery_order",
):
    report = env.ref(xmlid)
    assert report.report_type == "qweb-pdf", (xmlid, report.report_type)
    pdf, content_type = report.with_context(
        lang="id_ID", force_report_rendering=True
    )._render_qweb_pdf(report.report_name, picking.ids)
    assert content_type == "pdf", (xmlid, content_type)
    assert isinstance(pdf, bytes) and pdf.startswith(b"%PDF-"), xmlid
    assert len(pdf) > 1000, (xmlid, len(pdf))
    print("WAREHOUSE_PDF_RENDERED=%s bytes=%s" % (xmlid, len(pdf)))

print("WAREHOUSE_PDF_SMOKE=PASS")
