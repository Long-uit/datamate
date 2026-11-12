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

try:
    from datamate.grounding_feasibility.normalizer_teencode import (
        normalize_teencode_token,
        get_teencode_dictionary,
    )
except ImportError:
    normalize_teencode_token = None
    get_teencode_dictionary = None

if TYPE_CHECKING:
    from datamate.ingestion.loader import BusinessData
else:
    BusinessData = Any
from datamate.types import Candidate, EntityMatch

# Từ điển viết tắt / teencode / lỗi gõ Telex tiếng Việt phổ biến trong bán lẻ
VIETNAMESE_ABBREVIATIONS: dict[str, str] = {
    # 1. Viết tắt nghiệp vụ bán lẻ & giao tiếp
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
    "cty": "công ty",
    "hd": "hóa đơn",
    "hđ": "hóa đơn",
    "ct": "chi tiết",
    "ck": "chiết khấu",
    "km": "khuyến mãi",
    "tt": "thành tiền",
    "vs": "với",
    "z": "vậy",
    "j": "gì",
    # 2. Lỗi kẹt bộ gõ Telex phổ biến trong tập dữ liệu
    "thangs": "tháng",
    "nawm": "năm",
    "ngayf": "ngày",
    "hoom": "hôm",
    "quys": "quý",
    "sangs": "sáng",
    "chieeuf": "chiều",
    "toois": "tối",
    "tuafn": "tuần",
    "tuaanf": "tuần",
    "truwowcs": "trước",
    "nayf": "này",
    "ddos": "đó",
    "cuoois": "cuối",
    "ddaauf": "đầu",
    "tieenf": "tiền",
    "hangf": "hàng",
    "cuwar": "cửa",
    "cuwa": "cửa",
    "cuar": "của",
    "nhaf": "nhà",
    "vaayj": "vậy",
    "đươc": "được",
    "dduwowcj": "được",
    "dduowcj": "được",
    "đuowc": "được",
    "đươcj": "được",
    "giumf": "giùm",
    "giups": "giúp",
    "nowj": "nợ",
    "laf": "là",
    "soos": "số",
    "ddown": "đơn",
    "nhieeu": "nhiều",
    "nhieeuf": "nhiều",
    "nhiêuf": "nhiều",
    "toongr": "tổng",
    "bans": "bán",
    "tooi": "tôi",
    "nhoms": "nhóm",
    "naof": "nào",
    "nàoo": "nào",
    "bieets": "biết",
    "nhaats": "nhất",
    "heets": "hết",
    "gias": "giá",
    "leen": "lên",
    "khachs": "khách",
    "tir": "tỉ",
    "tyr": "tỷ",
    "bij": "bị",
    "maays": "mấy",
    "cos": "có",
    "trawm": "trăm",
    "mawtj": "mặt",
    "coongj": "cộng",
    "hown": "hơn",
    "ees": "ế",
    "vaof": "vào",
    "hoir": "hỏi",
    "mooix": "mỗi",
    "nhaapj": "nhập",
    "veef": "về",
    "binhf": "bình",
    "quaan": "quân",
    "leej": "lệ",
    "vowis": "với",
    "huyr": "hủy",
    "khoong": "không",
    "bawngf": "bằng",
    "ddax": "đã",
    "nhir": "nhỉ",
    "gaanf": "gần",
    "ddieenj": "điện",
    "thoaij": "thoại",
    "tawng/giamr": "tăng/giảm",
    "tawng": "tăng",
    "giamr": "giảm",
    "cungf": "cùng",
    "vaf": "và",
    "luwowtj": "lượt",
    "tuwf": "từ",
    "trowr": "trở",
    "xuaats": "xuất",
    "its": "ít",
    "thuoocs": "thuốc",
    "thuoocj": "thuộc",
    "trar": "trả",
    "nguwowif": "người",
    "ddeems": "đếm",
    "mootj": "một",
    "treen": "trên",
    "toonf": "tồn",
    "phaanf": "phần",
    "tinhs": "tính",
    "laij": "lại",
    "ddoof": "đồ",
    "chieems": "chiếm",
    "ddeens": "đến",
    "tieeu": "tiêu",
    "conf": "còn",
    "bowts": "bớt",
    "thais": "thái",
    "ddooir": "đổi",
    "chiuj": "chịu",
    "rooif": "rồi",
    "laix": "lãi",
    "chayj": "chạy",
    "loaij": "loại",
    "suwar": "sửa",
}

