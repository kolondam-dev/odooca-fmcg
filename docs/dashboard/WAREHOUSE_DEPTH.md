# Tahap 5 — Warehouse detail

Scope: current physical storage detail, actual movement-line throughput, explicit server event clocks, and company inventory/ledger diagnostic. Stacked after backlog3B closure, not a deployment or stage6 Three.js implementation.

## Sources and decisions

| Decision | Authoritative source / definition | Limitation and next action |
| --- | --- | --- |
| Zone/rack/bin/pallet position | Extend native `stock.location`; native hierarchy and warehouse membership | No parallel bin inventory ledger. Populate measured usable capacity and source, not building gross volume. |
| Pallet occupancy | Native `stock.package.parent_package_id` physical nesting; outermost explicitly classified pallet; one location only | Destination `outermost_package_id` is not used. Unclassified/split physical pallets prevent a complete slot ratio. |
| Capacity constraints | Explicit location usable m³/slots; native storage-category max weight converted from configured weight UoM to kg; one unambiguous pallet-type capacity rule | Alternative pallet-type rules are not summed. Carton-equivalent stock volume is not proof of stacking or weight safety. Parent rows include children and must not be summed. |
| Layout readiness | Verified local coordinate frame, dimensions in metres, source and company; verified child must fit verified parent's envelope | This prepares actual spatial data; does not generate an imaginary warehouse, rack, bin or vehicle position. Multiple verified frames in a warehouse are flagged. |
| Current stock health | Native quants per SKU/warehouse: on hand, reserved, available; lot expiry; missing required expiry | Quant `in_date` is an age proxy, unweighted median/p90 over positive positions. Not original lot receipt time. Negative positions remain visible exceptions. |
| Slow / inactive | Oldest positive position age and latest observed done customer outbound; warehouse thresholds default90/180 days | Inactive means no outbound in configured finite window, not never sold. Labels expose the observation horizon. No invented stock-cover denominator. |
| Throughput | Native done positive `stock.move.line`, WITA date, selected period; received/shipped/putaway/picking/other buckets | Each movement line counted once. Not order count, productivity per worker-hour or a sum of incompatible SKU units. Actual chart/tooltips and source list retained. |
| Picking/putaway/receipt dwell | New explicit clock actions on ready native operations; server start/end/actor, matching company; completion requires native done operation | Elapsed time includes waiting/click latency. Historical done moves do not acquire invented starts. Multi-step receiving must complete active linked receipt chain and reach storage. Median/p90 only completed events in period; running current and cancelled period separate. |
| Valuation diagnostic | Native Odoo19 product `total_value`; company `_get_accounts_by_product` and `stock_accounting_value` posted mapped-account balance | Company-wide current snapshot, accounting role only. Warehouse/category/period do not apply. Missing accounts unavailable. Difference is a reconciliation exception, not automatic loss/posting. Existing legacy standard-cost estimate remains separately labeled by its own scope. |

## Scope, control and operation

Warehouse selector affects this new detail section only. Category applies to SKU health/movement lines, not location occupancy or clocks. Vehicle does not apply. The existing cohort date inputs define movement/completed-clock period; stock/capacity/layout remain current. Native company/role ACL and rules remain in effect. No sudo read bypass or raw evidence payload exposure.

Stock managers maintain native location physical fields, pallet classification and observation policy. Operators can create/start their event clock; only starting worker or stock manager completes/cancels. Recorded facts, identity after start and completed/cancelled clocks cannot be edited/deleted via RPC/context defaults. Duplicate kind/operation clocks use a native picking row lock. Source corrections require a documented follow-up; no silent rewrite of an elapsed event.

Query guard: max1,000 locations,50,000 quants/movement lines/clocks,10,000 valuation products; exceedance returns an explicit narrow-scope error. UI shows first200 locations/SKU rows, with total and disclosure. No cache bypasses company/role. Read model never posts stock/accounting data or changes production masters.

## Acceptance evidence

Added native regressions: package nesting/slots/unknown dimensions, surveyed child geometry, invalid policy; server-fact context spoof/duplicate/idempotence/worker guard; stock aging and native movement classification; mapped posted valuation control. Added JS source-domain/stale-click regression and native CI fixture/screenshot at desktop/tablet/portrait. CI fixtures are restricted to disposable `ci_db` and never mutate the live server.

Local Ruff, manifest, XML/compile, Node and whitespace checks are implementation checks, not native PASS. Native install/upgrade/visual evidence and reviewer verdict must refer to final HEAD. Stage6 stays separate: sourced layouts must pass data acceptance before any Three.js scene is enabled.
