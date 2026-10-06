# Multiple conversations, one private memory

A session is a conversation, not an app. Two chats in one app use different session IDs. The same person across apps keeps one actor ID. Do not create one memory repository per conversation.

## Cooperative-client protocol

1. Read the canonical AI_MEMORY entry and the owner's identity policy. Generate a random 32-hex `session_id` once per conversation. Reuse it within that conversation only. `actor_id` identifies a person; `app_id` is source provenance, not identity or authority.
2. Read `memory/revision.json` before a substantive memory-dependent turn. It is a small generated manifest with no event text. Compare project revisions and `next_transition_at`. If changed or expired, reload affected source events, not only an old profile. Read related files at one Git commit when the connector supports refs. Do not pretend background pushes updated a live chat.
3. Submit immutable requests with `context`. Keep independent simple facts append-only. State updates, decisions, structured claims, corrections and forgetting require `observed_revisions` for every affected project. Use `empty_project_revision` for a new project.
4. A `stale_project_revision` receipt means the worker did not apply this request. Read the new evidence, reconcile it with the user's latest statement, then submit a new request ID. Never merely replace the revision token and resend an obsolete conclusion. Never relabel a state change as a plain fact to evade the guard.
5. Verify ID, operation, digest, outcome, event references AND `session_context` in the receipt. A local computed write, an uploaded request and a published memory are different states.

```json
{
  "context": {
    "actor_id": "person-a",
    "session_id": "11111111111111111111111111111111",
    "app_id": "example-app",
    "observed_revisions": {"demo": "COPY_ACTUAL_PROJECT_REVISION_FROM_REVIEWED_MANIFEST"}
  }
}
```

The illustrative token above is not a valid request. Replace it with the real 64-hex project token; do not copy fictional identity or facts into a personal store.

## Server enforcement

`cloud.write_events` and the early-write stage share the same preflight guard. A repository may enable strict envelopes with `memory/session-policy.json`:

```json
{"version":1,"require_context":true,"actors":["person-a","person-b","unknown"],"legacy_actor_bindings":{}}
```

No policy means backward-compatible legacy requests remain accepted. With strict mode, old clients missing context get `session_context_required`, not fabricated success. Unknown actors may append candidate background but cannot confirm personal facts or change state. Superseding/forgetting another actor's event is rejected. Unattributed legacy events are not assigned to the current user; owner-reviewed `legacy_actor_bindings` require an actor and a source reference.

Project revisions cover canonical event contents, explicit actor bindings and effective lifecycle state. Unrelated project changes do not invalidate a write. Within one project the guard is deliberately conservative: unrelated additions may force a state-edit refresh. Events are not inferred equivalent from prose. Conflicting updates are not resolved by last-write-wins.

## Working memory and handoff

Checkpoint lookup is keyed by project, task, actor and session. Two conversations may use the same task name without taking each other's working state. Legacy unscoped resume only returns legacy checkpoints. Explicit handoff uses `resume_session_id` with the same actor in context; subsequent writes retain the new conversation's own session ID. A checkpoint is a sourced historical note, not proof an action is still executing.

## Publication and refresh helpers

The single-writer workflow remains mandatory. On push contention, new request files can be rebased. If upstream canonical events, checkpoints or session policy changed, publication fails closed and requires a fresh checkout rather than publishing a decision validated against an old corpus. No force pushes are introduced.

`python sessions.py --root PRIVATE_CHECKOUT` regenerates the manifest. `operation: revision` also returns a fresh snapshot via the worker. Expiry does not run a daemon; clients must recheck time boundaries. `session_client.py --repository OWNER/PRIVATE_MEMORY --actor-id person-a --app-id example-app` makes read-only API calls and pins the manifest read to one commit. Reuse its session ID on subsequent calls; affected evidence must still be read before adopting its revision tokens. The helper does not claim an LLM has read or understood evidence.

## Explicit limitations

Actor/session labels are cooperative metadata, not cryptographic identity or GitHub path-level permissions. A writer with direct repository access can bypass the worker. Historical conversation text may lack speaker identity, and RAG over the shared archive is not an actor ACL. Its contextual receipts disclose this. An arbitrary old app can still answer from stale context unless it follows the refresh protocol; guarded writes, not model thoughts, are enforceable here. SUMMARY/profile pages are not magically refreshed per fact. The manifest covers canonical events, not every transcript or attachment. All public fixtures are fictional. No model training, perpetual background polling, new server or credential sharing is required.
