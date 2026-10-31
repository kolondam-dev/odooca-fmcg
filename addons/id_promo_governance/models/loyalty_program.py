import logging

from odoo import fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class LoyaltyProgram(models.Model):
    _inherit = "loyalty.program"

    mou_number = fields.Char(
        string="Nomor Perjanjian / MoU Prinsipal",
        required=True,
        copy=False,
        index=True,
        default=lambda self: self.env["ir.sequence"].next_by_code("id.promo.mou") or "MOU-PROMO-DRAFT",
        help="Nomor Surat Perjanjian Dagang / Trade Promo Agreement dari Prinsipal",
    )
    doc_date = fields.Date(
        string="Tanggal Dokumen Kontrak",
        default=fields.Date.context_today,
        help="Tanggal penandatanganan kesepakatan promosi antara prinsipal dan distributor",
    )
    budget_source = fields.Selection(
        [
            ("principal", "100% Beban Prinsipal (Klaim Penuh)"),
            ("distributor", "100% Beban Distributor MDU"),
            ("joint", "Joint Sharing (50% Prinsipal : 50% Distributor MDU)"),
        ],
        string="Sumber Anggaran Promosi",
        default="principal",
        required=True,
        tracking=True,
        help="Alokasi penanggung beban biaya diskon promosi",
    )
    principal_id = fields.Many2one(
        "id.principal",
        string="Prinsipal Pemilik",
        required=True,
        index=True,
        tracking=True,
        help="Prinsipal yang menerbitkan promo dan menjadi tujuan penagihan reimbursement",
    )
    claim_account_id = fields.Many2one(
        "account.account",
        string="Akun Piutang Klaim Promosi",
        domain="[('account_type', 'in', ['asset_receivable', 'asset_current'])]",
        help="Akun perantara neraca untuk mencatat saldo piutang klaim promosi ke prinsipal",
    )
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Akun Analitik / Cost Center",
        help="Akun analitik untuk memonitor realisasi anggaran promosi per prinsipal",
    )
    principal_approver_name = fields.Char(
        string="Nama Approver Prinsipal",
        help="Nama pejabat resmi dari prinsipal yang menyetujui program promo",
    )
    principal_approver_title = fields.Char(
        string="Jabatan Approver Prinsipal",
        help="Jabatan pejabat prinsipal (contoh: Area Sales Manager, Regional Trade Marketing)",
    )
    mou_attachment = fields.Binary(
        string="Lampiran Dokumen MoU",
        attachment=True,
        help="File pindaian / digital dokumen resmi kesepakatan promo dari prinsipal",
    )
    mou_filename = fields.Char(string="Nama File MoU")
    governance_state = fields.Selection(
        [
            ("draft", "Draft Program"),
            ("pending", "Menunggu Approval Internal"),
            ("approved", "Disetujui (Approved)"),
            ("active", "Sedang Berjalan (Active)"),
            ("closed", "Selesai / Ditutup"),
            ("rejected", "Ditolak (Rejected)"),
        ],
        string="Status Tata Kelola",
        default="draft",
        tracking=True,
        copy=False,
    )
    approver_id = fields.Many2one(
        "res.users",
        string="Disetujui Oleh (Internal)",
        copy=False,
        readonly=True,
    )
    approval_date = fields.Datetime(
        string="Waktu Persetujuan",
        copy=False,
        readonly=True,
    )
    rejection_notes = fields.Text(
        string="Catatan Penolakan",
        copy=False,
    )
    total_claimable_amount = fields.Monetary(
        string="Total Tagihan Klaim Terkumpul",
        compute="_compute_claim_totals",
        currency_field="currency_id",
        help="Total akumulasi rupiah diskon promosi yang dapat ditagihkan kembali ke prinsipal",
    )
    order_line_count = fields.Integer(
        string="Jumlah Transaksi Terkait",
        compute="_compute_claim_totals",
    )

    def _compute_claim_totals(self):
        so_line_model = self.env["sale.order.line"]
        for record in self:
            lines = so_line_model.search([
                ("promo_program_id", "=", record.id),
                ("order_id.state", "in", ["sale", "done"]),
            ])
            record.order_line_count = len(lines)
            record.total_claimable_amount = sum(lines.mapped("promo_claim_amount"))

    def action_submit_approval(self):
        for record in self:
            if not record.rule_ids:
                msg = _("Harap tentukan minimal satu aturan promosi (SKU target) sebelum mengajukan approval!")
                raise ValidationError(msg)
            if not record.reward_ids:
                msg = _("Harap tentukan imbalan / nilai diskon promosi sebelum mengajukan approval!")
                raise ValidationError(msg)
            record.write({"governance_state": "pending"})
            _logger.info("Promo %s (%s) diajukan untuk approval internal", record.name, record.mou_number)

    def action_approve(self):
        for record in self:
            record.write({
                "governance_state": "approved",
                "approver_id": self.env.user.id,
                "approval_date": fields.Datetime.now(),
                "active": True,
            })
            _logger.info("Promo %s disetujui oleh %s", record.name, self.env.user.name)

    def action_activate(self):
        for record in self:
            if record.governance_state != "approved":
                raise UserError(_("Hanya program promosi yang telah disetujui (Approved) yang dapat diaktifkan!"))
            record.write({
                "governance_state": "active",
                "active": True,
            })

    def action_reject(self):
        for record in self:
            record.write({
                "governance_state": "rejected",
                "active": False,
            })

    def action_close(self):
        for record in self:
            record.write({
                "governance_state": "closed",
                "active": False,
            })

    def action_reset_draft(self):
        for record in self:
            record.write({
                "governance_state": "draft",
                "active": False,
                "approver_id": False,
                "approval_date": False,
            })

    def action_open_sku_wizard(self):
        self.ensure_one()
        return {
            "name": _("Pilih Target SKU Promosi"),
            "type": "ir.actions.act_window",
            "res_model": "id.promo.sku.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_program_id": self.id,
                "default_principal_id": self.principal_id.id,
            },
        }

    def action_view_claims(self):
        self.ensure_one()
        return {
            "name": _("Rincian Klaim Tagihan Promosi: %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "sale.order.line",
            "view_mode": "list,pivot,form",
            "domain": [("promo_program_id", "=", self.id), ("order_id.state", "in", ["sale", "done"])],
            "context": {"create": False},
        }
