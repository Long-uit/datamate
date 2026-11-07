"""
worker.py — Subprocess worker thực thi mã Python/SQL độc lập trong sandbox.

Hỗ trợ 2 chế độ:
1. Persistent Daemon mode (--daemon <biz_dir> <src_dir>):
   - Nạp toàn bộ dữ liệu của shop vào RAM đúng 1 lần duy nhất.
   - Giữ tiến trình sống và thực thi liên tục các đoạn code qua stdin/stdout.
   - Giải quyết triệt để điểm nghẽn I/O đọc lại tệp Excel/CSV từ đĩa.
2. One-shot mode (Legacy: <code_file> <biz_dir> <result_file> <src_dir>):
   - Tương thích ngược với các lệnh gọi đơn lẻ trước đây.
"""

from __future__ import annotations

import datetime
from datetime import datetime as dt, date, timedelta
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import traceback
import unicodedata
from typing import Any, Dict


class SmartDataDict(dict):
    """
    Dictionary thông minh hỗ trợ tra cứu bảng dữ liệu mềm dẻo:
    - Không phân biệt chữ hoa, chữ thường.
    - Không phụ thuộc dấu tiếng Việt (NFD/NFC).
    - Tự động bỏ qua phần mở rộng file (.csv, .xlsx).
    - Hỗ trợ khớp mềm (substring match) nếu tên bảng có tiền tố/hậu tố.
    """
    def __init__(self, data_dict: Dict[str, Any]):
        super().__init__(data_dict)
        self._norm_map: Dict[str, str] = {}
        for k in data_dict.keys():
            norm_k = self._normalize(k)
            if norm_k:
                self._norm_map[norm_k] = k

    @staticmethod
    def _normalize(k: Any) -> str:
        s = str(k).strip().lower()
        s = s.replace("đ", "d").replace("Đ", "d")
        s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
        s = re.sub(r"\.(?:csv|xlsx|xls)$", "", s)
        s = re.sub(r"[^a-z0-9]", "", s)
        return s

    def __getitem__(self, key: Any) -> Any:
        if key in self:
            return super().__getitem__(key)
        nk = self._normalize(key)
        if nk in self._norm_map:
            return super().__getitem__(self._norm_map[nk])
        # Khớp mềm nếu một bên chứa bên kia
        for norm_cand, orig_k in self._norm_map.items():
            if nk and (nk in norm_cand or norm_cand in nk):
                return super().__getitem__(orig_k)
        raise KeyError(key)

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


def _to_json_serializable(val: Any) -> Any:
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


