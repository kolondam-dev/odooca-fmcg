#!/usr/bin/env bash
# deploy/init.sh — entrypoint idempoten: siapkan DB -> (restore | build) -> postinit -> jalankan Odoo.
# STATUS: kerangka M0, BELUM DIUJI (perlu Docker + Postgres). Lihat docs/HANDOFF.md.
#
# Env wajib : PGHOST PGUSER PGPASSWORD (admin Postgres; di Railway biasanya user "postgres")
#             ODOO_DB_USER ODOO_DB_PASSWORD (peran untuk Odoo; Odoo menolak db_user=postgres)
#             ADMIN_PASSWD (master password Odoo)
# Env opsional: PGPORT PGDATABASE BASE_URL ADMIN_LOGIN_PASSWORD INIT_MODULES RESET_DB
#               SEED_URL SEED_SHA256 SEED_FILESTORE_URL SEED_FILESTORE_SHA256
#               ODOO_WORKERS ODOO_MAX_CRON PORT ODOO_DATA_DIR
set -euo pipefail
log() { echo "[init] $*"; }

: "${PGHOST:?PGHOST wajib}" "${PGUSER:?PGUSER wajib}" "${PGPASSWORD:?PGPASSWORD wajib}"
: "${ODOO_DB_USER:?ODOO_DB_USER wajib}" "${ODOO_DB_PASSWORD:?ODOO_DB_PASSWORD wajib}"
: "${ADMIN_PASSWD:?ADMIN_PASSWD wajib}"
PGPORT="${PGPORT:-5432}"; PGDATABASE="${PGDATABASE:-fmcg}"
DATA_DIR="${ODOO_DATA_DIR:-/var/lib/odoo}"

if [ "$(id -u)" = "0" ]; then
  mkdir -p "$DATA_DIR"
  chown -R odoo:odoo "$DATA_DIR"
  if command -v gosu >/dev/null 2>&1; then
    exec gosu odoo "$0" "$@"
  elif command -v runuser >/dev/null 2>&1; then
    exec runuser -u odoo -- "$0" "$@"
  else
    exec su -p -s /bin/bash odoo -c "exec '$0' \"\$@\"" -- "$@"
  fi
fi

INIT_MODULES="${INIT_MODULES:-id_base,id_approval,id_ui,id_ui_shell,id_ui_form,id_promo_governance,id_dashboard_monetary,id_dashboard_wms,l10n_id,fleet,hr,uom,product_expiry,stock_account}"
export PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE
case "$ODOO_DB_USER" in postgres) log "ODOO_DB_USER tidak boleh 'postgres'"; exit 1;; esac
case "$ODOO_DB_USER$ODOO_DB_PASSWORD$PGDATABASE" in *\'*|*\"*|*\\*) log "kutip/backslash tidak diizinkan pada user, password, atau nama DB"; exit 1;; esac

q() { psql -v ON_ERROR_STOP=1 -qtAX -c "$1"; }   # sebagai admin Postgres
has_mark() { [ "$(q "SELECT 1 FROM id_meta.marks WHERE name='$1'")" = "1" ]; }
set_mark() { q "INSERT INTO id_meta.marks(name) VALUES ('$1') ON CONFLICT DO NOTHING"; }

# Odoo dijalankan dengan kredensial peran Odoo (bukan admin). env PG* menimpa odoo.conf, jadi diset eksplisit.
# Subperintah (mis. "shell") HARUS berada sebelum opsi: odoo_run shell --no-http
odoo_run() {
  local sub=""
  case "${1:-}" in shell) sub="shell"; shift ;; esac
  env PGUSER="$ODOO_DB_USER" PGPASSWORD="$ODOO_DB_PASSWORD" \
    odoo $sub -c /tmp/odoo.conf -d "$PGDATABASE" --db_host "$PGHOST" --db_port "$PGPORT" \
         --addons-path "$(/opt/deploy/addons_path.sh)" --data-dir "$DATA_DIR" --without-demo=true "$@"
}

# 0. Tunggu Postgres
for i in $(seq 1 60); do pg_isready -q && break; [ "$i" = 60 ] && { log "Postgres tidak siap"; exit 1; }; sleep 2; done

# 1. Peran, kepemilikan, skema meta (idempoten)
q "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='${ODOO_DB_USER}') THEN CREATE ROLE \"${ODOO_DB_USER}\" LOGIN CREATEDB PASSWORD '${ODOO_DB_PASSWORD}'; END IF; END \$\$;"
q "ALTER ROLE \"${ODOO_DB_USER}\" PASSWORD '${ODOO_DB_PASSWORD}'"
q "ALTER DATABASE \"${PGDATABASE}\" OWNER TO \"${ODOO_DB_USER}\""
q "ALTER SCHEMA public OWNER TO \"${ODOO_DB_USER}\""
q "CREATE SCHEMA IF NOT EXISTS id_meta;
   CREATE TABLE IF NOT EXISTS id_meta.marks(name text PRIMARY KEY, at timestamptz NOT NULL DEFAULT now());
   CREATE TABLE IF NOT EXISTS id_meta.reset_log(token text PRIMARY KEY, at timestamptz NOT NULL DEFAULT now());"

