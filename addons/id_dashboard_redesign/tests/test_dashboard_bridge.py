from datetime import datetime

from odoo.fields import Domain
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user
from odoo.exceptions import AccessError, UserError


@tagged("post_install", "-at_install")
class TestDashboardBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("base.IDR").active = True
        cls.env.company.currency_id = cls.env.ref("base.IDR")
        cls.bridge = cls.env["id.dashboard.redesign"]
        cls.manager = new_test_user(cls.env, login="d1_manager", groups="sales_team.group_sale_manager")
        cls.partner = cls.env["res.partner"].create({"name": "D1 fixture outlet"})
        cls.product = cls.env["product.product"].create({"name": "D1 fixture SKU", "type": "consu"})
        cls.product2 = cls.env["product.product"].create({"name": "D1 other SKU", "type": "consu"})
        pricelist = cls.env["product.pricelist"].create({"name": "D1 currency fixture",
            "currency_id": cls.env.company.currency_id.id})
        cls.sale = cls.env["sale.order"].create({"partner_id": cls.partner.id,
            "pricelist_id": pricelist.id, "user_id": cls.manager.id,
            "order_line": [(0, 0, {"product_id": cls.product.id, "product_uom_qty": 2,
                                  "price_unit": 100, "discount": 10}),
                           (0, 0, {"product_id": cls.product2.id, "product_uom_qty": 1, "price_unit": 50})]})
        cls.sale.action_confirm()
        cls.sale.date_order = datetime(2026, 8, 1, 16, 0)  # Aug 2 00:00 WITA
        cls.query = {"period": {"from": "2026-08-02", "to": "2026-08-02", "compare": False}, "filters": {}}

    def read(self, query=None, bridge=None):
        return (bridge if bridge is not None else self.bridge).get_data("D1", {"query": query or self.query})["source"]

    def test_signed_money_and_wita_boundary(self):
        data = self.read()
        self.assertEqual(data["total"]["gross"], 250)
        self.assertEqual(data["total"]["discount"], 20)
        self.assertEqual(data["total"]["net"], 230)
        self.assertEqual(data["total"]["orders"], 1)
        self.assertEqual(len(data["monthly"]), 5)
        self.assertEqual(data["monthly_period"]["start"], "2026-04-01")
        self.assertEqual(data["monthly"][-1]["net"], 230)
        self.assertEqual(sum(p["net"] for p in data["trend"]), 230)
        earlier = {"period": {"from": "2026-08-01", "to": "2026-08-01"}, "filters": {}}
        self.assertEqual(self.read(earlier)["total"]["orders"], 0)

    def test_product_slice_aggregates_lines_not_whole_order(self):
        query = {**self.query, "filters": {"sku": {"mode": "in", "ids": [self.product.id]}}}
        data = self.read(query)
        self.assertEqual(data["total"]["net"], 180)
        self.assertEqual(data["total"]["aov"], 180)
        self.assertFalse(data["total"]["pjp"].get("available"))
        # Drill source ties to the same line amount, never the entire mixed-SKU order.
        lines = self.env["sale.order.line"].search(data["line_domain"])
        self.assertEqual(lines.product_id, self.product)
        self.assertEqual(sum(lines.mapped("price_subtotal")), 180)
        native = self.env.ref("sale.action_orders")
        scope = Domain("order_line", "any", Domain(data["line_domain"]))
        orders = self.env[native.res_model].search(scope)
        self.assertEqual(orders, self.sale)
        self.assertEqual(sum(orders.order_line.mapped("price_subtotal")), 230)
        self.assertEqual(sum(r["net"] for r in data["principal"]), 180)

    def test_exclusion_empty_and_scope(self):
        query = {**self.query, "filters": {"sku": {"mode": "out", "ids": [self.product.id]}}}
        self.assertEqual(self.read(query)["total"]["net"], 50)
        query["filters"]["sku"]["ids"].append(self.product2.id)
        empty = self.read(query)
        self.assertEqual(empty["total"]["net"], 0)
        self.assertIsNone(empty["total"]["aov"])
        self.assertFalse(empty["target"]["available"])

    def test_comparison_and_invalid_inputs(self):
        query = {**self.query, "period": {**self.query["period"], "compare": True, "compareMode": "previous"}}
        data = self.read(query)
        self.assertEqual(data["previous_period"]["start"], "2026-08-01")
        self.assertEqual(data["previous"]["net"], 0)
        for period in ({"from": "bad", "to": "2026-01-01"},
                       {"from": "2026-08-02", "to": "2026-08-01"},
                       {"from": "2026-08-01", "to": "2026-08-02", "align": True}):
            with self.assertRaises(UserError):
                self.read({"period": period, "filters": {}})
        with self.assertRaises(UserError):
            self.read({**self.query, "filters": {"sku": {"mode": "in", "ids": [True]}}})
        with self.assertRaises(UserError):
            self.bridge.get_filters("D2")

    def test_roles_and_company_boundary(self):
        user = new_test_user(self.env, login="d1_no_sales", groups="base.group_user")
        with self.assertRaises(AccessError):
            self.read(bridge=self.bridge.with_user(user))
        other = self.env["res.company"].create({
            "name": "D1 other company", "currency_id": self.env.company.currency_id.id})
        data = self.read(bridge=self.bridge.with_context(allowed_company_ids=other.ids))
        self.assertEqual(data["total"]["net"], 0)
        self.assertEqual(data["total"]["orders"], 0)

    def test_action_scope_is_d1_only(self):
        self.assertEqual(self.env.ref("id_dashboard_sales.action_sales_productivity").tag, "id_dashboard_redesign.d1")
        self.assertFalse(self.env.ref("id_dashboard_redesign.action_d2", raise_if_not_found=False))

    def test_refund_is_posted_accounting_amount_not_so_subtraction(self):
        accounts = {}
        for key, kind, code in (("income", "income", "D19901"), ("ar", "asset_receivable", "D19902")):
            accounts[key] = self.env["account.account"].create({"name": "D1 " + key, "code": code,
                "account_type": kind, "reconcile": key == "ar", "company_ids": [(6, 0, self.env.company.ids)]})
        self.partner.property_account_receivable_id = accounts["ar"]
        self.product.property_account_income_id = accounts["income"]
        journal = self.env["account.journal"].create({"name": "D1 refunds", "code": "D1R", "type": "sale"})
        sale_lines = self.sale.order_line.filtered(lambda line: line.product_id == self.product)
        refund = self.env["account.move"].create({"move_type": "out_refund", "partner_id": self.partner.id,
            "invoice_date": "2026-08-02", "journal_id": journal.id,
            "invoice_line_ids": [(0, 0, {"product_id": self.product.id, "quantity": 1, "price_unit": 30,
                "account_id": accounts["income"].id, "tax_ids": [(5, 0, 0)],
                "sale_line_ids": [(6, 0, sale_lines.ids)]})]})
        self.assertEqual(self.read()["refund"]["amount"], 0)
        refund.action_post()
        result = self.read()
        self.assertEqual(result["refund"]["amount"], 30)
        self.assertEqual(result["total"]["net"], 230)
        query = {**self.query, "filters": {"sku": {"mode": "in", "ids": [self.product2.id]}}}
        self.assertEqual(self.read(query)["refund"]["amount"], 0)

    def test_own_sales_record_rules_and_no_role_escalation(self):
        own = new_test_user(self.env, login="d1_own", groups="sales_team.group_sale_salesman")
        other = new_test_user(self.env, login="d1_other", groups="sales_team.group_sale_salesman")
        self.sale.user_id = other
        scoped = self.bridge.with_user(own)
        self.assertEqual(self.read(bridge=scoped)["total"]["net"], 0)
        self.sale.user_id = own
        self.assertEqual(self.read(bridge=scoped)["total"]["net"], 230)
        query = {**self.query, "filters": {"salesman": {"mode": "in", "ids": [other.id]}}}
        self.assertEqual(self.read(query, scoped)["total"]["net"], 0)

    def test_exact_target_partition_and_signed_lines(self):
        users = self.env["res.users"].search([("active", "=", True),
            ("company_ids", "in", self.env.companies.ids),
            ("all_group_ids", "in", self.env.ref("sales_team.group_sale_salesman").ids)])
        self.assertTrue(users)
        Target = self.env["id.sales.segment.target"]
        for user in users:
            Target.create({"name": "D1 target " + user.name, "dimension": "salesman", "salesman_id": user.id,
                "date_from": "2026-08-02", "date_to": "2026-08-02", "target_amount": 1000})
        result = self.read()
        self.assertTrue(result["target"]["available"])
        self.assertEqual(result["target"]["amount"], len(users) * 1000)
        Target.search([("name", "like", "D1 target%")], limit=1).unlink()
        self.assertFalse(self.read()["target"]["available"])
        self.sale.order_line[0].price_unit = -100
        result = self.read()
        self.assertEqual(result["total"]["net"], -130)
        self.assertEqual(result["total"]["gross"] - result["total"]["discount"], -130)

    def test_calls_use_accepted_visits_and_assigned_days(self):
        import json
        import uuid
        if "id.mobile.command" not in self.env:
            self.skipTest("Optional mobile API is not installed")
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        self.env["id.mobile.workday"].create({"company_id": self.env.company.id, "user_id": self.manager.id,
            "business_date": "2026-08-02", "warehouse_id": warehouse.id,
            "pricelist_id": self.sale.pricelist_id.id, "outlet_ids": [(6, 0, self.partner.ids)],
            "product_ids": [(6, 0, self.product.ids)]})
        command = self.env["id.mobile.command"].create({"user_id": self.manager.id,
            "company_id": self.env.company.id, "client_uuid": str(uuid.uuid4()), "fingerprint": "d" * 64,
            "command_type": "sales.visit.check_in", "status": "accepted",
            "payload_json": json.dumps({"outlet_id": str(self.partner.id), "business_date": "2026-08-02"})})
        self.env.flush_all()
        self.cr.execute("UPDATE id_mobile_command SET create_date=%s WHERE id=%s",
                        [datetime(2026, 8, 1, 16), command.id])
        command.invalidate_recordset(["create_date"])
        result = self.read()
        self.assertEqual(result["total"]["pjp"]["effective"], 1)
        self.assertEqual(result["total"]["calls_per_day"], 1)
        self.assertEqual(result["salesmen"][0]["calls_per_day"], 1)
        zero_user = new_test_user(self.env, login="d1_zero_sales", groups="sales_team.group_sale_salesman")
        self.env["id.mobile.workday"].create({"company_id": self.env.company.id, "user_id": zero_user.id,
            "business_date": "2026-08-02", "warehouse_id": warehouse.id,
            "pricelist_id": self.sale.pricelist_id.id, "outlet_ids": [(6, 0, self.partner.ids)],
            "product_ids": [(6, 0, self.product.ids)]})
        rows = {row["id"]: row for row in self.read()["salesmen"]}
        self.assertEqual(rows[zero_user.id]["net"], 0)
        self.assertEqual(rows[zero_user.id]["calls_per_day"], 0)

    def test_month_end_comparison_matches_control_presets(self):
        from ..models.dashboard_bridge import comparison_range, parse_range
        period = {"from": "2024-03-01", "to": "2024-03-31", "preset": "mtd",
                  "compare": True, "compareMode": "previous"}
        start, end = parse_range(period)
        self.assertEqual(tuple(day.isoformat() for day in comparison_range(period, start, end)),
                         ("2024-02-01", "2024-03-01"))

    def test_uninstall_preserves_other_custom_actions(self):
        from ..hooks import uninstall_hook
        action = self.env.ref("id_dashboard_sales.action_sales_productivity")
        action.tag = "third_party.custom_sales"
        uninstall_hook(self.env)
        self.assertEqual(action.tag, "third_party.custom_sales")
        action.tag = "id_dashboard_redesign.d1"
        uninstall_hook(self.env)
        self.assertEqual(action.tag, "id_dashboard_sales.sales_productivity")
