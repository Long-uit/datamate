"""
tests/test_submission.py — Unit tests cho module submission của DataMate (Phase 1).

Chạy: pytest tests/test_submission.py -v
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Thêm thư mục src vào sys.path để import
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from src.submission import (
        SubmissionWriter,
        make_abstain,
        to_answer,
        validate_submission,
    )
except ImportError:
    from submission import (
        SubmissionWriter,
        make_abstain,
        to_answer,
        validate_submission,
    )


# ===========================================================================
# 1. Test to_answer & make_abstain
# ===========================================================================

def test_to_answer_bool_before_int():
    """True / False phải suy luận thành boolean, KHÔNG được thành number."""
    ans_true = to_answer(True)
    assert ans_true["type"] == "boolean"
    assert ans_true["answer"] is True

    ans_false = to_answer(False)
    assert ans_false["type"] == "boolean"
    assert ans_false["answer"] is False

    ans_np_bool = to_answer(np.bool_(True))
    assert ans_np_bool["type"] == "boolean"
    assert ans_np_bool["answer"] is True


def test_to_answer_int_and_float():
    """int và float được chuyển thành number."""
    ans_int = to_answer(123456)
    assert ans_int["type"] == "number"
    assert ans_int["answer"] == 123456

    ans_float = to_answer(99.5)
    assert ans_float["type"] == "number"
    assert ans_float["answer"] == 99.5


def test_to_answer_str_and_list():
    """Chuỗi thành string, danh sách thành list."""
    ans_str = to_answer("Cà phê sữa đá")
    assert ans_str["type"] == "string"
    assert ans_str["answer"] == "Cà phê sữa đá"

    ans_list = to_answer(["SP01", "SP02", 100])
    assert ans_list["type"] == "list"
    assert ans_list["answer"] == ["SP01", "SP02", 100]


def test_to_answer_dict_with_type():
    """Dict có đúng 2 khóa type và answer được giữ nguyên cho normalizer."""
    custom = {"type": "date", "answer": "2025-05-20"}
    res = to_answer(custom)
    assert res == custom

    custom_table = {
        "type": "table",
        "answer": {"columns": ["san_pham", "doanh_thu"], "rows": [["A", 100]]},
    }
    assert to_answer(custom_table) == custom_table


def test_to_answer_none_and_strange_types():
    """None hoặc đối tượng không xác định -> abstain."""
    ans_none = to_answer(None)
    assert ans_none["type"] == "abstain"

    ans_obj = to_answer(object())
    assert ans_obj["type"] == "abstain"

    ans_dict_strange = to_answer({"invalid_key": 123})
    assert ans_dict_strange["type"] == "abstain"


def test_to_answer_nan_and_numpy_scalars():
    """NaN/NA chuyển thành abstain; numpy.int64/float64 chuyển thành int/float thuần."""
    ans_nan = to_answer(float("nan"))
    assert ans_nan["type"] == "abstain"

    ans_np_nan = to_answer(np.nan)
    assert ans_np_nan["type"] == "abstain"

    ans_pd_na = to_answer(pd.NA)
    assert ans_pd_na["type"] == "abstain"

    ans_np_int = to_answer(np.int64(42))
    assert ans_np_int["type"] == "number"
    assert ans_np_int["answer"] == 42
    assert type(ans_np_int["answer"]) is int

    ans_np_float = to_answer(np.float64(3.14))
    assert ans_np_float["type"] == "number"
    assert abs(ans_np_float["answer"] - 3.14) < 1e-4


def test_make_abstain():
    """make_abstain trả về type abstain, có thể kèm reason."""
    a1 = make_abstain()
    assert a1["type"] == "abstain"
    assert "reason" not in a1

    a2 = make_abstain("Không đủ độ tin cậy")
    assert a2["type"] == "abstain"
    assert a2["reason"] == "Không đủ độ tin cậy"


# ===========================================================================
# 2. Test SubmissionWriter
# ===========================================================================

def test_submission_writer_basic(tmp_path: Path):
    """File có đúng số dòng, parse được JSON, tiếng Việt không bị escape."""
    sub_file = tmp_path / "sub.jsonl"
    log_dir = tmp_path / "logs"

    with SubmissionWriter(sub_file, log_dir) as writer:
        writer.write("q_01", {"type": "string", "answer": "Cà phê sữa đá"})
        writer.write("q_02", {"type": "number", "answer": 150000})

    assert sub_file.exists()
    content = sub_file.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    assert len(lines) == 2
    # Tiếng Việt không bị escape thành \u...
    assert "Cà phê sữa đá" in content

    item1 = json.loads(lines[0])
    assert item1["id"] == "q_01"
    assert item1["type"] == "string"
    assert item1["answer"] == "Cà phê sữa đá"

    item2 = json.loads(lines[1])
    assert item2["id"] == "q_02"
    assert item2["type"] == "number"
    assert item2["answer"] == 150000


def test_submission_writer_disk_persistence_while_open(tmp_path: Path):
    """Dữ liệu đã nằm trên đĩa ngay sau mỗi lệnh write() (đọc file khi writer còn mở)."""
    sub_file = tmp_path / "sub_live.jsonl"
    log_dir = tmp_path / "logs_live"

    with SubmissionWriter(sub_file, log_dir) as writer:
        writer.write("q_live_1", {"type": "boolean", "answer": True})

        # Đọc trực tiếp từ đĩa trong khi context manager vẫn đang mở
        with open(sub_file, "r", encoding="utf-8") as f:
            live_lines = f.readlines()
        assert len(live_lines) == 1
        assert "q_live_1" in live_lines[0]

        writer.write("q_live_2", {"type": "boolean", "answer": False})

        with open(sub_file, "r", encoding="utf-8") as f:
            live_lines2 = f.readlines()
        assert len(live_lines2) == 2


def test_submission_writer_exception_preserves_lines(tmp_path: Path):
    """Khi gặp Exception giữa chừng, các dòng đã ghi trước đó không bị mất."""
    sub_file = tmp_path / "sub_crash.jsonl"
    log_dir = tmp_path / "logs_crash"

    try:
        with SubmissionWriter(sub_file, log_dir) as writer:
            writer.write("q_01", {"type": "number", "answer": 10})
            writer.write("q_02", {"type": "number", "answer": 20})
            raise RuntimeError("Cố tình làm gián đoạn chương trình!")
    except RuntimeError:
        pass

    assert sub_file.exists()
    lines = [l for l in sub_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    assert "q_01" in lines[0]
    assert "q_02" in lines[1]


def test_submission_writer_log_file(tmp_path: Path):
    """Log file tồn tại và có đủ trường tối thiểu."""
    sub_file = tmp_path / "sub.jsonl"
    log_dir = tmp_path / "logs"

    with SubmissionWriter(sub_file, log_dir) as writer:
        writer.write(
            "q_test_log",
            {"type": "number", "answer": 42},
            code="x = 42\nFINAL_RESULT = x",
            raw_result=42,
            error=None,
            elapsed_ms=125,
        )

    log_file = log_dir / "q_test_log.json"
    assert log_file.exists()

    log_data = json.loads(log_file.read_text(encoding="utf-8"))
    assert log_data["question_id"] == "q_test_log"
    assert log_data["elapsed_ms"] == 125
    assert log_data["answer"]["answer"] == 42
    assert "x = 42" in log_data["code"]
    assert log_data["raw_result"] == 42


def test_question_id_sanitization_no_path_traversal(tmp_path: Path):
    """question_id có ký tự lạ ('../x') không được thoát khỏi log_dir."""
    sub_file = tmp_path / "sub.jsonl"
    log_dir = tmp_path / "logs"

    with SubmissionWriter(sub_file, log_dir) as writer:
        writer.write("../../etc_passwd", {"type": "abstain"})
        writer.write("../x", {"type": "abstain"})

    # Tất cả file log phải nằm bên trong log_dir, không nằm ở tmp_path
    log_files = list(log_dir.iterdir())
    assert len(log_files) == 2
    for f in log_files:
        assert f.parent.resolve() == log_dir.resolve()
        assert not f.name.startswith("..")


# ===========================================================================
# 3. Test validate_submission
# ===========================================================================

@pytest.fixture
def dummy_questions_file(tmp_path: Path) -> Path:
    q_file = tmp_path / "questions.jsonl"
    items = [
        {"id": "q_01", "question": "Hỏi câu 1"},
        {"id": "q_02", "question": "Hỏi câu 2"},
        {"id": "q_03", "question": "Hỏi câu 3"},
    ]
    with open(q_file, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    return q_file


def test_validate_valid_file(tmp_path: Path, dummy_questions_file: Path):
    """File hợp lệ 100% trả về danh sách rỗng []."""
    sub_file = tmp_path / "valid_submission.jsonl"
    items = [
        {"id": "q_01", "type": "number", "answer": 123},
        {"id": "q_02", "type": "string", "answer": "Bia Tiger"},
        {"id": "q_03", "type": "abstain", "answer": None},
    ]
    with open(sub_file, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    errors = validate_submission(sub_file, dummy_questions_file)
    assert errors == []


def test_validate_broken_json(tmp_path: Path, dummy_questions_file: Path):
    """Bắt được dòng hỏng cú pháp JSON."""
    sub_file = tmp_path / "broken_json.jsonl"
    sub_file.write_text("INVALID JSON LINE\n", encoding="utf-8")

    errors = validate_submission(sub_file, dummy_questions_file)
    assert any("Lỗi cú pháp JSON" in e for e in errors)


def test_validate_invalid_type(tmp_path: Path, dummy_questions_file: Path):
    """Bắt được type không thuộc danh sách hợp lệ."""
    sub_file = tmp_path / "bad_type.jsonl"
    items = [
        {"id": "q_01", "type": "unknown_type", "answer": 123},
        {"id": "q_02", "type": "number", "answer": 123},
        {"id": "q_03", "type": "abstain", "answer": None},
    ]
    with open(sub_file, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    errors = validate_submission(sub_file, dummy_questions_file)
    assert any("type 'unknown_type' không hợp lệ" in e for e in errors)


def test_validate_type_mismatch(tmp_path: Path, dummy_questions_file: Path):
    """Bắt được kiểu của answer không khớp với type."""
    sub_file = tmp_path / "mismatch.jsonl"
    items = [
        {"id": "q_01", "type": "number", "answer": "không phải số"},  # lỗi number
        {"id": "q_02", "type": "boolean", "answer": "true"},          # lỗi boolean không phải bool
        {"id": "q_03", "type": "table", "answer": [1, 2, 3]},          # lỗi table thiếu columns/rows
    ]
    with open(sub_file, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    errors = validate_submission(sub_file, dummy_questions_file)
    assert any("type='number' nhưng answer không phải số" in e for e in errors)
    assert any("type='boolean' nhưng answer không phải bool" in e for e in errors)
    assert any("type='table' nhưng answer thiếu 'columns' hoặc 'rows'" in e for e in errors)


def test_validate_duplicate_and_missing_and_unknown_ids(tmp_path: Path, dummy_questions_file: Path):
    """Bắt được trùng id, thiếu id và id lạ ngoài questions."""
    sub_file = tmp_path / "id_issues.jsonl"
    items = [
        {"id": "q_01", "type": "number", "answer": 1},
        {"id": "q_01", "type": "number", "answer": 2},          # Trùng id
        {"id": "q_stranger", "type": "string", "answer": "Lạ"},  # id lạ ngoài questions
        # Thiếu q_02, q_03
    ]
    with open(sub_file, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    errors = validate_submission(sub_file, dummy_questions_file)
    assert any("Trùng lặp id 'q_01'" in e for e in errors)
    assert any("không tồn tại trong questions.jsonl (id lạ)" in e for e in errors)
    assert any("Thiếu 2/3 câu hỏi" in e for e in errors)

