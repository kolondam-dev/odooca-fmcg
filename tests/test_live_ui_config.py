"""Safety contract for the committed live-UI environment template."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "pwa" / ".env.live-ui.example"
PROTECTED_KEYS = {
    "LIVE_UI_ODOO_URL",
    "LIVE_UI_PWA_URL",
    "ODOO_DEMO_LOGIN",
    "ODOO_DEMO_PASSWORD",
}


def assignments(text: str) -> dict[str, str]:
    """Read active KEY=VALUE assignments without interpreting dotenv values."""
    result = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


class TestLiveUiEnvironmentTemplate(unittest.TestCase):
    def test_remote_target_and_credentials_are_present_but_empty(self):
        configured = assignments(TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(PROTECTED_KEYS - configured.keys(), set(), "protected key missing")
        populated = {key: configured[key] for key in PROTECTED_KEYS if configured[key]}
        self.assertEqual(
            populated,
            {},
            "Remote URLs belong in demo-ui Variables and credentials in demo-ui Secrets; "
            "the committed template must keep these assignments empty.",
        )


if __name__ == "__main__":
    unittest.main()
