#!/usr/bin/env python3
"""Run pending private-memory requests on GitHub-hosted runners."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import memory_bridge
import rag
import privacy


def request_events(item):
    """Return one or more event payloads while preserving the v1 single-event form."""
    has_one = 'event' in item
    has_many = 'events' in item
    if has_one and has_many:
        raise ValueError('Use event or events, not both')
    if has_many:
        events = item['events']
        if not isinstance(events, list) or not 1 <= len(events) <= 100:
            raise ValueError('events must contain 1..100 event objects')
        if not all(isinstance(event, dict) for event in events):
            raise ValueError('events must contain objects')
        return events
    if has_one:
        if not isinstance(item['event'], dict):
            raise ValueError('event must be an object')
        return [item['event']]
    return []


def validate_request(item, ident):
    if not re.fullmatch(r'[a-f0-9]{32}', ident) or item.get('id') != ident:
        raise ValueError('Request ID/path mismatch')
    operation=item.get('operation','recall')
    if operation not in {'recall','write','sync','forget','graph','reflect','checkpoint','resume','conflicts','evaluate'}:
        raise ValueError('Unsupported operation')
    if operation in {'recall','sync'}:
        if not isinstance(item.get('query'),str) or not 1 <= len(item['query'].strip()) <= 2000:
            raise ValueError('Query must be 1..2000 characters')
        if memory_bridge.SECRET.search(item['query']): raise ValueError('Possible credential in query')
    if operation in {'graph','reflect','checkpoint','resume'} and not item.get('project'):
        raise ValueError('Operation requires explicit project')
    if operation=='evaluate' and (not isinstance(item.get('cases_path'),str) or not re.fullmatch(r'memory/evaluation/[A-Za-z0-9_.-]+\.json',item['cases_path'])):
        raise ValueError('Evaluation requires a safe memory/evaluation JSON path')
    if operation in {'write','sync','forget'} and not request_events(item):
        raise ValueError('Write-like operations require event or events')
    if item.get('created_at'): memory_bridge.instant(item['created_at'])
    if item.get('mode', 'hybrid') not in {'keyword', 'semantic', 'hybrid'}:
        raise ValueError('Invalid query mode')
    if isinstance(item.get('limit', 8), bool) or not isinstance(item.get('limit', 8), int) or not 1 <= item.get('limit', 8) <= 50:
        raise ValueError('Invalid limit')
    if not isinstance(item.get('budget', 12000), int) or not 300 <= item.get('budget', 12000) <= 50000:
        raise ValueError('Invalid context budget')
    for key in ('project', 'platform', 'account', 'topic', 'memory_type'):
        if item.get(key) is not None and (not isinstance(item[key], str) or len(item[key]) > 200):
            raise ValueError('Invalid scope field')
    privacy.require_clean(item)
    return item


def pending(root):
    root = Path(root)
    items = []
    for path in sorted((root/'memory/requests').glob('*.json')):
        item = validate_request(json.loads(path.read_text()), path.stem)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result = root/'memory/results'/(path.stem+'.json')
        if result.exists():
            if json.loads(result.read_text()).get('request_sha256') != digest:
                raise ValueError('Processed request was modified; use a fresh request ID')
            continue
        items.append((item, digest))
    return items


def write_event(root,item,event=None,index=0,total=1,kind=None):
    event=dict(event if event is not None else item.get('event',{}))
    suffix=':event' if total == 1 else ':event:'+str(index)
    ident=hashlib.sha256((item['id']+suffix).encode()).hexdigest()[:32]
    old=next((Path(root)/'memory/events').glob('*/'+ident+'.json'),None)
    timestamp=json.loads(old.read_text())['created_at'] if old else item.get('created_at',dt.datetime.now(dt.timezone.utc).isoformat())
    event.update(version=1,id=ident,created_at=timestamp)
    event.setdefault('supersedes',[])
    if kind:event['kind']=kind
    path=memory_bridge.save(root,event)
    return dict(event_id=ident,path=path.relative_to(root).as_posix())


def write_events(root,item,kind=None):
    events=request_events(item)
    rows=[write_event(root,item,event,index,len(events),kind) for index,event in enumerate(events)]
    return rows[0] if len(rows) == 1 else dict(count=len(rows),events=rows)


def run(root, db, model_dir):
    import manager
    root=Path(root).resolve()
    jobs=pending(root)
    # Fail before writing if any incoming event is invalid; prevent partial batches.
    for item,_ in jobs:
        if item.get('operation') in {'write','sync','forget'}:
            for raw in request_events(item):
                candidate=dict(raw);candidate.update(version=1,id='0'*32,created_at=item.get('created_at',dt.datetime.now(dt.timezone.utc).isoformat()));candidate.setdefault('supersedes',[])
                if item['operation']=='forget':candidate['kind']='forget'
                memory_bridge.validate(candidate)
    if not jobs:return 0
    memory_bridge.load(root)
    prepared={}
    for item,_ in jobs:
        op=item.get('operation','recall')
        if op in {'write','sync','forget'}:
            prepared[item['id']]=write_events(root,item,'forget' if op=='forget' else None)
        elif op=='checkpoint':
            payload=dict(item.get('checkpoint',{}));payload['project']=item['project']
            prepared[item['id']]=manager.checkpoint(root,item['id'],payload)
    recalls=[item for item,_ in jobs if item.get('operation','recall') in {'recall','sync'}]
    provider=None
    if recalls:
        rag.build(root,db)
        semantic_jobs=[item for item in recalls if item.get('mode','hybrid')!='keyword']
        if semantic_jobs:
            from embeddings import LocalE5,download
            from semantic import embed
            directory=Path(model_dir)
            if not (directory/'manifest.json').exists():download(directory)
            provider=LocalE5(directory)
            scopes=[{key:item.get(key) for key in ('project','platform','account','topic','memory_type')} for item in semantic_jobs]
            scopes=None if any(all(v is None for v in scope.values()) for scope in scopes) else scopes
            def progress(done,total):
                if done%512==0 or done==total:print(f'Encoding {done}/{total}',flush=True)
            report=embed(root,db,provider,batch_size=64,progress=progress,scopes=scopes)
            print(f"Semantic coverage: {report['coverage']}; reused {report['cached']} chunks",flush=True)
    out=root/'memory/results';out.mkdir(parents=True,exist_ok=True)
    for item,digest in jobs:
        op=item.get('operation','recall')
        result=dict(id=item['id'],request_sha256=digest,
                    generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                    execution='github-actions',operation=op,
                    base_commit=os.environ.get('GITHUB_SHA','unknown'),
                    workflow_url=os.environ.get('MEMORY_RUN_URL','unknown'))
        if op in {'recall','sync'}:
            filters={key:item.get(key) for key in ('project','platform','account','topic','memory_type')}
            mode=item.get('mode','hybrid')
            if mode=='keyword':hits=rag.retrieve(root,db,item['query'],item.get('limit',8),**filters)
            else:
                from semantic import retrieve
                hits=retrieve(root,db,item['query'],provider,mode,item.get('limit',8),**filters)
            result.update(mode=mode,filters=filters,results=hits,index_snapshot=rag.snapshot(root),
                          context=rag.bundle(hits,item.get('budget',12000)))
            if op=='sync':result['write']=prepared[item['id']]
        elif op in {'write','forget','checkpoint'}:result['result']=prepared[item['id']]
        elif op=='resume':result['result']=manager.resume(root,item['project'],item.get('task_id'))
        elif op=='graph':result['result']=manager.graph(root,item['project'],item.get('entity'),item.get('hops',1))
        elif op=='conflicts':result['result']=memory_bridge.conflicts(memory_bridge.load(root))
        elif op=='evaluate':
            from evaluate import evaluate
            evaluation_db=Path(db).with_name(Path(db).stem+'.evaluation.sqlite3')
            result['result']=evaluate(root,evaluation_db,json.loads((root/item['cases_path']).read_text()))
        elif op=='reflect':
            result['result']=manager.reflect(root,item['project'])
            if item.get('save'):
                rows=result['result']['items']
                draft=dict(version=1,kind='fact',status='candidate',
                           text='Evidence consolidation:\n'+'\n'.join('['+e['status']+'] '+e['text'] for e in rows)[:10000],
                           scope=dict(project=item['project'],platform='memory-cloud',account='unknown'),
                           source=dict(reference='memory/results/'+item['id']+'.json',excerpt='Derived from event IDs: '+','.join(e['id'] for e in rows)),
                           evidence_role='assistant',supersedes=[],related=[e['id'] for e in rows])
                result['draft']=write_event(root,{**item,'event':draft})
        target=out/(item['id']+'.json')
        with target.open('x') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print('Completed request '+item['id'],flush=True)
    return len(jobs)


def build_now(root,limit=50):
    """Materialize a small current-state view from confirmed lifecycle-aware events."""
    root=Path(root)
    events=memory_bridge.load(root)
    inactive=memory_bridge.inactive_ids(events)
    rows=[]
    for event in events:
        if event['id'] in inactive or event['status'] != 'confirmed' or event['kind'] == 'forget' or not memory_bridge.in_time(event):
            continue
        stability=event.get('stability','stable')
        if not (stability in {'temporary','evolving'} or event['kind'] in {'project_state','decision'} or event.get('expires_at')):
            continue
        rows.append(event)
    rows.sort(key=lambda event:(float(event.get('importance',0)),event['created_at'],event['id']),reverse=True)
    rows=rows[:limit]
    generated=dt.datetime.now(dt.timezone.utc).isoformat()
    lines=[
        '# NOW · current memory state',
        '',
        '> GENERATED from memory/events. Do not edit manually.',
        '',
        'Generated: '+generated,
        '',
        'This view contains current confirmed project states, decisions, expiring memories, and events marked evolving/temporary.',
        ''
    ]
    if not rows:
        lines.append('- No current-state events matched the materialization rules.')
    for event in rows:
        meta=[event['scope']['project'],event.get('stability','stable'),event['created_at'][:10]]
        if event.get('expires_at'):meta.append('expires '+event['expires_at'])
        lines.append('- '+event['text'].replace('\n',' ')+'  ')
        lines.append('  _'+ ' · '.join(meta) +' · event '+event['id']+'_')
    target=root/'memory/NOW.md'
    target.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return rows


def status_snapshot(root,phase='idle'):
    root=Path(root)
    requests=sorted(path.stem for path in (root/'memory/requests').glob('*.json'))
    results=sorted(path.stem for path in (root/'memory/results').glob('*.json'))
    failures=sorted(path.stem for path in (root/'memory/failures').glob('*.json')) if (root/'memory/failures').exists() else []
    done=set(results)|set(failures)
    pending_ids=[ident for ident in requests if ident not in done]
    last_result=None
    for ident in results:
        try:
            row=json.loads((root/'memory/results'/(ident+'.json')).read_text())
        except (OSError,ValueError,json.JSONDecodeError):
            continue
        if last_result is None or row.get('generated_at','') > last_result.get('generated_at',''):
            last_result=row
    payload=dict(
        version=1,
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        phase=phase,
        requests_total=len(requests),
        succeeded=len(results),
        failed_known=len(failures),
        pending=len(pending_ids),
        pending_ids=pending_ids[:100],
        last_completed_at=last_result.get('generated_at') if last_result else None,
        last_workflow_url=os.environ.get('MEMORY_RUN_URL') or (last_result.get('workflow_url') if last_result else None),
    )
    target=root/'memory/status.json'
    target.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    build_now(root)
    return payload


def publish(root,status_only=False):
    """Fast-forward retries regenerate no files and never overwrite concurrent edits."""
    root = Path(root)
    def git(*args):
        return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True,text=True)
    branch = os.environ.get('MEMORY_BRANCH', 'main')
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', branch) or branch.startswith('-') or '..' in branch:
        raise ValueError('Invalid destination branch')
    git('config','user.name','github-actions[bot]')
    git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    if status_only:
        paths=[name for name in ['memory/status.json','memory/NOW.md'] if (root/name).exists()]
    else:
        paths=[name for name in ['memory/results','memory/events','memory/working','memory/status.json','memory/NOW.md'] if (root/name).exists()]
    if not paths:return
    git('add',*paths)
    if not git('diff','--cached','--name-only').stdout.strip(): return
    message='Update memory cloud status' if status_only else 'Save cloud memory results and materialized views'
    git('commit','-m',message)
    for attempt in range(3):
        try:
            git('push','origin','HEAD:'+branch);return
        except subprocess.CalledProcessError:
            git('fetch','origin',branch)
            try: git('rebase','origin/'+branch)
            except subprocess.CalledProcessError:
                git('rebase','--abort')
                raise ValueError('Concurrent content conflict; results not pushed')
    raise ValueError('Could not publish after concurrent branch updates')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('pending')
    sub.add_parser('publish')
    sub.add_parser('publish-status')
    status=sub.add_parser('status');status.add_argument('--phase',default='idle',choices=['idle','running','completed','failed'])
    work=sub.add_parser('run');work.add_argument('--db',required=True);work.add_argument('--model-dir',required=True)
    a=p.parse_args()
    if a.command=='pending':
        count=len(pending(a.root))
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('pending='+('true' if count else 'false')+'\n')
        jobs=pending(a.root)
        semantic=any(item.get('operation','recall') in {'recall','sync'} and item.get('mode','hybrid')!='keyword' for item,_ in jobs)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('semantic='+str(semantic).lower()+'\n')
        print(f'{count} pending memory requests')
    elif a.command=='publish':publish(a.root)
    elif a.command=='publish-status':publish(a.root,status_only=True)
    elif a.command=='status':print(json.dumps(status_snapshot(a.root,a.phase),ensure_ascii=False))
    else:print(f'Completed {run(a.root,a.db,a.model_dir)} requests')


if __name__=='__main__':main()
