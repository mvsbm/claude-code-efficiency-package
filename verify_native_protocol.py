#!/usr/bin/env python3
"""Native Claude executor with deterministic fake API. No real model/generation."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from accounting import analyze

ROOT=Path(__file__).resolve().parent
HELPER=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'claude-code-efficiency-package/operations.py'
p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True,mode=0o700)
reports={}
for format,grant in [('json',True),('json',False),('patch',True),('patch',False),('region',True),('region',False),('completion',True)]:
    case=out/(('granted' if grant else 'denied')+('_'+format if format!='json' else ''));case.mkdir();work=case/'workspace';work.mkdir();seen=[]
    spec={'files':[{'path':str(work/'fixed.py'),'content':'value = 42\n'}],'then_run':{'command':'test -f fixed.py && touch validated','timeout':5}}
    command=f"python3 {HELPER} apply --spec - <<'EFFICIENCY_JSON'\n"+json.dumps(spec)+'\nEFFICIENCY_JSON'
    if format=='patch':
        command=f"python3 {HELPER} apply-patch --patch - --then-run 'test -f fixed.py && touch validated' --timeout 5 <<'EFFICIENCY_PATCH'\n*** Begin Patch\n*** Add File: {work/'fixed.py'}\n+value = 42\n*** End Patch\nEFFICIENCY_PATCH"
    if format=='region':
        (work/'fixed.py').write_text('value = 0\n')
        from regions import store
        ident,_,_=store(case/'state/regions',work/'fixed.py',1,1)
        command=f"python3 {HELPER} region-replace {ident} --replacement - --then-run 'test -f fixed.py && touch validated' --timeout 5 <<'CODE'\nvalue = 42\nCODE"
    if format=='completion':
        for args in [('init','-q'),('config','user.name','Synthetic'),('config','user.email','synthetic@invalid')]:subprocess.run(['git','-C',str(work),*args],check=True)
        (work/'base.txt').write_text('base\n');subprocess.run(['git','-C',str(work),'add','.'],check=True);subprocess.run(['git','-C',str(work),'commit','-qm','base'],check=True)
        base_commit=subprocess.check_output(['git','-C',str(work),'rev-parse','HEAD'],text=True).strip()
    class Fake(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));seen.append(body)
            first=len(seen)==1 or (format=='completion' and len(seen)==3)
            emitted_command=command if len(seen)!=3 or format!='completion' else f'git -C {work} add fixed.py validated && git -C {work} commit -m completed'
            block={'type':'tool_use','id':'fake_call','name':'Bash','input':{}} if first else {'type':'text','text':''}
            delta={'type':'input_json_delta','partial_json':json.dumps({'command':emitted_command,'description':'Apply repair and validate'})} if first else {'type':'text_delta','text':'Synthetic native test complete.'}
            message={'id':'msg_fake_'+str(len(seen)),'type':'message','role':'assistant','model':'claude-sonnet-5-5','content':[],'stop_reason':None,'stop_sequence':None,'usage':{'input_tokens':1,'output_tokens':0,'cache_read_input_tokens':0,'cache_creation_input_tokens':0}}
            events=[{'type':'message_start','message':message},{'type':'content_block_start','index':0,'content_block':block},{'type':'content_block_delta','index':0,'delta':delta},{'type':'content_block_stop','index':0},{'type':'message_delta','delta':{'stop_reason':'tool_use' if first else 'end_turn','stop_sequence':None},'usage':{'output_tokens':1}},{'type':'message_stop'}]
            raw=''.join('event: '+e['type']+'\ndata: '+json.dumps(e)+'\n\n' for e in events).encode()
            self.send_response(200);self.send_header('request-id','req_fake_'+str(len(seen)));self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Fake);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    env=os.environ.copy();env.update(ANTHROPIC_BASE_URL=f'http://127.0.0.1:{server.server_port}',ANTHROPIC_API_KEY='synthetic-only',ANTHROPIC_AUTH_TOKEN='synthetic-only',EFFICIENCY_STATE=str(case/'state'),EFFICIENCY_MODEL='claude-sonnet-5-5',EFFICIENCY_ACCOUNTING='1',EFFICIENCY_ACCOUNTING_SYNTHETIC='1',CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
    if format=='completion':env.update(EFFICIENCY_REQUIRE_COMMIT='1',EFFICIENCY_BASE_COMMIT=base_commit)
    start=time.monotonic()
    try:
        with (case/'chat.stream.jsonl').open('w') as log,(case/'stderr').open('w') as err:
            code=subprocess.run([str(Path.home()/'.local/bin/claude-code-efficiency'),'-p','--verbose','--output-format','stream-json','--no-session-persistence','--max-turns','4','--permission-mode','default','--allowedTools','Read,Glob,Grep,Bash' if grant else 'Read','--','Synthetic executor test. Execute only when permission allows. Stop if denied.'],cwd=work,env=env,stdout=log,stderr=err,timeout=20).returncode
        tools={t['name'] for t in seen[0].get('tools',[])} if seen else set()
        fusion=sum(len(json.loads(f.read_text()).get('calls',{})) for f in (case/'state/live').glob('*.fusion.json'))
        reports[case.name]={'exit_code':code,'elapsed_seconds':time.monotonic()-start,'synthetic_usage_not_benchmark':True,'tools':sorted(tools),'fused_calls':fusion,'mutated':(work/'fixed.py').exists() and (work/'fixed.py').read_text()=='value = 42\n','validated':(work/'validated').exists(),'system_guidance_present':'Efficiency workflow:' in json.dumps(seen[0].get('system')) if seen else False}
        traces=list((case/'state').glob('api-*'))
        accounting=analyze(traces[0],json.loads((ROOT/'pricing.json').read_text())) if len(traces)==1 else {'cost_complete':False,'issues':['Trace directory missing']}
        accounting['synthetic']=True;(case/'SYNTHETIC_ACCOUNTING.json').write_text(json.dumps(accounting,indent=2))
        reports[case.name]['native_accounting_complete']=accounting['cost_complete']
        reports[case.name]['accounted_requests']=len(accounting.get('requests',[]))
        reports[case.name]['accounting_issues']=accounting.get('issues')
    finally:server.shutdown();server.server_close();thread.join(timeout=2)
g,d=reports['granted'],reports['denied']
checks={'native_palette_excludes_mutation_bypass':all('Write' not in r['tools'] and 'Edit' not in r['tools'] for r in reports.values()),'approved_bash_fuses_and_validates':g['mutated'] and g['validated'] and g['fused_calls']==1,'bash_denial_prevents_execution':not d['mutated'] and not d['validated'] and d['fused_calls']==0,'system_prompt_loaded':all(r['system_guidance_present'] for r in reports.values()),'native_usage_capture':all(r['native_accounting_complete'] and r['accounted_requests']==(4 if name=='granted_completion' else 2) for name,r in reports.items()),'approved_patch_fuses_and_validates':reports['granted_patch']['mutated'] and reports['granted_patch']['validated'] and reports['granted_patch']['fused_calls']==1,'patch_permission_denial_prevents_execution':not reports['denied_patch']['mutated'] and not reports['denied_patch']['validated'] and reports['denied_patch']['fused_calls']==0,'approved_region_fuses_and_validates':reports['granted_region']['mutated'] and reports['granted_region']['validated'] and reports['granted_region']['fused_calls']==1,'region_permission_denial_prevents_execution':not reports['denied_region']['mutated'] and not reports['denied_region']['validated'] and reports['denied_region']['fused_calls']==0,'completion_guard_blocks_then_allows_explicit_commit':reports['granted_completion']['accounted_requests']==4 and bool(list((out/'granted_completion/state/completion').glob('*.json'))) and subprocess.check_output(['git','-C',str(out/'granted_completion/workspace'),'status','--porcelain'],text=True)==''}
report={'checks':checks,'cases':reports};(out/'REPORT.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));raise SystemExit(0 if all(checks.values()) else 1)
