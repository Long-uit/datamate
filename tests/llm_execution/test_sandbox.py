"""
tests/llm_execution/test_sandbox.py — Unit tests cho execution runner và persistent worker.
Tương thích hoàn toàn với unittest chuẩn của Python.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

from datamate.llm_execution.sandbox import (
    RunResult,
    close_sandbox_worker,
    run_code,
)


class TestSandboxRunner(unittest.TestCase):
    """Kiểm thử Sandbox và Persistent Worker."""

    @classmethod
    def setUpClass(cls):
        cls.tmp_dir_obj = tempfile.TemporaryDirectory()
        cls.dummy_biz = Path(cls.tmp_dir_obj.name) / "dummy_shop"
        cls.dummy_biz.mkdir()
        (cls.dummy_biz / "README.md").write_text("# Dummy Shop\nMo ta cua hang.", encoding="utf-8")
        csv_content = (
            "Mã hàng,Tên hàng,Giá,Số lượng\n"
            "SP01,Cà phê sữa,25000,10\n"
            "SP02,Bánh mì thịt,15000,5\n"
            "SP03,Trà đào,30000,2\n"
        )
        (cls.dummy_biz / "menu.csv").write_text(csv_content, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        close_sandbox_worker()
        cls.tmp_dir_obj.cleanup()

    def test_sql_execution(self):
        """Thực thi SQL truy vấn bảng SQLite được nạp trong bộ nhớ."""
        code = """
cur = con.cursor()
cur.execute("SELECT COUNT(*) FROM t_01")
row = cur.fetchone()
FINAL_RESULT = row[0]
"""
        res = run_code(code, self.dummy_biz, timeout_s=10)
        self.assertTrue(res.ok)
        self.assertEqual(res.final_result, 3)

    def test_pandas_execution(self):
        """Thực thi Pandas tính tổng từ biến dfs."""
        code = """
df = dfs["t_01"]
FINAL_RESULT = int(df["Số lượng"].astype(int).sum())
"""
        res = run_code(code, self.dummy_biz, timeout_s=10)
        self.assertTrue(res.ok)
        self.assertEqual(res.final_result, 17)

    def test_solution_data_function(self):
        """Hỗ trợ hàm def solution(data) do LLM sinh ra."""
        code = """
def solution(data):
    df = list(data.values())[0]
    return int(df["Số lượng"].astype(int).sum())
"""
        res = run_code(code, self.dummy_biz, timeout_s=10)
        self.assertTrue(res.ok)
        self.assertEqual(res.final_result, 17)

    def test_missing_final_result(self):
        """Báo lỗi khi code không gán FINAL_RESULT hoặc không có solution()."""
        code = "a = 10 + 20"
        res = run_code(code, self.dummy_biz, timeout_s=10)
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "NO_FINAL_RESULT")

    def test_syntax_error(self):
        """Bắt lỗi cú pháp trong sandbox."""
        code = "def invalid_func(:\n    pass\nFINAL_RESULT = 1"
        res = run_code(code, self.dummy_biz, timeout_s=10)
        self.assertFalse(res.ok)
        self.assertIn("SyntaxError", res.error or "")

    def test_runtime_error(self):
        """Bắt lỗi chia cho 0 trong sandbox."""
        code = "FINAL_RESULT = 10 / 0"
        res = run_code(code, self.dummy_biz, timeout_s=10)
        self.assertFalse(res.ok)
        self.assertIn("ZeroDivisionError", res.error or "")

    def test_timeout(self):
        """Bắt lỗi timeout khi gặp vòng lặp vô hạn."""
        code = "while True:\n    pass"
        res = run_code(code, self.dummy_biz, timeout_s=2)
        self.assertFalse(res.ok)
        self.assertIn("TIMEOUT", res.error or "")

    def test_serialization(self):
        """Chuyển đổi đúng kiểu JSON cho numpy scalar, float, NaN, Timestamp."""
        code = """
import numpy as np, pandas as pd
FINAL_RESULT = {
    "num_int": np.int64(42),
    "num_float": np.float64(3.14),
    "time": pd.Timestamp("2026-10-31 10:00:00"),
    "nan_val": np.nan,
    "na_val": pd.NA,
}
"""
        res = run_code(code, self.dummy_biz, timeout_s=10)
        self.assertTrue(res.ok)
        self.assertEqual(res.final_result["num_int"], 42)
        self.assertAlmostEqual(res.final_result["num_float"], 3.14, places=2)
        self.assertIn("2026-10-31", res.final_result["time"])
        self.assertIsNone(res.final_result["nan_val"])
        self.assertIsNone(res.final_result["na_val"])

    def test_persistent_worker_reuse(self):
        """Chạy liên tiếp 2 câu hỏi trên cùng 1 worker để kiểm tra tái sử dụng RAM."""
        code1 = "FINAL_RESULT = 'Q1_ANSWER'"
        res1 = run_code(code1, self.dummy_biz, timeout_s=10)
        self.assertTrue(res1.ok)
        self.assertEqual(res1.final_result, "Q1_ANSWER")

        code2 = "FINAL_RESULT = 'Q2_ANSWER'"
        res2 = run_code(code2, self.dummy_biz, timeout_s=10)
        self.assertTrue(res2.ok)
        self.assertEqual(res2.final_result, "Q2_ANSWER")


if __name__ == "__main__":
    unittest.main()

