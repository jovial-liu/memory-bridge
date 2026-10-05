# Temporal and portable-client correctness audit

## Reproduced before repair

The test-only commit `fd45c368c4513d8aa68b08a051168a98add03c4d` runs the pre-repair production code with 16 new synthetic regressions. CI run [37346177278](https://github.com/jovial-liu/memory-bridge/actions/runs/37346177278) reproduced candidate corrections hiding confirmed evidence (including RAG), incorrect mixed-offset event/checkpoint ordering, premature replacement, unbound/mismatched receipts being accepted, missing failure-receipt handling and non-idempotent create retries. Failure counts include subtests; they are not a count of independent vulnerabilities.

## Correction authority and time

Only user-confirmed, effective supersedes links invalidate prior facts. Candidate links remain proposals and cannot silently remove confirmed evidence. Historical records do not grant current replacement authority. The effective boundary is valid_from when explicitly supplied, otherwise the recording time. An accepted replacement expiring still does not revive an old value. Logical-forgetting semantics remain unchanged.

Event search and checkpoint resume compare timezone-aware datetime values, not ISO strings. Original offsets are preserved in storage. This does NOT turn recording time into occurrence time, infer missing dates or implement full bitemporal/as-of querying. Existing occurrence/source timestamps must still be established from evidence. No historical personal timestamps are rewritten by this code change.

## Bound receipts and retries

The optional bridge.py client validates request privacy/schema before upload. It checks receipt ID, operation, request-byte SHA-256, execution, outcome, read filters and returned scope; successful write references must have consistent safe event IDs/paths. An unbound legacy receipt is rejected rather than reported as saved. Failed evaluations are normalized as failed, even if an older producer claimed success. Partial sync-write references remain visible separately from failed retrieval.

A create conflict or ambiguous transport failure triggers one read-back: identical request bytes are reusable; differing content is a collision. The client never supplies a replacement SHA or overwrites a submitted request. Only a missing receipt (HTTP 404 after repository access has succeeded) is treated as not ready. Permission, rate-limit, and transport errors are reported rather than swallowed as pending. Failure receipts are checked as well as result receipts. HTTP error bodies are not echoed.

```sh
python bridge.py --repository YOUR_ACCOUNT/PRIVATE_MEMORY check REQUEST_ID --wait 30
```

`check` verifies an existing request without issuing a new write. Waiting is bounded (0..300 seconds; each transport call also has its own 30-second timeout). It does not create an always-on background service.

The old happy-path client test fixture is updated to carry real protocol binding fields, while retaining its assertions. Negative receipt tests explicitly reject its previous unbound shape. No private retrieval evaluation cases are relaxed for this change.

## Boundaries and next measured work

These are deterministic correctness tests, not an external memory benchmark or every-vendor compatibility test. The optional CLI and direct GitHub connector are different adapters; the session protocol still applies to both. App permissions/forced confirmations remain authoritative. Deferred work includes automated source-backed summary consolidation, explicit occurrence-time indexing, real-model paraphrase/hybrid evaluation, and end-to-end testing in independently authorized third-party apps.

Official API references: [repository contents](https://docs.github.com/en/rest/repos/contents), [gh api headers](https://cli.github.com/manual/gh_api).
