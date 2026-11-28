"""Loopback-only HTTPS gateway to the disposable Odoo container."""
import argparse
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ssl
from threading import Lock


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.forward({"/api/v1/me/bootstrap", "/api/v1/sync/snapshot"})

    def do_POST(self):
        paths = {"/web/session/authenticate", "/api/v1/sync/commands"}
        if self.server.session_probe:
            paths.add("/web/session/destroy")
        self.forward(paths)

    def forward(self, paths):
        if self.path not in paths or self.headers.get("Host") != "127.0.0.1:18443":
            self.send_error(404)
            return
        if self.headers.get("Transfer-Encoding"):
            self.send_error(400)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 64_000:
                raise ValueError
        except ValueError:
            self.send_error(400)
            return
        request_headers = ("Content-Type", "Cookie", "X-CSRF-Token")
        forwarded = {key: self.headers[key] for key in request_headers if key in self.headers}
        forwarded.update({
            "Host": "127.0.0.1:18443", "X-Forwarded-Host": "127.0.0.1:18443",
            "X-Forwarded-Proto": "https", "X-Forwarded-For": "127.0.0.1",
        })
        upstream = HTTPConnection("127.0.0.1", self.server.odoo_port, timeout=20)
        try:
            upstream.request(self.command, self.path, self.rfile.read(length), forwarded)
            response = upstream.getresponse()
            content = response.read()
        except (OSError, TimeoutError):
            self.send_error(502)
            return
        finally:
            upstream.close()
        self.send_response(response.status)
        for key, value in response.getheaders():
            if key.lower() in {"set-cookie", "content-type", "cache-control", "vary"}:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if self.path == "/api/v1/sync/commands" and response.status == 200:
            with self.server.fault_lock:
                if self.server.drop_first_command_receipt:
                    self.server.drop_first_command_receipt = False
                    # The upstream transaction has returned its body. Close downstream with the
                    # advertised Content-Length still pending, so the caller loses the receipt.
                    self.close_connection = True
                    print("command_receipt_truncated=1", flush=True)
                    return
        self.wfile.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("odoo_port", type=int)
    parser.add_argument("certificate")
    parser.add_argument("key")
    parser.add_argument("--drop-first-command-receipt", action="store_true")
    parser.add_argument("--session-probe", action="store_true")
    args = parser.parse_args()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    tls.load_cert_chain(args.certificate, args.key)
    with ThreadingHTTPServer(("127.0.0.1", 18443), Handler) as server:
        server.odoo_port = args.odoo_port
        server.session_probe = args.session_probe
        server.drop_first_command_receipt = args.drop_first_command_receipt
        server.fault_lock = Lock()
        server.socket = tls.wrap_socket(server.socket, server_side=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
