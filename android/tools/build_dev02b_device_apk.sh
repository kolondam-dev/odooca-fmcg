#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
if [[ ${1:-} == --origin ]]; then
    [[ $# == 4 && "$3" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$ ]]
    origin=$2 database=$3 destination=$4
    tls=android-system
    fixture_options=(-Podooca.deviceSystemTls=true)
else
    [[ $# == 3 && "$1" =~ ^fmcg_staging_[a-f0-9]{32}$ ]]
    origin=https://127.0.0.1:18443 database=$1 destination=$3
    tls=loopback-ca
    ca=$(realpath "$2")
    fixture_options=()
fi
mkdir -m 700 -- "$destination"
output=$(realpath "$destination")
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
if [[ "$tls" == loopback-ca ]]; then
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
    fixture_options+=("-Podooca.b09Resources=$scratch/res")
fi
(
    cd android
    ./gradlew --no-daemon :app:assembleDebug :app:assembleDebugAndroidTest \
        "-Podooca.baseUrl=$origin" "-Podooca.database=$database" \
        "${fixture_options[@]}" -Podooca.deviceFixture=true
)
cp android/app/build/outputs/apk/debug/app-debug.apk "$output/poco-fixture.apk"
cp android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk "$output/poco-fixture-test.apk"
(
    cd "$output"
    sha256sum poco-fixture.apk poco-fixture-test.apk > apk.sha256
)
{
    printf 'sha=%s\ndatabase=%s\norigin=%s\ntls=%s\napplication_id=com.kolondam.odooca.field.fixture\n' \
        "$(git rev-parse HEAD)" "$database" "$origin" "$tls"
    if [[ "$tls" == loopback-ca ]]; then openssl x509 -in "$ca" -noout -fingerprint -sha256; fi
} > "$output/build.txt"
