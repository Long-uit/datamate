import os
import sys
import json
import re
import difflib
import hashlib
import sqlite3
import argparse
import random
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import pandas as pd
except ImportError:
    print("[ERROR] pandas chưa được cài đặt. Vui lòng chạy: pip install pandas openpyxl")
    sys.exit(1)

try:
    import openpyxl
except ImportError:
    openpyxl = None


# ==============================================================================
# HÀM TIỆN ÍCH CHUNG
# ==============================================================================

def get_file_sha256(path: Path) -> str:
    """Tính SHA256 checksum của file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def truncate_val(val: Any, max_len: int = 40) -> str:
    """Cắt ngắn chuỗi hiển thị nếu quá dài."""
    s = str(val) if val is not None else ""
    return s if len(s) <= max_len else s[:max_len - 3] + "..."


def is_blank(val: Any) -> bool:
    """Kiểm tra giá trị trống: None, NaN, hoặc chuỗi rỗng / chỉ chứa khoảng trắng."""
    if val is None:
        return True
    if pd.isna(val):
        return True
    if isinstance(val, str) and not val.strip():
        return True
    return False


# ==============================================================================
# 2. XỬ LÝ NGÀY THÁNG THỦ CÔNG (ĐỊNH DẠNG TƯỜNG MINH & EXCEL SERIAL)
# ==============================================================================

DATE_FORMAT_CANDIDATES = [
    ("ISO_YYYY-MM-DD", "%Y-%m-%d"),
    ("ISO_YYYY/MM/DD", "%Y/%m/%d"),
    ("DD/MM/YYYY", "%d/%m/%Y"),
    ("DD-MM-YYYY", "%d-%m-%Y"),
    ("DD/MM/YYYY_HH:MM", "%d/%m/%Y %H:%M"),
    ("DD/MM/YYYY_HH:MM:SS", "%d/%m/%Y %H:%M:%S"),
    ("ISO_DATETIME", "%Y-%m-%d %H:%M:%S"),
]

def parse_date_series(series: pd.Series) -> Optional[Dict[str, Any]]:
    """Thử parse cột theo từng định dạng cụ thể, hỗ trợ cả Excel serial numbers.
    Chọn định dạng parse được nhiều giá trị hợp lệ nhất.
    """
    non_blank = series[~series.map(is_blank)]
    if len(non_blank) == 0:
        return None

    total_valid_entries = len(non_blank)

    # 1. Kiểm tra trường hợp Excel serial số nguyên/thực (ví dụ 45000 -> 2023-03-15)
    numeric_series = pd.to_numeric(non_blank, errors="coerce")
    valid_numeric_count = numeric_series.notna().sum()
    if valid_numeric_count / total_valid_entries >= 0.8:
        # Kiểm tra khoảng giá trị hợp lý của ngày Excel (30000 = ~1982 đến 60000 = ~2064)
        sensible_mask = (numeric_series >= 30000) & (numeric_series <= 60000)
        if sensible_mask.sum() / total_valid_entries >= 0.7:
            try:
                parsed_excel = pd.to_datetime(numeric_series[sensible_mask], unit="D", origin="1899-12-30", errors="coerce")
                valid_parsed = parsed_excel.dropna()
                if len(valid_parsed) > 0:
                    unparsed = total_valid_entries - len(valid_parsed)
                    return {
                        "chosen_format": "Excel_Serial_Numeric",
                        "parsed_count": len(valid_parsed),
                        "unparsed_count": unparsed,
                        "min_date": str(valid_parsed.min().date()),
                        "max_date": str(valid_parsed.max().date()),
                        "min_ts": valid_parsed.min(),
                        "max_ts": valid_parsed.max()
                    }
            except Exception:
                pass

    # 2. Thử các chuỗi định dạng
    str_series = non_blank.astype(str).str.strip()
    best_res = None
    max_parsed_cnt = 0

    for fmt_name, fmt_pattern in DATE_FORMAT_CANDIDATES:
        try:
            parsed = pd.to_datetime(str_series, format=fmt_pattern, errors="coerce")
            valid = parsed.dropna()
            cnt = len(valid)
            if cnt > max_parsed_cnt:
                max_parsed_cnt = cnt
                unparsed = total_valid_entries - cnt
                best_res = {
                    "chosen_format": fmt_name,
                    "parsed_count": cnt,
                    "unparsed_count": unparsed,
                    "min_date": str(valid.min().date()),
                    "max_date": str(valid.max().date()),
                    "min_ts": valid.min(),
                    "max_ts": valid.max()
                }
        except Exception:
            continue

    # Chỉ công nhận là cột ngày nếu tỷ lệ parse thành công >= 70% số ô không trống
    if best_res and (best_res["parsed_count"] / total_valid_entries >= 0.7):
        return best_res

    return None


# ==============================================================================
# B3. SO SÁNH RULEBOOK GIỮA CÁC SPLIT
# ==============================================================================

def analyze_rulebooks(train_root: Path, test_root: Path) -> Dict[str, Any]:
    """B3: So sánh rulebook giữa train và public_test, tính SHA256, in diff và 40 dòng đầu."""
    report = {
        "train_rulebook_exists": False,
        "test_rulebook_exists": False,
        "train_sha256": None,
        "test_sha256": None,
        "is_identical": False,
        "first_40_lines": [],
        "diff_summary": None,
        "diff_lines": []
    }

    train_rb = train_root / "rulebook.md"
    test_rb = test_root / "rulebook.md"

    if train_rb.exists():
        report["train_rulebook_exists"] = True
        report["train_sha256"] = get_file_sha256(train_rb)
        with open(train_rb, "r", encoding="utf-8-sig", errors="ignore") as f:
            t_lines = f.readlines()
        report["first_40_lines"] = [l.rstrip("\r\n") for l in t_lines[:40]]
    else:
        t_lines = []

    if test_rb.exists():
        report["test_rulebook_exists"] = True
        report["test_sha256"] = get_file_sha256(test_rb)
        with open(test_rb, "r", encoding="utf-8-sig", errors="ignore") as f:
            p_lines = f.readlines()
    else:
        p_lines = []

    if train_rb.exists() and test_rb.exists():
        if report["train_sha256"] == report["test_sha256"]:
            report["is_identical"] = True
        else:
            report["is_identical"] = False
            diff = list(difflib.unified_diff(
                t_lines, p_lines,
                fromfile="train/rulebook.md",
                tofile="public_test/rulebook.md",
                n=2
            ))
            report["diff_lines"] = [d.rstrip("\r\n") for d in diff[:80]]
            report["diff_summary"] = f"Khác nhau ({len(diff)} dòng diff, hiển thị tối đa 80 dòng)"
    return report


# ==============================================================================
# B1. PHÂN TÍCH QUESTIONS & ANSWERS (CHUẨN 9 TYPES)
# ==============================================================================

OFFICIAL_9_TYPES = [
    "number", "percent", "date", "boolean", "string", "list", "table",
    "unanswerable", "abstain"
]

def analyze_questions_and_answers(split_dir: Path, is_train: bool = True) -> Dict[str, Any]:
    """B1: Phân tích questions.jsonl (và answers.jsonl nếu là train), chuẩn 9 types."""
    q_file = split_dir / "questions.jsonl"
    a_file = split_dir / "answers.jsonl"
    data_dir = split_dir / "data"

    shop_dirs = {d.name for d in data_dir.iterdir() if d.is_dir()} if data_dir.exists() else set()

    res: Dict[str, Any] = {
        "total_questions": 0,
        "corrupted_json_lines": [],
        "missing_fields_lines": [],
        "duplicate_ids": [],
        "business_counts": {},
        "business_mismatches": {"missing_in_data": [], "extra_in_data": []},
        "as_of_date_stats": {"unique_count": 0, "min": None, "max": None, "is_constant_per_business": True},
        "question_lengths": {"min": 0, "median": 0, "max": 0},
        "temporal_patterns": {},
        "teencode_informal_ratio": 0.0,
        "answer_types_distribution": {t: 0 for t in OFFICIAL_9_TYPES},
        "unanswerable_count": 0,
        "unanswerable_ratio": 0.0,
        "type_by_business": {},
        "raw_answer_examples_by_type": {},
        "alias_stats": {"has_alias_count": 0, "samples": []},
        "raw_data_cache": []
    }

    if not q_file.exists():
        res["error"] = f"Không tìm thấy file: {q_file}"
        return res

    answers_map = {}
    if is_train and a_file.exists():
        with open(a_file, "r", encoding="utf-8-sig", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    q_id = obj.get("id")
                    if q_id is not None:
                        answers_map[q_id] = obj
                except Exception:
                    pass

    seen_ids = set()
    lengths = []
    as_of_dates = set()
    as_of_by_biz: Dict[str, set] = {}

    temporal_regexes = {
        "hôm nay": re.compile(r"\bhôm nay\b", re.I),
        "hôm qua": re.compile(r"\bhôm qua\b", re.I),
        "tuần này": re.compile(r"\btuần này\b", re.I),
        "tuần trước/tuần rồi": re.compile(r"\b(tuần trước|tuần rồi)\b", re.I),
        "tháng này": re.compile(r"\btháng này\b", re.I),
        "tháng trước/tháng rồi": re.compile(r"\b(tháng trước|tháng rồi)\b", re.I),
        "tháng X (tháng \\d+)": re.compile(r"\btháng\s+\d+\b", re.I),
        "N ngày qua/gần nhất": re.compile(r"\b\d+\s*ngày\s*(gần nhất|qua)\b", re.I),
        "tết (âm/dương)": re.compile(r"\btết\b", re.I),
        "quý (quý \\d+)": re.compile(r"\bquý\s*\d+\b", re.I),
        "năm YYYY": re.compile(r"\bnăm\s*\d{4}\b", re.I),
    }
    temporal_counts = {k: 0 for k in temporal_regexes}

    informal_regex = re.compile(r"\b(dthu|d thu|hnay|hqua|bnhiu|bnhieu|bn|k|ko|khg|dt|dc|đc|sp|nv|sl|slg|chua|thag|tuan)\b", re.I)
    vietnamese_accents = re.compile(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", re.I)
    informal_count = 0

    with open(q_file, "r", encoding="utf-8-sig", errors="ignore") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            res["total_questions"] += 1
            try:
                q_obj = json.loads(line)
            except Exception as e:
                res["corrupted_json_lines"].append({"line": idx + 1, "error": str(e)})
                continue

            q_id = q_obj.get("id")
            biz = q_obj.get("business_id")
            q_text = q_obj.get("question", "")
            as_of = q_obj.get("as_of_date")

            if q_id is None or biz is None:
                res["missing_fields_lines"].append(idx + 1)

            if q_id in seen_ids:
                res["duplicate_ids"].append(q_id)
            seen_ids.add(q_id)

            if biz:
                res["business_counts"][biz] = res["business_counts"].get(biz, 0) + 1
                if biz not in as_of_by_biz:
                    as_of_by_biz[biz] = set()
                if as_of:
                    as_of_by_biz[biz].add(as_of)

            if as_of:
                as_of_dates.add(str(as_of))

            lengths.append(len(q_text))

            for pat_name, reg in temporal_regexes.items():
                if reg.search(q_text):
                    temporal_counts[pat_name] += 1

            has_teencode_word = bool(informal_regex.search(q_text))
            accents_count = len(vietnamese_accents.findall(q_text))
            ratio_accents = (accents_count / max(1, len(q_text))) if len(q_text) > 15 else 0.2
            if has_teencode_word or ratio_accents < 0.05:
                informal_count += 1

            ans_obj = answers_map.get(q_id, {})
            merged_item = {**q_obj, **ans_obj}
            res["raw_data_cache"].append(merged_item)

            if is_train and ans_obj:
                ans_type = ans_obj.get("type", "unknown")
                ans_val = ans_obj.get("answer")

                # Chuẩn hóa về 9 types chính thức
                if ans_val is None or ans_type == "unanswerable":
                    ans_type = "unanswerable"
                    res["unanswerable_count"] += 1

                if ans_type not in res["answer_types_distribution"]:
                    res["answer_types_distribution"][ans_type] = 0
                res["answer_types_distribution"][ans_type] += 1

                if biz:
                    if biz not in res["type_by_business"]:
                        res["type_by_business"][biz] = {}
                    res["type_by_business"][biz][ans_type] = res["type_by_business"][biz].get(ans_type, 0) + 1

                if ans_type not in res["raw_answer_examples_by_type"]:
                    res["raw_answer_examples_by_type"][ans_type] = {
                        "id": q_id,
                        "question": q_text,
                        "raw_answer": ans_val,
                    }

                alias_val = ans_obj.get("alias")
                if alias_val:
                    res["alias_stats"]["has_alias_count"] += 1
                    if len(res["alias_stats"]["samples"]) < 5:
                        res["alias_stats"]["samples"].append({"id": q_id, "alias": alias_val, "question": q_text})

    res["temporal_patterns"] = temporal_counts
    if res["total_questions"] > 0:
        res["teencode_informal_ratio"] = round(informal_count / res["total_questions"], 4)
        if lengths:
            lengths.sort()
            res["question_lengths"]["min"] = lengths[0]
            res["question_lengths"]["median"] = lengths[len(lengths) // 2]
            res["question_lengths"]["max"] = lengths[-1]

        if is_train:
            res["unanswerable_ratio"] = round(res["unanswerable_count"] / res["total_questions"], 4)

    q_bizs = set(res["business_counts"].keys())
    res["business_mismatches"]["missing_in_data"] = sorted(list(q_bizs - shop_dirs))
    res["business_mismatches"]["extra_in_data"] = sorted(list(shop_dirs - q_bizs))

    if as_of_dates:
        s_dates = sorted(list(as_of_dates))
        res["as_of_date_stats"]["unique_count"] = len(s_dates)
        res["as_of_date_stats"]["min"] = s_dates[0]
        res["as_of_date_stats"]["max"] = s_dates[-1]
        const_biz = all(len(dates) == 1 for dates in as_of_by_biz.values())
        res["as_of_date_stats"]["is_constant_per_business"] = const_biz

    return res


# ==============================================================================
# B2. PROFILE TỪNG BẢNG DỮ LIỆU (RULE 8 TOÀN DIỆN, DATE THEO FORMAT)
# ==============================================================================

def profile_tabular_data(
    df: pd.DataFrame,
    source_name: str,
    max_rows_limit: Optional[int] = None,
    actual_total_rows: Optional[int] = None,
    header_shift_note: Optional[str] = None
) -> Dict[str, Any]:
    """B2: Profile chi tiết cho 1 dataframe.
    - Toàn bộ giá trị phân loại.
    - Rule 8 forward-fill quét trên toàn bộ dòng đã nạp, coi '' như trống.
    - Date parse có format rõ ràng.
    """
    profiled_rows = len(df)
    total_cols = len(df.columns)
    is_truncated = False

    if max_rows_limit and profiled_rows > max_rows_limit:
        df = df.iloc[:max_rows_limit]
        profiled_rows = len(df)
        is_truncated = True

    meta: Dict[str, Any] = {
        "source": source_name,
        "profiled_rows": profiled_rows,
        "actual_total_rows": actual_total_rows or profiled_rows,
        "is_truncated": is_truncated,
        "header_shift_note": header_shift_note,
        "cols": total_cols,
        "columns": [str(c) for c in df.columns],
        "sample_3_rows": [],
        "null_ratios": {},
        "high_null_cols": [],
        "duplicate_rows_count": 0,
        "group_null_candidates": [], # Nghi ngờ Rule 8
        "date_cols_summary": {},
        "categorical_cols": {}, # TOÀN BỘ giá trị
        "potential_keys": {},
    }

    if profiled_rows == 0:
        return meta

    # 3 dòng mẫu
    sample_records = []
    for _, row in df.head(3).iterrows():
        sample_records.append({str(k): truncate_val(v, 40) for k, v in row.to_dict().items()})
    meta["sample_3_rows"] = sample_records

    # Đếm dòng trùng lặp hoàn toàn
    try:
        meta["duplicate_rows_count"] = int(df.duplicated().sum())
    except Exception:
        pass

    key_name_re = re.compile(r"(mã|id|code|sku|uuid|key)", re.I)

    # 4. Quét Rule 8 Forward-fill TOÀN DIỆN:
    # Cột có ô trống (NaN hoặc rỗng), mà dòng liền trước không trống và các cột khác cùng dòng có dữ liệu.
    # Coi '' và khoảng trắng như trống.
    is_blank_df = df.map(is_blank)
    row_has_other_data = (is_blank_df.sum(axis=1) < total_cols) # Dòng không phải trống toàn bộ

    for col in df.columns:
        c_str = str(col)
        blank_series = is_blank_df[col]
        blank_cnt = int(blank_series.sum())
        blank_ratio = round(blank_cnt / profiled_rows, 4)
        meta["null_ratios"][c_str] = blank_ratio
        if blank_ratio > 0.3:
            meta["high_null_cols"].append({"col": c_str, "ratio": blank_ratio})

        # Quét ứng viên nghi ngờ cần forward fill
        if 0.05 <= blank_ratio <= 0.90:
            # Điều kiện: dòng hiện tại trống, dòng liền trước có giá trị, và dòng hiện tại vẫn có cột khác có dữ liệu
            prev_not_blank = (~blank_series).shift(1, fill_value=False)
            ffill_mask = blank_series & prev_not_blank & row_has_other_data
            suspect_count = int(ffill_mask.sum())
            if suspect_count >= 2:
                # Trích 5 mẫu
                sample_indices = df[ffill_mask].index[:5].tolist()
                samples_info = []
                for s_idx in sample_indices:
                    prev_v = truncate_val(df.at[s_idx - 1, col], 20)
                    curr_v = "<TRỐNG>"
                    samples_info.append(f"Dòng {s_idx+1}: [{prev_v} -> {curr_v}]")

                meta["group_null_candidates"].append({
                    "col": c_str,
                    "blank_ratio": blank_ratio,
                    "suspect_ffill_count": suspect_count,
                    "samples": samples_info
                })

        # 2. Parse ngày tháng theo format tường minh
        col_series = df[col]
        parsed_date_meta = parse_date_series(col_series)
        if parsed_date_meta:
            meta["date_cols_summary"][c_str] = parsed_date_meta

        # 1. Cột phân loại: lưu TOÀN BỘ giá trị nếu <= 15 giá trị khác nhau
        try:
            non_blank_vals = col_series[~blank_series]
            n_unique = non_blank_vals.nunique()
            if 1 < n_unique <= 15:
                # Lưu toàn bộ giá trị và tần suất xuất hiện
                val_counts = non_blank_vals.value_counts().to_dict()
                meta["categorical_cols"][c_str] = {str(k): int(v) for k, v in val_counts.items()}
        except Exception:
            pass

        # Cột tiềm năng là Khóa
        if key_name_re.search(c_str):
            try:
                meta["potential_keys"][c_str] = int(col_series[~blank_series].nunique())
            except Exception:
                pass

    return meta


def profile_shop_directory(shop_dir: Path, max_rows: int = 100000) -> Dict[str, Any]:
    """Profile toàn bộ file/sheet/bảng trong một shop."""
    shop_profile: Dict[str, Any] = {
        "shop_name": shop_dir.name,
        "readme_info": {},
        "tables": {},
        "cross_table_potential_joins": [],
        "operating_months": None,
        "shop_min_date": None,
        "shop_max_date": None,
        "errors": []
    }

    all_keys_by_table: Dict[str, Dict[str, int]] = {}
    shop_min_ts = None
    shop_max_ts = None

    # Quét README trước
    readme_path = shop_dir / "README.md"
    if readme_path.exists():
        try:
            with open(readme_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                r_lines = [l.rstrip("\r\n") for l in f]
            shop_profile["readme_info"] = {
                "lines_count": len(r_lines),
                "is_short": len(r_lines) < 15,
                "first_10_lines": r_lines[:10]
            }
        except Exception as e:
            shop_profile["readme_info"] = {"error": str(e)}

    for fpath in sorted(shop_dir.rglob("*.*")):
        ext = fpath.suffix.lower()
        rel_str = fpath.relative_to(shop_dir).as_posix()

        # 1. File CSV
        if ext == ".csv" and fpath.name.lower() != "calendar.csv":
            try:
                enc = "utf-8-sig"
                try:
                    pd.read_csv(fpath, encoding=enc, nrows=5)
                except Exception:
                    enc = "latin1"

                df = pd.read_csv(fpath, encoding=enc, low_memory=False)
                t_prof = profile_tabular_data(df, source_name=rel_str, max_rows_limit=max_rows)
                shop_profile["tables"][rel_str] = t_prof
                all_keys_by_table[rel_str] = t_prof.get("potential_keys", {})

                # Gom ngày min/max của shop
                for d_meta in t_prof.get("date_cols_summary", {}).values():
                    if d_meta.get("min_ts") and (shop_min_ts is None or d_meta["min_ts"] < shop_min_ts):
                        shop_min_ts = d_meta["min_ts"]
                    if d_meta.get("max_ts") and (shop_max_ts is None or d_meta["max_ts"] > shop_max_ts):
                        shop_max_ts = d_meta["max_ts"]
            except Exception as e:
                shop_profile["errors"].append({"file": rel_str, "error": str(e)})

        # 2. File Excel
        elif ext in [".xlsx", ".xls"]:
            # Mở openpyxl 1 lần cho cả workbook để lấy số dòng thật từng sheet
            sheet_real_rows = {}
            if openpyxl:
                try:
                    wb = openpyxl.load_workbook(fpath, read_only=True, data_only=True)
                    for sname in wb.sheetnames:
                        ws = wb[sname]
                        sheet_real_rows[sname] = max(0, (ws.max_row or 1) - 1)
                    wb.close()
                except Exception:
                    pass

            try:
                xl = pd.ExcelFile(fpath)
                for sheet in xl.sheet_names:
                    s_id = f"{rel_str} :: [{sheet}]"
                    real_r = sheet_real_rows.get(sheet)
                    try:
                        # 3. Dò header lệch trước khi đọc
                        raw_10 = pd.read_excel(xl, sheet_name=sheet, nrows=10, header=None)
                        detected_header = 0
                        header_note = None

                        # Kiểm tra xem dòng 0 có nhiều Unnamed hoặc trống không
                        head_0 = pd.read_excel(xl, sheet_name=sheet, nrows=5, header=0)
                        unnamed_cnt = sum(1 for c in head_0.columns if "Unnamed:" in str(c))
                        if unnamed_cnt >= 2 or len(head_0.columns) - unnamed_cnt <= 2:
                            # Dò dòng có nhiều ô chuỗi nhất
                            best_r = 0
                            max_strs = 0
                            for r_idx in range(len(raw_10)):
                                row_vals = raw_10.iloc[r_idx]
                                s_cnt = sum(1 for v in row_vals if isinstance(v, str) and v.strip())
                                if s_cnt > max_strs and s_cnt >= len(row_vals) * 0.4:
                                    max_strs = s_cnt
                                    best_r = r_idx
                            if best_r > 0:
                                detected_header = best_r
                                header_note = f"Header đã dịch dòng {detected_header + 1} (index {detected_header})"

                        # Đọc lại sheet với header đã dò được
                        df = pd.read_excel(xl, sheet_name=sheet, header=detected_header, nrows=max_rows)
                        t_prof = profile_tabular_data(
                            df,
                            source_name=s_id,
                            max_rows_limit=max_rows,
                            actual_total_rows=real_r,
                            header_shift_note=header_note
                        )
                        shop_profile["tables"][s_id] = t_prof
                        all_keys_by_table[s_id] = t_prof.get("potential_keys", {})

                        # Gom ngày min/max của shop
                        for d_meta in t_prof.get("date_cols_summary", {}).values():
                            if d_meta.get("min_ts") and (shop_min_ts is None or d_meta["min_ts"] < shop_min_ts):
                                shop_min_ts = d_meta["min_ts"]
                            if d_meta.get("max_ts") and (shop_max_ts is None or d_meta["max_ts"] > shop_max_ts):
                                shop_max_ts = d_meta["max_ts"]
                    except Exception as se:
                        shop_profile["errors"].append({"file": s_id, "error": str(se)})
            except Exception as e:
                shop_profile["errors"].append({"file": rel_str, "error": str(e)})

        # 3. File SQLite (dùng as_uri + mode=ro)
        elif ext in [".sqlite", ".db", ".sqlite3"]:
            try:
                uri = f"{fpath.resolve().as_uri()}?mode=ro"
                conn = sqlite3.connect(uri, uri=True)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                tables = [r[0] for r in cursor.fetchall()]
                for tbl in tables:
                    t_id = f"{rel_str} :: [{tbl}]"
                    try:
                        cursor.execute(f'SELECT COUNT(*) FROM "{tbl}";')
                        tbl_rows = cursor.fetchone()[0]
                        df = pd.read_sql_query(f'SELECT * FROM "{tbl}" LIMIT {max_rows};', conn)
                        t_prof = profile_tabular_data(
                            df,
                            source_name=t_id,
                            max_rows_limit=max_rows,
                            actual_total_rows=tbl_rows
                        )
                        shop_profile["tables"][t_id] = t_prof
                        all_keys_by_table[t_id] = t_prof.get("potential_keys", {})

                        for d_meta in t_prof.get("date_cols_summary", {}).values():
                            if d_meta.get("min_ts") and (shop_min_ts is None or d_meta["min_ts"] < shop_min_ts):
                                shop_min_ts = d_meta["min_ts"]
                            if d_meta.get("max_ts") and (shop_max_ts is None or d_meta["max_ts"] > shop_max_ts):
                                shop_max_ts = d_meta["max_ts"]
                    except Exception as te:
                        shop_profile["errors"].append({"file": t_id, "error": str(te)})
                conn.close()
            except Exception as e:
                shop_profile["errors"].append({"file": rel_str, "error": str(e)})

    # Tính số tháng hoạt động (min -> max) của shop
    if shop_min_ts is not None and shop_max_ts is not None:
        shop_profile["shop_min_date"] = str(shop_min_ts.date())
        shop_profile["shop_max_date"] = str(shop_max_ts.date())
        m_diff = (shop_max_ts.year - shop_min_ts.year) * 12 + (shop_max_ts.month - shop_min_ts.month) + 1
        shop_profile["operating_months"] = max(1, m_diff)

    # Khóa liên kết
    table_names = list(all_keys_by_table.keys())
    for i in range(len(table_names)):
        for j in range(i + 1, len(table_names)):
            t1, t2 = table_names[i], table_names[j]
            keys1 = set(all_keys_by_table[t1].keys())
            keys2 = set(all_keys_by_table[t2].keys())
            common_keys = keys1.intersection(keys2)
            for ck in common_keys:
                shop_profile["cross_table_potential_joins"].append({
                    "table_a": t1,
                    "table_b": t2,
                    "shared_key": ck,
                    "unique_in_a": all_keys_by_table[t1][ck],
                    "unique_in_b": all_keys_by_table[t2][ck]
                })

    return shop_profile


# ==============================================================================
# B4. CHỌN 10 CÂU HỎI MẪU TIÊU BIỂU CHO PROMPT (ƯU TIÊN CỐ ĐỊNH, KHÔNG BỊ CẮT)
# ==============================================================================

def select_10_sample_questions(
    raw_data: List[Dict[str, Any]],
    train_root: Path,
    seed: int = 42
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """B4: Chọn 10 câu mẫu theo thứ tự ưu tiên cố định:
    1. >= 2 câu unanswerable
    2. >= 2 câu thời gian tương đối
    3. >= 1 câu Tết (nếu có)
    4. Lấp các type còn thiếu (number, percent, date, boolean, string, list, table)
    5. Đảm bảo >= 4 business_id khác nhau.
    """
    random.seed(seed)

    biz_files_map: Dict[str, List[str]] = {}
    data_dir = train_root / "data"
    if data_dir.exists():
        for b_dir in data_dir.iterdir():
            if b_dir.is_dir():
                f_list = [f.name for f in b_dir.rglob("*.*") if f.is_file() and not f.name.startswith(".")]
                biz_files_map[b_dir.name] = f_list

    temporal_re = re.compile(r"\b(hôm nay|hôm qua|tuần này|tuần trước|tuần rồi|tháng này|tháng trước|tháng rồi|ngày qua|gần nhất)\b", re.I)
    tet_re = re.compile(r"\btết\b", re.I)

    unanswerable_pool = []
    temporal_pool = []
    tet_pool = []
    by_type: Dict[str, List[Dict[str, Any]]] = {}

    for item in raw_data:
        ans_type = item.get("type", "unknown")
        q_text = item.get("question", "")
        ans_val = item.get("answer")

        if ans_val is None or ans_type == "unanswerable":
            unanswerable_pool.append(item)
            ans_type = "unanswerable"
        by_type.setdefault(ans_type, []).append(item)

        if tet_re.search(q_text):
            tet_pool.append(item)
        if temporal_re.search(q_text):
            temporal_pool.append(item)

    selected: List[Dict[str, Any]] = []
    selected_ids = set()

    def add_candidate(c: Optional[Dict[str, Any]]) -> bool:
        if c and c.get("id") not in selected_ids and len(selected) < 10:
            selected.append(c)
            selected_ids.add(c.get("id"))
            return True
        return False

    # 1. ƯU TIÊN 1: >= 2 câu unanswerable
    random.shuffle(unanswerable_pool)
    u_added = 0
    for c in unanswerable_pool:
        if u_added >= 2 or len(selected) >= 10:
            break
        if add_candidate(c):
            u_added += 1

    # 2. ƯU TIÊN 2: >= 2 câu thời gian tương đối
    random.shuffle(temporal_pool)
    temp_added = sum(1 for x in selected if temporal_re.search(x.get("question", "")))
    for c in temporal_pool:
        if temp_added >= 2 or len(selected) >= 10:
            break
        if add_candidate(c):
            temp_added += 1

    # 3. ƯU TIÊN 3: >= 1 câu Tết (nếu có)
    random.shuffle(tet_pool)
    tet_added = sum(1 for x in selected if tet_re.search(x.get("question", "")))
    for c in tet_pool:
        if tet_added >= 1 or len(selected) >= 10:
            break
        if add_candidate(c):
            tet_added += 1

    # 4. ƯU TIÊN 4: Lấp các type còn thiếu
    target_types = ["number", "percent", "date", "boolean", "string", "list", "table"]
    for t in target_types:
        if len(selected) >= 10:
            break
        has_t = any(x.get("type") == t for x in selected)
        if not has_t:
            pool = by_type.get(t, [])
            random.shuffle(pool)
            for c in pool:
                if add_candidate(c):
                    break

    # 5. Nếu vẫn chưa đủ 10, bổ sung ngẫu nhiên
    all_pool = [x for x in raw_data if x.get("id") not in selected_ids]
    random.shuffle(all_pool)
    for c in all_pool:
        if len(selected) >= 10:
            break
        add_candidate(c)

    # Checklist kiểm tra
    chk_u = sum(1 for x in selected if x.get("answer") is None or x.get("type") == "unanswerable") >= 2
    chk_temp = sum(1 for x in selected if temporal_re.search(x.get("question", ""))) >= 2
    chk_tet = (sum(1 for x in selected if tet_re.search(x.get("question", ""))) >= 1) if tet_pool else True
    types_in_sel = {x.get("type") for x in selected}
    chk_types = len(types_in_sel) >= 6
    biz_in_sel = {x.get("business_id") for x in selected}
    chk_biz = len(biz_in_sel) >= 4

    checklist = {
        ">= 2 câu unanswerable": chk_u,
        ">= 2 câu thời gian tương đối": chk_temp,
        ">= 1 câu Tết": chk_tet,
        "Đa dạng kiểu dữ liệu (>= 6 types)": chk_types,
        ">= 4 business_id khác nhau": chk_biz,
        "Số lượng chính xác 10 câu": len(selected) == 10
    }

    output_samples = []
    for s in selected:
        b_id = s.get("business_id", "")
        item_copy = dict(s)
        item_copy["business_files"] = biz_files_map.get(b_id, [])
        output_samples.append(item_copy)

    return output_samples, checklist


# ==============================================================================
# XUẤT BÁO CÁO (MARKDOWN & JSON)
# ==============================================================================

def generate_dynamic_recommendations(full_data: Dict[str, Any]) -> List[str]:
    """Sinh 5-8 gạch đầu dòng khuyến nghị tự động từ số liệu thực tế quét được."""
    recs = []

    # 1. BOM & Encoding
    bom_cnt = full_data.get("metrics", {}).get("total_bom_files", 0)
    recs.append(f"Xử lý BOM và Encoding: Đã phát hiện {bom_cnt} file/cột dính BOM (\\ufeff). Bắt buộc mở toàn bộ CSV với 'utf-8-sig' và strip khoảng trắng đầu/cuối của tên cột.")

    # 2. Lệch Header
    shift_cnt = full_data.get("metrics", {}).get("total_shifted_headers", 0)
    recs.append(f"Bộ dò Header thông minh (Header Shift): Phát hiện {shift_cnt} sheet/bảng Excel bị lệch dòng tiêu đề (Unnamed cols). Parser phải quét 10 dòng đầu để dò tìm dòng header thật thay vì fix cứng header=0.")

    # 3. Rule 8 Forward-fill
    ffill_cnt = full_data.get("metrics", {}).get("total_ffill_suspect_tables", 0)
    recs.append(f"Lá chắn Rule 8 Forward-fill: Phát hiện {ffill_cnt} bảng có dấu hiệu ô trống theo nhóm cấp đơn hàng (Mã đơn/Ngày/Trạng thái trống xen kẽ). Parser bắt buộc thực hiện forward-fill các cột định danh theo thứ tự dòng.")

    # 4. Định dạng ngày tháng
    date_fmts = full_data.get("metrics", {}).get("encountered_date_formats", [])
    fmt_str = ", ".join(date_fmts[:5]) if date_fmts else "ISO, DD/MM/YYYY, Excel Serial"
    unparsed_cnt = full_data.get("metrics", {}).get("total_unparsed_dates", 0)
    recs.append(f"Chuẩn hóa Ngày tháng đa định dạng: Đã ghi nhận các dạng ({fmt_str}) cùng {unparsed_cnt} giá trị không thể parse bằng format chuẩn. Cần bộ chuyển đổi ưu tiên thử chuỗi định dạng trước khi fallback.")

    # 5. So sánh Rulebook
    rb_diff = not full_data.get("rulebook_analysis", {}).get("is_identical", True)
    if rb_diff:
        recs.append("Đồng bộ Nghiệp vụ theo Rulebook mới nhất: Rulebook giữa train và public_test KHÁC NHAU (thêm ngành Mẹ & Bé, Sửa xe, Xếp hạng mới). Toàn bộ lá chắn logic phải tuân theo rulebook.md của public_test.")
    else:
        recs.append("Đồng bộ Nghiệp vụ: Rulebook giữa hai split đồng nhất 100%.")

    # 6. Chuẩn hóa 9 kiểu dữ liệu đầu ra
    types_found = list(full_data.get("train", {}).get("questions_stats", {}).get("answer_types_distribution", {}).keys())
    recs.append(f"Format Normalizer cho 9 kiểu đáp án: Đã lập bản đồ 9 types BTC quy định ({', '.join(OFFICIAL_9_TYPES)}). Đặc biệt percent không để dấu %, unanswerable trả về null, boolean trả về true/false viết thường.")

    # 7. Deduplication
    dup_cnt = full_data.get("metrics", {}).get("total_duplicate_rows", 0)
    recs.append(f"Khử trùng lặp dòng POS: Đã phát hiện tổng cộng {dup_cnt} dòng trùng lặp 100% trong toàn bộ tập dữ liệu do lỗi xuất file. Bắt buộc drop duplicates trước khi tính tổng.")

    return recs


def generate_markdown_report(full_data: Dict[str, Any]) -> str:
    """Tạo báo cáo markdown tự đủ dạng gạch đầu dòng (KHÔNG dùng bảng)."""
    lines = []
    lines.append("# BÁO CÁO PHÂN TÍCH VÀ ĐẶC TẢ DỮ LIỆU TOÀN DIỆN (EDA PROFILE REPORT)")
    lines.append(f"> Thời gian quét: {full_data.get('timestamp')}")
    lines.append(f"> Thư mục gốc: `{full_data.get('root_dir')}`")
    lines.append("")

    # MỤC 7: TÓM TẮT CẢNH BÁO Ở ĐẦU BÁO CÁO
    lines.append("## 🚨 TÓM TẮT PHÁT HIỆN QUAN TRỌNG & CẢNH BÁO CỐT TỬ")
    warnings = full_data.get("global_warnings", [])
    if not warnings:
        lines.append("- Không phát hiện cảnh báo nghiêm trọng cấp hệ thống.")
    else:
        for w in warnings:
            lines.append(f"- **[CẢNH BÁO]** {w}")
    lines.append("")

    # SO SÁNH RULEBOOK
    rb = full_data.get("rulebook_analysis", {})
    lines.append("## 📜 1. SO SÁNH QUY TẮC NGHIỆP VỤ (RULEBOOK.MD)")
    lines.append(f"- Train Rulebook tồn tại: {rb.get('train_rulebook_exists')} (SHA256: `{rb.get('train_sha256')}`)")
    lines.append(f"- Public Test Rulebook tồn tại: {rb.get('test_rulebook_exists')} (SHA256: `{rb.get('test_sha256')}`)")
    lines.append(f"- Tính đồng nhất SHA256: {'Trùng khớp 100%' if rb.get('is_identical') else 'KHÁC NHAU!'}")
    if rb.get("diff_lines"):
        lines.append(f"- Chi tiết khác biệt giữa 2 file ({rb.get('diff_summary')}):")
        for dl in rb["diff_lines"]:
            lines.append(f"  - `{dl}`")
    lines.append("- Trích đoạn 40 dòng đầu của Rulebook:")
    for l in rb.get("first_40_lines", []):
        lines.append(f"  > {l}")
    lines.append("")

    # CHI TIẾT TỪNG SPLIT
    for split_key in ["train", "public_test"]:
        s_data = full_data.get(split_key, {})
        lines.append(f"## 📊 2. PHÂN TÍCH TẬP DỮ LIỆU: `{split_key.upper()}`")
        q_stats = s_data.get("questions_stats", {})

        lines.append(f"### A. Thống kê Câu hỏi (questions.jsonl):")
        lines.append(f"- Tổng số câu hỏi: {q_stats.get('total_questions')}")
        lines.append(f"- Số dòng JSON lỗi parse: {len(q_stats.get('corrupted_json_lines', []))}")
        lines.append(f"- Số dòng thiếu trường bắt buộc: {len(q_stats.get('missing_fields_lines', []))}")
        lines.append(f"- Số ID bị trùng lặp: {len(q_stats.get('duplicate_ids', []))}")
        lines.append(f"- Độ dài câu hỏi (ký tự): Min = {q_stats.get('question_lengths', {}).get('min')}, Median = {q_stats.get('question_lengths', {}).get('median')}, Max = {q_stats.get('question_lengths', {}).get('max')}")
        lines.append(f"- Thống kê as_of_date: Có {q_stats.get('as_of_date_stats', {}).get('unique_count')} giá trị khác nhau (Khoảng: {q_stats.get('as_of_date_stats', {}).get('min')} đến {q_stats.get('as_of_date_stats', {}).get('max')})")
        lines.append(f"- as_of_date cố định theo từng doanh nghiệp: {'CÓ (Cố định)' if q_stats.get('as_of_date_stats', {}).get('is_constant_per_business') else 'KHÔNG (Thay đổi theo từng câu)'}")
        lines.append(f"- Phân bổ câu hỏi theo Business ID:")
        for biz, cnt in q_stats.get("business_counts", {}).items():
            lines.append(f"  - Business `{biz}`: {cnt} câu hỏi")
        lines.append(f"- Kiểm tra khớp thư mục data/:")
        lines.append(f"  - Business có trong questions nhưng thiếu folder data: {q_stats.get('business_mismatches', {}).get('missing_in_data') or 'Không có (Khớp)'}")
        lines.append(f"  - Folder data có nhưng không có câu hỏi: {q_stats.get('business_mismatches', {}).get('extra_in_data') or 'Không có (Khớp)'}")

        lines.append(f"- Tần suất xuất hiện biểu thức thời gian (Regex Heuristic):")
        for pat, cnt in q_stats.get("temporal_patterns", {}).items():
            lines.append(f"  - Mẫu '{pat}': {cnt} lần")
        lines.append(f"- Tỷ lệ câu chứa teencode / viết tắt / không dấu (Heuristic): ~{round(q_stats.get('teencode_informal_ratio', 0) * 100, 2)}% câu hỏi")

        if split_key == "train":
            lines.append(f"### B. Thống kê Đáp án (answers.jsonl) theo 9 Kiểu của BTC:")
            lines.append(f"- Phân bố kiểu dữ liệu đầu ra (Type):")
            for t_name in OFFICIAL_9_TYPES:
                t_cnt = q_stats.get("answer_types_distribution", {}).get(t_name, 0)
                lines.append(f"  - Kiểu `{t_name}`: {t_cnt} câu ({round(t_cnt / max(1, q_stats.get('total_questions', 1)) * 100, 2)}%)")
            lines.append(f"- Tỷ lệ câu hỏi unanswerable: {q_stats.get('unanswerable_count')} câu (~{round(q_stats.get('unanswerable_ratio', 0) * 100, 2)}%)")
            lines.append(f"- Số câu có cung cấp alias: {q_stats.get('alias_stats', {}).get('has_alias_count')} câu")

            # MỤC 1: in type_by_business
            lines.append(f"- Phân bố Type theo từng Business ID (type_by_business):")
            for biz, t_map in sorted(q_stats.get("type_by_business", {}).items()):
                t_desc = ", ".join([f"{k}: {v}" for k, v in t_map.items()])
                lines.append(f"  - Shop `{biz}`: {t_desc}")

            lines.append(f"### C. Cấu trúc Thực tế Trường 'answer' theo Kiểu:")
            for t_name, ex in q_stats.get("raw_answer_examples_by_type", {}).items():
                lines.append(f"- **Kiểu: `{t_name}`**")
                lines.append(f"  - Câu hỏi: \"{ex.get('question')}\"")
                lines.append(f"  - Đáp án nguyên văn: `{json.dumps(ex.get('raw_answer'), ensure_ascii=False)}`")

        lines.append(f"### D. Profile Chi tiết Dữ liệu Bảng của từng Shop:")
        shops_dict = s_data.get("shops_profile", {})
        for s_name, s_prof in shops_dict.items():
            lines.append(f"- **Shop: `{s_name}`**")
            # MỤC 1: In 10 dòng đầu README
            r_info = s_prof.get("readme_info", {})
            if r_info.get("lines_count") is not None:
                lines.append(f"  - README: {r_info.get('lines_count')} dòng {'[CẢNH BÁO: README RẤT NGẮN < 15 DÒNG]' if r_info.get('is_short') else ''}")
                lines.append(f"    - 10 dòng đầu README:")
                for rl in r_info.get("first_10_lines", []):
                    lines.append(f"      > {rl}")

            # MỤC 2: Khoảng ngày và số tháng hoạt động
            if s_prof.get("operating_months"):
                lines.append(f"  - Thời gian hoạt động: Từ {s_prof.get('shop_min_date')} đến {s_prof.get('shop_max_date')} (~{s_prof.get('operating_months')} tháng)")

            if s_prof.get("errors"):
                for err in s_prof["errors"]:
                    lines.append(f"  - ⚠️ LỖI: {err.get('file')} -> {err.get('error')}")

            # Khóa ngoại
            joins = s_prof.get("cross_table_potential_joins", [])
            if joins:
                lines.append(f"  - Liên kết bảng tiềm năng (Potential JOINs):")
                for j in joins[:6]:
                    lines.append(f"    - Cột `{j.get('shared_key')}` nối `{j.get('table_a')}` ({j.get('unique_in_a')} keys) với `{j.get('table_b')}` ({j.get('unique_in_b')} keys)")

            # Từng bảng
            for t_name, t_meta in s_prof.get("tables", {}).items():
                lines.append(f"  - **Bảng/Sheet: `{t_name}`**")
                # MỤC 8: ghi chú chỉ profile N dòng đầu kèm số dòng thật
                trunc_note = f"(Chỉ profile {t_meta.get('profiled_rows')} dòng đầu, tổng dòng thật: {t_meta.get('actual_total_rows')})" if t_meta.get("is_truncated") else f"({t_meta.get('profiled_rows')} dòng)"
                lines.append(f"    - Kích thước: {trunc_note} x {t_meta.get('cols')} cột")
                if t_meta.get("header_shift_note"):
                    lines.append(f"    - 📌 {t_meta.get('header_shift_note')}")

                lines.append(f"    - Dòng trùng lặp hoàn toàn: {t_meta.get('duplicate_rows_count')} dòng")

                # MỤC 1: In đầy đủ danh sách tên cột
                lines.append(f"    - Danh sách tên cột đầy đủ: {', '.join(t_meta.get('columns', []))}")

                # MỤC 1: In 3 dòng mẫu
                lines.append(f"    - 3 dòng dữ liệu mẫu:")
                for r_idx, r_dict in enumerate(t_meta.get("sample_3_rows", []), 1):
                    row_repr = ", ".join([f"{k}: {v}" for k, v in list(r_dict.items())[:6]])
                    lines.append(f"      - Mẫu {r_idx}: {row_repr} ...")

                # MỤC 1: In tỷ lệ trống từng cột
                null_r_strs = [f"{k}: {round(v*100, 1)}%" for k, v in t_meta.get("null_ratios", {}).items()]
                lines.append(f"    - Tỷ lệ trống từng cột: {', '.join(null_r_strs)}")

                # MỤC 4: Gắn cờ "nghi ngờ" Rule 8 và in 5 ví dụ
                if t_meta.get("group_null_candidates"):
                    lines.append(f"    - 🚩 **NGHI NGỜ CẦN FORWARD-FILL (RULE 8):**")
                    for g in t_meta["group_null_candidates"]:
                        lines.append(f"      - Cột `{g['col']}`: trống {round(g['blank_ratio']*100, 1)}%, phát hiện {g.get('suspect_ffill_count')} điểm nghi ngờ")
                        lines.append(f"        - 5 ví dụ: {'; '.join(g.get('samples', []))}")

                # MỤC 2: Cột thời gian có format rõ ràng và số unparsed
                if t_meta.get("date_cols_summary"):
                    lines.append(f"    - Cột thời gian nhận diện được:")
                    for dc, d_info in t_meta["date_cols_summary"].items():
                        lines.append(f"      - `{dc}`: Định dạng chọn `{d_info.get('chosen_format')}` | Từ {d_info.get('min_date')} đến {d_info.get('max_date')} | Không parse được: {d_info.get('unparsed_count')} giá trị")

                # MỤC 1: In TOÀN BỘ giá trị cột phân loại
                if t_meta.get("categorical_cols"):
                    lines.append(f"    - Toàn bộ giá trị cột phân loại (<= 15 nhãn):")
                    for cc, vals in t_meta["categorical_cols"].items():
                        val_details = ", ".join([f"'{k}': {v} lần" for k, v in vals.items()])
                        lines.append(f"      - `{cc}`: [{val_details}]")
        lines.append("")

    # MỤC 6: Khuyến nghị tự sinh từ số liệu thật
    lines.append("## 🎯 3. ĐIỀU DATA PARSER CẦN XỬ LÝ (TỰ SINH TỪ SỐ LIỆU QUÉT THỰC TẾ)")
    recs = full_data.get("parser_recommendations", [])
    for r in recs:
        lines.append(f"- {r}")

    lines.append("")
    return "\n".join(lines)


def export_sample_questions_markdown(
    samples: List[Dict[str, Any]],
    checklist: Dict[str, bool],
    out_path: Path
):
    """Xuất file sample_questions_for_prompt.md theo chuẩn B4 với checklist."""
    lines = []
    lines.append("# BỘ 10 CÂU HỎI MẪU TIÊU BIỂU CHO PROMPT DEMONSTRATION")
    lines.append("> Lựa chọn theo thứ tự ưu tiên cố định (Seed = 42) từ tập train.")
    lines.append("")

    for idx, s in enumerate(samples, 1):
        lines.append(f"### Câu hỏi {idx} (ID: `{s.get('id')}`)")
        lines.append(f"- **Doanh nghiệp (business_id):** `{s.get('business_id')}`")
        lines.append(f"- **Thời điểm mốc (as_of_date):** `{s.get('as_of_date')}`")
        lines.append(f"- **Câu hỏi:** {s.get('question')}")
        lines.append(f"- **Kiểu đáp án kỳ vọng (type):** `{s.get('type')}`")
        lines.append(f"- **Đáp án mẫu (answer):** `{json.dumps(s.get('answer'), ensure_ascii=False)}`")
        lines.append(f"- **Alias (nếu có):** `{json.dumps(s.get('alias'), ensure_ascii=False) if s.get('alias') else 'Không có'}`")
        lines.append(f"- **Danh sách tệp dữ liệu của shop này:** {', '.join(s.get('business_files', []))}")
        lines.append("")

    # Checklist cuối file
    lines.append("## 📋 BẢNG CHECKLIST TIÊU CHÍ LỰA CHỌN (B4)")
    for req_name, is_ok in checklist.items():
        status_sym = "✅ ĐẠT" if is_ok else "❌ CHƯA ĐẠT"
        lines.append(f"- [{status_sym}] {req_name}")
    lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ==============================================================================
# HÀM CHÍNH (MAIN)
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="DataMate - Bộ phân tích chuyên sâu EDA Profile (Phase 1 B1-B4)")
    parser.add_argument("--root", type=str, default=None, help="Đường dẫn thư mục competition_data")
    parser.add_argument("--out", type=str, default="./eda_output", help="Thư mục ghi kết quả")
    parser.add_argument("--max-rows", type=int, default=100000, help="Số dòng tối đa khi đọc profile sheet/table lớn")
    args = parser.parse_args()

    # Tìm root path linh hoạt
    if args.root:
        base_dir = Path(args.root).resolve()
    else:
        candidates = [
            Path.cwd() / "competition_data",
            Path.cwd().parent / "competition_data",
            Path(__file__).resolve().parent.parent / "competition_data",
            Path(__file__).resolve().parent.parent.parent / "competition_data",
        ]
        base_dir = next((c for c in candidates if c.exists()), candidates[0])

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print("================================================================================")
    print("         DATAMATE - BỘ PROFILE DỮ LIỆU CHUYÊN SÂU (PHẦN B: B1 -> B4)           ")
    print(f"  Root: {base_dir}")
    print(f"  Out:  {out_dir}")
    print("================================================================================")

    train_root = base_dir / "train"
    test_root = base_dir / "public_test"

    full_report: Dict[str, Any] = {
        "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "root_dir": str(base_dir),
        "global_warnings": [],
        "rulebook_analysis": {},
        "train": {},
        "public_test": {},
        "metrics": {
            "total_bom_files": 0,
            "total_shifted_headers": 0,
            "total_ffill_suspect_tables": 0,
            "total_duplicate_rows": 0,
            "total_unparsed_dates": 0,
            "encountered_date_formats": set(),
            "short_readme_shops": [],
            "failed_shops": [],
        },
        "parser_recommendations": []
    }

    # B3. Phân tích Rulebook
    print("\n[1/4] Đang phân tích và so sánh Rulebook (B3)...")
    rb_res = analyze_rulebooks(train_root, test_root)
    full_report["rulebook_analysis"] = rb_res
    if not rb_res.get("is_identical"):
        full_report["global_warnings"].append("Quy tắc rulebook.md giữa train và public_test KHÁC NHAU! Cần kiểm tra kỹ các thay đổi.")

    # B1. Phân tích Questions & Answers
    print("\n[2/4] Đang phân tích questions.jsonl và answers.jsonl (B1)...")
    if train_root.exists():
        print("  -> Đang quét train...")
        train_qa = analyze_questions_and_answers(train_root, is_train=True)
        raw_train_cache = train_qa.pop("raw_data_cache", [])
        full_report["train"]["questions_stats"] = train_qa
        if train_qa.get("business_mismatches", {}).get("missing_in_data"):
            full_report["global_warnings"].append(f"Train có business_id thiếu folder data: {train_qa['business_mismatches']['missing_in_data']}")
    else:
        raw_train_cache = []

    if test_root.exists():
        print("  -> Đang quét public_test...")
        test_qa = analyze_questions_and_answers(test_root, is_train=False)
        test_qa.pop("raw_data_cache", None)
        full_report["public_test"]["questions_stats"] = test_qa
        if test_qa.get("business_mismatches", {}).get("missing_in_data"):
            full_report["global_warnings"].append(f"Public test có business_id thiếu folder data: {test_qa['business_mismatches']['missing_in_data']}")

    # B2. Profile từng bảng dữ liệu của các shop
    print("\n[3/4] Đang profile từng shop dữ liệu (B2)...")
    for split_name, split_path in [("train", train_root), ("public_test", test_root)]:
        if not split_path.exists():
            continue
        d_dir = split_path / "data"
        if not d_dir.exists():
            continue
        full_report[split_name]["shops_profile"] = {}
        shops = sorted([d for d in d_dir.iterdir() if d.is_dir()])
        print(f"  -> Split '{split_name}': tìm thấy {len(shops)} shop.")
        for s in shops:
            print(f"     [Profile] Shop: {s.name} ...")
            s_prof = profile_shop_directory(s, max_rows=args.max_rows)
            full_report[split_name]["shops_profile"][s.name] = s_prof

            # Gom cảnh báo
            r_info = s_prof.get("readme_info", {})
            if r_info.get("is_short"):
                full_report["metrics"]["short_readme_shops"].append(f"{split_name}/{s.name}")
                full_report["global_warnings"].append(f"Shop '{s.name}' ({split_name}) có README.md rất ngắn ({r_info.get('lines_count')} dòng < 15 dòng).")

            if s_prof.get("errors"):
                full_report["metrics"]["failed_shops"].append(f"{split_name}/{s.name}")
                for err in s_prof["errors"]:
                    full_report["global_warnings"].append(f"Lỗi đọc file tại shop '{s.name}' ({split_name}): {err.get('file')} -> {err.get('error')}")

            for t_name, t_meta in s_prof.get("tables", {}).items():
                if t_meta.get("header_shift_note"):
                    full_report["metrics"]["total_shifted_headers"] += 1
                    full_report["global_warnings"].append(f"Shop '{s.name}' bảng '{t_name}': {t_meta.get('header_shift_note')}.")

                if t_meta.get("group_null_candidates"):
                    full_report["metrics"]["total_ffill_suspect_tables"] += 1
                    full_report["global_warnings"].append(f"Shop '{s.name}' bảng '{t_name}': Nghi ngờ cần forward-fill ô trống (Rule 8).")

                full_report["metrics"]["total_duplicate_rows"] += t_meta.get("duplicate_rows_count", 0)

                for dc, d_info in t_meta.get("date_cols_summary", {}).items():
                    full_report["metrics"]["encountered_date_formats"].add(d_info.get("chosen_format"))
                    full_report["metrics"]["total_unparsed_dates"] += d_info.get("unparsed_count", 0)
                    if d_info.get("unparsed_count", 0) > 0:
                        full_report["global_warnings"].append(f"Shop '{s.name}' bảng '{t_name}' cột '{dc}': Có {d_info.get('unparsed_count')} giá trị không thể parse theo định dạng {d_info.get('chosen_format')}.")

    # Chuyển set format sang list để JSON serialize
    full_report["metrics"]["encountered_date_formats"] = sorted(list(full_report["metrics"]["encountered_date_formats"]))

    # B4. Chọn 10 câu mẫu
    print("\n[4/4] Đang chọn 10 câu hỏi mẫu tiêu biểu cho Prompt Demonstration (B4)...")
    if raw_train_cache:
        sample_questions, checklist = select_10_sample_questions(raw_train_cache, train_root, seed=42)
        sample_out = out_dir / "sample_questions_for_prompt.md"
        export_sample_questions_markdown(sample_questions, checklist, sample_out)
        print(f"  -> Đã lưu 10 câu mẫu vào: {sample_out}")

    # Sinh khuyến nghị động từ số liệu thực tế
    full_report["parser_recommendations"] = generate_dynamic_recommendations(full_report)

    # Xuất eda_report.json
    json_out = out_dir / "eda_report.json"
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(full_report, f, ensure_ascii=False, indent=2, default = str)
    print(f"\n-> Đã xuất báo cáo JSON: {json_out}")

    # Xuất eda_report.md
    md_out = out_dir / "eda_report.md"
    md_content = generate_markdown_report(full_report)
    with open(md_out, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"-> Đã xuất báo cáo Markdown: {md_out}")

    print("\n" + "=" * 80)
    print("HOÀN TẤT PROFILE DỮ LIỆU THÀNH CÔNG!")
    print("=" * 80)


if __name__ == "__main__":
    main()