def execute_code_in_env(
    code_str: str,
    data_dict: Dict[str, Any],
    business: Any,
    con: Any,
    pd: Any,
    np: Any,
    apply_tie_breaker: Any,
    filter_future_data: Any,
    clean_num: Any,
    clean_date: Any,
    DataNotFoundError: Any,
) -> Dict[str, Any]:
    """Thực thi mã nguồn an toàn trong môi trường namespace có dữ liệu nạp sẵn."""
    # Tạo bản sao shallow-copy để bảo vệ DataFrame gốc trong RAM và bọc bằng SmartDataDict
    isolated_data = {k: v.copy(deep=False) for k, v in data_dict.items()}
    smart_data = SmartDataDict(isolated_data)

    def _pct(a: Any, b: Any) -> float:
        try:
            fa, fb = float(a), float(b)
            return (fa / fb * 100.0) if fb != 0 else 0.0
        except Exception:
            return 0.0

    namespace = {
        "__builtins__": __builtins__,
        "con": con,
        "dfs": smart_data,
        "data": smart_data,
        "business": business,
        "pd": pd,
        "np": np,
        "re": re,
        "math": math,
        "datetime": datetime,
        "date": date,
        "timedelta": timedelta,
        "pct": _pct,
        "apply_tie_breaker": apply_tie_breaker,
        "filter_future_data": filter_future_data,
        "clean_num": clean_num,
        "clean_date": clean_date,
        "DataNotFoundError": DataNotFoundError,
    }
    if isinstance(namespace.get("__builtins__"), dict):
        namespace["__builtins__"]["DataNotFoundError"] = DataNotFoundError

    # Bắt stdout của code
    old_stdout = sys.stdout
    captured_stdout = io.StringIO()
    sys.stdout = captured_stdout

    res_payload: Dict[str, Any] = {
        "ok": False,
        "final_result": None,
        "stdout": "",
        "error": None,
        "error_type": None,
        "unanswerable_source": "none",
        "missing_info": None,
    }

    try:
        compiled = compile(code_str, "<submitted_code>", "exec")
        exec(compiled, namespace)

        if "FINAL_RESULT" not in namespace:
            if "solution" in namespace and callable(namespace["solution"]):
                _raw = namespace["solution"](isolated_data)
                if _raw is None or (isinstance(_raw, str) and not _raw.strip()):
                    namespace["FINAL_RESULT"] = {
                        "type": "abstain",
                        "answer": None,
                        "unanswerable_source": "none",
                        "reason": "Solution returned None or empty string",
                    }
                elif _raw == "unanswerable" or (
                    isinstance(_raw, str) and _raw.strip().lower() in ("unanswerable", "không thể trả lời")
                ):
                    namespace["FINAL_RESULT"] = {
                        "type": "unanswerable",
                        "answer": None,
                        "unanswerable_source": "model",
                        "reason": "Model explicitly returned unanswerable string",
                    }
                elif isinstance(_raw, dict) and _raw.get("type") == "unanswerable":
                    src = _raw.get("unanswerable_source", "model")
                    namespace["FINAL_RESULT"] = {
                        "type": "unanswerable",
                        "answer": None,
                        "unanswerable_source": src,
                    }
                else:
                    namespace["FINAL_RESULT"] = _raw
            else:
                res_payload["ok"] = False
                res_payload["error"] = "NO_FINAL_RESULT"
                res_payload["error_type"] = "NoFinalResult"

        if "FINAL_RESULT" in namespace:
            raw_res = namespace["FINAL_RESULT"]
            try:
                clean_res = _to_json_serializable(raw_res)
                json.dumps(clean_res, ensure_ascii=False)
                res_payload["ok"] = True
                res_payload["final_result"] = clean_res
                if isinstance(raw_res, dict):
                    res_payload["unanswerable_source"] = raw_res.get("unanswerable_source", "none")
            except Exception as ser_err:
                res_payload["ok"] = False
                res_payload["error"] = f"CANNOT_SERIALIZE_JSON: {ser_err}"
                res_payload["error_type"] = "SerializationError"

    except DataNotFoundError as dne:
        res_payload["ok"] = False
        res_payload["error_type"] = "DataNotFoundError"
        res_payload["error"] = str(dne)
        res_payload["missing_info"] = str(dne)
    except Exception as exc:
        res_payload["ok"] = False
        err_tb = traceback.format_exc()
        if "DataNotFoundError" in str(exc) or "DataNotFoundError" in err_tb:
            res_payload["error_type"] = "DataNotFoundError"
            res_payload["error"] = str(exc)
            res_payload["missing_info"] = str(exc)
        else:
            res_payload["error_type"] = type(exc).__name__
            res_payload["error"] = err_tb
    finally:
        sys.stdout = old_stdout

    # Lấy stdout tối đa 10_000 ký tự
    stdout_val = captured_stdout.getvalue()
    if len(stdout_val) > 10_000:
        stdout_val = stdout_val[:10_000]
    res_payload["stdout"] = stdout_val

    return res_payload


