"""Run via Odoo shell on the explicitly bound disposable staging DB only.

    odoo shell -c /tmp/odoo.conf -d fmcg_staging_remote --no-http < /opt/scripts/ops/provision_mobile_staging.py

Set FMCG_STAGING_DISPOSABLE=YES and FMCG_STAGING_DATABASE=fmcg_staging_remote.
Supply distinct FMCG_STAGING_PASSWORD_1/2 through the operator environment.
Neither passwords nor a credential file are printed or written by this script.
"""

import json
import os

from odoo.addons.id_mobile_api.staging import provision

try:
    result = provision(
        env,  # noqa: F821
        expected_database=os.environ.get("FMCG_STAGING_DATABASE", ""),
        disposable=os.environ.get("FMCG_STAGING_DISPOSABLE", ""),
        passwords=[os.environ.get("FMCG_STAGING_PASSWORD_1", ""), os.environ.get("FMCG_STAGING_PASSWORD_2", "")],
    )
    env.cr.commit()  # noqa: F821
except Exception:
    env.cr.rollback()  # noqa: F821
    raise
print(json.dumps({"mode": "disposable-staging", "accounts": result}, indent=2))
