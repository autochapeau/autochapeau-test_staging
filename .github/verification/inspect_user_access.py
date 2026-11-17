import json
from lxml import etree

generated = env.ref('base.user_groups_view')
root = env.ref('base.view_users_form')
commission = env.ref('sales_region_commission.users_commission_access')
arch = etree.fromstring(env['res.users'].get_view(root.id, 'form')['arch'])
page = arch.xpath("//page[@name='access_rights']")[0]
print('USER_ACCESS_DIAGNOSTIC=' + json.dumps({
    'database': env.cr.dbname,
    'generated_arch': generated.arch_db,
    'commission_arch': commission.arch_db,
    'access_page': etree.tostring(page, encoding='unicode'),
    'installed_version': env['ir.module.module'].search([('name', '=', 'sales_region_commission')]).latest_version,
}))
env.cr.rollback()
