#!/usr/bin/env bash
# Menghidupkan lingkungan Odoo di SANDBOX AGEN (tanpa Docker). Jalankan di awal SETIAP sesi/giliran:
# proses latar belakang (Postgres, Odoo) dimatikan di batas giliran; berkas dan data DB tetap ada.
# Prasyarat satu kali: lihat docs/SANDBOX.md.
set -euo pipefail
pg_lsclusters | grep -q " online " || { pg_ctlcluster 16 main start; sleep 4; }
su postgres -c "psql -qc \"ALTER ROLE postgres PASSWORD 'pgadmin-sandbox'\"" >/dev/null
su postgres -c "psql -qtAc \"select 1 from pg_roles where rolname='odoo'\"" | grep -q 1 || \
  su postgres -c "psql -qc \"CREATE ROLE odoo LOGIN CREATEDB PASSWORD 'odoo'\""
# wrapper `odoo` meniru image resmi: menambahkan addons inti ke --addons-path
cat > /usr/local/bin/odoo <<'WRAP'
#!/usr/bin/env bash
args=(); while [ $# -gt 0 ]; do
  if [ "$1" = "--addons-path" ]; then args+=("--addons-path" "/opt/odoo/addons,$2"); shift 2; else args+=("$1"); shift; fi
done
exec /opt/venv/bin/python /opt/odoo/odoo-bin "${args[@]}"
WRAP
chmod +x /usr/local/bin/odoo
ln -sfn /home/claude/scaffold/addons /opt/id-addons
mkdir -p /opt/deploy && cp /home/claude/scaffold/deploy/*.sh /opt/deploy/ && chmod +x /opt/deploy/*.sh
pg_lsclusters | tail -1
