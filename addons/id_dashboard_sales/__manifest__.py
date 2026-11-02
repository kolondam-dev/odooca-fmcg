# Part of odooca-fmcg. License LGPL-3.
{
    "name": "ID Dashboard: Sales Productivity",
    "summary": "Field sales productivity dashboard: KPI cards, PJP compliance, effective call, "
               "lines per order, SKU penetration and fulfillment-to-invoice ratio.",
    "version": "19.0.1.3.0",
    "category": "Distribution",
    "author": "kolondam-dev",
    "license": "LGPL-3",
    "depends": ["web", "id_base", "sale_stock", "account", "spreadsheet_dashboard"],
    "data": [
        "security/ir.model.access.csv",
        "security/target_rules.xml",
        "views/dashboard_views.xml",
        "views/segment_target_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "id_dashboard_sales/static/src/scss/sales_productivity.scss",
            "id_dashboard_sales/static/src/js/sales_productivity.js",
            "id_dashboard_sales/static/src/js/sales_productivity.xml",
        ],
    },
    "installable": True,
    "application": False,
}
