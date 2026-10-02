"""Deterministic diagnostic compaction. Raw evidence stays local; no model calls."""
import hashlib
import codecs
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
import uuid

FORMATS={'auto','plain','ruff-json','pyright-json'}
MAX_PARSE=16*1024*1024

def inferred(command):
    try:w=shlex.split(command)
    except ValueError:return 'plain'
    if any(x in w for x in ('&&',';','|','||')) or not w:return 'plain'
    if Path(w[0]).name=='ruff' and ('--output-format=json' in w or any(w[i:i+2]==['--output-format','json'] for i in range(len(w)-1))):return 'ruff-json'
    if Path(w[0]).name=='pyright' and '--outputjson' in w:return 'pyright-json'
    return 'plain'

def compact(raw,format,code,limit=None,max_bytes=None):
    """Strict parser: reject unknown/inconsistent data instead of hiding diagnostics."""
    from settings import load
    options=load()['checks']
    if limit is None:limit=options['max_diagnostics']
    if max_bytes is None:max_bytes=options['max_bytes']
    data=json.loads(raw);items=[]
    if code not in (0,1):raise ValueError('Unexpected checker exit code')
    if format=='ruff-json':
        if not isinstance(data,list):raise ValueError('Expected Ruff diagnostic array')
        for d in data:
            if not isinstance(d,dict) or not isinstance(d.get('message'),str) or not isinstance(d.get('filename'),str) or not isinstance(d.get('code'),str):raise ValueError('Unknown Ruff schema')
            loc=d['location']
            if not all(isinstance(loc[k],int) and not isinstance(loc[k],bool) and loc[k]>0 for k in ('row','column')):raise ValueError('Invalid location')
            items.append((d['filename'],loc['row'],loc['column'],'error',d['code'],d['message']))
        if bool(items)!=(code!=0):raise ValueError('Exit/diagnostics mismatch')
    elif format=='pyright-json':
        if not isinstance(data,dict) or not isinstance(data.get('generalDiagnostics'),list):raise ValueError('Expected Pyright schema')
        for d in data['generalDiagnostics']:
            if not isinstance(d,dict) or not isinstance(d.get('file'),str) or not isinstance(d.get('message'),str) or d.get('severity') not in ('error','warning','information'):raise ValueError('Unknown Pyright diagnostic')
            loc=d['range']['start']
            if not all(isinstance(loc[k],int) and not isinstance(loc[k],bool) and loc[k]>=0 for k in ('line','character')):raise ValueError('Invalid location')
            rule=d.get('rule','');
            if not isinstance(rule,str):raise ValueError('Invalid rule')
            items.append((d['file'],loc['line']+1,loc['character']+1,d['severity'],rule,d['message']))
        counts={s:sum(i[3]==s for i in items) for s in ('error','warning','information')}
        summary=data['summary']
        if not isinstance(summary,dict):raise ValueError('Unknown Pyright summary')
        if any(summary.get(k)!=counts[s] for k,s in [('errorCount','error'),('warningCount','warning'),('informationCount','information')]):raise ValueError('Summary mismatch')
        if bool(counts['error'])!=(code!=0):raise ValueError('Exit/diagnostics mismatch')
    else:raise ValueError('No parser')
    # JSON lines avoid ambiguous multiline messages and preserve actionable text.
    unique=list(dict.fromkeys(items));shown=[];encoded=[];size=0
    for item in unique[:limit]:
        p,r,c,s,rule,m=item
        line=json.dumps({'file':p,'line':r,'column':c,'severity':s,'code':rule,'message':m},ensure_ascii=False,separators=(',',':'))
        if size+len(line.encode())+1>max_bytes:break
        shown.append(item);encoded.append(line);size+=len(line.encode())+1
    header=f'{format}: {"PASS" if code==0 else "FAIL"}; exit={code}; diagnostics={len(items)}; unique={len(unique)}; shown={len(shown)}; omitted={len(unique)-len(shown)}'
    lines=[header]+encoded
    return '\n'.join(lines)+'\n'

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def emit(path,stream):
    decoder=codecs.getincrementaldecoder('utf-8')(errors='backslashreplace')
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(64*1024),b''):stream.write(decoder.decode(chunk))
    stream.write(decoder.decode(b'',final=True));stream.flush()

def execute(command,timeout,format,root):
    if format not in FORMATS:raise ValueError('Unknown output_format')
    root=Path(root);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    ident='check_'+uuid.uuid4().hex;folder=root/ident;folder.mkdir(mode=0o700)
    start=time.monotonic();error=None
    with (folder/'stdout').open('wb') as out,(folder/'stderr').open('wb') as err:
        child=subprocess.Popen(['/bin/bash','-o','pipefail','-c',command],stdout=out,stderr=err,start_new_session=True)
        try:code=child.wait(timeout=timeout)
        except BaseException as exc:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            child.wait();code=child.returncode;error=exc
    chosen=inferred(command) if format=='auto' else format
    reduced=None;fallback=None
    from settings import load
    if chosen!='plain' and error is None and load()['checks']['compact']:
        try:
            if (folder/'stdout').stat().st_size>MAX_PARSE:raise ValueError('Output exceeds safe parser size')
            reduced=compact((folder/'stdout').read_text(encoding='utf-8'),chosen,code)
            if len(reduced.encode()) >= (folder/'stdout').stat().st_size:reduced=None;fallback='No size benefit'
        except (ValueError,KeyError,TypeError,UnicodeError) as exc:fallback=f'{type(exc).__name__}: {exc}'
    record={'id':ident,'command':command,'exit_code':code,'duration_seconds':time.monotonic()-start,'format':chosen,'compacted':reduced is not None,'fallback':fallback,'interrupted':error is not None,'streams':{name:{'bytes':(folder/name).stat().st_size,'sha256':digest(folder/name)} for name in ('stdout','stderr')}}
    if reduced is not None:(folder/'compact.txt').write_text(reduced)
    (folder/'manifest.json').write_text(json.dumps(record,indent=2))
    print(f'[check_archive:{ident}] Full stdout/stderr preserved; recall with operations.py check-recall {ident} --stream stdout',flush=True)
    if reduced is not None:print(reduced,end='',flush=True)
    else:emit(folder/'stdout',sys.stdout)
    emit(folder/'stderr',sys.stderr)
    if error:raise error
    return code

def recall(root,ident,stream='stdout',offset=0,limit=8192):
    if not re.fullmatch(r'check_[a-f0-9]{32}',ident) or stream not in ('stdout','stderr','compact.txt','manifest.json'):raise ValueError('Invalid recall identifier/stream')
    if offset<0 or limit<1 or limit>16384:raise ValueError('Invalid byte range')
    path=Path(root)/ident/stream
    if path.parent.is_symlink() or path.is_symlink():raise ValueError('Symlink refused')
    metadata=json.loads((path.parent/'manifest.json').read_text())
    if stream in ('stdout','stderr') and digest(path)!=metadata['streams'][stream]['sha256']:raise ValueError('Archive corruption')
    with path.open('rb') as f:f.seek(offset);chunk=f.read(limit)
    # Base64 preserves exact bytes even at UTF-8 boundaries; displayed text is advisory.
    import base64
    return {'id':ident,'stream':stream,'offset':offset,'next_offset':offset+len(chunk),'eof':offset+len(chunk)>=path.stat().st_size,'base64':base64.b64encode(chunk).decode(),'text':chunk.decode('utf-8',errors='backslashreplace')}
