# syntax=docker/dockerfile:1
# Tahap 1: ambil repo OCA pada SHA yang di-pin (oca.lock)
FROM ubuntu:noble AS oca
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY oca.lock /tmp/oca.lock
COPY scripts/fetch_oca.sh /tmp/fetch_oca.sh
RUN chmod +x /tmp/fetch_oca.sh && LOCK=/tmp/oca.lock /tmp/fetch_oca.sh /opt/oca

# Tahap 2: Odoo 19 (image resmi; pin digest saat build pertama berhasil, lihat docs/DEVELOPMENT.md)
FROM odoo:19.0
USER root
COPY --from=oca /opt/oca /opt/oca
RUN cat /opt/oca/*/requirements.txt 2>/dev/null | grep -Ev '^\s*(#|$)' | sort -u > /tmp/oca-req.txt \
    && pip3 install --no-cache-dir --break-system-packages --ignore-installed -r /tmp/oca-req.txt \
    && rm -f /tmp/oca-req.txt
COPY addons /opt/id-addons
# deploy/ memuat init.sh dan seed/ (dump tidak disimpan di git; lihat deploy/seed/README.md)
COPY deploy /opt/deploy
RUN chmod +x /opt/deploy/*.sh && chown -R odoo:odoo /opt/oca /opt/id-addons /opt/deploy
ENTRYPOINT ["/opt/deploy/init.sh"]
CMD []
