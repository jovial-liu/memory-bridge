# Memory Bridge

**One sentence to restore and update your context across compatible AI apps.**

[![Tests](https://github.com/jovial-liu/memory-bridge/actions/workflows/tests.yml/badge.svg)](https://github.com/jovial-liu/memory-bridge/actions/workflows/tests.yml)
[English](README.md) · [简体中文](README.zh-CN.md) · [MIT](LICENSE)

Memory Bridge is an open-source method and reference implementation for **GitHub-backed external AI memory**. This public repository presents the design and provides reusable tools, protocols, templates, tests and fictional examples. Your real personal context belongs in your own **separate private repository**.

## One sentence, not another introduction

After authorizing a compatible AI app to access your private repository, use this in a new chat or an existing conversation:

> Use my GitHub memory YOUR_ACCOUNT/PRIVATE_MEMORY: read AI_MEMORY.md, then enable relevant recall and timely updates for this conversation.

> 使用我的 GitHub 记忆库 YOUR_ACCOUNT/PRIVATE_MEMORY：读取 AI_MEMORY.md，开启本对话的记忆读取和更新。

The assistant restores small core context, retrieves relevant evidence as needed, and saves meaningful sourced changes during the conversation. It checks actual processing receipts instead of treating a request commit as success. New chats load the entry again; the previous model's hidden state is not being transferred.

**This does not require a vendor-native memory store, but it does require authorized GitHub tools.** Read-only connections cannot write. A prompt cannot grant missing permissions, bypass app restrictions, guarantee every model follows the protocol, or recover unseen chat history. Never paste credentials into the sentence.

[How the method works](docs/METHOD.md) · [One-prompt contract and app boundaries](docs/ONE_PROMPT.md)

## Create your own private memory

[**Use this template**](https://github.com/jovial-liu/memory-bridge/generate) → choose **Private** → **Actions → Initialize Private Memory → Run workflow** → authorize your AI app for that repository.

Open the generated **START_HERE.md**: it contains English and Chinese activation sentences with your own repository already filled in. AI_MEMORY.md is the authoritative session contract; AGENTS.md routes supporting agents to it. Initialization creates missing files and never overwrites existing personal records. Public copies do not run personal-memory processing.

GitHub Actions runs retrieval and memory management; no laptop model or permanent server is required. The optional CLI is for development or clients with shell access. Your AI app still needs its own authorized integration.

[Complete setup](docs/QUICKSTART.md) · [Cloud protocol](docs/CLOUD.md) · [Agent architecture](docs/ARCHITECTURE.md)

## What is implemented

| Capability | Implementation |
| --- | --- |
| One-prompt onboarding | Repository-bound bilingual starter; a conversation-scoped read/write contract |
| Semantic and hybrid retrieval | Multilingual E5 with quantized ONNX; SQLite FTS5/BM25 and reciprocal rank fusion |
| Scoped evidence | Project, platform, account, topic and memory-type filters; context budgets |
| Traceable answers | Source paths, distinct passage offsets, hashes, roles, time precision and coverage |
| Current state | Bounded generated NOW.md and scoped checkpoints/resume |
| Lifecycle and correction | Validity windows, explicit supersession, provenance-aware deduplication and logical forgetting |
| Relationships | Explicit source-backed claims and links; unresolved conflicts remain visible |
| Write reliability | Batch preflight, per-request failure isolation, verifiable receipts and outcome-aware status |
| Reflection | Candidate-only evidence consolidation, not autonomous fact promotion |
| Privacy | Before-upload checks, optional encrypted originals, separate public code/private data |
| Evaluation | Synthetic software tests and source-labelled regressions; no universal memory-accuracy claim |

The calling assistant decides what is relevant and generates responses. The toolkit stores, validates and retrieves evidence. There is no always-on hosted API, automatic whole-account export, autonomous extraction model, trained reranker, model-weight continual learning or RSI implemented here. Filesystem batch rollback is not a crash-atomic database transaction; see [reliability semantics](docs/RELIABILITY.md).

## Two repositories, distinct responsibilities

```text
public memory-bridge            your private memory
  method + source code            START_HERE.md    copy your one sentence
  protocols + templates           AI_MEMORY.md     session contract
  synthetic tests                 SUMMARY.md       compact core context
  fictional examples              memory/NOW.md    current state
                                  memory/events/   sourced facts and changes
                                  conversations/   archival evidence
                                  memory/requests/ submitted operations
                                  memory/results/ outcome receipts
```

Anyone can reuse the public method and implementation under the repository license. Creating a private copy does not expose anyone else's memory or share account credentials. Existing archives may remain in place. Derived summaries and caches are not the sole source of truth.

## Optional local/development usage

Python 3.10+ with SQLite FTS5. Basic event handling and keyword retrieval use the standard library; semantic retrieval has optional dependencies.

```sh
git clone https://github.com/jovial-liu/memory-bridge.git
cd memory-bridge
python3 initialize.py --root ../PRIVATE_MEMORY --repository YOUR_ACCOUNT/PRIVATE_MEMORY
python3 memory_bridge.py --root ../PRIVATE_MEMORY search --project demo
python3 rag.py --root ../PRIVATE_MEMORY --db ../memory-index.sqlite3 index
python3 rag.py --root ../PRIVATE_MEMORY --db ../memory-index.sqlite3 retrieve 'research' --mode keyword
```

The disposable index stays outside the archive. For model download, content-addressed vector caching and hybrid context generation, see [RAG.md](docs/RAG.md). `bridge.py` is an optional authorized GitHub client; using it does not certify another vendor's connector.

## Documentation and tests

[Method](docs/METHOD.md) · [One prompt](docs/ONE_PROMPT.md) · [Read/write protocol](docs/PROTOCOL.md) · [Cloud execution](docs/CLOUD.md) · [Lifecycle](docs/LIFECYCLE.md) · [Reliability](docs/RELIABILITY.md) · [Privacy](docs/PRIVACY.md) · [Imports](docs/IMPORTS.md) · [Evaluation](docs/EVALUATION.md) · [Future training data](docs/TRAINING.md)

```sh
python3 -m unittest discover -s tests -v
```

NumPy enables deterministic vector tests. Unit tests do not download a model; real-model integration checks and vendor-app trials are separate. Passing tests is not an external benchmark score or a guarantee of perfect memory.

## Privacy and limitations

Private GitHub repositories provide access control, not end-to-end encryption. Authorized apps can process the data they read. Credential checks are limited pattern matching. Logical forgetting does not erase Git history, original conversations or old caches. History is evidence, not current authorization; unknown message authors stay unknown.

An activation sentence requests scoped updates, not full chat export or unrelated actions. Honor read-only, do-not-save and stop commands. [GitHub repository limits](https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits) and each app's capabilities still apply.
