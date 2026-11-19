"""Restore and validate only a uniquely named TEST candidate database."""
import ast,hashlib,json,os,subprocess,sys,uuid
from pathlib import Path
import psycopg2
from psycopg2 import sql
from odoo.tools import config,exec_pg_environ,find_pg_tool

config.parse_config([])
run_id,mode=sys.argv[1:3];assert run_id.isdigit()
target='autochapeau_prod_test'
candidate='test_refresh_candidate_'+run_id
rollback='test_before_refresh_'+run_id
assert all(name!='autochapeau' for name in (target,candidate,rollback))
root=Path(config['data_dir'])/'test-refresh-backups'/('production-copy-'+run_id)
incoming=root/'incoming'
manifest=json.loads((incoming/'manifest.json').read_text())
assert manifest['source_database']=='autochapeau' and manifest['run_id']==run_id
options={k:config['db_'+k] for k in ('host','port','user','password') if config['db_'+k]}
pg_env=exec_pg_environ()
tools=Path(__file__).parent

def admin():
    conn=psycopg2.connect(dbname='postgres',**options);conn.autocommit=True
    return conn

def preserve(database):
    with psycopg2.connect(dbname=database,**options) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cr:
            for table,expected in manifest['business'].items():
                columns=expected['columns']
                cr.execute(sql.SQL('SELECT {} FROM {} ORDER BY id').format(sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier(table)))
                h=hashlib.sha256();count=0
                while rows:=cr.fetchmany(1000):
                    for row in rows:h.update((json.dumps(row,default=str,sort_keys=True,separators=(',',':'))+'\n').encode());count+=1
                assert count==expected['count'] and h.hexdigest()==expected['sha256'],'Business data differs: '+table

def cli(args,name,source=None):
    log=root/(name+'.private.log')
    environment=dict(os.environ,VIDEO_VERIFICATION_ROOT=str(tools/'verification'))
    with log.open('wb') as output:
        result=subprocess.run(['python3',str(tools/'test_refresh_odoo.py'),*args],input=source,env=environment,stdout=output,stderr=subprocess.STDOUT)
    if result.returncode:
        print('TEST_REFRESH_PRIVATE_LOG='+str(log),flush=True)
        raise RuntimeError(name+' failed; review private log without publishing business data')
    for line in log.read_text(errors='replace').splitlines():
        if line.startswith(('VIDEO_REQUIREMENTS_SMOKE=','VIDEO_REQUIREMENTS_REGRESSION=','MODULE_UNIQUE_TESTS=','PRODUCTION_MAINTENANCE_TESTS=')):
            print(line,flush=True)

def neutralize(database):
    assert database==candidate
    with psycopg2.connect(dbname=database,**options) as conn:
        with conn.cursor() as cr:
            cr.execute('ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS mobile_unique_key varchar')
            cr.execute('UPDATE ir_cron SET active=false')
            cr.execute("UPDATE ir_mail_server SET active=false,smtp_user=NULL,smtp_pass=NULL")
            cr.execute("UPDATE ir_mail_server SET active=true,smtp_host='127.0.0.1',smtp_port=9 WHERE name='neutralization - disable emails'")
            for table in ('fetchmail_server','payment_provider','sms_sms','mail_mail','iap_account','res_users_apikeys'):
                cr.execute('SELECT to_regclass(%s)',[table])
                if not cr.fetchone()[0]:continue
                if table=='fetchmail_server':cr.execute('UPDATE fetchmail_server SET active=false,password=NULL')
                elif table=='payment_provider':cr.execute("UPDATE payment_provider SET state='disabled',is_published=false")
                elif table=='sms_sms':cr.execute("UPDATE sms_sms SET state='canceled' WHERE state IN ('outgoing','processing','pending')")
                elif table=='mail_mail':cr.execute("UPDATE mail_mail SET state='cancel' WHERE state='outgoing'")
                elif table=='iap_account':cr.execute("UPDATE iap_account SET account_token='neutralized'")
                elif table=='res_users_apikeys':cr.execute('DELETE FROM res_users_apikeys')
            cr.execute("UPDATE ir_config_parameter SET value='' WHERE key ~* 'infinito|tabby|tamara|hyperpay|alrajhi|qitaf|mylist|yougotagift|card_terminal|ziwo|api[_.]?key|secret|token' AND key NOT IN ('database.secret','database.uuid','portal_api.allow_test_otp')")
            parameters={'web.base.url':'https://erp-test.autochapeau.com','web.base.url.freeze':'True','web.base.portal_url':'https://web-test.autochapeau.com','database.is_neutralized':'True','portal_api.allow_test_otp':'True'}
            if not (root/'neutralized.json').exists():parameters.update({'database.uuid':str(uuid.uuid4()),'database.secret':uuid.uuid4().hex+uuid.uuid4().hex})
            for key,value in parameters.items():
                cr.execute('INSERT INTO ir_config_parameter (key,value) VALUES (%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value',[key,value])
            cr.execute("SELECT column_name,data_type FROM information_schema.columns WHERE table_name='res_company' AND column_name LIKE 'forge_ziwo_%'")
            for name,kind in cr.fetchall():
                if kind=='boolean':cr.execute(sql.SQL('UPDATE res_company SET {}=false').format(sql.Identifier(name)))
                elif any(word in name for word in ('token','password','user_name','account_name')):
                    cr.execute(sql.SQL('UPDATE res_company SET {}=NULL').format(sql.Identifier(name)))
            cr.execute('UPDATE res_company SET stock_move_sms_validation=false')
    (root/'neutralized.json').write_text(json.dumps({'database':database,'outbound_disabled':True,'api_keys_reset':True}))

