"""
sandbox.py — Execution Runner cho DataMate (Phase 1).

Chạy mã Python/SQL trong một subprocess riêng độc lập, cô lập với runner.
Hỗ trợ cơ chế Persistent Daemon Subprocess:
- Nạp dữ liệu của shop vào RAM tiến trình con đúng 1 lần duy nhất.
- Tái sử dụng tiến trình con cho các câu hỏi cùng shop (và các lượt retry).
- Cắt giảm 100% chi phí đọc lại Excel/CSV từ đĩa cứng.
- Đảm bảo an toàn tuyệt đối: cô lập bộ nhớ, có hard-timeout và tự động khởi động lại nếu crash.
"""

from __future__ import annotations

import ast
import atexit
import datetime
import json
import math
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import numpy as np
import pandas as pd


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


class PersistentWorker:
    """
    Quản lý một tiến trình worker chạy ngầm độc lập cho 1 business_dir cụ thể.
    Dữ liệu được nạp vào RAM của worker 1 lần khi khởi tạo, sau đó worker nhận mã
    thực thi qua stdin và trả kết quả qua stdout theo giao thức JSON-lines.
    """

    def __init__(self, biz_dir: Path, src_dir: Path, startup_timeout: int = 180):
        self.biz_dir = Path(biz_dir).resolve()
        self.src_dir = Path(src_dir).resolve()
        self.proc: Optional[subprocess.Popen] = None
        self.stdout_queue: queue.Queue = queue.Queue()
        self.reader_thread: Optional[threading.Thread] = None
        self.is_alive = False
        self._start(startup_timeout)

    def _reader(self):
        """Thread đọc liên tục các dòng từ stdout của worker và đẩy vào queue."""
        try:
            assert self.proc is not None and self.proc.stdout is not None
            for line in iter(self.proc.stdout.readline, ""):
                if not line:
                    break
                self.stdout_queue.put(line)
        except Exception:
            pass
        finally:
            self.stdout_queue.put(None)  # Ký hiệu kết thúc tiến trình

    def _start(self, timeout: int):
        worker_file = Path(__file__).parent / "worker.py"
        if not worker_file.exists():
            raise FileNotFoundError(f"Không tìm thấy worker.py tại: {worker_file}")

        sub_env = os.environ.copy()
        existing_pythonpath = sub_env.get("PYTHONPATH", "")
        sub_env["PYTHONPATH"] = (
            str(self.src_dir) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
        )
        sub_env["PYTHONIOENCODING"] = "utf-8"

        cmd = [
            sys.executable,
            str(worker_file),
            "--daemon",
            str(self.biz_dir),
            str(self.src_dir),
        ]

        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=sub_env,
        )
        self.reader_thread = threading.Thread(target=self._reader, daemon=True)
        self.reader_thread.start()

        # Đợi tín hiệu __WORKER_READY__ từ worker
        t_start = time.perf_counter()
        while time.perf_counter() - t_start < timeout:
            try:
                line = self.stdout_queue.get(timeout=1.0)
            except queue.Empty:
                if self.proc.poll() is not None:
                    stderr_msg = self.proc.stderr.read() if self.proc.stderr else ""
                    self.kill()
                    raise RuntimeError(
                        f"Worker dừng đột ngột (code {self.proc.returncode}): {stderr_msg}"
                    )
                continue

            if line is None:
                stderr_msg = self.proc.stderr.read() if self.proc.stderr else ""
                self.kill()
                raise RuntimeError(f"Worker đóng kết nối trước khi sẵn sàng: {stderr_msg}")

            if "__WORKER_READY__" in line:
                self.is_alive = True
                return

        self.kill()
        raise TimeoutError(f"Worker nạp dữ liệu quá thời gian chờ ({timeout}s) cho shop: {self.biz_dir}")

    def execute(self, code: str, timeout_s: int, as_of_date: Any = None) -> RunResult:
        """Gửi mã nguồn sang worker và đợi kết quả với thời gian timeout chỉ định."""
        if not self.is_alive or self.proc is None or self.proc.poll() is not None:
            return RunResult(
                ok=False,
                final_result=None,
                stdout="",
                error="WORKER_NOT_RUNNING",
                elapsed_ms=0,
                error_type="WorkerNotRunning",
            )

        t_start = time.perf_counter()
        clean_c = sanitize_code_syntax(code)
        req_msg = json.dumps({"cmd": "run", "code": clean_c, "as_of_date": as_of_date}, ensure_ascii=False)
        try:
            assert self.proc.stdin is not None
            self.proc.stdin.write(req_msg + "\n")
            self.proc.stdin.flush()
        except Exception as write_err:
            self.kill()
            return RunResult(
                ok=False,
                final_result=None,
                stdout="",
                error=f"WRITE_TO_WORKER_ERROR: {write_err}",
                elapsed_ms=0,
                error_type="CommunicationError",
            )

        deadline = time.perf_counter() + timeout_s
        while time.perf_counter() < deadline:
            remaining = max(0.1, deadline - time.perf_counter())
            try:
                line = self.stdout_queue.get(timeout=remaining)
            except queue.Empty:
                # Quá thời gian timeout -> Buộc phải tiêu diệt tiến trình con để tránh treo GPU/CPU
                elapsed_ms = int((time.perf_counter() - t_start) * 1000)
                self.kill()
                return RunResult(
                    ok=False,
                    final_result=None,
                    stdout="",
                    error="TIMEOUT: Quá thời gian thực thi cho phép trong sandbox",
                    elapsed_ms=elapsed_ms,
                    error_type="Timeout",
                )

            if line is None:
                # Tiến trình con bị sập (Crash / Out-of-memory)
                elapsed_ms = int((time.perf_counter() - t_start) * 1000)
                stderr_msg = self.proc.stderr.read() if self.proc.stderr else ""
                self.kill()
                return RunResult(
                    ok=False,
                    final_result=None,
                    stdout="",
                    error=f"SUBPROCESS_CRASHED: {stderr_msg}",
                    elapsed_ms=elapsed_ms,
                    error_type="ProcessCrash",
                )

            if line.startswith("__RESULT__:"):
                payload_str = line[len("__RESULT__:") :].strip()
                elapsed_ms = int((time.perf_counter() - t_start) * 1000)
                try:
                    data = json.loads(payload_str)
                    stdout_str = data.get("stdout", "")
                    if len(stdout_str) > 10_000:
                        stdout_str = stdout_str[:10_000]

                    fin_res = data.get("final_result")
                    unans_source = "none"
                    if isinstance(fin_res, dict):
                        unans_source = fin_res.get(
                            "unanswerable_source", data.get("unanswerable_source", "none")
                        )
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
                        stdout="",
                        error=f"PARSE_RESULT_ERROR: {parse_err}\nRaw line: {line}",
                        elapsed_ms=elapsed_ms,
                    )

        elapsed_ms = int((time.perf_counter() - t_start) * 1000)
        self.kill()
        return RunResult(
            ok=False,
            final_result=None,
            stdout="",
            error="TIMEOUT",
            elapsed_ms=elapsed_ms,
            error_type="Timeout",
        )

    def close(self):
        """Đóng tiến trình worker một cách lịch sự."""
        if self.is_alive and self.proc and self.proc.poll() is None:
            try:
                assert self.proc.stdin is not None
                self.proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=2)
            except Exception:
                self.kill()
            finally:
                self.is_alive = False
                try:
                    if self.proc.stdin:
                        self.proc.stdin.close()
                except Exception:
                    pass
                try:
                    if self.proc.stdout:
                        self.proc.stdout.close()
                except Exception:
                    pass

    def kill(self):
        """Ép dừng tiến trình worker ngay lập tức."""
        self.is_alive = False
        if self.proc:
            try:
                self.proc.kill()
            except Exception:
                pass
            try:
                if self.proc.stdin:
                    self.proc.stdin.close()
            except Exception:
                pass
            try:
                if self.proc.stdout:
                    self.proc.stdout.close()
            except Exception:
                pass


