import json
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import numpy as np
except ImportError:
    np = None
import rag
import semantic


class FixtureEncoder:
    """Known semantic relations for deterministic pipeline tests, not a real model."""
    fingerprint='fixture-encoder-v1'
    dimension=2
    def encode(self,texts,query=False):
        return np.array([[1,0] if ('concise' in t or '简洁' in t) else [0,1] for t in texts],dtype=np.float32)


@unittest.skipIf(np is None, 'Install NumPy to run vector pipeline tests')
class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)/'memory';self.root.mkdir()
        folder=self.root/'conversations/demo';folder.mkdir(parents=True)
        (folder/'one.json').write_text(json.dumps(dict(source='demo',account_label='fictional',project='demo',title='',
            messages=[dict(role='user',text='请使用简洁的回答。'),dict(role='user',text='我喜欢在海边散步。')]),ensure_ascii=False))
        self.db=Path(self.tmp.name)/'index.sqlite3';rag.build(self.root,self.db)
        self.encoder=FixtureEncoder()
    def tearDown(self):self.tmp.cleanup()
    def test_semantics_without_keyword_overlap(self):
        self.assertEqual(rag.retrieve(self.root,self.db,'concise'),[])
        semantic.embed(self.root,self.db,self.encoder)
        hits=semantic.retrieve(self.root,self.db,'concise',self.encoder,mode='semantic',limit=1)
        self.assertIn('简洁',hits[0]['text'])
        self.assertEqual(semantic.retrieve(self.root,self.db,'concise',self.encoder,project='other'),[])
    def test_cache_survives_reindex(self):
        first=semantic.embed(self.root,self.db,self.encoder)
        self.assertEqual(first['encoded'],2)
        rag.build(self.root,self.db)
        second=semantic.embed(self.root,self.db,self.encoder)
        self.assertEqual(second['encoded'],0)
        self.assertEqual(second['cached'],2)
    def test_model_mismatch(self):
        semantic.embed(self.root,self.db,self.encoder)
        other=FixtureEncoder();other.fingerprint='different'
        with self.assertRaises(ValueError):semantic.retrieve(self.root,self.db,'concise',other)
    def test_rrf_preserves_both_channels(self):
        semantic.embed(self.root,self.db,self.encoder)
        result=semantic.retrieve(self.root,self.db,'简洁',self.encoder,mode='hybrid',limit=1)
        self.assertEqual(set(result[0]['retrieval_channels']),{'keyword','semantic'})
    def test_memory_only_reports_coverage(self):
        out=semantic.embed(self.root,self.db,self.encoder,memory_only=True)
        self.assertEqual(out['chunks'],0)
        self.assertEqual(out['coverage'],'memory-only')
        hits=semantic.retrieve(self.root,self.db,'简洁',self.encoder,mode='hybrid')
        self.assertEqual(hits[0]['vector_coverage'],'memory-only')
    def test_nan_rejected(self):
        class Broken(FixtureEncoder):
            def encode(self,texts,query=False):return np.full((len(texts),2),np.nan)
        with self.assertRaises(ValueError):semantic.embed(self.root,self.db,Broken())


if __name__=='__main__':unittest.main()
