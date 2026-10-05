# One-sentence access from other AI apps

First tell your assistant the private repository name, OWNER/PRIVATE_MEMORY_REPO, and authorize that repository through its GitHub integration. Do not paste access tokens into chat or memory files.

Copy [AI_MEMORY.template.md](AI_MEMORY.template.md) to the root of the private repository as AI_MEMORY.md. Adapt the paths to your actual archive. The setup is done once; subsequent tasks can use natural language.

## Read prompt

> Use my private GitHub memory repository OWNER/PRIVATE_MEMORY_REPO. Read AI_MEMORY.md first, recover only context relevant to this project, and cite the sources you actually used.

## Write prompt

> Save what we just agreed to OWNER/PRIVATE_MEMORY_REPO. Create a separate event according to AI_MEMORY.md, preserve source, scope and time, and use supersedes for a correction. Return the commit link after saving.

## Capability check

| Connector capability | Supported workflow |
| --- | --- |
| Search/read only | Read context; produce a proposed event file for another writer |
| Repository file creation/update | Save events through GitHub APIs and read back results |
| Local execution or a retrieval tool | Run keyword, semantic, or hybrid retrieval |
| Local clone/commit/push | Use the Python toolkit and submit Git changes |

GitHub's Contents API uses GET to read and PUT with Base64 content to create/update. Updating an existing file requires its current blob SHA. Fine-grained access typically requires Contents: read for reading and Contents: write for writing; the integration's actual authorization mechanism may differ.

Prefer a new event file per write. GitHub operations may still conflict at the branch level; re-read and retry without force-overwriting. This project does not run an online synchronization service and has not verified every vendor's GitHub plugin.

Official reference: [GitHub Contents API](https://docs.github.com/en/rest/repos/contents).
