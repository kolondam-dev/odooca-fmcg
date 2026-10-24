#!/usr/bin/env bash
# Setup SATU KALI lingkungan Odoo di sandbox agen (Ubuntu 24.04, root, tanpa Docker). Disk dan /opt bertahan antar sesi.
# STATUS: disusun dari perintah yang dijalankan satu per satu pada 2026-10-23; belum dijalankan utuh sebagai satu skrip.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
ODOO_SHA="${ODOO_SHA:-f4378f29ac34c0c9668ee1769bfa93eb19b3cf5a}"   # commit odoo/odoo 19.0, 2026-10-22
REPO_DIR="${REPO_DIR:-/home/claude/scaffold}"                        # akar repo (tempat oca.lock)
apt-get update -qq
# JANGAN pasang node-less: bentrok dengan Node bawaan sandbox ("held broken packages")
apt-get install -y --no-install-recommends postgresql postgresql-client libpq-dev libldap2-dev libsasl2-dev \
  libxml2-dev libxslt1-dev python3-dev build-essential libjpeg-dev zlib1g-dev libffi-dev libssl-dev
mkdir -p /opt/odoo && cd /opt/odoo && git init -q . && git remote add origin https://github.com/odoo/odoo.git 2>/dev/null || true
git fetch -q --depth 1 origin "$ODOO_SHA" && git checkout -q FETCH_HEAD
python3 -m venv /opt/venv && /opt/venv/bin/pip install -q --upgrade pip wheel setuptools
/opt/venv/bin/pip install -q -r /opt/odoo/requirements.txt
cd "$REPO_DIR" && LOCK=oca.lock scripts/fetch_oca.sh /opt/oca
cat /opt/oca/*/requirements.txt | grep -Ev '^\s*(#|$)' | sort -u > /tmp/oca-req.txt
/opt/venv/bin/pip install -q -r /tmp/oca-req.txt && /opt/venv/bin/pip check
"$REPO_DIR/scripts/sandbox/sandbox_up.sh"
