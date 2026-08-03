{
    "name": "External Referral",
    "summary": "Track percentage-based fees for external agency referrals",
    "version": "17.0.1.0.0",
    "author": "Wellknot",
    "category": "Sales",
    "depends": [
        "sale_management",
        "account",
        "cars_management",
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
