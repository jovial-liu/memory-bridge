# Memory Bridge

**Your memory. Across AI apps. On your terms.**

[![Tests](https://github.com/jovial-liu/memory-bridge/actions/workflows/tests.yml/badge.svg)](https://github.com/jovial-liu/memory-bridge/actions/workflows/tests.yml)
[English](README.md) · [简体中文](README.zh-CN.md) · [MIT](LICENSE)

Memory Bridge is a GitHub-native memory protocol and cloud retrieval toolkit for AI assistants. Keep your actual conversations and memories in a **separate private repository**. This public project contains tools, documentation, and fictional examples.

Once an assistant knows your private repository and has the necessary GitHub access, ask:

> Read my memory. Restore only the context relevant to this project.

> Save the decision we just made, with its source and date.

> Don't use historical memory for this conversation.

No shared cloud memory account is required. A GitHub integration still needs to support the requested operation: a read-only connector cannot write, and a connector must be able to submit request files to use cloud retrieval.

## Create your private memory — no laptop setup

[**Create a private memory repository**](https://github.com/jovial-liu/memory-bridge/generate) → choose **Private** → open **Actions → Initialize Private Memory → Run workflow**. Connect your AI app to your new repository and ask it to read `AI_MEMORY.md`.

The template includes the complete runtime, cloud workflows, blank memory structure, protocol, and tests. No developer token or external database is required for Actions itself. Your AI connector needs separately authorized repository access. Existing personal data is never overwritten by initialization. Public copies cannot run memory processing.

[Step-by-step setup and first request](docs/QUICKSTART.md) · [Agent memory architecture](docs/ARCHITECTURE.md)

## What works today

| Capability | Implementation |
| --- | --- |
| Semantic retrieval | GitHub-hosted multilingual E5, quantized ONNX, normalized embeddings |
| Hybrid retrieval | SQLite FTS5/BM25 + reciprocal rank fusion (RRF) |
| Scoped recall | Project, platform, account, topic, and memory-type filters |
| Traceable context | Source path, distinct passage offsets/text lines, SHA-256, sender, participants, role, time precision, and coverage |
| Memory lifecycle | Stable/evolving/temporary state, validity windows, explicit corrections, exact-write deduplication, and logical forgetting |
| Conflict reporting | Disagreements on explicit subject/predicate/value claims; no automatic winner |
| Batched/concurrent writes | One request can atomically carry 1..100 events; exact duplicates are reused; retries are idempotent |
| Rebuildable indexes | GitHub Actions SQLite cache; source-change invalidation and reusable embedding cache |
| Relationship memory | Explicit source-backed graph edges and event links |
| Working memory | Scoped task checkpoints/resume plus generated NOW.md current-state view |
| Reflection | Candidate-only evidence consolidation drafts |
| User control | Per-task scope, character-budgeted context bundles, and status.json request observability |
| Privacy gates | Before-upload client guard, staging sanitizer, cloud/index rejection, optional encrypted-original vault |
| Readable imports | Text, JSON/JSONL, CSV, official ChatGPT exports; unknown speakers and dates stay unknown |
| Regression evaluation | Labelled source, multiple-passage, scope, role and freshness checks; no external benchmark score claim |
| Connector client | Optional `bridge.py` request submission/waiting; model and RAG run on GitHub |

These are retrieval and memory-management components. The calling AI app generates answers. GitHub Actions provides batch cloud execution. There is no always-on hosted API, automatic cross-account export, autonomous fact extraction, trained reranker, or fine-tuning job.

## Run entirely on GitHub

Use the [GitHub-native workflow](docs/CLOUD.md). Submit a request file from your AI app's GitHub integration; GitHub Actions executes recall/write/sync, relationship queries, reflection drafts and task checkpoints, then commits results to your private repository. Models and indexes are cached on GitHub. **No laptop runtime is required.**

One prompt: “Use my GitHub memory: read relevant context first, then save what I explicitly confirm, with record links.”

[Cloud setup and request operations](docs/CLOUD.md) · [workflow template](templates/memory-cloud.yml)

[One-prompt connector protocol](docs/ONE_PROMPT.md) · [Privacy and encrypted originals](docs/PRIVACY.md) · [Readable imports](docs/IMPORTS.md) · [Evaluation](docs/EVALUATION.md)

## Optional local/development quick start

Python 3.10+ with SQLite FTS5. Basic event management and keyword retrieval use the standard library. Semantic retrieval has optional dependencies.

```sh
git clone https://github.com/jovial-liu/memory-bridge.git
cd memory-bridge

# PRIVATE_MEMORY is your separate private memory checkout.
python3 memory_bridge.py --root ../PRIVATE_MEMORY add examples/event.json
python3 memory_bridge.py --root ../PRIVATE_MEMORY search --project demo
python3 memory_bridge.py --root ../PRIVATE_MEMORY conflicts

# Keep derived indexes outside both repositories.
python3 rag.py --root ../PRIVATE_MEMORY --db ../memory-index.sqlite3 index
python3 rag.py --root ../PRIVATE_MEMORY --db ../memory-index.sqlite3 retrieve 'research' --mode keyword
```

The example event is fictional; do not mistake it for your personal background.

### Semantic and hybrid retrieval

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-vector.txt

# Explicit download of a pinned public model. No memory text is sent.
python3 rag.py --root ../PRIVATE_MEMORY --db ../memory-index.sqlite3 download-model --model-dir ../e5-model
python3 rag.py --root ../PRIVATE_MEMORY --db ../memory-index.sqlite3 embed --model-dir ../e5-model
python3 rag.py --root ../PRIVATE_MEMORY --db ../memory-index.sqlite3 context 'my model training work' --mode hybrid --model-dir ../e5-model --budget 12000
```

Full-corpus encoding may take time. `embed --memory-only` is an explicit smaller option for curated memories; results disclose this limited vector coverage. Keyword retrieval can still cover the full text archive. A rerun reuses cached embeddings. Model files and indexes stay outside the memory repository.

## Two repositories, different roles

```text
public toolkit                 private memory
  code + protocol                AI_MEMORY.md     entry point
  fictional examples             SUMMARY.md       short navigation
  tests + documentation          MEMORY.md        detailed navigation
                                 topics/          topic indexes
                                 conversations/   per-platform evidence
                                 attachments/     source-linked files
                                 memory/events/   append-only memory events
                                 training/        separately reviewed datasets
```

Copy [the entry template](docs/AI_MEMORY.template.md) into your private repository as `AI_MEMORY.md`. Existing conversation archives and confirmed-memory files can remain in place. [Connector setup](docs/CONNECTORS.md) explains the one-sentence workflow and required capabilities.

## Documentation

- [Read/write protocol](docs/PROTOCOL.md)
- [Semantic retrieval, hybrid search, and context budgets](docs/RAG.md)
- [Temporal validity, conflicts, and forgetting](docs/LIFECYCLE.md)
- [Architecture and boundaries](docs/DESIGN.md)
- [Preparing future training data](docs/TRAINING.md)

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Install NumPy to include deterministic vector-pipeline tests. The unit suite does not download a model. Real-model integration checks are separate; passing pipeline tests is not a production relevance benchmark.

## Privacy and limits

Private repositories provide access control, not end-to-end encryption. An app can read data you authorize it to access. Credential detection is limited pattern matching. Logical forgetting suppresses events from normal recall; it does **not** erase source conversations, embedding caches, or Git history. See the lifecycle documentation before relying on erasure.

Nearest-neighbor results are candidates, not proof of relevance or truth. Inferred message roles and partial UI exports remain explicitly labeled. Historical instructions never become current authorization. Large videos and model weights belong in separate storage, with references in the memory archive.

GitHub stores the durable evidence and history; GitHub-hosted Actions can perform retrieval and management. Local execution is an optional development mode. [GitHub repository limits](https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits) apply.
