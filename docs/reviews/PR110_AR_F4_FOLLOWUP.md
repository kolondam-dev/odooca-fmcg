# PR #110 AR/F4 follow-up — candidate evidence and remaining gates

## PR #213 oracle blocker follow-up (2026-11-28; TAMBAH)

**[F] Repaired source SHA `5e545ab8b49f01e933be258fff3e81576f1aa421`:** [F4 46127916187](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/46127916187) PASS in two disposable databases, and [Full Regression Gate 46127916276](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/46127916276) PASS with exact-SHA verdict. F4 report: scenario A zero drift PASS; scenario B PASS and digest MATCH; audit PASS with zero violations; fault injection PASS. Both scenario audits checked 2,514 posted-by-cutoff invoices, 345 open, source/observed residual `2,368,135,989.94`, mismatch count **0**. Ledger account `112000`: GL = invoice residual `2,368,135,989.94`, refund `0`, unallocated payment `0.00`, other `0.00`. Runtime negative control: `PAY-AR-01753` shifted from paid `INV-202608-0255` to equal-amount open `INV-202608-0197` inside savepoint; GL unchanged, per-account invoice residual unchanged, ledger tieout violations **0**, independent source invoice mismatches **2**, rollback digest MATCH. This is the required executable counterexample and preserves the per-account ledger evidence.

**[BU] Release decision remains separate:** PR #213 remains draft; independent reviewer acceptance and merge/deploy authorization remain HOLD. Documentation-only evidence commit after `5e545ab` must be independently tied to exact head SHA; it does not change the reviewed verifier/loader/tests. Clone re-apply, demo apply and July invoice changes remain HOLD.

**[F] First runtime iteration `4f3de1d7cb68b70546d56560e2b415b8c1306384`:** Full Regression Gate [46123600595](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/46123600595) passed exact-SHA. F4 [46123600682](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/46123600682) **failed** after Scenario B because the negative-control setup searched a hard-coded company name and could not find it (`RuntimeError: AR probe company not found`); no successful ORM wrong-invoice result can be claimed from this run. Fix resolves the unique posted donor invoice first and obtains the company from `donor.company_id`, then scopes the target and payment to it. The final SHA needs a new F4 run; prior full regression does not substitute for it.

**[F] Root cause of apparent source/GL gap:** The August pack has 50 carry-forward invoices dated **2026-09-01**, totalling `195,474,994.89`. These are listed under `closing_state.carry_invoices`, not `open_invoices`. The naive August pack total `2,563,610,984.83` minus this future amount is exactly `2,368,135,989.94` at the `2026-08-31` cutoff. The approved July register (fingerprints in the canonical reconciliation), July cash/early discounts, August pack invoices and cash, plus closing-state membership now provide an independent source expectation: 2,514 posted-by-cutoff invoices, 345 open, `2,368,135,989.94`. The approved July 31 AR checkpoint is 309 invoices / `2,370,371,980.58`. No DB reconciliation link is used in this expectation.

**[F] Production oracle:** `scripts/ops/verify_disposable_period_pack.py` now checks *each* posted customer invoice's summed receivable-term residual at cutoff (including paid zeroes), with strict identity and ±`0.01` tolerance. It retains the old signed ledger per-account breakdown. Missing/unknown/duplicated invoice identities and mismatched source closing membership fail closed. A runtime negative control selects August source payment `PAY-AR-01753` for fully paid `INV-202608-0255` and redirects it to the equal-amount open `INV-202608-0197` within account `112000`, inside a rollback-only savepoint. It requires unchanged GL and per-account invoice total, old ledger tie-out PASS, independent source oracle FAIL for both invoice IDs, and digest/restored state match after rollback. No historical July source is modified.

**[F] Local unit evidence:** 92 tests + 9 subtests passed (`python -m pytest tests/test_period_pack_loader.py -q`), `python -m ruff check .` PASS, `python scripts/check_manifests.py` PASS. Unit counterexample shows the legacy ledger assertion passes both allocations with identical GL and account residual, while the new independent oracle fails the wrong allocation on *both* invoice IDs.

**[F] Runtime closure at source SHA `5e545ab`:** F4 full two-DB check and full regression exact-SHA PASS (details above). Test impact **TAMBAH**, with direct unit counterexample and F4 runtime integration probe; `scripts/ops/verify_disposable_period_pack.py` / `tests/test_period_pack_loader.py` trigger F4, and the fail-closed CI impact plan selects full 11-suite regression. PR remains draft; merge, deploy, clone re-apply and original demo apply HOLD; July invoice freeze remains in force. The earlier `81aa3a8` / `e722b28` PASS below belongs to the **old** oracle only.

**Scope [F]:** PR #110 is merged. This follow-up is based on `origin/main` at `6de45c50bdf902ab79bc4d1ab1032f5846b1b30c`, not the old PR branch. The three original files at this base are byte-identical to the v2 patch base `f66e4cc60fe53d71d07b407194d95c7c57d1b429`; the patch changes exactly `scripts/ops/load_period_pack.py`, `scripts/ops/verify_disposable_period_pack.py`, and `tests/test_period_pack_loader.py`. No frozen July record, demo instance, or clone was applied by this follow-up.

## Reproducible source and probe provenance

