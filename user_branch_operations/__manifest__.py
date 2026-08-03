{
    "name": "User Branch Operations",
    "summary": "Propagate the user's branch to sales, appointments, payments, and invoices",
    "version": "17.0.1.0.0",
    "author": "Wellknot",
    "category": "Operations",
    "depends": [
        "hr_branch_department",
        "cars_management",
        "appointment_management",
        "sale_split_payment",
    ],
    "data": [
        "views/res_users_views.xml",
        "views/account_move_views.xml",
        "views/account_payment_views.xml",
        "views/sale_order_payment_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
