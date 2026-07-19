{
    "name": "Account Balance Sheet Report",
    "version": "17.0.1.0.2",
    "depends": ["account", "report_xlsx"],
    "author": "WellKnot",
    "category": "Accounting & Finance",
    "data": [
        "security/ir.model.access.csv",
        "data/data_account_type.xml",
        "report/report_financial.xml",
        "report/report.xml",
        "wizard/balance_sheet.xml",
        "wizard/profit_and_loss.xml",
        "views/res_partner_supplier_company_filter.xml",
        "data/res_partner_filter_companies_default_contacts.xml",
    ],
    "installable": True,
    "license": "AGPL-3",
}
