{
    "name": "Workorder Time Tracking",
    "summary": "Start/pause/resume task time logs with configurable pause reasons",
    "version": "17.0.1.1.0",
    "author": "Wellknot",
    "category": "Services",
    "depends": [
        "work_orders",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/pause_reason_data.xml",
        "wizard/pause_reason_wizard_views.xml",
        "views/workorder_pause_reason_views.xml",
        "views/car_workorder_service_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
