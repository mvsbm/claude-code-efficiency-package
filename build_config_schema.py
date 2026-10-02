#!/usr/bin/env python3
"""Generate the partial-override JSON Schema from the runtime validator."""
import json
from pathlib import Path
import settings

def schema(value,prefix=''):
 if isinstance(value,dict):return {'type':'object','additionalProperties':False,'properties':{k:schema(v,prefix+k+'.') for k,v in value.items()}}
 name=prefix.rstrip('.')
 result={'type':'boolean' if isinstance(value,bool) else 'integer' if isinstance(value,int) else 'string','default':value}
 if name in settings.BOUNDS:result.update(minimum=settings.BOUNDS[name][0],maximum=settings.BOUNDS[name][1])
 if name=='version':result['const']=1
 if name=='profile':result['enum']=['fused','native','before']
 return result
if __name__=='__main__':
 result={'$schema':'https://json-schema.org/draft/2020-12/schema','title':'Claude Code Efficiency configuration v1',**schema(settings.DEFAULTS),'description':'Partial overrides allowed. Permissions, evidence integrity and failure preservation are not configurable.'}
 Path(__file__).with_name('config.schema.json').write_text(json.dumps(result,indent=2)+'\n')
