from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError


APPROVAL_WORK_TZ = "Asia/Makassar"  # hari/bulan kerja WITA, selaras PWA (WORK_TZ)


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

        decision = self._approval_discount_decision(category)
        req = self.env["fmcg.approval.request"].create({
            "category_id": category.id,
            "res_model": "sale.order",
            "res_id": self.id,
            "reference_document": f"{self.name} - {self.partner_id.name}",
            "amount": self.amount_total,
            "discount_percent": decision["pct"],
            "principal_id": decision["principal_id"] or False,
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
        """Principal pertama pada baris produk (kompatibilitas pesanan satu principal)."""
        self.ensure_one()
        for line in self.order_line:
            pid = self._approval_line_principal(line)
            if pid:
                return pid
        return False

    @staticmethod
    def _approval_line_principal(line):
        """Principal sebuah baris: baris reward memakai principal program promo (bila ada),
        selain itu principal produk. 0/False = tanpa principal."""
        if line.price_subtotal < 0:
            promo_principal = getattr(line, "promo_principal_id", False)
            if promo_principal:
                return promo_principal.id
        return line.product_id.principal_id.id or False

    @api.model
    def _approval_tz_bounds(self, anchor, scope):
        """Awal/akhir jendela (UTC naif) menurut hari/bulan kerja WITA, bukan hari UTC."""
        tz = pytz.timezone(APPROVAL_WORK_TZ)
        local = pytz.utc.localize(anchor).astimezone(tz)
        day = local.date()
        if scope == "outlet_month":
            first = day.replace(day=1)
            nxt = (first + timedelta(days=32)).replace(day=1)
        else:
            first, nxt = day, day + timedelta(days=1)

        def to_utc(d):
            return tz.localize(datetime.combine(d, time.min)).astimezone(pytz.utc).replace(tzinfo=None)

        return to_utc(first), to_utc(nxt)

    @classmethod
    def _stats_by_principal(cls, lines, into=None):
        """{principal_id: [nilai diskon Rp, nilai bruto Rp]}: diskon baris + reward program resmi."""
        stats = into if into is not None else {}
        for line in lines:
            if line.display_type:
                continue
            bucket = stats.setdefault(cls._approval_line_principal(line), [0.0, 0.0])
            if line.price_subtotal < 0:  # baris reward/program bernilai negatif
                bucket[0] += abs(line.price_subtotal)
                continue
            line_gross = line.price_unit * line.product_uom_qty
            bucket[1] += line_gross
            bucket[0] += line_gross * (line.discount or 0.0) / 100.0
        return stats

    def _approval_cumulative_by_principal(self, scope="order"):
        """{principal_id: diskon kumulatif %} berbobot nilai, dihitung terpisah per principal.

        Pada cakupan outlet_month / salesman_day, pesanan lain pada jendela WITA yang sama
        (company sama, tidak batal, tidak ditolak) ikut dihitung per principal.
        """
        self.ensure_one()
        stats = self._stats_by_principal(self.order_line)
        if scope in ("outlet_month", "salesman_day"):
            start, end = self._approval_tz_bounds(self.date_order or fields.Datetime.now(), scope)
            owner = ("order_id.partner_id", "=", self.partner_id.id) if scope == "outlet_month" \
                else ("order_id.user_id", "=", self.user_id.id)
            others = self.env["sale.order.line"].sudo().search([
                owner,
                ("order_id", "!=", self.id),
                ("order_id.company_id", "=", self.company_id.id),
                ("order_id.state", "!=", "cancel"),
                ("order_id.discount_approval_state", "!=", "rejected"),
                ("order_id.date_order", ">=", start),
                ("order_id.date_order", "<", end),
            ])
            self._stats_by_principal(others, into=stats)
        return {pid: round(d / g * 100.0, 4) for pid, (d, g) in stats.items() if g > 0}

    def _approval_cumulative_discount_pct(self, scope="order"):
        """Diskon kumulatif tertinggi (%) di antara principal pada pesanan."""
        self.ensure_one()
        by_principal = self._approval_cumulative_by_principal(scope)
        return max(by_principal.values()) if by_principal else 0.0

    def _approval_discount_decision(self, category):
        """Keputusan approval diskon per principal.

        Mengembalikan dict: within_free_zone (semua principal berdiskon di dalam zona bebasnya),
        principal_id dan pct (principal penentu: rantai tier terpanjang, lalu % tertinggi),
        free_limit (batas principal penentu, bila ada).
        """
        self.ensure_one()
        by_principal = {
            pid: pct for pid, pct in self._approval_cumulative_by_principal(category.cumulative_scope).items()
            if pct > 0.0
        }
        if not by_principal:
            return {"within_free_zone": False, "principal_id": False, "pct": 0.0, "free_limit": None}
        exceeding = []
        for pid, pct in by_principal.items():
            limit = category._free_zone_limit(pid)
            if limit is None or pct > limit:
                exceeding.append((pid, pct, limit))
        if not exceeding:
            pid = max(by_principal, key=by_principal.get)
            return {"within_free_zone": True, "principal_id": pid, "pct": by_principal[pid],
                    "free_limit": category._free_zone_limit(pid)}
        pid, pct, limit = max(
            exceeding,
            key=lambda e: (len(category._applicable_tier_rules(e[0], e[1], self.amount_total)), e[1]),
        )
        return {"within_free_zone": False, "principal_id": pid, "pct": pct, "free_limit": limit}

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
                decision = order._approval_discount_decision(category) if category else {}
                if category and decision["within_free_zone"]:
                    order.message_post(
                        body=f"Diskon kumulatif {decision['pct']:.2f}% berada dalam zona bebas "
                             f"(&le; {decision['free_limit']:.2f}%): tanpa persetujuan.",
                        subtype_xmlid="mail.mt_note",
                    )
                elif category:
                    req = Request.create({
                        "category_id": category.id,
                        "res_model": "sale.order",
                        "res_id": order.id,
                        "reference_document": f"{order.name} - {order.partner_id.name}",
                        "amount": order.amount_total,
                        "discount_percent": decision["pct"],
                        "principal_id": decision["principal_id"] or False,
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
