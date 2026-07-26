{
    "name": "POS Partner Car",
    "summary": "Select a customer car after choosing the customer in POS",
    "version": "17.0.1.3.3",
    "author": "Wellknot",
    "category": "Point of Sale",
    "depends": ["point_of_sale", "cars_management"],
    "data": [
        "views/pos_vehicle_action.xml",
        "views/pos_order_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_partner_car/static/src/app/**/*",
        ],
    },
    "installable": True,
    "license": "LGPL-3",
}
