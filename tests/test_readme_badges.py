from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "madmallard_badges", ROOT / "scripts" / "badges.py"
)
badges = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(badges)


class ReadmeBadgeStandardsTests(unittest.TestCase):
    def test_detects_only_repo_evidenced_core_stack(self):
        detected = set(badges.detected(ROOT))
        self.assertTrue(
            {"Python", "Django", "SQLite", "Docker", "Docker Compose", "Terraform", "AWS"}
            <= detected
        )

    @mock.patch.object(badges, "published_release_exists", return_value=False)
    def test_readme_badge_block_matches_generator(self, _release):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        start = readme.index(badges.START)
        end = readme.index(badges.END) + len(badges.END)
        self.assertEqual(badges.generate(ROOT), readme[start:end])

    def test_badge_markers_are_unique(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(1, readme.count(badges.START))
        self.assertEqual(1, readme.count(badges.END))


if __name__ == "__main__":
    unittest.main()
