"""One-use, forced-command SSH receiver for one authorized TEST refresh."""
import hashlib,json,os,sys,tarfile
from pathlib import Path,PurePosixPath

root=Path(__file__).resolve().parent
state=json.loads((root/'transfer.private.json').read_text())
authorized=Path(state['authorized_keys'])
tag='test-refresh-'+state['run_id']

def revoke():
    lines=authorized.read_text().splitlines()
    authorized.write_text('\n'.join(line for line in lines if tag not in line)+'\n')
    authorized.chmod(0o600)
    os.chown(authorized,state['ssh_uid'],state['ssh_gid'])

command=sys.argv[1] if len(sys.argv)==2 else ''
if command=='ready':
    assert state['backup_verified'] and not (root/'received.json').exists()
    print('TEST_BACKUP_VERIFIED_READY')
elif command=='receive':
    assert state['backup_verified'] and not (root/'incoming').exists()
    incoming=root/'incoming';incoming.mkdir(mode=0o700)
    seen=set();total=0
    try:
        with tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as archive:
            manifest=None
            for member in archive:
                path=PurePosixPath(member.name)
                assert not path.is_absolute() and '..' not in path.parts
                assert member.isfile(), 'Only regular files are accepted'
                assert member.name not in seen
                assert member.name in ('manifest.json','database.dump') or (path.parts[0]=='filestore' and len(path.parts)==3)
                assert member.size<=5*1024**3
                target=incoming.joinpath(*path.parts)
                assert target.resolve().is_relative_to(incoming.resolve())
                target.parent.mkdir(parents=True,exist_ok=True)
                if member.name=='manifest.json':
                    assert not seen and member.size<32*1024**2
                    data=archive.extractfile(member).read()
                    manifest=json.loads(data)
                    assert manifest['run_id']==state['run_id'] and manifest['source_database']=='autochapeau'
                    target.write_bytes(data)
                else:
                    assert manifest is not None
                    if member.name=='database.dump':expected=manifest['dump_sha256'];size=manifest['dump_bytes']
                    else:
                        info=manifest['files'][str(path.relative_to('filestore'))]
                        expected=info['sha256'];size=info['size']
                    assert member.size==size
                    fs=os.statvfs(root)
                    assert fs.f_bavail*fs.f_frsize>size+512*1024**2,'TEST disk reserve would be exceeded'
                    h=hashlib.sha256()
                    with target.open('xb') as output:
                        stream=archive.extractfile(member)
                        while block:=stream.read(1024*1024):output.write(block);h.update(block);total+=len(block)
                    assert h.hexdigest()==expected,'Transferred file checksum differs'
                seen.add(member.name)
        assert seen=={'manifest.json','database.dump'}|{'filestore/'+name for name in manifest['files']}
        receipt={'run_id':state['run_id'],'files_verified':len(manifest['files']),'bytes_verified':total,'checksums_verified':True}
        (root/'received.json').write_text(json.dumps(receipt,indent=2))
        print('TEST_TRANSFER_VERIFIED='+json.dumps(receipt,sort_keys=True))
    finally:
        revoke()
else:
    raise SystemExit('Only the one-use backup transfer is permitted')
