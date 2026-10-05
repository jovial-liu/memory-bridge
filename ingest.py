"""Stage readable exports before upload; never infer missing authors or dates."""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import privacy


def timestamp(value):
    if isinstance(value,(int,float)):
        return dt.datetime.fromtimestamp(value,dt.timezone.utc).isoformat(),'exact'
    if isinstance(value,str):
        try:
            t=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
            if t.tzinfo:return t.isoformat(),'exact'
        except ValueError:pass
        return None,'date-label' if value.strip() else 'unknown'
    return None,'unknown'

def messages(value,format):
    if format=='text':return [{'role':'participant','sender':'unknown','text':value,'role_status':'unknown-speaker-pasted-batch'}]
    if format=='csv':
        rows=list(csv.DictReader(io.StringIO(value)))
        if not rows or not all('text' in r for r in rows):raise ValueError('CSV requires a text column; optional sender,timestamp columns')
        return [dict(role='participant',sender=r.get('sender') or 'unknown',text=r['text'],timestamp=r.get('timestamp'),role_status='csv-participant-author-not-user-inferred') for r in rows]
    data=[json.loads(line) for line in value.splitlines() if line.strip()] if format=='jsonl' else json.loads(value)
    if isinstance(data,dict) and 'mapping' in data:
        # Official ChatGPT exports: follow the current branch; do not repeat alternate branches.
        node=data.get('current_node');trail=[];seen=set()
        while node:
            if node in seen:raise ValueError('Cyclic exported message graph')
            seen.add(node);record=data['mapping'].get(node)
            if not record:raise ValueError('Missing exported message graph node')
            message=record.get('message')
            if message:
                role=message.get('author',{}).get('role');parts=message.get('content',{}).get('parts',[])
                if role in {'user','assistant'}:trail.append({'role':role,'sender':role,'text':'\n'.join(x for x in parts if isinstance(x,str)),'timestamp':message.get('create_time'),'role_status':'official-export-role'})
            node=record.get('parent')
        return list(reversed(trail))
    if isinstance(data,dict):data=data.get('messages')
    if not isinstance(data,list) or not all(isinstance(r,dict) and isinstance(r.get('text'),str) for r in data):raise ValueError('Expected normalized messages or a readable export')
    return data

def stage(source,output,platform,account,project,format='auto',participants=None):
    import re
    for value in [platform,account,project]:
        if not re.fullmatch(r'[\w.-]{1,100}',value) or value in {'.','..'}:raise ValueError('Invalid scope identifier')
    source=Path(source);output=Path(output);raw=source.read_bytes()
    if source.suffix.lower() in {'.bak','.db','.sqlite','.sqlite3'}:raise ValueError('Protected databases are backup artifacts, not readable exports')
    format=({'json':'json','jsonl':'jsonl','csv':'csv'}.get(source.suffix.lstrip('.'),'text') if format=='auto' else format)
    decoded=raw.decode('utf-8');parsed=json.loads(decoded) if format=='json' else None
    blocks=parsed if isinstance(parsed,list) and parsed and all(isinstance(x,dict) and 'mapping' in x for x in parsed) else [parsed]
    paths=[];all_findings=[];all_rows=[]
    for index,block in enumerate(blocks):
        rows=messages(json.dumps(block) if len(blocks)>1 else decoded,format);normalized=[]
        if not rows:raise ValueError('No supported text messages; inspect export coverage before import')
        for row in rows:
            role=row.get('role','participant')
            if role not in {'user','assistant','participant'}:role='participant'
            time,precision=timestamp(row.get('timestamp'))
            normalized.append({**row,'role':role,'sender':row.get('sender') or 'unknown','timestamp':time,'timestamp_precision':precision,'date_label':row.get('date_label') or (str(row.get('timestamp')) if precision=='date-label' else None),'role_status':row.get('role_status','source-declared-not-personal-fact')})
        clean,findings=privacy.sanitize_object(normalized);privacy.require_clean(clean)
        ident=hashlib.sha256(raw+((':'+str(index)).encode() if len(blocks)>1 else b'')).hexdigest()[:24]
        conv={'id':ident,'source':platform,'account_label':account,'project':project,'participants':participants or [],'title':block.get('title','') if isinstance(block,dict) else '', 'coverage':'supplied-export-only; no whole-account completeness claim','original_message_count':None if format=='text' else len(normalized),'original_sha256':hashlib.sha256(raw).hexdigest(),'messages':clean}
        conv,_=privacy.sanitize_object(conv);privacy.require_clean(conv)
        path=output/'conversations'/platform/(ident+'.json')
        if path.exists():raise ValueError('Staged import exists; compare before replacing')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(conv,ensure_ascii=False,indent=2)+'\n');paths.append(path.relative_to(output).as_posix());all_rows.extend(clean);all_findings.extend(findings)
    ident=hashlib.sha256(raw).hexdigest()[:24]
    report={'version':1,'input_sha256':hashlib.sha256(raw).hexdigest(),'redaction_count':len(all_findings),'findings':all_findings,'records':len(all_rows),'conversations':len(paths),'original_message_count':None if format=='text' else len(all_rows),'unknown_speakers':sum(r['sender']=='unknown' for r in all_rows),'unknown_timestamps':sum(r['timestamp'] is None for r in all_rows),'path':paths[0] if len(paths)==1 else None,'paths':paths,'status':'staged-not-uploaded'}
    reportpath=output/'memory/imports'/(ident+'.json');reportpath.parent.mkdir(parents=True,exist_ok=True);reportpath.write_text(json.dumps(report,indent=2)+'\n')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');p.add_argument('--output',required=True);p.add_argument('--platform',required=True);p.add_argument('--account',required=True);p.add_argument('--project',required=True);p.add_argument('--format',choices=['auto','text','json','jsonl','csv'],default='auto');p.add_argument('--participant',action='append');a=p.parse_args()
    # Treat scope names as identifiers, not file paths.
    for value in [a.platform,a.account,a.project]:
        if '/' in value or '\\' in value or value in {'.','..'}:raise ValueError('Invalid scope identifier')
    report=stage(a.input,a.output,a.platform,a.account,a.project,a.format,a.participant)
    print(json.dumps({k:report[k] for k in ['records','original_message_count','unknown_speakers','unknown_timestamps','redaction_count','status']}))
if __name__=='__main__':main()
