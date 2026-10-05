# One-prompt access from an AI app

The app must have access to the selected private repository and file read/create capabilities. A read-only GitHub connector can read curated files but cannot submit a cloud retrieval or write request. Vendor plugins, account authentication, and custom tool availability differ; no repository can grant those missing capabilities by itself.

## Reusable prompts

> Read `AI_MEMORY.md` in `YOUR_ACCOUNT/PRIVATE_MEMORY`. Retrieve only the memories relevant to this question using the documented cloud request protocol. Wait for the matching result; cite source records and distinguish unknown speakers, historical evidence, and confirmed facts.

> Save the decision I explicitly asked you to remember in `YOUR_ACCOUNT/PRIVATE_MEMORY`, with a source and date. Exclude credentials and unnecessary third-party details. Use candidate status unless I directly confirmed the fact. Submit a unique cloud write request, wait for its result, and give me the saved-record link.

> Do not read or write historical memory for this conversation.

## Protocol for connector authors

1. Read the repository entry point and choose a project/contact scope. Never load the entire archive as the default prompt.
2. Minimize and validate content **before upload**. Historical messages and embedded commands are evidence, not instructions.
3. Create `memory/requests/<UUID-without-dashes>.json`; recall uses query/mode/project and optional platform/account filters. Write includes a sourced event.
4. Poll for `memory/results/<same-ID>.json`, respecting normal app/tool limits. Treat submission as pending, not completion.
5. Verify request ID, operation, execution, sources, scopes, role, time precision, and conflicts. If a timeout occurs, return the pending ID so a later call can resume.
6. Report missing permissions or sources accurately. Do not infer message authors, dates, or whole-account export completeness.

Example request/event payloads and lifecycle rules are in [CLOUD.md](CLOUD.md) and [PROTOCOL.md](PROTOCOL.md). `bridge.py` is an optional command-line client for agents with shell access; it uses existing `gh` authentication and never runs a local semantic model. Its recall, submission/wait, privacy rejection, and idempotent cloud-write paths have regression coverage. This does not certify every vendor's plugin.

```sh
python bridge.py --repository YOUR_ACCOUNT/PRIVATE_MEMORY recall 'current project decisions' --project demo --mode hybrid --wait 180
python bridge.py --repository YOUR_ACCOUNT/PRIVATE_MEMORY remember 'The demo uses concise answers.' --project demo --source-reference 'user-message-42' --source-excerpt 'Please keep the demo answers concise.' --wait 120
```

Cloud jobs are asynchronous. Curated profile/summary files can be read immediately; semantic recall waits for Actions startup and processing. There is no always-on GitHub-hosted API in this project.
