"""Read a revision manifest at one Git commit; no background polling or writes."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import quote
import uuid

import bridge
import sessions


def inspect(repository, actor_id, app_id, session_id=None, previous=None, api=None):
    bridge.validate_options(repository, 0, 5)
    context = dict(actor_id=actor_id, app_id=app_id, session_id=session_id or uuid.uuid4().hex)
    sessions.validate_context(context)
    api = api or bridge.api
    metadata = api(repository, '')
    if not isinstance(metadata, dict) or metadata.get('private') is not True:
        raise ValueError('Memory must remain in a private repository')
    branch = metadata.get('default_branch')
    if not isinstance(branch, str) or not branch:
        raise ValueError('Missing repository default branch')
    ref = api(repository, 'git/ref/heads/' + quote(branch, safe=''))
    sha = ref.get('object', {}).get('sha')
    if not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{40}', sha):
        raise ValueError('Invalid source commit')
    raw = bridge.decode_content(api(repository, 'contents/memory/revision.json?ref=' + sha))
    view = json.loads(raw)
    if (not isinstance(view, dict) or view.get('version') != 1
            or not isinstance(view.get('projects'), dict)
            or view.get('empty_project_revision') != sessions.EMPTY_REVISION
            or not isinstance(view.get('revision'), str) or not sessions.DIGEST.fullmatch(view['revision'])):
        raise ValueError('Invalid revision manifest')
    context['observed_revisions'] = view['projects']
    sessions.validate_context(context)
    changed = sessions.refresh_required(previous, view)
    previous_projects = previous.get('projects', {}) if isinstance(previous, dict) else {}
    names = sorted(set(view['projects']) | set(previous_projects))
    changed_projects = [name for name in names if view['projects'].get(name) != previous_projects.get(name)]
    return dict(read_ref=sha, context=context, snapshot=view, refresh_required=changed,
                changed_projects=changed_projects,
                instructions='Reload affected evidence at read_ref before using its revision. Never blindly replace tokens after a conflict. The manifest does not push updates into other conversations.')


def verify_receipt(item, digest, row, failure=False):
    checked = bridge.verify_receipt(item, digest, row, failure=failure)
    if not failure and item.get('context') is not None:
        if checked.get('session_context') != sessions.origin(item['context']):
            raise ValueError('Receipt belongs to a different actor or conversation')
    return checked


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repository', required=True)
    p.add_argument('--actor-id', required=True)
    p.add_argument('--app-id', required=True)
    p.add_argument('--session-id')
    p.add_argument('--previous', help='Optional earlier revision manifest JSON')
    args = p.parse_args()
    previous = json.loads(Path(args.previous).read_text()) if args.previous else None
    print(json.dumps(inspect(args.repository, args.actor_id, args.app_id, args.session_id, previous), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
