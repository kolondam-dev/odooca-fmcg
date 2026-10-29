#!/usr/bin/env bash
# Menambah entri ke agent-log/<agen>.log (append-only) dan mencetak baris tanda tangan commit.
# Pakai : scripts/agent/log_entry.sh <agen> <INFO|WARN|ERROR> "<judul>" "<butir 1>" "<butir 2>" ...
#         scripts/agent/log_entry.sh <agen> --sig-only      # hanya cetak tanda tangan commit
# Agen  : claude-dev | antigravity | claude-design
# Waktu : ISO 8601 zona WIB (+07:00), sama dengan konvensi AntiGravity. Jangan menulis rahasia ke log.
set -euo pipefail
agent="${1:?agen wajib: claude-dev|antigravity|claude-design}"; shift
case "$agent" in
  claude-dev)    file="claude-dev.log";    sig="claude-dev agent" ;;
  antigravity)   file="anti-gravity.log";  sig="antigravity-agent" ;;
  claude-design) file="claude-design.log"; sig="claude-design agent" ;;
  codex) file="codex.log"; sig="codex agent" ;;
  *) echo "agen tidak dikenal: $agent" >&2; exit 2 ;;
esac
ts="$(TZ=Asia/Jakarta date +%Y-%m-%dT%H:%M:%S%:z)"
if [ "${1:-}" = "--sig-only" ]; then echo "task managed by ${sig} at ${ts}"; exit 0; fi
level="${1:?level wajib: INFO|WARN|ERROR}"; title="${2:?judul wajib}"; shift 2
case "$level" in INFO|WARN|ERROR) ;; *) echo "level harus INFO|WARN|ERROR" >&2; exit 2 ;; esac
root="$(git rev-parse --show-toplevel)"; mkdir -p "$root/agent-log"; out="$root/agent-log/$file"
{
  [ -s "$out" ] && echo
  echo "[${ts}] [${level}] ${title}"
  for b in "$@"; do echo "- ${b}"; done
  echo "- Task managed by ${sig} at ${ts}"
} >> "$out"
echo "entri ditambahkan ke agent-log/${file}"
echo "tanda tangan commit (baris TERAKHIR pesan commit):"
echo "task managed by ${sig} at ${ts}"
