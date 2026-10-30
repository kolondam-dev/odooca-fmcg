"""CI-only positive-path smoke on a separately cloned disposable database."""

import os
import runpy
import secrets

from odoo.exceptions import AccessError

if env.cr.dbname != "fmcg_staging_acceptance" or not env.su:  # noqa: F821
    raise AccessError("This smoke requires the dedicated CI staging database.")
os.environ["FMCG_STAGING_DATABASE"] = env.cr.dbname  # noqa: F821
os.environ["FMCG_STAGING_DISPOSABLE"] = "YES"
for number in (1, 2):
    os.environ[f"FMCG_STAGING_PASSWORD_{number}"] = secrets.token_urlsafe(24)
# CI ci_db does not install l10n_id; prepare only its isolated staging clone.
env.ref("base.IDR").active = True  # noqa: F821
env.cr.commit()  # noqa: F821
previous = None
for _attempt in range(2):
    # Execute the operator entrypoint itself, including its guard and commit.
    runpy.run_path("/opt/scripts/ops/provision_mobile_staging.py", init_globals={"env": env})  # noqa: F821
    users = env["res.users"].search([("login", "in", ["staging.capture.1", "staging.capture.2"])])  # noqa: F821
    assert len(users) == 2
    records = []
    for actor in users:
        service = env["id.mobile.workday"].with_user(actor).with_context(allowed_company_ids=actor.company_ids.ids)  # noqa: F821
        snapshot = service._snapshot_payload()
        assert snapshot["office"]["coordinate_status"] == "test"
        assert not actor.has_group("base.group_system")
        records.append((actor.id, snapshot["version"]))
    if previous is not None:
        assert previous == records, "Provisioning changed fixture identities or snapshot on replay"
    previous = records
print("STAGING_PROVISION_SMOKE=PASS (real shell, two accounts, two runs, no secrets printed)")
