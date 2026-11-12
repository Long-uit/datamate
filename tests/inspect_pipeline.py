"""
Script: tests/inspect_pipeline.py
Mục đích: Công cụ Toàn Năng Kiểm Thử, Chẩn Đoán White-Box & Đánh Giá Toàn Trình (Comprehensive White-Box Diagnostic Inspector & Batch Evaluator).

Bao quát 100% chức năng của `run_eval.py` và nâng cấp toàn diện 8 mục chẩn đoán chuyên sâu:
1. Hồ sơ Metadata Cửa hàng (Shop Metadata Deep-Dive): min_date -> max_date, README, bảng, dòng, sheet merge, header.
2. Checklist Thẩm định Khả thi (Feasibility Gate Checklist): Điều 5 (ngày tương lai), Điều 7 (ngày so sánh), Out-of-Scope concepts.
3. Bảng Thực thể & Lịch Âm (Entity Linker & Lunar Calendar Table): ánh xạ mention -> matched_value -> table.col -> score >= 0.85, ngày âm lịch.
4. So sánh Cắt tỉa Lược đồ (Schema Pruning Diff): Trước vs Sau, bảng giữ lại kèm lý do (intent/entity), bảng bị loại bỏ, tỷ lệ nén.
5. Giải phẫu Prompt & Few-Shot Dynamic (Prompt & Token Budget Anatomy): exemplar title & intent, token breakdown các thành phần.
6. Phân tích Tĩnh AST, An toàn mã & Tự sửa lỗi (AST Safety, Code Extraction & Self-Correction Trace): cú pháp AST, bảng/cột tham chiếu, tiện ích sử dụng, toàn bộ code, trace vòng 1 -> vòng 2.
7. Giải phẫu Toán học Điểm Tự Tin (Confidence Score Breakdown): C_base (exec, sanity, ast, zero) - các mức phạt Grounding (thực thể bỏ sót, thời gian, offtopic table) vs tau* = 0.50.
8. Phân tích Độ lệch Số học, Chuẩn hóa & Chẩn đoán Lỗi tự động (Error & Tolerance Analysis): raw -> normalized, sai số tuyệt đối, sai số %, chẩn đoán sai đơn vị (x1000), quên lọc đơn hủy, làm tròn.

Hỗ trợ 2 chế độ:
- Chế độ Đơn lẻ (Single Question Deep Inspection): Chẩn đoán chi tiết 8 mục, xuất Telemetry JSON & Dashboard PNG độ phân giải cao.
- Chế độ Hàng loạt (Batch Evaluation Mode): Đánh giá tập dữ liệu, tính điểm Penalized Accuracy (PA), Accuracy, Coverage, xuất biểu đồ Pillow 4-panel native và file submission JSONL.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import io
import json
import logging
import math
import os
from pathlib import Path
import random
import re
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import unicodedata

if "PYTORCH_CUDA_ALLOC_CONF" not in os.environ:
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

# Tự động nạp thư mục src và root vào sys.path
_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = str(_ROOT / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

# Nhập các thành phần cốt lõi của DataMate
from datamate.config import load_config
from datamate.exceptions import DataNotFoundError
from datamate.grounding_feasibility.entity_linker import (
    explain_and_expand_abbreviations,
    extract_candidates_from_business,
    link_entities,
    VIETNAMESE_ABBREVIATIONS,
)
from datamate.grounding_feasibility.feasibility import (
    check_feasibility,
    extract_shop_metadata,
)
from datamate.grounding_feasibility.rulebook import load_rulebook
from datamate.grounding_feasibility.temporal import (
    filter_future_data,
    format_temporal_for_prompt,
    get_calendar,
    LunarCalendar,
    resolve_temporal_context,
    TET_SOLAR_RANGES,
)
from datamate.ingestion_schema.cleaner import clean_business
from datamate.ingestion_schema.loader import load_business
from datamate.ingestion_schema.schema_profiler import profile_business_schema
from datamate.llm_execution.client import LLMClient
from datamate.llm_execution.prompt import (
    build_prompt,
    build_retry_prompt,
    classify_intent,
    EXEMPLAR_BANK,
    prune_schema_by_intent,
    retrieve_dynamic_few_shot,
    ShopExecutionMemory,
)
from datamate.llm_execution.sandbox import (
    clean_date,
    clean_num,
    run_code,
    try_deterministic_fallback,
)
from datamate.output_abstention.abstention import (
    apply_abstention_gate,
    compute_confidence_score,
    evaluate_grounding_coverage,
    evaluate_semantic_rule_compliance,
)
from datamate.output_abstention.normalizer import (
    apply_tie_breaker,
    check_result_sanity,
    normalize_output,
)
from datamate.output_abstention.submission import (
    make_abstain,
    SubmissionWriter,
    validate_submission,
    _clean_for_json,
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

    cache_dir = Path("/kaggle/working/.cache_parquet") / biz_id if Path("/kaggle/working").exists() else Path(".cache_parquet") / biz_id
    flag_file = cache_dir / ".ready"
    meta_file = cache_dir / "meta.pkl"

    # 1. Tận dụng Parquet Cache trên ổ đĩa nếu đã có (tốc độ < 0.1s thay vì 68s)
    if flag_file.exists() and meta_file.exists():
        try:
            import pickle
            with open(meta_file, "rb") as f_meta:
                unpickled = pickle.load(f_meta)
                canonical_keys = None
                aliases = {}
                if len(unpickled) == 5:
                    schema_summary, shop_meta, candidates, bd, meta_extra = unpickled
                    if isinstance(meta_extra, dict):
                        aliases = meta_extra
                    elif isinstance(meta_extra, (list, set)):
                        canonical_keys = set(meta_extra)
                elif len(unpickled) == 4:
                    schema_summary, shop_meta, candidates, bd = unpickled
                else:
                    schema_summary, shop_meta, candidates = unpickled
                    bd = None

                data_dict: Dict[str, pd.DataFrame] = {}
                seen_signatures = set()
                for p_file in sorted(cache_dir.glob("*.parquet")):
                    t_key = p_file.stem
                    if canonical_keys and t_key not in canonical_keys:
                        continue
                    df_t = pd.read_parquet(p_file)
                    # Chống nạp trùng bảng do cache cũ lưu nhiều alias cho cùng 1 file
                    sig = (len(df_t), tuple(df_t.columns.tolist()[:10]))
                    if not canonical_keys and sig in seen_signatures:
                        continue
                    seen_signatures.add(sig)
                    data_dict[t_key] = df_t

                if data_dict:
                    setattr(data_dict, "_aliases", aliases)
                    return data_dict, None, schema_summary, bd, shop_meta, candidates
        except Exception:
            pass

    try:
        raw_bd = load_business(biz_dir)
        bd = clean_business(raw_bd)
        con = None  # Tối ưu hóa nạp kép: LLM 100% dùng Pandas trên data, bỏ nạp SQLite mặc định
        data_dict: Dict[str, pd.DataFrame] = {}
        aliases: Dict[str, str] = {}
        for ti in bd.tables:
            t_base = Path(ti.fixed_file_name).stem if getattr(ti, "fixed_file_name", None) else ti.table_id
            t_name = f"{t_base}_{ti.sheet_name}" if ti.sheet_name and ti.sheet_name != "Sheet1" else t_base

            # Chỉ lưu bảng chính tắc 1 lần duy nhất để chống cộng trùng bảng (nhân 2x/4x doanh thu)
            data_dict[t_name] = ti.df
            if ti.sheet_name and ti.sheet_name != "Sheet1" and ti.sheet_name != t_name:
                aliases[ti.sheet_name] = t_name
            if t_base != t_name:
                aliases[t_base] = t_name
            if ti.table_id and ti.table_id != t_name:
                aliases[ti.table_id] = t_name

        setattr(data_dict, "_aliases", aliases)

        # Sử dụng Rich Schema Profiler hiển thị kiểu dữ liệu, min-max date và giá trị mẫu (tối ưu 15 cột)
        schema_summary = profile_business_schema(bd, max_cols=15)
        shop_meta = extract_shop_metadata(business_obj=bd, data_dict=data_dict)
        candidates = extract_candidates_from_business(bd)

        # Lưu Parquet Cache để nạp tức thì trong các lượt sau
        try:
            import pickle
            cache_dir.mkdir(parents=True, exist_ok=True)
            for k, df_table in data_dict.items():
                if isinstance(df_table, pd.DataFrame):
                    df_table.to_parquet(cache_dir / f"{k}.parquet", index=False)
            with open(meta_file, "wb") as f_meta:
                pickle.dump((schema_summary, shop_meta, candidates, bd, aliases), f_meta)
            flag_file.touch()
        except Exception:
            pass

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
# THỰC THI MÃ NGUỒN AN TOÀN TRONG SANDBOX & TRÍCH XUẤT AST
# ==============================================================================

def validate_code_safety(code_str: str) -> Tuple[bool, Optional[str]]:
    """Kiểm tra tính an toàn và tính hợp lệ cú pháp của mã nguồn bằng AST."""
    if not code_str or not code_str.strip():
        return False, "Mã nguồn rỗng"
    try:
        tree = ast.parse(code_str)
    except SyntaxError as se:
        return False, f"Lỗi cú pháp Python (SyntaxError): {se.msg} ở dòng {se.lineno}"

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names] if hasattr(node, "names") else []
            for n in names:
                if any(bad in n for bad in ["socket", "urllib", "requests", "shutil"]):
                    return False, f"Mã nguồn chứa thư viện cấm truy cập mạng/hệ thống: {n}"
    return True, None


def extract_referenced_tables_and_columns(code_str: str, available_tables: List[str]) -> Tuple[List[str], List[str], List[str]]:
    """Trích xuất tên các bảng, cột và tiện ích được truy cập trong mã nguồn."""
    sel_tables = []
    sel_cols = []
    sel_utils = []
    if not code_str:
        return sel_tables, sel_cols, sel_utils

    for t in available_tables:
        if t in code_str:
            sel_tables.append(t)

    col_matches = re.findall(r"\[\s*[\'\"]([^\'\"]+)[\'\"]\s*\]", code_str)
    for c in col_matches:
        if c not in sel_cols and c not in sel_tables:
            sel_cols.append(c)

    for u in ["clean_num", "clean_date", "apply_tie_breaker", "filter_future_data", "pct", "normalize_text"]:
        if u in code_str:
            sel_utils.append(u)

    return sel_tables, sel_cols[:15], sel_utils


def execute_solution(
    code_text: str,
    biz_dir: Path,
    data_dict: Dict[str, pd.DataFrame],
    con: Any,
    business_obj: Any,
    timeout_s: int = 30,
    use_sandbox: bool = True,
    return_details: bool = False,
    as_of_date: Any = None,
) -> Tuple[Any, ...]:
    """Thực thi mã nguồn mô hình sinh ra trong subprocess sandbox hoặc môi trường in-process."""
    if use_sandbox:
        res = run_code(code_text.strip(), business_dir=biz_dir, timeout_s=timeout_s, as_of_date=as_of_date)
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

    # In-process fallback: truyền trực tiếp code_text cho execute_code_in_env để dùng smart_data đã lọc và sắp xếp
    from datamate.llm_execution.worker import execute_code_in_env

    t_start = time.perf_counter()
    res_payload = execute_code_in_env(
        code_str=code_text.strip(),
        data_dict=data_dict,
        business=business_obj,
        con=con,
        pd=pd,
        np=np,
        apply_tie_breaker=apply_tie_breaker,
        filter_future_data=filter_future_data,
        clean_num=clean_num,
        clean_date=clean_date,
        DataNotFoundError=DataNotFoundError,
        as_of_date=as_of_date,
    )
    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    unans_src = res_payload.get("unanswerable_source", "none")
    fin = res_payload.get("final_result")
    if isinstance(fin, dict):
        unans_src = fin.get("unanswerable_source", unans_src)

    if res_payload.get("ok"):
        if return_details:
            return fin, None, elapsed_ms, None, unans_src
        return fin, None, elapsed_ms
    else:
        err_msg = res_payload.get("error") or "Lỗi thực thi"
        err_type = res_payload.get("error_type") or ("DataNotFoundError" if "DataNotFoundError" in str(err_msg) else "RuntimeError")
        if return_details:
            return None, err_msg, elapsed_ms, err_type, unans_src
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
    val = unicodedata.normalize("NFC", str(s)).lower()
    out_chars = [ch if (ch.isalnum() or ch.isspace()) else " " for ch in val]
    return re.sub(r"\s+", " ", "".join(out_chars)).strip()


def _split_aliases(cell: Any) -> list[str]:
    raw = unicodedata.normalize("NFC", str(cell)).strip()
    return [p.strip() for p in raw.split("|") if p.strip()] if "|" in raw else [raw]


def _to_bool(val: Any) -> Optional[bool]:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        if val == 1:
            return True
        if val == 0:
            return False
        return None
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("true", "1", "có", "đúng", "yes", "t", "y"):
            return True
        if s in ("false", "0", "không", "sai", "no", "f", "n"):
            return False
        return None
    return None


def _compare_cells(pred_cell: Any, gold_cell: Any, aliases: Optional[Any] = None) -> bool:
    try:
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
        if aliases is not None:
            if isinstance(aliases, (str, bytes)):
                alias_list = [aliases]
            elif isinstance(aliases, (int, float, Decimal)) and not isinstance(aliases, bool):
                alias_list = [aliases]
            elif isinstance(aliases, (list, tuple, set)):
                alias_list = list(aliases)
            elif isinstance(aliases, dict):
                alias_list = list(aliases.values())
            else:
                alias_list = [aliases]
            for a in alias_list:
                if a is None or isinstance(a, bool):
                    continue
                if isinstance(a, (list, tuple, set)):
                    sub_aliases = list(a)
                else:
                    sub_aliases = [a]
                for sa in sub_aliases:
                    if sa is None or isinstance(sa, bool):
                        continue
                    if _is_number(pred_cell) and _is_number(sa):
                        if _numeric_equal(pred_cell, sa):
                            return True
                    for alias in _split_aliases(sa):
                        if _is_number(pred_cell) and _is_number(alias):
                            if _numeric_equal(pred_cell, alias):
                                return True
                        if pred_str == _norm_str(alias):
                            return True
        return False
    except Exception:
        return False


def compare_single_answer(pred_record: dict, gold_record: dict) -> bool:
    """So khớp 1 đáp án dự đoán với đáp án chuẩn theo Rulebook Mục 9 (hỗ trợ alias product code/tên)."""
    try:
        if not isinstance(pred_record, dict) or not isinstance(gold_record, dict):
            return False

        p_type = pred_record.get("type")
        g_type = gold_record.get("type")

        if not p_type or not g_type or p_type != g_type:
            return False
        if p_type in ("unanswerable", "abstain"):
            return True

        p_ans = pred_record.get("answer")
        g_ans = gold_record.get("answer")

        if p_ans is None or g_ans is None:
            return False

        g_alias = gold_record.get("alias")

        if p_type == "number":
            return _numeric_equal(p_ans, g_ans)

        if p_type == "percent":
            p_dec = _to_decimal(p_ans)
            g_dec = _to_decimal(g_ans)
            if p_dec is None or g_dec is None:
                return False
            try:
                return p_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == g_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except Exception:
                return False

        if p_type == "string":
            if isinstance(g_alias, (str, bytes, int, float, Decimal)) and not isinstance(g_alias, bool):
                cell_aliases = [g_alias]
            elif isinstance(g_alias, (list, tuple, set)):
                cell_aliases = list(g_alias)
            else:
                cell_aliases = None
            return _compare_cells(p_ans, g_ans, cell_aliases)

        if p_type == "date":
            p_str = str(p_ans).strip()
            g_str = str(g_ans).strip()
            if p_str == g_str:
                return True
            if len(g_str) == 10 and len(p_str) > 10 and p_str[:10] == g_str:
                return True
            if len(p_str) == 10 and len(g_str) > 10 and g_str[:10] == p_str:
                return True
            return False

        if p_type == "boolean":
            p_b = _to_bool(p_ans)
            g_b = _to_bool(g_ans)
            if p_b is None or g_b is None:
                return False
            return p_b == g_b

        if p_type == "list":
            if not isinstance(p_ans, (list, tuple)) or not isinstance(g_ans, (list, tuple)):
                return False
            if len(p_ans) != len(g_ans):
                return False
            has_per_element_alias = (
                isinstance(g_alias, (list, tuple)) and len(g_alias) == len(g_ans)
            )
            return all(
                _compare_cells(
                    pa,
                    ga,
                    g_alias[idx] if (has_per_element_alias and isinstance(g_alias[idx], (list, tuple, set, str, bytes, int, float, Decimal))) else None,
                )
                for idx, (pa, ga) in enumerate(zip(p_ans, g_ans))
            )

        if p_type == "table":
            if not isinstance(p_ans, dict) or not isinstance(g_ans, dict):
                return False

            p_cols = p_ans.get("columns")
            g_cols = g_ans.get("columns")
            if not isinstance(p_cols, (list, tuple)) or not isinstance(g_cols, (list, tuple)):
                return False
            if [_norm_str(c) for c in p_cols] != [_norm_str(c) for c in g_cols]:
                return False

            p_rows = p_ans.get("rows")
            g_rows = g_ans.get("rows")
            if not isinstance(p_rows, (list, tuple)) or not isinstance(g_rows, (list, tuple)):
                return False
            if len(p_rows) != len(g_rows):
                return False

            if any(not isinstance(r, (list, tuple)) for r in p_rows):
                return False
            if any(not isinstance(r, (list, tuple)) for r in g_rows):
                return False

            has_per_row_alias = (
                isinstance(g_alias, (list, tuple)) and len(g_alias) == len(g_rows)
            )
            used_gold = set()
            for pr in p_rows:
                matched_idx = None
                for idx, gr in enumerate(g_rows):
                    if idx in used_gold:
                        continue
                    if len(pr) != len(gr):
                        continue
                    # 1. So khớp trực tiếp toàn bộ ô trong dòng
                    if all(_compare_cells(pc, gc) for pc, gc in zip(pr, gr)):
                        matched_idx = idx
                        break
                    # 2. So khớp có hỗ trợ alias cho ô thực thể (mã khách hàng / mã sản phẩm)
                    row_alias = (
                        g_alias[idx]
                        if (has_per_row_alias and isinstance(g_alias[idx], (list, tuple, set, str, bytes, int, float, Decimal)))
                        else None
                    )
                    if row_alias is not None:
                        row_matched = False
                        for c_idx in range(len(gr)):
                            if _compare_cells(pr[c_idx], gr[c_idx], row_alias):
                                if all(_compare_cells(pr[i], gr[i]) for i in range(len(gr)) if i != c_idx):
                                    row_matched = True
                                    break
                        if row_matched:
                            matched_idx = idx
                            break
                if matched_idx is None:
                    return False
                used_gold.add(matched_idx)
            return True

        return False
    except Exception:
        return False


def analyze_numerical_deviation(pred_ans: Any, gold_ans: Any, pred_type: str, gold_type: str) -> Dict[str, Any]:
    """Phân tích chuyên sâu độ lệch số học và chẩn đoán nguyên nhân lỗi định lượng."""
    res = {
        "is_applicable": False,
        "abs_diff": None,
        "pct_diff": None,
        "diagnostic_hypothesis": None,
    }
    p_dec = _to_decimal(pred_ans)
    g_dec = _to_decimal(gold_ans)
    if p_dec is None or g_dec is None:
        return res

    res["is_applicable"] = True
    abs_d = abs(p_dec - g_dec)
    res["abs_diff"] = float(abs_d)

    if g_dec != 0:
        pct_d = abs(abs_d / g_dec) * 100
        res["pct_diff"] = float(pct_d)
    else:
        res["pct_diff"] = 0.0

    # Chẩn đoán lỗi phổ biến
    pf = float(p_dec)
    gf = float(g_dec)
    if gf != 0:
        ratio = pf / gf
        if 990 <= ratio <= 1010 or 0.00099 <= ratio <= 0.00101:
            res["diagnostic_hypothesis"] = "LỆCH ĐƠN VỊ TIỀN TỆ (Nghìn đồng vs Đồng, tỷ lệ x1000)."
        elif 1.05 <= ratio <= 1.30:
            res["diagnostic_hypothesis"] = "CÓ THỂ QUÊN LỌC ĐƠN HỦY / TRẢ LẠI (Giá trị dự đoán cao hơn chuẩn 5-30%)."
        elif 0.70 <= ratio <= 0.95:
            res["diagnostic_hypothesis"] = "CÓ THỂ LỌC THIẾU DÒNG HOẶC ÁP DỤNG TRÙNG ĐIỀU KIỆN (Dự đoán thấp hơn chuẩn 5-30%)."
        elif abs_d <= Decimal("0.05"):
            res["diagnostic_hypothesis"] = "SAI SỐ LÀM TRÒN THẬP PHÂN (Chênh lệch <= 0.05 đơn vị)."

    return res


# ==============================================================================
# HÀM TRỰC QUAN HÓA DASHBOARD (PILLOW NATIVE DASHBOARD GENERATOR)
# ==============================================================================

def render_diagnostic_dashboard(telemetry: Dict[str, Any], output_path: Path) -> Path:
    """
    Vẽ dashboard chẩn đoán trực quan độ phân giải cao (1200x860 px) bằng Pillow:
    - Card 1: Header thông tin câu hỏi, cửa hàng, ngày as_of_date và huy hiệu kết quả.
    - Card 2: Biểu đồ thời gian thực thi từng module (Latency Breakdown Bar Chart).
    - Card 3: Thước đo Điểm Tin Cậy Calibrated Confidence Gauge vs Ngưỡng tau* = 0.50.
    - Card 4: Thanh tiến trình Độ Bám Thực Thể & Thời Gian (Grounding Coverage).
    - Card 5: Khung hiển thị Trước / Sau khi mở rộng viết tắt tiếng Việt.
    - Card 6: Hộp phân tích và Đề xuất tối ưu hóa dành cho AI.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1200, 860
    bg_color = (18, 22, 30)          # Nền tối sang trọng
    card_bg = (28, 34, 46)           # Màu nền thẻ
    card_border = (45, 55, 72)       # Viền thẻ
    text_white = (248, 250, 252)
    text_muted = (148, 163, 184)
    text_accent = (56, 189, 248)     # Xanh cyan

    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # 1. HEADER CARD
    draw.rectangle([20, 20, 1180, 115], fill=card_bg, outline=card_border, width=2)
    draw.text((40, 32), "DATAMATE — MODULAR DIAGNOSTIC INSPECTOR DASHBOARD", fill=text_accent)
    
    qid = telemetry.get("question_id", "q_unknown")
    biz_id = telemetry.get("business_id", "biz_unknown")
    as_of = telemetry.get("as_of_date", "2026-01-01")
    draw.text((40, 58), f"Question ID: {qid}  |  Shop: {biz_id}  |  As-of-date: {as_of}", fill=text_muted)
    
    status_label = telemetry.get("eval_status_label", "EVALUATED")
    status_score = telemetry.get("eval_score", 0.0)
    if status_score > 0:
        badge_color = (16, 185, 129)   # Xanh lá
        badge_text = f"CORRECT (+1.0) | {status_label}"
    elif status_score < 0:
        badge_color = (239, 68, 68)    # Đỏ
        badge_text = f"WRONG (-1.0) | {status_label}"
    else:
        badge_color = (245, 158, 11)   # Vàng hổ phách
        badge_text = f"ABSTAIN (0.0) | {status_label}"

    draw.rectangle([820, 35, 1160, 95], fill=badge_color)
    draw.text((835, 55), badge_text, fill=(255, 255, 255))

    # 2. PANEL TRÁI: BIỂU ĐỒ THỜI GIAN TỪNG MODULE (LATENCY BREAKDOWN)
    draw.rectangle([20, 130, 580, 470], fill=card_bg, outline=card_border, width=2)
    draw.text((40, 145), "1. THỜI GIAN THỰC THI TỪNG MODULE (LATENCY PROFILING)", fill=text_accent)

    latencies = telemetry.get("latencies_ms", {})
    total_ms = telemetry.get("total_latency_ms", 1.0)
    modules = [
        ("Ingestion & Profiler", latencies.get("ingest_schema", 0.0)),
        ("Feasibility Gate", latencies.get("feasibility", 0.0)),
        ("Vietnamese Grounding", latencies.get("grounding", 0.0)),
        ("Prompt Assembly", latencies.get("prompt_build", 0.0)),
        ("LLM Generation (3B)", latencies.get("llm_gen", 0.0)),
        ("Sandbox Execution", latencies.get("sandbox_exec", 0.0)),
        ("Normalizer & Gate", latencies.get("normalizer", 0.0)),
    ]

    max_lat = max([lat for _, lat in modules] + [1.0])
    bar_y = 185
    for name, lat in modules:
        pct = (lat / total_ms * 100.0) if total_ms > 0 else 0.0
        bar_len = int((lat / max_lat) * 260) if max_lat > 0 else 0
        bar_len = max(4, min(260, bar_len))

        draw.text((40, bar_y), f"{name[:20]:<20}", fill=text_white)
        draw.rectangle([220, bar_y + 2, 220 + bar_len, bar_y + 14], fill=(99, 102, 241))
        draw.text((490, bar_y), f"{lat:6.1f}ms ({pct:4.1f}%)", fill=text_muted)
        bar_y += 38

    draw.line([40, 445, 560, 445], fill=card_border, width=1)
    draw.text((40, 450), f"TỔNG THỜI GIAN TOÀN TRÌNH: {total_ms:.1f} ms ({total_ms/1000:.2f}s)", fill=text_accent)

    # 3. PANEL PHẢI TRÊN: CALIBRATED CONFIDENCE & GATE GAUGE
    draw.rectangle([600, 130, 1180, 470], fill=card_bg, outline=card_border, width=2)
    draw.text((620, 145), "2. ĐIỂM TIN CẬY CALIBRATED CONFIDENCE & GROUNDING", fill=text_accent)

    conf = telemetry.get("confidence_score", 0.0)
    tau = telemetry.get("threshold_tau_star", 0.50)
    g_eval = telemetry.get("grounding_eval", {})
    e_cov = g_eval.get("entity_coverage", 1.0) * 100
    t_cov = g_eval.get("temporal_coverage", 1.0) * 100
    penalty = g_eval.get("total_penalty", 0.0)

    draw.text((620, 185), f"Độ Tin Cậy C: {conf:.2f} / 1.00  (Ngưỡng tau*: {tau:.2f})", fill=text_white)
    draw.rectangle([620, 210, 1140, 235], fill=(45, 55, 72))
    fill_w = int(conf * 520)
    bar_color = (16, 185, 129) if conf >= tau else (245, 158, 11)
    if fill_w > 0:
        draw.rectangle([620, 210, 620 + fill_w, 235], fill=bar_color)
    tau_x = 620 + int(tau * 520)
    draw.line([tau_x, 205, tau_x, 240], fill=(239, 68, 68), width=3)
    draw.text((tau_x - 30, 242), f"Ngưỡng tau*={tau:.2f}", fill=(239, 68, 68))

    draw.text((620, 280), f"Độ bám thực thể (Entity Coverage)  : {e_cov:.1f}%", fill=text_white)
    draw.rectangle([620, 305, 1140, 320], fill=(45, 55, 72))
    draw.rectangle([620, 305, 620 + int(e_cov * 5.2), 320], fill=(56, 189, 248))

    draw.text((620, 340), f"Độ bám thời gian (Temporal Coverage): {t_cov:.1f}%", fill=text_white)
    draw.rectangle([620, 365, 1140, 380], fill=(45, 55, 72))
    draw.rectangle([620, 365, 620 + int(t_cov * 5.2), 380], fill=(168, 85, 247))

    draw.text((620, 400), f"Tổng điểm phạt Grounding Penalty: -{penalty:.2f}", fill=(244, 63, 94))
    gate_decision = "CHO PHÉP NỘP ĐÁP ÁN" if conf >= tau else "LÁ CHẮN ÉP VỀ ABSTAIN AN TOÀN"
    draw.text((620, 430), f"Quyết định Cổng Từ Chối: {gate_decision}", fill=bar_color)

    # 4. PANEL DƯỚI TRÁI: VIETNAMESE TEXT PROCESSING TRƯỚC VÀ SAU
    draw.rectangle([20, 485, 580, 840], fill=card_bg, outline=card_border, width=2)
    draw.text((40, 500), "3. XỬ LÝ TIẾNG VIỆT & MỞ RỘNG VIẾT TẮT (TRƯỚC & SAU)", fill=text_accent)

    orig_q = telemetry.get("original_question", "")
    norm_q = telemetry.get("normalized_question", "")
    replaced = telemetry.get("expanded_abbreviations", {})
    intent = telemetry.get("intent", "aggregation")
    t_desc = telemetry.get("temporal_desc", "")

    draw.text((40, 530), "• Câu hỏi GỐC (Trước khi chuẩn hóa):", fill=(251, 191, 36))
    draw.text((40, 550), f"  \"{orig_q[:70]}\"", fill=text_white)
    if len(orig_q) > 70:
        draw.text((40, 570), f"  \"{orig_q[70:140]}\"", fill=text_white)

    draw.text((40, 600), "• Câu hỏi CHUẨN HÓA (Sau khi mở rộng viết tắt):", fill=(52, 211, 153))
    draw.text((40, 620), f"  \"{norm_q[:70]}\"", fill=text_white)
    if len(norm_q) > 70:
        draw.text((40, 640), f"  \"{norm_q[70:140]}\"", fill=text_white)

    rep_str = ", ".join([f"'{k}' -> '{v}'" for k, v in list(replaced.items())[:4]]) or "Không có từ viết tắt"
    draw.text((40, 675), f"• Viết tắt phát hiện: {rep_str}", fill=text_muted)
    draw.text((40, 705), f"• Ý định nhận diện  : {intent}", fill=text_white)
    draw.text((40, 735), f"• Khoảng thời gian  : {t_desc[:55]}", fill=text_white)

    pred_ans = telemetry.get("predicted_answer")
    gold_ans = telemetry.get("gold_answer")
    draw.text((40, 775), f"• DỰ ĐOÁN : {str(pred_ans)[:35]}", fill=(56, 189, 248))
    draw.text((40, 805), f"• ĐÁP ÁN   : {str(gold_ans)[:35]}", fill=(16, 185, 129))

    # 5. PANEL DƯỚI PHẢI: AI DIAGNOSTIC TELEMETRY & RECOMMENDATIONS
    draw.rectangle([600, 485, 1180, 840], fill=card_bg, outline=card_border, width=2)
    draw.text((620, 500), "4. AI TELEMETRY & ĐỀ XUẤT TỐI ƯU HÓA TỰ ĐỘNG", fill=text_accent)

    rec_list = telemetry.get("ai_recommendations", [])
    dy = 535
    for i, rec in enumerate(rec_list[:6], 1):
        draw.text((620, dy), f"{i}. {rec[:68]}", fill=text_white)
        if len(rec) > 68:
            dy += 22
            draw.text((640, dy), f"{rec[68:136]}", fill=text_muted)
        dy += 28

    img.save(output_path, quality=95)
    return output_path


