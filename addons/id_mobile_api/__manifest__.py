{
    "name": "FMCG Mobile API",
    "summary": "Scoped mobile reads and immutable geolocation/photo evidence capture.",
    "version": "19.0.1.2.2",
    "license": "LGPL-3",
    "author": "kolondam-dev",
    "category": "Distribution",
    "depends": ["id_base", "sale_stock"],
    "data": [
        "security/mobile_security.xml",
        "security/ir.model.access.csv",
        "views/mobile_workday_views.xml",
        "views/mobile_office_views.xml",
    ],
    "installable": True,
    "application": False,
}
