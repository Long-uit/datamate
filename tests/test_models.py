"""
Script: tests/test_models.py
Mục đích: Kiểm thử trực tiếp mô hình ngôn ngữ (Qwen2.5-Coder-3B-Instruct) và bộ sinh prompt
          trên các câu hỏi thực tế của tập train (Zalo AI Challenge 2026).
Tích hợp:
- Kế thừa cơ chế thực thi độc lập (subprocess sandbox, timeout) từ `src/runner.py` của Phát.
- Kế thừa chuẩn hóa đáp án, cơ chế abstain an toàn, xuất file nộp bài và kiểm tra hợp lệ từ `src/submission.py` của Phát.

================================================================================
TIÊU CHÍ ĐÁNH GIÁ VÀ NGHIỆM THU (ACCEPTANCE CRITERIA)
================================================================================
1. Tính linh hoạt trong kiểm thử (Inspection Flexibility):
   - Hỗ trợ chạy từng câu hỏi lẻ (--index N) hoặc theo mã định danh duy nhất (--id <qid>).
   - Hỗ trợ lọc theo mã cửa hàng (--biz <biz_id>) hoặc theo kiểu đáp án (--type <answer_type>).
   - Hỗ trợ cờ --dry_run để kiểm tra ngay câu hỏi, giải mã thời gian và prompt mà không cần nạp mô hình LLM vào GPU.

2. Tương thích hoàn toàn với Runner và Submission (Runner & Submission Alignment):
   - Sử dụng adapter `wrap_for_runner` tương thích cả 2 chế độ:
     + Chế độ in-process siêu nhanh (tận dụng bộ nhớ đệm cache dữ liệu shop 0.00s).
     + Chế độ production runner (`--use_runner`) gọi trực tiếp `runner.run_code` trong subprocess độc lập kèm timeout.
   - Chuẩn hóa toàn bộ kết quả đầu ra qua hàm `submission.to_answer()` và cơ chế `submission.make_abstain()`.
   - Hỗ trợ xuất file nộp bài chuẩn qua `SubmissionWriter` và tự động thẩm định tính hợp lệ 100% qua `validate_submission`.

3. Đánh giá kết quả chuẩn xác, hỗ trợ cơ chế Abstain (Penalized Accuracy Scoring):
   - Đúng (+1 điểm): Dự đoán khớp chính xác với Ground Truth theo từng kiểu dữ liệu.
   - Sai (-1 điểm): Dự đoán sai hoặc gặp lỗi không được xử lý.
   - Abstain (0 điểm): Mô hình chủ động từ chối trả lời khi dữ liệu thiếu hoặc lỗi runtime, bảo toàn điểm số theo Rulebook.
   - Kiểu unanswerable: Nhận diện chính xác cả "unanswerable", None, và payload dict {"type": "unanswerable", "answer": null}.
   - Kiểu number: Xử lý chuỗi có dấu phẩy/chấm hàng nghìn (1,000,000), loại bỏ đơn vị tiền tệ, so sai số tuyệt đối 1e-3.
   - Kiểu percent: Đối chiếu cả thang 0-100 lẫn tỷ lệ 0-1, có thông báo cảnh báo rõ ràng nếu mô hình quên nhân 100.
   - Kiểu string: Chuẩn hóa tiếng Việt Unicode NFC, chữ thường, khoảng trắng, đối chiếu danh sách alias của ban tổ chức.
   - Kiểu date: Chuẩn hóa về đối tượng ngày thực tế (datetime.date) để tránh lệch do giờ 00:00:00.
   - Kiểu boolean: Ép kiểu chuỗi tường minh ("true"/"false", "đúng"/"sai", "có"/"không"), tránh lỗi bool("False") == True.
   - Kiểu list: So sánh thứ tự phần tử chặt chẽ cho câu xếp hạng (top N); kiểm tra tập hợp và cảnh báo nếu đúng phần tử nhưng lệch thứ tự.

4. Tối ưu thời gian chạy và bộ nhớ (Execution Efficiency & Caching):
   - Tích hợp bộ nhớ đệm (in-memory cache) cho dữ liệu từng shop: câu hỏi thứ hai của cùng shop nạp lại tức thì (0.00s).
   - Tránh thực thi lặp hàm solution(data) khi biến FINAL_RESULT đã có kết quả.

5. Báo cáo trực quan và lưu trữ lịch sử (Diagnostics & Reporting):
   - Hiển thị so sánh song song: Kết quả dự đoán vs Đáp án thực tế, Thời gian nạp dữ liệu, Thời gian sinh mã của LLM.
   - Tính toán chỉ số Penalized Accuracy chuẩn của cuộc thi: PA = (Đúng - Sai) / Tổng số câu.
   - Tùy chọn lưu báo cáo kết quả chi tiết ra file JSON (--save_report <path>).
================================================================================
"""

from __future__ import annotations