# ==============================================================================
# QUẢN LÝ TIẾN TRÌNH CON ĐƠN NHẤT (SINGLETON WORKER MANAGER)
# ==============================================================================

_CURRENT_WORKER: Optional[PersistentWorker] = None
_CURRENT_BIZ_DIR: Optional[Path] = None
_WORKER_LOCK = threading.Lock()


def get_or_create_worker(business_dir: Path, timeout_startup: int = 180) -> PersistentWorker:
    """Trả về worker đang chạy cho business_dir hoặc tạo mới nếu chưa có / đã đổi shop."""
    global _CURRENT_WORKER, _CURRENT_BIZ_DIR
    resolved_biz = Path(business_dir).resolve()

    with _WORKER_LOCK:
        if (
            _CURRENT_WORKER is not None
            and _CURRENT_WORKER.is_alive
            and _CURRENT_WORKER.proc is not None
            and _CURRENT_WORKER.proc.poll() is None
            and _CURRENT_BIZ_DIR == resolved_biz
        ):
            return _CURRENT_WORKER

        # Dọn dẹp worker cũ nếu đổi sang shop khác
        close_sandbox_worker()

        src_dir = Path(__file__).resolve().parents[2]
        _CURRENT_WORKER = PersistentWorker(resolved_biz, src_dir, startup_timeout=timeout_startup)
        _CURRENT_BIZ_DIR = resolved_biz
        return _CURRENT_WORKER


def close_sandbox_worker() -> None:
    """Dọn dẹp và đóng tiến trình worker ngầm."""
    global _CURRENT_WORKER, _CURRENT_BIZ_DIR
    if _CURRENT_WORKER is not None:
        try:
            _CURRENT_WORKER.close()
        except Exception:
            pass
        _CURRENT_WORKER = None
        _CURRENT_BIZ_DIR = None


# Đăng ký tự động đóng worker khi tiến trình chính kết thúc
atexit.register(close_sandbox_worker)


def sanitize_code_syntax(code: str) -> str:
    """
    Tự động chuẩn hóa và vá lỗi cú pháp do bị cắt cụt token hoặc thiếu khối except/ngoặc đóng.
    Đảm bảo ast.parse(code) thành công và mã chạy an toàn trong sandbox.
    """
    if not code or not code.strip():
        return "def solution(data):\n    return None\n"

    # Bước 1: Thử parse trực tiếp, nếu hợp lệ thì trả về nguyên vẹn
    try:
        ast.parse(code)
        return code
    except SyntaxError:
        pass

    working_code = code

    # Bước 2: Xử lý khối try: bị cắt cụt hoặc thiếu except ở cuối file
    lines = working_code.split("\n")
    last_non_empty_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip():
            last_non_empty_idx = i
            break

    if last_non_empty_idx is not None:
        last_line = lines[last_non_empty_idx]
        indent = len(last_line) - len(last_line.lstrip())
        indent_str = " " * indent
        sub_indent = " " * (indent + 4)

        if re.search(r"^\s*try\s*:\s*$", last_line):
            lines.insert(last_non_empty_idx + 1, f"{sub_indent}pass")
            lines.insert(last_non_empty_idx + 2, f"{indent_str}except Exception:")
            lines.insert(last_non_empty_idx + 3, f"{sub_indent}pass")
            working_code = "\n".join(lines)
        elif re.search(r"^\s*except.*:\s*$", last_line) or re.search(r"^\s*finally\s*:\s*$", last_line):
            lines.insert(last_non_empty_idx + 1, f"{sub_indent}pass")
            working_code = "\n".join(lines)
        elif re.search(r"^\s*(?:if|elif|else|for|while|with|def|class)\b.*:\s*$", last_line):
            lines.insert(last_non_empty_idx + 1, f"{sub_indent}pass")
            working_code = "\n".join(lines)

    try:
        ast.parse(working_code)
        return working_code
    except SyntaxError:
        pass

    # Bước 3: Cân bằng unclosed try... (try có thân nhưng không có except/finally ở cùng indent)
    lines = working_code.split("\n")
    try_stack = []
    for idx, line in enumerate(lines):
        m_try = re.match(r"^(\s*)try\s*:\s*(?:#.*)?$", line)
        if m_try:
            try_stack.append((len(m_try.group(1)), idx))
        else:
            m_handler = re.match(r"^(\s*)(?:except\b|finally\s*:)", line)
            if m_handler:
                h_indent = len(m_handler.group(1))
                for i in range(len(try_stack) - 1, -1, -1):
                    if try_stack[i][0] == h_indent:
                        try_stack.pop(i)
                        break

    if try_stack:
        for t_indent, _ in reversed(try_stack):
            t_ind_str = " " * t_indent
            lines.append(f"{t_ind_str}except Exception:")
            lines.append(f"{t_ind_str}    pass")
        working_code = "\n".join(lines)

    try:
        ast.parse(working_code)
        return working_code
    except SyntaxError:
        pass

    # Bước 4: Cân bằng ngoặc mở chưa đóng (, [, {
    open_chars = []
    in_quote = None
    escaped = False
    for ch in working_code:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if in_quote:
            if ch == in_quote:
                in_quote = None
            continue
        if ch in ("'", '"'):
            in_quote = ch
            continue
        if ch in "([{":
            open_chars.append(ch)
        elif ch in ")]}":
            if open_chars:
                if (ch == ")" and open_chars[-1] == "(") or \
                   (ch == "]" and open_chars[-1] == "[") or \
                   (ch == "}" and open_chars[-1] == "{"):
                    open_chars.pop()

    matching_close = {"(": ")", "[": "]", "{": "}"}
    closers = "".join(matching_close[c] for c in reversed(open_chars))
    if closers:
        candidate_code = working_code + closers
        try:
            ast.parse(candidate_code)
            return candidate_code
        except SyntaxError:
            pass

    # Bước 5: Cắt tỉa các dòng cuối cùng bị đứt đoạn do token limit (cắt tối đa 5 dòng cuối bị lỗi)
    lines = working_code.split("\n")
    for _ in range(min(5, len(lines) - 1)):
        lines.pop()
        candidate = "\n".join(lines)
        try:
            ast.parse(candidate)
            return candidate
        except SyntaxError:
            if "try:" in candidate and "except" not in candidate:
                candidate_with_except = candidate + "\n    except Exception:\n        pass\n"
                try:
                    ast.parse(candidate_with_except)
                    return candidate_with_except
                except SyntaxError:
                    pass

    return code


def _run_code_oneshot(code: str, business_dir: Path, timeout_s: int = 60) -> RunResult:
    """Thực thi một lần (One-shot Fallback) khi không sử dụng persistent daemon."""
    t_start = time.perf_counter()
    clean_c = sanitize_code_syntax(code)
    with tempfile.TemporaryDirectory(prefix="dm_runner_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        code_file = tmp_path / "code.py"
        result_file = tmp_path / "result.json"
        code_file.write_text(clean_c, encoding="utf-8")

        worker_file = Path(__file__).parent / "worker.py"
        src_dir = Path(__file__).resolve().parents[2]

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

            if result_file.exists():
                data = json.loads(result_file.read_text(encoding="utf-8"))
                stdout_str = data.get("stdout", "")
                if len(stdout_str) > 10_000:
                    stdout_str = stdout_str[:10_000]

                unans_source = "none"
                fin_res = data.get("final_result")
                if isinstance(fin_res, dict):
                    unans_source = fin_res.get(
                        "unanswerable_source", data.get("unanswerable_source", "none")
                    )
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
            else:
                err_msg = proc.stderr.strip() if proc.stderr else "SUBPROCESS_CRASHED"
                return RunResult(
                    ok=False,
                    final_result=None,
                    stdout=proc.stdout[:10_000] if proc.stdout else "",
                    error=err_msg,
                    elapsed_ms=elapsed_ms,
                )
        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.perf_counter() - t_start) * 1000)
            return RunResult(
                ok=False,
                final_result=None,
                stdout="",
                error="TIMEOUT: Quá thời gian thực thi cho phép trong sandbox",
                elapsed_ms=elapsed_ms,
                error_type="Timeout",
            )


