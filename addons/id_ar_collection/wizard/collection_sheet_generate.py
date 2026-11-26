from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.addons.id_base.models.business_day import business_date

from ..models.collection_sheet import ACTIVE_STATES, OPEN_PAYMENT_STATES


class CollectionSheetGenerate(models.TransientModel):
    _name = "id.collection.sheet.generate"
    _description = "Generate Surat Jalan Penagihan"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    collect_date = fields.Date(
        string="Tanggal Penagihan", required=True, default=lambda self: business_date()
    )
    due_until = fields.Date(
        string="Jatuh Tempo Sampai",
        required=True,
        default=lambda self: business_date(),
        help="Faktur terbuka dengan tanggal jatuh tempo sampai tanggal ini (termasuk yang terlambat).",
    )
    collector_id = fields.Many2one(
        "res.users",
        string="Salesman / Kolektor",
        domain="[('share', '=', False)]",
        help="Bila diisi, hanya faktur outlet pada penugasan (PJP) kolektor itu pada tanggal penagihan.",
    )
    route = fields.Char(
        string="Rute",
        help="Bila diisi, hanya faktur pelanggan dengan kode rute pengiriman ini.",
    )
    note = fields.Text(string="Catatan")
    candidate_count = fields.Integer(compute="_compute_candidates", string="Kandidat Faktur")
    candidate_total = fields.Monetary(compute="_compute_candidates", string="Total Kandidat")
    warning = fields.Char(compute="_compute_candidates")
    foreign_count = fields.Integer(
        compute="_compute_candidates",
        string="Faktur Mata Uang Asing Dikecualikan",
        help="Faktur bermata uang selain mata uang perusahaan tidak dimasukkan ke SJP.",
    )
    currency_id = fields.Many2one(related="company_id.currency_id")

    def _candidates(self):
        """(faktur kandidat, peringatan). Kandidat = AR terbuka yang belum ada di SJP aktif."""
        self.ensure_one()
        Move = self.env["account.move"]
        busy = self.env["id.collection.sheet.line"].search([
            ("company_id", "=", self.company_id.id),
            ("sheet_id.state", "in", ACTIVE_STATES),
        ]).move_id
        pending = self.env["id.collection.receipt.line"].sudo().search([
            ("company_id", "=", self.company_id.id), ("holds_invoice", "=", True)]).move_id
        busy |= pending
        domain = [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("company_id", "=", self.company_id.id),
            ("currency_id", "=", self.company_id.currency_id.id),
            ("payment_state", "in", OPEN_PAYMENT_STATES),
            ("amount_residual", ">", 0),
            ("invoice_date_due", "!=", False),
            ("invoice_date_due", "<=", self.due_until),
            ("id", "not in", busy.ids),
        ]
        if self.route:
            domain += [
                "|",
                ("partner_id.delivery_route", "=", self.route),
                ("commercial_partner_id.delivery_route", "=", self.route),
            ]
        if self.collector_id:
            workday = self.env["id.mobile.workday"].sudo().search([
                ("user_id", "=", self.collector_id.id),
                ("company_id", "=", self.company_id.id),
                ("business_date", "=", self.collect_date),
            ], limit=1)
            if not workday:
                return Move.browse(), _("Kolektor tidak punya penugasan (PJP) pada tanggal penagihan ini.")
            domain.append(
                ("commercial_partner_id", "in", workday.outlet_ids.commercial_partner_id.ids)
            )
        return Move.search(domain, order="invoice_date_due, id"), False

    def _foreign_count(self):
        self.ensure_one()
        return self.env["account.move"].search_count([
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("company_id", "=", self.company_id.id),
            ("currency_id", "!=", self.company_id.currency_id.id),
            ("payment_state", "in", OPEN_PAYMENT_STATES),
            ("invoice_date_due", "!=", False),
            ("invoice_date_due", "<=", self.due_until),
        ])

    @api.depends("company_id", "collect_date", "due_until", "collector_id", "route")
    def _compute_candidates(self):
        for wiz in self:
            moves, warning = wiz._candidates()
            wiz.candidate_count = len(moves)
            wiz.candidate_total = sum(moves.mapped("amount_residual"))
            wiz.warning = warning
            wiz.foreign_count = wiz._foreign_count()

    def action_generate(self):
        self.ensure_one()
        moves, warning = self._candidates()
        if warning:
            raise UserError(warning)
        if not moves:
            raise UserError(_("Tidak ada faktur kandidat untuk kriteria ini."))
        sheet = self.env["id.collection.sheet"].create({
            "company_id": self.company_id.id,
            "collect_date": self.collect_date,
            "due_until": self.due_until,
            "collector_id": self.collector_id.id,
            "route": self.route,
            "note": self.note,
            "line_ids": [
                Command.create({"move_id": move.id, "amount_due": move.amount_residual})
                for move in moves
            ],
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "id.collection.sheet",
            "res_id": sheet.id,
            "view_mode": "form",
            "target": "current",
        }
