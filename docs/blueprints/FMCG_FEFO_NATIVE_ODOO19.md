# FMCG Native FEFO & Warehouse Picking Foundation — Odoo 19

## Source data audit (baseline 4f61086e680c530e560417b98800bcce341cca43)

The canonical registers already contain expiry and lot data:

- `initial_stock_20260701.csv`: 150 opening lots, all with expiry date `2027-12-31`.
- `inbound_po_intransit_june_lines.csv`: 194 received PO lot rows, all with expiry date `2028-06-30`.
- `perpetual_stock_event_ledger.csv`: 5,741 events, including 150 INITIAL_STOCK, 194 PO_RECEIPT, 2,738 SO_RESERVATION, 2,650 DO_DISPATCH, and 9 QUARANTINE_RECEIPT events.
- The 150 opening SKUs all have at least one inbound lot; 44 SKUs have two inbound lots (three lots total including opening stock).
- Total canonical lot identities across opening and inbound receipts: 344.

This is sufficient to exercise FEFO ordering in the disposable runtime: opening lots expire before inbound PO lots. The loader must not fabricate additional lots or expiry dates.

## Root cause addressed

The existing canonical loader populated `stock.lot.expiration_date` only when a lot record was newly created. Existing lots were found by name/product and then left unchanged. If those lots were created before `product_expiry` was installed, a later loader run would never backfill the now-available expiry field.

The updated loader:
1. Requires `product_expiry` metadata fields for the canonical seed.
2. Requires canonical products to use lot tracking and enables `product.template.use_expiration_date`.
3. Backfills a missing `expiration_date` on an existing lot from its canonical register row.
4. Never overwrites a conflicting non-empty expiry date; it fails for manual reconciliation.
5. Recomputes Odoo's native `removal_date` when it is missing and verifies readback.
6. Performs a final audit of all 194 inbound lots, including receipts already marked done.

## Native Odoo FEFO behavior

Odoo 19 FEFO is native, not a custom SQL sort:
- `product.template.use_expiration_date` must be enabled for the product.
- `stock.lot.expiration_date` feeds computed `stock.lot.removal_date`.
- FEFO quant ordering uses `removal_date, in_date, id`.
- Expiry-aware stock moves pass their scheduled date as `with_expiration`; native quant gathering excludes lots whose `removal_date` is earlier than that date.
- `stock.location.removal_strategy_id` can use the `product_expiry.removal_fefo` strategy.
- A product category strategy overrides the location strategy; child locations can also override parent fallback.

The loader configures FEFO on the seed warehouse stock location only when no conflicting strategy exists. It fails rather than silently overwriting a category or child-location strategy that would defeat FEFO.

## Warehouse slotting boundary

The seed product master contains complete carton dimensions, carton volume, and carton weight for all 150 SKUs; carton volume matches length × width × height for all rows.

The existing master-data enrichment created nine warehouse zones beneath `WH/Stock` (main/bulk, eaches, returns, bad stock, promo, premium, cold, dock, in-transit). However:
- opening stock and PO receipts are currently placed in `WH/Stock`;
- no canonical SKU-to-bin assignment or putaway rules are present;
- the nine zones are not evidence of actual rack/bin placement or capacity.

Therefore the first FEFO implementation uses the real stock location and lot reservation results. It must not invent bin assignments. A later slotting phase needs verified rack/bin identifiers, capacities, and SKU placement rules before recommending or automatically assigning detailed pick paths.

## Safety boundary

This change modifies loader/configuration code only. It does not execute against the live database, move quants, rewrite stock moves, change valuation, or deploy. Runtime verification must occur in disposable Odoo first; live activation requires separate explicit authorization.
