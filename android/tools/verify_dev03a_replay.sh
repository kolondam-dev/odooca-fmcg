#!/usr/bin/env bash
# Disposable host integration. No Android runtime or production target is used.
set -euo pipefail
umask 077
cd "$(git rev-parse --show-toplevel)"
[[ -z "$(git status --porcelain --untracked-files=no)" ]]
source android/tools/dev02a_cleanup.sh
source android/tools/dev02a_backend.sh
scratch=$(mktemp -d)
metadata=$scratch/runtime
head=$(git rev-parse HEAD)
export DEV02A_UUID FMCG_STAGING_DATABASE FMCG_STAGING_DISPOSABLE=YES
DEV02A_UUID=$(python3 -c 'from uuid import uuid4; print(uuid4())')
run="odooca-dev03a-$DEV02A_UUID"
label="org.odooca.b09=$run"
FMCG_STAGING_DATABASE="fmcg_staging_${DEV02A_UUID//-/}"
backend_tls=
started=false
phase=certificate
cleanup() {
    local result=$?
    trap - EXIT
    trap '' INT TERM
    if [[ "$started" == true ]]; then backend_cleanup || result=1; fi
    rm -rf -- "$scratch" || result=1
    if (( result == 0 )); then printf 'result=passed\n'; else printf 'result=failed phase=%s\n' "$phase"; fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
printf 'sha=%s\nfixture=b09-dev03a-loss-v1\n' "$head"
backend_certificate
phase=backend
started=true
backend_start --drop-first-command-receipt > "$scratch/backend.log" 2>&1
cat "$metadata"
phase=first
backend_audit before
python3 android/tools/verify_dev03a_replay.py first "$scratch"
backend_audit after
phase=replay
python3 android/tools/verify_dev03a_replay.py replay "$scratch"
backend_audit after_replay
[[ $(grep -Fxc 'command_receipt_truncated=1' "$scratch/tls.log") == 1 ]]
phase=verify
python3 android/tools/verify_dev03a_replay.py verify "$scratch"
