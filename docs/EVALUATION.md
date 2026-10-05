# Measuring memory behavior

Run source-labelled regressions with `evaluate.py`, or submit a private cloud `evaluate` request referencing a JSON case file under `memory/evaluation/`. Reports contain pass/fail checks and counts, not retrieved private text. Cases can assert expected source paths, multiple distinct passages, required text, exact scopes, evidence roles/statuses, empty out-of-scope results, and unknown authors/times.

```sh
python evaluate.py --root PRIVATE_MEMORY --db /tmp/evaluation.sqlite3 --cases CASES.json --output REPORT.json
```

A case:

```json
{"id":"two-passages","query":"pear comet","project":"demo","expected":{"paths_all":["conversations/demo/one.json"],"min_chunks":2,"roles":["participant"],"unknown_times":true}}
```

Results report curated case pass rate, source hit rate, and scope leakage. They do **not** estimate accuracy on all future questions. Unit/regression tests additionally cover keyword/vector passage identity, RRF fusion, source hashes, corrections, validity, logical forgetting, conflict reporting, credential rejection, import provenance, authenticated backup tampering, and request submission/waiting. Fixture embeddings test the vector pipeline, not real-model semantic quality. Cloud semantic checks must separately disclose their model and encoded scope.

No LongMemEval, LoCoMo, trained reranker, autonomous fact extraction, or automatic truth arbitration is claimed. Add failures discovered in real use as new labelled regressions; retain historical reports with their source snapshot IDs.

For mixed evidence queries, assert `source_roles` and `source_statuses` as path-to-value mappings. `roles` and `statuses` apply to every returned hit; do not require historical document observations to become confirmed personal facts.