# 2. Konfigurasi Odoo (admin_passwd hanya bisa lewat berkas konfigurasi; tidak disimpan di repo)
umask 077
ADDONS_PATH="$(/opt/deploy/addons_path.sh)"
cat <<EOF > /tmp/odoo.conf
[options]
admin_passwd = ${ADMIN_PASSWD}
addons_path = ${ADDONS_PATH}
data_dir = ${DATA_DIR}
without_demo = True
db_host = ${PGHOST}
db_port = ${PGPORT}
db_user = ${ODOO_DB_USER}
db_password = ${ODOO_DB_PASSWORD}
EOF

# Subperintah shell: jika dipanggil langsung (mis. oleh CI atau operator untuk skrip/repl)
if [ "${1:-}" = "shell" ]; then
  shift
  log "menjalankan Odoo shell dengan konfigurasi penuh"
  odoo_run shell "$@"
  exit $?
fi

# 3. Reset terkontrol: token harus BARU (tercatat di id_meta.reset_log); token lama diabaikan
if [ -n "${RESET_DB:-}" ]; then
  tok="${RESET_DB//[^A-Za-z0-9._-]/}"
  if [ "$(q "SELECT 1 FROM id_meta.reset_log WHERE token='${tok}'")" = "1" ]; then
    log "RESET_DB='${tok}' sudah pernah dipakai; diabaikan. Hapus variabel ini."
  else
    log "RESET_DB='${tok}': mengosongkan skema public dan marks"
    # DROP SCHEMA ... CASCADE dalam SATU transaksi menghabiskan lock Postgres ("out of shared memory") pada ribuan
    # objek Odoo. Hapus tabel satu per satu (tiap perintah = transaksi sendiri), baru skema dan sisanya.
    q "SELECT format('DROP TABLE IF EXISTS public.%I CASCADE;', tablename) FROM pg_tables WHERE schemaname='public'" \
      | psql -v ON_ERROR_STOP=1 -qtAX >/dev/null
    q "DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION \"${ODOO_DB_USER}\"; TRUNCATE id_meta.marks;"
    rm -rf "${DATA_DIR:?}/filestore/${PGDATABASE}"
    q "INSERT INTO id_meta.reset_log(token) VALUES ('${tok}')"
  fi
fi

# 4. Restore dump ATAU build penuh (hanya sekali; dilewati bila mark ada)
restore_seed() {
  local sql
  sql="$(ls /opt/deploy/seed/*.sql.gz 2>/dev/null | head -1 || true)"
  if [ -z "$sql" ] && [ -n "${SEED_URL:-}" ]; then
    : "${SEED_SHA256:?SEED_SHA256 wajib bila SEED_URL dipakai}"
    curl -fsSL "$SEED_URL" -o /tmp/seed.sql.gz
    echo "${SEED_SHA256}  /tmp/seed.sql.gz" | sha256sum -c -
    sql=/tmp/seed.sql.gz
    if [ -n "${SEED_FILESTORE_URL:-}" ]; then
      : "${SEED_FILESTORE_SHA256:?SEED_FILESTORE_SHA256 wajib}"
      curl -fsSL "$SEED_FILESTORE_URL" -o /tmp/filestore.tgz
      echo "${SEED_FILESTORE_SHA256}  /tmp/filestore.tgz" | sha256sum -c -
      mkdir -p "$DATA_DIR/filestore"; tar -xzf /tmp/filestore.tgz -C "$DATA_DIR/filestore"
    fi
  fi
  [ -n "$sql" ] || return 1
  log "restore dari $sql"
  # dump dibuat dengan --no-owner --no-acl; PGOPTIONS membuat objek dimiliki peran Odoo
  gunzip -c "$sql" | PGOPTIONS="-c role=${ODOO_DB_USER}" psql -v ON_ERROR_STOP=1 -q
}

if ! has_mark init.base; then
  if restore_seed; then
    set_mark init.restored
  else
    log "tanpa dump: build penuh (base -> perusahaan ID/IDR -> ${INIT_MODULES})"
    # Negara Indonesia harus diatur SEBELUM modul akuntansi terinstal; kalau tidak, COA generik (US, pajak 15%) termuat.
    odoo_run -i base --stop-after-init
    odoo_run shell --no-http <<'PYEOF'
c = env.company
c.country_id = env.ref('base.id')
env.ref('base.IDR').active = True
c.currency_id = env.ref('base.IDR')
c.name = 'PT Manado Distribusi Utama'
env.cr.commit()
PYEOF
    odoo_run -i "$INIT_MODULES" --stop-after-init
  fi
  set_mark init.base
