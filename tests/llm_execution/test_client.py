"""
Tệp kiểm thử: tests/llm_execution/test_client.py
Mục đích: Kiểm thử các chức năng kiểm tra cú pháp (AST), bóc tách mã nguồn và cơ chế
          tự sửa lỗi (Self-Correction Loop) trong module src/datamate/llm_execution/client.py.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    @patch("datamate.llm_execution.client.TORCH_AVAILABLE", True)
    @patch("datamate.llm_execution.client.BitsAndBytesConfig")
    @patch("datamate.llm_execution.client.torch")
    @patch("datamate.llm_execution.client.AutoTokenizer")
    @patch("datamate.llm_execution.client.AutoModelForCausalLM")
    def test_load_model_fallback_on_4bit_error(self, mock_auto_model, mock_tokenizer, mock_torch, mock_bnb):
        """Kiểm tra fallback khi nạp 4-bit bị lỗi (WinError 4551/DLL) sang unquantized CUDA."""
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.is_bf16_supported.return_value = True
        mock_torch.bfloat16 = "bfloat16"

        mock_tok_inst = MagicMock()
        mock_tok_inst.pad_token = None
        mock_tok_inst.eos_token = "<eos>"
        mock_tokenizer.from_pretrained.return_value = mock_tok_inst

        # Lần 1 nạp 4-bit lỗi (DLL bị chặn), lần 2 nạp unquantized thành công
        mock_model_inst = MagicMock()
        mock_auto_model.from_pretrained.side_effect = [
            OSError("[WinError 4551] An Application Control policy has blocked this file"),
            mock_model_inst,
        ]

        client = LLMClient(auto_load=False)
        client.load_model()

        self.assertTrue(client.is_loaded)
        self.assertEqual(mock_auto_model.from_pretrained.call_count, 2)
        # Lần 2 phải dùng device_map={"": 0} và torch_dtype=bfloat16, không có quantization_config
        second_call_kwargs = mock_auto_model.from_pretrained.call_args_list[1][1]
        self.assertNotIn("quantization_config", second_call_kwargs)
        self.assertEqual(second_call_kwargs["device_map"], {"": 0})
        self.assertEqual(second_call_kwargs["torch_dtype"], "bfloat16")

    def test_generate_code_records_raw_text_for_initial_and_retry(self):
        """Kiểm tra last_generation_meta lưu đủ raw_text, lỗi AST và telemetry cho cả lần đầu & retry."""
        client = LLMClient(auto_load=False)
        client.is_loaded = True

        raw_initial = "def solution(:\n    pass\n```"
        raw_retry = "```python\ndef solution(data):\n    return 42\n```"

        def fake_generate_raw(messages, max_new_tokens=1536):
            call_idx = len(recorded_calls)
            recorded_calls.append(messages)
            if call_idx == 0:
                client._last_raw_meta = {
                    "backend": "transformers",
                    "raw_text": raw_initial,
                    "prompt_tokens": 3700,
                    "prompt_tokens_used": 3584,
                    "max_safe_input_tokens": 3584,
                    "truncated": True,
                    "truncation_reason": "max_safe_input_tokens",
                    "generated_tokens": 120,
                    "max_new_tokens_limit": max_new_tokens,
                    "finish_reason": "stop",
                    "stop_detail": "eos_token",
                }
                return raw_initial
            client._last_raw_meta = {
                "backend": "transformers",
                "raw_text": raw_retry,
                "prompt_tokens": 900,
                "prompt_tokens_used": 900,
                "max_safe_input_tokens": 3584,
                "truncated": False,
                "truncation_reason": None,
                "generated_tokens": 25,
                "max_new_tokens_limit": max_new_tokens,
                "finish_reason": "stop",
                "stop_detail": "stopping_criteria",
            }
            return raw_retry

        recorded_calls = []
        client._generate_raw = fake_generate_raw

        code = client.generate_code("Hãy tính tổng", system_prompt="sys", max_new_tokens=1536, max_retries=1)

        self.assertIn("return 42", code)
        meta = client.last_generation_meta
        self.assertTrue(meta["final_ast_valid"])
        self.assertFalse(meta["used_fallback_return_none"])
        self.assertEqual(meta["total_attempts"], 2)

        init_att, retry_att = meta["attempts"]
        self.assertEqual(init_att["role"], "initial")
        self.assertEqual(init_att["raw_text"], raw_initial)
        self.assertFalse(init_att["ast_valid"])
        self.assertIn("SyntaxError", str(init_att["ast_error"]))
        self.assertEqual(init_att["prompt_tokens"], 3700)
        self.assertEqual(init_att["prompt_tokens_used"], 3584)
        self.assertTrue(init_att["truncated"])
        self.assertEqual(init_att["generated_tokens"], 120)
        self.assertEqual(init_att["finish_reason"], "stop")

        self.assertEqual(retry_att["role"], "ast_retry")
        self.assertEqual(retry_att["raw_text"], raw_retry)
        self.assertTrue(retry_att["ast_valid"])
        self.assertFalse(retry_att["truncated"])
        self.assertEqual(retry_att["generated_tokens"], 25)
        self.assertEqual(retry_att["finish_reason"], "stop")

    @patch("datamate.llm_execution.client.StoppingCriteriaList", side_effect=lambda x: x)
    @patch("datamate.llm_execution.client.TORCH_AVAILABLE", True)
    def test_generate_raw_tracks_stop_length_and_truncation(self, _mock_sc):
        """Kiểm tra _generate_raw phân biệt đúng finish_reason='stop' vs 'length' và prompt truncation."""
        import torch

        client = LLMClient(auto_load=False)
        client.is_loaded = True
        client.backend = "transformers"

        class FakeBatch(dict):
            def __getattr__(self, name):
                return self[name]

            def __setattr__(self, name, val):
                self[name] = val

            def to(self, _dev):
                return self

        class FakeTokenizer:
            eos_token_id = 151645
            unk_token_id = None

            def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
                return "prompt"

            def convert_tokens_to_ids(self, tok):
                return 151645 if tok == "<|im_end|>" else -1

            def __call__(self, texts, return_tensors="pt"):
                return FakeBatch(
                    input_ids=torch.ones((1, 3700), dtype=torch.long),
                    attention_mask=torch.ones((1, 3700), dtype=torch.long),
                )

            def decode(self, ids, skip_special_tokens=True):
                return "def solution(data):\n    return 1\n```"

        class FakeModel:
            device = "cpu"
            config = MagicMock(eos_token_id=151645)
            generation_config = MagicMock(eos_token_id=[151645, 151643])

            def __init__(self, out_len, end_tok):
                self.out_len = out_len
                self.end_tok = end_tok

            def generate(self, input_ids, **kwargs):
                gen = torch.full((1, self.out_len), 100, dtype=torch.long)
                gen[0, -1] = self.end_tok
                return torch.cat([input_ids, gen], dim=1)

        client.tokenizer = FakeTokenizer()

        with patch.object(torch.cuda, "is_available", return_value=False):
            # Trường hợp 1: Đụng max_new_tokens=50 và không có EOS -> finish_reason="length", truncated=True
            client.model = FakeModel(out_len=50, end_tok=999)
            client._generate_raw([{"role": "user", "content": "hi"}], max_new_tokens=50)
            meta_len = dict(client._last_raw_meta)
            self.assertEqual(meta_len["prompt_tokens"], 3700)
            self.assertEqual(meta_len["prompt_tokens_used"], 3584)
            self.assertTrue(meta_len["truncated"])
            self.assertEqual(meta_len["generated_tokens"], 50)
            self.assertEqual(meta_len["finish_reason"], "length")
            self.assertEqual(meta_len["stop_detail"], "max_new_tokens")

            # Trường hợp 2: Sinh EOS ở cuối -> finish_reason="stop"
            client.model = FakeModel(out_len=20, end_tok=151645)
            client._generate_raw([{"role": "user", "content": "hi"}], max_new_tokens=50)
            meta_eos = dict(client._last_raw_meta)
            self.assertEqual(meta_eos["generated_tokens"], 20)
            self.assertEqual(meta_eos["finish_reason"], "stop")
            self.assertEqual(meta_eos["stop_detail"], "eos_token")

            # Trường hợp 3: Dừng sớm trước max_new_tokens nhưng không kết bằng EOS -> stopping_criteria
            client.model = FakeModel(out_len=18, end_tok=999)
            client._generate_raw([{"role": "user", "content": "hi"}], max_new_tokens=50)
            meta_sc = dict(client._last_raw_meta)
            self.assertEqual(meta_sc["generated_tokens"], 18)
            self.assertEqual(meta_sc["finish_reason"], "stop")
            self.assertEqual(meta_sc["stop_detail"], "stopping_criteria")


if __name__ == "__main__":
    unittest.main()

