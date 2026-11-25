#!/usr/bin/env bash
# B09: create, exercise, and dispose of one isolated Odoo/PostgreSQL fixture.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
odoo_image="$(docker image inspect --format '{{.Id}}' "${DEV02A_ODOO_IMAGE:-odooca-fmcg-odoo:latest}")"
postgres_image="$(docker image inspect --format '{{.Id}}' "${DEV02A_POSTGRES_IMAGE:-postgres:16}")"
db_password="$(openssl rand -hex 24)"
umask 077
scratch="$(mktemp -d)"
run="odooca-b09-${scratch##*.}"
label="org.odooca.dev02a=$run"
network=
volume=
postgres=
odoo=
phase=initialization

cleanup() {
    result=$?
    trap - EXIT
    trap '' INT TERM
    cleanup_result=0
    if [[ -n "$odoo" ]]; then docker rm -fv "$odoo" >/dev/null || cleanup_result=1; fi
    if [[ -n "$postgres" ]]; then docker rm -fv "$postgres" >/dev/null || cleanup_result=1; fi
    if [[ -n "$volume" ]]; then docker volume rm "$volume" >/dev/null || cleanup_result=1; fi
    if [[ -n "$network" ]]; then docker network rm "$network" >/dev/null || cleanup_result=1; fi
    rm -rf -- "$scratch" || cleanup_result=1
    containers_left="$(docker ps -aq --filter "label=$label")" || cleanup_result=1
    volumes_left="$(docker volume ls -q --filter "label=$label")" || cleanup_result=1
    networks_left="$(docker network ls -q --filter "label=$label")" || cleanup_result=1
    if (( cleanup_result != 0 )) || [[ -n "$containers_left$volumes_left$networks_left" ]]; then
        printf 'cleanup=failed run=%s label=%s\n' "$run" "$label"
        exit 1
    fi
    printf 'cleanup=passed run=%s containers=0 volumes=0 networks=0\n' "$run"
    if (( result != 0 )); then printf 'result=failed phase=%s exit=%s\n' "$phase" "$result"; fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cd "$repo_root"
head="$(git rev-parse HEAD)"
printf 'fixture=dev02a-v1 commit=%s android_commit=%s odoo_image=%s postgres_image=%s\n' \
    "$head" "$(git rev-list -1 "$head" -- android ':!android/tools/verify_dev02a.sh')" \
    "$odoo_image" "$postgres_image"
printf 'tracked_tree=%s\n' "$(if [[ -z "$(git status --porcelain --untracked-files=no)" ]]; then echo clean; else echo dirty; fi)"
printf 'transport=HTTP loopback inside Odoo container; no published ports\n'

phase=postgres
network="$(docker network create --internal --label "$label" "$run")"
volume="$(docker volume create --label "$label" "$run-pgdata")"
postgres="$(docker create --pull never --name "$run-pg" --label "$label" --network "$network" \
    --network-alias fixture-pg --mount "type=volume,source=$volume,target=/var/lib/postgresql/data" \
    -e POSTGRES_USER=odoo -e POSTGRES_DB=postgres -e "POSTGRES_PASSWORD=$db_password" "$postgres_image")"
docker start "$postgres" >/dev/null
# The temporary server used by the Postgres entrypoint listens on a Unix socket only.
deadline=$((SECONDS + 90))
until docker exec "$postgres" pg_isready -q -h 127.0.0.1 -U odoo -d postgres; do
    if (( SECONDS >= deadline )); then exit 1; fi
    sleep 1
done
postgres_version="$(docker exec "$postgres" psql -U odoo -d postgres -Atc 'SHOW server_version')"
printf 'postgres_version=%s\n' "$postgres_version"

phase=odoo
odoo="$(docker create --pull never --name "$run-odoo" --label "$label" --network "$network" \
    --tmpfs /var/lib/odoo --tmpfs /mnt/extra-addons \
    -e "DEV02A_DB_PASSWORD=$db_password" --entrypoint bash "$odoo_image" -ec '
        printf "ODOO_VERSION="
        dpkg-query -W -f="\${Version}\n" odoo
        addons_path="$(/opt/deploy/addons_path.sh)"
        exec odoo -d dev02a --db_host fixture-pg --db_port 5432 -r odoo -w "$DEV02A_DB_PASSWORD" \
            --addons-path "/tmp/addons${addons_path#/opt/id-addons}" --without-demo=true \
            --data-dir /tmp/dev02a-odoo --http-interface 127.0.0.1 --http-port 18069 \
            -i id_mobile_api,id_approval --test-tags /id_mobile_api:TestDev02aHarness \
            --stop-after-init --log-level=test
    ')"
# Ship the exact committed addon tree and avoid importing addons baked into the image.
git archive "$head" addons | docker cp - "$odoo:/tmp"
set +e
timeout --kill-after=15s 15m docker start -a "$odoo" >"$scratch/odoo.log" 2>&1
run_result=$?
set -e
# The allowlisted test report excludes Odoo logs, HTTP bodies, cookies, and credentials.
sed -n -E '/^ODOO_VERSION=[[:alnum:].~+:_-]+$/p; s/^.*INFO [^ ]+ odoo.addons.id_mobile_api.tests.test_dev02a_harness: DEV02A_EVIDENCE (\{.*\})$/\1/p' \
    "$scratch/odoo.log" >"$scratch/evidence"
cat "$scratch/evidence"
if (( run_result != 0 )); then exit "$run_result"; fi
python3 - "$scratch/evidence" <<'PY'
from collections import Counter
import json
from pathlib import Path
import sys

lines = Path(sys.argv[1]).read_text().splitlines()
scenarios = Counter(json.loads(line)["scenario"] for line in lines if line.startswith("{"))
expected = Counter(installed_addons=1, unauthenticated=1, login=2, bootstrap=2, other_account_scope=1,
                   snapshot=1, command_receipt=1, wita_rollover=1, scope_revoked=1)
if scenarios != expected or sum(line.startswith("ODOO_VERSION=") for line in lines) != 1:
    sys.exit("DEV-02A evidence missing or duplicated")
PY
phase=complete
printf 'result=passed\n'