else
  log "init.base sudah ada; lewati"
fi

# 4b. Sinkronisasi & pembaruan modul (idempoten: memastikan kolom model baru seperti res_partner.channel_id terbuat di DB)
if ! has_mark upgrade_modules_v3 || [ "${FORCE_UPGRADE:-0}" = "1" ]; then
  log "upgrade_modules_v3: mengupdate dan menginstal modul ${INIT_MODULES}..."
  odoo_run -i "$INIT_MODULES" -u "$INIT_MODULES" --stop-after-init
  set_mark upgrade_modules_v3
fi

# 5. Postinit (v1): URL dasar, kata sandi admin, bahasa. TODO M1: aktifkan id_ID, grup bisnis admin.
if ! has_mark postinit_v1; then
  log "postinit_v1"
  odoo_run shell --no-http <<'PY'
import os
icp = env['ir.config_parameter'].sudo()
base = os.environ.get('BASE_URL')
if base:
    icp.set_param('web.base.url', base)
    icp.set_param('web.base.url.freeze', 'True')
pw = os.environ.get('ADMIN_LOGIN_PASSWORD')
if pw:
    env.ref('base.user_admin').password = pw
env.cr.commit()
PY
  set_mark postinit_v1
fi

# 5a. Profil Perusahaan & Jadwal Kerja 5 Hari
if ! has_mark company_profile_v2; then
  log "company_profile_v2: konfigurasi PT Manado Distribusi Utama & Jadwal Kerja..."
  odoo_run shell --no-http <<'PY'
try:
    c = env.company.sudo().with_context(no_vat_validation=True, tracking_disable=True)
    c.write({
        'name': 'PT Manado Distribusi Utama',
        'street': 'Jl. AA Maramis No. 88, Interchange Maumbi',
        'city': 'Manado',
        'zip': '95371',
        'phone': '0431-889900',
        'email': 'info@mdu-manado.co.id',
    })
    if c.partner_id:
        c.partner_id.with_context(no_vat_validation=True, tracking_disable=True).write({
            'name': 'PT Manado Distribusi Utama',
            'street': 'Jl. AA Maramis No. 88, Interchange Maumbi',
            'city': 'Manado',
            'zip': '95371',
            'phone': '0431-889900',
            'email': 'info@mdu-manado.co.id',
            'vat': '012345678821000',
        })
    indonesia = env.ref('base.id', raise_if_not_found=False)
    if indonesia:
        c.country_id = indonesia
    idr = env.ref('base.IDR', raise_if_not_found=False)
    if idr:
        idr.active = True
        c.currency_id = idr

    # Kalender Kerja 5 Hari (Senin - Jumat 08:00-17:00, Sabtu-Minggu libur)
    if 'resource.calendar' in env:
        Calendar = env['resource.calendar'].sudo()
        cal = env.ref('resource.resource_calendar_std', raise_if_not_found=False) or Calendar.search([], limit=1)
        if cal:
            cal.name = 'Standard 40 Jam (Senin - Jumat, 08:00 - 17:00)'
            cal.attendance_ids.filtered(lambda a: a.dayofweek in ('5', '6')).unlink()

    env.cr.commit()
    print("[init] company_profile_v2: berhasil dikonfigurasi.")
except Exception as e:
    env.cr.rollback()
    print(f"[init] warning: company_profile_v2 error: {e}")
PY
  set_mark company_profile_v2
fi

# 5b. Master Seed FMCG (150 SKU, 354 Outlet, Vendor, Armada, Roster)
if ! has_mark seed_master_v4; then
  if [ -f "/opt/scripts/load_fmcg_seed.py" ]; then
    log "seed_master_v4: memuat master seed FMCG setelah modul id_base terpasang..."
    if odoo_run shell --no-http < /opt/scripts/load_fmcg_seed.py; then
      set_mark seed_master_v4
      log "seed_master_v4: berhasil dimuat dan ditandai."
    else
      log "seed_master_v4 error: pemuatan gagal, mark tidak diset agar dapat diulang pada boot berikutnya."
    fi
  fi
fi

# 6. Jalankan Odoo (hemat RAM untuk Railway Hobby; sesuaikan lewat env)
log "menjalankan Odoo"
exec env PGUSER="$ODOO_DB_USER" PGPASSWORD="$ODOO_DB_PASSWORD" \
  odoo -c /tmp/odoo.conf -d "$PGDATABASE" --db_host "$PGHOST" --db_port "$PGPORT" \
       --addons-path "$(/opt/deploy/addons_path.sh)" --data-dir "$DATA_DIR" --without-demo=true \
       --http-port "${PORT:-8069}" --proxy-mode --no-database-list --db-filter "^${PGDATABASE}\$" \
       --workers "${ODOO_WORKERS:-0}" --max-cron-threads "${ODOO_MAX_CRON:-1}"
