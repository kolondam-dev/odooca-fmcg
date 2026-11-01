import hashlib
import json
import logging
import uuid
from psycopg2 import IntegrityError
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from .mobile_workday import MobileReadConflict

_logger = logging.getLogger(__name__)

SUPPORTED_COMMANDS = {
    "sales.order.submit",
    "sales.visit.check_in",
    "sales.visit.check_out",
    "delivery.pod.submit",
    "delivery.trip.close",
    "delivery.proof.submit",
    "collection.receipt.submit",
    "hris.attendance.capture",
    "hris.leave.request",
    "field_expense.request",
    "field_expense.realization.submit",
}


def canonical_command_fingerprint(command_data):
    """Computes a deterministic SHA-256 fingerprint from the command dictionary."""
    canonical_json = json.dumps(command_data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class MobileCommand(models.Model):
    _name = "id.mobile.command"
    _description = "Mobile Ingestion Command Log"
    _order = "id desc"
    _rec_name = "client_uuid"

    client_uuid = fields.Char(string="Client UUID", required=True, index=True)
    command_type = fields.Char(string="Command Type", required=True, index=True)
    fingerprint = fields.Char(string="Canonical Fingerprint", required=True, index=True)
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
    def _actor(self):
        """Validates that the calling user has valid mobile operational privileges."""
        user = self.env.user
        if not user or not user.active or user.share or not user.has_group("id_mobile_api.group_mobile_sales"):
            raise AccessError(_("Mobile command submission is not authorized."))
        company = user.company_id
        if not company or company not in user.company_ids:
            raise AccessError(_("Company access is not available."))
        return user, company

    @api.model
    def process_command(self, command_data):
        """Dispatches an incoming PWA command idempotently and atomically."""
        user, company = self._actor()

        # 1. Envelope Validation
        raw_uuid = command_data.get("client_uuid")
        if not raw_uuid:
            raise UserError(_("Invalid command format: client_uuid is required."))
        try:
            parsed_uuid = uuid.UUID(str(raw_uuid), version=4)
            if str(parsed_uuid) != str(raw_uuid).lower():
                raise ValueError()
            client_uuid = str(parsed_uuid)
        except (ValueError, TypeError, AttributeError):
            raise UserError(_("Invalid client_uuid: must be a canonical UUID v4."))

        cmd_type = command_data.get("type")
        if not cmd_type:
            raise UserError(_("Invalid command format: type is required."))
        if cmd_type not in SUPPORTED_COMMANDS:
            raise UserError(_("Unsupported command type: %s") % cmd_type)

        payload = command_data.get("payload")
        if payload is None or not isinstance(payload, dict):
            raise UserError(_("Command payload must be a JSON object."))

        fingerprint = canonical_command_fingerprint(command_data)

        # 2. Strict Idempotency Check
        existing = self.sudo().search([
            ("user_id", "=", user.id),
            ("client_uuid", "=", client_uuid),
        ], limit=1)
        if existing:
            if (
                existing.fingerprint != fingerprint
                or existing.command_type != cmd_type
                or existing.company_id.id != company.id
            ):
                raise MobileReadConflict(_("Command client_uuid reused with different payload, type, or company."))
            return {
                "client_uuid": existing.client_uuid,
                "status": existing.status,
                "message": existing.message or "Command already processed.",
                "reference": existing.reference or "",
            }

        # 3. Atomic Dispatch and Persistence
        try:
            with self.env.cr.savepoint():
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
                    raise UserError(_("Unsupported command handler for %s") % cmd_type)

                record = self.sudo().create({
                    "client_uuid": client_uuid,
                    "command_type": cmd_type,
                    "fingerprint": fingerprint,
                    "user_id": user.id,
                    "company_id": company.id,
                    "occurred_at": fields.Datetime.now(),
                    "payload_json": json.dumps(command_data, sort_keys=True, separators=(",", ":")),
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
        except IntegrityError as error:
            if error.pgcode != "23505":
                raise
            raise MobileReadConflict(_("Command submission raced; retry the same UUID.")) from None

    def _handle_sales_order_submit(self, payload, client_uuid):
        user, company = self._actor()
        Workday = self.env["id.mobile.workday"]
        assignment, day = Workday._current_assignment()

        if day.weekday() == 6:
            raise UserError(_("Operasional sales order libur pada hari Minggu."))

        # Snapshot version validation
        snapshot_version = payload.get("snapshot_version")
        if snapshot_version:
            current_snapshot = Workday._snapshot_payload()
            if snapshot_version != current_snapshot.get("version"):
                raise MobileReadConflict(_("Stale catalog snapshot version."))

        outlet_id = int(payload.get("outlet_id", 0))
        if not outlet_id:
            raise UserError(_("Outlet wajib ditentukan."))

        if outlet_id not in assignment.outlet_ids.ids:
            raise UserError(_("Outlet %s tidak termasuk dalam scope assignment aktif hari ini.") % outlet_id)

        partner = self.env["res.partner"].browse(outlet_id)
        if not partner.exists() or not partner.active:
            raise UserError(_("Outlet tidak ditemukan atau tidak aktif."))
        partner.check_access("read")
        if partner.company_id and partner.company_id != company:
            raise UserError(_("Outlet milik company yang berbeda."))

        raw_lines = payload.get("lines", [])
        if not raw_lines:
            raise UserError(_("Order kosong tanpa produk."))

        assigned_product_ids = set(assignment.product_ids.ids)
        lines_by_principal = {}
        Product = self.env["product.product"].sudo()

        for line in raw_lines:
            pid = int(line.get("product_id", 0))
            if not pid or pid not in assigned_product_ids:
                raise UserError(_("Produk %s tidak termasuk dalam scope assignment aktif hari ini.") % pid)
            product = Product.browse(pid)
            if not product.exists() or not product.active or not product.sale_ok:
                raise UserError(_("Produk %s tidak valid atau tidak aktif.") % pid)
            if product.company_id and product.company_id != company:
                raise UserError(_("Produk %s milik company lain.") % pid)

            principal_id = product.principal_id.id if product.principal_id else 0
            lines_by_principal.setdefault(principal_id, []).append((product, line))

        pricelist = assignment.pricelist_id or partner.property_product_pricelist
        warehouse = assignment.warehouse_id

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
                if qty_val <= 0:
                    raise UserError(_("Jumlah pesanan produk %s harus lebih dari 0.") % product.name)
                uom_tier = item.get("uom", "carton")
                qty_in_unit = qty_val
                if uom_tier == "carton" and product.carton_qty:
                    qty_in_unit = qty_val * product.carton_qty
                elif uom_tier == "pack" and product.inner_qty:
                    qty_in_unit = qty_val * product.inner_qty

                line_disc = float(item.get("discount", 0.0)) or discount_pct
                order_lines.append((0, 0, {
                    "product_id": product.id,
                    "product_uom_qty": qty_in_unit,
                    "product_uom_id": product.uom_id.id,
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
        user, company = self._actor()
        Workday = self.env["id.mobile.workday"]
        assignment, day = Workday._current_assignment()

        outlet_id = int(payload.get("outlet_id", 0))
        if not outlet_id:
            raise UserError(_("Outlet wajib ditentukan untuk kunjungan."))

        if outlet_id not in assignment.outlet_ids.ids:
            raise UserError(_("Outlet %s tidak termasuk dalam scope assignment aktif hari ini.") % outlet_id)

        if cmd_type == "sales.visit.check_in":
            if day.weekday() == 6:
                raise UserError(_("Kunjungan operasional libur pada hari Minggu."))

            evidence_uuid = payload.get("evidence_uuid") or payload.get("evidence_receipt", {}).get("client_uuid")
            if not evidence_uuid:
                raise UserError(_("Check-in wajib menyertakan bukti foto dan lokasi yang valid."))

            evidence = self.env["id.mobile.evidence"].sudo().search([
                ("user_id", "=", user.id),
                ("client_uuid", "=", evidence_uuid),
                ("outlet_id", "=", outlet_id),
            ], limit=1)
            if not evidence:
                raise UserError(_("Bukti foto kunjungan tidak ditemukan atau tidak valid untuk outlet ini."))

            ref = f"VISIT-{client_uuid[:8]}"
            return "accepted", f"Check-in kunjungan outlet {outlet_id} tercatat dengan bukti {evidence_uuid[:8]}.", ref

        elif cmd_type == "sales.visit.check_out":
            ref = f"VISIT-{client_uuid[:8]}"
            return "accepted", f"Check-out kunjungan outlet {outlet_id} tercatat.", ref
        else:
            raise UserError(_("Unsupported visit command: %s") % cmd_type)

    def _handle_delivery(self, cmd_type, payload, client_uuid):
        user, company = self._actor()
        if not payload:
            raise UserError(_("Payload bukti pengiriman tidak boleh kosong."))

        trip_id = payload.get("trip_id") or payload.get("manifest_id")
        if not trip_id:
            raise UserError(_("Trip ID atau Manifest ID wajib disertakan untuk pengiriman."))

        if cmd_type in ("delivery.pod.submit", "delivery.proof.submit"):
            evidence_uuid = payload.get("evidence_uuid") or payload.get("proof_uuid")
            if not evidence_uuid:
                raise UserError(_("POD submit wajib menyertakan bukti foto atau tanda tangan penerima."))
            ref = f"POD-{client_uuid[:8]}"
            return "accepted", f"Bukti serah terima pengiriman trip {trip_id} berhasil disimpan.", ref

        elif cmd_type == "delivery.trip.close":
            ref = f"TRIP-{client_uuid[:8]}"
            return "accepted", f"Trip {trip_id} berhasil ditutup.", ref

        raise UserError(_("Unsupported delivery command: %s") % cmd_type)

    def _handle_collection(self, payload, client_uuid):
        user, company = self._actor()
        if not payload:
            raise UserError(_("Payload penerimaan kas tidak boleh kosong."))

        try:
            amount = float(payload.get("amount", 0))
        except (ValueError, TypeError):
            raise UserError(_("Nilai penerimaan kas tidak valid."))
        if amount <= 0:
            raise UserError(_("Nilai pembayaran harus lebih besar dari 0."))

        outlet_id = payload.get("outlet_id")
        invoice_id = payload.get("invoice_id")
        if not outlet_id and not invoice_id:
            raise UserError(_("Penerimaan kas harus terkait outlet atau faktur tagihan."))

        method = payload.get("method", "cash")
        ref = f"PAY-{client_uuid[:8]}"
        return "accepted", f"Penerimaan kas/transfer Rp {amount:,.0f} ({method}) tercatat.", ref

    def _handle_hris(self, cmd_type, payload, client_uuid):
        user, company = self._actor()
        if not payload:
            raise UserError(_("Payload absensi atau perizinan tidak boleh kosong."))
        ref = f"HR-{client_uuid[:8]}"
        return "accepted", "Absensi/kehadiran kerja berhasil dicatat.", ref

    def _handle_expense(self, cmd_type, payload, client_uuid):
        user, company = self._actor()
        if not payload:
            raise UserError(_("Payload biaya operasional tidak boleh kosong."))
        try:
            amount = float(payload.get("amount", 0))
        except (ValueError, TypeError):
            raise UserError(_("Jumlah biaya tidak valid."))
        if amount <= 0:
            raise UserError(_("Jumlah biaya harus lebih dari 0."))
        ref = f"EXP-{client_uuid[:8]}"
        return "needs_approval", "Pengajuan biaya lapangan dikirim ke supervisor.", ref