def run_code(
    code: str,
    business_dir: Path,
    timeout_s: int = 60,
    use_persistent: bool = True,
    as_of_date: Any = None,
) -> RunResult:
    """
    Chạy mã Python/SQL của câu hỏi trong subprocess độc lập.

    Tham số:
        code: Chuỗi mã Python do LLM hoặc người dùng sinh ra (cần gán biến FINAL_RESULT hoặc hàm solution).
        business_dir: Đường dẫn thư mục business (chế độ chỉ đọc).
        timeout_s: Thời gian chờ tối đa (giây).
        use_persistent: Tái sử dụng tiến trình con đã nạp sẵn RAM (mặc định: True, tốc độ tăng gấp 100 lần).

    Trả về:
        RunResult chứa trạng thái thực thi, stdout, error và kết quả. Không bao giờ raise exception.
    """
    if use_persistent:
        try:
            worker = get_or_create_worker(business_dir)
            return worker.execute(code, timeout_s=timeout_s, as_of_date=as_of_date)
        except Exception as e:
            # Nếu khởi tạo persistent worker gặp sự cố, tự động fallback về One-shot
            close_sandbox_worker()
            return _run_code_oneshot(code, business_dir, timeout_s=timeout_s)

    return _run_code_oneshot(code, business_dir, timeout_s=timeout_s)


# ==============================================================================
# CÁC TIỆN ÍCH LÀM SẠCH DỮ LIỆU ĐƯỢC NẠP SẴN VÀO SANDBOX (HELPERS)
# ==============================================================================

def clean_num(series_or_val: Any) -> Any:
    """
    Chuyển đổi an toàn Series, mảng hoặc giá trị đơn lẻ sang kiểu số thực (float/int).
    
    Quy tắc xử lý:
    - Loại bỏ ký hiệu tiền tệ 'đ', 'vnđ', 'vnd', '$', khoảng trắng.
    - Xử lý ngoặc đơn kế toán: '(100)' -> -100.
    - Phân biệt định dạng VN ('1.250.000' hoặc '1.250.000,50') và US ('1,250,000' hoặc '1,250.50').
    - Hỗ trợ từ viết tắt: 'triệu', 'k', 'nghìn'.
    """
    def _parse_scalar(val: Any) -> float:
        if val is None or pd.isna(val):
            return 0.0
        if isinstance(val, (int, float, np.number)):
            if math.isnan(val) or math.isinf(val):
                return 0.0
            return float(val)
        
        s = str(val).strip()
        if not s or s.lower() in ("nan", "none", "null", ""):
            return 0.0
        
        # Ngoặc đơn kế toán: (500) -> -500
        is_negative = False
        if s.startswith("(") and s.endswith(")"):
            is_negative = True
            s = s[1:-1].strip()
        elif s.startswith("-"):
            is_negative = True
            s = s[1:].strip()
            
        s_low = s.lower()
        s_clean = re.sub(r"(?:vnđ|vnd|đ|đồng|\$|(?<=\d|\s)d$)", "", s_low).strip()
        
        multiplier = 1.0
        if "triệu" in s_clean or re.search(r"(?<=\d)\s*tr\b", s_clean):
            multiplier = 1_000_000.0
            s_clean = re.sub(r"triệu|tr\b", "", s_clean).strip()
        elif "nghìn" in s_clean or "ngàn" in s_clean:
            multiplier = 1_000.0
            s_clean = s_clean.replace("nghìn", "").replace("ngàn", "").strip()
        elif s_clean.endswith("k"):
            multiplier = 1_000.0
            s_clean = s_clean[:-1].strip()
            
        # Xử lý dấu phân cách
        if "." in s_clean and "," in s_clean:
            if s_clean.rfind(",") > s_clean.rfind("."):
                # Dạng VN: 1.250.000,50
                s_clean = s_clean.replace(".", "").replace(",", ".")
            else:
                # Dạng US: 1,250,000.50
                s_clean = s_clean.replace(",", "")
        elif "," in s_clean:
            parts = s_clean.split(",")
            # Nếu có multiplier ('1,156tr') hoặc sau dấu phẩy không phải 3 chữ số -> dấu thập phân VN
            if multiplier > 1.0 or (len(parts) == 2 and len(parts[1]) != 3):
                s_clean = s_clean.replace(",", ".")
            else:
                s_clean = s_clean.replace(",", "")
        elif "." in s_clean:
            parts = s_clean.split(".")
            # Nếu có nhiều hơn 1 dấu chấm (1.250.000) hoặc có 3 chữ số sau dấu chấm (1.250) -> phân cách nghìn VN
            if multiplier == 1.0 and (len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and parts[0].isdigit() and int(parts[0]) != 0)):
                s_clean = s_clean.replace(".", "")
                
        try:
            num = float(s_clean) * multiplier
            return -num if is_negative else num
        except Exception:
            # Dự phòng regex bóc tách chữ số nếu vẫn còn lẫn text
            m = re.search(r"[-+]?\d*\.?\d+", s_clean)
            if m:
                try:
                    num = float(m.group(0)) * multiplier
                    return -num if is_negative else num
                except Exception:
                    return 0.0
            return 0.0

    if isinstance(series_or_val, pd.Series):
        s = series_or_val
        if pd.api.types.is_bool_dtype(s):
            return s.fillna(False).astype(float)
        if pd.api.types.is_numeric_dtype(s):
            return pd.to_numeric(s, errors="coerce").fillna(0.0).astype(float)

        s_str = s.astype(str).str.strip()
        is_null = s_str.isin(["", "nan", "None", "null", "NaN", "NAT", "NaT"]) | s.isna()
        s_clean = s_str.str.replace(r"(?i)\s*(?:vnđ|vnd|đ|đồng|\$|(?<=\d|\s)d)\b", "", regex=True)
        is_neg = (s_clean.str.startswith("(") & s_clean.str.endswith(")")) | s_clean.str.startswith("-")
        s_clean = s_clean.str.strip("()").str.lstrip("-").str.strip()

        # Nếu có dấu chấm có khả năng là phân cách hàng nghìn (ví dụ 396.000 hoặc 1.250.000 hoặc 396.000đ),
        # KHÔNG dùng pd.to_numeric trực tiếp vì nó sẽ parse 396.000 thành 396.0!
        has_dot_thousand = s_clean.str.contains(r"\.\d{3}(?:\.|\b|$)", regex=True, na=False).any()

        if not has_dot_thousand:
            # Đường đi nhanh cho số không có dấu chấm phân cách hàng nghìn (chỉ có dấu phẩy hoặc số nguyên)
            s_no_comma = s_clean.str.replace(",", "", regex=False)
            num_res = pd.to_numeric(s_no_comma, errors="coerce")

            if (~is_null & num_res.isna()).sum() == 0:
                res = num_res.fillna(0.0).astype(float)
                res[is_neg] = -res[is_neg]
                return res

        return s.apply(_parse_scalar)
    elif isinstance(series_or_val, (list, tuple)):
        return [_parse_scalar(x) for x in series_or_val]
    elif isinstance(series_or_val, np.ndarray):
        return np.vectorize(_parse_scalar)(series_or_val)
    else:
        return _parse_scalar(series_or_val)


