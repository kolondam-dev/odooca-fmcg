#!/usr/bin/env python3
"""Read-only stock costing and valuation diagnostic for the I3 (HPP) spike.

Run inside an Odoo shell on the demo database:

    docker exec -i odoo /opt/deploy/init.sh shell --no-http \
        < scripts/ops/verify_finance_i3_costing.py

The diagnostic only reads. It reports, per product category, the costing method
and valuation mode, plus the valuation carried by stock moves, so the method
decision for HPP can be made on observed state instead of assumption. A category
that keeps FIFO + real_time while Odoo 19 defaults new categories to periodic
looks identical in the UI until someone reads these fields.

Odoo 19 removed the pre-19 ``stock.valuation.layer`` model: a stock move now
carries its own ``value``, ``remaining_qty`` and ``remaining_value``. The CI
run on 2026-11-15 confirmed the layer model is absent on 19, so this script
reads moves. ``stock.valuation.layer`` is still read when a database has it.

``--self-test`` exercises ``analyze`` against fixtures with no Odoo registry, so
CI can prove the aggregation logic without a database.
"""

import argparse
import json
import sys

# What the seeded demo was expected to use. This is an assumption, not a fact
# read from the database: the diagnostic reports every deviation instead of
# silently accepting it. The CI disposable database reports every category as
# Odoo 19's default (standard + periodic), so this profile must be re-checked
# against the demo database, not trusted.
DEMO_PROFILE = {"cost_method": "fifo", "valuation": "real_time"}


def analyze(data, profile=DEMO_PROFILE):
    """Turn collected rows into the diagnostic report.

    ``data`` uses plain Python values only, so the same logic runs against a
    live registry and against the self-test fixtures.
    """
    categories = data.get("categories") or []
    by_cost_method = {}
    by_valuation = {}
    deviations = []
    real_time_without_valuation = []

    for category in categories:
        cost_method = category.get("cost_method") or "unset"
        valuation = category.get("valuation") or "unset"
        by_cost_method[cost_method] = by_cost_method.get(cost_method, 0) + 1
        by_valuation[valuation] = by_valuation.get(valuation, 0) + 1
        if cost_method != profile["cost_method"] or valuation != profile["valuation"]:
            deviations.append({
                "category": category.get("name"),
                "cost_method": cost_method,
                "valuation": valuation,
            })
        if valuation == "real_time" and not category.get("valued_move_count"):
            real_time_without_valuation.append(category.get("name"))

    valuation_data = data.get("valuation") or {}
    findings = []
    if not categories:
        findings.append("No product categories were found; costing cannot be assessed.")
    if deviations:
        findings.append(
            f"{len(deviations)} of {len(categories)} categories differ from the demo profile "
            f"({profile['cost_method']} + {profile['valuation']})."
        )
    if real_time_without_valuation:
        findings.append(
            f"{len(real_time_without_valuation)} real_time categories have no valued stock move; "
            "their stock value is not evidenced yet."
        )
    if categories and not valuation_data.get("available"):
        findings.append(
            "The stock move value fields are unavailable; stock value cannot be read from this database."
        )
    if valuation_data.get("available") and valuation_data.get("negative_remaining_qty"):
        findings.append(
            f"{valuation_data['negative_remaining_qty']} stock moves end with negative remaining quantity."
        )
    if valuation_data.get("available") and valuation_data.get("zero_value_with_stock"):
        findings.append(
            f"{valuation_data['zero_value_with_stock']} stock moves keep stock at zero remaining value."
        )
    if data.get("zero_cost_products"):
        findings.append(
            f"{data['zero_cost_products']} storable products still carry a zero standard cost."
        )
    if not findings:
        findings.append("Every category matches the demo profile and the valued moves look consistent.")

    return {
        "scope": "I3 costing diagnostic only: read-only state, not FIN01-58 acceptance",
        "company": data.get("company"),
        "currency": data.get("currency"),
        "profile_is_assumption": True,
        "demo_profile": dict(profile),
        "stock_account_installed": bool(data.get("stock_account_installed")),
        "categories_total": len(categories),
        "by_cost_method": by_cost_method,
        "by_valuation": by_valuation,
        "deviations": deviations,
        "real_time_without_valuation": real_time_without_valuation,
        "valuation": valuation_data,
        "zero_cost_products": data.get("zero_cost_products", 0),
        "findings": findings,
    }


