#!/usr/bin/env bash
# Mencetak baris oca.lock baru (HEAD terbaru cabang 19.0). Tinjau diff-nya, jalankan CI, lalu commit.
set -euo pipefail
LOCK="${LOCK:-oca.lock}"
echo "# repo  branch  sha   — pin OCA; diperbarui $(date +%F). Perbarui lewat scripts/oca_bump.sh"
grep -Ev '^\s*(#|$)' "$LOCK" | while read -r repo branch _; do
  sha="$(git ls-remote "https://github.com/OCA/${repo}.git" "refs/heads/${branch}" | cut -f1)"
  [ -n "$sha" ] || { echo "cabang ${branch} tidak ada di ${repo}" >&2; exit 1; }
  echo "$repo $branch $sha"
done
