#!/usr/bin/env bash
# Mengambil repo OCA pada SHA yang dikunci di oca.lock.
# Pakai: scripts/fetch_oca.sh [DEST=/opt/oca]   (env: LOCK=oca.lock, KEEP_GIT=1 untuk menyimpan .git)
set -euo pipefail
LOCK="${LOCK:-oca.lock}"
DEST="${1:-/opt/oca}"
mkdir -p "$DEST"
grep -Ev '^\s*(#|$)' "$LOCK" | while read -r repo branch sha; do
  d="$DEST/$repo"
  rm -rf "$d"; git init -q "$d"
  git -C "$d" remote add origin "https://github.com/OCA/${repo}.git"
  git -C "$d" fetch -q --depth 1 origin "$sha"
  git -C "$d" checkout -q FETCH_HEAD
  got="$(git -C "$d" rev-parse HEAD)"
  [ "$got" = "$sha" ] || { echo "SHA tidak cocok untuk $repo: $got != $sha" >&2; exit 1; }
  [ "${KEEP_GIT:-0}" = "1" ] || rm -rf "$d/.git"
  echo "ok $repo@${sha:0:10}"
done
