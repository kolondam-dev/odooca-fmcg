# Sourced by verify_dev02a_runner.sh. Resources belong exclusively to this run label.
backend_certificate() {
    openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 2 -subj /CN=Odooca-B09-Fixture \
        -addext 'basicConstraints=critical,CA:TRUE,pathlen:0' -addext 'keyUsage=critical,keyCertSign,cRLSign' \
        -keyout "$scratch/ca.key" -out "$scratch/ca.pem" > "$scratch/cert.log" 2>&1
    openssl req -new -newkey rsa:2048 -nodes -subj /CN=127.0.0.1 -keyout "$scratch/server.key" \
        -out "$scratch/server.csr" >> "$scratch/cert.log" 2>&1
    printf 'subjectAltName=IP:127.0.0.1\nextendedKeyUsage=serverAuth\n' > "$scratch/extensions"
    openssl x509 -req -in "$scratch/server.csr" -CA "$scratch/ca.pem" -CAkey "$scratch/ca.key" -CAcreateserial \
        -days 2 -sha256 -extfile "$scratch/extensions" -out "$scratch/server.pem" >> "$scratch/cert.log" 2>&1
}

b09_android_resources() {
    local res=$1
mkdir -p "$res/xml" "$res/raw"
cp "$2" "$res/raw/b09_ca.pem"
cat > "$res/xml/network_security_config.xml" <<'XML'
<network-security-config>
    <base-config cleartextTrafficPermitted="false" />
    <domain-config cleartextTrafficPermitted="false">
        <domain>127.0.0.1</domain>
        <trust-anchors><certificates src="@raw/b09_ca" /></trust-anchors>
    </domain-config>
</network-security-config>
XML
}

backend_start() {
    local pg_image odoo_image postgres_version odoo_version odoo_port deadline untrusted_status=0
    pg_image=$(docker image inspect -f '{{.Id}}' "${DEV02A_POSTGRES_IMAGE:-postgres:16}")
    odoo_image=$(docker image inspect -f '{{.Id}}' "${DEV02A_ODOO_IMAGE:-odooca-fmcg-odoo:latest}")
    printf 'postgres_image=%s\nodoo_image=%s\n' "$pg_image" "$odoo_image" >> "$metadata"
    export DEV02A_DB_PASSWORD FMCG_STAGING_PASSWORD_1 FMCG_STAGING_PASSWORD_2
    DEV02A_DB_PASSWORD=$(openssl rand -hex 24)
    FMCG_STAGING_PASSWORD_1=$(openssl rand -hex 24)
    FMCG_STAGING_PASSWORD_2=$(openssl rand -hex 24)

    backend_network=$(docker network create --label "$label" "$run")
    backend_volume=$(docker volume create --label "$label" "$run-pg")
    backend_pg=$(docker create --pull never --name "$run-pg" --label "$label" --network "$backend_network" \
        --network-alias fixture-pg --mount "type=volume,source=$backend_volume,target=/var/lib/postgresql/data" \
        -e POSTGRES_USER=odoo -e POSTGRES_DB=postgres -e "POSTGRES_PASSWORD=$DEV02A_DB_PASSWORD" "$pg_image")
    docker start "$backend_pg" >/dev/null
    deadline=$((SECONDS + 90))
    until docker exec "$backend_pg" pg_isready -q -h 127.0.0.1 -U odoo -d postgres; do
        (( SECONDS < deadline )) || return 1
        sleep 1
    done
    postgres_version=$(docker exec "$backend_pg" psql -U odoo -d postgres -Atc 'SHOW server_version')
    [[ "$postgres_version" =~ ^[[:alnum:][:space:].()+_-]+$ ]] || return 1
    printf 'postgres_version=%s\n' "$postgres_version" >> "$metadata"

    backend_odoo=$(docker create --pull never --name "$run-odoo" --label "$label" --network "$backend_network" \
        --publish 127.0.0.1::8069 --tmpfs /var/lib/odoo --tmpfs /mnt/extra-addons \
        -e FMCG_STAGING_DATABASE -e FMCG_STAGING_DISPOSABLE -e DEV02A_DB_PASSWORD \
        -e FMCG_STAGING_PASSWORD_1 -e FMCG_STAGING_PASSWORD_2 -e DEV02B_IDLE_SECONDS \
        --entrypoint bash "$odoo_image" /tmp/android/tools/dev02a_odoo.sh)
    git archive "$head" addons android/tools/dev02a_odoo.sh scripts/ops/provision_mobile_staging.py \
        scripts/ops/verify_mobile_dev02a_receipt.py | docker cp - "$backend_odoo:/tmp"
    docker start "$backend_odoo" >/dev/null
    odoo_port=$(docker port "$backend_odoo" 8069/tcp)
    [[ "$odoo_port" =~ ^127\.0\.0\.1:([0-9]+)$ ]] || return 1
    odoo_port=${BASH_REMATCH[1]}
    python3 android/tools/dev02a_tls.py "$odoo_port" "$scratch/server.pem" "$scratch/server.key" "$@" \
        > "$scratch/tls.log" 2>&1 &
    backend_tls=$!
    deadline=$((SECONDS + 480))
    until [[ "$(curl -q --noproxy 127.0.0.1 --silent --max-time 2 --cacert "$scratch/ca.pem" --write-out '%{http_code}' \
        --output /dev/null https://127.0.0.1:18443/api/v1/sync/snapshot)" == 401 ]]; do
        kill -0 "$backend_tls" && [[ "$(docker inspect -f '{{.State.Running}}' "$backend_odoo")" == true ]] \
            && (( SECONDS < deadline )) || return 1
        sleep 2
    done
    # This route consistently returns 401 before login. Prove default CA trust rejects this CA.
    curl -q --noproxy 127.0.0.1 --silent --max-time 3 https://127.0.0.1:18443/api/v1/sync/snapshot \
        >/dev/null || untrusted_status=$?
    [[ "$untrusted_status" == 60 ]] || return 1
    odoo_version=$(docker exec "$backend_odoo" dpkg-query -W -f '${Version}' odoo)
    [[ "$odoo_version" =~ ^[[:alnum:].~+:_-]+$ ]] || return 1
    printf 'odoo_version=%s\ntls_verified=passed\n' "$odoo_version" >> "$metadata"
    # Capture only installed versions from the trusted fixture script, never its output stream.
    docker logs "$backend_odoo" > "$scratch/odoo.log" 2>&1
    sed -n -E 's/^B09_ADDON (id_mobile_api|id_base|id_approval)=([0-9.]+)$/addon_\1=\2/p' \
        "$scratch/odoo.log" > "$scratch/addons"
    [[ $(sort -u "$scratch/addons" | wc -l) == 3 ]] || return 1
    cat "$scratch/addons" >> "$metadata"
}

