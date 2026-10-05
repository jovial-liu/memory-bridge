"""Portable GitHub client with bound receipts and non-overwriting retries.

Models and retrieval execute on GitHub Actions, not in this client.
"""
import argparse
import base64
import binascii
import datetime as dt
import hashlib
import json
import math
import re
import subprocess
import time
import uuid

import cloud
import memory_bridge


class GitHubAPIError(RuntimeError):
    """Sanitized transport error; never expose response bodies or credentials."""
    def __init__(self, status_code=None):
        self.status_code = status_code
        label = str(status_code) if status_code is not None else 'transport/timeout'
        super().__init__('GitHub operation failed (' + label + '); check connection and repository access')


def api(repository, path, body=None):
    args = ['gh', 'api', '--hostname', 'github.com', '--include',
            'repos/' + repository + ('/' + path if path else '')]
    if body is not None:
        args += ['--method', 'PUT', '--input', '-']
    try:
        result = subprocess.run(args, input=json.dumps(body).encode() if body is not None else None,
                                capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        raise GitHubAPIError() from None
    text = result.stdout.decode('utf-8', errors='replace').replace('\r\n', '\n')
    status = None
    # gh --include supplies response headers; consume interim HTTP blocks too.
    while text.startswith('HTTP/'):
        header, separator, text = text.partition('\n\n')
        match = re.match(r'HTTP/\S+\s+(\d{3})(?:\s|$)', header)
        if not separator or not match:
            raise GitHubAPIError() from None
        status = int(match.group(1))
    if result.returncode or status is None or not 200 <= status < 300:
        raise GitHubAPIError(status)
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        raise GitHubAPIError(status) from None


def request_bytes(item):
    return (json.dumps(item, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def decode_content(response):
    if (not isinstance(response, dict) or response.get('encoding', 'base64') != 'base64'
            or not isinstance(response.get('content'), str)):
        raise ValueError('Expected a Base64 repository file')
    try:
        return base64.b64decode(''.join(response['content'].split()), validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('Malformed repository file encoding') from None


def validate_options(repository, wait_seconds, poll_seconds):
    if (not isinstance(repository, str)
            or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository)
            or any(part in {'.', '..'} for part in repository.split('/'))):
        raise ValueError('Invalid repository')
    for value, lower, upper, label in [(wait_seconds, 0, 300, 'wait_seconds'),
                                       (poll_seconds, 0.25, 30, 'poll_seconds')]:
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not lower <= value <= upper):
            raise ValueError('Invalid ' + label)


def validate_item(item):
    if not isinstance(item, dict) or not isinstance(item.get('id'), str):
        raise ValueError('Request requires an ID')
    cloud.validate_request(item, item['id'])  # Includes privacy checks BEFORE upload.
    if item.get('operation') in cloud.WRITE_OPS:
        payloads = cloud.request_events(item)
        stamp = item.get('created_at', dt.datetime.now(dt.timezone.utc).isoformat())
        for index, raw in enumerate(payloads):
            suffix = ':event' if len(payloads) == 1 else ':event:' + str(index)
            candidate = dict(raw, version=1, id=hashlib.sha256((item['id'] + suffix).encode()).hexdigest()[:32],
                             created_at=stamp)
            candidate.setdefault('supersedes', [])
            if item['operation'] == 'forget':
                candidate['kind'] = 'forget'
            memory_bridge.validate(candidate)
    request_bytes(item)  # Reject non-JSON/nonfinite input before any network operation.


def require_private(repository):
    metadata = api(repository, '')
    if not isinstance(metadata, dict) or metadata.get('private') is not True:
        raise ValueError('Personal memory requires a private repository')


def verify_event_paths(written):
    if not isinstance(written, dict):
        raise ValueError('Successful write requires event references')
    rows = written.get('events', [written])
    if (not isinstance(rows, list) or not rows
            or ('events' in written and (type(written.get('count')) is not int or written['count'] != len(rows)))):
        raise ValueError('Invalid written-event count')
    for event in rows:
        if not isinstance(event, dict):
            raise ValueError('Invalid written event')
        ident, path = event.get('event_id'), event.get('path')
        if (not isinstance(ident, str) or not re.fullmatch(r'[a-f0-9]{32}', ident)
                or not isinstance(path, str)
                or not re.fullmatch(r'memory/events/[0-9]{4}-[0-9]{2}/' + re.escape(ident) + r'\.json', path)):
            raise ValueError('Written event identity/path mismatch')


def verify_receipt(item, digest, row, failure=False):
    if (not isinstance(row, dict) or row.get('id') != item['id']
            or row.get('request_sha256') != digest):
        raise ValueError('Receipt identity or request checksum mismatch')
    if failure:
        # Quarantine receipts intentionally omit operation/execution and raw input.
        if row.get('status') != 'failed' or not isinstance(row.get('error_code'), str):
            raise ValueError('Invalid quarantine receipt')
        return row
    if row.get('operation') != item.get('operation', 'recall') or row.get('execution') != 'github-actions':
        raise ValueError('Receipt operation or execution mismatch')
    state = cloud.outcome(row)
    if state == 'invalid':
        raise ValueError('Invalid result outcome')
    if row['operation'] in {'write', 'forget'} and state == 'succeeded':
        verify_event_paths(row.get('result'))
    if row['operation'] == 'sync' and (state == 'succeeded' or row.get('write') is not None):
        verify_event_paths(row.get('write'))
    if state == 'succeeded' and row['operation'] in {'recall', 'sync'}:
        if not isinstance(row.get('results'), list):
            raise ValueError('Successful recall requires results')
        filters = row.get('filters', {})
        if not isinstance(filters, dict):
            raise ValueError('Invalid result filters')
        for key in cloud.SCOPES:
            expected = item.get(key)
            if expected is not None and filters.get(key) != expected:
                raise ValueError('Receipt retrieval scope mismatch')
        for hit in row['results']:
            if not isinstance(hit, dict):
                raise ValueError('Invalid retrieval result')
            for key in ('project', 'platform', 'account'):
                if item.get(key) is not None and hit.get(key) != item[key]:
                    raise ValueError('Retrieved evidence crossed requested scope')
            if item.get('topic') is not None and item['topic'] not in hit.get('topics', []):
                raise ValueError('Retrieved evidence crossed requested topic')
            if item.get('memory_type') is not None:
                default = 'episodic' if hit.get('kind') == 'conversation' else 'semantic'
                if hit.get('memory_type', default) != item['memory_type']:
                    raise ValueError('Retrieved evidence crossed requested memory type')
    # Preserve partial sync-write metadata even when retrieval/evaluation failed.
    return {**row, 'status': state}


def read_receipt(repository, item, digest):
    for folder in ('results', 'failures'):
        try:
            response = api(repository, 'contents/memory/' + folder + '/' + item['id'] + '.json')
        except GitHubAPIError as exc:
            if exc.status_code == 404:
                continue
            raise
        try:
            row = json.loads(decode_content(response))
        except (ValueError, UnicodeError):
            raise ValueError('Invalid receipt JSON') from None
        return verify_receipt(item, digest, row, failure=folder == 'failures')
    return None


def wait_for_receipt(repository, item, digest, wait_seconds, poll_seconds, check_once=False):
    pending = dict(id=item['id'], status='submitted', result_path='memory/results/' + item['id'] + '.json',
                   failure_path='memory/failures/' + item['id'] + '.json', execution='github-actions')
    deadline = time.monotonic() + wait_seconds
    first = True
    while (first and check_once) or (wait_seconds > 0 and time.monotonic() < deadline):
        first = False
        found = read_receipt(repository, item, digest)
        if found is not None:
            return found
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_seconds, remaining))
    return pending


