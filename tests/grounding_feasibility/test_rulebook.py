"""
test_rulebook.py — Kiểm thử nạp Rulebook từ thư mục split (grounding_feasibility).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent.parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from datamate.grounding_feasibility.rulebook import load_rulebook, clear_rulebook_cache


class TestRulebook(unittest.TestCase):
    def setUp(self):
        clear_rulebook_cache()
        self._temp_dir_obj = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._temp_dir_obj.name)

    def tearDown(self):
        clear_rulebook_cache()
        self._temp_dir_obj.cleanup()

    def test_load_rulebook_from_existing(self):
        rule_file = self.tmp_path / "rulebook.md"
        rule_file.write_text("# Test Rulebook\nQuy định mẫu", encoding="utf-8")

        content = load_rulebook(self.tmp_path)
        self.assertIn("Test Rulebook", content)
        self.assertIn("Quy định mẫu", content)

    def test_load_rulebook_cache(self):
        rule_file = self.tmp_path / "rulebook.md"
        rule_file.write_text("Nội dung v1", encoding="utf-8")

        v1 = load_rulebook(self.tmp_path, use_cache=True)
        self.assertEqual(v1, "Nội dung v1")

        rule_file.write_text("Nội dung v2", encoding="utf-8")
        v2 = load_rulebook(self.tmp_path, use_cache=True)
        self.assertEqual(v2, "Nội dung v1")

        clear_rulebook_cache()
        v3 = load_rulebook(self.tmp_path, use_cache=False)
        self.assertEqual(v3, "Nội dung v2")

    def test_load_rulebook_not_found(self):
        content = load_rulebook("non_existent_directory_12345")
        self.assertEqual(content, "")


if __name__ == "__main__":
    unittest.main()

