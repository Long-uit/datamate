"""
tests/llm_execution/test_worker.py — Kiểm thử tự động độc lập 4 tệp cốt lõi và worker trong src/datamate/llm_execution.

Bao gồm:
1. client.py: Kiểm tra validate_code, extract_python_code, cut_after_first_solution, LLMClient cấu hình Qwen2.5-Coder-7B.
2. prompt.py: Kiểm tra classify_intent, prune_schema_by_intent, build_prompt, build_retry_prompt, resolve_temporal_context, retrieve_dynamic_few_shot.
3. sandbox.py: Kiểm tra clean_num, clean_date, PersistentWorker, thực thi RunResult, One-shot fallback.
4. worker.py: Kiểm tra serialization dữ liệu và luồng IPC qua subprocess.
5. Kiểm tra cấu trúc thư mục: Đảm bảo src/datamate/llm_execution CHỈ chứa đúng 4 file nêu trên.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent.parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import numpy as np
import pandas as pd


class TestLLMExecutionSuite(unittest.TestCase):
    """Kiểm tra toàn diện 4 tệp trong datamate.llm_execution."""

    # --------------------------------------------------------------------------
    # 1. client.py
    # --------------------------------------------------------------------------
    def test_01_client(self):
        from datamate.llm_execution.client import (
            cut_after_first_solution,
            extract_python_code,
            validate_code,
            LLMClient,
        )
        # Test validate_code
        ok, err = validate_code("def solution(data):\n    return 42\n")
        self.assertTrue(ok)
        self.assertIsNone(err)

        ok, err = validate_code("x = 10\n")
        self.assertFalse(ok)
        self.assertIn("solution", err or "")

        # Test extract_python_code
        raw = "```python\ndef solution(data):\n    return 'OK'\n```"
        self.assertEqual(extract_python_code(raw), "def solution(data):\n    return 'OK'")

        # Test cut_after_first_solution
        dup = "def solution(data):\n    return 1\ndef solution(data):\n    return 2"
        self.assertEqual(cut_after_first_solution(dup).strip(), "def solution(data):\n    return 1")

        # Test default model configuration is Qwen2.5-Coder-7B
        client = LLMClient(auto_load=False)
        self.assertIn("7B", client.model_id)
        self.assertEqual(client.model_id, "Qwen/Qwen2.5-Coder-7B-Instruct")

    # --------------------------------------------------------------------------
    # 2. prompt.py
    # --------------------------------------------------------------------------
    def test_02_prompt(self):
        from datamate.llm_execution.prompt import (
            build_prompt,
            build_retry_prompt,
            classify_intent,
            prune_schema_by_intent,
            resolve_temporal_context,
            retrieve_dynamic_few_shot,
            select_few_shots,
            EXEMPLAR_BANK,
        )
        # classify_intent
        self.assertEqual(classify_intent("Tổng doanh thu tháng này là bao nhiêu?"), "aggregation")
        self.assertEqual(classify_intent("Sản phẩm nào bán chạy nhất dịp Tết?"), "ranking_topk")
        self.assertEqual(classify_intent("Hapacol còn bao nhiêu hộp và viên lẻ?"), "inventory_unit_conversion")

        # prune_schema_by_intent
        schema = (
            "- Bảng 'HoaDon': [Mã đơn, Ngày lập, Tổng tiền]\n"
            "- Bảng 'BangGia': [Mã hàng, Giá bán]\n"
            "- Bảng 'TonKho': [Mã hàng, Số lượng tồn]\n"
        )
        pruned = prune_schema_by_intent(schema, "aggregation", "Doanh thu tháng 5")
        self.assertIn("HoaDon", pruned)

        # resolve_temporal_context
        t_res = resolve_temporal_context("Dịp Tết 2026", as_of_date_str="2026-06-28")
        self.assertEqual(t_res["start_date"], "2026-02-10")
        self.assertEqual(t_res["end_date"], "2026-02-26")

        # retrieve_dynamic_few_shot
        few_shot = retrieve_dynamic_few_shot("Doanh thu tháng này", "aggregation")
        self.assertIn("def solution(data):", few_shot)
        self.assertTrue(len(EXEMPLAR_BANK) > 0)

        # build_prompt
        prompt_str = build_prompt(
            schema_str=schema,
            as_of_date="2026-06-28",
            question="Dịp Tết 2026, sản phẩm nào bán chạy nhất?",
        )
        self.assertIn("def solution(data):", prompt_str)
        self.assertIn("Dịp Tết 2026", prompt_str)

        # build_retry_prompt kèm missed_mentions (Turn 2 grounding feedback)
        sys_retry, usr_retry = build_retry_prompt(
            question="Tổng doanh thu áo thun",
            failed_code="def solution(data):\n    return data['wrong_col']",
            error_message="KeyError: 'wrong_col'",
            schema_str=schema,
            as_of_date="2026-06-28",
            missed_mentions=["áo thun"],
        )
        self.assertIn("KeyError", usr_retry)
        self.assertIn("wrong_col", usr_retry)
        self.assertIn("áo thun", usr_retry)

    # --------------------------------------------------------------------------
    # 3. sandbox.py (Bao gồm clean_num, clean_date & thực thi Sandbox)
    # --------------------------------------------------------------------------
    def test_03_sandbox(self):
        from datamate.llm_execution.sandbox import (
            clean_date,
            clean_num,
            RunResult,
            close_sandbox_worker,
            run_code,
        )
        # Test clean_num
        self.assertEqual(clean_num("1.500.000 đ"), 1500000.0)
        self.assertEqual(clean_num("100k"), 100000.0)
        self.assertEqual(clean_num("(50.000)"), -50000.0)
        self.assertEqual(clean_num(None), 0.0)

        # Test clean_date
        dt = clean_date("2026-05-25")
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 5)
        self.assertEqual(dt.day, 25)

        # Test execution
        with tempfile.TemporaryDirectory() as tmp_dir:
            biz = Path(tmp_dir) / "shop1"
            biz.mkdir()
            (biz / "README.md").write_text("# Shop", encoding="utf-8")
            (biz / "data.csv").write_text("ID,Name,Amount\n1,A,100\n2,B,200\n", encoding="utf-8")

            # One-shot and persistent execution
            code = """
