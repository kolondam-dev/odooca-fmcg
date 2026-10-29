from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tests.common import new_test_user

from ..models.mobile_workday import business_date, MobileReadConflict


class MobileFixture:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        currency = cls.env.ref("base.IDR")
        currency.active = True
        cls.company = cls.env["res.company"].create({"name": "Mobile API Company", "currency_id": currency.id})
        cls.foreign = cls.env["res.company"].create({"name": "Mobile API Foreign", "currency_id": currency.id})
        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        if not cls.warehouse:
            cls.warehouse = cls.env["stock.warehouse"].create({
                "name": "Mobile Stock", "code": "MBL", "company_id": cls.company.id,
            })
        cls.other_warehouse = cls.env["stock.warehouse"].create({
            "name": "Not Assigned", "code": "MBLX", "company_id": cls.company.id,
        })
        cls.foreign_warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.foreign.id)], limit=1)
        if not cls.foreign_warehouse:
            cls.foreign_warehouse = cls.env["stock.warehouse"].create({
                "name": "Foreign Stock", "code": "FRGN", "company_id": cls.foreign.id,
            })
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Mobile IDR", "currency_id": currency.id, "company_id": cls.company.id,
        })
        cls.mobile = new_test_user(
            cls.env, login="mobile-api-sales", password="mobile-api-test", groups="id_mobile_api.group_mobile_sales",
            company_id=cls.company.id,
        )
        cls.other = new_test_user(
            cls.env, login="mobile-api-other", groups="id_mobile_api.group_mobile_sales", company_id=cls.company.id,
        )
        cls.internal = new_test_user(cls.env, login="mobile-api-denied", company_id=cls.company.id)
        cls.portal = new_test_user(cls.env, login="mobile-api-portal", groups="base.group_portal")
        cls.principal = cls.env["id.principal"].create({"name": "API Principal", "code": "API-TEST"})
        unit = cls.env.ref("uom.product_uom_unit")
        cls.product = cls.env["product.product"].create({
            "name": "API Product", "default_code": "API-SKU", "principal_id": cls.principal.id,
            "company_id": False, "uom_id": unit.id, "list_price": 1000,
            "carton_qty": 24, "inner_qty": 6, "type": "consu", "is_storable": True,
            "taxes_id": [Command.clear()],
        })
        cls.outlet = cls.env["res.partner"].create({
            "name": "API Scheduled Outlet", "company_id": cls.company.id, "user_id": cls.mobile.id,
            "partner_latitude": 1.465, "partner_longitude": 124.833, "street": "Test Street",
        })
        cls.assignment = cls.env["id.mobile.workday"].create({
            "user_id": cls.mobile.id, "company_id": cls.company.id, "business_date": business_date(),
            "warehouse_id": cls.warehouse.id, "pricelist_id": cls.pricelist.id,
            "outlet_ids": [Command.set(cls.outlet.ids)], "product_ids": [Command.set(cls.product.ids)],
        })
        # Native quant update API: no inventory posting and no invoice/payment creation.
        Quant = cls.env["stock.quant"].with_company(cls.company)
        Quant._update_available_quantity(cls.product, cls.warehouse.lot_stock_id, 48)
        Quant._update_reserved_quantity(cls.product, cls.warehouse.lot_stock_id, 12)
        Quant._update_available_quantity(cls.product, cls.other_warehouse.lot_stock_id, 2400)
        cls.env["stock.quant"].with_company(cls.foreign)._update_available_quantity(
            cls.product, cls.foreign_warehouse.lot_stock_id, 4800,
        )
        Quant._update_available_quantity(cls.product, cls.warehouse.lot_stock_id, 1200, owner_id=cls.outlet)