def clean_date(series_or_val: Any, dayfirst: Optional[bool] = None, **kwargs) -> Any:
    """
    Chuyển đổi an toàn sang chuẩn pd.to_datetime:
    - Thay thế tiền tố tháng tiếng Việt: 'thg', 'tháng' -> '/'.
    - Xử lý số serial ngày của Excel (30000 đến 60000) với origin='1899-12-30'.
    - Nếu dữ liệu dạng ISO ('2025-10-05'): Luôn giữ chuẩn YYYY-MM-DD.
    - Mặc định dayfirst=True cho dữ liệu Việt Nam ('05/10/2025').
    """
    use_df = dayfirst if dayfirst is not None else True

    def _parse_scalar(val: Any) -> Any:
        if val is None or pd.isna(val):
            return pd.NaT
        if isinstance(val, (pd.Timestamp, datetime.date, datetime.datetime)):
            return pd.to_datetime(val)
        if isinstance(val, (int, float)):
            if 30000 <= val <= 60000:
                try:
                    return pd.to_datetime(int(val), unit="D", origin="1899-12-30")
                except Exception:
                    pass
            return pd.to_datetime(val, errors="coerce")
        s = str(val).strip()
        if not s or s.lower() in ("nan", "none", "null", "nat"):
            return pd.NaT
        # Excel serial dạng chuỗi: '45658' hoặc '45658.0'
        m_serial = re.match(r"^(\d{5})(?:\.0+)?$", s)
        if m_serial:
            v = int(m_serial.group(1))
            if 30000 <= v <= 60000:
                try:
                    return pd.to_datetime(v, unit="D", origin="1899-12-30")
                except Exception:
                    pass
        # Chuẩn hóa tháng tiếng Việt: 'thg 1', 'tháng 1' -> '/ 1'
        s = re.sub(r"\b(?:thg|tháng|thg\.)\s*", "/", s, flags=re.IGNORECASE)
        # Nếu chuỗi bắt đầu bằng 4 chữ số (YYYY-MM-DD...) -> Tuyệt đối không đảo ngày tháng
        if re.match(r"^\d{4}[-/]", s):
            try:
                return pd.to_datetime(s, dayfirst=False)
            except Exception:
                return pd.to_datetime(s, errors="coerce")
        try:
            return pd.to_datetime(s, dayfirst=use_df, errors="coerce")
        except Exception:
            return pd.NaT

    if isinstance(series_or_val, pd.Series):
        s = series_or_val
        if pd.api.types.is_datetime64_any_dtype(s):
            return s

        # Xử lý chuỗi và thay thế 'thg' / 'tháng'
        s_str = s.astype(str).str.strip()
        s_str = s_str.str.replace(r"\b(?:thg|tháng|thg\.)\s*", "/", regex=True, case=False)

        # Kiểm tra nếu chuỗi định dạng ISO bắt đầu bằng năm (YYYY-MM-DD...), không dùng dayfirst
        is_null = s.isna() | s_str.isin(["nan", "None", "null", "NaT", ""])
        is_iso = (~is_null) & s_str.str.match(r"^\d{4}[-/]").fillna(False)

        # Kiểm tra Excel serials
        s_num = pd.to_numeric(s_str, errors="coerce")
        is_serial = (~is_null) & (s_num >= 30000) & (s_num <= 60000)

        if is_serial.all():
            return pd.to_datetime(s_num.astype(int), unit="D", origin="1899-12-30", errors="coerce")

        res = pd.Series(pd.NaT, index=s.index, dtype="datetime64[us]")
        if is_serial.any():
            serials_dt = pd.to_datetime(s_num[is_serial].astype(int), unit="D", origin="1899-12-30")
            res.update(serials_dt)

        rem_iso = is_iso & (~is_serial)
        if rem_iso.any():
            try:
                iso_dt = pd.to_datetime(s_str[rem_iso], dayfirst=False, format="mixed", errors="coerce")
            except Exception:
                iso_dt = pd.to_datetime(s_str[rem_iso], dayfirst=False, errors="coerce")
            res.update(iso_dt)

        rem_other = (~is_null) & (~is_serial) & (~is_iso)
        if rem_other.any():
            try:
                other_dt = pd.to_datetime(s_str[rem_other], dayfirst=use_df, format="mixed", errors="coerce")
            except Exception:
                other_dt = pd.to_datetime(s_str[rem_other], dayfirst=use_df, errors="coerce")
            res.update(other_dt)

        return res

    elif isinstance(series_or_val, (list, tuple)):
        return [_parse_scalar(x) for x in series_or_val]
    else:
        return _parse_scalar(series_or_val)


def _patch_pandas_date_comparisons():
    """
    Đảm bảo so sánh an toàn giữa pd.Series / pd.Timestamp và datetime.date
    mà không raise TypeError: 'Invalid comparison between dtype=datetime64 and date'
    hoặc TypeError: 'Cannot compare Timestamp with datetime.date'.
    """
    import datetime

    ops = ["__ge__", "__le__", "__gt__", "__lt__", "__eq__", "__ne__"]

    # 1. Patch pd.Series
    for op_name in ops:
        orig = getattr(pd.Series, op_name, None)
        if orig and not getattr(orig, "_is_date_resilient", False):
            def _make_series_op(orig_op):
                def _wrapped(self, other):
                    if isinstance(other, datetime.date) and not isinstance(other, datetime.datetime):
                        if pd.api.types.is_datetime64_any_dtype(self):
                            return orig_op(self, pd.Timestamp(other))
                        elif self.dtype == object or str(self.dtype).startswith("string"):
                            return orig_op(self.astype(str).str[:10], other.isoformat())
                    return orig_op(self, other)
                _wrapped._is_date_resilient = True
                return _wrapped
            try:
                setattr(pd.Series, op_name, _make_series_op(orig))
            except Exception:
                pass

    # 2. Patch pd.Timestamp
    for op_name in ops:
        orig = getattr(pd.Timestamp, op_name, None)
        if orig and not getattr(orig, "_is_date_resilient", False):
            def _make_ts_op(orig_op):
                def _wrapped(self, other):
                    if isinstance(other, datetime.date) and not isinstance(other, datetime.datetime):
                        return orig_op(self, pd.Timestamp(other))
                    return orig_op(self, other)
                _wrapped._is_date_resilient = True
                return _wrapped
            try:
                setattr(pd.Timestamp, op_name, _make_ts_op(orig))
            except Exception:
                pass


def _strip_accents(text: Any) -> str:
    """Loại bỏ dấu tiếng Việt để so khớp mềm dẻo (NFKD/NFD)."""
    s = str(text).replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _norm_col_key(text: Any) -> str:
    """Chuẩn hóa tên cột trong sandbox: bỏ dấu, lowercase, thay _ và - bằng khoảng trắng."""
    s = _strip_accents(text).lower()
    s = re.sub(r"[_\-./()]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def should_retry_self_correction(
    exec_err: Optional[str],
    sanity_err: Optional[str],
    err_type: Optional[str] = None,
) -> bool:
    """
    Bước 3: Với lỗi DataNotFoundError (lỗi schema / không tìm thấy bảng hoặc cột)
    thì KHÔNG chạy vòng tự sửa lỗi bằng LLM, vì các retry sinh lại đúng code cũ và tốn thời gian.
    """
    if err_type == "DataNotFoundError":
        return False
    err_str = str(exec_err or "")
    if "DataNotFoundError" in err_str or "Không tìm thấy bảng" in err_str or "Không tìm thấy cột" in err_str:
        return False
    return bool(exec_err or sanity_err)


