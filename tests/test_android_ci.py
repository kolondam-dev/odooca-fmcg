from __future__ import annotations

import unittest
import zipfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android"
WORKFLOW = ROOT / ".github" / "workflows" / "android.yml"


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
