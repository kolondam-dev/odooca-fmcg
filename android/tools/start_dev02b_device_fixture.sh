#!/usr/bin/env bash
# Lead only: lease an isolated fixture in the foreground. Ctrl+C releases it.
set -euo pipefail
umask 077
cd "$(git rev-parse --show-toplevel)"
[[ $# -eq 1 && -z "$(git status --porcelain --untracked-files=no)" ]]
# Use a new private directory outside the checkout and keep all private state out of artifacts.
mkdir -m 700 -- "$1"
handoff=$(realpath "$1")
scratch=$(mktemp -d)
metadata=$scratch/runtime
head=$(git rev-parse HEAD)
uuid=$(python3 -c 'from uuid import uuid4; print(uuid4())')
run="odooca-dev02b-$uuid"
label="org.odooca.b09=$run"
export FMCG_STAGING_DATABASE="fmcg_staging_${uuid//-/}" FMCG_STAGING_DISPOSABLE=YES
export DEV02B_IDLE_SECONDS=${DEV02B_IDLE_SECONDS:-180}
[[ "$DEV02B_IDLE_SECONDS" =~ ^[1-9][0-9]{1,2}$ ]]
(( DEV02B_IDLE_SECONDS >= 15 && DEV02B_IDLE_SECONDS <= 600 ))
backend_tls=
started=false
source android/tools/dev02a_cleanup.sh
source android/tools/dev02a_backend.sh
cleanup() {
    local result=$?
    trap - EXIT
    trap '' INT TERM
    if [[ "$started" == true ]]; then backend_cleanup || result=1; fi
    rm -rf -- "$scratch" || result=1
    rm -f -- "$handoff/accounts.env" "$handoff/ready.tsv" || result=1
    exit "$result"
}
trap cleanup EXIT
trap 'exit 0' INT TERM
backend_certificate
started=true
backend_start > "$scratch/backend.log" 2>&1
docker logs "$backend_odoo" > "$scratch/startup.log" 2>&1
grep -Fxq "B09_SESSION_IDLE_SECONDS=$DEV02B_IDLE_SECONDS" "$scratch/startup.log"
install -m 600 "$scratch/ca.pem" "$handoff/fixture-ca.pem"
printf 'FMCG_STAGING_PASSWORD_1=%s\nFMCG_STAGING_PASSWORD_2=%s\n' \
    "$FMCG_STAGING_PASSWORD_1" "$FMCG_STAGING_PASSWORD_2" > "$handoff/accounts.env"
{
    printf 'sha=%s\ndatabase=%s\nidle_seconds=%s\nendpoint=https://127.0.0.1:18443\n' \
        "$head" "$FMCG_STAGING_DATABASE" "$DEV02B_IDLE_SECONDS"
    openssl x509 -in "$handoff/fixture-ca.pem" -noout -fingerprint -sha256
    cat "$metadata"
} > "$scratch/ready"
mv -- "$scratch/ready" "$handoff/ready.tsv"
printf 'fixture=ready lease_seconds=7200\n'
deadline=$((SECONDS + 7200))
while (( SECONDS < deadline )); do
    kill -0 "$backend_tls"
    [[ "$(docker inspect -f '{{.State.Running}}' "$backend_odoo")" == true ]]
    sleep 3
done
