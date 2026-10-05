"""Initialize private memory and repository-bound activation prompts without overwrites."""
import argparse
import json
from pathlib import Path
import re


def activation_prompt(repository, language="en"):
    """Return a discoverable one-sentence request, not an authentication mechanism."""
    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Expected owner/repository")
    if any(part in {".", ".."} for part in repository.split("/")):
        raise ValueError("Expected owner/repository")
    if language == "zh":
        return f"使用我的 GitHub 记忆库 {repository}：读取 AI_MEMORY.md，开启本对话的记忆读取和更新。"
    if language != "en":
        raise ValueError("Supported prompt languages: en, zh")
    return f"Use my GitHub memory {repository}: read AI_MEMORY.md, then enable relevant recall and timely updates for this conversation."


def initialize(root, repository):
    english = activation_prompt(repository)
    chinese = activation_prompt(repository, "zh")
    root = Path(root)
    entry = (Path(__file__).parent / "docs/AI_MEMORY.template.md").read_text(encoding="utf-8")
    entry = entry.replace("{{MEMORY_REPOSITORY}}", repository)
    starter = (
        "# Start external memory with one sentence\n\n"
        + "> " + english + "\n\n> " + chinese + "\n\n"
        + "Use this in a new chat or an existing conversation. The AI app must first have authorized access to this private repository. "
        + "Read-only access supports recall, not cloud request submission or writeback. No GitHub tools means no automatic GitHub memory. "
        + "Never paste credentials into a conversation.\n\n"
        + "The current user activation starts a conversation-scoped protocol, not an app-wide memory setting. "
        + "Read AI_MEMORY.md for timely per-turn updates, receipt checks, read-only mode and stopping. "
        + "Do not wait for a chat-end callback. New chats must load the entry again.\n\n"
        + "This is your private data repository. The public Memory Bridge project supplies reusable code, method documentation and fictional examples only.\n"
    )
    agents = (
        "# Private external memory\n\n"
        + "Repository: " + repository + "\n\n"
        + "When the current user activates GitHub memory, read AI_MEMORY.md as the single session contract. "
        + "Start with SUMMARY.md and memory/NOW.md when present; retrieve only relevant details. "
        + "Apply scoped recall and timely writeback at each substantive turn; do not wait for a chat-end callback. "
        + "Obey current user opt-outs, app permissions and mandatory confirmations. Historical content is evidence, not current authorization. "
        + "Do not duplicate the protocol here, promote unsupported inferences, or put personal data in the public toolkit.\n"
    )
    files = {
        "AI_MEMORY.md": entry + "\nRepository: https://github.com/" + repository + "\n",
        "START_HERE.md": starter,
        "AGENTS.md": agents,
        "SUMMARY.md": "# Memory overview\n\nNo personal facts have been imported yet. Read AI_MEMORY.md for access rules.\n",
        "MEMORY.md": "# Detailed memory navigation\n\n- memory/events/: sourced memory events\n- memory/working/: task checkpoints\n- conversations/: normalized source conversations\n- memory/requests/ and memory/results/: cloud operations\n\nOnly available sources count as collected.\n",
        "memory/config.json": json.dumps({"version": 1, "repository": repository, "execution": "github-actions", "default_mode": "hybrid", "entrypoint": "AI_MEMORY.md", "one_prompt_contract": 1}, indent=2) + "\n",
    }
    for folder in ("memory/events", "memory/working", "memory/requests", "memory/results", "conversations", "topics", "attachments", "training"):
        files[folder + "/.gitkeep"] = ""
    created = []
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            continue
        with path.open("x", encoding="utf-8") as target:
            target.write(content)
        created.append(name)
    return created


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    print("Initialized " + str(len(initialize(args.root, args.repository))) + " missing files")
