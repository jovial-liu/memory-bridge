# Semantic and hybrid retrieval

## Pipeline

Source messages → overlapping chunks → BM25 and/or local E5 vectors → scope/time/lifecycle filtering → reciprocal rank fusion → deduplication → verified citations → budgeted context → the calling AI app generates an answer.

The toolkit implements retrieval and context assembly, not a generation model. It does not send private text to an embedding API.

## Index and query

```sh
python3 rag.py --root ../PRIVATE_MEMORY --db ../index.sqlite3 index
python3 rag.py --root ../PRIVATE_MEMORY --db ../index.sqlite3 download-model --model-dir ../e5-model
python3 rag.py --root ../PRIVATE_MEMORY --db ../index.sqlite3 embed --model-dir ../e5-model
python3 rag.py --root ../PRIVATE_MEMORY --db ../index.sqlite3 retrieve 'past research decisions' --mode hybrid --model-dir ../e5-model --topic research --limit 8
python3 rag.py --root ../PRIVATE_MEMORY --db ../index.sqlite3 context 'how I prefer answers' --mode semantic --model-dir ../e5-model --budget 12000
```

Modes: keyword (no vector dependencies), semantic, hybrid. Filters: --project, --platform, --account, --topic, --memory-type. --project matches explicit labels only; unlabeled historical conversations stay unknown. Topic labels come from index.json, not automatic identity inference.

## Embedding model

The default backend is the quantized ONNX conversion of intfloat/multilingual-e5-small from Xenova/multilingual-e5-small, pinned to revision 761b726dd34fb83930e26aab4e9ac3899aa1fa78. Downloads verify the model's LFS SHA-256 and record file digests. Loading checks those digests again. Query/passage prefixes, attention-mask mean pooling, and L2 normalization follow the original model card.

Long chunks use overlapping tokenizer overflow windows; window vectors are averaged and normalized. This covers the full chunk instead of silently dropping its tail, but can dilute narrow details. The original 1200-character chunks overlap by 160 characters. Quantization and window averaging can change quality from the original model.

## Cache and coverage

Embeddings are cached by model fingerprint and text digest. Lexical rebuilds retain reusable embedding-cache entries, then embed reconnects vectors to the current chunk IDs. A partial/interrupted encoding has no valid vector_snapshot, so semantic queries refuse it. Completed results disclose all-chunks or memory-only coverage.

Use --memory-only for explicit limited semantic coverage of curated facts/events. Keywords can still cover the historical archive; this is not full-corpus semantic recall.

The cache contains private derivatives. Keep it outside Git repositories. Snapshot invalidation catches source/index changes, and retrieved files are checked by SHA-256. Expiry and future validity are evaluated at query time, even if the files did not change.

## Ranking and citations

RRF adds 1/(60+rank) for each candidate channel. It is deterministic rank fusion, not a trained reranker. Semantic scores express relative similarity, not truth or confidence. Top neighbors can be irrelevant; the calling assistant must assess relevance and acknowledge missing evidence.

Results retain source file, message index, character offset, checksum, role, role-status, time, coverage, platform and account. Explicit unresolved claims include conflicting event IDs. Context budgets count characters, not model tokens; the calling app must check its own token budget.

Attachments are not embedded or OCR'd by this version. Historical conversations remain evidence, not current facts. Inferred UI roles and partial exports retain their labels.

References: [SQLite FTS5](https://www.sqlite.org/fts5.html), [original multilingual E5 model card](https://huggingface.co/intfloat/multilingual-e5-small), [ONNX conversion](https://huggingface.co/Xenova/multilingual-e5-small).

## Local document evidence imported into GitHub

`memory/documents/*.json` archives have `version: 1` and a `documents` array. Each entry requires `text`, `source_path`, `source_sha256` (64 hexadecimal characters), and explicit `coverage`; optional fields include `title`, `modified`, and an explicitly assigned `project`. Retrieval labels these entries `kind=document`, `role=document`, `status=historical`. A document mentioning a person is evidence about that document, not confirmation of the repository owner's identity. Original source hashes identify the imported version; the cloud can verify the stored archive hash, but cannot verify a local original it cannot access.

Document extraction and filesystem inventory are ingestion steps. After upload, recall runs on GitHub, with no local model execution. Full source coverage must never be claimed for a page or character excerpt.
