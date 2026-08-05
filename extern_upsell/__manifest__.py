{
    "name": "Extern Upsell",
    "summary": "Shared visit and extra sale orders for Extern referrals (commission on parent only)",
    "version": "17.0.1.0.1",
    "author": "Wellknot",
    "category": "Sales",
    "depends": [
        "partner_management",
        "contract_upsell",
        "work_orders",
        "cars_management",
        "appointment_management",
        "external_referral",
    ],
    "data": [
        "views/sale_order_views.xml",
        "views/car_work_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
