{
    "name": "Ehsan Donation",
    "summary": "Customer and company Ehsan donations with reports and paid-invoice journal entries",
    "version": "17.0.1.4.1",
    "author": "Wellknot",
    "category": "Sales",
    "depends": [
        "sale_management",
        "account",
        "cars_management",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/ehsan_donation_wizard_views.xml",
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
        "views/res_config_settings_views.xml",
        "views/ehsan_donation_report_views.xml",
        "views/company_ehsan_donation_report_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
