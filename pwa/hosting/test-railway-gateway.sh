#!/usr/bin/env bash
# Railway-style HTTP hop behind an HTTPS edge. Transport fixture, not Odoo login.
set -euo pipefail
network="pwa-railway-gateway-$$"
fixture_dir=$(mktemp -d)
cleanup() {
  docker rm -f "${network}-proxy" "${network}-odoo" "${network}-pwa" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
  rm -rf "$fixture_dir"
}
trap cleanup EXIT
docker build -f pwa/hosting/Dockerfile.railway-gateway -t "${network}-gateway" pwa
docker build -f pwa/hosting/gateway-fixture.Dockerfile -t "${network}-fixture" pwa/hosting
docker network create "$network" >/dev/null
docker run -d --name "${network}-odoo" --network "$network" --network-alias odoo "${network}-fixture" >/dev/null
docker run -d --name "${network}-pwa" --network "$network" --network-alias field-pwa fmcg-pwa-staging >/dev/null
docker run -d --name "${network}-proxy" --network "$network" -p 127.0.0.1::8080 \
  -e STAGING_HOST=staging.test -e ODOO_UPSTREAM=odoo:8069 -e FIELD_UPSTREAM=field-pwa:8080 "${network}-gateway" >/dev/null
port=$(docker port "${network}-proxy" 8080/tcp | sed 's/.*://')
base="http://127.0.0.1:$port"
curl --retry 10 --retry-all-errors --retry-delay 1 --max-time 5 -fsS "$base/healthz" >/dev/null
curl -fsS -H 'Host: staging.test' "$base/field/" -o "$fixture_dir/index"
test "$(curl -s -H 'Host: attacker.invalid' -o /dev/null -w '%{http_code}' "$base/field/" || true)" = 000
curl -fsS -D "$fixture_dir/headers" -H 'Host: staging.test' -H 'X-Forwarded-Host: evil.invalid' \
  -H 'X-Forwarded-Proto: http' "$base/web/login" -o /dev/null
grep -qi 'X-Fixture-Origin: https://staging.test' "$fixture_dir/headers"
grep -qi 'Set-Cookie: .*Secure' "$fixture_dir/headers"
for route in me/bootstrap sync/snapshot outlets/1/image; do
  curl -fsS -H 'Host: staging.test' -H 'Origin: https://staging.test' -H 'Cookie: session_id=gateway-test' \
    -H 'X-Forwarded-Host: evil.invalid' -H 'X-Forwarded-Proto: http' \
    "$base/api/v1/$route" -o "$fixture_dir/payload"
  python3 - "$fixture_dir/payload" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1]))
assert payload['effective']['origin'] == 'https://staging.test', payload
assert payload['raw']['host'] == payload['raw']['forwarded_host'] == 'staging.test', payload
PY
done
test "$(curl -s -H 'Host: staging.test' -H 'Origin: https://evil.invalid' -H 'Cookie: session_id=gateway-test' \
  -o /dev/null -w '%{http_code}' "$base/api/v1/me/bootstrap")" = 400
test "$(curl -s -X POST -H 'Host: staging.test' -H 'Origin: https://staging.test' -H 'Cookie: session_id=gateway-test' \
  -F metadata='{}' -o /dev/null -w '%{http_code}' "$base/api/v1/evidence")" = 200
test "$(curl -s -X POST -H 'Host: staging.test' -o /dev/null -w '%{http_code}' "$base/api/v1/sync/commands")" = 404
if docker run --rm -e 'STAGING_HOST=staging.test;invalid' -e ODOO_UPSTREAM=odoo:8069 \
  -e FIELD_UPSTREAM=field-pwa:8080 "${network}-gateway"; then
  echo 'Invalid gateway configuration was accepted' >&2; exit 1
fi
echo 'PASS: Railway HTTPS authority, host rejection, secure cookie, explicit API boundary (transport fixture)'