| File / artifact | SHA-256 |
| --- | --- |
| `scripts/ops/load_period_pack.py` | `a38c09b51445df459e3ee09e4b6c326eb443609fc5a20e8965d005d6464adae2` |
| `scripts/ops/verify_disposable_period_pack.py` | `7487cffefd1c9387eb01537a59ff85775ffa4cb2b58ef4d240090a32e02eee91` |
| `tests/test_period_pack_loader.py` | `49cc057b3c341449625ec31e8bd32152ab2de0703556fcab3d4cbd6d11791b8a` |
| private three-file review ZIP v2 | `2dfb69891719be42f954a52c2cf0b9f76628692b2ec1f74e7266c0b1db722f80` |
| private three-file patch v2 | `e3eb573f40cfa0bbac09abeae99397de19348910046091e01f51935d740278b5` |
| private rollback-probe scripts/log ZIP | `76dca6852804c89ac529fdec0af2d384a2fc43f6b292aaf25952bb376e642532` |

The full **three-file diff is in this branch** (`git diff origin/main...HEAD --` and the three paths above). The private ZIPs remain outside git under `20261127-pr110-rehearsal-baseline` in the operator's backup folder; hashes identify the reviewed artifacts without publishing raw runtime logs, database contents, filestore or secrets. CI artifacts from this branch/PR are the shareable exact-SHA runtime evidence once the jobs finish. Source hashes above were also checked on the disposable runtime probe. The missing historical commit object `7f8a0d45…` is **not** claimed as a source.

## Test impact: TAMBAH

The prior validator rejected an invoice whose first term was paid and second remained open; the added counterexample checks a single account across terms, correct open residual and payment coverage, plus native rollback-only reconciliation of both terms. The prior F4 compared all GL receivable entries only to invoice residual; the added counterexamples separately cover refund, unallocated payment, later-dated reconciliation, identified vs unidentified other posted AR entries, and offsetting differences across accounts `112000` and `11210010`. The per-account signed-open oracle and canonical `112000` assertion must not be relaxed. `scripts/ops/*.py` are unmapped by `.ci/test-impact.yml`: planner fails closed to **full regression (11 suites)**. PR-triggered `.github/workflows/period-pack-runtime.yml` runs the **full F4** on two fresh CI disposable databases; `Full Regression Gate` runs the selected suites. A green static gate alone does not accept seed data.

**Local checks [F]:** `python -m pytest tests/test_period_pack_loader.py -q`: 90 passed, 9 subtests; `python -m ruff check .`, `python scripts/check_manifests.py`, `git diff --check` pass. The operator's earlier dry-run and native probes used a *different* disposable rehearsal DB (`pr110_restore_probe_20261127`), all rollback-only. Two-term invoice on `112000`: first term paid, second remains open and is accepted by dry/apply-path validation, then reconciles without remapping the account. Native F4 **slice** at August cutoff: posted GL `112000` Rp588,000 = open invoice Rp1,110,000 − refund Rp222,000 − unallocated payment Rp300,000; a September reconciliation does not change the August snapshot. Business/config digests returned to baseline and filestore comparison matched 1,198/1,198 files. These are **not** full F4 or permission to apply.

## Exact-SHA gates passed at `81aa3a89b667d4e1a5a382e2155cb912585d0234`

All runs below are on candidate head `81aa3a89…` (PR #213, base `6de45c50…`). The PR synthetic merge `a149039011d596e95272f43f6fc3e36d56c23b49` has the **same tree** `30e750eea03c2daf6f99e66d114544ad1ffc0e82` as the head; `git diff` between them is empty. This evidence commit only adds documentation, so the three source hashes above are unchanged.

| Run | Event | Result |
| --- | --- | --- |
| `CI` [46099561690](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/46099561690) | pull_request | success (static, install-test, init-test) |
| `Period Pack Runtime Verification` (full F4) [46099561792](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/46099561792) | pull_request | success |
| `Full Regression Gate` [46099658002](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/46099658002) | workflow_dispatch, `ref=81aa3a8…`, purpose release | success, all suites + `Exact-SHA full regression verdict` |
| `Seed supervision` / `PWA quality` / `Finance I0 candidate spike` / `Android native` / `Full Dataset Runtime Verification` / `Upgrade Runtime Verification` | pull_request | success |

F4 runtime report (`period-pack-runtime-report`, run `46099561792`): `scenario_a_zero_drift: PASS`; `scenario_b_continuation.status: PASS` with `digest_comparison: MATCH`; audit `violations: []`; `receipt_to_cash_slice` and `historical_commercial_slice` PASS; `rejection_trace_rollback: REJECTED_AND_RESTORED`; fault injection PASS with rollback zero drift; `STATUS: RUNTIME VERIFICATION COMPLETED SUCCESSFULLY.`

Full-period AR tieout at cutoff `2026-08-31`, account `112000`: GL `2,368,135,989.94` = signed open invoice `2,368,135,989.94`, refund `0`, unallocated payment `0.00`, other `0.00`, `other_sources: []`. This answers the reviewer's full-data question: on the canonical period dataset the extra signed buckets are zero, so the canonical `112000` assertion holds unchanged, while the components would expose refund/unallocated/other differences instead of silently passing. AP `211000` GL `7,666,137,600.00` equals open bill residual.

**Remaining [BU]:** independent source review and a merge/deploy decision. This evidence commit re-runs the two exact-SHA gates; results are reported in PR #213. Clone re-apply and original demo apply remain **HOLD**; July stays frozen; no dump, filestore, credential or raw probe log is in git.
