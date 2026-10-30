from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..staging import _provision_records, provision
from .test_read_api import MobileFixture


@tagged("post_install", "-at_install")
class TestOfficeMap(MobileFixture, TransactionCase):
    def test_office_master_scope_acl_and_snapshot_binding(self):
        office = self.env["id.mobile.office"].create(
            {
                "name": "Office Master",
                "company_id": self.company.id,
                "latitude": 1.465,
                "longitude": 124.833,
                "radius": 50,
                "coordinate_status": "unverified",
                "coordinate_note": "Owner coordinates pending field verification",
            }
        )
        self.assignment.office_id = office
        service = (
            self.env["id.mobile.workday"].with_user(self.mobile).with_context(allowed_company_ids=self.company.ids)
        )
        snapshot = service._snapshot_payload()
        self.assertEqual(snapshot["office"]["id"], str(office.id))
        self.assertEqual(snapshot["office"]["coordinate_status"], "unverified")
        self.assertNotIn("coordinate_note", snapshot["office"])
        with self.assertRaises(AccessError):
            office.with_user(self.mobile).write({"coordinate_status": "verified"})
        with self.assertRaises(AccessError):
            office.with_user(self.mobile).unlink()
        with self.assertRaises(AccessError):
            self.env["id.mobile.office"].with_user(self.mobile).create({"name": "Spoofed office"})
        office.coordinate_status = "verified"
        self.assertNotEqual(snapshot["version"], service._snapshot_payload()["version"])
        office.active = False
        with self.assertRaises(UserError):
            service._snapshot_payload()

    def test_foreign_office_and_invalid_coordinates_are_rejected(self):
        office = self.env["id.mobile.office"].create(
            {
                "name": "Foreign Office",
                "company_id": self.foreign.id,
                "latitude": -6.2,
                "longitude": 106.8,
                "coordinate_note": "Test location",
                "coordinate_status": "test",
            }
        )
        with self.assertRaises(AccessError):
            office.with_user(self.mobile).read(["latitude"])
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.assignment.office_id = office
        for values in ({"latitude": 91}, {"longitude": 181}, {"radius": 501}, {"coordinate_note": " "}):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                office.write(values)

    def test_provisioning_requires_explicit_disposable_database_before_mutation(self):
        before = self.env["res.users"].search_count([])
        for expected, flag in ((self.env.cr.dbname, "YES"), ("fmcg_staging_remote", "NO"), ("production", "YES")):
            with self.assertRaises(AccessError):
                provision(
                    self.env,
                    expected_database=expected,
                    disposable=flag,
                    passwords=["test-password-one", "test-password-two"],
                )
        self.assertEqual(self.env["res.users"].search_count([]), before)

    def test_disposable_fixture_orm_is_repeatable_and_has_no_business_write(self):
        # The actual CI DB is ci_db, so invoke only the private record builder here.
        # The public guard above is deliberately not bypassed or weakened.
        passwords = ["test-password-one", "test-password-two"]
        first = _provision_records(self.env, passwords=passwords)
        again = _provision_records(self.env, passwords=passwords)
        self.assertEqual(first, again)
        self.assertNotEqual(first[0]["outlet_id"], first[1]["outlet_id"])
        for item in first:
            user = self.env["res.users"].browse(item["user_id"])
            self.assertFalse(user.has_group("base.group_system"))
            self.assertTrue(user.has_group("id_mobile_api.group_mobile_evidence"))
            with self.assertRaises(AccessError):
                self.env["sale.order"].with_user(user).create({"partner_id": item["outlet_id"]})
            self.assertEqual(
                self.env["id.mobile.workday"]
                .with_user(user)
                .with_context(allowed_company_ids=user.company_ids.ids)
                ._snapshot_payload()["office"]["coordinate_status"],
                "test",
            )
        # Fixture does not hijack or reset somebody else's account with the same login.
        marker = self.env["ir.model.data"].search([("module", "=", "id_mobile_api_staging"), ("name", "=", "user_1")])
        marker.unlink()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            _provision_records(self.env, passwords=passwords)

    def test_rollover_rejects_provisioning_summary(self):
        with patch(
            "odoo.addons.id_mobile_api.models.mobile_workday.business_date",
            return_value=self.assignment.business_date.replace(year=2025),
        ):
            with self.assertRaises(UserError), self.env.cr.savepoint():
                _provision_records(self.env, passwords=["test-password-one", "test-password-two"])
