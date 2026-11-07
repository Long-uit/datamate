"""
sqlite_mirror.py — Quản lý In-Memory SQLite Mirror, lập chỉ mục tự động và Caching theo shop.

Dựa trên nghiên cứu:
- SchemaGraphSQL & LinkAlign: Đánh chỉ mục trên các cột khóa (Mã đơn, Ngày, SKU, Khách hàng)
  giúp tăng tốc độ JOIN bảng lên hàng trăm lần, ngăn ngừa Timeout trong Sandbox.
- Tabular Deployment & Efficiency: In-memory caching theo business_id giúp giảm tải I/O đĩa,
  thời gian nạp và dựng CSDL < 1 giây/shop.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from datamate.ingestion_schema.loader import BusinessData

log = logging.getLogger(__name__)

# Các mẫu regex cột cần tạo Index tự động
INDEX_TARGET_PATTERNS = [
    (r"m[aã]\s*đ[oơ]n|m[aã]\s*phi[eế]u|s[oố]\s*hđ|order\s*id", "order"),
    (r"ng[aà]y|th[oờ]i\s*gian|date", "date"),
    (r"sku|m[aã]\s*h[aà]ng|m[aã]\s*sp|s[aả]n\s*ph[aẩ]m", "sku"),
    (r"kh[aá]ch\s*h[aà]ng|m[aã]\s*kh|m[aã]\s*kh[aá]ch|t[eê]n\s*kh[aá]ch", "customer"),
]

# Cache lưu trữ connection SQLite theo business_id
_SQLITE_MIRROR_CACHE: dict[str, sqlite3.Connection] = {}


def _normalize_name(text: str) -> str:
    """Chuẩn hóa tên để đối sánh regex."""
    text = unicodedata.normalize("NFC", str(text)).lower()
    return re.sub(r"\s+", " ", text).strip()


def _sanitize_ident(text: str) -> str:
    """Loại bỏ ký tự lạ khỏi định danh index SQL."""
    return re.sub(r"[^\w]", "_", text, flags=re.UNICODE).strip("_")


def create_indexes(con: sqlite3.Connection, table_id: str, columns: list[str]) -> list[str]:
    """
    Tự động dò và tạo index trên các cột khóa chính/ngoại và các cột lọc chính.
    Trả về danh sách tên các index đã tạo thành công.
    """
    created = []
    for col in columns:
        norm = _normalize_name(col)
        for pattern, label in INDEX_TARGET_PATTERNS:
            if re.search(pattern, norm):
                safe_col = _sanitize_ident(col)
                idx_name = f"idx_{table_id}_{label}_{safe_col}"
                try:
                    # Cột trong SQL được bọc dấu nháy kép để an toàn với dấu cách/tiếng Việt
                    con.execute(f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table_id}" ("{col}")')
                    created.append(idx_name)
                except Exception as exc:
                    log.debug("Không thể tạo index %s trên %s(%s): %s", idx_name, table_id, col, exc)
                break
    return created


def to_sqlite(business: BusinessData, clean: bool = False) -> sqlite3.Connection:
    """
    Tạo SQLite in-memory database từ BusinessData.
    - clean: Nếu True, áp dụng Rule 8 Cleaner (Group forward-fill + Deduplicate) trước khi nạp.
    - Tự động đánh index cho các bảng.
    - Tạo bảng _table_map ghi chú metadata.
    """
    if clean:
        from datamate.ingestion.cleaner import clean_business
        business = clean_business(business)

    con = sqlite3.connect(":memory:", check_same_thread=False)

    # Tạo bảng metadata _table_map
    con.execute("""
        CREATE TABLE IF NOT EXISTS _table_map (
            table_id TEXT,
            source_file TEXT,
            fixed_file_name TEXT,
            sheet_name TEXT,
            n_rows INTEGER
        )
    """)

    for ti in business.tables:
        if ti.df is None or ti.df.empty:
            continue

        try:
            ti.df.to_sql(
                ti.table_id,
                con,
                if_exists="replace",
                index=False,
                chunksize=5_000,
                method="multi",
            )
        except Exception:
            try:
                ti.df.to_sql(
                    ti.table_id,
                    con,
                    if_exists="replace",
                    index=False,
                    chunksize=2_000,
                )
            except Exception as exc:
                log.warning("to_sqlite: không thể nạp bảng %s: %s", ti.table_id, exc)
                continue

        # Đánh index tự động
        create_indexes(con, ti.table_id, ti.columns)

        # Tạo View theo tên bảng trực quan (t_base, t_name) để LLM có thể query trực tiếp bằng SQL
        t_base = Path(ti.fixed_file_name).stem
        t_name = f"{t_base}_{ti.sheet_name}" if ti.sheet_name and ti.sheet_name != "Sheet1" else t_base
        for alias in set([a for a in [t_base, t_name, ti.sheet_name] if a]):
            if alias and alias != ti.table_id:
                try:
                    con.execute(f'CREATE VIEW IF NOT EXISTS "{alias}" AS SELECT * FROM "{ti.table_id}"')
                except Exception:
                    pass

        # Lưu thông tin bảng vào _table_map
        con.execute(
            "INSERT INTO _table_map VALUES (?, ?, ?, ?, ?)",
            (
                ti.table_id,
                str(ti.source_file),
                ti.fixed_file_name,
                ti.sheet_name or "",
                ti.n_rows,
            ),
        )

    con.commit()
    return con


def get_sqlite_mirror(
    business: BusinessData,
    clean: bool = True,
    use_cache: bool = True,
) -> sqlite3.Connection:
    """
    Lấy SQLite Connection có cache theo business_id.
    Nếu đã có trong cache, trả về connection đã tạo sẵn (<1ms).
    """
    b_id = business.business_id
    if use_cache and b_id in _SQLITE_MIRROR_CACHE:
        return _SQLITE_MIRROR_CACHE[b_id]

    con = to_sqlite(business, clean=clean)
    if use_cache and b_id:
        _SQLITE_MIRROR_CACHE[b_id] = con

    return con


def clear_sqlite_cache() -> None:
    """Dọn dẹp toàn bộ SQLite connection trong cache giải phóng bộ nhớ."""
    global _SQLITE_MIRROR_CACHE
    for con in _SQLITE_MIRROR_CACHE.values():
        try:
            con.close()
        except Exception:
            pass
    _SQLITE_MIRROR_CACHE.clear()
