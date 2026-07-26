{
    "name": "Partner City",
    "summary": "Select city from a list and sync it to the partner city field",
    "version": "17.0.1.0.0",
    "author": "Wellknot",
    "category": "Contacts",
    "depends": ["base", "contacts"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_city_views.xml",
        "views/res_partner_views.xml",
    ],
    "installable": True,
    "license": "LGPL-3",
}
