#!/bin/sh
set -eu
: "${PORT:=8080}"
: "${STAGING_HOST:?public HTTPS hostname is required}"
: "${ODOO_UPSTREAM:?private Odoo host:port is required}"
: "${FIELD_UPSTREAM:?private field-pwa host:port is required}"
case "$PORT" in ''|*[!0-9]*) echo 'Invalid PORT' >&2; exit 1;; esac
test "$PORT" -ge 1 && test "$PORT" -le 65535
# Restrict values before substituting into Nginx config; never accept URL syntax.
printf '%s' "$STAGING_HOST" | grep -Eq '^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$'
for upstream in "$ODOO_UPSTREAM" "$FIELD_UPSTREAM"; do
  printf '%s' "$upstream" | grep -Eq '^[a-z0-9][a-z0-9.-]*:[0-9]{1,5}$'
done
export PORT STAGING_HOST
envsubst '${PORT} ${STAGING_HOST}' < /opt/gateway/railway-gateway.conf.template > /etc/nginx/conf.d/default.conf
# Public authority/protocol are deployment constants. Do not trust incoming
# forwarded headers (including those supplied by a client via the edge).
sed -e "s|http://field-pwa:8080|http://$FIELD_UPSTREAM|g" \
    -e "s|http://odoo:8069|http://$ODOO_UPSTREAM|g" \
    -e "s|proxy_set_header Host \$http_host;|proxy_set_header Host $STAGING_HOST;|g" \
    -e "s|proxy_set_header X-Forwarded-Host \$http_host;|proxy_set_header X-Forwarded-Host $STAGING_HOST;|g" \
    -e 's|proxy_set_header X-Forwarded-Proto $scheme;|proxy_set_header X-Forwarded-Proto https;|g' \
    /opt/gateway/staging-locations.conf > /etc/nginx/staging-locations.conf
nginx -t
exec nginx -g 'daemon off;'
