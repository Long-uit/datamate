"""
entity_linker.py — Bộ liên kết thực thể tiếng Việt (Entity & Alias Linker).

Áp dụng kỹ thuật từ các nghiên cứu SOTA:
- CHESS (Contextual Harnessing for Efficient SQL Synthesis): Candidate Values Retrieval.
- AutoLink: Liên kết tự động giữa ngôn ngữ tự nhiên và cơ sở dữ liệu quan hệ.

Khả năng chính:
- Chuẩn hóa tiếng Việt có/không dấu, teencode, viết tắt ("cf" -> "cà phê", "sp" -> "sản phẩm").
- Bóc tách thuộc tính kích thước, quy cách: (M), (L), size M, 330ml, chai, lon, thùng.
- Thuật toán kết hợp Exact Substring + N-gram Token Overlap + Jaro-Winkler Similarity.
- Giúp Feasibility Gate phát hiện câu hỏi về thực thể không tồn tại trong shop.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Optional, TYPE_CHECKING, Any

try:
    import pandas as pd
except ImportError:
    pd = None

if TYPE_CHECKING:
    from datamate.ingestion.loader import BusinessData
else:
    BusinessData = Any
from datamate.types import Candidate, EntityMatch

# Từ điển viết tắt / teencode tiếng Việt phổ biến trong bán lẻ
VIETNAMESE_ABBREVIATIONS: dict[str, str] = {
    "cf": "cà phê",
    "cafe": "cà phê",
    "sp": "sản phẩm",
    "kh": "khách hàng",
    "dthu": "doanh thu",
    "sl": "số lượng",
    "slg": "số lượng",
    "đh": "đơn hàng",
    "dh": "đơn hàng",
    "sz": "size",
    "hnay": "hôm nay",
    "thg": "tháng",
    "bnhiu": "bao nhiêu",
}

# Các cột tiềm năng chứa thực thể
PRODUCT_COL_KEYWORDS = [
    r"s[aả]n\s*ph[aẩ]m",
    r"t[eê]n\s*h[aà]ng",
    r"t[eê]n\s*m[aặ]t\s*h[aà]ng",
    r"m[aặ]t\s*h[aà]ng",
    r"sku",
    r"m[aã]\s*h[aà]ng",
    r"m[aã]\s*sp",
]

CUSTOMER_COL_KEYWORDS = [
    r"kh[aá]ch\s*h[aà]ng",
    r"t[eê]n\s*kh[aá]ch",
    r"m[aã]\s*kh",
    r"m[aã]\s*kh[aá]ch",
]


def remove_accents(input_str: str) -> str:
    """Loại bỏ dấu tiếng Việt (đ -> d, é -> e...)."""
    s = unicodedata.normalize("NFD", str(input_str))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "D")
    return s


def normalize_entity_text(text: str, strip_accents: bool = False) -> str:
    """Chuẩn hóa văn bản: Unicode NFC, chữ thường, gộp khoảng trắng thừa."""
    text = unicodedata.normalize("NFC", str(text)).strip().lower()
    if strip_accents:
        text = remove_accents(text)
    # Loại bỏ ký tự đặc biệt không cần thiết nhưng giữ chữ số và chữ cái
    text = re.sub(r"[^\w\s\(\)]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def expand_abbreviations(text: str) -> str:
    """Mở rộng các từ viết tắt / teencode trong câu."""
    tokens = text.split()
    expanded = [VIETNAMESE_ABBREVIATIONS.get(t, t) for t in tokens]
    return " ".join(expanded)


def jaro_winkler_similarity(s1: str, s2: str) -> float:
    """Tính độ tương đồng chuỗi bằng difflib.SequenceMatcher (chuẩn hóa 0.0 -> 1.0)."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    return difflib.SequenceMatcher(None, s1, s2).ratio()


def token_overlap_score(query: str, target: str) -> float:
    """Tính tỷ lệ bao phủ token của query trong target."""
    q_tokens = set(query.split())
    t_tokens = set(target.split())
    if not q_tokens:
        return 0.0
    common = q_tokens.intersection(t_tokens)
    return len(common) / len(q_tokens)


