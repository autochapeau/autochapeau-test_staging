{
    'name': 'Sales Commission Studio',
    'version': '17.0.2.0.0',
    'license': 'LGPL-3',
    'depends': ['sale_management', 'account', 'commission'],
    'data': ['security/security.xml', 'security/ir.model.access.csv', 'views/views.xml', 'views/accounting.xml'],
    'assets': {'web.assets_backend': [
        'sales_region_commission/static/src/dashboard.js',
        'sales_region_commission/static/src/dashboard.xml',
        'sales_region_commission/static/src/dashboard.scss',
    ]},
    'application': True,
}
