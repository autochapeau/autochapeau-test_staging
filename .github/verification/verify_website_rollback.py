"""Verify original website behavior and preserve unrelated business data."""
import hashlib,json
from pathlib import Path
from odoo.tools import config
assert env.cr.dbname=='autochapeau_prod_test'
expected={'portal_content':'17.0.1.0.13','portal_api':'17.0.1.0.31','partner_management':'17.0.1.6.4'}
for name,version in expected.items():
    m=env['ir.module.module'].search([('name','=',name)])
    assert m.state=='installed' and m.latest_version==version,(name,m.latest_version)
assert 'website_card_price' not in env['product.template']._fields
assert 'portal_image' not in env['product.category']._fields
assert 'website_request_user_id' not in env['maintenance.claim']._fields
assert 'portal.google.review.source' not in env.registry.models
assert 'metric' not in env['portal.statistic']._fields
assert not env['portal.offer'].search_count([('name','ilike','DEMO Website QA Offer')])
assert not env['product.product'].search_count([('id','=',6902)])
before=json.loads((Path(config['data_dir'])/'website-rollback-backups/20261121/business-before.json').read_text())
changed=[]
for table,item in before.items():
    columns=item['columns'];env.cr.execute('SELECT '+','.join('"'+c+'"' for c in columns)+' FROM "'+table+'" ORDER BY id')
    h=hashlib.sha256();count=0
    while True:
        rows=env.cr.fetchmany(500)
        if not rows:break
        for row in rows:h.update(json.dumps(row,default=str,separators=(',',':')).encode()+b'\n');count+=1
    if item['count']!=count or item['sha256']!=h.hexdigest():changed.append(table)
assert not changed,'Unrelated business tables changed: '+','.join(changed)
env.cr.rollback()
print('WEBSITE_ROLLBACK_VERIFIED='+json.dumps({'database':env.cr.dbname,'modules':expected,'new_website_fields_removed':True,'unrelated_business_tables_unchanged':len(before),'production_changed':False}),flush=True)
