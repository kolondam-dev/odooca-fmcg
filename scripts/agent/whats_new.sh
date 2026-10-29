#!/usr/bin/env bash
# WAJIB dijalankan sebelum agen mengambil aksi: apa yang terjadi sejak commit terakhir agen ini.
#  1) fetch semua cabang  2) titik acuan = commit terakhir agen (dari tanda tangan di pesan commit)
#  3) commit sejak acuan di SEMUA cabang + tanda tangan agen  4) berkas berubah per ujung cabang
#  5) entri BARU di agent-log/*.log sejak acuan  6) rekomendasi basis kerja
# Pakai: scripts/agent/whats_new.sh [claude-dev|antigravity|claude-design|codex] [--since <ref>]
set -uo pipefail
agent="claude-dev"; since=""
while [ $# -gt 0 ]; do
  case "$1" in
    --since) since="${2:?--since butuh ref}"; shift 2 ;;
    claude-dev|antigravity|claude-design|codex) agent="$1"; shift ;;
    *) echo "argumen tidak dikenal: $1" >&2; exit 2 ;;
  esac
done
case "$agent" in
  claude-dev) pat="claude-dev agent" ;; antigravity) pat="antigravity-agent" ;; claude-design) pat="claude-design agent" ;; codex) pat="codex agent" ;;
esac
git fetch --all --prune -q 2>/dev/null || echo "(PERINGATAN: git fetch gagal; data bisa usang)"
if [ -n "$since" ]; then last="$(git rev-parse "$since")"; how="--since $since"
else
  last="$(git log --all -i --grep="task managed by ${pat}" -1 --format=%H)"; how="commit bertanda tangan '${pat}'"
  [ -z "$last" ] && { last="$(git rev-list --max-parents=0 --all | tail -1)"; how="belum ada commit bertanda tangan; dasar = commit akar"; }
fi
# ref unik per commit (hindari duplikasi: main/origin/main, cabang lokal vs remote, ref simbolik HEAD)
declare -A names; order=()
while read -r full; do
  short="${full#refs/heads/}"; short="${short#refs/remotes/}"; sha="$(git rev-parse "$full")"
  [ -z "${names[$sha]:-}" ] && order+=("$sha")
  names[$sha]="${names[$sha]:-}${names[$sha]:+, }$short"
done < <(git for-each-ref --format='%(refname)' refs/heads refs/remotes | grep -Ev '^refs/remotes/[^/]+/HEAD$|^refs/remotes/[^/]+$')

echo "=== AGEN: ${agent} | ACUAN: $(git log -1 --format='%h %ad %s' --date=format:'%Y-%m-%d %H:%M' "$last")"
echo "    ($how)"
echo; echo "=== UJUNG CABANG ==="
for sha in "${order[@]}"; do echo "  $(git log -1 --format='%h %ad' --date=format:'%Y-%m-%d %H:%M' "$sha")  ${names[$sha]}"; done
echo; echo "=== COMMIT SEJAK ACUAN (semua cabang, urut waktu) ==="; n=0
for c in $(git rev-list --all --not "$last" --reverse); do
  n=$((n+1)); sig="$(git log -1 --format=%B "$c" | grep -i '^task managed by' | tail -1)"
  echo "  $(git log -1 --format='%h %ad | %s' --date=format:'%m-%d %H:%M' "$c")"
  echo "      tanda tangan: ${sig:-(tanpa tanda tangan agen; mis. merge/commit pemilik)}"
done
[ "$n" -eq 0 ] && echo "  (tidak ada commit baru)"
echo; echo "=== BERKAS BERUBAH (acuan -> ujung) ==="
for sha in "${order[@]}"; do
  [ "$sha" = "$last" ] && continue; git merge-base --is-ancestor "$last" "$sha" 2>/dev/null || continue
  echo "  [${names[$sha]}]"; git diff --stat "$last" "$sha" | sed 's/^/    /'
done
echo; echo "=== ENTRI BARU DI agent-log/ SEJAK ACUAN (tanpa duplikat antar cabang) ==="; found=0
seen="$(mktemp)"; trap 'rm -f "$seen"' EXIT
for sha in "${order[@]}"; do
  [ "$sha" = "$last" ] && continue; git merge-base --is-ancestor "$last" "$sha" 2>/dev/null || continue
  d="$(git diff "$last" "$sha" -- agent-log | grep '^+' | grep -v '^+++' | sed 's/^+//')"
  new="$(printf '%s\n' "$d" | awk -v f="$seen" 'BEGIN{while((getline l<f)>0) s[l]=1} {if($0==""||!s[$0]) print}')"
  if [ -n "$(printf '%s' "$new" | tr -d '[:space:]')" ]; then
    found=1; echo "  --- [${names[$sha]}] ---"; printf '%s\n' "$new" | sed 's/^/  | /'
    printf '%s\n' "$new" | grep -v '^$' >> "$seen"
  fi
done
[ "$found" -eq 0 ] && echo "  (tidak ada entri baru)"
echo; echo "=== REKOMENDASI BASIS KERJA ==="
tip="$(git for-each-ref --sort=-committerdate --format='%(refname:short)' refs/remotes | grep -Ev '/HEAD$|^[^/]+$' | head -1)"
echo "  Commit terbaru ada di: $tip ($(git log -1 --format='%h %s' "$tip"))"
mainref="$(git for-each-ref --format='%(refname:short)' refs/remotes | grep -E '/main$' | head -1)"
for sha in "${order[@]}"; do
  [ -z "$mainref" ] && break
  if git merge-base --is-ancestor "$mainref" "$sha" 2>/dev/null && [ "$sha" != "$(git rev-parse "$mainref")" ]; then
    echo "  PERHATIAN: [${names[$sha]}] di DEPAN $mainref ($(git rev-list --count "$mainref..$sha") commit belum di-merge)."
  fi
done
echo "  Bangun patch di atas ujung cabang yang relevan, bukan di atas salinan lama."
