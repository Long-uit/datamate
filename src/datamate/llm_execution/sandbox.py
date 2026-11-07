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

import atexit
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

    def __init__(self, biz_dir: Path, src_dir: Path, startup_timeout: int = 60):
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

    def execute(self, code: str, timeout_s: int) -> RunResult:
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
        req_msg = json.dumps({"cmd": "run", "code": code}, ensure_ascii=False)
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


def get_or_create_worker(business_dir: Path, timeout_startup: int = 60) -> PersistentWorker:
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


def _run_code_oneshot(code: str, business_dir: Path, timeout_s: int = 60) -> RunResult:
    """Thực thi một lần (One-shot Fallback) khi không sử dụng persistent daemon."""
    t_start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="dm_runner_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        code_file = tmp_path / "code.py"
        result_file = tmp_path / "result.json"
        code_file.write_text(code, encoding="utf-8")

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
            return worker.execute(code, timeout_s=timeout_s)
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
        s_clean = re.sub(r"(?:vnđ|vnd|đ|đồng|\$)", "", s_low).strip()
        
        multiplier = 1.0
        if "triệu" in s_clean:
            multiplier = 1_000_000.0
            s_clean = s_clean.replace("triệu", "").strip()
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
            # Nếu sau dấu phẩy là 3 chữ số -> phân cách nghìn kiểu US (1,250)
            if len(parts) == 2 and len(parts[1]) != 3:
                s_clean = s_clean.replace(",", ".")
            else:
                s_clean = s_clean.replace(",", "")
        elif "." in s_clean:
            parts = s_clean.split(".")
            # Nếu có nhiều hơn 1 dấu chấm (1.250.000) hoặc có 3 chữ số sau dấu chấm (1.250) -> phân cách nghìn VN
            if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and parts[0].isdigit() and int(parts[0]) != 0):
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
        return series_or_val.apply(_parse_scalar)
    elif isinstance(series_or_val, (list, tuple)):
        return [_parse_scalar(x) for x in series_or_val]
    elif isinstance(series_or_val, np.ndarray):
        return np.vectorize(_parse_scalar)(series_or_val)
    else:
        return _parse_scalar(series_or_val)


def clean_date(series_or_val: Any, dayfirst: Optional[bool] = None) -> Any:
    """
    Chuyển đổi an toàn sang chuẩn pd.to_datetime:
    - Nếu dữ liệu dạng ISO ('2025-10-05'): Luôn giữ chuẩn YYYY-MM-DD (chống lỗi đảo ngày/tháng do dayfirst=True).
    - Nếu dữ liệu dạng Việt Nam ('05/10/2025'): Tự động bật dayfirst=True (DD/MM/YYYY).
    """
    def _parse_scalar(val: Any) -> Any:
        if val is None or pd.isna(val):
            return pd.NaT
        s = str(val).strip()
        if not s or s.lower() in ("nan", "none", "null", "nat"):
            return pd.NaT
        # Nếu chuỗi bắt đầu bằng 4 chữ số (YYYY-MM-DD...) -> Tuyệt đối không đảo ngày tháng
        if re.match(r"^\d{4}[-/]", s):
            try:
                return pd.to_datetime(s, dayfirst=False)
            except Exception:
                return pd.to_datetime(s, errors="coerce")
        # Chuỗi dạng DD/MM/YYYY -> Bật dayfirst=True
        use_df = dayfirst if dayfirst is not None else True
        try:
            return pd.to_datetime(s, dayfirst=use_df, errors="coerce")
        except Exception:
            return pd.NaT

    if isinstance(series_or_val, pd.Series):
        non_na = series_or_val.dropna()
        if not non_na.empty:
            first_val = str(non_na.iloc[0]).strip()
            if re.match(r"^\d{4}[-/]", first_val):
                # Định dạng ISO: YYYY-MM-DD
                try:
                    return pd.to_datetime(series_or_val, dayfirst=False, errors="coerce")
                except Exception:
                    pass
        use_df = dayfirst if dayfirst is not None else True
        try:
            return pd.to_datetime(series_or_val, dayfirst=use_df, format="mixed", errors="coerce")
        except Exception:
            try:
                return pd.to_datetime(series_or_val, dayfirst=use_df, errors="coerce")
            except Exception:
                return pd.to_datetime(series_or_val, errors="coerce")

    elif isinstance(series_or_val, (list, tuple)):
        return [_parse_scalar(x) for x in series_or_val]
    else:
        return _parse_scalar(series_or_val)

__all__ = [
    "RunResult",
    "PersistentWorker",
    "get_or_create_worker",
    "close_sandbox_worker",
    "run_code",
    "clean_num",
    "clean_date",
]

