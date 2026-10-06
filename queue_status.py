"""Read-only Actions diagnostics; never infer liveness from memory/status.json."""
import argparse
import datetime as dt
import json
import re


def instant(value):
    if not isinstance(value, str):
        raise ValueError('Timezone-aware timestamp required')
    stamp = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Timezone-aware timestamp required')
    return stamp


def diagnose(run, jobs, snapshot=None, now=None, jobs_complete=True):
    if not isinstance(run, dict) or type(run.get('id')) is not int or not isinstance(jobs, list):
        raise ValueError('Invalid workflow data')
    now = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(now, dt.datetime) or now.tzinfo is None:
        raise ValueError('Timezone-aware check time required')
    observed = []
    for job in jobs:
        if not isinstance(job, dict) or job.get('run_id') != run['id']:
            raise ValueError('Job does not belong to the requested run')
        steps = job.get('steps') or []
        if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
            raise ValueError('Invalid job steps')
        executed = any(step.get('status') == 'in_progress'
                       or (step.get('status') == 'completed' and step.get('conclusion') != 'skipped')
                       for step in steps)
        assigned = type(job.get('runner_id')) is int and job['runner_id'] > 0
        status = job.get('status')
        if status == 'completed':
            state = 'terminal_' + str(job.get('conclusion') or 'unknown')
        elif executed:
            state = 'executing'
        elif status == 'queued' and job.get('runner_id') == 0:
            state = 'waiting_for_runner'
        elif assigned:
            state = 'runner_assigned_no_steps_observed'
        else:
            state = 'waiting_or_unknown'
        observed.append({'job_id': job.get('id'), 'state': state,
                         'job_status': status, 'job_conclusion': job.get('conclusion'),
                         'runner_assigned': assigned, 'steps_observed': executed})
    status = run.get('status')
    if status == 'completed':
        phase = 'terminal_' + str(run.get('conclusion') or 'unknown')
    elif any(job['state'] == 'executing' for job in observed):
        phase = 'executing'
    elif any(job['state'] == 'waiting_for_runner' for job in observed):
        phase = 'waiting_for_runner'
    elif status in {'pending', 'waiting', 'requested', 'queued'}:
        phase = 'waiting_or_gated'
    else:
        phase = 'unknown_no_execution_evidence'
    result = {'version': 1, 'checked_at': now.isoformat(), 'run_id': run['id'],
              'phase': phase, 'workflow_status': status, 'workflow_conclusion': run.get('conclusion'),
              'jobs_complete': jobs_complete, 'jobs': observed,
              'cause': 'not_determined_from_queue_state',
              'receipt_semantics': 'Workflow success does not prove a specific memory write succeeded.'}
    if isinstance(snapshot, dict):
        try:
            stamp = instant(snapshot.get('generated_at'))
            age = (now - stamp).total_seconds()
            result['snapshot'] = {'generated_at': snapshot['generated_at'],
                                  'age_seconds': age if age >= 0 else None,
                                  'clock_anomaly': age < 0,
                                  'scope': 'request ledger only; not workflow liveness'}
        except (ValueError, TypeError):
            result['snapshot'] = {'timestamp_valid': False, 'scope': 'not workflow liveness'}
    return result


def fetch_status(repository, run_id, api=None, now=None, max_pages=5):
    if (not isinstance(repository, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository)
            or any(part in {'.', '..'} for part in repository.split('/'))):
        raise ValueError('Invalid repository')
    if type(run_id) is not int or run_id <= 0 or type(max_pages) is not int or not 1 <= max_pages <= 10:
        raise ValueError('Invalid run ID or page limit')
    if api is None:
        from bridge import api
    run = api(repository, 'actions/runs/' + str(run_id))
    if run.get('id') != run_id:
        raise ValueError('Run identity mismatch')
    jobs = []
    complete = False
    total = None
    for page in range(1, max_pages + 1):
        result = api(repository, 'actions/runs/' + str(run_id) + '/jobs?filter=latest&per_page=100&page=' + str(page))
        rows = result.get('jobs')
        count = result.get('total_count')
        if not isinstance(rows, list) or type(count) is not int or count < 0:
            raise ValueError('Invalid jobs response')
        total = count
        jobs.extend(rows)
        if len(jobs) >= count:
            complete = True
            break
        if not rows:
            break
    # API/permission errors deliberately propagate, rather than becoming "pending".
    report = diagnose(run, jobs, now=now, jobs_complete=complete)
    report['reported_job_count'] = total
    report['consistency'] = 'bounded multi-request observation, not an atomic server snapshot'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--run-id', required=True, type=int)
    args = parser.parse_args()
    try:
        report = fetch_status(args.repository, args.run_id)
    except Exception:
        parser.exit(2, 'Cannot verify workflow status; check API access and run ID.\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
