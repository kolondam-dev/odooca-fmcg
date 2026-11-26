from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
import runpy
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml


ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android"
WORKFLOW = ROOT / ".github" / "workflows" / "android.yml"
DEPENDABOT = ROOT / ".github" / "dependabot.yml"


class TestAndroidBootstrapContract(unittest.TestCase):
    def test_gradle_wrapper_is_pinned_and_complete(self):
        properties = (ANDROID / "gradle" / "wrapper" / "gradle-wrapper.properties").read_text(
            encoding="utf-8"
        )
        self.assertIn("gradle-9.9.1-bin.zip", properties)
        self.assertIn(
            "distributionSha256Sum=d8a18a7a841dd5df825d35a685fad6f2d7f12ac0c280e57b67c27b4a520ba228",
            properties,
        )
        self.assertTrue((ANDROID / "gradlew").is_file())
        self.assertTrue((ANDROID / "gradlew.bat").is_file())
        with zipfile.ZipFile(ANDROID / "gradle" / "wrapper" / "gradle-wrapper.jar") as archive:
            self.assertIn("org/gradle/wrapper/GradleWrapperMain.class", archive.namelist())

    def test_workflow_installs_the_platform_matching_compile_sdk(self):
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        platforms = {}
        for job in ("data-tests", "build", "emulator-smoke"):
            steps = "\n".join(step.get("run", "") for step in jobs[job]["steps"])
            if job == "emulator-smoke":
                self.assertIn("bash android/tools/install_emulator_sdk.sh", steps)
                steps = (ANDROID / "tools" / "install_emulator_sdk.sh").read_text(encoding="utf-8")
            installed = re.findall(r"platforms;android-(\d+(?:\.\d+)?)", steps)
            self.assertEqual(1, len(installed), f"{job}: {installed}")
            self.assertIn("build-tools;36.0.0", steps, job)
            platforms[job] = installed[0]

        for module in ("app", "core/data", "core/designsystem"):
            source = (ANDROID / module / "build.gradle.kts").read_text(encoding="utf-8")
            match = re.search(r"compileSdk\s*=\s*(\d+)", source)
            self.assertIsNotNone(match, f"compileSdk missing in {module}")
            major = match.group(1)
            # From API 37 AGP resolves the major to the .0 SDK package.
            expected = f"{major}.0" if int(major) >= 37 else major
            for job, installed in platforms.items():
                self.assertEqual(expected, installed, f"{module}: wrong SDK in {job}")

        smoke = (ANDROID / "tools" / "emulator_smoke.sh").read_text(encoding="utf-8")
        self.assertIn(f"verify_revision platforms/android-{platforms['emulator-smoke']} 2", smoke)
        self.assertIn("verify_revision build-tools/36.0.0 36.0.0", smoke)
        self.assertIn("android/gradle/wrapper/gradle-wrapper.properties", smoke)

    def test_gradle_retries_are_widened_for_transient_ci_failures(self):
        properties = {}
        for line in (ANDROID / "gradle.properties").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            properties[key.strip()] = value.strip()

        # Gradle defaults are 3 attempts with a 125 ms initial backoff; the KSP
        # plugin resolution flake seen in PR #162/#173 needs a wider window.
        for key in (
            "systemProp.org.gradle.internal.repository.max.retries",
            "systemProp.org.gradle.internal.repository.initial.backoff",
        ):
            self.assertIn(key, properties)
            self.assertGreater(
                int(properties[key]), 0, f"{key} must be a positive integer"
            )

    def test_dependabot_never_opens_locked_toolchain_updates(self):
        config = yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))
        gradle = next(
            update for update in config["updates"] if update["package-ecosystem"] == "gradle"
        )
        ignored = {
            rule["dependency-name"]: set(rule.get("update-types") or ())
            for rule in gradle.get("ignore", [])
        }

        # AGP, Kotlin and KSP only work as a matched set with a supported Gradle
        # wrapper, so no Dependabot update of any kind may touch them. A Kotlin
        # 2.0.21 -> 2.4.21 bump is semver-minor yet still broke compatibility
        # (PR #164), hence "all versions" rather than only majors.
        for name in (
            "com.android.application",
            "com.android.library",
            "com.android.tools.build:gradle",
            "org.jetbrains.kotlin:*",
            "org.jetbrains.kotlin.*",
            "com.google.devtools.ksp",
        ):
            self.assertIn(name, ignored, f"{name} must not be auto-bumped")
            self.assertEqual(set(), ignored[name], f"{name} must ignore every version")

        # Kotlin coroutines/serialization (org.jetbrains.kotlinx) are ordinary
        # dependencies and must keep flowing; the ignore patterns must not
        # swallow them.
        self.assertTrue(self._wildcard_match("org.jetbrains.kotlin:*", "org.jetbrains.kotlin:kotlin-test"))
        self.assertTrue(self._wildcard_match("org.jetbrains.kotlin.*", "org.jetbrains.kotlin.android"))
        self.assertFalse(
            self._wildcard_match(
                "org.jetbrains.kotlin:*", "org.jetbrains.kotlinx:kotlinx-coroutines-android"
            )
        )
        self.assertFalse(
            self._wildcard_match("org.jetbrains.kotlin.*", "org.jetbrains.kotlinx:kotlinx-serialization-json")
        )

        # The wrapper is pinned to one version plus its official checksum by
        # test_gradle_wrapper_is_pinned_and_complete, so no bump can pass the
        # gate; every wrapper update has to be ignored.
        self.assertIn("gradle-wrapper", ignored)
        self.assertEqual(set(), ignored["gradle-wrapper"])

        # The Compose BOM uses CalVer: a year change is a semver-major update,
        # so ignoring androidx majors would freeze the BOM.
        self.assertEqual([], [name for name in ignored if name.startswith("androidx")])
        self.assertEqual({"kotlin-compose", "android-jetpack"}, set(gradle["groups"]))
        self.assertLessEqual(gradle["open-pull-requests-limit"], 3)

    @staticmethod
    def _wildcard_match(pattern, candidate):
        # Mirrors Dependabot's `*` wildcard matching for dependency names.
        regex = ".*".join(re.escape(part) for part in pattern.split("*"))
        return re.fullmatch(regex, candidate, flags=re.IGNORECASE) is not None

    def test_workflow_uses_wrapper_and_publishes_stable_gate(self):
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.assertIn("android-gate", workflow["jobs"])
        self.assertEqual(workflow["jobs"]["android-gate"]["if"], "always()")

        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("./gradlew --no-daemon :core:domain:test", source)
        self.assertIn(":app:lintDebug :app:assembleDebug", source)
        self.assertNotIn("run: gradle ", source)
        self.assertIn("android-actions/setup-android@v4", source)
        self.assertNotIn("android-actions/setup-android@v3", source)
        self.assertIn("android/tools/validate_contract.py", source)
        self.assertIn("odooca-field-debug-${{ github.sha }}", source)
        self.assertIn("app-debug.apk.sha256", source)

    def test_emulator_matrix_is_opt_in_and_outside_required_gate(self):
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        events = workflow[True]  # YAML 1.1 interprets the Actions key "on" as true.
        inputs = events["workflow_dispatch"]["inputs"]
        self.assertIs(inputs["emulator_smoke"]["default"], False)
        self.assertIs(inputs["emulator_ui"]["default"], False)
        self.assertNotIn("emulator_smoke", events["workflow_call"]["inputs"])
        jobs = workflow["jobs"]
        self.assertEqual(
            jobs["emulator-smoke"]["if"],
            "github.event_name == 'workflow_dispatch' && inputs.emulator_smoke",
        )
        self.assertEqual(jobs["emulator-smoke"]["strategy"]["matrix"]["api"], [24, 35])
        self.assertEqual(
            jobs["android-gate"]["needs"], ["changes", "guards", "domain-tests", "data-tests", "build"]
        )

    def test_emulator_provisioning_uses_versioned_sdk_archives(self):
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        self.assertTrue(any("bash android/tools/install_emulator_sdk.sh" in step.get("run", "")
                            for step in jobs["emulator-smoke"]["steps"]))
        provision = (ANDROID / "tools" / "install_emulator_sdk.sh").read_text(encoding="utf-8")
        commands = provision.replace("\\\n", " ").splitlines()
        install = next(line for line in commands if "--channel=0" in line)
        self.assertNotIn('"platform-tools"', install)
        self.assertNotIn('"emulator"', install)
        self.assertNotIn("system-images;", install)
        self.assertIn("install_archive platform-tools_r37.0.3-linux.zip", provision)
        self.assertIn("install_archive emulator-linux_x64-16970787.zip", provision)
        self.assertIn('<localPackage path="emulator"', provision)
        self.assertIn("<revision><major>37</major><minor>3</minor><micro>10</micro></revision>", provision)
        self.assertIn("24) install_archive sys-img/google_apis/x86_64-24_r27.zip", provision)
        self.assertIn("35) install_archive sys-img/google_apis/x86_64-35_r09.zip", provision)
        self.assertIn("sha1sum --check --status", provision)

        smoke = (ANDROID / "tools" / "emulator_smoke.sh").read_text(encoding="utf-8")
        self.assertIn("verify_revision platform-tools 37.0.3", smoke)
        self.assertIn("verify_revision emulator 37.3.10", smoke)

    def test_ui_smoke_removes_smoke_apk_before_gradle_installs_the_fixture(self):
        smoke = (ANDROID / "tools" / "emulator_smoke.sh").read_text(encoding="utf-8")
        steps = (
            ":app:assembleDebug",
            "-Podooca.baseUrl=https://ci.invalid -Podooca.uiFixture=false",
            "record login_ui PASS",
            'timeout 30 "$adb" uninstall "$package"',
            'timeout 10 "$adb" shell pm list packages "$package"',
            "record fixture_reset PASS",
            ":app:connectedDebugAndroidTest -Podooca.uiFixture=true",
            "python3 android/tools/ui_smoke_report.py",
            'test "$test_result" -eq 0',
            "record instrumentation PASS",
        )
        offsets = [smoke.index(step) for step in steps]
        self.assertEqual(offsets, sorted(offsets))
        self.assertNotIn("shell pm clear", smoke)
        self.assertEqual(1, smoke.count("-Podooca.uiFixture=true"))

    def test_contract_validator_has_four_negative_schema_controls(self):
        source = (ANDROID / "tools" / "validate_contract.py").read_text(encoding="utf-8")
        self.assertEqual(source.count('check("[negatif]'), 4)

    def test_workflow_runs_room_session_data_layer_tests(self):
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.assertIn("data-tests", workflow["jobs"])
        self.assertEqual(workflow["jobs"]["data-tests"]["needs"], "changes")

        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("./gradlew --no-daemon :core:data:testDebugUnitTest", source)
        self.assertIn("android-data-reports-${{ github.sha }}", source)

        gate = workflow["jobs"]["android-gate"]
        self.assertIn("data-tests", gate["needs"])
        self.assertIn("DATA_RESULT", gate["steps"][0]["env"])
        self.assertIn('test "$DATA_RESULT" = success', gate["steps"][0]["run"])
        self.assertIn('test "$DATA_RESULT" = skipped', gate["steps"][0]["run"])

    def test_data_layer_test_covers_session_switch_and_401_recovery(self):
        source = (
            ANDROID
            / "core"
            / "data"
            / "src"
            / "test"
            / "kotlin"
            / "com"
            / "kolondam"
            / "odooca"
            / "field"
            / "data"
            / "repo"
            / "OutboxSessionIntegrationTest.kt"
        ).read_text(encoding="utf-8")
        self.assertIn("queuedOwnerCannotUseAnotherOwnersSession", source)
        self.assertIn("first401StopsBatchAndOnlySameOwnerReauthenticationResumesIt", source)
        self.assertIn("accountSwitchBetweenTwoSendsStopsBeforeSecondRequest", source)
        self.assertIn("resumeAfterAuthentication", source)
        self.assertIn("RobolectricTestRunner", source)
        self.assertIn("inMemoryDatabaseBuilder", source)
        # Server HTTP harus memakai kelas yang ada di android.jar; com.sun.* tidak tersedia.
        self.assertIn("ServerSocket", source)
        self.assertNotIn("com.sun", source)


