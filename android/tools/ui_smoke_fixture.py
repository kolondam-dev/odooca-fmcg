"""Synthetic HTTP contract for the opt-in, loopback-only UI test."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def reply(self, status, payload, cookie=None):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/web/session/authenticate":
            self.reply(404, {})
            return
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 4096:
            self.reply(400, {})
            return
        credentials = json.loads(self.rfile.read(size))["params"]
        if (credentials.get("login"), credentials.get("password")) != ("ui-test", "ui-test-pass"):
            self.reply(200, {"result": {"uid": False}})
            return
        self.reply(200, {"result": {"uid": 1}}, "session_id=ui-session; Path=/; HttpOnly")

    def do_GET(self):
        if self.path == "/health":
            self.reply(200, {"ready": True})
            return
        if self.headers.get("Cookie") != "session_id=ui-session":
            self.reply(401, {})
            return
        if self.path == "/api/v1/me/bootstrap":
            self.reply(200, {
                "id": "1", "companyId": "1", "name": "Pengguna Uji",
                "businessDate": "2026-11-19", "csrfToken": "ui-csrf",
            })
        elif self.path == "/api/v1/sync/snapshot":
            self.reply(200, {
                "version": "ui-test", "updatedAt": "2026-11-19T00:00:00Z", "outlets": [],
                "scope": {
                    "user_id": "1", "company_id": "1",
                    "warehouse_id": "1", "business_date": "2026-11-19",
                },
            })
        else:
            self.reply(404, {})


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", 18080), FixtureHandler) as server:
        server.serve_forever()
