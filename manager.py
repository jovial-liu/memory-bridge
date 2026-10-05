"""Evidence-first relationship memory, reflection drafts, and working checkpoints."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import memory_bridge


def graph(root, project, entity=None, hops=1):
    if not isinstance(project,str) or not project.strip(): raise ValueError('Graph requires explicit project')
    if not isinstance(hops,int) or not 1 <= hops <= 3: raise ValueError('hops must be 1..3')
    events=memory_bridge.search(root,project=project)
    edges=[]
    for e in events:
        claim=e.get('claim')
        if claim:
            value=claim['value'] if isinstance(claim['value'],str) else json.dumps(claim['value'],sort_keys=True)
            edges.append(dict(from_node=claim['subject'],relation=claim['predicate'],to_node=value,
                              event_id=e['id'],status=e['status'],source=e['source']['reference'],
                              created_at=e['created_at'],valid_from=e.get('valid_from'),expires_at=e.get('expires_at')))
        for target in e.get('related',[]):
            if any(x['id']==target for x in events):
                edges.append(dict(from_node=e['id'],relation='related',to_node=target,event_id=e['id'],
                                  status=e['status'],source=e['source']['reference'],created_at=e['created_at']))
    if entity is not None:
        nodes={entity};selected=[]
        for _ in range(hops):
            additions=[]
            for edge in edges:
                if edge in selected:continue
                if edge['from_node'] in nodes or edge['to_node'] in nodes:
                    selected.append(edge);additions.extend([edge['from_node'],edge['to_node']])
            nodes.update(additions)
        edges=selected
    return dict(project=project,edges=edges,conflicts=[x for x in memory_bridge.conflicts(events)],
                interpretation='Explicit sourced relations, not inferred graph facts')


def reflect(root,project):
    events=memory_bridge.search(root,project=project)
    rows=[dict(id=e['id'],kind=e['kind'],status=e['status'],text=e['text'],source=e['source']['reference'],
               created_at=e['created_at']) for e in events]
    return dict(project=project,status='candidate',items=rows,
                conflicts=memory_bridge.conflicts(events),
                interpretation='Evidence consolidation draft; no generated conclusions are confirmed')


def checkpoint(root,ident,payload):
    if not re.fullmatch(r'[a-f0-9]{32}',ident):raise ValueError('Invalid checkpoint ID')
    for name in ('project','task_id'):
        if not isinstance(payload.get(name),str) or not payload[name].strip() or len(payload[name])>200:
            raise ValueError('Checkpoint requires project and task_id')
    state=payload.get('state')
    if not isinstance(state,dict) or not isinstance(state.get('objective'),str) or not state['objective'].strip():
        raise ValueError('Checkpoint requires state.objective')
    for key in ('done','pending','next_steps'):
        if not isinstance(state.get(key,[]),list) or not all(isinstance(x,str) for x in state.get(key,[])):
            raise ValueError('Checkpoint state lists must contain strings')
    source=payload.get('source')
    if not isinstance(source,dict) or not all(isinstance(source.get(k),str) and source[k].strip() for k in ('reference','excerpt')):
        raise ValueError('Checkpoint requires source evidence')
    if len(json.dumps(payload))>24000 or memory_bridge.SECRET.search(json.dumps(payload)):
        raise ValueError('Checkpoint too large or contains a possible credential')
    item=dict(id=ident,project=payload['project'],task_id=payload['task_id'],state=state,source=source,
              status='candidate',created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
              interpretation='Reported task state; verify before resuming actions')
    folder=Path(root)/'memory/working';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(ident+'.json')
    if path.exists():
        prior=json.loads(path.read_text())
        if all(prior.get(key)==item[key] for key in ('project','task_id','state','source')):return prior
        raise ValueError('Checkpoint ID collision')
    with path.open('x') as f:f.write(json.dumps(item,ensure_ascii=False,indent=2)+'\n')
    return item


def resume(root,project,task_id):
    states=[]
    for path in (Path(root)/'memory/working').glob('*.json'):
        state=json.loads(path.read_text())
        if state.get('project')==project and state.get('task_id')==task_id:
            states.append(state)
    # ISO strings with different UTC offsets are not lexicographically chronological.
    states.sort(key=lambda x:(memory_bridge.instant(x['created_at']),x['id']))
    return dict(project=project,task_id=task_id,checkpoint=states[-1] if states else None,
                interpretation='Historical checkpoint, not proof that tasks are currently running')
