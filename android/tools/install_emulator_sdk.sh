#!/usr/bin/env bash
set -euo pipefail

API=${1:?Provide API 24 or 35}
[[ "$API" == 24 || "$API" == 35 ]]
: "${ANDROID_SDK_ROOT:?Provide isolated SDK directory}" "${RUNNER_TEMP:=${TMPDIR:-/tmp}}"

install_archive() {
  local package=$1 checksum=$2 destination=$3
  local archive="$RUNNER_TEMP/${package##*/}"
  curl --fail --silent --show-error --location --retry 3 \
    "https://dl.google.com/android/repository/$package" -o "$archive"
  printf '%s  %s\n' "$checksum" "$archive" | sha1sum --check --status
  mkdir -p "$destination"
  unzip -q "$archive" -d "$destination"
}

mkdir -p "$ANDROID_SDK_ROOT/cmdline-tools"
install_archive commandlinetools-linux-13114758_latest.zip \
  5fdcc763663eefb86a5b8879697aa6088b041e70 "$ANDROID_SDK_ROOT/cmdline-tools"
mv "$ANDROID_SDK_ROOT/cmdline-tools/cmdline-tools" "$ANDROID_SDK_ROOT/cmdline-tools/19.0"
manager="$ANDROID_SDK_ROOT/cmdline-tools/19.0/bin/sdkmanager"
(set +o pipefail; yes | "$manager" --licenses >/dev/null)
"$manager" --channel=0 "platforms;android-37.0" "build-tools;36.0.0"

# Install the exact host tools and image archives to avoid rolling packages
# and the API 35 image pulling a second emulator through SDK Manager.
install_archive platform-tools_r37.0.3-linux.zip \
  e1579b288a7ae4e9bc28dedec6a154d78b3c04ed "$ANDROID_SDK_ROOT"
install_archive emulator-linux_x64-16970787.zip \
  5f7314368fc6c05c937f6991bb4106214dc389e7 "$ANDROID_SDK_ROOT"
# The emulator ZIP has source.properties but avdmanager requires a local package entry.
cat > "$ANDROID_SDK_ROOT/emulator/package.xml" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<repo:repository xmlns:repo="http://schemas.android.com/repository/android/common/02" xmlns:generic="http://schemas.android.com/repository/android/generic/02" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <localPackage path="emulator" obsolete="false">
    <type-details xsi:type="generic:genericDetailsType"/>
    <revision><major>37</major><minor>3</minor><micro>10</micro></revision>
    <display-name>Android Emulator</display-name>
  </localPackage>
</repo:repository>
EOF
images="$ANDROID_SDK_ROOT/system-images/android-$API/google_apis"
case "$API" in
  24) install_archive sys-img/google_apis/x86_64-24_r27.zip \
        46d09c0723b77ddba00f2281099a2c44a88ac971 "$images" ;;
  35) install_archive sys-img/google_apis/x86_64-35_r09.zip \
        0103e6dab21290c4b9d16550a3ce99476f884eef "$images" ;;
  *) echo "Unsupported smoke API: $API" >&2; exit 2 ;;
esac
