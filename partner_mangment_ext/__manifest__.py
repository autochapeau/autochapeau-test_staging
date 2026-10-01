{
    "name": "Partner Management Ext",
    "summary": "Customer gender, nationality, CR, national address, and line-only sale discounts",
    "version": "17.0.1.1.11",
    "author": "Gulfboost",
    "category": "Contacts",
    "depends": [
        "base_vat", "partner_management", "sale",
        "account", "sales_team",
    ],
    "data": [
        "views/res_partner_views.xml",
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
