"""
Script: run_eval.py
Mục đích: Pipeline duy nhất chạy toàn trình từ Suy luận (Inference), So khớp Đáp án (Evaluation),
          Chấm điểm Penalized Accuracy (PA) và Xuất Biểu đồ Hình ảnh Thống kê Trực quan (Visualization Dashboard).
"""

from __future__ import annotations

import os
import sys
import re
import json
import time
import math
import unicodedata
import argparse
from pathlib import Path
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple, Set

# Tự động nạp thư mục src vào sys.path
_SRC_DIR = str(Path(__file__).resolve().parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# Thiết lập encoding console an toàn trên Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd
import numpy as np

# Nhập các thành phần cốt lõi của package datamate
from datamate.config import load_config
from datamate.llm_execution.client import LLMClient
from datamate.llm_execution.prompt import build_prompt, load_rulebook, build_retry_prompt
from datamate.grounding_feasibility.feasibility import check_feasibility, extract_shop_metadata
from datamate.ingestion_schema.loader import load_business, to_sqlite
from datamate.ingestion_schema.schema_profiler import profile_business_schema
from datamate.ingestion_schema.cleaner import clean_business
from datamate.grounding_feasibility.entity_linker import extract_candidates_from_business, link_entities
from datamate.grounding_feasibility.temporal import filter_future_data
from datamate.llm_execution.sandbox import clean_num, clean_date, run_code
from datamate.exceptions import DataNotFoundError
from datamate.output_abstention.submission import make_abstain, SubmissionWriter, validate_submission
from datamate.output_abstention.normalizer import normalize_output, apply_tie_breaker, check_result_sanity
from datamate.output_abstention.abstention import (
    compute_confidence_score,
    apply_abstention_gate,
    evaluate_grounding_coverage,
)


# ==============================================================================
# BỘ NHỚ ĐỆM DỮ LIỆU CỬA HÀNG (IN-MEMORY CACHE)
# ==============================================================================
_BUSINESS_CACHE: Dict[str, Tuple[Dict[str, pd.DataFrame], Any, str, Any, Dict[str, Any], List[Any]]] = {}


def load_business_data(biz_id: str, data_root: Path) -> Tuple[Dict[str, pd.DataFrame], Any, str, Any, Dict[str, Any], List[Any]]:
    """Nạp dữ liệu sạch của doanh nghiệp (áp dụng Rule 8), tạo schema summary, trích xuất shop_meta và candidates."""
    biz_dir = data_root / biz_id
    if not biz_dir.exists():
        return {}, None, f"Không tìm thấy thư mục shop: {biz_dir}", None, {}, []

    try:
        raw_bd = load_business(biz_dir)
        bd = clean_business(raw_bd)
        con = None  # Tối ưu hóa nạp kép: LLM 100% dùng Pandas trên data, bỏ nạp SQLite mặc định
        data_dict: Dict[str, pd.DataFrame] = {}
        for ti in bd.tables:
            t_base = Path(ti.fixed_file_name).stem if getattr(ti, "fixed_file_name", None) else ti.table_id
            t_name = f"{t_base}_{ti.sheet_name}" if ti.sheet_name and ti.sheet_name != "Sheet1" else t_base
            data_dict[t_name] = ti.df
            if t_base != t_name and t_base not in data_dict:
                data_dict[t_base] = ti.df
            if ti.table_id and ti.table_id not in data_dict:
                data_dict[ti.table_id] = ti.df

        # Sử dụng Rich Schema Profiler hiển thị kiểu dữ liệu, min-max date và giá trị mẫu
        schema_summary = profile_business_schema(bd, max_cols=25)
        shop_meta = extract_shop_metadata(business_obj=bd, data_dict=data_dict)
        candidates = extract_candidates_from_business(bd)
        return data_dict, con, schema_summary, bd, shop_meta, candidates
    except Exception as exc:
        return {}, None, f"Lỗi nạp dữ liệu: {exc}", None, {}, []


def get_cached_business_data(biz_id: str, data_root: Path) -> Tuple[Dict[str, pd.DataFrame], Any, str, Any, Dict[str, Any], List[Any], bool]:
    """Lấy dữ liệu shop, shop_meta và candidates từ RAM cache."""
    if biz_id in _BUSINESS_CACHE:
        d, c, s, b, sm, cd = _BUSINESS_CACHE[biz_id]
        return d, c, s, b, sm, cd, True

    d, c, s, b, sm, cd = load_business_data(biz_id, data_root)
    _BUSINESS_CACHE[biz_id] = (d, c, s, b, sm, cd)
    return d, c, s, b, sm, cd, False


# ==============================================================================
# THỰC THI MÃ NGUỒN AN TOÀN TRONG SANDBOX
# ==============================================================================

def extract_referenced_tables_and_columns(code_str: str, available_tables: List[str]) -> Tuple[List[str], List[str]]:
    """Trích xuất tên các bảng và cột được truy cập trong mã nguồn mô hình sinh ra."""
    sel_tables = []
    sel_cols = []
    if not code_str:
        return sel_tables, sel_cols
    for t in available_tables:
        if t in code_str:
            sel_tables.append(t)
    col_matches = re.findall(r"\[\s*[\'\"]([^\'\"]+)[\'\"]\s*\]", code_str)
    for c in col_matches:
        if c not in sel_cols and c not in sel_tables:
            sel_cols.append(c)
    return sel_tables, sel_cols[:15]


def execute_solution(
    code_text: str,
    biz_dir: Path,
    data_dict: Dict[str, pd.DataFrame],
    con: Any,
    business_obj: Any,
    timeout_s: int = 30,
    use_sandbox: bool = True,
    return_details: bool = False,
) -> Tuple[Any, ...]:
    """Thực thi mã nguồn mô hình sinh ra trong subprocess sandbox độc lập có hard timeout."""
    adapter = """
if 'FINAL_RESULT' not in globals() and 'solution' in globals() and callable(solution):
    _raw_sol = solution(data)
    if _raw_sol is None or (isinstance(_raw_sol, str) and not _raw_sol.strip()):
        FINAL_RESULT = {"type": "abstain", "answer": None, "unanswerable_source": "none"}
    elif _raw_sol == "unanswerable" or (isinstance(_raw_sol, str) and _raw_sol.strip().lower() in ("unanswerable", "không thể trả lời")):
        FINAL_RESULT = {"type": "unanswerable", "answer": None, "unanswerable_source": "model"}
    elif isinstance(_raw_sol, dict) and _raw_sol.get("type") == "unanswerable":
        FINAL_RESULT = {"type": "unanswerable", "answer": None, "unanswerable_source": _raw_sol.get("unanswerable_source", "model")}
    else:
        FINAL_RESULT = _raw_sol
"""
    executable_code = code_text.strip() + "\n" + adapter

    if use_sandbox:
        res = run_code(executable_code, business_dir=biz_dir, timeout_s=timeout_s)
        unans_src = res.unanswerable_source
        if isinstance(res.final_result, dict):
            unans_src = res.final_result.get("unanswerable_source", unans_src)
        if res.ok:
            if return_details:
                return res.final_result, None, res.elapsed_ms, None, unans_src
            return res.final_result, None, res.elapsed_ms
        err_msg = res.error or "Lỗi thực thi trong sandbox"
        if return_details:
            return None, err_msg, res.elapsed_ms, res.error_type, unans_src
        return None, err_msg, res.elapsed_ms

    # In-process fallback
    t_start = time.perf_counter()
    isolated_data = {k: v.copy(deep=False) for k, v in data_dict.items()}
    exec_globals = {
        "__builtins__": __builtins__,
        "pd": pd,
        "np": np,
        "data": isolated_data,
        "dfs": isolated_data,
        "con": con,
        "business": business_obj,
        "apply_tie_breaker": apply_tie_breaker,
        "filter_future_data": filter_future_data,
        "clean_num": clean_num,
        "clean_date": clean_date,
        "DataNotFoundError": DataNotFoundError,
    }
    if isinstance(exec_globals.get("__builtins__"), dict):
        exec_globals["__builtins__"]["DataNotFoundError"] = DataNotFoundError

    try:
        exec(executable_code, exec_globals)
        elapsed_ms = int((time.perf_counter() - t_start) * 1000)
        fin = exec_globals.get("FINAL_RESULT")
        if fin is None and "solution" in exec_globals and callable(exec_globals["solution"]):
            fin = exec_globals["solution"](isolated_data)
        
        unans_src = "none"
        if isinstance(fin, dict):
            unans_src = fin.get("unanswerable_source", "none")

        if return_details:
            return fin, None, elapsed_ms, None, unans_src
        return fin, None, elapsed_ms
    except DataNotFoundError as dne:
        elapsed_ms = int((time.perf_counter() - t_start) * 1000)
        if return_details:
            return None, str(dne), elapsed_ms, "DataNotFoundError", "none"
        return None, str(dne), elapsed_ms
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - t_start) * 1000)
        err_msg = f"{type(exc).__name__}: {exc}"
        err_type = "DataNotFoundError" if "DataNotFoundError" in err_msg else type(exc).__name__
        if return_details:
            return None, err_msg, elapsed_ms, err_type, "none"
        return None, err_msg, elapsed_ms


