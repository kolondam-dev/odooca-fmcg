{
    "name": "ID FMCG Dashboard Redesign",
    "summary": "PNG baseline dashboard compositions and read-only legacy-source bridge",
    "version": "19.0.2.0.0",
    "author": "kolondam-dev",
    "license": "LGPL-3",
    "depends": ["id_dashboard_ui", "id_dashboard_sales"],
    "data": ["views/dashboard_actions.xml"],
    "assets": {"web.assets_backend": [
        "id_dashboard_redesign/static/src/adapters.js",
        "id_dashboard_redesign/static/src/action.js",
        "id_dashboard_redesign/static/src/action.xml",
    ]},
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "application": False,
}
