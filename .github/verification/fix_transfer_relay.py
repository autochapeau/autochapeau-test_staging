"""Use an unprivileged one-use upload directory; do not grant sudo access."""
import datetime,json,os,pwd,shutil,subprocess,time
from pathlib import Path
run_id='44505400366'
root=Path('/var/lib/docker/volumes/autochapeau_staging_odoo_odoo-data/_data/test-refresh-backups/production-copy-'+run_id)
assert (root/'rollback-backup.json').exists() and not (root/'received.json').exists()
user=pwd.getpwnam('admin')
relay=Path(user.pw_dir)/('test-refresh-transfer-'+run_id)
relay.mkdir(mode=0o700,exist_ok=False)
os.chown(relay,user.pw_uid,user.pw_gid)
assert relay.stat().st_dev==root.stat().st_dev,'Relay must support an atomic move without duplicating files'
for name in ('receive.py','transfer.private.json'):
    shutil.copy2(root/name,relay/name)
    os.chown(relay/name,user.pw_uid,user.pw_gid);(relay/name).chmod(0o600)
state=json.loads((relay/'transfer.private.json').read_text())
authorized=Path(state['authorized_keys']);tag='test-refresh-'+run_id
lines=authorized.read_text().splitlines()
existing=next(line for line in lines if tag in line)
public=existing[existing.index('ssh-ed25519 '):]
expiry=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=60)).strftime('%Y%m%d%H%M%SZ')
forced='/usr/bin/python3 '+str(relay/'receive.py')+' "$SSH_ORIGINAL_COMMAND"'
replacement='restrict,expiry-time="'+expiry+'",command="'+forced.replace('"','\\"')+'" '+public
authorized.write_text('\n'.join(replacement if tag in line else line for line in lines)+'\n')
os.chown(authorized,user.pw_uid,user.pw_gid);authorized.chmod(0o600)
test=subprocess.run(['sudo','-u','admin','/usr/bin/python3',str(relay/'receive.py'),'ready'],capture_output=True,text=True)
assert test.returncode==0 and test.stdout.strip()=='TEST_BACKUP_VERIFIED_READY','Unprivileged receiver check failed'
print('UNPRIVILEGED_TEST_RECEIVER_VERIFIED=true',flush=True)
deadline=time.monotonic()+2400
while not (relay/'received.json').exists():
    if time.monotonic()>deadline:raise TimeoutError('One-use relay did not receive the production archive')
    time.sleep(3)
receipt=json.loads((relay/'received.json').read_text());assert receipt['checksums_verified']
assert not (root/'incoming').exists()
(relay/'incoming').rename(root/'incoming')
(relay/'received.json').rename(root/'received.json')
print('PRIVATE_TEST_STAGING_TRANSFER_COMPLETE='+json.dumps(receipt,sort_keys=True),flush=True)