def filter_valid_sales(
    df: pd.DataFrame,
    data: Optional[Dict[str, Any]] = None,
    as_of_date: Optional[str] = None,
    *args: Any,
    **kwargs: Any,
) -> pd.DataFrame:
    """
    Hàm tiện ích chuẩn hóa đơn hàng hợp lệ theo Điều 1 Rulebook:
    1. Loại bỏ đơn hủy, trả hàng, hoàn hàng, không giao được, nháp theo cột trạng thái (nếu có).
       (Chú ý: KHÔNG loại 'Đã hoàn thành' / 'Hoàn tất').
    2. Nếu một mã đơn có dòng bị trả 1 phần -> loại bỏ toàn bộ mã đơn đó.
    3. Nếu cửa hàng có bảng/sheet trả hàng riêng trong `data`, loại bỏ mọi mã đơn
       xuất hiện trong bảng trả hàng có ngày trả <= as_of_date.
    4. Hỗ trợ tương thích khi mã LLM truyền `(df, date_col, start_date, end_date)`.
    """
    if df is None or df.empty:
        return df

    out = df.copy()
    cols = list(out.columns)
    order_col = next(
        (c for c in cols if any(k in _norm_col_key(c) for k in [
            "ma don", "ma hoa don", "ma hd", "order id", "ma chung tu", "so ct", "ma gd", "so phieu"
        ])),
        None,
    )
    status_col = next(
        (c for c in cols if any(k in _norm_col_key(c) for k in [
            "trang thai", "tinh trang", "status", "ghi chu tt", "xu ly"
        ])),
        None,
    )

    if status_col:
        # Tránh khớp nhầm chữ 'hoàn' trong 'Đã hoàn thành' / 'Hoàn tất'
        inv_mask = out[status_col].astype(str).str.contains(
            r"hủy|huỷ|huy|trả|tra|hoàn(?!\s*(?:thành|tất))|hoan(?!\s*(?:thanh|tat))|không\s*giao\s*được|khong\s*giao\s*duoc|nháp|nhap|cancel|return|draft",
            case=False,
            na=False,
        )
        if order_col and inv_mask.any():
            bad_orders = set(out.loc[inv_mask, order_col].dropna().astype(str).str.strip())
            bad_orders.discard("")
            bad_orders.discard("nan")
            if bad_orders:
                out = out[~out[order_col].astype(str).str.strip().isin(bad_orders)]
        else:
            out = out[~inv_mask]

    # Nếu LLM gọi filter_valid_sales(df, date_col, start_date, end_date)
    if isinstance(data, str) and data in out.columns and as_of_date is not None and len(args) >= 1:
        date_col_arg = data
        start_arg = as_of_date
        end_arg = args[0]
        try:
            dt_col = clean_date(out[date_col_arg])
            s_ts = clean_date(start_arg)
            e_ts = clean_date(end_arg)
            if pd.notna(s_ts) and pd.notna(e_ts):
                out = out[(dt_col >= s_ts) & (dt_col <= e_ts)]
        except Exception:
            pass
        return out

    # Kiểm tra bảng trả hàng riêng trong `data` (Luật §1: chỉ coi là đã trả nếu ngày trả <= as_of_date)
    if data and order_col and isinstance(data, dict):
        returned_orders = set()
        for t_name, t_df in data.items():
            if not isinstance(t_df, pd.DataFrame) or t_df.empty:
                continue
            tn_norm = _norm_col_key(t_name)
            if any(k in tn_norm for k in ["tra hang", "trahang", "phieutra", "hoanhang", "return"]):
                r_cols = list(t_df.columns)
                r_ord = next(
                    (c for c in r_cols if any(k in _norm_col_key(c) for k in [
                        "ma don", "ma hoa don", "ma hd", "order id", "ma chung tu", "so ct", "ma gd", "so phieu"
                    ])),
                    None,
                )
                if not r_ord:
                    continue
                sub_ret = t_df
                if as_of_date:
                    r_date = next(
                        (c for c in r_cols if any(k in _norm_col_key(c) for k in [
                            "ngay", "date", "thoi gian"
                        ])),
                        None,
                    )
                    if r_date:
                        dt_s = clean_date(sub_ret[r_date])
                        sub_ret = sub_ret[dt_s.dt.date <= pd.to_datetime(as_of_date).date()]
                for oid in sub_ret[r_ord].dropna().astype(str).str.strip():
                    if oid and oid.lower() != "nan":
                        returned_orders.add(oid)
        if returned_orders:
            out = out[~out[order_col].astype(str).str.strip().isin(returned_orders)]

    return out


def convert_to_base_qty(
    df: pd.DataFrame,
    data: Optional[Dict[str, Any]] = None,
    qty_col: Optional[str] = None,
    unit_col: Optional[str] = None,
    item_col: Optional[str] = None,
) -> pd.Series:
    """
    Hàm tiện ích quy đổi số lượng về đơn vị cơ sở nhỏ nhất theo Điều 3 & Điều 10 Rulebook.
    Tự động tra cứu bảng DanhSachQuyDoi / QuyDoiDonVi trong `data` (nếu có).
    Trả về pd.Series số lượng đã nhân hệ số quy đổi.
    """
    if df is None or df.empty:
        return pd.Series(dtype=float)

    cols = list(df.columns)
    if not qty_col or qty_col not in cols:
        qty_col = next(
            (c for c in cols if any(k in _strip_accents(str(c)).lower() for k in [
                "so luong", "soluong", "sl", "khoi luong", "trong luong", "qty"
            ])),
            None,
        )
    if not qty_col:
        return pd.Series(0.0, index=df.index)

    base_q = clean_num(df[qty_col])
    if not data or not isinstance(data, dict):
        return base_q

    if not unit_col or unit_col not in cols:
        unit_col = next(
            (c for c in cols if any(k in _strip_accents(str(c)).lower() for k in [
                "don vi", "dvt", "unit"
            ])),
            None,
        )
    if not item_col or item_col not in cols:
        item_col = next(
            (c for c in cols if any(k in _strip_accents(str(c)).lower() for k in [
                "ma hang", "ma sp", "ten hang", "san pham", "mat hang", "hang", "mon"
            ])),
            None,
        )
    if not unit_col:
        return base_q

    # Tìm bảng quy đổi trong data
    conv_map = {}
    for t_name, t_df in data.items():
        if not isinstance(t_df, pd.DataFrame) or t_df.empty:
            continue
        tn_norm = _strip_accents(str(t_name)).lower()
        if any(k in tn_norm for k in ["quydoi", "quy_doi", "donvi", "danhmuc", "hanghoa", "sanpham"]):
            t_cols = list(t_df.columns)
            f_col = next(
                (c for c in t_cols if any(k in _strip_accents(str(c)).lower() for k in [
                    "he so", "ty le quy doi", "quy cach", "so luong quy doi", "sl quy doi"
                ])),
                None,
            )
            u_col = next(
                (c for c in t_cols if any(k in _strip_accents(str(c)).lower() for k in [
                    "don vi lon", "dvt lon", "don vi quy doi", "don vi ban", "don vi tinh", "dvt"
                ])),
                None,
            )
            i_col = next(
                (c for c in t_cols if any(k in _strip_accents(str(c)).lower() for k in [
                    "ma hang", "ma sp", "ten hang", "san pham", "mat hang"
                ])),
                None,
            )
            if f_col and u_col:
                for _, r in t_df.iterrows():
                    try:
                        fv = float(clean_num(r[f_col]))
                        if fv <= 0:
                            continue
                        uk = _strip_accents(str(r[u_col])).lower().strip()
                        ik = _strip_accents(str(r[i_col])).lower().strip() if i_col and not pd.isna(r[i_col]) else "*"
                        conv_map[(ik, uk)] = fv
                        if ("*", uk) not in conv_map:
                            conv_map[("*", uk)] = fv
                    except Exception:
                        continue

    if not conv_map:
        return base_q

    multipliers = []
    for idx, r in df.iterrows():
        u_val = _strip_accents(str(r[unit_col])).lower().strip() if not pd.isna(r[unit_col]) else ""
        i_val = _strip_accents(str(r[item_col])).lower().strip() if (item_col and not pd.isna(r[item_col])) else "*"
        mult = conv_map.get((i_val, u_val), conv_map.get(("*", u_val), 1.0))
        multipliers.append(mult)

    return base_q * pd.Series(multipliers, index=df.index, dtype=float)