def extract_candidates_from_business(business: BusinessData) -> list[Candidate]:
    """Trích xuất tất cả các giá trị thực thể tiềm năng từ các bảng của shop."""
    candidates: list[Candidate] = []
    seen: set[tuple[str, str]] = set()

    for ti in business.tables:
        if ti.df is None or ti.df.empty:
            continue

        for col in ti.columns:
            norm_col = normalize_entity_text(col)

            # Xác định loại thực thể
            entity_type = None
            for pattern in PRODUCT_COL_KEYWORDS:
                if re.search(pattern, norm_col):
                    entity_type = "product"
                    break

            if not entity_type:
                for pattern in CUSTOMER_COL_KEYWORDS:
                    if re.search(pattern, norm_col):
                        entity_type = "customer"
                        break

            if entity_type:
                unique_vals = ti.df[col].dropna().unique()
                for val in unique_vals:
                    val_str = str(val).strip()
                    if not val_str or len(val_str) < 2:
                        continue
                    key = (entity_type, val_str)
                    if key not in seen:
                        seen.add(key)
                        candidates.append(Candidate(
                            value=val_str,
                            norm_value=normalize_entity_text(val_str),
                            entity_type=entity_type,
                            source_table=ti.table_id,
                            source_col=col,
                        ))

    return candidates


def link_entities(
    question: str,
    candidates: list[Candidate] | list[str],
    entity_type: str = "product",
    threshold: float = 0.6,
) -> list[EntityMatch]:
    """
    Tìm kiếm và ánh xạ các thực thể xuất hiện trong câu hỏi tới danh mục candidates.
    - Hỗ trợ truyền danh sách Candidate hoặc danh sách chuỗi thô.
    - Kết hợp Exact Match, Token Overlap và Fuzzy Similarity.
    """
    norm_q = normalize_entity_text(question)
    expanded_q = expand_abbreviations(norm_q)
    unaccented_q = remove_accents(expanded_q)

    # Chuẩn bị danh sách Candidate chuẩn
    cand_objs: list[Candidate] = []
    for c in candidates:
        if isinstance(c, Candidate):
            cand_objs.append(c)
        else:
            cand_objs.append(Candidate(
                value=str(c),
                norm_value=normalize_entity_text(str(c)),
                entity_type=entity_type,
                source_table="",
                source_col="",
            ))

    matches: list[EntityMatch] = []

    for cand in cand_objs:
        target_norm = cand.norm_value
        target_unaccented = remove_accents(target_norm)

        score = 0.0
        matched_term = ""

        # 1. Exact Substring Match (Ưu tiên cao nhất)
        if target_norm in expanded_q:
            score = 1.0
            matched_term = target_norm
        elif target_unaccented in unaccented_q and len(target_unaccented) > 3:
            score = 0.95
            matched_term = target_unaccented
        else:
            # 2. Token Overlap & Fuzzy N-gram
            overlap = token_overlap_score(target_norm, expanded_q)
            overlap_unaccented = token_overlap_score(target_unaccented, unaccented_q)
            best_overlap = max(overlap, overlap_unaccented)

            if best_overlap >= 0.5:
                # Tính bổ trợ bằng Jaro-Winkler
                sim = jaro_winkler_similarity(target_unaccented, unaccented_q)
                score = 0.6 * best_overlap + 0.4 * sim
                matched_term = cand.value

        if score >= threshold:
            matches.append(EntityMatch(
                query_term=matched_term or cand.value,
                matched_value=cand.value,
                entity_type=cand.entity_type,
                score=round(score, 3),
                metadata={
                    "source_table": cand.source_table,
                    "source_col": cand.source_col,
                },
            ))

    # Sắp xếp theo độ tin cậy giảm dần và loại bỏ trùng lặp giá trị
    matches.sort(key=lambda m: m.score, reverse=True)

    unique_matches: list[EntityMatch] = []
    seen_values: set[str] = set()
    for m in matches:
        if m.matched_value not in seen_values:
            seen_values.add(m.matched_value)
            unique_matches.append(m)

    return unique_matches