# ==============================================================================
# THUẬT TOÁN SO KHỚP ĐÁP ÁN CHUẨN MỤC 9 RULEBOOK
# ==============================================================================

def _is_number(val: Any) -> bool:
    if isinstance(val, bool) or not isinstance(val, (int, float, Decimal)):
        return False
    if isinstance(val, float):
        return math.isfinite(val)
    if isinstance(val, Decimal):
        return val.is_finite()
    return True


def _to_decimal(val: Any) -> Optional[Decimal]:
    if not _is_number(val):
        return None
    try:
        if isinstance(val, Decimal):
            return val
        if isinstance(val, int):
            return Decimal(val)
        return Decimal(str(val))
    except Exception:
        return None


def _numeric_equal(pred: Any, gold: Any) -> bool:
    p_num = _to_decimal(pred)
    g_num = _to_decimal(gold)
    if p_num is None or g_num is None:
        return False
    if p_num == g_num:
        return True
    if p_num == p_num.to_integral_value() and g_num == g_num.to_integral_value():
        return False
    try:
        pf, gf = float(p_num), float(g_num)
        if not math.isfinite(pf) or not math.isfinite(gf):
            return False
        ulp = max(math.ulp(pf), math.ulp(gf))
        return abs(pf - gf) <= ulp if ulp < 1 else False
    except Exception:
        return False


def _norm_str(s: Any) -> str:
    val = unicodedata.normalize("NFC", str(s)).strip().casefold()
    return re.sub(r"\s+", " ", val)


def _split_aliases(cell: Any) -> list[str]:
    raw = unicodedata.normalize("NFC", str(cell)).strip()
    return [p.strip() for p in raw.split("|") if p.strip()] if "|" in raw else [raw]


