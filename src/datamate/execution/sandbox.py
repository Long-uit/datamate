"""
runner.py — Execution Runner tối giản cho DataMate (Phase 1).

Chạy mã Python/SQL trong một subprocess riêng độc lập, cô lập với runner,
nạp sẵn dữ liệu business qua ingest.py (con, dfs, business, pd),
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

# Đoạn mã bootstrap chạy bên trong subprocess
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
    # Xử lý boolean trước int vì bool là subclass của int trong Python
    if isinstance(val, bool):
        return val
    # Số nguyên / float chuẩn hoặc numpy
    if isinstance(val, (int,)):
        return int(val)
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)

    # Thử check numpy/pandas types mà không bắt buộc cài numpy nếu môi trường tối giản
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

    # Timestamp / datetime
    if hasattr(val, "isoformat"):
        return val.isoformat()

    # List, tuple, set
    if isinstance(val, (list, tuple, set)):
        return [_to_json_serializable(x) for x in val]

    # Dict
    if isinstance(val, dict):
        return {str(k): _to_json_serializable(v) for k, v in val.items()}

    # Pandas DataFrame / Series
    if hasattr(val, "to_dict"):
        try:
            return _to_json_serializable(val.to_dict())
        except Exception:
            pass

    # Chuỗi hoặc các đối tượng chuyển string
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
    from datamate.ingestion.loader import load_business, to_sqlite

    # Đọc mã nguồn cần thực thi
    code_str = code_file.read_text(encoding="utf-8")

    # Nạp dữ liệu business
    business = load_business(biz_dir)
    con = to_sqlite(business)
    dfs = {ti.table_id: ti.df for ti in business.tables}

    # Chuẩn bị namespace
    namespace = {
        "con": con,
        "dfs": dfs,
        "business": business,
        "pd": pd,
    }

    # Bắt stdout của code người dùng
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
                # Kiểm tra serialize JSON thực sự
                json.dumps(clean_res, ensure_ascii=False)
                res_payload["ok"] = True
                res_payload["final_result"] = clean_res
            except Exception as ser_err:
                res_payload["ok"] = False
                res_payload["error"] = f"CANNOT_SERIALIZE_JSON: {ser_err}"

    except Exception as exc:
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
"""


@dataclass
class RunResult:
    """Kết quả thực thi mã trong sandbox subprocess."""
    ok: bool
    final_result: Any          # Giá trị FINAL_RESULT, None nếu lỗi
    stdout: str                # Cắt tối đa 10_000 ký tự
    error: str | None          # Traceback hoặc mã lỗi ("TIMEOUT", "NO_FINAL_RESULT", v.v.)
    elapsed_ms: int


def run_code(code: str, business_dir: Path, timeout_s: int = 60) -> RunResult:
    """
    Chạy mã Python/SQL của câu hỏi trong subprocess độc lập.

    Tham số:
        code: Chuỗi mã Python do LLM hoặc người dùng sinh ra (cần gán biến FINAL_RESULT).
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

                    return RunResult(
                        ok=bool(data.get("ok", False)),
                        final_result=data.get("final_result"),
                        stdout=stdout_str,
                        error=data.get("error"),
                        elapsed_ms=elapsed_ms,
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

