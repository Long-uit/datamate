"""
paraphrase.py — Sinh biến thể câu hỏi tiếng Việt (Teencode, viết tắt, không dấu, văn phong hội thoại).

Giúp mô hình học sâu học được độ trơ (robustness) trước các kiểu hành văn đa dạng của người dùng.
"""

from __future__ import annotations

import random
import re
import unicodedata

# Từ điển viết tắt / teencode áp dụng khi paraphrase
SLANG_MAP: dict[str, list[str]] = {
    "doanh thu": ["dthu", "tiền bán", "doanh số", "d/thu"],
    "hôm nay": ["hnay", "nay", "h.nay"],
    "hôm qua": ["hqua", "qua"],
    "bao nhiêu": ["bnhiu", "bn", "mấy", "nhiêu"],
    "tháng": ["thg", "t"],
    "tuần này": ["tuần nì", "tuan nay"],
    "sản phẩm": ["sp", "mặt hàng", "món"],
    "khách hàng": ["kh", "khách", "người mua"],
    "đơn hàng": ["đơn", "đh", "bill"],
    "số lượng": ["sl", "slg"],
}

# Tiền tố / hậu tố văn phong đời thường
PREFIXES = [
    "Cho mình hỏi ",
    "Shop ơi, ",
    "Tính giúp tôi ",
    "Thống kê xem ",
    "Kiểm tra giúp em ",
    "Xem hộ mình ",
    "",
]

SUFFIXES = [
    " với ạ?",
    " nhé.",
    " vậy?",
    " nhỉ?",
    "?",
    "",
]


def remove_vietnamese_accents(text: str) -> str:
    """Khử toàn bộ dấu tiếng Việt."""
    s = unicodedata.normalize("NFD", text)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "D")
    return s


def replace_slang(text: str, prob: float = 0.5) -> str:
    """Thay thế ngẫu nhiên các từ phổ biến bằng teencode/viết tắt."""
    res = text
    for word, slangs in SLANG_MAP.items():
        if word in res.lower() and random.random() < prob:
            choice = random.choice(slangs)
            # Thay thế không phân biệt hoa thường
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            res = pattern.sub(choice, res, count=1)
    return res


def paraphrase_question(question: str, num_variants: int = 3) -> list[str]:
    """Sinh ra num_variants biến thể câu hỏi khác nhau từ một câu hỏi gốc."""
    variants: set[str] = set()
    cleaned = question.strip().rstrip("?.,")

    # 1. Biến thể teencode / viết tắt
    v1 = replace_slang(cleaned, prob=0.8)
    variants.add(v1 + "?")

    # 2. Biến thể không dấu
    v2 = remove_vietnamese_accents(cleaned)
    variants.add(v2)

    # 3. Biến thể phong cách giao tiếp
    prefix = random.choice([p for p in PREFIXES if p])
    suffix = random.choice([s for s in SUFFIXES if s])
    v3 = f"{prefix}{cleaned.lower()}{suffix}"
    variants.add(v3)

    # 4. Biến thể kết hợp teencode + không dấu
    v4 = remove_vietnamese_accents(replace_slang(cleaned, prob=0.9))
    variants.add(v4)

    # Lọc bỏ câu trùng với câu gốc và giới hạn số lượng
    result = [v for v in variants if v.strip().lower() != question.strip().lower()]
    return result[:num_variants]

