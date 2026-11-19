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

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):h.update(block)
    return h.hexdigest()

command=sys.argv[1] if len(sys.argv)==2 else ''
if command=='ready':
    assert state['backup_verified'] and not (root/'received.json').exists()
    print('TEST_BACKUP_VERIFIED_READY')
elif command=='inventory':
    assert state['backup_verified'] and not (root/'received.json').exists()
    incoming=root/'incoming';verified=[]
    metadata=incoming/'manifest.json'
    if metadata.exists():
        manifest=json.loads(metadata.read_text())
        assert manifest['run_id']==state['run_id']
        expected={'database.dump':{'size':manifest['dump_bytes'],'sha256':manifest['dump_sha256']}}
        expected.update({'filestore/'+name:info for name,info in manifest['files'].items()})
        for name,info in expected.items():
            path=incoming/name
            assert path.resolve().is_relative_to(incoming.resolve())
            if path.is_file() and not path.is_symlink() and path.stat().st_size==info['size'] and digest(path)==info['sha256']:
                verified.append(name)
    cached={'verified':verified,'manifest_sha256':digest(metadata) if metadata.exists() else None}
    (root/'verified-existing.private.json').write_text(json.dumps(cached))
    print(json.dumps(cached))
elif command=='receive':
    assert state['backup_verified'] and not (root/'received.json').exists()
    incoming=root/'incoming';incoming.mkdir(mode=0o700,exist_ok=True)
    cache=root/'verified-existing.private.json'
    cached=json.loads(cache.read_text()) if cache.exists() else {'verified':[],'manifest_sha256':None}
    existing=set(cached['verified'])
    seen=set();total=0
    try:
        with tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as archive:
            manifest=None
            for member in archive:
                path=PurePosixPath(member.name)
                assert not path.is_absolute() and '..' not in path.parts
                assert member.isfile(), 'Only regular files are accepted'
                assert member.name not in seen
                assert member.name in ('manifest.json','database.dump') or (path.parts[0]=='filestore' and 2<=len(path.parts)<=8)
                assert member.size<=5*1024**3
                target=incoming.joinpath(*path.parts)
                assert target.resolve().is_relative_to(incoming.resolve())
                target.parent.mkdir(parents=True,exist_ok=True)
                if member.name=='manifest.json':
                    assert not seen and member.size<32*1024**2
                    data=archive.extractfile(member).read()
                    manifest=json.loads(data)
                    assert manifest['run_id']==state['run_id'] and manifest['source_database']=='autochapeau'
                    if cached['manifest_sha256']:assert hashlib.sha256(data).hexdigest()==cached['manifest_sha256']
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
                    temporary=target.with_name(target.name+'.transfer-part')
                    with temporary.open('wb') as output:
                        stream=archive.extractfile(member)
                        while block:=stream.read(1024*1024):output.write(block);h.update(block);total+=len(block)
                    assert h.hexdigest()==expected,'Transferred file checksum differs'
                    temporary.replace(target)
                seen.add(member.name)
        assert seen|existing=={'manifest.json','database.dump'}|{'filestore/'+name for name in manifest['files']}
        while sys.stdin.buffer.read(1024*1024):pass
        receipt={'run_id':state['run_id'],'files_verified':len(manifest['files']),'bytes_verified':manifest['dump_bytes']+manifest['filestore_bytes'],'bytes_received_this_attempt':total,'checksums_verified':True}
        (root/'received.json').write_text(json.dumps(receipt,indent=2))
        print('TEST_TRANSFER_VERIFIED='+json.dumps(receipt,sort_keys=True))
    finally:
        revoke()
else:
    raise SystemExit('Only the one-use backup transfer is permitted')
