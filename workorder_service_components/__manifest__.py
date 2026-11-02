{
    "name": "Work Order Service Components",
    "summary": "Vehicle parts, service materials and stock consumption when work finishes",
    "version": "17.0.2.0.1",
    "author": "Wellknot",
    "category": "Services",
    "depends": ["work_orders", "workorder_task_quality"],
    "data": [
        "security/ir.model.access.csv",
        "views/car_part_views.xml",
        "views/product_views.xml",
        "views/car_work_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "post_init_hook": "post_init_hook",
    "license": "LGPL-3",
}
