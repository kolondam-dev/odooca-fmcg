import csv
import pathlib
import tempfile

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


class TestFMCGDimensionsUoM(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.principal = cls.env["id.principal"].create({
            "name": "PT Mayora Indah",
            "code": "TEST-FMCG-DIMENSIONS",
        })
        cls.brand = cls.env["id.brand"].create({
            "name": "Roma",
            "code": "BRD-RMA",
            "principal_id": cls.principal.id,
        })
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")

    def test_existing_seed_sku_replay_preserves_inventory_uom_and_stock_quantity(self):
        product = self.env["product.template"].create({
            "name": "Existing Seed SKU UoM Replay",
            "default_code": "TEST-SEED-UOM-PRESERVE",
            "uom_id": self.uom_unit.id,
            "is_storable": True,
        })
        variant = product.product_variant_id
        location = self.env.ref("stock.stock_location_stock")
        Quant = self.env["stock.quant"]
        Quant._update_available_quantity(variant, location, 37.0)

        original_uom_id = product.uom_id.id
        original_quantity = sum(Quant.search([
            ("product_id", "=", variant.id),
            ("location_id", "=", location.id),
        ]).mapped("quantity"))

        # Same guard invoked by load_products() before writing any existing SKU fields.
        self.assertTrue(product.assert_fmcg_seed_inventory_uom(self.uom_unit))
        product.write({
            "name": "Existing Seed SKU UoM Replay Updated",
            "list_price": 1234.0,
        })

        self.assertEqual(product.uom_id.id, original_uom_id)
        self.assertEqual(
            sum(Quant.search([
                ("product_id", "=", variant.id),
                ("location_id", "=", location.id),
            ]).mapped("quantity")),
            original_quantity,
        )
        self.assertEqual(original_quantity, 37.0)

    def test_existing_seed_sku_with_different_inventory_uom_fails_before_write(self):
        product = self.env["product.template"].create({
            "name": "Noncanonical Existing Seed SKU",
            "default_code": "TEST-SEED-UOM-MISMATCH",
            "uom_id": self.uom_unit.id,
        })
        original_name = product.name
        sachet_uom = self.env.ref("id_base.uom_sch")

        with self.assertRaisesRegex(ValidationError, "tidak akan mengubah UoM"):
            product.assert_fmcg_seed_inventory_uom(sachet_uom)

        self.assertEqual(product.name, original_name)
        self.assertEqual(product.uom_id, self.uom_unit)


    def _run_products_csv_loader(self, rows, *, backfill=None, packaging=False, offer_status=None):
        """Execute the real load_products() function against a temporary CSV in this Odoo test DB."""
        repo_root = next(
            parent for parent in pathlib.Path(__file__).resolve().parents
            if (parent / "scripts" / "load_fmcg_seed.py").is_file()
        )
        loader_path = repo_root / "scripts" / "load_fmcg_seed.py"
        source = loader_path.read_text(encoding="utf-8")
        # Import the script's definitions without invoking load_all() (which commits the test cursor).
        source = source.rsplit('\nif "FMCG_VENDOR_CARTON_MODE"', 1)[0]
        with tempfile.TemporaryDirectory(prefix="fmcg-seed-uom-") as tmp:
            seed_dir = pathlib.Path(tmp)
            csv_path = seed_dir / "products_150.csv"
            fieldnames = [
                "default_code", "name", "principal_code", "brand_code",
                "fmcg_category", "base_uom", "inner_qty", "carton_qty", "purchase_uom", "cost_price",
            ]
            with csv_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            with (seed_dir / "principals_4.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(("code", "lead_time_days"))
                for code in sorted({row["principal_code"] for row in rows}):
                    writer.writerow((code, 12))

            namespace = {"env": self.env, "__file__": str(loader_path)}
            exec(compile(source, str(loader_path), "exec"), namespace)
            namespace["seed_dir"] = seed_dir
            if backfill is None:
                namespace["load_products"]()
                return
            if packaging:
                return namespace["backfill_carton_uoms"](self.env, apply=backfill)
            return namespace["backfill_vendor_cartons"](self.env, apply=backfill, offer_status=offer_status)

    def test_real_seed_loader_replay_preserves_stock_uom_and_packaging(self):
        product = self.env["product.template"].create({
            "name": "Existing Seed SKU Loader Replay",
            "default_code": "TEST-SEED-LOADER-REPLAY",
            "principal_id": self.principal.id,
            "brand_id": self.brand.id,
            "uom_id": self.uom_unit.id,
            "is_storable": True,
        })
        variant = product.product_variant_id
        location = self.env.ref("stock.stock_location_stock")
        quant_model = self.env["stock.quant"]
        quant_model._update_available_quantity(variant, location, 37.0)

        vendor = self.env["res.partner"].create({"name": "Seed Carton Vendor"})
        self.principal.partner_id = vendor
        row = {
            "default_code": product.default_code,
            "name": "Existing Seed SKU Loader Replay",
            "principal_code": self.principal.code,
            "brand_code": self.brand.code,
            "fmcg_category": "biscuit_wafer",
            "base_uom": "Pcs",
            "inner_qty": "10",
            "carton_qty": "120",
            "purchase_uom": "Karton",
            "cost_price": "1250",
        }
        self._run_products_csv_loader([row])
        product.invalidate_recordset()
        first_uom_ids = tuple(sorted(product.uom_ids.ids))
        first_base_uom_id = product.fmcg_base_uom_id.id
        first_inner_uom_id = product.fmcg_inner_uom_id.id
        first_carton_uom_id = product.fmcg_carton_uom_id.id
        offer = product.seller_ids.filtered(lambda seller: seller.partner_id == vendor)
        self.assertEqual(len(offer), 1)
        self.assertEqual(offer.product_uom_id, product.fmcg_carton_uom_id)
        self.assertEqual(offer.price, 150000)
        self.assertEqual(offer.company_id, self.env.company)
        self.assertEqual(offer.currency_id, self.env.company.currency_id)
        self.assertEqual(offer.delay, 12)
        first_qty = sum(quant_model.search([
            ("product_id", "=", variant.id),
            ("location_id", "=", location.id),
        ]).mapped("quantity"))

        # A second real CSV replay must be idempotent for stock and UoM relationships.
        self._run_products_csv_loader([row])
        product.invalidate_recordset()
        second_qty = sum(quant_model.search([
            ("product_id", "=", variant.id),
            ("location_id", "=", location.id),
        ]).mapped("quantity"))

        self.assertEqual(product.seller_ids.filtered(lambda seller: seller.partner_id == vendor), offer)
        self.assertEqual(product.uom_id, self.uom_unit)
        self.assertEqual(first_qty, 37.0)
        self.assertEqual(second_qty, first_qty)
        self.assertEqual(tuple(sorted(product.uom_ids.ids)), first_uom_ids)
        self.assertEqual(product.fmcg_base_uom_id.id, first_base_uom_id)
        self.assertEqual(product.fmcg_inner_uom_id.id, first_inner_uom_id)
        self.assertEqual(product.fmcg_carton_uom_id.id, first_carton_uom_id)

    def test_seed_preserves_existing_vendor_offers_by_company_scope(self):
        vendor = self.env["res.partner"].create({"name": "Existing Carton Vendor"})
        self.principal.partner_id = vendor
        product = self.env["product.template"].create({
            "name": "Seed SKU with Custom Offer",
            "default_code": "TEST-CUSTOM-OFFER",
            "uom_id": self.uom_unit.id,
        })
        foreign = self.env["res.company"].create({"name": "Foreign Offer Company"})
        row = {
            "default_code": product.default_code,
            "name": product.name,
            "principal_code": self.principal.code,
            "brand_code": self.brand.code,
            "base_uom": "Pcs",
            "inner_qty": "10",
            "carton_qty": "120",
            "purchase_uom": "Karton",
            "cost_price": "1250",
        }
        seller_model = self.env["product.supplierinfo"].sudo()
        offer = seller_model.create({
            "partner_id": vendor.id,
            "product_tmpl_id": product.id,
            "company_id": False,
            "product_uom_id": self.uom_unit.id,
            "price": 9876,
            "min_qty": 7,
            "delay": 3,
        })
        fields = ["product_uom_id", "price", "min_qty", "delay", "company_id", "currency_id"]
        domain = [("product_tmpl_id", "=", product.id), ("partner_id", "=", vendor.id)]

        for company in (self.env.company, self.env["res.company"], foreign):
            offer.company_id = company
            before = offer.read(fields)
            self._run_products_csv_loader([row])
            self.assertEqual(offer.read(fields), before)
            offers = seller_model.search(domain)
            if company == foreign:
                local = offers - offer
                self.assertEqual(len(local), 1)
                self.assertEqual(local.company_id, self.env.company)
                self.assertEqual(local.product_uom_id, product.fmcg_carton_uom_id)
            else:
                self.assertEqual(offers, offer)

    def test_legacy_carton_uom_backfill_preserves_inventory_offer(self):
        vendor = self.env["res.partner"].create({"name": "Legacy Vendor"})
        self.principal.partner_id = vendor
        product = self.env["product.template"].create({
            "name": "Legacy SKU",
            "default_code": "TEST-LEGACY-CARTON",
            "principal_id": self.principal.id,
            "uom_id": self.uom_unit.id,
        })
        offer = self.env["product.supplierinfo"].create({
            "product_tmpl_id": product.id,
            "partner_id": vendor.id,
            "company_id": self.env.company.id,
            "product_uom_id": self.uom_unit.id,
            "price": 1250,
            "min_qty": 7,
        })
        row = {
            "default_code": product.default_code,
            "principal_code": self.principal.code,
            "base_uom": "Pcs",
            "inner_qty": "10",
            "carton_qty": "120",
            "purchase_uom": "Karton",
            "cost_price": "1250",
        }
        lookup = self._run_products_csv_loader
        expected = ([(product.default_code, 120)], [])
        self.assertEqual(lookup([row], packaging=True, backfill=False), expected)
        self.assertFalse(product.fmcg_carton_uom_id)
        self.assertEqual(lookup([row], packaging=True, backfill=True), expected)
        carton = product.fmcg_carton_uom_id
        self.assertEqual(carton._compute_quantity(1, self.uom_unit, round=False), 120)
        self.assertEqual(lookup([row], packaging=True, backfill=True), ([], [product.default_code]))
        self.assertEqual(product.fmcg_carton_uom_id, carton)
        self.assertEqual(product.uom_id, self.uom_unit)
        counts = dict.fromkeys(("carton", "inventory", "other"), 0)
        self.assertEqual(lookup([row], backfill=False, offer_status=counts), ([], [product.default_code]))
        self.assertEqual(counts, {"carton": 0, "inventory": 1, "other": 0})
        self.assertEqual(product.seller_ids, offer)
        self.assertEqual((offer.product_uom_id, offer.price, offer.min_qty), (self.uom_unit, 1250, 7))

    def test_existing_database_vendor_carton_backfill(self):
        vendor = self.env["res.partner"].create({"name": "Backfill Vendor"})
        self.principal.partner_id = vendor
        row = {
            "default_code": "TEST-BACKFILL",
            "name": "Initially Seeded Product",
            "principal_code": self.principal.code,
            "brand_code": self.brand.code,
            "base_uom": "Pcs",
            "inner_qty": "10",
            "carton_qty": "120",
            "cost_price": "1250",
        }
        self._run_products_csv_loader([row])
        product = self.env["product.template"].search([("default_code", "=", row["default_code"])])
        backfill_row = dict(row, name="Must Not Be Renamed", purchase_uom="Karton")

        with self.assertRaisesRegex(ValueError, "Carton conversion mismatch"):
            self._run_products_csv_loader([dict(backfill_row, carton_qty="121")], backfill=True)

        dry_run = self._run_products_csv_loader([backfill_row], backfill=False)
        self.assertEqual(len(dry_run[0]), 1)
        self.assertFalse(product.seller_ids)
        self.assertEqual(self._run_products_csv_loader([backfill_row], backfill=True), dry_run)
        self.assertEqual(product.name, row["name"])
        self.assertEqual(len(product.seller_ids), 1)
        self.assertEqual(product.seller_ids.product_uom_id, product.fmcg_carton_uom_id)
        self.assertEqual(product.seller_ids.price, 150000)
        self.assertEqual(
            self._run_products_csv_loader([backfill_row], backfill=True),
            ([], [row["default_code"]]),
        )
        self.assertEqual(len(product.seller_ids), 1)

    def test_real_seed_loader_rejects_noncanonical_uom_before_product_write(self):
        sachet_uom = self.env.ref("id_base.uom_sch")
        product = self.env["product.template"].create({
            "name": "Do Not Rewrite Noncanonical SKU",
            "default_code": "TEST-SEED-LOADER-UOM-MISMATCH",
            "principal_id": self.principal.id,
            "brand_id": self.brand.id,
            "uom_id": sachet_uom.id,
            "list_price": 4321.0,
        })
        before = {
            "name": product.name,
            "uom_id": product.uom_id.id,
            "list_price": product.list_price,
            "uom_ids": tuple(sorted(product.uom_ids.ids)),
        }
        row = {
            "default_code": product.default_code,
            "name": "This Must Not Be Written",
            "principal_code": self.principal.code,
            "brand_code": self.brand.code,
            "fmcg_category": "biscuit_wafer",
            "base_uom": "Pcs",
            "inner_qty": "10",
            "carton_qty": "120",
            "cost_price": "1250",
        }
        with self.assertRaisesRegex(ValidationError, "tidak akan mengubah UoM"):
            self._run_products_csv_loader([row])

        product.invalidate_recordset()
        self.assertEqual(product.name, before["name"])
        self.assertEqual(product.uom_id.id, before["uom_id"])
        self.assertEqual(product.list_price, before["list_price"])
        self.assertEqual(tuple(sorted(product.uom_ids.ids)), before["uom_ids"])

    def test_01_product_dimensions_and_weight_computation(self):
        """Verifikasi bahwa 14 kolom FMCG dan komputasi dua arah bobot/kubikasi berjalan presisi."""
        product = self.env["product.template"].create({
            "name": "Roma Kelapa 300g",
            "default_code": "MYR-RMA-01",
            "principal_id": self.principal.id,
            "brand_id": self.brand.id,
            "fmcg_category": "biscuit_wafer",
            "uom_id": self.uom_unit.id,
            "weight": 0.3,
            "inner_qty": 1,
            "carton_qty": 30,
            "carton_length_cm": 39.3,
            "carton_width_cm": 28.3,
            "carton_height_cm": 40.1,
            "carton_weight_kg": 9.45,
            "carton_barcode": "1899275310001",
            "standard_price": 7500.0,
            "list_price": 8500.0,
        })

        # Cek konversi otomatis kg -> g
        self.assertAlmostEqual(product.base_weight_g, 300.0, places=1)

        # Cek komputasi kubikasi karton (39.3 * 28.3 * 40.1 / 1000000 = 0.0446 m3)
        self.assertAlmostEqual(product.carton_volume_cbm, 0.0446, places=4)

        # Cek inverse gramasi g -> kg
        product.write({"base_weight_g": 250.0})
        self.assertAlmostEqual(product.weight, 0.25, places=2)

    def test_02_native_uom_records_exist(self):
        """Verifikasi bahwa satuan-satuan native FMCG tersedia di registry."""
        uom_pcs = self.env.ref("id_base.uom_pcs", raise_if_not_found=False)
        self.assertTrue(uom_pcs, "id_base.uom_pcs wajib ada!")
        self.assertEqual(uom_pcs.name, "Pieces")

        uom_sch = self.env.ref("id_base.uom_sch", raise_if_not_found=False)
        self.assertTrue(uom_sch, "id_base.uom_sch wajib ada!")

        uom_karton = self.env.ref("id_base.uom_karton", raise_if_not_found=False)
        self.assertTrue(uom_karton, "id_base.uom_karton wajib ada!")


    def test_04_native_per_sku_packaging_uom_hierarchy(self):
        """SKU packaging uses Odoo 19 UoMs while preserving the inventory UoM."""
        product = self.env["product.template"].create({
            "name": "Coffee Sachet Test",
            "default_code": "TEST-UOM-SACHET",
            "principal_id": self.principal.id,
            "brand_id": self.brand.id,
            "uom_id": self.uom_unit.id,
            "standard_price": 1000.0,
            "list_price": 1500.0,
        })
        base_uom = self.env.ref("id_base.uom_sch")
        product.configure_fmcg_packaging_uoms(base_uom, inner_qty=10, carton_qty=120)

        self.assertEqual(product.uom_id, self.uom_unit)
        self.assertEqual(product.fmcg_base_uom_id, base_uom)
        self.assertTrue(product.fmcg_inner_uom_id)
        self.assertTrue(product.fmcg_carton_uom_id)
        self.assertIn(base_uom, product.uom_ids)
        self.assertIn(product.fmcg_inner_uom_id, product.uom_ids)
        self.assertIn(product.fmcg_carton_uom_id, product.uom_ids)
        self.assertEqual(
            product.fmcg_inner_uom_id._compute_quantity(1, product.uom_id),
            10,
        )
        self.assertEqual(
            product.fmcg_carton_uom_id._compute_quantity(1, product.uom_id),
            120,
        )

        inner_id = product.fmcg_inner_uom_id.id
        carton_id = product.fmcg_carton_uom_id.id
        product.configure_fmcg_packaging_uoms(base_uom, inner_qty=10, carton_qty=120)
        self.assertEqual(product.fmcg_inner_uom_id.id, inner_id)
        self.assertEqual(product.fmcg_carton_uom_id.id, carton_id)

    def test_05_native_packaging_without_inner_tier(self):
        """Products with inner_qty=1 expose carton and base UoM only."""
        product = self.env["product.template"].create({
            "name": "Bottled Coffee Test",
            "default_code": "TEST-UOM-BOTTLE",
            "principal_id": self.principal.id,
            "brand_id": self.brand.id,
            "uom_id": self.uom_unit.id,
            "standard_price": 5000.0,
            "list_price": 6000.0,
        })
        base_uom = self.env.ref("id_base.uom_btl")
        product.configure_fmcg_packaging_uoms(base_uom, inner_qty=1, carton_qty=24)

        self.assertFalse(product.fmcg_inner_uom_id)
        self.assertEqual(
            product.fmcg_carton_uom_id._compute_quantity(1, product.uom_id),
            24,
        )

    def test_08_sales_line_defaults_base_uom_and_shows_breakdown(self):
        product = self.env["product.template"].create({
            "name": "Sales Line Sachet Test",
            "default_code": "TEST-UOM-SALES",
            "principal_id": self.principal.id,
            "brand_id": self.brand.id,
            "uom_id": self.uom_unit.id,
            "standard_price": 1000.0,
            "list_price": 1500.0,
        })
        base_uom = self.env.ref("id_base.uom_sch")
        product.configure_fmcg_packaging_uoms(base_uom, inner_qty=10, carton_qty=120)
        partner = self.env["res.partner"].create({"name": "FMCG UoM Test Customer"})
        order = self.env["sale.order"].create({"partner_id": partner.id})
        variant = product.product_variant_id

        base_line = self.env["sale.order.line"].create({
            "order_id": order.id,
            "product_id": variant.id,
            "product_uom_qty": 2,
            "price_unit": 1500,
        })
        self.assertEqual(base_line.product_uom_id, base_uom)
        self.assertEqual(base_line.fmcg_qty_breakdown, "2 Sachet (2 Sachet)")

        carton_line = self.env["sale.order.line"].create({
            "order_id": order.id,
            "product_id": variant.id,
            "product_uom_qty": 1.1,
            "product_uom_id": product.fmcg_carton_uom_id.id,
            "price_unit": 180000,
        })
        self.assertEqual(
            carton_line.fmcg_qty_breakdown,
            "1 Karton + 1 Inner + 2 Sachet (132 Sachet)",
        )

    def test_07_configured_packaging_ratio_cannot_be_silently_changed(self):
        product = self.env["product.template"].create({
            "name": "Configured Ratio Test",
            "default_code": "TEST-UOM-LOCKED",
            "principal_id": self.principal.id,
            "brand_id": self.brand.id,
            "uom_id": self.uom_unit.id,
            "standard_price": 1000.0,
            "list_price": 1500.0,
        })
        product.configure_fmcg_packaging_uoms(
            self.env.ref("id_base.uom_sch"),
            inner_qty=10,
            carton_qty=120,
        )
        with self.assertRaises(ValidationError):
            product.write({"carton_qty": 130})

    def test_06_invalid_packaging_ratio_is_rejected(self):
        product = self.env["product.template"].create({
            "name": "Invalid Ratio Test",
            "default_code": "TEST-UOM-INVALID",
            "principal_id": self.principal.id,
            "brand_id": self.brand.id,
            "uom_id": self.uom_unit.id,
            "standard_price": 1000.0,
            "list_price": 1500.0,
        })
        with self.assertRaises(ValidationError):
            product.configure_fmcg_packaging_uoms(
                self.env.ref("id_base.uom_sch"),
                inner_qty=10,
                carton_qty=125,
            )

    def test_03_partner_coverage_and_matrix_pricelist(self):
        """Verifikasi bahwa partner dengan coverage area dan channel otomatis mendapat matriks harga."""
        channel_mt = self.env.ref("id_base.channel_mt")
        area_mnd = self.env.ref("id_base.area_mnd_urban")

        partner = self.env["res.partner"].create({
            "name": "FreshMart Bahu Test",
            "channel_id": channel_mt.id,
            "coverage_area_id": area_mnd.id,
        })

        pl = partner._get_matrix_pricelist()
        self.assertTrue(pl, "Partner MT di Manado Urban wajib mendapat matriks daftar harga!")
        self.assertEqual(pl.channel_id.id, channel_mt.id)

        # Action assign matrix
        partner.action_assign_matrix_pricelist()
        self.assertEqual(partner.property_product_pricelist.id, pl.id)


@tagged("-at_install", "post_install")
class TestFMCGVendorCartonPurchase(TransactionCase):
    _run_products_csv_loader = TestFMCGDimensionsUoM._run_products_csv_loader

    def test_vendor_carton_order_receipt_and_bill_line(self):
        if "purchase.order" not in self.env or "purchase_line_id" not in self.env["stock.move"]._fields:
            self.skipTest("Requires purchase_stock, installed by the Odoo CI job")

        vendor = self.env["res.partner"].create({"name": "Carton Purchase Vendor"})
        principal = self.env["id.principal"].create({
            "code": "TEST-CARTON",
            "name": "Carton Purchase Principal",
            "partner_id": vendor.id,
        })
        brand = self.env["id.brand"].create({
            "code": "TEST-CARTON",
            "name": "Carton Purchase Brand",
            "principal_id": principal.id,
        })
        code = "TEST-VENDOR-CARTON"
        self._run_products_csv_loader([{
            "default_code": code,
            "name": "Carton Purchase Product",
            "principal_code": principal.code,
            "brand_code": brand.code,
            "base_uom": "Pcs",
            "inner_qty": "10",
            "carton_qty": "120",
            "purchase_uom": "Karton",
            "cost_price": "1250",
        }])
        product = self.env["product.product"].search([("default_code", "=", code)])
        product.write({"tracking": "none", "purchase_method": "receive"})
        order = self.env["purchase.order"].create({
            "partner_id": vendor.id,
            "order_line": [Command.create({"product_id": product.id, "product_qty": 2})],
        })
        line = order.order_line
        self.assertEqual(line.product_uom_id, product.fmcg_carton_uom_id)
        self.assertEqual(line.price_unit, 150000)
        self.assertEqual(line.price_subtotal, 300000)
        order.button_confirm()
        receipt = order.picking_ids
        move = receipt.move_ids
        self.assertEqual(move.product_qty, 240)
        move.quantity = move.product_uom_qty
        move.picked = True
        receipt.button_validate()
        self.assertEqual(receipt.state, "done")
        self.assertEqual(line.qty_received, 2)

        bill_line = line._prepare_account_move_line()
        self.assertEqual(bill_line["product_uom_id"], product.fmcg_carton_uom_id.id)
        self.assertEqual(bill_line["quantity"], 2)
        self.assertEqual(bill_line["price_unit"], 150000)
