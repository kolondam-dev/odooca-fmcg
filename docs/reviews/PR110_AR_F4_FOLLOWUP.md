# PR #110 AR/F4 follow-up — candidate evidence and remaining gates

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

**Pending [BU]:** Full 11-suite CI and full F4 must pass on the exact candidate commit in a disposable CI DB. Inspect each unique required PR job, logs, and runtime report; distinguish PR synthetic merge from head SHA and verify their trees or integration diff. Independently review legitimate manual AR adjustments and the canonical `112000` result on full-period data. A CI failure is a HOLD, not a reason to weaken the oracle. Clone re-apply and original demo apply remain **HOLD**; merge and deploy require separate authorization.
