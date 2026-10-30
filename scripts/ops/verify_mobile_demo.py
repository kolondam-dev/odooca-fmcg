"""CI-only exact-target simulation on an existing-data database clone."""

# ruff: noqa: F821
import base64
import hashlib
import json
import os
import runpy
import secrets
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from odoo.addons.id_mobile_api.existing_demo import TARGET, protected_snapshot

if env.cr.dbname != "fmcg_demo_acceptance" or not env.su:  # noqa: F821
    raise RuntimeError("CI clone required; never execute this verifier on Railway")
env.ref("base.IDR").active = True  # noqa: F821
partner = env["res.partner"].create({"name": "EXISTING preserve contact", "street": "Original address"})  # noqa: F821
attachment = env["ir.attachment"].create(
    {  # noqa: F821
        "name": "Existing preservation sentinel",
        "res_model": "res.partner",
        "res_id": partner.id,
        "datas": base64.b64encode(b"existing filestore content"),
    }
)
env["sale.order"].create({"partner_id": partner.id})  # noqa: F821
env.cr.commit()  # noqa: F821
before = protected_snapshot(env)  # noqa: F821
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    dump = root / "database.dump"
    subprocess.run(
        ["pg_dump", "-h", "localhost", "-p", "5432", "-U", "odoo", "-Fc", "-f", str(dump), env.cr.dbname],
        check=True,
        env={**os.environ, "PGPASSWORD": "odoo"},
    )  # noqa: F821
    subprocess.run(["pg_restore", "--list", str(dump)], check=True, stdout=subprocess.DEVNULL)
    archive = root / "filestore.tar.gz"
    filestore = Path(env["ir.attachment"]._filestore())  # noqa: F821
    with tarfile.open(archive, "w:gz") as target:
        target.add(filestore, arcname=env.cr.dbname)  # noqa: F821
    manifest = {
        "database": env.cr.dbname,
        "target": TARGET,  # noqa: F821
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    for key, path in (("database_dump", dump), ("filestore_archive", archive)):
        manifest[key] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest_path = root / "backup.json"
    manifest_path.write_text(json.dumps(manifest))
    runtime = {
        **TARGET,
        "PGDATABASE": env.cr.dbname,
        "FMCG_DEMO_DATABASE": env.cr.dbname,  # noqa: F821
        "FMCG_DEMO_OPT_IN": "PRESERVE_EXISTING_DEMO",
        "FMCG_DEMO_BACKUP_MANIFEST": str(manifest_path),
        "FMCG_DEMO_PASSWORD_1": secrets.token_urlsafe(24),
        "FMCG_DEMO_PASSWORD_2": secrets.token_urlsafe(24),
    }
    with patch.dict(os.environ, runtime):
        for _attempt in range(2):
            runpy.run_path("/opt/scripts/ops/provision_mobile_demo.py", init_globals={"env": env})  # noqa: F821
            after = protected_snapshot(env)  # noqa: F821
            assert all(
                after[model].get(row_id) == digest for model, rows in before.items() for row_id, digest in rows.items()
            )
            assert base64.b64decode(attachment.datas) == b"existing filestore content"
print("EXISTING_DEMO_PROVISION=PASS (real dump/archive, operator entrypoint twice, old rows/file preserved)")