# Các từ tiếng Anh / thương hiệu không được giải mã Telex tự động
_NON_TELEX_BRAND_WORDS: set[str] = {
    "top", "size", "bill", "pos", "kg", "ml", "gb", "id", "ok", "vat", "vip", "online", "app", "ship", "min", "max",
    "gas", "tiger", "fugacar", "namilux", "petrolimex", "salonpas", "plus", "plusssz", "dulux", "acyclovir", "upsa-c",
    "power-s", "order", "weber", "weber.tai", "fix", "for", "costar", "v.rohto", "rohto", "brew", "inox", "kudos",
    "clear", "strepsils", "cool", "kids", "powerflexx", "insee", "doppelherz", "cheese", "voucher", "thanks", "knorr",
    "pudding", "seller", "blackmores", "vihawa", "d-nee", "air", "moony", "hippis", "huggies",
}

_TONE_TABLE: dict[str, dict[str, str]] = {
    "a": {"s": "á", "f": "à", "r": "ả", "x": "ã", "j": "ạ"},
    "ă": {"s": "ắ", "f": "ằ", "r": "ẳ", "x": "ẵ", "j": "ặ"},
    "â": {"s": "ấ", "f": "ầ", "r": "ẩ", "x": "ẫ", "j": "ậ"},
    "e": {"s": "é", "f": "è", "r": "ẻ", "x": "ẽ", "j": "ẹ"},
    "ê": {"s": "ế", "f": "ề", "r": "ể", "x": "ễ", "j": "ệ"},
    "i": {"s": "í", "f": "ì", "r": "ỉ", "x": "ĩ", "j": "ị"},
    "o": {"s": "ó", "f": "ò", "r": "ỏ", "x": "õ", "j": "ọ"},
    "ô": {"s": "ố", "f": "ồ", "r": "ổ", "x": "ỗ", "j": "ộ"},
    "ơ": {"s": "ớ", "f": "ờ", "r": "ở", "x": "ỡ", "j": "ợ"},
    "u": {"s": "ú", "f": "ù", "r": "ủ", "x": "ũ", "j": "ụ"},
    "ư": {"s": "ứ", "f": "ừ", "r": "ử", "x": "ữ", "j": "ự"},
    "y": {"s": "ý", "f": "ỳ", "r": "ỷ", "x": "ỹ", "j": "ỵ"},
}


def decode_telex_token(word: str) -> str:
    """
    Giải mã tự động một từ tiếng Việt bị lỗi bộ gõ Telex (ví dụ: 'thangs' -> 'tháng', 'dduwowcj' -> 'được').
    Chỉ kích hoạt khi từ có dấu hiệu Telex rõ ràng (dd, aa, ee, oo, aw, ow, uw hoặc kết thúc bằng phụ âm + phím dấu)
    và không nằm trong danh sách từ tiếng Anh / thương hiệu.
    """
    w = word.lower()
    if len(w) < 2 or len(w) > 10 or w in _NON_TELEX_BRAND_WORDS:
        return word
    if not re.match(r"^[a-z]+$", w):
        return word
    has_telex_vowel_or_d = bool(re.search(r"(?:dd|aa|ee|oo|aw|ow|uw)", w))
    if not has_telex_vowel_or_d:
        return word

    tone = None
    if w[-1] in ("s", "f", "r", "x", "j") and len(w) >= 3:
        tone = w[-1]
        w = w[:-1]

    if w.startswith("dd"):
        w = "đ" + w[2:]
    w = w.replace("uow", "ươ").replace("uwow", "ươ")
    w = w.replace("aa", "â").replace("ee", "ê").replace("oo", "ô")
    w = w.replace("aw", "ă").replace("ow", "ơ").replace("uw", "ư")

    if tone:
        # Ưu tiên đặt dấu thanh lên nguyên âm có mũ/móc (ă, â, ê, ô, ơ, ư), nếu có 'ươ' thì đặt lên 'ơ'
        placed = False
        if "ươ" in w:
            w = w.replace("ươ", "ư" + _TONE_TABLE["ơ"][tone], 1)
            placed = True
        if not placed:
            for idx in range(len(w) - 1, -1, -1):
                if w[idx] in ("ă", "â", "ê", "ô", "ơ", "ư"):
                    w = w[:idx] + _TONE_TABLE[w[idx]][tone] + w[idx + 1 :]
                    placed = True
                    break
        if not placed:
            # Nếu nguyên âm mở ở cuối hoặc có phụ âm cuối, tìm nguyên âm chính
            for idx in range(len(w) - 1, -1, -1):
                if w[idx] in _TONE_TABLE:
                    # Trường hợp oa, oe, uy hoặc nguyên âm đôi có phụ âm cuối
                    w = w[:idx] + _TONE_TABLE[w[idx]][tone] + w[idx + 1 :]
                    break
    return w

