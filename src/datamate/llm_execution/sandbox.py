"""
sandbox.py — Execution Runner cho DataMate (Phase 1).

Chạy mã Python/SQL trong một subprocess riêng độc lập, cô lập với runner,
nạp sẵn dữ liệu business qua loader và cleaner (con, dfs, data, business, pd, np),
và trả về RunResult an toàn (bắt lỗi, timeout, serialize JSON).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Đoạn mã bootstrap chạy bên trong subprocess (đồng bộ hoàn toàn với worker.py)
_SUBPROCESS_WORKER_SCRIPT = """
import sys
import os
import io
import json
import traceback
from pathlib import Path
import math

def _to_json_serializable(val):
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
    import numpy as np
    from datamate.ingestion.loader import load_business
    from datamate.ingestion.cleaner import clean_business
    from datamate.ingestion.sqlite_mirror import get_sqlite_mirror
    from datamate.output.normalizer import apply_tie_breaker
    from datamate.grounding.temporal import filter_future_data
    from datamate.execution.helpers import clean_num, clean_date
    from datamate.exceptions import DataNotFoundError

    # Đọc mã nguồn cần thực thi
    code_str = code_file.read_text(encoding="utf-8")

    # Nạp dữ liệu business và áp dụng Rule 8 Cleaner
    raw_business = load_business(biz_dir)
    business = clean_business(raw_business)

    # Nạp SQLite mirror có index tự động
    con = get_sqlite_mirror(business, clean=False, use_cache=True)
    data_dict = {}
    for ti in business.tables:
        t_base = Path(ti.fixed_file_name).stem
        t_name = f"{t_base}_{ti.sheet_name}" if ti.sheet_name and ti.sheet_name != "Sheet1" else t_base
        data_dict[t_name] = ti.df
        if t_base not in data_dict:
            data_dict[t_base] = ti.df
        if ti.table_id:
            data_dict[ti.table_id] = ti.df
        if ti.sheet_name and ti.sheet_name not in data_dict:
            data_dict[ti.sheet_name] = ti.df

    # Chuẩn bị namespace
    namespace = {
        "__builtins__": __builtins__,
        "con": con,
        "dfs": data_dict,
        "data": data_dict,
        "business": business,
        "pd": pd,
        "np": np,
        "apply_tie_breaker": apply_tie_breaker,
        "filter_future_data": filter_future_data,
        "clean_num": clean_num,
        "clean_date": clean_date,
        "DataNotFoundError": DataNotFoundError,
    }
    if isinstance(namespace.get("__builtins__"), dict):
        namespace["__builtins__"]["DataNotFoundError"] = DataNotFoundError

    # Bắt stdout của code người dùng
    old_stdout = sys.stdout
    captured_stdout = io.StringIO()
    sys.stdout = captured_stdout

    res_payload = {
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
                _raw = namespace["solution"](data_dict)
                if _raw is None or (isinstance(_raw, str) and not _raw.strip()):
                    namespace["FINAL_RESULT"] = {
                        "type": "abstain",
                        "answer": None,
                        "unanswerable_source": "none",
                        "reason": "Solution returned None or empty string",
                    }
                elif _raw == "unanswerable" or (isinstance(_raw, str) and _raw.strip().lower() in ("unanswerable", "không thể trả lời")):
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
        try:
            con.close()
        except Exception:
            pass

    stdout_val = captured_stdout.getvalue()
    if len(stdout_val) > 10_000:
        stdout_val = stdout_val[:10_000]
    res_payload["stdout"] = stdout_val

    result_file.write_text(json.dumps(res_payload, ensure_ascii=False), encoding="utf-8")

if __name__ == "__main__":
    main()
"""


@dataclass
class RunResult:
    """Kết quả thực thi mã trong sandbox subprocess."""
    ok: bool
    final_result: Any                        # Giá trị FINAL_RESULT, None nếu lỗi
    stdout: str                              # Cắt tối đa 10_000 ký tự
    error: str | None                        # Traceback hoặc mã lỗi ("TIMEOUT", "NO_FINAL_RESULT", v.v.)
    elapsed_ms: int
    error_type: str | None = None            # "DataNotFoundError", "Timeout", "SyntaxError", etc.
    unanswerable_source: str = "none"        # "gate" | "model" | "none"
    missing_info: str | None = None          # Thông tin chi tiết bảng/cột thiếu


def run_code(code: str, business_dir: Path, timeout_s: int = 60) -> RunResult:
    """
    Chạy mã Python/SQL của câu hỏi trong subprocess độc lập.

    Tham số:
        code: Chuỗi mã Python do LLM hoặc người dùng sinh ra (cần gán biến FINAL_RESULT hoặc hàm solution).
        business_dir: Đường dẫn thư mục business (chế độ chỉ đọc).
        timeout_s: Thời gian chờ tối đa (giây). Hết giờ sẽ kill process và báo TIMEOUT.

    Trả về:
        RunResult chứa trạng thái thực thi, stdout, error và kết quả. Không bao giờ raise exception.
    """
    t_start = time.perf_counter()

    # Tạo thư mục tạm để giao tiếp an toàn (ngoài thư mục business_dir)
    with tempfile.TemporaryDirectory(prefix="dm_runner_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        code_file = tmp_path / "code.py"
        result_file = tmp_path / "result.json"
        code_file.write_text(code, encoding="utf-8")

        # Ưu tiên sử dụng worker.py chính thức
        real_worker = Path(__file__).parent / "worker.py"
        if real_worker.exists():
            worker_file = real_worker
        else:
            worker_file = tmp_path / "worker.py"
            worker_file.write_text(_SUBPROCESS_WORKER_SCRIPT, encoding="utf-8")

        # Thư mục src/ chứa package datamate
        src_dir = Path(__file__).resolve().parents[2]  # sandbox.py -> execution -> datamate -> src

        # Tạo môi trường subprocess có PYTHONPATH trỏ vào src
        sub_env = os.environ.copy()
        existing_pythonpath = sub_env.get("PYTHONPATH", "")
        sub_env["PYTHONPATH"] = (
            str(src_dir) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
        )
        sub_env["PYTHONIOENCODING"] = "utf-8"

        cmd = [
            sys.executable,
            str(worker_file),
            str(code_file),
            str(Path(business_dir).resolve()),
            str(result_file),
            str(src_dir),
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env=sub_env,
            )

            elapsed_ms = int((time.perf_counter() - t_start) * 1000)

            # Kiểm tra xem result_file có được tạo và chứa dữ liệu không
            if result_file.exists():
                try:
                    data = json.loads(result_file.read_text(encoding="utf-8"))
                    stdout_str = data.get("stdout", "")
                    if len(stdout_str) > 10_000:
                        stdout_str = stdout_str[:10_000]

                    unans_source = "none"
                    fin_res = data.get("final_result")
                    if isinstance(fin_res, dict):
                        unans_source = fin_res.get("unanswerable_source", data.get("unanswerable_source", "none"))
                    elif data.get("unanswerable_source"):
                        unans_source = data.get("unanswerable_source")

                    return RunResult(
                        ok=bool(data.get("ok", False)),
                        final_result=fin_res,
                        stdout=stdout_str,
                        error=data.get("error"),
                        elapsed_ms=elapsed_ms,
                        error_type=data.get("error_type"),
                        unanswerable_source=unans_source,
                        missing_info=data.get("missing_info"),
                    )
                except Exception as parse_err:
                    return RunResult(
                        ok=False,
                        final_result=None,
                        stdout=proc.stdout[:10_000] if proc.stdout else "",
                        error=f"PARSE_RESULT_ERROR: {parse_err}\nWorker stderr: {proc.stderr}",
                        elapsed_ms=elapsed_ms,
                    )
            else:
                # Nếu không có result_file, có thể worker crash trước khi ghi file
                err_msg = proc.stderr.strip() if proc.stderr else "SUBPROCESS_CRASHED"
                return RunResult(
                    ok=False,
                    final_result=None,
                    stdout=proc.stdout[:10_000] if proc.stdout else "",
                    error=err_msg,
                    elapsed_ms=elapsed_ms,
                )

        except subprocess.TimeoutExpired as tex:
            elapsed_ms = int((time.perf_counter() - t_start) * 1000)
            # Lấy stdout nếu có một phần
            sub_stdout = ""
            if tex.stdout:
                if isinstance(tex.stdout, bytes):
                    sub_stdout = tex.stdout.decode("utf-8", errors="replace")
                else:
                    sub_stdout = str(tex.stdout)
            return RunResult(
                ok=False,
                final_result=None,
                stdout=sub_stdout[:10_000],
                error="TIMEOUT",
                elapsed_ms=elapsed_ms,
                error_type="Timeout",
                unanswerable_source="none",
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - t_start) * 1000)
            return RunResult(
                ok=False,
                final_result=None,
                stdout="",
                error=f"RUNNER_EXCEPTION: {exc}",
                elapsed_ms=elapsed_ms,
            )
