#!/usr/bin/env bash
# Mencetak addons_path: addon id_* + semua repo OCA yang di-pin. Dipakai init.sh dan CI.
set -euo pipefail
p="/opt/id-addons"
for d in /opt/oca/*/; do [ -d "$d" ] && p="$p,${d%/}"; done
printf '%s' "$p"
