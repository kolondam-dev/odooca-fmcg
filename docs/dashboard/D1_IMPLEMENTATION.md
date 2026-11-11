# D1 — Sales Performance & Salesforce Productivity

Task Managed by Agent Codex-Dashboard

## Scope

Base: `main` at `2d7c37cad38bf9bed7e9233a2e3ea7dfa7049357`.
Branch: `agen/d1-dashboard-(Codex-Dashboard)`.

This release installs two optional addons: `id_dashboard_ui` (reusable OWL components, styles, locally bundled Inter font) and `id_dashboard_redesign` (D1 read service, action and adapter). Only the existing Sales Productivity action is retargeted. Its XML ID and menu invocation remain unchanged. WMS, Finance, D2–D6, posting, order processing, mobile commands, seed and Railway configuration are unchanged.

The baseline is the owner's PNG, with the approved anchored popover / pinnable inline controls from package v2. The production asset bundle contains no preview data. Other page compositions in the UI library are presentation building blocks; they do not register or expose additional dashboard actions.

## Data contract

All reads use the current ORM user, record rules and selected companies. Business record reads never use `sudo`. Selected companies must share a company currency. SO foreign currency uses the existing service's explicit exchange-rate checks and WITA order-date conversion.

| Presentation | Source and meaning |
|---|---|
| Gross SO | Confirmed SO product lines: subtotal + native quantity × unit price × discount %. Signed adjustments retained; tax excluded. |
| Net SO | Sum of the same line subtotals. Gross minus native line discount; refunds are not subtracted again. |
| Posted refunds / gross SO | Posted customer refund product-line balance in company currency, by invoice date, divided by selected-period gross SO. This is a cross-flow ratio, **not** a return rate for the selected SO cohort. Draft refunds excluded. Product dimensions apply directly; order dimensions require a matching linked SO line. |
| Target achievement | Selected SO net / an exact-date, complete salesperson target partition. All readable active Sales users in selected companies form the denominator universe, including zero-sales users; users without the all-leads Sales role are restricted to their own target universe. No summing of overlapping principal/channel/area targets and no invented MTD proration. Partial scope/period or missing target gives unavailable. |
| Discount | Native SO line discount / gross SO. Not an inferred all-in commercial discount. |
| Effective call | Existing accepted check-in proof and subsequent SO for exact user, company, outlet and WITA day. Photo alone is not a visit. Mobile ACLs retained. |
| Calls / assigned workday | Accepted visits / distinct readable (company, salesperson, assigned business date) slots. Calendar days are not used as a proxy. Product/geographic slices make call metrics unavailable because a matching planned denominator is absent. |
| AOV | Filtered SO line net / distinct orders containing those lines. A mixed-SKU order is counted once; excluded lines do not enter its amount. No orders gives unavailable. |
| Principal, channel, city ranking | Same signed line net, same filters and dates. Missing dimensions remain explicit Unassigned rows. Shares divide by selected net; negative values retain signs. |
| Daily trend | All calendar dates in the selected WITA range, including actual zero-sales dates. Real monetary sparklines use these aggregates. Comparison trend aligns ordinal day positions; longer comparison tails are omitted from the line while comparison totals retain their complete date range. |
| Monthly context | Five calendar months ending at the selected end date, same dimension filters. Zero months remain zero; discount without a gross denominator is a gap, not 0%. This wider window is explicitly labelled. |
| Top 8 / scatter | Salespeople ordered by signed net; teams come from source SO teams. Accepted planned users with no sales remain zero-sales rows. Scatter requires a readable assigned-day denominator. Bubble size uses distinct active SO outlets. |
| Coverage map | Owner-supplied North Sulawesi geometry keyed to authoritative city codes. Kemendagri codes are preferred; four-digit BPS codes normalized. Out-of-map and unassigned locations remain in the ranking. City clicks open scoped source lines; district/village map hierarchy is not advertised. |

