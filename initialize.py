"""Initialize an empty private memory without overwriting existing records."""
import argparse
import json
from pathlib import Path
import re


def initialize(root, repository):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Expected owner/repository")
    root = Path(root)
    entry = (Path(__file__).parent / "docs/AI_MEMORY.template.md").read_text()
    files = {
        "AI_MEMORY.md": entry + "\nRepository: https://github.com/" + repository + "\n",
        "SUMMARY.md": "# Memory overview\n\nNo personal facts have been imported yet. Read AI_MEMORY.md for access rules.\n",
        "MEMORY.md": "# Detailed memory navigation\n\n- memory/events/: sourced memory events\n- memory/working/: task checkpoints\n- conversations/: normalized source conversations\n- memory/requests/ and memory/results/: cloud operations\n\nOnly available sources count as collected.\n",
        "memory/config.json": json.dumps({"version": 1, "repository": repository, "execution": "github-actions", "default_mode": "hybrid"}, indent=2) + "\n",
    }
    for folder in ("memory/events", "memory/working", "memory/requests", "memory/results", "conversations", "topics", "attachments", "training"):
        files[folder + "/.gitkeep"] = ""
    created = []
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            continue
        with path.open("x") as target:
            target.write(content)
        created.append(name)
    return created


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    print("Initialized " + str(len(initialize(args.root, args.repository))) + " missing files")
