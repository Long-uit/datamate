"""
Tệp kiểm thử: test_llm_client.py
Mục đích: Kiểm thử các chức năng kiểm tra cú pháp (AST), bóc tách mã nguồn và cơ chế
          tự sửa lỗi (Self-Correction Loop) trong module src/models/llm_client.py.

================================================================================
CÁC TIÊU CHÍ ĐÁNH GIÁ ĐẶT RA CHO MODULE LLM_CLIENT:
1. Kiểm tra tính hợp lệ của mã nguồn bằng AST (Code Validation):
   - Nhận diện chính xác mã Python hợp lệ có đầy đủ hàm `def solution(data)` và lệnh `return`.
   - Phát hiện chính xác lỗi cú pháp `SyntaxError` và chỉ rõ vị trí lỗi.
   - Phát hiện trường hợp thiếu hàm `solution` hoặc hàm không nhận tham số đầu vào.
   - Phát hiện trường hợp hàm `solution` không có lệnh `return`.
   - Phát hiện và từ chối các mã nguồn chứa lệnh gọi bị hạn chế (như `os.system`, `subprocess`).
2. Bóc tách và làm sạch mã nguồn (Code Extraction):
   - Trích xuất sạch sẽ mã nguồn khi mô hình đặt trong khối ```python ... ```.
   - Trích xuất được mã nguồn khi đặt trong khối ``` ... ``` không ghi chữ python.
   - Trích xuất được mã nguồn khi mô hình viết trực tiếp không dùng khối markdown.
   - Loại bỏ các khối hàm `def solution` bị sinh lặp lại ở phía sau bằng hàm cut_after_first_solution.
3. Cơ chế tự sửa lỗi ngắn (Self-Correction / Retry Logic):
   - Khi mã sinh ra lần đầu bị lỗi cú pháp, kích hoạt lượt thử lại với thông báo lỗi cụ thể.
   - Nếu lượt thử lại sinh ra mã hợp lệ, chấp nhận mã mới.
   - Nếu qua hết số lần thử lại mà mã vẫn lỗi, kích hoạt fallback an toàn trả về "unanswerable"
     để đảm bảo không làm sập tiến trình chạy của hệ thống.
4. Quản lý tài nguyên và độ trễ:
   - Cung cấp hàm theo dõi bộ nhớ GPU get_gpu_memory_stats và đo thời gian suy luận last_latency_ms.
================================================================================
"""

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

# Thêm thư mục src vào sys.path để import
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from models.llm_client import (
    validate_code,
    extract_python_code,
    cut_after_first_solution,
    LLMClient,
)


