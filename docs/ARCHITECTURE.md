# Evidence-first agent memory

There is no universal best agent-memory architecture. Choose retrieval and lifecycle controls for the task, and measure them against real questions. This project combines portable evidence, scoped retrieval, and explicit user control rather than claiming a benchmark-leading model.

| Layer | Implemented here | Why it matters |
| --- | --- | --- |
| Source archive | Per-platform conversations, account labels, source hashes and partial-coverage markers | Preserve what was actually said and keep accounts traceable |
| Navigation/core context | SUMMARY.md plus generated NOW.md current-state view and detailed MEMORY.md | Keep stable background separate from temporary/evolving state without making a summary the sole record |
| Long-term events | Semantic, episodic and procedural labels; candidate versus confirmed evidence; stability metadata and exact-write deduplication | Separate assistant hypotheses from user-supported facts and control memory growth |
| Working context | Project/task checkpoints and resume | Continue scoped work across sessions without asserting that reported steps actually executed |
| Retrieval | Multilingual vectors, BM25, RRF, scopes and context budgets | Restore relevant evidence instead of loading the whole archive |
| Time and change | Validity windows, corrections, explicit claim conflicts | Avoid treating an expired or contradicted fact as current |
| Relationships | Explicit source-backed claims and links | Navigate known connections without silently inventing an entity graph |
| Consolidation | Candidate-only evidence drafts | Support review without promoting inference into fact |
| Control | Explicit read/write/sync/forget requests, per-task scope, batched events[] writes, machine-readable workflow status | Let the user decide when and where memory applies while keeping writeback efficient and observable |

A private deployment can materialize two lightweight derived views from the event log: `memory/NOW.md` for current/evolving state and `memory/status.json` for request-processing health. They are disposable views, not canonical facts. Exact duplicate active events can be reused instead of appended again, while conflicting structured claims remain explicit rather than silently overwritten.

Production storage and batch execution are on GitHub. The public template ships every listed capability; each deployment's actual personal records belong only in its private repository. Derived vectors are rebuildable cache, not the sole source of truth. Public code and private data remain separate repositories even when the private template also contains its own code snapshot.

## Research and implemented boundaries

[Letta's stateful agent design](https://docs.letta.com/v1-sdk/concepts/stateful-agents) describes persistent state and editable in-context memory blocks. This project's navigation files and checkpoints are a lighter Git-based counterpart; it does not implement Letta's agent runtime or automatic context scheduling.

[Graphiti](https://github.com/getzep/graphiti) develops temporal knowledge graphs for agent context. Here temporal event validity and sourced explicit relationships are implemented, but automatic entity extraction, entity resolution and a full temporal graph database are not.

[A-MEM](https://arxiv.org/abs/2502.12110) explores dynamically linked notes and memory evolution. Here links and candidate consolidation are supported; autonomous LLM note creation and link evolution are not implemented.

The unit suite checks lifecycle behavior, source integrity, scope isolation, deterministic retrieval mechanics, request processing and safe initialization. It is not a long-term-memory relevance benchmark. Learned reranking, automatic extraction, autonomous promotion, model-based reflection, and published LongMemEval/LoCoMo results remain future work. Add these only with evaluation and explicit trust boundaries; more named modules alone do not establish better memory.

A suitable future evaluation set covers paraphrased recall, Chinese/English queries, conflicting accounts, changed preferences, expired facts, forgotten facts, task resume, and insufficient evidence. Measure retrieval coverage, wrong-scope leakage, citation correctness, stale-fact use, latency, and the rate of unsupported writebacks.
