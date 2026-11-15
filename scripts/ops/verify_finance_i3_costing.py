#!/usr/bin/env python3
"""Read-only stock costing and valuation diagnostic for the I3 (HPP) spike.

Run inside an Odoo shell on the demo database:

    docker exec -i odoo /opt/deploy/init.sh shell --no-http \
        < scripts/ops/verify_finance_i3_costing.py

The diagnostic only reads. It reports, per product category, the costing method
and valuation mode, plus stock valuation layer totals, so the method decision
for HPP can be made on observed state instead of assumption. A category that
keeps FIFO + real_time while Odoo 19 defaults new categories to periodic looks
identical in the UI until someone reads these fields.

``--self-test`` exercises ``analyze`` against fixtures with no Odoo registry, so
CI can prove the aggregation logic without a database.
"""

import argparse
import json
import sys

# What the seeded demo is expected to use. This is an assumption, not a fact
# read from the database: the diagnostic reports every deviation instead of
# silently accepting it.
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
    real_time_without_layers = []

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
        if valuation == "real_time" and not category.get("layer_count"):
            real_time_without_layers.append(category.get("name"))

    layers = data.get("layers") or {}
    findings = []
    if not categories:
        findings.append("No product categories were found; costing cannot be assessed.")
    if deviations:
        findings.append(
            f"{len(deviations)} of {len(categories)} categories differ from the demo profile "
            f"({profile['cost_method']} + {profile['valuation']})."
        )
    if real_time_without_layers:
        findings.append(
            f"{len(real_time_without_layers)} real_time categories have no stock valuation layer; "
            "their stock value is not evidenced yet."
        )
    if layers.get("available") and layers.get("negative_remaining_qty"):
        findings.append(
            f"{layers['negative_remaining_qty']} valuation layers end with negative remaining quantity."
        )
    if layers.get("available") and layers.get("zero_value_with_stock"):
        findings.append(
            f"{layers['zero_value_with_stock']} valuation layers keep stock at zero remaining value."
        )
    if data.get("zero_cost_products"):
        findings.append(
            f"{data['zero_cost_products']} storable products still carry a zero standard cost."
        )
    if not findings:
        findings.append("Every category matches the demo profile and the layers look consistent.")

    return {
        "scope": "I3 costing diagnostic only: read-only state, not FIN01-58 acceptance",
        "profile_is_assumption": True,
        "demo_profile": dict(profile),
        "stock_account_installed": bool(data.get("stock_account_installed")),
        "categories_total": len(categories),
        "by_cost_method": by_cost_method,
        "by_valuation": by_valuation,
        "deviations": deviations,
        "real_time_without_layers": real_time_without_layers,
        "layers": layers,
        "zero_cost_products": data.get("zero_cost_products", 0),
        "findings": findings,
    }


def collect(env):
    """Read the registry without writing anything."""
    company = env.company
    product_fields = env["product.product"]._fields
    storable_domain = [("is_storable", "=", True)] if "is_storable" in product_fields else []

    installed = env["ir.module.module"].search(
        [("name", "=", "stock_account"), ("state", "=", "installed")],
        limit=1,
    )
    layer_model = env["stock.valuation.layer"] if "stock.valuation.layer" in env else None

    def value(category, field, default="unset"):
        return category[field] if field in category._fields else default

    categories = []
    categ_model = env["product.category"]
    for category in categ_model.search([]):
        layer_count = 0
        if layer_model is not None:
            layer_count = layer_model.search_count([
                ("product_id.categ_id", "=", category.id),
            ])
        categories.append({
            "id": category.id,
            "name": category.display_name,
            "cost_method": value(category, "property_cost_method"),
            "valuation": value(category, "property_valuation"),
            "product_count": env["product.product"].search_count([("categ_id", "=", category.id)]),
            "layer_count": layer_count,
        })

    layers = {"available": False}
    if layer_model is not None:
        def total(field):
            rows = layer_model.read_group([], [f"{field}:sum"], [])
            return (rows[0].get(f"{field}_sum") if rows else 0) or 0

        layers = {
            "available": True,
            "count": layer_model.search_count([]),
            "value_total": total("value"),
            "remaining_value_total": total("remaining_value"),
            "negative_remaining_qty": layer_model.search_count([("remaining_qty", "<", 0)]),
            "zero_value_with_stock": layer_model.search_count([
                ("remaining_qty", ">", 0),
                ("remaining_value", "=", 0),
            ]),
        }

    return {
        "company": company.display_name,
        "currency": company.currency_id.name if "currency_id" in company._fields else None,
        "stock_account_installed": bool(installed),
        "categories": categories,
        "layers": layers,
        "zero_cost_products": env["product.product"].search_count(storable_domain + [("standard_price", "=", 0)]),
    }


def _fixture():
    return {
        "stock_account_installed": True,
        "categories": [
            {"name": "All / FIFO real time", "cost_method": "fifo", "valuation": "real_time",
             "product_count": 12, "layer_count": 40},
            {"name": "All / Average periodic", "cost_method": "average", "valuation": "periodic",
             "product_count": 3, "layer_count": 0},
            {"name": "All / FIFO periodic", "cost_method": "fifo", "valuation": "periodic",
             "product_count": 1, "layer_count": 0},
            {"name": "Empty real time", "cost_method": "fifo", "valuation": "real_time",
             "product_count": 0, "layer_count": 0},
        ],
        "layers": {
            "available": True,
            "count": 40,
            "value_total": 1000.0,
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
    assert {row["category"] for row in report["deviations"]} == {
        "All / Average periodic", "All / FIFO periodic"}, report
    assert report["real_time_without_layers"] == ["Empty real time"], report
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
                        "layer_count": 2}],
        "layers": {"available": True, "negative_remaining_qty": 0, "zero_value_with_stock": 0},
        "zero_cost_products": 0,
    })
    assert matching["deviations"] == [], matching
    assert matching["findings"] == [
        "Every category matches the demo profile and the layers look consistent."
    ], matching

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
