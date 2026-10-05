import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rag
import memory_bridge
from test_memory_bridge import event


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'private'
        self.root.mkdir()
        self.db = Path(self.tmp.name) / 'rag.sqlite3'
        folder = self.root / 'conversations/example'; folder.mkdir(parents=True)
        self.source = folder / 'conversation.json'
        self.source.write_text(json.dumps(dict(source='example', account_label='demo',
            project='demo', title='论文投稿', coverage='official-text',
            messages=[dict(role='user', text='我的论文需要核对投稿要求。'),
                      dict(role='assistant', text='请核对官方指南。')]), ensure_ascii=False))
    def tearDown(self): self.tmp.cleanup()
    def test_chinese_and_scope(self):
        rag.build(self.root, self.db)
        found = rag.retrieve(self.root, self.db, '论文投稿', project='demo')
        self.assertTrue(found)
        self.assertEqual(found[0]['path'], 'conversations/example/conversation.json')
        self.assertEqual(rag.retrieve(self.root, self.db, '论文投稿', project='other'), [])
        self.assertEqual(rag.retrieve(self.root, self.db, '论文投稿', account='other'), [])
        self.assertIn('[R1]', rag.bundle(found))
    def test_stale_sources(self):
        rag.build(self.root, self.db)
        self.source.write_text('{}')
        with self.assertRaises(ValueError): rag.retrieve(self.root, self.db, '论文')
    def test_replacements_excluded(self):
        a = event(text='旧的简洁回答偏好'); memory_bridge.save(self.root, a)
        b = event('b'*32, text='新的详细回答偏好'); b['supersedes']=[a['id']]
        memory_bridge.save(self.root, b)
        rag.build(self.root, self.db)
        found = rag.retrieve(self.root, self.db, '回答偏好')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['text'], b['text'])
    def test_index_stays_outside_private_repo(self):
        with self.assertRaises(ValueError): rag.build(self.root, self.root/'rag.sqlite3')
    def test_new_correction_invalidates_index(self):
        a = event(); memory_bridge.save(self.root, a)
        rag.build(self.root, self.db)
        b = event('b'*32, text='New preference'); b['supersedes']=[a['id']]
        memory_bridge.save(self.root, b)
        with self.assertRaises(ValueError): rag.retrieve(self.root, self.db, 'answers')
    def test_context_budget_and_root_mismatch(self):
        rag.build(self.root, self.db)
        found = rag.retrieve(self.root, self.db, '论文')
        self.assertLessEqual(len(rag.bundle(found, 300)), 300)
        with self.assertRaises(ValueError): rag.retrieve(self.root.parent, self.db, '论文')

    def test_document_evidence_is_not_user_identity(self):
        folder = self.root/'memory/documents'; folder.mkdir(parents=True)
        source = folder/'files.json'
        doc = dict(text='操作系统实验报告 姓名 示例学生', source_path='/example/report.docx',
                   source_sha256='a'*64, coverage='first 100 characters', project='coursework')
        source.write_text(json.dumps(dict(version=1, documents=[doc])))
        rag.build(self.root, self.db)
        found = rag.retrieve(self.root, self.db, '实验报告', project='coursework')
        self.assertEqual(found[0]['role'], 'document')
        self.assertEqual(found[0]['status'], 'historical')
        self.assertEqual(found[0]['kind'], 'document')
        self.assertEqual(found[0]['source_sha256'], 'a'*64)
        self.assertEqual(rag.retrieve(self.root, self.db, '实验报告', project='other'), [])
        doc['text'] = 'changed source'
        source.write_text(json.dumps(dict(version=1, documents=[doc])))
        with self.assertRaises(ValueError): rag.retrieve(self.root, self.db, '实验报告')

    def test_document_requires_provenance(self):
        folder = self.root/'memory/documents'; folder.mkdir(parents=True)
        (folder/'bad.json').write_text(json.dumps(dict(version=1, documents=[dict(text='unsourced identity claim')])))
        with self.assertRaises(ValueError): rag.build(self.root, self.db)

    def test_human_chat_participant_keeps_its_role(self):
        source = self.root/'conversations/example/human-chat.json'
        source.write_text(json.dumps(dict(source='qq', project='private-chat', title='Fictional chat',
            coverage='UI excerpt, not complete', messages=[dict(role='participant', sender='fictional-peer',
            role_status='inferred-from-ui-not-verified', text='A peer discussed database practice.')]))))
        rag.build(self.root, self.db)
        found = rag.retrieve(self.root, self.db, 'database practice', platform='qq')
        self.assertEqual(found[0]['role'], 'participant')
        self.assertEqual(found[0]['status'], 'historical')
        self.assertEqual(found[0]['role_status'], 'inferred-from-ui-not-verified')


if __name__ == '__main__': unittest.main()
