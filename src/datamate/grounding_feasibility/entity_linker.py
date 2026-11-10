"""
entity_linker.py — Bộ liên kết thực thể tiếng Việt (Entity & Alias Linker).

Áp dụng kỹ thuật từ các nghiên cứu SOTA:
- CHESS (Contextual Harnessing for Efficient SQL Synthesis): Candidate Values Retrieval.
- AutoLink: Liên kết tự động giữa ngôn ngữ tự nhiên và cơ sở dữ liệu quan hệ.

Khả năng chính:
- Chuẩn hóa tiếng Việt có/không dấu, teencode, viết tắt ("cf" -> "cà phê", "sp" -> "sản phẩm").
- Bóc tách thuộc tính kích thước, quy cách: (M), (L), size M, 330ml, chai, lon, thùng.
- Thuật toán kết hợp Exact Match có ranh giới từ (Word Boundary) + N-gram Token Overlap + Sliding Window Phrase Similarity.
- Khắc phục hiện tượng pha loãng điểm số (Diluted Similarity) khi so sánh với câu hỏi dài và loại bỏ hoàn toàn việc khớp nhầm chuỗi con.
- Giúp Feasibility Gate phát hiện câu hỏi về thực thể không tồn tại trong shop.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
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
    "dt": "doanh thu",
    "dso": "doanh số",
    "sl": "số lượng",
    "slg": "số lượng",
    "đh": "đơn hàng",
    "dh": "đơn hàng",
    "sz": "size",
    "hnay": "hôm nay",
    "hqua": "hôm qua",
    "thg": "tháng",
    "bnhiu": "bao nhiêu",
    "bnhieu": "bao nhiêu",
    "bnhiêu": "bao nhiêu",
    "bn": "bao nhiêu",
    "trc": "trước",
    "dc": "được",
    "đc": "được",
    "ko": "không",
    "k": "không",
    "nv": "nhân viên",
    "ncc": "nhà cung cấp",
    "hd": "hóa đơn",
    "hđ": "hóa đơn",
    "ct": "chi tiết",
    "ck": "chiết khấu",
    "km": "khuyến mãi",
    "tt": "thành tiền",
    "nowj": "nợ",
    "cuwar": "cửa",
    "nhaf": "nhà",
    "vaayj": "vậy",
    "đươc": "được",
}

# Các cột tiềm năng chứa thực thể (Mở rộng toàn diện các trường nghiệp vụ)
ENTITY_COL_MAP = [
    ("product", [
        r"s[aả]n\s*ph[aẩ]m",
        r"t[eê]n\s*h[aà]ng",
        r"t[eê]n\s*m[aặ]t\s*h[aà]ng",
        r"m[aặ]t\s*h[aà]ng",
        r"thu[oố]c",
        r"sku",
        r"m[aã]\s*h[aà]ng",
        r"m[aã]\s*sp",
    ]),
    ("active_ingredient", [
        r"ho[aạ]t\s*ch[aấ]t",
        r"th[aà]nh\s*ph[aầ]n",
        r"active",
        r"hoatchat",
    ]),
    ("category", [
        r"nh[oó]m\s*h[aà]ng",
        r"danh\s*m[uụ]c",
        r"lo[aạ]i\s*h[aà]ng",
        r"ng[aà]nh\s*h[aà]ng",
        r"nh[oó]m\s*sp",
        r"category",
    ]),
    ("customer", [
        r"kh[aá]ch\s*h[aà]ng",
        r"t[eê]n\s*kh[aá]ch",
        r"m[aã]\s*kh",
        r"m[aã]\s*kh[aá]ch",
    ]),
    ("staff", [
        r"nh[aâ]n\s*vi[eê]n",
        r"ng[uư][oờ]i\s*b[aá]n",
        r"thu\s*ng[aâ]n",
        r"d[uư][oợ]c\s*s[iĩ]",
        r"staff",
    ]),
    ("supplier", [
        r"nh[aà]\s*cung\s*c[aấ]p",
        r"ncc",
        r"nh[aà]\s*ph[aâ]n\s*ph[oố]i",
        r"supplier",
    ]),
    ("channel", [
        r"k[eê]nh\s*b[aá]n",
        r"ngu[oồ]n\s*đ[oơ]n",
        r"k[eê]nh",
        r"channel",
    ]),
]

PRODUCT_COL_KEYWORDS = ENTITY_COL_MAP[0][1]
CUSTOMER_COL_KEYWORDS = ENTITY_COL_MAP[3][1]


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
    expanded = [VIETNAMESE_ABBREVIATIONS.get(t.lower().strip(".,!?:;\"'()[]{}"), t) for t in tokens]
    return " ".join(expanded)


def explain_and_expand_abbreviations(text: str) -> tuple[str, dict[str, str]]:
    """
    Mở rộng các từ viết tắt và ghi lại chi tiết các từ trước/sau đã được chuyển đổi.
    Trả về (câu_mới, {từ_viết_tắt: dạng_chuẩn}).
    """
    tokens = text.split()
    replaced = {}
    expanded = []
    for t in tokens:
        clean_t = t.lower().strip(".,!?:;\"'()[]{}")
        if clean_t in VIETNAMESE_ABBREVIATIONS:
            full_word = VIETNAMESE_ABBREVIATIONS[clean_t]
            replaced[t] = full_word
            expanded.append(full_word)
        else:
            expanded.append(t)
    return " ".join(expanded), replaced


def jaro_winkler_similarity(s1: str, s2: str) -> float:
    """Tính độ tương đồng chuỗi bằng difflib.SequenceMatcher (chuẩn hóa 0.0 -> 1.0)."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    return difflib.SequenceMatcher(None, s1, s2).ratio()