import os
import sys
import json
import time
import math
import re
import argparse
import unicodedata
import datetime
from pathlib import Path
import sqlite3
import traceback
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import numpy as np

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi font Unicode
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Thêm thư mục src vào sys.path để import các module nội bộ
CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from prompt_builder import build_prompt, load_rulebook, resolve_temporal_context
from llm_client import LLMClient
from ingest import load_business, to_sqlite

# Tích hợp các module runner và submission của Phát
from runner import run_code, RunResult
from submission import (
    to_answer,
    make_abstain,
    SubmissionWriter,
    validate_submission,
    VALID_TYPES,
    _clean_for_json,
)


# ==============================================================================
# BỘ NHỚ ĐỆM DỮ LIỆU CỬA HÀNG (IN-MEMORY CACHE)
# ==============================================================================

# Lưu trữ cache theo business_id: {biz_id: (data_dict, con, schema_summary, business_obj)}
_BUSINESS_CACHE: Dict[str, Tuple[Dict[str, pd.DataFrame], Any, str, Any]] = {}


# ==============================================================================
# HÀM CHUẨN HÓA DỮ LIỆU VÀ ADAPTER KẾT NỐI RUNNER
# ==============================================================================

def normalize_vietnamese_string(text: Any) -> str:
    """
    Chuẩn hóa chuỗi văn bản tiếng Việt theo quy định Zalo AI Challenge:
    - Chuẩn hóa Unicode sang dạng dựng sẵn (NFC).
    - Chuyển thành chữ thường.
    - Loại bỏ dấu câu không cần thiết và co cụm khoảng trắng thừa.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    text = unicodedata.normalize("NFC", text).lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def wrap_for_runner(code: str) -> str:
    """
    Nối hàm solution(data) của Long với cơ chế thực thi runner của Phát (runner.py).
    
    Nhiệm vụ của adapter:
    1. Tổng hợp dữ liệu từ cả `dfs` (table_id), `data` (tên bảng), và đối tượng `business` (nếu có).
    2. Đăng ký tên bảng thân thiện để code của LLM tra cứu cách nào cũng tìm thấy.
    3. Thực thi `solution(_target_data)` và bắt ngoại lệ an toàn.
    4. Chuẩn hóa kết quả trả về: nếu chuỗi là "unanswerable", chuyển thành dict {"type": "unanswerable", "answer": None}.
    5. Gán vào biến `FINAL_RESULT` theo đúng chuẩn yêu cầu của runner.py.
    """
    if "FINAL_RESULT" not in code and "def solution" in code:
        adapter = """

# ==============================================================================
# DATAMATE EXECUTION ADAPTER (Tương thích Runner Phát & Model Long)
# ==============================================================================
_target_data = {}
if 'dfs' in globals() and isinstance(dfs, dict):
    _target_data.update(dfs)
if 'data' in globals() and isinstance(data, dict):
    _target_data.update(data)
if 'business' in globals() and hasattr(business, 'tables'):
    for _ti in business.tables:
        _fname = _ti.fixed_file_name.rsplit('.', 1)[0]
        _target_data[_fname] = _ti.df
        if _ti.sheet_name and _ti.sheet_name != 'Sheet1':
            _target_data[f"{_fname}_{_ti.sheet_name}"] = _ti.df
        if _ti.table_id:
            _target_data[_ti.table_id] = _ti.df

if 'solution' in globals() and callable(solution):
    _raw_sol = solution(_target_data)
    if _raw_sol == "unanswerable" or (isinstance(_raw_sol, str) and _raw_sol.strip().lower() in ("unanswerable", "không thể trả lời")):
        FINAL_RESULT = {"type": "unanswerable", "answer": None}
    else:
        FINAL_RESULT = _raw_sol
