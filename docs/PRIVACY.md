# Privacy boundaries and pre-upload checks

A private GitHub repository is access-controlled storage, not end-to-end encryption. Its owner, authorized collaborators, tokens, applications, and GitHub-hosted processing can access data within their permissions. An AI app that reads memory also receives that selected content under its own policies.

## Before anything leaves the client

Run `privacy.py sanitize input.txt --output reviewed.txt --report review.json`, or use `ingest.py` to stage normalized exports. Review the report and the sanitized output before committing. The scanner covers credential labels with and without colons, authentication service lines, standalone credential replies, common token formats. Optional strict mode also checks national identity-number patterns, phone numbers, and specific address patterns. Reports contain positions and categories, never matched values. This is pattern-based minimization, not complete anonymization or permission to upload third-party information without considering scope.

`bridge.py` rejects sensitive request/event payloads before calling GitHub. Cloud requests and indexing independently reject detected sensitive content. A vendor's generic GitHub file-upload tool can bypass the client guard: do not submit raw credentials through it and then expect a cloud check to undo the transmission.

## Preserve originals separately

Use optional `vault.py` authenticated AES-256-GCM archives when exact originals must be retained. Install `requirements-privacy.txt` on the import client, generate an owner-only key outside the repository, and keep a secure independent backup of the key. Do not commit it or set it as an Actions secret. Cloud retrieval operates on reviewed, sanitized text; cloud jobs cannot decrypt the original vault without the user-held key. Losing the key loses access to the encrypted originals.

```sh
python vault.py encrypt ORIGINAL --output PRIVATE_MEMORY/vault/original.aesgcm --key-file /secure/outside-repository/archive.key --create-key --repository-root PRIVATE_MEMORY
```

Logical forgetting, current-file redaction, and encrypted replacement do not purge Git history, past clones, Actions logs/caches, or unreferenced objects. Rotate exposed credentials first. Review history removal separately; do not force-push a destructive rewrite as an incidental import operation. If an object cannot be purged through normal controls, ask GitHub Support about the available removal process. Do not claim complete erasure merely because a file is gone from the current branch.

## Permissions

Keep the personal repository private and the public toolkit fictional. Grant applications only the repositories and operations they need; use read access for retrieval and add contents write only where request submission is required. Prefer scoped GitHub Apps/fine-grained tokens to account-wide legacy repository authorization. Do not silently revoke working integrations: audit their repository selection first. Enable account two-factor authentication and review existing sessions and tokens.

Workflows use private-repository guards, pinned action revisions, a pinned reviewed toolkit in deployed archives, and a new cache namespace after privacy migrations. Keyword-only jobs do not install or run semantic models. Encrypted backups, model caches, and sanitized text have distinct retention and access requirements.

## Proportionate filtering

Default guards block credentials (passwords, API keys, private keys and verification codes). Ordinary personal context stays available in the private repository. Use `privacy.py sanitize ... --strict` to additionally minimize identity numbers, phones and precise addresses. Existing redactions are not reversed automatically. Public toolkit examples must always be fictional.
