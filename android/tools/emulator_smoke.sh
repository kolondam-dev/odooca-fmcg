#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
if [[ $# -ne 3 || ! "$1" =~ ^(24|35)$ || ! "$3" =~ ^(smoke|ui)$ ]]; then
    echo "Usage: $0 {24|35} evidence-dir {smoke|ui}" >&2
    exit 2
fi

api=$1
mkdir -p "$2"
evidence=$(realpath "$2")
for name in smoke.tsv login.png display.txt instrumentation.tsv; do
    if [[ -e "$evidence/$name" ]]; then
        echo "Use a fresh evidence directory for each run" >&2
        exit 2
    fi
done
mode=$3
sdk=${ANDROID_SDK_ROOT:?Set ANDROID_SDK_ROOT to the isolated smoke SDK}
adb=$sdk/platform-tools/adb
emulator=$sdk/emulator/emulator
abi=x86_64
image="system-images;android-$api;google_apis;$abi"
image_revision=27
if [[ "$api" == 35 ]]; then image_revision=9; fi

work=$(mktemp -d)
export ANDROID_AVD_HOME="$work/avd"
export ANDROID_SERIAL=emulator-5556
export PATH="$sdk/platform-tools:$PATH"
package=com.kolondam.odooca.field
apk=android/app/build/outputs/apk/debug/app-debug.apk
report=$evidence/smoke.tsv
stage=toolchain
emulator_pid=
fixture_pid=
record() {
    printf '%s\t%s\n' "$1" "$2" | tee -a "$report"
}
cleanup() {
    local result=$?
    if (( result != 0 )); then record "$stage" FAIL; fi
    if [[ -n "$fixture_pid" ]]; then
        timeout 5 "$adb" reverse --remove tcp:18080 >/dev/null 2>&1 || true
        kill "$fixture_pid" 2>/dev/null || true
    fi
    if [[ -n "$emulator_pid" ]]; then
        timeout 5 "$adb" emu kill >/dev/null 2>&1 || true
        kill "$emulator_pid" 2>/dev/null || true
        wait "$emulator_pid" 2>/dev/null || true
    fi
    rm -rf -- "$work"
    return "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

: > "$report"
record sha "$(git rev-parse HEAD)"
record api "$api"
record abi "$abi"
record image "$image"
record expected_image_revision "$image_revision"
record mode "$mode"
for check in kvm build boot install cold_start login_ui instrumentation; do
    record "$check" NOT_RUN
done

revision() {
    awk -F= '/^Pkg.Revision[[:space:]]*=/ {gsub(/[[:space:]\r]/, "", $2); print $2; exit}' "$sdk/$1/source.properties"
}
verify_revision() {
    local observed
    observed=$(revision "$1")
    [[ "$observed" =~ ^[0-9]+(\.[0-9]+)*$ ]]
    record "$1.revision" "$observed"
    if [[ "$observed" != "$2" ]]; then
        echo "Expected $1 revision $2, found $observed" >&2
        return 1
    fi
}
verify_revision cmdline-tools/19.0 19.0
verify_revision platforms/android-37.0 2
verify_revision build-tools/36.0.0 36.0.0
verify_revision platform-tools 37.0.3
verify_revision emulator 37.3.10
verify_revision "system-images/android-$api/google_apis/$abi" "$image_revision"
java_runtime=$(java -XshowSettings:properties -version 2>&1 |
    awk -F' = ' '/^[[:space:]]*java.runtime.version = / { print $2 }')
record java_runtime "$java_runtime"
test "$java_runtime" = '17.0.17+10'
command -v javac >/dev/null
gradle_wrapper=$(sed -nE 's@^distributionUrl=.*gradle-([0-9]+(\.[0-9]+)+)-bin\.zip$@\1@p' \
    android/gradle/wrapper/gradle-wrapper.properties)
test -n "$gradle_wrapper"
record gradle_wrapper "$gradle_wrapper"
record host_arch "$(uname -m)"
record toolchain PASS

stage=kvm
test "$(uname -m)" = x86_64
test -r /dev/kvm && test -w /dev/kvm
"$emulator" -accel-check > "$work/accel.log" 2>&1
grep -qi 'KVM.*usable' "$work/accel.log"
record kvm PASS

stage=build
gradle_args=(-Podooca.baseUrl=https://ci.invalid)
if [[ "$mode" == ui ]]; then gradle_args=(-Podooca.uiFixture=true); fi
(cd android && timeout 12m ./gradlew --no-daemon :app:assembleDebug "${gradle_args[@]}")
test -s "$apk"
record apk_sha256 "$(sha256sum "$apk" | cut -d' ' -f1)"
record build PASS

stage=boot
# Each AVD is new and gets a dedicated adb serial. An existing serial means another run owns it.
timeout 15 "$adb" start-server >/dev/null
if timeout 10 "$adb" devices | grep -q "^$ANDROID_SERIAL[[:space:]]"; then
    echo "ADB serial $ANDROID_SERIAL is already in use" >&2
    exit 1
fi
mkdir -p "$ANDROID_AVD_HOME"
printf 'no\n' | "$sdk/cmdline-tools/19.0/bin/avdmanager" create avd --name odooca-smoke --package "$image" --device pixel_2
"$emulator" -avd odooca-smoke -port 5556 -no-window -no-audio -no-boot-anim \
    -no-snapshot -accel on -gpu swiftshader_indirect > "$work/emulator.log" 2>&1 &
emulator_pid=$!
deadline=$((SECONDS + 300))
while true; do
    kill -0 "$emulator_pid"
    if [[ "$(timeout 5 "$adb" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || true)" == 1 ]] &&
       timeout 5 "$adb" shell pm path android 2>/dev/null | grep -q '^package:'; then
        break
    fi
    if (( SECONDS >= deadline )); then
        echo "Emulator boot timed out after 300 seconds" >&2
        exit 1
    fi
    sleep 3
done
observed_api=$(timeout 10 "$adb" shell getprop ro.build.version.sdk | tr -d '\r')
observed_abi=$(timeout 10 "$adb" shell getprop ro.product.cpu.abi | tr -d '\r')
[[ "$observed_api" == "$api" && "$observed_abi" == "$abi" ]]
record observed_api "$observed_api"
record observed_abi "$observed_abi"
timeout 10 "$adb" shell input keyevent 82
record boot PASS

stage=install
timeout 60 "$adb" install "$apk" | grep -q '^Success'
timeout 10 "$adb" shell pm path "$package" | grep -q '^package:'
record install PASS

stage=cold_start
timeout 10 "$adb" shell am force-stop "$package"
timeout 35 "$adb" shell am start -W -n "$package/.MainActivity" > "$work/start.txt"
grep -Eq '^Status: ok[[:space:]]*$' "$work/start.txt"
record cold_start PASS

stage=login_ui
deadline=$((SECONDS + 60))
while true; do
    if timeout 10 "$adb" shell dumpsys activity activities > "$work/activities.txt" &&
        grep -Eq "(mResumedActivity|topResumedActivity|ResumedActivity):.*com\.kolondam\.odooca\.field/\.MainActivity" "$work/activities.txt" &&
        timeout 10 "$adb" shell uiautomator dump /data/local/tmp/odooca-ui.xml >/dev/null 2>&1 &&
        timeout 10 "$adb" exec-out cat /data/local/tmp/odooca-ui.xml > "$work/ui.xml" &&
        python3 - "$work/ui.xml" <<'PY'
import sys
import xml.etree.ElementTree as ET

try:
    app_nodes = [
        node for node in ET.parse(sys.argv[1]).iter("node")
        if node.get("package") == "com.kolondam.odooca.field"
    ]
except ET.ParseError:
    sys.exit(1)
texts = {node.get("text") for node in app_nodes}
test_ids = {node.get("resource-id") for node in app_nodes}
sys.exit(not (
    "Masuk dengan akun Odoo Anda" in texts
    and {"login_user", "login_password", "login_submit"} <= test_ids
))
PY
    then
        break
    fi
    if (( SECONDS >= deadline )); then
        echo "Login semantics did not appear in the foreground activity" >&2
        exit 1
    fi
    sleep 2
done
timeout 10 "$adb" exec-out screencap -p > "$work/login.png"
test -s "$work/login.png"
mv "$work/login.png" "$evidence/login.png"
record login_ui PASS

if [[ "$mode" == ui ]]; then
    stage=instrumentation
    connected=$(timeout 10 "$adb" devices | awk 'NR > 1 && NF {print $1}')
    if [[ "$connected" != "$ANDROID_SERIAL" ]]; then
        echo "Instrumentation requires exactly one attached device: the smoke AVD" >&2
        exit 1
    fi
    python3 android/tools/ui_smoke_fixture.py &
    fixture_pid=$!
    for _ in {1..20}; do
        kill -0 "$fixture_pid"
        if curl -fsS --max-time 1 http://127.0.0.1:18080/health >/dev/null 2>&1; then break; fi
        sleep 0.25
    done
    kill -0 "$fixture_pid"
    curl -fsS --max-time 1 http://127.0.0.1:18080/health >/dev/null
    timeout 10 "$adb" reverse tcp:18080 tcp:18080
    timeout 10 "$adb" shell pm clear "$package" | grep -q '^Success'
    timeout 10 "$adb" shell wm size | tee "$evidence/display.txt"
    timeout 10 "$adb" shell wm density | tee -a "$evidence/display.txt"
    timeout 10 "$adb" shell settings get system font_scale | tee -a "$evidence/display.txt"
    test_started=$(date +%s%N)
    test_result=0
    (cd android && timeout 12m ./gradlew --no-daemon :app:connectedDebugAndroidTest "${gradle_args[@]}") || test_result=$?
    python3 android/tools/ui_smoke_report.py android/app/build/outputs/androidTest-results/connected/debug \
        "$evidence/instrumentation.tsv" "$test_started"
    test "$test_result" -eq 0
    record instrumentation PASS
fi
