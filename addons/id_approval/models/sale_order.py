from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from hashlib import sha256
import json

import pytz

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


APPROVAL_WORK_TZ = "Asia/Makassar"  # hari/bulan kerja WITA, selaras PWA (WORK_TZ)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    has_program_discount = fields.Boolean(
        string="Memakai Promo Resmi", compute="_compute_has_program_discount")

    def _compute_has_program_discount(self):
        for order in self:
            order.has_program_discount = order._has_program_discount()

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

    @api.depends("order_line.discount", "order_line.price_unit", "order_line.product_id",
                 "order_line.product_uom_qty", "commercial_tactical_components")
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
                promo_basis = (order.commercial_tactical_components or {}).get("promo_basis")
                if promo_basis and line.price_unit > 0 and line.product_uom_qty > 0:
                    net_price -= promo_basis[2] / line.product_uom_qty
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
        self.check_access("write")
        req = self.env["fmcg.approval.request"].sudo().create({
            "category_id": category.id,
            "res_model": "sale.order",
            "res_id": self.id,
            "reference_document": f"{self.name} - {self.partner_id.name}",
            "amount": self.amount_total,
            "discount_percent": decision["pct"],
            "principal_id": decision["principal_id"] or False,
            "principal_decided": True,
            "analytic_account_id": self.tactical_analytic_account_id.id,
            "reason": reason or f"Pengajuan diskon taktikal untuk pesanan {self.name}",
            **self._approval_snapshot_vals(),
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
            reward = getattr(line, "reward_id", False)
            promo_principal = getattr(line, "promo_principal_id", False) or (
                getattr(reward.program_id, "principal_id", False) if reward else False
            )
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

    @api.model
    def _approval_usage_entries(self, scope, user, partner_ids, company, anchor):
        """Pemakaian diskon pada jendela WITA berjalan: [{outlet_id, principal, discount_amount, gross_amount}].

        salesman_day: pesanan salesman pada hari ini (outlet_id null). outlet_month: pesanan outlet PJP
        pada bulan ini. Dibaca lewat ACL pengguna (tanpa sudo): record rule dapat menyembunyikan
        pesanan salesman lain sehingga angka bisa lebih rendah; server tetap otoritatif.
        """
        start, end = self._approval_tz_bounds(anchor, scope)
        domain = [
            ("order_id.company_id", "=", company.id),
            ("order_id.state", "!=", "cancel"),
            ("order_id.discount_approval_state", "!=", "rejected"),
            ("order_id.date_order", ">=", start),
            ("order_id.date_order", "<", end),
        ]
        if scope == "salesman_day":
            domain.append(("order_id.user_id", "=", user.id))
        else:
            domain.append(("order_id.partner_id", "in", list(partner_ids)))
        grouped = {}
        for line in self.env["sale.order.line"].search(domain):
            outlet = line.order_id.partner_id.id if scope == "outlet_month" else False
            key = (outlet, self._approval_line_principal(line))
            self._stats_by_principal(line, into=grouped.setdefault(key, {}))
        entries = []
        for (outlet, principal), stats in sorted(grouped.items(), key=lambda kv: (kv[0][0] or 0, kv[0][1] or 0)):
            disc = sum(v[0] for v in stats.values())
            gross = sum(v[1] for v in stats.values())
            if gross <= 0:
                continue
            entries.append({
                "outlet_id": str(outlet) if outlet else None,
                "principal": str(principal) if principal else None,
                "discount_amount": round(disc, 2),
                "gross_amount": round(gross, 2),
            })
        return entries

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

    def _approval_discount_amounts(self):
        """(diskon manual Rp, diskon program Rp) pada pesanan saat ini."""
        self.ensure_one()
        manual = program = 0.0
        for line in self.order_line:
            if line.display_type:
                continue
            if line.price_subtotal < 0:
                program += abs(line.price_subtotal)
            else:
                manual += line.price_unit * line.product_uom_qty * (line.discount or 0.0) / 100.0
        return manual, program

    commercial_tactical_components = fields.Json(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any("commercial_tactical_components" in vals for vals in vals_list):
            raise AccessError("Rincian diskon komersial hanya dapat ditetapkan oleh action server.")
        return super().create(vals_list)

    def write(self, vals):
        if "commercial_tactical_components" in vals and not self.env.su:
            raise AccessError("Rincian diskon komersial hanya dapat ditetapkan oleh action server.")
        return super().write(vals)

    def action_apply_tactical_components(self, line_steps, footer_amount=0):
        """Apply native tactical line percentages and a fixed order footer."""
        self.ensure_one()
        self.check_access("write")
        if self.state not in ("draft", "sent"):
            raise UserError("Diskon bertingkat hanya dapat diterapkan pada penawaran.")
        lines = self.order_line.filtered(lambda line: not line.display_type and line.product_id
                                         and line.price_unit > 0 and line.product_uom_qty > 0)
        if not lines or not isinstance(line_steps, dict) or set(line_steps) - {str(line.id) for line in lines}:
            raise UserError("Rincian diskon harus merujuk ke baris penjualan yang berlaku.")

        def value(raw):
            try:
                number = Decimal(str(raw))
                if number.is_finite() and number >= 0:
                    return number
            except InvalidOperation:
                pass
            raise UserError("Nilai diskon tidak valid.")

        def money(amount):
            return Decimal(str(self.currency_id.round(float(amount))))

        promo = Decimal(0)
        promo_basis = self._tactical_promo_basis()
        if self._has_program_discount():
            if len(lines) != 1 or not promo_basis:
                raise UserError("Stack/footer hanya mendukung satu line dan satu promo nominal tetap.")
            promo = money(value(promo_basis[2]))

        gross, net, steps_by_line = {}, {}, {}
        for line in lines:
            key = str(line.id)
            steps = line_steps.get(key, [])
            if not isinstance(steps, list) or len(steps) > 4:
                raise UserError("Maksimal empat tingkat diskon per baris.")
            eligible_steps = [value(step) for step in steps]
            if any(step > 100 for step in eligible_steps):
                raise UserError("Persentase diskon tidak boleh melebihi 100%.")
            steps_by_line[key] = [str(step) for step in eligible_steps]
            gross[key] = money(value(line.price_unit) * value(line.product_uom_qty))
            net[key] = gross[key] - promo
            if net[key] < 0:
                raise UserError("Promo melebihi nilai baris.")
            for step in eligible_steps:
                net[key] = money(net[key] * (1 - step / 100))

        footer = money(value(footer_amount))
        base = sum(net.values())
        if footer > base:
            raise UserError("Diskon footer melebihi nilai setelah diskon baris.")
        quantum = value(self.currency_id.rounding)
        quotas = {key: footer * amount / base if base else Decimal(0) for key, amount in net.items()}
        allocated = {key: (quota / quantum).to_integral_value(rounding=ROUND_DOWN) * quantum
                     for key, quota in quotas.items()}
        remainder = int((footer - sum(allocated.values())) / quantum)
        for key in sorted(net, key=lambda key: (-(quotas[key] - allocated[key]), int(key)))[:remainder]:
            allocated[key] += quantum

        with self.env.cr.savepoint():
            for line in lines:
                key = str(line.id)
                final = net[key] - allocated[key] + promo
                line.discount = float((gross[key] - final) * 100 / gross[key]) if gross[key] else 0
                if money(line.price_subtotal) != final:
                    raise UserError("Alokasi diskon tidak dapat direpresentasikan dengan presisi diskon Odoo.")
            self.sudo().write({"commercial_tactical_components": {
                "steps": steps_by_line, "footer": str(footer), "promo_basis": promo_basis,
                "allocations": {key: str(amount) for key, amount in allocated.items()},
                "basis": {str(line.id): [line.price_unit, line.product_uom_qty, line.discount]
                          for line in lines},
            }})
        return True

    def _tactical_promo_basis(self):
        """Allow native fixed rewards that retain their amount after line/footer deductions."""
        self.ensure_one()
        rewards = self.order_line.filtered(lambda line: getattr(line, "reward_id", False))
        if len(rewards) != 1 or rewards.price_subtotal >= 0:
            return []
        reward = rewards.reward_id
        program = reward.program_id
        if (
            reward.discount_mode != "per_order" or not getattr(program, "principal_id", False)
            or program.currency_id != self.currency_id
            or self.currency_id.compare_amounts(-rewards.price_subtotal, reward.discount) != 0
        ):
            return []
        return [program.id, reward.id, -rewards.price_subtotal]

    def _check_tactical_component_basis(self):
        self.ensure_one()
        if self.commercial_tactical_components:
            basis = {str(line.id): [line.price_unit, line.product_uom_qty, line.discount]
                     for line in self.order_line if not line.display_type and line.product_id
                     and line.price_unit > 0 and line.product_uom_qty > 0}
            promo_basis = self._tactical_promo_basis()
            if (basis != self.commercial_tactical_components["basis"]
                    or promo_basis != self.commercial_tactical_components.get("promo_basis", [])
                    or (self._has_program_discount() and not promo_basis)):
                raise UserError("Basis diskon bertingkat berubah. Terapkan ulang diskon sebelum melanjutkan.")

    def _commercial_approval_fingerprint(self):
        """Bind the approval to the commercial composition as submitted."""
        self.ensure_one()
        self._check_tactical_component_basis()
        lines = [
            (line.id, line.product_id.id, line.product_uom_id.id, line.product_uom_qty,
             line.price_unit, line.discount, sorted(line.tax_ids.ids),
             getattr(getattr(line, "promo_program_id", False), "id", False),
             getattr(getattr(line, "reward_id", False), "id", False))
            for line in self.order_line.sorted("id") if not line.display_type
        ]
        payload = (self.company_id.id, self.partner_id.id, self.user_id.id, self.pricelist_id.id,
                   self.currency_id.id, self.tactical_analytic_account_id.id,
                   self.commercial_tactical_components or {}, lines)
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _approval_snapshot_vals(self):
        """Nilai diskon saat pengajuan dibuat, untuk mendeteksi perubahan setelah disetujui."""
        self.ensure_one()
        manual, program = self._approval_discount_amounts()
        return {
            "snapshot_taken": True,
            "manual_discount_amount": manual,
            "program_discount_amount": program,
        }

    def _has_program_discount(self):
        """True bila pesanan memuat diskon program resmi (baris program atau baris reward negatif)."""
        self.ensure_one()
        return any(
            (not line.display_type)
            and (getattr(line, "promo_program_id", False) or line.price_subtotal < 0)
            for line in self.order_line
        )

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
                        "principal_decided": True,
                        "analytic_account_id": order.tactical_analytic_account_id.id or False,
                        **order._approval_snapshot_vals(),
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
            # Pemantauan promo resmi: tetap approval, hanya hingga Supervisor (keputusan pemilik).
            # Bila pengajuan diskon taktikal masih berjalan, rantainya sudah memuat Supervisor.
            if order._has_program_discount() and not order._open_approval_request("tactical_discount"):
                created |= order._create_promo_usage_request()
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
        is_seed_load = self.env.su and (
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
                # 2. Guard pengajuan diskon (taktikal) dan pemantauan promo resmi: SO tidak boleh
                #    dikonfirmasi saat pengajuannya menunggu atau ditolak.
                order._check_discount_requests_allow_confirm()
        return super().action_confirm()

    def _approval_effective_request(self, category_code):
        """Pengajuan yang berlaku untuk kategori: terbaru yang tidak dibatalkan (riwayat lama tetap tersimpan)."""
        self.ensure_one()
        return self.env["fmcg.approval.request"].sudo().search([
            ("res_model", "=", "sale.order"),
            ("res_id", "=", self.id),
            ("category_id.code", "=", category_code),
            ("state", "!=", "cancelled"),
        ], order="id desc", limit=1)

    def _check_discount_requests_allow_confirm(self):
        """Guard konfirmasi berdasarkan pengajuan yang berlaku (terbaru, tidak dibatalkan).

        - Promo resmi (wajib): tanpa pengajuan, menunggu, atau ditolak -> diblokir; hanya disetujui yang lolos.
          Pesanan campuran dengan pengajuan taktikal cukup satu rantai taktikal (tanpa pengajuan promo kedua).
        - Diskon taktikal di atas zona bebas perlu pengajuan yang berlaku dan sudah disetujui.
        Penolakan lama tidak memblokir bila pengajuan pengganti yang berlaku sudah disetujui.
        """
        self.ensure_one()
        self._check_tactical_component_basis()
        tactical = self._approval_effective_request("tactical_discount")
        if self.has_tactical_discount and not tactical:
            category = self.env.ref("id_approval.cat_tactical_discount")
            if not self._approval_discount_decision(category)["within_free_zone"]:
                raise UserError("Ajukan persetujuan diskon taktikal sebelum konfirmasi.")
        self._check_commercial_approval_revision(tactical)
        manual_now, program_now = self._approval_discount_amounts()
        eps = 0.5  # toleransi pembulatan (Rp)
        # Pengajuan yang sudah disetujui hanya berlaku untuk isi pesanan saat diajukan.
        if tactical and tactical.snapshot_taken and manual_now > tactical.manual_discount_amount + eps:
            raise UserError(
                f"Pesanan {self.name} tidak dapat dikonfirmasi: diskon manual bertambah setelah pengajuan "
                f"{tactical.name}. Ajukan ulang persetujuan diskon."
            )
        # Pesanan campuran (promo resmi + diskon manual) mengikuti satu rantai taktikal yang sudah
        # memuat Supervisor, selama rantai itu sudah mencakup promo yang ada sekarang. Promo yang
        # ditambahkan setelah pengajuan, atau pengajuan zona bebas tanpa approver, tetap butuh
        # pemantauan promo Supervisor sendiri.
        tactical_covers_program = bool(
            self.has_tactical_discount and tactical.line_ids
            and (not tactical.snapshot_taken or program_now <= tactical.program_discount_amount + eps)
        )
        if self._has_program_discount() and not tactical_covers_program:
            req = self._approval_effective_request("promo_program_usage")
            if not req:
                raise UserError(
                    f"Pesanan {self.name} memakai promo resmi dan belum diajukan untuk pemantauan Supervisor. "
                    f"Gunakan tombol 'Ajukan Pemantauan Promo' sebelum konfirmasi."
                )
            self._check_commercial_approval_revision(req)
            if req.snapshot_taken and program_now > req.program_discount_amount + eps:
                raise UserError(
                    f"Pesanan {self.name} tidak dapat dikonfirmasi: nilai promo bertambah setelah pengajuan "
                    f"{req.name}. Ajukan ulang pemantauan promo."
                )
            self._raise_unless_approved(req, "pemantauan promo resmi")
        if tactical:
            self._raise_unless_approved(tactical, "diskon taktikal")

    def _check_commercial_approval_revision(self, request):
        if (request and request.commercial_fingerprint
                and request.commercial_fingerprint != self._commercial_approval_fingerprint()):
            raise UserError("Komposisi komersial berubah setelah pengajuan. Ajukan ulang persetujuan.")

    def _raise_unless_approved(self, req, label):
        if req.state == "approved":
            return
        if req.state == "rejected":
            raise UserError(
                f"Pesanan {self.name} tidak dapat dikonfirmasi: pengajuan {label} {req.name} DITOLAK. "
                f"Revisi pesanan dan ajukan ulang."
            )
        raise UserError(
            f"Pesanan {self.name} tidak dapat dikonfirmasi: pengajuan {label} {req.name} "
            f"masih menunggu persetujuan."
        )

    def _create_promo_usage_request(self):
        """Membuat pengajuan pemantauan promo resmi (hingga Supervisor). Idempoten untuk yang berjalan."""
        self.ensure_one()
        if self._open_approval_request("promo_program_usage"):
            return self.env["fmcg.approval.request"]
        category = self.env["fmcg.approval.category"].sudo().search(
            [("code", "=", "promo_program_usage")], limit=1)
        if not category:
            return self.env["fmcg.approval.request"]
        req = self.env["fmcg.approval.request"].sudo().create({
            "category_id": category.id,
            "res_model": "sale.order",
            "res_id": self.id,
            "reference_document": f"{self.name} - {self.partner_id.name}",
            "amount": self.amount_total,
            "discount_percent": self._approval_cumulative_discount_pct(category.cumulative_scope),
            "reason": f"Pemantauan penggunaan promo resmi untuk pesanan {self.name}",
            **self._approval_snapshot_vals(),
        })
        req.action_submit()
        self.message_post(
            body=f"Pemantauan promo resmi <b>{req.name}</b> diajukan ke Supervisor.",
            subtype_xmlid="mail.mt_note",
        )
        return req

    def action_request_promo_usage_approval(self):
        """Tombol: ajukan pemantauan promo resmi (hingga Supervisor)."""
        self.ensure_one()
        self.check_access("write")
        if not self._has_program_discount():
            raise UserError("Pesanan ini tidak memuat diskon program resmi.")
        req = self._create_promo_usage_request()
        if not req:
            raise UserError("Sudah ada pengajuan pemantauan promo yang berjalan atau kategori belum dikonfigurasi.")
        return {
            "type": "ir.actions.act_window",
            "res_model": "fmcg.approval.request",
            "res_id": req.id,
            "view_mode": "form",
            "target": "current",
        }

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
            elif request.category_code == "promo_program_usage":
                if status == "approved":
                    order.message_post(
                        body="Penggunaan promo resmi telah DISETUJUI Supervisor.", subtype_xmlid="mail.mt_note")
                elif status == "rejected":
                    order.message_post(
                        body="Penggunaan promo resmi DITOLAK Supervisor.", subtype_xmlid="mail.mt_note")
            elif request.category_code == "tactical_discount":
                if status == "approved":
                    if hasattr(order, "discount_approval_state"):
                        order.write({"discount_approval_state": "approved"})
                    order.message_post(body="Diskon taktikal telah DISETUJUI.", subtype_xmlid="mail.mt_note")
                elif status == "rejected":
                    if hasattr(order, "discount_approval_state"):
                        order.write({"discount_approval_state": "rejected"})
                    order.message_post(body="Diskon taktikal DITOLAK.", subtype_xmlid="mail.mt_note")
