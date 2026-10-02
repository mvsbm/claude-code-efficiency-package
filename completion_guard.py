#!/usr/bin/env python3
"""Opt-in bounded Stop reminder for an explicitly required commit. Never mutates Git."""
import fcntl,hashlib,json,os,subprocess,sys
from pathlib import Path
import settings

def evaluate(event,env=None):
 env=os.environ if env is None else env
 config=settings.load(env.get('EFFICIENCY_CONFIG'))['completion']
 if env.get('EFFICIENCY_REQUIRE_COMMIT',str(int(config['require_commit'])))!='1':return {}
 cwd=Path(event.get('cwd',os.getcwd()));base=env.get('EFFICIENCY_BASE_COMMIT')
 if not base:raise ValueError('Explicit base commit required for completion guard')
 def git(*args):return subprocess.check_output(['git','-C',str(cwd),*args],text=True,stderr=subprocess.PIPE,timeout=3)
 head=git('rev-parse','HEAD').strip();base=git('rev-parse',base+'^{commit}').strip()
 problems=[]
 if head==base or not git('diff','--name-only',base,'HEAD').strip():problems.append('required implementation commit is missing')
 if git('status','--porcelain').strip():problems.append('uncommitted/untracked changes remain; review task changes and temporary files')
 if not problems:return {}
 root=Path(env.get('EFFICIENCY_STATE',str(Path.home()/'.local/state/claude-code-efficiency-package')))/'completion';root.mkdir(parents=True,exist_ok=True,mode=0o700)
 if root.is_symlink():raise ValueError('Unsafe completion state')
 key=hashlib.sha256(str(event.get('session_id','unknown')).encode()).hexdigest();path=root/(key+'.json')
 fd=os.open(root/(key+'.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'a+') as f:
  fcntl.flock(f,fcntl.LOCK_EX)
  if path.is_symlink():raise ValueError('Unsafe completion record')
  state=json.loads(path.read_text()) if path.exists() else {'blocks':0}
  if state['blocks']>=config['max_reminders']:
   state['unresolved_contract']=problems;path.write_text(json.dumps(state));return {}
  state['blocks']+=1;state['problems']=problems;state['read_only_guard']=True;path.write_text(json.dumps(state))
 return {'decision':'block','reason':'Task completion contract: '+ '; '.join(problems)+'. Finish necessary validation and explicitly commit only completed task changes before finishing. Do NOT commit incomplete code to satisfy this reminder. If genuinely blocked, report the blocker honestly. This read-only reminder does not prove tests passed or authorize extra mutations.'}

if __name__=='__main__':
 try:print(json.dumps(evaluate(json.load(sys.stdin))))
 except Exception as exc:print('Completion guard unavailable: '+str(exc),file=sys.stderr);print('{}')
