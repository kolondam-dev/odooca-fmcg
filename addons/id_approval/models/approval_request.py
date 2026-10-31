from odoo import api, fields, models
from odoo.exceptions import UserError


class FmcgApprovalRequest(models.Model):
    _name = "fmcg.approval.request"
    _description = "Transaksi Pengajuan Persetujuan FMCG"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "request_date desc, id desc"

    name = fields.Char(
        string="No. Pengajuan",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env["ir.sequence"].next_by_code("fmcg.approval.request") or "Draft",
    )
    category_id = fields.Many2one(
        "fmcg.approval.category",
        string="Kategori Persetujuan",
        required=True,
        tracking=True,
    )
    category_code = fields.Char(related="category_id.code", string="Kode Kategori", store=True)
    res_model = fields.Char(string="Model Sasaran", required=True)
    res_id = fields.Integer(string="ID Record Sasaran", required=True)
    reference_document = fields.Char(string="Dokumen / Mitra Terkait", required=True, tracking=True)

    requested_by = fields.Many2one(
        "res.users",
        string="Diajukan Oleh",
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    request_date = fields.Datetime(
        string="Tanggal Pengajuan",
        default=fields.Datetime.now,
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        string="Mata Uang",
    )
    amount = fields.Monetary(string="Nominal Pengajuan", currency_field="currency_id", tracking=True)
    discount_percent = fields.Float(string="Persentase Diskon (%)", tracking=True)
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Akun Analitik (Traceable)",
        help="Akun analitik operasional untuk pelacakan dampak diskon atau biaya.",
        tracking=True,
    )
    reason = fields.Text(string="Alasan & Justifikasi Pengajuan", required=True)

    state = fields.Selection([
        ("draft", "Draf"),
        ("pending", "Menunggu Persetujuan"),
        ("approved", "Disetujui Penuh"),
        ("rejected", "Ditolak"),
        ("cancelled", "Dibatalkan"),
    ], string="Status Persetujuan", default="draft", tracking=True, index=True)

    current_tier_sequence = fields.Integer(string="Tingkat Saat Ini (Tier)", default=1, tracking=True)
    total_tiers = fields.Integer(string="Total Tingkatan (Tiers)", compute="_compute_tier_summary", store=True)

    line_ids = fields.One2many(
        "fmcg.approval.request.line",
        "request_id",
        string="Riwayat & Rincian Tingkatan Persetujuan",
    )

    is_current_user_approver = fields.Boolean(
        string="Pengguna Berhak Menyetujui",
        compute="_compute_is_current_user_approver",
        search="_search_is_current_user_approver",
    )

    @api.depends("line_ids")
    def _compute_tier_summary(self):
        for rec in self:
            rec.total_tiers = len(rec.line_ids)

    @api.depends("state", "current_tier_sequence", "line_ids")
    def _compute_is_current_user_approver(self):
        current_user = self.env.user
        for rec in self:
            if rec.state != "pending":
                rec.is_current_user_approver = False
                continue

            current_line = rec.line_ids.filtered(
                lambda line: line.tier_sequence == rec.current_tier_sequence and line.state == "pending"
            )
            if not current_line:
                rec.is_current_user_approver = False
                continue

            # Periksa apakah user termasuk dalam approver line
            is_approver = False
            if current_line.user_id and current_line.user_id == current_user:
                is_approver = True
            elif current_line.group_id and current_line.group_id in current_user.group_ids:
                is_approver = True
            elif current_line.approver_type == "manager":
                # Atasan langsung dari requester
                employee = self.env["hr.employee"].search([("user_id", "=", rec.requested_by.id)], limit=1)
                if employee and employee.parent_id and employee.parent_id.user_id == current_user:
                    is_approver = True

            # Direktur / Administrator selalu berhak mengesahkan jika diperlukan
            if current_user.has_group("id_approval.group_fmcg_approval_director"):
                is_approver = True

            rec.is_current_user_approver = is_approver

    def _search_is_current_user_approver(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            return []

        current_user = self.env.user
        user_groups = current_user.group_ids.ids

        # Cari lines yang berstatus pending dan approver cocok dengan user atau group
        lines = self.env["fmcg.approval.request.line"].search([
            ("state", "=", "pending"),
            "|",
            ("user_id", "=", current_user.id),
            ("group_id", "in", user_groups),
        ])

        req_ids = []
        for line in lines:
            req = line.request_id
            if req.state == "pending" and line.tier_sequence == req.current_tier_sequence:
                req_ids.append(req.id)

        # Direktur / Administrator berhak mengesahkan semua permintaan pending
        if current_user.has_group("id_approval.group_fmcg_approval_director"):
            all_pending = self.search([("state", "=", "pending")]).ids
            req_ids = list(set(req_ids + all_pending))

        is_positive = (operator == "=" and value is True) or (operator == "!=" and value is False)
        if is_positive:
            return [("id", "in", req_ids)]
        else:
            return [("id", "not in", req_ids)]

    def action_submit(self):
        """Membangun lines tier persetujuan dan mengaktifkan status pending."""
        for rec in self:
            if rec.state != "draft":
                continue

            # Cari aturan tier yang sesuai dari kategori
            rules = rec.category_id.rule_ids.sorted(key=lambda r: r.tier_sequence)
            applicable_rules = []
            for r in rules:
                # Filter nominal jika kategori bertingkat nominal
                if rec.category_id.has_amount_tiers and r.min_amount > 0 and rec.amount < r.min_amount:
                    continue
                # Filter diskon jika kategori bertingkat diskon
                if rec.category_id.has_discount_tiers and r.min_discount > 0 and rec.discount_percent < r.min_discount:
                    continue
                applicable_rules.append(r)

            if not applicable_rules:
                # Fallback ke rule standar pertama
                applicable_rules = list(rules[:1])

            # Buat approval request lines
            lines_vals = []
            for idx, r in enumerate(applicable_rules):
                lines_vals.append((0, 0, {
                    "tier_sequence": idx + 1,
                    "tier_name": r.name,
                    "rule_id": r.id,
                    "approver_type": r.approver_type,
                    "group_id": r.group_id.id if r.group_id else False,
                    "user_id": r.user_id.id if r.user_id else False,
                    "state": "pending" if idx == 0 else "waiting",
                }))

            rec.write({
                "line_ids": lines_vals,
                "current_tier_sequence": 1,
                "state": "pending",
            })
            rec.message_post(
                body=f"Pengajuan persetujuan <b>{rec.name}</b> telah diajukan untuk <b>{rec.reference_document}</b>.",
                subtype_xmlid="mail.mt_note",
            )
            # Notifikasi ke dokumen target
            rec._notify_target_record("pending")

    def action_approve(self, notes=""):
        """Menyetujui tier aktif saat ini. Jika ini tier terakhir, status menjadi approved."""
        for rec in self:
            if rec.state != "pending":
                raise UserError("Pengajuan ini tidak sedang menunggu persetujuan.")

            current_line = rec.line_ids.filtered(
                lambda line: line.tier_sequence == rec.current_tier_sequence and line.state == "pending"
            )
            if not current_line:
                raise UserError("Tidak ditemukan tahapan persetujuan aktif untuk diproses.")

            current_line.write({
                "state": "approved",
                "actual_approver_id": self.env.user.id,
                "action_date": fields.Datetime.now(),
                "notes": notes or "Disetujui",
            })

            # Cek apakah ada tier selanjutnya
            next_tier = rec.current_tier_sequence + 1
            next_line = rec.line_ids.filtered(lambda line: line.tier_sequence == next_tier)

            if next_line:
                next_line.write({"state": "pending"})
                rec.write({"current_tier_sequence": next_tier})
                rec.message_post(
                    body=f"Tingkat {current_line.tier_name} telah disetujui oleh {self.env.user.name}. "
                         f"Beralih ke tingkat berikutnya: <b>{next_line.tier_name}</b>.",
                    subtype_xmlid="mail.mt_note",
                )
            else:
                # Selesai seluruh tingkat approval
                rec.write({"state": "approved"})
                rec.message_post(
                    body=f"Persetujuan <b>{rec.name}</b> telah disetujui penuh oleh {self.env.user.name}!",
                    subtype_xmlid="mail.mt_note",
                )
                rec._notify_target_record("approved")

    def action_reject(self, notes=""):
        """Menolak pengajuan persetujuan."""
        for rec in self:
            if rec.state != "pending":
                raise UserError("Pengajuan ini tidak sedang menunggu persetujuan.")

            current_line = rec.line_ids.filtered(
                lambda line: line.tier_sequence == rec.current_tier_sequence and line.state == "pending"
            )
            if current_line:
                current_line.write({
                    "state": "rejected",
                    "actual_approver_id": self.env.user.id,
                    "action_date": fields.Datetime.now(),
                    "notes": notes or "Ditolak",
                })

            rec.write({"state": "rejected"})
            rec.message_post(
                body=f"Pengajuan <b>{rec.name}</b> DITOLAK oleh {self.env.user.name}. Catatan: {notes or '-'}",
                subtype_xmlid="mail.mt_note",
            )
            rec._notify_target_record("rejected")

    def action_cancel(self):
        for rec in self:
            rec.write({"state": "cancelled"})
            rec._notify_target_record("cancelled")

    def _notify_target_record(self, status):
        """Memanggil callback pada record model target jika tersedia."""
        for rec in self:
            target = self.env[rec.res_model].browse(rec.res_id).exists()
            if target and hasattr(target, "_on_approval_status_change"):
                target._on_approval_status_change(rec, status)


class FmcgApprovalRequestLine(models.Model):
    _name = "fmcg.approval.request.line"
    _description = "Rincian Tingkatan Persetujuan (Tier Line)"
    _order = "tier_sequence, id"

    request_id = fields.Many2one(
        "fmcg.approval.request",
        string="Pengajuan Persetujuan",
        required=True,
        ondelete="cascade",
    )
    tier_sequence = fields.Integer(string="Tingkat (Tier)", default=1, required=True)
    tier_name = fields.Char(string="Nama Tingkatan", required=True)
    rule_id = fields.Many2one("fmcg.approval.rule", string="Aturan Referensi")
    approver_type = fields.Selection([
        ("group", "Grup Pengguna"),
        ("user", "Pengguna Spesifik"),
        ("manager", "Atasan Langsung"),
    ], string="Tipe Approver", default="group")
    group_id = fields.Many2one("res.groups", string="Grup Wewenang")
    user_id = fields.Many2one("res.users", string="Pengguna Ditunjuk")
    actual_approver_id = fields.Many2one("res.users", string="Disetujui/Ditolak Oleh")
    action_date = fields.Datetime(string="Waktu Aksi")
    state = fields.Selection([
        ("waiting", "Menunggu Giliran"),
        ("pending", "Menunggu Persetujuan"),
        ("approved", "Disetujui"),
        ("rejected", "Ditolak"),
        ("skipped", "Dilewati"),
    ], string="Status Tier", default="waiting", required=True)
    notes = fields.Text(string="Catatan Manajerial")