def render_batch_evaluation_dashboard(metrics: Dict[str, Any], output_path: Path | str) -> bool:
    """Vẽ dashboard thống kê đánh giá hàng loạt (4 panels) chuẩn độ nét cao bằng Pillow (Native)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1400, 950
    bg_color = (248, 250, 252)
    card_bg = (255, 255, 255)
    card_border = (226, 232, 240)
    text_dark = (30, 41, 59)
    text_muted = (100, 116, 139)

    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    total = metrics.get("total", 0)
    correct = metrics.get("correct", 0)
    wrong = metrics.get("wrong", 0)
    abstain = metrics.get("abstain", 0)
    pa = metrics.get("pa", 0.0)
    acc = metrics.get("accuracy", 0.0)
    cov = metrics.get("coverage", 0.0)
    breakdown = metrics.get("breakdown", {})

    # Header
    draw.rectangle([20, 20, 1380, 100], fill=(30, 41, 59))
    draw.text((40, 35), "DATAMATE — BENCHMARK EVALUATION DASHBOARD", fill=(56, 189, 248))
    draw.text((40, 65), f"Penalized Accuracy (PA): {pa:+.4f}  |  Accuracy: {acc*100:.1f}%  |  Coverage: {cov*100:.1f}%  |  Total: {total} câu", fill=(241, 245, 249))

    # Panel 1: Thống kê tổng quan (Donut / Card)
    draw.rectangle([20, 120, 680, 500], fill=card_bg, outline=card_border, width=2)
    draw.text((40, 135), "1. TỔNG QUAN PHÂN BỔ KẾT QUẢ & ĐIỂM PA", fill=(14, 116, 144))
    
    # Vẽ 3 thẻ lớn: Đúng, Sai, Abstain
    cards = [
        ("ĐÚNG (+1.0)", correct, f"{correct/total*100:.1f}%" if total else "0%", (16, 185, 129)),
        ("SAI (-1.0)", wrong, f"{wrong/total*100:.1f}%" if total else "0%", (239, 68, 68)),
        ("TỪ CHỐI (0.0)", abstain, f"{abstain/total*100:.1f}%" if total else "0%", (245, 158, 11)),
    ]
    cx = 50
    for title, count, pct, col in cards:
        draw.rectangle([cx, 180, cx + 180, 310], fill=(248, 250, 252), outline=col, width=2)
        draw.text((cx + 20, 195), title, fill=col)
        draw.text((cx + 20, 230), f"{count}", fill=text_dark)
        draw.text((cx + 20, 275), f"Tỷ lệ: {pct}", fill=text_muted)
        cx += 210

    # Bảng số liệu chi tiết
    draw.text((50, 340), f"• Điểm thi Penalized Accuracy (PA) : {pa:+.4f}", fill=text_dark)
    draw.text((50, 375), f"• Độ chính xác khi trả lời (Accuracy): {acc*100:.1f}%", fill=text_dark)
    draw.text((50, 410), f"• Tỷ lệ tham gia trả lời (Coverage) : {cov*100:.1f}%", fill=text_dark)
    draw.text((50, 445), f"• Thời gian chạy tổng cộng           : {metrics.get('total_time_sec', 0):.1f}s", fill=text_muted)

    # Panel 2: Điểm PA theo từng loại (Bar chart)
    draw.rectangle([700, 120, 1380, 500], fill=card_bg, outline=card_border, width=2)
    draw.text((720, 135), "2. ĐIỂM PENALIZED ACCURACY THEO KIỂU ĐÁP ÁN", fill=(14, 116, 144))

    types = sorted(breakdown.keys())
    by = 180
    for t in types[:8]:
        st = breakdown[t]
        t_pa = st.get("pa", 0.0)
        t_tot = st.get("total", 0)
        draw.text((720, by), f"{t:<14} (n={t_tot:>2})", fill=text_dark)
        # Trục 0 ở x=980
        center_x = 1000
        bar_len = int(t_pa * 220)
        if bar_len >= 0:
            draw.rectangle([center_x, by + 2, center_x + bar_len, by + 16], fill=(16, 185, 129))
        else:
            draw.rectangle([center_x + bar_len, by + 2, center_x, by + 16], fill=(239, 68, 68))
        draw.line([center_x, by - 2, center_x, by + 20], fill=text_muted, width=1)
        draw.text((1240, by), f"{t_pa:+.2f}", fill=text_dark)
        by += 38

    # Panel 3: Stacked Bar Chart theo loại
    draw.rectangle([20, 520, 680, 920], fill=card_bg, outline=card_border, width=2)
    draw.text((40, 535), "3. TỶ LỆ ĐÚNG / SAI / ABSTAIN THEO TỪNG KIỂU", fill=(14, 116, 144))

    sy = 580
    for t in types[:8]:
        st = breakdown[t]
        tot = st.get("total", 1)
        c_pct = st.get("correct", 0) / tot
        w_pct = st.get("wrong", 0) / tot
        a_pct = st.get("abstain", 0) / tot

        draw.text((40, sy), f"{t:<14}", fill=text_dark)
        sx = 180
        w_c = int(c_pct * 360)
        w_w = int(w_pct * 360)
        w_a = int(a_pct * 360)
        if w_c > 0:
            draw.rectangle([sx, sy + 2, sx + w_c, sy + 16], fill=(16, 185, 129))
        if w_w > 0:
            draw.rectangle([sx + w_c, sy + 2, sx + w_c + w_w, sy + 16], fill=(239, 68, 68))
        if w_a > 0:
            draw.rectangle([sx + w_c + w_w, sy + 2, sx + w_c + w_w + w_a, sy + 16], fill=(245, 158, 11))

        draw.text((560, sy), f"C:{st.get('correct',0)} W:{st.get('wrong',0)} A:{st.get('abstain',0)}", fill=text_muted)
        sy += 40

    # Panel 4: Độ trễ xử lý trung bình theo loại
    draw.rectangle([700, 520, 1380, 920], fill=card_bg, outline=card_border, width=2)
    draw.text((720, 535), "4. ĐỘ TRỄ XỬ LÝ TRUNG BÌNH THEO KIỂU ĐÁP ÁN (ms)", fill=(14, 116, 144))

    max_lat = max([st.get("avg_latency_ms", 1.0) for st in breakdown.values()] + [1.0])
    ly = 580
    for t in types[:8]:
        st = breakdown[t]
        alat = st.get("avg_latency_ms", 0.0)
        draw.text((720, ly), f"{t:<14}", fill=text_dark)
        bar_len = int((alat / max_lat) * 380) if max_lat > 0 else 0
        draw.rectangle([860, ly + 2, 860 + bar_len, ly + 16], fill=(59, 130, 246))
        draw.text((1260, ly), f"{int(alat)} ms", fill=text_dark)
        ly += 40

    img.save(output_path, quality=95)
    return True


# ==============================================================================
# HÀM SINH HƯỚNG ĐỀ XUẤT TỰ ĐỘNG CHO AI
# ==============================================================================

def generate_ai_recommendations(
    is_match: bool,
    pred_ans: Any,
    gold_ans: Any,
    pred_type: str,
    gold_type: str,
    confidence: float,
    threshold: float,
    exec_err: Optional[str],
    sanity_err: Optional[str],
    grounding_eval: Dict[str, Any],
    intent: str,
    question_text: str,
    deviation_analysis: Dict[str, Any],
) -> List[str]:
    """Tự động phân tích telemetry và sinh hướng đề xuất thông minh mà AI có thể đọc và hành động."""
    recs: List[str] = []

    if is_match and pred_type != "abstain":
        recs.append("KẾT QUẢ ĐẠT CHUẨN (+1.0): Logic pipeline ăn khớp hoàn hảo từ Intent đến Execution.")
        recs.append("Duy trì cấu trúc Prompt và chiến lược Schema Pruning hiện tại cho nhóm intent này.")
        if confidence < 0.80:
            recs.append(f"Lưu ý: Độ tin cậy C={confidence:.2f} còn hơi thấp, có thể giảm bớt Grounding Penalty để tránh rủi ro.")
        return recs

    if pred_type == "abstain":
        recs.append("TRẠNG THÁI TỪ CHỐI (ABSTAIN - 0.0): Bảo toàn điểm số an toàn không bị trừ điểm.")
        if exec_err:
            recs.append(f"Khắc phục Runtime Error: '{exec_err[:50]}...'. Bổ sung thư viện hoặc alias cột tương ứng.")
        elif sanity_err:
            recs.append(f"Khắc phục Sanity Check: '{sanity_err[:55]}...'. Kiểm tra công thức tính và điều kiện lọc.")
        elif confidence < threshold:
            missed = grounding_eval.get("missed_mentions", [])
            if missed:
                m_str = ", ".join([m.get("term", "") for m in missed[:2]])
                recs.append(f"Bổ sung lọc thực thể bỏ sót: '{m_str}' trong prompt hoặc vòng Self-Correction lượt 2.")
            if grounding_eval.get("temporal_coverage", 1.0) < 1.0:
                recs.append("Bổ sung ràng buộc ngày tháng ISO vào code để xóa mức phạt Temporal Penalty.")
        return recs

    # Trường hợp trả lời sai (-1.0)
    recs.append("CẢNH BÁO BỊ PHẠT (-1.0): Đáp án sai lệch so với Ground Truth của Ban tổ chức.")
    if deviation_analysis.get("diagnostic_hypothesis"):
        recs.append(f"Chẩn đoán sai số: {deviation_analysis['diagnostic_hypothesis']}")

    if "đơn" in question_text.lower() and ("bnhiu" in question_text.lower() or "bao nhiêu" in question_text.lower()):
        recs.append("Kiểm tra nhầm lẫn Count vs Sum: Câu hỏi có thể hỏi số lượng đơn (Count) nhưng code tính tổng tiền (Sum).")
    if intent in ("rate_percentage", "time_series"):
        recs.append("Kiểm tra thứ tự mốc so sánh: Đảm bảo công thức (V_hiện_tại - V_quá_khứ) / V_quá_khứ * 100.0.")
    if pred_type != gold_type:
        recs.append(f"Sai lệch định dạng đầu ra: Dự đoán kiểu '{pred_type}' trong khi đáp án chuẩn là '{gold_type}'.")
    recs.append("Kích hoạt chuyển sang 'abstain' nếu độ tin cậy của dạng bài này chưa vượt qua 0.65.")

    return recs


# ==============================================================================
# HÀM CHẨN ĐOÁN CHI TIẾT 1 CÂU HỎI (SINGLE INSPECTION MODE)
# ==============================================================================

def run_single_inspection(
    target_q: Dict[str, Any],
    gold_record: Optional[Dict[str, Any]],
    data_dir: Path,
    data_root: Path,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    qid = target_q["id"]
    biz_id = target_q["business_id"]
    question_text = target_q["question"]
    as_of_date = target_q["as_of_date"]

    print("\n" + "=" * 80)
    print(" 🔬  DATAMATE MODULAR WHITE-BOX DIAGNOSTICS & TELEMETRY INSPECTOR")
    print("=" * 80)
    print(f"• Question ID   : {qid}")
    print(f"• Business ID   : {biz_id}")
    print(f"• as_of_date    : {as_of_date}")
    print(f"• Câu hỏi Gốc   : \"{question_text}\"")
    if gold_record:
        print(f"• Đáp án Chuẩn  : {gold_record.get('answer')} (Type: {gold_record.get('type')})")
    print("=" * 80)

    latencies: Dict[str, float] = {}

    # --------------------------------------------------------------------------
    # MỤC 1: XỬ LÝ TIẾNG VIỆT & MỞ RỘNG VIẾT TẮT
    # --------------------------------------------------------------------------
    t0 = time.perf_counter()
    normalized_q, replaced_abbr = explain_and_expand_abbreviations(question_text)
    ms_vn = (time.perf_counter() - t0) * 1000

    print("\n" + "┌" + "─" * 78 + "┐")
    print("│ [MỤC 1] XỬ LÝ TIẾNG VIỆT TỪ VIẾT TẮT SANG DẠNG CHUẨN (TRƯỚC & SAU)          │")
    print("├" + "─" * 78 + "┤")
    print(f"│ • TRƯỚC (Gốc)      : \"{question_text}\"")
    print(f"│ • SAU (Chuẩn hóa)  : \"{normalized_q}\"")
    if replaced_abbr:
        rep_str = ", ".join([f"'{k}' -> '{v}'" for k, v in replaced_abbr.items()])
        print(f"│ • Viết tắt đã mở   : {rep_str}")
    else:
        print("│ • Viết tắt đã mở   : (Không chứa từ viết tắt trong từ điển)")
    print("└" + "─" * 78 + "┘")

    # --------------------------------------------------------------------------
    # MỤC 2: HỒ SƠ METADATA & DỮ LIỆU CỬA HÀNG (SHOP METADATA DEEP-DIVE)
    # --------------------------------------------------------------------------
    t0 = time.perf_counter()
    data_dict, con, raw_schema_str, bd, shop_meta, candidates = load_business_data(biz_id, data_root)
    ms_ingest = (time.perf_counter() - t0) * 1000
    latencies["ingest_schema"] = ms_ingest

    print(f"\n--- [BƯỚC 1] NẠP DỮ LIỆU CỬA HÀNG (⏱️ {ms_ingest:.2f} ms) ---")
    print(f"  • Thư mục shop      : {(data_root / biz_id).resolve()}")
    print(f"  • Số bảng đọc được  : {len(bd.tables) if bd else 0} bảng")
    if shop_meta:
        print(f"  • Khoảng ngày shop  : [{shop_meta.get('min_date')} -> {shop_meta.get('max_date')}] (so với as_of_date: {as_of_date})")
    print(f"  • Tổng thực thể trích xuất: {len(candidates)} ứng viên")
    if bd and bd.readme_text:
        snippet = bd.readme_text[:120].replace('\n', ' ')
        print(f"  • README Cửa hàng   : \"{snippet}...\"")

    print("\n┌──────────────────────────────────────────────────────────────────────────────┐")
    print("│ [MỤC 2] CHI TIẾT BẢNG DỮ LIỆU & DÒ TÌM HEADER                                │")
    print("├──────────────────────────────────────────────────────────────────────────────┤")
    for ti in getattr(bd, "tables", []):
        t_base = Path(ti.fixed_file_name).stem if getattr(ti, "fixed_file_name", None) else ti.table_id
        sheet_info = f", sheet: '{ti.sheet_name}'" if ti.sheet_name else ""
        merge_info = f", gộp {len(ti.merged_sheets)} sheet" if getattr(ti, "merged_sheets", None) else ""
        header_info = f", header dòng {ti.header_row_detected}" if ti.header_row_detected is not None else ""
        print(f"│ • Bảng '{t_base}' ({ti.table_id}): {ti.n_rows} dòng, {len(ti.columns)} cột{sheet_info}{merge_info}{header_info}")
    print("└──────────────────────────────────────────────────────────────────────────────┘")

    # --------------------------------------------------------------------------
    # MỤC 3: CHECKLIST THẨM ĐỊNH KHẢ THI (FEASIBILITY GATE CHECKLIST)
    # --------------------------------------------------------------------------
    t0 = time.perf_counter()
    is_feasible, unans_reason = check_feasibility(question_text, as_of_date, shop_meta)
    ms_feas = (time.perf_counter() - t0) * 1000
    latencies["feasibility"] = ms_feas

    calendar_path = data_dir / "calendar.csv"
    cal_str = str(calendar_path) if calendar_path.exists() else None
    temp_info = resolve_temporal_context(question_text, as_of_date, calendar_path=cal_str)

    print(f"\n--- [BƯỚC 2] FEASIBILITY GATE CHECKLIST (⏱️ {ms_feas:.2f} ms) ---")
    print("┌──────────────────────────────────────────────────────────────────────────────┐")
    print("│ [MỤC 3] CHECKLIST TIÊU CHÍ RULEBOOK THẨM ĐỊNH KHẢ THI                         │")
    print("├──────────────────────────────────────────────────────────────────────────────┤")
    # Điều 5: Ngày tương lai
    q_start = temp_info.get("start_date")
    q_end = temp_info.get("end_date")
    d5_pass = True
    if q_start and as_of_date and q_start > as_of_date:
        d5_pass = False
    print(f"│ • Điều 5 (Ngày câu hỏi <= as_of_date {as_of_date}): [{'PASS' if d5_pass else 'FAIL'}] (Khoảng: {q_start} -> {q_end})")

    # Điều 7: Dữ liệu kỳ đối chiếu
    comp_start = temp_info.get("comparison_start")
    comp_end = temp_info.get("comparison_end")
    d7_pass = True
    if comp_start and shop_meta.get("min_date") and comp_start < shop_meta.get("min_date"):
        d7_pass = False
    comp_label = f"[{'PASS' if d7_pass else 'FAIL'}] (Khoảng: {comp_start} -> {comp_end})" if comp_start else "[N/A] (Câu hỏi không có so sánh)"
    print(f"│ • Điều 7 (Dữ liệu kỳ đối chiếu >= min_date): {comp_label}")

    # Khái niệm ngoài phạm vi
    out_of_scope = any(k in normalized_q for k in ["lương", "mặt bằng", "tiền điện", "tiền nước", "thuế thu nhập"])
    print(f"│ • Khái niệm ngoài schema (Lương, mặt bằng, điện nước): [{'CÓ PHÁT HIỆN' if out_of_scope else 'KHÔNG'}]")
    print(f"│ 👉 KẾT LUẬN CỔNG FEASIBILITY GATE: {'KHẢ THI TRẢ LỜI (FEASIBLE)' if is_feasible else f'TỪ CHỐI TẤT ĐỊNH (UNANSWERABLE: {unans_reason})'}")
    print("└──────────────────────────────────────────────────────────────────────────────┘")

    # --------------------------------------------------------------------------
    # MỤC 4: GROUNDING (BẢNG THỰC THỂ & LỊCH ÂM)
    # --------------------------------------------------------------------------
    t0 = time.perf_counter()
    entity_matches = link_entities(normalized_q, candidates=candidates, threshold=0.55) if candidates else []
    ms_grounding = (time.perf_counter() - t0) * 1000
    latencies["grounding"] = ms_grounding

    cal_obj = get_calendar(cal_str)
    lunar_info = cal_obj.get_lunar_info(as_of_date) if cal_obj and as_of_date else None

    print(f"\n--- [BƯỚC 3] GROUNDING (ĐỊNH VỊ THỜI GIAN, LỊCH ÂM & THỰC THỂ) (⏱️ {ms_grounding:.2f} ms) ---")
    print(f"  • Mốc thời gian     : {temp_info['description']}")
    print(f"  • Khoảng ISO        : [{temp_info.get('start_date')} -> {temp_info.get('end_date')}]")
    if lunar_info:
        print(f"  • Ngày Âm của as-of : Ngày {lunar_info.get('lunar_day')}/{lunar_info.get('lunar_month')}/{lunar_info.get('lunar_year')} (Âm lịch)")
    print(f"  • Gợi ý lọc Pandas  : {temp_info['code_hint']}")

    print("\n┌──────────────────────────────────────────────────────────────────────────────┐")
    print("│ [MỤC 4] BẢNG ÁNH XẠ THỰC THỂ (ENTITY LINKER MAPPING TABLE)                   │")
    print("├──────────────────────────────────────────────────────────────────────────────┤")
    if entity_matches:
        print(f"│ {'Cụm từ (Mention)':<22} | {'Khớp trong DB':<22} | {'Bảng.Cột':<18} | {'Score':>6} │")
        print("├──────────────────────────────────────────────────────────────────────────────┤")
        for m in entity_matches[:8]:
            mention = getattr(m, "mention", getattr(m, "matched_value", ""))[:20]
            val = getattr(m, "matched_value", "")[:20]
            src_t = getattr(m, "source_table", "") or (m.metadata.get("source_table", "") if getattr(m, "metadata", None) else "")
            src_c = getattr(m, "source_col", "") or (m.metadata.get("source_col", "") if getattr(m, "metadata", None) else "")
            src = f"{src_t}.{src_c}" if (src_t or src_c) else "(Chưa gán)"
            score = getattr(m, "score", 0.0)
            print(f"│ {mention:<22} | {val:<22} | {src[:18]:<18} | {score:>6.2f} │")
    else:
        print("│ • Không phát hiện thực thể tên riêng biệt (Mã/Tên SP, Khách hàng) trong câu. │")
    print("└──────────────────────────────────────────────────────────────────────────────┘")

    # --------------------------------------------------------------------------
    # MỤC 5: SO SÁNH CẮT TỈA LƯỢC ĐỒ (SCHEMA PRUNING DIFF)
    # --------------------------------------------------------------------------
    t0 = time.perf_counter()
    intent = classify_intent(normalized_q)
    pruned_schema = prune_schema_by_intent(
        schema_str=raw_schema_str,
        intent=intent,
        question=normalized_q,
        entity_matches=entity_matches,
    )
    ms_schema_prune = (time.perf_counter() - t0) * 1000

    raw_len = len(raw_schema_str)
    pruned_len = len(pruned_schema)
    reduc_pct = ((raw_len - pruned_len) / raw_len * 100) if raw_len > 0 else 0.0

    print("\n┌──────────────────────────────────────────────────────────────────────────────┐")
    print("│ [MỤC 5] SO SÁNH CẮT TỈA LƯỢC ĐỒ (SCHEMA PRUNING DIFF)                        │")
    print("├──────────────────────────────────────────────────────────────────────────────┤")
    print(f"│ • Ý định phân loại : '{intent}'")
    print(f"│ • Kích thước Schema: {raw_len} ký tự -> {pruned_len} ký tự (Giảm {reduc_pct:.1f}% nhiễu)")
    
    # Liệt kê chính xác bảng giữ lại và bảng lược bỏ từ schema
    all_schema_tables = []
    for line in raw_schema_str.splitlines():
        if line.startswith("- Bảng '") and "'" in line[8:]:
            all_schema_tables.append(line[8:].split("'")[0])

    retained_tables = []
    for line in pruned_schema.splitlines():
        if line.startswith("- Bảng '") and "'" in line[8:]:
            retained_tables.append(line[8:].split("'")[0])

    dropped_tables = [t for t in all_schema_tables if t not in retained_tables]
    print(f"│ • Bảng giữ lại     : {', '.join(retained_tables) if retained_tables else '(Không có)'}")
    print(f"│ • Bảng lược bỏ     : {', '.join(dropped_tables) if dropped_tables else '(Không có)'}")
    print("└──────────────────────────────────────────────────────────────────────────────┘")

    # --------------------------------------------------------------------------
    # MỤC 6: GIẢI PHẪU PROMPT & FEW-SHOT DYNAMIC (TOKEN BUDGET ANATOMY)
    # --------------------------------------------------------------------------
    t0 = time.perf_counter()
    few_shot = retrieve_dynamic_few_shot(question=normalized_q, intent=intent, entity_matches=entity_matches)
    rulebook_content = load_rulebook(str(data_dir))
    sys_prompt, user_prompt = build_prompt(
        schema_str=pruned_schema,
        as_of_date=as_of_date,
        question=normalized_q,
        rulebook_content=rulebook_content,
        business_note=getattr(bd, "readme_text", None) if bd else None,
        candidates=candidates,
        entity_matches=entity_matches,
        return_messages=True,
    )
    ms_prompt = (time.perf_counter() - t0) * 1000
    latencies["prompt_build"] = ms_prompt

    exemplar_title = few_shot.splitlines()[0] if few_shot else "Mặc định (Aggregation)"
    sys_tok = len(sys_prompt) // 3
    schema_tok = len(pruned_schema) // 3
    fewshot_tok = len(few_shot) // 3
    user_tok = len(user_prompt) // 3
    total_tok = sys_tok + user_tok

    print(f"\n--- [BƯỚC 4] PROMPT BUILDER & TOKEN BUDGET (⏱️ {ms_prompt:.2f} ms) ---")
    print("┌──────────────────────────────────────────────────────────────────────────────┐")
    print("│ [MỤC 6] GIẢI PHẪU PROMPT & PHÂN BỔ NGÂN SÁCH TOKEN (TOKEN BUDGET)            │")
    print("├──────────────────────────────────────────────────────────────────────────────┤")
    print(f"│ • Ví dụ Few-Shot đã chọn : {exemplar_title[:56]}")
    print(f"│ • System Prompt (Cache)  : {len(sys_prompt):>5} ký tự (~{sys_tok:>4} tokens)")
    print(f"│   ├─ Lược đồ (Pruned)    : {len(pruned_schema):>5} ký tự (~{schema_tok:>4} tokens)")
    print(f"│   └─ Ví dụ (Few-Shot)    : {len(few_shot):>5} ký tự (~{fewshot_tok:>4} tokens)")
    print(f"│ • User Prompt            : {len(user_prompt):>5} ký tự (~{user_tok:>4} tokens)")
    print(f"│ 👉 TỔNG PROMPT (GỬI LLM) : {len(sys_prompt) + len(user_prompt):>5} ký tự (~{total_tok:>4} tokens)")
    print("└──────────────────────────────────────────────────────────────────────────────┘")

    # --------------------------------------------------------------------------
    # MỤC 7: LLM CODE GENERATION, AN TOÀN AST & VÒNG LẶP TỰ SỬA LỖI
    # --------------------------------------------------------------------------
    code_text = ""
    gen_time_s = 0.0
    self_correction_trace = []

    if not is_feasible:
        code_text = '# Feasibility Gate detected unanswerable\ndef solution(data):\n    return "unanswerable"'
        latencies["llm_gen"] = 0.0
        print(f"\n--- [BƯỚC 5] LLM CODE GENERATION (Bỏ qua vì câu Unanswerable) ---")
    elif args.with_llm:
        print(f"\n--- [BƯỚC 5] LLM CODE GENERATION (Qwen2.5-Coder-3B GPU) ---")
        print(f"  • Nạp mô hình {args.model_id} (4-bit NF4)...")
        t0 = time.time()
        client = LLMClient(model_id=args.model_id, auto_load=True)
        code_text = client.generate_code(prompt=user_prompt, system_prompt=sys_prompt, max_new_tokens=getattr(args, "max_new_tokens", 1536))
        gen_time_s = time.time() - t0
        latencies["llm_gen"] = gen_time_s * 1000
        print(f"  • Thời gian sinh mã : {gen_time_s:.2f}s ({latencies['llm_gen']:.1f}ms)")
    else:
        latencies["llm_gen"] = 0.0
        print(f"\n--- [BƯỚC 5] LLM CODE GENERATION (Chế độ Dry-Run: Bỏ qua nạp GPU) ---")
        print("  💡 Thêm cờ --with_llm để sinh mã thật bằng GPU.")
        code_text = 'def solution(data):\n    # Dry run mock code\n    return "abstain"'

    # Kiểm tra AST Safety
    is_safe_ast, ast_err = validate_code_safety(code_text)
    ref_tables, ref_cols, ref_utils = extract_referenced_tables_and_columns(code_text, list(data_dict.keys()))

    print("\n┌──────────────────────────────────────────────────────────────────────────────┐")
    print("│ [MỤC 7] PHÂN TÍCH TĨNH MÃ NGUỒN (STATIC AST SAFETY & CODE INSPECTION)         │")
    print("├──────────────────────────────────────────────────────────────────────────────┤")
    print(f"│ • Cú pháp & An toàn AST : [{'PASS - HỢP LỆ' if is_safe_ast else f'FAIL - {ast_err}'}]")
    print(f"│ • Bảng code truy cập    : {', '.join(ref_tables) if ref_tables else '(Không phát hiện)'}")
    print(f"│ • Cột code truy cập     : {', '.join(ref_cols[:8]) if ref_cols else '(Không phát hiện)'}")
    print(f"│ • Tiện ích sử dụng      : {', '.join(ref_utils) if ref_utils else '(Không dùng)'}")
    print("├──────────────────────────────────────────────────────────────────────────────┤")
    print("│ [TOÀN BỘ MÃ NGUỒN PYTHON SINH RA]:                                           │")
    for line in code_text.strip().splitlines():
        print(f"│   {line}")
    print("└──────────────────────────────────────────────────────────────────────────────┘")

    # --------------------------------------------------------------------------
    # THỰC THI SANDBOX & TỰ SỬA LỖI (SELF-CORRECTION)
    # --------------------------------------------------------------------------
    t0 = time.perf_counter()
    raw_result = None
    exec_err = None
    exec_ms = 0.0

    if not is_feasible:
        raw_result = "unanswerable"
        exec_ms = 0.0
    elif args.with_llm:
        raw_result, exec_err, exec_ms, err_type, unans_source = execute_solution(
            code_text=code_text,
            biz_dir=data_root / biz_id,
            data_dict=data_dict,
            con=con,
            business_obj=bd,
            timeout_s=30,
            use_sandbox=True,
            return_details=True,
        )
        # Self-correction nếu gặp lỗi
        if exec_err:
            self_correction_trace.append(f"Vòng 1 Lỗi: {exec_err}")
            print(f"  🔄 [Self-Correction Vòng 1] Gặp lỗi: {exec_err}. Đang kích hoạt sửa lỗi...")
            retry_sys, retry_user = build_retry_prompt(
                question=normalized_q,
                failed_code=code_text,
                error_message=f"Lỗi thực thi: {exec_err}",
                schema_str=pruned_schema,
                as_of_date=as_of_date,
                retry_round=1,
                temporal_text=format_temporal_for_prompt(temp_info),
            )
            retry_code = client.generate_code(prompt=retry_user, system_prompt=retry_sys, max_new_tokens=getattr(args, "max_new_tokens", 1536))
            r_res, r_err, r_ms = execute_solution(
                code_text=retry_code,
                biz_dir=data_root / biz_id,
                data_dict=data_dict,
                con=con,
                business_obj=bd,
                timeout_s=30,
                use_sandbox=True,
            )
            exec_ms += r_ms
            if not r_err:
                code_text = retry_code
                raw_result = r_res
                exec_err = None
                self_correction_trace.append("Vòng 2 Sửa thành công!")
                print("  ✅ [Self-Correction] Vòng 2 sửa lỗi thành công!")
            else:
                self_correction_trace.append(f"Vòng 2 Vẫn lỗi: {r_err}")
    else:
        raw_result = "abstain"
        exec_ms = 0.0

    ms_sandbox = (time.perf_counter() - t0) * 1000
    latencies["sandbox_exec"] = ms_sandbox

    print(f"\n--- [BƯỚC 6] EXECUTION SANDBOX (⏱️ {ms_sandbox:.2f} ms) ---")
    if args.with_llm:
        print(f"  • Thời gian chạy code: {exec_ms:.2f} ms")
    else:
        print(f"  • Thời gian chạy code: {exec_ms:.2f} ms (Chế độ Mock)")
    print(f"  • Lỗi Sandbox (nếu)  : {exec_err or 'Không có (Thực thi thành công)'}")
    print(f"  • Kết quả thô (Raw)  : {raw_result} (Kiểu: {type(raw_result).__name__})")

    # --------------------------------------------------------------------------
    # MỤC 8: GIẢI PHẪU TOÁN HỌC ĐIỂM TỰ TIN CALIBRATED CONFIDENCE
    # --------------------------------------------------------------------------
    t0 = time.perf_counter()
    grounding_eval = evaluate_grounding_coverage(
        code_text=code_text,
        question=normalized_q,
        entity_matches=entity_matches,
        temporal_info=temp_info,
    )

    sanity_err = None
    if not args.with_llm and is_feasible:
        final_ans = make_abstain("Dry Run Mock")
        confidence = 0.0
    elif exec_err:
        final_ans = make_abstain(f"Execution Error: {exec_err}")
        confidence = 0.0
    elif not is_feasible:
        final_ans = {"type": "unanswerable", "answer": None}
        confidence = 1.0
    else:
        norm_cand = normalize_output(raw_result, question=normalized_q, code_text=code_text)
        is_sane, sanity_reason = check_result_sanity(norm_cand, question=normalized_q, code_text=code_text)
        if not is_sane:
            sanity_err = sanity_reason
            final_ans = make_abstain(f"Sanity Check: {sanity_reason}")
            confidence = 0.0
        else:
            confidence = compute_confidence_score(
                sub_ans=norm_cand,
                exec_error=exec_err,
                exec_ms=int(exec_ms),
                retry_count=len(self_correction_trace),
                sanity_passed=True,
                code_text=code_text,
                has_feasibility_pass=is_feasible,
                grounding_eval=grounding_eval,
            )
            final_ans, is_abs = apply_abstention_gate(norm_cand, confidence=confidence, threshold=0.50)

    ms_output = (time.perf_counter() - t0) * 1000
    latencies["normalizer"] = ms_output
    total_pipeline_ms = sum(latencies.values())

    print("\n┌──────────────────────────────────────────────────────────────────────────────┐")
    print("│ [MỤC 8] GIẢI PHẪU TOÁN HỌC ĐIỂM TỰ TIN (CALIBRATED CONFIDENCE BREAKDOWN)      │")
    print("├──────────────────────────────────────────────────────────────────────────────┤")
    if not args.with_llm and is_feasible:
        base_score = 0.0
        print(f"│ • Chế độ Dry-Run Mock   : Mã giả lập 'abstain' -> C ép về 0.00               │")
        print(f"│ • Điểm cơ sở (C_base)   : {base_score:.2f} (Không nạp GPU/LLM)                              │")
    else:
        c_exec = 0.40 if not exec_err else 0.00
        c_sanity = 0.35 if not sanity_err else 0.00
        c_ast = 0.25 if is_safe_ast else 0.00
        base_score = c_exec + c_sanity + c_ast
        print(f"│ • Điểm cơ sở (C_base)   : {base_score:.2f} (Exec={c_exec:.2f}, Sanity={c_sanity:.2f}, AST={c_ast:.2f})")

    e_pen = grounding_eval.get("entity_penalty", 0.0)
    t_pen = grounding_eval.get("temporal_penalty", 0.0)
    tab_pen = grounding_eval.get("table_penalty", 0.0)
    tot_pen = grounding_eval.get("total_penalty", 0.0)
    missed_m = [m.get("term", "") for m in grounding_eval.get("missed_mentions", [])]

    print(f"│ • Phạt thực thể (P_ent) : -{e_pen:.2f} (Độ phủ: {grounding_eval.get('entity_coverage', 1.0)*100:.0f}%)")
    if missed_m:
        print(f"│   └─ Thực thể bỏ sót    : {', '.join(missed_m)}")
    print(f"│ • Phạt thời gian (P_tem): -{t_pen:.2f} (Độ phủ: {grounding_eval.get('temporal_coverage', 1.0)*100:.0f}%)")
    print(f"│ • Phạt bảng ngoài (P_tb): -{tab_pen:.2f}")

    if final_ans.get("type") == "abstain":
        print(f"│ • Luật an toàn Abstain  : Output = 'abstain' -> Ép điểm tin cậy C = 0.00      │")

    print(f"│ • ĐỘ TIN CẬY CUỐI CÙNG  : C = {confidence:.2f} (So với ngưỡng tau* = 0.50)")
    gate_decision = "CHO PHÉP NỘP ĐÁP ÁN" if confidence >= 0.50 else "LÁ CHẮN ÉP VỀ ABSTAIN (0 ĐIỂM AN TOÀN)"
    print(f"│ 👉 QUYẾT ĐỊNH CỦA CỔNG  : {gate_decision}")
    print("└──────────────────────────────────────────────────────────────────────────────┘")

    # --------------------------------------------------------------------------
    # MỤC 9: PHÂN TÍCH ĐỘ LỆCH SỐ HỌC, BIẾN ĐỔI NORMALIZER & SO SÁNH GOLD
    # --------------------------------------------------------------------------
    pred_val = final_ans.get("answer")
    pred_type = final_ans.get("type", "abstain")
    gold_val = gold_record.get("answer") if gold_record else None
    gold_type = gold_record.get("type") if gold_record else "unknown"

    is_match = False
    eval_score = 0.0
    eval_label = "CHƯA CÓ ĐÁP ÁN"

    if gold_record:
        is_match = compare_single_answer(final_ans, gold_record)
        if pred_type == "abstain":
            eval_score = 0.0
            eval_label = "TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0)"
        elif is_match:
            eval_score = 1.0
            eval_label = "HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0)"
        else:
            eval_score = -1.0
            eval_label = "SAI LỆCH ĐÁP ÁN (WRONG - -1.0)"

    dev_analysis = analyze_numerical_deviation(pred_val, gold_val, pred_type, gold_type)

    print("\n┌──────────────────────────────────────────────────────────────────────────────┐")
    print("│ [MỤC 9] GIẢI THÍCH THỐNG KÊ KẾT QUẢ & SO SÁNH VỚI ĐÁP ÁN CHUẨN (GOLD)        │")
    print("├──────────────────────────────────────────────────────────────────────────────┤")
    print(f"│ • DỰ ĐOÁN (PRED) : {str(pred_val)[:58]} (Type: {pred_type})")
    print(f"│ • CHUẨN   (GOLD) : {str(gold_val)[:58]} (Type: {gold_type})")
    print(f"│ • KẾT LUẬN       : {eval_label}")
    if dev_analysis.get("is_applicable") and not is_match and pred_type != "abstain":
        print("├──────────────────────────────────────────────────────────────────────────────┤")
        print(f"│ • Sai số tuyệt đối: {dev_analysis['abs_diff']}")
        print(f"│ • Sai số phần trăm: {dev_analysis['pct_diff']:.2f}%")
        if dev_analysis.get("diagnostic_hypothesis"):
            print(f"│ 💡 CHẨN ĐOÁN LỖI TỰ ĐỘNG: {dev_analysis['diagnostic_hypothesis']}")
    print("└──────────────────────────────────────────────────────────────────────────────┘")
    print("-" * 80)
    print("BẢNG ĐỘ TRỄ CHI TIẾT TỪNG MODULE:")
    for m_name, m_lat in [
        ("1. Ingestion & Loader", latencies.get("ingest_schema", 0.0)),
        ("2. Feasibility Gate", latencies.get("feasibility", 0.0)),
        ("3. Grounding & Entity", latencies.get("grounding", 0.0)),
        ("4. Prompt Assembly", latencies.get("prompt_build", 0.0)),
        ("5. LLM Code Gen (3B)", latencies.get("llm_gen", 0.0)),
        ("6. Sandbox Subprocess", latencies.get("sandbox_exec", 0.0)),
        ("7. Normalizer & Gate", latencies.get("normalizer", 0.0)),
    ]:
        m_pct = (m_lat / total_pipeline_ms * 100.0) if total_pipeline_ms > 0 else 0.0
        print(f"  • {m_name:<25}: {m_lat:8.2f} ms ({m_pct:5.1f}%)")
    print(f"👉 TỔNG THỜI GIAN TOÀN TRÌNH: {total_pipeline_ms:8.2f} ms ({total_pipeline_ms/1000:.2f}s)")
    print("=" * 80)

    # --------------------------------------------------------------------------
    # MỤC 10: TỔNG HỢP TELEMETRY & ĐỀ XUẤT CHO AI
    # --------------------------------------------------------------------------
    ai_recs = generate_ai_recommendations(
        is_match=is_match,
        pred_ans=pred_val,
        gold_ans=gold_val,
        pred_type=pred_type,
        gold_type=gold_type,
        confidence=confidence,
        threshold=0.50,
        exec_err=exec_err,
        sanity_err=sanity_err,
        grounding_eval=grounding_eval,
        intent=intent,
        question_text=normalized_q,
        deviation_analysis=dev_analysis,
    )

    print("\n┌──────────────────────────────────────────────────────────────────────────────┐")
    print("│ [MỤC 10] THÔNG TIN TELEMETRY & HƯỚNG ĐỀ XUẤT CHO AI                           │")
    print("├──────────────────────────────────────────────────────────────────────────────┤")
    for i, rec in enumerate(ai_recs, 1):
        print(f"│ {i}. {rec}")
    print("└──────────────────────────────────────────────────────────────────────────────┘")

    telemetry_payload = {
        "question_id": qid,
        "business_id": biz_id,
        "as_of_date": as_of_date,
        "original_question": question_text,
        "normalized_question": normalized_q,
        "expanded_abbreviations": replaced_abbr,
        "intent": intent,
        "temporal_desc": temp_info.get("description", ""),
        "temporal_range": [temp_info.get("start_date"), temp_info.get("end_date")],
        "entity_matches": [getattr(m, "matched_value", str(m)) for m in entity_matches],
        "pruned_schema": pruned_schema,
        "code_text": code_text,
        "raw_result": raw_result,
        "predicted_answer": pred_val,
        "predicted_type": pred_type,
        "gold_answer": gold_val,
        "gold_type": gold_type,
        "is_correct": is_match,
        "eval_score": eval_score,
        "eval_status_label": eval_label,
        "confidence_score": confidence,
        "threshold_tau_star": 0.50,
        "grounding_eval": grounding_eval,
        "latencies_ms": latencies,
        "total_latency_ms": total_pipeline_ms,
        "ai_recommendations": ai_recs,
        "deviation_analysis": dev_analysis,
        "self_correction_trace": self_correction_trace,
    }

    # Xuất telemetry JSON
    telemetry_file = Path(args.telemetry_file) if args.telemetry_file else Path("reports/diagnostics") / f"{qid}_telemetry.json"
    telemetry_file.parent.mkdir(parents=True, exist_ok=True)
    with open(telemetry_file, "w", encoding="utf-8") as f:
        json.dump(telemetry_payload, f, ensure_ascii=False, indent=2)
    print(f"\n📁 Đã lưu Telemetry JSON tại: {telemetry_file.resolve()}")

    # Xuất Dashboard PNG trực quan
    chart_file = Path(args.chart_file) if args.chart_file else Path("reports/diagnostics") / f"{qid}_dashboard.png"
    render_diagnostic_dashboard(telemetry_payload, chart_file)
    print(f"🖼️ Đã tạo Dashboard hình ảnh trực quan tại: {chart_file.resolve()}")

    # Xuất Báo cáo Markdown (.md) chi tiết cho câu hỏi
    md_file = Path(args.md_file) if getattr(args, "md_file", None) else Path("reports/diagnostics") / f"{qid}_report.md"
    render_single_markdown_report(telemetry_payload, md_file)
    print(f"📝 Đã xuất Báo cáo Markdown chi tiết tại: {md_file.resolve()}\n")

    return telemetry_payload


def render_single_markdown_report(telemetry: Dict[str, Any], md_path: Path):
    """Xuất báo cáo phân tích chuyên sâu (.md) cho 1 câu hỏi (Single Inspection Mode)."""
    md_path.parent.mkdir(parents=True, exist_ok=True)
    qid = telemetry.get("question_id", "unknown")
    biz_id = telemetry.get("business_id", "unknown")
    as_of = telemetry.get("as_of_date", "")
    orig_q = telemetry.get("original_question", "")
    norm_q = telemetry.get("normalized_question", "")
    intent = telemetry.get("intent", "")
    t_desc = telemetry.get("temporal_desc", "")
    t_range = telemetry.get("temporal_range", [])
    entities = telemetry.get("entity_matches", [])
    pred_val = telemetry.get("predicted_answer")
    pred_type = telemetry.get("predicted_type", "abstain")
    gold_val = telemetry.get("gold_answer")
    gold_type = telemetry.get("gold_type", "unknown")
    eval_label = telemetry.get("eval_status_label", "")
    eval_score = telemetry.get("eval_score", 0.0)
    conf = telemetry.get("confidence_score", 0.0)
    tau = telemetry.get("threshold_tau_star", 0.50)
    code_text = telemetry.get("code_text", "")
    dev = telemetry.get("deviation_analysis") or {}
    recs = telemetry.get("ai_recommendations") or []
    traces = telemetry.get("self_correction_trace") or []

    lines = [
        f"# Báo cáo Kiểm thử Chuyên sâu Câu hỏi `{qid}` (`{biz_id}`)",
        "",
        "## 1. Thông tin Câu hỏi & Ngữ cảnh Neo dữ liệu (Grounding)",
        f"- **Mã câu hỏi (`question_id`)**: `{qid}`",
        f"- **Doanh nghiệp (`business_id`)**: `{biz_id}`",
        f"- **Ngày tham chiếu (`as_of_date`)**: `{as_of}`",
        f"- **Câu hỏi gốc**: {orig_q}",
        f"- **Câu hỏi chuẩn hóa**: {norm_q}",
        f"- **Ý định (`intent`)**: `{intent}`",
        f"- **Mốc thời gian giải mã**: {t_desc} (`{t_range}`)",
        f"- **Thực thể khớp trong CSDL**: {', '.join(f'`{e}`' for e in entities) if entities else '*(Không có)*'}",
        "",
        "## 2. Kết quả Dự đoán & Chấm điểm Penalized Accuracy (PA)",
        f"- **Đáp án Dự đoán (Pred)**: `{pred_val}` (Kiểu: `{pred_type}`)",
        f"- **Đáp án Chuẩn (Gold)**: `{gold_val}` (Kiểu: `{gold_type}`)",
        f"- **Kết luận Đánh giá**: **{eval_label}** (Điểm PA: `{eval_score:+.1f}`)",
        f"- **Điểm Tự tin Hiệu chuẩn ($C$)**: `{conf:.2f}` (Ngưỡng $\\tau^* = {tau:.2f}$)",
    ]
    if dev.get("is_applicable"):
        lines.append(f"- **Sai số số học**: Tuyệt đối = `{dev.get('abs_diff')}` | Phần trăm = `{dev.get('pct_diff')}%`")
        if dev.get("diagnostic_hypothesis"):
            lines.append(f"- **Chẩn đoán nguyên nhân sai lệch**: {dev.get('diagnostic_hypothesis')}")

    lines.extend([
        "",
        "## 3. Phân tích Nguyên nhân & Khuyến nghị Cải tiến",
    ])
    for r in recs:
        lines.append(f"- {r}")

    if traces:
        lines.extend(["", "## 4. Lịch sử Tự sửa lỗi (Self-Correction Trace)"])
        for tr in traces:
            lines.append(f"- {tr}")

    lines.extend([
        "",
        "## 5. Mã nguồn Python Sinh ra (`solution(data)`)",
        "```python",
        code_text.strip() if code_text else "# Không có code",
        "```",
        "",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")


def render_markdown_evaluation_report(
    metrics: Dict[str, Any],
    eval_qids: List[str],
    log_dir: Path,
    gold_map: Dict[str, Any],
    written_records: Dict[str, Any],
    md_path: Path,
    model_id: str = "",
):
    """
    Xuất Báo cáo Đánh giá Toàn diện định dạng Markdown (.md) cho Batch Evaluation:
    - Tổng hợp điểm PA, Accuracy, Coverage, phân rã theo kiểu đáp án.
    - Thống kê nguyên nhân lỗi (Error & Abstention Taxonomy).
    - Báo cáo chi tiết từng câu hỏi: Dự đoán vs Chuẩn, điểm tự tin, nguyên nhân lỗi, chẩn đoán sai lệch và code.
    """
    md_path.parent.mkdir(parents=True, exist_ok=True)
    eval_total = metrics.get("total", len(eval_qids))
    correct = metrics.get("correct", 0)
    wrong = metrics.get("wrong", 0)
    abstain = metrics.get("abstain", 0)
    pa_score = metrics.get("pa", 0.0)
    acc_score = metrics.get("accuracy", 0.0)
    coverage = metrics.get("coverage", 0.0)
    total_time = metrics.get("total_time_sec", 0.0)
    breakdown = metrics.get("breakdown", {})

    lines = [
        "# 📊 Báo cáo Đánh giá Toàn diện Hệ thống DataMate (Batch Evaluation Report)",
        "",
        f"- **Mô hình sử dụng (`model_id`)**: `{model_id}`",
        f"- **Tổng số câu hỏi đánh giá**: `{eval_total}` câu",
        f"- **Tổng thời gian thực thi**: `{total_time:.2f}s` (Trung bình `{total_time/max(1, eval_total):.2f}s/câu`)",
        "",
        "## 1. Tổng hợp Điểm Penalized Accuracy (PA)",
        "",
        "| Chỉ số Đánh giá | Giá trị | Tỷ lệ / Ghi chú |",
        "| :--- | :---: | :--- |",
        f"| **Penalized Accuracy (PA)** | **`{pa_score:+.4f}`** | Công thức: $(Correct - Wrong) / N$ |",
        f"| **Số câu Đúng (+1 điểm)** | `{correct}` | `{100*correct/max(1, eval_total):.1f}%` |",
        f"| **Số câu Sai (-1 điểm)** | `{wrong}` | `{100*wrong/max(1, eval_total):.1f}%` |",
        f"| **Số câu Từ chối / Abstain (0 điểm)** | `{abstain}` | `{100*abstain/max(1, eval_total):.1f}%` |",
        f"| **Accuracy (khi trả lời)** | `{acc_score*100:.1f}%` | $Correct / (Correct + Wrong)$ |",
        f"| **Coverage (Độ bao phủ trả lời)** | `{coverage*100:.1f}%` | $(Correct + Wrong) / N$ |",
        "",
        "## 2. Phân rã Kết quả theo Kiểu Đáp án (Answer Type Breakdown)",
        "",
        "| Kiểu đáp án (`type`) | Tổng số câu | Đúng (+1) | Sai (-1) | Abstain (0) | Điểm PA | Độ trễ TB (ms) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for t in sorted(breakdown.keys()):
        st = breakdown[t]
        lines.append(
            f"| `{t}` | {st['total']} | {st['correct']} | {st['wrong']} | {st['abstain']} | **`{st['pa']:+.3f}`** | {st.get('avg_latency_ms', 0.0):.1f} |"
        )

    # Đọc log chi tiết từng câu để thống kê nguyên nhân lỗi & lập báo cáo từng câu
    per_question_logs: List[Dict[str, Any]] = []
    error_reasons: Dict[str, int] = defaultdict(int)

    for qid in eval_qids:
        log_file = log_dir / f"{qid}.json"
        if log_file.exists():
            try:
                log_data = json.loads(log_file.read_text(encoding="utf-8"))
                per_question_logs.append(log_data)
                extra_d = log_data.get("extra_log") or {}
                err_str = log_data.get("error") or extra_d.get("error")
                ans_obj = log_data.get("answer") or {}
                reason_str = ans_obj.get("reason")
                if err_str:
                    short_err = str(err_str).split("\n")[0][:90]
                    error_reasons[f"Runtime/Sanity Error: {short_err}"] += 1
                elif ans_obj.get("type") == "abstain" and reason_str:
                    error_reasons[f"Abstention Gate: {reason_str}"] += 1
                elif (log_data.get("match_result") or extra_d.get("match_result") or {}).get("eval_score") == -1.0:
                    hyp = ((log_data.get("deviation_analysis") or extra_d.get("deviation_analysis") or {}).get("diagnostic_hypothesis"))
                    error_reasons[f"Sai lệch logic/số học: {hyp or 'Chưa khớp đáp án chuẩn'}"] += 1
            except Exception:
                pass

    if error_reasons:
        lines.extend([
            "",
            "## 3. Thống kê Nguyên nhân Lỗi & Lý do Từ chối (Error & Abstention Taxonomy)",
            "",
            "| Nguyên nhân / Chẩn đoán | Số lượng câu |",
            "| :--- | :---: |",
        ])
        for r_key, r_cnt in sorted(error_reasons.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"| {r_key} | `{r_cnt}` |")

    lines.extend([
        "",
        "---",
        "",
        "## 4. Báo cáo Phân tích Chi tiết Từng Câu hỏi (Per-Question Analysis)",
        "",
    ])

    for idx, qid in enumerate(eval_qids, 1):
        log_file = log_dir / f"{qid}.json"
        log_obj = {}
        if log_file.exists():
            try:
                log_obj = json.loads(log_file.read_text(encoding="utf-8"))
            except Exception:
                log_obj = {}

        extra = log_obj.get("extra_log") or {}
        biz_id = log_obj.get("business_id") or extra.get("business_id") or "unknown"
        as_of = log_obj.get("as_of_date") or extra.get("as_of_date") or ""
        orig_q = log_obj.get("original_question") or extra.get("original_question") or ""
        norm_q = log_obj.get("normalized_question") or extra.get("normalized_question") or orig_q
        intent = log_obj.get("intent") or extra.get("intent") or ""
        temp_info = log_obj.get("temporal_info") or extra.get("temporal_info") or {}
        entities = log_obj.get("entity_matches") or extra.get("entity_matches") or []
        sel_tables = log_obj.get("selected_tables") or extra.get("selected_tables") or []
        sel_cols = log_obj.get("selected_columns") or extra.get("selected_columns") or []
        conf = log_obj.get("confidence", extra.get("confidence", 0.0))
        sc_count = log_obj.get("self_correction_count", extra.get("self_correction_count", 0))
        sc_trace = log_obj.get("self_correction_trace") or extra.get("self_correction_trace") or []
        err_msg = log_obj.get("error") or extra.get("error")
        code_str = log_obj.get("code") or extra.get("code") or ""
        dev = log_obj.get("deviation_analysis") or extra.get("deviation_analysis") or {}
        g_eval = log_obj.get("grounding_eval") or extra.get("grounding_eval") or {}
        lat_bd = log_obj.get("latency_breakdown_ms") or extra.get("latency_breakdown_ms") or {}

        pred_item = written_records.get(qid, log_obj.get("answer") or {"type": "abstain", "answer": None})
        gold_item = gold_map.get(qid, log_obj.get("gold_answer") or extra.get("gold_answer") or {})
        p_type = pred_item.get("type", "abstain")
        p_val = pred_item.get("answer")
        g_type = gold_item.get("type", "unknown")
        g_val = gold_item.get("answer")

        match_res = log_obj.get("match_result") or extra.get("match_result") or {}
        status_label = match_res.get("eval_status_label", "")
        score_val = match_res.get("eval_score")
        if score_val is None and gold_item:
            if p_type == "abstain":
                score_val = 0.0
                status_label = "TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0)"
            elif compare_single_answer(pred_item, gold_item):
                score_val = 1.0
                status_label = "HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0)"
            else:
                score_val = -1.0
                status_label = "SAI LỆCH ĐÁP ÁN (WRONG - -1.0)"

        icon = "✅" if score_val == 1.0 else ("🛡️" if score_val == 0.0 else "❌")
        score_str = f"{score_val:+.1f}" if isinstance(score_val, (int, float)) else "N/A"

        lines.extend([
            f"### {icon} Câu {idx}: `{qid}` (`{biz_id}`) — Điểm PA: `{score_str}` ({status_label})",
            f"- **Câu hỏi gốc**: {orig_q}",
        ])
        if norm_q and norm_q != orig_q:
            lines.append(f"- **Câu hỏi mở rộng viết tắt**: {norm_q}")
        comp_str = ""
        if temp_info.get("comparison_start") or temp_info.get("comparison_end"):
            comp_str = f" | Kỳ so sánh: `{temp_info.get('comparison_start')} -> {temp_info.get('comparison_end')}` ({temp_info.get('comparison_desc', '')})"
        lines.extend([
            f"- **Ngữ cảnh**: `as_of_date = {as_of}` | `intent = {intent}` | Khoảng ngày: `{temp_info.get('start_date')} -> {temp_info.get('end_date')}` ({temp_info.get('description', '')}){comp_str}",
            f"- **Thực thể khớp (Entity Linking)**: {', '.join(f'`{e}`' for e in entities) if entities else '*(Không có)*'}",
            f"- **Bảng & Cột truy vấn**: Bảng={sel_tables if sel_tables else '[]'} | Cột={sel_cols[:8] if sel_cols else '[]'}",
            f"- **Dự đoán (Pred)**: `{p_val}` (Kiểu: `{p_type}`) | **Đáp án Chuẩn (Gold)**: `{g_val}` (Kiểu: `{g_type}`)",
            f"- **Độ tin cậy ($C$)**: `{conf:.2f}` | **Số vòng tự sửa lỗi (Self-Correction)**: `{sc_count}`",
        ])
        if lat_bd:
            lines.append(
                f"- **Thời gian từng pha (ms)**: Nạp dữ liệu=`{lat_bd.get('ingest_schema', 0.0):.1f}ms` | "
                f"Grounding=`{lat_bd.get('grounding', 0.0):.1f}ms` | "
                f"LLM=`{lat_bd.get('llm_gen', 0.0):.1f}ms` | "
                f"Thực thi=`{lat_bd.get('sandbox_exec', 0.0):.1f}ms` | "
                f"Normalizer=`{lat_bd.get('normalizer', 0.0):.1f}ms` | "
                f"Retry=`{sc_count}`"
            )

        if g_eval:
            lines.append(
                f"- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`{g_eval.get('entity_coverage', 1.0)*100:.0f}%` (Phạt `-{g_eval.get('entity_penalty', 0.0):.2f}`), "
                f"Temporal Coverage=`{g_eval.get('temporal_coverage', 1.0)*100:.0f}%` (Phạt `-{g_eval.get('temporal_penalty', 0.0):.2f}`)"
            )

        if err_msg:
            lines.append(f"- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `{err_msg}`")
        if pred_item.get("reason"):
            lines.append(f"- **🛡️ Lý do Cổng Abstention**: `{pred_item.get('reason')}`")
        if dev.get("is_applicable") and score_val == -1.0:
            lines.append(
                f"- **🔍 Phân tích Độ lệch Số học**: Lệch tuyệt đối = `{dev.get('abs_diff')}` ({dev.get('pct_diff')}%) — "
                f"**Chẩn đoán**: *{dev.get('diagnostic_hypothesis') or 'Sai lệch logic lọc hoặc cột tính toán'}*"
            )

        if sc_trace:
            lines.append("- **🔄 Nhật ký Tự sửa lỗi (Self-Correction)**:")
            for tr in sc_trace:
                if isinstance(tr, dict):
                    lines.append(
                        f"  - Vòng {tr.get('round')}: Lỗi đầu vào `{tr.get('input_error')}` -> "
                        f"Kết quả thử lại: `{'Thành công' if tr.get('success') else (tr.get('retry_error') or tr.get('sanity_error'))}`"
                    )
                else:
                    lines.append(f"  - {tr}")

        lines.extend([
            "",
            "<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>",
            "",
            "```python",
            code_str.strip() if code_str else "# Không có mã nguồn",
            "```",
            "</details>",
            "",
        ])

    md_path.write_text("\n".join(lines), encoding="utf-8")


# ==============================================================================
# HÀM CHẠY ĐÁNH GIÁ HÀNG LOẠT (BATCH EVALUATION MODE - THAY THẾ RUN_EVAL.PY)
# ==============================================================================

def run_batch_evaluation(args: argparse.Namespace):
    """Chạy toàn bộ pipeline suy luận và đánh giá hàng loạt thay thế hoàn toàn run_eval.py."""
    cfg = load_config(args.config) if args.config else load_config()

    data_dir = Path(args.data_dir)
    if getattr(args, "batch_file", None):
        questions_path = Path(args.batch_file)
        args.no_fill_abstain = True
    elif args.questions_file:
        questions_path = Path(args.questions_file)
    else:
        questions_path = data_dir / "questions.jsonl"
    data_root = data_dir / "data"

    if not questions_path.exists():
        print(f"❌ Không tìm thấy questions.jsonl tại: {questions_path.resolve()}")
        sys.exit(1)

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

    replay_logs_dir: Optional[Path] = Path(args.replay_logs) if getattr(args, "replay_logs", None) else None
    replay_map: Dict[str, dict] = {}
    if replay_logs_dir and replay_logs_dir.exists():
        args.no_fill_abstain = True
        for lf in sorted(replay_logs_dir.glob("*.json")):
            try:
                lobj = json.loads(lf.read_text(encoding="utf-8"))
                qid_k = lobj.get("question_id") or lf.stem
                replay_map[qid_k] = lobj
            except Exception:
                pass

    target_questions = all_questions
    if replay_map and not args.sample and getattr(args, "batch_index", None) is None and not getattr(args, "batch_file", None):
        target_questions = [q for q in target_questions if q.get("id") in replay_map]

    if getattr(args, "range", None):
        # Hỗ trợ định dạng START-END (ví dụ: 1-50, 101-200, 1:50)
        m_range = re.match(r"^(\d+)[\-:,_](\d+)$", str(args.range).strip())
        if m_range:
            s_num = max(1, int(m_range.group(1)))
            e_num = min(len(all_questions), int(m_range.group(2)))
            if s_num <= e_num:
                target_questions = all_questions[s_num - 1 : e_num]
                args.no_fill_abstain = True
                print(f"• Chọn khoảng câu hỏi   : từ câu {s_num} đến câu {e_num} ({len(target_questions)} câu)")

    if getattr(args, "batch_index", None) is not None and 1 <= args.batch_index <= 6:
        bs = getattr(args, "batch_size", None) or 20
        start_idx = (args.batch_index - 1) * bs
        end_idx = start_idx + bs
        target_questions = all_questions[start_idx:end_idx]
        args.no_fill_abstain = True

    if args.biz:
        target_questions = [q for q in target_questions if q.get("business_id") == args.biz]
    if args.id:
        target_questions = [q for q in target_questions if q.get("id") == args.id]
    if args.sample is not None and args.sample < len(target_questions):
        rng = random.Random(args.seed)
        if getattr(args, "stratified", False):
            # Lấy mẫu phân tầng (Stratified Sampling) theo loại câu hỏi (gold type hoặc infer_expected_type)
            from datamate.output_abstention.normalizer import infer_expected_type
            by_type: Dict[str, List[dict]] = {}
            for q_item in target_questions:
                qid_item = q_item.get("id", "")
                g_type = (gold_map.get(qid_item) or {}).get("type") if gold_map else None
                if not g_type:
                    g_type = infer_expected_type(q_item.get("question", ""))
                by_type.setdefault(str(g_type), []).append(q_item)
            sampled_list: List[dict] = []
            total_pool = len(target_questions)
            # Đảm bảo mỗi nhóm hiếm có ít nhất 1 câu nếu args.sample >= số nhóm
            sorted_types = sorted(by_type.keys(), key=lambda t: len(by_type[t]))
            remaining_quota = args.sample
            allocations: Dict[str, int] = {}
            for idx_t, t_name in enumerate(sorted_types):
                group_pool = by_type[t_name]
                if remaining_quota <= 0:
                    allocations[t_name] = 0
                    continue
                prop = max(1, int(round(args.sample * (len(group_pool) / total_pool)))) if args.sample >= len(sorted_types) else int(round(args.sample * (len(group_pool) / total_pool)))
                take_n = min(len(group_pool), prop, remaining_quota)
                allocations[t_name] = take_n
                remaining_quota -= take_n
            # Phân bổ phần dư (nếu có) vào các nhóm còn phần tử chưa lấy hết
            for t_name in reversed(sorted_types):
                if remaining_quota <= 0:
                    break
                avail = len(by_type[t_name]) - allocations.get(t_name, 0)
                if avail > 0:
                    add_n = min(avail, remaining_quota)
                    allocations[t_name] = allocations.get(t_name, 0) + add_n
                    remaining_quota -= add_n
            for t_name in sorted_types:
                k_take = allocations.get(t_name, 0)
                if k_take > 0:
                    sampled_list.extend(rng.sample(by_type[t_name], k_take))
            target_questions = sampled_list
        else:
            target_questions = rng.sample(target_questions, args.sample)

    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_mode = "w"
    existing_completed_ids = set()
    preloaded_records: Dict[str, dict] = {}

    planned_questions = target_questions[: args.limit] if args.limit is not None else list(target_questions)
    planned_eval_qids = [q["id"] for q in sorted(planned_questions, key=lambda q: (q.get("business_id", ""), q.get("id", "")))]

    if args.resume and output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f_ex:
                for line in f_ex:
                    if line.strip():
                        obj = json.loads(line)
                        if obj.get("id"):
                            existing_completed_ids.add(obj["id"])
                            preloaded_records[obj["id"]] = obj
            if existing_completed_ids:
                write_mode = "a"
                target_questions = [q for q in planned_questions if q["id"] not in existing_completed_ids]
        except Exception:
            pass

    active_limit = args.limit if (args.limit is not None and not existing_completed_ids) else len(target_questions)
    active_questions = target_questions[:active_limit]
    if not getattr(args, "preserve_order", False):
        active_questions = sorted(active_questions, key=lambda q: (q.get("business_id", ""), q.get("id", "")))
    active_qids = {q["id"] for q in active_questions} | existing_completed_ids

    chart_path = Path(args.chart_file) if args.chart_file else Path("results/evaluation_dashboard.png")
    report_path = Path(args.report_file) if args.report_file else Path("results/evaluation_report.json")

    print("=" * 80)
    print("DATAMATE — PIPELINE SUY LUẬN, SO KHỚP ĐÁP ÁN & TRỰC QUAN HÓA TOÀN TRÌNH")
    print("=" * 80)
    print(f"• Dữ liệu đầu vào       : {questions_path.resolve()} ({len(all_questions)} câu)")
    print(f"• Số câu thực hiện chạy : {len(active_questions)} câu (Limit: {args.limit})")
    print(f"• File đáp án chuẩn     : {gold_path.resolve() if has_gold else 'Không có (Chế độ Test ẩn)'}")
    print(f"• File kết quả JSONL    : {output_path.resolve()}")
    print(f"• Ảnh Dashboard thống kê: {chart_path.resolve()}")
    print("=" * 80)

    llm: Optional[LLMClient] = None
    if (args.with_llm or not args.dry_run) and not replay_logs_dir:
        print(f"[Khởi tạo] Đang nạp mô hình {args.model_id} (4-bit NF4)...")
        llm = LLMClient(model_id=args.model_id)
    elif replay_logs_dir:
        print(f"[Replay Mode] Nạp {len(replay_map)} file log từ {replay_logs_dir.resolve()} (bỏ qua LLM)...")

    writer = SubmissionWriter(output_file=str(output_path), log_dir=args.log_dir, mode=write_mode).open()
    written_records: Dict[str, dict] = dict(preloaded_records)
    latencies: Dict[str, int] = {}
    t_start_all = time.time()

    try:
        current_biz_id: Optional[str] = None
        shop_memory = ShopExecutionMemory()
        for idx, q in enumerate(active_questions, start=1):
            qid = q["id"]
            biz_id = q["business_id"]
            question_text = q["question"]
            as_of_date = q["as_of_date"]

            # Giải phóng RAM của shop cũ khi chuyển sang shop tiếp theo (do câu hỏi đã được group_by_business)
            if current_biz_id is not None and biz_id != current_biz_id:
                old_entry = _BUSINESS_CACHE.pop(current_biz_id, None)
                if old_entry and old_entry[1] is not None:
                    try:
                        old_entry[1].close()
                    except Exception:
                        pass
            current_biz_id = biz_id

            print(f"\n[{idx}/{len(active_questions)}] Câu hỏi ID: {qid} (Shop: {biz_id})")
            print(f"Nội dung: \"{question_text}\" | as_of_date: {as_of_date}")

            # Bộ theo dõi độ trễ từng module (Telemetry Latency Breakdown)
            mod_latencies: Dict[str, float] = {}

            # Bước 1: Nạp & Cache Dữ liệu Shop
            t_ingest = time.perf_counter()
            data_dict, con, schema_str, bd, shop_meta, candidates, is_cache = get_cached_business_data(biz_id, data_root)
            mod_latencies["ingest_schema"] = round((time.perf_counter() - t_ingest) * 1000, 2)

            if not data_dict:
                sub_ans = make_abstain(f"Data Not Found: {schema_str}")
                gold_record = gold_map.get(qid) if has_gold else None
                is_match = False
                dev_analysis = {"is_applicable": False, "abs_diff": None, "pct_diff": None, "diagnostic_hypothesis": None}
                early_telemetry = {
                    "question_id": qid,
                    "business_id": biz_id,
                    "as_of_date": as_of_date,
                    "original_question": question_text,
                    "normalized_question": question_text,
                    "expanded_abbreviations": {},
                    "intent": "unknown",
                    "temporal_info": {},
                    "entity_matches": [],
                    "pruned_schema": "",
                    "code": "",
                    "raw_result": None,
                    "answer": {"id": qid, **sub_ans},
                    "gold_answer": {"answer": gold_record.get("answer"), "type": gold_record.get("type"), "alias": gold_record.get("alias", [])} if gold_record else None,
                    "match_result": {"is_match": is_match, "eval_score": 0.0, "eval_status_label": "TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0)"},
                    "deviation_analysis": dev_analysis,
                    "confidence": 0.0,
                    "threshold_tau_star": args.tau_star,
                    "unanswerable_source": "none",
                    "selected_tables": [],
                    "selected_columns": [],
                    "grounding_eval": {},
                    "elapsed_ms": int(mod_latencies["ingest_schema"]),
                    "latency_breakdown_ms": mod_latencies,
                    "self_correction_count": 0,
                    "self_correction_trace": [],
                    "error": str(schema_str),
                }
                writer.write(
                    question_id=qid,
                    answer=sub_ans,
                    code="",
                    raw_result=None,
                    error=schema_str,
                    elapsed_ms=int(mod_latencies["ingest_schema"]),
                    confidence=0.0,
                    extra_log=early_telemetry,
                    write_log=True,
                )
                written_records[qid] = {"id": qid, **sub_ans}
                latencies[qid] = int(mod_latencies["ingest_schema"])
                continue

            # Bước 2: Lá chắn Feasibility Gate
            t_feas = time.perf_counter()
            is_feasible, unans_reason = check_feasibility(question_text, as_of_date, shop_meta)
            mod_latencies["feasibility"] = round((time.perf_counter() - t_feas) * 1000, 2)

            if not is_feasible:
                print(f"  🛡️ [Feasibility Gate] Bất khả thi ({unans_reason}) -> Trả về 'unanswerable'")
                sub_ans = {"type": "unanswerable", "answer": None}
                gold_record = gold_map.get(qid) if has_gold else None
                is_match = compare_single_answer(sub_ans, gold_record) if gold_record else None
                eval_score = 1.0 if is_match else (-1.0 if gold_record else None)
                eval_label = "HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0)" if is_match else ("SAI LỆCH ĐÁP ÁN (WRONG - -1.0)" if gold_record else "CHƯA CÓ ĐÁP ÁN CHUẨN")
                dev_analysis = analyze_numerical_deviation(None, gold_record.get("answer") if gold_record else None, "unanswerable", gold_record.get("type", "unknown") if gold_record else "unknown")
                total_lat = int(mod_latencies["ingest_schema"] + mod_latencies["feasibility"])

                gate_telemetry = {
                    "question_id": qid,
                    "business_id": biz_id,
                    "as_of_date": as_of_date,
                    "original_question": question_text,
                    "normalized_question": question_text,
                    "expanded_abbreviations": {},
                    "intent": "unanswerable_gate",
                    "temporal_info": {},
                    "entity_matches": [],
                    "pruned_schema": "",
                    "code": "# Feasibility Gate: Unanswerable detected deterministically",
                    "raw_result": "unanswerable",
                    "answer": {"id": qid, **sub_ans},
                    "gold_answer": {"answer": gold_record.get("answer"), "type": gold_record.get("type"), "alias": gold_record.get("alias", [])} if gold_record else None,
                    "match_result": {"is_match": is_match, "eval_score": eval_score, "eval_status_label": eval_label},
                    "deviation_analysis": dev_analysis,
                    "confidence": 1.0,
                    "threshold_tau_star": args.tau_star,
                    "unanswerable_source": "gate",
                    "unanswerable_reason": unans_reason,
                    "selected_tables": [],
                    "selected_columns": [],
                    "grounding_eval": {},
                    "elapsed_ms": total_lat,
                    "latency_breakdown_ms": mod_latencies,
                    "self_correction_count": 0,
                    "self_correction_trace": [],
                    "error": None,
                }
                writer.write(
                    question_id=qid,
                    answer=sub_ans,
                    code="# Feasibility Gate: Unanswerable detected deterministically",
                    raw_result="unanswerable",
                    error=None,
                    elapsed_ms=total_lat,
                    confidence=1.0,
                    unanswerable_source="gate",
                    extra_log=gate_telemetry,
                    write_log=True,
                )
                written_records[qid] = {"id": qid, **sub_ans}
                latencies[qid] = total_lat
                continue

            # Bước 3: Tiền xử lý & Entity Linking
            t_ground = time.perf_counter()
            normalized_q, replaced_abbr = explain_and_expand_abbreviations(question_text)
            intent = classify_intent(normalized_q)
            cal_str = str(data_dir / "calendar.csv") if (data_dir / "calendar.csv").exists() else None
            temp_info = resolve_temporal_context(normalized_q, as_of_date, calendar_path=cal_str)
            entity_matches = link_entities(normalized_q, candidates=candidates, threshold=0.55) if candidates else []

            pruned_schema = prune_schema_by_intent(
                schema_str=schema_str,
                intent=intent,
                question=normalized_q,
                entity_matches=entity_matches,
            )
            mod_latencies["grounding"] = round((time.perf_counter() - t_ground) * 1000, 2)

            # Bước 4: Lắp ráp Prompt
            t_prompt = time.perf_counter()
            sys_prompt, user_prompt = build_prompt(
                schema_str=pruned_schema,
                as_of_date=as_of_date,
                question=normalized_q,
                rulebook_content=rulebook_content,
                business_note=getattr(bd, "readme_text", None) if bd else None,
                candidates=candidates,
                entity_matches=entity_matches,
                return_messages=True,
                calendar_path=cal_str,
                shop_memory_hints=shop_memory.get_hints(biz_id),
            )
            mod_latencies["prompt_build"] = round((time.perf_counter() - t_prompt) * 1000, 2)

            # Chế độ Dry-Run hoặc không có LLM (và không phải replay_logs)
            if (args.dry_run or (not args.with_llm and llm is None)) and not replay_logs_dir:
                sub_ans = make_abstain("Dry Run Mode")
                mod_latencies["llm_gen"] = 0.0
                mod_latencies["sandbox_exec"] = 0.0
                mod_latencies["normalizer"] = 0.0
                total_lat = int(sum(mod_latencies.values()))

                gold_record = gold_map.get(qid) if has_gold else None
                is_match = False
                eval_score = 0.0
                eval_label = "TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0)"
                dev_analysis = {"is_applicable": False, "abs_diff": None, "pct_diff": None, "diagnostic_hypothesis": None}

                dry_telemetry = {
                    "question_id": qid,
                    "business_id": biz_id,
                    "as_of_date": as_of_date,
                    "original_question": question_text,
                    "normalized_question": normalized_q,
                    "expanded_abbreviations": replaced_abbr,
                    "intent": intent,
                    "temporal_info": {
                        "description": temp_info.get("description", ""),
                        "start_date": temp_info.get("start_date"),
                        "end_date": temp_info.get("end_date"),
                    },
                    "entity_matches": [getattr(m, "matched_value", str(m)) for m in entity_matches],
                    "pruned_schema": pruned_schema,
                    "code": "def solution(data):\n    # Dry run mock code\n    return 'abstain'",
                    "raw_result": "abstain",
                    "answer": {"id": qid, **sub_ans},
                    "gold_answer": {
                        "answer": gold_record.get("answer") if gold_record else None,
                        "type": gold_record.get("type") if gold_record else None,
                        "alias": gold_record.get("alias", []) if gold_record else [],
                    } if gold_record else None,
                    "match_result": {
                        "is_match": is_match,
                        "eval_score": eval_score,
                        "eval_status_label": eval_label,
                    },
                    "deviation_analysis": dev_analysis,
                    "confidence": 0.0,
                    "threshold_tau_star": args.tau_star,
                    "unanswerable_source": "none",
                    "selected_tables": [],
                    "selected_columns": [],
                    "grounding_eval": {},
                    "elapsed_ms": total_lat,
                    "latency_breakdown_ms": mod_latencies,
                    "self_correction_count": 0,
                    "self_correction_trace": [],
                    "error": None,
                }
                writer.write(
                    question_id=qid,
                    answer=sub_ans,
                    code="def solution(data):\n    # Dry run mock code\n    return 'abstain'",
                    raw_result=None,
                    error=None,
                    elapsed_ms=total_lat,
                    confidence=0.0,
                    extra_log=dry_telemetry,
                    write_log=True,
                )
                written_records[qid] = {"id": qid, **sub_ans}
                latencies[qid] = total_lat
                continue

            # Bước 5: LLM Sinh mã hoặc Replay từ Log
            prev_log = replay_map.get(qid) if replay_logs_dir else None
            if replay_logs_dir:
                if not prev_log:
                    sub_ans = make_abstain("Replay Log Not Found")
                    written_records[qid] = {"id": qid, **sub_ans}
                    latencies[qid] = 0
                    continue
                extra_prev = prev_log.get("extra_log") or {}
                code_text = prev_log.get("code") or extra_prev.get("code") or ""
                mod_latencies["llm_gen"] = 0.0
                self_correction_count = prev_log.get("self_correction_count", extra_prev.get("self_correction_count", 0))
                self_correction_trace = prev_log.get("self_correction_trace") or extra_prev.get("self_correction_trace") or []
            else:
                t_llm = time.perf_counter()
                assert llm is not None
                code_text = llm.generate_code(prompt=user_prompt, system_prompt=sys_prompt, max_new_tokens=getattr(args, "max_new_tokens", 1536))
                mod_latencies["llm_gen"] = round((time.perf_counter() - t_llm) * 1000, 2)
                self_correction_count = 0
                self_correction_trace = []

            # Bước 6: Thực thi Sandbox & Self-Correction tối đa 2 vòng
            t_exec = time.perf_counter()
            biz_dir = data_root / biz_id
            raw_result, exec_err, exec_ms, err_type, unans_source = execute_solution(
                code_text=code_text,
                biz_dir=biz_dir,
                data_dict=data_dict,
                con=con,
                business_obj=bd,
                timeout_s=args.timeout,
                use_sandbox=not args.in_process,
                return_details=True,
                as_of_date=as_of_date,
            )

            max_self_corrections = 0 if replay_logs_dir else 2
            sanity_err = None

            if not exec_err:
                sub_ans_cand = normalize_output(raw_result, question=normalized_q, code_text=code_text)
                is_sane, sanity_reason = check_result_sanity(sub_ans_cand, question=normalized_q, code_text=code_text)
                if raw_result == "unanswerable" or sub_ans_cand.get("type") == "unanswerable":
                    sanity_err = "Dữ liệu shop CÓ ĐỦ số liệu (KHÔNG ĐƯỢC trả về unanswerable). Hãy tính toán cụ thể."
                elif not is_sane:
                    sanity_err = sanity_reason
                else:
                    sem_eval1 = evaluate_semantic_rule_compliance(
                        code_text=code_text,
                        question=normalized_q,
                        sub_ans=sub_ans_cand,
                        as_of_date=as_of_date,
                    )
                    if not sem_eval1.get("is_compliant", True):
                        sanity_err = "; ".join(sem_eval1.get("violations", []))

            try:
                from datamate.llm_execution.sandbox import should_retry_self_correction
            except ImportError:
                from src.datamate.llm_execution.sandbox import should_retry_self_correction
            while should_retry_self_correction(exec_err, sanity_err, err_type) and self_correction_count < max_self_corrections:
                self_correction_count += 1
                current_err = exec_err or sanity_err
                print(f"  🔄 [Self-Correction Vòng {self_correction_count}/{max_self_corrections}] Đang sửa: {current_err}")
                err_feedback = f"Lỗi: {current_err}"
                retry_sys, retry_user = build_retry_prompt(
                    question=normalized_q,
                    failed_code=code_text,
                    error_message=err_feedback,
                    schema_str=pruned_schema,
                    as_of_date=as_of_date,
                    retry_round=self_correction_count,
                    temporal_text=format_temporal_for_prompt(temp_info),
                )
                t_retry_gen = time.perf_counter()
                retry_code = llm.generate_code(prompt=retry_user, system_prompt=retry_sys, max_new_tokens=getattr(args, "max_new_tokens", 1536))
                mod_latencies["llm_gen"] = round(mod_latencies["llm_gen"] + (time.perf_counter() - t_retry_gen) * 1000, 2)

                raw_retry, err_retry, ms_retry, type_retry, src_retry = execute_solution(
                    code_text=retry_code,
                    biz_dir=biz_dir,
                    data_dict=data_dict,
                    con=con,
                    business_obj=bd,
                    timeout_s=args.timeout,
                    use_sandbox=not args.in_process,
                    return_details=True,
                    as_of_date=as_of_date,
                )
                exec_ms += ms_retry

                round_record = {
                    "round": self_correction_count,
                    "input_error": str(current_err),
                    "retry_code": retry_code,
                    "retry_error": str(err_retry) if err_retry else None,
                    "retry_raw_result": _clean_for_json(raw_retry),
                    "execution_ms": round(ms_retry, 2),
                    "success": False,
                }

                if not err_retry:
                    sub_ans_cand2 = normalize_output(raw_retry, question=normalized_q, code_text=retry_code)
                    is_sane2, sanity_reason2 = check_result_sanity(sub_ans_cand2, question=normalized_q, code_text=retry_code)
                    if not is_sane2 or raw_retry == "unanswerable" or sub_ans_cand2.get("type") == "unanswerable":
                        sanity_err = sanity_reason2 or "Vẫn trả về unanswerable"
                        code_text = retry_code
                        round_record["sanity_error"] = str(sanity_err)
                    else:
                        sem_eval2 = evaluate_semantic_rule_compliance(
                            code_text=retry_code,
                            question=normalized_q,
                            sub_ans=sub_ans_cand2,
                            as_of_date=as_of_date,
                        )
                        if not sem_eval2.get("is_compliant", True):
                            sanity_err = "; ".join(sem_eval2.get("violations", []))
                            code_text = retry_code
                            round_record["sanity_error"] = str(sanity_err)
                        else:
                            code_text = retry_code
                            raw_result = raw_retry
                            exec_err = None
                            sanity_err = None
                            round_record["success"] = True
                            self_correction_trace.append(round_record)
                            print(f"  ✅ [Self-Correction] Vòng {self_correction_count} thành công!")
                            break
                else:
                    code_text = retry_code
                    exec_err = err_retry

                self_correction_trace.append(round_record)

            mod_latencies["sandbox_exec"] = round((time.perf_counter() - t_exec) * 1000, 2)
            shop_memory.record_attempt(biz_id, code_text, exec_err or sanity_err)

            # Cơ chế Cứu hộ Chủ động (Active Deterministic Fallback) nếu LLM + Self-Correction thất bại
            if exec_err or sanity_err:
                fb_val, fb_src = try_deterministic_fallback(
                    intent=intent,
                    question=normalized_q,
                    data_dict=data_dict,
                    temporal_info=temp_info,
                    entity_matches=entity_matches,
                    as_of_date=as_of_date,
                )
                if fb_val is not None:
                    fb_ans = normalize_output(fb_val, question=normalized_q, code_text=f"# {fb_src}")
                    fb_sane, _ = check_result_sanity(fb_ans, question=normalized_q, code_text=f"# {fb_src}")
                    if fb_sane:
                        print(f"  🚑 [Active Fallback] Cứu hộ thành công bằng {fb_src} -> Kết quả: {fb_val}")
                        raw_result = fb_val
                        exec_err = None
                        sanity_err = None
                        code_text = f"# {fb_src}\n# Recovered after LLM error"

            # Bước 7: Chuẩn hóa & Cổng Abstention
            t_norm = time.perf_counter()
            confidence = 0.0
            grounding_eval_res = {}
            if exec_err:
                sub_ans = make_abstain(f"Runtime Error: {exec_err}")
            elif sanity_err:
                sub_ans = make_abstain(f"Sanity Error: {sanity_err}")
            else:
                sub_ans = normalize_output(raw_result, question=normalized_q, code_text=code_text)
                grounding_eval_res = evaluate_grounding_coverage(
                    code_text=code_text,
                    question=normalized_q,
                    entity_matches=entity_matches,
                    temporal_info=temp_info,
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
                    temporal_info={**(temp_info or {}), "as_of_date": as_of_date},
                    question=normalized_q,
                )
                sub_ans, is_abs = apply_abstention_gate(
                    sub_ans,
                    confidence=confidence,
                    threshold=args.tau_star,
                    unanswerable_source=unans_source,
                )

            mod_latencies["normalizer"] = round((time.perf_counter() - t_norm) * 1000, 2)
            total_lat = int(sum(mod_latencies.values()))

            # Bước 8: Đối chiếu Đáp án Chuẩn (Gold Comparison) & Phân tích Sai lệch
            gold_record = gold_map.get(qid) if has_gold else None
            is_match = None
            eval_score = None
            eval_label = "CHƯA CÓ ĐÁP ÁN CHUẨN"
            dev_analysis = {"is_applicable": False, "abs_diff": None, "pct_diff": None, "diagnostic_hypothesis": None}

            if gold_record:
                is_match = compare_single_answer(sub_ans, gold_record)
                if sub_ans.get("type") == "abstain":
                    eval_score = 0.0
                    eval_label = "TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0)"
                elif is_match:
                    eval_score = 1.0
                    eval_label = "HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0)"
                else:
                    eval_score = -1.0
                    eval_label = "SAI LỆCH ĐÁP ÁN (WRONG - -1.0)"

                dev_analysis = analyze_numerical_deviation(
                    pred_ans=sub_ans.get("answer"),
                    gold_ans=gold_record.get("answer"),
                    pred_type=sub_ans.get("type", "unknown"),
                    gold_type=gold_record.get("type", "unknown"),
                )

            sel_tables, sel_cols, _ = extract_referenced_tables_and_columns(code_text, list(data_dict.keys()))

            # Lắp ráp Payload Telemetry Đầy đủ theo Yêu cầu R2
            enriched_telemetry = {
                "question_id": qid,
                "business_id": biz_id,
                "as_of_date": as_of_date,
                "original_question": question_text,
                "normalized_question": normalized_q,
                "expanded_abbreviations": replaced_abbr,
                "intent": intent,
                "temporal_info": {
                    "description": temp_info.get("description", ""),
                    "start_date": temp_info.get("start_date"),
                    "end_date": temp_info.get("end_date"),
                    "comparison_start": temp_info.get("comparison_start"),
                    "comparison_end": temp_info.get("comparison_end"),
                    "comparison_desc": temp_info.get("comparison_desc", ""),
                },
                "entity_matches": [getattr(m, "matched_value", str(m)) for m in entity_matches],
                "pruned_schema": pruned_schema,
                "code": code_text,
                "raw_result": _clean_for_json(raw_result),
                "answer": {"id": qid, **sub_ans},
                "gold_answer": {
                    "answer": gold_record.get("answer") if gold_record else None,
                    "type": gold_record.get("type") if gold_record else None,
                    "alias": gold_record.get("alias", []) if gold_record else [],
                } if gold_record else None,
                "match_result": {
                    "is_match": is_match,
                    "eval_score": eval_score,
                    "eval_status_label": eval_label,
                },
                "deviation_analysis": dev_analysis,
                "confidence": confidence,
                "threshold_tau_star": args.tau_star,
                "unanswerable_source": unans_source,
                "selected_tables": sel_tables,
                "selected_columns": sel_cols,
                "grounding_eval": grounding_eval_res,
                "elapsed_ms": total_lat,
                "latency_breakdown_ms": mod_latencies,
                "self_correction_count": self_correction_count,
                "self_correction_trace": self_correction_trace,
                "error": str(exec_err or sanity_err) if (exec_err or sanity_err) else None,
            }

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
                extra_log=enriched_telemetry,
                write_log=True,
            )
            written_records[qid] = {"id": qid, **sub_ans}
            latencies[qid] = total_lat
            print(f"  👉 Đáp án: {sub_ans.get('answer')} (Type: {sub_ans.get('type')}, C={confidence:.2f})")
            if gold_record:
                print(f"  👉 Đánh giá: {eval_label} (Gold: {gold_record.get('answer')})")

        # Điền abstain cho các câu còn lại nếu không dùng --no_fill_abstain
        if not args.no_fill_abstain:
            for q in all_questions:
                if q["id"] not in active_qids:
                    abstain_ans = make_abstain("Default Abstain")
                    writer.write(
                        question_id=q["id"],
                        answer=abstain_ans,
                        code="",
                        raw_result=None,
                        error=None,
                        elapsed_ms=0,
                        confidence=0.0,
                        write_log=False,
                    )
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
    print(f"HOÀN THÀNH QUÁ TRÌNH SUY LUẬN BATCH! (Thời gian: {total_time}s)")
    print("=" * 80)

    # Chấm điểm Penalized Accuracy nếu có file đáp án chuẩn
    if has_gold:
        print("\n[ĐÁNH GIÁ & SO KHỚP ĐÁP ÁN] Đang chấm điểm theo Rulebook...")
        eval_qids = planned_eval_qids if planned_eval_qids else [q["id"] for q in active_questions]
        correct = 0
        wrong = 0
        abstain = 0
        status_changes: List[Dict[str, Any]] = []
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
                new_state = "ABSTAIN"
            else:
                is_correct = compare_single_answer(pred_item, gold_item)
                if is_correct:
                    correct += 1
                    breakdown[g_type]["correct"] += 1
                    new_state = "CORRECT"
                else:
                    wrong += 1
                    breakdown[g_type]["wrong"] += 1
                    new_state = "WRONG"

            if replay_logs_dir and qid in replay_map:
                old_log = replay_map[qid]
                old_ans = old_log.get("answer") or (old_log.get("extra_log") or {}).get("answer") or {"type": "abstain", "answer": None}
                if old_ans.get("type") == "abstain":
                    old_state = "ABSTAIN"
                elif compare_single_answer(old_ans, gold_item):
                    old_state = "CORRECT"
                else:
                    old_state = "WRONG"
                if old_state != new_state:
                    status_changes.append({
                        "question_id": qid,
                        "old_state": old_state,
                        "new_state": new_state,
                        "old_answer": old_ans.get("answer"),
                        "new_answer": pred_item.get("answer"),
                        "reason": pred_item.get("reason") or "",
                    })

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
            "status_changes_count": len(status_changes),
            "status_changes": status_changes,
            "breakdown": dict(breakdown),
        }

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
        if replay_logs_dir:
            print(f"Số câu đổi trạng thái : {len(status_changes)} câu")
            for sc in status_changes:
                print(f"  • {sc['question_id']}: {sc['old_state']} ({sc['old_answer']}) -> {sc['new_state']} ({sc['new_answer']}) [{sc['reason']}]")
        print("-" * 76)
        print(f"{'Kiểu đáp án':<16} | {'Tổng':>6} | {'Đúng':>6} | {'Sai':>6} | {'Abstain':>7} | {'Điểm PA':>8}")
        print("-" * 76)
        for t in sorted(breakdown.keys()):
            st = breakdown[t]
            print(f"{t:<16} | {st['total']:>6} | {st['correct']:>6} | {st['wrong']:>6} | {st['abstain']:>7} | {st['pa']:>+8.3f}")
        print("=" * 76)

        # Lưu báo cáo JSON
        rep_file = Path(args.report_file) if args.report_file else Path("results/evaluation_report.json")
        rep_file.parent.mkdir(parents=True, exist_ok=True)
        with open(rep_file, "w", encoding="utf-8") as f_rep:
            json.dump(metrics, f_rep, ensure_ascii=False, indent=2)
        print(f"• Báo cáo số liệu chi tiết đã lưu tại: {rep_file.resolve()}")

        # Xuất biểu đồ hình ảnh thống kê hàng loạt Native Pillow
        chart_file = Path(args.chart_file) if args.chart_file else Path("results/evaluation_dashboard.png")
        render_batch_evaluation_dashboard(metrics, chart_file)
        print(f"🎉 ĐÃ XUẤT THÀNH CÔNG BIỂU ĐỒ BATCH DASHBOARD TẠI: {chart_file.resolve()}")

        # Xuất Báo cáo Markdown (.md) tổng hợp & phân tích từng câu hỏi
        if getattr(args, "md_file", None):
            md_file = Path(args.md_file)
        else:
            md_file = rep_file.with_suffix(".md")
        render_markdown_evaluation_report(
            metrics=metrics,
            eval_qids=eval_qids,
            log_dir=Path(args.log_dir),
            gold_map=gold_map,
            written_records=written_records,
            md_path=md_file,
            model_id=args.model_id,
        )
        print(f"📝 ĐÃ XUẤT BÁO CÁO PHÂN TÍCH MARKDOWN (.MD) CHI TIẾT TỪNG CÂU TẠI: {md_file.resolve()}")


# ==============================================================================
# HÀM CHÍNH (MAIN CLI ROUTER)
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Công cụ Toàn Năng Kiểm Thử White-Box & Đánh Giá Toàn Trình (DataMate Inspector & Evaluator)."
    )
    # Tùy chọn chung
    parser.add_argument("--data_dir", type=str, default="competition_data/train", help="Thư mục dữ liệu train/public_test")
    parser.add_argument("--config", type=str, default=None, help="Đường dẫn file cấu hình YAML tùy chỉnh")
    parser.add_argument("--biz", type=str, default=None, help="Chỉ định ID doanh nghiệp (ví dụ: biz_119)")
    parser.add_argument("--id", type=str, default=None, help="Chỉ định ID câu hỏi (ví dụ: q_8d076e8b04fa)")
    parser.add_argument("--random", action="store_true", help="Chọn ngẫu nhiên 1 câu hỏi từ tập dữ liệu")
    parser.add_argument("--with_llm", action="store_true", help="Kích hoạt nạp mô hình LLM GPU thật để sinh mã")
    parser.add_argument("--model_id", type=str, default="Qwen/Qwen2.5-Coder-14B-Instruct", help="Tên model LLM")
    parser.add_argument("--chart_file", type=str, default=None, help="Đường dẫn file ảnh dashboard PNG")
    parser.add_argument("--telemetry_file", type=str, default=None, help="Đường dẫn file telemetry JSON")

    # Tùy chọn đánh giá hàng loạt (Batch Evaluation Mode)
    parser.add_argument("--batch", action="store_true", help="Kích hoạt chế độ đánh giá hàng loạt nhiều câu hỏi")
    parser.add_argument("--batch_file", type=str, default=None, help="Đường dẫn file batch JSONL (ví dụ: batch_1_questions.jsonl)")
    parser.add_argument("--batch_index", type=int, default=None, help="Chỉ định đợt kiểm thử từ 1 đến 6 (mỗi đợt 20 câu)")
    parser.add_argument("--batch_size", type=int, default=20, help="Số lượng câu hỏi trong mỗi đợt (mặc định: 20)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng câu hỏi cần chạy trong batch")
    parser.add_argument("--sample", type=int, default=None, help="Lấy ngẫu nhiên N câu hỏi để đánh giá")
    parser.add_argument("--stratified", action="store_true", help="Lấy mẫu phân tầng (stratified) đảm bảo đủ các loại câu hỏi (number, list, string, percent, date, boolean, table, unanswerable)")
    parser.add_argument("--seed", type=int, default=42, help="Seed ngẫu nhiên khi lấy mẫu")
    parser.add_argument("--output_file", type=str, default="results/predictions.jsonl", help="File xuất kết quả dự đoán JSONL")
    parser.add_argument("--log_dir", type=str, default="results/logs", help="Thư mục lưu log chi tiết từng câu")
    parser.add_argument("--report_file", "--output", type=str, default="results/evaluation_report.json", help="File xuất báo cáo chi tiết JSON")
    parser.add_argument("--md_file", type=str, default=None, help="File xuất báo cáo chi tiết Markdown (.md) cho từng câu")
    parser.add_argument("--gold", "--answers", type=str, default=None, help="Đường dẫn file đáp án chuẩn answers.jsonl")
    parser.add_argument("--questions_file", type=str, default=None, help="Đường dẫn file câu hỏi questions.jsonl cụ thể")
    parser.add_argument("--dry_run", action="store_true", help="Chế độ chạy thử: không nạp GPU")
    parser.add_argument("--no_fill_abstain", action="store_true", help="Không tự động điền abstain cho các câu còn lại")
    parser.add_argument("--resume", action="store_true", help="Tiếp tục chạy các câu chưa hoàn thành")
    parser.add_argument("--tau_star", type=float, default=0.50, help="Ngưỡng độ tin cậy tối ưu để từ chối trả lời (mặc định: 0.50)")
    parser.add_argument("--timeout", type=int, default=30, help="Thời gian chờ tối đa khi chạy code trong sandbox (giây)")
    parser.add_argument("--in_process", action="store_true", help="Chạy code trực tiếp trong tiến trình thay vì sandbox")
    parser.add_argument("--max_new_tokens", type=int, default=768, help="Số token tối đa sinh ra từ LLM (mặc định: 768)")
    parser.add_argument("--replay_logs", type=str, default=None, help="Thư mục logs đã sinh để chạy lại sandbox + cổng abstention + format (bỏ qua LLM)")
    parser.add_argument("--quantization", "--quant", type=str, default="4bit", choices=["8bit", "4bit", "none"], help="Chế độ lượng tử hóa mô hình (mặc định: 4bit)")
    parser.add_argument("--preserve_order", action="store_true", help="Chạy đúng theo thứ tự gốc từ câu 1 đến câu cuối trong questions.jsonl (không gom nhóm theo shop)")
    parser.add_argument("--range", type=str, default=None, help="Chỉ định khoảng câu hỏi cần chạy (1-based, ví dụ: 1-50 hoặc 101-200)")

    args = parser.parse_args()

    if getattr(args, "quantization", None):
        os.environ["DATAMATE_QUANTIZATION"] = args.quantization

    # Nhận diện chế độ: Nếu có cờ --batch, --batch_file, --batch_index, --replay_logs hoặc (limit > 1 mà không chỉ định --id cụ thể)
    is_batch_mode = (
        args.batch
        or (args.range is not None)
        or (args.replay_logs is not None)
        or (args.batch_file is not None)
        or (args.batch_index is not None)
        or (args.limit is not None and args.limit > 1 and not args.id)
        or (args.sample is not None and not args.id)
    )

    if is_batch_mode:
        run_batch_evaluation(args)
        return

    # Chế độ Single Inspection Mode
    data_dir = Path(args.data_dir)
    questions_file = Path(args.questions_file) if args.questions_file else (data_dir / "questions.jsonl")
    answers_file = Path(args.gold) if args.gold else (data_dir / "answers.jsonl")
    data_root = data_dir / "data"

    if not questions_file.exists():
        print(f"❌ Không tìm thấy {questions_file}")
        sys.exit(1)

    with open(questions_file, "r", encoding="utf-8") as f:
        all_questions = [json.loads(line) for line in f if line.strip()]

    gold_answers = {}
    if answers_file.exists():
        with open(answers_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    gold_answers[item["id"]] = item

    target_q = None
    if args.id:
        target_q = next((q for q in all_questions if q.get("id") == args.id), None)
    elif args.biz:
        biz_qs = [q for q in all_questions if q.get("business_id") == args.biz]
        if biz_qs:
            target_q = random.choice(biz_qs) if args.random else biz_qs[0]
    elif args.random:
        target_q = random.choice(all_questions)
    else:
        target_q = all_questions[0]

    if not target_q:
        print("❌ Không tìm thấy câu hỏi phù hợp với tiêu chí lọc!")
        sys.exit(1)

    gold_record = gold_answers.get(target_q["id"])
    run_single_inspection(target_q, gold_record, data_dir, data_root, args)


if __name__ == "__main__":
    main()
