"""DEV-02A: exercise the Android-facing endpoints on Odoo's real HTTP server."""
import json
import logging
from uuid import uuid4

from freezegun import freeze_time

from odoo import Command
from odoo.tests import HttpCase, tagged

from .test_read_api import MobileFixture

_logger = logging.getLogger(__name__)
BOOTSTRAP = "/api/v1/me/bootstrap"
SNAPSHOT = "/api/v1/sync/snapshot"
COMMANDS = "/api/v1/sync/commands"
LOGIN = "/web/session/authenticate"


@tagged("post_install", "-at_install")
class TestDev02aHarness(MobileFixture, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other_outlet = cls.outlet.copy({"name": "TEST B Outlet", "user_id": cls.other.id})
        cls.other_product = cls.env["product.product"].create({
            "name": "TEST B Product", "default_code": "TEST-B", "principal_id": cls.principal.id,
            "company_id": False, "uom_id": cls.product.uom_id.id, "list_price": 1000,
            "carton_qty": 24, "inner_qty": 6, "type": "consu", "is_storable": True,
            "taxes_id": [Command.clear()],
        })
        cls.office = cls.env["id.mobile.office"].create({
            "name": "TEST Office",
            "company_id": cls.company.id,
            "latitude": 1.46,
            "longitude": 124.83,
            "coordinate_status": "test",
            "coordinate_note": "Synthetic DEV-02A fixture",
        })
        cls.assignment.office_id = cls.office
        cls.other_assignment = cls.assignment.copy({
            "user_id": cls.other.id,
            "outlet_ids": [Command.set(cls.other_outlet.ids)],
            "product_ids": [Command.set(cls.other_product.ids)],
        })

    def _evidence(self, scenario, **fields):
        # Allowlisted facts only. Never serialize raw HTTP bodies, headers, or sessions.
        _logger.info("DEV02A_EVIDENCE %s", json.dumps({"scenario": scenario, **fields}, sort_keys=True))

    def _login(self, actor, fixture_password, label):
        self.authenticate(None, None)
        response = self.url_open(LOGIN, json=self.build_rpc_payload({
            "db": self.env.cr.dbname,
            "login": actor.login,
            "password": fixture_password,
        }))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("result", {}).get("uid"), actor.id)
        self._evidence("login", method="POST", route=LOGIN, http=200, actor=label)
        response = self.url_open(BOOTSTRAP)
        self.assertEqual(response.status_code, 200)
        bootstrap = response.json()
        self.assertEqual(bootstrap["id"], str(actor.id))
        self.assertTrue(bootstrap["csrfToken"])
        self._evidence("bootstrap", method="GET", route=BOOTSTRAP, http=200, actor=label,
                       business_date=bootstrap["businessDate"])
        return bootstrap["csrfToken"]

    def _snapshot(self, actor, assignment, day):
        response = self.url_open(SNAPSHOT)
        self.assertEqual(response.status_code, 200)
        snapshot = response.json()
        self.assertEqual(snapshot["scope"], {
            "user_id": str(actor.id),
            "company_id": str(self.company.id),
            "warehouse_id": str(self.warehouse.id),
            "business_date": day,
        })
        self.assertEqual([row["id"] for row in snapshot["outlets"]], [str(assignment.outlet_ids.id)])
        self.assertEqual([row["id"] for row in snapshot["products"]], [str(assignment.product_ids.id)])
        self.assertEqual(snapshot["office"]["id"], str(self.office.id))
        self.assertEqual(snapshot["office"]["coordinate_status"], "test")
        return snapshot["version"]

    def _submit(self, csrf, command):
        return self.url_open(COMMANDS, json=command, headers={"X-CSRF-Token": csrf})

    def test_login_snapshot_command_and_access_boundaries(self):
        ledger = self.env["id.mobile.command"].sudo()
        before = "2026-11-16T15:59:00Z"
        after = "2026-11-16T16:00:01Z"
        installed = self.env["ir.module.module"].search([
            ("name", "in", ["id_base", "id_mobile_api", "id_approval"]), ("state", "=", "installed"),
        ])
        self.assertEqual(set(installed.mapped("name")), {"id_base", "id_mobile_api", "id_approval"})
        self._evidence("installed_addons", versions={mod.name: mod.latest_version for mod in installed})

        with freeze_time(before, tick=True) as clock:
            self.authenticate(None, None)
            response = self.url_open(SNAPSHOT)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["error"], "not_authenticated")
            self._evidence("unauthenticated", method="GET", route=SNAPSHOT, http=401,
                           error="not_authenticated")

            self._login(self.other, "mobile-api-other", "TEST B")
            self._snapshot(self.other, self.other_assignment, "2026-11-16")
            response = self.url_open(f"/api/v1/outlets/{self.outlet.id}/image")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["error"], "forbidden")
            self._evidence("other_account_scope", actor="TEST B", method="GET",
                           route="/api/v1/outlets/{outlet_id}/image", http=403,
                           own_snapshot_http=200, error="forbidden")

            csrf = self._login(self.mobile, "mobile-api-test", "TEST A")
            version = self._snapshot(self.mobile, self.assignment, "2026-11-16")
            self._evidence("snapshot", actor="TEST A", method="GET", route=SNAPSHOT, http=200,
                           business_date="2026-11-16", version=version, utc=before,
                           catalog_items=1, outlets=1, office="test")
            command = {
                "client_uuid": str(uuid4()),
                "type": "sales.order.submit",
                "payload": {
                    "snapshot_version": version,
                    "outlet_id": str(self.outlet.id),
                    "lines": [{"product_id": str(self.product.id), "qty": "1", "uom": "carton"}],
                },
            }
            response = self._submit(csrf, command)
            self.assertEqual(response.status_code, 200)
            receipt = response.json()
            self.assertEqual(receipt["client_uuid"], command["client_uuid"])
            self.assertIn(receipt["status"], {"accepted", "needs_approval"})
            self.assertTrue(receipt["reference"])
            self.env.invalidate_all()
            record = ledger.search([("client_uuid", "=", command["client_uuid"])])
            self.assertEqual(len(record), 1)
            self.assertEqual(record.user_id, self.mobile)
            self.assertEqual(record.company_id, self.company)
            self.assertEqual(record.status, receipt["status"])
            self.assertEqual(record.reference, receipt["reference"])
            self.assertEqual(len(record.sale_order_ids), 1)
            self.assertEqual(record.sale_order_ids.name, receipt["reference"])
            self._evidence("command_receipt", method="POST", route=COMMANDS, http=200,
                           request=command,
                           receipt={key: receipt[key] for key in ("client_uuid", "status", "reference")})

            clock.move_to(after)
            next_version = self._snapshot(self.mobile, self.assignment, "2026-11-17")
            self.assertNotEqual(next_version, version)
            stale = {**command, "client_uuid": str(uuid4())}
            response = self._submit(csrf, stale)
            self.assertEqual(response.status_code, 409)
            self.assertFalse(ledger.search_count([("client_uuid", "=", stale["client_uuid"])]))
            self._evidence("wita_rollover", method="GET", route=SNAPSHOT, http=200,
                           before_wita="2026-11-16T23:59:00+08:00",
                           after_wita="2026-11-17T00:00:01+08:00", after_utc=after,
                           business_date="2026-11-17", version=next_version, stale_command_http=409)

            self.env.invalidate_all()
            today = self.env["id.mobile.workday"].search([
                ("user_id", "=", self.mobile.id),
                ("company_id", "=", self.company.id),
                ("business_date", "=", "2026-11-17"),
            ])
            today.ensure_one()
            today.active = False
            response = self.url_open(SNAPSHOT)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["error"], "forbidden")
            revoked = {
                **stale,
                "client_uuid": str(uuid4()),
                "payload": {**command["payload"], "snapshot_version": next_version},
            }
            response = self._submit(csrf, revoked)
            self.assertEqual(response.status_code, 403)
            self.assertFalse(ledger.search_count([("client_uuid", "=", revoked["client_uuid"])]))
            self._evidence("scope_revoked", method="GET", route=SNAPSHOT, http=403,
                           command_http=403, same_session=True, command_persisted=False)
