# Part of odooca-fmcg. License LGPL-3.
{
    "name": "FMCG Warehouse and Logistics Dashboard",
    "summary": "Stock by FMCG category, FEFO expiry monitoring, delivery fulfillment, "
               "rejection breakdown, and delivery cost ratio per vehicle.",
    "version": "19.0.1.1.0",
    "category": "Inventory/Reporting",
    "author": "kolondam-dev",
    "license": "LGPL-3",
    "depends": ["base", "stock", "sale_stock", "product_expiry", "fleet", "id_base", "spreadsheet_dashboard"],
    "data": [
        "security/ir.model.access.csv",
        "security/company_rules.xml",
        "views/stock_picking_views.xml",
        "views/stock_category_views.xml",
        "views/expiry_views.xml",
        "views/delivery_views.xml",
        "views/fleet_cost_views.xml",
        "views/menu_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "id_dashboard_wms/static/src/scss/wms_dashboard.scss",
            "id_dashboard_wms/static/src/js/wms_dashboard.js",
            "id_dashboard_wms/static/src/js/wms_dashboard.xml",
        ],
    },
    "installable": True,
    "application": False,
}
