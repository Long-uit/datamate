"""
schema_profiler.py — Bộ trích xuất hồ sơ dữ liệu chi tiết (Rich Schema Profiler) cho DataMate.

Cung cấp thông tin phong phú về từng bảng và cột:
- Số dòng thực tế của bảng.
- Kiểu dữ liệu ngữ nghĩa của cột: date (kèm min date -> max date), categorical (kèm toàn bộ giá trị nếu <= 6),
  numeric/currency (kèm ví dụ), string/ID (kèm ví dụ).
- Chống phân loại nhầm trên bảng ít dòng (small-sample protection).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, List, Optional
import pandas as pd
import numpy as np

from datamate.ingestion.loader import BusinessData, TableInfo


def _normalize_text(s: Any) -> str:
    if s is None or pd.isna(s):
        return ""
    text = unicodedata.normalize("NFC", str(s)).strip()
    return re.sub(r"\s+", " ", text)


def profile_table_columns(df: pd.DataFrame, max_cols: int = 25) -> List[str]:
    """Phân tích và tạo mô tả giàu ngữ nghĩa cho từng cột trong bảng."""
    col_previews: List[str] = []
    
    for c in df.columns[:max_cols]:
        col_name = str(c)
        c_low = col_name.lower()
        non_null = df[c].dropna()
        n_unique = non_null.nunique()
        n_rows = len(df)
        
        if non_null.empty:
            col_previews.append(f"'{col_name}' (rỗng)")
            continue

        # 1. Nhận diện cột ngày tháng
        is_date_col = any(k in c_low for k in ["ngày", "date", "ngaylap", "thời gian", "thoigian", "hsd", "hạn dùng"])
        if is_date_col:
            try:
                from datamate.execution.helpers import clean_date
                dt_series = clean_date(non_null).dropna()
                if not dt_series.empty:
                    min_d = dt_series.min().strftime("%Y-%m-%d")
                    max_d = dt_series.max().strftime("%Y-%m-%d")
                    col_previews.append(f"'{col_name}' (ngày: '{min_d}' -> '{max_d}')")
                    continue
            except Exception:
                pass

        # 2. Nhận diện cột tiền tệ / số lượng (kiểm tra trước phân loại để tránh nhầm số thành categorical)
        is_num_keyword = any(k in c_low for k in ["tiền", "giá", "số lượng", "soluong", "doanh thu", "chiết khấu", "thuế", "vat", "nợ", "tồn", "cần trả", "đơn giá"])
        sample_val = _normalize_text(non_null.iloc[0])
        if len(sample_val) > 22:
            sample_val = sample_val[:19] + "..."

        if is_num_keyword:
            col_previews.append(f"'{col_name}' (số/tiền, vd: '{sample_val}')")
            continue

        # 3. Nhận diện cột phân loại (categorical):
        # Chỉ đánh nhãn phân loại khi tên cột có ngữ nghĩa phân loại HOẶC khi bảng có đủ dòng (>= 15 dòng) và n_unique <= 6
        is_cat_keyword = any(k in c_low for k in ["trạng thái", "status", "tình trạng", "kênh", "channel", "loại", "hình thức", "phương thức", "nhóm", "phân loại", "đơn vị", "đvt", "dvt", "gender", "giới tính"])
        is_valid_categorical = is_cat_keyword or (n_rows >= 15 and 1 <= n_unique <= 6)
        
        if is_valid_categorical and 1 <= n_unique <= 6:
            unique_vals = [_normalize_text(v) for v in non_null.unique() if _normalize_text(v)]
            unique_vals = [v for v in unique_vals if v.lower() not in ("nan", "none", "null")]
            if unique_vals:
                vals_str = ", ".join(f"'{v}'" for v in unique_vals[:6])
                col_previews.append(f"'{col_name}' (phân loại: [{vals_str}])")
                continue

        # 4. Mặc định là chuỗi / mã
        col_previews.append(f"'{col_name}' (vd: '{sample_val}')")

    return col_previews


def profile_business_schema(business: BusinessData, max_cols: int = 25) -> str:
    """Tạo bản tóm tắt schema phong phú (Rich Schema) cho toàn bộ shop."""
    schema_lines: List[str] = []

    for ti in business.tables:
        t_base = Path(ti.fixed_file_name).stem if hasattr(ti, "fixed_file_name") and ti.fixed_file_name else ti.table_id
        t_name = f"{t_base}_{ti.sheet_name}" if ti.sheet_name and ti.sheet_name != "Sheet1" else t_base

        cols_desc = profile_table_columns(ti.df, max_cols=max_cols)
        extra_note = f", ... và {len(ti.columns) - max_cols} cột khác" if len(ti.columns) > max_cols else ""
        
        schema_lines.append(
            f"- Bảng '{t_name}' ({ti.n_rows} dòng):\n"
            f"  Cột ({len(ti.columns)}): [{', '.join(cols_desc)}{extra_note}]"
        )

    return "\n".join(schema_lines)
