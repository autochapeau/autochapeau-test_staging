import json
from lxml import etree

generated = env.ref('base.user_groups_view')
root = env.ref('base.view_users_form')
commission = env.ref('sales_region_commission.users_commission_access')
arch = etree.fromstring(env['res.users'].get_view(root.id, 'form')['arch'])
page = arch.xpath("//page[@name='access_rights']")[0]
print('USER_ACCESS_DIAGNOSTIC=' + json.dumps({
    'database': env.cr.dbname,
    'generated_prefix': generated.arch_db[:250],
    'generated_fields': len(etree.fromstring(generated.arch_db.encode()).xpath('.//field')),
    'access_page_fields': [dict(node.attrib) for node in page.xpath('.//field') if node.get('invisible') != '1'],
    'inheritance': [{'name': view.name, 'priority': view.priority, 'active': view.active} for view in env['ir.ui.view'].search([('inherit_id', '=', root.id)])],
    'installed_version': env['ir.module.module'].search([('name', '=', 'sales_region_commission')]).latest_version,
}))
env.cr.rollback()