def _patch_pandas_str_contains():
    """
    Bổ sung cơ chế fallback so khớp không dấu (diacritic-insensitive unidecode)
    cho pd.Series.str.contains khi so khớp trực tiếp trả về 0 dòng khớp.
    """
    try:
        from pandas.core.strings.accessor import StringMethods
    except ImportError:
        return

    orig_contains = getattr(StringMethods, "contains", None)
    if orig_contains and not getattr(orig_contains, "_is_diacritic_resilient", False):
        def _resilient_contains(self, pat, case=True, flags=0, na=None, regex=True):
            res = orig_contains(self, pat, case=case, flags=flags, na=na, regex=regex)
            try:
                # Nếu so khớp trực tiếp trả về 0 kết quả True, thử fallback qua phiên bản bỏ dấu tiếng Việt
                if isinstance(pat, str) and not bool((res == True).any()):
                    s_orig = getattr(self, "_data", None)
                    if s_orig is None:
                        s_orig = getattr(self, "_orig", None)
                    if s_orig is not None and len(s_orig) > 0:
                        s_unaccent = s_orig.astype(str).map(_strip_accents)
                        pat_unaccent = _strip_accents(pat)
                        # Thử trước với thiết lập case gốc
                        fallback_res = orig_contains(s_unaccent.str, pat_unaccent, case=case, flags=flags, na=na, regex=regex)
                        if bool((fallback_res == True).any()):
                            return fallback_res
                        # Nếu vẫn không khớp và case=True, thử thêm fallback không phân biệt hoa thường case=False
                        if case:
                            fallback_res_ci = orig_contains(s_unaccent.str, pat_unaccent, case=False, flags=flags, na=na, regex=regex)
                            if bool((fallback_res_ci == True).any()):
                                return fallback_res_ci
                        # Nếu pat có tiền tố chung như 'nhóm ', 'loại ', 'mặt hàng ', 'sản phẩm ', thử bỏ tiền tố
                        pat_stripped = re.sub(
                            r"^(?:nhom\s*hang|loai\s*hang|nhom|loai|mat\s*hang|san\s*pham)\s+",
                            "",
                            pat_unaccent.strip(),
                            flags=re.IGNORECASE,
                        ).strip()
                        if pat_stripped and pat_stripped != pat_unaccent.strip():
                            fallback_stripped = orig_contains(s_unaccent.str, pat_stripped, case=False, flags=flags, na=na, regex=regex)
                            if bool((fallback_stripped == True).any()):
                                return fallback_stripped
            except Exception:
                pass
            return res

        _resilient_contains._is_diacritic_resilient = True
        try:
            StringMethods.contains = _resilient_contains
        except Exception:
            pass


def _select_sales_df(data_or_df: Any, require_product: bool = False) -> tuple[Optional[pd.DataFrame], Optional[dict]]:
    """Chọn bảng bán hàng phù hợp nhất từ dict data hoặc trả về DataFrame trực tiếp."""
    if isinstance(data_or_df, pd.DataFrame):
        return data_or_df.copy(), None
    if hasattr(data_or_df, "tables"):
        d_map = {t.table_id: t.df for t in getattr(data_or_df, "tables", []) if t.df is not None}
    elif isinstance(data_or_df, dict):
        d_map = data_or_df
    else:
        return None, None

    def _norm(s: Any) -> str:
        s_str = str(s).strip().lower().replace("đ", "d").replace("Đ", "d")
        s_str = "".join(c for c in unicodedata.normalize("NFD", s_str) if unicodedata.category(c) != "Mn")
        return re.sub(r"[^a-z0-9]+", " ", s_str).strip()

    detail_candidates: list[tuple[str, pd.DataFrame]] = []
    header_candidates: list[tuple[str, pd.DataFrame]] = []
    seen_ids: set[int] = set()

    for name, df in d_map.items():
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        if id(df) in seen_ids:
            continue
        n_norm = _norm(name)
        if any(k in n_norm for k in ["nhap", "ton kho", "tonkho", "the kho", "thekho", "chi phi", "chiphi", "ncc", "bang gia", "banggia", "quy doi", "quydoi", "don vi", "donvi", "khach hang", "khachhang", "san pham", "sanpham", "danh muc", "danhmuc", "thanh toan", "thanhtoan", "lo"]):
            continue
        cols_norm = [_norm(c) for c in df.columns]
        has_date = any(any(k in cn for k in ["ngay", "date", "thoi gian"]) for cn in cols_norm)
        has_amt = any(any(k in cn for k in ["thanh tien", "t tien", "tien ban", "tri gia", "tong tien", "doanh thu", "amount"]) for cn in cols_norm)
        if not (has_date and has_amt):
            continue
        seen_ids.add(id(df))
        if any(k in n_norm for k in ["chi tiet", "chitiet", "detail", "so ban hang", "sobanhang", "ban hang", "banhang"]):
            detail_candidates.append((name, df))
        else:
            header_candidates.append((name, df))

    target_list = detail_candidates if (detail_candidates or require_product) else header_candidates
    if not target_list:
        target_list = header_candidates or detail_candidates
    if not target_list:
        return None, d_map

    if len(target_list) == 1:
        return target_list[0][1].copy(), d_map

    # Nếu có các bảng phân mảnh theo kỳ (_1, _2, _2025, _2026) cùng cấu trúc cột, gộp lại
    first_name, first_df = target_list[0]
    first_cols = set(first_df.columns)
    shards = [df for _, df in target_list if set(df.columns) == first_cols]
    if len(shards) > 1:
        return pd.concat(shards, ignore_index=True), d_map
    return first_df.copy(), d_map


def _find_line_revenue_col(df: pd.DataFrame, order_col: Optional[str] = None) -> Optional[str]:
    """
    Chọn cột doanh thu dòng hàng theo Điều 1 Rulebook:
    - Sau chiết khấu cấp dòng, không trừ voucher cấp đơn, không gồm VAT và phí giao hàng.
    - Tránh chọn các cột cấp đơn bị forward-fill lặp lại trên từng dòng sản phẩm (như Tổng bill, Khách trả, Còn lại).
    """
    def _norm(s: Any) -> str:
        s_str = str(s).strip().lower().replace("đ", "d").replace("Đ", "d")
        s_str = "".join(c for c in unicodedata.normalize("NFD", s_str) if unicodedata.category(c) != "Mn")
        return re.sub(r"[^a-z0-9]+", " ", s_str).strip()

    cols = list(df.columns)
    forbidden = ["vat", "thue", "tax", "ship", "giao hang", "van chuyen", "voucher", "khach tra", "khach dua", "con lai", "con no", "tong bill", "tong thanh toan", "gia von", "gia nhap", "don gia", "gia san pham", "gia ban", "gia le"]

    # Ưu tiên 1: Cột thành tiền cấp dòng rõ ràng
    line_priority = ["thanh tien", "t tien", "tien ban", "tri gia", "tien hang", "line total", "amount"]
    for kw in line_priority:
        for c in cols:
            cn = _norm(c)
            if kw in cn and not any(f in cn for f in forbidden):
                return c

    # Ưu tiên 2: Cột tổng tiền / doanh thu (nhưng phải kiểm tra xem có bị lặp cấp đơn không)
    fallback_priority = ["tong tien", "doanh thu", "tong"]
    for kw in fallback_priority:
        for c in cols:
            cn = _norm(c)
            if (cn == kw or kw in cn) and not any(f in cn for f in forbidden):
                return c
    return None


