{
    "name": "Work Order Service Components",
    "summary": "Service tags, default components, and suggested versus used quantities on work orders",
    "version": "17.0.1.0.0",
    "author": "Wellknot",
    "category": "Services",
    "depends": ["work_orders"],
    "data": [
        "views/product_views.xml",
        "views/car_work_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "post_init_hook": "post_init_hook",
    "license": "LGPL-3",
}
