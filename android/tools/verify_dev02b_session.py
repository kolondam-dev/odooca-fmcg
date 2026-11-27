"""Exercise B09's provisional session endpoints from a host HTTPS client."""
import argparse
from copy import copy
from http.cookiejar import CookieJar
import json
import os
import ssl
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, HTTPSHandler, ProxyHandler, Request, build_opener

BASE = "https://127.0.0.1:18443"
BOOTSTRAP = "/api/v1/me/bootstrap"
SNAPSHOT = "/api/v1/sync/snapshot"
AUTH = "/web/session/authenticate"
DESTROY = "/web/session/destroy"


class Client:
    def __init__(self, tls):
        self.cookies = CookieJar()
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(self.cookies), HTTPSHandler(context=tls))

    def request(self, path, expected=200, params=None):
        options = {}
        if params is not None:
            options = {
                "data": json.dumps({"jsonrpc": "2.0", "method": "call", "id": 1, "params": params}).encode(),
                "headers": {"Content-Type": "application/json"},
            }
        try:
            response = self.opener.open(Request(BASE + path, **options), timeout=25)
        except HTTPError as error:
            response = error
        with response:
            if response.code != expected:
                raise ValueError(f"{path}: expected HTTP {expected}, received {response.code}")
            return json.load(response)


def check(tls, database, passwords):
    anonymous = Client(tls)
    for path in (BOOTSTRAP, SNAPSHOT):
        anonymous.request(path, expected=401)
    print("anonymous bootstrap=401 snapshot=401")

    rejected = anonymous.request(AUTH, params={
        "db": database, "login": "staging.capture.1", "password": "dev02b-invalid-probe-password",
    })
    if not rejected.get("error") and rejected.get("result", {}).get("uid"):
        raise ValueError("invalid authentication unexpectedly succeeded")
    anonymous.request(BOOTSTRAP, expected=401)
    print("invalid_login rejected; bootstrap=401")

    def authenticated(index):
        client = Client(tls)
        result = client.request(AUTH, params={
            "db": database, "login": f"staging.capture.{index}", "password": passwords[index - 1],
        })
        identity = client.request(BOOTSTRAP)
        snapshot = client.request(SNAPSHOT)
        scope = snapshot["scope"]
        if (
            str(result["result"]["uid"]) != identity["id"]
            or (scope["user_id"], scope["company_id"]) != (identity["id"], identity["companyId"])
            or not identity["csrfToken"]
            or len(snapshot["outlets"]) != 1
        ):
            raise ValueError("identity or assignment mismatch")
        return client, identity["id"], snapshot["outlets"][0]["id"]

    first, owner_a, outlet_a = authenticated(1)
    other, owner_b, outlet_b = authenticated(2)
    if owner_a == owner_b or outlet_a == outlet_b:
        raise ValueError("fixture did not isolate account assignments")
    print("login bootstrap=200 snapshot=200 accounts=2 assignments_isolated=true")

    stale = Client(tls)
    for cookie in first.cookies:
        stale.cookies.set_cookie(copy(cookie))
    stale.request(BOOTSTRAP)
    result = first.request(DESTROY, params={})
    if "error" in result:
        raise ValueError("server did not destroy the session")
    for path in (BOOTSTRAP, SNAPSHOT):
        stale.request(path, expected=401)
    if other.request(BOOTSTRAP)["id"] != owner_b:
        raise ValueError("revocation affected the other account")
    other.request(SNAPSHOT)
    print("server_revoked stale_cookie_bootstrap=401 stale_cookie_snapshot=401 other_account=200")

    _, restored, restored_outlet = authenticated(1)
    if (owner_a, outlet_a) != (restored, restored_outlet):
        raise ValueError("reauthentication did not restore the original scope")
    print("reauthentication bootstrap=200 snapshot=200 original_scope=true")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture_ca")
    args = parser.parse_args()
    try:
        database = os.environ["FMCG_STAGING_DATABASE"]
        if not database.startswith("fmcg_staging_") or os.environ.get("FMCG_STAGING_DISPOSABLE") != "YES":
            raise ValueError("disposable fixture required")
        passwords = [os.environ[f"FMCG_STAGING_PASSWORD_{i}"] for i in (1, 2)]
        check(ssl.create_default_context(cafile=args.fixture_ca), database, passwords)
    except (OSError, KeyError, TypeError, ValueError):
        parser.exit(1, "DEV-02B provisional HTTPS probe failed\n")


if __name__ == "__main__":
    main()
