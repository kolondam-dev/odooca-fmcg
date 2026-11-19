#!/usr/bin/env bash
set -euo pipefail

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != --gradle ) ]]; then
    echo "Usage: bash android/tools/integration_gate.sh [--gradle]" >&2
    exit 2
fi

cd "$(git rev-parse --show-toplevel)"
base="$(git rev-parse --verify refs/remotes/origin/main)"
head="$(git rev-parse HEAD)"
printf 'Base %s\nHEAD %s\n' "$base" "$head"

if ! git merge-base --is-ancestor "$base" "$head"; then
    echo "Sync this candidate with origin/main before checking it." >&2
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

if [[ $# -eq 1 ]]; then
    (
        cd android
        ./gradlew --no-daemon :core:domain:test :core:data:testDebugUnitTest \
            :app:lintDebug :app:assembleDebug -Podooca.baseUrl=https://ci.invalid
    )
    python android/tools/validate_contract.py pwa/contracts/openapi.json android/core/domain/build/contract-samples
else
    echo "Gradle checks require --gradle and the Android toolchain."
fi