class TestB09Evidence(unittest.TestCase):
    def setUp(self):
        tools = ANDROID / "tools"
        instrumentation = runpy.run_path(str(tools / "dev02a_instrumentation.py"))
        self.extract = instrumentation["extract"]
        self.verify_junit = instrumentation["verify_junit"]
        self.verify = runpy.run_path(str(tools / "verify_dev02a_apk.py"))["verify"]
        self.uuid = "a22a5b03-f435-4b9d-8b3a-d7cc94547d90"
        self.scope = {"user_id": "4", "company_id": "2"}
        command = {
            "type": "sales.order.submit", "client_uuid": self.uuid,
            "payload": {
                "outlet_id": "9", "snapshot_version": "odoo-read-v1:" + "a" * 64,
                "lines": [{"product_id": "7", "qty": "1", "uom": "carton"}],
            },
        }
        receipt = {"client_uuid": self.uuid, "status": "accepted", "reference": "S00001"}
        self.first = {"phase": "first", "request": command, "receipt": receipt,
                      "business_date": "2026-11-26", **self.scope}
        self.replay = {**deepcopy(self.first), "phase": "replay"}
        self.before = {
            "fixture": "id_mobile_api_staging", "uuid": self.uuid, "outlet_id": "9", "product_id": "7",
            "company_command_count": 0, "ledger": [], "orders": [], "approvals": [], **self.scope,
        }
        serialized = json.dumps(command, sort_keys=True, separators=(",", ":"))
        row = {**self.scope, **receipt, "type": command["type"], "sale_order_ids": [99],
               "fingerprint": hashlib.sha256(serialized.encode()).hexdigest()}
        order = {**self.scope, "id": 99, "outlet_id": "9", "reference": "S00001", "state": "draft",
                 "picking_ids": [], "invoice_ids": [], "lines": [{"product_id": "7", "qty": 24}]}
        self.after = {**self.before, "company_command_count": 1, "ledger": [row], "orders": [order]}

    def test_b09_is_manual_and_outside_required_gates(self):
        workflow = yaml.safe_load(WORKFLOW.read_text())
        inputs = workflow[True]["workflow_dispatch"]["inputs"]
        self.assertIs(inputs["b09"]["default"], False)
        self.assertNotIn("b09", workflow[True]["workflow_call"]["inputs"])
        self.assertNotIn("apk-odoo", workflow["jobs"]["android-gate"]["needs"])
        job = workflow["jobs"]["apk-odoo"]
        self.assertEqual(job["if"], "github.event_name == 'workflow_dispatch' && inputs.b09")
        self.assertNotIn("continue-on-error", job)
        self.assertEqual(job["steps"][-1]["if"], "always()")
        paths = job["steps"][-1]["with"]["path"]
        self.assertNotIn("*", paths)
        self.assertNotIn(".log", paths)
        self.assertNotIn(".pem", paths)

    def test_instrumentation_rejects_missing_skipped_failed_and_stale(self):
        case = (
            "INSTRUMENTATION_STATUS: class=com.kolondam.odooca.field.DisposableOdooReceiptTest\n"
            "INSTRUMENTATION_STATUS: test=submitOrReplay\n"
        )
        evidence = "INSTRUMENTATION_STATUS: dev02a_evidence=" + json.dumps(self.first) + "\n"
        evidence += "INSTRUMENTATION_STATUS_CODE: 0\n"
        start = case + "INSTRUMENTATION_STATUS_CODE: 1\n"
        finished = case + "INSTRUMENTATION_STATUS_CODE: 0\n"
        final = "INSTRUMENTATION_CODE: -1\n"
        raw = start + evidence + finished + final
        self.assertEqual(self.first, self.extract(raw, self.uuid, "first"))
        for label, candidate, uuid, phase in [
            ("missing", start + finished + final, self.uuid, "first"),
            ("skipped", raw.replace(finished, case + "INSTRUMENTATION_STATUS_CODE: -4\n"), self.uuid, "first"),
            ("failed", raw.replace(finished, case + "INSTRUMENTATION_STATUS_CODE: -2\n"), self.uuid, "first"),
            ("duplicate", start + evidence + evidence + finished + final, self.uuid, "first"),
            ("stale", raw, "e7b4fb53-4b4d-49ef-a74a-08cb92178339", "first"),
            ("wrong_phase", raw, self.uuid, "replay"),
            ("aborted", raw + "INSTRUMENTATION_FAILED: process crashed\n", self.uuid, "first"),
        ]:
            with self.subTest(label=label), self.assertRaises(ValueError):
                self.extract(candidate, uuid, phase)

    def test_junit_requires_one_fresh_success_in_each_phase(self):
        test = '<testcase classname="com.kolondam.odooca.field.DisposableOdooReceiptTest" name="submitOrReplay" />'
        with TemporaryDirectory() as work:
            report = Path(work) / "report.xml"
            with self.assertRaises(FileNotFoundError):
                self.verify_junit(report, self.uuid, "first")
            for phase in ("first", "replay"):
                valid = (
                    f'<testsuite uuid="{self.uuid}" phase="{phase}" tests="1" failures="0" skipped="0">'
                    f"{test}</testsuite>"
                )
                report.write_text(valid)
                self.assertIn('name="submitOrReplay"', self.verify_junit(report, self.uuid, phase))
                for label, broken in (
                    ("no_case", valid.replace(test, "")),
                    ("skipped", valid.replace('skipped="0"', 'skipped="1"')),
                    ("failed", valid.replace(" />", "><failure/></testcase>")),
                    ("duplicate", valid.replace(test, test * 2)),
                    ("stale", valid.replace(self.uuid, "e7b4fb53-4b4d-49ef-a74a-08cb92178339")),
                    ("wrong_phase", valid.replace(phase, "replay" if phase == "first" else "first")),
                    ("wrong_test", valid.replace("submitOrReplay", "otherTest")),
                    ("raw_secret", valid.replace(" />", ' token="fake" />')),
                ):
                    with self.subTest(phase=phase, label=label), self.assertRaises(ValueError):
                        report.write_text(broken)
                        self.verify_junit(report, self.uuid, phase)

    def test_verifier_rejects_each_reviewed_mutation(self):
        def set_ledger(after, key, value):
            after["ledger"][0][key] = value

        def duplicate(after, key):
            after[key].append({**after[key][0], "id": 100})

        self.assertEqual(
            self.verify(self.first, self.replay, self.before, self.after, deepcopy(self.after))["result"], "passed",
        )
        for mutation, change, reason in (
            ("fingerprint", lambda a: set_ledger(a, "fingerprint", "0" * 64), "exact APK command"),
            ("duplicate_ledger", lambda a: duplicate(a, "ledger"), "exactly one"),
            ("duplicate_order", lambda a: duplicate(a, "orders"), "exactly one"),
            ("reference", lambda a: set_ledger(a, "reference", "S09999"), "receipt does not match ledger"),
            ("scope", lambda a: set_ledger(a, "user_id", "44"), "actor scope mismatch"),
        ):
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, reason):
                after = deepcopy(self.after)
                change(after)
                self.verify(self.first, self.replay, self.before, after, deepcopy(after))

        replay = deepcopy(self.replay)
        replay["request"]["payload"]["lines"][0]["qty"] = "2"
        with self.assertRaisesRegex(ValueError, "replay changed the wire payload"):
            self.verify(self.first, replay, self.before, self.after, deepcopy(self.after))

        after_replay = deepcopy(self.after)
        after_replay["orders"][0]["picking_ids"] = [1]
        with self.assertRaisesRegex(ValueError, "replay changed the Odoo checkpoint"):
            self.verify(self.first, self.replay, self.before, self.after, after_replay)


if __name__ == "__main__":
    unittest.main()
