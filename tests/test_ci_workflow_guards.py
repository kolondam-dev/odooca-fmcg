"""Kontrak guard langkah runtime pada workflow yang dipilih berdasarkan dampak.

Job seperti `init-test` dan `install-test` selalu berjalan agar nama check tetap
muncul, lalu langkahnya sendiri yang dilewati ketika planner tidak memilih suite
runtime. Langkah tanpa guard akan mengeksekusi `docker exec` pada container yang
tidak pernah dibuat: PR docs-only #147 gagal karena satu langkah I3 ditambahkan
tanpa `if: needs.changes.outputs.odoo_init == 'true'`.

Guard harus berupa **kondisi** (`if:`), bukan sekadar rujukan. Rujukan flag di
`env:` tidak mencegah eksekusi, sehingga langkah `docker exec` tanpa syarat tetap
dijalankan walau `env:` memuat `needs.changes.outputs.odoo_init`. Gate agregasi
yang memang membaca flag di shell dicatat satu per satu di
`SHELL_GATE_EXCEPTIONS` beserta alasannya.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
IMPACT_FLAG = re.compile(r"needs\.changes\.outputs\.\w+")

# Pengecualian eksplisit: gate agregasi yang membaca flag di `env:` lalu memutuskan
# PASS/no-op di shell. Entry wajib cocok dengan langkah nyata yang masih merujuk
# flag tersebut, dan langkahnya tidak boleh menyentuh container.
SHELL_GATE_EXCEPTIONS = {
    (
        "seed-invariants.yml",
        "seed-invariants",
        "Require selected unit gate or record intentional no-op",
    ): (
        "Gate agregasi: memilih PASS/no-op dari needs.changes.outputs.seed di env "
        "dan tidak menjalankan container."
    ),
}


def references_impact(value) -> bool:
    """True bila objek/ekspresi memuat rujukan flag impact plan."""
    return bool(IMPACT_FLAG.search(str(value or "")))


def guarded_by_if(step: dict) -> bool:
    """True bila langkah punya kondisi `if:` yang merujuk flag impact plan."""
    return references_impact(step.get("if"))


def step_gated_jobs(workflow: dict):
    """Job yang menggerbangi langkahnya sendiri dengan flag impact plan.

    Job terkualifikasi bila bergantung pada `changes`, tidak punya guard tingkat
    job, dan setidaknya satu langkahnya memakai guard `if:` impact. Job agregasi
    seperti `pwa-gate` tidak punya langkah ber-guard sehingga sengaja selalu
    dieksekusi.
    """
    for name, job in (workflow.get("jobs") or {}).items():
        needs = job.get("needs") or []
        if isinstance(needs, str):
            needs = [needs]
        if "changes" not in needs or references_impact(job.get("if")):
            continue
        steps = job.get("steps") or []
        if not any(guarded_by_if(step) for step in steps):
            continue
        yield name, job


def unguarded_run_steps(workflow: dict, filename: str = "") -> list[str]:
    """Langkah `run` yang akan mengeksekusi tanpa kondisi impact plan."""
    problems = []
    for name, job in step_gated_jobs(workflow):
        for step in job.get("steps") or []:
            if "run" not in step or guarded_by_if(step):
                continue
            key = (filename, name, step.get("name") or "<unnamed>")
            if key in SHELL_GATE_EXCEPTIONS:
                if not references_impact(step.get("env")):
                    problems.append(f"{key} :: pengecualian gate tanpa rujukan flag di env")
                continue
            problems.append(f"{key} :: langkah run tanpa if: impact plan")
    return problems


def load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def scanned_workflows():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        yield path.name, yaml.safe_load(path.read_text(encoding="utf-8"))


class TestWorkflowImpactGuards(unittest.TestCase):
    def test_every_run_step_in_step_gated_jobs_has_impact_condition(self):
        problems = []
        for filename, workflow in scanned_workflows():
            problems += unguarded_run_steps(workflow, filename)
        self.assertEqual(
            problems,
            [],
            "Langkah `run` tanpa kondisi `if: needs.changes.outputs...` akan "
            "mengeksekusi container saat suite tidak dipilih; rujukan di `env:` "
            "saja tidak mencegah eksekusi.",
        )

    def test_init_test_runtime_steps_are_gated_by_odoo_init(self):
        workflow = load("ci.yml")
        names = {
            step.get("name")
            for step in workflow["jobs"]["init-test"]["steps"]
            if "run" in step and "needs.changes.outputs.odoo_init" in str(step.get("if"))
        }
        self.assertIn("Diagnostik costing I3 read-only dan regresi lingkup perusahaan", names)

    def test_env_reference_alone_does_not_cover_a_runtime_step(self):
        workflow = {
            "jobs": {
                "init-test": {
                    "needs": ["static", "changes"],
                    "steps": [
                        {"name": "Entrypoint runtime not selected",
                         "if": "needs.changes.outputs.odoo_init != 'true'",
                         "run": "echo PASS"},
                        {"name": "Docker exec tanpa syarat",
                         "env": {"SELECTED": "${{ needs.changes.outputs.odoo_init }}"},
                         "run": "docker exec -i odoo true"},
                    ],
                }
            }
        }
        self.assertEqual(
            unguarded_run_steps(workflow, "ci.yml"),
            ["('ci.yml', 'init-test', 'Docker exec tanpa syarat') :: langkah run tanpa if: impact plan"],
        )

    def test_if_condition_covers_the_step(self):
        workflow = {
            "jobs": {
                "init-test": {
                    "needs": ["changes"],
                    "steps": [
                        {"name": "Guarded",
                         "if": "needs.changes.outputs.odoo_init == 'true'",
                         "run": "docker exec -i odoo true"},
                    ],
                }
            }
        }
        self.assertEqual(unguarded_run_steps(workflow, "ci.yml"), [])

    def test_unlisted_shell_gate_is_rejected(self):
        workflow = {
            "jobs": {
                "other-gate": {
                    "needs": ["changes"],
                    "steps": [
                        {"name": "Guarded",
                         "if": "needs.changes.outputs.seed == 'true'",
                         "run": "echo selected"},
                        {"name": "Gate tanpa daftar",
                         "env": {"SELECTED": "${{ needs.changes.outputs.seed }}"},
                         "run": "test \"$SELECTED\" = true"},
                    ],
                }
            }
        }
        self.assertEqual(
            unguarded_run_steps(workflow, "other.yml"),
            ["('other.yml', 'other-gate', 'Gate tanpa daftar') :: langkah run tanpa if: impact plan"],
        )

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
        self.assertEqual(unguarded_run_steps(workflow, "pwa.yml"), [])

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
        self.assertEqual(unguarded_run_steps(workflow, "upgrade-runtime.yml"), [])

    def test_shell_gate_exceptions_match_real_steps(self):
        for (filename, job_name, step_name), reason in SHELL_GATE_EXCEPTIONS.items():
            self.assertTrue(reason.strip(), f"alasan kosong untuk {filename}::{step_name}")
            workflow = load(filename)
            steps = workflow["jobs"][job_name]["steps"]
            matches = [step for step in steps if (step.get("name") or "") == step_name]
            self.assertEqual(len(matches), 1, f"{filename}::{step_name} tidak ditemukan")
            step = matches[0]
            self.assertFalse(guarded_by_if(step), "pengecualian tidak diperlukan bila ada if:")
            self.assertTrue(references_impact(step.get("env")), "gate harus membaca flag di env")
            self.assertNotIn("docker", str(step.get("run")), "gate agregasi tidak boleh menyentuh container")


if __name__ == "__main__":
    unittest.main()
