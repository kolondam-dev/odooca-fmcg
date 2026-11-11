# D1 visual review baseline and explicit deviations

The source references are the owner's `D1 · Sales Performance.png` and the approved `D1_Popover_Approved.html` from `ODOO_FMCG_Dashboard_Redesign_v2.zip`. SHA-256 values are recorded in `report.json`. These references contain fictional figures and are visual/interaction baselines, not numerical oracles for the native fixture.

| Aspect | Native implementation / review decision |
|---|---|
| Layout | Eight KPI cards in a four-by-two desktop grid, principal/channel panels, Sulut map and two-column city ranking, daily trend, monthly combo, top-eight table and scatter. Responsive layouts are captured at 1440, 1024 and 768. |
| Native shell | Odoo navigation remains visible above D1. A stitched full-dashboard image excludes the navigation and preserves the original CSS/layout; all original scroll captures are included. |
| Period and filters | The approved v2 anchored popover and pinnable inline panel replace the original PNG toolbar's conventional popup. Open period/filter panels and pinned inline states are separately captured. |
| Figures and dates | Deterministic native October 2026 fixtures replace the PNG's November examples. Refund invoice-date / gross-SO ratio is labelled explicitly; SO net is not reduced again. Source reconciliation is in `fixture.json`, including individual salesperson scope. |
| Missing values | No estimated target/PJP fallback. A September case deliberately lacks matching targets and plans. Unavailable achievement uses a plain dash, not `—%`. |
| Scatter labels | Only the two highest-net salespeople are labelled continuously; every point retains its full name as accessible label and hover title. This prevents overlapping labels for identical call rates. |
| Negative monthly bars | Red upward magnitude plus signed numeric label is the intentional existing encoding. `negative-1440-full.png` preserves this case for review; it is not a positive revenue value. A reserved label band separates line percentages from bar amounts. |
| Calendar | The live alignment checkbox is disabled until an approved company working-day/holiday contract exists. The mock's Monday–Saturday simulation is not promoted to business truth. |
| Geography | Native city codes and source net values populate the provided Sulut shapes. The ranking retains unassigned/out-of-map records. Only city-level source drill is advertised. |
| Sources and targets | Current fields use confirmed SO, native line discount, posted refund, exact-date complete target partitions, accepted check-ins and assigned days. The mock's arbitrary sparklines, threshold 7% and daily target guide are not invented when no source contract exists. |
| Acceptance | Automated checks establish native rendering, geometry, interaction, source reconciliation and screenshot provenance. They do not declare pixel-perfect visual approval. The reviewer/owner compares the included PNG and views and records visual acceptance separately. |

Open `index.html` after extracting the CI artifact. `report.json` records PR HEAD, checkout SHA/tree, production-source hashes, screenshot hashes/sizes and browser assertions. `fixture.json` records expected numbers derived from fixture inputs and native role-specific reconciliation. No live database or Railway activation is used.
