import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import rag,cloud
class OriginalImportTests(unittest.TestCase):
 def test_authorization_is_bound_to_bytes_and_does_not_change_source(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);path=root/'conversations/demo/one.json';path.parent.mkdir(parents=True)
   # Fictional detector fixture, not a real credential.
   raw=json.dumps({'messages':[{'role':'user','text':'password: fictional123'}]}).encode();path.write_bytes(raw)
   with self.assertRaises(ValueError):list(rag.documents(root))
   policy=root/'memory/import-policy.json';policy.parent.mkdir();policy.write_text(json.dumps({'version':1,'mode':'owner-authorized-original-private-import','authorization':'Explicit owner opt-in for private archive','sha256_by_path':{'conversations/demo/one.json':hashlib.sha256(raw).hexdigest()}}))
   self.assertEqual(list(rag.documents(root))[0]['text'],'password: fictional123');self.assertEqual(path.read_bytes(),raw)
   path.write_bytes(raw+b' ')
   with self.assertRaises(ValueError):list(rag.documents(root))
 def test_policy_does_not_disable_request_validation(self):
  ident='0'*32
  with self.assertRaises(ValueError):cloud.validate_request({'id':ident,'operation':'recall','query':'password: fictional123'},ident)
 def test_policy_changes_invalidate_index(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);before=rag.snapshot(root);p=root/'memory/import-policy.json';p.parent.mkdir();p.write_text('{}');self.assertNotEqual(before,rag.snapshot(root))
