"""
test_rulebook.py — Kiểm thử nạp Rulebook từ thư mục split.
"""

from pathlib import Path
import pytest

from datamate.grounding.rulebook import load_rulebook, clear_rulebook_cache


def test_load_rulebook_from_existing(tmp_path: Path):
    clear_rulebook_cache()
    rule_file = tmp_path / "rulebook.md"
    rule_file.write_text("# Test Rulebook\nQuy định mẫu", encoding="utf-8")

    content = load_rulebook(tmp_path)
    assert "Test Rulebook" in content
    assert "Quy định mẫu" in content


def test_load_rulebook_cache(tmp_path: Path):
    clear_rulebook_cache()
    rule_file = tmp_path / "rulebook.md"
    rule_file.write_text("Nội dung v1", encoding="utf-8")

    v1 = load_rulebook(tmp_path, use_cache=True)
    assert v1 == "Nội dung v1"

    # Sửa tệp trên đĩa nhưng vì có cache nên vẫn đọc v1
    rule_file.write_text("Nội dung v2", encoding="utf-8")
    v2 = load_rulebook(tmp_path, use_cache=True)
    assert v2 == "Nội dung v1"

    # Xóa cache thì đọc được v2
    clear_rulebook_cache()
    v3 = load_rulebook(tmp_path, use_cache=False)
    assert v3 == "Nội dung v2"


def test_load_rulebook_not_found():
    clear_rulebook_cache()
    content = load_rulebook("non_existent_directory_12345")
    assert content == ""
