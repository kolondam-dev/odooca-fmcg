#!/usr/bin/env bash
# Host-only DEV-02B probe using B09's disposable HTTPS fixture and cleanup.
set -euo pipefail
umask 077
cd "$(git rev-parse --show-toplevel)"
[[ -z "$(git status --porcelain --untracked-files=no)" ]]
source android/tools/dev02a_cleanup.sh
source android/tools/dev02a_backend.sh
scratch=$(mktemp -d)
metadata=$scratch/runtime
head=$(git rev-parse HEAD)
uuid=$(python3 -c 'from uuid import uuid4; print(uuid4())')
run="odooca-dev02b-$uuid"
label="org.odooca.b09=$run"
export FMCG_STAGING_DATABASE="fmcg_staging_${uuid//-/}" FMCG_STAGING_DISPOSABLE=YES
backend_tls=
backend_started=false
phase=certificate

cleanup() {
    local result=$?
    trap - EXIT
    trap '' INT TERM
    if [[ "$backend_started" == true ]]; then
        if ! backend_cleanup; then result=1; fi
    fi
    rm -rf -- "$scratch" || result=1
    if (( result == 0 )); then
        printf 'result=passed\n'
    else
        printf 'result=failed phase=%s exit=%s\n' "$phase" "$result"
    fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
printf 'sha=%s\nfixture=b09-dev02b-session-v1\n' "$head"
backend_certificate
phase=backend
backend_started=true
backend_start --session-probe > "$scratch/backend.log" 2>&1
cat "$metadata"
phase=session
python3 android/tools/verify_dev02b_session.py "$scratch/ca.pem"
