"""Regression guard: every JavaScript block embedded in smoke_ui.py must parse.

Python cannot catch syntax errors inside the browser-side strings, so a broken
audit function used to survive static checks and only fail minutes into the
Odoo browser job. This test extracts the exact production strings and runs
``node --check`` before the smoke test is reached.
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from js_blocks import js_blocks


class TestSmokeJavascriptParses(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node is required to parse embedded JavaScript")
    def test_every_embedded_javascript_block_parses(self):
        blocks = js_blocks()
        self.assertIn("FOOTER_SCROLL_AUDIT", blocks)
        self.assertIn("TITLE_STATE", blocks)
        for name, source in blocks.items():
            with self.subTest(block=name), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"{name}.js"
                path.write_text(f"const __block = {source};\n", encoding="utf-8")
                completed = subprocess.run(
                    ["node", "--check", str(path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    f"{name} failed node --check:\n{completed.stderr}",
                )

    def test_footer_audit_derives_bottom_sticky_interval(self):
        source = js_blocks()["FOOTER_SCROLL_AUDIT"]
        # Guard the contract that later review rounds depended on: normal-flow
        # measurement with sticky disabled, containing-block bounds, and the
        # bottom-inset release point.
        for needle in (
            "setProperty('position', 'static', 'important')",
            "containingBlockTopAtZero",
            "containingBlockBottomAtZero",
            "bottomInset",
            "releaseAt",
            "pinStart",
            "pinEnd",
        ):
            self.assertIn(needle, source)


if __name__ == "__main__":
    unittest.main()