def _load_shop_context(biz_dir: Path):
    """Nạp và làm sạch dữ liệu shop vào RAM 1 lần duy nhất."""
    import pandas as pd
    import numpy as np
    from datamate.ingestion_schema.loader import load_business
    from datamate.ingestion_schema.cleaner import clean_business
    from datamate.ingestion_schema.sqlite_mirror import get_sqlite_mirror
    from datamate.output_abstention.normalizer import apply_tie_breaker
    from datamate.grounding_feasibility.temporal import filter_future_data
    from datamate.llm_execution.sandbox import clean_num, clean_date
    from datamate.exceptions import DataNotFoundError

    class _LazySQLiteConnection:
        """Tối ưu hóa nạp kép: Không nạp SQLite mặc định. Chỉ dựng SQLite Mirror khi mã thực sự gọi con."""
        def __init__(self, biz_obj):
            self._biz_obj = biz_obj
            self._real_con = None

        def _get(self):
            if self._real_con is None:
                self._real_con = get_sqlite_mirror(self._biz_obj, clean=False, use_cache=True)
            return self._real_con

        def cursor(self, *args, **kwargs):
            return self._get().cursor(*args, **kwargs)

        def execute(self, *args, **kwargs):
            return self._get().execute(*args, **kwargs)

        def close(self):
            if self._real_con is not None:
                try:
                    self._real_con.close()
                except Exception:
                    pass
                self._real_con = None

        def __getattr__(self, item):
            return getattr(self._get(), item)

    raw_business = load_business(biz_dir)
    business = clean_business(raw_business)
    con = _LazySQLiteConnection(business)

    data_dict = {}
    for ti in business.tables:
        t_base = Path(ti.fixed_file_name).stem if getattr(ti, "fixed_file_name", None) else ti.table_id
        t_name = f"{t_base}_{ti.sheet_name}" if ti.sheet_name and ti.sheet_name != "Sheet1" else t_base
        data_dict[t_name] = ti.df
        if t_base != t_name and t_base not in data_dict:
            data_dict[t_base] = ti.df
        if ti.table_id and ti.table_id not in data_dict:
            data_dict[ti.table_id] = ti.df

    return {
        "business": business,
        "con": con,
        "data_dict": data_dict,
        "pd": pd,
        "np": np,
        "apply_tie_breaker": apply_tie_breaker,
        "filter_future_data": filter_future_data,
        "clean_num": clean_num,
        "clean_date": clean_date,
        "DataNotFoundError": DataNotFoundError,
    }


def main():
    if len(sys.argv) < 3:
        sys.exit(1)

    # =========================================================================
    # CHẾ ĐỘ 1: PERSISTENT DAEMON WORKER (Nạp 1 lần, chạy liên tục qua pipe)
    # =========================================================================
    if sys.argv[1] == "--daemon":
        biz_dir = Path(sys.argv[2])
        root_src = Path(sys.argv[3]) if len(sys.argv) > 3 else None
        if root_src and str(root_src) not in sys.path:
            sys.path.insert(0, str(root_src))

        ctx = _load_shop_context(biz_dir)

        # Gửi tín hiệu hoàn tất nạp dữ liệu tới Sandbox runner
        sys.stdout.write("__WORKER_READY__\n")
        sys.stdout.flush()

        # Vòng lặp nhận và thực thi các câu hỏi
        for line in sys.stdin:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                msg = json.loads(line_str)
            except Exception:
                continue

            cmd = msg.get("cmd")
            if cmd == "quit":
                break
            elif cmd == "run":
                code_text = msg.get("code", "")
                result_payload = execute_code_in_env(
                    code_str=code_text,
                    data_dict=ctx["data_dict"],
                    business=ctx["business"],
                    con=ctx["con"],
                    pd=ctx["pd"],
                    np=ctx["np"],
                    apply_tie_breaker=ctx["apply_tie_breaker"],
                    filter_future_data=ctx["filter_future_data"],
                    clean_num=ctx["clean_num"],
                    clean_date=ctx["clean_date"],
                    DataNotFoundError=ctx["DataNotFoundError"],
                )
                serialized = json.dumps(result_payload, ensure_ascii=False)
                sys.stdout.write(f"__RESULT__:{serialized}\n")
                sys.stdout.flush()

        try:
            if ctx.get("con"):
                ctx["con"].close()
        except Exception:
            pass
        sys.exit(0)

    # =========================================================================
    # CHẾ ĐỘ 2: ONE-SHOT (Tương thích ngược với định dạng đối số cũ)
    # =========================================================================
    code_file = Path(sys.argv[1])
    biz_dir = Path(sys.argv[2])
    result_file = Path(sys.argv[3])
    root_src = Path(sys.argv[4]) if len(sys.argv) > 4 else None

    if root_src and str(root_src) not in sys.path:
        sys.path.insert(0, str(root_src))

    code_str = code_file.read_text(encoding="utf-8")
    ctx = _load_shop_context(biz_dir)

    res_payload = execute_code_in_env(
        code_str=code_str,
        data_dict=ctx["data_dict"],
        business=ctx["business"],
        con=ctx["con"],
        pd=ctx["pd"],
        np=ctx["np"],
        apply_tie_breaker=ctx["apply_tie_breaker"],
        filter_future_data=ctx["filter_future_data"],
        clean_num=ctx["clean_num"],
        clean_date=ctx["clean_date"],
        DataNotFoundError=ctx["DataNotFoundError"],
    )

    try:
        if ctx.get("con"):
            ctx["con"].close()
    except Exception:
        pass

    result_file.write_text(json.dumps(res_payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
