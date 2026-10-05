# Readable imports and coverage

`ingest.py` stages plain text, normalized message JSON, JSONL, CSV (`text` plus optional `sender,timestamp` columns), and official ChatGPT mapping exports. It supports the current branch of each conversation in a multi-conversation export. Preserve raw exports outside the working repository or in the encrypted vault; only reviewed normalized text goes into the retrievable archive.

```sh
python ingest.py EXPORT --output REVIEW_STAGE --platform wechat --account owner --project contact-example --participant owner --participant peer
```

The output is explicitly staged, not uploaded. Human text defaults to participant; a copied line does not become a user fact. Plain-text line counts are not message counts. Unknown dates stay null, date-only labels remain date labels, and only timezone-aware or numeric export timestamps become exact timestamps. Contact names require the user's explicit clarification or reliable export metadata; never infer alternating speakers.

Protected native `.bak`, `.db`, `.sqlite` files are archival artifacts, not plaintext exports. The importer rejects them rather than counting database files as chats or attempting key extraction. Vendor-specific backup decryption, account login, media transcription, and automatic acquisition of every platform are outside this importer.

Maintain an import registry containing platform/account, imported artifacts, messages with known/unknown roles and dates, coverage status (`partial`, `unknown`, or evidenced complete), and the exact next source needed. A missing export stays missing. Imported attachments are document evidence, never counted as chat messages.
