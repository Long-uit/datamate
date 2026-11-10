"""
types.py — Định nghĩa các kiểu dữ liệu dùng chung trong hệ thống DataMate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class TimeWindow:
    """Cửa sổ thời gian được giải mã từ câu hỏi và as_of_date."""
    start_date: str          # YYYY-MM-DD
    end_date: str            # YYYY-MM-DD
    label: str               # e.g., "today", "this_week", "last_week", "tet_2025"
    description: str = ""    # Mô tả ngữ nghĩa (tiếng Việt hoặc Anh)


@dataclass
class BusinessMeta:
    """Thông tin metadata tổng hợp của một doanh nghiệp (shop)."""
    business_id: str
    date_range: tuple[Optional[str], Optional[str]] = (None, None)  # (min_date, max_date)
    tables: list[str] = field(default_factory=list)
    columns_by_table: dict[str, list[str]] = field(default_factory=dict)
    categories_by_col: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class BusinessContext:
    """Ngữ cảnh nghiệp vụ của một shop phục vụ suy luận LLM và Feasibility Gate."""
    business_id: str
    meta: BusinessMeta
    rulebook_text: str = ""
    readme_text: str = ""


@dataclass
class GateDecision:
    """Quyết định từ chối / chấp nhận của Feasibility Gate."""
    feasible: bool
    reason: Optional[str] = None
    confidence: float = 1.0


@dataclass
class EntityMatch:
    """Kết quả đối sánh thực thể (Entity Linking)."""
    query_term: str          # Chuỗi tìm kiếm trong câu hỏi (ví dụ: "cf sữa")
    matched_value: str       # Chuỗi thực tế trong DB (ví dụ: "Cà phê sữa đá 330ml")
    entity_type: str         # "sku", "product", "customer", "category"
    score: float             # Điểm tương đồng 0.0 -> 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    source_table: str = ""
    source_col: str = ""

    def __post_init__(self):
        if not self.source_table and self.metadata:
            self.source_table = str(self.metadata.get("source_table", ""))
        if not self.source_col and self.metadata:
            self.source_col = str(self.metadata.get("source_col", ""))


@dataclass
class Candidate:
    """Ứng viên thực thể phục vụ xếp hạng và lọc."""
    value: str
    norm_value: str
    entity_type: str
    source_table: str
    source_col: str
    row_context: dict[str, Any] = field(default_factory=dict)
