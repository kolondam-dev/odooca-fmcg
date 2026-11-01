import json
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MobileCommand(models.Model):
    _name = "id.mobile.command"
    _description = "Mobile Ingestion Command Log"
    _order = "id desc"
    _rec_name = "client_uuid"

    client_uuid = fields.Char(string="Client UUID", required=True, index=True)
    command_type = fields.Char(string="Command Type", required=True, index=True)
    user_id = fields.Many2one(
        "res.users", string="Salesperson / Driver", required=True, index=True, ondelete="restrict"
    )
    company_id = fields.Many2one("res.company", string="Company", required=True, index=True, ondelete="restrict")
    occurred_at = fields.Datetime(string="Occurred At")
    payload_json = fields.Text(string="Payload JSON", required=True)
    status = fields.Selection([
        ("accepted", "Accepted"),
        ("needs_approval", "Needs Approval"),
        ("rejected", "Rejected"),
    ], string="Result Status", required=True, default="accepted")
    reference = fields.Char(string="Document Reference")
    message = fields.Char(string="Status Message")
    sale_order_ids = fields.Many2many("sale.order", string="Generated Sales Orders")

    _unique_client_uuid = models.Constraint(
        "UNIQUE(user_id, client_uuid)",
        "Command client UUID must be unique per user for strict idempotency.",
    )

    @api.model
    def process_command(self, command_data):
        """Dispatches an incoming PWA command idempotently."""
        user = self.env.user
        company = user.company_id
        client_uuid = command_data.get("client_uuid")
        cmd_type = command_data.get("type")
        payload = command_data.get("payload") or {}

        if not client_uuid or not cmd_type:
            raise UserError(_("Invalid command format: client_uuid and type are required."))

        # 1. Idempotency Check
        existing = self.sudo().search([
            ("user_id", "=", user.id),
            ("client_uuid", "=", client_uuid),
        ], limit=1)
        if existing:
            return {
                "client_uuid": existing.client_uuid,
                "status": existing.status,
                "message": existing.message or "Command already processed.",
                "reference": existing.reference or "",
            }

        # 2. Dispatch by command type
        status = "accepted"
        message = "Perintah berhasil diproses."
        reference = f"{cmd_type.upper()}-{client_uuid[:8]}"
        created_so_ids = []

        if cmd_type == "sales.order.submit":
            created_so_ids, status, message, reference = self._handle_sales_order_submit(payload, client_uuid)
        elif cmd_type in ("sales.visit.check_in", "sales.visit.check_out"):
            status, message, reference = self._handle_visit(cmd_type, payload, client_uuid)
        elif cmd_type in ("delivery.pod.submit", "delivery.trip.close", "delivery.proof.submit"):
            status, message, reference = self._handle_delivery(cmd_type, payload, client_uuid)
        elif cmd_type == "collection.receipt.submit":
            status, message, reference = self._handle_collection(payload, client_uuid)
        elif cmd_type in ("hris.attendance.capture", "hris.leave.request"):
            status, message, reference = self._handle_hris(cmd_type, payload, client_uuid)
        elif cmd_type in ("field_expense.request", "field_expense.realization.submit"):
            status, message, reference = self._handle_expense(cmd_type, payload, client_uuid)
        else:
            reference = f"GEN-{client_uuid[:8]}"

        # 3. Store record for idempotency
        record = self.sudo().create({
            "client_uuid": client_uuid,
            "command_type": cmd_type,
            "user_id": user.id,
            "company_id": company.id,
            "occurred_at": fields.Datetime.now(),
            "payload_json": json.dumps(command_data),
            "status": status,
            "reference": reference,
            "message": message,
            "sale_order_ids": [(6, 0, created_so_ids)] if created_so_ids else False,
        })

        return {
            "client_uuid": record.client_uuid,
            "status": record.status,
            "message": record.message,
            "reference": record.reference,
        }

    def _handle_sales_order_submit(self, payload, client_uuid):
        user = self.env.user
        company = user.company_id
        outlet_id = int(payload.get("outlet_id", 0))
        partner = self.env["res.partner"].browse(outlet_id)
        if not partner.exists():
            return [], "rejected", "Outlet tidak ditemukan.", ""

        # Dapatkan workday assignment aktif untuk pricelist & warehouse
        Workday = self.env["id.mobile.workday"]
        assignment = Workday.search([
            ("user_id", "=", user.id),
            ("company_id", "=", company.id),
            ("active", "=", True),
        ], limit=1, order="business_date desc")

        pricelist = assignment.pricelist_id if assignment else partner.property_product_pricelist
        warehouse = (
            assignment.warehouse_id
            if assignment
            else self.env["stock.warehouse"].sudo().search([("company_id", "=", company.id)], limit=1)
        )

        raw_lines = payload.get("lines", [])
        if not raw_lines:
            return [], "rejected", "Order kosong tanpa produk.", ""

        # Pengelompokan baris per Principal FMCG (Aturan Single-Principal SO)
        lines_by_principal = {}
        Product = self.env["product.product"].sudo()
        for line in raw_lines:
            pid = int(line.get("product_id"))
            product = Product.browse(pid)
            if not product.exists():
                continue
            principal_id = product.principal_id.id if product.principal_id else 0
            lines_by_principal.setdefault(principal_id, []).append((product, line))

        created_orders = []
        discount_req = payload.get("discount_request") or {}
        discount_pct = float(discount_req.get("percent", 0.0))
        discount_reason = discount_req.get("reason", "")
        customer_po = payload.get("customer_po_number") or payload.get("note") or ""

        needs_approval = False
        SaleOrder = self.env["sale.order"].sudo()

        for principal_id, items in lines_by_principal.items():
            order_lines = []
            for product, item in items:
                qty_val = float(item.get("qty", 1))
                uom_tier = item.get("uom", "carton")
                # Konversi satuan pcs/pack/carton
                qty_in_unit = qty_val
                if uom_tier == "carton" and product.carton_qty:
                    qty_in_unit = qty_val * product.carton_qty
                elif uom_tier == "pack" and product.inner_qty:
                    qty_in_unit = qty_val * product.inner_qty

                # Line discount jika ada
                line_disc = float(item.get("discount", 0.0)) or discount_pct
                order_lines.append((0, 0, {
                    "product_id": product.id,
                    "product_uom_qty": qty_in_unit,
                    "product_uom": product.uom_id.id,
                    "discount": line_disc,
                }))

            order_vals = {
                "partner_id": partner.id,
                "user_id": user.id,
                "company_id": company.id,
                "pricelist_id": pricelist.id if pricelist else False,
                "warehouse_id": warehouse.id if warehouse else False,
                "client_order_ref": customer_po[:64] if customer_po else False,
                "origin": f"PWA Mobile Order {client_uuid[:8]}",
                "order_line": order_lines,
            }
            if discount_pct > 0:
                order_vals["discount_approval_note"] = discount_reason

            so = SaleOrder.create(order_vals)
            created_orders.append(so)

            if getattr(so, "credit_limit_exceeded", False) or getattr(so, "has_below_hpp", False) or discount_pct > 0:
                needs_approval = True

        so_names = ", ".join(so.name for so in created_orders)
        if needs_approval:
            msg = f"Pesanan {so_names} dibuat, menunggu approval kredit/diskon."
            return [so.id for so in created_orders], "needs_approval", msg, so_names
        return [so.id for so in created_orders], "accepted", f"Pesanan {so_names} berhasil diajukan.", so_names

    def _handle_visit(self, cmd_type, payload, client_uuid):
        outlet_id = payload.get("outlet_id")
        action = "Check-in" if "check_in" in cmd_type else "Check-out"
        ref = f"VISIT-{client_uuid[:8]}"
        return "accepted", f"{action} kunjungan outlet {outlet_id} tercatat.", ref

    def _handle_delivery(self, cmd_type, payload, client_uuid):
        ref = f"POD-{client_uuid[:8]}"
        return "accepted", "Bukti serah terima pengiriman berhasil disimpan.", ref

    def _handle_collection(self, payload, client_uuid):
        ref = f"PAY-{client_uuid[:8]}"
        amount = payload.get("amount", "0")
        method = payload.get("method", "cash")
        return "accepted", f"Penerimaan kas/transfer Rp {amount} ({method}) tercatat.", ref

    def _handle_hris(self, cmd_type, payload, client_uuid):
        ref = f"HR-{client_uuid[:8]}"
        return "accepted", "Absensi/kehadiran kerja berhasil dicatat.", ref

    def _handle_expense(self, cmd_type, payload, client_uuid):
        ref = f"EXP-{client_uuid[:8]}"
        return "needs_approval", "Pengajuan biaya lapangan dikirim ke supervisor.", ref
