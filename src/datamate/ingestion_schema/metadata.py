"""
metadata.py — Trích xuất metadata tổng hợp của doanh nghiệp (BusinessMeta).

Đầu ra của module này là giao diện (interface) trực tiếp cung cấp cho Feasibility Gate:
- date_range: (min_date, max_date) xác định kỳ hoạt động thực tế của shop.
- tables: Danh sách các bảng dữ liệu.
- columns_by_table: Danh sách cột theo từng bảng.
- categories_by_col: Các giá trị phân loại (trạng thái đơn, hình thức thanh toán, nhóm khách, ngành hàng...).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Optional
import pandas as pd

from datamate.ingestion.loader import BusinessData
from datamate.types import BusinessMeta

log = logging.getLogger(__name__)

DATE_COL_PATTERNS = [
    r"ng[aà]y",
    r"th[oờ]i\s*gian",
    r"date",
    r"time",
]

CATEGORICAL_PATTERNS = [
    r"tr[aạ]ng\s*th[aá]i",
    r"t[iì]nh\s*tr[aạ]ng",
    r"status",
    r"h[iì]nh\s*th[uứ]c",
    r"thanh\s*to[aá]n",
    r"payment",
    r"nh[oó]m",
    r"lo[aạ]i",
    r"k[eê]nh",
    r"chi\s*nh[aá]nh",
    r"ng[aà]nh\s*h[aà]ng",
]


def _normalize_col(text: str) -> str:
    """Chuẩn hóa tên cột để kiểm tra regex."""
    text = unicodedata.normalize("NFC", str(text)).lower()
    return re.sub(r"\s+", " ", text).strip()


def is_date_column(col_name: str) -> bool:
    norm = _normalize_col(col_name)
    return any(re.search(pat, norm) for pat in DATE_COL_PATTERNS)


def is_categorical_column(col_name: str) -> bool:
    norm = _normalize_col(col_name)
    return any(re.search(pat, norm) for pat in CATEGORICAL_PATTERNS)


def extract_date_range(business: BusinessData) -> tuple[Optional[str], Optional[str]]:
    """
    Quét qua toàn bộ các bảng để tìm ngày sớm nhất (min_date) và muộn nhất (max_date)
    được ghi nhận trong dữ liệu của shop.
    """
    all_dates: list[pd.Timestamp] = []

    for ti in business.tables:
        if ti.df is None or ti.df.empty:
            continue

        for col in ti.df.columns:
            if is_date_column(col):
                s = ti.df[col].dropna().astype(str).str.strip().str[:10]
                # Thử parse datetime chuẩn ISO hoặc format thường gặp
                parsed = pd.to_datetime(s, errors="coerce", format="mixed")
                valid = parsed.dropna()
                if not valid.empty:
                    all_dates.append(valid.min())
                    all_dates.append(valid.max())

    if not all_dates:
        return (None, None)

    min_ts = min(all_dates)
    max_ts = max(all_dates)
    return (min_ts.strftime("%Y-%m-%d"), max_ts.strftime("%Y-%m-%d"))


def extract_categories(
    business: BusinessData,
    max_unique: int = 50,
) -> dict[str, list[str]]:
    """
    Trích xuất các giá trị phân loại chính trong các bảng.
    Khóa dạng 'table_id.column_name' hoặc 'column_name'.
    """
    categories: dict[str, list[str]] = {}

    for ti in business.tables:
        if ti.df is None or ti.df.empty:
            continue

        for col in ti.df.columns:
            if is_categorical_column(col):
                uniques = (
                    ti.df[col]
                    .dropna()
                    .astype(str)
                    .str.strip()
                    .unique()
                    .tolist()
                )
                # Chỉ lấy nếu số lượng giá trị không quá lớn (chuẩn phân loại)
                clean_uniques = [u for u in uniques if u and u.lower() not in ("nan", "none", "null")]
                if 0 < len(clean_uniques) <= max_unique:
                    key = f"{ti.table_id}.{col}"
                    categories[key] = clean_uniques
                    # Cũng lưu khóa ngắn nếu chưa có
                    if col not in categories:
                        categories[col] = clean_uniques

    return categories


def get_metadata(business: BusinessData) -> BusinessMeta:
    """
    Tạo BusinessMeta tổng hợp từ BusinessData.
    Interface chính cho Feasibility Gate và các module downstream.
    """
    tables = [ti.table_id for ti in business.tables]
    columns_by_table: dict[str, list[str]] = {}

    for ti in business.tables:
        if ti.df is not None:
            columns_by_table[ti.table_id] = list(ti.df.columns)
        else:
            columns_by_table[ti.table_id] = list(ti.columns)

    date_range = extract_date_range(business)
    categories_by_col = extract_categories(business)

    return BusinessMeta(
        business_id=business.business_id,
        date_range=date_range,
        tables=tables,
        columns_by_table=columns_by_table,
        categories_by_col=categories_by_col,
    )
