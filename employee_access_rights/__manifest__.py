{
    'name': 'Employee Access Rights',
    'version': '1.0',
    'summary': 'Adds Rules in several modules to restrict access records to the employee branch',
    'author': 'Wellknot',
    'category': 'Hidden',
    'depends': [
        'hr_branch_department',
        'sale',
        'stock',
        'work_orders',
        'appointment_management',
        'cars_management'
    ],
    'data': [
        'security/security_groups.xml',
        'security/security_rules_inventory.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
