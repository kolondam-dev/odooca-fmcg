"""Disposable local D1 browser fixture. Never run on a live database."""
import os
from datetime import datetime

if not env.cr.dbname.startswith("d1_"):  # noqa: F821
    raise RuntimeError("D1 fixture requires a disposable d1_ database")
admin = env.ref("base.user_admin")  # noqa: F821
admin.password = os.environ["D1_TEST_PASSWORD"]
company = env.company  # noqa: F821
pricelist = env["product.pricelist"].create({"name": "D1 QA currency", "currency_id": company.currency_id.id})  # noqa: F821
principal = env["id.principal"].search([], limit=1)  # noqa: F821
city = env["id.city"].search([("kode_kemendagri", "=", "71.71")], limit=1)  # noqa: F821
district = env["id.district"].search([("city_id", "=", city.id)], limit=1)  # noqa: F821
env["res.partner"].search([("name", "=", "D1 QA outlet")]).write({"district_id": district.id})  # noqa: F821
partner = env["res.partner"].create({"name": "D1 QA outlet", "district_id": district.id})  # noqa: F821
product = env["product.product"].create({"name": "D1 QA SKU", "type": "consu", "principal_id": principal.id})  # noqa: F821
for day in ([] if env["sale.order"].search_count([("partner_id.name", "=", "D1 QA outlet")]) else range(1, 29)):  # noqa: F821
    sale = env["sale.order"].create({"partner_id": partner.id, "user_id": admin.id,  # noqa: F821
        "pricelist_id": pricelist.id,
        "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": 100 + day,
                              "price_unit": 10000, "discount": day % 10})]})
    sale.action_confirm()
    sale.date_order = datetime(2026, 10, day, 4, 0)
env.cr.commit()  # noqa: F821
