# D1: native browser and visual evidence in CI

Task Managed by Agent Codex-Dashboard

This closes the reproducibility gap identified in PR #113's review of `d18a051`: legacy browser CI on `ci_db` was not D1 coverage. Draft/Ready status did not cause that gap. The new steps explicitly provision and serve the optional redesign on `d1_ci`, port 8071, using a separate filestore. Legacy UI smoke still runs on its original database and port.

## Evidence to review

Download `d1-native-visual-<full PR HEAD SHA>` from the CI `install-test` job and open `index.html` after extraction.

- `report.json`: actual PR HEAD, synthetic checkout SHA/tree, image digest, production-source hashes checked against the running image, image dimensions/hashes, assertions and status. CI provenance is distinct from the earlier local verification JSON.
- `fixture.json`: deterministic input-derived expectations and 30 native reconciliation assertions across 224 confirmed October SOs, eight salespeople, four principals/channels/cities, 224 assigned days, 192 accepted visits, 152 effective calls, complete targets and one posted versus one draft refund. No fictional mock KPI is used as a numeric oracle.
- `dashboard-<width>-full.png`: the whole native D1 content stitched from unaltered scroll captures at 1440/1024/768. Individual scroll captures and top views are retained. The DOM and CSS are not resized for the stitch.
- `period-open-*`, `filter-open-*`, `filter-inline-*`: actual open controls. The tests switch pinned inline back to popover and verify that the footer is on top and clickable, not merely visible in the DOM.
- `initial-error-1440.png`, `loading-retry-1440.png`: deliberate initial get_data failure and native retry loading state. The injected response is isolated to that fault test; subsequent data and document reads are real native RPCs.
- `negative-1440-full.png`, `negative-unavailable-1440.png`: signed September data, missing target/PJP and the documented red magnitude encoding for negative monthly bars.
- `scoped-native-drill-1440.png`: native filtered order-line action.
- `own-sales-role-1440-full.png`: separately authenticated ordinary salesman; native RPC must return only 28 orders and his own source amount. Other users are also checked in fixture reconciliation; a non-Sales role must be rejected.
- `reference/approved.png`, `reference/approved-controls.html`, `reference/DEVIATIONS.md`: original approved baselines and explicit semantic/layout deviations. Numeric differences follow the native fixture inputs.
- `runtime-source.json`, `server.log`, `browser.log`, `fixture.log`: source chain and failure diagnostics. Artifacts upload even when the job fails; artifact existence alone is not a PASS. Check report status and the job conclusion.

Artifacts have a 30-day retention period. Source references and executable fixtures remain in the repository. No Railway deployment or live database is needed.

## Defects caught by the expanded case

The representative filter catalogue reproduced footer occlusion after unpinning at 1024px: the isolated controls root had no stacking order above subsequent dashboard content. The root now has an explicit z-index and browser hit-testing verifies the footer before an ordinary click. No force-click or weaker assertion is used.

The Top 8 unavailable achievement now uses a plain dash. Small negative monthly amounts retain sufficient decimals rather than displaying `-0`. A separate 28px label band now prevents the percentage-line label from overlapping a high negative-magnitude bar label. The browser bounding-box assertion was reproduced failing before this fix and passing after it. Scatter keeps continuous labels for the top two and full names on every point via title/accessible label, avoiding label overlap for identical call rates.

## Acceptance boundary

Automated native browser checks and reconciled fixtures make current-HEAD evidence inspectable. They do not confer an independent visual approval: compare the screenshots and references, review the recorded deviations, and decide visual acceptance separately. This agent implemented the fixes and inspected its own output; reviewer acceptance remains distinct. The earlier 12 native backend methods remain unchanged and continue to run in CI.
