#!/usr/bin/env bash
# Run from repository root with Docker. Tests TLS/proxy transport, not Odoo auth.
set -euo pipefail
network="pwa-read-gateway-$$"
fixture_dir=$(mktemp -d)
cleanup() {
  docker rm -f "${network}-proxy" "${network}-pwa" "${network}-odoo" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
  rm -rf "$fixture_dir"
}
trap cleanup EXIT
# Ephemeral test-only key/cert; never print, publish, or commit them.
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=staging.test' \
  -addext 'subjectAltName=DNS:staging.test' \
  -keyout "$fixture_dir/key.pem" -out "$fixture_dir/cert.pem" >/dev/null 2>&1
{
  echo 'server { listen 80; server_name staging.test;'
  cat pwa/hosting/staging-locations.conf
  echo '}'
  echo 'server { listen 443 ssl; server_name staging.test;'
  echo 'ssl_certificate /etc/nginx/testtls/cert.pem; ssl_certificate_key /etc/nginx/testtls/key.pem;'
  cat pwa/hosting/staging-locations.conf
  echo '}'
} > "$fixture_dir/default.conf"
docker network create "$network" >/dev/null
docker build -f pwa/hosting/gateway-fixture.Dockerfile -t "${network}-fixture" pwa/hosting
docker run --rm "${network}-fixture" python -m pip show Werkzeug | sed -n '1,2p'
docker run --rm -v "$PWD/pwa/hosting/test_gateway_fixture.py:/test_gateway_fixture.py:ro" \
  "${network}-fixture" python /test_gateway_fixture.py
docker run -d --name "${network}-odoo" --network "$network" --network-alias odoo "${network}-fixture" >/dev/null
docker run -d --name "${network}-pwa" --network "$network" --network-alias field-pwa fmcg-pwa-staging >/dev/null
docker run -d --name "${network}-proxy" --network "$network" -p 127.0.0.1::80 -p 127.0.0.1::443 \
  -v "$fixture_dir/default.conf:/etc/nginx/conf.d/default.conf:ro" \
  -v "$fixture_dir:/etc/nginx/testtls:ro" nginx:stable-alpine >/dev/null
for scheme in http https; do
  internal_port=80
  spoof_proto=https
  if [ "$scheme" = https ]; then internal_port=443; spoof_proto=http; fi
  port=$(docker port "${network}-proxy" "$internal_port/tcp" | sed 's/.*://')
  base="$scheme://staging.test:$port"
  curl_args=(--noproxy staging.test --resolve "staging.test:$port:127.0.0.1" --cacert "$fixture_dir/cert.pem")
  curl "${curl_args[@]}" --retry 10 --retry-all-errors --retry-delay 1 --max-time 5 --fail "$base/field/" -o "$fixture_dir/index.html"
  for attempt in {1..10}; do
    status=$(curl "${curl_args[@]}" -s -o /dev/null -w '%{http_code}' "$base/api/v1/me/bootstrap")
    if [ "$status" != 502 ]; then break; fi
    sleep 1
  done
  test "$status" = 401
  # Also exercise the native-login fallback location with malicious proxy headers.
  curl "${curl_args[@]}" -fsS -D "$fixture_dir/headers" -c "$fixture_dir/cookies-$scheme" \
    -H 'X-Forwarded-Host: attacker.invalid:9000' -H "X-Forwarded-Proto: $spoof_proto" \
    "$base/web/login?redirect=%2Ffield%2F" -o /dev/null
  grep -qi 'HttpOnly' "$fixture_dir/headers"
  grep -qi 'Location: /field/' "$fixture_dir/headers"
  grep -qi "X-Fixture-Origin: $base" "$fixture_dir/headers"
  if [ "$scheme" = https ]; then grep -qi 'Set-Cookie: .*Secure' "$fixture_dir/headers"; fi
  for route in api/v1/me/bootstrap api/v1/sync/snapshot web/proxy-probe; do
    for spoof in no yes; do
      spoof_args=()
      if [ "$spoof" = yes ]; then
        spoof_args=(-H 'X-Forwarded-Host: attacker.invalid:9000' -H "X-Forwarded-Proto: $spoof_proto"
          -H 'X-Forwarded-For: 203.0.113.66' -H 'X-Forwarded-Port: 81'
          -H 'X-Forwarded-Prefix: /evil' -H "Forwarded: host=attacker.invalid;proto=$spoof_proto")
      fi
      curl "${curl_args[@]}" -fsS -b "$fixture_dir/cookies-$scheme" -H "Origin: $base" \
        "${spoof_args[@]}" "$base/$route" -o "$fixture_dir/payload"
      python3 - "$fixture_dir/payload" "$base" <<'PY'
import json
import sys
from urllib.parse import urlsplit
with open(sys.argv[1]) as stream:
    payload = json.load(stream)
base = urlsplit(sys.argv[2])
assert payload['fixture'] is True
assert payload['raw']['host'] == base.netloc, payload
assert payload['raw']['forwarded_host'] == base.netloc, payload
assert payload['raw']['forwarded_proto'] == base.scheme, payload
assert payload['raw']['forwarded_for'] != '203.0.113.66', payload
assert payload['effective']['remote_addr'] == payload['raw']['forwarded_for'], payload
assert payload['effective']['origin'] == sys.argv[2], payload
assert payload['effective']['host'] == base.netloc, payload
assert payload['effective']['scheme'] == base.scheme, payload
for name in ('forwarded', 'forwarded_port', 'forwarded_prefix'):
    assert payload['raw'][name] is None, payload
PY
    done
    test "$(curl "${curl_args[@]}" -s -b "$fixture_dir/cookies-$scheme" -H 'Origin: https://attacker.invalid' -o /dev/null -w '%{http_code}' "$base/$route")" = 400
  done
  for route in me/bootstrap sync/snapshot; do
    test "$(curl "${curl_args[@]}" -s -X POST -b "$fixture_dir/cookies-$scheme" -o /dev/null -w '%{http_code}' "$base/api/v1/$route")" = 403
  done
  test "$(curl "${curl_args[@]}" -s -X POST -b "$fixture_dir/cookies-$scheme" -o /dev/null -w '%{http_code}' "$base/api/v1/sync/commands")" = 404
  echo "PASS: staging $scheme gateway trusted headers, effective origin/port, spoof rejection, cookie and read-only boundary (Werkzeug transport fixture)"
done
