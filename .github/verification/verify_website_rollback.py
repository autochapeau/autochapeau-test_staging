"""Read-only SQL verification without a competing access-role registry writer."""
import ast,hashlib,json
from pathlib import Path
import odoo
from odoo.tools import config
config.parse_config([])
database='autochapeau_prod_test'
expected={'portal_content':'17.0.1.0.13','portal_api':'17.0.1.0.31','partner_management':'17.0.1.6.4'}
other=['work_orders','workorder_service_components','account_asset_management','appointment_management','sale_split_payment','account_deferred_revenue','sales_region_commission','account_move_print','commission']
for name in other:expected[name]=ast.literal_eval((Path('/mnt/extra-addons')/name/'__manifest__.py').read_text())['version']
with odoo.sql_db.db_connect(database).cursor() as cr:
    cr.execute('SELECT current_database()');assert cr.fetchone()[0]==database
    for name,version in expected.items():
        cr.execute('SELECT state,latest_version FROM ir_module_module WHERE name=%s',[name]);assert cr.fetchone()==('installed',version),name
    removed=[('product.template','website_card_price'),('product.category','portal_image'),('maintenance.claim','website_request_user_id'),('portal.statistic','metric')]
    for model,name in removed:
        cr.execute('SELECT count(*) FROM ir_model_fields WHERE model=%s AND name=%s',[model,name]);assert cr.fetchone()[0]==0,(model,name)
    cr.execute("SELECT count(*) FROM ir_model WHERE model='portal.google.review.source'");assert cr.fetchone()[0]==0
    cr.execute("SELECT count(*) FROM portal_offer WHERE active AND name::text ILIKE '%DEMO Website QA Offer%'");assert cr.fetchone()[0]==0
    before=json.loads((Path(config['data_dir'])/'website-rollback-backups/20261121/business-before.json').read_text())
    changed=[]
    for table,item in before.items():
        columns=item['columns'];cr.execute('SELECT '+','.join('"'+c+'"' for c in columns)+' FROM "'+table+'" ORDER BY id');h=hashlib.sha256();count=0
        while True:
            rows=cr.fetchmany(500)
            if not rows:break
            for row in rows:h.update(json.dumps(row,default=str,separators=(',',':')).encode()+b'\n');count+=1
        if item['count']!=count or item['sha256']!=h.hexdigest():changed.append(table)
    assert not changed,'Unrelated business tables changed: '+','.join(changed)
    cr.rollback()
print('WEBSITE_ROLLBACK_VERIFIED='+json.dumps({'database':database,'modules':expected,'new_website_fields_removed':True,'unrelated_business_tables_unchanged':len(before),'production_changed':False}),flush=True)
