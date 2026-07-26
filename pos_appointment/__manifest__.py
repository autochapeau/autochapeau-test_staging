{
    "name": "POS Appointment",
    "summary": "Book car appointments from POS and link them to POS orders",
    "version": "17.0.1.0.0",
    "author": "Wellknot",
    "category": "Point of Sale",
    "depends": [
        "point_of_sale",
        "pos_partner_car",
        "appointment_management",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/pos_appointment_action.xml",
        "views/pos_order_views.xml",
        "views/car_appointment_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_appointment/static/src/app/**/*",
        ],
    },
    "installable": True,
    "license": "LGPL-3",
}
