"""Run only after backup + targeted addon install on the authorized demo target.

Use Odoo shell as OS user odoo, overriding PGUSER/PGPASSWORD to the Odoo role.
No init.sh/reset/seed, no credential output. A real backup manifest is mandatory.
"""

import json
import os

from odoo.addons.id_mobile_api.existing_demo import provision_existing_demo

try:
    with open(os.environ["FMCG_DEMO_BACKUP_MANIFEST"]) as stream:
        backup = json.load(stream)
    result = provision_existing_demo(
        env,  # noqa: F821
        expected_database=os.environ.get("FMCG_DEMO_DATABASE", ""),
        opt_in=os.environ.get("FMCG_DEMO_OPT_IN", ""),
        backup=backup,
        passwords=[os.environ.get("FMCG_DEMO_PASSWORD_1", ""), os.environ.get("FMCG_DEMO_PASSWORD_2", "")],
    )
    env.cr.commit()  # noqa: F821
except Exception:
    env.cr.rollback()  # noqa: F821
    raise
print(json.dumps(result, indent=2))