Periods accept 1–366 inclusive calendar dates. Comparison modes: previous equivalent period, prior year, prior quarter, or custom range; month-end clamping matches the controls. MTD/last-month/YTD presets use calendar shifting rather than a guessed fixed day count. **Working-day alignment is disabled pending an approved company calendar and holiday contract.** Saved views are not exposed.

Filters: salesperson, channel, coverage area, city, principal, brand and SKU. OR within a selection; AND between dimensions; Include/Exclude supported by server-owned ORM paths. Child selections are never silently discarded. Invalid, inaccessible or deleted IDs fail before aggregation. Catalogues and selected IDs are bounded; large queries fail explicitly rather than returning partial totals.

## Integration and controls

- `models/dashboard_bridge.py`: validated query, native aggregation and independent source domains. The original `id.sales.productivity` API is unchanged.
- `static/src/adapters.js`: formatting and component props, source availability, currency/unit labels, and scoped drill metadata.
- `static/src/action.js`: authenticated RPC, request-generation guard, commit-after-success query state, native document actions and temporary `id_shell` dashboard lease.
- `ApprovedControls`: OWL lifecycle wrapper around a scoped DOM controller. Unique instance IDs, escaped source labels, listener cleanup, staged edits, async Apply, pending-control lock and focus restoration. Data refresh preserves the active controller. Initial RPC errors retain a recovery toolbar so users can narrow and retry the query.
- `pages/pages.xml`: D1 composition. Components receive data rather than query the database. No CDN, mock fallback or arbitrary caller-supplied domain reaches the service.
- Uninstall restores the old Sales action only if its current tag still belongs to this addon; another customization is preserved.

## Reproducible validation

Native local runtime: Odoo 19 source `aa121b1711e26846ec914341f4a610cf30b64422`, PostgreSQL 17.11, Python 3.12.14. No production database was used.

```bash
ruff check .
python scripts/check_manifests.py
node --test docs/ui/e2e/dashboard*.test.cjs
odoo -d d1_clean --addons-path <core>,addons --without-demo=true \
  -i id_dashboard_redesign,id_mobile_api --test-tags /id_dashboard_redesign --stop-after-init
odoo -d d1_clean --addons-path <core>,addons \
  -u id_dashboard_ui,id_dashboard_redesign --test-tags /id_dashboard_redesign --stop-after-init
```

The CI workflow repeats installation and upgrade on isolated `d1_ci`, leaving the existing legacy UI smoke database untouched. Dedicated current-HEAD browser/screenshots now run on isolated D1 CI, with representative fixture and image/source fingerprints. See `D1_CI_VISUAL.md`. Native browser acceptance: `scripts/ui/test_d1_browser.py`; provision only a disposable `d1_` database with `scripts/ui/d1_fixture.py`, supplying `D1_TEST_PASSWORD` privately via environment. Optional `D1_BROWSER` selects the installed headless browser. No credential is committed. The native browser test injects one initial RPC failure and proves controls and a successful retry remain available.

Verified locally: clean install and upgrade (12 native test methods), 27 static dashboard regressions, native OWL compilation and browser checks at 1440/1024/768 pixels. See `D1_VERIFICATION.json` for final counts. Browser checks cover popovers within viewport, no page-level horizontal overflow, Escape/focus, inline displacement, custom comparison Apply, SKU Apply and native scoped document drill. Native source tests cover WITA boundaries, signed money, mixed-SKU line attribution, posted refunds, exact target coverage, role/company isolation, accepted visits and uninstall behavior.

## Review and activation

The implementation is ready for review, not automatic live activation. Local screenshots were inspected against the PNG for layout; exact pixel equivalence and representative seeded production-like data acceptance remain reviewer/owner gates. Missing targets/plans/master geo links are displayed honestly rather than filled with mock values. The original mock's fictional KPI values are not an acceptance oracle for real transactions.

After review and explicit activation authorization, install `id_dashboard_redesign` on staging, validate actual seed figures and role-specific views, then decide rollout. Do not add this module to production INIT_MODULES or trigger Railway deployment as part of this PR. Rollback is module uninstall plus native action-tag verification.
