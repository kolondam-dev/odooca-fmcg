import json
import uuid
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, tagged
from ..models.mobile_workday import MobileReadConflict
from .test_read_api import MobileFixture


@tagged("post_install", "-at_install")
class TestMobileCommandsApi(MobileFixture, TransactionCase):

    def setUp(self):
        super().setUp()
        self.assignment.write({
            "outlet_radius": 100,
        })

    def _command_model(self, user=None):
        target_user = user or self.mobile
        return self.env["id.mobile.command"].with_user(target_user).with_company(self.company)

    def test_actor_model_guard(self):
        """Direct ORM/RPC call without mobile sales privileges must fail closed."""
        valid_uuid = str(uuid.uuid4())
        cmd = {
            "client_uuid": valid_uuid,
            "type": "sales.order.submit",
            "payload": {
                "outlet_id": str(self.outlet.id),
                "lines": [{"product_id": str(self.product.id), "qty": "1", "uom": "carton"}],
            },
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
            "payload": {
                "outlet_id": str(self.outlet.id),
                "lines": [{"product_id": str(self.product.id), "qty": "1", "uom": "carton"}],
            },
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

        # System admin can audit commands
        admin = self.env.ref("base.user_admin")
        admin_records = self.env["id.mobile.command"].with_user(admin).search([
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
            "payload": {
                "outlet_id": str(self.outlet.id),
                "lines": [{"product_id": str(self.product.id), "qty": "1", "uom": "carton"}],
            },
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
            "payload": {
                "outlet_id": str(self.outlet.id),
                "lines": [{"product_id": str(self.product.id), "qty": "99", "uom": "carton"}],
            },
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

    def test_scope_and_snapshot_guards(self):
        """Orders outside scheduled outlet, unassigned SKU, or with stale snapshot must be rejected."""
        model = self._command_model()

        # Unassigned outlet
        unassigned_outlet = self.env["res.partner"].create({
            "name": "Unassigned Outlet",
            "company_id": self.company.id,
        })
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.order.submit",
                "payload": {
                    "outlet_id": str(unassigned_outlet.id),
                    "lines": [{"product_id": str(self.product.id), "qty": "1", "uom": "carton"}],
                },
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
        })
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.order.submit",
                "payload": {
                    "outlet_id": str(self.outlet.id),
                    "lines": [{"product_id": str(unassigned_product.id), "qty": "1", "uom": "carton"}],
                },
            })

        # Stale snapshot version
        with self.assertRaises(MobileReadConflict):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.order.submit",
                "payload": {
                    "outlet_id": str(self.outlet.id),
                    "snapshot_version": "odoo-read-v1:stale-version-hash",
                    "lines": [{"product_id": str(self.product.id), "qty": "1", "uom": "carton"}],
                },
            })

    def test_atomic_split_so_savepoint_rollback(self):
        """When multi-principal split SO encounters a failure, all generated SOs and logs must roll back cleanly."""
        # Create second principal and product
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

        cmd_uuid = str(uuid.uuid4())
        command = {
            "client_uuid": cmd_uuid,
            "type": "sales.order.submit",
            "payload": {
                "outlet_id": str(self.outlet.id),
                "lines": [
                    {"product_id": str(self.product.id), "qty": "1", "uom": "carton"},
                    {"product_id": str(product2.id), "qty": "2", "uom": "carton"},
                ],
            },
        }

        # Mock failure during second SaleOrder creation
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

        # Assert zero SOs persisted and zero command records persisted
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
        })
        self.assignment.product_ids = [Command.link(product2.id)]

        cmd_uuid = str(uuid.uuid4())
        command = {
            "client_uuid": cmd_uuid,
            "type": "sales.order.submit",
            "payload": {
                "outlet_id": str(self.outlet.id),
                "customer_po_number": "PO-SPLIT-001",
                "lines": [
                    {"product_id": str(self.product.id), "qty": "2", "uom": "carton", "discount": 10},
                    {"product_id": str(product2.id), "qty": "3", "uom": "carton", "discount": 5},
                ],
            },
        }

        model = self._command_model()
        rc = model.process_command(command)
        self.assertEqual(rc["status"], "accepted")

        orders = self.env["sale.order"].sudo().search([("origin", "=", f"PWA Mobile Order {cmd_uuid[:8]}")])
        self.assertEqual(len(orders), 2, "Must create 2 distinct SOs for 2 principals.")
        self.assertTrue(all(so.client_order_ref == "PO-SPLIT-001" for so in orders))

    def test_visit_checkin_requires_evidence(self):
        """Visit check-in without evidence or invalid evidence is rejected fail-closed."""
        model = self._command_model()

        # Check-in without evidence
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.visit.check_in",
                "payload": {"outlet_id": str(self.outlet.id)},
            })

        # Check-in with nonexistent evidence
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "sales.visit.check_in",
                "payload": {
                    "outlet_id": str(self.outlet.id),
                    "evidence_uuid": str(uuid.uuid4()),
                },
            })

        # Positive check-in with stored evidence
        evidence_uuid = str(uuid.uuid4())
        self.env["id.mobile.evidence"].sudo().create({
            "user_id": self.mobile.id,
            "company_id": self.company.id,
            "outlet_id": self.outlet.id,
            "client_uuid": evidence_uuid,
            "fingerprint": "fake-evidence-fingerprint",
            "receipt_json": json.dumps({"status": "accepted"}),
            "original": b"fake-jpg",
            "watermarked": b"fake-jpg-wm",
        })
        rc = model.process_command({
            "client_uuid": str(uuid.uuid4()),
            "type": "sales.visit.check_in",
            "payload": {
                "outlet_id": str(self.outlet.id),
                "evidence_uuid": evidence_uuid,
            },
        })
        self.assertEqual(rc["status"], "accepted")

    def test_delivery_pod_validation(self):
        """Delivery POD submit requires trip identity and proof."""
        model = self._command_model()

        # Empty payload
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "delivery.pod.submit",
                "payload": {},
            })

        # Missing trip_id
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "delivery.pod.submit",
                "payload": {"evidence_uuid": str(uuid.uuid4())},
            })

        # Missing evidence
        with self.assertRaises(UserError):
            model.process_command({
                "client_uuid": str(uuid.uuid4()),
                "type": "delivery.pod.submit",
                "payload": {"trip_id": "TRIP-123"},
            })

        # Valid POD
        pod_uuid = str(uuid.uuid4())
        rc = model.process_command({
            "client_uuid": pod_uuid,
            "type": "delivery.pod.submit",
            "payload": {"trip_id": "TRIP-123", "evidence_uuid": str(uuid.uuid4())},
        })
        self.assertEqual(rc["status"], "accepted")
        self.assertEqual(rc["reference"], f"POD-{pod_uuid[:8]}")


@tagged("post_install", "-at_install")
class TestMobileCommandsHttp(MobileFixture, HttpCase):

    def test_http_csrf_and_role_protection(self):
        """Validates CSRF token verification, auth gates, and command HTTP route responses."""
        url = "/api/v1/sync/commands"
        cmd = {
            "client_uuid": str(uuid.uuid4()),
            "type": "sales.order.submit",
            "payload": {
                "outlet_id": str(self.outlet.id),
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

        # Empty body -> 400
        res = self.url_open(url, data="", headers={"X-CSRF-Token": csrf})
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
