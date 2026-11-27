#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(git rev-parse --show-toplevel)"
[[ $# == 2 && "$1" =~ ^(24|35)$ ]]
api=$1
mkdir -p "$2"
evidence=$(realpath "$2")
[[ -z "$(ls -A "$evidence")" ]] || { echo "B09 requires a fresh evidence directory" >&2; exit 2; }
scratch=$(mktemp -d)
metadata=$evidence/run.tsv
phase=initialization
backend_started=false
backend_tls=
emulator_pid=
reverse=false
head=$(git rev-parse HEAD)
export DEV02A_UUID FMCG_STAGING_DATABASE FMCG_STAGING_DISPOSABLE=YES ANDROID_SERIAL=emulator-5556
DEV02A_UUID=$(python3 -c 'from uuid import uuid4; print(uuid4())')
run="odooca-b09-$DEV02A_UUID"
label="org.odooca.b09=$run"
FMCG_STAGING_DATABASE="fmcg_staging_${DEV02A_UUID//-/}"
sdk=${ANDROID_SDK_ROOT:-}
adb=$sdk/platform-tools/adb
emulator=$sdk/emulator/emulator

source android/tools/dev02a_cleanup.sh
source android/tools/dev02a_backend.sh
cleanup() {
    local result=$? failed=0 resource
    trap - EXIT
    trap '' INT TERM
    local report=$evidence/cleanup.tsv
    printf 'resource\tstatus\tdetail\n' > "$report" || failed=1
    cleanup_emulator >> "$report" || failed=1
    if [[ "$backend_started" == true ]]; then
        backend_cleanup >> "$report" || failed=1
    else
        for resource in gateway_process gateway_listener docker_containers docker_volumes docker_networks; do
            cleanup_record "$resource" not_started - >> "$report" || failed=1
        done
    fi
    if rm -rf -- "$scratch" && [[ ! -e "$scratch" && ! -L "$scratch" ]]; then
        cleanup_record temporary_directory removed - >> "$report" || failed=1
    else
        cleanup_record temporary_directory remaining - >> "$report" || true
        failed=1
    fi
    [[ -s "$report" && "$(wc -l < "$report")" == 10 ]] || failed=1
    if (( failed )); then
        printf 'cleanup=failed\nresult=failed phase=%s\n' "$phase" > "$evidence/result.txt"
        exit 1
    fi
    printf 'cleanup=passed\n' > "$evidence/result.txt"
    if (( result )); then
        printf 'result=failed phase=%s exit=%s\n' "$phase" "$result" >> "$evidence/result.txt"
        cat "$evidence/result.txt"
        exit "$result"
    fi
    printf 'result=passed\n' >> "$evidence/result.txt"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

printf 'sha=%s\napi=%s\nabi=x86_64\nfixture=b09-apk-v1\nuuid=%s\n' \
    "$head" "$api" "$DEV02A_UUID" > "$metadata"
[[ -z "$(git status --porcelain --untracked-files=no)" ]]
if [[ -n ${DEV02A_EXPECTED_SHA:-} ]]; then [[ "$head" == "$DEV02A_EXPECTED_SHA" ]]; fi
phase=kvm
test "$(uname -m)" = x86_64
[[ -r /dev/kvm && -w /dev/kvm ]]
"$emulator" -accel-check > "$scratch/kvm.log" 2>&1
grep -qi 'KVM.*usable' "$scratch/kvm.log"

phase=fixture_day
[[ "$(TZ=Asia/Makassar date +%u)" != 7 ]]
printf 'runner_os=%s\nrunner_image_version=%s\nbusiness_date_hint=%s\n' \
    "${ImageOS:-local}" "${ImageVersion:-local}" "$(TZ=Asia/Makassar date +%F)" >> "$metadata"

phase=tls_certificate
res=$scratch/res
mkdir -p "$res/xml" "$res/raw"
backend_certificate
cp "$scratch/ca.pem" "$res/raw/b09_ca.pem"
cat > "$res/xml/network_security_config.xml" <<'XML'
<network-security-config>
    <base-config cleartextTrafficPermitted="false" />
    <domain-config cleartextTrafficPermitted="false">
        <domain>127.0.0.1</domain>
        <trust-anchors><certificates src="@raw/b09_ca" /></trust-anchors>
    </domain-config>
</network-security-config>
XML

phase=build
(
    cd android
    timeout 15m ./gradlew --no-daemon :app:assembleDebug :app:assembleDebugAndroidTest \
        -Podooca.baseUrl=https://127.0.0.1:18443 "-Podooca.database=$FMCG_STAGING_DATABASE" \
        "-Podooca.b09Resources=$res"
) > "$scratch/build.log" 2>&1
app=android/app/build/outputs/apk/debug/app-debug.apk
tests=android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
sha256sum "$app" "$tests" > "$evidence/apk.sha256"

phase=backend
backend_started=true
backend_start > "$scratch/backend.log" 2>&1

phase=emulator
export ANDROID_AVD_HOME="$scratch/avd"
mkdir -p "$ANDROID_AVD_HOME"
image="system-images;android-$api;google_apis;x86_64"
revision=$(awk -F= '/^Pkg.Revision[[:space:]]*=/ {gsub(/[[:space:]\r]/, "", $2); print $2; exit}' \
    "$sdk/system-images/android-$api/google_apis/x86_64/source.properties")
[[ "$api:$revision" == 24:27 || "$api:$revision" == 35:9 ]]
printf 'image=%s\nimage_revision=%s\n' "$image" "$revision" >> "$metadata"
timeout 15 "$adb" start-server > "$scratch/adb.log" 2>&1
timeout 10 "$adb" devices > "$scratch/devices"
if grep -q "^$ANDROID_SERIAL[[:space:]]" "$scratch/devices"; then exit 1; fi
printf 'no\n' | "$sdk/cmdline-tools/19.0/bin/avdmanager" create avd --name odooca-b09 --package "$image" \
    --device pixel_2 > "$scratch/avd.log" 2>&1
"$emulator" -avd odooca-b09 -port 5556 -no-window -no-audio -no-boot-anim -no-snapshot -accel on \
    -gpu swiftshader_indirect > "$scratch/emulator.log" 2>&1 &
emulator_pid=$!
deadline=$((SECONDS + 300))
until [[ "$(timeout 5 "$adb" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || true)" == 1 ]]; do
    kill -0 "$emulator_pid" && (( SECONDS < deadline )) || exit 1
    sleep 3
done
[[ "$(timeout 10 "$adb" shell getprop ro.build.version.sdk | tr -d '\r')" == "$api" ]]
[[ "$(timeout 10 "$adb" shell getprop ro.product.cpu.abi | tr -d '\r')" == x86_64 ]]
timeout 15 "$adb" reverse --no-rebind tcp:18443 tcp:18443 > "$scratch/adb.log" 2>&1
reverse=true
for apk in "$app" "$tests"; do
    timeout 60 "$adb" install "$apk" > "$scratch/install.log" 2>&1
    grep -Fxq Success "$scratch/install.log"
done

run_apk_phase() {
    local invocation=$1 version=${2:-}
    local junit="files/b09-$DEV02A_UUID-$1.xml"
    timeout 10 "$adb" shell run-as com.kolondam.odooca.field rm -f "$junit" > "$scratch/adb.log" 2>&1
    # Pass the random TEST password over stdin and never upload raw runner output.
    printf '%s\n' "am instrument -w -r -e class com.kolondam.odooca.field.DisposableOdooReceiptTest \
        -e listener com.kolondam.odooca.field.B09XmlListener \
        -e dev02a true -e phase $invocation -e uuid $DEV02A_UUID \
        -e fixturePassword $FMCG_STAGING_PASSWORD_1 -e snapshotVersion '$version' \
        com.kolondam.odooca.field.test/androidx.test.runner.AndroidJUnitRunner" \
        | timeout 120 "$adb" shell > "$scratch/instrumentation" 2>&1
    timeout 10 "$adb" exec-out run-as com.kolondam.odooca.field cat "$junit" > "$scratch/junit.xml" 2>"$scratch/adb.log"
    python3 android/tools/dev02a_instrumentation.py "$scratch/instrumentation" "$scratch/junit.xml" \
        "$evidence/$invocation.xml" "$DEV02A_UUID" "$invocation" \
        > "$scratch/$invocation.json"
}

phase=audit_before
backend_audit before
phase=apk_first
run_apk_phase first
phase=audit_after
backend_audit after
phase=apk_replay
version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["request"]["payload"]["snapshot_version"])' \
    "$scratch/first.json")
run_apk_phase replay "$version"
phase=audit_replay
backend_audit after_replay
phase=verify
python3 android/tools/verify_dev02a_apk.py "$scratch"/{first,replay,before,after,after_replay}.json > "$scratch/verifier.json"
for file in first replay before after after_replay verifier; do cp "$scratch/$file.json" "$evidence/"; done
phase=complete
