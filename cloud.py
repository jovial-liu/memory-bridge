#!/usr/bin/env python3
"""Source-preserving memory writes, isolated queue processing, and truthful receipts."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import memory_bridge
import privacy
import rag
import sessions

WRITE_OPS = {'write', 'sync', 'forget'}
SCOPES = ('project', 'platform', 'account', 'topic', 'memory_type')
ID = re.compile(r'[a-f0-9]{32}')


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize_event_payload(event):
    """Read legacy connector aliases; never change the source excerpt or status."""
    event = dict(event)
    if event.get('evidence_role') in {'user_direct_confirmation', 'user-confirmed', 'direct-user'}:
        event['evidence_role'] = 'user'
    scope = dict(event.get('scope') or {})
    scope.setdefault('project', scope.get('topic') or 'unknown')
    scope.setdefault('platform', 'user-statement')
    scope.setdefault('account', 'unknown')
    event['scope'] = scope
    kind = event.get('kind')
    if kind not in memory_bridge.KINDS:
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError('Event kind must be a nonempty string')
        event.setdefault('original_kind', kind)
        label = kind.casefold()
        if any(t in label for t in ('preference', 'style', 'behavior', 'workflow')):
            event['kind'] = 'preference'
        elif any(t in label for t in ('plan', 'goal', 'strategy', 'principle', 'direction', 'structure', 'priority')):
            event['kind'] = 'decision'
        else:
            event['kind'] = 'fact'
    return event


def request_events(item):
    if 'event' in item and 'events' in item:
        raise ValueError('Use event or events, not both')
    if 'events' in item:
        events = item['events']
        if not isinstance(events, list) or not 1 <= len(events) <= 100:
            raise ValueError('events must contain 1..100 objects')
    elif 'event' in item:
        events = [item['event']]
    else:
        return []
    if not all(isinstance(e, dict) for e in events):
        raise ValueError('Event payloads must be objects')
    return [normalize_event_payload(e) for e in events]


def validate_request(item, ident):
    if not isinstance(item, dict) or not ID.fullmatch(ident) or item.get('id') != ident:
        raise ValueError('Request ID/path mismatch')
    op = item.get('operation', 'recall')
    if op not in {'recall', 'write', 'sync', 'forget', 'graph', 'reflect', 'checkpoint', 'resume', 'conflicts', 'evaluate', 'revision'}:
        raise ValueError('Unsupported operation')
    if op in {'recall', 'sync'}:
        if not isinstance(item.get('query'), str) or not 1 <= len(item['query'].strip()) <= 2000:
            raise ValueError('Query must be 1..2000 characters')
    if op in {'graph', 'reflect', 'checkpoint', 'resume'} and not item.get('project'):
        raise ValueError('Operation requires explicit project')
    if op == 'evaluate' and (not isinstance(item.get('cases_path'), str) or not re.fullmatch(r'memory/evaluation/[A-Za-z0-9_.-]+\.json', item['cases_path'])):
        raise ValueError('Evaluation requires a safe memory/evaluation JSON path')
    if op in WRITE_OPS and not request_events(item):
        raise ValueError('Write-like operations require event or events')
    if item.get('created_at'):
        memory_bridge.instant(item['created_at'])
    if 'context' in item:
        sessions.validate_context(item['context'])
    if 'resume_session_id' in item:
        if op != 'resume' or not isinstance(item['resume_session_id'], str) or not ID.fullmatch(item['resume_session_id']) or 'context' not in item:
            raise ValueError('Explicit session resume requires a valid context and session ID')
    if item.get('mode', 'hybrid') not in {'keyword', 'semantic', 'hybrid'}:
        raise ValueError('Invalid query mode')
    for key, default, low, high in [('limit', 8, 1, 50), ('budget', 12000, 300, 50000)]:
        v = item.get(key, default)
        if isinstance(v, bool) or not isinstance(v, int) or not low <= v <= high:
            raise ValueError('Invalid ' + key)
    for key in SCOPES:
        v = item.get(key)
        if v is not None and (not isinstance(v, str) or not v.strip() or len(v) > 200):
            raise ValueError('Invalid scope field')
    privacy.require_clean(item)
    return item


def write_json(path, item, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(item, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if exclusive:
        with path.open('x', encoding='utf-8') as handle:
            handle.write(text)
        return
    fd, name = tempfile.mkstemp(prefix='.memory-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
        os.replace(name, path)
    finally:
        if Path(name).exists():
            Path(name).unlink()


def outcome(row):
    """Execution completion is not the same as a passing evaluation."""
    if not isinstance(row, dict):
        return 'invalid'
    if row.get('status') == 'failed' or row.get('error'):
        return 'failed'
    if row.get('status', 'succeeded') != 'succeeded':
        return 'invalid'
    if row.get('operation') == 'evaluate':
        report = row.get('result')
        if not isinstance(report, dict):
            return 'invalid'
        total, passed = report.get('total'), report.get('passed')
        if type(total) is not int or type(passed) is not int or total <= 0 or not 0 <= passed <= total:
            return 'invalid'
        if passed != total:
            return 'failed'
    return 'succeeded'


def pending(root, quarantine=False):
    """Strict by default; the worker quarantines bad inputs without blocking siblings."""
    root = Path(root)
    jobs = []
    for path in sorted((root / 'memory/requests').glob('*.json')):
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        ident = path.stem
        failure_id = ident if ID.fullmatch(ident) else hashlib.sha256(path.name.encode()).hexdigest()[:32]
        failure = root / 'memory/failures' / (failure_id + '.json')
        if quarantine and failure.exists():
            continue
        try:
            item = validate_request(json.loads(raw), ident)
            result = root / 'memory/results' / (ident + '.json')
            if result.exists():
                saved = json.loads(result.read_text(encoding='utf-8'))
                if saved.get('id') != ident or saved.get('request_sha256') != digest:
                    raise ValueError('Processed request changed; use a fresh request ID')
                if outcome(saved) == 'invalid':
                    raise ValueError('Invalid result receipt')
                continue
            jobs.append((item, digest))
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
            if not quarantine:
                raise
            write_json(failure, dict(id=failure_id, request_sha256=digest, status='failed',
                                     generated_at=utcnow(), error_code='request_validation_or_integrity',
                                     retry='Create a new request ID after reviewing the original input.'), exclusive=True)
    return jobs


def comparable_event(event):
    """Preserve every field except assigned identity and recording time, including provenance."""
    return {k: v for k, v in event.items() if k not in {'id', 'version', 'created_at'}}


def write_event(root, item, event=None, index=0, total=1, kind=None):
    root = Path(root)
    event = normalize_event_payload(event if event is not None else item.get('event', {}))
    if kind:
        event['kind'] = kind
    suffix = ':event' if total == 1 else ':event:' + str(index)
    ident = hashlib.sha256((item['id'] + suffix).encode()).hexdigest()[:32]
    existing = memory_bridge.load(root)
    own = next((e for e in existing if e['id'] == ident), None)
    timestamp = own['created_at'] if own else item.get('created_at', utcnow())
    event.update(version=1, id=ident, created_at=timestamp)
    event.setdefault('supersedes', [])
    memory_bridge.validate(event)
    if own is not None:
        path = memory_bridge.save(root, event)
        return dict(event_id=ident, path=path.relative_to(root).as_posix(), deduplicated=False)
    structural = any(event.get(k) for k in ('supersedes', 'related', 'forgets'))
    reusable = event['kind'] in {'fact', 'preference', 'decision'} and event.get('memory_type', 'semantic') != 'episodic'
    if reusable and not structural:
        inactive = memory_bridge.inactive_ids(existing)
        for prior in existing:
            if prior['id'] in inactive or prior['status'] not in {'confirmed', 'candidate'} or not memory_bridge.in_time(prior):
                continue
            if comparable_event(prior) == comparable_event(event):
                path = root / 'memory/events' / prior['created_at'][:7] / (prior['id'] + '.json')
                return dict(event_id=prior['id'], path=path.relative_to(root).as_posix(), deduplicated=True)
    path = memory_bridge.save(root, event)
    return dict(event_id=ident, path=path.relative_to(root).as_posix(), deduplicated=False)


def write_events(root, item, kind=None):
    """Guard the session, then preflight the entire request in an isolated event tree.

    Git publication is atomic. Filesystem rollback handles ordinary I/O exceptions,
    not every possible crash. Stable IDs support retries.
    """
    root = Path(root)
    normalized = {k: v for k, v in item.items() if k not in {'event', 'events'}}
    normalized['events'] = request_events(item)
    if kind:
        for e in normalized['events']:
            e['kind'] = kind
    guarded = sessions.prepare_write(root, normalized, memory_bridge.load(root))
    events = guarded['events']
    with tempfile.TemporaryDirectory(prefix='memory-preflight-') as folder:
        staged = Path(folder)
        original = root / 'memory/events'
        if original.exists():
            shutil.copytree(original, staged / 'memory/events')
        request = dict(guarded)
        request.setdefault('created_at', utcnow())
        rows = [write_event(staged, request, e, i, len(events), kind) for i, e in enumerate(events)]
        memory_bridge.load(staged)
        created = []
        try:
            for source in sorted((staged / 'memory/events').glob('*/*.json')):
                target = root / source.relative_to(staged)
                data = source.read_bytes()
                if target.exists():
                    if target.read_bytes() != data:
                        raise ValueError('Concurrent event conflict')
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as handle:
                    created.append(target)
                    handle.write(data)
            memory_bridge.load(root)
        except Exception:
            for target in reversed(created):
                target.unlink(missing_ok=True)
            raise
    return rows[0] if len(rows) == 1 else dict(count=len(rows), events=rows)


def receipt(item, digest):
    row = dict(id=item['id'], request_sha256=digest, generated_at=utcnow(),
               execution='github-actions', operation=item.get('operation', 'recall'),
               status='succeeded', base_commit=os.environ.get('GITHUB_SHA', 'unknown'),
               workflow_url=os.environ.get('MEMORY_RUN_URL', 'unknown'))
    return sessions.bind_receipt(row, item)


def finish(root, row):
    write_json(Path(root) / 'memory/results' / (row['id'] + '.json'), row, exclusive=True)
    print('Processed request ' + row['id'] + ' status=' + row['status'], flush=True)


def fail(row, stage, error=None):
    # Never serialize arbitrary exception text; it can contain private content.
    code = error.code if isinstance(error, sessions.SessionConflict) else stage
    row.update(status='failed', error_code=code,
               retry='Reload the affected evidence, reconcile changes, then use a new request ID. Do not blindly replace revision tokens.')


def run(root, db, model_dir):
    import manager
    root = Path(root).resolve()
    jobs = pending(root, quarantine=True)
    memory_bridge.load(root)
    remaining = []
    for item, digest in jobs:
        op = item.get('operation', 'recall')
        row = receipt(item, digest)
        try:
            if op in WRITE_OPS:
                result = write_events(root, item, 'forget' if op == 'forget' else None)
                row['write' if op == 'sync' else 'result'] = result
            elif op == 'checkpoint':
                row['result'] = manager.checkpoint(root, item['id'], sessions.checkpoint_payload(root, item))
        except Exception as exc:
            fail(row, 'write_or_checkpoint_failed', exc)
            finish(root, row)
            continue
        if op in {'write', 'forget', 'checkpoint'}:
            finish(root, row)
        else:
            remaining.append((item, row))
    recalls = [i for i, _ in remaining if i.get('operation', 'recall') in {'recall', 'sync'}]
    provider = None
    index_error = semantic_error = False
    if recalls:
        try:
            rag.build(root, db)
        except Exception:
            index_error = True
        semantic_jobs = [i for i in recalls if i.get('mode', 'hybrid') != 'keyword']
        if semantic_jobs and not index_error:
            try:
                from embeddings import LocalE5, download
                from semantic import embed
                directory = Path(model_dir)
                if not (directory / 'manifest.json').exists():
                    download(directory)
                provider = LocalE5(directory)
                scopes = [{key: i.get(key) for key in SCOPES} for i in semantic_jobs]
                if any(all(v is None for v in s.values()) for s in scopes):
                    scopes = None
                embed(root, db, provider, batch_size=64, scopes=scopes)
            except Exception:
                semantic_error = True
    remaining.sort(key=lambda pair: pair[0].get('operation') == 'reflect' and pair[0].get('save', False))
    for item, row in remaining:
        op = item.get('operation', 'recall')
        try:
            if op in {'recall', 'sync'}:
                mode = item.get('mode', 'hybrid')
                if index_error or (mode != 'keyword' and semantic_error):
                    raise RuntimeError('Retrieval initialization failed')
                filters = {key: item.get(key) for key in SCOPES}
                if mode == 'keyword':
                    hits = rag.retrieve(root, db, item['query'], item.get('limit', 8), **filters)
                else:
                    from semantic import retrieve
                    hits = retrieve(root, db, item['query'], provider, mode, item.get('limit', 8), **filters)
                row.update(mode=mode, filters=filters, results=hits, index_snapshot=rag.snapshot(root),
                           context=rag.bundle(hits, item.get('budget', 12000)))
                if item.get('context'):
                    row['actor_filter_enforced'] = False
                    row['attribution_notice'] = 'Shared archive retrieval is not an actor ACL. Verify the speaker and source before adopting a hit.'
            elif op == 'resume':
                row['result'] = manager.resume(root, item['project'], item.get('task_id'),
                                               item.get('context'), item.get('resume_session_id'))
            elif op == 'graph':
                row['result'] = manager.graph(root, item['project'], item.get('entity'), item.get('hops', 1))
            elif op == 'conflicts':
                row['result'] = memory_bridge.conflicts(memory_bridge.load(root))
            elif op == 'revision':
                row['result'] = sessions.snapshot(memory_bridge.load(root), sessions.read_policy(root))
            elif op == 'evaluate':
                from evaluate import evaluate
                evaluation_db = Path(db).with_name(Path(db).stem + '.evaluation.sqlite3')
                row['result'] = evaluate(root, evaluation_db, json.loads((root / item['cases_path']).read_text(encoding='utf-8')))
                if outcome(row) != 'succeeded':
                    fail(row, 'evaluation_assertions_failed')
            elif op == 'reflect':
                row['result'] = manager.reflect(root, item['project'])
                if item.get('save'):
                    rows = row['result']['items']
                    draft = dict(kind='fact', status='candidate',
                                 text=('Evidence consolidation:\n' + '\n'.join('[' + e['status'] + '] ' + e['text'] for e in rows))[:10000],
                                 scope=dict(project=item['project'], platform='memory-cloud', account='unknown'),
                                 source=dict(reference='memory/results/' + item['id'] + '.json', excerpt='Derived from event IDs: ' + ','.join(e['id'] for e in rows)),
                                 evidence_role='assistant', supersedes=[], related=[e['id'] for e in rows])
                    row['draft'] = write_events(root, {**item, 'event': draft})
        except Exception as exc:
            fail(row, 'operation_failed', exc)
            if 'write' in row:
                row['write_applied'] = True
        finish(root, row)
    return len(jobs)


def build_now(root, limit=12, budget=6000):
    root = Path(root)
    events = memory_bridge.load(root)
    inactive = memory_bridge.inactive_ids(events)
    rows = [e for e in events if e['id'] not in inactive and e['status'] == 'confirmed'
            and e['kind'] != 'forget' and memory_bridge.in_time(e)
            and (e.get('stability') in {'temporary', 'evolving'} or e['kind'] == 'project_state' or e.get('expires_at'))]
    rows.sort(key=lambda e: (float(e.get('importance', 0)), memory_bridge.instant(e['created_at']), e['id']), reverse=True)
    conflicts = {i for group in memory_bridge.conflicts(events) for i in group['event_ids']}
    policy = sessions.read_policy(root)
    lines = ['# NOW · current memory state', '', '> GENERATED from memory/events; do not edit manually.',
             '', 'Generated: ' + utcnow(), '',
             'Snapshot, not a fresh confirmation. Check validity and sources before acting.',
             'Budget: ' + str(budget) + ' characters; omitted items remain in the event log.', '']
    selected = []
    for e in rows:
        warning = 'UNRESOLVED CONFLICT · ' if e['id'] in conflicts else ''
        path = 'events/' + e['created_at'][:7] + '/' + e['id'] + '.json'
        block = '- ' + warning + e['text'].replace('\n', ' ') + '\n  [' + e['scope']['project'] + ' · source](' + path + ')'
        block += ' · actor ' + sessions.actor(e, policy) + ' · recorded ' + e['created_at']
        if e.get('expires_at'):
            block += ' · expires ' + e['expires_at']
        block += '\n'
        if len(selected) >= limit:
            break
        if len('\n'.join(lines)) + len(block) + 100 > budget:
            continue
        lines.append(block); selected.append(e)
    lines.append('Omitted matching events: ' + str(len(rows) - len(selected)) + '.')
    if not rows:
        lines.append('No currently valid state events matched.')
    target = root / 'memory/NOW.md'; target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return selected


def status_snapshot(root, phase='idle'):
    root = Path(root)
    counts = dict(succeeded=0, failed_known=0, integrity_errors=0, pending=0)
    pending_ids = []
    last = None
    paths = sorted((root / 'memory/requests').glob('*.json'))
    for path in paths:
        ident = path.stem
        failure_id = ident if ID.fullmatch(ident) else hashlib.sha256(path.name.encode()).hexdigest()[:32]
        result = root / 'memory/results' / (ident + '.json')
        failure = root / 'memory/failures' / (failure_id + '.json')
        if failure.exists():
            counts['failed_known'] += 1
            continue
        if not result.exists():
            counts['pending'] += 1; pending_ids.append(failure_id)
            continue
        try:
            row = json.loads(result.read_text(encoding='utf-8'))
            if row.get('id') != ident or row.get('request_sha256') != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError('Receipt digest mismatch')
            state = outcome(row)
            if state == 'invalid':
                raise ValueError('Malformed receipt')
            memory_bridge.instant(row['generated_at'])
            counts['succeeded' if state == 'succeeded' else 'failed_known'] += 1
            if state == 'succeeded' and (last is None or memory_bridge.instant(row['generated_at']) > memory_bridge.instant(last['generated_at'])):
                last = row
        except (ValueError, TypeError, KeyError, AttributeError):
            counts['integrity_errors'] += 1
    effective = phase
    if phase == 'completed':
        effective = 'completed_with_errors' if counts['failed_known'] or counts['integrity_errors'] else ('pending' if counts['pending'] else 'completed')
    payload = dict(version=2, generated_at=utcnow(), phase=effective, requested_phase=phase,
                   requests_total=len(paths), **counts, pending_ids=pending_ids[:100],
                   last_completed_at=last['generated_at'] if last else None,
                   last_workflow_url=os.environ.get('MEMORY_RUN_URL') or (last.get('workflow_url') if last else None),
                   status_semantics='Snapshot; historical failed evaluations count as failed; not live worker liveness.')
    try:
        build_now(root)
        payload['memory_revision'] = sessions.write_snapshot(root)['revision']
    except Exception:
        payload['view_error'] = 'event_corpus_or_projection_failed'
    write_json(root / 'memory/status.json', payload)
    return payload


def publish(root, status_only=False):
    """Never force-push; do not merge already-validated writes across changed canonical data."""
    root = Path(root)
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True)
    branch = os.environ.get('MEMORY_BRANCH', 'main')
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', branch) or branch.startswith('-') or '..' in branch:
        raise ValueError('Invalid destination branch')
    git('config', 'user.name', 'github-actions[bot]')
    git('config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
    names = ['memory/status.json'] if status_only else ['memory/results', 'memory/events', 'memory/failures', 'memory/working', 'memory/status.json', 'memory/NOW.md', 'memory/revision.json']
    paths = [name for name in names if (root / name).exists()]
    if not paths:
        return
    git('add', *paths)
    if not git('diff', '--cached', '--name-only').stdout.strip():
        return
    git('commit', '-m', 'Save memory receipts and projections')
    for _ in range(3):
        try:
            git('push', 'origin', 'HEAD:' + branch)
            return
        except subprocess.CalledProcessError:
            old_remote = git('rev-parse', 'origin/' + branch).stdout.strip()
            git('fetch', 'origin', branch)
            changed = git('diff', '--name-only', old_remote, 'origin/' + branch, '--',
                          'memory/events', 'memory/working', 'memory/session-policy.json').stdout.strip()
            if changed and not status_only:
                raise ValueError('Canonical data changed during publication; retry from a fresh checkout') from None
            try:
                git('rebase', 'origin/' + branch)
            except subprocess.CalledProcessError:
                git('rebase', '--abort')
                raise ValueError('Concurrent content conflict; no force overwrite') from None
            if (root / 'memory/status.json').exists():
                old = json.loads((root / 'memory/status.json').read_text(encoding='utf-8'))
                status_snapshot(root, old.get('requested_phase', 'completed'))
                if not status_only:
                    build_now(root)
                git('add', *paths)
                if git('diff', '--cached', '--name-only').stdout.strip():
                    git('commit', '--amend', '--no-edit')
    raise ValueError('Could not publish after concurrent branch updates')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('pending'); sub.add_parser('publish'); sub.add_parser('publish-status')
    state = sub.add_parser('status')
    state.add_argument('--phase', default='idle', choices=['idle', 'running', 'completed', 'failed'])
    work = sub.add_parser('run'); work.add_argument('--db', required=True); work.add_argument('--model-dir', required=True)
    a = p.parse_args()
    if a.command == 'pending':
        before = set((Path(a.root) / 'memory/failures').glob('*.json'))
        jobs = pending(a.root, quarantine=True)
        rejected = bool(set((Path(a.root) / 'memory/failures').glob('*.json')) - before)
        semantic = any(i.get('operation', 'recall') in {'recall', 'sync'} and i.get('mode', 'hybrid') != 'keyword' for i, _ in jobs)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as handle:
                handle.write('pending=' + str(bool(jobs)).lower() + '\nsemantic=' + str(semantic).lower() + '\nrejected=' + str(rejected).lower() + '\n')
        print(str(len(jobs)) + ' eligible memory requests')
    elif a.command in {'publish', 'publish-status'}:
        publish(a.root, status_only=a.command == 'publish-status')
    elif a.command == 'status':
        payload = status_snapshot(a.root, a.phase)
        if a.phase != 'failed':
            build_now(a.root)
        print(json.dumps(payload))
    else:
        before = set((Path(a.root) / 'memory/results').glob('*.json'))
        failures_before = set((Path(a.root) / 'memory/failures').glob('*.json'))
        print('Processed ' + str(run(a.root, a.db, a.model_dir)) + ' requests')
        build_now(a.root)
        status_snapshot(a.root, 'completed')
        new_results = set((Path(a.root) / 'memory/results').glob('*.json')) - before
        new_failures = set((Path(a.root) / 'memory/failures').glob('*.json')) - failures_before
        if new_failures or any(outcome(json.loads(path.read_text(encoding='utf-8'))) != 'succeeded' for path in new_results):
            raise SystemExit(2)


if __name__ == '__main__':
    main()