class TestLLMClient(unittest.TestCase):
    """Bộ kiểm thử cho module llm_client.py."""

    # --------------------------------------------------------------------------
    # Tiêu chí 1: Kiểm tra tính hợp lệ của mã nguồn (AST Validation)
    # --------------------------------------------------------------------------
    def test_validate_code_valid(self):
        """Mã Python chuẩn với hàm solution(data) và lệnh return hợp lệ."""
        criterion = "Chỉ tiêu 1.1: Chấp nhận mã Python hợp lệ có đầy đủ hàm solution(data) và lệnh return"
        try:
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
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_validate_code_syntax_error(self):
        """Phát hiện lỗi cú pháp SyntaxError."""
        criterion = "Chỉ tiêu 1.2: Phát hiện chính xác lỗi cú pháp SyntaxError và thông báo rõ dòng lỗi"
        try:
            code = """
def solution(data):
    for x in data:
        if x == 1
            return 10
"""
            is_valid, error = validate_code(code)
            self.assertFalse(is_valid)
            self.assertIn("SyntaxError", str(error))
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_validate_code_missing_function(self):
        """Phát hiện trường hợp thiếu hàm solution."""
        criterion = "Chỉ tiêu 1.3: Phát hiện lỗi khi mã nguồn thiếu định nghĩa hàm solution"
        try:
            code = """
import pandas as pd
total = 100
print(total)
"""
            is_valid, error = validate_code(code)
            self.assertFalse(is_valid)
            self.assertIn("def solution(data):", str(error))
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_validate_code_missing_args(self):
        """Phát hiện trường hợp hàm solution không nhận tham số."""
        criterion = "Chỉ tiêu 1.4: Phát hiện lỗi khi hàm solution không khai báo tham số đầu vào"
        try:
            code = """
def solution():
    return 42
"""
            is_valid, error = validate_code(code)
            self.assertFalse(is_valid)
            self.assertIn("ít nhất 1 tham số", str(error))
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_validate_code_varargs_and_async(self):
        """Hỗ trợ hàm nhận *args hoặc định nghĩa dạng async def."""
        criterion = "Chỉ tiêu 1.5: Hỗ trợ linh hoạt hàm solution nhận *args hoặc khai báo async def"
        try:
            code_varargs = "def solution(*args):\n    return 42"
            valid_1, err_1 = validate_code(code_varargs)
            self.assertTrue(valid_1)
            self.assertIsNone(err_1)

            code_async = "async def solution(data):\n    return 42"
            valid_2, err_2 = validate_code(code_async)
            self.assertTrue(valid_2)
            self.assertIsNone(err_2)
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_validate_code_eval_exec_disallowed(self):
        """Phát hiện lệnh gọi eval/exec bị hạn chế."""
        criterion = "Chỉ tiêu 1.6: Phát hiện và chặn các hàm nguy hiểm (eval, exec) vì lý do an toàn"
        try:
            code_eval = "def solution(data):\n    eval('2+2')\n    return 4"
            valid_eval, err_eval = validate_code(code_eval)
            self.assertFalse(valid_eval)
            self.assertIn("bị hạn chế", str(err_eval))
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_validate_code_missing_return(self):
        """Phát hiện trường hợp hàm solution không có lệnh return."""
        criterion = "Chỉ tiêu 1.7: Phát hiện lỗi khi hàm solution không có câu lệnh return"
        try:
            code = """
def solution(data):
    total = 100
    print(total)
"""
            is_valid, error = validate_code(code)
            self.assertFalse(is_valid)
            self.assertIn("không chứa lệnh 'return'", str(error))
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_validate_code_disallowed_modules(self):
        """Phát hiện lệnh gọi bị hạn chế vì lý do an toàn."""
        criterion = "Chỉ tiêu 1.8: Phát hiện và chặn các module hệ thống nguy hiểm (os.system, subprocess)"
        try:
            code = """
import os
def solution(data):
    os.system("ls")
    return "unanswerable"
"""
            is_valid, error = validate_code(code)
            self.assertFalse(is_valid)
            self.assertIn("bị hạn chế", str(error))
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    # --------------------------------------------------------------------------
    # Tiêu chí 2: Bóc tách mã nguồn sạch (Code Extraction)
    # --------------------------------------------------------------------------
    def test_extract_code_markdown_python(self):
        """Trích xuất khối code trong cặp ```python ... ```."""
        criterion = "Chỉ tiêu 2.1: Bóc tách chính xác khối mã Python nằm trong cặp markdown ```python ... ```"
        try:
            raw_text = """Dưới đây là lời giải bài toán:
```python
def solution(data):
    return 100
```
Chúc bạn thành công!"""
            code = extract_python_code(raw_text)
            self.assertEqual(code, "def solution(data):\n    return 100")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_extract_code_generic_markdown(self):
        """Trích xuất khối code trong cặp ``` ... ``` không có chữ python."""
        criterion = "Chỉ tiêu 2.2: Bóc tách chính xác khối mã nằm trong cặp markdown ``` ... ``` không có chữ python"
        try:
            raw_text = """```
def solution(data):
    return 200
```"""
            code = extract_python_code(raw_text)
            self.assertEqual(code, "def solution(data):\n    return 200")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_extract_code_plain_text(self):
        """Trích xuất khi mô hình viết trực tiếp def solution không dùng markdown."""
        criterion = "Chỉ tiêu 2.3: Bóc tách chính xác mã nguồn khi mô hình viết văn bản thô trực tiếp"
        try:
            raw_text = """Chào bạn, giải pháp:
def solution(data):
    return 300"""
            code = extract_python_code(raw_text)
            self.assertEqual(code, "def solution(data):\n    return 300")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_extract_code_unclosed_markdown(self):
        """Trích xuất khối code trong trường hợp token bị ngắt chưa kịp đóng backtick."""
        criterion = "Chỉ tiêu 2.4: Bóc tách được mã nguồn khi token bị ngắt chưa kịp đóng backtick"
        try:
            raw_text = "Dưới đây là hàm:\n```python\ndef solution(data):\n    return 99"
            code = extract_python_code(raw_text)
            self.assertEqual(code, "def solution(data):\n    return 99")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_cut_after_first_solution_duplicates(self):
        """Cắt bỏ hàm solution thứ 2 nếu mô hình bị lặp lại code."""
        criterion = "Chỉ tiêu 2.5: Cắt bỏ các khối hàm solution sinh lặp lại ở phía sau"
        try:
            code_with_dups = """def solution(data):
    return 1

def solution(data):
    return 2
"""
            clean = cut_after_first_solution(code_with_dups)
            self.assertEqual(clean.strip(), "def solution(data):\n    return 1")
            self.assertNotIn("return 2", clean)
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    # --------------------------------------------------------------------------
    # Tiêu chí 3: Cơ chế tự sửa lỗi ngắn (Self-Correction Loop)
    # --------------------------------------------------------------------------
    def test_generate_code_retry_success(self):
        """Mô phỏng trường hợp lần 1 sinh lỗi cú pháp, lần 2 tự sửa thành công."""
        criterion = "Chỉ tiêu 3.1: Tự sửa lỗi thành công sau 1 lượt retry khi mã lần đầu gặp lỗi cú pháp"
        try:
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
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_generate_code_retry_exhausted_fallback(self):
        """Mô phỏng trường hợp cả 2 lần đều lỗi cú pháp -> trả về fallback unanswerable."""
        criterion = "Chỉ tiêu 3.2: Kích hoạt fallback unanswerable an toàn khi hết số lượt retry mà mã vẫn lỗi"
        try:
            client = LLMClient(auto_load=False)
            client.is_loaded = True

            bad_response = "```python\ndef solution(:\n    pass\n```"
            client._generate_raw = MagicMock(return_value=bad_response)

            code = client.generate_code("Hãy viết hàm tính tổng", max_retries=1)

            self.assertIn("def solution(data):", code)
            self.assertIn('return "unanswerable"', code)
            self.assertEqual(client._generate_raw.call_count, 2)
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise


if __name__ == "__main__":
    print("=" * 80)
    print("BẮT ĐẦU KIỂM THỬ: tests/test_llm_client.py")
    print("=" * 80)
    unittest.main()
