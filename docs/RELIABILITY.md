# Reliability contract

This document qualifies older shorthand in README/CLOUD documentation.

## Evidence-preserving deduplication

Only identical active semantic facts, preferences or decisions, including identical source evidence and metadata, may be reused. Corrections, forgetting, related links, episodic events and repeated project-state observations are never removed by content deduplication. Assigned IDs and recording timestamps are excluded from the equality comparison; new provenance is not. Validation and same-request collision detection happen before reuse.

## Request isolation and publication

Each write request is preflighted against an isolated copy of the canonical event tree. This checks every event plus reference integrity before changing live files. Ordinary I/O failures roll back newly created event files. Publishing the resulting Git commit is atomic. This is NOT a crash-atomic multi-file database transaction. Request-derived event IDs permit replay after interruption.

Malformed requests are recorded in memory/failures with opaque failure codes, not raw exception text. They do not block other requests. A failed processed request is terminal; review it and submit a corrected fresh ID. Do not edit already processed requests. A sync request can apply a write and then fail retrieval; its failed receipt explicitly retains write and write_applied=true.

## Honest status

status.json version 2 validates receipt digests and reports succeeded, failed_known, integrity_errors, and pending separately. An evaluation that runs but fails assertions is failed, including old evaluation receipts without an explicit status. Historical failures remain visible after a corrected rerun. A status file is a snapshot, not proof of a live worker. NOW is capped at 12 entries and 6,000 characters by default, links source events, marks known conflicts, and excludes invalidated/expired events. It never confirms that a real-world task has completed.

The CLI run command exits nonzero for newly failed results after recording outcomes. A production workflow must publish outcomes with an always()/not-cancelled finalization step even when run fails, and fail explicitly when pending.outputs.rejected is true. Otherwise valid sibling results can remain only on the runner. Pin a tested toolkit commit; never use a moving main ref in a private production workflow.

## Validation boundaries

The synthetic reliability tests exercise adverse cases. They do not establish semantic retrieval quality, production uptime, complete privacy protection, or an external benchmark score. Hand-curated keyword regressions are separate from paraphrase/temporal LongMemEval-style evaluations. Existing raw sources are not automatically rewritten by these repairs.
