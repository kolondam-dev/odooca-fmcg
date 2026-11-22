from __future__ import annotations

import re
import unittest
import zipfile
from pathlib import Path

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
        provision = next(
            step["run"]
            for step in jobs["emulator-smoke"]["steps"]
            if step.get("name") == "Install Android SDK and system image"
        )
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


if __name__ == "__main__":
    unittest.main()
