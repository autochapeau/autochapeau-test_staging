{
    "name": "Sale Discount Limit",
    "summary": "Sale line discount limits with manager approval workflow",
    "version": "17.0.1.2.0",
    "author": "Wellknot",
    "category": "Sales",
    "depends": [
        "sale_management",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/sale_discount_limit_views.xml",
        "views/res_users_views.xml",
        "views/sale_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
