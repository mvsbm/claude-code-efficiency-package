#!/usr/bin/env python3
"""Native hooks: workflow guidance and revision-aware read ledger. No model calls.
Hints are not cached results. Never suppress tests, writes, or requested rereads.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import operations
import settings

STATE=Path(os.environ.get('EFFICIENCY_STATE',str(Path.home()/'.local/state/claude-efficiency')))
TEXT={'.py','.js','.ts','.tsx','.jsx','.md','.txt','.json','.yaml','.yml','.toml','.sh','.rs','.go','.c','.cpp','.h'}


def fingerprint(path):
    if path.suffix not in TEXT or path.is_symlink():return None
    try:
        st=path.stat()
        if not path.is_file() or st.st_size>1024*1024:return None
        raw=path.read_bytes()
        after=path.stat()
        if (st.st_ino,st.st_size,st.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):return None
        return hashlib.sha256(raw).hexdigest()
    except OSError:return None


def process(event):
    output=operations.hook(event) if event.get('tool_name')=='Bash' else {}
    session=event.get('session_id')
    if not session:return output
    folder=STATE/'ledger';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    key=hashlib.sha256(session.encode()).hexdigest();path=folder/(key+'.json')
    fd=os.open(folder/(key+'.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if path.is_symlink():raise ValueError('Unsafe ledger path')
        data=json.loads(path.read_text()) if path.exists() else {'session_id':session,'reads':{},'pending':{},'duplicate_read_hints':0}
        name=event.get('hook_event_name');tool=event.get('tool_name');args=event.get('tool_input',{})
        if tool=='Read' and name in ('PreToolUse','PostToolUse','PostToolUseFailure'):
            file=Path(args.get('file_path',''))
            if not file.is_absolute():file=Path(event.get('cwd',os.getcwd()))/file
            signature=json.dumps({'path':str(file.absolute()),'offset':args.get('offset'),'limit':args.get('limit'),'pages':args.get('pages')},sort_keys=True)
            call=event.get('tool_use_id');sha=fingerprint(file)
            if call and name=='PreToolUse':
                data['pending'][call]={'signature':signature,'sha':sha,'path':str(file.absolute())}
                old=data['reads'].get(signature)
                if sha and old and old['sha']==sha and settings.load()['workflow']['read_reuse_hints']:
                    data['duplicate_read_hints']+=1
                    output={'hookSpecificOutput':{'hookEventName':'PreToolUse','additionalContext':'Efficiency hint: the same Read arguments already completed for this unchanged file revision. Reuse that observation if sufficient; use a different range if it was truncated. A fresh user-requested read remains allowed. This is a hint, NOT a cached result.'}}
            elif call:
                pending=data['pending'].pop(call,None)
                if name=='PostToolUse' and pending and sha and pending['sha']==sha:
                    data['reads'][signature]={'sha':sha,'path':str(file.absolute()),'at':time.time()}
        elif name=='UserPromptSubmit':
            hints=[v for v in data['reads'].values() if fingerprint(Path(v['path']))==v['sha']][-5:]
            if hints and settings.load()['workflow']['read_reuse_hints']:output={'hookSpecificOutput':{'hookEventName':name,'additionalContext':'Previously inspected unchanged revisions (reuse prior output only when sufficient; explicit rereads are allowed): '+', '.join(v['path'] for v in hints)}}
        # Bounded metadata, not an ever-growing conversation injected into prompts.
        data['reads']=dict(list(data['reads'].items())[-64:]);data['pending']=dict(list(data['pending'].items())[-64:])
        tmp=folder/(key+'.'+str(os.getpid())+'.tmp')
        fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as handle:json.dump(data,handle)
        tmp.replace(path)
    return output

if __name__=='__main__':
    try:print(json.dumps(process(json.load(sys.stdin))))
    except Exception as exc:print('Efficiency hook failed open: '+str(exc),file=sys.stderr);print('{}')
