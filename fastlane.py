"""Publish lightweight memory writes before expensive retrieval in the same worker.

This is not a second writer or a runner-free API. The existing canonical validators,
immutable request IDs, receipts, and non-forcing Git publication remain authoritative.
"""
import argparse
import json
from pathlib import Path
import sessions

FAST_OPERATIONS = frozenset({'write', 'forget', 'checkpoint'})


def drain(root, publish=False):
    import cloud
    import memory_bridge
    import manager

    root = Path(root).resolve()
    memory_bridge.load(root)
    before = set((root / 'memory/failures').glob('*.json'))
    jobs = cloud.pending(root, quarantine=True)
    selected = [(item, digest) for item, digest in jobs
                if item.get('operation', 'recall') in FAST_OPERATIONS]
    failed = 0
    for item, digest in selected:
        op = item['operation']
        row = cloud.receipt(item, digest)
        try:
            if op == 'checkpoint':
                payload = sessions.checkpoint_payload(root, item)
                row['result'] = manager.checkpoint(root, item['id'], payload)
            else:
                row['result'] = cloud.write_events(root, item, 'forget' if op == 'forget' else None)
        except Exception as exc:
            code = exc.code if isinstance(exc, sessions.SessionConflict) else 'write_or_checkpoint_failed'
            cloud.fail(row, code)
            failed += 1
        cloud.finish(root, row)
    quarantined = len(set((root / 'memory/failures').glob('*.json')) - before)
    result = {'processed': len(selected), 'failed': failed, 'quarantined': quarantined,
              'deferred': len(jobs) - len(selected), 'publication': 'not_requested'}
    if selected or quarantined:
        cloud.status_snapshot(root, 'running' if result['deferred'] else 'completed')
        if publish:
            cloud.publish(root)
            result['publication'] = 'git_publish_completed'
    elif publish:
        result['publication'] = 'no_changes'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    try:
        result = drain(args.root, args.publish)
    except Exception:
        parser.exit(2, 'Fast stage failed; inspect canonical integrity and publication access.\n')
    print(json.dumps(result, sort_keys=True))
    if result['failed'] or result['quarantined']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
