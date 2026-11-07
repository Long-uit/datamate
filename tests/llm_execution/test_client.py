"""
Tệp kiểm thử: tests/llm_execution/test_client.py
Mục đích: Kiểm thử các chức năng kiểm tra cú pháp (AST), bóc tách mã nguồn và cơ chế
          tự sửa lỗi (Self-Correction Loop) trong module src/datamate/llm_execution/client.py.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Đảm bảo console Windows hiển thị đúng tiếng Việt có dấu
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from datamate.llm_execution.client import (
    validate_code,
    extract_python_code,
    cut_after_first_solution,
    LLMClient,
)


class TestLLMClient(unittest.TestCase):
    """Bộ kiểm thử cho module client.py (Qwen2.5-Coder-3B)."""

    # --------------------------------------------------------------------------
    # Tiêu chí 1: Kiểm tra tính hợp lệ của mã nguồn (AST Validation)
    # --------------------------------------------------------------------------
    def test_validate_code_valid(self):
        """Mã Python chuẩn với hàm solution(data) và lệnh return hợp lệ."""
        code = """
import pandas as pd

def solution(data):
    df = data.get("DonHang")
    if df is None:
        return "unanswerable"
    return int(df["Thành tiền"].sum())
"""
        is_valid, error = validate_code(code)
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_code_syntax_error(self):
        """Phát hiện lỗi cú pháp SyntaxError."""
        code = """
def solution(data):
    for x in data:
        if x == 1
            return 10
"""
        is_valid, error = validate_code(code)
        self.assertFalse(is_valid)
        self.assertIn("SyntaxError", str(error))

    def test_validate_code_missing_function(self):
        """Phát hiện trường hợp thiếu hàm solution."""
        code = """
import pandas as pd
total = 100
print(total)
"""
        is_valid, error = validate_code(code)
        self.assertFalse(is_valid)
        self.assertIn("def solution(data):", str(error))

    def test_validate_code_missing_args(self):
        """Phát hiện trường hợp hàm solution không nhận tham số."""
        code = """
def solution():
    return 42
"""
        is_valid, error = validate_code(code)
        self.assertFalse(is_valid)
        self.assertIn("ít nhất 1 tham số", str(error))

    def test_validate_code_varargs_and_async(self):
        """Hỗ trợ hàm nhận *args hoặc định nghĩa dạng async def."""
        code_varargs = "def solution(*args):\n    return 42"
        valid_1, err_1 = validate_code(code_varargs)
        self.assertTrue(valid_1)
        self.assertIsNone(err_1)

        code_async = "async def solution(data):\n    return 42"
        valid_2, err_2 = validate_code(code_async)
        self.assertTrue(valid_2)
        self.assertIsNone(err_2)

    def test_validate_code_eval_exec_disallowed(self):
        """Phát hiện lệnh gọi eval/exec bị hạn chế."""
        code_eval = "def solution(data):\n    eval('2+2')\n    return 4"
        valid_eval, err_eval = validate_code(code_eval)
        self.assertFalse(valid_eval)
        self.assertIn("bị hạn chế", str(err_eval))

    def test_validate_code_missing_return(self):
        """Phát hiện trường hợp hàm solution không có lệnh return."""
        code = """
def solution(data):
    total = 100
    print(total)
"""
        is_valid, error = validate_code(code)
        self.assertFalse(is_valid)
        self.assertIn("không chứa lệnh 'return'", str(error))

    def test_validate_code_disallowed_modules(self):
        """Phát hiện lệnh gọi bị hạn chế vì lý do an toàn."""
        code = """
import os
def solution(data):
    os.system("ls")
    return "unanswerable"
"""
        is_valid, error = validate_code(code)
        self.assertFalse(is_valid)
        self.assertIn("bị hạn chế", str(error))

    # --------------------------------------------------------------------------
    # Tiêu chí 2: Bóc tách mã nguồn sạch (Code Extraction)
    # --------------------------------------------------------------------------
    def test_extract_code_markdown_python(self):
        """Trích xuất khối code trong cặp ```python ... ```."""
        raw_text = """Dưới đây là lời giải bài toán:
```python
def solution(data):
    return 100
```
Chúc bạn thành công!"""
        code = extract_python_code(raw_text)
        self.assertEqual(code, "def solution(data):\n    return 100")

    def test_extract_code_generic_markdown(self):
        """Trích xuất khối code trong cặp ``` ... ``` không có chữ python."""
        raw_text = """```
def solution(data):
    return 200
```"""
        code = extract_python_code(raw_text)
        self.assertEqual(code, "def solution(data):\n    return 200")

    def test_extract_code_plain_text(self):
        """Trích xuất khi mô hình viết trực tiếp def solution không dùng markdown."""
        raw_text = """Chào bạn, giải pháp:
def solution(data):
    return 300"""
        code = extract_python_code(raw_text)
        self.assertEqual(code, "def solution(data):\n    return 300")

    def test_extract_code_unclosed_markdown(self):
        """Trích xuất khối code trong trường hợp token bị ngắt chưa kịp đóng backtick."""
        raw_text = "Dưới đây là hàm:\n```python\ndef solution(data):\n    return 99"
        code = extract_python_code(raw_text)
        self.assertEqual(code, "def solution(data):\n    return 99")

    def test_cut_after_first_solution_duplicates(self):
        """Cắt bỏ hàm solution thứ 2 nếu mô hình bị lặp lại code."""
        code_with_dups = """def solution(data):
    return 1

def solution(data):
    return 2
"""
        clean = cut_after_first_solution(code_with_dups)
        self.assertEqual(clean.strip(), "def solution(data):\n    return 1")
        self.assertNotIn("return 2", clean)

    # --------------------------------------------------------------------------
    # Tiêu chí 3: Cơ chế tự sửa lỗi ngắn (Self-Correction Loop)
    # --------------------------------------------------------------------------
    def test_generate_code_retry_success(self):
        """Mô phỏng trường hợp lần 1 sinh lỗi cú pháp, lần 2 tự sửa thành công."""
        client = LLMClient(auto_load=False)
        client.is_loaded = True

        responses = [
            "```python\ndef solution(:\n    pass\n```",
            "```python\ndef solution(data):\n    return 42\n```"
        ]
        client._generate_raw = MagicMock(side_effect=responses)

        code = client.generate_code("Hãy viết hàm tính tổng", max_retries=1)

        self.assertIn("return 42", code)
        self.assertEqual(client._generate_raw.call_count, 2)

    def test_generate_code_retry_exhausted_fallback(self):
        """Mô phỏng trường hợp cả 2 lần đều lỗi cú pháp -> trả về fallback unanswerable."""
        client = LLMClient(auto_load=False)
        client.is_loaded = True

        bad_response = "```python\ndef solution(:\n    pass\n```"
        client._generate_raw = MagicMock(return_value=bad_response)

        code = client.generate_code("Hãy viết hàm tính tổng", max_retries=1)

        self.assertIn("def solution(data):", code)
        self.assertTrue("return None" in code or 'return "unanswerable"' in code)
        self.assertEqual(client._generate_raw.call_count, 2)


if __name__ == "__main__":
    unittest.main()