def best_phrase_similarity(target: str, text: str) -> float:
    """
    Tính độ tương đồng chuỗi tối ưu theo cửa sổ trượt (Sliding Window N-gram).
    Khắc phục triệt để hiện tượng pha loãng điểm số (Diluted Similarity) khi so sánh
    tên thực thể ngắn với toàn bộ câu hỏi dài của người dùng.
    """
    t_words = target.split()
    q_words = text.split()
    k = len(t_words)
    m = len(q_words)
    if not t_words or not q_words:
        return 0.0
    if m <= k:
        return difflib.SequenceMatcher(None, target, text).ratio()

    best_sim = 0.0
    min_window = max(1, k - 1)
    max_window = min(m + 1, k + 3)
    for l in range(min_window, max_window):
        for i in range(m - l + 1):
            window = " ".join(q_words[i : i + l])
            s = difflib.SequenceMatcher(None, target, window).ratio()
            if s > best_sim:
                best_sim = s
                if best_sim >= 0.98:
                    return best_sim
    return best_sim


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

            # Xác định loại thực thể qua ENTITY_COL_MAP mở rộng
            entity_type = None
            for e_type, patterns in ENTITY_COL_MAP:
                if any(re.search(pat, norm_col) for pat in patterns):
                    entity_type = e_type
                    break

            if entity_type:
                tbl_label = Path(ti.fixed_file_name).stem if hasattr(ti, "fixed_file_name") and ti.fixed_file_name else ti.table_id
                unique_vals = ti.df[col].dropna().unique()
                
                # Trích xuất các cột thông tin phụ trợ quan trọng (Mã, ĐVT, Quy đổi, Hoạt chất...)
                is_catalog_size = len(ti.df) <= 1000
                key_cols = [
                    c for c in ti.columns if c != col and any(
                        k in str(c).lower() for k in [
                            "mã", "code", "sku", "id", "quy cách", "đơn vị", "dvt", "đvt", 
                            "quy đổi", "quydoi", "hoạt chất", "hoatchat", "thành phần", 
                            "nhóm", "loại", "giá", "danh mục"
                        ]
                    )
                ]

                for val in unique_vals:
                    val_str = str(val).strip()
                    if not val_str or len(val_str) < 2:
                        continue
                    key = (entity_type, val_str)
                    if key not in seen:
                        seen.add(key)
                        row_ctx = {}
                        if is_catalog_size and key_cols:
                            matched_rows = ti.df[ti.df[col].astype(str).str.strip() == val_str]
                            if not matched_rows.empty:
                                first_row = matched_rows.iloc[0]
                                for kc in key_cols[:5]:
                                    v_kc = first_row.get(kc)
                                    if v_kc is not None and not pd.isna(v_kc):
                                        s_vkc = str(v_kc).strip()
                                        if s_vkc and s_vkc.lower() not in ("nan", "none", "null", ""):
                                            row_ctx[kc] = s_vkc

                        candidates.append(Candidate(
                            value=val_str,
                            norm_value=normalize_entity_text(val_str),
                            entity_type=entity_type,
                            source_table=tbl_label,
                            source_col=col,
                            row_context=row_ctx,
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
    - Kết hợp Exact Word Boundary Match, Token Overlap và Sliding Window Phrase Similarity.
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

        # 1. Exact Word-Boundary Match (Ưu tiên cao nhất: ngăn chặn triệt để false positive chuỗi con)
        pattern_norm = r"(?<!\w)" + re.escape(target_norm) + r"(?!\w)"
        pattern_unacc = r"(?<!\w)" + re.escape(target_unaccented) + r"(?!\w)"

        if re.search(pattern_norm, expanded_q):
            score = 1.0
            matched_term = target_norm
        elif len(target_unaccented) > 2 and re.search(pattern_unacc, unaccented_q):
            score = 0.95
            matched_term = target_unaccented
        else:
            # 2. Token Overlap & Sliding Window Phrase Similarity (Chống pha loãng câu dài)
            overlap = token_overlap_score(target_norm, expanded_q)
            overlap_unaccented = token_overlap_score(target_unaccented, unaccented_q)
            best_overlap = max(overlap, overlap_unaccented)

            if best_overlap >= 0.5:
                sim = best_phrase_similarity(target_unaccented, unaccented_q)
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
                    "row_context": getattr(cand, "row_context", {}),
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
