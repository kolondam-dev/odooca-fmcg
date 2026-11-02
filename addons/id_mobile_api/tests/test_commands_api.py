import base64
from datetime import datetime, timedelta
import json
import uuid
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, tagged
from ..models.mobile_workday import MobileReadConflict, business_date
from .test_read_api import MobileFixture


@tagged("post_install", "-at_install")
class TestMobileCommandsApi(MobileFixture, TransactionCase):

    def setUp(self):
        super().setUp()
        self.assignment.write({
            "outlet_radius": 100,
        })
        snapshot_payload = self.env["id.mobile.workday"].with_user(self.mobile).with_context(
            allowed_company_ids=self.mobile.company_ids.ids
        )._snapshot_payload()
        self.snapshot_version = snapshot_payload["version"]

    def _command_model(self, user=None):
        target_user = user or self.mobile
        return self.env["id.mobile.command"].with_user(target_user).with_company(self.company)

    def _valid_order_payload(self, **overrides):
        payload = {
            "outlet_id": str(self.outlet.id),
            "snapshot_version": self.snapshot_version,
            "lines": [{"product_id": str(self.product.id), "qty": "1", "uom": "carton"}],
        }
        payload.update(overrides)
        return payload

    def test_actor_model_guard(self):
        """Direct ORM/RPC call without mobile sales privileges must fail closed."""
        cmd = {
            "client_uuid": str(uuid.uuid4()),
            "type": "sales.order.submit",
            "payload": self._valid_order_payload(),
        }
        # Portal user
        with self.assertRaises(AccessError):
            self._command_model(self.portal).process_command(cmd)
        # Internal non-sales user
        with self.assertRaises(AccessError):
            self._command_model(self.internal).process_command(cmd)
        # Public user
        public_user = self.env.ref("base.public_user")
        with self.assertRaises(AccessError):
            self._command_model(public_user).process_command(cmd)

    def test_record_rule_isolation(self):
        """Users can only view their own commands, while admins can audit all."""
        valid_uuid = str(uuid.uuid4())
        cmd = {
            "client_uuid": valid_uuid,
            "type": "sales.order.submit",
            "payload": self._valid_order_payload(),
        }
        self._command_model(self.mobile).process_command(cmd)

        # Other mobile user cannot see this command
        other_records = self.env["id.mobile.command"].with_user(self.other).search([
            ("client_uuid", "=", valid_uuid)
        ])
        self.assertEqual(len(other_records), 0, "Other user must not see commands across users.")

        # Author can see their own command
        own_records = self.env["id.mobile.command"].with_user(self.mobile).search([
            ("client_uuid", "=", valid_uuid)
        ])
        self.assertEqual(len(own_records), 1)

        # System admin can audit commands within company scope
        admin = self.env.ref("base.user_admin")
        admin.write({"company_ids": [Command.link(self.company.id)]})
        admin_records = self.env["id.mobile.command"].with_user(admin).with_company(self.company).search([
            ("client_uuid", "=", valid_uuid)
        ])
        self.assertEqual(len(admin_records), 1)

    def test_envelope_validation(self):
        """Invalid UUID, missing envelope fields, and unsupported types must fail closed."""
        model = self._command_model()

        # Missing client_uuid
        with self.assertRaises(UserError):
            model.process_command({"type": "sales.order.submit", "payload": {}})

        # Malformed non-UUID
        with self.assertRaises(UserError):
            model.process_command({"client_uuid": "not-a-valid-uuid", "type": "sales.order.submit", "payload": {}})

        # Unsupported command type
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "unsupported.command.type",
                "payload": {},
            })

        # Payload not a dict
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.order.submit",
                "payload": "not-a-dict",
            })

    def test_strict_idempotency_fingerprint_conflict(self):
        """Replaying the same UUID with identical payload succeeds; changed content raises 409 conflict."""
        cmd_uuid = str(uuid.uuid4())
        command = {
            "client_uuid": cmd_uuid,
            "type": "sales.order.submit",
            "payload": self._valid_order_payload(),
        }
        model = self._command_model()
        rc1 = model.process_command(command)
        self.assertEqual(rc1["client_uuid"], cmd_uuid)

        # Replay identical -> idempotent cached receipt
        rc2 = model.process_command(command)
        self.assertEqual(rc1["reference"], rc2["reference"])

        # Replay same UUID with changed content -> MobileReadConflict (409)
        tampered = {
            "client_uuid": cmd_uuid,
            "type": "sales.order.submit",
            "payload": self._valid_order_payload(
                lines=[{"product_id": str(self.product.id), "qty": "99", "uom": "carton"}]
            ),
        }
        with self.assertRaises(MobileReadConflict):
            model.process_command(tampered)

        # Replay same UUID with different command type -> MobileReadConflict (409)
        different_type = {
            "client_uuid": cmd_uuid,
            "type": "delivery.pod.submit",
            "payload": {"trip_id": "TRIP-01", "evidence_uuid": "proof-1"},
        }
        with self.assertRaises(MobileReadConflict):
            model.process_command(different_type)

    def test_order_snapshot_and_scope_guards(self):
        """Orders outside scheduled outlet, unassigned SKU, inactive SKU, or stale snapshot must be rejected."""
        model = self._command_model()

        # Missing snapshot_version (mandatory per P1-A)
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.order.submit",
                "payload": {
                    "outlet_id": str(self.outlet.id),
                    "lines": [{"product_id": str(self.product.id), "qty": "1", "uom": "carton"}],
                },
            })

        # Stale snapshot version
        with self.assertRaises(MobileReadConflict):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.order.submit",
                "payload": self._valid_order_payload(snapshot_version="odoo-read-v1:stale-version-hash"),
            })

        # Unassigned outlet
        unassigned_outlet = self.env["res.partner"].create({
            "name": "Unassigned Outlet",
            "company_id": self.company.id,
        })
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.order.submit",
                "payload": self._valid_order_payload(outlet_id=str(unassigned_outlet.id)),
            })

        # Unassigned SKU
        unit = self.env.ref("uom.product_uom_unit")
        unassigned_product = self.env["product.product"].create({
            "name": "Unassigned Product",
            "default_code": "UNASSIGNED-SKU",
            "principal_id": self.principal.id,
            "uom_id": unit.id,
            "carton_qty": 10,
            "inner_qty": 2,
            "type": "consu",
            "is_storable": True,
            "taxes_id": [Command.clear()],
        })
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.order.submit",
                "payload": self._valid_order_payload(
                    lines=[{"product_id": str(unassigned_product.id), "qty": "1", "uom": "carton"}]
                ),
            })

        # Inactive SKU (excluded from active assignment domain, rejected fail-closed)
        inactive_product = self.env["product.product"].create({
            "name": "Inactive Product",
            "default_code": "INACTIVE-SKU",
            "principal_id": self.principal.id,
            "uom_id": unit.id,
            "carton_qty": 10,
            "inner_qty": 2,
            "type": "consu",
            "active": False,
            "is_storable": True,
            "taxes_id": [Command.clear()],
        })
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.order.submit",
                "payload": self._valid_order_payload(
                    lines=[{"product_id": str(inactive_product.id), "qty": "1", "uom": "carton"}]
                ),
            })

    def test_order_hidden_sku_rule_guard(self):
        """Assigned SKU hidden from actor by ir.rule or catalog ACL raises AccessError."""
        model = self._command_model()
        unit = self.env.ref("uom.product_uom_unit")
        hidden_product = self.env["product.product"].create({
            "name": "Hidden Product",
            "default_code": "HIDDEN-SKU",
            "principal_id": self.principal.id,
            "uom_id": unit.id,
            "carton_qty": 10,
            "inner_qty": 2,
            "type": "consu",
            "active": True,
            "is_storable": True,
            "taxes_id": [Command.clear()],
        })
        self.assignment.product_ids = [Command.link(hidden_product.id)]

        rule = self.env["ir.rule"].sudo().create({
            "name": "Hide Secret Product From Sales",
            "model_id": self.env.ref("product.model_product_product").id,
            "domain_force": f"[('id', '!=', {hidden_product.id})]",
        })
        try:
            with self.assertRaises(AccessError):
                model.process_command({
                    "client_uuid": str(uuid.uuid4()),
                    "type": "sales.order.submit",
                    "payload": self._valid_order_payload(
                        snapshot_version=self.snapshot_version,
                        lines=[{"product_id": str(hidden_product.id), "qty": "1", "uom": "carton"}]
                    ),
                })
        finally:
            rule.unlink()

    def test_order_uom_quantity_and_discount_guards(self):
        """Invalid UoMs, quantities (zero/negative/NaN), or discounts (>100 or short reason) fail closed."""
        model = self._command_model()

        # Invalid UoM (e.g. PALLET-HACK must be rejected fail-closed)
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.order.submit",
                "payload": self._valid_order_payload(
                    lines=[{"product_id": str(self.product.id), "qty": "1", "uom": "PALLET-HACK"}]
                ),
            })

        # Invalid Quantity (zero, negative or non-finite)
        for bad_qty in ("0", "-5", "NaN"):
            with self.assertRaises(UserError):
                model.process_command({
                    "client_uuid": str(uuid.uuid4()),
                    "type": "sales.order.submit",
                    "payload": self._valid_order_payload(
                        lines=[{"product_id": str(self.product.id), "qty": bad_qty, "uom": "carton"}]
                    ),
                })

        # Invalid Discount (> 100 or reason too short)
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.order.submit",
                "payload": self._valid_order_payload(
                    discount_request={"percent": 150, "reason": "Too big"}
                ),
            })
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.order.submit",
                "payload": self._valid_order_payload(
                    discount_request={"percent": 10, "reason": "ab"}
                ),
            })

    def test_atomic_split_so_savepoint_rollback(self):
        """When multi-principal split SO encounters a failure, all generated SOs and logs must roll back cleanly."""
        principal2 = self.env["id.principal"].create({"name": "Principal Two", "code": "PRIN-2"})
        unit = self.env.ref("uom.product_uom_unit")
        product2 = self.env["product.product"].create({
            "name": "Product Two",
            "default_code": "PROD-2",
            "principal_id": principal2.id,
            "uom_id": unit.id,
            "carton_qty": 12,
            "inner_qty": 4,
            "type": "consu",
            "is_storable": True,
        })
        self.assignment.product_ids = [Command.link(product2.id)]
        fresh_snapshot = self.env["id.mobile.workday"].with_user(self.mobile).with_context(
            allowed_company_ids=self.mobile.company_ids.ids
        )._snapshot_payload()["version"]

        cmd_uuid = str(uuid.uuid4())
        command = {
            "client_uuid": cmd_uuid,
            "type": "sales.order.submit",
            "payload": self._valid_order_payload(
                snapshot_version=fresh_snapshot,
                lines=[
                    {"product_id": str(self.product.id), "qty": "1", "uom": "carton"},
                    {"product_id": str(product2.id), "qty": "2", "uom": "carton"},
                ]
            ),
        }

        orig_create = self.env["sale.order"].create
        call_count = [0]

        def fail_on_second(vals_list):
            call_count[0] += 1
            if call_count[0] == 2:
                raise UserError("Simulated PostgreSQL error on second principal SO")
            return orig_create(vals_list)

        model = self._command_model()
        with patch.object(type(self.env["sale.order"]), "create", side_effect=fail_on_second):
            with self.assertRaises(UserError):
                model.process_command(command)

        orders = self.env["sale.order"].sudo().search([("origin", "=", f"PWA Mobile Order {cmd_uuid[:8]}")])
        self.assertEqual(len(orders), 0, "No partial SO should remain after rollback.")
        cmds = self.env["id.mobile.command"].sudo().search([("client_uuid", "=", cmd_uuid)])
        self.assertEqual(len(cmds), 0, "No partial command log should remain after rollback.")

    def test_positive_multi_principal_split_orders(self):
        """Positive multi-principal submission successfully creates separate SOs per principal."""
        principal2 = self.env["id.principal"].create({"name": "Principal Pos", "code": "PRIN-POS"})
        unit = self.env.ref("uom.product_uom_unit")
        product2 = self.env["product.product"].create({
            "name": "Product Pos",
            "default_code": "PROD-POS",
            "principal_id": principal2.id,
            "uom_id": unit.id,
            "carton_qty": 10,
            "inner_qty": 2,
            "type": "consu",
            "is_storable": True,
            "company_id": self.company.id,
            "taxes_id": [Command.clear()],
        })
        self.assignment.product_ids = [Command.link(product2.id)]
        fresh_snapshot = self.env["id.mobile.workday"].with_user(self.mobile).with_context(
            allowed_company_ids=self.mobile.company_ids.ids
        )._snapshot_payload()["version"]

        cmd_uuid = str(uuid.uuid4())
        command = {
            "client_uuid": cmd_uuid,
            "type": "sales.order.submit",
            "payload": self._valid_order_payload(
                snapshot_version=fresh_snapshot,
                customer_po_number="PO-SPLIT-001",
                lines=[
                    {"product_id": str(self.product.id), "qty": "2", "uom": "carton", "discount": 10},
                    {"product_id": str(product2.id), "qty": "3", "uom": "carton", "discount": 5},
                ],
            ),
        }

        model = self._command_model()
        rc = model.process_command(command)
        self.assertEqual(rc["status"], "accepted")

        orders = self.env["sale.order"].sudo().search([("origin", "=", f"PWA Mobile Order {cmd_uuid[:8]}")])
        self.assertEqual(len(orders), 2, "Must create 2 distinct SOs for 2 principals.")
        self.assertTrue(all(so.client_order_ref == "PO-SPLIT-001" for so in orders))

    def test_visit_checkin_and_checkout_validation(self):
        """Visit check-in requires fresh valid evidence; check-out requires prior active check-in."""
        model = self._command_model()
        day = business_date()
        day_str = day.isoformat()
        # Boundary 00:30 WITA = (day - 1 day) at 16:30 UTC
        sampled_0030 = (
            datetime.combine(day - timedelta(days=1), datetime.min.time())
            .replace(hour=16, minute=30)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        # Boundary 08:30 WITA = day at 00:30 UTC
        sampled_0830 = (
            datetime.combine(day, datetime.min.time())
            .replace(hour=0, minute=30)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )

        # 1. Check-in without evidence -> rejected
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.visit.check_in",
                "payload": {"outlet_id": str(self.outlet.id)},
            })

        # 2. Check-in with nonexistent evidence -> rejected
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.visit.check_in",
                "payload": {
                    "outlet_id": str(self.outlet.id),
                    "evidence": {"id": str(uuid.uuid4())},
                },
            })

        # 3. Check-in with evidence from other company -> rejected
        foreign_company = self.env["res.company"].create({
            "name": "Foreign Company",
            "currency_id": self.company.currency_id.id,
        })
        foreign_evidence_uuid = str(uuid.uuid4())
        dummy_base64 = base64.b64encode(b"valid-image-bytes")
        self.env["id.mobile.evidence"].sudo().create({
            "user_id": self.mobile.id,
            "company_id": foreign_company.id,
            "outlet_id": self.outlet.id,
            "client_uuid": foreign_evidence_uuid,
            "fingerprint": "foreign-fingerprint",
            "receipt_json": json.dumps({"business_date": day_str}),
            "original": dummy_base64,
            "watermarked": dummy_base64,
        })
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.visit.check_in",
                "payload": {
                    "outlet_id": str(self.outlet.id),
                    "evidence": {"id": foreign_evidence_uuid},
                },
            })

        # 4. Check-in with stale seed date (e.g. July 2026) -> rejected
        stale_evidence_uuid = str(uuid.uuid4())
        self.env["id.mobile.evidence"].sudo().create({
            "user_id": self.mobile.id,
            "company_id": self.company.id,
            "outlet_id": self.outlet.id,
            "client_uuid": stale_evidence_uuid,
            "fingerprint": "stale-fingerprint",
            "receipt_json": json.dumps({"business_date": "2026-07-15"}),
            "original": dummy_base64,
            "watermarked": dummy_base64,
        })
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.visit.check_in",
                "payload": {
                    "outlet_id": str(self.outlet.id),
                    "evidence": {"id": stale_evidence_uuid},
                },
            })

        # 5. Check-out without prior check-in -> rejected fail-closed
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.visit.check_out",
                "payload": {
                    "outlet_id": str(self.outlet.id),
                    "outcome": "order_requested",
                },
            })

        # 6. Valid check-in using frontend wire DTO format (VisitCheckInSchema)
        valid_evidence_uuid = str(uuid.uuid4())
        self.env["id.mobile.evidence"].sudo().create({
            "user_id": self.mobile.id,
            "company_id": self.company.id,
            "outlet_id": self.outlet.id,
            "client_uuid": valid_evidence_uuid,
            "fingerprint": "valid-evidence-fingerprint",
            "receipt_json": json.dumps({
                "business_date": day_str,
                "original_sha256": "fake-photo-hash",
            }),
            "original": dummy_base64,
            "watermarked": dummy_base64,
        })
        # 6. Valid check-in for Session A using frontend wire DTO format (VisitCheckInSchema)
        session_a_visit_uuid = str(uuid.uuid4())
        session_a_work_session_id = str(uuid.uuid4())
        checkin_uuid_a = str(uuid.uuid4())
        rc_checkin_a = model.process_command({
            "client_uuid": checkin_uuid_a,
            "type": "sales.visit.check_in",
            "payload": {
                "outlet_id": str(self.outlet.id),
                "visit_uuid": session_a_visit_uuid,
                "work_session_id": session_a_work_session_id,
                "business_date": day_str,
                "snapshot_version": self.snapshot_version,
                "site": {"latitude": 1.465, "longitude": 124.833, "radius": 100},
                "fix": {
                    "latitude": 1.465,
                    "longitude": 124.833,
                    "accuracy": 3.0,
                    "sampled_at": sampled_0030,  # Boundary 00:30 WITA
                },
                "evidence": {
                    "id": valid_evidence_uuid,
                    "packageHash": "fake-photo-hash",
                },
            },
        })
        self.assertEqual(rc_checkin_a["status"], "accepted")

        # Counterexample: Check-out with nonexistent/unstarted Session B -> UserError
        session_b_visit_uuid = str(uuid.uuid4())
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.visit.check_out",
                "payload": {
                    "outlet_id": str(self.outlet.id),
                    "visit_uuid": session_b_visit_uuid,
                    "work_session_id": session_a_work_session_id,
                    "business_date": day_str,
                    "snapshot_version": self.snapshot_version,
                    "site": {"latitude": 1.465, "longitude": 124.833, "radius": 100},
                    "fix": {
                        "latitude": 1.465,
                        "longitude": 124.833,
                        "accuracy": 3.0,
                        "sampled_at": sampled_0830,  # Boundary 08:30 WITA
                    },
                    "outcome": "order_requested",
                    "notes": "Attempting invalid session B checkout",
                    "order_uuids": [],
                },
            })

        # 7. Valid check-out for Session A with boundary 08:30 WITA (00:30 UTC)
        checkout_uuid_a = str(uuid.uuid4())
        checkout_payload_a = {
            "outlet_id": str(self.outlet.id),
            "visit_uuid": session_a_visit_uuid,
            "work_session_id": session_a_work_session_id,
            "business_date": day_str,
            "snapshot_version": self.snapshot_version,
            "site": {"latitude": 1.465, "longitude": 124.833, "radius": 100},
            "fix": {
                "latitude": 1.465,
                "longitude": 124.833,
                "accuracy": 3.0,
                "sampled_at": sampled_0830,  # Boundary 08:30 WITA
            },
            "outcome": "order_requested",
            "notes": "Visit session A completed successfully.",
            "order_uuids": [],
        }
        rc_checkout_a = model.process_command({
            "client_uuid": checkout_uuid_a,
            "type": "sales.visit.check_out",
            "payload": checkout_payload_a,
        })
        self.assertEqual(rc_checkout_a["status"], "accepted")
        self.assertEqual(rc_checkout_a["reference"], f"VISIT-{checkout_uuid_a[:8]}")

        # Counterexample: Second checkout for Session A with NEW command UUID -> UserError (session already closed)
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.visit.check_out",
                "payload": checkout_payload_a,
            })

        # Idempotency: Identical retry with same client_uuid and payload -> returns cached accepted receipt
        rc_checkout_retry = model.process_command({
            "client_uuid": checkout_uuid_a,
            "type": "sales.visit.check_out",
            "payload": checkout_payload_a,
        })
        self.assertEqual(rc_checkout_retry["status"], "accepted")
        self.assertEqual(rc_checkout_retry["reference"], f"VISIT-{checkout_uuid_a[:8]}")

    def test_delivery_pod_and_trip_close_validation(self):
        """Delivery POD submit requires valid picking manifest and persistent evidence; trip close binds PODs."""
        model = self._command_model()
        day_str = business_date().isoformat()
        dummy_base64 = base64.b64encode(b"valid-pod-photo")

        # 1. POD with nonexistent trip / manifest -> rejected
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "delivery.pod.submit",
                "payload": {
                    "source": {"trip": "NONEXISTENT-TRIP", "id": "DO-NONE"},
                    "evidence": {"id": str(uuid.uuid4())},
                    "recipient": "Pak Budi",
                },
            })

        # 2. Prepare valid picking manifest and evidence in database
        picking_type = self.env["stock.picking.type"].search([
            ("company_id", "=", self.company.id),
            ("code", "=", "outgoing"),
        ], limit=1)
        if not picking_type:
            picking_type = self.env["stock.picking.type"].create({
                "name": "Delivery Orders",
                "sequence_code": "OUT",
                "code": "outgoing",
                "company_id": self.company.id,
            })
        location_src = self.env["stock.location"].search([("company_id", "=", self.company.id)], limit=1)
        if not location_src:
            location_src = self.env["stock.location"].create({
                "name": "Stock Location",
                "usage": "internal",
                "company_id": self.company.id,
            })
        location_dest = self.env.ref("stock.stock_location_customers")

        # Create 2 delivery orders under the same trip TRIP-01
        picking1 = self.env["stock.picking"].sudo().create({
            "name": "DO-FMCG-001",
            "origin": "TRIP-01",
            "partner_id": self.outlet.id,
            "picking_type_id": picking_type.id,
            "location_id": location_src.id,
            "location_dest_id": location_dest.id,
            "company_id": self.company.id,
            "state": "assigned",
            "scheduled_date": fields.Datetime.now(),
            "user_id": self.mobile.id,
        })

        outlet2 = self.env["res.partner"].create({
            "name": "API Scheduled Outlet 2",
            "company_id": self.company.id,
            "user_id": self.mobile.id,
        })
        picking2 = self.env["stock.picking"].sudo().create({
            "name": "DO-FMCG-002",
            "origin": "TRIP-01",
            "partner_id": outlet2.id,
            "picking_type_id": picking_type.id,
            "location_id": location_src.id,
            "location_dest_id": location_dest.id,
            "company_id": self.company.id,
            "state": "assigned",
            "scheduled_date": fields.Datetime.now(),
            "user_id": self.mobile.id,
        })
        self.env.cr.execute(
            "UPDATE stock_picking SET state = 'assigned' WHERE id IN %s",
            (tuple([picking1.id, picking2.id]),),
        )
        picking1.invalidate_recordset(["state"])
        picking2.invalidate_recordset(["state"])

        pod_evidence_uuid1 = str(uuid.uuid4())
        self.env["id.mobile.evidence"].sudo().create({
            "user_id": self.mobile.id,
            "company_id": self.company.id,
            "outlet_id": self.outlet.id,
            "client_uuid": pod_evidence_uuid1,
            "fingerprint": "pod-evidence-fingerprint-1",
            "receipt_json": json.dumps({
                "business_date": day_str,
                "original_sha256": "pod-hash-01",
            }),
            "original": dummy_base64,
            "watermarked": dummy_base64,
        })

        # Counterexample: DO exists, but submitted with fabricated trip origin -> UserError
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "delivery.pod.submit",
                "payload": {
                    "source": {"trip": "TRIP-FABRICATED", "id": picking1.name, "outlet_id": str(self.outlet.id)},
                    "recipient": "Budi",
                    "evidence": {"id": pod_evidence_uuid1, "packageHash": "pod-hash-01"},
                },
            })

        # Counterexample: Outlet 2 not in assignment yet -> UserError
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "delivery.pod.submit",
                "payload": {
                    "source": {"trip": "TRIP-01", "id": picking2.name, "outlet_id": str(outlet2.id)},
                    "recipient": "Andi",
                    "evidence": {"id": pod_evidence_uuid1, "packageHash": "pod-hash-01"},
                },
            })

        # Assign outlet2 to mobile workday
        self.assignment.outlet_ids = [Command.link(outlet2.id)]

        # Counterexample: Submitting DO 2 with evidence created for Outlet 1 -> UserError
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "delivery.pod.submit",
                "payload": {
                    "source": {"trip": "TRIP-01", "id": picking2.name, "outlet_id": str(outlet2.id)},
                    "recipient": "Andi",
                    "evidence": {"id": pod_evidence_uuid1, "packageHash": "pod-hash-01"},
                },
            })

        # Counterexample: DO cancelled -> UserError
        picking_cancelled = self.env["stock.picking"].sudo().create({
            "name": "DO-FMCG-CANCELLED",
            "origin": "TRIP-01",
            "partner_id": self.outlet.id,
            "picking_type_id": picking_type.id,
            "location_id": location_src.id,
            "location_dest_id": location_dest.id,
            "company_id": self.company.id,
            "state": "cancel",
            "scheduled_date": fields.Datetime.now(),
            "user_id": self.mobile.id,
        })
        self.env.cr.execute(
            "UPDATE stock_picking SET state = 'cancel' WHERE id = %s",
            (picking_cancelled.id,),
        )
        picking_cancelled.invalidate_recordset(["state"])
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "delivery.pod.submit",
                "payload": {
                    "source": {"trip": "TRIP-01", "id": picking_cancelled.name, "outlet_id": str(self.outlet.id)},
                    "recipient": "Budi",
                    "evidence": {"id": pod_evidence_uuid1, "packageHash": "pod-hash-01"},
                },
            })

        # Counterexample: DO draft -> UserError
        picking_draft = self.env["stock.picking"].sudo().create({
            "name": "DO-FMCG-DRAFT",
            "origin": "TRIP-01",
            "partner_id": self.outlet.id,
            "picking_type_id": picking_type.id,
            "location_id": location_src.id,
            "location_dest_id": location_dest.id,
            "company_id": self.company.id,
            "state": "draft",
            "scheduled_date": fields.Datetime.now(),
            "user_id": self.mobile.id,
        })
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "delivery.pod.submit",
                "payload": {
                    "source": {"trip": "TRIP-01", "id": picking_draft.name, "outlet_id": str(self.outlet.id)},
                    "recipient": "Budi",
                    "evidence": {"id": pod_evidence_uuid1, "packageHash": "pod-hash-01"},
                },
            })

        # Counterexample: Stale / historical scheduled date (July 2026) -> UserError
        picking_stale = self.env["stock.picking"].sudo().create({
            "name": "DO-FMCG-HISTORIS",
            "origin": "TRIP-01",
            "partner_id": self.outlet.id,
            "picking_type_id": picking_type.id,
            "location_id": location_src.id,
            "location_dest_id": location_dest.id,
            "company_id": self.company.id,
            "state": "assigned",
            "scheduled_date": datetime(2026, 7, 15, 8, 0, 0),
            "user_id": self.mobile.id,
        })
        self.env.cr.execute(
            "UPDATE stock_picking SET state = 'assigned' WHERE id = %s",
            (picking_stale.id,),
        )
        picking_stale.invalidate_recordset(["state"])
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "delivery.pod.submit",
                "payload": {
                    "source": {"trip": "TRIP-01", "id": picking_stale.name, "outlet_id": str(self.outlet.id)},
                    "recipient": "Budi",
                    "evidence": {"id": pod_evidence_uuid1, "packageHash": "pod-hash-01"},
                },
            })

        # Counterexample: Non-outgoing picking type (e.g. incoming) -> UserError
        picking_type_in = self.env["stock.picking.type"].create({
            "name": "Incoming Receipts",
            "sequence_code": "IN",
            "code": "incoming",
            "company_id": self.company.id,
        })
        picking_incoming = self.env["stock.picking"].sudo().create({
            "name": "IN-FMCG-001",
            "origin": "TRIP-01",
            "partner_id": self.outlet.id,
            "picking_type_id": picking_type_in.id,
            "location_id": location_src.id,
            "location_dest_id": location_dest.id,
            "company_id": self.company.id,
            "state": "assigned",
            "scheduled_date": fields.Datetime.now(),
            "user_id": self.mobile.id,
        })
        self.env.cr.execute(
            "UPDATE stock_picking SET state = 'assigned' WHERE id = %s",
            (picking_incoming.id,),
        )
        picking_incoming.invalidate_recordset(["state"])
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "delivery.pod.submit",
                "payload": {
                    "source": {"trip": "TRIP-01", "id": picking_incoming.name, "outlet_id": str(self.outlet.id)},
                    "recipient": "Budi",
                    "evidence": {"id": pod_evidence_uuid1, "packageHash": "pod-hash-01"},
                },
            })

        # Counterexample: DO assigned to another courier -> UserError
        other_courier = self.env["res.users"].create({
            "name": "Other Courier",
            "login": "courier2@fmcg.example",
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
        })
        picking_other_courier = self.env["stock.picking"].sudo().create({
            "name": "DO-FMCG-COURIER2",
            "origin": "TRIP-01",
            "partner_id": self.outlet.id,
            "picking_type_id": picking_type.id,
            "location_id": location_src.id,
            "location_dest_id": location_dest.id,
            "company_id": self.company.id,
            "state": "assigned",
            "scheduled_date": fields.Datetime.now(),
            "user_id": other_courier.id,
        })
        self.env.cr.execute(
            "UPDATE stock_picking SET state = 'assigned' WHERE id = %s",
            (picking_other_courier.id,),
        )
        picking_other_courier.invalidate_recordset(["state"])
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "delivery.pod.submit",
                "payload": {
                    "source": {"trip": "TRIP-01", "id": picking_other_courier.name, "outlet_id": str(self.outlet.id)},
                    "recipient": "Budi",
                    "evidence": {"id": pod_evidence_uuid1, "packageHash": "pod-hash-01"},
                },
            })

        # 3. Positive POD submission for DO 1 matching frontend DeliveryPodSchema
        pod_uuid1 = str(uuid.uuid4())
        rc_pod1 = model.process_command({
            "client_uuid": pod_uuid1,
            "type": "delivery.pod.submit",
            "payload": {
                "pod_version": 1,
                "source": {
                    "id": picking1.name,
                    "trip": "TRIP-01",
                    "outlet_id": str(self.outlet.id),
                },
                "recipient": "Budi Santoso",
                "outcome": "delivered",
                "lines": [{"id": "1", "received": 2}],
                "evidence": {
                    "id": pod_evidence_uuid1,
                    "packageHash": "pod-hash-01",
                },
            },
        })
        self.assertEqual(rc_pod1["status"], "accepted")
        self.assertEqual(rc_pod1["reference"], f"POD-{pod_uuid1[:8]}")

        # Counterexample: Trip close attempted while DO 2 in TRIP-01 is still missing POD -> UserError
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "delivery.trip.close",
                "payload": {
                    "trip_id": "TRIP-01",
                    "business_date": day_str,
                    "pod_uuids": [pod_uuid1],
                },
            })

        # 4. Create valid evidence for DO 2 and submit POD 2
        pod_evidence_uuid2 = str(uuid.uuid4())
        self.env["id.mobile.evidence"].sudo().create({
            "user_id": self.mobile.id,
            "company_id": self.company.id,
            "outlet_id": outlet2.id,
            "client_uuid": pod_evidence_uuid2,
            "fingerprint": "pod-evidence-fingerprint-2",
            "receipt_json": json.dumps({
                "business_date": day_str,
                "original_sha256": "pod-hash-02",
            }),
            "original": dummy_base64,
            "watermarked": dummy_base64,
        })

        pod_uuid2 = str(uuid.uuid4())
        rc_pod2 = model.process_command({
            "client_uuid": pod_uuid2,
            "type": "delivery.pod.submit",
            "payload": {
                "pod_version": 1,
                "source": {
                    "id": picking2.name,
                    "trip": "TRIP-01",
                    "outlet_id": str(outlet2.id),
                },
                "recipient": "Andi Wijaya",
                "outcome": "delivered",
                "lines": [{"id": "1", "received": 5}],
                "evidence": {
                    "id": pod_evidence_uuid2,
                    "packageHash": "pod-hash-02",
                },
            },
        })
        self.assertEqual(rc_pod2["status"], "accepted")

        # 5. Trip close without PODs or nonexistent trip -> rejected
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "delivery.trip.close",
                "payload": {"trip_id": "NONEXISTENT-TRIP"},
            })

        # 6. Trip close with invalid/foreign POD UUID -> rejected
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "delivery.trip.close",
                "payload": {
                    "trip_id": "TRIP-01",
                    "pod_uuids": [str(uuid.uuid4())],
                },
            })

        # 7. Positive trip close proving all submitted PODs for all DOs in TRIP-01
        close_uuid = str(uuid.uuid4())
        rc_close = model.process_command({
            "client_uuid": close_uuid,
            "type": "delivery.trip.close",
            "payload": {
                "trip_id": "TRIP-01",
                "business_date": day_str,
                "pod_uuids": [pod_uuid1, pod_uuid2],
            },
        })
        self.assertEqual(rc_close["status"], "accepted")

    def test_unsupported_commands_fail_closed(self):
        """Unimplemented domains (collection, hris, expense) fail closed with UserError."""
        model = self._command_model()
        for cmd_type in ("collection.receipt.submit", "hris.attendance.capture", "field_expense.request"):
            with self.assertRaises(UserError):
                model.process_command({
                    "client_uuid": str(uuid.uuid4()),
                    "type": cmd_type,
                    "payload": {},
                })