def _compare_cells(pred_cell: Any, gold_cell: Any) -> bool:
    if _is_number(pred_cell) and _is_number(gold_cell):
        if _numeric_equal(pred_cell, gold_cell):
            return True
    pred_str = _norm_str(pred_cell)
    for alias in _split_aliases(gold_cell):
        if _is_number(pred_cell) and _is_number(alias):
            if _numeric_equal(pred_cell, alias):
                return True
        if pred_str == _norm_str(alias):
            return True
    return False


def compare_single_answer(pred_record: dict, gold_record: dict) -> bool:
    """So khớp 1 đáp án dự đoán với đáp án chuẩn theo Rulebook Mục 9."""
    p_type = pred_record.get("type")
    g_type = gold_record.get("type")

    if p_type != g_type:
        return False
    if p_type in ("unanswerable", "abstain"):
        return True

    p_ans = pred_record.get("answer")
    g_ans = gold_record.get("answer")

    if p_ans is None or g_ans is None:
        return False

    if p_type == "number":
        return _numeric_equal(p_ans, g_ans)

    if p_type == "percent":
        p_dec = _to_decimal(p_ans)
        g_dec = _to_decimal(g_ans)
        if p_dec is None or g_dec is None:
            return False
        return p_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == g_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if p_type == "string":
        return _norm_str(p_ans) == _norm_str(g_ans)

    if p_type == "date":
        return str(p_ans).strip() == str(g_ans).strip()

    if p_type == "boolean":
        return bool(p_ans) == bool(g_ans)

    if p_type == "list":
        if not isinstance(p_ans, (list, tuple)) or not isinstance(g_ans, (list, tuple)):
            return False
        if len(p_ans) != len(g_ans):
            return False
        return all(_compare_cells(pa, ga) for pa, ga in zip(p_ans, g_ans))

    if p_type == "table":
        if not isinstance(p_ans, dict) or not isinstance(g_ans, dict):
            return False
        p_cols = p_ans.get("columns", [])
        g_cols = g_ans.get("columns", [])
        if [_norm_str(c) for c in p_cols] != [_norm_str(c) for c in g_cols]:
            return False
        p_rows = p_ans.get("rows", [])
        g_rows = g_ans.get("rows", [])
        if len(p_rows) != len(g_rows):
            return False
        # Kiểm tra bipartite matching cho các hàng của bảng
        used_gold = set()
        for pr in p_rows:
            matched_idx = None
            for idx, gr in enumerate(g_rows):
                if idx in used_gold:
                    continue
                if len(pr) == len(gr) and all(_compare_cells(pc, gc) for pc, gc in zip(pr, gr)):
                    matched_idx = idx
                    break
            if matched_idx is None:
                return False
            used_gold.add(matched_idx)
        return True

    return False


# ==============================================================================
# VẼ BIỂU ĐỒ HÌNH ẢNH TRỰC QUAN THỐNG KÊ (VISUALIZATION DASHBOARD)
# ==============================================================================

