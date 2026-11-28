{
    "name": "FMCG PWA Attendance",
    "summary": "Record verified PWA attendance in Odoo",
    "version": "19.0.3.0.0",
    "license": "LGPL-3",
    "author": "kolondam-dev",
    "category": "Human Resources/Attendances",
    "depends": ["hr_attendance", "hr_holidays", "id_mobile_api", "id_approval"],
    "data": [
        "security/ir.model.access.csv",
        "security/report_rules.xml",
        "security/correction_rules.xml",
        "views/employee_views.xml",
        "views/attendance_report_views.xml",
        "views/correction_views.xml",
    ],
    "installable": True,
    "application": False,
}
