#!/usr/bin/env bash
# Menjalankan deploy/init.sh di SANDBOX AGEN (tanpa Docker) dan menunggu HTTP 200.
# Pakai: scripts/sandbox/test_init.sh <nama_log> [VAR=nilai ...]
#   contoh A (DB kosong)      : buat DB init_db kosong, lalu: test_init.sh testA
#   contoh restart            : test_init.sh testB
#   contoh reset + restore    : taruh dump di /opt/deploy/seed/, lalu: test_init.sh testC RESET_DB=tokC1
# PERINGATAN: jangan menulis `pkill -f "odoo-bin"` langsung di perintah shell; pola itu cocok dengan baris perintah
# shell itu sendiri dan mematikannya. Pakai pola `[o]doo-bin`.
LOG=/tmp/$1.log; shift
"$(dirname "$0")/sandbox_up.sh" >/dev/null 2>&1; sleep 1
export PGHOST=localhost PGUSER=postgres PGPASSWORD=pgadmin-sandbox PGDATABASE=init_db
export ODOO_DB_USER=odoo_app ODOO_DB_PASSWORD=app-sandbox ADMIN_PASSWD=master-sandbox ADMIN_LOGIN_PASSWORD=admin-sandbox
export BASE_URL=http://demo.example.test ODOO_DATA_DIR=/tmp/odoo-data PORT=8071
export INIT_MODULES="${INIT_MODULES:-id_base,l10n_id,sale_management,stock}"
for kv in "$@"; do export "$kv"; done
pkill -f "[o]doo-bin.*8071" 2>/dev/null; sleep 1
setsid nohup /opt/deploy/init.sh > "$LOG" 2>&1 < /dev/null &
for i in $(seq 1 100); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8071/web/login 2>/dev/null)
  [ "$code" = "200" ] && { echo "HTTP 200 setelah ~$((i*3))s"; break; }
  grep -qE "^\[init\].*(wajib|tidak boleh|tidak siap)|Traceback|^ERROR:" "$LOG" && { echo "init gagal; lihat $LOG"; break; }
  sleep 3
done
