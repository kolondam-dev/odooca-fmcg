#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
[[ $# == 3 && "$1" =~ ^fmcg_staging_[a-f0-9]{32}$ ]]
ca=$(realpath "$2")
mkdir -m 700 -- "$3"
output=$(realpath "$3")
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
# Accept exactly one public PEM certificate. The fixture signing key stays on the host.
python3 - "$ca" <<'PY'
import re
import sys
from pathlib import Path
data = Path(sys.argv[1]).read_bytes()
if not re.fullmatch(rb"-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----\s*", data):
    sys.exit("expected one public CA certificate")
PY
openssl x509 -in "$ca" -noout -checkend 0
openssl x509 -in "$ca" -noout -ext basicConstraints | grep -Fq 'CA:TRUE'
source android/tools/dev02a_backend.sh
b09_android_resources "$scratch/res" "$ca"
(
    cd android
    ./gradlew --no-daemon :app:assembleDebug :app:assembleDebugAndroidTest \
        -Podooca.baseUrl=https://127.0.0.1:18443 "-Podooca.database=$1" \
        "-Podooca.b09Resources=$scratch/res" -Podooca.deviceFixture=true
)
cp android/app/build/outputs/apk/debug/app-debug.apk "$output/poco-fixture.apk"
cp android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk "$output/poco-fixture-test.apk"
(
    cd "$output"
    sha256sum poco-fixture.apk poco-fixture-test.apk > apk.sha256
)
{
    printf 'sha=%s\ndatabase=%s\napplication_id=com.kolondam.odooca.field.fixture\n' "$(git rev-parse HEAD)" "$1"
    openssl x509 -in "$ca" -noout -fingerprint -sha256
} > "$output/build.txt"
