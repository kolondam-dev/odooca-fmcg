from odoo import fields, models
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    fmcg_approval_state = fields.Selection([
        ("draft", "Draf SKU"),
        ("pending", "Menunggu Persetujuan"),
        ("active", "Aktif / Terverifikasi"),
        ("rejected", "Ditolak"),
    ], string="Status Persetujuan SKU", default="active", tracking=True)

    approval_request_ids = fields.One2many(
        "fmcg.approval.request",
        compute="_compute_approval_requests",
        string="Riwayat Persetujuan SKU",
    )
    approval_count = fields.Integer(
        string="Jumlah Pengajuan",
        compute="_compute_approval_requests",
    )

    def _compute_approval_requests(self):
        ApprovalRequest = self.env["fmcg.approval.request"]
        for prod in self:
            requests = ApprovalRequest.search([
                ("res_model", "=", "product.template"),
                ("res_id", "=", prod.id),
            ])
            prod.approval_request_ids = requests
            prod.approval_count = len(requests)

    def action_request_new_sku_approval(self, reason=""):
        """Mengajukan persetujuan SKU produk baru sebelum diperjualbelikan."""
        self.ensure_one()
        category = self.env["fmcg.approval.category"].search([("code", "=", "new_sku")], limit=1)
        if not category:
            raise UserError("Kategori persetujuan 'new_sku' tidak ditemukan.")

        req = self.env["fmcg.approval.request"].create({
            "category_id": category.id,
            "res_model": "product.template",
            "res_id": self.id,
            "reference_document": f"[{self.default_code or '-'}] {self.name}",
            "reason": reason or f"Pengajuan registrasi SKU baru: {self.name} (Barcode: {self.barcode or '-'})",
        })
        req.action_submit()
        self.write({"fmcg_approval_state": "pending"})
        self.message_post(
            body=(
                f"Pengajuan verifikasi SKU baru <b>{req.name}</b> telah dikirimkan ke "
                f"Branch Manager / Master Data Admin."
            ),
            subtype_xmlid="mail.mt_note",
        )
        return {
            "name": "Pengajuan Persetujuan",
            "view_mode": "form",
            "res_model": "fmcg.approval.request",
            "res_id": req.id,
            "type": "ir.actions.act_window",
            "target": "current",
        }

    def _on_approval_status_change(self, request, status):
        """Callback ketika status pengajuan approval berubah."""
        for prod in self:
            if request.category_code == "new_sku":
                if status == "approved":
                    prod.write({
                        "fmcg_approval_state": "active",
                        "sale_ok": True,
                    })
                    prod.message_post(
                        body="SKU telah DISETUJUI dan aktif untuk transaksi penjualan.",
                        subtype_xmlid="mail.mt_note",
                    )
                elif status == "rejected":
                    prod.write({
                        "fmcg_approval_state": "rejected",
                        "sale_ok": False,
                    })
                    prod.message_post(body="Pengajuan SKU baru DITOLAK oleh manajemen.", subtype_xmlid="mail.mt_note")
