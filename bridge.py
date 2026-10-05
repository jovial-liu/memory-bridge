"""A small GitHub client; retrieval/model execution stays on GitHub Actions."""
import argparse
import base64
import datetime as dt
import json
import re
import subprocess
import time
import uuid
import cloud


def api(repository,path,body=None):
    args=['gh','api','repos/'+repository+('/'+path if path else '')]
    if body is not None:args+=['--method','PUT','--input','-']
    result=subprocess.run(args,input=json.dumps(body).encode() if body is not None else None,capture_output=True)
    if result.returncode:raise RuntimeError('GitHub operation failed; check authentication and repository permissions')
    return json.loads(result.stdout)

def submit(repository,item,wait_seconds=0,poll_seconds=5):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):raise ValueError('Invalid repository')
    cloud.validate_request(item,item['id'])  # Before any sensitive payload leaves the client.
    if api(repository,'')['private'] is not True:raise ValueError('Personal memory requires a private repository')
    content=(json.dumps(item,ensure_ascii=False,indent=2)+'\n').encode()
    api(repository,'contents/memory/requests/'+item['id']+'.json',{'message':'Submit private memory '+item.get('operation','recall')+' request','content':base64.b64encode(content).decode()})
    receipt={'id':item['id'],'status':'submitted','result_path':'memory/results/'+item['id']+'.json','execution':'github-actions'}
    deadline=time.monotonic()+wait_seconds
    while wait_seconds and time.monotonic()<deadline:
        try:
            result=api(repository,'contents/'+receipt['result_path'])
            return json.loads(base64.b64decode(result['content']))
        except RuntimeError:time.sleep(min(poll_seconds,max(0,deadline-time.monotonic())))
    return receipt

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repository',required=True);sub=p.add_subparsers(dest='command',required=True)
    recall=sub.add_parser('recall');recall.add_argument('query');recall.add_argument('--mode',choices=['keyword','semantic','hybrid'],default='hybrid')
    remember=sub.add_parser('remember');remember.add_argument('text');remember.add_argument('--source-reference',required=True);remember.add_argument('--source-excerpt',required=True);remember.add_argument('--confirm',action='store_true',help='Only with explicit direct-user confirmation')
    for c in [recall,remember]:
        c.add_argument('--project',required=True);c.add_argument('--platform');c.add_argument('--account');c.add_argument('--wait',type=int,default=0)
    a=p.parse_args();item={'id':uuid.uuid4().hex,'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'project':a.project}
    if a.command=='recall':
        item.update(operation='recall',query=a.query,mode=a.mode)
        if a.platform:item['platform']=a.platform
        if a.account:item['account']=a.account
    else:
        item.update(operation='write',event={'version':1,'kind':'fact','status':'confirmed' if a.confirm else 'candidate','text':a.text,'scope':{'project':a.project,'platform':a.platform or 'user-statement','account':a.account or 'unknown'},'source':{'reference':a.source_reference,'excerpt':a.source_excerpt},'evidence_role':'user','supersedes':[]})
    print(json.dumps(submit(a.repository,item,a.wait),ensure_ascii=False))
if __name__=='__main__':main()
