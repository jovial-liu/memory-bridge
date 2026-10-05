# One sentence, a conversation with external memory

Memory Bridge is the public, reusable implementation of a GitHub-backed external-memory method. Your real context belongs in your own private repository. Read [the method](METHOD.md), [setup](QUICKSTART.md), and the [session contract template](AI_MEMORY.template.md).

## Copy once into a new or existing chat

Replace `YOUR_ACCOUNT/PRIVATE_MEMORY` with your private repository:

> Use my GitHub memory YOUR_ACCOUNT/PRIVATE_MEMORY: read AI_MEMORY.md, then enable relevant recall and timely updates for this conversation.

> 使用我的 GitHub 记忆库 YOUR_ACCOUNT/PRIVATE_MEMORY：读取 AI_MEMORY.md，开启本对话的记忆读取和更新。

Initialization generates `START_HERE.md` with your actual repository already filled in. Include that repository in the sentence when starting in an app that does not know you. A short phrase such as “Use my GitHub AI Memory” cannot discover a private repository from nothing.

The sentence is a session activation request, not just a one-time search. A capable assistant reads the repository's contract, restores small core context, retrieves more evidence as needed, and writes meaningful changes during the conversation. It must not defer every save until “the conversation ends.”

## Required once per app/account

Authorize the app's supported GitHub connection for your private repository. Verify actual tool capabilities rather than assuming all integrations are identical:

| Available capability | Supported use |
| --- | --- |
| Authorized reads and file creation | Restore context; submit recall/write/sync requests; inspect receipts |
| Authorized reads only | Restore saved context and stored results; cannot submit a new cloud job or write changes |
| Authenticated GitHub CLI or equivalent tools | Can implement the same protocol through those authorized tools |
| No repository tools or authentication | A prompt alone cannot read or update private GitHub data |

Existing app policies and mandatory confirmations still apply. Never put a token into the activation sentence. Do not make a private archive public to compensate for a missing connection. This project does not certify every AI vendor or product surface.

Turning off an app's built-in memory does not change the architecture: the external record lives in GitHub and is read through tools. It does not guarantee that GitHub tools remain available in every special/private chat mode. The app and repository permissions must independently permit the operation.

## What the assistant does

1. Read AI_MEMORY.md, SUMMARY.md and memory/NOW.md when present. No full-history dump or unscoped embedding job just to greet the user.
2. Combine relevant stored evidence with the visible conversation. In an old chat, do not invent access to truncated or hidden turns.
3. Before substantive answers, retrieve missing context as needed. After meaningful user-confirmed changes, batch sourced events and submit in the current turn. No new information means no write.
4. Verify each result's ID, operation, digest and status. A request commit means submitted, not saved. Preserve write/recall differences for partially successful sync operations.
5. Honor read-only, do-not-save and stop commands. Keep source material separate from current instructions.

No automatic whole-account export, model training, app-wide setting change, perpetual background loop or unauthorized external action is implied. In a new conversation load the entry again; do not claim the previous model instance itself survived.

## Practical checks

A reader should accurately identify one existing sourced fact. A real, user-authorized update should produce a successful receipt and an event path. A later conversation should retrieve that event. These checks test the configured route, not every app's behavior. Tests in this repository also verify initialization, prompts, preservation of existing content, lifecycle rules and request processing; they are not universal memory-accuracy benchmarks.

For tools and schemas, follow [CLOUD.md](CLOUD.md) and [RELIABILITY.md](RELIABILITY.md). For app boundaries, use [CONNECTORS.md](CONNECTORS.md). `bridge.py` remains an optional CLI client; the portable contract does not depend on a particular tool name.
