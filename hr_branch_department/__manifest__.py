{
    "name": "HR Branch & Department enhancements",
    "version": "17.0.1.0.1",
    "summary": "Adds department types and a 'Branch' field for employees",
    "category": "Human Resources",
    "author": "Wellknot",
    "depends": ["hr"],
    "data": [
        "data/department_sequence.xml",
        "views/hr_department_views.xml",
        "views/hr_employee_views.xml",
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
