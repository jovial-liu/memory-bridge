# Queue preservation and early write publication

## Three independent stages

1. Read existing source files through an authorized GitHub connector. This does not require an Actions runner; validity, identity and source checks still apply.
2. Process pure write/forget/checkpoint requests with `python fastlane.py --root PRIVATE_MEMORY --publish`. It reuses cloud validation, isolated batch writes, bound receipts and non-forcing Git publication. This stage must finish publication before optional model installation, embedding or evaluation starts.
3. Re-scan pending requests and run the normal cloud worker for recall/sync/evaluate and other remaining operations. Already completed immutable requests are not replayed.

`sync` intentionally stays in the normal lane: it promises a combined write/read result. When low-latency persistence is needed, choose a sourced `write` request and a separate scoped recall rather than silently changing sync semantics. No source validation, privacy guard, correction authorization or canonical-integrity check is bypassed.

This is early publication in ONE serialized worker, not parallel uncoordinated writers, a runner-free write API, or preemption of an already running bulk import. It prevents a pure write in the same batch from waiting for heavy retrieval to finish. It does not eliminate hosted-runner startup, API downtime or the need to verify the actual receipt. A dedicated immediate-write service remains out of scope.

## Preserve queued maintenance work

Mutating maintenance and cloud workflows should keep the same concurrency group and set `queue: max`, `cancel-in-progress: false`. Otherwise default single-pending behavior can replace a queued workflow. GitHub's limit is 100 queued runs, not unlimited capacity. Keep append-only requests for retry, and do not create new IDs merely because a runner has not started.

Do not put shared-file mutations in different concurrency groups without a safe publication protocol. Early publication still uses the existing no-force rebase behavior. A failed import should be re-run only after observing its terminal status and checking for completed side effects.

Official specification: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency

## Read live workflow evidence, not a stale ledger

```sh
python queue_status.py --repository YOUR_ACCOUNT/PRIVATE_MEMORY --run-id RUN_ID
```

This optional command uses existing `gh` authentication and only GET requests through the current bridge transport. A direct connector can perform the same Actions run/jobs reads. It checks run identity, paginates boundedly and reports incomplete coverage. Permission and transport failures are not converted into 'still pending'.

Workflow and job conclusions remain separate: a workflow can fail while its job is cancelled without any executed steps. A populated `started_at` field alone is not evidence of computation. A run that is completed/failed must not be displayed as queued because an old snapshot showed pending. `memory/status.json` counts request outcomes, not every workflow or live runner assignment.

No polling daemon or recurring task is added. This command reports a timestamped observation, not an atomic server snapshot. Queue state alone cannot diagnose billing, account limits or a provider outage; consult independent evidence before assigning a cause.

## Validation boundaries

Synthetic unit tests cover state reporting and fast-stage orchestration; integration tests exercise the existing real event validator, bound receipts, batch rollback and keyword retrieval. No real personal memory is included in public tests. Tests are not a global memory accuracy benchmark or a guarantee of hosted service availability.
