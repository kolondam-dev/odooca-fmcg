import json
import uuid
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from ..models.delivery_cohort import local_day


@tagged("post_install", "-at_install")
class TestPodAttempt(TransactionCase):
    def test_redacted_projection_corrections_reasons_and_role(self):
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        partner = self.env["res.partner"].create({"name": "POD projection outlet"})
        picking = self.env["stock.picking"].create({"picking_type_id": warehouse.out_type_id.id,
            "partner_id": partner.id, "origin": "POD-TRIP", "location_id": warehouse.lot_stock_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id})
        def command(outcome, parent=None, reason=None):
            at = fields.Datetime.now()+timedelta(seconds=1 if parent else 0)
            data = {"source": {"id": picking.name, "trip": picking.origin, "outlet_id": str(partner.id),
                    "business_date": str(local_day(at)), "version": "one-manifest"},
                    "recipient": "PRIVATE RECIPIENT", "evidence": {"private_url": "PRIVATE MEDIA"},
                    "outcome": outcome, "do_reason": reason,
                    "lines": [{"item_reason": "ITEM RUSAK"}] if reason else []}
            if parent:
                data["supersedes_uuid"] = parent.client_uuid
            return self.env["id.mobile.command"].create({"client_uuid": str(uuid.uuid4()),
                "command_type": "delivery.pod.submit", "fingerprint": "fixture", "user_id": self.env.uid,
                "company_id": self.env.company.id, "payload_json": json.dumps({"payload": data}),
                "occurred_at": at, "status": "accepted"})
        first = command("partial", reason="TOKO TUTUP")
        Projection = self.env["id.delivery.attempt"]
        report = Projection._for_deliveries(picking.ids)
        self.assertEqual(report["outcomes"], {"partial": 1})
        self.assertEqual(report["item_reasons"], {"ITEM RUSAK": 1})
        second = command("delivered", first)
        report = Projection._for_deliveries(picking.ids)
        self.assertEqual((report["attempts"], report["corrections"]), (1, 1))
        self.assertEqual(report["outcomes"], {"delivered": 1})
        self.assertFalse(report["item_reasons"])
        self.assertEqual(report["first_events"][0]["accepted_at"], str(first.occurred_at))
        user = self.env["res.users"].with_context(no_reset_password=True).create({"name": "POD warehouse reader",
            "login": "pod_warehouse_reader", "group_ids": [(6, 0, [self.env.ref("stock.group_stock_user").id])]})
        redacted = Projection.with_user(user).search([("id", "=", second.id)]).read()[0]
        self.assertNotIn("PRIVATE", json.dumps(redacted, default=str))
        with self.assertRaises(AccessError):
            self.env["id.mobile.command"].with_user(user).search([])
        command("rejected", first)  # a fork is unavailable, not whichever leaf happens to be latest
        report = Projection._for_deliveries(picking.ids)
        self.assertEqual(report["attempts"], 0)
        self.assertGreater(report["invalid_lineage"], 0)

    def test_malformed_payload_and_cross_company_do_not_leak(self):
        foreign = self.env["res.company"].create({"name": "POD foreign"})
        cmd = self.env["id.mobile.command"].create({"client_uuid": str(uuid.uuid4()),
            "command_type": "delivery.pod.submit", "fingerprint": "malformed", "user_id": self.env.uid,
            "company_id": foreign.id, "payload_json": "not JSON", "status": "accepted"})
        view = self.env["id.delivery.attempt"]
        self.assertFalse(view.with_context(allowed_company_ids=self.env.company.ids).search([("id", "=", cmd.id)]))
        row = view.with_context(allowed_company_ids=foreign.ids).browse(cmd.id)
        self.assertFalse(row.binding_valid)
        self.assertEqual(row.outcome, "unclassified")
