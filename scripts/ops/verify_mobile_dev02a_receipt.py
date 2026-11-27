"""Read-only ledger checkpoint for DEV-02A, run through Odoo shell on the fixture DB."""
import json
import os
from uuid import UUID


def read_checkpoint(env, *, database, disposable, uuid):
    if not env.su or disposable != "YES" or database != env.cr.dbname or not database.startswith("fmcg_staging_"):
        raise ValueError("Use the explicitly bound disposable fixture database.")
    parsed = UUID(uuid)
    if parsed.version != 4 or str(parsed) != uuid:
        raise ValueError("A canonical UUIDv4 is required.")
    fixture = "id_mobile_api_staging."
    company = env.ref(fixture + "company")
    user = env.ref(fixture + "user_1")
    outlet = env.ref(fixture + "outlet_1")
    product = env.ref(fixture + "product")
    if user.company_ids != company or outlet.company_id != company or product.company_id != company:
        raise ValueError("Fixture ownership does not match.")
    ledger = env["id.mobile.command"]
    orders = env["sale.order"].search([("company_id", "=", company.id)], order="id")
    rows = ledger.search([("client_uuid", "=", uuid)], order="id")
    approvals = env.registry.get("fmcg.approval.request")
    approvals = env["fmcg.approval.request"].search([
        ("res_model", "=", "sale.order"), ("res_id", "in", orders.ids),
    ], order="id") if approvals is not None else []
    return {
        "fixture": "id_mobile_api_staging",
        "uuid": uuid,
        "user_id": str(user.id),
        "company_id": str(company.id),
        "outlet_id": str(outlet.id),
        "product_id": str(product.id),
        "company_command_count": ledger.search_count([("company_id", "=", company.id)]),
        "approvals": [{"id": row.id, "write_date": str(row.write_date)} for row in approvals],
        "ledger": [{
            "id": row.id,
            "user_id": str(row.user_id.id),
            "company_id": str(row.company_id.id),
            "type": row.command_type,
            "client_uuid": row.client_uuid,
            "status": row.status,
            "reference": row.reference,
            "fingerprint": row.fingerprint,
            "write_date": str(row.write_date),
            "sale_order_ids": row.sale_order_ids.ids,
        } for row in rows],
        "orders": [{
            "id": order.id,
            "company_id": str(order.company_id.id),
            "user_id": str(order.user_id.id),
            "outlet_id": str(order.partner_id.id),
            "reference": order.name,
            "state": order.state,
            "write_date": str(order.write_date),
            "picking_ids": sorted(order.picking_ids.ids),
            "invoice_ids": sorted(order.invoice_ids.ids),
            "lines": [
                {"id": line.id, "product_id": str(line.product_id.id), "qty": line.product_uom_qty,
                 "write_date": str(line.write_date)}
                for line in order.order_line
            ],
        } for order in orders],
    }


if "env" in globals():
    result = read_checkpoint(
        env,  # noqa: F821
        database=os.environ["FMCG_STAGING_DATABASE"],
        disposable=os.environ.get("FMCG_STAGING_DISPOSABLE"),
        uuid=os.environ["DEV02A_UUID"],
    )
    print(json.dumps(result, sort_keys=True))