def solution(data):
    df = list(data.values())[0]
    return int(clean_num(df['Amount']).sum())
"""
            res = run_code(code, biz, timeout_s=10, use_persistent=True)
            self.assertTrue(res.ok)
            self.assertEqual(res.final_result, 300)

            # Error handling
            err_code = "FINAL_RESULT = 1 / 0"
            res_err = run_code(err_code, biz, timeout_s=10)
            self.assertFalse(res_err.ok)
            self.assertIn("ZeroDivisionError", res_err.error or "")

            close_sandbox_worker()

    # --------------------------------------------------------------------------
    # 4. worker.py
    # --------------------------------------------------------------------------
    def test_04_worker(self):
        from datamate.llm_execution.worker import _to_json_serializable, SmartDataDict, execute_code_in_env
        self.assertEqual(_to_json_serializable(np.int64(99)), 99)
        self.assertAlmostEqual(_to_json_serializable(np.float64(1.23)), 1.23, places=2)
        self.assertIsNone(_to_json_serializable(float("nan")))
        self.assertIsNone(_to_json_serializable(pd.NA))
        self.assertIn("2026-05-25", _to_json_serializable(pd.Timestamp("2026-05-25")))

        # Test SmartDataDict: không phân biệt hoa thường, dấu tiếng Việt, đuôi .csv
        dummy_df = pd.DataFrame({"col": [1, 2, 3]})
        s_dict = SmartDataDict({"HoaDonBanHang.csv": dummy_df, "Hàng Hóa": dummy_df})
        self.assertIn("HoaDonBanHang.csv", s_dict)
        self.assertIs(s_dict["hoadonbanhang"], dummy_df)
        self.assertIs(s_dict["Hóa Đơn Bán Hàng"], dummy_df)
        self.assertIs(s_dict.get("hang_hoa"), dummy_df)
        self.assertIs(s_dict.get("Hang Hoa"), dummy_df)

        # Test execute_code_in_env có sẵn re, math, datetime, pct
        code = """
def solution(data):
    # Dùng re, math, pct mà không cần import
    s = re.sub(r'[^0-9]', '', 'ABC 123 XYZ')
    val = math.ceil(float(s) / 10.0)
    p = pct(10, 100)
    return int(val + p)
"""
        from datamate.llm_execution.sandbox import clean_num, clean_date
        res = execute_code_in_env(
            code_str=code,
            data_dict={"sample": dummy_df},
            business=None,
            con=None,
            pd=pd,
            np=np,
            apply_tie_breaker=lambda x, **kw: x,
            filter_future_data=lambda x, **kw: x,
            clean_num=clean_num,
            clean_date=clean_date,
            DataNotFoundError=Exception,
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["final_result"], 13 + 10)  # ceil(12.3) = 13 + 10.0 = 23

    # --------------------------------------------------------------------------
    # 5. Kiểm tra tính gọn nhẹ cấu trúc: CHỈ ĐÚNG 4 FILE TRONG llm_execution
    # --------------------------------------------------------------------------
    def test_05_strict_four_files_architecture(self):
        llm_dir = Path(__file__).resolve().parent.parent.parent / "src" / "datamate" / "llm_execution"
        py_files = sorted([f.name for f in llm_dir.glob("*.py")])
        expected_files = ["client.py", "prompt.py", "sandbox.py", "worker.py"]
        self.assertEqual(py_files, expected_files, f"llm_execution phải chứa chính xác 4 file: {expected_files}, nhưng thực tế có: {py_files}")

        all_files = sorted([f.name for f in llm_dir.iterdir() if f.is_file()])
        self.assertEqual(all_files, expected_files, f"llm_execution không được chứa thêm bất kỳ file thừa nào: {all_files}")


if __name__ == "__main__":
    unittest.main()
