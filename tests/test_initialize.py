import tempfile
import unittest
from pathlib import Path
import initialize
import cloud
import memory_bridge


class InitializationTests(unittest.TestCase):
    def test_ready_empty_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize.initialize(directory, "example/my-memory")
            self.assertEqual(memory_bridge.load(directory), [])
            self.assertEqual(cloud.pending(directory), [])
            entry = (Path(directory)/"AI_MEMORY.md").read_text()
            self.assertIn("example/my-memory", entry)
            self.assertTrue((Path(directory)/"memory/working").is_dir())

    def test_existing_personal_content_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"SUMMARY.md"
            path.write_text("My existing summary")
            initialize.initialize(directory, "example/my-memory")
            self.assertEqual(path.read_text(), "My existing summary")
            self.assertEqual(initialize.initialize(directory, "example/my-memory"), [])

    def test_invalid_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                initialize.initialize(directory, "../private/path")
            self.assertEqual(list(Path(directory).iterdir()), [])
