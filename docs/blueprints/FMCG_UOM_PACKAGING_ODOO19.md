# FMCG SKU UoM & Packaging Architecture — Odoo 19

## Decision

Use the native Odoo 19 unit hierarchy. Do not use the removed `product.packaging` model or the removed `product.template.uom_po_id` field.

Odoo 19 uses:
- `uom.uom.relative_uom_id` and `relative_factor` to express a hierarchical conversion chain.
- `product.template.uom_ids` to expose additional units/packagings that may be selected for that product.
- `product.uom` to associate product-specific barcodes with a UoM.
- `product.supplierinfo.product_uom_id` for vendor-specific purchase units.

References:
- Odoo core change: https://mergebot.odoo.com/odoo/odoo/pull/184131
- Odoo 19 UoM documentation: https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/product_management/configure/uom.html
- Odoo 19 packaging documentation: https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/product_management/configure/packaging.html

## Data invariants

1. Existing `product.template.uom_id` remains the inventory/base UoM for the current database. This implementation does not rewrite it.
2. The FMCG base label (Pcs, Sachet, Botol, Pouch, Box) is represented by an equivalent 1:1 UoM and linked through `uom_ids`.
3. Inner and carton UoMs are attached to the product and use SKU-specific ratios. A shared global "Karton" UoM with factor 1 is not a valid conversion.
4. The loader never changes an existing UoM conversion factor. If an existing SKU mapping differs from the requested master ratio, it fails and requires a controlled migration.
5. Historical transaction quantities, stock quant quantities, valuation layers, and posted accounting entries are not rewritten by this configuration.

## Current master data audit

At baseline `4f61086e680c530e560417b98800bcce341cca43`, `data/seed/products_150.csv` contains 150 SKUs:

| Base label | SKU count |
| --- | ---: |
| Pcs | 70 |
| Sachet | 28 |
| Botol | 28 |
| Pouch | 22 |
| Box | 2 |

- 56 SKUs have an inner tier (`inner_qty > 1`).
- 94 SKUs have no distinct inner tier (`inner_qty = 1`).
- All 150 SKUs have a carton quantity greater than one.
- All 150 ratios satisfy `carton_qty % inner_qty == 0`; no divisibility anomaly was found.

The source currently does not define the actual business name of the intermediate tier. The loader therefore uses the neutral label `Inner`; replace it with Pack/Renceng/etc. only when the SKU-specific master value is confirmed.

## Implementation boundary

This milestone adds the native product-level UoM hierarchy and keeps the existing inventory UoM unchanged. It does not yet change sales/purchase transaction defaults, add quantity breakdown columns to documents, or implement picking/packing/delivery reports.

The next milestone must:
- expose the product's base/inner/carton UoMs in the Sales Order selector;
- preserve native conversion into the existing inventory UoM for stock moves;
- show a derived breakdown from one canonical quantity on SO, picking, packing, delivery, and invoice documents;
- configure vendor-specific purchase UoM through `product.supplierinfo.product_uom_id`, not a removed product-level field.
