from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import uuid
from zoneinfo import ZoneInfo
from psycopg2 import IntegrityError
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from .mobile_workday import MobileReadConflict

_logger = logging.getLogger(__name__)

WITA = ZoneInfo("Asia/Makassar")

SUPPORTED_COMMANDS = {
    "sales.order.submit",
    "sales.visit.check_in",
    "sales.visit.check_out",
    "delivery.pod.submit",
    "delivery.trip.close",
    "delivery.proof.submit",
}


def to_wita_date(dt):
    """Converts a UTC datetime from PostgreSQL to a calendar date in Asia/Makassar (WITA)."""
    if not dt:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(WITA).date()
    return dt


def extract_cmd_payload(cmd_record):
    """Safely extracts inner payload dictionary from either full envelope or raw payload."""
    try:
        data = json.loads(cmd_record.payload_json or "{}")
        if isinstance(data, dict) and "payload" in data and isinstance(data["payload"], dict):
            return data["payload"]
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


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

        # Snapshot version validation (mandatory)
        snapshot_version = payload.get("snapshot_version")
        if not snapshot_version:
            raise UserError(_("Snapshot version wajib disertakan."))
        current_snapshot = Workday._snapshot_payload()
        if snapshot_version != current_snapshot.get("version"):
            raise MobileReadConflict(_("Stale catalog snapshot version."))

        try:
            outlet_id = int(payload.get("outlet_id", 0))
        except (ValueError, TypeError):
            outlet_id = 0
        if not outlet_id:
            raise UserError(_("Outlet wajib ditentukan."))

        if outlet_id not in assignment.outlet_ids.ids:
            raise UserError(_("Outlet %s tidak termasuk dalam scope assignment aktif hari ini.") % outlet_id)

        partner = self.env["res.partner"].browse(outlet_id)
        if not partner.exists() or not partner.active:
            raise UserError(_("Outlet tidak ditemukan atau tidak aktif."))
        partner.check_access("read")
        if partner.company_id and partner.company_id != company:
            raise AccessError(_("Outlet milik company yang berbeda."))

        raw_lines = payload.get("lines", [])
        if not raw_lines:
            raise UserError(_("Order kosong tanpa produk."))

        assigned_product_ids = set(assignment.sudo().product_ids.ids)
        lines_by_principal = {}
        # Validate SKU visibility and catalog access via actor's permissions (no sudo bypass)
        ActorProduct = self.env["product.product"]

        for line in raw_lines:
            try:
                pid = int(line.get("product_id", 0))
            except (ValueError, TypeError):
                pid = 0
            if not pid or pid not in assigned_product_ids:
                raise UserError(_("Produk %s tidak termasuk dalam scope assignment aktif hari ini.") % pid)

            product = ActorProduct.browse(pid)
            if not product.exists():
                raise AccessError(_("Produk %s tidak ditemukan atau tidak dapat diakses.") % pid)
            product.check_access("read")
            if not product.active or not product.sale_ok:
                raise UserError(_("Produk %s tidak aktif atau bukan barang dagangan.") % pid)
            if product.company_id and product.company_id != company:
                raise AccessError(_("Produk %s milik company lain.") % pid)

            principal_id = product.principal_id.id if product.principal_id else 0
            lines_by_principal.setdefault(principal_id, []).append((product, line))

        pricelist = assignment.pricelist_id or partner.property_product_pricelist
        warehouse = assignment.warehouse_id

        created_orders = []
        discount_req = payload.get("discount_request") or {}
        try:
            discount_pct = float(discount_req.get("percent", 0.0))
        except (ValueError, TypeError):
            raise UserError(_("Persentase diskon order tidak valid."))
        if math.isnan(discount_pct) or math.isinf(discount_pct) or discount_pct < 0.0 or discount_pct > 100.0:
            raise UserError(_("Persentase diskon order harus antara 0 dan 100."))
        discount_reason = str(discount_req.get("reason", "")).strip()
        if discount_pct > 0.0 and len(discount_reason) < 3:
            raise UserError(_("Alasan pengajuan diskon order wajib minimal 3 karakter."))

        customer_po = str(payload.get("customer_po_number") or payload.get("note") or "").strip()

        needs_approval = False
        SaleOrder = self.env["sale.order"].sudo()
        UOM_WHITELIST = {"carton", "pack", "pcs"}

        for principal_id, items in lines_by_principal.items():
            order_lines = []
            for product, item in items:
                try:
                    qty_val = float(item.get("qty", 1))
                except (ValueError, TypeError):
                    raise UserError(_("Kuantitas produk %s tidak valid.") % product.name)
                if math.isnan(qty_val) or math.isinf(qty_val) or qty_val <= 0:
                    raise UserError(_("Jumlah pesanan produk %s harus bilangan positif lebih dari 0.") % product.name)

                uom_tier = str(item.get("uom", "carton")).strip().lower()
                if uom_tier not in UOM_WHITELIST:
                    raise UserError(_("Satuan UoM '%s' tidak didukung (hanya carton, pack, pcs).") % uom_tier)

                if uom_tier == "carton":
                    qty_in_unit = qty_val * (product.carton_qty or 1)
                elif uom_tier == "pack":
                    if not product.inner_qty:
                        raise UserError(_("Produk %s tidak mendukung satuan pack.") % product.name)
                    qty_in_unit = qty_val * product.inner_qty
                elif uom_tier == "pcs":
                    qty_in_unit = qty_val
                else:
                    raise UserError(_("Satuan UoM '%s' tidak valid.") % uom_tier)

                try:
                    line_disc = float(item.get("discount", 0.0)) or discount_pct
                except (ValueError, TypeError):
                    raise UserError(_("Diskon produk %s tidak valid.") % product.name)
                if math.isnan(line_disc) or math.isinf(line_disc) or line_disc < 0.0 or line_disc > 100.0:
                    raise UserError(_("Diskon produk %s harus antara 0 dan 100.") % product.name)

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

        try:
            outlet_id = int(payload.get("outlet_id", 0))
        except (ValueError, TypeError):
            outlet_id = 0
        if not outlet_id:
            raise UserError(_("Outlet wajib ditentukan untuk kunjungan."))

        if outlet_id not in assignment.outlet_ids.ids:
            raise UserError(_("Outlet %s tidak termasuk dalam scope assignment aktif hari ini.") % outlet_id)

        if cmd_type == "sales.visit.check_in":
            if day.weekday() == 6:
                raise UserError(_("Kunjungan operasional libur pada hari Minggu."))

            evidence_uuid = (
                payload.get("evidence", {}).get("id")
                or payload.get("evidence_uuid")
                or payload.get("evidence_receipt", {}).get("client_uuid")
            )
            if not evidence_uuid:
                raise UserError(_("Check-in wajib menyertakan bukti foto dan lokasi yang valid."))

            evidence = self.env["id.mobile.evidence"].sudo().search([
                ("user_id", "=", user.id),
                ("company_id", "=", company.id),
                ("client_uuid", "=", evidence_uuid),
                ("outlet_id", "=", outlet_id),
            ], limit=1)
            if not evidence or not evidence.original:
                raise UserError(_("Bukti foto kunjungan tidak ditemukan atau tidak valid untuk outlet ini."))

            receipt_data = json.loads(evidence.receipt_json or "{}")
            if receipt_data.get("business_date") != day.isoformat():
                raise UserError(_("Bukti foto kunjungan bukan untuk hari kerja hari ini (%s).") % day.isoformat())

            package_hash = payload.get("evidence", {}).get("packageHash")
            if package_hash:
                valid_hashes = {
                    receipt_data.get("original_sha256"),
                    receipt_data.get("watermarked_sha256"),
                    receipt_data.get("binding_sha256"),
                }
                if package_hash not in valid_hashes:
                    raise UserError(_("Hash paket bukti foto kunjungan tidak cocok dengan media tersimpan."))

            ref = f"VISIT-{client_uuid[:8]}"
            return "accepted", f"Check-in kunjungan outlet {outlet_id} tercatat dengan bukti {evidence_uuid[:8]}.", ref

        elif cmd_type == "sales.visit.check_out":
            # Checkout must bind to an active check-in session for this outlet on the same WITA business day
            prior_checkin = self.sudo().search([
                ("user_id", "=", user.id),
                ("company_id", "=", company.id),
                ("command_type", "=", "sales.visit.check_in"),
                ("status", "=", "accepted"),
            ], order="id desc")
            has_valid_checkin = False
            for cmd in prior_checkin:
                p = extract_cmd_payload(cmd)
                cmd_outlet = str(p.get("outlet_id") or "")
                if cmd_outlet == str(outlet_id) and to_wita_date(cmd.create_date) == day:
                    has_valid_checkin = True
                    break
            if not has_valid_checkin:
                raise UserError(
                    _("Check-out ditolak: belum ada sesi check-in yang sah untuk outlet ini pada hari ini.")
                )

            # If checkout provides closing evidence (e.g. store closed/unavailable)
            closing_evidence_uuid = payload.get("evidence", {}).get("id") or payload.get("evidence_uuid")
            if closing_evidence_uuid:
                closing_ev = self.env["id.mobile.evidence"].sudo().search([
                    ("user_id", "=", user.id),
                    ("company_id", "=", company.id),
                    ("client_uuid", "=", closing_evidence_uuid),
                    ("outlet_id", "=", outlet_id),
                ], limit=1)
                if not closing_ev or not closing_ev.original:
                    raise UserError(_("Bukti foto closing checkout tidak ditemukan atau tidak memiliki media valid."))
                ev_receipt = json.loads(closing_ev.receipt_json or "{}")
                if ev_receipt.get("business_date") != day.isoformat():
                    raise UserError(_("Bukti foto closing checkout bukan untuk hari kerja hari ini."))

            ref = f"VISIT-{client_uuid[:8]}"
            return "accepted", f"Check-out kunjungan outlet {outlet_id} tercatat.", ref
        else:
            raise UserError(_("Unsupported visit command: %s") % cmd_type)

    def _handle_delivery(self, cmd_type, payload, client_uuid):
        user, company = self._actor()
        Workday = self.env["id.mobile.workday"]
        assignment, day = Workday._current_assignment()

        if not payload:
            raise UserError(_("Payload bukti pengiriman tidak boleh kosong."))

        if cmd_type in ("delivery.pod.submit", "delivery.proof.submit"):
            source = payload.get("source") or {}
            trip_id = str(source.get("trip") or payload.get("trip_id") or payload.get("manifest_id") or "").strip()
            do_id = str(source.get("id") or payload.get("do_id") or "").strip()
            outlet_id_raw = source.get("outlet_id") or payload.get("outlet_id")
            try:
                outlet_id = int(outlet_id_raw or 0)
            except (ValueError, TypeError):
                outlet_id = 0

            evidence_data = payload.get("evidence") or {}
            ev_id = evidence_data.get("id") or payload.get("evidence_uuid") or payload.get("proof_uuid")
            evidence_uuid = str(ev_id or "").strip()
            package_hash = evidence_data.get("packageHash")
            recipient = str(payload.get("recipient") or "").strip()

            if not trip_id:
                raise UserError(_("Trip ID atau Manifest ID wajib disertakan untuk pengiriman."))
            if not do_id:
                raise UserError(_("DO ID wajib disertakan untuk pengiriman."))
            if not evidence_uuid:
                raise UserError(_("POD submit wajib menyertakan bukti foto atau tanda tangan penerima."))
            if not recipient or len(recipient) < 2:
                raise UserError(_("Nama penerima POD wajib diisi (minimal 2 karakter)."))

            # 1. Authoritative manifest resolution: bind exact trip + DO + company pair (no OR bypass)
            picking = self.env["stock.picking"].sudo().search([
                ("company_id", "=", company.id),
                ("name", "=", do_id),
                ("origin", "=", trip_id),
            ], limit=1)
            if not picking:
                raise UserError(
                    _("DO %s dengan trip %s tidak ditemukan dalam manifest operasional.") % (do_id, trip_id)
                )

            # 2. DO outlet binding: must match DO partner and active workday assignment
            do_partner_id = picking.partner_id.id
            if outlet_id and do_partner_id != outlet_id:
                raise UserError(_("DO %s bukan untuk outlet %s.") % (do_id, outlet_id))

            if do_partner_id not in assignment.outlet_ids.ids:
                raise UserError(_("Outlet %s tidak termasuk dalam scope assignment aktif hari ini.") % do_partner_id)

            # 3. Persistent evidence binding: must match DO partner, actor, company, current day, and media
            evidence = self.env["id.mobile.evidence"].sudo().search([
                ("client_uuid", "=", evidence_uuid),
                ("user_id", "=", user.id),
                ("company_id", "=", company.id),
                ("outlet_id", "=", do_partner_id),
            ], limit=1)
            if not evidence or not evidence.original:
                raise UserError(
                    _("Bukti POD %s tidak ditemukan atau tidak valid untuk outlet %s.") % (evidence_uuid, do_partner_id)
                )

            receipt_data = json.loads(evidence.receipt_json or "{}")
            if receipt_data.get("business_date") != day.isoformat():
                raise UserError(_("Bukti POD bukan untuk hari kerja hari ini (%s).") % day.isoformat())

            if package_hash:
                valid_hashes = {
                    receipt_data.get("original_sha256"),
                    receipt_data.get("watermarked_sha256"),
                    receipt_data.get("binding_sha256"),
                }
                if package_hash not in valid_hashes:
                    raise UserError(_("Hash paket bukti foto POD tidak cocok dengan media tersimpan."))

            ref = f"POD-{client_uuid[:8]}"
            return "accepted", f"Bukti serah terima pengiriman trip {trip_id} DO {do_id} berhasil disimpan.", ref

        elif cmd_type == "delivery.trip.close":
            trip_id = str(payload.get("trip_id") or "").strip()
            if not trip_id:
                raise UserError(_("Trip ID wajib disertakan untuk menutup trip pengiriman."))

            business_date_str = payload.get("business_date")
            if business_date_str and business_date_str != day.isoformat():
                raise UserError(_("Trip closure hanya dapat dilakukan untuk hari kerja hari ini."))

            # Trip must exist in authoritative operational pickings
            manifest_pickings = self.env["stock.picking"].sudo().search([
                ("company_id", "=", company.id),
                ("origin", "=", trip_id),
            ])
            if not manifest_pickings:
                raise UserError(_("Trip pengiriman %s tidak ditemukan dalam manifest operasional.") % trip_id)

            required_do_names = set(manifest_pickings.mapped("name"))

            # Prove all DOs in manifest have accepted PODs submitted on this WITA day
            submitted_pods = self.sudo().search([
                ("user_id", "=", user.id),
                ("company_id", "=", company.id),
                ("command_type", "=", "delivery.pod.submit"),
                ("status", "=", "accepted"),
            ])
            accepted_dos_in_trip = set()
            valid_pod_uuids_for_trip = set()
            for pod_cmd in submitted_pods:
                if to_wita_date(pod_cmd.create_date) == day:
                    p = extract_cmd_payload(pod_cmd)
                    p_src = p.get("source") or {}
                    p_trip = str(p_src.get("trip") or p.get("trip_id") or p.get("manifest_id") or "").strip()
                    p_do = str(p_src.get("id") or p.get("do_id") or "").strip()
                    if p_trip == trip_id and p_do:
                        accepted_dos_in_trip.add(p_do)
                        valid_pod_uuids_for_trip.add(pod_cmd.client_uuid)

            missing_dos = required_do_names - accepted_dos_in_trip
            if missing_dos:
                raise UserError(
                    _("Trip %s belum lengkap: DO %s belum memiliki POD yang diterima hari ini.")
                    % (trip_id, ", ".join(sorted(missing_dos)))
                )

            pod_uuids = payload.get("pod_uuids") or []
            if not pod_uuids:
                raise UserError(_("Trip closure wajib menyertakan daftar POD yang diverifikasi."))

            for pid in pod_uuids:
                if pid not in valid_pod_uuids_for_trip:
                    raise UserError(
                        _("POD %s bukan milik manifest trip %s pada hari ini atau belum diterima.") % (pid, trip_id)
                    )

            ref = f"TRIP-{client_uuid[:8]}"
            msg = f"Trip pengiriman {trip_id} berhasil ditutup dengan {len(accepted_dos_in_trip)} DO terverifikasi."
            return "accepted", msg, ref

        raise UserError(_("Unsupported delivery command: %s") % cmd_type)
