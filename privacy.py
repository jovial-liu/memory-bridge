"""Client-side data minimization. Findings never contain matched secret values."""
import argparse
import hashlib
import json
from pathlib import Path
import re

TOKEN = re.compile(r'gh[pousr]_[A-Za-z0-9]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----')
LABEL = re.compile(r'''(?ix)(?:["']?(?:password|passwd|api[_-]?key|access[_-]?token|authorization|密码|口令|验证码)["']?[ \t]*[:：=][ \t]*["']?|(?:密码|口令)[ \t]+|(?:密码|口令)(?=[!]))([^\s,"'，；;。<>}\]]+)''')
AUTH = re.compile(r'(?im)^.*(?:facebook|pinterest|printerest|instagram|\bins\b|\bx[ \t]+).*(?:![A-Za-z0-9]{4,}|\b(?:pin|code)[ \t]+\d{4,8}).*$')
PIN = re.compile(r'(?i)\b(?:pin|code)[ \t]+(\d{4,8})\b')
ID = re.compile(r'(?<![A-Za-z0-9])\d{6}(?:19|20)\d{9}[\dXx](?![A-Za-z0-9])')
PHONE = re.compile(r'(?<![A-Za-z0-9])1[3-9]\d{9}(?![A-Za-z0-9])')
ADDRESS = re.compile(r'(?m)^.*(?:省|自治区|市).*(?:社区|小区|街道|\d+号|\d+室).*$')
CUE = re.compile(r'(?i)密码|口令|验证码|password|\bpin\b')
PLACEHOLDER = re.compile(r'(?i)^(?:\[redacted|<|your_|example_|dummy_|test_|none$|null$|怎么|什么|啥|格式|同$|没有|不知道|不记得)')

def findings(text):
    if not isinstance(text, str): raise ValueError('Expected text')
    spans=[]
    def add(kind,start,end):
        if end > start and not PLACEHOLDER.match(text[start:end]):
            spans.append({'kind':kind,'start':start,'end':end,'line':text.count('\n',0,start)+1})
    for kind,pattern in [('credential',TOKEN),('credential',AUTH),('identity-number',ID),('phone-number',PHONE),('precise-address',ADDRESS)]:
        for match in pattern.finditer(text):add(kind,*match.span())
    for pattern in [LABEL,PIN]:
        for match in pattern.finditer(text):
            value=match.group(1)
            if re.search(r'[A-Za-z0-9!@#$%^&*]',value):add('credential',*match.span(1))
    lines=text.splitlines(keepends=True);pos=0
    for index,line in enumerate(lines):
        value=line.strip()
        nearby=''.join(lines[max(0,index-4):index])
        if CUE.search(nearby) and re.fullmatch(r'[A-Za-z0-9!@#$%^&*_.+-]{6,100}',value) and re.search(r'\d',value) and re.search(r'[A-Za-z!@#$%^&*]',value):
            add('credential',pos+line.index(value),pos+line.index(value)+len(value))
        pos+=len(line)
    # Merge overlapping detector findings once, including auth-line/number overlaps.
    merged=[]
    for item in sorted(spans,key=lambda x:(x['start'],-x['end'])):
        if merged and item['start'] < merged[-1]['end']:
            merged[-1]['end']=max(item['end'],merged[-1]['end'])
            if item['kind']=='credential':merged[-1]['kind']='credential'
        else:merged.append(item.copy())
    return merged

def sanitize_text(text):
    hits=findings(text);clean=text
    for hit in reversed(hits):
        clean=clean[:hit['start']]+'[REDACTED_'+hit['kind'].upper().replace('-','_')+']'+clean[hit['end']:]
    return clean,hits

def sanitize_object(value):
    report=[]
    def walk(item,field):
        if isinstance(item,str):
            clean,hits=sanitize_text(item)
            report.extend({**h,'field':field} for h in hits)
            return clean
        if isinstance(item,list):return [walk(x,field+'/'+str(i)) for i,x in enumerate(item)]
        if isinstance(item,dict):
            result={k:walk(v,field+'/'+str(k)) for k,v in item.items()}
            messages=result.get('messages')
            if isinstance(messages,list):
                for i,msg in enumerate(messages):
                    if not isinstance(msg,dict) or not isinstance(msg.get('text'),str):continue
                    prior='\n'.join(m.get('text','') for m in messages[max(0,i-2):i] if isinstance(m,dict))
                    text=msg['text'].strip()
                    if CUE.search(prior) and re.fullmatch(r'[A-Za-z0-9!@#$%^&*_.+-]{6,100}',text) and re.search(r'\d',text) and re.search(r'[A-Za-z!@#$%^&*]',text) and not PLACEHOLDER.match(text):
                        msg['text']='[REDACTED_CREDENTIAL]';report.append({'kind':'credential','field':field+'/messages/'+str(i)+'/text','line':1,'start':0,'end':len(text)})
            return result
        return item
    return walk(value,''),report

def require_clean(value):
    _,report=sanitize_object(value)
    if report:raise ValueError('Sensitive data detected ('+str(len(report))+' findings); sanitize BEFORE upload')


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    command=sub.add_parser('sanitize');command.add_argument('input');command.add_argument('--output',required=True);command.add_argument('--report',required=True)
    scan=sub.add_parser('scan');scan.add_argument('input');scan.add_argument('--report',required=True)
    args=parser.parse_args();source=Path(args.input);raw=source.read_bytes();text=raw.decode('utf-8')
    if source.suffix=='.json':
        clean,hits=sanitize_object(json.loads(text));data=(json.dumps(clean,ensure_ascii=False,indent=2)+'\n').encode()
    else:
        clean,hits=sanitize_text(text);data=clean.encode()
    report={'version':1,'input_sha256':hashlib.sha256(raw).hexdigest(),'output_sha256':hashlib.sha256(data).hexdigest(),'findings':hits,'count':len(hits),'scope':'pattern-based; not a guarantee of complete anonymization'}
    Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    if args.command=='sanitize':
        target=Path(args.output)
        if target.resolve()==source.resolve():raise ValueError('Preserve the original; use a separate output')
        target.write_bytes(data)
    print('Sensitive pattern findings: '+str(len(hits)))
    if args.command=='scan' and hits:raise SystemExit(2)

if __name__=='__main__':main()
