"""
worker.py — Subprocess worker thực thi mã Python/SQL độc lập trong sandbox.

Được sandbox.py gọi qua subprocess.
Nạp sẵn:
- con: sqlite3.Connection (đã nạp bảng sạch theo Rule 8 và tự động đánh index)
- dfs: dict[table_id, pd.DataFrame] (đã làm sạch theo Rule 8)
- business: BusinessData
- pd: pandas module
"""

from __future__ import annotations

import io
import json
import math
import os
from pathlib import Path
import sys
import traceback


def _to_json_serializable(val):
    """Chuyển đổi các kiểu dữ liệu phong phú (numpy, pandas, datetime) sang JSON chuẩn."""
    if val is None or val is Ellipsis:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int,)):
        return int(val)
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)

    type_str = type(val).__name__
    module_str = type(val).__module__

    if "numpy" in module_str or "pandas" in module_str:
        if hasattr(val, "item"):
            try:
                py_val = val.item()
                return _to_json_serializable(py_val)
            except Exception:
                pass
        if hasattr(val, "isoformat"):
            return val.isoformat()
        if type_str in ("NAType", "NaTType"):
            return None

    if hasattr(val, "isoformat"):
        return val.isoformat()

    if isinstance(val, (list, tuple, set)):
        return [_to_json_serializable(x) for x in val]

    if isinstance(val, dict):
        return {str(k): _to_json_serializable(v) for k, v in val.items()}

    if hasattr(val, "to_dict"):
        try:
            return _to_json_serializable(val.to_dict())
        except Exception:
            pass

    return str(val)


def main():
    if len(sys.argv) < 4:
        sys.exit(1)

    code_file = Path(sys.argv[1])
    biz_dir = Path(sys.argv[2])
    result_file = Path(sys.argv[3])
    root_src = Path(sys.argv[4]) if len(sys.argv) > 4 else None

    if root_src and str(root_src) not in sys.path:
        sys.path.insert(0, str(root_src))

    import pandas as pd
    from datamate.ingestion.loader import load_business
    from datamate.ingestion.cleaner import clean_business
    from datamate.ingestion.sqlite_mirror import get_sqlite_mirror

    # Đọc mã nguồn cần thực thi
    code_str = code_file.read_text(encoding="utf-8")

    # Nạp dữ liệu business và áp dụng Rule 8 Cleaner
    raw_business = load_business(biz_dir)
    business = clean_business(raw_business)

    # Nạp SQLite mirror có index tự động
    con = get_sqlite_mirror(business, clean=False, use_cache=True)
    dfs = {ti.table_id: ti.df for ti in business.tables}

    # Chuẩn bị namespace
    namespace = {
        "con": con,
        "dfs": dfs,
        "business": business,
        "pd": pd,
    }

    # Bắt stdout của code
    old_stdout = sys.stdout
    captured_stdout = io.StringIO()
    sys.stdout = captured_stdout

    res_payload = {
        "ok": False,
        "final_result": None,
        "stdout": "",
        "error": None,
    }

    try:
        compiled = compile(code_str, "<submitted_code>", "exec")
        exec(compiled, namespace)

        if "FINAL_RESULT" not in namespace:
            res_payload["ok"] = False
            res_payload["error"] = "NO_FINAL_RESULT"
        else:
            raw_res = namespace["FINAL_RESULT"]
            try:
                clean_res = _to_json_serializable(raw_res)
                # Kiểm tra tính hợp lệ JSON
                json.dumps(clean_res, ensure_ascii=False)
                res_payload["ok"] = True
                res_payload["final_result"] = clean_res
            except Exception as ser_err:
                res_payload["ok"] = False
                res_payload["error"] = f"CANNOT_SERIALIZE_JSON: {ser_err}"

    except Exception:
        res_payload["ok"] = False
        res_payload["error"] = traceback.format_exc()
    finally:
        sys.stdout = old_stdout
        try:
            con.close()
        except Exception:
            pass

    # Lấy stdout tối đa 10_000 ký tự
    stdout_val = captured_stdout.getvalue()
    if len(stdout_val) > 10_000:
        stdout_val = stdout_val[:10_000]
    res_payload["stdout"] = stdout_val

    # Ghi kết quả sang result_file
    result_file.write_text(json.dumps(res_payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
