#!/usr/bin/env python3
"""Read-only, aggregate finance discovery. Run inside the authorized Odoo image.

Does not load the ORM, authenticate users, or prove application ACLs. Credentials
are consumed from PG* environment variables and never included in the output.
"""

import ast
import datetime
import hashlib
import json
import os
from pathlib import Path


CANDIDATES = (
    "account", "l10n_id", "stock_account", "l10n_id_efaktur_coretax",
    "account_usability", "account_financial_report", "account_tax_balance",
    "mis_builder", "mis_builder_budget", "mis_builder_cash_flow",
    "partner_statement", "account_reconcile_oca",
    "account_statement_import_sheet_file_xlsx", "account_credit_control",
    "sale_financial_risk", "account_asset_management", "account_cutoff_base",
    "account_multicurrency_revaluation", "stock_landed_costs", "hr_expense",
    "payroll", "payroll_account",
)


def source_inventory(roots):
    """Resolve literal manifests without executing addon code; retain ambiguity."""
    index = {}
    for root in roots:
        for path in sorted(Path(root).glob("*/__manifest__.py")):
            index.setdefault(path.parent.name, []).append(path)
    result = {}

    def visit(name, stack=()):
        if name in stack:
            return
        if name in result:
            return
        paths = index.get(name, [])
        row = {"paths": [str(p) for p in paths], "status": "MISSING_SOURCE"}
        result[name] = row
        if len(paths) != 1:
            if paths:
                row["status"] = "AMBIGUOUS_SOURCE"
            return
        raw = paths[0].read_bytes()
        try:
            manifest = ast.literal_eval(raw.decode("utf-8"))
        except (ValueError, SyntaxError, UnicodeError):
            row["status"] = "UNPARSEABLE_MANIFEST"
            return
        row.update({
            "status": "MANIFEST_ONLY", "sha256": hashlib.sha256(raw).hexdigest(),
            **{key: manifest.get(key) for key in (
                "version", "license", "depends", "external_dependencies",
                "pre_init_hook", "post_init_hook", "uninstall_hook",
            )},
            "installable": manifest.get("installable", True),
        })
        for dependency in manifest.get("depends", []):
            visit(dependency, (*stack, name))

    for name in CANDIDATES:
        visit(name)
    return result


QUERIES = {
    "modules": "SELECT name,state,latest_version FROM ir_module_module ORDER BY name",
    "companies": """SELECT c.id,c.active,c.currency_id,r.name AS currency,
        c.chart_template FROM res_company c JOIN res_currency r ON r.id=c.currency_id
        ORDER BY c.id""",
    "journals": """SELECT company_id,type,count(*) AS count FROM account_journal
        GROUP BY company_id,type ORDER BY company_id,type""",
    "taxes": """SELECT company_id,type_tax_use,amount_type,active,count(*) AS count
        FROM account_tax GROUP BY company_id,type_tax_use,amount_type,active
        ORDER BY company_id,type_tax_use,amount_type,active""",
    "warehouse_counts": """SELECT company_id,count(*) AS count FROM stock_warehouse
        GROUP BY company_id ORDER BY company_id""",
    "move_counts": """SELECT company_id,state,move_type,count(*) AS count,
        min(date) AS first_date,max(date) AS last_date FROM account_move
        GROUP BY company_id,state,move_type ORDER BY company_id,state,move_type""",
    "legacy_tax_usage": """SELECT company_id,state,move_type,count(*) AS count,
        count(NULLIF(l10n_id_tax_invoice_number,'')) AS legacy_number_count,
        count(*) FILTER (WHERE l10n_id_coretax_exported) AS legacy_exported_count
        FROM account_move GROUP BY company_id,state,move_type
        ORDER BY company_id,state,move_type""",
    "account_types": """SELECT account_type,count(*) AS count FROM account_account
        GROUP BY account_type ORDER BY account_type""",
    "category_costing": """SELECT property_cost_method,property_valuation,count(*) AS count
        FROM product_category GROUP BY property_cost_method,property_valuation""",
    "finance_actions": """SELECT res_model,count(*) AS count FROM ir_act_window
        WHERE res_model LIKE 'account.%' OR res_model LIKE 'mis.%'
        OR res_model='coretax.export.wizard' GROUP BY res_model ORDER BY res_model""",
    "native_tax_fields": """SELECT model,name,ttype,relation,store FROM ir_model_fields
        WHERE model IN ('account.move','res.partner','res.company')
        AND (name LIKE 'l10n_id%' OR name LIKE '%coretax%') ORDER BY model,name""",
    "finance_model_fields": """SELECT model,name,ttype,relation,store FROM ir_model_fields
        WHERE model IN ('res.company','product.category','account.account','stock.move')
        AND (name LIKE '%cost%' OR name LIKE '%valuation%' OR name LIKE '%stock%'
             OR name LIKE '%company%' OR name LIKE '%lock%' OR name LIKE '%anglo%')
        ORDER BY model,name""",
    "finance_acl": """SELECT m.model,a.group_id,a.perm_read,a.perm_write,
        a.perm_create,a.perm_unlink,a.active FROM ir_model_access a
        JOIN ir_model m ON m.id=a.model_id
        WHERE m.model LIKE 'account.%' OR m.model LIKE 'mis.%'
        OR m.model='coretax.export.wizard' ORDER BY m.model,a.id""",
    "finance_rules": """SELECT m.model,r.active,r.global,r.perm_read,r.perm_write,
        r.perm_create,r.perm_unlink FROM ir_rule r JOIN ir_model m ON m.id=r.model_id
        WHERE m.model LIKE 'account.%' OR m.model LIKE 'mis.%' ORDER BY m.model,r.id""",
}


def collect(connection, roots):
    # A repeatable read-only transaction also prevents accidental writes introduced
    # by future query changes. Never commit and never initialize an Odoo registry.
    connection.set_session(readonly=True, isolation_level="REPEATABLE READ", autocommit=False)
    report = {
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "database aggregates; SQL metadata is not ORM ACL acceptance",
        "candidates": list(CANDIDATES), "sources": source_inventory(roots),
        "database": {}, "errors": {},
    }
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '20s'")
            cursor.execute("SHOW transaction_read_only")
            if cursor.fetchone()[0] != "on":
                raise RuntimeError("Finance inventory requires a read-only transaction")
            for name, query in QUERIES.items():
                cursor.execute("SAVEPOINT audit_section")
                try:
                    cursor.execute(query)
                    columns = [col[0] for col in cursor.description]
                    report["database"][name] = [dict(zip(columns, row)) for row in cursor.fetchall()]
                except Exception as exc:
                    cursor.execute("ROLLBACK TO SAVEPOINT audit_section")
                    # Exception text may contain business data or connection details.
                    report["errors"][name] = type(exc).__name__
                cursor.execute("RELEASE SAVEPOINT audit_section")
    finally:
        connection.rollback()
    report["status"] = "PARTIAL" if report["errors"] else "INVENTORIED_NOT_ACCEPTED"
    return report


def main():
    import psycopg2

    roots = ["/opt/id-addons", "/usr/lib/python3/dist-packages/odoo/addons"]
    roots.extend(str(path) for path in Path("/opt/oca").glob("*") if path.is_dir())
    connection = psycopg2.connect(
        host=os.environ["PGHOST"], port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ["PGDATABASE"], user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"], connect_timeout=15,
    )
    try:
        report = collect(connection, roots)
    finally:
        connection.close()
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
