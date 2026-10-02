#!/usr/bin/env python3
"""Price successful native API responses; report gaps instead of inventing usage."""
import argparse
import hashlib
import json
import math
from pathlib import Path

KEYS=('input','write_5m','write_1h','read','output')

def count(value):
    if isinstance(value,bool) or not isinstance(value,int) or value<0:raise ValueError('Invalid usage counter')
    return value

def categories(usage):
    result={k:count(usage[f]) for k,f in [('input','input_tokens'),('read','cache_read_input_tokens'),('output','output_tokens')]}
    total=count(usage.get('cache_creation_input_tokens',0))
    split=usage.get('cache_creation')
    if total and not isinstance(split,dict):raise ValueError('Cache write TTL breakdown missing')
    result['write_5m']=count((split or {}).get('ephemeral_5m_input_tokens',0))
    result['write_1h']=count((split or {}).get('ephemeral_1h_input_tokens',0))
    if result['write_5m']+result['write_1h']!=total:raise ValueError('Cache write TTL breakdown inconsistent')
    return result

def price(usage,model,table):
    tokens=categories(usage);rates=table['models'][model]
    if any(isinstance(rates[k],bool) or not isinstance(rates[k],(int,float)) or not math.isfinite(rates[k]) or rates[k]<0 for k in KEYS):raise ValueError('Invalid price table')
    costs={k:tokens[k]*rates[k]/1_000_000 for k in KEYS}
    return tokens,costs

def analyze(root,table):
    root=Path(root).resolve();rows=[];issues=[];seen={};matched=set()
    try:provenance=json.loads((root/'accounting-provenance.json').read_text())
    except (OSError,ValueError):provenance={};issues.append('Endpoint provenance missing; direct API rates are unverified')
    if provenance and provenance.get('endpoint_host')!='api.anthropic.com' and not provenance.get('synthetic'):issues.append('Not a direct API endpoint: do not interpret list-rate estimates as billed cost')
    index=root/'index.jsonl'
    if not index.exists():return {'issues':['Native index.jsonl missing'],'cost_complete':False,'requests':[],'estimated_known_usd':0}
    def local(name):
        path=Path(name)
        if not path.is_absolute():path=root/path
        resolved=path.resolve()
        if not resolved.is_relative_to(root) or path.is_symlink():raise ValueError('Body path outside archive/symlink')
        return resolved
    for number,line in enumerate(index.read_text().splitlines(),1):
        try:
            row=json.loads(line);request=local(row['request_file']);response=local(row['response_file'])
            raw=response.read_bytes();ident=row.get('request_id') or row.get('message_id')
            if not ident:raise ValueError('Request/message identity absent')
            signature=hashlib.sha256(raw).hexdigest()
            if ident in seen:
                if seen[ident]!=signature:raise ValueError('Conflicting duplicate response')
                continue
            seen[ident]=signature;matched.add(request)
            body=json.loads(raw);params=json.loads(request.read_bytes());model=row.get('model')
            if body.get('model')!=model:raise ValueError('Model identity mismatch')
            # Never silently apply regular pricing to paid server tools/speed/geo tiers.
            usage=body['usage']
            server=usage.get('server_tool_use',{})
            if not isinstance(server,dict):raise ValueError('Unknown server-tool usage')
            if any(v for v in server.values()) or params.get('speed')=='fast' or params.get('inference_geo','global')!='global' or usage.get('inference_geo','global') not in ('global','') or usage.get('service_tier','standard')!='standard':raise ValueError('Unsupported billing modifier/server tool')
            tokens,costs=price(usage,model,table)
            rows.append({'request_id':ident,'model':model,'query_source':row.get('query_source'),'tokens':tokens,'estimated_usd':costs,'estimated_total_usd':sum(costs.values())})
        except (ValueError,KeyError,TypeError,OSError) as exc:issues.append(f'index line {number}: {type(exc).__name__}: {exc}')
    if not rows:issues.append('No priceable successful responses')
    unmatched=sorted(str(p) for p in root.glob('*.request.json') if p.resolve() not in matched)
    if unmatched:issues.append('Unpaired request attempts: billed usage unknown; inspect native telemetry/errors and reconcile billing')
    return {'synthetic':bool(provenance.get('synthetic')),'endpoint_host':provenance.get('endpoint_host'),'basis':table['basis'],'pricing_checked':table['checked'],'pricing_source':table['source'],'cost_complete':not issues,'coverage':'Successful native response bodies; not an invoice. Thinking content is redacted by Claude Code; output usage still priced.','issues':issues,'unpaired_requests':unmatched,'requests':rows,'tokens':{k:sum(r['tokens'][k] for r in rows) for k in KEYS},'estimated_usd_by_category':{k:sum(r['estimated_usd'][k] for r in rows) for k in KEYS},'estimated_known_usd':sum(r['estimated_total_usd'] for r in rows)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--pricing',type=Path,default=Path(__file__).with_name('pricing.json'));p.add_argument('--synthetic',action='store_true');a=p.parse_args()
    report=analyze(a.directory,json.loads(a.pricing.read_text()));report['synthetic']=a.synthetic or report.get('synthetic',False)
    if report['synthetic']:report['coverage']='FAKE API protocol evidence; not actual spend or a savings benchmark'
    print(json.dumps(report,indent=2));raise SystemExit(0 if report['cost_complete'] else 1)
