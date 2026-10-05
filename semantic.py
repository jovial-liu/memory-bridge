"""Semantic and hybrid retrieval on the same scoped, auditable SQLite index."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3

import memory_bridge
import rag


def embed(root, db, provider, batch_size=16, progress=None, memory_only=False, scopes=None):
    import numpy as np
    if not 1 <= batch_size <= 128: raise ValueError('batch_size must be 1..128')
    db = Path(db).resolve()
    if not db.exists(): raise ValueError('Run rag index first')
    c = sqlite3.connect(db)
    try:
        info = dict(c.execute('select key,value from metadata'))
        if info['root'] != str(Path(root).resolve()) or info['snapshot'] != rag.snapshot(root):
            raise ValueError('Index root/snapshot mismatch; rebuild first')
        c.execute('create table if not exists vector_cache(model text, digest text, vector blob, primary key(model,digest))')
        c.execute('create table if not exists vectors(id integer primary key, vector blob)')
        c.execute("delete from metadata where key='vector_snapshot'")
        c.execute('delete from vectors')
        c.commit()
        rows = list(c.execute('select id,meta from chunks order by id'))
        if memory_only:
            rows = [(ident, raw) for ident,raw in rows if json.loads(raw)['kind'] == 'memory']
        if scopes is not None:
            def matches(item,scope):
                return all(value is None or (value in item['topics'] if key=='topic' else
                    item.get(key, 'episodic' if item['kind']=='conversation' else 'semantic') == value)
                    for key,value in scope.items())
            rows = [(ident,raw) for ident,raw in rows if any(matches(json.loads(raw),s) for s in scopes)]
        cached, encoded = 0, 0
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            pending, items = {}, []
            for ident, raw in batch:
                item = json.loads(raw)
                text = item['title'] + '\n' + item['text']
                digest = hashlib.sha256(text.encode()).hexdigest()
                cached_row = c.execute('select vector from vector_cache where model=? and digest=?',
                                       (provider.fingerprint, digest)).fetchone()
                blob = cached_row[0] if cached_row else None
                items.append((ident, digest, blob))
                if blob is None: pending.setdefault(digest, text)
                else: cached += 1
            produced = {}
            if pending:
                values = np.asarray(provider.encode(list(pending.values())), dtype='<f4')
                if values.shape != (len(pending), provider.dimension) or not np.isfinite(values).all():
                    raise ValueError('Embedding provider returned invalid dimensions/values')
                norms = np.linalg.norm(values, axis=1, keepdims=True)
                if np.any(norms <= 0): raise ValueError('Zero embedding vector')
                values /= norms
                for digest, vector in zip(pending, values):
                    blob = vector.astype('<f4').tobytes()
                    produced[digest] = blob
                    c.execute('insert or replace into vector_cache values (?,?,?)',
                              (provider.fingerprint, digest, blob))
                encoded += len(pending)
            for ident, digest, blob in items:
                c.execute('insert into vectors values (?,?)', (ident, blob if blob is not None else produced[digest]))
            c.commit()
            if progress: progress(min(start + batch_size, len(rows)), len(rows))
        if rag.snapshot(root) != info['snapshot']:
            raise ValueError('Memory changed while embedding; rebuild index')
        for key, value in dict(vector_snapshot=info['snapshot'], vector_model=provider.fingerprint,
                               vector_dimension=str(provider.dimension),
                               vector_coverage='memory-only' if memory_only else ('scoped' if scopes is not None else 'all-chunks'),
                               vector_scopes=json.dumps(scopes)).items():
            c.execute('insert or replace into metadata values (?,?)', (key, value))
        c.commit()
        return dict(chunks=len(rows), encoded=encoded, cached=cached,
                    coverage='memory-only' if memory_only else ('scoped' if scopes is not None else 'all-chunks'))
    finally:
        c.close()


def vector_candidates(root, db, query, provider, limit=50, project=None, platform=None,
                      account=None, topic=None, memory_type=None):
    import numpy as np
    c = sqlite3.connect(Path(db).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        info = dict(c.execute('select key,value from metadata'))
        if info['root'] != str(Path(root).resolve()) or info.get('vector_snapshot') != rag.snapshot(root):
            raise ValueError('Vectors missing or stale; rebuild/encode first')
        if info.get('vector_model') != provider.fingerprint:
            raise ValueError('Query encoder does not match the indexed model')
        if int(info.get('vector_dimension', '0')) != provider.dimension:
            raise ValueError('Vector dimensions do not match')
        where, params = [], []
        for field, value in [('project', project), ('platform', platform), ('account', account)]:
            if value is not None: where.append(f'c.{field}=?'); params.append(value)
        sql = 'select c.meta,v.vector from chunks c join vectors v on c.id=v.id'
        if where: sql += ' where ' + ' and '.join(where)
        metadata, vectors = [], []
        inactive = memory_bridge.inactive_ids(memory_bridge.load(root))
        for raw, blob in c.execute(sql, params):
            item = json.loads(raw)
            if topic is not None and topic not in item['topics']: continue
            if memory_type is not None and item.get('memory_type', 'episodic' if item['kind']=='conversation' else 'semantic') != memory_type:
                continue
            if not memory_bridge.in_time(item): continue
            if item.get('event_id') in inactive: continue
            vector = np.frombuffer(blob, dtype='<f4')
            if vector.shape != (provider.dimension,) or not np.isfinite(vector).all():
                raise ValueError('Corrupt stored vector')
            metadata.append(item); vectors.append(vector)
        if not vectors: return [], info['vector_coverage']
        q = np.asarray(provider.encode([query], query=True), dtype=np.float32)
        if q.shape != (1, provider.dimension) or not np.isfinite(q).all() or np.linalg.norm(q) <= 0:
            raise ValueError('Invalid query embedding')
        q = q[0] / np.linalg.norm(q)
        scores = np.asarray(vectors) @ q
        found, seen = [], set()
        for index in np.argsort(-scores, kind='stable'):
            item = metadata[int(index)]
            key = rag.chunk_key(item)
            if key in seen: continue
            item.update(semantic_score=float(scores[index]))
            found.append(item); seen.add(key)
            if len(found) >= limit: break
        if rag.snapshot(root) != info['vector_snapshot']:
            raise ValueError('Memory changed during retrieval')
        return found, info['vector_coverage']
    finally:
        c.close()


def fuse(lists, constant=60):
    """Reciprocal rank fusion; no arbitrary mixing of incomparable score scales."""
    merged = {}
    for channel, items in lists:
        for rank, item in enumerate(items, 1):
            key = rag.chunk_key(item)
            if key not in merged: merged[key] = {**item, 'rrf_score':0.0, 'retrieval_channels':[]}
            merged[key]['rrf_score'] += 1 / (constant + rank)
            merged[key]['retrieval_channels'].append(channel)
            if 'semantic_score' in item: merged[key]['semantic_score'] = item['semantic_score']
    return sorted(merged.values(), key=lambda x: (-x['rrf_score'], x['path'], str(x['message_index']), x.get('char_offset', 0)))


def retrieve(root, db, query, provider, mode='hybrid', limit=8, **filters):
    if mode not in {'semantic', 'hybrid'} or not 1 <= limit <= 50:
        raise ValueError('Invalid retrieval mode/limit')
    candidates, coverage = vector_candidates(root, db, query, provider, 50, **filters)
    channels = [('semantic', candidates)]
    if mode == 'hybrid':
        channels.append(('keyword', rag.retrieve(root, db, query, 50, **filters)))
    results = fuse(channels)[:limit]
    verified = {}
    for number, item in enumerate(results, 1):
        path = (Path(root) / item['path']).resolve()
        if not path.is_relative_to(Path(root).resolve()): raise ValueError('Source escapes root')
        if item['path'] not in verified:
            verified[item['path']] = hashlib.sha256(path.read_bytes()).hexdigest()
        if verified[item['path']] != item['sha256']: raise ValueError('Source checksum changed')
        item.update(citation=f'R{number}', vector_coverage=coverage)
    return rag.annotate_conflicts(root, results)