def revenue(
    data_or_df: Any,
    start_date: Any = None,
    end_date: Any = None,
    as_of_date: Any = None,
    product: Optional[str] = None,
    customer: Optional[str] = None,
) -> int:
    """
    Hàm tính Doanh thu tất định theo đúng Điều 1 & Điều 5 Rulebook:
    - Doanh thu = tổng giá trị các dòng hàng đã bán sau chiết khấu cấp dòng;
      không trừ giảm giá/voucher cấp đơn; không gồm VAT và phí giao hàng.
    - Loại CẢ ĐƠN nếu đơn bị hủy hoặc có bất kỳ mặt hàng nào bị trả (dù chỉ trả 1 phần).
    - Tránh cộng lặp các cột cấp đơn (Tổng bill, Khách trả) bị forward-fill trên nhiều dòng sản phẩm.
    - Tự động lọc bỏ bản ghi sau ngày as_of_date (nếu có).
    """
    df, d_map = _select_sales_df(data_or_df, require_product=bool(product))
    if df is None or df.empty:
        return 0

    def _norm(s: Any) -> str:
        s_str = str(s).strip().lower().replace("đ", "d").replace("Đ", "d")
        s_str = "".join(c for c in unicodedata.normalize("NFD", s_str) if unicodedata.category(c) != "Mn")
        return re.sub(r"[^a-z0-9]+", " ", s_str).strip()

    # 1. Loại cả đơn nếu đơn bị hủy hoặc có bất kỳ mặt hàng nào bị trả (gồm cả trả 1 phần / trả theo lô / dòng âm)
    df = filter_valid_sales(df, data=d_map, as_of_date=str(as_of_date)[:10] if as_of_date else None)
    if df.empty:
        return 0

    cols = list(df.columns)
    order_col = next(
        (c for c in cols if any(k in _norm(c) for k in ["ma don", "ma hoa don", "ma hd", "order id", "ma chung tu", "so ct", "ma gd", "so phieu"])),
        None,
    )
    qty_col = next(
        (c for c in cols if any(k in _norm(c) for k in ["so luong", "sl", "qty"]) and "quy doi" not in _norm(c) and "tra" not in _norm(c)),
        None,
    )
    if qty_col and order_col:
        q_num = clean_num(df[qty_col])
        if (q_num < 0).any():
            neg_ords = set(df.loc[q_num < 0, order_col].dropna().astype(str).str.strip())
            df = df[~df[order_col].astype(str).str.strip().isin(neg_ords)]
            if df.empty:
                return 0

    # 2. Lọc theo ngày (start_date, end_date, as_of_date)
    date_col = next(
        (c for c in cols if any(k in _norm(c) for k in ["ngay", "date", "thoi gian"])),
        None,
    )
    if date_col:
        dt_series = clean_date(df[date_col])
        if as_of_date is not None:
            as_of_dt = pd.to_datetime(str(as_of_date)[:10], errors="coerce")
            if pd.notna(as_of_dt):
                df = df[dt_series.dt.date <= as_of_dt.date()]
                dt_series = dt_series.loc[df.index]
        if start_date is not None:
            s_dt = pd.to_datetime(str(start_date)[:10], errors="coerce")
            if pd.notna(s_dt):
                df = df[dt_series.dt.date >= s_dt.date()]
                dt_series = dt_series.loc[df.index]
        if end_date is not None:
            e_dt = pd.to_datetime(str(end_date)[:10], errors="coerce")
            if pd.notna(e_dt):
                df = df[dt_series.dt.date <= e_dt.date()]
                dt_series = dt_series.loc[df.index]

    if df.empty:
        return 0

    # 3. Lọc theo sản phẩm / khách hàng nếu được truyền vào
    if product:
        prod_col = next(
            (c for c in cols if any(k in _norm(c) for k in ["ten hang", "ten san pham", "ten mon", "san pham", "mat hang", "hang hoa", "hang"])),
            None,
        )
        cat_col = next(
            (c for c in cols if any(k in _norm(c) for k in ["nhom hang", "loai hang", "danh muc", "nhom sp", "category"])),
            None,
        )
        p_clean = re.sub(
            r"^(?:nhom\s*hang|loai\s*hang|nhom|loai|mat\s*hang|san\s*pham)\s+",
            "",
            _norm(product),
        ).strip() or _norm(product)
        masks = []
        if prod_col:
            p_norm_series = df[prod_col].astype(str).apply(_norm)
            masks.append(p_norm_series.str.contains(p_clean, regex=False, na=False) | df[prod_col].astype(str).str.contains(str(product), case=False, na=False))
        if cat_col:
            c_norm_series = df[cat_col].astype(str).apply(_norm)
            masks.append(c_norm_series.str.contains(p_clean, regex=False, na=False) | df[cat_col].astype(str).str.contains(str(product), case=False, na=False))
        if masks:
            final_m = masks[0]
            for m in masks[1:]:
                final_m = final_m | m
            df = df[final_m]
    if customer:
        cust_col = next(
            (c for c in cols if any(k in _norm(c) for k in ["khach hang", "ten khach", "khach", "so kh", "ma kh"])),
            None,
        )
        if cust_col:
            df = df[df[cust_col].astype(str).str.contains(str(customer), case=False, na=False)]

    if df.empty:
        return 0

    amt_col = _find_line_revenue_col(df, order_col=order_col)
    if not amt_col:
        return 0

    return int(round(float(clean_num(df[amt_col]).sum())))


def count_orders(
    data_or_df: Any,
    start_date: Any = None,
    end_date: Any = None,
    as_of_date: Any = None,
    status: str = "valid",
    product: Optional[str] = None,
    customer: Optional[str] = None,
) -> int:
    """
    Hàm đếm số đơn hàng tất định theo Điều 1 Rulebook:
    - Mặc định (status='valid'): loại bỏ toàn bộ đơn bị hủy và đơn có bất kỳ mặt hàng nào bị trả,
      sau đó đếm số mã đơn duy nhất (nunique).
    - Nếu status='cancelled' / 'hủy': chỉ đếm số mã đơn duy nhất bị hủy.
    - Nếu status='returned' / 'trả': chỉ đếm số mã đơn duy nhất bị trả hàng.
    """
    df, d_map = _select_sales_df(data_or_df, require_product=bool(product))
    if df is None or df.empty:
        return 0

    def _norm(s: Any) -> str:
        s_str = str(s).strip().lower().replace("đ", "d").replace("Đ", "d")
        s_str = "".join(c for c in unicodedata.normalize("NFD", s_str) if unicodedata.category(c) != "Mn")
        return re.sub(r"[^a-z0-9]+", " ", s_str).strip()

    cols = list(df.columns)
    order_col = next(
        (c for c in cols if any(k in _norm(c) for k in ["ma don", "ma hoa don", "ma hd", "order id", "ma chung tu", "so ct", "ma gd", "so phieu"])),
        None,
    )
    status_col = next(
        (c for c in cols if any(k in _norm(c) for k in ["trang thai", "tinh trang", "status", "ghi chu tt", "xu ly"])),
        None,
    )

    st_mode = _norm(status)
    if st_mode in ("valid", "hop le", "thanh cong", "completed"):
        df = filter_valid_sales(df, data=d_map, as_of_date=str(as_of_date)[:10] if as_of_date else None)
    elif any(k in st_mode for k in ["cancel", "huy"]):
        if status_col:
            df = df[df[status_col].astype(str).str.contains(r"hủy|huỷ|huy|cancel", case=False, na=False)]
    elif any(k in st_mode for k in ["return", "tra", "hoan"]):
        if status_col:
            df = df[df[status_col].astype(str).str.contains(r"trả|tra|hoàn(?!\s*(?:thành|tất))|hoan(?!\s*(?:thanh|tat))|return", case=False, na=False)]

    if df.empty:
        return 0

    date_col = next(
        (c for c in cols if any(k in _norm(c) for k in ["ngay", "date", "thoi gian"])),
        None,
    )
    if date_col:
        dt_series = clean_date(df[date_col])
        if as_of_date is not None:
            as_of_dt = pd.to_datetime(str(as_of_date)[:10], errors="coerce")
            if pd.notna(as_of_dt):
                df = df[dt_series.dt.date <= as_of_dt.date()]
                dt_series = dt_series.loc[df.index]
        if start_date is not None:
            s_dt = pd.to_datetime(str(start_date)[:10], errors="coerce")
            if pd.notna(s_dt):
                df = df[dt_series.dt.date >= s_dt.date()]
                dt_series = dt_series.loc[df.index]
        if end_date is not None:
            e_dt = pd.to_datetime(str(end_date)[:10], errors="coerce")
            if pd.notna(e_dt):
                df = df[dt_series.dt.date <= e_dt.date()]
                dt_series = dt_series.loc[df.index]

    if df.empty:
        return 0

    if product:
        prod_col = next(
            (c for c in cols if any(k in _norm(c) for k in ["ten hang", "ten san pham", "ten mon", "san pham", "mat hang", "hang hoa", "hang"])),
            None,
        )
        if prod_col:
            df = df[df[prod_col].astype(str).str.contains(str(product), case=False, na=False)]
    if customer:
        cust_col = next(
            (c for c in cols if any(k in _norm(c) for k in ["khach hang", "ten khach", "khach", "so kh", "ma kh"])),
            None,
        )
        if cust_col:
            df = df[df[cust_col].astype(str).str.contains(str(customer), case=False, na=False)]

    if df.empty:
        return 0

    if order_col and order_col in df.columns:
        return int(df[order_col].dropna().astype(str).str.strip().replace("", np.nan).dropna().nunique())
    return int(len(df))


