"""
normalizer_teencode.py — Bộ chuẩn hóa từ viết tắt, teencode và lỗi gõ phím tiếng Việt.

Tích hợp toàn diện:
1. Nạp từ điển chuẩn hóa JSON (`resources/teencode_dictionary.json`) với cơ chế cache trong bộ nhớ.
2. Hỗ trợ phân tầng miền ngữ cảnh (Domain-Aware):
   - 'retail': Ưu tiên ngữ nghĩa bán lẻ, thương mại điện tử, kế toán (bn -> bao nhiêu, ck -> chiết khấu/chuyển khoản, kh -> khách hàng).
   - 'general': Ngữ cảnh giao tiếp xã hội đời thường (bn -> bạn, ck -> chồng, kh -> không).
3. Cơ chế khử đa nghĩa theo ngữ cảnh cục bộ (Contextual Disambiguation):
   - Tự động kiểm tra các token trước/sau để phân biệt chính xác các từ viết tắt có nhiều nghĩa.
4. Xử lý triệt để các dạng:
   - Kéo dài nguyên âm biểu thị cảm xúc: 'điiiiiii' -> 'đi', 'nhiềuuu' -> 'nhiều'.
   - Rút gọn đuôi 'ng' thành 'g': 'khôg' -> 'không', 'nhữg' -> 'những', 'đag' -> 'đang'.
   - Lỗi kẹt bộ gõ Telex: 'thangs' -> 'tháng', 'ngayf' -> 'ngày', 'dduwowcj' -> 'được'.
   - Viết liền số tháng: 'th5/2025' -> 'tháng 5/2025'.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import unicodedata

_TEENCODE_DICT_CACHE: Optional[Dict[str, Any]] = None


def find_teencode_dictionary_path() -> Optional[Path]:
    """Tìm đường dẫn tệp teencode_dictionary.json trong dự án."""
    cwd = Path.cwd()
    candidates = [
        cwd / "resources" / "teencode_dictionary.json",
        cwd.parent / "resources" / "teencode_dictionary.json",
        Path(__file__).resolve().parent.parent.parent.parent / "resources" / "teencode_dictionary.json",
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c.resolve()
    return None


def get_teencode_dictionary(force_reload: bool = False) -> Dict[str, Any]:
    """Nạp từ điển teencode_dictionary.json và cache vào RAM."""
    global _TEENCODE_DICT_CACHE
    if _TEENCODE_DICT_CACHE is not None and not force_reload:
        return _TEENCODE_DICT_CACHE

    p = find_teencode_dictionary_path()
    if p and p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                _TEENCODE_DICT_CACHE = json.load(f)
                return _TEENCODE_DICT_CACHE
        except Exception:
            pass

    # Fallback từ điển nội suy nếu không tìm thấy tệp JSON
    _TEENCODE_DICT_CACHE = {
        "direct_lookup": {
            "cf": "cà phê", "sp": "sản phẩm", "dthu": "doanh thu", "sl": "số lượng",
            "đh": "đơn hàng", "dh": "đơn hàng", "hnay": "hôm nay", "hqua": "hôm qua",
            "bnhiu": "bao nhiêu", "bnhieu": "bao nhiêu", "ko": "không", "k": "không",
            "nv": "nhân viên", "ncc": "nhà cung cấp", "cty": "công ty", "hd": "hóa đơn",
            "hđ": "hóa đơn", "stk": "số tài khoản", "sđt": "số điện thoại",
        },
        "retail_specific_lookup": {
            "bn": "bao nhiêu", "ck": "chiết khấu", "kh": "khách hàng",
            "dt": "doanh thu", "tt": "thành tiền", "sl": "số lượng",
        },
        "general_chat_lookup": {
            "bn": "bạn", "ck": "chồng", "kh": "không",
            "dt": "điện thoại", "tt": "thông tin",
        },
    }
    return _TEENCODE_DICT_CACHE


def _strip_accents(text: str) -> str:
    s = unicodedata.normalize("NFD", str(text))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def _disambiguate_token(
    token: str,
    prev_token: Optional[str] = None,
    next_token: Optional[str] = None,
    domain: str = "retail",
) -> Optional[str]:
    """
    Khử đa nghĩa cho các từ viết tắt có nghĩa kép (bn, ck, kh, dt, tt, sl)
    dựa trên ngữ cảnh lân cận (prev_token, next_token) và miền nghiệp vụ.
    """
    clean_t = token.lower().strip(".,!?:;\"'()[]{}")
    p_unacc = _strip_accents(prev_token.lower().strip(".,!?:;\"'()[]{}")) if prev_token else ""
    n_unacc = _strip_accents(next_token.lower().strip(".,!?:;\"'()[]{}")) if next_token else ""

    if clean_t == "bn":
        # 'bn' trong bán lẻ: bao nhiêu (nếu đi với đơn, tiền, mặt hàng, ngày, tháng, có, bán, nhập, còn, ly, kg...)
        retail_signals = {
            "don", "tien", "hang", "sp", "mon", "ly", "kg", "hop", "chiec", "chai",
            "lan", "ngay", "thang", "nam", "co", "ban", "nhap", "con", "thu", "chi",
            "gia", "may", "bao", "duoc", "dc", "tong", "tri", "doanh", "thu"
        }
        if n_unacc in retail_signals or p_unacc in retail_signals or domain == "retail":
            return "bao nhiêu"
        if n_unacc in {"oi", "than", "nhe", "a", "ha"} or p_unacc in {"chao", "voi", "gap"}:
            return "bạn"
        return "bao nhiêu" if domain == "retail" else "bạn"

    if clean_t == "ck":
        # 'ck' trong bán lẻ: chiết khấu hoặc chuyển khoản
        discount_signals = {"%", "phan", "tram", "giam", "duoc", "ap", "dung", "chuong", "trinh"}
        transfer_signals = {"stk", "ngan", "hang", "qua", "khoan", "tien", "thanh", "toan"}
        if n_unacc in discount_signals or p_unacc in discount_signals:
            return "chiết khấu"
        if n_unacc in transfer_signals or p_unacc in transfer_signals:
            return "chuyển khoản"
        if domain == "retail":
            return "chiết khấu"
        return "chồng"

    if clean_t == "kh":
        # 'kh' trong bán lẻ: khách hàng (nếu đi với VIP, thân thiết, mua, quen, tên, mã, nợ...)
        cust_signals = {"vip", "than", "thiet", "mua", "quen", "ma", "ten", "danh", "sach", "no", "cua", "cac"}
        neg_signals = {"co", "thay", "biet", "ban", "phai", "duoc", "dc"}
        if n_unacc in cust_signals or p_unacc in cust_signals or domain == "retail":
            if n_unacc in neg_signals and domain != "retail":
                return "không"
            return "khách hàng"
        return "không"

    if clean_t == "dt":
        phone_signals = {"thoai", "sac", "mua", "sua", "hang", "cu", "may", "iphone", "samsung"}
        rev_signals = {"thang", "ngay", "nam", "tong", "cao", "thap", "dat", "thu", "ban"}
        if n_unacc in phone_signals or p_unacc in phone_signals:
            return "điện thoại"
        if n_unacc in rev_signals or p_unacc in rev_signals or domain == "retail":
            return "doanh thu"
        return "doanh thu" if domain == "retail" else "điện thoại"

    if clean_t == "tt":
        money_signals = {"cot", "tien", "tong", "sau", "hoa", "don", "bill"}
        if n_unacc in money_signals or p_unacc in money_signals or domain == "retail":
            return "thành tiền"
        return "thông tin"

    return None


def normalize_teencode_token(
    token: str,
    prev_token: Optional[str] = None,
    next_token: Optional[str] = None,
    domain: str = "retail",
) -> Tuple[str, Optional[str]]:
    """
    Chuẩn hóa 1 token đơn lẻ (giữ nguyên dấu câu bao quanh).
    Trả về (token_mới, từ_chuẩn_nếu_có_thay_đổi).
    """
    m_punct = re.match(r"^([.,!?:;\"'()\[\]{}]*)(.*?)([.,!?:;\"'()\[\]{}]*)$", token)
    if not m_punct:
        return token, None
    prefix, core, suffix = m_punct.group(1), m_punct.group(2), m_punct.group(3)
    if not core:
        return token, None

    clean_t = core.lower()

    # 1. Khử đa nghĩa theo ngữ cảnh cho các token đặc biệt (bn, ck, kh, dt, tt)
    disambig = _disambiguate_token(clean_t, prev_token=prev_token, next_token=next_token, domain=domain)
    if disambig is not None:
        return f"{prefix}{disambig}{suffix}", disambig

    # 2. Xử lý 'th' đứng trước số tháng hoặc 'này'/'trước': 'th 5/2025' -> 'tháng 5/2025'
    if clean_t == "th" and next_token:
        next_clean = next_token.lower().strip(".,!?:;\"'()[]{}")
        if re.match(r"^(?:0?[1-9]|1[0-2])(?:/\d{2,4})?$", next_clean) or next_clean in ("này", "nay", "trước", "trc"):
            return f"{prefix}tháng{suffix}", "tháng"

    # 3. Xử lý viết liền 'th5/2025', 'thg5/2025'
    m_th_num = re.match(r"^(?:thg|th)(0?[1-9]|1[0-2])(/\d{2,4})?$", clean_t)
    if m_th_num:
        full_w = f"tháng {m_th_num.group(1)}{m_th_num.group(2) or ''}"
        return f"{prefix}{full_w}{suffix}", full_w

    # 4. Tra từ điển chuẩn hóa JSON
    dict_data = get_teencode_dictionary()
    direct_map = dict_data.get("direct_lookup", {})
    retail_map = dict_data.get("retail_specific_lookup", {})

    if domain == "retail" and clean_t in retail_map:
        res = retail_map[clean_t]
        return f"{prefix}{res}{suffix}", res

    if clean_t in direct_map:
        res = direct_map[clean_t]
        return f"{prefix}{res}{suffix}", res

    # 5. Xử lý rút gọn kéo dài nguyên âm: ví dụ 'điiiiiii' -> 'đi', 'nhiềuuu' -> 'nhiều'
    m_elongated = re.match(r"^([a-zA-Zà-ỹÀ-Ỹ]+?)([aeiouyà-ỹ])\2{2,}$", clean_t)
    if m_elongated:
        shortened = m_elongated.group(1) + m_elongated.group(2)
        if shortened in direct_map:
            res = direct_map[shortened]
            return f"{prefix}{res}{suffix}", res
        if shortened in retail_map:
            res = retail_map[shortened]
            return f"{prefix}{res}{suffix}", res

    return token, None


def normalize_teencode(text: str, domain: str = "retail") -> str:
    """
    Chuẩn hóa toàn bộ câu chứa từ viết tắt / teencode / lỗi gõ phím.
    
    Args:
        text (str): Văn bản đầu vào.
        domain (str): 'retail' (mặc định cho DataMate) hoặc 'general'.
        
    Returns:
        str: Câu văn đã được chuẩn hóa trọn vẹn.
    """
    if not text or not isinstance(text, str):
        return text

    tokens = text.split()
    n = len(tokens)
    out_tokens = []

    for i, t in enumerate(tokens):
        prev_t = tokens[i - 1] if i > 0 else None
        next_t = tokens[i + 1] if i + 1 < n else None
        new_t, _ = normalize_teencode_token(t, prev_token=prev_t, next_token=next_t, domain=domain)
        out_tokens.append(new_t)

    return " ".join(out_tokens)


def explain_teencode_normalization(text: str, domain: str = "retail") -> Tuple[str, List[Dict[str, str]]]:
    """
    Chuẩn hóa câu và ghi nhận chi tiết danh sách các từ đã thay đổi.
    Trả về: (câu_mới, [{'original': '...', 'replacement': '...'}])
    """
    if not text or not isinstance(text, str):
        return text, []

    tokens = text.split()
    n = len(tokens)
    out_tokens = []
    changes = []

    for i, t in enumerate(tokens):
        prev_t = tokens[i - 1] if i > 0 else None
        next_t = tokens[i + 1] if i + 1 < n else None
        new_t, rep = normalize_teencode_token(t, prev_token=prev_t, next_token=next_t, domain=domain)
        if rep is not None:
            changes.append({
                "original": t,
                "replacement": rep,
            })
        out_tokens.append(new_t)

    return " ".join(out_tokens), changes


__all__ = [
    "normalize_teencode",
    "explain_teencode_normalization",
    "normalize_teencode_token",
    "get_teencode_dictionary",
    "find_teencode_dictionary_path",
]

