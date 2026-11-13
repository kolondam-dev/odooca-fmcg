import unittest

from scripts.load_canonical_perpetual import CanonicalPerpetualAdapter


class LotStub:
    _fields = {
        "expiration_date": object(),
        "removal_date": object(),
        "name": object(),
    }

    def __init__(self, name="LOT-TEST", expiration_date=False, removal_date=False, noop_write=False):
        self.name = name
        self.expiration_date = expiration_date
        self.removal_date = removal_date
        self.noop_write = noop_write
        self.compute_calls = 0

    def write(self, vals):
        if not self.noop_write:
            for key, value in vals.items():
                setattr(self, key, value)

    def _compute_dates(self):
        self.compute_calls += 1
        self.removal_date = self.expiration_date


class AdapterStub:
    _ensure_lot_expiry = CanonicalPerpetualAdapter._ensure_lot_expiry
    _ensure_expiry_product_configuration = CanonicalPerpetualAdapter._ensure_expiry_product_configuration


class TemplateStub:
    _fields = {"tracking": object(), "use_expiration_date": object()}

    def __init__(self, tracking="lot", use_expiration_date=False):
        self.tracking = tracking
        self.use_expiration_date = use_expiration_date

    def write(self, vals):
        for key, value in vals.items():
            setattr(self, key, value)


class ProductStub:
    def __init__(self, template):
        self.product_tmpl_id = template


class TemplateModelStub:
    _fields = {"tracking": object(), "use_expiration_date": object()}

    def __init__(self):
        self.templates = []

    def sudo(self):
        return self


class EnvStub:
    def __init__(self, models):
        self.models = models

    def __getitem__(self, key):
        return self.models[key]


class TestFefoExpiryHelpers(unittest.TestCase):
    def setUp(self):
        self.adapter = AdapterStub()
        self.adapter.stats = {"lot_expiry_backfilled": 0}

    def test_enables_expiration_tracking_for_lot_tracked_canonical_products(self):
        template_model = TemplateModelStub()
        template = TemplateStub(tracking="lot", use_expiration_date=False)
        self.adapter.env = EnvStub({"product.template": template_model})
        self.adapter.product_by_code = {"SKU-1": ProductStub(template)}

        self.adapter._ensure_expiry_product_configuration()

        self.assertTrue(template.use_expiration_date)
        self.assertEqual(self.adapter.stats.get("expiry_products_enabled"), 1)

    def test_expiry_configuration_rejects_non_lot_tracked_product(self):
        template_model = TemplateModelStub()
        template = TemplateStub(tracking="none", use_expiration_date=False)
        self.adapter.env = EnvStub({"product.template": template_model})
        self.adapter.product_by_code = {"SKU-1": ProductStub(template)}

        with self.assertRaisesRegex(RuntimeError, "tracking='lot'"):
            self.adapter._ensure_expiry_product_configuration()

    def test_backfills_existing_lot_without_expiration_date(self):
        lot = LotStub(expiration_date=False, removal_date=False)

        self.adapter._ensure_lot_expiry(lot, "2027-12-31")

        self.assertEqual(lot.expiration_date, "2027-12-31 00:00:00")
        self.assertEqual(lot.removal_date, "2027-12-31 00:00:00")
        self.assertEqual(self.adapter.stats["lot_expiry_backfilled"], 1)
        self.assertEqual(lot.compute_calls, 1)

    def test_matching_expiry_is_not_overwritten_and_removal_date_is_recomputed(self):
        lot = LotStub(expiration_date="2027-12-31 00:00:00", removal_date=False)

        self.adapter._ensure_lot_expiry(lot, "2027-12-31")

        self.assertEqual(lot.expiration_date, "2027-12-31 00:00:00")
        self.assertEqual(lot.removal_date, "2027-12-31 00:00:00")
        self.assertEqual(self.adapter.stats["lot_expiry_backfilled"], 0)
        self.assertEqual(lot.compute_calls, 1)

    def test_conflicting_expiry_is_rejected_without_overwrite(self):
        lot = LotStub(expiration_date="2028-06-30 00:00:00", removal_date="2028-06-30 00:00:00")

        with self.assertRaisesRegex(RuntimeError, "Konflik expiry"):
            self.adapter._ensure_lot_expiry(lot, "2027-12-31")

        self.assertEqual(lot.expiration_date, "2028-06-30 00:00:00")

    def test_noop_backfill_write_is_rejected(self):
        lot = LotStub(expiration_date=False, removal_date=False, noop_write=True)

        with self.assertRaisesRegex(RuntimeError, "Readback expiration_date"):
            self.adapter._ensure_lot_expiry(lot, "2027-12-31")

    def test_missing_expiration_metadata_field_is_rejected(self):
        lot = LotStub()
        lot._fields = {"name": object()}

        with self.assertRaisesRegex(RuntimeError, "expiration_date/removal_date"):
            self.adapter._ensure_lot_expiry(lot, "2027-12-31")

    def test_missing_source_expiry_is_rejected(self):
        lot = LotStub()

        with self.assertRaisesRegex(RuntimeError, "Tanggal expiry sumber kosong"):
            self.adapter._ensure_lot_expiry(lot, "")


if __name__ == "__main__":
    unittest.main()
