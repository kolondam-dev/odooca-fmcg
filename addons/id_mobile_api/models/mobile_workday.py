import hashlib
import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.addons.id_base.models.business_day import business_date as _business_date


def business_date():
    # Satu definisi hari bisnis WITA bersama id_base (dipakai juga validasi kredit server).
    return _business_date()


class MobileReadConflict(UserError):
    pass


class MobileWorkday(models.Model):
    _name = "id.mobile.workday"
    _description = "Mobile Read Assignment"
    _rec_name = "business_date"
    _check_company_auto = True
    _order = "business_date desc, id"

    active = fields.Boolean(default=True)
    business_date = fields.Date(required=True, index=True)
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    warehouse_id = fields.Many2one("stock.warehouse", required=True, check_company=True)
    pricelist_id = fields.Many2one("product.pricelist", required=True, check_company=True)
    outlet_ids = fields.Many2many("res.partner", string="Scheduled Outlets", check_company=True)
    product_ids = fields.Many2many("product.product", string="Allowed Products", check_company=True)
    outlet_radius = fields.Integer(string="Outlet Geofence Radius (m)", required=True, default=100)
    office_id = fields.Many2one("id.mobile.office", string="Office Location", check_company=True)

    _unique_day = models.Constraint(
        "UNIQUE(user_id, company_id, business_date)",
        "Only one mobile read assignment is allowed per user, company and day.",
    )

    @api.constrains("user_id", "company_id", "warehouse_id", "pricelist_id", "outlet_radius",
                    "product_ids", "outlet_ids")
    def _check_mobile_scope(self):
        for record in self:
            if record.user_id.share or record.company_id not in record.user_id.company_ids:
                raise ValidationError(_("Assignment requires an internal user in the assigned company."))
            if record.warehouse_id.company_id != record.company_id:
                raise ValidationError(_("Warehouse must belong to the assigned company."))
            if record.pricelist_id.company_id and record.pricelist_id.company_id != record.company_id:
                raise ValidationError(_("Pricelist must belong to the assigned company or be shared."))
            if record.pricelist_id.currency_id.name != "IDR" or record.company_id.currency_id.name != "IDR":
                raise ValidationError(_("The mobile read contract currently requires IDR."))
            if not 5 <= record.outlet_radius <= 150:
                raise ValidationError(_("Outlet radius must be between 5 and 150 metres."))
            if len(record.product_ids) > 1000 or len(record.outlet_ids) > 1000:
                raise ValidationError(_("A mobile assignment may contain at most 1000 products and 1000 outlets."))

    @api.model
    def _current_assignment(self):
        user = self.env.user
        if not user.active or user.share or not user.has_group("id_mobile_api.group_mobile_sales"):
            raise AccessError(_("Mobile read access is not enabled."))
        # No company/user/warehouse/pricelist selector is accepted from HTTP.
        company = user.company_id
        if company not in user.company_ids:
            raise AccessError(_("Company access is not available."))
        day = business_date()
        assignment = self.with_company(company).with_context(active_test=False).search([
            ("user_id", "=", user.id), ("company_id", "=", company.id),
            ("business_date", "=", day),
        ], limit=2)
        if len(assignment) == 1 and not assignment.active:
            raise AccessError(_("Today's assignment is inactive; contact your supervisor."))
        if not assignment:
            latest = self.with_company(company).search([
                ("user_id", "=", user.id), ("company_id", "=", company.id),
                ("business_date", "<", day),
                ("active", "=", True),
            ], order="business_date desc, id desc", limit=1)
            if (
                latest
                and latest.product_ids
                and latest.outlet_ids
                and latest.warehouse_id.active
                and latest.pricelist_id.active
            ):
                assignment = self.sudo().create({
                    "user_id": user.id,
                    "company_id": company.id,
                    "business_date": day,
                    "warehouse_id": latest.warehouse_id.id,
                    "pricelist_id": latest.pricelist_id.id,
                    "office_id": latest.office_id.id if latest.office_id else False,
                    "outlet_radius": latest.outlet_radius,
                    "product_ids": [(6, 0, latest.product_ids.ids)],
                    "outlet_ids": [(6, 0, latest.outlet_ids.ids)],
                    "active": True,
                })
        if len(assignment) != 1:
            raise AccessError(_("An active assignment for today is required."))
        assignment._check_mobile_scope()
        if not assignment.product_ids or not assignment.outlet_ids:
            raise UserError(_("Assign at least one product and scheduled outlet before enabling mobile reads."))
        if not assignment.warehouse_id.active or not assignment.pricelist_id.active:
            raise AccessError(_("Assigned warehouse or pricelist is unavailable."))
        return assignment, day

    def _assert_day(self, day):
        if business_date() != day:
            raise MobileReadConflict(_("The business day changed; bootstrap again."))

    @api.model
    def _bootstrap_payload(self):
        assignment, day = self._current_assignment()
        user = self.env.user
        is_driver = (
            "driver" in user.login.lower()
            or bool(user.partner_id.function and "driver" in user.partner_id.function.lower())
        )
        roles = ["delivery"] if is_driver else ["sales"]
        result = {
            "id": str(user.id), "companyId": str(assignment.company_id.id),
            "companyName": assignment.company_id.name,
            "name": user.name, "title": user.partner_id.function or "",
            "roles": roles, "businessDate": day.isoformat(),
        }
        if user.has_group("id_mobile_api.group_mobile_evidence"):
            result["capabilities"] = ["evidence.capture"]
        if "delivery" in roles:
            result.setdefault("capabilities", []).append("collection.capture")
        assignment._assert_day(day)
        return result

    def _outlet_commercial(self, partner, company):
        """Assigned outlet only; native model/field ACLs remain authoritative."""
        visible = partner.fields_get(["property_payment_term_id", "credit_limit", "pic_name", "credit_mode"])
        result = {"currency": company.currency_id.name, "max_order": None,
                  "previous_visit_total": None, "top_sku": None,
                  "payment_terms": None, "credit_limit": None, "contact": None,
                  "credit_mode": None}
        if "credit_mode" in visible:
            # BE-19: kebijakan kredit EFEKTIF seperti server (`sale.order._compute_credit_limit_exceeded`
            # memakai commercial partner/parent); jarang berubah → ikut digest, jadi perubahan pada parent
            # ikut mengubah versi outlet anak. Parent yang tidak boleh dibaca → tidak diketahui (None).
            parent = partner.commercial_partner_id or partner
            try:
                result["credit_mode"] = parent.credit_mode or "limit"
            except AccessError:
                result["credit_mode"] = None
        if "pic_name" in visible:
            result["contact"] = partner.pic_name or None
        if "property_payment_term_id" in visible:
            result["payment_terms"] = partner.with_company(company).property_payment_term_id.name or None
        if "credit_limit" in visible:
            limit = partner.with_company(company).credit_limit
            result["credit_limit"] = limit if limit > 0 else None
        try:
            orders = self.env["sale.order"].with_company(company)
            domain = [("company_id", "=", company.id), ("partner_id", "=", partner.id),
                      ("state", "in", ["sale", "done"]), ("currency_id", "=", company.currency_id.id)]
            largest = orders.search(domain, order="amount_untaxed desc, id desc", limit=1)
            if largest:
                result["max_order"] = largest.amount_untaxed
            lines = self.env["sale.order.line"].with_company(company)._read_group(
                [("order_id.company_id", "=", company.id), ("order_id.partner_id", "=", partner.id),
                 ("order_id.state", "in", ["sale", "done"]), ("order_id.currency_id", "=", company.currency_id.id),
                 ("display_type", "=", False)], ["product_id"], ["price_subtotal:sum"])
            if lines:
                product, _amount = max(lines, key=lambda row: row[1])
                result["top_sku"] = product.default_code or product.name if product else None
        except AccessError:
            # A mobile-read account is not automatically a sales-history account.
            result["max_order"] = result["top_sku"] = None
        return result

    @api.model
    def _outlet_overdue(self, partners, company, day):
        """BE-19: faktur jatuh tempo per outlet ditugaskan (fakta baca-saja untuk pemblokiran mode strict).

        Kriteria sama dengan `sale.order._compute_credit_limit_exceeded` (faktur pelanggan terposting,
        belum lunas, `invoice_date_due` < hari bisnis). Agregat saja (jumlah, sisa tagihan, jatuh tempo
        tertua) dibaca dengan sudo karena akun mobile tidak otomatis boleh membaca faktur; cakupan dibatasi
        pada outlet yang sudah lolos `check_access` dan perusahaan sesi. Perimeter kredit = COMMERCIAL
        PARTNER (parent) dalam perusahaan sesi, sama dengan server: faktur outlet saudara yang tidak
        ditugaskan tetapi satu parent ikut terhitung; kunci hasil tetap hanya outlet yang ditugaskan.
        Hanya outlet yang punya tunggakan dimuat (blok kosong = tidak ada tunggakan)."""
        commercial = {p.id: (p.commercial_partner_id or p).id for p in partners}
        if not commercial:
            return {}
        rows = self.env["account.move"].sudo()._read_group(
            [("company_id", "=", company.id), ("commercial_partner_id", "in", list(set(commercial.values()))),
             ("move_type", "=", "out_invoice"), ("state", "=", "posted"),
             ("payment_state", "not in", ["paid", "in_payment", "reversed"]),
             ("invoice_date_due", "<", day)],
            ["commercial_partner_id"],
            ["__count", "amount_residual_signed:sum", "invoice_date_due:min"])
        by_partner = {partner.id: (count, amount, oldest) for partner, count, amount, oldest in rows}
        result = {}
        for outlet_id, partner_id in commercial.items():
            if partner_id in by_partner:
                count, amount, oldest = by_partner[partner_id]
                result[str(outlet_id)] = {
                    "overdue_count": count, "overdue_total": round(amount, 2),
                    "oldest_due": oldest.isoformat() if oldest else None,
                }
        return result

    # Batas faktur terbuka per outlet pada snapshot (urut jatuh tempo tertua); sisanya hanya masuk total.
    RECEIVABLE_INVOICE_CAP = 50

    @api.model
    def _outlet_receivables(self, partners, company, day):
        """BE-7: piutang berjalan dan daftar faktur terbuka per outlet ditugaskan (baca-saja).

        Perimeter dan kriteria sama dengan `_outlet_overdue` (BE-19): faktur pelanggan terposting, belum
        lunas, perusahaan sesi, commercial partner (parent) outlet; faktur outlet saudara ikut dan
        ditandai lewat `partner`. Total dihitung dari SEMUA faktur terbuka; daftar dipotong
        `RECEIVABLE_INVOICE_CAP` (jatuh tempo tertua dulu) dengan `truncated`. Nominal dalam mata uang
        perusahaan (`*_signed`). Dibaca sudo dan hanya field ringkas (akun mobile tidak otomatis boleh
        membaca faktur). Hanya outlet yang punya piutang dimuat ({} = server membaca, tidak ada piutang)."""
        commercial = {p.id: (p.commercial_partner_id or p).id for p in partners}
        if not commercial:
            return {}
        moves = self.env["account.move"].sudo().search([
            ("company_id", "=", company.id), ("commercial_partner_id", "in", list(set(commercial.values()))),
            ("move_type", "=", "out_invoice"), ("state", "=", "posted"),
            ("payment_state", "not in", ["paid", "in_payment", "reversed"]),
        ], order="invoice_date_due asc, id asc")
        by_commercial = {}
        for move in moves:
            by_commercial.setdefault(move.commercial_partner_id.id, []).append(move)
        result = {}
        for outlet_id, partner_id in commercial.items():
            rows = by_commercial.get(partner_id)
            if not rows:
                continue
            overdue = [m for m in rows if m.invoice_date_due and m.invoice_date_due < day]
            result[str(outlet_id)] = {
                "outstanding_total": round(sum(m.amount_residual_signed for m in rows), 2),
                "open_count": len(rows),
                "overdue_count": len(overdue),
                "overdue_total": round(sum(m.amount_residual_signed for m in overdue), 2),
                "oldest_due": next((m.invoice_date_due.isoformat() for m in rows if m.invoice_date_due), None),
                "truncated": len(rows) > self.RECEIVABLE_INVOICE_CAP,
                "invoices": [{
                    "reference": m.name,
                    "partner": m.partner_id.display_name,
                    "invoice_date": m.invoice_date.isoformat() if m.invoice_date else None,
                    "due_date": m.invoice_date_due.isoformat() if m.invoice_date_due else None,
                    "total": round(m.amount_total_signed, 2),
                    "balance": round(m.amount_residual_signed, 2),
                    "overdue": bool(m.invoice_date_due and m.invoice_date_due < day),
                } for m in rows[:self.RECEIVABLE_INVOICE_CAP]],
            }
        return result

    @api.model
    def _snapshot_payload(self, include_volatile=True):
        assignment, day = self._current_assignment()
        assignment = assignment.with_company(assignment.company_id)
        company = assignment.company_id
        products = assignment.product_ids.sorted("id")
        partners = assignment.outlet_ids.sorted("id")
        # Ordinary ORM ACL/record rules remain effective for these business records.
        products.check_access("read")
        partners.check_access("read")
        assignment.pricelist_id.check_access("read")
        location = assignment.warehouse_id.lot_stock_id
        if location.company_id != company or location.usage != "internal":
            raise UserError(_("A company-owned primary stock location is required."))
        # Native read ACL and quant record rules remain in force. Aggregate only
        # assigned products at the exact company-owned primary stock location,
        # excluding consignment. No lots, owners, costs or quant rows are returned.
        quantities = self.env["stock.quant"]._read_group([
            ("company_id", "=", company.id), ("location_id", "=", location.id),
            ("product_id", "in", products.ids), ("owner_id", "=", False),
        ], ["product_id"], ["quantity:sum", "reserved_quantity:sum"])
        if any(not math.isfinite(quantity) or not math.isfinite(reserved) or reserved < 0
               for _, quantity, reserved in quantities):
            raise UserError(_("Stock availability is not valid for the assigned scope."))
        available = {product.id: max(0.0, quantity - reserved) for product, quantity, reserved in quantities}
        unit = self.env.ref("uom.product_uom_unit")
        catalog = []
        codes = set()
        for product in products:
            carton, pack = product.carton_qty, product.inner_qty
            if (not product.active or not product.sale_ok
                    or (product.company_id and product.company_id != company)
                    or product.uom_id != unit or carton <= 0 or pack <= 0 or carton > 1000000
                    or carton < pack or carton % pack or not product.principal_id or not product.default_code):
                raise UserError(_("Assigned products require valid pcs packaging, SKU code and principal."))
            code = product.default_code.strip()
            if not code or code in codes:
                raise UserError(_("Assigned SKU codes must be nonempty and unique."))
            codes.add(code)
            product.principal_id.check_access("read")
            price = assignment.pricelist_id._get_product_price(product, carton, uom=unit, date=day)
            taxes = product.sudo().taxes_id.filtered(lambda tax: tax.company_id == company)
            price = taxes.compute_all(
                price * carton, currency=assignment.pricelist_id.currency_id,
                quantity=1, product=product,
            )["total_excluded"]
            if not math.isfinite(price) or price < 0:
                raise UserError(_("Assigned prices must be finite and nonnegative."))
            catalog.append({
                "id": str(product.id), "sku_code": code, "name": product.name,
                "brand": product.brand_id.name or "", "principal": str(product.principal_id.id),
                "principal_name": product.principal_id.name,
                "unit": f"karton {carton} pcs / pack {pack} pcs",
                "packaging": {"carton": carton, "pack": pack, "pcs": 1},
                "price": price, "stock": available.get(product.id, 0.0) / carton,
                "price_basis": "carton", "stock_basis": "carton",
            })
        outlets = []
        for partner in partners:
            latitude, longitude = partner.partner_latitude, partner.partner_longitude
            if (not partner.active or not partner.name or (partner.company_id and partner.company_id != company)
                    or not math.isfinite(latitude) or not math.isfinite(longitude)
                    or not -90 <= latitude <= 90 or not -180 <= longitude <= 180
                    or (latitude == 0 and longitude == 0)):
                raise UserError(_("Scheduled outlets require valid company scope and coordinates."))
            outlets.append({
                "id": str(partner.id), "name": partner.name, "channel": partner.channel_id.name or "",
                "address": ", ".join(filter(None, [partner.street, partner.street2, partner.city])),
                "distance": "", "time": "", "latitude": latitude, "longitude": longitude,
                "radius": assignment.outlet_radius,
                "image_url": f"/api/v1/outlets/{partner.id}/image" if partner.image_128 else None,
                "commercial": self._outlet_commercial(partner, company),
            })
        result = {
            "catalog_version": 2,
            "scope": {"company_id": str(company.id), "user_id": str(self.env.uid),
                      "warehouse_id": str(assignment.warehouse_id.id), "business_date": day.isoformat()},
            "products": catalog, "outlets": outlets, "deliveries": [],
            "warehouseName": assignment.warehouse_id.name,
        }
        if assignment.office_id:
            result["office"] = assignment.office_id._map_payload()
        digest = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        result.update(
            version=f"odoo-read-v1:{digest}",
            updatedAt=datetime.now(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
        )
        # BE-18: id_approval opsional (tanpa dependensi manifest); tier dipakai PWA hanya untuk pratinjau.
        # Sengaja DI LUAR digest versi: pemakaian berubah setiap order dan konfigurasi bisa berubah kapan
        # saja; bila ikut digest, command offline berikutnya ditolak 'Stale catalog snapshot version'.
        category_model = self.env.registry.get("fmcg.approval.category")
        if include_volatile and category_model is not None \
                and hasattr(category_model, "_mobile_snapshot_payload"):
            tiers = self.env["fmcg.approval.category"]._mobile_snapshot_payload(
                principal_ids=products.mapped("principal_id").ids,
                partner_ids=partners.ids, user=self.env.user, company=company,
                anchor=datetime.now(ZoneInfo("UTC")).replace(tzinfo=None),
            )
            if tiers:
                result["approval_tiers"] = {"discount": tiers}
        # BE-19: tunggakan faktur outlet berubah setiap pembayaran → di luar digest, sama alasannya.
        if include_volatile:
            result["outlet_credit"] = self._outlet_overdue(partners, company, day)
            # BE-7: piutang berjalan + faktur terbuka (juga berubah tiap pembayaran → di luar digest).
            result["outlet_receivables"] = self._outlet_receivables(partners, company, day)
        assignment._assert_day(day)
        return result
