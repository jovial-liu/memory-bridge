# GitHub-native memory execution

The entire production workflow can run on GitHub. Durable memory and results live in a private repository. Model files and derived indexes live in that repository's Actions cache. GitHub-hosted runners execute the code; the user's laptop does not need a model or retrieval server.

## Setup

For a new deployment, use the [private template quick start](QUICKSTART.md). It includes the complete runtime and initialization workflow. The separate-archive installation below is optional.

Copy [memory-cloud.yml](../templates/memory-cloud.yml) to `.github/workflows/memory-cloud.yml` in the private memory repository. The template defaults to the upstream toolkit on main; a production deployment may pin the toolkit ref to a reviewed commit.

Create `AI_MEMORY.md` from the entry template. Grant your AI app access to the private repository and file creation permissions if it will submit requests. Workflow execution uses the repository's GITHUB_TOKEN to commit private results.

## One-prompt read/write

> Use my GitHub memory: read relevant context first, then save the new information I explicitly confirm, with sources and record links.

The connector creates `memory/requests/<32-character hex ID>.json`, waits for the private Actions job, and reads `memory/results/<same ID>.json`. The job is triggered by a request-file push or manually via workflow_dispatch. First-run model download/indexing may take time; this is asynchronous execution, not an always-on API.

A read-only connector can inspect stored memory/results but cannot submit a new request. A connector must actually support creating repository files for this workflow; documentation does not grant permissions.

## Operations

| operation | Payload / result |
| --- | --- |
| recall | query + scope; returns cited context |
| write | event or events[]; validates and saves one or up to 100 memory events atomically |
| sync | event or events[] + query; saves and retrieves in one request |
| forget | user-confirmed forget event; suppresses event recall |
| conflicts | returns unresolved structured claim disagreements |
| graph | explicit project, optional entity/hops; sourced relation graph |
| reflect | explicit project; candidate consolidation, optional save=true |
| checkpoint | project + checkpoint(task_id/state/source); records working state |
| resume | project + task_id; returns last checkpoint for that task |

All requests have id, optionally created_at, and an operation. recall/sync additionally require query. mode is keyword, semantic or hybrid; scope fields are project/platform/account/topic/memory_type. See [request example](../examples/request.json).

write/sync/forget carry either `event` or an `events` array with the protocol fields. A batch contains 1..100 events. The cloud validates the complete batch before writing, assigns stable event IDs derived from the request ID and position, and records time if omitted. A retry reuses the same IDs. checkpoint state contains objective and optional string lists done/pending/next_steps. Checkpoints are reported historical state, not proof that an action completed.

The cloud batches pending requests, applies authorized writes, then builds retrieval data. Scoped queries encode the union of their scopes and disclose vector_coverage=scoped. An unscoped semantic request encodes the full eligible corpus. Content-addressed embedding caches reuse earlier vectors. File-only graph/working/reflect operations do not require a language model.

### Confirmed write example (fictional)

Use a fresh request ID and replace the fictional text and source with the user's actual explicit statement. Do not import this example as personal information.

```json
{
  "id": "11111111111111111111111111111111",
  "operation": "write",
  "event": {
    "kind": "preference",
    "status": "confirmed",
    "text": "For the demo project, give concise answers with source links.",
    "scope": {"project": "demo", "platform": "example-app", "account": "fictional-user"},
    "source": {"reference": "fictional-message-1", "excerpt": "Please give concise answers with source links for this demo."},
    "evidence_role": "user",
    "supersedes": []
  }
}
```

For a combined request, change operation to `sync`, add `query`, and optionally `project` and `mode` at the request's top level. To save several confirmed memories from one conversation turn, replace `event` with `events: [ ... ]` instead of creating one request/commit per fact. Writes still require direct user evidence to be confirmed.

## Storage and limits

- Private repository: conversations, events, requests, results, working checkpoints, `memory/status.json`, and generated `memory/NOW.md`.
- Private Actions cache: model and SQLite/embedding derivatives; cache eviction is possible, so these are rebuildable.
- Public repository: toolkit, protocol, tests, and fictional examples only.

`memory/status.json` exposes request/result counts and workflow phase; `memory/NOW.md` is a compact generated current-state view. The workflow publishes a running status before heavy retrieval work and a completed/failed status afterward. Results and written events are committed together on successful runs, with fast-forward retries for concurrent branch updates. Logs show request IDs and counts, not retrieved memory excerpts. GitHub Actions uses execution minutes and has runtime/cache limits; it is a batch workflow, not unlimited compute or a permanent inference host.

The template runs only when the repository is private. Do not copy personal memory into the public toolkit. Logical forgetting does not erase Git history or old caches.

References: [workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), [cache behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching).

Source-labelled regression evaluation is available through `evaluate` with `cases_path: memory/evaluation/<name>.json`. Inspect the report pass count; workflow success alone does not mean all cases passed. See [evaluation guidance](docs/EVALUATION.md).
