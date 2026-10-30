"""Read-only Odoo-shell inventory. No install, seed, reset or credential output."""

# ruff: noqa: F821
import json
import os

module = env["ir.module.module"].sudo().search([("name", "=", "id_mobile_api")], limit=1)
models = (
    "res.company",
    "res.users",
    "res.partner",
    "product.product",
    "sale.order",
    "stock.picking",
    "stock.quant",
    "account.move",
    "account.move.line",
    "ir.attachment",
)
print(
    "MOBILE_DEMO_PREFLIGHT="
    + json.dumps(
        {
            "database": env.cr.dbname,
            "runtime": {
                key: os.environ.get(key)
                for key in ("RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_ID", "RAILWAY_SERVICE_ID")
            },
            "mobile_module": {
                "state": module.state if module else "not_listed",
                "installed_version": module.installed_version if module else None,
            },
            "counts": {
                model: env[model].sudo().with_context(active_test=False).search_count([])
                for model in models
                if model in env
            },
            "filestore": env["ir.attachment"]._filestore(),
        },
        sort_keys=True,
    )
)
