{
    'name': 'Analytic Account Tag',
    'version': '17.0.1.0.0',
    'summary': 'Tags for analytic accounts',
    'category': 'Accounting',
    'author': 'Wellknot',
    'depends': ['analytic'],
    'data': [
        'security/ir.model.access.csv',
        'views/analytic_account_tag_views.xml',
        'views/account_analytic_account_tag_inherit.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
