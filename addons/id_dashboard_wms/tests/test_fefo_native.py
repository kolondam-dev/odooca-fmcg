from odoo import fields
from odoo.tests.common import TransactionCase


class TestNativeFmcgFefo(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fefo = cls.env.ref("product_expiry.removal_fefo")
        cls.unit = cls.env.ref("uom.product_uom_unit")
        cls.company = cls.env.company

    def test_product_expiry_builds_removal_date_and_location_uses_fefo(self):
        category = self.env["product.category"].create({
            "name": "FMCG FEFO Test Category",
        })
        parent = self.env.ref("stock.stock_location_stock")
        location = self.env["stock.location"].create({
            "name": "FMCG FEFO Test Location",
            "usage": "internal",
            "location_id": parent.id,
            "company_id": self.company.id,
            "removal_strategy_id": self.fefo.id,
        })
        template = self.env["product.template"].create({
            "name": "FMCG FEFO Test Product",
            "is_storable": True,
            "tracking": "lot",
            "use_expiration_date": True,
            "uom_id": self.unit.id,
            "categ_id": category.id,
        })
        product = template.product_variant_id

        older_lot = self.env["stock.lot"].create({
            "name": "LOT-FEFO-OLDER",
            "product_id": product.id,
            "company_id": self.company.id,
            "expiration_date": "2027-12-31 00:00:00",
        })
        newer_lot = self.env["stock.lot"].create({
            "name": "LOT-FEFO-NEWER",
            "product_id": product.id,
            "company_id": self.company.id,
            "expiration_date": "2028-06-30 00:00:00",
        })

        self.assertTrue(template.use_expiration_date)
        self.assertTrue(older_lot.removal_date)
        self.assertTrue(newer_lot.removal_date)
        self.assertLess(older_lot.removal_date, newer_lot.removal_date)
        self.assertEqual(
            self.env["stock.quant"]._get_removal_strategy(product, location),
            "fefo",
        )
        self.assertEqual(
            self.env["stock.quant"]._get_removal_strategy_order("fefo"),
            "removal_date, in_date, id",
        )

    def test_expired_lots_are_excluded_and_remaining_lots_follow_fefo(self):
        category = self.env["product.category"].create({
            "name": "FMCG FEFO Reservation Test Category",
        })
        parent = self.env.ref("stock.stock_location_stock")
        location = self.env["stock.location"].create({
            "name": "FMCG FEFO Reservation Location",
            "usage": "internal",
            "location_id": parent.id,
            "company_id": self.company.id,
            "removal_strategy_id": self.fefo.id,
        })
        template = self.env["product.template"].create({
            "name": "FMCG FEFO Reservation Product",
            "is_storable": True,
            "tracking": "lot",
            "use_expiration_date": True,
            "uom_id": self.unit.id,
            "categ_id": category.id,
        })
        product = template.product_variant_id
        lots = self.env["stock.lot"].create([
            {
                "name": "LOT-FEFO-EXPIRED",
                "product_id": product.id,
                "company_id": self.company.id,
                "expiration_date": "2025-12-31 00:00:00",
            },
            {
                "name": "LOT-FEFO-FIRST",
                "product_id": product.id,
                "company_id": self.company.id,
                "expiration_date": "2027-12-31 00:00:00",
            },
            {
                "name": "LOT-FEFO-SECOND",
                "product_id": product.id,
                "company_id": self.company.id,
                "expiration_date": "2028-06-30 00:00:00",
            },
        ])
        Quant = self.env["stock.quant"]
        for lot in lots:
            Quant._update_available_quantity(product, location, 10, lot_id=lot.id)

        move = self.env["stock.move"].create({
            "name": "FMCG FEFO Reservation Test",
            "product_id": product.id,
            "product_uom": self.unit.id,
            "product_uom_qty": 1,
            "location_id": location.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "company_id": self.company.id,
            "date": fields.Datetime.now(),
        })
        quants = Quant.with_context(with_expiration=move.date)._gather(product, location)

        self.assertEqual(quants.mapped("lot_id.name"), ["LOT-FEFO-FIRST", "LOT-FEFO-SECOND"])
        self.assertEqual(move._get_available_quantity(location), 20)

    def test_product_category_strategy_overrides_location_fallback(self):
        category = self.env["product.category"].create({
            "name": "FMCG FEFO Category Override Test",
            "removal_strategy_id": self.fefo.id,
        })
        location = self.env.ref("stock.stock_location_stock")
        template = self.env["product.template"].create({
            "name": "FMCG FEFO Category Product",
            "is_storable": True,
            "tracking": "lot",
            "use_expiration_date": True,
            "uom_id": self.unit.id,
            "categ_id": category.id,
        })
        self.assertEqual(
            self.env["stock.quant"]._get_removal_strategy(template.product_variant_id, location),
            "fefo",
        )
