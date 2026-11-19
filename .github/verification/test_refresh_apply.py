"""Stage, verify and atomically replace TEST; production is never an action target."""
import copy,datetime,http.client,json,os,pwd,re,shutil,socket,subprocess,sys,time,signal
from pathlib import Path
from urllib.parse import quote,urlencode

SERVICE='autochapeau_staging_odoo_odoo'
assert SERVICE!='autochapeau_erp_odoo'
tools=Path(__file__).resolve().parent
settings=json.loads((tools/'test_refresh_transfer.json').read_text())
run_id=settings['run_id'];public_key=settings['public_key']
assert run_id.isdigit() and re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+ test-refresh-'+run_id,public_key)

class Unix(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.settimeout(30);self.sock.connect('/var/run/docker.sock')

def docker(method,path,body=None):
    conn=Unix('localhost',timeout=30)
    try:
        conn.request(method,path,json.dumps(body) if body is not None else None,{'Content-Type':'application/json'})
        response=conn.getresponse();data=response.read();value=json.loads(data) if data else {}
        assert response.status<400,'Docker request failed: '+str(response.status)
        return value
    finally:conn.close()

def service():return docker('GET','/services/'+SERVICE)
def update(spec):
    assert spec['Name']==SERVICE
    for attempt in range(8):
        current=service()
        try:return docker('POST','/services/'+current['ID']+'/update?version='+str(current['Version']['Index']),spec)
        except AssertionError:
            if attempt==7:raise
            time.sleep(1)

def tasks(name):
    return docker('GET','/tasks?'+urlencode({'filters':json.dumps({'service':[name]})}))

def stopped(name):
    return not any(t['Status']['State'] in ('running','starting','ready','preparing') for t in tasks(name))

def running(name):
    rows=[t for t in tasks(name) if t.get('DesiredState')=='running' and t['Status']['State']=='running']
    return max(rows,key=lambda t:t['CreatedAt'])['Status']['ContainerStatus']['ContainerID'] if rows else None

def wait(predicate,seconds,label):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=predicate()
        if result:return result
        time.sleep(3)
    raise TimeoutError(label)

original=service()['Spec'];assert original['Name']==SERVICE
assert original['Mode']['Replicated']['Replicas']==1
container=wait(lambda:running(SERVICE),60,'TEST container unavailable')
info=json.loads(subprocess.check_output(['docker','inspect',container],text=True))[0]
volume=next(m for m in info['Mounts'] if m['Destination']=='/var/lib/odoo')
data=Path(volume['Source']).resolve()
assert 'autochapeau_staging_odoo_odoo-data' in str(data) and 'autochapeau_erp_odoo-data' not in str(data)
backup=json.loads((data/'test-refresh-backups/latest-before-production.json').read_text())
assert backup['database']=='autochapeau_prod_test' and backup['scratch_restore_verified']
stamp=datetime.datetime.strptime(backup['created_utc'],'%Y%m%dT%H%M%SZ').replace(tzinfo=datetime.timezone.utc)
assert datetime.datetime.now(datetime.timezone.utc)-stamp<datetime.timedelta(hours=24)
root=data/'test-refresh-backups'/('production-copy-'+run_id)
root.mkdir(mode=0o700,exist_ok=True)
assert not (root/'completed.json').exists(),'This refresh already completed'
resuming=(root/'received.json').exists()
partial=(root/'incoming').exists()
# Superseded waiters have never entered candidate preparation or TEST cutover.
for old_run in settings.get('superseded_workflow_runs',[]):
    assert old_run.isdigit()
    old_script='/tmp/test-refresh-tools-'+old_run+'/test_refresh_apply.py'
    assert not (root/'candidate-verified.json').exists()
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit() or int(directory.name)==os.getpid():continue
        try:
            args=[x.decode() for x in (directory/'cmdline').read_bytes().split(b'\0') if x]
            if len(args)>1 and args[0].endswith('python3') and args[1]==old_script and directory.stat().st_uid==0:
                os.kill(int(directory.name),signal.SIGTERM)
        except (FileNotFoundError,ProcessLookupError):pass

(root/'original-test-service.private.json').write_text(json.dumps(original,indent=2))
(root/'rollback-backup.json').write_text(json.dumps(backup,indent=2))
if not resuming and not partial and shutil.disk_usage(data).free<7*1024**3:
    print('Reclaiming unused TEST build cache only; no images or volumes are removed',flush=True)
    subprocess.run(['docker','builder','prune','--all','--force','--keep-storage','512MB'],check=True)
assert shutil.disk_usage(data).free>(2 if resuming else 3 if partial else 6)*1024**3,'Insufficient TEST staging space'
assert os.environ.get('SUDO_UID'),'Use the existing TEST deployment identity'
user=pwd.getpwuid(int(os.environ['SUDO_UID']))
assert user.pw_uid!=0
# Remove only this task's expired/superseded transfer keys from prior attempts.
for old_state in (data/'test-refresh-backups').glob('production-copy-*/transfer.private.json'):
    previous=json.loads(old_state.read_text())
    if previous['run_id']==run_id:continue
    old_keys=Path(previous['authorized_keys'])
    if old_keys.is_file():
        old_tag='test-refresh-'+previous['run_id']
        old_keys.write_text('\n'.join(line for line in old_keys.read_text().splitlines() if old_tag not in line)+'\n')
        old_keys.chmod(0o600);os.chown(old_keys,previous['ssh_uid'],previous['ssh_gid'])
authorized=Path(user.pw_dir)/'.ssh/authorized_keys'
assert user.pw_shell not in ('/usr/sbin/nologin','/bin/false')
authorized.parent.mkdir(mode=0o700,exist_ok=True)
assert authorized.parent.resolve().is_relative_to(Path(user.pw_dir).resolve())
os.chown(authorized.parent,user.pw_uid,user.pw_gid)
authorized.parent.chmod(0o700)
authorized.touch(mode=0o600,exist_ok=True)
tag='test-refresh-'+run_id
assert tag not in authorized.read_text()
shutil.copy2(tools/'test_refresh_receive.py',root/'receive.py')
state={'run_id':run_id,'authorized_keys':str(authorized),'ssh_uid':user.pw_uid,'ssh_gid':user.pw_gid,'backup_verified':True}
(root/'transfer.private.json').write_text(json.dumps(state))
expiry=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=75)).strftime('%Y%m%d%H%M%SZ')
forced='sudo -n /usr/bin/python3 '+str(root/'receive.py')+' "$SSH_ORIGINAL_COMMAND"'
line='restrict,expiry-time="'+expiry+'",command="'+forced.replace('"','\\"')+'" '+public_key+'\n'
if not resuming:
    with authorized.open('a') as file:file.write('\n'+line)
