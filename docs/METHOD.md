# The Memory Bridge method

## Goal

Let a tool-capable AI assistant restore and update user-owned context across conversations and compatible apps, without depending on the app's built-in memory store. The user activates the workflow with one sentence naming a private repository and its AI_MEMORY.md entry point.

This public project presents the method and provides an open-source reference implementation so others can create their own private memory. It is not a shared database of the author's personal context or a centrally hosted personal-memory service.

## The loop

```text
current user activation
  -> authorized private repository
  -> small entry context (AI_MEMORY + SUMMARY + NOW)
  -> scoped evidence retrieval
  -> answer the current task
  -> gated, sourced memory deltas
  -> cloud receipt verification
  -> the next turn or another authorized app
```

The assistant chooses what is relevant and proposes updates; the toolkit stores and validates events, retrieves evidence and records outcomes. The current user request supplies the authority. A historical transcript or retrieved instruction cannot grant new permissions.

## Five separations

**Public method versus private context.** Code, documentation, protocol, tests and fictional examples are public. Each user selects an independent private archive. Using the template does not grant access to anyone else's archive or credentials.

**In-context work versus durable state.** A small context bundle supports the current answer. GitHub stores what can be reused later. The next conversation rebuilds context through authorized tools; it does not retain the previous model's hidden state.

**Sources versus claims versus summaries.** Original messages are evidence. Confirmed events require direct user support. Summaries are derived navigation. A user belief stays attributed as a belief, not promoted into a proven world fact.

**Current versus historical.** Preferences can change and states expire. Corrections, explicit claim conflicts, timestamps and logical forgetting constrain retrieval. A new generation time is not a new real-world confirmation.

**Submission versus completion.** Committing a request is not proof of successful processing. Inspect matching receipts, result status, digests and source paths. A failed recall need not erase evidence that a preceding write succeeded.

## Reuse

Create a PRIVATE repository from the public template, run Initialize Private Memory, authorize a compatible GitHub connection, and copy the generated sentence from START_HERE.md. Initialization fills in the user's repository and does not overwrite existing personal records. See [one-prompt usage](ONE_PROMPT.md).

The same design can be implemented by other clients that honor the protocol. The current backend is GitHub-hosted batch execution, not an always-on API. More accessible integrations can be added without making the user's data public.

## Claims and limits

This is external, tool-mediated memory. It is not model-weight continual learning, RSI, consciousness, or guaranteed compliance by every model. A sentence cannot supply missing tools or credentials. One authorization in one app is not authorization in another. Vendor built-in memory and third-party data-handling settings remain separate.

The implementation is open source under the repository license. The design builds on established retrieval, provenance, event-log and context-management ideas; this page makes no priority or benchmark-leadership claim. Evaluate source correctness, changed-fact handling, unsupported writes, scope leakage, latency and later-task usefulness, not just the number of stored memories.