def generate_evaluation_dashboard(metrics: dict, output_chart_path: Path | str) -> bool:
    """Tự động vẽ và xuất bảng điều khiển đồ họa trực quan (Dashboard 4 panels) phân tích điểm PA."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[Lưu ý] Chưa cài matplotlib. Hãy cài `pip install matplotlib` để tự động xuất file ảnh thống kê.")
        return False

    chart_path = Path(output_chart_path)
    chart_path.parent.mkdir(parents=True, exist_ok=True)

    total = metrics["total"]
    correct = metrics["correct"]
    wrong = metrics["wrong"]
    abstain = metrics["abstain"]
    pa_score = metrics["pa"]
    acc_score = metrics["accuracy"]
    coverage = metrics["coverage"]

    # Thiết lập giao diện tổng thể
    fig, axes = plt.subplots(2, 2, figsize=(15, 11), dpi=200)
    fig.patch.set_facecolor("#f8f9fa")

    # --- PANEL 1: DONUT CHART PHÂN BỔ KẾT QUẢ & ĐIỂM PA ---
    ax1 = axes[0, 0]
    ax1.set_facecolor("#ffffff")
    sizes = [correct, wrong, abstain]
    labels = [f"Đúng (+1)\n{correct} câu", f"Sai (-1)\n{wrong} câu", f"Từ chối (0)\n{abstain} câu"]
    colors = ["#2ecc71", "#e74c3c", "#f39c12"]
    
    # Lọc các lát có giá trị > 0
    active_indices = [i for i, s in enumerate(sizes) if s > 0]
    sub_sizes = [sizes[i] for i in active_indices]
    sub_labels = [labels[i] for i in active_indices]
    sub_colors = [colors[i] for i in active_indices]

    wedges, _, autotexts = ax1.pie(
        sub_sizes,
        labels=sub_labels,
        colors=sub_colors,
        autopct="%1.1f%%",
        startangle=140,
        pctdistance=0.75,
        wedgeprops=dict(width=0.45, edgecolor="white", linewidth=2),
    )
    for at in autotexts:
        at.set_fontsize(10)
        at.set_weight("bold")

    center_text = f"Penalized Accuracy\nPA: {pa_score:+.4f}\nAccuracy: {acc_score*100:.1f}%\nCoverage: {coverage*100:.1f}%"
    ax1.text(0, 0, center_text, ha="center", va="center", fontsize=11, weight="bold", color="#2c3e50")
    ax1.set_title(f"1. Tổng quan Kết quả Đánh giá ({total} câu hỏi)", fontsize=13, weight="bold", pad=10)

    # --- PANEL 2: BAR CHART ĐIỂM PENALIZED ACCURACY THEO KIỂU ĐÁP ÁN ---
    ax2 = axes[0, 1]
    ax2.set_facecolor("#ffffff")
    breakdown = metrics.get("breakdown", {})
    types = sorted(breakdown.keys())
    pas = [breakdown[t]["pa"] for t in types]
    counts = [breakdown[t]["total"] for t in types]
    bar_colors = ["#2ecc71" if p >= 0.5 else ("#f39c12" if p >= 0 else "#e74c3c") for p in pas]

    y_pos = np.arange(len(types))
    bars = ax2.barh(y_pos, pas, color=bar_colors, edgecolor="none", height=0.55)
    ax2.axvline(0, color="#7f8c8d", linestyle="--", linewidth=1)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels([f"{t} (n={c})" for t, c in zip(types, counts)], fontsize=10)
    ax2.set_xlabel("Penalized Accuracy (PA)", fontsize=10, weight="bold")
    ax2.set_xlim(-1.05, 1.05)
    ax2.set_title("2. Điểm PA Chi tiết theo 8 Kiểu Đáp án", fontsize=13, weight="bold", pad=10)

    for bar, p in zip(bars, pas):
        x_val = bar.get_width()
        offset = 0.03 if x_val >= 0 else -0.15
        ax2.text(x_val + offset, bar.get_y() + bar.get_height() / 2, f"{p:+.2f}", va="center", fontsize=9, weight="bold")

    # --- PANEL 3: STACKED BAR CHART TỶ LỆ ĐÚNG / SAI / ABSTAIN ---
    ax3 = axes[1, 0]
    ax3.set_facecolor("#ffffff")
    c_list = [breakdown[t]["correct"] for t in types]
    w_list = [breakdown[t]["wrong"] for t in types]
    a_list = [breakdown[t]["abstain"] for t in types]

    ax3.bar(types, c_list, label="Đúng (+1)", color="#2ecc71", width=0.55)
    ax3.bar(types, w_list, bottom=c_list, label="Sai (-1)", color="#e74c3c", width=0.55)
    bottom_wa = [c + w for c, w in zip(c_list, w_list)]
    ax3.bar(types, a_list, bottom=bottom_wa, label="Abstain (0)", color="#f39c12", width=0.55)

    ax3.set_ylabel("Số lượng câu hỏi", fontsize=10, weight="bold")
    ax3.set_title("3. Tỷ lệ Đúng / Sai / Từ chối theo từng Kiểu", fontsize=13, weight="bold", pad=10)
    ax3.set_xticks(range(len(types)))
    ax3.set_xticklabels(types, rotation=35, ha="right", fontsize=9)
    ax3.legend(loc="upper right", frameon=True)

    # --- PANEL 4: HIỆU NĂNG THỜI GIAN THỰC THI (LATENCY) ---
    ax4 = axes[1, 1]
    ax4.set_facecolor("#ffffff")
    avg_lats = [breakdown[t].get("avg_latency_ms", 0) for t in types]
    lat_bars = ax4.bar(types, avg_lats, color="#3498db", width=0.55)
    ax4.set_ylabel("Thời gian trung bình (ms)", fontsize=10, weight="bold")
    ax4.set_title("4. Tốc độ Xử lý Trung bình theo Kiểu Đáp án", fontsize=13, weight="bold", pad=10)
    ax4.set_xticks(range(len(types)))
    ax4.set_xticklabels(types, rotation=35, ha="right", fontsize=9)

    for bar, lat in zip(lat_bars, avg_lats):
        ax4.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 15, f"{int(lat)}ms", ha="center", fontsize=8)

    plt.suptitle("BẢNG ĐIỀU KHIỂN ĐÁNH GIÁ ĐỘ CHÍNH XÁC & HIỆU NĂNG (DATAMATE ENGINE)", fontsize=16, weight="bold", y=0.98, color="#1a252f")
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])

    plt.savefig(chart_path, format="png", bbox_inches="tight")
    plt.close()
    return True


# ==============================================================================
# PIPELINE CHẠY SUY LUẬN + ĐÁNH GIÁ TRỌN GÓI
# ==============================================================================

def main():
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Pipeline duy nhất chạy suy luận, so khớp đáp án và xuất biểu đồ hình ảnh thống kê.")
    parser.add_argument("--config", type=str, default=None, help="Đường dẫn file cấu hình YAML tùy chỉnh (mặc định: config/default.yaml)")
    parser.add_argument("--data_dir", type=str, default="competition_data/train", help="Thư mục dữ liệu (mặc định: competition_data/train)")
    parser.add_argument("--gold", type=str, default=None, help="Đường dẫn file đáp án chuẩn answers.jsonl để so khớp")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng câu hỏi cần chạy (ví dụ: --limit 300)")
    parser.add_argument("--output_file", type=str, default="results/predictions.jsonl", help="File xuất kết quả dự đoán JSONL")
    parser.add_argument("--log_dir", type=str, default="results/logs", help="Thư mục lưu log chi tiết từng câu")
    parser.add_argument("--chart_file", type=str, default="results/evaluation_dashboard.png", help="File xuất ảnh biểu đồ thống kê trực quan")
    parser.add_argument("--report_file", type=str, default="results/evaluation_report.json", help="File xuất báo cáo chi tiết JSON")
    parser.add_argument("--model_id", type=str, default=cfg.model.model_id, help=f"Tên hoặc đường dẫn mô hình LLM (mặc định: {cfg.model.model_id})")
    parser.add_argument("--biz", type=str, default=None, help="Lọc theo cửa hàng cụ thể (ví dụ: biz_01)")
    parser.add_argument("--id", type=str, default=None, help="Lọc theo ID câu hỏi cụ thể")
    parser.add_argument("--dry_run", action="store_true", help="Chế độ chạy thử: chỉ in prompt, không nạp GPU")
    parser.add_argument("--no_fill_abstain", action="store_true", help="Không tự động điền abstain cho các câu còn lại khi dùng --limit")
    parser.add_argument("--resume", action="store_true", help="Tiếp tục chạy các câu chưa hoàn thành")
    parser.add_argument("--tau_star", type=float, default=cfg.output.tau_star, help=f"Ngưỡng độ tin cậy tối ưu để từ chối trả lời (mặc định: {cfg.output.tau_star:.2f})")
    parser.add_argument("--timeout", type=int, default=cfg.output.default_timeout, help=f"Thời gian chờ tối đa khi chạy code trong sandbox (giây, mặc định: {cfg.output.default_timeout})")
    parser.add_argument("--in_process", action="store_true", help="Chạy code trực tiếp trong tiến trình thay vì sandbox")
    parser.add_argument("--questions_file", type=str, default=None, help="Đường dẫn file câu hỏi cụ thể")
    parser.add_argument("--sample", type=int, default=None, help="Lấy ngẫu nhiên N câu hỏi để đánh giá")
    parser.add_argument("--seed", type=int, default=42, help="Seed ngẫu nhiên khi lấy mẫu (mặc định: 42)")
    args = parser.parse_args()

    if args.config:
        cfg = load_config(args.config)

    data_dir = Path(args.data_dir)
    questions_path = Path(args.questions_file) if args.questions_file else (data_dir / "questions.jsonl")
    data_root = data_dir / "data"

    if not questions_path.exists():
        print(f"[Lỗi] Không tìm thấy questions.jsonl tại: {questions_path.resolve()}")
        sys.exit(1)

    # Tự động dò tìm file đáp án chuẩn nếu người dùng chưa chỉ định
    gold_path = Path(args.gold) if args.gold else (data_dir / "answers.jsonl")
    has_gold = gold_path.exists()

    with open(questions_path, "r", encoding="utf-8") as f:
        all_questions = [json.loads(line) for line in f if line.strip()]

    gold_map: Dict[str, dict] = {}
    if has_gold:
        with open(gold_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    gold_map[item["id"]] = item

    rulebook_content = load_rulebook(str(data_dir))

    # Lọc câu hỏi theo yêu cầu
    target_questions = all_questions
    if args.biz:
        target_questions = [q for q in target_questions if q.get("business_id") == args.biz]
    if args.id:
        target_questions = [q for q in target_questions if q.get("id") == args.id]
    if args.sample is not None and args.sample < len(target_questions):
        import random
        rng = random.Random(args.seed)
        target_questions = rng.sample(target_questions, args.sample)

    # Resume mode
    existing_completed_ids = set()
    output_path = Path(args.output_file)
    write_mode = "w"
    if args.resume and output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f_ex:
                for line in f_ex:
                    if line.strip():
                        existing_completed_ids.add(json.loads(line).get("id"))
            if existing_completed_ids:
                write_mode = "a"
                target_questions = [q for q in target_questions if q["id"] not in existing_completed_ids]
        except Exception:
            pass

    active_limit = args.limit if args.limit is not None else len(target_questions)
    active_questions = target_questions[:active_limit]
    # Gom nhóm các câu hỏi theo shop để tận dụng tối đa RAM Cache và Persistent Sandbox Worker
    active_questions = sorted(active_questions, key=lambda q: (q.get("business_id", ""), q.get("id", "")))
    active_qids = {q["id"] for q in active_questions} | existing_completed_ids

    print("=" * 80)
    print("DATAMATE — PIPELINE SUY LUẬN, SO KHỚP ĐÁP ÁN & TRỰC QUAN HÓA THỐNG KÊ")
    print("=" * 80)
    print(f"• Dữ liệu đầu vào       : {questions_path.resolve()} ({len(all_questions)} câu)")
    print(f"• Số câu thực hiện chạy : {len(active_questions)} câu (Limit: {args.limit})")
    print(f"• File đáp án chuẩn     : {gold_path.resolve() if has_gold else 'Không có (Chế độ Test ẩn)'}")
    print(f"• File kết quả JSONL    : {output_path.resolve()}")
    print(f"• Ảnh Dashboard thống kê: {Path(args.chart_file).resolve()}")
    print("=" * 80)

    # Khởi tạo mô hình
    llm: Optional[LLMClient] = None
    if not args.dry_run:
        print(f"[Khởi tạo] Đang nạp mô hình {args.model_id} (4-bit NF4)...")
        llm = LLMClient(model_id=args.model_id)
        if not llm.is_loaded:
            print("\n❌ [LỖI NGHIÊM TRỌNG] Không thể nạp trọng số mô hình LLM!")
            print("Quá trình dừng lại để tránh sinh kết quả rỗng. Vui lòng kiểm tra VRAM GPU hoặc thông báo lỗi ở trên.")
            sys.exit(1)

    writer = SubmissionWriter(output_file=args.output_file, log_dir=args.log_dir, mode=write_mode).open()
    written_records: Dict[str, dict] = {}
    latencies: Dict[str, int] = {}
    t_start_all = time.time()

    try:
        for idx, q in enumerate(active_questions, start=1):
            qid = q["id"]
            biz_id = q["business_id"]
            question_text = q["question"]
            as_of_date = q["as_of_date"]

            print(f"\n[{idx}/{len(active_questions)}] Câu hỏi ID: {qid} (Shop: {biz_id})")
            print(f"Nội dung: \"{question_text}\" | as_of_date: {as_of_date}")

            data_dict, con, schema_str, bd, shop_meta, candidates, is_cache = get_cached_business_data(biz_id, data_root)
            if not data_dict:
                print(f"  ❌ [Lỗi nạp dữ liệu shop {biz_id}] {schema_str}")
                sub_ans = make_abstain(f"Data Not Found: {schema_str}")
                writer.write(question_id=qid, answer=sub_ans, code="", raw_result=None, error=schema_str, elapsed_ms=0, confidence=0.0)
                written_records[qid] = {"id": qid, **sub_ans}
                latencies[qid] = 0
                continue

            # Lá chắn 1: Feasibility Gate
            is_feasible, unans_reason = check_feasibility(question_text, as_of_date, shop_meta)
            if not is_feasible:
                print(f"  🛡️ [Feasibility Gate] Bất khả thi ({unans_reason}) -> Trả về 'unanswerable'")
                sub_ans = {"type": "unanswerable", "answer": None}
                writer.write(
                    question_id=qid,
                    answer=sub_ans,
                    code="# Feasibility Gate: Unanswerable detected deterministically",
                    raw_result="unanswerable",
                    error=None,
                    elapsed_ms=0,
                    confidence=1.0,
                    unanswerable_source="gate",
                )
                written_records[qid] = {"id": qid, **sub_ans}
                latencies[qid] = 0
                continue

            if args.dry_run:
                sub_ans = make_abstain("Dry Run Mode")
                writer.write(question_id=qid, answer=sub_ans, code="", raw_result=None, error=None, elapsed_ms=0, confidence=0.0)
                written_records[qid] = {"id": qid, **sub_ans}
                latencies[qid] = 0
                continue

            # Entity Linking & Prompt Building
            biz_dir = data_root / biz_id
            entity_matches = link_entities(question_text, candidates=candidates, threshold=0.55) if candidates else []
            biz_readme = getattr(bd, "readme_text", None) if bd is not None else None
            sys_prompt, user_prompt = build_prompt(
                schema_str=schema_str,
                as_of_date=as_of_date,
                question=question_text,
                rulebook_content=rulebook_content,
                business_note=biz_readme,
                candidates=candidates,
                entity_matches=entity_matches,
                return_messages=True
            )

            # Sinh mã qua LLM (Lượt 1)
            t0 = time.time()
            assert llm is not None
            code_text = llm.generate_code(prompt=user_prompt, system_prompt=sys_prompt, max_new_tokens=1024)
            gen_sec = round(time.time() - t0, 2)

            # Chạy code qua Sandbox (Lượt 1)
            max_self_corrections = 2
            self_correction_count = 0
            raw_result, exec_err, exec_ms, err_type, unans_source = execute_solution(
                code_text=code_text,
                biz_dir=biz_dir,
                data_dict=data_dict,
                con=con,
                business_obj=bd,
                timeout_s=args.timeout,
                use_sandbox=not args.in_process,
                return_details=True,
            )

            # Kiểm tra Sanity Check & Feasibility Authority
            sanity_err = None
            if not exec_err:
                sub_ans_cand = normalize_output(raw_result, question=question_text, code_text=code_text)
                is_sane, sanity_reason = check_result_sanity(sub_ans_cand, question=question_text, code_text=code_text)
                if raw_result == "unanswerable" or sub_ans_cand.get("type") == "unanswerable":
                    sanity_err = "Cơ sở dữ liệu của cửa hàng CÓ ĐẦY ĐỦ số liệu để trả lời câu hỏi này (KHÔNG ĐƯỢC trả về 'unanswerable'!). Hãy kiểm tra lại danh sách bảng và cột để tính toán và trả về kết quả số/danh sách cụ thể."
                    unans_source = "model"
                    print("  ⚠️ [Feasibility Authority] Phát hiện code trả về unanswerable trên câu hỏi khả thi -> Kích hoạt Self-Correction...")
                elif not is_sane:
                    sanity_err = sanity_reason

            # Tự sửa lỗi (Self-Correction Loop tối đa 2 vòng)
            while (exec_err or sanity_err) and self_correction_count < max_self_corrections:
                self_correction_count += 1
                print(f"  🔄 [Self-Correction Vòng {self_correction_count}/{max_self_corrections}] Đang sửa lỗi...")

                # Tạo feedback chuyên biệt nếu gặp DataNotFoundError
                if err_type == "DataNotFoundError" or (exec_err and "DataNotFoundError" in exec_err):
                    actual_schema_summary = []
                    for t_name, df_t in data_dict.items():
                        actual_schema_summary.append(f"- Bảng '{t_name}': các cột {list(df_t.columns)[:15]}")
                    schema_guide = "\n".join(actual_schema_summary[:10])
                    err_feedback = (
                        f"Mã nguồn bị lỗi DataNotFoundError: {exec_err}\n"
                        f"Bảng hoặc cột bạn tìm không tồn tại trong dữ liệu thực tế của shop!\n"
                        f"DANH SÁCH BẢNG VÀ CỘT THỰC TẾ TRONG data:\n{schema_guide}\n"
                        f"HÃY CHỌN ĐÚNG TÊN BẢNG VÀ CỘT Ở TRÊN, KHÔNG ĐOÁN TÊN BẢNG CÓ DẤU '_' HOẶC HẬU TỐ LẠ.\n"
                        f"Hãy viết lại code tính toán chính xác."
                    )
                elif exec_err:
                    err_feedback = f"Lỗi thực thi: {exec_err}"
                else:
                    err_feedback = f"Kết quả tính toán không hợp lý: {sanity_err}"

                retry_sys_prompt, retry_user_prompt = build_retry_prompt(
                    question=question_text,
                    failed_code=code_text,
                    error_message=err_feedback,
                    schema_str=schema_str,
                    as_of_date=as_of_date,
                    retry_round=self_correction_count,
                )
                t_retry = time.time()
                retry_code = llm.generate_code(prompt=retry_user_prompt, system_prompt=retry_sys_prompt, max_new_tokens=1024)
                gen_sec = round(gen_sec + (time.time() - t_retry), 2)
                raw_retry, err_retry, ms_retry, type_retry, src_retry = execute_solution(
                    code_text=retry_code,
                    biz_dir=biz_dir,
                    data_dict=data_dict,
                    con=con,
                    business_obj=bd,
                    timeout_s=args.timeout,
                    use_sandbox=not args.in_process,
                    return_details=True,
                )
                exec_ms += ms_retry

                if not err_retry:
                    sub_ans_cand2 = normalize_output(raw_retry, question=question_text, code_text=retry_code)
                    is_sane2, sanity_reason2 = check_result_sanity(sub_ans_cand2, question=question_text, code_text=retry_code)
                    if raw_retry == "unanswerable" or sub_ans_cand2.get("type") == "unanswerable":
                        sanity_err = f"Sau vòng {self_correction_count}, mô hình vẫn trả về 'unanswerable' trên câu hỏi khả thi."
                        err_type = "UnanswerableReturned"
                        unans_source = "model"
                        code_text = retry_code
                    elif not is_sane2:
                        sanity_err = sanity_reason2
                        err_type = "SanityError"
                        code_text = retry_code
                    else:
                        # Tự sửa lỗi thành công!
                        code_text = retry_code
                        raw_result = raw_retry
                        exec_err = None
                        sanity_err = None
                        unans_source = src_retry
                        err_type = None
                        print(f"  ✅ [Self-Correction] Vòng {self_correction_count} thành công!")
                        break
                else:
                    code_text = retry_code
                    exec_err = err_retry
                    err_type = type_retry
                    unans_source = src_retry

            # Chuẩn hóa & Lá chắn Abstention Gate
            confidence = 0.0
            if exec_err:
                sub_ans = make_abstain(f"Runtime Error sau {self_correction_count} lần sửa: {exec_err}")
                print(f"  ⚠️ [Lỗi thực thi Sandbox] {exec_err} -> Chủ động Abstain (0 điểm)")
            elif sanity_err:
                sub_ans = make_abstain(f"Sanity Check: {sanity_err}")
                print(f"  ⚠️ [Sanity Check không hợp lý] {sanity_err} -> Chủ động Abstain (0 điểm)")
            else:
                sub_ans = normalize_output(raw_result, question=question_text, code_text=code_text)
                grounding_eval_res = evaluate_grounding_coverage(
                    code_text=code_text,
                    question=question_text,
                    entity_matches=entity_matches,
                    temporal_info=temporal_res,
                )
                confidence = compute_confidence_score(
                    sub_ans=sub_ans,
                    exec_error=exec_err,
                    exec_ms=exec_ms,
                    retry_count=self_correction_count,
                    sanity_passed=(sanity_err is None),
                    sanity_error=sanity_err,
                    code_text=code_text,
                    has_feasibility_pass=True,
                    unanswerable_source=unans_source,
                    grounding_eval=grounding_eval_res,
                )
                sub_ans, is_abs = apply_abstention_gate(
                    sub_ans, 
                    confidence=confidence, 
                    threshold=args.tau_star,
                    unanswerable_source=unans_source,
                )
                penalty = grounding_eval_res.get("total_penalty", 0.0)
                if penalty > 0:
                    print(f"  🛡️ [Grounding Penalty] -{penalty:.2f} (Entity: {grounding_eval_res.get('entity_coverage', 1.0)*100:.0f}%, Time: {grounding_eval_res.get('temporal_coverage', 1.0)*100:.0f}%)")
                if is_abs:
                    print(f"  🛡️ [Abstention Gate] C={confidence:.2f} < tau*={args.tau_star:.2f} (Source={unans_source}) -> Ép về Abstain (0 điểm)")
                else:
                    print(f"  ✓ Sinh: {gen_sec}s | Chạy: {exec_ms}ms | Tin cậy: {confidence:.2f} | Đáp án: {sub_ans.get('answer')} ({sub_ans.get('type')})")

            total_lat = int(gen_sec * 1000 + exec_ms)
            sel_tables, sel_cols = extract_referenced_tables_and_columns(code_text, list(data_dict.keys()))
            writer.write(
                question_id=qid,
                answer=sub_ans,
                code=code_text,
                raw_result=raw_result,
                error=exec_err or sanity_err,
                elapsed_ms=total_lat,
                confidence=confidence,
                unanswerable_source=unans_source,
                selected_tables=sel_tables,
                selected_columns=sel_cols,
                self_correction_count=self_correction_count,
            )
            written_records[qid] = {"id": qid, **sub_ans}
            latencies[qid] = total_lat

        # Nếu cần fill abstain cho các câu còn lại
        if not args.no_fill_abstain:
            for q in all_questions:
                if q["id"] not in active_qids:
                    abstain_ans = make_abstain("Default Abstain")
                    writer.write(question_id=q["id"], answer=abstain_ans, code="", raw_result=None, error=None, elapsed_ms=0, confidence=0.0)
                    written_records[q["id"]] = {"id": q["id"], **abstain_ans}
                    latencies[q["id"]] = 0

    finally:
        writer.close()
        for item in _BUSINESS_CACHE.values():
            if item[1]:
                try:
                    item[1].close()
                except Exception:
                    pass

    total_time = round(time.time() - t_start_all, 2)
    print("\n" + "=" * 80)
    print(f"HOÀN THÀNH QUÁ TRÌNH SUY LUẬN! (Thời gian: {total_time}s)")
    print("=" * 80)

    # ==========================================================================
    # SO KHỚP VỚI ĐÁP ÁN CHUẨN & XUẤT BẢNG BÁO CÁO + HÌNH ẢNH TRỰC QUAN
    # ==========================================================================
    if has_gold:
        print("\n[ĐÁNH GIÁ & SO KHỚP ĐÁP ÁN] Đang chấm điểm theo Rulebook...")
        eval_qids = [q["id"] for q in active_questions]
        correct = 0
        wrong = 0
        abstain = 0
        breakdown: Dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0, "wrong": 0, "abstain": 0, "latencies": []})

        for qid in eval_qids:
            if qid not in gold_map:
                continue
            gold_item = gold_map[qid]
            g_type = gold_item.get("type", "unknown")
            breakdown[g_type]["total"] += 1
            breakdown[g_type]["latencies"].append(latencies.get(qid, 0))

            pred_item = written_records.get(qid, {"type": "abstain", "answer": None})
            p_type = pred_item.get("type", "abstain")

            if p_type == "abstain":
                abstain += 1
                breakdown[g_type]["abstain"] += 1
            else:
                is_correct = compare_single_answer(pred_item, gold_item)
                if is_correct:
                    correct += 1
                    breakdown[g_type]["correct"] += 1
                else:
                    wrong += 1
                    breakdown[g_type]["wrong"] += 1

        eval_total = len(eval_qids)
        pa_score = round((correct - wrong) / eval_total, 4) if eval_total else 0.0
        acc_score = round(correct / (correct + wrong), 4) if (correct + wrong) else 0.0
        coverage = round((correct + wrong) / eval_total, 4) if eval_total else 0.0

        for t, stat in breakdown.items():
            tot = stat["total"]
            stat["pa"] = round((stat["correct"] - stat["wrong"]) / tot, 4) if tot else 0.0
            stat["avg_latency_ms"] = round(sum(stat["latencies"]) / len(stat["latencies"]), 1) if stat["latencies"] else 0.0

        metrics = {
            "total": eval_total,
            "correct": correct,
            "wrong": wrong,
            "abstain": abstain,
            "pa": pa_score,
            "accuracy": acc_score,
            "coverage": coverage,
            "total_time_sec": total_time,
            "breakdown": dict(breakdown),
        }

        # In bảng báo cáo trực tiếp
        print("\n" + "=" * 76)
        print("BÁO CÁO KẾT QUẢ ĐÁNH GIÁ (PENALIZED ACCURACY - PA)")
        print("=" * 76)
        print(f"Tổng số câu đánh giá : {eval_total}")
        print(f"Số câu đúng (+1)      : {correct} ({100*correct/eval_total:.1f}%)")
        print(f"Số câu sai (-1)       : {wrong} ({100*wrong/eval_total:.1f}%)")
        print(f"Số câu từ chối (0)    : {abstain} ({100*abstain/eval_total:.1f}%)")
        print(f"Penalized Accuracy (PA): {pa_score:+.4f}")
        print(f"Accuracy (khi trả lời): {acc_score*100:.1f}%")
        print(f"Coverage (Độ bao phủ) : {coverage*100:.1f}%")
        print("-" * 76)
        print(f"{'Kiểu đáp án':<16} | {'Tổng':>6} | {'Đúng':>6} | {'Sai':>6} | {'Abstain':>7} | {'Điểm PA':>8}")
        print("-" * 76)
        for t in sorted(breakdown.keys()):
            st = breakdown[t]
            print(f"{t:<16} | {st['total']:>6} | {st['correct']:>6} | {st['wrong']:>6} | {st['abstain']:>7} | {st['pa']:>+8.3f}")
        print("=" * 76)

        # Lưu báo cáo JSON
        rep_path = Path(args.report_file)
        rep_path.parent.mkdir(parents=True, exist_ok=True)
        with open(rep_path, "w", encoding="utf-8") as f_rep:
            json.dump(metrics, f_rep, ensure_ascii=False, indent=2)
        print(f"• Báo cáo số liệu chi tiết đã lưu tại: {rep_path.resolve()}")

        # TỰ ĐỘNG XUẤT HÌNH ẢNH TRỰC QUAN DASHBOARD
        print("\n[TRỰC QUAN HÓA] Đang vẽ biểu đồ thống kê ra file ảnh...")
        chart_ok = generate_evaluation_dashboard(metrics, args.chart_file)
        if chart_ok:
            print(f"🎉 ĐÃ XUẤT THÀNH CÔNG BIỂU ĐỒ TRỰC QUAN TẠI: {Path(args.chart_file).resolve()}")
    else:
        print("\n[Lưu ý] Không phát hiện file answers.jsonl nên bỏ qua bước so khớp. File submission đã được lưu thành công.")


if __name__ == "__main__":
    main()

