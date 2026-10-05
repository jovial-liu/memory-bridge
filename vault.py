"""Authenticated encrypted archives; keys stay outside the GitHub repository."""
import argparse
import hashlib
import json
import os
from pathlib import Path
MAGIC=b'MEMORYVAULT1\n'

def key(path,create=False):
    path=Path(path)
    if create and not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(os.urandom(32))
    raw=path.read_bytes()
    if len(raw)!=32:raise ValueError('Key must contain exactly 32 random bytes')
    if path.stat().st_mode & 0o077:raise ValueError('Key file must be owner-only (0600)')
    return raw

def encrypt(data,secret):
    from Cryptodome.Cipher import AES
    cipher=AES.new(secret,AES.MODE_GCM,nonce=os.urandom(12),mac_len=16)
    cipher.update(MAGIC)
    ciphertext,tag=cipher.encrypt_and_digest(data)
    return MAGIC+cipher.nonce+tag+ciphertext

def decrypt(data,secret):
    from Cryptodome.Cipher import AES
    if not data.startswith(MAGIC) or len(data)<len(MAGIC)+28:raise ValueError('Invalid archive format')
    raw=data[len(MAGIC):];cipher=AES.new(secret,AES.MODE_GCM,nonce=raw[:12],mac_len=16);cipher.update(MAGIC)
    return cipher.decrypt_and_verify(raw[28:],raw[12:28])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=['encrypt','decrypt']);p.add_argument('input');p.add_argument('--output',required=True);p.add_argument('--key-file',required=True);p.add_argument('--create-key',action='store_true');p.add_argument('--repository-root',required=True);a=p.parse_args()
    root=Path(a.repository_root).resolve();keypath=Path(a.key_file).resolve()
    if keypath==root or root in keypath.parents:raise ValueError('Never store the encryption key in the repository')
    target=Path(a.output)
    if target.exists() or target.resolve()==Path(a.input).resolve():raise ValueError('Output must be a new file')
    source=Path(a.input).read_bytes();secret=key(keypath,a.create_key)
    raw=encrypt(source,secret) if a.operation=='encrypt' else decrypt(source,secret)
    target.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw)
    print(json.dumps({'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'operation':a.operation}))
if __name__=='__main__':main()
