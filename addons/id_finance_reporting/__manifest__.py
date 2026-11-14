{
    "name": "FMCG Finance Reporting Boundaries",
    "summary": "Server-side role and company boundaries for finance reports",
    "version": "19.0.1.5.1",
    "category": "Accounting",
    "license": "LGPL-3",
    "author": "kolondam-dev",
    "depends": ["account_financial_report", "stock_account"],
    "data": [
        "security/ir.model.access.csv",
        "views/finance_report_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
