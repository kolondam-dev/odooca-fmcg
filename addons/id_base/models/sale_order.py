from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    fmcg_seed_batch = fields.Char(
        string="FMCG Seed Source Batch",
        default=False,
        copy=False,
        index=True,
        help="Penanda batch persisten untuk Sales Order seed FMCG kanonikal.",
    )

    # --- Approval Kredit & Limit Outlet FMCG ---
    credit_limit_exceeded = fields.Boolean(
        string="Melebihi Limit / Overdue",
        compute="_compute_credit_limit_exceeded",
        store=True,
        help=(
            "Menandakan bahwa pesanan ini menyebabkan piutang outlet melebihi "
            "limit kredit atau terdapat faktur jatuh tempo."
        ),
    )
    partner_credit_limit = fields.Float(
        string="Limit Kredit Outlet",
        related="partner_id.credit_limit",
        readonly=True,
    )
    partner_credit_balance = fields.Monetary(
        string="Saldo Piutang Berjalan",
        compute="_compute_partner_credit_balance",
        help="Total saldo piutang berjalan outlet di sistem.",
    )
    total_credit_exposure = fields.Monetary(
        string="Total Eksposur Piutang",
        compute="_compute_partner_credit_balance",
        help="Saldo piutang berjalan ditambah total pesanan saat ini.",
    )
    credit_approval_state = fields.Selection(
        [
            ("none", "Normal / Dalam Limit"),
            ("pending", "Menunggu Persetujuan"),
            ("approved", "Disetujui"),
            ("rejected", "Ditolak"),
        ],
        string="Status Persetujuan Kredit",
        default="none",
        copy=False,
        tracking=True,
    )
    credit_approved_by = fields.Many2one(
        "res.users",
        string="Disetujui Oleh (Kredit)",
        copy=False,
        readonly=True,
    )
    credit_approved_date = fields.Datetime(
        string="Waktu Persetujuan Kredit",
        copy=False,
        readonly=True,
    )
    credit_approval_note = fields.Text(
        string="Catatan Persetujuan Kredit",
        copy=False,
    )

    # --- Approval Diskon Khusus / Manual FMCG ---
    max_line_discount = fields.Float(
        string="Diskon Baris Tertinggi (%)",
        compute="_compute_max_line_discount",
        store=True,
    )
    discount_approval_state = fields.Selection(
        [
            ("none", "Normal / Sesuai Matriks"),
            ("pending", "Menunggu Persetujuan"),
            ("approved", "Disetujui"),
            ("rejected", "Ditolak"),
        ],
        string="Status Persetujuan Diskon",
        default="none",
        copy=False,
        tracking=True,
    )
    discount_approved_by = fields.Many2one(
        "res.users",
        string="Disetujui Oleh (Diskon)",
        copy=False,
        readonly=True,
    )
    discount_approved_date = fields.Datetime(
        string="Waktu Persetujuan Diskon",
        copy=False,
        readonly=True,
    )
    discount_approval_note = fields.Text(
        string="Catatan Persetujuan Diskon",
        copy=False,
    )

    @api.depends("partner_id", "partner_id.credit")
    def _compute_partner_credit_balance(self):
        for order in self:
            partner = order.partner_id.commercial_partner_id or order.partner_id
            order.partner_credit_balance = partner.credit if partner else 0.0
            order.total_credit_exposure = order.partner_credit_balance + (order.amount_total or 0.0)

    @api.depends("order_line.discount")
    def _compute_max_line_discount(self):
        for order in self:
            discounts = [line.discount for line in order.order_line if line.discount]
            order.max_line_discount = max(discounts) if discounts else 0.0

    @api.depends(
        "partner_id",
        "partner_id.credit",
        "partner_id.credit_limit",
        "partner_id.credit_mode",
        "amount_total",
    )
    def _compute_credit_limit_exceeded(self):
        today = fields.Date.today()
        for order in self:
            # Lewati order historis kanonikal
            if order.fmcg_seed_batch or self.env.context.get("fmcg_seed_load"):
                order.credit_limit_exceeded = False
                continue

            partner = order.partner_id.commercial_partner_id or order.partner_id
            if not partner:
                order.credit_limit_exceeded = False
                continue

            credit_mode = partner.credit_mode or "limit"
            limit = partner.credit_limit or 0.0
            cur_credit = partner.credit or 0.0
            exposure = cur_credit + (order.amount_total or 0.0)

            exceeded = False

            # 1. Cek faktur jatuh tempo (overdue invoices) untuk mode strict atau limit_due
            if credit_mode in ["strict", "limit_due"]:
                overdue_inv = self.env["account.move"].search_count([
                    ("commercial_partner_id", "=", partner.id),
                    ("move_type", "=", "out_invoice"),
                    ("state", "=", "posted"),
                    ("payment_state", "not in", ["paid", "in_payment", "reversed"]),
                    ("invoice_date_due", "<", today),
                ])
                if overdue_inv > 0:
                    exceeded = True

            # 2. Cek limit kredit jika limit > 0
            if not exceeded and credit_mode in ["limit", "limit_due", "approval"]:
                if limit > 0.0 and exposure > limit:
                    exceeded = True

            order.credit_limit_exceeded = exceeded

    # --- Action Methods Approval Kredit ---
    def action_request_credit_approval(self):
        """Mengajukan permintaan persetujuan kredit ke supervisor / Branch Manager."""
        for order in self:
            if not order.credit_limit_exceeded:
                continue
            order.write({"credit_approval_state": "pending"})
            order.message_post(
                body=(
                    f"Pengajuan Persetujuan Kredit: Total eksposur Rp {order.total_credit_exposure:,.2f} "
                    f"melebihi limit kredit outlet Rp {order.partner_credit_limit:,.2f}."
                ),
                subject="Permohonan Persetujuan Limit Kredit FMCG",
            )
        return True

    def action_approve_credit(self):
        """Menyetujui penjualan over-limit oleh Branch Manager / Finance."""
        for order in self:
            order.write({
                "credit_approval_state": "approved",
                "credit_approved_by": self.env.user.id,
                "credit_approved_date": fields.Datetime.now(),
            })
            order.message_post(
                body=f"Persetujuan Kredit Diberikan oleh {self.env.user.name}. Pesanan diizinkan diproses.",
                subject="Persetujuan Kredit Disetujui",
            )
        return True

    def action_reject_credit(self):
        """Menolak penjualan over-limit oleh Branch Manager / Finance."""
        for order in self:
            order.write({
                "credit_approval_state": "rejected",
                "credit_approved_by": self.env.user.id,
                "credit_approved_date": fields.Datetime.now(),
            })
            order.message_post(
                body=f"Persetujuan Kredit Ditolak oleh {self.env.user.name}.",
                subject="Persetujuan Kredit Ditolak",
            )
        return True

    # --- Action Methods Approval Diskon Khusus ---
    def action_request_discount_approval(self):
        """Mengajukan persetujuan diskon khusus ke Sales Supervisor."""
        for order in self:
            order.write({"discount_approval_state": "pending"})
            order.message_post(
                body=f"Pengajuan Persetujuan Diskon Khusus: Diskon tertinggi baris {order.max_line_discount:.1f}%.",
                subject="Permohonan Persetujuan Diskon Penjualan",
            )
        return True

    def action_approve_discount(self):
        """Menyetujui diskon khusus oleh Sales Supervisor."""
        for order in self:
            order.write({
                "discount_approval_state": "approved",
                "discount_approved_by": self.env.user.id,
                "discount_approved_date": fields.Datetime.now(),
            })
            order.message_post(
                body=f"Diskon khusus disetujui oleh {self.env.user.name}.",
                subject="Persetujuan Diskon Disetujui",
            )
        return True

    def action_reject_discount(self):
        """Menolak diskon khusus oleh Sales Supervisor."""
        for order in self:
            order.write({
                "discount_approval_state": "rejected",
                "discount_approved_by": self.env.user.id,
                "discount_approved_date": fields.Datetime.now(),
            })
            order.message_post(
                body=f"Diskon khusus ditolak oleh {self.env.user.name}.",
                subject="Persetujuan Diskon Ditolak",
            )
        return True

    def action_confirm(self):
        """Guard persetujuan kredit dan diskon sebelum SO dikonfirmasi."""
        for order in self:
            # Lewati proteksi jika seed batch atau context load
            if order.fmcg_seed_batch or self.env.context.get("fmcg_seed_load"):
                continue

            # 1. Guard Credit Limit
            if order.credit_limit_exceeded and order.credit_approval_state != "approved":
                raise UserError(
                    f"Pesanan {order.name} tidak dapat dikonfirmasi!\n"
                    f"Pelanggan '{order.partner_id.name}' melebihi batas kredit / memiliki faktur jatuh tempo.\n"
                    f"- Limit Kredit: Rp {order.partner_credit_limit:,.2f}\n"
                    f"- Saldo Piutang: Rp {order.partner_credit_balance:,.2f}\n"
                    f"- Total Pesanan: Rp {order.amount_total:,.2f}\n"
                    f"- Total Eksposur: Rp {order.total_credit_exposure:,.2f}\n\n"
                    "Silakan klik tombol 'Ajukan Persetujuan Kredit' untuk meminta persetujuan Branch Manager."
                )

            # 2. Guard Diskon Khusus
            if order.discount_approval_state == "pending":
                raise UserError(
                    f"Pesanan {order.name} memiliki diskon khusus yang masih menunggu persetujuan Branch Manager."
                )
            if order.discount_approval_state == "rejected":
                raise UserError(
                    f"Pesanan {order.name} memiliki diskon khusus yang telah ditolak oleh Branch Manager. "
                    "Harap sesuaikan diskon baris sebelum konfirmasi."
                )

        return super().action_confirm()
