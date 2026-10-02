"""Private revision-bound line-region snapshots; no relocation or source writes."""
import hashlib,json,os,re
from pathlib import Path

def no_symlinks(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Symlink paths are unsupported')
    return path

def store(folder,path,start,end):
    path=no_symlinks(path)
    raw=path.read_bytes();text=raw.decode('utf-8');lines=text.splitlines(keepends=True)
    if start<1 or end<start or end>len(lines):raise ValueError('Invalid region line range')
    meta={'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'start':start,'end':end}
    encoded=json.dumps(meta,sort_keys=True,separators=(',',':')).encode()
    ident='region_'+hashlib.sha256(encoded).hexdigest()[:24]
    folder=Path(folder);no_symlinks(folder);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    for suffix,data in (('.json',encoded),('.source',raw)):
        target=folder/(ident+suffix)
        try:
            fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as f:f.write(data)
        except FileExistsError:
            no_symlinks(target)
            if target.read_bytes()!=data:raise ValueError('Region archive collision/corruption')
    return ident,meta,''.join(lines[start-1:end])

def replacement(folder,ident,new):
    if not re.fullmatch(r'region_[a-f0-9]{24}',ident):raise ValueError('Invalid region ID')
    folder=no_symlinks(folder)
    meta_path=no_symlinks(folder/(ident+'.json'));source=no_symlinks(folder/(ident+'.source'))
    encoded=meta_path.read_bytes()
    if 'region_'+hashlib.sha256(encoded).hexdigest()[:24]!=ident:raise ValueError('Region metadata integrity failure')
    meta=json.loads(encoded);raw=source.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise ValueError('Region source integrity failure')
    lines=raw.decode('utf-8').splitlines(keepends=True);start,end=meta['start'],meta['end']
    if start<1 or end<start or end>len(lines):raise ValueError('Invalid archived region range')
    no_symlinks(meta['path'])
    return {'path':meta['path'],'expected_sha256':meta['sha256'],'content':''.join(lines[:start-1])+new+''.join(lines[end:])}
