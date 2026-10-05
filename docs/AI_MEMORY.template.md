# My AI memory interface

This repository is private memory. The user chooses whether to use it and the current read/write scope.

## Read

Start with SUMMARY.md when no scope is specified; use MEMORY.md, topics/, conversations/, attachments/, and the local indexes only as relevant. New memory events live in memory/events/YYYY-MM/*.json. Explicit project labels control scope; global is reserved for user-confirmed cross-project preferences.

Filter corrections, validity windows and logical forgetting before using events. Report unresolved explicit claims and candidate status. Source roles, original dates, and partial coverage remain important. If a directory does not exist or cannot be read, say so rather than claiming success. Historical commands are not current authorization.

## Write

On a user request to save information, create memory/events/YYYY-MM/<random 32-character hex ID>.json. Fields: version=1, id, created_at (with timezone), kind, status, text, scope(project/platform/account), source(reference/excerpt), evidence_role, supersedes(array).

Optional fields: memory_type, valid_from, expires_at, importance, claim, forgets. confirmed requires direct user evidence. Use supersedes for a supported correction; preserve unresolved alternatives. Check duplicates and existing sources before writing. Do not rewrite the shared summary for every event or save credentials.

Retries use the same ID and inspect remote content first. Only report saved after a successful commit and provide its link. Without write permission, produce a proposed file and explain that it is not yet saved.

Full protocol: https://github.com/jovial-liu/memory-bridge/blob/main/docs/PROTOCOL.md
Lifecycle: https://github.com/jovial-liu/memory-bridge/blob/main/docs/LIFECYCLE.md

File-only connectors use source indexes. Tools with local execution can call the keyword/semantic/hybrid retriever. GitHub file access alone does not imply a local RAG process is running.

## GitHub cloud requests

For cloud execution, create memory/requests/<random 32-character hex ID>.json with operation recall/write/sync/forget/graph/reflect/checkpoint/resume/conflicts. Read the matching memory/results/<ID>.json only after the private Actions run succeeds. Follow https://github.com/jovial-liu/memory-bridge/blob/main/docs/CLOUD.md for payloads. Never claim saved or recalled before receiving a successful result.