@tagged("post_install", "-at_install")
class TestMobileRead(MobileFixture, TransactionCase):
    def service(self, user=None):
        actor = user or self.mobile
        return self.env["id.mobile.workday"].with_user(actor).with_context(allowed_company_ids=actor.company_ids.ids)

    def extra_product(self, code):
        # Create a persisted second variant explicitly. product.product.copy()
        # can return an empty variant record in Odoo19's template copy flow.
        product = self.env["product.product"].create({
            "name": "Extra API Product", "default_code": code, "principal_id": self.principal.id,
            "company_id": False, "uom_id": self.product.uom_id.id, "list_price": 1000,
            "carton_qty": 24, "inner_qty": 6, "type": "consu", "is_storable": True,
            "taxes_id": [Command.clear()],
        })
        self.assertTrue(product.id)
        return product

    def hide_product_rule(self):
        self.env["ir.rule"].create({
            "name": "Hide assigned test product", "model_id": self.env.ref("product.model_product_product").id,
            "domain_force": "[('id', '!=', %s)]" % self.product.id,
        })

    def test_bootstrap_and_catalog_are_scoped_and_tax_excluded(self):
        bootstrap = self.service()._bootstrap_payload()
        self.assertEqual(bootstrap["id"], str(self.mobile.id))
        self.assertEqual(bootstrap["companyId"], str(self.company.id))
        self.assertEqual(bootstrap["roles"], ["sales"])
        snapshot = self.service()._snapshot_payload()
        self.assertEqual(snapshot["scope"]["warehouse_id"], str(self.warehouse.id))
        self.assertEqual(snapshot["scope"]["business_date"], business_date().isoformat())
        self.assertEqual(snapshot["products"][0]["packaging"], {"carton": 24, "pack": 6, "pcs": 1})
        self.assertEqual(snapshot["products"][0]["price"], 24000)
        self.assertEqual(snapshot["products"][0]["stock"], 1.5)
        self.assertEqual([p["id"] for p in snapshot["outlets"]], [str(self.outlet.id)])
        self.assertEqual(snapshot["deliveries"], [])
        serialized = str(snapshot)
        for secret in ("standard_price", "credit_limit", "vat", "phone", "amount_residual", "demo_unrestricted"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(snapshot["version"], self.service()._snapshot_payload()["version"])

    def test_missing_role_assignment_and_portal_are_denied(self):
        for user in (self.other, self.internal, self.portal):
            with self.assertRaises(AccessError):
                self.service(user)._snapshot_payload()
        self.assignment.active = False
        with self.assertRaises(AccessError):
            self.service()._bootstrap_payload()

    def test_own_assignment_read_only_acl(self):
        own = self.env["id.mobile.workday"].with_user(self.mobile).search([])
        self.assertEqual(own, self.assignment)
        self.assertFalse(self.env["id.mobile.workday"].with_user(self.other).search([]))
        with self.assertRaises(AccessError):
            self.assignment.with_user(self.mobile).write({"warehouse_id": self.other_warehouse.id})
        with self.assertRaises(AccessError):
            self.assignment.with_user(self.mobile).unlink()
        with self.assertRaises(AccessError):
            self.env["id.mobile.workday"].with_user(self.mobile).create({"business_date": business_date()})

    def test_mobile_read_group_does_not_grant_business_write_access(self):
        with self.assertRaises(AccessError):
            self.env["sale.order"].with_user(self.mobile).create({"partner_id": self.outlet.id})
        with self.assertRaises(AccessError):
            self.env["stock.quant"].with_user(self.mobile).create({
                "product_id": self.product.id, "location_id": self.warehouse.lot_stock_id.id,
            })

    def test_empty_catalog_or_stops_is_configuration_error(self):
        self.assignment.product_ids = [Command.clear()]
        with self.assertRaises(UserError):
            self.service()._snapshot_payload()

    def test_company_membership_rechecked_and_cross_company_config_rejected(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.assignment.company_id = self.foreign
        self.assignment.active = False
        self.mobile.company_ids = [Command.link(self.foreign.id)]
        self.mobile.company_id = self.foreign
        with self.assertRaises(AccessError):
            self.service()._snapshot_payload()

    def test_invalid_packaging_and_duplicate_codes_fail_closed(self):
        self.product.inner_qty = 5
        with self.assertRaises(UserError):
            self.service()._snapshot_payload()
        self.product.inner_qty = 6
        duplicate = self.extra_product(self.product.default_code)
        self.assignment.product_ids = [Command.link(duplicate.id)]
        with self.assertRaises(UserError):
            self.service()._snapshot_payload()

    def test_product_record_rule_is_not_bypassed(self):
        self.hide_product_rule()
        visible = self.env["product.product"].with_user(self.mobile).search([("id", "=", self.product.id)])
        self.assertFalse(visible)
        self.assertFalse(self.service().env.su)
        # Odoo filters hidden records from the assignment's M2M relation. An
        # entirely hidden catalog becomes empty and must not return a snapshot.
        with self.assertRaisesRegex(UserError, "Assign at least one product"):
            self.service()._snapshot_payload()

    def test_partially_hidden_catalog_contains_only_authorized_products(self):
        visible = self.extra_product("API-VISIBLE")
        self.assignment.product_ids = [Command.link(visible.id)]
        self.hide_product_rule()
        snapshot = self.service()._snapshot_payload()
        self.assertEqual([p["id"] for p in snapshot["products"]], [str(visible.id)])
        self.assertNotIn(self.product.default_code, str(snapshot))

    def test_day_rollover_is_conflict_not_a_new_scope(self):
        with patch("odoo.addons.id_mobile_api.models.mobile_workday.business_date", side_effect=[
            business_date(), business_date().replace(year=2000),
        ]):
            with self.assertRaises(MobileReadConflict):
                self.service()._bootstrap_payload()

    def test_read_does_not_write_business_models(self):
        models = ("sale.order", "stock.picking", "stock.move", "account.move", "account.payment", "id.mobile.workday")
        before = {model: self.env[model].search_count([]) for model in models}
        config_date = self.assignment.write_date
        self.service()._bootstrap_payload()
        self.service()._snapshot_payload()
        self.assertEqual(before, {model: self.env[model].search_count([]) for model in models})
        self.assertEqual(self.assignment.write_date, config_date)


@tagged("post_install", "-at_install")
class TestMobileReadHttp(MobileFixture, HttpCase):
    def test_public_portal_role_and_query_isolation(self):
        response = self.url_open("/api/v1/me/bootstrap")
        self.assertEqual(response.status_code, 401)
        self.authenticate(self.portal.login, "mobile-api-portal")
        self.assertEqual(self.url_open("/api/v1/sync/snapshot").status_code, 403)
        self.authenticate(self.internal.login, "mobile-api-denied")
        self.assertEqual(self.url_open("/api/v1/me/bootstrap").status_code, 403)
        self.authenticate(self.other.login, "mobile-api-other")
        self.assertEqual(self.url_open("/api/v1/me/bootstrap").status_code, 403)
        self.authenticate(self.mobile.login, "mobile-api-test")
        for query in ("?company_id=1", "?user_id=1", "?warehouse_id=1", "?db=other"):
            self.assertEqual(self.url_open("/api/v1/sync/snapshot" + query).status_code, 400)

    def test_session_response_cache_boundary_and_read_only_routes(self):
        self.authenticate(self.mobile.login, "mobile-api-test")
        bootstrap = self.url_open("/api/v1/me/bootstrap")
        self.assertEqual(bootstrap.status_code, 200)
        self.assertEqual(bootstrap.json()["id"], str(self.mobile.id))
        self.assertTrue(bootstrap.json()["csrfToken"])
        snapshot = self.url_open("/api/v1/sync/snapshot")
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(snapshot.json()["scope"]["company_id"], str(self.company.id))
        self.assertEqual(snapshot.json()["products"][0]["stock"], 1.5)
        self.assertIn("no-store", snapshot.headers["Cache-Control"])
        self.assertIn("Cookie", snapshot.headers["Vary"])
        self.assertNotIn("Access-Control-Allow-Origin", snapshot.headers)
        self.assertEqual(self.url_open("/api/v1/me/bootstrap", data="{}").status_code, 405)
        cross = self.url_open("/api/v1/sync/snapshot", headers={"Origin": "https://other.invalid"})
        self.assertEqual(cross.status_code, 400)
        self.assertEqual(self.url_open("/api/v1/sync/commands", data="{}").status_code, 404)
