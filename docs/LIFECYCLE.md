# Memory validity, conflicts, and forgetting

Optional fields are backward compatible with protocol v1.

## Validity

valid_from and expires_at are timezone-aware ISO 8601 timestamps. Validity is start-inclusive and end-exclusive. An event with a future start or expired end is excluded from ordinary recall. Created time records when the event was saved; it is not automatically the date the fact became true.

A future-dated correction does not replace the current event before valid_from. Once a correction is effective, expiration of the replacement does not resurrect the old value. Query-time filtering handles time changes without requiring a new source-file edit.

memory_type is semantic, episodic, or procedural. Unlabeled conversations are episodic; curated memories default to semantic. importance accepts 0..1 and is recorded metadata only. stability is stable, evolving, or temporary. Use temporary/evolving for current priorities and changing plans; use stable for durable identity, preferences, and long-term goals.

## Explicit disagreements

```json
{"claim": {"subject": "user", "predicate": "preferred_database", "value": "SQLite"}}
```

Active events in the same project with the same subject/predicate and different values form an unresolved group. `memory_bridge.py conflicts` reports IDs; retrieval marks the group. Cross-project statements are not merged. No semantic-prose contradiction detector or last-write-wins resolver is used.

## Logical forgetting

Create a user-confirmed event with kind=forget, forgets=[target event IDs], and supersedes=[]. Targets must exist in the same project. A forget marker is immediate and persistent, with no validity window. Ordinary event search and RAG omit its targets and any correction descendants, preventing accidental resurrection. The marker itself is not ordinary background context.

This is event suppression, not secure deletion. `search --history` can still inspect the audit trail. Source conversations, Git commits, and old embedding caches can retain the content. A complete erasure request requires separately locating/redacting source material, purging indexes/caches and handling Git history; this toolkit does not claim to do that automatically.

## Materialized current state

The cloud runtime can generate `memory/NOW.md` from active confirmed events that are project states, decisions, expiring memories, or marked `stability=evolving/temporary`. `NOW.md` is a derived view, not a source of truth; edit the underlying events instead.

## Candidate consolidation

When the user asks for a summary, the calling assistant may review related evidence and write a new sourced event. Assistant-generated conclusions remain candidate unless directly confirmed by the user. Source archives stay unchanged. There is no autonomous reflection job that silently turns guesses into facts.
