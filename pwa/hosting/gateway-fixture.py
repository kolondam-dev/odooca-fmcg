"""Disposable HTTP transport fixture, NOT an Odoo authentication service.

Mirror Odoo19's conditional ProxyFix gate (proxy_mode enabled and forwarded host
present), using Werkzeug itself. This proves gateway origin reconstruction, not
Odoo business ACL, login, or deployment acceptance.
"""

import json
import os
from wsgiref.simple_server import make_server

from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.wrappers import Request, Response


@Request.application
def serve(request):
    origin = request.host_url.rstrip("/")
    if request.path == "/web/login":
        response = Response(status=302, headers={"Location": "/field/", "X-Fixture-Origin": origin})
        response.set_cookie("session_id", "gateway-test", httponly=True, samesite="Lax", secure=request.is_secure)
        return response
    if request.path not in ("/api/v1/me/bootstrap", "/api/v1/sync/snapshot", "/web/proxy-probe"):
        return Response(status=404)
    if request.cookies.get("session_id") != "gateway-test":
        return Response('{"error":"not_authenticated"}', status=401, content_type="application/json")
    if request.headers.get("Origin") and request.headers["Origin"] != origin:
        return Response('{"error":"invalid_origin"}', status=400, content_type="application/json")
    return Response(json.dumps({
        "fixture": True,
        "path": request.path,
        "raw": request.environ["fixture.raw"],
        "effective": {"origin": origin, "host": request.host, "scheme": request.scheme,
                      "remote_addr": request.remote_addr},
    }), content_type="application/json")


proxied = ProxyFix(serve, x_for=1, x_proto=1, x_host=1)


def application(environ, start_response):
    environ["fixture.raw"] = {header: environ.get(key) for header, key in {
        "host": "HTTP_HOST", "forwarded_host": "HTTP_X_FORWARDED_HOST",
        "forwarded_proto": "HTTP_X_FORWARDED_PROTO", "forwarded_for": "HTTP_X_FORWARDED_FOR",
        "forwarded_port": "HTTP_X_FORWARDED_PORT", "forwarded_prefix": "HTTP_X_FORWARDED_PREFIX",
        "forwarded": "HTTP_FORWARDED",
    }.items()}
    # Same conditional and trust counts as Odoo19 http.py with proxy_mode=True.
    handler = proxied if environ.get("HTTP_X_FORWARDED_HOST") else serve

    def no_cache(status, headers, exc_info=None):
        headers.append(("Cache-Control", "no-store, private"))
        return start_response(status, headers, exc_info)

    return handler(environ, no_cache)


if __name__ == "__main__":
    make_server("0.0.0.0", int(os.environ.get("PORT", "8069")), application).serve_forever()
