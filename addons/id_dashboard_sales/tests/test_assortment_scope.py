from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from datetime import datetime


@tagged("post_install", "-at_install")
class TestEligibleDistribution(TransactionCase):
    def _source(self):
        self.env.company.currency_id.active = True
        self.manager = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Eligibility manager", "login": "eligibility_manager", "group_ids": [(6, 0, [
                self.env.ref("sales_team.group_sale_manager").id, self.env.ref("base.group_system").id])]})
        self.salesman = self.manager
        self.outlet_mt, self.outlet_gt = self.env["res.partner"].create([
            {"name": "Eligible outlet A"}, {"name": "Eligible outlet B"}])
        self.products = self.env["product.product"].create([
            {"name": "Eligible SKU " + c, "type": "consu", "list_price": 1000} for c in "ABC"])
        self.pricelist = self.env["product.pricelist"].create({"name": "Eligibility currency",
            "currency_id": self.env.company.currency_id.id})

    def _order(self, partner, user, products, day, qty):
        order = self.env["sale.order"].create({"partner_id": partner.id, "user_id": user.id,
            "pricelist_id": self.pricelist.id, "order_line": [(0, 0, {"product_id": product.id,
                "product_uom_qty": qty, "price_unit": 1000, "tax_ids": [(5, 0, 0)]}) for product in products]})
        order.action_confirm()
        order.date_order = day
        return order

    def _service(self):
        return self.env["id.sales.productivity"].with_user(self.manager)

    def test_frozen_outlets_zero_sku_and_observed_turnover_weight(self):
        self._source()
        self._order(self.outlet_mt, self.salesman, self.products[:1], datetime(2026, 7, 15, 3), qty=1)
        self._order(self.outlet_gt, self.salesman, self.products[1:2], datetime(2026, 7, 15, 4), qty=3)
        scope = self.env["id.sales.assortment.scope"].create({"name": "Explicit eligible outlets",
            "date_from": "2026-07-01", "date_to": "2026-07-31", "source": "Approved catalogue",
            "outlet_ids": [(6, 0, (self.outlet_mt | self.outlet_gt).ids)],
            "product_ids": [(6, 0, (self.products[:1] | self.products[2:3]).ids)]})
        scope.action_publish()
        data = self._service().get_data("month", "2026-07-15")
        rows = data["distribution"]["rows"]
        first = next(row for row in rows if row["sku"] == self.products[0].display_name)
        zero = next(row for row in rows if row["sku"] == self.products[2].display_name)
        self.assertEqual((first["numeric"], first["weighted"]), (50, 25))
        self.assertEqual((zero["numeric"], zero["weighted"]), (0, 0))
        self.outlet_gt.active = False
        self.products[2].active = False
        archived = self._service().get_data("month", "2026-07-15")["distribution"]
        self.assertTrue(archived["available"])
        again = next(row for row in archived["rows"] if row["sku"] == self.products[0].display_name)
        self.assertEqual((again["numeric"], again["weighted"]), (50, 25))
        self.assertEqual(len(archived["rows"]), 2)
        filtered = self._service().get_data("month", "2026-07-15", [self.salesman.id])
        self.assertFalse(filtered["distribution"]["available"])
        with self.assertRaises(AccessError):
            scope.write({"outlet_ids": [(5, 0, 0)]})
