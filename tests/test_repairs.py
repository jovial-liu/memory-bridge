import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bridge
import cloud
import evaluate
import ingest
import privacy
import rag
import semantic
import vault

class RepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'repo';self.root.mkdir();self.db=Path(self.tmp.name)/'db.sqlite3'
    def tearDown(self):self.tmp.cleanup()
    def conversation(self):
        p=self.root/'conversations/demo/one.json';p.parent.mkdir(parents=True)
        text='pear orchard\n'+('ordinary background '*85)+'\ncomet telescope'
        p.write_text(json.dumps({'source':'demo','account_label':'owner','project':'demo','participants':['owner','peer'],'messages':[{'role':'participant','sender':'unknown','text':text,'role_status':'unknown-speaker'}]}))
        return p
    def test_multiple_passages_and_provenance(self):
        self.conversation();rag.build(self.root,self.db);hits=rag.retrieve(self.root,self.db,'pear comet',limit=5,project='demo')
        self.assertGreaterEqual(len(hits),2);self.assertGreaterEqual(len({h['char_offset'] for h in hits}),2)
        self.assertTrue(all(h['sender']=='unknown' and h['timestamp_precision']=='unknown' for h in hits))
        self.assertTrue(all(h['text_line_start']<=h['text_line_end'] for h in hits))
        self.assertEqual(rag.retrieve(self.root,self.db,'pear',project='other'),[])
    def test_rrf_keeps_offsets_and_merges_identical_passage(self):
        a={'path':'one','message_index':0,'char_offset':0};b={**a,'char_offset':1000}
        hits=semantic.fuse([('keyword',[a,b]),('semantic',[b])])
        self.assertEqual(len(hits),2);self.assertEqual(hits[0]['char_offset'],1000);self.assertEqual(set(hits[0]['retrieval_channels']),{'keyword','semantic'})
    def test_no_colon_auth_and_standalone_value(self):
        value='Lab'+str(987654)+'!';text='密码啥\n我在找\n'+value+'\nins !'+str(678901)+'Ab\nX code '+str(4567)
        cleaned,hits=privacy.sanitize_text(text);self.assertNotIn(value,cleaned);self.assertGreaterEqual(len(hits),3);privacy.require_clean(cleaned)
        self.assertTrue(all('value' not in h for h in hits))
    def test_identity_phone_and_tracking_boundaries(self):
        number='110105'+'20060101'+'1234';phone='138'+'00138000'
        cleaned,hits=privacy.sanitize_text(number+'\n'+phone+'\n1ZABC'+phone,strict=True)
        self.assertNotIn('\n'+phone+'\n',cleaned);self.assertNotIn(number,cleaned);self.assertIn('1ZABC'+phone,cleaned);privacy.require_clean(phone+' ordinary personal context')
    def test_json_adjacent_messages_and_placeholders(self):
        value='Lab'+str(887766);clean,hits=privacy.sanitize_object({'messages':[{'text':'密码是什么'},{'text':value}]})
        self.assertNotIn(value,json.dumps(clean));privacy.require_clean('password: YOUR_PASSWORD');privacy.require_clean(clean)
    def test_ingest_does_not_infer_speaker_or_timestamp(self):
        p=Path(self.tmp.name)/'input.txt';p.write_text('hello\nthere')
        r=ingest.stage(p,self.root,'demo','owner','demo');self.assertIsNone(r['original_message_count']);self.assertEqual(r['unknown_speakers'],1);self.assertEqual(r['unknown_timestamps'],1)
        item=json.loads((self.root/r['path']).read_text());self.assertEqual(item['messages'][0]['role'],'participant')
    def test_readable_csv_and_protected_backup(self):
        p=Path(self.tmp.name)/'input.csv';p.write_text('sender,text,timestamp\npeer,hello,2026-01-01\n')
        r=ingest.stage(p,self.root,'demo','owner','demo');msg=json.loads((self.root/r['path']).read_text())['messages'][0]
        self.assertIsNone(msg['timestamp']);self.assertEqual(msg['date_label'],'2026-01-01');self.assertEqual(msg['role'],'participant')
        p=Path(self.tmp.name)/'protected.bak';p.write_bytes(b'not plain text')
        with self.assertRaises(ValueError):ingest.stage(p,self.root,'qq','owner','qq')
    def test_bridge_rejects_before_any_network(self):
        item={'id':'a'*32,'operation':'recall','query':'password: '+('Lab'+str(789456))}
        with patch('bridge.api') as mocked:
            with self.assertRaises(ValueError):bridge.submit('owner/private',item)
            mocked.assert_not_called()
    def test_bridge_submit_and_wait(self):
        item={'id':'a'*32,'operation':'recall','query':'pear','mode':'keyword'}
        result={'execution':'github-actions','results':[]}
        with patch('bridge.api',side_effect=[{'private':True},{'commit':{}},{'content':base64.b64encode(json.dumps(result).encode()).decode()}]) as mocked:
            self.assertEqual(bridge.submit('owner/private',item,wait_seconds=1),result);self.assertEqual(mocked.call_count,3)
    def test_source_labelled_evaluation(self):
        p=self.conversation();relative=p.relative_to(self.root).as_posix()
        cases=[{'id':'passages','query':'pear comet','project':'demo','expected':{'paths_all':[relative],'min_chunks':2,'contains_all':['pear','comet'],'roles':['participant'],'unknown_speakers':True,'unknown_times':True}},{'id':'scope','query':'pear','project':'other','expected':{'empty':True}}]
        r=evaluate.evaluate(self.root,self.db,cases);self.assertEqual(r['passed'],2);self.assertEqual(r['scope_leaks'],0)
    def test_incoming_sensitive_query_and_event_blocked(self):
        item={'id':'a'*32,'operation':'write','event':{'text':'密码 '+('Lab'+str(654321))}}
        with self.assertRaises(ValueError):cloud.validate_request(item,'a'*32)
    def test_official_multi_chat_export_current_branch(self):
        def conversation(title):
            return {'title':title,'current_node':'b','mapping':{'a':{'parent':None,'message':{'author':{'role':'user'},'content':{'parts':['hello']},'create_time':1700000000}},'b':{'parent':'a','message':{'author':{'role':'assistant'},'content':{'parts':['reply']}}},'alternate':{'parent':'a','message':{'author':{'role':'assistant'},'content':{'parts':['unused alternative']}}}}}
        p=Path(self.tmp.name)/'export.json';p.write_text(json.dumps([conversation('first'),conversation('second')]))
        report=ingest.stage(p,self.root,'chatgpt','owner','demo');self.assertEqual(report['conversations'],2);self.assertEqual(report['records'],4)
        for path in report['paths']:
            conv=json.loads((self.root/path).read_text());self.assertNotIn('unused alternative',json.dumps(conv));self.assertEqual(conv['messages'][0]['timestamp_precision'],'exact')
    def test_vector_candidates_keep_multiple_passages(self):
        try:import numpy
        except ImportError:self.skipTest('NumPy unavailable')
        class Provider:
            fingerprint='fixture-only';dimension=2
            def encode(self,texts,query=False):return [[1.0,1.0] for text in texts]
        self.conversation();rag.build(self.root,self.db);semantic.embed(self.root,self.db,Provider())
        hits,coverage=semantic.vector_candidates(self.root,self.db,'pear comet',Provider(),project='demo')
        self.assertGreaterEqual(len(hits),2);self.assertEqual(len(hits),len({rag.chunk_key(h) for h in hits}))
    def test_evaluation_requires_assertions(self):
        self.conversation()
        with self.assertRaises(ValueError):evaluate.evaluate(self.root,self.db,[{'id':'empty','query':'pear','expected':{}}])
    def test_vault_roundtrip_and_tampering(self):
        try:from Cryptodome.Cipher import AES
        except ImportError:self.skipTest('Optional privacy runtime unavailable')
        secret=os.urandom(32);raw=vault.encrypt(b'original archive',secret);self.assertEqual(vault.decrypt(raw,secret),b'original archive')
        with self.assertRaises(ValueError):vault.decrypt(raw[:-1]+bytes([raw[-1]^1]),secret)
        with self.assertRaises(ValueError):vault.decrypt(raw,os.urandom(32))
if __name__=='__main__':unittest.main()
