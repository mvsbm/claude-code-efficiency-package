#!/usr/bin/env python3
"""Action Fusion, exact mutations, diagnostic recall, and native hook reporting.
Reference mechanism: NVlabs/SoL-Pi 1559b5cb (MIT). No MCP or model reducer.
"""
import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import re
import shlex
import subprocess
import sys
import time
import uuid
from . import checks, regions, settings
from .patch_input import parse_patch

ARCHIVES=Path(os.environ.get('SOL_ARCHIVE_DIR',str(Path.home()/'.local/state/claude-efficiency/archives'))).resolve()
STATS=Path(os.environ.get('SOL_STATS_DIR',str(Path.home()/'.local/state/claude-efficiency/live'))).resolve()
STATE=Path(os.environ.get('EFFICIENCY_STATE',str(Path.home()/'.local/state/claude-code-efficiency-package')))
LOCKS=STATE/'file-locks'
CHECKS=STATE/'checks'

def is_apply(command):
    try:words=shlex.split(command.splitlines()[0])
    except (ValueError,IndexError):return False
    actions=('apply','apply-patch','repair-input','region-replace')
    targets=(str(Path(__file__).resolve()),'claude_code_efficiency.operations')
    return any(words[i] in targets and words[i+1] in actions for i in range(len(words)-1))

def hook(event):
    if event.get('tool_name')!='Bash':return {}
    if event.get('hook_event_name')=='PreToolUse':
        command=event.get('tool_input',{}).get('command','')
        if os.environ.get('EFFICIENCY_PROFILE')!='fused':return {}
        if is_apply(command):return {}
        try:
            lexer=shlex.shlex(command,posix=True,punctuation_chars=';&|<>')
            lexer.whitespace_split=True
            words=list(lexer)
            if words and words[0] in ('cat','head','tail','rg','grep','ls','wc','pwd','find') and not any(w in (';','&&','||','|','>','>>','<','<<') for w in words):return {}
        except ValueError:pass
        # Guidance enforcement, not a shell sandbox: catch obvious mutation bypasses.
        rules=[r'\.(?:write_text|write_bytes)\s*\(',r'\b(?:sed|perl)\s+[^\n;]*\s-i\b',r'\b(?:sed|perl)\s+-i\b',r'\btee\s+(?:-a\s+)?[^\n;]*\.(?:py|md|ts|tsx|js|jsx|json|yaml|yml|go|rs|c|cpp|h|sh|toml)\b',r'(?<![<>])>{1,2}\s*[\"\']?[^\s;|<>]+\.(?:py|md|ts|tsx|js|jsx|json|yaml|yml|go|rs|c|cpp|h|sh|toml)\b',r'\bopen\([^\n]*,[\s]*[\"\'][wax]']
        if any(re.search(rule,command) for rule in rules):
            return {'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':'Action Fusion profile: use python3 -m claude_code_efficiency.operations apply-patch --patch - --then-run "known check" with a raw *** Begin Patch / *** End Patch heredoc in ONE Bash call. JSON apply --spec - is also supported. Direct source-file writes bypass fused validation. This is a workflow constraint, not a permission grant.'}}
        return {}
    if event.get('hook_event_name') not in ('PostToolUse','PostToolUseFailure'):return {}
    session=event.get('session_id','unknown')
    root=ARCHIVES/hashlib.sha256(session.encode()).hexdigest()[:24]
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    # Preserve raw hook-visible results separately; no tool result is rewritten here.
    response=event.get('tool_response',event.get('error',{}))
    ident=uuid.uuid4().hex
    (root/(ident+'.hook.json')).write_text(json.dumps(event,ensure_ascii=False,indent=2))
    command=event.get('tool_input',{}).get('command','')
    if not is_apply(command):return {}
    output='\n'.join(response.get(k,'') for k in ('stdout','stderr') if isinstance(response.get(k),str)) if isinstance(response,dict) else str(response)
    if '[action_fusion:validation]' not in output.splitlines():return {}
    STATS.mkdir(parents=True,exist_ok=True,mode=0o700)
    key=hashlib.sha256(session.encode()).hexdigest()
    path=STATS/(key+'.fusion.json')
    fd=os.open(STATS/(key+'.fusion.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=json.loads(path.read_text()) if path.exists() else {'session_id':session,'calls':{}}
        state['calls'][event.get('tool_use_id',ident)]={'event':event.get('hook_event_name'),'command':event.get('tool_input',{}).get('command'),'record':str(root/(ident+'.hook.json'))}
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2));tmp.replace(path)
    return {}

