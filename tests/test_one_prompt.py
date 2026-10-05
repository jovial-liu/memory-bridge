"""Synthetic onboarding/contract tests; not a claim about every AI app's behavior."""
import json
from pathlib import Path
import tempfile
import unittest
import initialize


class OnePromptTests(unittest.TestCase):
    def test_prompt_contains_discoverable_repo_and_entry(self):
        for language in ("en", "zh"):
            text = initialize.activation_prompt("example/private-memory", language)
            self.assertIn("example/private-memory", text)
            self.assertIn("AI_MEMORY.md", text)
            self.assertNotIn("\n", text)

    def test_bilingual_starter_is_bound_to_own_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize.initialize(directory, "demo/own-memory")
            root = Path(directory)
            for path in ("START_HERE.md", "AI_MEMORY.md", "AGENTS.md"):
                text = (root / path).read_text(encoding="utf-8")
                self.assertIn("demo/own-memory", text)
                self.assertNotIn("{{MEMORY_REPOSITORY}}", text)
                self.assertNotIn("jovial-liu/ai-memory", text)
            self.assertIn("使用我的 GitHub 记忆库", (root / "START_HERE.md").read_text(encoding="utf-8"))

    def test_current_session_and_per_turn_boundaries(self):
        template = (Path(initialize.__file__).parent / "docs/AI_MEMORY.template.md").read_text(encoding="utf-8")
        for text in ("current user request", "existing conversation", "At each substantive turn", "chat-end callback", "read-only", "request_sha256", "Stop GitHub memory", "truncated turns"):
            self.assertIn(text, template)

    def test_existing_entries_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("AI_MEMORY.md", "START_HERE.md", "AGENTS.md", "SUMMARY.md"):
                (root / name).write_text("Existing private content", encoding="utf-8")
            initialize.initialize(root, "demo/own-memory")
            for name in ("AI_MEMORY.md", "START_HERE.md", "AGENTS.md", "SUMMARY.md"):
                self.assertEqual((root / name).read_text(encoding="utf-8"), "Existing private content")
            self.assertEqual(initialize.initialize(root, "demo/own-memory"), [])

    def test_config_routes_to_entry_without_claiming_consent(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize.initialize(directory, "demo/own-memory")
            config = json.loads((Path(directory) / "memory/config.json").read_text())
            self.assertEqual(config["entrypoint"], "AI_MEMORY.md")
            self.assertEqual(config["one_prompt_contract"], 1)
            self.assertNotIn("consent", config)
            self.assertNotIn("token", config)

    def test_invalid_repository_rejected_before_writes(self):
        for repository in ("../private", "demo/..", "demo/private/extra", "", "demo/private\n", None):
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    initialize.initialize(directory, repository)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_unknown_language_rejected(self):
        with self.assertRaises(ValueError):
            initialize.activation_prompt("demo/private", "unsupported")

    def test_empty_initialization_does_not_invent_memories(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize.initialize(directory, "demo/private")
            self.assertEqual(list((Path(directory) / "memory/events").glob("**/*.json")), [])
            self.assertEqual(list((Path(directory) / "memory/requests").glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