@tagged("post_install", "-at_install")
class TestMobileCommandsHttp(MobileFixture, HttpCase):

    def test_http_csrf_and_role_protection(self):
        """Validates CSRF token verification, auth gates, and command HTTP route responses."""
        url = "/api/v1/sync/commands"
        snapshot_payload = self.env["id.mobile.workday"].with_user(self.mobile).with_context(
            allowed_company_ids=self.mobile.company_ids.ids
        )._snapshot_payload()
        snapshot_version = snapshot_payload["version"]

        cmd = {
            "client_uuid": str(uuid.uuid4()),
            "type": "sales.order.submit",
            "payload": {
                "outlet_id": str(self.outlet.id),
                "snapshot_version": snapshot_version,
                "lines": [{"product_id": str(self.product.id), "qty": "1", "uom": "carton"}],
            },
        }
        body = json.dumps(cmd)

        # 1. Unauthenticated -> 401
        res = self.url_open(url, data=body)
        self.assertEqual(res.status_code, 401)

        # 2. Portal user -> 403
        self.authenticate(self.portal.login, "mobile-api-portal")
        res = self.url_open(url, data=body)
        self.assertEqual(res.status_code, 403)

        # 3. Mobile user without CSRF token -> 400
        self.authenticate(self.mobile.login, "mobile-api-test")
        res = self.url_open(url, data=body)
        self.assertEqual(res.status_code, 400)

        # 4. Mobile user with wrong CSRF token -> 400
        res = self.url_open(url, data=body, headers={"X-CSRF-Token": "invalid-csrf-token"})
        self.assertEqual(res.status_code, 400)

        # 5. Mobile user with valid CSRF token obtained from bootstrap
        bootstrap = self.url_open("/api/v1/me/bootstrap")
        self.assertEqual(bootstrap.status_code, 200)
        csrf = bootstrap.json()["csrfToken"]
        self.assertTrue(csrf)

        # Empty body via raw POST -> 400
        url_full = self.base_url() + url
        res = self.opener.post(url_full, data="", headers={"X-CSRF-Token": csrf})
        self.assertEqual(res.status_code, 400)

        # Missing client_uuid -> 422
        res = self.url_open(url, data=json.dumps({"type": "sales.order.submit"}), headers={"X-CSRF-Token": csrf})
        self.assertEqual(res.status_code, 422)

        # Valid submission -> 200
        res = self.url_open(url, data=body, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res.status_code, 200)
        receipt = res.json()
        self.assertEqual(receipt["client_uuid"], cmd["client_uuid"])
        self.assertIn(receipt["status"], ["accepted", "needs_approval"])
