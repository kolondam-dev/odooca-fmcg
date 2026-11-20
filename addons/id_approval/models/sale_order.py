from datetime import timedelta

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
            "discount_percent": self._approval_cumulative_discount_pct(category.cumulative_scope),
            "analytic_account_id": self.tactical_analytic_account_id.id,
            "reason": reason or f"Pengajuan diskon taktikal untuk pesanan {self.name}",
        })
        req.action_submit()
        if hasattr(self, "discount_approval_state") and req.state == "pending":
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

    def _approval_principal_id(self):
        """Principal pesanan (pesanan lapangan dipecah per principal; ambil dari baris produk)."""
        self.ensure_one()
        for line in self.order_line:
            if line.product_id.principal_id:
                return line.product_id.principal_id.id
        return False

    @staticmethod
    def _discount_stats(lines):
        """(nilai diskon Rp, nilai bruto Rp) dari baris: diskon baris + baris reward program resmi."""
        gross = disc = 0.0
        for line in lines:
            if line.display_type:
                continue
            if line.price_subtotal < 0:  # baris reward/program bernilai negatif
                disc += abs(line.price_subtotal)
                continue
            line_gross = line.price_unit * line.product_uom_qty
            gross += line_gross
            disc += line_gross * (line.discount or 0.0) / 100.0
        return disc, gross

    def _approval_cumulative_discount_pct(self, scope="order"):
        """Diskon kumulatif (%), berbobot nilai, per principal pesanan.

        Menggabungkan diskon baris + diskon program resmi (reward). Untuk cakupan
        outlet_month / salesman_day, pesanan lain pada jendela yang sama (principal sama,
        tidak batal, tidak ditolak) ikut dihitung bersama pesanan ini.
        """
        self.ensure_one()
        disc, gross = self._discount_stats(self.order_line)
        if scope in ("outlet_month", "salesman_day"):
            principal = self._approval_principal_id()
            day = (self.date_order or fields.Datetime.now()).date()
            if scope == "outlet_month":
                start = day.replace(day=1)
                end = (start + timedelta(days=32)).replace(day=1)
                owner = [("order_id.partner_id", "=", self.partner_id.id)]
            else:
                start, end = day, day + timedelta(days=1)
                owner = [("order_id.user_id", "=", self.user_id.id)]
            domain = owner + [
                ("order_id", "!=", self.id),
                ("order_id.state", "!=", "cancel"),
                ("order_id.discount_approval_state", "!=", "rejected"),
                ("order_id.date_order", ">=", fields.Datetime.to_datetime(start)),
                ("order_id.date_order", "<", fields.Datetime.to_datetime(end)),
                ("product_id.principal_id", "=", principal or False),
            ]
            other_disc, other_gross = self._discount_stats(
                self.env["sale.order.line"].sudo().search(domain))
            disc += other_disc
            gross += other_gross
        return round(disc / gross * 100.0, 4) if gross > 0 else 0.0

    def _open_approval_request(self, category_code):
        """Permintaan approval yang masih berjalan (draf/pending) untuk SO ini dan kategori tertentu."""
        self.ensure_one()
        return self.env["fmcg.approval.request"].sudo().search([
            ("res_model", "=", "sale.order"),
            ("res_id", "=", self.id),
            ("category_id.code", "=", category_code),
            ("state", "in", ("draft", "pending")),
        ], limit=1)

    def _mobile_auto_request_approvals(self, discount_reason=""):
        """Membuat permintaan approval otomatis untuk SO dari aplikasi lapangan (BE-14).

        Berbeda dengan tombol di form SO, jalur ini tidak mewajibkan akun analitik
        (akun diisi bila SO sudah memilikinya) karena salesman tidak mengisinya.
        Idempoten: kategori yang sudah punya permintaan berjalan dilewati.
        Mengembalikan recordset fmcg.approval.request yang baru dibuat.
        """
        Request = self.env["fmcg.approval.request"].sudo()
        Category = self.env["fmcg.approval.category"].sudo()
        created = Request
        for order in self:
            if order.has_tactical_discount and not order._open_approval_request("tactical_discount"):
                category = Category.search([("code", "=", "tactical_discount")], limit=1)
                cumulative = order._approval_cumulative_discount_pct(
                    category.cumulative_scope if category else "order")
                free_limit = category._free_zone_limit(order._approval_principal_id()) if category else None
                if category and free_limit is not None and cumulative <= free_limit:
                    order.message_post(
                        body=f"Diskon kumulatif {cumulative:.2f}% berada dalam zona bebas "
                             f"(&le; {free_limit:.2f}%): tanpa persetujuan.",
                        subtype_xmlid="mail.mt_note",
                    )
                elif category:
                    req = Request.create({
                        "category_id": category.id,
                        "res_model": "sale.order",
                        "res_id": order.id,
                        "reference_document": f"{order.name} - {order.partner_id.name}",
                        "amount": order.amount_total,
                        "discount_percent": cumulative,
                        "analytic_account_id": order.tactical_analytic_account_id.id or False,
                        "reason": (discount_reason or order.discount_approval_note
                                   or f"Diskon taktikal dari aplikasi lapangan untuk pesanan {order.name}"),
                    })
                    req.action_submit()
                    if req.state == "pending":
                        order.write({"discount_approval_state": "pending"})
                    order.message_post(
                        body=f"Pengajuan diskon taktikal <b>{req.name}</b> dibuat otomatis dari aplikasi lapangan.",
                        subtype_xmlid="mail.mt_note",
                    )
                    created |= req
            if order.has_below_hpp and order.below_hpp_approval_state in ("none", False) \
                    and not order._open_approval_request("discount_below_hpp"):
                category = Category.search([("code", "=", "discount_below_hpp")], limit=1)
                if category:
                    req = Request.create({
                        "category_id": category.id,
                        "res_model": "sale.order",
                        "res_id": order.id,
                        "reference_document": f"{order.name} - {order.partner_id.name}",
                        "amount": order.amount_total,
                        "analytic_account_id": order.tactical_analytic_account_id.id or False,
                        "reason": f"Persetujuan harga di bawah HPP:\n{order.below_hpp_summary}",
                    })
                    req.action_submit()
                    order.write({"below_hpp_approval_state": "pending"})
                    order.message_post(
                        body=f"Pengajuan harga di bawah HPP <b>{req.name}</b> dibuat otomatis dari aplikasi lapangan.",
                        subtype_xmlid="mail.mt_note",
                    )
                    created |= req
            if getattr(order, "credit_limit_exceeded", False) \
                    and getattr(order, "credit_approval_state", False) in ("none", False):
                order.action_request_credit_approval()
        return created

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
