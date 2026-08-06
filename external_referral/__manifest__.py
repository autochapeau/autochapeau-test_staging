{
    "name": "External Referral",
    "summary": "Track manual Autochapeau/Autoflex agency referral fees",
    "version": "17.0.1.1.3",
    "author": "Wellknot",
    "category": "Sales",
    "depends": [
        "sale_management", "account", "cars_management", "work_orders",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/res_partner_views.xml",
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
        "views/external_referral_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
