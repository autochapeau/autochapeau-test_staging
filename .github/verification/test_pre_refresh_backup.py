"""Back up TEST and prove the dump restores before any production copy is made."""
import json
import subprocess
from pathlib import Path

SERVICE = 'autochapeau_staging_odoo_odoo'
ids=subprocess.check_output(['docker','ps','--filter','label=com.docker.swarm.service.name='+SERVICE,'--format','{{.ID}}'],text=True).split()
assert len(ids)==1, 'Expected exactly one running TEST container'
code=r'''
import datetime,hashlib,json,os,subprocess,tarfile,uuid
from pathlib import Path
import psycopg2
from psycopg2 import sql
from odoo.tools import config,exec_pg_environ,find_pg_tool
config.parse_config([])
database='autochapeau_prod_test'
os.umask(0o077)
root=Path(config['data_dir'])/'test-refresh-backups'
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
folder=root/('test-before-production-'+stamp)
folder.mkdir(parents=True,exist_ok=False)
options={k:config['db_'+k] for k in ('host','port','user','password') if config['db_'+k]}
tables=('res_partner','account_move','account_move_line','car_work_order','car_workorder_service','car_workorder_product','stock_quant','stock_move','ir_attachment')
dump=folder/'database.dump'
pg_env=exec_pg_environ()
with psycopg2.connect(dbname=database,**options) as source:
    source.set_session(readonly=True,isolation_level='REPEATABLE READ')
    with source.cursor() as cr:
        cr.execute('SELECT pg_export_snapshot()')
        snapshot=cr.fetchone()[0]
        counts={}
        for table in tables:
            cr.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table)))
            counts[table]=cr.fetchone()[0]
        read_env=dict(pg_env,PGOPTIONS='-c default_transaction_read_only=on')
        subprocess.run([find_pg_tool('pg_dump'),'--format=c','--no-owner','--snapshot='+snapshot,'--file='+str(dump),database],env=read_env,check=True)
subprocess.run([find_pg_tool('pg_restore'),'--list',str(dump)],env=pg_env,stdout=subprocess.DEVNULL,check=True)
filestore=Path(config.filestore(database))
files=sorted(p for p in filestore.rglob('*') if p.is_file())
archive_path=folder/'filestore.tar.gz'
with tarfile.open(archive_path,'w:gz') as archive:
    archive.add(filestore,arcname='filestore')
with tarfile.open(archive_path,'r:gz') as archive:
    restored_bytes=0;file_count=0
    for member in archive:
        if member.isfile():
            stream=archive.extractfile(member)
            while block:=stream.read(1024*1024):restored_bytes+=len(block)
            file_count+=1
assert file_count==len(files)
assert restored_bytes==sum(p.stat().st_size for p in files)
scratch='test_restore_check_'+stamp.lower()
assert scratch.startswith('test_restore_check_') and scratch not in ('autochapeau',database)
admin=psycopg2.connect(dbname='postgres',**options);admin.autocommit=True
with admin.cursor() as cr:cr.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(scratch)))
try:
    # pg_dump 17+ emits this session setting even when dumping PostgreSQL 16.
    # Strip only the unsupported header setting; keep all schema and data intact.
    with (folder/'scratch-restore.private.log').open('wb') as errors:
        reader=subprocess.Popen([find_pg_tool('pg_restore'),'--no-owner','--no-privileges','--file=-',str(dump)],env=pg_env,stdout=subprocess.PIPE,stderr=errors)
        writer=subprocess.Popen([find_pg_tool('psql'),'--dbname='+scratch,'--set=ON_ERROR_STOP=1','--quiet'],env=pg_env,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors)
        for index,line in enumerate(reader.stdout):
            if index<100 and line.strip()==b'SET transaction_timeout = 0;':continue
            writer.stdin.write(line)
        writer.stdin.close()
        assert reader.wait()==0 and writer.wait()==0,'Scratch restore failed; inspect private backup log'

    with psycopg2.connect(dbname=scratch,**options) as restored:
        restored.set_session(readonly=True)
        with restored.cursor() as cr:
            for table,count in counts.items():
                cr.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table)))
                assert cr.fetchone()[0]==count,table
finally:
    with admin.cursor() as cr:
        cr.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()',[scratch])
        cr.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(scratch)))
    admin.close()
def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):value.update(block)
    return value.hexdigest()
metadata={'database':database,'directory':str(folder),'created_utc':stamp,'database_dump_bytes':dump.stat().st_size,'filestore_archive_bytes':archive_path.stat().st_size,'filestore_file_count':file_count,'filestore_source_bytes':restored_bytes,'counts':counts,'sha256':{p.name:digest(p) for p in (dump,archive_path)},'scratch_restore_verified':True}
(folder/'backup.json').write_text(json.dumps(metadata,indent=2))
(root/'latest-before-production.json').write_text(json.dumps(metadata,indent=2))
print('TEST_ROLLBACK_BACKUP_VERIFIED='+json.dumps(metadata,sort_keys=True))
'''
subprocess.run(['docker','exec','-i',ids[0],'python3','-'],input=code,text=True,check=True)
info=json.loads(subprocess.check_output(['docker','inspect',ids[0]],text=True))[0]
mount=next(m for m in info['Mounts'] if m['Destination']=='/var/lib/odoo')
marker=Path(mount['Source'])/'test-refresh-backups/latest-before-production.json'
metadata=json.loads(marker.read_text())
folder=Path(mount['Source'])/'test-refresh-backups'/Path(metadata['directory']).name
spec=json.loads(subprocess.check_output(['docker','service','inspect',SERVICE],text=True))[0]
(folder/'test-service.private.json').write_text(json.dumps(spec,indent=2))
(folder/'test-service.private.json').chmod(0o600)
print('TEST_DOCKER_DISK_USAGE',flush=True)
subprocess.run(['docker','system','df'],check=True)
subprocess.run(['df','-h',mount['Source']],check=True)
