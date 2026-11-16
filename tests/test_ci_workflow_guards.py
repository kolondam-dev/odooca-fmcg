"""Kontrak guard langkah runtime pada workflow yang dipilih berdasarkan dampak.

Job seperti `init-test` dan `install-test` selalu berjalan agar nama check tetap
muncul, lalu langkahnya sendiri yang dilewati ketika planner tidak memilih suite
runtime. Langkah tanpa guard akan mengeksekusi `docker exec` pada container yang
tidak pernah dibuat: PR docs-only #147 gagal karena satu langkah I3 ditambahkan
tanpa `if: needs.changes.outputs.odoo_init == 'true'`.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
IMPACT_GUARD = re.compile(r"needs\.changes\.outputs\.\w+")


def impact_guarded(step_or_condition) -> bool:
    """True bila langkah/kondisi merujuk flag impact plan.

    Rujukan di `if:` adalah bentuk utama. Rujukan di `env:` juga diterima karena
    gate agregasi seperti `seed-invariants` membaca flag di `env` lalu memutuskan
    sendiri apakah suite dipilih, sehingga langkahnya tetap eksplisit.
    """
    return bool(IMPACT_GUARD.search(str(step_or_condition or "")))


def step_gated_jobs(workflow: dict):
    """Job yang menggerbangi langkahnya sendiri dengan flag impact plan.

    Job terkualifikasi bila bergantung pada `changes`, tidak punya guard tingkat
    job, dan setidaknya satu langkahnya memakai guard impact. Job agregasi seperti
    `pwa-gate` tidak punya langkah ber-guard sehingga sengaja selalu dieksekusi.
    """
    for name, job in (workflow.get("jobs") or {}).items():
        needs = job.get("needs") or []
        if isinstance(needs, str):
            needs = [needs]
        if "changes" not in needs or impact_guarded(job.get("if")):
            continue
        steps = job.get("steps") or []
        if not any(impact_guarded(step.get("if")) for step in steps):
            continue
        yield name, job


def unguarded_run_steps(workflow: dict) -> list[str]:
    problems = []
    for name, job in step_gated_jobs(workflow):
        for step in job.get("steps") or []:
            if "run" in step and not impact_guarded(step):
                problems.append(f"{name} :: {step.get('name') or '<unnamed>'}")
    return problems


def load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


class TestWorkflowImpactGuards(unittest.TestCase):
    def test_every_run_step_in_step_gated_jobs_has_impact_guard(self):
        problems = []
        for path in sorted(WORKFLOWS.glob("*.yml")):
            workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
            problems += [f"{path.name} :: {item}" for item in unguarded_run_steps(workflow)]
        self.assertEqual(
            problems,
            [],
            "Langkah `run` tanpa guard impact plan akan mengeksekusi container "
            "saat suite tidak dipilih; tambahkan `if: needs.changes.outputs.<flag> ...`.",
        )

    def test_init_test_runtime_steps_are_gated_by_odoo_init(self):
        workflow = load("ci.yml")
        job = workflow["jobs"]["init-test"]
        names = {
            step.get("name")
            for step in job["steps"]
            if "run" in step and "needs.changes.outputs.odoo_init" in str(step.get("if"))
        }
        self.assertIn("Diagnostik costing I3 read-only dan regresi lingkup perusahaan", names)

    def test_missing_step_guard_is_reported(self):
        workflow = {
            "jobs": {
                "init-test": {
                    "needs": ["static", "changes"],
                    "steps": [
                        {"name": "Entrypoint runtime not selected",
                         "if": "needs.changes.outputs.odoo_init != 'true'",
                         "run": "echo PASS"},
                        {"name": "Tanpa guard", "run": "docker exec -i odoo true"},
                    ],
                }
            }
        }
        self.assertEqual(unguarded_run_steps(workflow), ["init-test :: Tanpa guard"])

    def test_env_reference_counts_as_explicit_gate(self):
        workflow = {
            "jobs": {
                "seed-invariants": {
                    "needs": ["changes", "invariant-tests"],
                    "steps": [
                        {"name": "Validate artifacts",
                         "if": "needs.changes.outputs.seed == 'true'",
                         "run": "python scripts/ops/verify_seed_invariants.py"},
                        {"name": "Require selected unit gate",
                         "env": {"SELECTED": "${{ needs.changes.outputs.seed }}"},
                         "run": "test \"$SELECTED\" = true"},
                    ],
                }
            }
        }
        self.assertEqual(unguarded_run_steps(workflow), [])

    def test_gate_job_without_step_guards_is_not_flagged(self):
        workflow = {
            "jobs": {
                "pwa-gate": {
                    "needs": ["changes", "pwa-quality"],
                    "steps": [{"name": "Require client and hosting gates",
                               "run": "test \"$RESULT\" = success"}],
                }
            }
        }
        self.assertEqual(unguarded_run_steps(workflow), [])

    def test_job_level_guard_covers_every_step(self):
        workflow = {
            "jobs": {
                "upgrade-proof": {
                    "needs": ["changes"],
                    "if": "needs.changes.outputs.upgrade == 'true'",
                    "steps": [{"name": "Tanpa guard langkah", "run": "docker run --rm x"}],
                }
            }
        }
        self.assertEqual(unguarded_run_steps(workflow), [])


if __name__ == "__main__":
    unittest.main()
