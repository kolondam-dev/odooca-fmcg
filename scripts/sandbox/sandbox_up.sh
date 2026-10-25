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
# user `odoo` seperti image resmi: init.sh mulai sebagai root, chown $DATA_DIR, lalu turun ke odoo (gosu/runuser/su)
id odoo >/dev/null 2>&1 || useradd -r -m -d /var/lib/odoo -U -s /bin/bash odoo
# salinan (bukan symlink): user odoo tidak boleh bergantung pada izin /home/claude
mkdir -p /opt/id-addons && rsync -a --delete /home/claude/scaffold/addons/ /opt/id-addons/ 2>/dev/null || { rm -rf /opt/id-addons && cp -a /home/claude/scaffold/addons /opt/id-addons; }
# meniru Dockerfile: COPY data /opt/data dan scripts /opt/scripts (loader seed dipanggil init.sh dari /opt/scripts)
mkdir -p /opt/data /opt/scripts
rsync -a --delete /home/claude/scaffold/data/ /opt/data/ 2>/dev/null || { rm -rf /opt/data && cp -a /home/claude/scaffold/data /opt/data; }
rsync -a --delete /home/claude/scaffold/scripts/ /opt/scripts/ 2>/dev/null || { rm -rf /opt/scripts && cp -a /home/claude/scaffold/scripts /opt/scripts; }
chown -R odoo:odoo /opt/data /opt/scripts /opt/id-addons 2>/dev/null || true
rm -f /tmp/odoo.conf   # sisa dari proses root sebelumnya tidak boleh menghalangi user odoo
mkdir -p /opt/deploy && cp /home/claude/scaffold/deploy/*.sh /opt/deploy/ && chmod +x /opt/deploy/*.sh
pg_lsclusters | tail -1
