from odoo import api, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    approval_request_ids = fields.One2many(
        "fmcg.approval.request",
        compute="_compute_approval_requests",
        string="Riwayat Persetujuan",
    )
    approval_count = fields.Integer(
        string="Jumlah Persetujuan",
        compute="_compute_approval_requests",
    )
    is_cash_customer = fields.Boolean(
        string="Pelanggan Tunai (Cash)",
        compute="_compute_is_cash_customer",
        help="Pelanggan tunai (Cash) tidak memerlukan persetujuan kredit.",
    )

    def _compute_approval_requests(self):
        ApprovalRequest = self.env["fmcg.approval.request"]
        for partner in self:
            requests = ApprovalRequest.search([
                ("res_model", "=", "res.partner"),
                ("res_id", "=", partner.id),
            ])
            partner.approval_request_ids = requests
            partner.approval_count = len(requests)

    @api.depends("property_payment_term_id", "credit_mode")
    def _compute_is_cash_customer(self):
        for partner in self:
            term = partner.property_payment_term_id
            name = (term.name or "").lower() if term else ""
            is_cash = partner.credit_mode == "cash" or "cash" in name or "tunai" in name or not term
            partner.is_cash_customer = is_cash

    def action_request_credit_limit_approval(self, reason=""):
        """Mengajukan persetujuan limit kredit & ToP tempo."""
        self.ensure_one()
        if self.is_cash_customer and self.credit_limit <= 0:
            raise UserError("Pelanggan dengan ToP Cash tidak memerlukan persetujuan limit kredit.")

        category = self.env["fmcg.approval.category"].search([("code", "=", "partner_credit_limit")], limit=1)
        if not category:
            raise UserError("Kategori persetujuan 'partner_credit_limit' tidak ditemukan. Harap hubungi administrator.")

        req = self.env["fmcg.approval.request"].create({
            "category_id": category.id,
            "res_model": "res.partner",
            "res_id": self.id,
            "reference_document": f"{self.name} (Limit: Rp {self.credit_limit:,.2f})",
            "amount": self.credit_limit,
            "reason": reason or f"Pengajuan plafon kredit Rp {self.credit_limit:,.2f} untuk outlet {self.name}",
        })
        req.action_submit()
        self.write({
            "credit_approval_state": "pending",
        })
        self.message_post(
            body=(
                f"Pengajuan persetujuan limit kredit <b>{req.name}</b> "
                f"(Rp {self.credit_limit:,.2f}) telah dikirimkan."
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
        for partner in self:
            if request.category_code == "partner_credit_limit":
                if status == "approved":
                    partner.write({
                        "credit_approval_state": "approved",
                    })
                    partner.message_post(
                        body=f"Plafon kredit sebesar Rp {partner.credit_limit:,.2f} telah DISETUJUI oleh manajemen.",
                        subtype_xmlid="mail.mt_note",
                    )
                elif status == "rejected":
                    partner.write({
                        "credit_approval_state": "rejected",
                    })
                    partner.message_post(
                        body="Pengajuan limit kredit telah DITOLAK oleh manajemen.",
                        subtype_xmlid="mail.mt_note",
                    )
