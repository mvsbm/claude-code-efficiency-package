#!/usr/bin/env python3
"""Strict runtime configuration. Permissions and evidence integrity are not knobs."""
import argparse,copy,hashlib,json,os
from pathlib import Path

DEFAULTS={
 'version':1,'profile':'fused',
 'regions':{'enabled':True},
 'workflow':{'read_reuse_hints':True},
 'completion':{'require_commit':False,'max_reminders':2},
 'checks':{'compact':True,'max_diagnostics':40,'max_bytes':7680}
}
BOUNDS={'completion.max_reminders':(1,3),'checks.max_diagnostics':(1,1000),'checks.max_bytes':(256,65536)}

def merge(default,user,prefix=''):
 if not isinstance(user,dict):raise ValueError('Configuration must be an object: '+prefix)
 result=copy.deepcopy(default)
 for key,value in user.items():
  name=prefix+key
  if key not in default:raise ValueError('Unknown setting: '+name)
  old=default[key]
  if isinstance(old,dict):result[key]=merge(old,value,name+'.');continue
  if isinstance(old,bool):
   if type(value) is not bool:raise ValueError('Expected boolean: '+name)
  elif isinstance(old,int):
   if type(value) is not int:raise ValueError('Expected integer: '+name)
   if name in BOUNDS and not BOUNDS[name][0]<=value<=BOUNDS[name][1]:raise ValueError('Out of range: '+name)
  elif not isinstance(value,str):raise ValueError('Expected string: '+name)
  result[key]=value
 return result

def load(path=None):
 path=path or os.environ.get('EFFICIENCY_CONFIG')
 config=merge(DEFAULTS,json.loads(Path(path).read_text()) if path else {})
 if config['version']!=1:raise ValueError('Unsupported config version')
 if config['profile'] not in ('fused','native','before'):raise ValueError('Invalid profile')
 return config

def identity(config):return hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def exports(config):
 return {'EFFICIENCY_PROFILE':config['profile'],'EFFICIENCY_REGIONS':str(int(config['regions']['enabled'])),'EFFICIENCY_REQUIRE_COMMIT':str(int(config['completion']['require_commit']))}

def main():
 p=argparse.ArgumentParser();p.add_argument('--config');p.add_argument('--export',action='store_true');p.add_argument('--flat',action='store_true');a=p.parse_args();config=load(a.config)
 if a.export:
  for key,value in exports(config).items():print(key+'='+value)
 elif a.flat:print(json.dumps(config,indent=2))
 else:print(json.dumps({'resolved':config,'sha256':identity(config)},indent=2))
if __name__=='__main__':
 try:main()
 except Exception as exc:print('Invalid efficiency config: '+str(exc));raise SystemExit(2)
