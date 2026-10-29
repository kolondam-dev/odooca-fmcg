{
    "name": "FMCG Mobile Read API",
    "summary": "Session-scoped, read-only bootstrap and catalog snapshots for mobile clients.",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "author": "kolondam-dev",
    "category": "Distribution",
    "depends": ["id_base", "sale_stock"],
    "data": [
        "security/mobile_security.xml",
        "security/ir.model.access.csv",
        "views/mobile_workday_views.xml",
    ],
    "installable": True,
    "application": False,
}
