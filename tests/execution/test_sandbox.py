"""
tests/test_runner.py — Unit tests cho execution runner của DataMate (Phase 1).

Chạy: pytest tests/test_runner.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest
import pandas as pd
import numpy as np


from datamate.execution.sandbox import RunResult, run_code



# ===========================================================================
# Helpers tạo dữ liệu thử
# ===========================================================================

@pytest.fixture
def dummy_biz(tmp_path: Path) -> Path:
    """Tạo một shop nhỏ với 1 CSV và 1 README."""
    bdir = tmp_path / "dummy_shop"
    bdir.mkdir()
    (bdir / "README.md").write_text("# Dummy Shop\nMo ta cua hang.", encoding="utf-8")
    
    csv_content = (
        "Mã hàng,Tên hàng,Giá,Số lượng\n"
        "SP01,Cà phê sữa,25000,10\n"
        "SP02,Bánh mì thịt,15000,5\n"
        "SP03,Trà đào,30000,2\n"
    )
    (bdir / "menu.csv").write_text(csv_content, encoding="utf-8")
    return bdir


# ===========================================================================
# Test Cases
# ===========================================================================

def test_sql_execution_success(dummy_biz: Path):
    """Code đúng dùng SQL trên biến `con` -> ok=True, kết quả chính xác."""
    code = """
cur = con.cursor()
cur.execute("SELECT COUNT(*) FROM t_01")
row = cur.fetchone()
FINAL_RESULT = row[0]
"""
    res = run_code(code, dummy_biz, timeout_s=10)
    assert res.ok is True
    assert res.final_result == 3
    assert res.error is None
    assert res.elapsed_ms > 0


def test_pandas_execution_success(dummy_biz: Path):
    """Code đúng dùng pandas trên biến `dfs`."""
    code = """
df = dfs["t_01"]
# Cột Giá là string nên ép kiểu tính tổng
total = df["Số lượng"].astype(int).sum()
FINAL_RESULT = int(total)
"""
    res = run_code(code, dummy_biz, timeout_s=10)
    assert res.ok is True
    assert res.final_result == 17
    assert res.error is None


def test_missing_final_result(dummy_biz: Path):
    """Thiếu biến FINAL_RESULT -> ok=False, error="NO_FINAL_RESULT"."""
    code = """
x = 10 + 20
y = "chua gan final_result"
"""
    res = run_code(code, dummy_biz, timeout_s=10)
    assert res.ok is False
    assert res.final_result is None
    assert res.error == "NO_FINAL_RESULT"


def test_syntax_error(dummy_biz: Path):
    """Lỗi cú pháp -> ok=False, traceback chứa SyntaxError."""
    code = """
def invalid_func(:
    pass
FINAL_RESULT = 1
"""
    res = run_code(code, dummy_biz, timeout_s=10)
    assert res.ok is False
    assert res.final_result is None
    assert "SyntaxError" in (res.error or "")


def test_runtime_error(dummy_biz: Path):
    """Lỗi runtime (ZeroDivisionError) -> ok=False, traceback chứa ZeroDivisionError."""
    code = """
a = 10 / 0
FINAL_RESULT = a
"""
    res = run_code(code, dummy_biz, timeout_s=10)
    assert res.ok is False
    assert res.final_result is None
    assert "ZeroDivisionError" in (res.error or "")


def test_infinite_loop_timeout(dummy_biz: Path):
    """Vòng lặp vô hạn -> timeout, process bị kill, error="TIMEOUT"."""
    code = """
while True:
    pass
FINAL_RESULT = 100
"""
    # Timeout 2 giây để test chạy nhanh
    res = run_code(code, dummy_biz, timeout_s=2)
    assert res.ok is False
    assert res.final_result is None
    assert res.error == "TIMEOUT"


def test_numpy_and_timestamp_serialization(dummy_biz: Path):
    """FINAL_RESULT là numpy int64, float, Timestamp, NaN -> được chuyển đúng kiểu JSON."""
    code = """
import numpy as np
import pandas as pd

FINAL_RESULT = {
    "num_int": np.int64(42),
    "num_float": np.float64(3.14),
    "time": pd.Timestamp("2026-10-31 10:00:00"),
    "nan_val": np.nan,
    "na_val": pd.NA,
}
"""
    res = run_code(code, dummy_biz, timeout_s=10)
    assert res.ok is True
    assert isinstance(res.final_result, dict)
    assert res.final_result["num_int"] == 42
    assert abs(res.final_result["num_float"] - 3.14) < 1e-4
    assert "2026-10-31" in res.final_result["time"]
    assert res.final_result["nan_val"] is None
    assert res.final_result["na_val"] is None


def test_print_does_not_corrupt_result(dummy_biz: Path):
    """Lệnh print() trong code người dùng không làm hỏng final_result và được lưu vào stdout."""
    code = """
print("Dang xu ly du lieu...")
print("In ra them mot dong nua: 12345")
FINAL_RESULT = "ket_qua_chuan"
"""
    res = run_code(code, dummy_biz, timeout_s=10)
    assert res.ok is True
    assert res.final_result == "ket_qua_chuan"
    assert "Dang xu ly du lieu..." in res.stdout
    assert "12345" in res.stdout


def test_runner_does_not_write_to_business_dir(dummy_biz: Path):
    """Xác nhận runner không tự tạo bất kỳ file nào trong thư mục business_dir."""
    files_before = set(dummy_biz.iterdir())
    
    code = """
cur = con.cursor()
cur.execute("SELECT 1")
FINAL_RESULT = "OK"
"""
    res = run_code(code, dummy_biz, timeout_s=10)
    assert res.ok is True
    
    files_after = set(dummy_biz.iterdir())
    assert files_before == files_after, "Runner khong duoc ghi file vao business_dir"

