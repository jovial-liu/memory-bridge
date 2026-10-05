# Deploy your own private memory on GitHub

1. [Use this template](https://github.com/jovial-liu/memory-bridge/generate). Choose a repository name and **Private**. Do not use Fork: create a new private repository from the template.
2. Open **Actions → Initialize Private Memory → Run workflow** on the default branch. The workflow refuses public repositories and adds only missing files; it does not import the author's private archive or overwrite your existing summary.
3. Wait for a successful run. You should see `AI_MEMORY.md`, `SUMMARY.md`, `MEMORY.md`, and empty archive/event/checkpoint directories.
4. Authorize your AI app's GitHub connector for this repository. For cloud operations it must create files and read files; read-only search plugins cannot write requests. For your first prompt say: **“Read AI_MEMORY.md in OWNER/REPOSITORY. Use GitHub cloud memory for this task, read relevant context and save only what I explicitly confirm.”**
5. Submit the following first request with the connector or GitHub's Add file UI, at `memory/requests/0123456789abcdef0123456789abcdef.json`:

```json
{"id":"0123456789abcdef0123456789abcdef","operation":"recall","query":"my current projects","mode":"keyword","limit":5,"budget":2000}
```

6. Wait for **Memory Cloud** to succeed and read `memory/results/0123456789abcdef0123456789abcdef.json`. An empty new archive correctly returns no matches. Each later request uses a fresh 32-character hexadecimal ID. A pending request can also be processed using **Memory Cloud → Run workflow** if a connector's credentials do not trigger push workflows.

For semantic retrieval, omit `mode` or set it to `hybrid`. The first semantic query downloads a pinned public embedding model onto the GitHub runner; personal text remains inside the private workflow. Later runs reuse a rebuildable private Actions cache. Actions quotas and cache eviction apply; processing is asynchronous.

For a confirmed memory write or a combined read/write, see the exact `write` and `sync` payloads in [CLOUD.md](CLOUD.md). A connector must report completion only after a successful result, and provide the record link. A single prompt is an instruction for a capable connector, not an installation of a vendor plugin.

## Troubleshooting and maintenance

- Permission denied while pushing: check organization policy and Actions write permissions. The workflows request `contents: write`; branch protection may require adapting publishing to pull requests.
- No workflow run: check the default branch, Actions enablement, request path, and the run's logs. The memory worker deliberately skips public repositories and pushes on other branches.
- Invalid request: inspect the failure, correct the unprocessed request or submit a new ID. Never modify a processed request.
- Template code updates are not automatic. Review and copy upstream code/workflow updates without replacing private data. The installed code is the snapshot you created.
- Existing separate private archives can keep using [the workflow template](../templates/memory-cloud.yml); pin its public toolkit checkout to a reviewed commit.

No author-owned account, API key, model subscription, or local background service is required. GitHub Actions may consume your account's allotted minutes/storage. The AI app itself needs its own authorized GitHub integration.
