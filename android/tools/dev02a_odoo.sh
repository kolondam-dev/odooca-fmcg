#!/usr/bin/env bash
set -euo pipefail
paths=$(/opt/deploy/addons_path.sh)
db=${FMCG_STAGING_DATABASE:?}
[[ "$db" =~ ^fmcg_staging_[a-f0-9]+$ && "$FMCG_STAGING_DISPOSABLE" == YES ]]
opts=(-d "$db" --db_host fixture-pg -r odoo -w "$DEV02A_DB_PASSWORD" \
    --addons-path "/tmp/addons${paths#/opt/id-addons}" --data-dir /tmp/b09-filestore)
if [[ ${1:-} == audit ]]; then
    exec odoo shell "${opts[@]}" --no-http < /tmp/scripts/ops/verify_mobile_dev02a_receipt.py
fi
odoo "${opts[@]}" --no-http --without-demo=true -i id_mobile_api,id_approval --stop-after-init
odoo shell "${opts[@]}" --no-http <<'PY'
from pathlib import Path

env.ref("base.IDR").active = True
path = Path("/tmp/scripts/ops/provision_mobile_staging.py")
exec(compile(path.read_text(), str(path), "exec"))
for name in ("id_base", "id_mobile_api", "id_approval"):
    module = env["ir.module.module"].search([("name", "=", name), ("state", "=", "installed")])
    print(f"B09_ADDON {name}={module.latest_version}")
PY
exec odoo "${opts[@]}" --proxy-mode --db-filter "^$db$" --no-database-list --http-port 8069
