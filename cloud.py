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


def validate_request(item, ident):
    if not re.fullmatch(r'[a-f0-9]{32}', ident) or item.get('id') != ident:
        raise ValueError('Request ID/path mismatch')
    operation=item.get('operation','recall')
    if operation not in {'recall','write','sync','forget','graph','reflect','checkpoint','resume','conflicts'}:
        raise ValueError('Unsupported operation')
    if operation in {'recall','sync'}:
        if not isinstance(item.get('query'),str) or not 1 <= len(item['query'].strip()) <= 2000:
            raise ValueError('Query must be 1..2000 characters')
        if memory_bridge.SECRET.search(item['query']): raise ValueError('Possible credential in query')
    if operation in {'graph','reflect','checkpoint','resume'} and not item.get('project'):
        raise ValueError('Operation requires explicit project')
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


def write_event(root,item,kind=None):
    event=dict(item.get('event',{}))
    ident=hashlib.sha256((item['id']+':event').encode()).hexdigest()[:32]
    old=next((Path(root)/'memory/events').glob('*/'+ident+'.json'),None)
    timestamp=json.loads(old.read_text())['created_at'] if old else item.get('created_at',dt.datetime.now(dt.timezone.utc).isoformat())
    event.update(version=1,id=ident,created_at=timestamp)
    event.setdefault('supersedes',[])
    if kind:event['kind']=kind
    path=memory_bridge.save(root,event)
    return dict(event_id=ident,path=path.relative_to(root).as_posix())


def run(root, db, model_dir):
    import manager
    root=Path(root).resolve()
    jobs=pending(root)
    if not jobs:return 0
    memory_bridge.load(root)
    prepared={}
    for item,_ in jobs:
        op=item.get('operation','recall')
        if op in {'write','sync','forget'}:
            prepared[item['id']]=write_event(root,item,'forget' if op=='forget' else None)
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


def publish(root):
    """Fast-forward retries regenerate no files and never overwrite concurrent edits."""
    root = Path(root)
    def git(*args):
        return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True,text=True)
    if not (root/'memory/results').exists(): return
    git('config','user.name','github-actions[bot]')
    git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    paths=[name for name in ['memory/results','memory/events','memory/working'] if (root/name).exists()]
    git('add',*paths)
    if not git('diff','--cached','--name-only').stdout.strip(): return
    git('commit','-m','Save cloud memory retrieval results')
    for attempt in range(3):
        try:
            git('push','origin','HEAD:main');return
        except subprocess.CalledProcessError:
            git('fetch','origin','main')
            try: git('rebase','origin/main')
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
    work=sub.add_parser('run');work.add_argument('--db',required=True);work.add_argument('--model-dir',required=True)
    a=p.parse_args()
    if a.command=='pending':
        count=len(pending(a.root))
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('pending='+('true' if count else 'false')+'\n')
        print(f'{count} pending memory requests')
    elif a.command=='publish':publish(a.root)
    else:print(f'Completed {run(a.root,a.db,a.model_dir)} requests')


if __name__=='__main__':main()
