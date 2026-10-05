#!/usr/bin/env python3
"""Portable, local-first memory events. Python standard library only."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import uuid
import privacy

STATUSES = {'candidate', 'confirmed', 'historical', 'superseded'}
KINDS = {'preference', 'fact', 'decision', 'project_state', 'correction', 'forget'}
REQUIRED = {'version', 'id', 'created_at', 'kind', 'status', 'text', 'scope',
            'source', 'evidence_role', 'supersedes'}
SECRET = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|'
                    r'-----BEGIN [A-Z ]*PRIVATE KEY-----|'
                    r'(?i:password|api[_-]?key|access[_-]?token)\s*[:=]\s*\S+)')


def instant(value):
    when = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if when.tzinfo is None:
        raise ValueError('Timestamps require a timezone')
    return when


def in_time(event, at=None):
    at = at or dt.datetime.now(dt.timezone.utc)
    return ((not event.get('valid_from') or instant(event['valid_from']) <= at)
            and (not event.get('expires_at') or at < instant(event['expires_at'])))


def forgotten_ids(events):
    hidden = {ident for e in events for ident in e.get('forgets', [])}
    # A correction cannot accidentally resurrect a forgotten event.
    while True:
        extra = {e['id'] for e in events if set(e['supersedes']) & hidden}
        if extra <= hidden:
            break
        hidden |= extra
    return hidden


def inactive_ids(events, at=None):
    at = at or dt.datetime.now(dt.timezone.utc)
    hidden = forgotten_ids(events)
    hidden |= {ident for e in events for ident in e['supersedes']
               if not e.get('valid_from') or instant(e['valid_from']) <= at}
    return hidden


def conflicts(events):
    """Report explicit fact-key disagreements, never guess contradictions from prose."""
    grouped = {}
    hidden = inactive_ids(events)
    for e in events:
        claim = e.get('claim')
        if not claim or e['id'] in hidden or e['kind'] == 'forget' or not in_time(e):
            continue
        if e['status'] not in {'confirmed', 'candidate'}:
            continue
        key = (e['scope']['project'], claim['subject'], claim['predicate'])
        grouped.setdefault(key, []).append(e)
    return [{'project':key[0], 'subject':key[1], 'predicate':key[2],
             'event_ids':[e['id'] for e in rows], 'resolution':'unresolved'}
            for key, rows in grouped.items()
            if len({json.dumps(e['claim']['value'], sort_keys=True) for e in rows}) > 1]


def validate(event):
    if not isinstance(event, dict) or REQUIRED - event.keys():
        raise ValueError('Missing required event fields')
    if event['version'] != 1 or not re.fullmatch(r'[a-f0-9]{32}', event['id']):
        raise ValueError('Unsupported version or invalid id')
    if event['kind'] not in KINDS or event['status'] not in STATUSES:
        raise ValueError('Invalid kind/status')
    if not isinstance(event['text'], str) or not event['text'].strip():
        raise ValueError('Memory text must be nonempty')
    if len(event['text']) > 12000:
        raise ValueError('Memory text exceeds 12000 characters; link longer source material')
    instant(event['created_at'])
    for field in ('valid_from', 'expires_at'):
        if event.get(field): instant(event[field])
    if event.get('valid_from') and event.get('expires_at'):
        if instant(event['valid_from']) >= instant(event['expires_at']):
            raise ValueError('valid_from must precede expires_at')
    if 'importance' in event and (isinstance(event['importance'], bool)
            or not isinstance(event['importance'], (int, float))
            or not 0 <= event['importance'] <= 1):
        raise ValueError('importance must be between 0 and 1')
    if event.get('memory_type', 'semantic') not in {'semantic', 'episodic', 'procedural'}:
        raise ValueError('Invalid memory_type')
    if 'claim' in event:
        claim = event['claim']
        if not isinstance(claim, dict) or not all(isinstance(claim.get(k), str) and claim[k].strip()
                for k in ('subject', 'predicate')) or 'value' not in claim:
            raise ValueError('claim requires subject, predicate and value')
    targets = event.get('forgets', [])
    if not isinstance(targets, list) or any(not isinstance(x, str) or not re.fullmatch(r'[a-f0-9]{32}', x)
                                           for x in targets):
        raise ValueError('forgets must contain event IDs')
    if event['kind'] == 'forget':
        if not targets or event['evidence_role'] != 'user' or event['supersedes'] or event['status'] != 'confirmed':
            raise ValueError('Forget requires user evidence, targets and no supersedes')
        if event.get('valid_from') or event.get('expires_at'):
            raise ValueError('Forget markers are immediate and persistent')
    elif targets:
        raise ValueError('Only forget events may include forgets')
    if event['id'] in targets:
        raise ValueError('An event cannot forget itself')
    related = event.get('related', [])
    if not isinstance(related, list) or any(not isinstance(x,str) or not re.fullmatch(r'[a-f0-9]{32}',x) for x in related):
        raise ValueError('related must contain event IDs')
    if event['id'] in related: raise ValueError('An event cannot relate to itself')
    scope = event['scope']
    if not isinstance(scope, dict) or not all(isinstance(scope.get(k), str) and scope[k].strip()
                                            for k in ('project', 'platform', 'account')):
        raise ValueError('Scope requires project, platform and account')
    source = event['source']
    if not isinstance(source, dict) or not all(isinstance(source.get(k), str) and source[k].strip()
                                             for k in ('reference', 'excerpt')):
        raise ValueError('Source requires reference and evidence excerpt')
    if event['evidence_role'] not in {'user', 'assistant', 'observation'}:
        raise ValueError('Invalid evidence role')
    if event['status'] == 'confirmed' and event['evidence_role'] != 'user':
        raise ValueError('Confirmed memory requires direct user evidence')
    if not isinstance(event['supersedes'], list) or any(
            not isinstance(x, str) or not re.fullmatch(r'[a-f0-9]{32}', x)
            for x in event['supersedes']):
        raise ValueError('supersedes must be a list of event IDs')
    if event['id'] in event['supersedes']:
        raise ValueError('An event cannot supersede itself')
    privacy.require_clean(event)
    if SECRET.search(json.dumps(event, ensure_ascii=False)):
        raise ValueError('Possible credential detected; remove it before saving')
    return event


def load(root):
    events = []
    for path in sorted((Path(root) / 'memory/events').glob('*/*.json')):
        event = validate(json.loads(path.read_text(encoding='utf-8')))
        if path.stem != event['id'] or path.parent.name != event['created_at'][:7]:
            raise ValueError('Event filename/month does not match its identity/date')
        events.append(event)
    ids = [e['id'] for e in events]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate event ID')
    known = set(ids)
    by_id = {e['id']: e for e in events}
    for event in events:
        for old in event['supersedes'] + event.get('forgets', []) + event.get('related', []):
            if old not in known:
                raise ValueError('Replacement references an unknown event')
            if by_id[old]['scope']['project'] != event['scope']['project']:
                raise ValueError('Replacement crosses project scope')
    # Reject cycles, including ones introduced by direct GitHub API writes.
    visited, visiting = set(), set()
    def walk(ident):
        if ident in visiting:
            raise ValueError('Cyclic supersedes references')
        if ident in visited:
            return
        visiting.add(ident)
        for old in by_id[ident]['supersedes']:
            walk(old)
        visiting.remove(ident)
        visited.add(ident)
    for ident in ids:
        walk(ident)
    return events


def save(root, event):
    validate(event)
    existing = load(root)
    by_id = {e['id']: e for e in existing}
    for old in event['supersedes'] + event.get('forgets', []) + event.get('related', []):
        if old not in by_id or by_id[old]['scope']['project'] != event['scope']['project']:
            raise ValueError('Replacement must reference existing events in the same project')
    target = Path(root) / 'memory/events' / event['created_at'][:7] / (event['id'] + '.json')
    if event['id'] in by_id:
        if by_id[event['id']] == event:
            return target  # Idempotent retry of an unchanged event.
        raise ValueError('Event ID already exists with different content')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as f:
        f.write(json.dumps(event, ensure_ascii=False, indent=2) + '\n')
    return target


def search(root, query='', project=None, platform=None, account=None, history=False):
    events = load(root)
    replaced = inactive_ids(events)
    found = []
    for e in events:
        if not history and (e['id'] in replaced or e['status'] in {'superseded', 'historical'}
                            or e['kind'] == 'forget' or not in_time(e)):
            continue
        if any(value is not None and e['scope'][key] != value for key, value in
               [('project', project), ('platform', platform), ('account', account)]):
            continue
        if query.casefold() not in (e['text'] + '\n' + e['source']['excerpt']).casefold():
            continue
        found.append(e)
    return sorted(found, key=lambda e: (e['created_at'], e['id']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.', help='Private memory checkout')
    sub = parser.add_subparsers(dest='command', required=True)
    add = sub.add_parser('add', help='Create an event from reviewed JSON; no Git push')
    add.add_argument('input', help='JSON event; id and created_at may be omitted')
    find = sub.add_parser('search', help='Find scoped memory events')
    find.add_argument('query', nargs='?', default='')
    for field in ('project', 'platform', 'account'):
        find.add_argument('--' + field)
    find.add_argument('--history', action='store_true')
    sub.add_parser('validate', help='Validate all event files')
    sub.add_parser('conflicts', help='Report unresolved explicit claim disagreements')
    args = parser.parse_args()
    try:
        if args.command == 'add':
            event = json.loads(Path(args.input).read_text(encoding='utf-8'))
            event.setdefault('id', uuid.uuid4().hex)
            event.setdefault('created_at', dt.datetime.now(dt.timezone.utc).isoformat())
            print(save(args.root, event))
        elif args.command == 'search':
            print(json.dumps(search(args.root, args.query, args.project, args.platform,
                                    args.account, args.history), ensure_ascii=False, indent=2))
        elif args.command == 'conflicts':
            print(json.dumps(conflicts(load(args.root)), ensure_ascii=False, indent=2))
        else:
            print(f'Validated {len(load(args.root))} memory events')
    except (ValueError, OSError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
