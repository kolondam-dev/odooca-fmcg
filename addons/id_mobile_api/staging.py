"""Explicit disposable-fixture provisioning, called from Odoo shell, never HTTP."""

from odoo import Command
from odoo.exceptions import AccessError, ValidationError

from .models.mobile_workday import business_date


def provision(env, *, expected_database, disposable, passwords):
    # Independent opt-in and exact database binding; refuse a production/renamed DB.
    if (
        not env.su
        or disposable != "YES"
        or env.cr.dbname != expected_database
        or not expected_database.startswith("fmcg_staging_")
        or len(passwords) != 2
        or any(not isinstance(p, str) or len(p) < 12 for p in passwords)
        or passwords[0] == passwords[1]
    ):
        raise AccessError("Disposable staging database and two distinct test passwords are required.")
    with env.cr.savepoint():
        result = _provision_records(env, passwords=passwords)
    return result


def _provision_records(env, *, passwords):
    """Private implementation; exported provision() enforces the shell/DB guards."""
    day = business_date()
    Data = env["ir.model.data"].sudo()

    def owned(key, model, values):
        marker = Data.search([("module", "=", "id_mobile_api_staging"), ("name", "=", key)], limit=1)
        if marker:
            if marker.model != model or not env[model].browse(marker.res_id).exists():
                raise ValidationError("Staging fixture ownership is inconsistent.")
            record = env[model].with_context(no_reset_password=True, tracking_disable=True).browse(marker.res_id)
            record.write(values)
        else:
            record = env[model].with_context(no_reset_password=True, tracking_disable=True).create(values)
            Data.create(
                {"module": "id_mobile_api_staging", "name": key, "model": model, "res_id": record.id, "noupdate": True}
            )
        return record

    # No canonical company, SKU, partner or assignment is modified.
    currency = env.ref("base.IDR")
    if not currency.active:
        raise ValidationError("Activate IDR before provisioning this disposable database.")
    company = owned("company", "res.company", {"name": "STAGING TEST Company", "currency_id": currency.id})
    warehouse = env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
    if not warehouse:
        warehouse = owned(
            "warehouse", "stock.warehouse", {"name": "STAGING TEST Warehouse", "code": "STGT", "company_id": company.id}
        )
    pricelist = owned(
        "pricelist",
        "product.pricelist",
        {"name": "STAGING TEST IDR", "currency_id": currency.id, "company_id": company.id},
    )
    principal = owned("principal", "id.principal", {"name": "STAGING TEST Principal", "code": "STG-ACCEPTANCE"})
    product = owned(
        "product",
        "product.product",
        {
            "name": "STAGING TEST Product",
            "default_code": "STG-ACCEPTANCE-SKU",
            "company_id": company.id,
            "principal_id": principal.id,
            "uom_id": env.ref("uom.product_uom_unit").id,
            "carton_qty": 24,
            "inner_qty": 6,
            "list_price": 1000,
            "type": "consu",
            "sale_ok": True,
            "taxes_id": [Command.clear()],
        },
    )
    office = owned(
        "office",
        "id.mobile.office",
        {
            "name": "STAGING TEST Office",
            "company_id": company.id,
            "latitude": 1.465,
            "longitude": 124.833,
            "radius": 50,
            "coordinate_status": "test",
            "coordinate_note": "Disposable acceptance fixture; not surveyed office coordinates.",
        },
    )
    summary = []
    for index, password in enumerate(passwords, 1):
        login = f"staging.capture.{index}"
        marker = Data.search([("module", "=", "id_mobile_api_staging"), ("name", "=", f"user_{index}")], limit=1)
        existing = env["res.users"].with_context(active_test=False).search([("login", "=", login)])
        if existing and (not marker or existing.id != marker.res_id):
            raise ValidationError("Refusing to reset an account not owned by this fixture.")
        user = owned(
            f"user_{index}",
            "res.users",
            {
                "name": f"STAGING TEST Capture {index}",
                "login": login,
                "password": password,
                "active": True,
                "company_ids": [Command.set([company.id])],
                "company_id": company.id,
                "group_ids": [
                    Command.set([env.ref("base.group_user").id, env.ref("id_mobile_api.group_mobile_evidence").id])
                ],
            },
        )
        outlet = owned(
            f"outlet_{index}",
            "res.partner",
            {
                "name": f"STAGING TEST Outlet {index}",
                "company_id": company.id,
                "user_id": user.id,
                "partner_latitude": 1.465 + index * 0.001,
                "partner_longitude": 124.833,
                "street": "Disposable test coordinates",
            },
        )
        assignment = owned(
            f"assignment_{index}_{day.isoformat()}",
            "id.mobile.workday",
            {
                "user_id": user.id,
                "company_id": company.id,
                "business_date": day,
                "active": True,
                "warehouse_id": warehouse.id,
                "pricelist_id": pricelist.id,
                "office_id": office.id,
                "outlet_ids": [Command.set(outlet.ids)],
                "product_ids": [Command.set(product.ids)],
                "outlet_radius": 10,
            },
        )
        service = env["id.mobile.workday"].with_user(user).with_context(allowed_company_ids=[company.id])
        service._bootstrap_payload()
        snapshot = service._snapshot_payload()
        summary.append(
            {
                "login": login,
                "user_id": user.id,
                "company_id": company.id,
                "assignment_id": assignment.id,
                "business_date": day.isoformat(),
                "office_id": office.id,
                "outlet_id": outlet.id,
                "snapshot_version": snapshot["version"],
            }
        )
    env["id.mobile.workday"]._assert_day(day)
    return summary
