{
    "name": "Contract Upsell",
    "summary": "Shared work order and dual invoicing for Contract sale upsells",
    "version": "17.0.1.4.0",
    "author": "Wellknot",
    "category": "Sales",
    "depends": [
        "partner_management",
        "work_orders",
        "cars_management",
        "appointment_management",
        "sale_split_payment",
    ],
    "data": [
        "views/sale_order_views.xml",
        "views/car_work_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
