# GitHub-native memory execution

Durable memory and receipts live in a separate private GitHub repository. GitHub-hosted runners process requests; model files and disposable indexes use that private repository's Actions cache. No laptop inference server is required. This is batch execution, not an always-on API or guaranteed real-time response.

## Setup

Use the [private template quick start](QUICKSTART.md), or install [the external-toolkit workflow](../templates/memory-cloud.yml) in the private archive. Pin a reviewed, tested toolkit commit. A moving `main` ref is not a production version pin. Grant the calling AI app the necessary repository access. Documentation does not grant read/write permissions.

The workflow uses the private repository's GITHUB_TOKEN to publish results. It must refuse execution in public repositories. Never copy personal history into the public toolkit.

## Read and write

> Read only relevant memory first; save new information I explicitly confirm with its source.

A connector creates `memory/requests/<32-character hexadecimal ID>.json`. GitHub Actions processes it, and the connector reads `memory/results/<same ID>.json`. A request file means submitted, NOT applied. A read-only connector can inspect existing sources but cannot submit cloud requests.

Requests contain `id`, optional timezone-aware `created_at`, and `operation`. A new task uses a new ID. Do not modify processed requests. After a timeout, read back the original path and check the receipt rather than blindly creating another write.

| Operation | Input and effect |
| --- | --- |
| recall | query and optional scope; returns cited context |
| write | event or events[]; validates and applies 1..100 events |
| sync | event/events[] plus query; writes then retrieves |
| forget | confirmed user forget event; logical suppression only |
| conflicts | unresolved structured claim disagreements |
| graph | explicit project, optional entity/hops; source-backed relations |
| reflect | explicit project; candidate evidence consolidation, optional save=true |
| checkpoint | project plus task_id/state/source in checkpoint payload |
| resume | project plus task_id; last reported task checkpoint |
| evaluate | cases_path under memory/evaluation; assertion report |

`recall` and `sync` require a query of 1..2000 characters. Modes are keyword, semantic, or hybrid. Scope filters are project/platform/account/topic/memory_type; limit is 1..50, context budget is 300..50000 characters (not tokens). Scope labels must match actual indexed metadata; nearest-neighbor results are not guaranteed relevant.

Events require kind, status, text, scope(project/platform/account), source(reference/excerpt), evidence_role, and supersedes. The worker assigns stable event IDs and recording time. Use the canonical kinds and roles in [PROTOCOL.md](PROTOCOL.md); legacy alias normalization is compatibility support, not a truth verifier. Only direct user evidence supports confirmed status.

```json
{
  "id": "11111111111111111111111111111111",
  "operation": "write",
  "event": {
    "kind": "preference",
    "status": "confirmed",
    "text": "For the fictional demo project, cite sources.",
    "scope": {"project": "demo", "platform": "example-app", "account": "fictional-user"},
    "source": {"reference": "fictional-message-1", "excerpt": "Please cite sources for this demo."},
    "evidence_role": "user",
    "supersedes": []
  }
}
```

This example is fictional. Replace it with real reviewed evidence; never ingest the example as personal data. For several memories, replace event with events[]. For sync, also add query and optional retrieval scope.

## Batch reliability

One request preflights every event and reference against an isolated event-tree copy before touching live files. Ordinary I/O exceptions roll back newly created event files. The published Git commit is atomic; local multi-file writes are NOT crash-atomic database transactions. Stable IDs support retries. Separate requests are isolated so a malformed request does not block valid siblings.

Exact deduplication includes source evidence and metadata. Corrections, forgetting, relationships, episodic events, and repeated project-state observations are not removed by that optimization. New provenance must not disappear just because the sentence matches.

Failures get explicit receipts. Malformed inputs are quarantined under memory/failures without echoing raw error content. A sync write can succeed before its retrieval fails: the failed receipt then retains write and write_applied=true. Review and correct failures using a fresh ID, not by modifying history.

## Status and current context

`memory/status.json` version 2 separates succeeded, failed_known, integrity_errors and pending. It checks receipt digests and counts assertion-failing evaluations as failures, including legacy results. Historical failures stay visible after a corrected rerun. The file is a snapshot, not worker-liveness telemetry.

`memory/NOW.md` is a generated view capped at 12 entries and 6,000 characters by default. It links source events, labels known conflicts, and omits expired/invalidated events. Omission is not deletion. `stability`, `valid_from`, `expires_at` and `importance` distinguish temporary state from enduring background. A freshly regenerated file does not freshly confirm its real-world claims.

The CLI exits nonzero when newly processed requests fail. Workflows must finalize and publish receipts even after that failure and must report quarantined input errors. Do not condition publication solely on success(). See [RELIABILITY.md](RELIABILITY.md).

## Retrieval and boundaries

Keyword retrieval and explicit graph/checkpoint operations do not require a language model. Semantic queries use the pinned embedding provider and content-addressed caches; scoped encoding reports limited coverage. Indexes are rebuildable and may be evicted. RAG and memory-management components do not themselves train the answer model.

Logical forgetting does not erase raw conversations, old caches or Git history. Access controls are not end-to-end encryption. See [privacy](PRIVACY.md), [lifecycle](LIFECYCLE.md), and [evaluation guidance](EVALUATION.md). A curated keyword regression score is not a LongMemEval/LoCoMo score or overall memory accuracy.
