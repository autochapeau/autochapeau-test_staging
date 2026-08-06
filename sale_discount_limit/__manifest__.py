{
    "name": "Sale Discount Limit",
    "summary": "Limit maximum sale line discount per user",
    "version": "17.0.1.0.0",
    "author": "Wellknot",
    "category": "Sales",
    "depends": [
        "sale_management",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/sale_discount_limit_views.xml",
        "views/res_users_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
