#!/usr/bin/env bash
# Run from repository root with Docker. Fixture tests transport only, not Odoo auth.
set -euo pipefail
network="pwa-read-gateway-$$"
fixture_dir=$(mktemp -d)
cleanup() {
  docker rm -f "${network}-proxy" "${network}-pwa" "${network}-odoo" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
  rm -rf "$fixture_dir"
}
trap cleanup EXIT
docker network create "$network" >/dev/null
{ echo 'server { listen 80;'; cat pwa/hosting/staging-locations.conf; echo '}'; } > "$fixture_dir/default.conf"
docker run -d --name "${network}-odoo" --network "$network" --network-alias odoo \
  -v "$PWD/pwa/hosting/gateway-fixture.mjs:/fixture.mjs:ro" node:24-alpine node /fixture.mjs >/dev/null
docker run -d --name "${network}-pwa" --network "$network" --network-alias field-pwa fmcg-pwa-staging >/dev/null
docker run -d --name "${network}-proxy" --network "$network" -p 127.0.0.1::80 \
  -v "$fixture_dir/default.conf:/etc/nginx/conf.d/default.conf:ro" nginx:stable-alpine >/dev/null
port=$(docker port "${network}-proxy" 80/tcp | sed 's/.*://')
base="http://127.0.0.1:$port"
curl --retry 10 --retry-all-errors --retry-delay 1 --max-time 5 --fail "$base/field/" -o "$fixture_dir/index.html"
for attempt in {1..10}; do
  status=$(curl -s -o /dev/null -w '%{http_code}' "$base/api/v1/me/bootstrap")
  if [ "$status" != 502 ]; then break; fi
  sleep 1
done
test "$status" = 401
curl -fsS -D "$fixture_dir/headers" -c "$fixture_dir/cookies" "$base/web/login?redirect=%2Ffield%2F" -o /dev/null
grep -qi 'HttpOnly' "$fixture_dir/headers"
grep -qi 'Location: /field/' "$fixture_dir/headers"
for route in me/bootstrap sync/snapshot; do
  curl -fsS -b "$fixture_dir/cookies" "$base/api/v1/$route" -o "$fixture_dir/payload"
  grep -q '"fixture":true' "$fixture_dir/payload"
  grep -q "\"host\":\"127.0.0.1:$port\"" "$fixture_dir/payload"
  grep -q '"proto":"http"' "$fixture_dir/payload"
  test "$(curl -s -X POST -b "$fixture_dir/cookies" -o /dev/null -w '%{http_code}' "$base/api/v1/$route")" = 403
done
test "$(curl -s -X POST -b "$fixture_dir/cookies" -o /dev/null -w '%{http_code}' "$base/api/v1/sync/commands")" = 404
echo 'PASS: staging gateway routing, native-cookie forwarding and read-only boundary (transport fixture)'