def archive_input(raw,format):
    folder=STATE/'inputs';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    if folder.is_symlink():raise ValueError('Unsafe input archive directory')
    ident='input_'+hashlib.sha256(format.encode()+b'\0'+raw).hexdigest()
    path=folder/(ident+'.raw')
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:f.write(raw)
    except FileExistsError:
        if path.is_symlink() or path.read_bytes()!=raw:raise ValueError('Corrupt input archive')
    metadata={'format':format,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    meta=folder/(ident+'.meta.json')
    try:
        fd=os.open(meta,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:json.dump(metadata,f)
    except FileExistsError:
        if meta.is_symlink() or json.loads(meta.read_text())!=metadata:raise ValueError('Corrupt input metadata')
    return ident

def read_input(name,format=None):
    if re.fullmatch(r'input_[a-f0-9]{64}',name):
        folder=STATE/'inputs';path=folder/(name+'.raw');meta=folder/(name+'.meta.json')
        if folder.is_symlink() or path.is_symlink() or meta.is_symlink():raise ValueError('Unsafe input archive')
        raw=path.read_bytes();m=json.loads(meta.read_text())
        if len(raw)!=m['bytes'] or hashlib.sha256(raw).hexdigest()!=m['sha256'] or 'input_'+hashlib.sha256(m['format'].encode()+b'\0'+raw).hexdigest()!=name:raise ValueError('Input archive integrity failure')
        if format and m['format']!=format:raise ValueError('Input format mismatch')
        return raw,m['format']
    if format is None:raise ValueError('Expected archived input ID')
    return (sys.stdin.buffer.read() if name=='-' else Path(name).read_bytes()),format

def parse_input(raw,format):
    text=raw.decode('utf-8')
    return json.loads(text) if format=='json' else parse_patch(text)

def apply(spec):
    actions=spec.get('files')
    if not isinstance(actions,list) or not actions:raise ValueError('files must be nonempty')
    targets=[Path(a['path']).resolve() for a in actions]
    if len(set(targets))!=len(targets):raise ValueError('Duplicate target path')
    LOCKS.mkdir(parents=True,exist_ok=True,mode=0o700)
    with ExitStack() as stack:
        for path in sorted(targets):
            lp=LOCKS/(hashlib.sha256(str(path).encode()).hexdigest()+'.lock')
            fd=os.open(lp,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            handle=stack.enter_context(os.fdopen(fd,'a+'))
            fcntl.flock(handle,fcntl.LOCK_EX)
        prepared=[]
        for action,path in zip(actions,targets):
            if 'expected_sha256' in action:
                regions.no_symlinks(action['path'])
                if hashlib.sha256(path.read_bytes()).hexdigest()!=action['expected_sha256']:raise ValueError('Stale region: full file revision changed; reread, never relocate')
            if action.get('must_not_exist') and path.exists():raise ValueError('Add File target already exists')
            if ('content' in action)==('edits' in action):raise ValueError('Specify content OR edits')
            if 'content' in action:
                text=action['content']
                if not isinstance(text,str):raise ValueError('content must be a string')
            else:
                text=path.read_text(encoding='utf-8');edits=action['edits']
                if not isinstance(edits,list) or not edits:raise ValueError('edits must be nonempty')
                changes=[]
                for e in edits:
                    old,new=e['oldText'],e['newText']
                    all_matches=e.get('replace_all',False)
                    if not isinstance(all_matches,bool):raise ValueError('replace_all must be boolean')
                    if not isinstance(old,str) or not isinstance(new,str) or not old or (text.count(old)<1 if all_matches else text.count(old)!=1):raise ValueError('oldText must match exactly once unless replace_all is true')
                    start=0
                    while True:
                        start=text.find(old,start)
                        if start<0:break
                        changes.append((start,start+len(old),new));start+=len(old)
                        if not all_matches:break
                changes.sort()
                if any(changes[i][1]>changes[i+1][0] for i in range(len(changes)-1)):raise ValueError('Overlapping edits')
                for start,end,new in reversed(changes):text=text[:start]+new+text[end:]
            prepared.append((path,text))
        commands=spec.get('then_run',[])
        if isinstance(commands,(str,dict)):commands=[commands]
        if not isinstance(commands,list):raise ValueError('Invalid then_run')
        normalized=[]
        for c in commands:
            c={'command':c} if isinstance(c,str) else c
            if not isinstance(c,dict) or not isinstance(c.get('command'),str):raise ValueError('Invalid validation command')
            timeout=c.get('timeout')
            if timeout is not None and (isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or timeout<=0):raise ValueError('Invalid timeout')
            format=c.get('output_format','auto')
            if format not in checks.FORMATS:raise ValueError('Invalid output_format')
            normalized.append((c['command'],timeout,format))
        hashes={}
        for action,path in zip(actions,targets):
            if 'expected_sha256' in action:
                regions.no_symlinks(action['path'])
                if hashlib.sha256(path.read_bytes()).hexdigest()!=action['expected_sha256']:raise ValueError('Stale region before write')
        for path,text in prepared:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text,encoding='utf-8')
            hashes[path]=hashlib.sha256(path.read_bytes()).hexdigest()
            print(f'Wrote {path}',flush=True)
        if normalized:
            time.sleep(0)
            if any(hashlib.sha256(path.read_bytes()).hexdigest()!=sha for path,sha in hashes.items()):
                print('[then_run:skipped] Target changed after mutation; no validation executed.',file=sys.stderr);return 1
            print('[action_fusion:validation]',flush=True)
        for command,timeout,format in normalized:
            print('Validation command: '+command,flush=True)
            validation_started=time.monotonic()
            code=checks.execute(command,timeout,format,CHECKS)
            print(f'[then_run:{"succeeded" if code==0 else "failed"}] Exit code: {code}; duration_seconds={time.monotonic()-validation_started:.6f}',flush=True)
            if code:return code if code>0 else 1
        return 0

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('hook')
    e=sub.add_parser('apply');e.add_argument('--spec',required=True,help='JSON path, archived input ID or - for stdin')
    q=sub.add_parser('apply-patch');q.add_argument('--patch',required=True,help='Exact-context patch path, archived input ID or -')
    q.add_argument('--then-run');q.add_argument('--timeout',type=float);q.add_argument('--output-format',choices=checks.FORMATS,default='auto')
    rr=sub.add_parser('region-read');rr.add_argument('--file',required=True);rr.add_argument('--start',type=int,required=True);rr.add_argument('--end',type=int,required=True)
    rp=sub.add_parser('region-replace');rp.add_argument('id');rp.add_argument('--replacement',required=True);rp.add_argument('--then-run');rp.add_argument('--timeout',type=float);rp.add_argument('--output-format',choices=checks.FORMATS,default='auto')
    fix=sub.add_parser('repair-input');fix.add_argument('id');fix.add_argument('--old',required=True);fix.add_argument('--new',required=True)
    c=sub.add_parser('check-recall');c.add_argument('id');c.add_argument('--stream',default='stdout');c.add_argument('--offset',type=int,default=0);c.add_argument('--limit',type=int,default=8192)
    a=p.parse_args()
    if a.action=='hook':
        try:print(json.dumps(hook(json.load(sys.stdin)),ensure_ascii=False))
        except Exception as exc:print(f'Reporting hook failed open: {exc}',file=sys.stderr)
        return 0
    try:
        if a.action=='check-recall':print(json.dumps(checks.recall(CHECKS,a.id,a.stream,a.offset,a.limit),ensure_ascii=False));return 0
        if a.action in ('region-read','region-replace') and os.environ.get('EFFICIENCY_REGIONS',str(int(settings.load()['regions']['enabled'])))!='1':raise ValueError('Region helpers disabled for this experimental condition')
        if a.action=='region-read':
            ident,meta,text=regions.store(STATE/'regions',a.file,a.start,a.end)
            print('[region] '+json.dumps({'id':ident,**meta}),flush=True)
            sys.stdout.write(text);return 0
        if a.action=='region-replace':
            raw,_=read_input(a.replacement,'replacement');ident=archive_input(raw,'replacement')
            print(f'[input_archive] id={ident}; format=replacement; bytes={len(raw)}',flush=True)
            spec={'files':[regions.replacement(STATE/'regions',a.id,raw.decode('utf-8'))]}
            if a.then_run:spec['then_run']={'command':a.then_run,'timeout':a.timeout,'output_format':a.output_format}
            return apply(spec)
        if a.action=='repair-input':
            raw,format=read_input(a.id)
            text=raw.decode('utf-8')
            if not a.old or text.count(a.old)!=1:raise ValueError('Repair old text must match exactly once')
            repaired=text.replace(a.old,a.new,1).encode('utf-8');ident=archive_input(repaired,format)
            print(f'[input_archive] id={ident}; original={a.id}; source files NOT modified',flush=True)
            spec=parse_input(repaired,format)
            if not isinstance(spec,dict) or not isinstance(spec.get('files'),list) or not spec['files']:raise ValueError('Expected nonempty files specification')
            print('[input_repair:syntax_valid] Review and explicitly apply this ID; file anchors not yet validated.')
            return 0
        format='patch' if a.action=='apply-patch' else 'json'
        raw,format=read_input(a.patch if format=='patch' else a.spec,format)
        ident=archive_input(raw,format)
        print(f'[input_archive] id={ident}; format={format}; bytes={len(raw)}',flush=True)
        spec=parse_input(raw,format)
        if a.action=='apply-patch' and a.then_run:
            spec['then_run']={'command':a.then_run,'timeout':a.timeout,'output_format':a.output_format}
        return apply(spec)
    except Exception as exc:
        print(f'{type(exc).__name__}: {exc}\n[then_run:skipped] Validation was not reached or did not complete.',file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