backend_audit() {
    timeout 90 docker exec -e DEV02A_UUID "$backend_odoo" bash /tmp/android/tools/dev02a_odoo.sh audit \
        > "$scratch/odoo-audit" 2>&1
    sed -n '/^{"approvals":/p' "$scratch/odoo-audit" > "$scratch/$1.json"
    python3 - "$scratch/$1.json" <<'PY'
import json
import os
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text())
if report["uuid"] != os.environ["DEV02A_UUID"]:
    sys.exit("Odoo checkpoint belongs to a different run")
PY
}

backend_cleanup() {
    local status=0
    if [[ -n "$backend_tls" ]]; then
        if stop_owned_process "$backend_tls"; then
            cleanup_record gateway_process removed -
        else
            cleanup_record gateway_process remaining -
            status=1
        fi
        # A successful connection means the fixture port is still occupied.
        local port_status=0
        python3 -c 'import errno, socket, sys
with socket.socket() as connection:
    connection.settimeout(2)
    result = connection.connect_ex(("127.0.0.1", 18443))
sys.exit(0 if result == errno.ECONNREFUSED else 1 if result == 0 else 2)
' >/dev/null 2>&1 || port_status=$?
        case "$port_status" in
            0) cleanup_record gateway_listener removed - ;;
            1) cleanup_record gateway_listener remaining -; status=1 ;;
            *) cleanup_record gateway_listener unverified -; status=1 ;;
        esac
    else
        cleanup_record gateway_process not_started -
        cleanup_record gateway_listener not_started -
    fi
    # Always check the run label, including interrupted creates that never returned an ID.
    cleanup_docker_resource docker_containers ps -aq || status=1
    cleanup_docker_resource docker_volumes volume ls -q || status=1
    cleanup_docker_resource docker_networks network ls -q || status=1
    return "$status"
}
