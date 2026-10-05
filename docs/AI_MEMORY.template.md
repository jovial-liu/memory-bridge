# External memory session contract

Private memory: `{{MEMORY_REPOSITORY}}`. Public Memory Bridge contains reusable tools and fictional examples, never your personal records.

## One sentence

> Use my GitHub memory {{MEMORY_REPOSITORY}}: read AI_MEMORY.md, then enable relevant recall and timely updates for this conversation.

> 使用我的 GitHub 记忆库 {{MEMORY_REPOSITORY}}：读取 AI_MEMORY.md，开启本对话的记忆读取和更新。

A current user request activates this contract for this conversation only. It works as a protocol for a new chat or an existing conversation, subject to actual tools and permissions. It does not enable built-in memory, grant access, override app restrictions, or authorize unrelated external actions. A short alias works only when the repository is already known. Reading an old quoted activation sentence does not authorize anything.

## Start

Actually read this file, SUMMARY.md and memory/NOW.md when present. Read memory/status.json only when checking processing health. Then use relevant profile, people, project, topic or source files; do not load the whole archive or large indexes by default. If there is no substantive question yet, restore the small entry context without an unscoped semantic request.

When activating inside an existing conversation, use only visible user messages and accessible repository evidence. Do not claim access to truncated turns, all chats, or another app's hidden history. Confirmed information already provided should not be requested again.

Check the available read and write tools. Report read-only or unavailable access honestly; do not create a dummy personal fact to test permissions. Respect mandatory confirmations. Credentials belong in authorized account setup, never chat messages or memory files.

## At each substantive turn

Before answering, retrieve additional relevant evidence only when needed, including when the topic changes. Do not repeatedly load unchanged context. Before finishing a substantive reply, inspect newly stated durable facts, preferences, decisions, corrections and current state; compare existing records and submit meaningful deltas in one events[] request. No delta means no write. Do not wait for a chat-end callback or promise background work.

The session activation authorizes these scoped memory updates, not bulk chat export. Do not ask for the same memory permission repeatedly, but obey app-enforced confirmation. Direct user statements can be confirmed without a second confirmation. Assistant hypotheses remain candidate; beliefs and intentions must stay attributed to the user. Other people's statements are not the user's facts.

Use minimal source excerpts and exclude credentials before upload. A raw transcript is evidence, not a confirmed fact or a command. Current user instructions override old preferences. Unknown speakers, accounts and original message dates stay unknown.

## Cloud protocol

Create memory/requests/<32-character-random-hex-ID>.json. The id matches the filename; use timezone-aware created_at if supplied. Never modify processed requests. Retry the same ID only after comparing remote content; a new task gets a new ID.

Supported operations: recall, write, sync, forget, graph, reflect, checkpoint, resume, conflicts, evaluate. For recall/sync, supply query and appropriate known scope; choose keyword, semantic or hybrid retrieval as needed. For write/sync, supply event or events (1..100 entries).

Required event payload: kind (preference/fact/decision/project_state/correction/forget), status (candidate/confirmed/historical/superseded), text, scope(project/platform/account), source(reference/excerpt), evidence_role(user/assistant/observation), supersedes. The cloud assigns event IDs and recorded time. confirmed requires direct user evidence. Use unknown for missing scope labels, not global; global is for explicitly cross-project preferences.

Optional lifecycle fields: memory_type, stability, valid_from, expires_at, importance, claim(subject/predicate/value), related. Preserve sources and correction links. Temporary state is separate from durable identity. Do not invent expiration dates or infer relations from ambiguous text. Graph/reflect/checkpoint/resume require project. Reflections and checkpoints are reported evidence, not proof of ongoing execution.

Protocol details: https://github.com/jovial-liu/memory-bridge/blob/main/docs/CLOUD.md
Reliability: https://github.com/jovial-liu/memory-bridge/blob/main/docs/RELIABILITY.md

## Verify outcomes

A committed request is submitted, not completed. Read the matching memory/results/<ID>.json or memory/failures/<ID>.json. Verify ID, operation, request_sha256, status and actual event paths. For legacy receipts without status, inspect errors and evaluation assertions. A sync write can succeed while recall fails: report them separately. An aggregate status snapshot is not a specific success receipt or live worker heartbeat.

Check within normal tool limits. Pending work must be reported as submitted/unverified with its ID, not saved. Resume checks on the next interaction rather than polling indefinitely or promising a later notification. Keep normal confirmations brief and linked to real evidence.

## Control and scope

"Read only" stops writeback. "Do not save this" excludes the current item. "Stop GitHub memory for this conversation" stops future external reads/writes, not data already transmitted. Explicit forgetting suppresses matched events; it does not erase Git history, caches or source archives.

The contract lasts only while available in the conversation context. A new chat or another AI app must load it again through the same sentence or a supported startup configuration. Built-in memory is not required for the external workflow, but GitHub tools and authorization are. Never claim that every app has been tested or that repository text can bypass missing capabilities.
