{
    "name": "FMCG AR Collection (Surat Jalan Penagihan)",
    "summary": "Surat Jalan Penagihan (SJP): daftar tagihan dari AR terbuka, dibuat finance/AR admin, "
               "ditugaskan ke kolektor atau rute.",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "author": "kolondam-dev",
    "category": "Accounting",
    "depends": ["id_base", "id_mobile_api", "account"],
    "data": [
        "security/collection_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "report/collection_sheet_report.xml",
        "views/collection_sheet_views.xml",
        "wizard/collection_sheet_generate_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": False,
}
