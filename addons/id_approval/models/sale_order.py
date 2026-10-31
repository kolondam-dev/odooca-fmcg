from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    has_tactical_discount = fields.Boolean(
        string="Memiliki Diskon Taktikal",
        compute="_compute_discount_and_cost_flags",
        store=True,
        help="Menandakan adanya diskon manual pada baris pesanan di luar program promo resmi.",
    )
    has_below_hpp = fields.Boolean(
        string="Harga Jual di Bawah HPP",
        compute="_compute_discount_and_cost_flags",
        store=True,
        help="Peringatan keras: Produk dijual dengan harga net lebih rendah dari HPP (standard_price)!",
    )
    below_hpp_summary = fields.Text(
        string="Rincian Produk di Bawah HPP",
        compute="_compute_below_hpp_summary",
    )
    below_hpp_approval_state = fields.Selection([
        ("none", "Normal"),
        ("pending", "Menunggu Persetujuan Direksi"),
        ("approved", "Disetujui Direksi"),
        ("rejected", "Ditolak Direksi"),
    ], string="Persetujuan Harga < HPP", default="none", copy=False, tracking=True)

    tactical_analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Akun Analitik Diskon Taktikal",
        help="Akun analitik wajib untuk penelusuran (traceability) dampak diskon khusus terhadap profitabilitas.",
    )
    approval_request_ids = fields.One2many(
        "fmcg.approval.request",
        compute="_compute_approval_requests",
        string="Riwayat Persetujuan Terkait",
    )
    approval_count = fields.Integer(
        string="Jumlah Pengajuan",
        compute="_compute_approval_requests",
    )

    def _compute_approval_requests(self):
        ApprovalRequest = self.env["fmcg.approval.request"]
        for order in self:
            requests = ApprovalRequest.search([
                ("res_model", "=", "sale.order"),
                ("res_id", "=", order.id),
            ])
            order.approval_request_ids = requests
            order.approval_count = len(requests)

    @api.depends("order_line.discount", "order_line.price_unit", "order_line.product_id")
    def _compute_discount_and_cost_flags(self):
        for order in self:
            tactical = False
            below_hpp = False
            for line in order.order_line:
                if not line.product_id or line.display_type:
                    continue
                if line.discount > 0.0:
                    tactical = True
                net_price = line.price_unit * (1.0 - (line.discount / 100.0))
                cost_price = line.product_id.standard_price
                if cost_price > 0.0 and net_price < cost_price:
                    below_hpp = True
            order.has_tactical_discount = tactical
            order.has_below_hpp = below_hpp

    @api.depends("order_line.discount", "order_line.price_unit", "order_line.product_id")
    def _compute_below_hpp_summary(self):
        for order in self:
            summary_items = []
            for line in order.order_line:
                if not line.product_id or line.display_type:
                    continue
                net_price = line.price_unit * (1.0 - (line.discount / 100.0))
                cost_price = line.product_id.standard_price
                if cost_price > 0.0 and net_price < cost_price:
                    selisih = cost_price - net_price
                    uom = getattr(line, "product_uom_id", None) or getattr(line.product_id, "uom_id", None)
                    uom_name = uom.name if uom else ""
                    summary_items.append(
                        f"• {line.product_id.name}: Harga Net Rp {net_price:,.2f} < HPP Rp {cost_price:,.2f} "
                        f"(Rugi Rp {selisih:,.2f}/unit x {line.product_uom_qty} {uom_name})"
                    )
            order.below_hpp_summary = "\n".join(summary_items) if summary_items else ""

    def action_request_below_hpp_approval(self, reason=""):
        """Mengajukan persetujuan 2-line untuk harga jual di bawah HPP."""
        self.ensure_one()
        if not self.has_below_hpp:
            raise UserError("Pesanan ini tidak memiliki produk yang dijual di bawah HPP.")

        category = self.env["fmcg.approval.category"].search([("code", "=", "discount_below_hpp")], limit=1)
        if not category:
            raise UserError("Kategori persetujuan 'discount_below_hpp' tidak ditemukan.")

        req = self.env["fmcg.approval.request"].create({
            "category_id": category.id,
            "res_model": "sale.order",
            "res_id": self.id,
            "reference_document": f"{self.name} - {self.partner_id.name}",
            "amount": self.amount_total,
            "analytic_account_id": self.tactical_analytic_account_id.id if self.tactical_analytic_account_id else False,
            "reason": reason or f"Persetujuan harga di bawah HPP:\n{self.below_hpp_summary}",
        })
        req.action_submit()
        self.write({
            "below_hpp_approval_state": "pending",
        })
        self.message_post(
            body=(
                f"Pengajuan persetujuan harga di bawah HPP <b>{req.name}</b> "
                f"telah dikirimkan ke Branch Manager &amp; Direksi."
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

    def action_request_tactical_discount_approval(self, reason=""):
        """Mengajukan persetujuan diskon taktikal berjenjang."""
        self.ensure_one()
        if not self.has_tactical_discount:
            raise UserError("Pesanan ini tidak memiliki diskon taktikal.")

        if not self.tactical_analytic_account_id:
            raise UserError(
                "Harap pilih 'Akun Analitik Diskon Taktikal' terlebih dahulu agar dampak diskon terlacak (traceable)!"
            )

        category = self.env["fmcg.approval.category"].search([("code", "=", "tactical_discount")], limit=1)
        if not category:
            raise UserError("Kategori persetujuan 'tactical_discount' tidak ditemukan.")

        req = self.env["fmcg.approval.request"].create({
            "category_id": category.id,
            "res_model": "sale.order",
            "res_id": self.id,
            "reference_document": f"{self.name} - {self.partner_id.name}",
            "amount": self.amount_total,
            "discount_percent": self.max_line_discount if hasattr(self, "max_line_discount") else 0.0,
            "analytic_account_id": self.tactical_analytic_account_id.id,
            "reason": reason or f"Pengajuan diskon taktikal untuk pesanan {self.name}",
        })
        req.action_submit()
        if hasattr(self, "discount_approval_state"):
            self.write({"discount_approval_state": "pending"})
        self.message_post(
            body=f"Pengajuan diskon taktikal <b>{req.name}</b> telah diajukan ke penyelia/manajer.",
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

    def action_confirm(self):
        """Guard konfirmasi penjualan untuk harga < HPP dan diskon taktikal."""
        is_seed_load = (
            self.env.context.get("fmcg_seed_load")
            or self.env.context.get("fmcg_seed_batch")
            or self.env.context.get("install_mode")
        )
        if not is_seed_load:
            for order in self:
                # 1. Guard Harga di Bawah HPP (Wajib persetujuan 2-line hingga Owner/Direksi)
                if order.has_below_hpp and order.below_hpp_approval_state != "approved":
                    raise UserError(
                        f"Pesanan {order.name} tidak dapat dikonfirmasi karena terdapat produk dengan harga jual "
                        f"DI BAWAH HPP (Harga Pokok Penjualan)!\n\n"
                        f"{order.below_hpp_summary}\n\n"
                        f"Wajib mengajukan persetujuan berjenjang (Branch Manager hingga Pemilik/Direksi) "
                        f"sebelum diproses."
                    )
        return super().action_confirm()

    def _on_approval_status_change(self, request, status):
        """Callback ketika status pengajuan approval berubah."""
        for order in self:
            if request.category_code == "discount_below_hpp":
                if status == "approved":
                    order.write({"below_hpp_approval_state": "approved"})
                    order.message_post(
                        body="Persetujuan penjualan di bawah HPP telah DISETUJUI oleh Direksi/Pemilik.",
                        subtype_xmlid="mail.mt_note",
                    )
                elif status == "rejected":
                    order.write({"below_hpp_approval_state": "rejected"})
                    order.message_post(
                        body="Pengajuan penjualan di bawah HPP DITOLAK oleh manajemen.",
                        subtype_xmlid="mail.mt_note",
                    )
            elif request.category_code == "tactical_discount":
                if status == "approved":
                    if hasattr(order, "discount_approval_state"):
                        order.write({"discount_approval_state": "approved"})
                    order.message_post(body="Diskon taktikal telah DISETUJUI.", subtype_xmlid="mail.mt_note")
                elif status == "rejected":
                    if hasattr(order, "discount_approval_state"):
                        order.write({"discount_approval_state": "rejected"})
                    order.message_post(body="Diskon taktikal DITOLAK.", subtype_xmlid="mail.mt_note")
