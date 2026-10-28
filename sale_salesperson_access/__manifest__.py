{
    "name": "Sale Salesperson Access",
    "summary": "Only selected users can change the salesperson on a sales order",
    "version": "17.0.1.0.0",
    "author": "Wellknot",
    "category": "Sales",
    "depends": ["sale"],
    "data": [
        "security/security.xml",
        "views/sale_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
