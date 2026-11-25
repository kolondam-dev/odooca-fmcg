"""Render the Surat Jalan Penagihan (SJP) PDF against the running CI Odoo server (BE-20b, D9)."""

# Executed by ``odoo shell``, which injects ``env`` into the script namespace.
# ruff: noqa: F821

import io
import re
from datetime import timedelta

from odoo import Command
from odoo.addons.id_base.models.business_day import business_date

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    from PyPDF2 import PdfFileReader as PdfReader

# wkhtmltopdf fetches report assets over HTTP, so this only runs after CI has started the web server.
env["ir.config_parameter"].sudo().set_param("report.url", "http://127.0.0.1:8069")

idr = env.ref("base.IDR")
idr.active = True
company = env["res.company"].create({"name": "CI SJP PDF Co", "currency_id": idr.id})
env = env(context={**env.context, "allowed_company_ids": company.ids})
receivable = env["account.account"].create({
    "name": "AR SJP PDF", "code": "113951", "account_type": "asset_receivable",
    "company_ids": [Command.set(company.ids)],
})
income = env["account.account"].create({
    "name": "Income SJP PDF", "code": "420951", "account_type": "income",
    "company_ids": [Command.set(company.ids)],
})
journal = env["account.journal"].create({
    "name": "Sales SJP PDF", "code": "SJPDF", "type": "sale", "company_id": company.id,
})
partner = env["res.partner"].create({"name": "CI SJP PDF Customer", "is_company": True})
partner.with_company(company).property_account_receivable_id = receivable
today = business_date()
move = env["account.move"].create({
    "move_type": "out_invoice", "company_id": company.id, "journal_id": journal.id,
    "partner_id": partner.id, "invoice_date": today - timedelta(days=30), "invoice_date_due": today,
    "invoice_line_ids": [Command.create({
        "name": "SJP PDF line", "quantity": 1, "price_unit": 12345, "account_id": income.id,
    })],
})
move.action_post()
sheet = env["id.collection.sheet"].create({
    "company_id": company.id,
    "collector_id": env.user.id,
    "line_ids": [Command.create({"move_id": move.id})],
})
assert sheet.line_count == 1 and sheet.amount_total == 12345.0, (sheet.line_count, sheet.amount_total)

report = env.ref("id_ar_collection.action_report_collection_sheet")
assert report.report_type == "qweb-pdf", report.report_type
pdf, content_type = report.with_context(force_report_rendering=True)._render_qweb_pdf(
    report.report_name, sheet.ids
)
assert content_type == "pdf", content_type
assert isinstance(pdf, bytes) and pdf.startswith(b"%PDF-"), "bukan PDF"
assert len(pdf) > 1000, len(pdf)
reader = PdfReader(io.BytesIO(pdf))
pages = reader.pages if hasattr(reader, "pages") else [reader.getPage(i) for i in range(reader.numPages)]
text = " ".join(" ".join((page.extract_text() or "").split()) for page in pages)
for needle in (sheet.name, "CI SJP PDF Customer", move.name, "CI SJP PDF Co", env.user.name):
    assert needle in text, (needle, text[:500])
assert re.search(r"12[.,]345", text), text[:500]
print("COLLECTION_SHEET_PDF_RENDERED=%s bytes=%s" % (sheet.name, len(pdf)))
print("COLLECTION_SHEET_PDF_SMOKE=PASS")
