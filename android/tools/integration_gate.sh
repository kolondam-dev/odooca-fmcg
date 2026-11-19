#!/usr/bin/env bash
set -euo pipefail

run_gradle=false
refresh_main=false
for option in "$@"; do
    case "$option" in
        --gradle) run_gradle=true ;;
        --refresh-main) refresh_main=true ;;
        *)
            echo "Usage: bash android/tools/integration_gate.sh [--gradle] [--refresh-main]" >&2
            exit 2
            ;;
    esac
done

cd "$(git rev-parse --show-toplevel)"
base_ref="${ANDROID_GATE_BASE:-refs/remotes/origin/main}"
if "$refresh_main"; then
    if [[ -n "${ANDROID_GATE_BASE:-}" ]]; then
        echo "--refresh-main uses origin/main. Clear ANDROID_GATE_BASE first." >&2
        exit 2
    fi
    git fetch origin refs/heads/main:refs/remotes/origin/main
fi
base="$(git rev-parse --verify --end-of-options "${base_ref}^{commit}")"
head="$(git rev-parse HEAD)"
printf 'Base %s\nHEAD %s\n' "$base" "$head"

if ! git merge-base --is-ancestor "$base" "$head"; then
    echo "Candidate HEAD must include the selected base $base_ref." >&2
    exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
    echo "Check a committed candidate with a clean working tree." >&2
    exit 1
fi

git diff --check "$base" "$head"
ruff check .
python scripts/check_manifests.py
python scripts/ci/plan.py --base "$base" --head "$head"
python -m unittest discover -s tests -p 'test_ci_*.py'
python -m unittest discover -s tests -p 'test_android_ci.py'

token_file="$(mktemp)"
trap 'rm -f "$token_file"' EXIT
python android/tools/gen_design_tokens.py pwa/design/tokens.json "$token_file"
diff -u android/core/designsystem/src/main/kotlin/com/kolondam/odooca/field/designsystem/Tokens.kt "$token_file"

if "$run_gradle"; then
    (
        cd android
        ./gradlew --no-daemon :core:domain:test :core:data:testDebugUnitTest \
            :app:lintDebug :app:assembleDebug -Podooca.baseUrl=https://ci.invalid
    )
    python android/tools/validate_contract.py pwa/contracts/openapi.json android/core/domain/build/contract-samples
else
    echo "Gradle checks require --gradle and the Android toolchain."
fi

if "$refresh_main"; then
    remote_main="$(git ls-remote --exit-code origin refs/heads/main)"
    if [[ "${remote_main%%$'\t'*}" != "$base" ]]; then
        echo "GitHub main changed during validation. Sync the candidate and rerun the gate." >&2
        exit 1
    fi
fi
