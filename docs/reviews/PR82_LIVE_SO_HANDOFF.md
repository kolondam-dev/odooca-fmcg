# PR82 live SO repair and integration

Authenticated sales.order.submit, including discount requests, is forwarded to Odoo. Pending SO receipts retain their official reference and cannot be approved through the local discount simulator. Browser approval simulation is confined to the HTTP test fixture. Delivery synchronization remains deferred.

Integrated main cfcf4cc (#83). Historical handoff entries remain available in the unchanged parent commits: PR82 at 546ab1a:docs/HANDOFF.md and main at cfcf4cc:docs/HANDOFF.md. The integrated HANDOFF file retains main verbatim; this scoped addendum records the PR82 repair without duplicating historical operational notes.

Local validation: 387 PWA unit tests, typecheck, contract drift, three builds, Ruff, 10 manifests and 18 dashboard RPC tests passed. Added native Odoo regression for persisted discounted draft SO, official pending receipt and idempotent replay. Final exact-SHA CI and native execution pending; no merge/deployment performed by this change.