# Các từ dừng / thuật ngữ kinh doanh chung tuyệt đối không được gán nhầm là tên thực thể (khách/món/NCC)
BUSINESS_ENTITY_STOPWORDS: set[str] = {
    "bình quân", "binh quan", "trung bình", "trung binh",
    "hàng hóa", "hang hoa", "hàng hoá", "hàng", "hang", "sản phẩm", "san pham", "mặt hàng", "mat hang",
    "bị hủy", "bi huy", "bị huỷ", "hủy", "huỷ", "huy", "đơn hủy", "don huy",
    "tháng", "thang", "năm", "nam", "tiền", "tien", "doanh thu", "dthu", "doanh so",
    "chi tiết", "chi tiet", "đơn hàng", "don hang", "đơn", "don", "hóa đơn", "hoa don", "bill",
    "khách hàng", "khach hang", "số lượng", "so luong", "giá trị", "gia tri", "giá bán", "gia ban",
    "ngày", "ngay", "quý", "quy", "tuần", "tuan", "hôm nay", "hom nay", "hôm qua", "hom qua", "bữa qua", "bua qua",
    "cửa hàng", "cua hang", "tổng cộng", "tong cong", "bao nhiêu", "bao nhieu", "tỉ trọng", "ti trong", "phần trăm", "phan tram",
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


def _expand_single_token(
    t: str,
    prev_token: Optional[str] = None,
    next_token: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """Giải mã một token đơn lẻ (giữ nguyên dấu câu đầu/cuối), trả về (token_mới, dạng_chuẩn_nếu_đổi)."""
    # 0. Ưu tiên bộ chuẩn hóa teencode & khử đa nghĩa chuyên sâu nếu có
    if normalize_teencode_token is not None:
        try:
            norm_tok, rep = normalize_teencode_token(t, prev_token=prev_token, next_token=next_token, domain="retail")
            if rep is not None:
                return norm_tok, rep
        except Exception:
            pass

    m_punct = re.match(r"^([.,!?:;\"'()\[\]{}]*)(.*?)([.,!?:;\"'()\[\]{}]*)$", t)
    if not m_punct:
        return t, None
    prefix, core, suffix = m_punct.group(1), m_punct.group(2), m_punct.group(3)
    if not core:
        return t, None

    clean_t = core.lower()

    # 1. Tra cứu trực tiếp trong từ điển VIETNAMESE_ABBREVIATIONS
    if clean_t in VIETNAMESE_ABBREVIATIONS:
        full_w = VIETNAMESE_ABBREVIATIONS[clean_t]
        return f"{prefix}{full_w}{suffix}", full_w

    # 2. Xử lý 'th' đứng trước số tháng (1..12 hoặc M/YYYY) hoặc 'này'/'trước', ví dụ 'th 5/2025', 'th 06'
    if clean_t == "th" and next_token:
        next_clean = next_token.lower().strip(".,!?:;\"'()[]{}")
        if re.match(r"^(?:0?[1-9]|1[0-2])(?:/\d{2,4})?$", next_clean) or next_clean in ("này", "nay", "nayf", "trước", "trc", "truwowcs"):
            return f"{prefix}tháng{suffix}", "tháng"

    # 3. Xử lý viết liền 'th5/2025', 'thg5/2025', 'th08/2025'
    m_th_num = re.match(r"^(?:thg|th)(0?[1-9]|1[0-2])(/\d{2,4})?$", clean_t)
    if m_th_num:
        full_w = f"tháng {m_th_num.group(1)}{m_th_num.group(2) or ''}"
        return f"{prefix}{full_w}{suffix}", full_w

    # 4. Xử lý từ ghép ngăn cách bằng dấu '/' (ví dụ 'tawng/giamr')
    if "/" in clean_t and not any(ch.isdigit() for ch in clean_t):
        parts = core.split("/")
        new_parts = []
        changed = False
        for p in parts:
            pl = p.lower()
            if pl in VIETNAMESE_ABBREVIATIONS:
                new_parts.append(VIETNAMESE_ABBREVIATIONS[pl])
                changed = True
            else:
                dec = decode_telex_token(pl)
                if dec != pl:
                    new_parts.append(dec)
                    changed = True
                else:
                    new_parts.append(p)
        if changed:
            full_w = "/".join(new_parts)
            return f"{prefix}{full_w}{suffix}", full_w

    # 5. Giải mã Telex tự động theo quy tắc âm vị nếu có tổ hợp Telex rõ ràng
    decoded = decode_telex_token(clean_t)
    if decoded != clean_t:
        return f"{prefix}{decoded}{suffix}", decoded

    return t, None


def expand_abbreviations(text: str) -> str:
    """Mở rộng các từ viết tắt / teencode / lỗi gõ Telex trong câu (giữ nguyên dấu câu)."""
    tokens = text.split()
    expanded = []
    n = len(tokens)
    for i, t in enumerate(tokens):
        prev_t = tokens[i - 1] if i > 0 else None
        nxt = tokens[i + 1] if i + 1 < n else None
        new_t, _ = _expand_single_token(t, prev_token=prev_t, next_token=nxt)
        expanded.append(new_t)
    return " ".join(expanded)


def explain_and_expand_abbreviations(text: str) -> tuple[str, dict[str, str]]:
    """
    Mở rộng các từ viết tắt và ghi lại chi tiết các từ trước/sau đã được chuyển đổi.
    Trả về (câu_mới, {từ_viết_tắt: dạng_chuẩn}).
    """
    tokens = text.split()
    replaced = {}
    expanded = []
    n = len(tokens)
    for i, t in enumerate(tokens):
        prev_t = tokens[i - 1] if i > 0 else None
        nxt = tokens[i + 1] if i + 1 < n else None
        new_t, full_word = _expand_single_token(t, prev_token=prev_t, next_token=nxt)
        if full_word is not None:
            replaced[t] = full_word
        expanded.append(new_t)
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


GENERIC_PRODUCT_PREFIXES: set[str] = {
    "trà", "tra", "cà phê", "ca phe", "cf", "cafe", "bánh", "banh",
    "nước", "nuoc", "sinh tố", "sinh to", "kem", "sữa", "sua", "chè", "che",
    "gà", "ga", "bò", "bo", "heo", "cá", "ca", "mì", "mi", "cơm", "com",
    "bún", "bun", "phở", "pho", "gạch", "gach", "xi măng", "xi mang", "ống", "ong",
}


def fuzzy_entity_match_score(query: str, target: str) -> float:
    """
    Tính điểm tương đồng khớp mờ giữa query và target (thực thể).
    Kết hợp chuẩn hóa Unicode NFC, bỏ dấu tiếng Việt, biến thể số/khoảng trắng và Jaro-Winkler ratio.
    """
    if not query or not target:
        return 0.0

    q_norm = normalize_entity_text(query)
    t_norm = normalize_entity_text(target)
    q_unacc = remove_accents(q_norm)
    t_unacc = remove_accents(t_norm)

    if t_norm == q_norm:
        return 1.0
    if t_unacc == q_unacc:
        return 0.98

    pat_norm = r"(?<!\w)" + re.escape(t_norm) + r"(?!\w)"
    pat_unacc = r"(?<!\w)" + re.escape(t_unacc) + r"(?!\w)"
    if re.search(pat_norm, q_norm):
        return 1.0
    if len(t_unacc) >= 3 and re.search(pat_unacc, q_unacc):
        return 0.95

    def _clean_spacing(s: str) -> str:
        s = re.sub(r"(\d+)\s*([a-zA-Z]+)", r"\1 \2", s)
        return re.sub(r"\s+", " ", s).strip()

    t_clean = _clean_spacing(t_unacc)
    q_clean = _clean_spacing(q_unacc)
    if t_clean == q_clean:
        return 0.96
    pat_clean = r"(?<!\w)" + re.escape(t_clean) + r"(?!\w)"
    if len(t_clean) >= 3 and re.search(pat_clean, q_clean):
        return 0.95

    t_tokens = set(t_clean.split())
    q_tokens = set(q_clean.split())
    if not t_tokens or not q_tokens:
        return 0.0

    common = t_tokens.intersection(q_tokens)

    # NGUYÊN TẮC BẢO VỆ TỪ ĐƠN NGẮN (<= 5 ký tự):
    # Với từ đơn lẻ như 'bánh' (banh), 'bò' (bo), 'gà' (ga), 'mì' (mi):
    # Tuyệt đối KHÔNG dùng fuzzy edit-distance (tránh 'ban' trong 'bán ra' khớp nhầm 'bánh' 0.86).
    # Bắt buộc từ này phải xuất hiện trọn vẹn trong câu hỏi!
    if len(t_tokens) == 1:
        single_tk = list(t_tokens)[0]
        if len(single_tk) <= 5:
            if single_tk in q_tokens:
                return 0.95
            return 0.0

    if not common:
        return 0.0

    # Ngăn chặn khớp nhầm khi chỉ trùng tiền tố chung (ví dụ 'Trà đào' chỉ trùng 'trà' với 'Trà sữa...')
    distinguishing_tokens = t_tokens - GENERIC_PRODUCT_PREFIXES
    if distinguishing_tokens and not distinguishing_tokens.intersection(q_tokens):
        return 0.0

    token_score = len(common) / len(t_tokens)
    phrase_sim = best_phrase_similarity(t_clean, q_clean)

    if token_score >= 0.5:
        return round(0.5 * token_score + 0.5 * phrase_sim, 3)

    return round(phrase_sim if phrase_sim >= 0.85 else 0.0, 3)


def link_entities(
    question: str,
    candidates: list[Candidate] | list[str],
    entity_type: str = "product",
    threshold: float = 0.55,
) -> list[EntityMatch]:
    """
    Tìm kiếm và ánh xạ các thực thể xuất hiện trong câu hỏi tới danh mục candidates.
    - Hỗ trợ truyền danh sách Candidate hoặc danh sách chuỗi thô.
    - Áp dụng khớp mờ (NFC, bỏ dấu, BM25 + Jaro-Winkler).
    - Ngăn chặn triệt để false positive từ các từ dừng kinh doanh và tên khách lẻ tẻ.
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

        # 1. Bỏ qua nếu giá trị thực thể trùng hoàn toàn với từ dừng kinh doanh
        if target_norm in BUSINESS_ENTITY_STOPWORDS or target_unaccented in BUSINESS_ENTITY_STOPWORDS:
            continue

        # 2. Khách hàng/nhân viên/nhà cung cấp: ngăn chặn false positive từ từ đơn lẻ khi câu hỏi không hỏi người
        if cand.entity_type in ("customer", "staff", "supplier"):
            is_about_person = bool(re.search(r"\b(?:khach|nhan\s*vien|nguoi\s*ban|ncc|nha\s*cung\s*cap|ong|ba|anh|chi|doi\s*tac)\b", unaccented_q))
            c_tokens = target_unaccented.split()
            if not is_about_person:
                # Nếu câu hỏi không hỏi người, bắt buộc toàn bộ các từ trong tên phải xuất hiện chính xác
                if len(c_tokens) < 2 or not all(re.search(r"(?<!\w)" + re.escape(tk) + r"(?!\w)", unaccented_q) for tk in c_tokens):
                    continue
            else:
                # Dù có hỏi người, không cho phép chỉ khớp 1 từ đơn lẻ
                if len(c_tokens) >= 2 and sum(bool(re.search(r"(?<!\w)" + re.escape(tk) + r"(?!\w)", unaccented_q)) for tk in c_tokens) < 2:
                    continue

        score = fuzzy_entity_match_score(expanded_q, cand.value)
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
                source_table=cand.source_table,
                source_col=cand.source_col,
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
