# Part of odooca-fmcg. License LGPL-3.
{
    "name": "FMCG Monetary and AR Monitoring Dashboard",
    "summary": "Financial funnel, receivable aging matrix, and AR breakdown by salesperson, "
               "coverage area, and customer.",
    "version": "19.0.1.1.0",
    "category": "Accounting/Reporting",
    "author": "kolondam-dev",
    "license": "LGPL-3",
    "depends": ["base", "account", "sale", "id_base", "spreadsheet_dashboard"],
    "data": [
        "security/ir.model.access.csv",
        "security/company_rules.xml",
        "data/id_monetary_target_data.xml",
        "views/monetary_target_views.xml",
        "views/monetary_funnel_views.xml",
        "views/ar_aging_views.xml",
        "views/menu_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "id_dashboard_monetary/static/src/scss/monetary_dashboard.scss",
            "id_dashboard_monetary/static/src/js/monetary_dashboard.js",
            "id_dashboard_monetary/static/src/js/monetary_dashboard.xml",
        ],
    },
    "installable": True,
    "application": False,
}
