"""Probe the fixture's Odoo19 conditional with real Werkzeug before gateway tests."""

import unittest

from werkzeug.test import Client
from werkzeug.wrappers import Response

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location("gateway_fixture", Path(__file__).with_name("gateway-fixture.py"))
fixture = module_from_spec(spec)
spec.loader.exec_module(fixture)
application = fixture.application


class TestOdooProxyGate(unittest.TestCase):
    def probe(self, headers):
        client = Client(application, Response)
        client.set_cookie("session_id", "gateway-test", domain="staging.test")
        return client.get("/web/proxy-probe", base_url="http://staging.test:8443", headers=headers).json

    def test_missing_forwarded_host_does_not_enable_proxy_fix(self):
        payload = self.probe({"X-Forwarded-Proto": "https"})
        self.assertEqual(payload["effective"]["origin"], "http://staging.test:8443")

    def test_untrusted_forwarded_host_would_take_over_authority(self):
        payload = self.probe({"X-Forwarded-Proto": "https", "X-Forwarded-Host": "attacker.invalid:9000"})
        self.assertEqual(payload["effective"]["origin"], "https://attacker.invalid:9000")

    def test_gateway_headers_reconstruct_https_and_nondefault_port(self):
        payload = self.probe({"X-Forwarded-Proto": "https", "X-Forwarded-Host": "staging.test:8443"})
        self.assertEqual(payload["effective"]["origin"], "https://staging.test:8443")


if __name__ == "__main__":
    unittest.main()