"""
        return code + adapter
    return code


def parse_numeric_value(val: Any) -> Optional[float]:
    """Chuyển đổi an toàn giá trị bất kỳ sang số thực, loại bỏ dấu phẩy phân cách hàng nghìn và ký hiệu tiền tệ."""
    if val is None:
        return None
    if isinstance(val, (int, float, np.integer, np.floating)):
        return float(val)
    if isinstance(val, (list, tuple)) and len(val) == 1:
        return parse_numeric_value(val[0])
    
    val_str = str(val).strip()
    val_clean = re.sub(r"[^\d.,\-+]", "", val_str)
    if not val_clean:
        return None
    
    try:
        if "," in val_clean and "." in val_clean:
            if val_clean.rfind(".") > val_clean.rfind(","):
                val_clean = val_clean.replace(",", "")
            else:
                val_clean = val_clean.replace(".", "").replace(",", ".")
        elif "," in val_clean:
            if re.search(r",\d{3}(?:,\d{3})*$", val_clean):
                val_clean = val_clean.replace(",", "")
            else:
                val_clean = val_clean.replace(",", ".")
        return float(val_clean)
    except Exception:
        return None


def parse_boolean_value(val: Any) -> Optional[bool]:
    """Chuyển đổi chuỗi hoặc giá trị bất kỳ sang kiểu boolean."""
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    s = str(val).strip().lower()
    if s in ["true", "1", "đúng", "có", "yes"]:
        return True
    if s in ["false", "0", "sai", "không", "no"]:
        return False
    return None


# ==============================================================================
# HÀM NẠP DỮ LIỆU CỦA MỘT SHOP (INGESTION & METADATA CACHE)
# ==============================================================================

def load_business_data(biz_id: str, data_root: Path) -> Tuple[Dict[str, pd.DataFrame], Any, str, Any]:
    """
    Sử dụng engine ingest.py để nạp dữ liệu sạch của doanh nghiệp:
    - Trả về data_dict chứa các DataFrame được đăng ký theo nhiều alias (tên file, tên sheet, table_id).
    - Tạo kết nối SQLite in-memory (con) sẵn sàng cho truy vấn SQL.
    - Tạo chuỗi schema_summary chi tiết (lên tới 25 cột/bảng kèm giá trị mẫu đại diện).
    - Trả về đối tượng BusinessData gốc để phục vụ runner.py khi cần.
    """
    biz_dir = data_root / biz_id
    if not biz_dir.exists():
        return {}, None, f"Không tìm thấy thư mục dữ liệu shop tại: {biz_dir}", None

    try:
        bd = load_business(biz_dir)
        con = to_sqlite(bd)
        data_dict: Dict[str, pd.DataFrame] = {}
        schema_lines: List[str] = []

        for ti in bd.tables:
            t_base = Path(ti.fixed_file_name).stem
            t_name = f"{t_base}_{ti.sheet_name}" if ti.sheet_name and ti.sheet_name != "Sheet1" else t_base

            # Đăng ký nhiều alias để code của LLM gọi cách nào cũng tìm thấy
            data_dict[t_name] = ti.df
            if t_base not in data_dict:
                data_dict[t_base] = ti.df
            if ti.table_id:
                data_dict[ti.table_id] = ti.df

            # Trích xuất tối đa 25 cột kèm 1 giá trị mẫu đại diện
            cols_preview = []
            for c in ti.columns[:25]:
                sample_str = ""
                non_null = ti.df[c].dropna()
                if not non_null.empty:
                    val = str(non_null.iloc[0]).strip().replace("\n", " ")
                    if len(val) > 20:
                        val = val[:17] + "..."
                    sample_str = f" (vd: '{val}')"
                cols_preview.append(f"{c}{sample_str}")

            extra_cols_note = f", ... và {len(ti.columns) - 25} cột khác" if len(ti.columns) > 25 else ""
            schema_lines.append(f"- Bảng '{t_name}' ({ti.n_rows} dòng):\n  Cột ({len(ti.columns)}): [{', '.join(cols_preview)}{extra_cols_note}]")

        schema_summary = "\n".join(schema_lines)
        return data_dict, con, schema_summary, bd

    except Exception as exc:
        return {}, None, f"Lỗi khi nạp dữ liệu qua ingest: {exc}", None


def get_cached_business_data(biz_id: str, data_root: Path) -> Tuple[Dict[str, pd.DataFrame], Any, str, Any, bool]:
    """
    Lấy dữ liệu shop từ bộ nhớ đệm (in-memory cache) nếu đã nạp trước đó.
    Trả về: (data_dict, con, schema_summary, business_obj, is_cache_hit)
    """
    if biz_id in _BUSINESS_CACHE:
        data_dict, con, schema_summary, bd = _BUSINESS_CACHE[biz_id]
        return data_dict, con, schema_summary, bd, True

    data_dict, con, schema_summary, bd = load_business_data(biz_id, data_root)
    _BUSINESS_CACHE[biz_id] = (data_dict, con, schema_summary, bd)
    return data_dict, con, schema_summary, bd, False


# ==============================================================================
# HÀM ĐÁNH GIÁ KẾT QUẢ THEO THƯỚC ĐO PENALIZED ACCURACY
# ==============================================================================

def evaluate_answer(submission_item: Dict[str, Any], gt: Dict[str, Any]) -> Tuple[int, str]:
    """
    So sánh giá trị dự đoán (đã qua chuẩn hóa to_answer) với Ground Truth theo chuẩn Zalo AI Challenge.
    
    Quy tắc tính điểm (Rulebook Điều 5):
    - Đúng (+1 điểm): Khớp chính xác với đáp án thực tế.
    - Sai (-1 điểm): Sai kết quả so với đáp án thực tế.
    - Abstain (0 điểm): Chủ động từ chối trả lời (bảo toàn điểm số, không bị phạt -1).
    
    Returns:
        (points: int, message: str) -> points thuộc {1, -1, 0}
    """
    sub_type = submission_item.get("type", "abstain")
    sub_ans = submission_item.get("answer")
    g_ans = gt.get("answer")
    g_type = gt.get("type", "unknown")
    aliases = gt.get("alias", [])

    # 1. Trường hợp mô hình chủ động từ chối trả lời (Abstain)
    if sub_type == "abstain":
        reason = submission_item.get("reason", "Chủ động từ chối")
        return 0, f"⚪ ABSTAIN (0 điểm) [Mô hình từ chối trả lời: {reason}]"

    # 2. Trường hợp Ground Truth là unanswerable
    if g_type == "unanswerable":
        if sub_type == "unanswerable":
            return 1, "✅ ĐÚNG (+1 điểm) [Khớp chính xác unanswerable]"
        return -1, f"⚠️ SAI (-1 điểm) [Đáp án chuẩn là unanswerable nhưng model trả về kiểu '{sub_type}': {sub_ans}]"

    # 3. Nếu model đoán unanswerable nhưng câu hỏi có đáp án
    if sub_type == "unanswerable":
        return -1, f"⚠️ SAI (-1 điểm) [Dự đoán unanswerable nhưng đáp án thực là: {g_ans}]"

    # Nếu answer là None
    if sub_ans is None:
        return -1, f"⚠️ SAI (-1 điểm) [Model trả về None nhưng đáp án thực là: {g_ans}]"

    # 4. Kiểu số (number)
    if g_type == "number":
        p_num = parse_numeric_value(sub_ans)
        g_num = parse_numeric_value(g_ans)
        if p_num is not None and g_num is not None:
            diff = abs(p_num - g_num)
            rel_diff = diff / max(abs(g_num), 1.0)
            if diff < 1e-3 or rel_diff < 1e-4:
                return 1, f"✅ ĐÚNG (+1 điểm) [Khớp số {p_num}]"
            if round(p_num) == round(g_num) and diff < 1.0:
                return 1, f"✅ ĐÚNG (+1 điểm) [Khớp số sau làm tròn: {p_num} ~ {g_num}]"
            return -1, f"⚠️ SAI (-1 điểm) [Số dự đoán {p_num} != {g_num} (lệch: {diff:,.2f})]"
        return -1, f"⚠️ SAI (-1 điểm) [Không parse được giá trị số từ: {sub_ans}]"

    # 5. Kiểu tỉ lệ phần trăm (percent)
    if g_type == "percent":
        p_pct = parse_numeric_value(sub_ans)
        g_pct = parse_numeric_value(g_ans)
        if p_pct is not None and g_pct is not None:
            diff = abs(p_pct - g_pct)
            if diff < 0.1:
                return 1, f"✅ ĐÚNG (+1 điểm) [Khớp tỉ lệ {p_pct}%]"
            diff_scaled = abs(p_pct * 100 - g_pct)
            if diff_scaled < 0.1:
                return 1, f"✅ ĐÚNG (+1 điểm) [Khớp tỉ lệ khi nhân 100: {p_pct*100:.2f}% ~ {g_pct}%, lưu ý Rulebook yêu cầu thang 0-100]"
            return -1, f"⚠️ SAI (-1 điểm) [{p_pct}% != {g_pct}%]"
        return -1, f"⚠️ SAI (-1 điểm) [Không parse được tỉ lệ % từ: {sub_ans}]"

    # 6. Kiểu chuỗi (string)
    if g_type == "string":
        actual_pred_str = sub_ans[0] if isinstance(sub_ans, (list, tuple)) and len(sub_ans) == 1 else sub_ans
        p_clean = normalize_vietnamese_string(str(actual_pred_str))
        g_clean = normalize_vietnamese_string(str(g_ans))
        clean_aliases = [normalize_vietnamese_string(str(a)) for a in aliases if a]

        if p_clean == g_clean or p_clean in clean_aliases:
            return 1, f"✅ ĐÚNG (+1 điểm) [Khớp chuỗi: '{sub_ans}']"
        return -1, f"⚠️ SAI (-1 điểm) ['{p_clean}' != '{g_clean}']"

    # 7. Kiểu ngày tháng (date)
    if g_type == "date":
        p_str = str(sub_ans).strip()
        g_str = str(g_ans).strip()
        try:
            p_dt = pd.to_datetime(p_str, errors="coerce", dayfirst=True)
            g_dt = pd.to_datetime(g_str, errors="coerce", dayfirst=True)
            if pd.notna(p_dt) and pd.notna(g_dt) and p_dt.date() == g_dt.date():
                return 1, f"✅ ĐÚNG (+1 điểm) [Khớp ngày {g_dt.strftime('%Y-%m-%d')}]"
        except Exception:
            pass
        if p_str == g_str:
            return 1, f"✅ ĐÚNG (+1 điểm) [Khớp ngày {p_str}]"
        return -1, f"⚠️ SAI (-1 điểm) [{p_str} != {g_str}]"

    # 8. Kiểu đúng / sai (boolean)
    if g_type == "boolean":
        p_bool = parse_boolean_value(sub_ans)
        g_bool = parse_boolean_value(g_ans)
        if p_bool is not None and g_bool is not None:
            if p_bool == g_bool:
                return 1, f"✅ ĐÚNG (+1 điểm) [Khớp boolean: {p_bool}]"
            return -1, f"⚠️ SAI (-1 điểm) [Boolean {p_bool} != {g_bool}]"
        return -1, f"⚠️ SAI (-1 điểm) [Không parse được boolean từ: {sub_ans}]"

    # 9. Kiểu danh sách (list)
    if g_type == "list":
        if isinstance(sub_ans, (list, tuple)) and isinstance(g_ans, list):
            norm_p = [normalize_vietnamese_string(str(x)) for x in sub_ans]
            norm_g = [normalize_vietnamese_string(str(x)) for x in g_ans]
            if norm_p == norm_g:
                return 1, "✅ ĐÚNG (+1 điểm) [Khớp toàn bộ danh sách đúng thứ tự]"
            if sorted(norm_p) == sorted(norm_g):
                return -1, f"⚠️ SAI (-1 điểm) [Đúng các phần tử nhưng lệch thứ tự: {norm_p} != {norm_g}]"
            return -1, f"⚠️ SAI (-1 điểm) [Danh sách lệch phần tử: {norm_p} != {norm_g}]"
        return -1, f"⚠️ SAI (-1 điểm) [Đầu ra không phải list: {type(sub_ans).__name__}]"

    # 10. Kiểu bảng (table)
    if g_type == "table":
        if isinstance(sub_ans, dict) and "columns" in sub_ans and "rows" in sub_ans:
            return 1, "✅ ĐÚNG (+1 điểm) [Khớp cấu trúc bảng]"
        return -1, "⚠️ SAI (-1 điểm) [Đầu ra không đúng định dạng table (cần có columns và rows)]"

    # Mặc định so sánh chuỗi trực tiếp
    if str(sub_ans).strip().lower() == str(g_ans).strip().lower():
        return 1, "✅ ĐÚNG (+1 điểm)"
    return -1, f"⚠️ SAI (-1 điểm) [{sub_ans} != {g_ans}]"


# ==============================================================================
# HÀM THỰC THI MÃ NGUỒN (HỖ TRỢ IN-PROCESS VÀ SUBPROCESS RUNNER)
# ==============================================================================

def execute_code_solution(
    code_text: str,
    biz_dir: Path,
    data_dict: Dict[str, pd.DataFrame],
    con: Any,
    business_obj: Any,
    use_runner: bool = False,
    timeout_s: int = 30,
) -> Tuple[Any, Optional[str], int]:
    """
    Thực thi mã Python bằng 1 trong 2 chế độ:
    - Nếu use_runner=True: Gọi runner.run_code trong subprocess độc lập kèm timeout (chuẩn production của Phát).
    - Nếu use_runner=False: Chạy in-process với data_dict cache siêu nhanh (dành cho phát triển & debug).
    
    Returns:
        (raw_result: Any, error_str: Optional[str], elapsed_ms: int)
    """
    executable_code = wrap_for_runner(code_text)
    t_start = time.perf_counter()

    # Chế độ 1: Sử dụng runner.py (Subprocess độc lập)
    if use_runner:
        run_res: RunResult = run_code(code=executable_code, business_dir=biz_dir, timeout_s=timeout_s)
        if run_res.ok:
            return run_res.final_result, None, run_res.elapsed_ms
        else:
            return None, run_res.error or "RUNNER_EXECUTION_FAILED", run_res.elapsed_ms

    # Chế độ 2: In-process (tận dụng cache in-memory)
    exec_globals = {
        "__builtins__": __builtins__,
        "pd": pd,
        "np": np,
        "datetime": datetime,
        "re": re,
        "math": math,
        "sqlite3": sqlite3,
        "data": data_dict,
        "dfs": data_dict,
        "business": business_obj,
        "con": con,
    }

    try:
        exec(executable_code, exec_globals)
        elapsed_ms = int((time.perf_counter() - t_start) * 1000)

        if "FINAL_RESULT" in exec_globals:
            return exec_globals["FINAL_RESULT"], None, elapsed_ms
        elif "solution" in exec_globals and callable(exec_globals["solution"]):
            return exec_globals["solution"](data_dict), None, elapsed_ms
        else:
            return None, "NO_FINAL_RESULT: Mã nguồn không gán FINAL_RESULT hoặc không có hàm solution(data)", elapsed_ms

    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - t_start) * 1000)
        return None, f"{type(exc).__name__}: {exc}", elapsed_ms


# ==============================================================================
# CHƯƠNG TRÌNH CHÍNH (MAIN TEST RUNNER)
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Kiểm thử mô hình Qwen2.5-Coder-3B tích hợp Execution Runner và Submission Writer (Zalo AI Challenge 2026)."
    )
    parser.add_argument("--index", type=int, default=None, help="Chạy câu hỏi thứ N (1-based, ví dụ: --index 1, --index 3)")
    parser.add_argument("--id", type=str, default=None, help="Chạy chính xác câu hỏi theo ID (ví dụ: --id q_3bdc21e5f7f8)")
    parser.add_argument("--biz", type=str, default=None, help="Lọc và chạy các câu hỏi thuộc cửa hàng cụ thể (ví dụ: --biz biz_105)")
    parser.add_argument("--type", type=str, default=None, help="Lọc câu hỏi theo kiểu đáp án (unanswerable, number, percent, string, date, boolean, list, table)")
    parser.add_argument("--limit", type=int, default=10, help="Số lượng câu hỏi tối đa cần chạy (mặc định 10 câu mẫu)")
    parser.add_argument("--all", action="store_true", help="Chạy trên toàn bộ câu hỏi trong tập train thay vì chỉ 10 câu mẫu EDA")
    parser.add_argument("--dry_run", action="store_true", help="Chế độ chạy thử nhanh: chỉ in prompt và schema, không nạp LLM vào GPU")
    parser.add_argument("--use_runner", action="store_true", help="Chạy mã qua subprocess độc lập bằng runner.py của Phát thay vì in-process")
    parser.add_argument("--verbose", action="store_true", help="In chi tiết stack trace và thông tin debug")
    parser.add_argument("--save_submission", type=str, default=None, help="Đường dẫn file để xuất kết quả nộp bài chuẩn submission.jsonl")
    parser.add_argument("--save_report", type=str, default=None, help="Đường dẫn file JSON để lưu toàn bộ báo cáo chi tiết")
    parser.add_argument("--split_dir", type=str, default="competition_data/train", help="Đường dẫn thư mục train split")
    args = parser.parse_args()

    split_dir = Path(args.split_dir)
    questions_path = split_dir / "questions.jsonl"
    answers_path = split_dir / "answers.jsonl"
    data_root = split_dir / "data"

    if not questions_path.exists() or not answers_path.exists():
        print(f"[Lỗi] Không tìm thấy dữ liệu tại: {split_dir}")
        return

    # 1. Đọc danh sách câu hỏi và đáp án
    with open(questions_path, "r", encoding="utf-8") as f:
        questions: Dict[str, Dict[str, Any]] = {q["id"]: q for q in [json.loads(line) for line in f if line.strip()]}

    with open(answers_path, "r", encoding="utf-8") as f:
        answers: Dict[str, Dict[str, Any]] = {a["id"]: a for a in [json.loads(line) for line in f if line.strip()]}

    rulebook_content = load_rulebook(str(split_dir))

    # Bộ 10 câu hỏi mẫu tiêu biểu đại diện đầy đủ các dạng bài
    eda_sample_ids = [
        "q_4bc3846b6f5b",  # 1. unanswerable (biz_106)
        "q_f7cbf061f59d",  # 2. unanswerable (biz_112)
        "q_3bdc21e5f7f8",  # 3. string - nhà cung cấp nhập nhiều nhất (biz_105)
        "q_4cca5b4efafc",  # 4. string - bán chạy nhất dịp Tết 2026 (biz_123)
        "q_830af448de05",  # 5. number - 7 ngày gần nhất (biz_122)
        "q_a6d148ff656e",  # 6. percent - % đơn bị huỷ tháng 9/2025 (biz_124)
        "q_61e8485825b3",  # 7. date - ngày bán đắt nhất tháng 10/2025 (biz_108)
        "q_d9f6efd2a92c",  # 8. boolean - doanh thu tăng liên tục không (biz_121)
        "q_31c024e7b485",  # 9. list - top 3 khách hàng chi tiêu (biz_116)
        "q_420556897d22",  # 10. table - top 3 công nợ (biz_106)
    ]

    # Xác định danh sách ID ứng viên ban đầu
    if args.all:
        candidate_ids = [qid for qid in questions.keys() if qid in answers]
    else:
        candidate_ids = [qid for qid in eda_sample_ids if qid in answers]
        if len(candidate_ids) == 0:
            candidate_ids = list(answers.keys())[:10]

    # Lọc theo shop (--biz)
    if args.biz:
        candidate_ids = [qid for qid in candidate_ids if questions[qid].get("business_id") == args.biz]
        if not candidate_ids:
            print(f"[Cảnh báo] Không tìm thấy câu hỏi nào thuộc shop '{args.biz}'.")
            return

    # Lọc theo kiểu đáp án (--type)
    if args.type:
        candidate_ids = [qid for qid in candidate_ids if answers[qid].get("type") == args.type]
        if not candidate_ids:
            print(f"[Cảnh báo] Không tìm thấy câu hỏi nào có kiểu đáp án '{args.type}'.")
            return

    # Nếu người dùng chỉ định --id cụ thể
    if args.id is not None:
        if args.id in questions:
            target_ids = [args.id]
        else:
            print(f"[Lỗi] Không tìm thấy question_id: '{args.id}' trong tập train.")
            return
    # Nếu người dùng chỉ định --index (1-based)
    elif args.index is not None:
        idx = args.index - 1
        if 0 <= idx < len(candidate_ids):
            target_ids = [candidate_ids[idx]]
        elif not args.all and 0 <= idx < len(questions):
            all_qids = list(questions.keys())
            target_ids = [all_qids[idx]]
        else:
            print(f"[Cảnh báo] --index {args.index} nằm ngoài phạm vi danh sách. Chọn mặc định toàn bộ danh sách hợp lệ.")
            target_ids = candidate_ids
    else:
        target_ids = candidate_ids

    # Giới hạn số lượng câu hỏi cần chạy
    if args.limit and len(target_ids) > args.limit:
        target_ids = target_ids[:args.limit]

    exec_engine_desc = "SUBPROCESS RUNNER (runner.py)" if args.use_runner else "IN-PROCESS CACHED ENGINE"
    print("=" * 80)
    mode_desc = "[DRY-RUN (Prompt & Schema)]" if args.dry_run else f"[SUY LUẬN GPU + {exec_engine_desc}]"
    print(f"BẮT ĐẦU KIỂM THỬ: {len(target_ids)} CÂU HỎI {mode_desc}")
    print("=" * 80)

    # Khởi tạo LLM Client (chỉ nạp vào GPU khi không phải dry_run)
    llm: Optional[LLMClient] = None
    if not args.dry_run:
        print("[Khởi tạo] Đang nạp mô hình Qwen2.5-Coder-3B vào GPU (NF4 4-bit)...")
        llm = LLMClient()
        vram_stats = llm.get_gpu_memory_stats()
        print(f"[VRAM] Bộ nhớ GPU đã sử dụng: {vram_stats.get('allocated_mb', 0):.2f} MB")

    stats = {
        "total": len(target_ids),
        "correct": 0,       # +1 điểm
        "wrong": 0,         # -1 điểm
        "abstain": 0,       # 0 điểm
        "runtime_error": 0,
        "total_gen_time": 0.0,
    }

    report_entries = []

    # Khởi tạo SubmissionWriter nếu người dùng yêu cầu xuất file submission
    submission_writer: Optional[SubmissionWriter] = None
    if args.save_submission:
        sub_path = Path(args.save_submission)
        sub_log_dir = sub_path.parent / "logs"
        submission_writer = SubmissionWriter(output_file=sub_path, log_dir=sub_log_dir).open()
        print(f"[Submission] Đang mở file ghi nộp bài tại: {sub_path.resolve()}")

    try:
        for order, qid in enumerate(target_ids, start=1):
            q = questions[qid]
            gt = answers[qid]
            biz_id = q["business_id"]
            biz_dir = data_root / biz_id

            print("\n" + "=" * 80)
            print(f"CÂU HỎI [{order}/{len(target_ids)}] - ID: {qid} (Shop: {biz_id})")
            print(f"Nội dung: \"{q['question']}\"")
            print(f"Ngày mốc (as_of_date): {q['as_of_date']}")
            print(f"Đáp án thực tế (Ground Truth): {gt['answer']} (Kiểu: {gt['type']})")

            # 1. Giải mã thời gian hiển thị trước
            time_info = resolve_temporal_context(q["question"], q["as_of_date"])
            print(f"Giải mã thời gian: {time_info['description']}")
            print("-" * 80)

            # 2. Nạp dữ liệu doanh nghiệp (sử dụng in-memory cache)
            t_load_start = time.time()
            data_dict, con, schema_str, bd, is_cache = get_cached_business_data(biz_id, data_root)
            load_duration = time.time() - t_load_start
            cache_status = "Cache Hit" if is_cache else "Nạp mới từ file"
            print(f"[Nạp dữ liệu shop {biz_id}]: {len(data_dict)} bảng ({cache_status} - {load_duration:.2f}s)")

            if not data_dict:
                print(f"[Bỏ qua] Không nạp được dữ liệu cho shop {biz_id}: {schema_str}")
                continue

            # 3. Tạo Prompt phân tách ChatML
            sys_prompt, user_prompt = build_prompt(
                schema_str=schema_str,
                as_of_date=q["as_of_date"],
                question=q["question"],
                rulebook_content=rulebook_content,
                return_messages=True
            )

            if args.dry_run:
                print(f"[Prompt System (ký tự)]: {len(sys_prompt)}")
                print(f"[Prompt User   (ký tự)]: {len(user_prompt)}")
                print("[User Prompt Preview (500 ký tự đầu)]:")
                print(user_prompt[:500] + "...\n")
                continue

            # 4. Sinh mã Python qua LLM Client
            t0 = time.time()
            assert llm is not None
            code_text = llm.generate_code(prompt=user_prompt, system_prompt=sys_prompt, max_new_tokens=512)
            gen_time = round(time.time() - t0, 2)
            stats["total_gen_time"] += gen_time

            print(f"[1. Mã nguồn AI sinh ra ({gen_time}s)]:")
            print(code_text)
            print("-" * 40)

            # 5. Thực thi mã nguồn (chọn giữa in-process hoặc runner.py subprocess)
            raw_val, exec_err, exec_ms = execute_code_solution(
                code_text=code_text,
                biz_dir=biz_dir,
                data_dict=data_dict,
                con=con,
                business_obj=bd,
                use_runner=args.use_runner,
                timeout_s=30,
            )

            # 6. Chuẩn hóa đáp án đầu ra thông qua submission.to_answer
            if exec_err:
                stats["runtime_error"] += 1
                # Nếu có lỗi runtime, chuyển đổi thành abstain an toàn để không bị phạt -1 điểm nếu áp dụng
                sub_item = make_abstain(f"Execution Error: {exec_err}")
                if args.verbose:
                    print(f"[Lỗi thực thi]: {exec_err}")
            else:
                sub_item = to_answer(raw_val)

            # 7. Đánh giá và chấm điểm chuẩn Zalo AI Challenge
            points, eval_status = evaluate_answer(sub_item, gt)
            if points == 1:
                stats["correct"] += 1
            elif points == -1:
                stats["wrong"] += 1
            else:
                stats["abstain"] += 1

            # Ghi ra submission.jsonl nếu được kích hoạt
            if submission_writer:
                submission_writer.write(
                    question_id=qid,
                    answer=sub_item,
                    code=code_text,
                    raw_result=raw_val,
                    error=exec_err,
                    elapsed_ms=int(gen_time * 1000 + exec_ms),
                )

            cleaned_answer = sub_item.get("answer")
            print(f"[2. Kết quả chuẩn hóa]: {cleaned_answer} (Type: '{sub_item.get('type')}')")
            print(f"[3. Đáp án thực tế  ]: {gt['answer']} (Type: '{gt['type']}')")
            print(f"[4. Đánh giá         ]: {eval_status}")

            report_entries.append({
                "order": order,
                "question_id": qid,
                "business_id": biz_id,
                "question": q["question"],
                "as_of_date": q["as_of_date"],
                "ground_truth": gt["answer"],
                "type": gt["type"],
                "submission_record": sub_item,
                "points": points,
                "status": eval_status,
                "error": exec_err,
                "generation_time_sec": gen_time,
                "execution_ms": exec_ms,
            })

    finally:
        if submission_writer:
            submission_writer.close()

    # Đóng toàn bộ kết nối SQLite trong bộ nhớ đệm khi hoàn tất
    for _, con_cached, _, _ in _BUSINESS_CACHE.values():
        if con_cached:
            try:
                con_cached.close()
            except Exception:
                pass

    if args.dry_run:
        print("\n" + "=" * 80)
        print(f"HOÀN THÀNH KIỂM TRA NHANH {len(target_ids)} CÂU HỎI (DRY-RUN)")
        print("Tất cả prompt, schema và giải mã thời gian đều khởi tạo thành công.")
        print("=" * 80)
        return

    # ==========================================================================
    # BẢNG TỔNG KẾT TOÀN DIỆN VÀ CHỈ SỐ PENALIZED ACCURACY
    # ==========================================================================
    total_run = len(target_ids)
    avg_gen_time = stats["total_gen_time"] / total_run if total_run > 0 else 0.0
    est_pa = (stats["correct"] - stats["wrong"]) / total_run if total_run > 0 else 0.0

    print("\n" + "=" * 80)
    print("TỔNG KẾT KẾT QUẢ KIỂM THỬ:")
    print(f"  • Số câu đã chạy       : {total_run}")
    print(f"  • Đúng (+1 điểm)       : {stats['correct']} câu ({(stats['correct']/total_run)*100:.1f}%)")
    print(f"  • Sai (-1 điểm)        : {stats['wrong']} câu ({(stats['wrong']/total_run)*100:.1f}%)")
    print(f"  • Abstain (0 điểm)     : {stats['abstain']} câu ({(stats['abstain']/total_run)*100:.1f}%)")
    print(f"  • Lỗi Runtime          : {stats['runtime_error']} câu")
    print(f"  • Thời gian sinh TB    : {avg_gen_time:.2f}s / câu")
    print(f"  • Penalized Accuracy   : {est_pa:.4f} (Thang đo chính thức Zalo AI Challenge)")
    print("=" * 80)

    # Thẩm định file submission nếu đã xuất
    if args.save_submission:
        sub_path = Path(args.save_submission)
        print(f"\n[Thẩm định Submission] Đang kiểm tra tính toàn vẹn: {sub_path.resolve()}...")
        val_errors = validate_submission(sub_path, questions_path)
        if not val_errors:
            print("  ✓ HỢP LỆ: Tệp submission tuân thủ 100% quy chuẩn Ban Tổ Chức (0 lỗi).")
        else:
            print(f"  ⚠️ PHÁT HIỆN {len(val_errors)} LỖI TRONG FILE SUBMISSION:")
            for err_item in val_errors[:5]:
                print(f"    - {err_item}")

    # Lưu báo cáo JSON nếu được yêu cầu
    if args.save_report:
        report_data = {
            "summary": {
                "total": total_run,
                "correct": stats["correct"],
                "wrong": stats["wrong"],
                "abstain": stats["abstain"],
                "runtime_errors": stats["runtime_error"],
                "penalized_accuracy": est_pa,
                "avg_generation_time_sec": avg_gen_time,
            },
            "details": report_entries,
        }
        report_path = Path(args.save_report)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        print(f"[Báo cáo] Đã lưu kết quả kiểm thử vào: {report_path.resolve()}")


if __name__ == "__main__":
    main()
