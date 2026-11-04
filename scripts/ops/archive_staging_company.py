"""Archive the leftover staging company, guarded.

Why: the live database carries a second active company named
"STAGING TEST Company" with no address, no country and two test users. It is
not part of the demo, so it keeps `state_id` coverage below 100% for active
companies.

Safety rules:
  * dry-run by default; writes require ARCHIVE_COMPANY_CONFIRM=yes
  * exactly one active company must match the target name
  * the target must have no accounting, sales or stock documents
  * the target must not be the last active company
  * users of the target must look like test logins (``staging.*``) unless
    ARCHIVE_COMPANY_ALLOW_USERS=yes is set

Usage (inside the container, same wrapper as deploy/init.sh):

    env PGUSER="$ODOO_DB_USER" PGPASSWORD="$ODOO_DB_PASSWORD" \
      odoo shell -c /tmp/odoo.conf -d "$PGDATABASE" \
      --addons-path "$(/opt/deploy/addons_path.sh)" --data-dir /var/lib/odoo \
      --without-demo=true --no-http < scripts/ops/archive_staging_company.py

Environment:
    ARCHIVE_COMPANY_CONFIRM=yes   perform the archive (default: dry-run)
    ARCHIVE_COMPANY_ALLOW_USERS=yes  allow non-test logins on the target
"""

import os

TARGET_NAME = "STAGING TEST Company"
DOCUMENT_MODELS = (
    "account.move",
    "account.payment",
    "sale.order",
    "purchase.order",
    "stock.picking",
)
TEST_LOGIN_PREFIX = "staging."


def _flag(name):
    return os.environ.get(name, "").strip().lower() in {"1", "yes", "true"}


def _report(key, value):
    print(f"[archive_staging] {key}: {value}")


def _documents(company):
    counts = {}
    for model in DOCUMENT_MODELS:
        if model not in company.env.registry:
            continue
        counts[model] = company.env[model].sudo().search_count([("company_id", "=", company.id)])
    return counts


def main():
    confirm = _flag("ARCHIVE_COMPANY_CONFIRM")
    allow_users = _flag("ARCHIVE_COMPANY_ALLOW_USERS")
    env = globals().get("env")
    if env is None:  # pragma: no cover - only reachable outside odoo shell
        raise RuntimeError("[archive_staging] must run inside `odoo shell`")

    Company = env["res.company"].sudo().with_context(active_test=False)
    active = Company.search([("active", "=", True)])
    matches = active.filtered(lambda c: c.name == TARGET_NAME)

    _report("mode", "apply" if confirm else "dry-run")
    _report("active_companies", len(active))
    _report("matches", len(matches))

    if not matches:
        _report("result", "nothing to do; target already archived or absent")
        return
    if len(matches) > 1:
        raise RuntimeError(f"[archive_staging] {len(matches)} active companies named {TARGET_NAME!r}")
    if len(active) <= 1:
        raise RuntimeError("[archive_staging] refusing to archive the last active company")

    company = matches
    _report("target_id", company.id)
    _report("target_name", company.name)

    documents = _documents(company)
    _report("documents", documents)
    if any(documents.values()):
        raise RuntimeError(f"[archive_staging] target has documents: {documents}")

    users = env["res.users"].sudo().with_context(active_test=False).search([("company_id", "=", company.id)])
    logins = sorted(u.login for u in users)
    _report("users", logins)
    unexpected = [login for login in logins if not login.startswith(TEST_LOGIN_PREFIX)]
    if unexpected and not allow_users:
        raise RuntimeError(
            f"[archive_staging] non-test logins {unexpected}; set ARCHIVE_COMPANY_ALLOW_USERS=yes to override"
        )

    if not confirm:
        _report("plan", "deactivate users then archive company")
        _report("result", "dry-run; no change committed")
        return

    if users:
        # Odoo refuses to archive a company that is the default of active users.
        users.write({"active": False})
        _report("users_deactivated", logins)

    company.write({"active": False})
    env.flush_all()
    env.cr.commit()
    _report("result", "archived")
    _report("active_companies_after", Company.search_count([("active", "=", True)]))


main()