def submit(repository, item, wait_seconds=0, poll_seconds=5):
    validate_options(repository, wait_seconds, poll_seconds)
    validate_item(item)
    require_private(repository)
    raw = request_bytes(item)
    path = 'contents/memory/requests/' + item['id'] + '.json'
    try:
        api(repository, path, {'message': 'Submit private memory ' + item.get('operation', 'recall') + ' request',
                               'content': base64.b64encode(raw).decode()})
    except GitHubAPIError as exc:
        # A timeout/conflict can mean the first create succeeded. Compare, never overwrite.
        if exc.status_code not in {None, 409, 422, 500, 502, 503, 504}:
            raise
        try:
            saved = decode_content(api(repository, path))
        except GitHubAPIError:
            raise exc from None
        if saved != raw:
            raise ValueError('Request ID already exists with different content; use a new ID')
    digest = hashlib.sha256(raw).hexdigest()
    return wait_for_receipt(repository, item, digest, wait_seconds, poll_seconds)


def check(repository, request_id, wait_seconds=0, poll_seconds=5):
    """Resume verification without creating a second request or changing its timestamp."""
    validate_options(repository, wait_seconds, poll_seconds)
    if not isinstance(request_id, str) or not re.fullmatch(r'[a-f0-9]{32}', request_id):
        raise ValueError('Invalid request ID')
    require_private(repository)
    raw = decode_content(api(repository, 'contents/memory/requests/' + request_id + '.json'))
    try:
        item = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError('Stored request is not valid JSON') from None
    validate_item(item)
    if item['id'] != request_id:
        raise ValueError('Stored request ID/path mismatch')
    return wait_for_receipt(repository, item, hashlib.sha256(raw).hexdigest(), wait_seconds, poll_seconds, check_once=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repository', required=True)
    sub = p.add_subparsers(dest='command', required=True)
    recall = sub.add_parser('recall')
    recall.add_argument('query')
    recall.add_argument('--mode', choices=['keyword', 'semantic', 'hybrid'], default='hybrid')
    remember = sub.add_parser('remember')
    remember.add_argument('text')
    remember.add_argument('--source-reference', required=True)
    remember.add_argument('--source-excerpt', required=True)
    remember.add_argument('--confirm', action='store_true', help='Only with explicit direct-user confirmation')
    for command in (recall, remember):
        command.add_argument('--project', required=True)
        command.add_argument('--platform')
        command.add_argument('--account')
        command.add_argument('--wait', type=float, default=0)
    resume = sub.add_parser('check', help='Check a submitted request; does not write')
    resume.add_argument('request_id')
    resume.add_argument('--wait', type=float, default=0)
    args = p.parse_args()
    try:
        if args.command == 'check':
            result = check(args.repository, args.request_id, args.wait)
        else:
            item = dict(id=uuid.uuid4().hex, created_at=dt.datetime.now(dt.timezone.utc).isoformat(), project=args.project)
            if args.command == 'recall':
                item.update(operation='recall', query=args.query, mode=args.mode)
                if args.platform: item['platform'] = args.platform
                if args.account: item['account'] = args.account
            else:
                item.update(operation='write', event=dict(version=1, kind='fact',
                    status='confirmed' if args.confirm else 'candidate', text=args.text,
                    scope=dict(project=args.project, platform=args.platform or 'user-statement', account=args.account or 'unknown'),
                    source=dict(reference=args.source_reference, excerpt=args.source_excerpt), evidence_role='user', supersedes=[]))
            result = submit(args.repository, item, args.wait)
        print(json.dumps(result, ensure_ascii=False))
        if result.get('status') == 'failed':
            p.exit(2)
    except (ValueError, RuntimeError) as exc:
        p.exit(1, 'Error: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
