"""Read-only TEST website export. No settings or business rows are changed."""
import base64, hashlib, json, os, subprocess
from pathlib import Path
from odoo.tools import config, exec_pg_environ, find_pg_tool
assert env.cr.dbname == 'autochapeau_prod_test'
root=Path('/tmp/website-rollback-export');root.mkdir(mode=0o700,exist_ok=True)
report={'database':env.cr.dbname,'portal_tables':{},'fields':{},'parameters':{},'attachments':[]}
env.cr.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'portal_%' ORDER BY tablename")
for (table,) in env.cr.fetchall():
    env.cr.execute('SELECT row_to_json(t) FROM "'+table+'" t ORDER BY id')
    report['portal_tables'][table]=[r[0] for r in env.cr.fetchall()]
selected={'product_template':['website_card_price_enabled','website_card_price','website_card_price_label'],'product_category':['portal_image'],'maintenance_claim':['website_submitted','website_message'],'res_partner':[]}
for table,wanted in selected.items():
    env.cr.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",[table]);cols={r[0] for r in env.cr.fetchall()};wanted=[x for x in wanted if x in cols]
    if wanted:
        env.cr.execute('SELECT id,'+','.join('"'+c+'"' for c in wanted)+' FROM "'+table+'" ORDER BY id')
        report['fields'][table]={'columns':['id']+wanted,'rows':env.cr.fetchall()}
params=env['ir.config_parameter'].sudo()
report['parameters']={k:params.get_param(k) for k in ['infinito_client_id','infinito_client_password','portal_api.allow_test_otp']}
attachments=env['ir.attachment'].sudo().search(['|',('res_model','=like','portal.%'),'&',('res_model','in',['product.product','product.template','product.category','fleet.vehicle.model.brand']),'|',('res_id','in',[4495,6902,375]),('res_field','=','portal_image')])
for a in attachments:
    report['attachments'].append({'id':a.id,'name':a.name,'res_model':a.res_model,'res_id':a.res_id,'res_field':a.res_field,'mimetype':a.mimetype,'public':a.public,'datas':a.datas.decode() if a.datas else False})
report['qa']={'offers':env['portal.offer'].with_context(active_test=False).search([('name','ilike','DEMO Website QA')]).read(['id','name','active','product_id']),'statistics':env['portal.statistic'].with_context(active_test=False).search([]).read(['id','name','active','value','metric','opening_value','count_from','car_count_mode']),'product':env['product.product'].browse(6902).read(['id','name','active','is_published','expected_duration','warranty']),'brand':env['fleet.vehicle.model.brand'].browse(375).read(['id','name','image_128'])}
def serial(x):
    if isinstance(x,bytes):return x.decode()
    return str(x)
(root/'website-state.json').write_text(json.dumps(report,default=serial,ensure_ascii=False),encoding='utf8')
protected=['account_move','account_move_line','account_payment','car_work_order','car_workorder_service','car_workorder_product','stock_quant','stock_move','stock_move_line','commission','commission_section','commission_target_job','commission_target_employee','commission_settlement','sales_commission_rule','sales_commission_tier','sales_commission_entry','maintenance_claim','maintenance_claim_part','sale_order','sale_order_line','res_partner']
hashes={}
for table in protected:
    env.cr.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",[table]);cols=[r[0] for r in env.cr.fetchall() if r[0] not in ('write_date','write_uid','create_date','create_uid')]
    if not cols:continue
    env.cr.execute('SELECT '+','.join('"'+c+'"' for c in cols)+' FROM "'+table+'" ORDER BY id');h=hashlib.sha256();count=0
    while True:
        rows=env.cr.fetchmany(1000)
        if not rows:break
        for row in rows:h.update(json.dumps(row,default=serial,separators=(',',':')).encode()+b'\n');count+=1
    hashes[table]={'columns':cols,'count':count,'sha256':h.hexdigest()}
(root/'business-before.json').write_text(json.dumps(hashes))
filestore=Path(config.filestore(env.cr.dbname));selected=root/'filestore';selected.mkdir(exist_ok=True)
# Full database snapshot is kept on the persistent TEST data volume as a recovery point.
backup=Path(config['data_dir'])/'website-rollback-backups'/'20261121';backup.mkdir(mode=0o700,parents=True,exist_ok=True)
dump=backup/'database.dump'
if not dump.exists():
    subprocess.run([find_pg_tool('pg_dump'),'--no-owner','--format=c','--file='+str(dump),env.cr.dbname],env=exec_pg_environ(),check=True)
subprocess.run([find_pg_tool('pg_restore'),'--list',str(dump)],stdout=subprocess.DEVNULL,check=True)
for name in ('website-state.json','business-before.json'):(backup/name).write_bytes((root/name).read_bytes())
env.cr.rollback()
print('WEBSITE_ROLLBACK_AUDIT='+json.dumps({'database':env.cr.dbname,'backup_directory':str(backup),'dump_bytes':dump.stat().st_size,'portal_tables':{k:len(v) for k,v in report['portal_tables'].items()},'protected_tables':len(hashes),'attachment_count':len(attachments)}),flush=True)
