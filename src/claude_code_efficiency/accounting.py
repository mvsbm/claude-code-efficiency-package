#!/usr/bin/env python3
"""Report token counters from captured API response bodies; never estimate cost."""
import argparse
import hashlib
import json
from pathlib import Path

COUNTERS=('input_tokens','cache_read_input_tokens','cache_creation_input_tokens','output_tokens')
TTL_COUNTERS=('ephemeral_5m_input_tokens','ephemeral_1h_input_tokens')


def count(value):
    if isinstance(value,bool) or not isinstance(value,int) or value<0:
        raise ValueError('Invalid usage counter')
    return value


def usage_counts(usage):
    counters={key:count(usage[key]) for key in COUNTERS}
    split=usage.get('cache_creation')
    if split is None:
        ttl={key:0 for key in TTL_COUNTERS} if counters['cache_creation_input_tokens']==0 else None
    else:
        if not isinstance(split,dict):
            raise ValueError('Invalid cache write TTL breakdown')
        ttl={key:count(split[key]) for key in TTL_COUNTERS}
        if sum(ttl.values())!=counters['cache_creation_input_tokens']:
            raise ValueError('Cache write TTL breakdown inconsistent')
    return counters,ttl


def analyze(root):
    root=Path(root).resolve();rows=[];issues=[];seen={};matched=set()
    try:provenance=json.loads((root/'accounting-provenance.json').read_text())
    except (OSError,ValueError):provenance={};issues.append('Endpoint provenance missing')
    if provenance and provenance.get('endpoint_host')!='api.anthropic.com' and not provenance.get('synthetic'):
        issues.append('Not a direct Anthropic API endpoint; usage schema is unverified')
    index=root/'index.jsonl'
    if not index.exists():
        return {'issues':['Native index.jsonl missing'],'archive_consistent':False,'requests':[],
                'captured_token_usage':None,'captured_cache_creation_by_ttl':None}

    def local(name):
        path=Path(name)
        if not path.is_absolute():path=root/path
        resolved=path.resolve()
        if not resolved.is_relative_to(root) or path.is_symlink():
            raise ValueError('Body path outside archive/symlink')
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
            body=json.loads(raw);json.loads(request.read_bytes());model=row.get('model')
            if body.get('model')!=model:raise ValueError('Model identity mismatch')
            counters,ttl=usage_counts(body['usage'])
            rows.append({'request_id':ident,'model':model,'query_source':row.get('query_source'),
                         'usage':counters,'cache_creation_by_ttl':ttl})
        except (ValueError,KeyError,TypeError,OSError) as exc:
            issues.append(f'index line {number}: {type(exc).__name__}: {exc}')

    if not rows:issues.append('No valid response usage captured')
    unmatched=sorted(str(p) for p in root.glob('*.request.json') if p.resolve() not in matched)
    if unmatched:issues.append('Unpaired request attempts; usage is unknown')
    totals={key:sum(r['usage'][key] for r in rows) for key in COUNTERS} if rows else None
    ttl_totals=({key:sum(r['cache_creation_by_ttl'][key] for r in rows) for key in TTL_COUNTERS}
                if rows and all(r['cache_creation_by_ttl'] is not None for r in rows) else None)
    return {'synthetic':bool(provenance.get('synthetic')),'endpoint_host':provenance.get('endpoint_host'),
            'coverage':'Captured successful response bodies only; failed, unpaired, or in-flight requests and invoice adjustments are not represented.',
            'archive_consistent':not issues,'issues':issues,'unpaired_requests':unmatched,
            'requests':rows,'captured_token_usage':totals,'captured_cache_creation_by_ttl':ttl_totals}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--synthetic',action='store_true');a=p.parse_args()
    report=analyze(a.directory)
    if a.synthetic:
        report['synthetic']=True
        report['coverage']='Synthetic protocol data; not measured production usage.'
    print(json.dumps(report,indent=2));raise SystemExit(0 if report['archive_consistent'] else 1)
