"""
tests/output_abstention/test_submission.py — Unit tests cho module submission của DataMate (Phase 1 & Phase 4).
Tương thích hoàn toàn với unittest chuẩn của Python.
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from datamate.output_abstention.submission import (
    SubmissionWriter,
    make_abstain,
    to_answer,
    validate_submission,
)


class TestSubmission(unittest.TestCase):
    """Bộ kiểm thử cho module submission.py."""

    # ===========================================================================
    # 1. Test to_answer & make_abstain
    # ===========================================================================

    def test_to_answer_bool_before_int(self):
        """True / False phải suy luận thành boolean, KHÔNG được thành number."""
        ans_true = to_answer(True)
        self.assertEqual(ans_true["type"], "boolean")
        self.assertIs(ans_true["answer"], True)

        ans_false = to_answer(False)
        self.assertEqual(ans_false["type"], "boolean")
        self.assertIs(ans_false["answer"], False)

        ans_np_bool = to_answer(np.bool_(True))
        self.assertEqual(ans_np_bool["type"], "boolean")
        self.assertIs(ans_np_bool["answer"], True)

    def test_to_answer_int_and_float(self):
        """int và float được chuyển thành number."""
        ans_int = to_answer(123456)
        self.assertEqual(ans_int["type"], "number")
        self.assertEqual(ans_int["answer"], 123456)

        ans_float = to_answer(99.5)
        self.assertEqual(ans_float["type"], "number")
        self.assertEqual(ans_float["answer"], 99.5)

    def test_to_answer_str_and_list(self):
        """Chuỗi thành string, danh sách thành list."""
        ans_str = to_answer("Cà phê sữa đá")
        self.assertEqual(ans_str["type"], "string")
        self.assertEqual(ans_str["answer"], "Cà phê sữa đá")

        ans_list = to_answer(["SP01", "SP02", 100])
        self.assertEqual(ans_list["type"], "list")
        self.assertEqual(ans_list["answer"], ["SP01", "SP02", 100])

    def test_to_answer_dict_with_type(self):
        """Dict có đúng 2 khóa type và answer được giữ nguyên cho normalizer."""
        custom = {"type": "date", "answer": "2025-05-20"}
        res = to_answer(custom)
        self.assertEqual(res, custom)

        custom_table = {
            "type": "table",
            "answer": {"columns": ["san_pham", "doanh_thu"], "rows": [["A", 100]]},
        }
        self.assertEqual(to_answer(custom_table), custom_table)

    def test_to_answer_none_and_strange_types(self):
        """None hoặc đối tượng không xác định -> abstain."""
        ans_none = to_answer(None)
        self.assertEqual(ans_none["type"], "abstain")

        ans_obj = to_answer(object())
        self.assertEqual(ans_obj["type"], "abstain")

        ans_dict_strange = to_answer({"invalid_key": 123})
        self.assertEqual(ans_dict_strange["type"], "abstain")

    def test_to_answer_nan_and_numpy_scalars(self):
        """NaN/NA chuyển thành abstain; numpy.int64/float64 chuyển thành int/float thuần."""
        ans_nan = to_answer(float("nan"))
        self.assertEqual(ans_nan["type"], "abstain")

        ans_np_nan = to_answer(np.nan)
        self.assertEqual(ans_np_nan["type"], "abstain")

        ans_pd_na = to_answer(pd.NA)
        self.assertEqual(ans_pd_na["type"], "abstain")

        ans_np_int = to_answer(np.int64(42))
        self.assertEqual(ans_np_int["type"], "number")
        self.assertEqual(ans_np_int["answer"], 42)
        self.assertIs(type(ans_np_int["answer"]), int)

        ans_np_float = to_answer(np.float64(3.14))
        self.assertEqual(ans_np_float["type"], "number")
        self.assertAlmostEqual(ans_np_float["answer"], 3.14, places=2)

    def test_make_abstain(self):
        """make_abstain trả về type abstain, có thể kèm reason."""
        a1 = make_abstain()
        self.assertEqual(a1["type"], "abstain")
        self.assertNotIn("reason", a1)

        a2 = make_abstain("Không đủ độ tin cậy")
        self.assertEqual(a2["type"], "abstain")
        self.assertEqual(a2["reason"], "Không đủ độ tin cậy")

    # ===========================================================================
    # 2. Test SubmissionWriter
    # ===========================================================================

    def test_submission_writer_basic(self):
        """File có đúng số dòng, parse được JSON, tiếng Việt không bị escape."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            sub_file = tmp_path / "sub.jsonl"
            log_dir = tmp_path / "logs"

            with SubmissionWriter(sub_file, log_dir) as writer:
                writer.write("q_01", {"type": "string", "answer": "Cà phê sữa đá"})
                writer.write("q_02", {"type": "number", "answer": 150000})

            self.assertTrue(sub_file.exists())
            content = sub_file.read_text(encoding="utf-8")
            lines = [line.strip() for line in content.splitlines() if line.strip()]

            self.assertEqual(len(lines), 2)
            self.assertIn("Cà phê sữa đá", content)

            item1 = json.loads(lines[0])
            self.assertEqual(item1["id"], "q_01")
            self.assertEqual(item1["type"], "string")
            self.assertEqual(item1["answer"], "Cà phê sữa đá")

            item2 = json.loads(lines[1])
            self.assertEqual(item2["id"], "q_02")
            self.assertEqual(item2["type"], "number")
            self.assertEqual(item2["answer"], 150000)

    def test_submission_writer_disk_persistence_while_open(self):
        """Dữ liệu đã nằm trên đĩa ngay sau mỗi lệnh write() (đọc file khi writer còn mở)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            sub_file = tmp_path / "sub_live.jsonl"
            log_dir = tmp_path / "logs_live"

            with SubmissionWriter(sub_file, log_dir) as writer:
                writer.write("q_live_1", {"type": "boolean", "answer": True})

                with open(sub_file, "r", encoding="utf-8") as f:
                    live_lines = f.readlines()
                self.assertEqual(len(live_lines), 1)
                self.assertIn("q_live_1", live_lines[0])

                writer.write("q_live_2", {"type": "boolean", "answer": False})

                with open(sub_file, "r", encoding="utf-8") as f:
                    live_lines2 = f.readlines()
                self.assertEqual(len(live_lines2), 2)

    def test_submission_writer_exception_preserves_lines(self):
        """Khi gặp Exception giữa chừng, các dòng đã ghi trước đó không bị mất."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            sub_file = tmp_path / "sub_crash.jsonl"
            log_dir = tmp_path / "logs_crash"

            try:
                with SubmissionWriter(sub_file, log_dir) as writer:
                    writer.write("q_01", {"type": "number", "answer": 10})
                    writer.write("q_02", {"type": "number", "answer": 20})
                    raise RuntimeError("Cố tình làm gián đoạn chương trình!")
            except RuntimeError:
                pass

            self.assertTrue(sub_file.exists())
            lines = [l for l in sub_file.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(lines), 2)
            self.assertIn("q_01", lines[0])
            self.assertIn("q_02", lines[1])

    def test_submission_writer_log_file(self):
        """Log file tồn tại và có đủ trường tối thiểu."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
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
            self.assertTrue(log_file.exists())

            log_data = json.loads(log_file.read_text(encoding="utf-8"))
            self.assertEqual(log_data["question_id"], "q_test_log")
            self.assertEqual(log_data["elapsed_ms"], 125)
            self.assertEqual(log_data["answer"]["answer"], 42)
            self.assertIn("x = 42", log_data["code"])
            self.assertEqual(log_data["raw_result"], 42)

    def test_question_id_sanitization_no_path_traversal(self):
        """question_id có ký tự lạ ('../x') không được thoát khỏi log_dir."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            sub_file = tmp_path / "sub.jsonl"
            log_dir = tmp_path / "logs"

            with SubmissionWriter(sub_file, log_dir) as writer:
                writer.write("../../etc_passwd", {"type": "abstain"})
                writer.write("../x", {"type": "abstain"})

            log_files = list(log_dir.iterdir())
            self.assertEqual(len(log_files), 2)
            for f in log_files:
                self.assertEqual(f.parent.resolve(), log_dir.resolve())
                self.assertFalse(f.name.startswith(".."))

    # ===========================================================================
    # 3. Test validate_submission
    # ===========================================================================

    def test_validate_valid_file(self):
        """File hợp lệ 100% trả về danh sách rỗng []."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            q_file = tmp_path / "questions.jsonl"
            q_items = [
                {"id": "q_01", "question": "Hỏi câu 1"},
                {"id": "q_02", "question": "Hỏi câu 2"},
                {"id": "q_03", "question": "Hỏi câu 3"},
            ]
            q_file.write_text("\n".join(json.dumps(x) for x in q_items), encoding="utf-8")

            sub_file = tmp_path / "valid_submission.jsonl"
            items = [
                {"id": "q_01", "type": "number", "answer": 123},
                {"id": "q_02", "type": "string", "answer": "Bia Tiger"},
                {"id": "q_03", "type": "abstain", "answer": None},
            ]
            sub_file.write_text("\n".join(json.dumps(x) for x in items), encoding="utf-8")

            errors = validate_submission(sub_file, q_file)
            self.assertEqual(errors, [])

    def test_validate_broken_json(self):
        """Bắt được dòng hỏng cú pháp JSON."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            q_file = tmp_path / "questions.jsonl"
            q_file.write_text(json.dumps({"id": "q_01", "question": "Hỏi 1"}), encoding="utf-8")

            sub_file = tmp_path / "broken_json.jsonl"
            sub_file.write_text("INVALID JSON LINE\n", encoding="utf-8")

            errors = validate_submission(sub_file, q_file)
            self.assertTrue(any("Lỗi cú pháp JSON" in e for e in errors))

    def test_validate_invalid_type(self):
        """Bắt được type không thuộc danh sách hợp lệ."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            q_file = tmp_path / "questions.jsonl"
            q_items = [
                {"id": "q_01", "question": "Hỏi 1"},
                {"id": "q_02", "question": "Hỏi 2"},
                {"id": "q_03", "question": "Hỏi 3"},
            ]
            q_file.write_text("\n".join(json.dumps(x) for x in q_items), encoding="utf-8")

            sub_file = tmp_path / "bad_type.jsonl"
            items = [
                {"id": "q_01", "type": "unknown_type", "answer": 123},
                {"id": "q_02", "type": "number", "answer": 123},
                {"id": "q_03", "type": "abstain", "answer": None},
            ]
            sub_file.write_text("\n".join(json.dumps(x) for x in items), encoding="utf-8")

            errors = validate_submission(sub_file, q_file)
            self.assertTrue(any("type 'unknown_type' không hợp lệ" in e for e in errors))

    def test_validate_type_mismatch(self):
        """Bắt được kiểu của answer không khớp với type."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            q_file = tmp_path / "questions.jsonl"
            q_items = [
                {"id": "q_01", "question": "Hỏi 1"},
                {"id": "q_02", "question": "Hỏi 2"},
                {"id": "q_03", "question": "Hỏi 3"},
            ]
            q_file.write_text("\n".join(json.dumps(x) for x in q_items), encoding="utf-8")

            sub_file = tmp_path / "mismatch.jsonl"
            items = [
                {"id": "q_01", "type": "number", "answer": "không phải số"},
                {"id": "q_02", "type": "boolean", "answer": "true"},
                {"id": "q_03", "type": "table", "answer": [1, 2, 3]},
            ]
            sub_file.write_text("\n".join(json.dumps(x) for x in items), encoding="utf-8")

            errors = validate_submission(sub_file, q_file)
            self.assertTrue(any("type='number' nhưng answer không phải số" in e for e in errors))
            self.assertTrue(any("type='boolean' nhưng answer không phải bool" in e for e in errors))
            self.assertTrue(any("type='table' nhưng answer thiếu 'columns' hoặc 'rows'" in e for e in errors))

    def test_validate_duplicate_and_missing_and_unknown_ids(self):
        """Bắt được trùng id, thiếu id và id lạ ngoài questions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            q_file = tmp_path / "questions.jsonl"
            q_items = [
                {"id": "q_01", "question": "Hỏi 1"},
                {"id": "q_02", "question": "Hỏi 2"},
                {"id": "q_03", "question": "Hỏi 3"},
            ]
            q_file.write_text("\n".join(json.dumps(x) for x in q_items), encoding="utf-8")

            sub_file = tmp_path / "id_issues.jsonl"
            items = [
                {"id": "q_01", "type": "number", "answer": 1},
                {"id": "q_01", "type": "number", "answer": 2},
                {"id": "q_stranger", "type": "string", "answer": "Lạ"},
            ]
            sub_file.write_text("\n".join(json.dumps(x) for x in items), encoding="utf-8")

            errors = validate_submission(sub_file, q_file)
            self.assertTrue(any("Trùng lặp id 'q_01'" in e for e in errors))
            self.assertTrue(any("không tồn tại trong questions.jsonl (id lạ)" in e for e in errors))
            self.assertTrue(any("Thiếu 2/3 câu hỏi" in e for e in errors))


if __name__ == "__main__":
    unittest.main()

