"""
schema.py — Re-export từ schema_profiler.py để đảm bảo tính tương thích ngược (Backward Compatibility).

Tất cả logic trích xuất hồ sơ lược đồ dữ liệu (cơ bản và nâng cao) đã được hợp nhất
vào Single Source of Truth: `datamate.ingestion_schema.schema_profiler`.
"""

from __future__ import annotations

from .schema_profiler import (
    describe_schema,
    profile_business_schema,
    profile_table_columns,
    infer_table_role,
)

__all__ = [
    "describe_schema",
    "profile_business_schema",
    "profile_table_columns",
    "infer_table_role",
]