if mode=='prepare':
    os.umask(0o077)
    conn=admin()
    with conn.cursor() as cr:
        cr.execute('SELECT 1 FROM pg_database WHERE datname=%s',[candidate])
        if cr.fetchone():
            assert candidate.startswith('test_refresh_candidate_') and candidate!=target
            cr.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()',[candidate])
            cr.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(candidate)))
        cr.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(candidate)))
    conn.close()
    with (root/'restore.private.log').open('wb') as errors:
        reader=subprocess.Popen([find_pg_tool('pg_restore'),'--no-owner','--no-privileges','--file=-',str(incoming/'database.dump')],env=pg_env,stdout=subprocess.PIPE,stderr=errors)
        writer=subprocess.Popen([find_pg_tool('psql'),'--dbname='+candidate,'--set=ON_ERROR_STOP=1','--quiet'],env=pg_env,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors)
        for index,line in enumerate(reader.stdout):
            if index<100 and line.strip()==b'SET transaction_timeout = 0;':continue
            writer.stdin.write(line)
        writer.stdin.close()
        assert reader.wait()==0 and writer.wait()==0,'Candidate restore failed; see private log'
    preserve(candidate)
    if (root/'neutralized.json').exists():(root/'neutralized.json').unlink()
    cli(['neutralize','-d',candidate],'native-neutralize')
    neutralize(candidate)
    link=Path(config.filestore(candidate))
    if link.is_symlink():
        assert link.resolve()==(incoming/'filestore').resolve();link.unlink()
    assert not link.exists();link.symlink_to(incoming/'filestore',target_is_directory=True)
    import odoo.modules.module
    odoo.modules.module.initialize_sys_path()
    upgrades=[]
    for name in manifest['installed']:
        path=odoo.modules.module.get_module_path(name,display_warning=False)
        assert path,'Installed production addon is missing on TEST: '+name
        if str(path).startswith('/mnt/extra-addons/'):
            upgrades.append(name)
    required=['portal_api','portal_content','workorder_service_components','order_maintenance','partner_management']
    installs=[name for name in required if name not in manifest['installed']]
    args=['-d',candidate,'-u',','.join(upgrades),'--stop-after-init','--no-http','--max-cron-threads=0','--without-demo=all']
    if installs:args+=['-i',','.join(installs)]
    cli(args,'upgrade')
    neutralize(candidate)
    preserve(candidate)
    for name in ['verify_staging.py','run_regression.py','run_mobile_unique_tests.py']:
        source=(tools/'verification'/name).read_bytes()
        cli(['shell','-d',candidate,'--no-http','--max-cron-threads=0'],name,source=source)
    neutralize(candidate)
    preserve(candidate)
    with psycopg2.connect(dbname=candidate,**options) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cr:
            cr.execute('SELECT DISTINCT store_fname FROM ir_attachment WHERE store_fname IS NOT NULL')
            missing={row[0] for row in cr.fetchall() if not (incoming/'filestore'/row[0]).is_file()}
            assert missing<=set(manifest['missing_source_attachments']),'A transferred attachment is missing'
            cr.execute('SELECT count(*) FROM ir_cron WHERE active');assert cr.fetchone()[0]==0
            cr.execute("SELECT count(*) FROM payment_provider WHERE state!='disabled'");assert cr.fetchone()[0]==0
    result={'candidate':candidate,'business_data_preserved':True,'checksums_verified':True,'outbound_disabled':True,'original_test_unchanged':True,'existing_source_missing_attachments':len(manifest['missing_source_attachments'])}
    (root/'candidate-verified.json').write_text(json.dumps(result,indent=2))
    print('TEST_REFRESH_CANDIDATE_VERIFIED='+json.dumps(result,sort_keys=True))
elif mode in ('cutover','rollback'):
    assert (root/'candidate-verified.json').exists()
    conn=admin()
    with conn.cursor() as cr:
        cr.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=ANY(%s) AND pid<>pg_backend_pid()',[[target,candidate,rollback]])
        if mode=='cutover':
            cr.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(sql.Identifier(target),sql.Identifier(rollback)))
            try:cr.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(sql.Identifier(candidate),sql.Identifier(target)))
            except Exception:
                cr.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(sql.Identifier(rollback),sql.Identifier(target)));raise
        else:
            cr.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(sql.Identifier(target),sql.Identifier(candidate)))
            cr.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(sql.Identifier(rollback),sql.Identifier(target)))
    conn.close()
    print('TEST_DATABASE_'+mode.upper()+'=complete')
elif mode=='verify':
    preserve(target)
    print('REFRESHED_TEST_BUSINESS_DATA_PRESERVED=true')
else:raise ValueError('Unsupported TEST-only operation')
