{
    "name": "AutoChapeau Loyalty",
    "version": "17.0.1.4.1",
    "summary": "Loyalty points on paid invoices and redeem on sale orders",
    "author": "Wellknot",
    "depends": ["sale_loyalty", "cars_management", "account", "appointment_management"],
    "data": [
        "security/ir.model.access.csv",
        "data/product_data.xml",
        "views/loyalty_rule_views.xml",
        "views/account_move_views.xml",
        "views/sale_order_views.xml",
        "views/sale_loyalty_redeem_wizard_views.xml",
        "views/res_partner_views.xml",
    ],
    "license": "LGPL-3",
}
