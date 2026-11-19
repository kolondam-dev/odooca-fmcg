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
        self.assertIn("gradle-8.9-bin.zip", properties)
        self.assertIn(
            "distributionSha256Sum=d725d707bfabd4dfdc958c624003b3c80accc03f7037b5122c4b1d0ef15cecab",
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
        self.assertIn("android/tools/validate_contract.py", source)
        self.assertIn("odooca-field-debug-${{ github.sha }}", source)
        self.assertIn("app-debug.apk.sha256", source)


if __name__ == "__main__":
    unittest.main()
