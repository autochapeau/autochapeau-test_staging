{
    "name": "Workorder Task Quality",
    "summary": "Quality check on workorder tasks with Features + BOM checklist and QA fault report",
    "version": "17.0.1.2.1",
    "author": "Wellknot",
    "category": "Services",
    "depends": [
        "work_orders",
        "workorder_time_tracking",
        "cars_management",
        "stock",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/task_quality_refuse_wizard_views.xml",
        "views/car_workorder_service_views.xml",
        "views/workorder_service_qa_fault_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
