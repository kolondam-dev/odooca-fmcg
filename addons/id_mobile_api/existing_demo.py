"""Explicit existing-demo provisioning. No HTTP/RPC entrypoint or reset path."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from psycopg2 import sql

from odoo import SUPERUSER_ID
from odoo.exceptions import AccessError, ValidationError

from .staging import _provision_records

TARGET = {
    "RAILWAY_PROJECT_ID": "569df00d-48e8-411a-93a5-df39ba97f16b",
    "RAILWAY_ENVIRONMENT_ID": "47b72704-4054-4941-b978-d42c1befca55",
    "RAILWAY_SERVICE_ID": "56186eb1-eec2-4604-92d3-f449504cba4a",
}
PROTECTED = (
    "res.company",
    "res.users",
    "res.partner",
    "product.template",
    "product.product",
    "product.pricelist",
    "id.principal",
    "stock.warehouse",
    "stock.location",
    "stock.quant",
    "sale.order",
    "sale.order.line",
    "stock.picking",
    "stock.move",
    "stock.move.line",
    "account.move",
    "account.move.line",
    "ir.attachment",
    "id.mobile.office",
    "id.mobile.workday",
)
NO_NEW_TRANSACTIONS = (
    "sale.order",
    "sale.order.line",
    "stock.picking",
    "stock.move",
    "stock.move.line",
    "stock.quant",
    "account.move",
    "account.move.line",
)


def verify_backup(backup, database):
    """Check local archive identity/integrity, NOT restore readiness or consistency."""
    try:
        if backup["database"] != database or backup["target"] != TARGET:
            raise ValueError("scope")
        created = datetime.fromisoformat(backup["created_at"])
        if created.tzinfo is None or not 0 <= (datetime.now(timezone.utc) - created).total_seconds() <= 86400:
            raise ValueError("age")
        paths = []
        for key in ("database_dump", "filestore_archive"):
            entry = backup[key]
            path = Path(entry["path"])
            if not path.is_absolute() or path.is_symlink() or not path.is_file() or not path.stat().st_size:
                raise ValueError("file")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != entry["sha256"]:
                raise ValueError("hash")
            paths.append(path.resolve())
        if os.path.samefile(paths[0], paths[1]):
            raise ValueError("same archive")
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise AccessError("A matching, recent database AND filestore backup manifest is required.") from error


def _excluded(env):
    owned = {}
    for marker in env["ir.model.data"].sudo().search([("module", "=", "id_mobile_api_staging")]):
        owned.setdefault(marker.model, set()).add(marker.res_id)
    # Native related records belonging to the existing TEST fixtures may be updated.
    users = env["res.users"].browse(list(owned.get("res.users", set()))).exists()
    companies = env["res.company"].browse(list(owned.get("res.company", set()))).exists()
    products = env["product.product"].browse(list(owned.get("product.product", set()))).exists()
    owned.setdefault("res.partner", set()).update((users.partner_id | companies.partner_id).ids)
    owned.setdefault("product.template", set()).update(products.product_tmpl_id.ids)
    return owned


def fixture_company_ids(env):
    """Company IDs owned by the staging fixture module, including an existing TEST company."""
    return _excluded(env).get("res.company", set())


def _raw_model_snapshot(env, model):
    """Raw rows for field-name-only diagnostics; never include business values in errors."""
    env.flush_all()
    table = env[model]._table
    env.cr.execute(sql.SQL("SELECT id, to_jsonb(t) FROM {} t ORDER BY id").format(sql.Identifier(table)))
    return {row_id: payload for row_id, payload in env.cr.fetchall()}


def _partner_company_property_snapshot(env):
    """Raw company-dependent stock properties and audit metadata, keyed by partner."""
    env.flush_all()
    env.cr.execute(
        "SELECT id, COALESCE(property_stock_customer, '{}'::jsonb), "
        "COALESCE(property_stock_supplier, '{}'::jsonb), write_uid, write_date "
        "FROM res_partner ORDER BY id"
    )
    result = {}
    for partner_id, customer, supplier, write_uid, write_date in env.cr.fetchall():
        if isinstance(customer, str):
            customer = json.loads(customer)
        if isinstance(supplier, str):
            supplier = json.loads(supplier)
        result[partner_id] = {
            "property_stock_customer": dict(customer or {}),
            "property_stock_supplier": dict(supplier or {}),
            "write_uid": write_uid,
            "write_date": write_date,
        }
    return result


def _existing_company_partner_ids(env, company_ids):
    return set(env["res.company"].browse(list(company_ids)).exists().mapped("partner_id").ids)


def protected_snapshot(env, *, normalize_company_property_company_ids=(), normalize_partner_audit_ids=()):
    if not env.su:
        raise AccessError("Only the operator shell may inspect the preservation baseline.")
    env.flush_all()
    excluded = _excluded(env)
    normalized_company_ids = {str(company_id) for company_id in normalize_company_property_company_ids}
    normalized_partner_audit_ids = set(normalize_partner_audit_ids)
    result = {}
    for model in PROTECTED:
        if model not in env:
            continue
        table = env[model]._table
        if model in ("res.users", "res.partner"):
            # Native res.company.create links the new company to its operator
            # and SUPERUSER_ID. Preserve their real audit timestamp; verify the
            # exact additive company/group change separately below.
            audit_ids = [env.uid, SUPERUSER_ID]
            if model == "res.partner":
                audit_ids = list(
                    set(env["res.users"].browse(audit_ids).partner_id.ids) | normalized_partner_audit_ids
                )
            env.cr.execute(
                sql.SQL(
                    "SELECT id, (CASE WHEN id = ANY(%s) THEN to_jsonb(t) - 'write_date' - 'write_uid' "
                    "ELSE to_jsonb(t) END)::text FROM {} t ORDER BY id"
                ).format(sql.Identifier(table)),
                (audit_ids,),
            )
        else:
            env.cr.execute(sql.SQL("SELECT id, to_jsonb(t)::text FROM {} t ORDER BY id").format(sql.Identifier(table)))
        rows = {}
        for row_id, value in env.cr.fetchall():
            if row_id in excluded.get(model, set()):
                continue
            if model == "res.partner":
                payload = json.loads(value)
                for field_name in ("property_stock_customer", "property_stock_supplier"):
                    company_values = payload.get(field_name)
                    if isinstance(company_values, dict):
                        for company_id in normalized_company_ids:
                            company_values.pop(company_id, None)
                value = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            rows[row_id] = hashlib.sha256(value.encode()).hexdigest()
        result[model] = rows
    return result


def _assert_partner_company_properties_preserved(env, before, existing_company_ids):
    after = _partner_company_property_snapshot(env)
    fixture_ids = fixture_company_ids(env)
    newly_created_fixture_ids = fixture_ids - set(existing_company_ids)
    newly_created_fixture_keys = {str(company_id) for company_id in newly_created_fixture_ids}
    if len(newly_created_fixture_ids) > 1:
        raise ValidationError("Unexpected TEST company creation; provisioning was rolled back.")

    existing_company_partners = _existing_company_partner_ids(env, existing_company_ids)
    inter_company_location_id = env.ref("stock.stock_location_inter_company").id
    fields = ("property_stock_customer", "property_stock_supplier")
    partners_with_expected_property_additions = set()

    for partner_id, old_fields in before.items():
        new_fields = after.get(partner_id)
        if new_fields is None:
            raise ValidationError("Existing partner row disappeared; provisioning was rolled back.")
        for field_name in fields:
            old_values = old_fields[field_name]
            new_values = new_fields[field_name]
            if any(
                company_id not in new_values or new_values[company_id] != value
                for company_id, value in old_values.items()
            ):
                raise ValidationError(
                    f"Existing company value changed in res.partner.{field_name}; provisioning was rolled back."
                )
            added_company_ids = set(new_values) - set(old_values)
            if added_company_ids:
                if (
                    partner_id not in existing_company_partners
                    or not added_company_ids <= newly_created_fixture_keys
                    or any(new_values[company_id] != inter_company_location_id for company_id in added_company_ids)
                ):
                    raise ValidationError(
                        f"Unexpected company-dependent value added in res.partner.{field_name}; "
                        "provisioning was rolled back."
                    )
                partners_with_expected_property_additions.add(partner_id)

        old_audit = (old_fields["write_uid"], old_fields["write_date"])
        new_audit = (new_fields["write_uid"], new_fields["write_date"])
        if old_audit != new_audit and (
            partner_id not in existing_company_partners
            or partner_id not in partners_with_expected_property_additions
            or new_audit[0] != env.uid
            or not new_audit[1]
            or (old_audit[1] and new_audit[1] < old_audit[1])
        ):
            raise ValidationError("Unexpected existing partner audit change; provisioning was rolled back.")


def _assert_preserved(env, before, partner_properties_before, existing_company_ids, stock_location_before):
    _assert_partner_company_properties_preserved(env, partner_properties_before, existing_company_ids)
    newly_created_fixture_ids = fixture_company_ids(env) - set(existing_company_ids)
    existing_company_partners = _existing_company_partner_ids(env, existing_company_ids)
    after = protected_snapshot(
        env,
        normalize_company_property_company_ids=newly_created_fixture_ids,
        normalize_partner_audit_ids=existing_company_partners,
    )
    for model, rows in before.items():
        if any(after[model].get(row_id) != digest for row_id, digest in rows.items()):
            if model == "stock.location":
                location_after = _raw_model_snapshot(env, "stock.location")
                changes = []
                for row_id, old_row in stock_location_before.items():
                    new_row = location_after.get(row_id)
                    if new_row is None:
                        changes.append(f"{row_id}:deleted")
                        continue
                    changed_fields = sorted(
                        key for key in set(old_row) | set(new_row) if old_row.get(key) != new_row.get(key)
                    )
                    if changed_fields:
                        changes.append(f"{row_id}:{','.join(changed_fields)}")
                detail = "; ".join(changes[:20]) or "unidentified"
                raise ValidationError(
                    f"Non-fixture records changed in stock.location ({detail}); provisioning was rolled back."
                )
            raise ValidationError(f"Non-fixture records changed in {model}; provisioning was rolled back.")
        if model in NO_NEW_TRANSACTIONS and after[model] != rows:
            raise ValidationError(f"Provisioning created transactions in {model}; changes were rolled back.")


def _user_scope(env):
    return {
        user.id: {
            "companies": set(user.company_ids.ids),
            "groups": set(user.group_ids.ids),
            "audit": (user.write_uid.id, user.write_date),
            "partner_audit": (user.partner_id.write_uid.id, user.partner_id.write_date),
        }
        for user in env["res.users"].with_context(active_test=False).search([])
    }


def _assert_user_scope(env, before, accounts):
    after = _user_scope(env)
    if set(after) != set(before) | {item["user_id"] for item in accounts}:
        raise ValidationError("Unexpected user creation; provisioning was rolled back.")
    companies = {item["company_id"] for item in accounts}
    multi = env.ref("base.group_multi_company").id
    for user_id, old in before.items():
        # Fixture accounts are checked by the existing minimal-group builder.
        if user_id in {item["user_id"] for item in accounts}:
            continue
        if user_id in (env.uid, SUPERUSER_ID):
            if after[user_id]["companies"] != old["companies"] | companies or not old["groups"] <= after[user_id][
                "groups"
            ] <= old["groups"] | {multi}:
                raise ValidationError("Unexpected operator scope change; provisioning was rolled back.")
            for field in ("audit", "partner_audit"):
                writer, at = after[user_id][field]
                if after[user_id][field] != old[field] and (
                    writer != env.uid or not at or (old[field][1] and at < old[field][1])
                ):
                    raise ValidationError("Unexpected operator audit metadata; provisioning was rolled back.")
        elif after[user_id] != old:
            raise ValidationError("Existing user access changed; provisioning was rolled back.")


def provision_existing_demo(env, *, expected_database, opt_in, backup, passwords):
    if (
        not env.su
        or opt_in != "PRESERVE_EXISTING_DEMO"
        or not expected_database
        or env.cr.dbname != expected_database
        or os.environ.get("PGDATABASE") != expected_database
        or any(os.environ.get(key) != value for key, value in TARGET.items())
        or len(passwords) != 2
        or any(not isinstance(p, str) or len(p) < 12 for p in passwords)
        or passwords[0] == passwords[1]
    ):
        raise AccessError("Exact Railway demo target, database, opt-in and distinct test passwords are required.")
    verify_backup(backup, expected_database)
    with env.cr.savepoint():
        # Serialize writes to the preservation tables for this short operator
        # transaction. Reads remain available; competing writers cause a bounded
        # lock timeout instead of silently invalidating the before/after proof.
        env.flush_all()
        env.cr.execute("SET LOCAL lock_timeout = '5s'")
        tables = sorted({env[model]._table for model in PROTECTED if model in env})
        env.cr.execute(
            sql.SQL("LOCK TABLE {} IN SHARE MODE").format(sql.SQL(", ").join(sql.Identifier(table) for table in tables))
        )
        existing_company_ids = set(env["res.company"].search([]).ids)
        existing_company_partners = _existing_company_partner_ids(env, existing_company_ids)
        before = protected_snapshot(env, normalize_partner_audit_ids=existing_company_partners)
        stock_location_before = _raw_model_snapshot(env, "stock.location")
        partner_properties_before = _partner_company_property_snapshot(env)
        scopes = _user_scope(env)
        accounts = _provision_records(env, passwords=passwords)
        _assert_preserved(
            env, before, partner_properties_before, existing_company_ids, stock_location_before
        )
        _assert_user_scope(env, scopes, accounts)
        after_scopes = _user_scope(env)
        operator_changes = [
            {
                "user_id": uid,
                "added_company_ids": sorted(after_scopes[uid]["companies"] - scopes[uid]["companies"]),
                "added_group_ids": sorted(after_scopes[uid]["groups"] - scopes[uid]["groups"]),
            }
            for uid in sorted({env.uid, SUPERUSER_ID})
        ]
        digest = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
    return {
        "database": expected_database,
        "mode": "existing-demo-preserve",
        "accounts": accounts,
        "protected_baseline_sha256": digest,
        "protected_models": sorted(before),
        "native_operator_scope_changes": operator_changes,
    }