def collect(env):
    """Read the registry without writing anything."""
    company = env.company
    product_model = env["product.product"]
    category_model = env["product.category"]
    move_model = env["stock.move"] if "stock.move" in env else None
    storable_domain = [("is_storable", "=", True)] if "is_storable" in product_model._fields else []
    installed = env["ir.module.module"].search(
        [("name", "=", "stock_account"), ("state", "=", "installed")],
        limit=1,
    )

    def value(category, field, default="unset"):
        return category[field] if field in category._fields else default

    valued_domain = [("state", "=", "done"), ("value", "!=", 0)]
    # An empty recordset is falsy, so test for None explicitly.
    has_move_value = move_model is not None and "value" in move_model._fields

    categories = []
    for category in category_model.search([]):
        valued_move_count = 0
        if has_move_value:
            valued_move_count = move_model.search_count(
                valued_domain + [("product_id.categ_id", "=", category.id)]
            )
        categories.append({
            "id": category.id,
            "name": category.display_name,
            "cost_method": value(category, "property_cost_method"),
            "valuation": value(category, "property_valuation"),
            "product_count": product_model.search_count([("categ_id", "=", category.id)]),
            "valued_move_count": valued_move_count,
        })

    valuation = {"available": False, "source": None}
    if has_move_value:
        rows = move_model._read_group(valued_domain, [], ["value:sum"])
        remaining = move_model.search([("remaining_qty", "=", True)])
        negative = 0
        zero_value_with_stock = 0
        for move in remaining:
            if move.remaining_qty < 0:
                negative += 1
            elif move.remaining_value == 0:
                zero_value_with_stock += 1
        valuation = {
            "available": True,
            "source": "stock.move (Odoo 19)",
            "done_valued_moves": move_model.search_count(valued_domain),
            "value_total": rows[0][0] if rows else 0,
            "remaining_moves": len(remaining),
            "remaining_qty_total": sum(remaining.mapped("remaining_qty")),
            "remaining_value_total": sum(remaining.mapped("remaining_value")),
            "negative_remaining_qty": negative,
            "zero_value_with_stock": zero_value_with_stock,
        }
    elif "stock.valuation.layer" in env:
        layer_model = env["stock.valuation.layer"]
        rows = layer_model._read_group([], [], ["value:sum", "remaining_value:sum"])
        valuation = {
            "available": True,
            "source": "stock.valuation.layer (pre-19)",
            "done_valued_moves": layer_model.search_count([]),
            "value_total": rows[0][0] if rows else 0,
            "remaining_moves": layer_model.search_count([]),
            "remaining_qty_total": 0,
            "remaining_value_total": rows[0][1] if rows else 0,
            "negative_remaining_qty": layer_model.search_count([("remaining_qty", "<", 0)]),
            "zero_value_with_stock": layer_model.search_count([
                ("remaining_qty", ">", 0),
                ("remaining_value", "=", 0),
            ]),
        }

    zero_cost_products = 0
    if "standard_price" in product_model._fields:
        zero_cost_products = product_model.search_count(storable_domain + [("standard_price", "=", 0)])

    return {
        "company": company.display_name,
        "currency": company.currency_id.name if "currency_id" in company._fields else None,
        "stock_account_installed": bool(installed),
        "categories": categories,
        "valuation": valuation,
        "zero_cost_products": zero_cost_products,
    }


def _fixture():
    return {
        "company": "PT Manado Distribusi Utama",
        "currency": "IDR",
        "stock_account_installed": True,
        "categories": [
            {"name": "All / FIFO real time", "cost_method": "fifo", "valuation": "real_time",
             "product_count": 12, "valued_move_count": 40},
            {"name": "All / Average periodic", "cost_method": "average", "valuation": "periodic",
             "product_count": 3, "valued_move_count": 0},
            {"name": "All / FIFO periodic", "cost_method": "fifo", "valuation": "periodic",
             "product_count": 1, "valued_move_count": 0},
            {"name": "Empty real time", "cost_method": "fifo", "valuation": "real_time",
             "product_count": 0, "valued_move_count": 0},
        ],
        "valuation": {
            "available": True,
            "source": "stock.move (Odoo 19)",
            "done_valued_moves": 40,
            "value_total": 1000.0,
            "remaining_moves": 25,
            "remaining_qty_total": 60.0,
            "remaining_value_total": 250.0,
            "negative_remaining_qty": 1,
            "zero_value_with_stock": 2,
        },
        "zero_cost_products": 4,
    }


def self_test():
    report = analyze(_fixture())
    assert report["categories_total"] == 4, report
    assert report["by_cost_method"] == {"fifo": 3, "average": 1}, report
    assert report["by_valuation"] == {"real_time": 2, "periodic": 2}, report
    assert report["company"] == "PT Manado Distribusi Utama", report
    assert {row["category"] for row in report["deviations"]} == {
        "All / Average periodic", "All / FIFO periodic"}, report
    assert report["real_time_without_valuation"] == ["Empty real time"], report
    assert report["zero_cost_products"] == 4, report
    assert any("negative remaining quantity" in line for line in report["findings"]), report
    assert any("zero remaining value" in line for line in report["findings"]), report
    assert any("zero standard cost" in line for line in report["findings"]), report

    empty = analyze({})
    assert empty["categories_total"] == 0, empty
    assert empty["findings"] == [
        "No product categories were found; costing cannot be assessed."
    ], empty

    matching = analyze({
        "categories": [{"name": "A", "cost_method": "fifo", "valuation": "real_time",
                        "valued_move_count": 2}],
        "valuation": {"available": True, "negative_remaining_qty": 0, "zero_value_with_stock": 0},
        "zero_cost_products": 0,
    })
    assert matching["deviations"] == [], matching
    assert matching["findings"] == [
        "Every category matches the demo profile and the valued moves look consistent."
    ], matching

    unavailable = analyze({
        "categories": [{"name": "A", "cost_method": "fifo", "valuation": "real_time",
                        "valued_move_count": 2}],
        "valuation": {"available": False},
        "zero_cost_products": 0,
    })
    assert unavailable["findings"] == [
        "The stock move value fields are unavailable; stock value cannot be read from this database."
    ], unavailable

    print("FINANCE_I3_COSTING_SELFTEST=PASS")
    return 0


def run(env):
    report = analyze(collect(env))
    print("FINANCE_I3_COSTING=" + json.dumps(report, sort_keys=True, default=str))
    # A completed read-only diagnostic, not an accounting acceptance verdict.
    print("FINANCE_I3_COSTING_RUN=PASS")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true",
                        help="Run the aggregation logic against fixtures, without Odoo.")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    print("Run this file inside an Odoo shell; see the module docstring.", file=sys.stderr)
    return 2


if "env" in globals():
    run(globals()["env"])
elif __name__ == "__main__":
    sys.exit(main())
