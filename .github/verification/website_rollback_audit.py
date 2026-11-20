"""Read-only streaming TEST export without loading an additional Odoo registry."""
import gzip,hashlib,json,os,subprocess,shutil
from pathlib import Path
import odoo
from odoo.tools import config,exec_pg_environ,find_pg_tool
config.parse_config([])
database='autochapeau_prod_test'
root=Path('/tmp/website-rollback-export');root.mkdir(mode=0o700,exist_ok=True)
def serial(x):
    if isinstance(x,bytes):return x.decode()
    return str(x)
report={'database':database,'fields':{},'parameters':{},'qa':{}}
with odoo.sql_db.db_connect(database).cursor() as cr:
    cr.execute('SELECT current_database()');assert cr.fetchone()[0]==database
    cr.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'portal_%' ORDER BY tablename");tables=[r[0] for r in cr.fetchall()]
    counts={}
    with gzip.open(root/'portal-tables.jsonl.gz','wt',encoding='utf8') as out:
        for table in tables:
            cr.execute('SELECT row_to_json(t) FROM "'+table+'" t');count=0
            while True:
                rows=cr.fetchmany(20)
                if not rows:break
                for (row,) in rows:out.write(json.dumps({'table':table,'row':row},default=serial,ensure_ascii=False)+'\n');count+=1
            counts[table]=count
    print('WEBSITE_PORTAL_TABLES_EXPORTED='+json.dumps(counts),flush=True)
    selected={'product_template':['website_card_price_enabled','website_card_price','website_card_price_label'],'maintenance_claim':['website_request_user_id']}
    for table,wanted in selected.items():
        cr.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",[table]);cols={r[0] for r in cr.fetchall()};wanted=[x for x in wanted if x in cols]
        if wanted:
            cr.execute('SELECT id,'+','.join('"'+c+'"' for c in wanted)+' FROM "'+table+'" ORDER BY id')
            report['fields'][table]={'columns':['id']+wanted,'rows':cr.fetchall()}
    cr.execute("SELECT key,value FROM ir_config_parameter WHERE key IN ('infinito_client_id','infinito_client_password','portal_api.allow_test_otp')");report['parameters']=dict(cr.fetchall())
    cr.execute("SELECT row_to_json(t) FROM portal_offer t WHERE name::text ILIKE '%DEMO Website QA%'");report['qa']['offers']=[r[0] for r in cr.fetchall()]
    cr.execute('SELECT row_to_json(t) FROM portal_statistic t');report['qa']['statistics']=[r[0] for r in cr.fetchall()]
    cr.execute('SELECT id,active,is_published FROM product_product WHERE id=6902');report['qa']['product']=cr.fetchall()
    cr.execute("SELECT id,name,res_model,res_id,res_field,mimetype,public,store_fname,db_datas FROM ir_attachment WHERE res_model LIKE 'portal.%' OR (res_model='product.category' AND res_field='portal_image') OR (res_model IN ('product.product','product.template','fleet.vehicle.model.brand') AND res_id IN (4495,6902,375))")
    rows=cr.fetchall();report['attachments']=[];files=root/'files';files.mkdir(exist_ok=True);filestore=Path(config.filestore(database))
    for rid,name,model,resid,field,mime,public,stored,dbdata in rows:
        report['attachments'].append(dict(id=rid,name=name,res_model=model,res_id=resid,res_field=field,mimetype=mime,public=public,store_fname=stored))
        if stored:
            src=filestore/stored;assert src.resolve().is_relative_to(filestore.resolve())
            if src.exists():target=files/stored;target.parent.mkdir(exist_ok=True);shutil.copyfile(src,target)
        elif dbdata:(files/str(rid)).write_bytes(bytes(dbdata))
    (root/'website-state.json').write_text(json.dumps(report,default=serial,ensure_ascii=False),encoding='utf8')
    protected=['account_move','account_move_line','account_payment','car_work_order','car_workorder_service','car_workorder_product','stock_quant','stock_move','stock_move_line','commission','commission_section','commission_target_job','commission_target_employee','commission_settlement','sales_commission_rule','sales_commission_tier','sales_commission_entry','maintenance_claim','maintenance_claim_part','sale_order','sale_order_line','res_partner']
    hashes={}
    for table in protected:
        cr.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",[table]);cols=[r[0] for r in cr.fetchall() if r[0] not in ('write_date','write_uid','create_date','create_uid','website_request_user_id')]
        if not cols:continue
        cr.execute('SELECT '+','.join('"'+c+'"' for c in cols)+' FROM "'+table+'" ORDER BY id');h=hashlib.sha256();count=0
        while True:
            rows=cr.fetchmany(500)
            if not rows:break
            for row in rows:h.update(json.dumps(row,default=serial,separators=(',',':')).encode()+b'\n');count+=1
        hashes[table]={'columns':cols,'count':count,'sha256':h.hexdigest()}
    (root/'business-before.json').write_text(json.dumps(hashes))
    cr.rollback()
print('WEBSITE_STATE_AND_BUSINESS_HASHES_READY=true',flush=True)
backup=Path(config['data_dir'])/'website-rollback-backups'/'20261121';backup.mkdir(mode=0o700,parents=True,exist_ok=True)
dump=backup/'database.dump'
if not dump.exists():subprocess.run([find_pg_tool('pg_dump'),'--no-owner','--format=c','--file='+str(dump),database],env=exec_pg_environ(),check=True)
subprocess.run([find_pg_tool('pg_restore'),'--list',str(dump)],stdout=subprocess.DEVNULL,check=True)
links=backup/'filestore'
if filestore.exists() and not links.exists():
    links.mkdir(mode=0o700)
    for source in filestore.rglob('*'):
        assert not source.is_symlink()
        target=links/source.relative_to(filestore)
        if source.is_dir():target.mkdir(exist_ok=True)
        elif source.is_file():os.link(source,target)
for name in ('website-state.json','business-before.json','portal-tables.jsonl.gz'):(backup/name).write_bytes((root/name).read_bytes())
print('WEBSITE_ROLLBACK_AUDIT='+json.dumps({'database':database,'backup_directory':str(backup),'dump_bytes':dump.stat().st_size,'protected_tables':len(hashes),'attachment_count':len(report['attachments'])}),flush=True)
