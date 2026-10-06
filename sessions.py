"""Session-aware optimistic concurrency for a serialized memory worker.

Actor IDs describe people; session IDs describe conversations, not applications.
This is consistency protection for cooperative clients, NOT an authorization ACL.
"""
import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

ID = re.compile(r'[a-f0-9]{32}')
DIGEST = re.compile(r'[a-f0-9]{64}')
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}')
CONTEXT_KEYS = {'actor_id', 'session_id', 'app_id', 'observed_revisions'}


class SessionConflict(ValueError):
    """Machine-readable failure without exposing source text."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def instant(value):
    stamp = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Timezone required')
    return stamp


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                   separators=(',', ':'), allow_nan=False).encode()).hexdigest()


EMPTY_REVISION = digest([])


def validate_context(context):
    if not isinstance(context, dict) or set(context) - CONTEXT_KEYS:
        raise ValueError('Invalid session context')
    for key in ('actor_id', 'app_id'):
        if not isinstance(context.get(key), str) or not LABEL.fullmatch(context[key]):
            raise ValueError('Invalid actor/app identifier')
    if not isinstance(context.get('session_id'), str) or not ID.fullmatch(context['session_id']):
        raise ValueError('Each conversation requires a random 32-hex session ID')
    versions = context.get('observed_revisions', {})
    if (not isinstance(versions, dict) or len(versions) > 100 or any(
            not isinstance(k, str) or not k.strip() or len(k) > 200
            or not isinstance(v, str) or not DIGEST.fullmatch(v) for k, v in versions.items())):
        raise ValueError('Invalid observed project revisions')
    return context


def origin(context):
    validate_context(context)
    return {key: context[key] for key in ('actor_id', 'session_id', 'app_id')}


def read_policy(root):
    path = Path(root) / 'memory/session-policy.json'
    if not path.exists():
        return {'version': 1, 'require_context': False, 'actors': [], 'legacy_actor_bindings': {}}
    policy = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(policy, dict) or policy.get('version') != 1
            or type(policy.get('require_context', False)) is not bool):
        raise ValueError('Invalid session policy')
    actors = policy.get('actors', [])
    bindings = policy.get('legacy_actor_bindings', {})
    if (not isinstance(actors, list) or len(actors) != len(set(actors))
            or any(not isinstance(a, str) or not LABEL.fullmatch(a) for a in actors)
            or not isinstance(bindings, dict)):
        raise ValueError('Invalid actor registry')
    for key, value in bindings.items():
        if (not isinstance(key, str) or not ID.fullmatch(key) or not isinstance(value, dict)
                or value.get('actor_id') not in actors or not isinstance(value.get('source'), str)
                or not value['source'].strip()):
            raise ValueError('Legacy actor bindings require explicit provenance')
    return policy


def actor(event, policy):
    explicit = event['scope'].get('actor_id')
    if explicit is not None:
        if not isinstance(explicit, str) or not LABEL.fullmatch(explicit):
            raise ValueError('Invalid event actor')
        return explicit
    return policy.get('legacy_actor_bindings', {}).get(event['id'], {}).get('actor_id', 'unknown')


def active_flags(events, at):
    # Match the canonical lifecycle, including persistent accepted replacements.
    hidden = {i for e in events for i in e.get('forgets', [])}
    while True:
        extra = {e['id'] for e in events if set(e.get('supersedes', [])) & hidden}
        if extra <= hidden:
            break
        hidden |= extra
    for e in events:
        if (e['status'] == 'confirmed' and e['evidence_role'] == 'user'
                and instant(e.get('valid_from') or e['created_at']) <= at):
            hidden.update(e.get('supersedes', []))
    return {e['id']: e['id'] not in hidden and e['kind'] != 'forget'
            and e['status'] in {'confirmed', 'candidate'}
            and (not e.get('valid_from') or instant(e['valid_from']) <= at)
            and (not e.get('expires_at') or at < instant(e['expires_at'])) for e in events}


def snapshot(events, policy=None, at=None):
    """Content/lifecycle hashes, not a heartbeat or the Git commit of this file itself."""
    policy = policy or {}
    at = at or dt.datetime.now(dt.timezone.utc)
    if at.tzinfo is None:
        raise ValueError('Timezone required')
    flags = active_flags(events, at)
    groups = {}
    transitions = []
    for e in sorted(events, key=lambda e: e['id']):
        groups.setdefault(e['scope']['project'], []).append(
            {'event': e, 'actor_id': actor(e, policy), 'active': flags[e['id']]})
        for name in ('valid_from', 'expires_at'):
            if e.get(name) and instant(e[name]) > at:
                transitions.append(instant(e[name]))
        if e.get('supersedes') and instant(e.get('valid_from') or e['created_at']) > at:
            transitions.append(instant(e.get('valid_from') or e['created_at']))
    projects = {name: digest(rows) for name, rows in sorted(groups.items())}
    return {'version': 1, 'generated_at': at.isoformat(), 'revision': digest(projects),
            'projects': projects, 'empty_project_revision': EMPTY_REVISION,
            'event_count': len(events), 'policy_revision': digest(policy),
            'next_transition_at': min(transitions).isoformat() if transitions else None,
            'scope': 'Canonical events only; not all transcripts, live conversations or an ACL.'}


def refresh_required(previous, current, at=None):
    """Clients must reload evidence before adopting a changed token; no blind retries."""
    at = at or dt.datetime.now(dt.timezone.utc)
    if not isinstance(previous, dict):
        return True
    for view in (previous, current):
        if not isinstance(view, dict) or view.get('version') != 1:
            return True
        try:
            if view.get('next_transition_at') and instant(view['next_transition_at']) <= at:
                return True
        except (ValueError, TypeError, AttributeError):
            return True
    return (previous.get('revision') != current.get('revision')
            or previous.get('policy_revision') != current.get('policy_revision'))


def require_context(root, item):
    policy = read_policy(root)
    context = item.get('context')
    if context is None:
        if policy.get('require_context'):
            raise SessionConflict('session_context_required')
        return policy, None
    validate_context(context)
    if policy.get('actors') and context['actor_id'] not in policy['actors']:
        raise SessionConflict('actor_not_registered')
    return policy, context


def prepare_write(root, item, events, at=None):
    """One preflight per request. No filesystem changes; preserve the caller's input."""
    policy, context = require_context(root, item)
    if context is None:
        return item  # Explicit legacy compatibility when the owner has not opted in.
    result = copy.deepcopy(item)
    payloads = result.get('events', [result.get('event')])
    if not payloads or not all(isinstance(e, dict) for e in payloads):
        raise ValueError('Invalid event payload')
    # Stable own IDs allow retries after a crash between event write and receipt write.
    own = {hashlib.sha256((item['id'] + (':event' if len(payloads) == 1 else ':event:' + str(i))).encode()).hexdigest()[:32]
           for i in range(len(payloads))}
    existing = [e for e in events if e['id'] not in own]
    versions = snapshot(existing, policy, at)['projects']
    flags = active_flags(existing, at or dt.datetime.now(dt.timezone.utc))
    by_id = {e['id']: e for e in existing}
    observed = context.get('observed_revisions', {})
    for e in payloads:
        if not isinstance(e.get('scope'), dict):
            raise ValueError('Invalid event scope')
        if e['scope'].get('actor_id', context['actor_id']) != context['actor_id']:
            raise SessionConflict('actor_context_mismatch')
        if e.get('origin') not in (None, origin(context)):
            raise SessionConflict('origin_context_mismatch')
        e['scope']['actor_id'] = context['actor_id']
        e['origin'] = origin(context)
        changes = (item.get('operation') == 'forget' or e.get('kind') in {'correction', 'forget', 'project_state', 'decision'}
                   or bool(e.get('supersedes')) or bool(e.get('claim')))
        if context['actor_id'] == 'unknown' and (changes or e.get('status') == 'confirmed'):
            raise SessionConflict('actor_confirmation_required')
        project = e['scope']['project']
        if changes:
            expected = observed.get(project)
            if expected is None:
                raise SessionConflict('observed_revision_required')
            if expected != versions.get(project, EMPTY_REVISION):
                raise SessionConflict('stale_project_revision')
        for key in ('supersedes', 'forgets'):
            for target in e.get(key, []):
                prior = by_id.get(target)
                if prior is None:
                    raise SessionConflict('unknown_replacement_target')
                if actor(prior, policy) == 'unknown':
                    raise SessionConflict('legacy_actor_unresolved')
                if actor(prior, policy) != context['actor_id']:
                    raise SessionConflict('cross_actor_replacement')
                if not flags[target]:
                    raise SessionConflict('inactive_replacement_target')
    return result


def checkpoint_payload(root, item):
    _, context = require_context(root, item)
    payload = copy.deepcopy(item.get('checkpoint', {}))
    payload['project'] = item['project']
    if context is not None:
        if context['actor_id'] == 'unknown':
            raise SessionConflict('actor_confirmation_required')
        if payload.get('session_context') not in (None, origin(context)):
            raise SessionConflict('actor_context_mismatch')
        payload['session_context'] = origin(context)
    return payload


def bind_receipt(row, item):
    if item.get('context') is not None:
        row['session_context'] = origin(item['context'])
    return row


def write_snapshot(root):
    import memory_bridge
    from cloud import write_json
    root = Path(root)
    view = snapshot(memory_bridge.load(root), read_policy(root))
    write_json(root / 'memory/revision.json', view)
    return view


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    args = parser.parse_args()
    print(json.dumps(write_snapshot(args.root), ensure_ascii=False))


if __name__ == '__main__':
    main()
