{
    "name": "FMCG PWA Attendance",
    "summary": "Record verified PWA attendance in Odoo",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "author": "kolondam-dev",
    "category": "Human Resources/Attendances",
    "depends": ["hr_attendance", "id_mobile_api"],
    "data": ["security/ir.model.access.csv", "views/employee_views.xml"],
    "installable": True,
    "application": False,
}
