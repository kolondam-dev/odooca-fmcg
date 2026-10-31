# Part of odooca-fmcg. License LGPL-3.
{
    "name": "FMCG Monetary and AR Monitoring Dashboard",
    "summary": "Financial funnel, receivable aging matrix, and AR breakdown by salesperson, "
               "coverage area, and customer.",
    "version": "19.0.1.0.0",
    "category": "Accounting/Reporting",
    "author": "kolondam-dev",
    "license": "LGPL-3",
    "depends": ["base", "account", "sale", "id_base"],
    "data": [
        "security/ir.model.access.csv",
        "data/id_monetary_target_data.xml",
        "views/monetary_target_views.xml",
        "views/monetary_funnel_views.xml",
        "views/ar_aging_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": False,
}
