{
    "name": "Commissions",
    "version": "17.0.1.1.1",
    "author": "Wellknot",
    "category": "Invoicing",
    "license": "AGPL-3",
    "depends": ["account", "hr", "work_orders"],
    "data": [
        "security/commission_security.xml",
        "security/ir.model.access.csv",
        "views/menu.xml",
        "views/commission_views.xml",
        "views/commission_category_views.xml",
        "views/commission_settlement_views.xml",
        "views/product_product_views.xml",
        "views/technicians_commission_settlement_views.xml",
    ],
    "installable": True,
}