authorized.chmod(0o600);os.chown(authorized,user.pw_uid,user.pw_gid)
print('TEST_RECEIVER_READY='+json.dumps({'run_id':run_id,'rollback_backup':backup['directory'],'minimum_free_bytes':shutil.disk_usage(data).free}),flush=True)
worker_name='test-refresh-worker-'+run_id
worker=None;scaled_down=False;files_switched=False;database_switched=False;complete=False

def execute(mode):
    result=subprocess.run(['docker','exec',worker,'python3','/opt/test-refresh-tools/test_refresh_candidate.py',run_id,mode],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    with (root/('candidate-'+mode+'.private.log')).open('w') as file:file.write(result.stdout);file.write(result.stderr)
    for line in result.stdout.splitlines():
        if line.startswith(('VIDEO_REQUIREMENTS_','MODULE_UNIQUE_TESTS=','TEST_REFRESH_','TEST_DATABASE_','REFRESHED_TEST_')):print(line,flush=True)
    assert result.returncode==0,'TEST candidate '+mode+' failed; inspect its private log'

try:
    wait(lambda:(root/'received.json').exists(),3000,'Production export was not received; existing TEST remains unchanged')
    incoming=root/'incoming'
    receipt=json.loads((root/'received.json').read_text());assert receipt['checksums_verified']
    for path in incoming.rglob('*'):
        os.chown(path,0,0)
    template=copy.deepcopy(original['TaskTemplate'])
    template['ContainerSpec']['Command']=['python3','-c','import time; time.sleep(7200)']
    template['ContainerSpec']['Args']=[];template['ContainerSpec']['User']='0'
    template['ContainerSpec']['Labels']={}
    template['ContainerSpec']['Healthcheck']={'Test':['NONE']}
    template['ContainerSpec'].setdefault('Mounts',[]).append({'Type':'bind','Source':str(tools),'Target':'/opt/test-refresh-tools','ReadOnly':True})
    template['RestartPolicy']={'Condition':'none'}
    template['Networks']=[{'Target':n['Target']} for n in template.get('Networks',[])]
    node=docker('GET','/info')['Swarm']['NodeID']
    template['Placement']={'Constraints':['node.id=='+node]}
    docker('POST','/services/create',{'Name':worker_name,'Labels':{'traefik.enable':'false','test-refresh':run_id},'TaskTemplate':template,'Mode':{'Replicated':{'Replicas':1}},'EndpointSpec':{'Mode':'vip'}})
    worker=wait(lambda:running(worker_name),180,'TEST worker did not start')
    execute('prepare')
    assert (root/'candidate-verified.json').exists()
    # Only after candidate verification do we stop the old TEST application.
    stopped_spec=copy.deepcopy(original);stopped_spec['Mode']['Replicated']['Replicas']=0
    update(stopped_spec);scaled_down=True
    wait(lambda:stopped(SERVICE),180,'TEST did not stop for atomic switch')
    live_store=data/'filestore/autochapeau_prod_test'
    old_store=root/'old-test-filestore'
    candidate_link=data/'filestore'/('test_refresh_candidate_'+run_id)
    assert candidate_link.is_symlink() and candidate_link.resolve()==(incoming/'filestore').resolve()
    candidate_link.unlink()
    if live_store.exists():live_store.rename(old_store)
    (incoming/'filestore').rename(live_store);files_switched=True
    uid=live_store.stat().st_uid
    # The application runs as the original Odoo uid and must read restored files.
    app_uid=int(subprocess.check_output(['docker','exec',worker,'id','-u','odoo'],text=True).strip())
    app_gid=int(subprocess.check_output(['docker','exec',worker,'id','-g','odoo'],text=True).strip())
    for path in [live_store,*live_store.rglob('*')]:os.chown(path,app_uid,app_gid)
    execute('cutover');database_switched=True
    live=copy.deepcopy(original)
    args=live['TaskTemplate']['ContainerSpec'].get('Args',[])
    args=[a for a in args if not a.startswith(('--max-cron-threads=','--db-filter=','--database='))]
    args+=['--max-cron-threads=0','--db-filter=^autochapeau_prod_test$','--database=autochapeau_prod_test']
    live['TaskTemplate']['ContainerSpec']['Args']=args
    update(live)
    app=wait(lambda:running(SERVICE),180,'Refreshed TEST did not start')
    probe=r'''import json,urllib.request
result={}
for route in ('/web/health','/web/login?db=autochapeau_prod_test'):
 with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8069'+route,headers={'Host':'erp-test.autochapeau.com'}),timeout=20) as response:
  assert response.status==200;result[route]=response.status
print('REFRESHED_TEST_HTTP='+json.dumps(result))
'''
    def health():
        result=subprocess.run(['docker','exec',app,'python3','-c',probe],capture_output=True,text=True)
        if result.returncode==0:print(result.stdout.strip(),flush=True);return True
        return False
    wait(health,600,'Refreshed TEST HTTP check failed')
    execute('verify')
    frontend=r'''import json,urllib.request
request=urllib.request.Request('http://autochapeau_staging_website_web/v1/portal/statistics?lang=en',headers={'Host':'web-test.autochapeau.com'})
with urllib.request.urlopen(request,timeout=30) as response:
 assert response.status==200;payload=json.load(response);assert isinstance(payload,list)
print('REFRESHED_TEST_FRONTEND_API=200')
'''
    api=subprocess.run(['docker','exec',worker,'python3','-c',frontend],capture_output=True,text=True)
    (root/'frontend-check.private.log').write_text(api.stdout+api.stderr)
    assert api.returncode==0,'TEST frontend API check failed; rolling back'
    print(api.stdout.strip(),flush=True)
    complete=True
    result={'run_id':run_id,'target_database':'autochapeau_prod_test','previous_test_database':'test_before_refresh_'+run_id,'previous_test_backup':backup['directory'],'new_copy_directory':'/var/lib/odoo/test-refresh-backups/'+root.name,'production_service_modified':False,'test_http':200,'test_frontend_api':200,'business_data_preserved':True,'outbound_disabled':True}
    (root/'completed.json').write_text(json.dumps(result,indent=2))
    print('TEST_REFRESH_COMPLETE='+json.dumps(result,sort_keys=True),flush=True)
except BaseException:
    if scaled_down:
        stopped_spec=copy.deepcopy(original);stopped_spec['Mode']['Replicated']['Replicas']=0;update(stopped_spec)
        wait(lambda:stopped(SERVICE),180,'Stopping failed TEST replacement')
        if database_switched:execute('rollback')
        if files_switched:
            (data/'filestore/autochapeau_prod_test').rename(root/'failed-new-filestore')
            if (root/'old-test-filestore').exists():(root/'old-test-filestore').rename(data/'filestore/autochapeau_prod_test')
        update(original)
        wait(lambda:running(SERVICE),180,'Original TEST recovery')
        print('ORIGINAL_TEST_RESTORED=true',flush=True)
    raise
finally:
    lines=authorized.read_text().splitlines()
    authorized.write_text('\n'.join(line for line in lines if tag not in line)+'\n')
    authorized.chmod(0o600);os.chown(authorized,user.pw_uid,user.pw_gid)
    if worker:
        item=docker('GET','/services/'+worker_name)
        docker('DELETE','/services/'+item['ID'])
    print('TEMPORARY_TEST_TRANSFER_ACCESS_REMOVED=true',flush=True)
