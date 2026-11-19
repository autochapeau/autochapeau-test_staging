"""Read-only inventory for a user-authorized production -> TEST refresh."""
import json
import subprocess

def run(*args):
    return subprocess.check_output(args, text=True)

probe = r'''
import json, os
from pathlib import Path
import psycopg2
from odoo.tools import config
config.parse_config([])
database = os.environ['REFRESH_PROBE_DB']
options = {k:config['db_'+k] for k in ('host','port','user','password') if config['db_'+k]}
with psycopg2.connect(dbname=database, **options) as conn:
    conn.set_session(readonly=True)
    with conn.cursor() as cr:
        cr.execute('SELECT name,latest_version FROM ir_module_module WHERE state=%s ORDER BY name', ['installed'])
        installed = dict(cr.fetchall())
        cr.execute('SELECT pg_database_size(current_database())')
        size = cr.fetchone()[0]
        counts = {}
        for table in ('res_partner','account_move','car_work_order','car_workorder_product','stock_quant','ir_attachment'):
            cr.execute('SELECT count(*) FROM '+table)
            counts[table] = cr.fetchone()[0]
        cr.execute("SELECT key FROM ir_config_parameter WHERE key ~* 'sms|infinito|ziwo|tabby|tamara|token|secret|api|web.base|database.uuid|neutral' ORDER BY key")
        keys=[r[0] for r in cr.fetchall()]
        cr.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND (table_name IN ('ir_cron','ir_mail_server','fetchmail_server','payment_provider','sms_sms','mail_mail','iap_account') OR (table_name='res_company' AND column_name ~* 'ziwo|sms|infinito|tabby|tamara|token|secret|api|edi')) ORDER BY table_name,ordinal_position")
        cols={}
        for table,col in cr.fetchall():cols.setdefault(table,[]).append(col)
print('REFRESH_DB_INVENTORY='+json.dumps({'database':database,'data_dir':config['data_dir'],'db_host':config['db_host'],'db_port':config['db_port'],'db_user':config['db_user'],'database_bytes':size,'installed':installed,'counts':counts,'integration_parameter_keys':keys,'integration_columns':cols},sort_keys=True))
'''

services = ['autochapeau_staging_odoo_odoo','autochapeau_erp_odoo']
for service, database in zip(services, ['autochapeau_prod_test','autochapeau']):
    ids = run('docker','ps','--filter','label=com.docker.swarm.service.name='+service,'--format','{{.ID}}').split()
    if len(ids)!=1:
        print('REFRESH_SERVICE_UNAVAILABLE='+json.dumps({'service':service,'containers':len(ids)}))
        continue
    info=json.loads(run('docker','inspect',ids[0]))[0]
    spec=json.loads(run('docker','service','inspect',service))[0]
    mounts=[{k:m.get(k) for k in ('Type','Name','Source','Destination','RW')} for m in info['Mounts']]
    print('REFRESH_SERVICE_INVENTORY='+json.dumps({'service':service,'container':ids[0],'image':info['Config']['Image'],'mounts':mounts,'networks':list(info['NetworkSettings']['Networks']),'replicas':spec['Spec']['Mode']},sort_keys=True))
    print(run('docker','exec','-i','-e','REFRESH_PROBE_DB='+database,ids[0],'python3','-c',probe))
print('REFRESH_DISK_SPACE\n'+run('df','-h','/var/lib/docker','/home/admin'))
