"""Source-labelled regression evaluation; does not claim external benchmark scores."""
import argparse
import json
from pathlib import Path
import privacy
import rag


def evaluate(root,db,cases):
    root=Path(root);privacy.require_clean(cases)
    if not isinstance(cases,list) or not cases:raise ValueError('Evaluation cases must be a nonempty list')
    rag.build(root,db);rows=[];source_cases=source_passes=0;leaks=0
    for case in cases:
        if not isinstance(case.get('id'),str) or not isinstance(case.get('query'),str):raise ValueError('Case requires id/query')
        filters={k:case[k] for k in ['project','platform','account','topic','memory_type'] if case.get(k) is not None}
        hits=rag.retrieve(root,db,case['query'],case.get('limit',8),**filters);expected=case.get('expected',{})
        if not isinstance(expected,dict) or not expected or not any(k in expected for k in ('paths_all','empty','min_chunks','contains_all','roles','statuses','unknown_speakers','unknown_times')):raise ValueError('Case must assert expected behavior')
        paths={h['path'] for h in hits};ok=True;checks={}
        if 'paths_all' in expected:
            source_cases+=1;checks['sources']=all(p in paths for p in expected['paths_all']);source_passes+=int(checks['sources'])
        if expected.get('empty'):checks['empty']=not hits
        if 'min_chunks' in expected:checks['chunks']=len({rag.chunk_key(h) for h in hits})>=expected['min_chunks']
        if 'contains_all' in expected:checks['text']=all(t in '\n'.join(h['text'] for h in hits) for t in expected['contains_all'])
        if 'roles' in expected:checks['roles']=bool(hits) and all(h['role'] in expected['roles'] for h in hits)
        if 'statuses' in expected:checks['statuses']=bool(hits) and all(h['status'] in expected['statuses'] for h in hits)
        if expected.get('unknown_speakers'):checks['unknown_speakers']=bool(hits) and all('unknown' in h.get('sender','unknown') for h in hits)
        if expected.get('unknown_times'):checks['unknown_times']=bool(hits) and all(h['timestamp'] is None for h in hits)
        checks['scope']=all(all(h.get(k)==v for k,v in filters.items() if k not in {'topic','memory_type'}) for h in hits)
        leaks+=int(not checks['scope']);checks['safe']=not any(privacy.findings(h['text']) for h in hits)
        if not checks:raise ValueError('Case must assert expected behavior')
        ok=all(checks.values());rows.append({'id':case['id'],'passed':ok,'checks':checks,'hits':len(hits)})
    passed=sum(r['passed'] for r in rows)
    return {'version':1,'mode':'keyword','total':len(rows),'passed':passed,'pass_rate':passed/len(rows),'source_hit_rate':source_passes/source_cases if source_cases else None,'scope_leaks':leaks,'cases':rows,'coverage_note':'Curated source-labelled regressions; not LongMemEval/LoCoMo or overall memory accuracy'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--db',required=True);p.add_argument('--cases',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    report=evaluate(a.root,a.db,json.loads(Path(a.cases).read_text()));Path(a.output).write_text(json.dumps(report,indent=2)+'\n');print('Evaluation: '+str(report['passed'])+'/'+str(report['total'])+' passed')
    if report['passed']!=report['total']:raise SystemExit(2)
if __name__=='__main__':main()