def debt(
    data_or_df: Any,
    end_date: Any = None,
    as_of_date: Any = None,
    customer: Optional[str] = None,
) -> int:
    """
    Hàm tính tổng công nợ còn lại của khách hàng tính đến hết ngày end_date / as_of_date:
    - Tìm bảng có cột nợ cấp đơn ('Còn lại', 'Còn nợ', 'Dư nợ', 'Tiền nợ').
    - Khử trùng lặp theo Mã đơn hàng nếu bảng ở cấp dòng để không bao giờ cộng lặp nợ cấp đơn.
    - Chỉ tính các đơn đã hoàn thành / hợp lệ (loại đơn hủy, trả hàng, hoặc đang giao chưa tất toán).
    """
    def _norm(s: Any) -> str:
        s_str = str(s).strip().lower().replace("đ", "d").replace("Đ", "d")
        s_str = "".join(c for c in unicodedata.normalize("NFD", s_str) if unicodedata.category(c) != "Mn")
        return re.sub(r"[^a-z0-9]+", " ", s_str).strip()

    target_df: Optional[pd.DataFrame] = None
    debt_col: Optional[str] = None

    if isinstance(data_or_df, pd.DataFrame):
        target_df = data_or_df.copy()
        debt_col = next((c for c in target_df.columns if any(k in _norm(c) for k in ["con lai", "con no", "du no", "tien no"])), None)
    elif isinstance(data_or_df, dict):
        for name, df in data_or_df.items():
            if not isinstance(df, pd.DataFrame) or df.empty:
                continue
            dc = next((c for c in df.columns if any(k in _norm(c) for k in ["con lai", "con no", "du no", "tien no"])), None)
            if dc:
                target_df = df.copy()
                debt_col = dc
                break

    if target_df is None or not debt_col:
        return 0

    cols = list(target_df.columns)
    status_col = next(
        (c for c in cols if any(k in _norm(c) for k in ["trang thai", "tinh trang", "status", "ghi chu tt", "xu ly"])),
        None,
    )
    if status_col:
        target_df = target_df[
            ~target_df[status_col].astype(str).str.contains(
                r"hủy|huỷ|huy|trả|tra|hoàn(?!\s*(?:thành|tất))|hoan(?!\s*(?:thanh|tat))|cancel|return|shipping|đang\s*giao|dang\s*giao|nháp|draft",
                case=False,
                na=False,
            )
        ]

    cutoff = end_date or as_of_date
    date_col = next(
        (c for c in cols if any(k in _norm(c) for k in ["ngay", "date", "thoi gian"])),
        None,
    )
    if date_col and cutoff is not None:
        dt_s = clean_date(target_df[date_col])
        c_dt = pd.to_datetime(str(cutoff)[:10], errors="coerce")
        if pd.notna(c_dt):
            target_df = target_df[dt_s.dt.date <= c_dt.date()]

    if target_df.empty:
        return 0

    order_col = next(
        (c for c in cols if any(k in _norm(c) for k in ["ma don", "ma hoa don", "ma hd", "order id", "ma chung tu", "so ct", "ma gd", "so phieu"])),
        None,
    )
    if order_col and order_col in target_df.columns:
        target_df = target_df.drop_duplicates(subset=[order_col], keep="first")

    return int(round(float(clean_num(target_df[debt_col]).sum())))


def _patch_pandas_groupby_numeric():
    """
    Đảm bảo SeriesGroupBy.sum() và SeriesGroupBy.mean() tự động chuyển chuỗi số
    qua clean_num() thay vì nối chuỗi ('100' + '200' -> '100200') khi cột đang ở kiểu object.
    """
    try:
        from pandas.core.groupby.generic import SeriesGroupBy
    except ImportError:
        return

    orig_gb_sum = getattr(SeriesGroupBy, "sum", None)
    if orig_gb_sum and not getattr(orig_gb_sum, "_is_numeric_resilient", False):
        def _resilient_gb_sum(self, *args, **kwargs):
            try:
                obj = getattr(self, "obj", None)
                if obj is not None and (obj.dtype == object or str(obj.dtype).startswith("string")):
                    cleaned_obj = clean_num(obj)
                    grouper = getattr(self, "_grouper", None) or getattr(self, "grouper", None)
                    if grouper is not None:
                        return cleaned_obj.groupby(grouper).sum(*args, **kwargs)
            except Exception:
                pass
            return orig_gb_sum(self, *args, **kwargs)

        _resilient_gb_sum._is_numeric_resilient = True
        try:
            SeriesGroupBy.sum = _resilient_gb_sum
        except Exception:
            pass

    orig_gb_mean = getattr(SeriesGroupBy, "mean", None)
    if orig_gb_mean and not getattr(orig_gb_mean, "_is_numeric_resilient", False):
        def _resilient_gb_mean(self, *args, **kwargs):
            try:
                obj = getattr(self, "obj", None)
                if obj is not None and (obj.dtype == object or str(obj.dtype).startswith("string")):
                    cleaned_obj = clean_num(obj)
                    grouper = getattr(self, "_grouper", None) or getattr(self, "grouper", None)
                    if grouper is not None:
                        return cleaned_obj.groupby(grouper).mean(*args, **kwargs)
            except Exception:
                pass
            return orig_gb_mean(self, *args, **kwargs)

        _resilient_gb_mean._is_numeric_resilient = True
        try:
            SeriesGroupBy.mean = _resilient_gb_mean
        except Exception:
            pass


def _patch_pandas_resilience():
    _patch_pandas_date_comparisons()
    _patch_pandas_str_contains()
    _patch_pandas_groupby_numeric()


_patch_pandas_resilience()


__all__ = [
    "RunResult",
    "PersistentWorker",
    "get_or_create_worker",
    "close_sandbox_worker",
    "run_code",
    "clean_num",
    "clean_date",
    "filter_valid_sales",
    "convert_to_base_qty",
    "revenue",
    "count_orders",
    "debt",
    "should_retry_self_correction",
    "sanitize_code_syntax",
    "_strip_accents",
    "_patch_pandas_date_comparisons",
    "_patch_pandas_str_contains",
    "_patch_pandas_groupby_numeric",
    "_patch_pandas_resilience",
]

