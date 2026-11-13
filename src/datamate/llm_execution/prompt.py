"""
Module: prompt.py
Mục đích: Xây dựng Prompt tinh gọn và thích ứng theo ý định (Intent-Driven Dynamic Prompting)
          cho mô hình sinh mã Python/Pandas phân tích dữ liệu.

Tích hợp toàn diện:
1. Dynamic System Instructions: Chỉ đưa các quy tắc liên quan trực tiếp đến Intent.
2. Schema Pruning: Tự động loại bỏ các bảng nội bộ không liên quan (chi phí, sổ quỹ, lương).
3. Rulebook Compression: Trích xuất các điều khoản trọng tâm tối đa ~1.000 ký tự.
4. Dynamic Few-shot RAG: Tích hợp thư viện Exemplar Bank và hàm truy hồi ví dụ mẫu.
5. Giải mã thời gian tự động: Quy đổi Tết âm lịch, mốc ngày dương ISO chuẩn xác.
6. Self-Correction Prompt Builder: Prompt tự sửa lỗi siêu gọn, kèm failed code và traceback.
"""

from __future__ import annotations

import calendar
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from datamate.grounding_feasibility.rulebook import load_rulebook, retrieve_relevant_rulebook_clauses
except ImportError:
    retrieve_relevant_rulebook_clauses = None

    def load_rulebook(split_dir: Optional[str] = None) -> str:
        if split_dir:
            p = Path(split_dir) / "rulebook.md"
            if p.exists():
                return p.read_text(encoding="utf-8")
        return ""

try:
    from datamate.grounding_feasibility.temporal import (
        TET_SOLAR_RANGES,
        format_temporal_for_prompt,
        get_calendar,
        get_tet_dates_from_calendar,
        parse_date,
        resolve_temporal,
        resolve_temporal_context,
    )
except ImportError:
    resolve_temporal = None
    resolve_temporal_context = None
    format_temporal_for_prompt = lambda x: ""
    get_calendar = None
    TET_SOLAR_RANGES = {
        2024: ("2024-02-02", "2024-02-19"),
        2025: ("2025-01-22", "2025-02-07"),
        2026: ("2026-02-10", "2026-02-26"),
        2027: ("2027-01-30", "2027-02-16"),
    }
    def get_tet_dates_from_calendar(year: int, calendar_path: Optional[str] = None):
        return TET_SOLAR_RANGES.get(year)

try:
    from datamate.grounding_feasibility.entity_linker import (
        Candidate,
        EntityMatch,
        expand_abbreviations,
        link_entities,
    )
except ImportError:
    link_entities = None
    expand_abbreviations = None
    Candidate = None
    EntityMatch = None

# Cấu hình encoding chuẩn trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ==============================================================================
# 1. BỘ GIẢI MÃ THỜI GIAN (ỦY QUYỀN TRỰC TIẾP CHO TEMPORAL.PY)
# ==============================================================================

# Toàn bộ logic giải mã thời gian tiếng Việt, lịch âm Tết, quý, tháng và mốc ISO
# được hợp nhất duy nhất (Single Source of Truth) tại `datamate.grounding_feasibility.temporal`.
# prompt.py kế thừa trực tiếp để tránh trùng lặp mã nguồn và đảm bảo đồng nhất 100%.


# ==============================================================================
# 2. PHÂN LOẠI Ý ĐỊNH CÂU HỎI (INTENT CLASSIFICATION)
# ==============================================================================

import unicodedata

def _strip_accents(text: str) -> str:
    s = str(text).lower()
    s = s.replace("đ", "d").replace("Đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def classify_intent(question: str) -> str:
    """Phân loại câu hỏi thành các nhóm nghiệp vụ chính."""
    q_lower = question.lower()
    q_norm = _strip_accents(q_lower)

    if any(k in q_lower for k in ["tay nghề", "kinh nghiệm", "sở thích", "thời tiết", "chuyên môn", "bằng cấp"]):
        return "unanswerable_suspect"

    if any(k in q_lower for k in [
        "tồn kho", "còn tồn", "tồn cuối", "hộp chẵn", "viên lẻ", "bao nhiêu hộp",
        "hộp và viên", "thùng và chai", "bao và kg", "thẻ kho"
    ]):
        return "inventory_unit_conversion"

    if any(k in q_lower for k in ["hoạt chất", "kê đơn", "quy đổi", "đơn vị lớn", "hoatchat"]):
        return "multitable_join"

    if any(k in q_lower for k in [
        "công nợ", "cong no", "còn nợ", "con no", "tuổi nợ", "tuoi no",
        "hạn nợ", "han no", "hạn trả", "phải thu", "khách nợ", "sổ nợ",
        "chưa trả", "chua tra", "nợ quá hạn", "thu hồi nợ", "khách còn nợ"
    ]):
        return "cong_no"

    if any(k in q_lower for k in [
        "nhà cung cấp", "nha cung cap", "nhaf cung cap", "ncc",
        "nhập hàng", "phiếu nhập", "tiền nhập", "nhap hang", "phieu nhap",
        "phiếu nhập hàng", "tiền mua hàng", "giá trị các phiếu nhập",
        "nhập vào", "giá nhập", "gia nhap", "nhap vao", "nhập nhiều"
    ]) or re.search(r"nhập.*(?:tiền|hàng|nhất|từ|nào)|(?:tiền|giá)\s*(?:bình\s*quân|trung\s*bình).*nhập|nhập.*giá\s*(?:bình\s*quân|trung\s*bình)", q_lower):
        return "purchase_import"

    if re.search(r"(?:gi[aá]s?\s*tr[iị]\s*)?(?:trung\s*b[iì]nh|b[iì]nh\s*qu[aâ]n)\s*(?:m[oộ]t|1|m[ỗo]i)\s*đ[oơ]n|tb\s*(?:m[oộ]t|1|m[ỗo]i)\s*đ[oơ]n|\baov\b", q_lower):
        return "average_order_value"

    if re.search(
        r"(?<!\d)%|ph[ầa]n\s*tr(?:[ăa]m|awm)|\bt[ỉỷi]\s*l[ệe]\b|\bty\s*le\b|\bt[ỉỷi]\s*tr[ọo]ng\b",
        q_lower,
    ):
        return "rate_percentage"

    if any(k in q_lower for k in ["tăng liên tục", "tăng giảm", "so với", "thay đổi bao nhiêu", "tăng trưởng"]):
        return "time_series"

    if re.search(
        r"(?:đơn|hoá\s*đơn|hoa\s*don|bill|\bdon\b).*(?:huỷ|hủy|cancel|\bhuy\b)"
        r"|(?:huỷ|hủy|cancel|\bhuy\b).*(?:đơn|hoá\s*đơn|hoa\s*don|bill|\bdon\b)"
        r"|(?:trạng\s*thái|trang\s*thai)\s*(?:huỷ|hủy|cancel|huy)",
        q_lower,
    ):
        return "cancelled_orders"

    if re.search(
        r"(?:đếm|bao\s*nhiêu|bn|mấy|có\s+mấy|co\s+bao\s*nhiu)\s+(?:số\s+)?(?:đơn|hoá\s*đơn|hoa\s*don|bill|\bdon\b|đợt(?:\s*(?:giao|hàng))?|lượt(?:\s*(?:giao|hàng))?)"
        r"|(?:bao\s*nhiêu|bn|mấy|đếm\s+số)\s+(?:đợt|lượt)\s*(?:giao|hàng)?"
        r"|chở\s*giao\s*bao\s*nhiêu\s*đợt"
        r"|có\s+(?:bao\s*nhiêu|mấy)\s+đơn|co\s+bao\s*nhiu\s+don",
        q_lower,
    ):
        return "count_orders"

    if re.search(
        r"\b(?:giá\s*bán|gia\s*ban|đơn\s*giá|don\s*gia|bao\s*nhiêu\s*tiền\s*(?:một|1)|bn\s*(?:một|1))\b"
        r"|giá\s*bán.*(?:bn|bao\s*nhiêu)"
        r"|gia\s*ban.*(?:bn|bao\s*nhiêu)",
        q_lower,
    ):
        return "price_lookup"

    if re.search(
        r"(?:bán|ban|mua)\s*(?:đc|được|duoc)?\s*(?:bao\s*nhiêu|bn|mấy)\s+(?:ly|phần|cái|kg|hộp|chai|gói|lon|bịch|suất|tô|chén|mét|thanh)"
        r"|mấy\s+kg\s+|bao\s*nhiêu\s+kg\s+|may\s+kg\s+|bao\s*nhiu\s+kg\s+",
        q_lower,
    ):
        return "quantity_sum"

    if (
        any(k in q_lower for k in [
            "bán chạy nhất", "bán chạy", "nhiều nhất", "nhiều tiền nhất", "cao nhất",
            "thấp nhất", "lời nhất", "đắt nhất", "top", "xếp thứ", "hot nhất", "giỏi nhất"
        ])
        or (any(k in q_lower for k in ["khách", "khach"]) and any(k in q_lower for k in ["chi tiêu", "chi tieu", "mua nhiều", "tiêu nhiều"]))
        or any(k in q_norm for k in [
            "ban chay nhat", "ban chay", "nhieu nhat", "nhieu tien nhat", "cao nhat",
            "thap nhat", "loi nhat", "dat nhat", "top", "xep thu", "hot nhat", "gioi nhat",
            "ngay nao", "mat hang nao", "san pham nao", "khach nao", "ai mua", "sp nao"
        ])
    ):
        return "ranking_topk" 
        return "ranking_topk"

    return "aggregation"


# ==============================================================================
# 3. RÚT GỌN SCHEMA ĐỘNG THEO Ý ĐỊNH (SCHEMA PRUNING)
# ==============================================================================

def prune_schema_by_intent(
    schema_str: str,
    intent: str,
    question: str,
    entity_matches: Optional[List[Any]] = None,
    temporal_info: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Rút gọn Schema động: Chỉ giữ lại các bảng liên quan đến Intent và câu hỏi.
    Tuân thủ 3 Nguyên tắc Vàng (Golden Guarantees):
    1. Entity Keyword Protection: Bảo vệ bảng chứa thực thể được hỏi (khách hàng, mặt hàng, đợt giao).
    2. Temporal Range Protection: Bảo vệ ít nhất một bảng bán hàng có cột ngày trong kỳ truy vấn.
    3. Foreign Key Relational Closure: Bảo toàn cặp bảng cha-con (don_hang <-> chi_tiet_don, khach_hang <-> don_hang).
    4. Primary Sales Immunity: Bảng bán hàng tổng hợp/chi tiết được miễn nhiễm hoàn toàn khỏi cắt tỉa.
    5. Không quét từ khóa phủ định trên dữ liệu ô mẫu (vd: 'lương' trong '264 Lương Định Của').
    6. Đồng bộ nguyên khối (atomic) giữa phần tóm tắt vai trò và phần chi tiết cột.
    """
    if not schema_str or not schema_str.strip():
        return ""

    q_low = question.lower()
    q_norm = unicodedata.normalize("NFKD", q_low).encode("ascii", "ignore").decode("utf-8")
    q_words = set(re.findall(r"\w+", q_low))
    q_norm_words = set(re.findall(r"\w+", q_norm))

    entity_tables = set()
    if entity_matches:
        for m in entity_matches:
            meta = getattr(m, "metadata", {}) or {}
            tbl = meta.get("source_table")
            if tbl:
                entity_tables.add(str(tbl).lower())

    explicit_expense = any(k in q_low for k in ["chi phí", "khoản chi", "sổ quỹ", "tiền điện", "tiền nước", "mặt bằng", "chi_phi"])
    explicit_import = bool(re.search(
        r"nhập|nhap|giá\s*nhập|nhập\s*vào|gia\s*nhap|nhap\s*vao|phiếu\s*nhập|nhà\s*cung\s*cấp|tiền\s*nhập|nhap_hang|"
        r"giá\s*bình\s*quân.*nhập|nhập.*giá\s*bình\s*quân",
        q_low,
    ))
    explicit_debt = any(k in q_low for k in ["công nợ", "sổ nợ", "còn nợ", "tuổi nợ", "hạn nợ", "phải thu"])
    explicit_employee = any(k in q_low for k in ["nhân viên", "tiền lương", "bảng lương", "chấm công", "chamcong"])
    explicit_customer = any(k in q_low for k in ["khách hàng", "khách", "sđt", "điện thoại", "khach hang", "nhóm", "thân thiết", "than thiet"])
    explicit_inventory = any(k in q_low for k in ["tồn kho", "thẻ kho", "còn tồn", "tồn cuối", "hộp", "viên", "tonkho"])
    explicit_delivery = any(k in q_low for k in ["giao hàng", "chở hàng", "đợt giao", "lượt giao", "chở giao", "giao hang", "cho hang"])

    # Phân tách 2 phần của schema_str nếu có
    has_dual_sections = "### CHI TIẾT CÁC BẢNG VÀ CỘT:" in schema_str
    if has_dual_sections:
        summary_section, detail_section = schema_str.split("### CHI TIẾT CÁC BẢNG VÀ CỘT:", 1)
    else:
        summary_section, detail_section = "", schema_str

    detail_blocks = re.split(r"(?=(?:^|\n)-\s*Bảng\s+)", detail_section)
    header = detail_blocks[0] if detail_blocks and not detail_blocks[0].strip().startswith("- Bảng") else ""
    table_items = [b.strip() for b in detail_blocks if b.strip().startswith("- Bảng")]

    if len(table_items) <= 3:
        return schema_str

    # Phân tích có cấu trúc từng bảng
    parsed_tables = []
    for item in table_items:
        tbl_m = re.search(r"Bảng\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?", item)
        tbl_name = tbl_m.group(1) if tbl_m else ""
        role_m = re.search(r"\[Vai trò:\s*([^\]]+)\]", item)
        role = role_m.group(1) if role_m else ""

        cols_m = re.search(r"Cột\s*\(\d+\):\s*\[(.*?)\]", item, re.DOTALL)
        cols_text = cols_m.group(1) if cols_m else ""
        col_names = [c.strip().lower() for c in re.findall(r"'([^']+)'", cols_text)]

        # clean_descriptor chỉ chứa tên bảng, vai trò và tên cột (KHÔNG CHỨA GIÁ TRỊ Ô MẪU)
        clean_descriptor = f"{tbl_name} {role} {' '.join(col_names)}".lower()
        clean_desc_norm = unicodedata.normalize("NFKD", clean_descriptor).encode("ascii", "ignore").decode("utf-8")

        parsed_tables.append({
            "name": tbl_name,
            "role": role,
            "cols": col_names,
            "desc": clean_descriptor,
            "desc_norm": clean_desc_norm,
            "raw": item,
        })

    kept_names: Set[str] = set()

    for p in parsed_tables:
        t_name_low = p["name"].lower()
        t_name_norm = unicodedata.normalize("NFKD", t_name_low).encode("ascii", "ignore").decode("utf-8")
        role_low = p["role"].lower()
        desc = p["desc"]
        desc_norm = p["desc_norm"]

        is_sales = any(k in role_low for k in ["bán hàng", "hóa đơn"]) or any(k in t_name_low for k in ["banhang", "donhang", "hoadon", "pos", "chitietdon", "sobanhang"])
        is_delivery = any(k in role_low for k in ["giao hàng", "vận chuyển"]) or any(k in t_name_low for k in ["giaohang", "phieugiao", "vanchuyen", "chohang", "sochohang"])
        is_product = any(k in role_low for k in ["sản phẩm", "thuốc", "bảng giá"]) or any(k in t_name_low for k in ["sanpham", "hanghoa", "danhmuc", "thuoc", "banggia"])
        is_cust = any(k in role_low for k in ["khách hàng"]) or any(k in t_name_low for k in ["khachhang", "customer"])
        is_debt = "công nợ" in role_low or any(k in t_name_low for k in ["congno", "sono"])
        is_expense = "chi phí" in role_low or any(k in t_name_low for k in ["chiphi", "soquy"])
        is_import = "nhập hàng" in role_low or any(k in t_name_low for k in ["nhaphang", "nhap"])
        is_inv = "tồn kho" in role_low or any(k in t_name_low for k in ["tonkho", "thekho"])
        is_hr = any(k in desc for k in ["bảng lương", "chấm công", "nhanvien"]) and not is_sales

        # --- NGUYÊN TẮC VÀNG 1: BẢO VỆ THỰC THỂ (Entity Keyword Protection) ---
        if t_name_low in entity_tables:
            kept_names.add(p["name"])
            continue

        if t_name_low in q_low or t_name_norm in q_norm or (len(t_name_norm) >= 4 and t_name_norm in q_norm_words):
            kept_names.add(p["name"])
            continue

        if is_delivery and explicit_delivery:
            kept_names.add(p["name"])
            continue

        if is_cust and explicit_customer:
            kept_names.add(p["name"])
            continue

        product_indicators = [
            "sản phẩm", "san pham", "mặt hàng", "mat hang", "thuốc", "thuoc",
            "bảng giá", "bang gia", "giá bán", "gia ban", "đơn giá", "don gia",
            "món", "mon", "cac mon", "tất cả các món", "size", "sz", "ly", "cốc", "coc",
            "chai", "lon", "thùng", "thung", "hộp", "hop", "bánh", "banh", "nước", "nuoc",
            "cà phê", "ca phe", "cf", "trà", "tra", "combo", "topping", "danh mục", "danh muc",
            "nhóm hàng", "nhom hang", "loại"
        ]
        if is_product and (any(k in q_low for k in product_indicators) or any(k in q_norm for k in product_indicators)):
            kept_names.add(p["name"])
            continue

        # --- NGUYÊN TẮC VÀNG 4: MIỄN NHIỄM CHO BẢNG BÁN HÀNG (Primary Sales Immunity) ---
        if is_sales:
            # Trong mọi truy vấn bán hàng, doanh thu, đơn hàng, mặt hàng, bảng bán hàng được miễn nhiễm
            if intent not in ("expense", "purchase_import"):
                kept_names.add(p["name"])
                continue

        # --- XỬ LÝ THEO Ý ĐỊNH ĐẶC THÙ (Specific Intents) ---
        if intent == "cong_no":
            if is_debt or is_cust or is_sales or explicit_debt:
                kept_names.add(p["name"])
            continue

        if intent == "purchase_import":
            if is_import or is_product:
                kept_names.add(p["name"])
            continue

        if intent == "inventory_unit_conversion":
            if is_inv or is_product or is_sales or explicit_inventory:
                kept_names.add(p["name"])
            continue

        # --- LỌC BỎ BẢNG NỘI BỘ (Chỉ lọc trên clean_descriptor) ---
        if is_expense and not explicit_expense:
            continue
        if is_hr and not explicit_employee:
            continue
        if is_debt and not explicit_debt:
            continue
        if is_import and not explicit_import:
            continue
        if is_delivery and not explicit_delivery:
            continue
        if is_inv and not explicit_inventory and intent not in ("inventory_unit_conversion", "aggregation"):
            continue
        if any(k in p["name"].lower() for k in ["donvitinh", "dvt"]) and not any(k in q_low for k in ["đơn vị tính", "đvt", "dvt", "quy đổi", "quydoi"]):
            continue
        if is_cust and not explicit_customer and intent not in ("ranking_customer", "customer_lookup", "cong_no"):
            continue

        kept_names.add(p["name"])

    # --- NGUYÊN TẮC VÀNG 2: BẢO VỆ PHẠM VI THỜI GIAN (Temporal Range Protection) ---
    # Đảm bảo luôn có ít nhất một bảng bán hàng có ngày giao dịch
    has_kept_sales = any(
        any(k in p["role"].lower() for k in ["bán hàng", "hóa đơn"])
        for p in parsed_tables if p["name"] in kept_names
    )
    if not has_kept_sales and intent not in ("purchase_import", "expense"):
        for p in parsed_tables:
            if any(k in p["role"].lower() for k in ["bán hàng", "hóa đơn"]) or any(k in p["name"].lower() for k in ["donhang", "hoadon", "banhang"]):
                kept_names.add(p["name"])
                break

    # --- NGUYÊN TẮC VÀNG 3: QUAN HỆ KHÓA NGOẠI & BẢO TOÀN CẶP BẢNG ---
    # 3.1. Nếu giữ bảng chi tiết dòng hàng (chi_tiet_don, DanhSachHoaDonChiTiet), bắt buộc giữ bảng đơn hàng (don_hang, DanhSachHoaDon)
    for p in parsed_tables:
        if p["name"] in kept_names:
            p_low = p["name"].lower()
            if any(k in p_low for k in ["chitiet", "chi_tiet", "detail"]):
                for parent_p in parsed_tables:
                    parent_low = parent_p["name"].lower()
                    if not any(k in parent_low for k in ["chitiet", "chi_tiet", "detail"]):
                        if (
                            ("don" in p_low and "don" in parent_low)
                            or ("hoadon" in p_low and "hoadon" in parent_low)
                            or ("banhang" in p_low and "banhang" in parent_low)
                        ):
                            kept_names.add(parent_p["name"])

    # 3.2. Bảo toàn tất cả các phần của bảng bị cắt nhỏ (ví dụ: DanhSachHoaDonChiTiet_1 và _2)
    split_bases = set()
    for name in list(kept_names):
        m_part = re.match(r"^(.*?)[_\-]\d+$", name)
        if m_part:
            split_bases.add(m_part.group(1).lower())
    if split_bases:
        for p in parsed_tables:
            m_p = re.match(r"^(.*?)[_\-]\d+$", p["name"])
            if m_p and m_p.group(1).lower() in split_bases:
                kept_names.add(p["name"])

    # 3.3. Bảo toàn bảng danh mục sản phẩm (DanhSachSanPham) khi có chi tiết đơn hàng bán ra
    has_order_details = any(any(k in p["name"].lower() for k in ["chitiet", "detail"]) for p in parsed_tables if p["name"] in kept_names)
    if has_order_details:
        for p in parsed_tables:
            if any(k in p["name"].lower() for k in ["sanpham", "hanghoa", "danhmuc"]):
                kept_names.add(p["name"])

    # Nếu giữ bảng khách hàng hoặc bảng sản phẩm, đảm bảo bảng bán hàng kết nối cũng được giữ
    has_cust_or_prod = any(
        (any(k in p["role"].lower() for k in ["khách hàng", "sản phẩm"]) and p["name"] in kept_names)
        for p in parsed_tables
    )
    if has_cust_or_prod:
        for p in parsed_tables:
            if any(k in p["role"].lower() for k in ["bán hàng", "hóa đơn"]):
                kept_names.add(p["name"])

    if len(kept_names) == 0:
        return schema_str

    # --- GIỚI HẠN TỐI ĐA 3-4 BẢNG (Tối ưu Context Window & VRAM Attention Matrix) ---
    max_k = 4 if intent == "multitable_join" else 3
    if len(kept_names) > max_k:
        def _score_table(tbl_p: Dict[str, Any]) -> int:
            t_name = tbl_p["name"].lower()
            role = tbl_p.get("role", "").lower()
            score = 0
            if any(e_t in t_name for e_t in entity_tables):
                score += 100
            if any(w in t_name for w in q_words if len(w) >= 3):
                score += 50
            if intent in ("revenue", "order_count", "cancelled_orders", "top_selling_product", "average_order_value"):
                if any(k in t_name or k in role for k in ["banhang", "ban_hang", "hoadon", "hoa_don", "donhang", "don_hang"]):
                    score += 45
                if any(k in t_name or k in role for k in ["chitiet", "chi_tiet", "detail"]):
                    score += 40
                if any(k in t_name or k in role for k in ["sanpham", "san_pham", "hanghoa", "hang_hoa", "mathang"]):
                    score += 25
            elif intent == "purchase_import":
                if any(k in t_name or k in role for k in ["nhaphang", "nhap_hang", "nhapkho", "phieunhap"]):
                    score += 45
                if any(k in t_name or k in role for k in ["sanpham", "hanghoa"]):
                    score += 30
            elif intent == "cong_no":
                if any(k in t_name or k in role for k in ["congno", "cong_no", "soquy", "thuchi"]):
                    score += 45
                if any(k in t_name or k in role for k in ["khachhang", "khach_hang"]):
                    score += 30
            elif intent == "expense":
                if any(k in t_name or k in role for k in ["chitudung", "phieuchi", "thuchi", "chiphi"]):
                    score += 45
            if any(k in role for k in ["bán hàng", "hóa đơn", "đơn hàng"]):
                score += 20
            return score

        scored_kept = [(p["name"], _score_table(p)) for p in parsed_tables if p["name"] in kept_names]
        scored_kept.sort(key=lambda x: x[1], reverse=True)
        kept_names = {name for name, _ in scored_kept[:max_k]}

    # --- TÁI CẤU TRÚC ĐỒNG BỘ NGUYÊN KHỐI (Atomic Re-rendering) ---
    kept_detail_blocks = [p["raw"] for p in parsed_tables if p["name"] in kept_names]

    if has_dual_sections and summary_section.strip():
        # Lọc lại phần summary header & join keys tương ứng với kept_names
        summary_lines = summary_section.strip().split("\n")
        filtered_summary_lines = []
        for line in summary_lines:
            s_line = line.strip()
            if s_line.startswith("- Bảng"):
                tbl_m = re.search(r"Bảng\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?", line)
                if tbl_m and tbl_m.group(1) in kept_names:
                    filtered_summary_lines.append(line)
            elif "<->" in s_line:
                pair_m = re.search(r"'([^']+)'\s*<->\s*'([^']+)'", s_line)
                if pair_m and pair_m.group(1) in kept_names and pair_m.group(2) in kept_names:
                    filtered_summary_lines.append(line)
            else:
                filtered_summary_lines.append(line)
        return "\n".join(filtered_summary_lines) + "\n\n### CHI TIẾT CÁC BẢNG VÀ CỘT:\n" + "\n\n".join(kept_detail_blocks)
    else:
        prefix = f"{header.strip()}\n\n" if header.strip() else ""
        return prefix + "\n\n".join(kept_detail_blocks)


# ==============================================================================
# 4. CHỈ DẪN HỆ THỐNG ĐỘNG (INTENT-DRIVEN SYSTEM INSTRUCTION) & RETURN FORMAT ADAPTER
# ==============================================================================

def is_table_question(question: str) -> bool:
    """Kiểm tra câu hỏi có yêu cầu trả về bảng (dict {'columns': [...], 'rows': [...]}) hay không."""
    if not question:
        return False
    q_low = unicodedata.normalize("NFC", question).lower()
    q_no_acc = re.sub(r"[^a-z0-9\s%]", " ", _strip_accents(q_low))
    q_no_acc = re.sub(r"\s+", " ", q_no_acc).strip()
    return bool(
        any(k in q_low for k in ("bảng", "lập bảng", "thống kê chi tiết từng", "mỗi người còn nợ", "số nợ của từng", "kèm số tiền còn nợ", "kèm số nợ từng người"))
        or re.search(r"(?:top\s*\d+|li[eệ]t\s*k[eê]\s*\d+|\d+\s*kh[aá]ch).*(?:m[oỗ]i\s*ng[uư][oờ]i|t[uừ]ng\s*ng(?:[uư][oờ]i|uwowif)|k[eè]m\s*s[oố]\s*(?:ti[eề]n|n[oợ]))", q_low)
        or re.search(r"(?:moi\s*nguoi\s*con\s*no|so\s*no\s*(?:cua\s*)?tung|tung\s*nguoi\s*con\s*no|kem\s*so\s*(?:tien\s*con\s*)?no|(?<!tra\s)\bbang\s+(?:hoa\s*hong|tien\s*hoa\s*hong|\d+\s*khach))", q_no_acc)
    )


def is_date_question(question: str) -> bool:
    """Kiểm tra câu hỏi có yêu cầu trả về ngày ('YYYY-MM-DD') hoặc tháng ('YYYY-MM') hay không."""
    if not question:
        return False
    q_low = unicodedata.normalize("NFC", question).lower()
    return bool(
        any(k in q_low for k in ("ngày nào", "ngay nao", "ngayf nào", "thời điểm nào", "tháng nào", "thang nao"))
        or re.search(r"\b(?:ng[aà]yf?|th[aá]ng)\s+n(?:[aà]o|aof)\b", q_low)
    )


def is_numeric_list_question(question: str) -> bool:
    """Kiểm tra câu hỏi có yêu cầu trả về danh sách các số nguyên [x1, x2, ...] (như quy đổi [chẵn, lẻ], doanh thu từng tháng/nhóm lần lượt, nợ thêm & trả được, 3 nhóm tuổi nợ) hay không."""
    if not question or is_table_question(question):
        return False
    q_low = unicodedata.normalize("NFC", question).lower()
    q_no_acc = re.sub(r"[^a-z0-9\s%]", " ", _strip_accents(q_low))
    q_no_acc = re.sub(r"\s+", " ", q_no_acc).strip()
    return bool(
        re.search(r"\b(?:chan|nguyen)\b.*\ble\b", q_no_acc)
        or re.search(r"\b(?:lan\s*luot|luwowtj|moi\s*loai\s*(?:la\s*)?(?:bao\s*nhieu|bnhiu|bao\s*nhiu|bn|nhieu)|moi\s*ben|moi\s*nhom|tu\s*thang\s*cu\s*den\s*thang\s*moi|ghi\s*(?:hai|2|ba|3)\s*so|tra\s*loi\s*(?:hai|2|ba|3)\s*so|theo\s*thu\s*tu\s*thoi\s*gian)\b", q_no_acc)
        or re.search(r"\b(?:no\s*them|mua\s*chiu\s*them|chiuj\s*them)\b.*\b(?:tra\s*(?:bot\s*)?no|tra\s*(?:duoc|dc|dduwowcj))\b", q_no_acc)
        or re.search(r"(?:doanh\s*thu|dthu)\s*cac\s*(?:don|ddown)\b.*?(?:doanh\s*thu|dthu|\bva)\s*cac\s*don\b", q_no_acc)
        or re.search(r"tuoi\s*no.*0.*7.*8.*15", q_no_acc)
    )


def is_topk_list_question(question: str) -> bool:
    """Kiểm tra câu hỏi có yêu cầu trả về danh sách Top-K (K >= 2 hoặc danh sách nhiều đối tượng) hay không."""
    if not question or is_table_question(question) or is_numeric_list_question(question):
        return False
    q_low = question.lower()
    is_count_how_many = bool(re.search(
        r"\b(?:c[oó]\s*(?:t[oổ]ng\s*c[oộ]ng\s*)?)?(?:m[aấ]y|maays|bao\s*nhi[eê]u|nhi[eê]u)\s+(?:m[aặ]t\s*h[aà]ng|s[aả]n\s*ph[aẩ]m|sp|kh[aá]ch(?:\s*h[aà]ng)?|m[oó]n)\b",
        q_low,
    ))
    if is_count_how_many:
        return False
    patterns = [
        r"\btop\s*(?:[2-9]|\d{2,})\b",
        r"(?<!/)(?<!\d)\b([2-9]|[1-4]\d|50)\s+(?:mặt\s*hàng|mat\s*hang|sản\s*phẩm|san\s*pham|sp|khách(?:\s*hàng)?|món|mon|hàng|khach)\b",
        r"\bliệt\s*kê\s+([2-9]|[1-4]\d|50)\b",
        r"\blist\s*\d+\b",
        r"\bcho\s+(?:tôi|mình|em)?\s*([2-9]|[1-4]\d|50)\s+(?:mặt\s*hàng|sp|sản\s*phẩm|khách|hàng)\b",
        r"\bnhững\s*(?:mặt\s*hàng|sản\s*phẩm|sp|khách)\s*nào\b",
        r"\bdanh\s*sách\s*(?:mặt\s*hàng|sản\s*phẩm|sp|khách)\b",
        r"\bh[aà]ng\s+n[aà]o\s+h[eế]t\s+h[aạ]n\b",
    ]
    return any(re.search(p, q_low) for p in patterns)


def is_boolean_question(question: str) -> bool:
    """Kiểm tra câu hỏi có phải câu hỏi xu hướng / Đúng-Sai (Boolean True/False) hay không."""
    if not question:
        return False
    q_low = question.lower().strip()
    patterns = [
        r"t[aăâ]ng\s*li[eê]n\s*t[uụ]c\s*(?:kh[oô]ng|ko|khoong|k\b|\?)",
        r"gi[aả]m\s*li[eê]n\s*t[uụ]c\s*(?:kh[oô]ng|ko|khoong|k\b|\?)",
        r"th[aá]ng\s*sau\s*c[oó]\s*(?:lu[oô]n\s*)?cao\s*h[oơ]n\s*th[aá]ng\s*tr[uư]?[oớ]?c",
        r"c[oó]\s*ph[aả]i\s*th[aá]ng.*cao\s*h[oơ]n.*v[aà]\s*th[aá]ng.*cao\s*h[oơ]n",
        r"c[oó]\s*t[aăâ]ng\s*li[eê]n\s*t[uụ]c",
        r"c[oó]\s*gi[aả]m\s*li[eê]n\s*t[uụ]c",
    ]
    return any(re.search(p, q_low) for p in patterns)


def is_top1_string_question(question: str) -> bool:
    """Kiểm tra câu hỏi có yêu cầu trả về duy nhất 1 mặt hàng / đối tượng đứng đầu (Top-1 scalar string) hay không."""
    if not question:
        return False
    if is_table_question(question) or is_date_question(question) or is_numeric_list_question(question) or is_topk_list_question(question):
        return False
    q_low = question.lower().strip()
    q_no_acc = _strip_accents(q_low)
    patterns = [
        r"\b(?:hàng|sp|sản\s*phẩm|mặt\s*hàng|món|hang|san\s*pham|mon)\s+n[aà]o[f]?\b",
        r"\b(?:hàng|hang)\s+n[aà]o[f]?\s+(?:chạy|chay)\b",
        r"\b(?:mặt\s*hàng|sản\s*phẩm|sp|món)\s+(?:bán\s*(?:chạy|được|dc|nhiều)|lời|hot|mang\s*lại).*l[aà]\s*(?:gì|chi|ai|gi)\b",
        r"\b(?:bán\s*(?:chạy|nhiều|hot)|chi\s*tiêu\s*nhiều|chay)\s*nhất\s*l[aà]\s*(?:gì|ai|những\s*gì|mặt\s*hàng\s*nào|sp\s*nào|gi|chi)\b",
        r"\bsp\s*bán\s*(?:dc|được|duoc)?\s*nhiều\s*nhất\b",
        r"\b(?:khách|khach)\s*n[aà]o[f]?\b",
        r"\bai\s+l[aà]\s+(?:khách|khach|người|nguoi|nhân|nhan|thợ|tho)\b",
        r"\b(?:ai|người\s*nào|nguoi\s*nao)\s*(?:mua|bán|ban|chi\s*tiêu|chi\s*tieu|nhập|nhap)\b",
        r"\b(?:mua|bán|ban|chi\s*tiêu|chi\s*tieu|nhập|nhap|nhân\s*viên|nhan\s*vien).*\bl[aà]\s*ai\b",
        r"\b(?:nhà\s*cung\s*c[aâấ]p|nha\s*cung\s*c[aâấ]p|nhaf\s*cung\s*c[aâấ]p|ncc)\s*n[aà]o[f]?\b",
        r"\btừ\s*(?:nhà\s*cung\s*c[aâấ]p|nha\s*cung\s*c[aâấ]p|nhaf\s*cung\s*c[aâấ]p|ncc)\b",
        r"\b(?:nhân\s*viên|thợ|nhan\s*vien)\s*(?:n[aà]o[f]?|bán\s*giỏi|giỏi\s*nhất|chăm\s*chỉ)\b",
        r"\btop\s*1\b",
        r"\bngười\s*mua\s*nhiều\s*nhất\b",
        r"\bl[aà]\s*(?:gì|chi|ai|gi)\s*[\?]?\s*$",
        r"\bl[aà]\s*(?:gì|chi|ai|gi)\s+(?:ạ|vậy|nhỉ|nhở|hả|ta|nhé|do|đó)\b",
    ]
    return any(re.search(p, q_low) for p in patterns) or bool(
        re.search(r"\b(?:lon\s*nhat|nhieu\s*nhat|nhiu\s*nhat|chay\s*nhat|cao\s*nhat|thap\s*nhat|it\s*nhat)\b.*\bla\s*(?:gi|chi|ai)\b", q_no_acc)
    )


def get_return_format_instruction(question: str, for_retry: bool = False) -> str:
    """Sinh chỉ dẫn định dạng trả về (Requirement 4) tương thích hoàn hảo với 7 kiểu đáp án."""
    prefix = "- " if for_retry else "4. "
    q_low = (question or "").lower()

    if is_boolean_question(question):
        return f"{prefix}BẮT BUỘC trả về giá trị logic Boolean (True hoặc False). TUYỆT ĐỐI KHÔNG trả về số, chuỗi ký tự hay danh sách!"

    if is_table_question(question):
        if any(k in _strip_accents(q_low) for k in ("hoa hong", "tho")):
            return f"{prefix}BẮT BUỘC trả về cấu trúc BẢNG dạng dict: {{'columns': ['ten_tho', 'tien_hoa_hong'], 'rows': [[str(ten), int(round(tien))], ...]}} sắp xếp giảm dần theo tiền hoa hồng!"
        return f"{prefix}BẮT BUỘC trả về cấu trúc BẢNG dạng dict: {{'columns': ['khach_hang', 'so_tien_no'], 'rows': [[str(ten_khach), int(round(so_no))], ...]}} đúng số lượng K khách được hỏi, sắp xếp theo số tiền nợ giảm dần!"

    if is_date_question(question):
        if re.search(r"\bth[aá]ng\s+n(?:[aà]o|aof)\b|thang\s+nao", q_low):
            return f"{prefix}BẮT BUỘC trả về chuỗi tháng định dạng ISO 'YYYY-MM' (ví dụ: '2025-07'). TUYỆT ĐỐI KHÔNG trả về số tiền, dict hay danh sách!"
        return f"{prefix}BẮT BUỘC trả về chuỗi ngày định dạng ISO 'YYYY-MM-DD' (ví dụ: '2025-05-13'). TUYỆT ĐỐI KHÔNG trả về số tiền, dict hay danh sách!"

    if is_numeric_list_question(question):
        return f"{prefix}BẮT BUỘC trả về DANH SÁCH các số nguyên (list of ints: [int(round(val1)), int(round(val2)), ...]) theo đúng thứ tự các mục/tháng/nhóm được nêu trong câu hỏi. TUYỆT ĐỐI KHÔNG trả về một số đơn lẻ hay dictionary!"

    if is_topk_list_question(question):
        return f"{prefix}BẮT BUỘC trả về DANH SÁCH các chuỗi tên (list of strings: ['Tên 1', 'Tên 2', ...]) đúng số lượng K được yêu cầu theo thứ tự từ cao xuống thấp. TUYỆT ĐỐI KHÔNG trả về một số, dict hay chuỗi đơn lẻ!"

    if is_top1_string_question(question):
        return f"{prefix}BẮT BUỘC trả về một chuỗi ký tự đơn lẻ (scalar string: ví dụ 'Tên hàng' hoặc 'Tên NCC' hoặc 'Tên khách') là tên đối tượng đứng đầu. TUYỆT ĐỐI KHÔNG trả về dạng list hay dict hay số tiền!"

    if re.search(r"(?<!\d)%|ph[ầa]n\s*tr(?:[ăa]m|awm)|\bt[ỉỷi]\s*l[ệe]\b|\bty\s*le\b|\bt[ỉỷi]\s*tr[ọo]ng\b|\bty\s*trong\b", q_low):
        return f"{prefix}BẮT BUỘC trả về một số thực phần trăm trong thang 0-100 làm tròn 2 chữ số thập phân: float(round(val, 2)). TUYỆT ĐỐI KHÔNG ép kiểu số nguyên và KHÔNG kèm ký hiệu '%'!"

    # Mặc định: câu hỏi AOV, doanh thu, đơn giá, số lượng, số đơn
    return f"{prefix}BẮT BUỘC trả về một số duy nhất (scalar number: int/float), làm tròn theo quy tắc làm tròn về đồng (int(round(...))). TUYỆT ĐỐI KHÔNG trả về dictionary hay list!"


def build_dynamic_system_instruction(intent: str, question: str, shop_static_prefix: str = "") -> str:
    """
    Tạo chỉ dẫn hệ thống tinh gọn, đặt phần tĩnh của cửa hàng (Core Instruction + Shop Schema + Business README)
    lên đầu tiên để tối đa hóa tỷ lệ trúng KV-Cache (Prefix Caching) khi gom nhóm theo business_id.
    """
    q_low = question.lower()

    core = r"""Bạn là chuyên gia phân tích dữ liệu kinh doanh Python/Pandas.
Viết duy nhất một hàm `def solution(data):` trả về kết quả chính xác.
QUY TẮC CỐT LÕI:
1. Tiện ích có sẵn: `get_sales_table(data)`, `get_date_col(df)`, `get_amount_col(df)`, `get_qty_col(df)`, `get_item_col(df)`, `clean_num(series)`, `clean_date(series)`.
2. Doanh thu, số đơn, công nợ: ƯU TIÊN GỌI HELPER: `revenue(data, start_date=..., end_date=..., as_of_date=..., product=...)` (tự xử lý đơn hủy/trả theo Rulebook §1), `count_orders(data, ...)` và `debt(data, ...)`.
3. Ngày: Gán `df['clean_date'] = clean_date(df[col])` trước khi so sánh với chuỗi ISO.
4. Tiền & Số lượng: Luôn bọc `clean_num(df[col]).sum()` hoặc `.mean()`.
5. Thiếu dữ liệu & Trả 0:
   - Thiếu bảng/cột cần thiết hoặc thực thể khớp 0 dòng trong TOÀN BỘ lịch sử: BẮT BUỘC `raise CannotAnswer("lý do")` để hệ thống abstain an toàn.
   - CHỈ trả về 0 (0.0, []) khi thực thể CÓ TỒN TẠI nhưng không có giao dịch trong kỳ/trạng thái được hỏi.
6. Trả về đúng 1 giá trị vô hướng (int, float, str, list, dict cho Table)."""

    conditional_rules: List[str] = []
    q_clean = _strip_accents(q_low)

    if any(k in q_clean for k in ["ngay nao", "ngay gi", "thoi diem nao", "thoi gian nao", "hom nao"]):
        conditional_rules.append(
            "- [CÂU HỎI TÌM NGÀY]: BẮT BUỘC group by theo ngày `df['clean_date'].dt.strftime('%Y-%m-%d')`, tìm ngày max/min và RETURN chuỗi ngày 'YYYY-MM-DD'. TUYỆT ĐỐI KHÔNG RETURN TỔNG TIỀN."
        )

    if any(k in q_clean for k in ["mat hang nao", "san pham nao", "mon nao", "hang nao", "thuoc nao", "sp nao"]):
        conditional_rules.append(
            "- [CÂU HỎI TÌM MẶT HÀNG]: Group by theo tên sản phẩm và RETURN chuỗi tên mặt hàng. TUYỆT ĐỐI KHÔNG RETURN TỔNG TIỀN."
        )

    if any(k in q_clean for k in ["khach nao", "khach hang nao", "ai mua"]):
        conditional_rules.append(
            "- [CÂU HỎI TÌM KHÁCH HÀNG]: Group by theo tên khách và RETURN chuỗi tên khách hàng (loại bỏ khách lẻ/vãng lai)."
        )

    if any(k in q_low for k in ["mấy đơn", "bao nhiêu đơn", "số đơn", "số lượng đơn", "so don", "có bao nhiêu đơn", "co bao nhiu don", "đếm số đơn", "dem so don", "bao nhiu don"]) or any(k in q_clean for k in ["may don", "bao nhieu don", "so don", "so luong don"]):
        conditional_rules.append(
            "- [Đếm số đơn]: Tìm cột mã đơn `order_col = next((c for c in cols if any(k in str(c).lower() for k in ['mã đơn', 'ma don', 'mã hoá đơn', 'mã hd', 'order_id'])), None)` "
            "và đếm `int(df[order_col].dropna().nunique())`. TUYỆT ĐỐI CẤM dùng `len(df)`!"
        )

    if any(k in q_low for k in ["huỷ", "hủy", "cancel", "huy"]) and any(k in q_low for k in ["đơn", "bill", "hoá đơn", "don"]):
        is_rate_query = any(k in q_low for k in ["tỉ lệ", "tỷ lệ", "ti le", "ty le", "%", "phần trăm", "phan tram", "suất"])
        if is_rate_query:
            conditional_rules.append(
                "- [Tỉ lệ hủy đơn (%)]: Mẫu số là TỔNG SỐ ĐƠN trong kỳ `total = int(df_p[order_col].dropna().nunique())`. "
                "Tử số là số đơn hủy: `cancel_orders = int(df_p[cancel_mask][order_col].dropna().nunique())`. "
                "`return round(float(cancel_orders / total * 100.0), 2)`. TUYỆT ĐỐI CẤM dùng `len(df)`!"
            )
        else:
            conditional_rules.append(
                "- [Đơn bị hủy]: Dùng bảng bán hàng / hóa đơn. Lọc trạng thái hủy: "
                "`df[status_col].astype(str).str.contains(r'hủy|huỷ|huy|cancel', case=False, na=False)` "
                "và đếm số đơn bằng `int(df[order_col].dropna().nunique())`. TUYỆT ĐỐI CẤM dùng `len(df)`!"
            )

    if any(k in q_low for k in ["từ", "trên", "dưới", "lớn hơn", "nhỏ hơn", "cao hơn", "thấp hơn", ">=", "<=", ">", "<"]) and any(k in q_low for k in ["đơn", "hoá đơn", "hoa don", "bill"]) and any(k in q_low for k in ["doanh thu", "tiền", "giá trị", "đồng", "k", "vnd"]):
        conditional_rules.append(
            "- [Đếm đơn theo ngưỡng doanh thu]: Gom nhóm theo mã đơn để tính tổng tiền từng đơn: `order_rev = df.groupby(order_col)[amt_col].apply(lambda s: clean_num(s).sum())`, đếm `int((order_rev >= X).sum())`."
        )

    # Lọc sản phẩm cụ thể nếu câu hỏi đề cập
    if any(k in q_low for k in ["mặt hàng", "sản phẩm", "thuốc", "hoạt chất", "món", "cà phê", "nước ép", "thép", "sữa", "tã", "bánh", "ly", "chai", "hộp"]) or intent in ("multitable_join", "price_lookup", "quantity_sum"):
        conditional_rules.append(
            "- [Lọc sản phẩm cụ thể]: Tìm cột tên hàng `prod_col = get_item_col(df)` và lọc: `df = df[df[prod_col].astype(str).str.contains(..., case=False, na=False)]` TRƯỚC KHI tính tổng."
        )

    if any(k in q_low for k in ["ly", "cốc", "chai", "lon", "kg", "cái", "hộp"]) and any(k in q_low for k in ["size", "(m)", "(l)", "(s)", "size m", "size l"]):
        conditional_rules.append(
            r"- [Phân tách Đơn vị tính và Kích cỡ (Size)]: "
            r"Từ chỉ đơn vị ('ly', 'cốc', 'chai') nằm ở cột đơn vị tính (`Unit`, `ĐVT`, `Đơn vị tính`), còn kích cỡ ('size M', '(M)') nằm ở cột tên hàng (`Hàng`, `Tên hàng`). "
            r"BẮT BUỘC lọc riêng: cột tên hàng lọc regex `r'\(m\)|\bsize\s*m\b'`, và nếu cần thì lọc cột đơn vị `df[unit_col].astype(str).str.contains('ly', case=False, na=False)`. "
            r"TUYỆT ĐỐI CẤM viết regex `r'ly.*size\s*m'` trên cột tên hàng!"
        )

    if intent == "quantity_sum" or any(k in q_low for k in ["bao nhiêu ly", "mấy ly", "bao nhiêu kg", "mấy kg", "số lượng", "so luong"]):
        conditional_rules.append(
            "- [Tính số lượng mặt hàng (Quantity)]: BẮT BUỘC tìm cột số lượng `qty_col = next((c for c in cols if any(k in str(c).lower() for k in ['số lượng', 'so_luong', 'soluong', 'sl', 'khối lượng', 'trọng lượng'])), None)` "
            "và tính tổng số lượng `int(round(clean_num(df[qty_col]).sum()))`. TUYỆT ĐỐI KHÔNG tính tổng cột doanh thu/tiền hàng!"
        )

    if intent == "price_lookup" or any(k in q_low for k in ["giá bán", "gia ban", "đơn giá", "don gia", "bao nhiêu tiền một", "bn một"]):
        conditional_rules.append(
            r"- [Tra cứu đơn giá / giá bán (Two-Tier Lookup Protocol)]: "
            r"BƯỚC 1: Tìm trong nhật ký bán hàng có ngày giao dịch (So_chi_tiet_ban_hang, DanhSachHoaDonChiTiet) vào đúng ngày cần tra. Nếu có giao dịch trong ngày đó, lấy đơn giá dòng bán: `int(round(clean_num(matched_day[price_col]).iloc[0]))`. "
            r"BƯỚC 2: Nếu không có giao dịch trong ngày đó hoặc câu hỏi không nêu ngày, tra cứu Bảng giá (BangGia) hoặc Danh mục hàng hóa (Danh sách hàng hóa, DanhMuc, DanhSachSanPham). Lọc đúng mặt hàng đó theo tên (dùng `r'\(m\)|\bm\b'` cho size M) để lấy `Giá bán` của đúng mặt hàng đó. "
            r"TUYỆT ĐỐI CẤM tính trung bình `.mean()` trên toàn bộ bảng danh mục hàng hóa (`data['Danh sách hàng hóa']['Giá bán'].mean()`)! "
            r"TUYỆT ĐỐI KHÔNG tính tổng doanh thu!"
        )

    if any(k in q_low for k in ["hoạt chất", "kê đơn", "natri"]) or (intent == "multitable_join" and any(k in q_low for k in ["thuốc", "dược", "y tế", "toa", "bệnh"])):
        conditional_rules.append(
            "- [Ghép nối bảng Nhà thuốc / Pharmacy Schema]: "
            "Trong nhà thuốc, ngày bán nằm ở Header (`BanHang_HoaDon`), chi tiết bán hàng nằm ở Detail (`BanHang_ChiTietHoaDon`), và thông tin hoạt chất nằm ở Catalog (`BanHang_Thuoc` / `BanHang_HangHoa`). "
            "BẮT BUỘC ghép Header `BanHang_HoaDon` (để lấy cột Ngày bán) với Detail `BanHang_ChiTietHoaDon` qua khóa `Order ID == Mã giao dịch`, rồi ghép với `BanHang_Thuoc` qua khóa `Ma hang == Mã HH` để lọc theo hoạt chất và ngày bán!"
        )

    is_ranking = intent in ("ranking_topk", "ranking_customer") or any(k in q_low for k in ["nhất", "top", "xếp hạng", "cao nhất", "thấp nhất", "nhiều nhất", "ít nhất"])
    if is_ranking:
        conditional_rules.append(
            "- [Quy tắc đồng hạng (Điều 9)]: Khi hai đối tượng bằng điểm nhau, sắp xếp theo MÃ tăng dần (nếu không có mã thì theo TÊN tăng dần). "
            "Dùng `apply_tie_breaker(records, sort_key, code_key, name_key)` hoặc `df.sort_values(by=[tieu_chi, ma_hoac_ten], ascending=[False, True])`."
        )

    if is_table_question(question):
        conditional_rules.append(
            "- [Định dạng trả về Bảng (Table)]: BẮT BUỘC trả về dict `{'columns': ['khach_hang', 'so_tien_no'], 'rows': [['Tên khách 1', int_no_1], ...]}` (hoặc cột tương ứng nếu là bảng hoa hồng thợ), sắp xếp giảm dần theo số tiền, đồng hạng theo tên tăng dần."
        )
    elif is_boolean_question(question):
        conditional_rules.append(
            "- [Câu hỏi xu hướng / Đúng Sai (Boolean)]: BẮT BUỘC trả về duy nhất giá trị Boolean `True` hoặc `False` (ví dụ `return bool(r_thang7 < r_thang8 < r_thang9)`). TUYỆT ĐỐI KHÔNG trả về số, chuỗi hay dict!"
        )
    elif is_date_question(question):
        conditional_rules.append(
            "- [Định dạng trả về Ngày / Tháng (Date)]: BẮT BUỘC trả về chuỗi `'YYYY-MM-DD'` (hoặc `'YYYY-MM'` nếu hỏi tháng nào). TUYỆT ĐỐI KHÔNG trả về số tiền hay `pd.Timestamp`!"
        )
    elif is_numeric_list_question(question):
        conditional_rules.append(
            "- [Định dạng trả về Danh sách số (Numeric List)]: Khi hỏi số liệu các kỳ/nhóm `lần lượt`, hoặc `[nợ thêm, trả được]`, hoặc 3 nhóm tuổi nợ `0-7, 8-15, trên 15 ngày`, BẮT BUỘC trả về `list` các số nguyên `[int_1, int_2, ...]` theo đúng thứ tự nêu trong câu hỏi!"
        )
    elif is_topk_list_question(question):
        conditional_rules.append(
            "- [Định dạng trả về Top-K (Danh sách)]: BẮT BUỘC trả về DANH SÁCH các chuỗi tên (list of strings: ['Tên 1', 'Tên 2', ...]) đúng số lượng K theo thứ tự xếp hạng. TUYỆT ĐỐI KHÔNG trả về một số hay một chuỗi đơn lẻ!"
        )
    elif is_top1_string_question(question):
        conditional_rules.append(
            "- [Định dạng trả về Top-1 (Tên đối tượng đứng đầu)]: BẮT BUỘC trả về một chuỗi ký tự đơn lẻ (scalar string: ví dụ 'Tên hàng' hoặc 'Tên NCC' hoặc 'Tên khách' hoặc 'Tên NV') là tên đối tượng đứng đầu. TUYỆT ĐỐI KHÔNG trả về số tiền, doanh thu, list hay dict!"
        )

    if any(k in q_low for k in ["nhà cung cấp", "nha cung cap", "nhaf cung cap", "ncc"]):
        conditional_rules.append(
            "- [Nhà cung cấp (Supplier)]: Khi hỏi về nhà cung cấp (nhập nhiều tiền nhất từ NCC nào), tìm bảng nhập hàng (`SoNhapHang` / `phieu_nhap`), tìm cột nhà cung cấp `ncc_col = next((c for c in cols if any(k in str(c).lower() for k in ['nhà cung cấp', 'nha cung cap', 'ncc', 'đối tác', 'nhà phân phối'])), None)`, nhóm theo `ncc_col` để tính tổng tiền nhập `clean_num(df[amt_col]).sum()`, và trả về tên chuỗi của NCC đứng đầu `df.groupby(ncc_col)['clean_amt'].sum().idxmax()`. TUYỆT ĐỐI KHÔNG trả về số tiền nhập!"
        )

    if intent == "average_order_value" or re.search(r"(?:gi[aá]s?\s*tr[iị]\s*)?trung\s*b[iì]nh\s*(?:m[oộ]t|1)\s*đ[oơ]n|tb\s*(?:m[oộ]t|1)\s*đ[oơ]n|\baov\b", q_low):
        conditional_rules.append(
            "- [Giá trị trung bình một đơn (AOV - Điều 3 & Điều 9)]: Doanh thu từng đơn hàng = tổng thành tiền các món trong đơn `df.groupby(order_col)[amt_col].sum()`, lấy `mean()`, và làm tròn về đồng bằng `int(round(aov))`. BẮT BUỘC trả về một số nguyên duy nhất, TUYỆT ĐỐI CẤM trả về dict hay list!"
        )

    is_pharma_inv = intent in ("inventory_unit_conversion", "multitable_join") or any(k in q_low for k in ["hộp", "viên", "chai", "thùng", "quy đổi", "divmod", "tồn"])
    if is_pharma_inv:
        conditional_rules.append(
            "- [Quy đổi tồn kho (Điều 5)]: Dùng `divmod(tong_so_luong, quy_cach)` để trả về list 2 số nguyên: `[số_hộp_chẵn, số_viên_lẻ]`."
        )

    if "khách" in q_low or "khach" in q_low:
        conditional_rules.append(
            "- [Khách hàng (Điều 3)]: Khi xếp hạng hoặc đếm khách, BẮT BUỘC loại bỏ khách lẻ/vãng lai ('lẻ', 'khách lẻ', 'kl', 'nan', 'none', `~df[cust_col].astype(str).str.contains(r'lẻ|khách lẻ|nan|none', case=False, na=False)`)."
        )
        if any(k in q_low for k in ["trung thành", "trung thanh"]):
            conditional_rules.append(
                "- [Khách trung thành nhất (Điều 3)]: Tính theo SỐ NGÀY MUA HÀNG KHÁC NHAU nhiều nhất (`df.groupby(cust_col)['clean_date_day'].nunique()`), chỉ tính đơn hợp lệ, loại khách lẻ."
            )
        if any(k in q_low for k in ["khách sộp", "khach sop", "sộp nhất", "sop nhat"]):
            conditional_rules.append(
                "- [Khách sộp nhất (Điều 3)]: Chỉ xét khách có TỐI THIỂU 3 ĐƠN HỢP LỆ trong kỳ (`nunique(order_col) >= 3`), xếp hạng theo GIÁ TRỊ TRUNG BÌNH MỘT ĐƠN (AOV = tổng doanh thu / số đơn hợp lệ) cao nhất."
            )
        if any(k in q_low for k in ["đổi ý", "doi y", "hay hủy", "hay huỷ"]):
            conditional_rules.append(
                "- [Khách hay đổi ý nhất (Điều 3)]: Là khách hàng (không tính khách lẻ) có SỐ ĐƠN BỊ HỦY nhiều nhất (`df_cancel.groupby(cust_col)[order_col].nunique()`)."
            )

    if any(k in q_low for k in ["ưa chuộng", "ua chuong"]):
        conditional_rules.append(
            "- [Mặt hàng được ưa chuộng nhất (Điều 3)]: Tính theo SỐ ĐƠN HÀNG HỢP LỆ KHÁC NHAU có xuất hiện mặt hàng đó (`df.groupby(prod_col)[order_col].nunique()`), TUYỆT ĐỐI KHÔNG tính theo tổng số lượng bán hay doanh thu! Loại trừ dòng 'Phí phục vụ'."
        )

    if any(k in q_low for k in ["bán chạy", "ban chay"]):
        conditional_rules.append(
            "- [Mặt hàng bán chạy nhất (Điều 3 & Điều 10)]: Loại trừ dòng 'Phí phục vụ'. Nếu cửa hàng bán nhiều đơn vị (thùng, hộp, lốc, cái/lon), BẮT BUỘC quy đổi về đơn vị cơ sở nhỏ nhất bằng `convert_to_base_qty(df, data)` trước khi cộng tổng số lượng!"
        )

    if any(k in q_low for k in ["chăm chỉ", "cham chi"]):
        conditional_rules.append(
            "- [Nhân viên / Thợ chăm chỉ nhất (Điều 3)]: Là người có SỐ NGÀY LÀM VIỆC THỰC TẾ (có phát sinh đơn/phiếu, tính cả phiếu bảo hành 0đ) nhiều nhất."
        )

    if any(k in q_low for k in ["đắt khách nhất", "dat khach nhat", "giờ cao điểm", "gio cao diem"]):
        conditional_rules.append(
            "- [Ngày đắt khách nhất / Giờ cao điểm (Điều 3)]: Đếm theo số đơn hàng hợp lệ (`nunique(order_col)`). Ngày đắt khách nhất trả về chuỗi `'YYYY-MM-DD'`; Giờ cao điểm trả về số nguyên giờ `h` (`0..23`, kiểu `int`)."
        )

    if any(k in q_low for k in ["topping", "kem cheese", "trân châu", "tran chau", "thạch"]):
        conditional_rules.append(
            "- [Luật Quán Cà phê (Điều 6.1)]: Khi đồ uống và topping ghi chung trong một ô của đơn hàng, phần topping vẫn được tách và tính là mặt hàng topping bán kèm."
        )

    if any(k in q_low for k in ["sửa xe", "sua xe", "thợ", "biển số", "bien so", "bảo hành", "nhớt", "ruột", "sửa điện", "xe khách quen"]):
        conditional_rules.append(
            "- [Luật Tiệm Sửa xe (Điều 6.4)]: Phiếu bảo hành (0đ) VẪN TÍNH vào tổng số lượt xe và số lượt làm của thợ, nhưng KHÔNG TÍNH vào doanh thu trung bình mỗi phiếu và KHÔNG CỘNG vào số lần thực hiện hạng mục trong cột `Làm gì`. "
            "Từ khóa: `'Nhớt'` = nhớt máy; `'ruột'` = thay ruột mới; `'Sửa điện'` KHÔNG tính thay bóng đèn hay thay bình ắc quy. "
            "`'Xe khách quen'` = xe có từ 2 lượt sửa CÓ TÍNH TIỀN trở lên trong kỳ, trả về chuỗi BIỂN SỐ XE."
        )

    if any(k in q_low for k in ["điện thoại", "dien thoai", "iphone", "samsung", "dòng máy", "dong may", "thu máy cũ", "trả góp", "tra gop", "hãng"]):
        conditional_rules.append(
            "- [Luật Cửa hàng Điện thoại (Điều 6.5)]: Khoản thu máy cũ đổi mới KHÔNG trừ vào doanh thu bán máy mới; khoản trả góp coi là công nợ. "
            "`'Dòng máy'` = phần tên trước dung lượng bộ nhớ `...GB` (vd: `'iPhone 13 128GB'` -> `'iPhone 13'`). "
            "`'Hãng'` = từ đầu tiên của tên máy (riêng `'iPhone'` -> `'Apple'`)."
        )

    if any(k in q_low for k in ["sữa số", "sua so", "tã size", "ta size", "bỉm size", "size tã", "số sữa"]):
        conditional_rules.append(
            "- [Luật Cửa hàng Mẹ & Bé (Điều 6.3)]: Khi lọc theo số sữa hoặc size tã, BẮT BUỘC chỉ lấy từ cột `Số / Size` trong bảng Danh mục sản phẩm (bỏ qua nếu ô trống, TUYỆT ĐỐI CẤM đoán số từ tên sản phẩm!)."
        )

    if any(k in q_low for k in ["hàng ế", "hang e", "không bán được", "khong ban duoc", "tăng giá", "tang gia", "ngay trước ngày đó"]):
        conditional_rules.append(
            "- [Hàng ế & Đợt tăng giá (Điều 5)]: `'Hàng ế'` là mặt hàng đã từng bán trước kỳ nhưng có 0 đơn hợp lệ trong kỳ. "
            "`'Ảnh hưởng của đợt tăng giá'` (so sánh N ngày kể từ ngày tăng giá D với N ngày ngay trước D): lọc mặt hàng, bỏ đơn hủy/trả, tính tổng số lượng (ưu tiên cột `'Số lượng quy đổi'` nếu có, nếu không dùng `'Số lượng'`) trong kỳ sau `[START_DATE..END_DATE]` (`qty_after`) và kỳ trước `[COMP_START_DATE..COMP_END_DATE]` (`qty_before`), rồi trả về `round(float(((qty_after - qty_before) / qty_before) * 100.0), 2)`."
        )

    if any(k in q_low for k in ["tỉ trọng", "ti trong", "tỷ trọng", "ty trong", "chiếm bao nhiêu %", "chiem bao nhieu %", "chiếm mấy %"]):
        conditional_rules.append(
            "- [Tỉ trọng doanh thu nhóm hàng / mặt hàng / kênh]: Gọi `rev_sub = revenue(data, start_date=START_DATE, end_date=END_DATE, product='tên nhóm/mặt hàng bỏ chữ nhóm/loại')` và `rev_total = revenue(data, start_date=START_DATE, end_date=END_DATE)`, trả về `round(float(rev_sub / rev_total * 100.0), 2)`."
        )

    if intent in ("rate_percentage", "time_series") or any(k in q_low for k in ["%", "phần trăm", "tỉ lệ", "tỷ lệ", "so với", "tăng trưởng"]):
        conditional_rules.append(
            "- [Tỉ lệ / Phần trăm]: Trả về float làm tròn 2 chữ số thập phân (vd: `12.50`, `1.06`), không kèm ký tự '%'."
        )

    if any(k in q_low for k in ["ca chiều", "ca sang", "ca sáng", "ca tối", "theo ca"]):
        conditional_rules.append(
            "- [Doanh thu theo ca làm việc]: BẮT BUỘC dùng cột thời gian có đủ giờ/phút (ví dụ 'Thời gian tạo' hoặc 'ThoiGianTao', TUYỆT ĐỐI KHÔNG dùng cột chỉ có ngày). "
            "Ca sáng: `(df['clean_dt'].dt.hour >= 6) & (df['clean_dt'].dt.hour <= 13)`. "
            "Ca chiều: `(df['clean_dt'].dt.hour >= 14) & (df['clean_dt'].dt.hour <= 21)`. "
            "BẮT BUỘC loại bỏ đơn hủy/trả hàng và dùng cột 'Tổng tiền hàng' (gross revenue trước giảm giá đơn)."
        )

    rules_text = "\n".join(conditional_rules) if conditional_rules else "- Tính toán chính xác theo đúng yêu cầu trong câu hỏi."

    output_format = """ĐỊNH DẠNG ĐÁP ÁN:
- Số nguyên/tiền: `int` | Tỉ lệ %: `float` (làm tròn 2 chữ số) | Ngày: `"YYYY-MM-DD"` | Top K: `list` | Bảng: `dict`.
- Viết code ngắn gọn, súc tích trong duy nhất hàm `def solution(data):`, không viết comment dài dòng."""

    prefix_part = f"{core}\n\n{shop_static_prefix.strip()}" if shop_static_prefix and shop_static_prefix.strip() else core
    return f"{prefix_part}\n\nQUY TẮC NGHIỆP VỤ BẮT BUỘC:\n{rules_text}\n\n{output_format}"


# ==============================================================================
# 5. TRÍCH XUẤT ĐIỀU KHOẢN RULEBOOK RÚT GỌN
# ==============================================================================

def extract_relevant_rulebook_clauses(
    rulebook_content: str,
    question: str,
    max_chars: int = 400,
    schema_str: str = "",
    business_note: str = "",
) -> str:
    """Trích xuất thông minh các điều khoản Rulebook theo cấu trúc schema/ngành hàng và câu hỏi."""
    if not rulebook_content or not rulebook_content.strip():
        return ""

    if retrieve_relevant_rulebook_clauses is not None:
        try:
            retrieved = retrieve_relevant_rulebook_clauses(
                rulebook_content=rulebook_content,
                question=question,
                schema_str=schema_str,
                business_note=business_note,
                max_chars=max_chars,
            )
            if retrieved and retrieved.strip():
                return retrieved
        except Exception:
            pass

    rb_text = rulebook_content.strip()
    if len(rb_text) <= max_chars:
        return rb_text

    raw_sections = re.split(r"(?=(?:^|\n)(?:#{1,3}\s+|Điều\s+\d+|Mục\s+\d+))", rb_text)
    sections = [s.strip() for s in raw_sections if s.strip()]

    if not sections or len(sections) == 1:
        truncated = rb_text[:max_chars]
        last_nl = truncated.rfind("\n")
        if last_nl > 600:
            truncated = truncated[:last_nl]
        return truncated + "\n... [Đã rút gọn tối ưu context]"

    q_lower = question.lower()
    wants_inventory = any(k in q_lower for k in ["tồn kho", "còn tồn", "hộp", "viên", "chai", "quy đổi", "divmod"])
    wants_customer = any(k in q_lower for k in ["khách hàng", "khách", "khach hang", "mua nhiều nhất"])
    wants_time_compare = any(k in q_lower for k in ["so với", "tháng trước", "tăng trưởng", "tăng hay giảm", "cùng kỳ", "trước tết"])
    wants_pharma = any(k in q_lower for k in ["hoạt chất", "thuốc", "kê đơn", "chỉ định", "dược"])
    wants_ranking = any(k in q_lower for k in ["nhất", "top", "xếp hạng", "cao nhất", "thấp nhất", "nhiều nhất"])
    wants_cancellation = any(k in q_lower for k in ["hủy", "huỷ", "trả hàng", "tỉ lệ hủy", "tỷ lệ huỷ"])

    scored_sections: List[Tuple[float, str]] = []
    for sec in sections:
        sec_low = sec.lower()
        score = 0.0

        if any(k in sec_low for k in ["điều 1", "điều 4", "điều 6", "điều 9", "doanh thu", "đồng hạng"]):
            score += 2.0
        if wants_inventory and any(k in sec_low for k in ["điều 5", "tồn kho", "quy đổi", "hộp chẵn"]):
            score += 5.0
        if wants_customer and any(k in sec_low for k in ["điều 3", "khách lẻ", "khách hàng"]):
            score += 5.0
        if wants_time_compare and any(k in sec_low for k in ["điều 2", "kỳ đối chiếu", "so sánh"]):
            score += 5.0
        if wants_pharma and any(k in sec_low for k in ["điều 7", "hoạt chất", "kê đơn"]):
            score += 5.0
        if wants_ranking and any(k in sec_low for k in ["điều 9", "đồng hạng", "tie-breaker"]):
            score += 4.0
        if wants_cancellation and any(k in sec_low for k in ["hủy", "huỷ", "trả hàng"]):
            score += 4.0

        q_words = set(re.findall(r"\w+", q_lower))
        sec_words = set(re.findall(r"\w+", sec_low))
        score += len(q_words & sec_words) * 0.1
        scored_sections.append((score, sec))

    scored_sections.sort(key=lambda x: x[0], reverse=True)
    selected: List[str] = []
    total_len = 0
    for score, sec in scored_sections:
        if total_len + len(sec) + 2 <= max_chars:
            selected.append(sec)
            total_len += len(sec) + 2
        else:
            remain = max_chars - total_len
            if remain > 150:
                selected.append(sec[:remain].rsplit("\n", 1)[0] + "\n...")
            break

    selected_set = set(selected)
    ordered_selected = [s for s in sections if s in selected_set or any(s.startswith(p[:80]) for p in selected)]
    return "\n\n".join(ordered_selected if ordered_selected else selected)


# ==============================================================================
# 6. THƯ VIỆN FEW-SHOT DYNAMIC EXEMPLAR BANK
# ==============================================================================

EXEMPLAR_BANK: Dict[str, str] = {
    "cong_no": """--- VÍ DỤ: TÍNH CÔNG NỢ ---
Câu hỏi: "Tính đến hết ngày 19/08/2026, có bao nhiêu khách còn nợ cửa hàng?" (as_of_date = "2026-08-19")
```python
def solution(data):
    df_d = next((df for k, df in data.items() if any(w in k.lower() for w in ['congno', 'sono', 'phaithu', 'soquy'])), None)
    if df_d is None: raise CannotAnswer("Không tìm thấy bảng công nợ")
    c_c = next((c for c in df_d.columns if any(w in str(c).lower() for w in ['khách hàng', 'mã khách', 'tenkh'])), None)
    d_c = next((c for c in df_d.columns if any(w in str(c).lower() for w in ['còn nợ', 'tiền nợ', 'phải thu'])), None)
    if not (c_c and d_c): raise CannotAnswer("Thiếu cột khách hàng hoặc số nợ")
    df_d['clean_debt'] = clean_num(df_d[d_c])
    valid = df_d[(df_d['clean_debt'] > 0) & (~df_d[c_c].astype(str).str.lower().str.contains(r'lẻ|khách lẻ|nan|none', na=False))]
    return int(valid[c_c].dropna().nunique())
```""",

    "purchase_import": """--- VÍ DỤ: TÍNH TỔNG TIỀN NHẬP HÀNG ---
Câu hỏi: "Tháng này tổng giá trị các phiếu nhập hàng là bao nhiêu?" (as_of_date = "2026-09-07")
```python
def solution(data):
    df_nhap = next((df for k, df in data.items() if 'nhap' in k.lower() and not any(w in k.lower() for w in ['chitiet', 'chi_tiet', 'detail'])), None)
    if df_nhap is None:
        raise CannotAnswer("Không tìm thấy bảng phiếu nhập")
    d_c, a_c = get_date_col(df_nhap), get_amount_col(df_nhap)
    if not (d_c and a_c):
        raise CannotAnswer("Thiếu cột ngày hoặc tiền trong bảng nhập")
    df_nhap['clean_date'] = clean_date(df_nhap[d_c])
    df_nhap = df_nhap[(df_nhap['clean_date'] >= '2026-09-01') & (df_nhap['clean_date'] <= '2026-09-07 23:59:59')]
    st_c = next((c for c in df_nhap.columns if any(w in str(c).lower() for w in ['trạng thái', 'status', 'ghi chú'])), None)
    if st_c:
        df_nhap = df_nhap[~df_nhap[st_c].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|cancel', na=False)]
    return int(round(clean_num(df_nhap[a_c]).sum()))
```""",

    "daily_revenue": r"""--- VÍ DỤ MINH HỌA: TÍNH DOANH THU TRONG NGÀY (DAILY REVENUE / HÔM NAY) ---
Câu hỏi: "Hôm nay doanh thu của cửa hàng là bao nhiêu?" (as_of_date = "2026-05-15")
```python
def solution(data):
    # Gọi trực tiếp hàm nghiệp vụ tất định revenue(...) theo Điều 1 & Điều 5 Rulebook:
    # Tự động lấy thành tiền sau chiết khấu dòng hàng, loại bỏ đơn hủy/trả và giới hạn theo ngày.
    total = revenue(
        data,
        start_date="2026-05-15",
        end_date="2026-05-15",
        as_of_date="2026-05-15",
    )
    return int(round(total))
```""",

    "aggregation": r"""--- VÍ DỤ MINH HỌA: TÍNH DOANH THU / TIỀN BÁN HÀNG ---
Câu hỏi: "Tháng 3/2026 hàng nước ép dưa hấu (L) thu về bao nhiêu tiền?" (as_of_date = "2026-06-24")
```python
def solution(data):
    # Ưu tiên gọi hàm nghiệp vụ chuẩn tắc revenue(...) đã có sẵn trong sandbox tuân thủ Rulebook §1:
    # Tự động chọn cột thành tiền sau chiết khấu, loại cả đơn hủy/trả, hỗ trợ lọc theo mặt hàng và khoảng thời gian.
    total = revenue(
        data,
        start_date="2026-03-01",
        end_date="2026-03-31",
        as_of_date="2026-06-24",
        product="nước ép dưa hấu (L)",
    )
    return int(round(total))
```""",

    "count_orders": """--- VÍ DỤ: ĐẾM SỐ ĐƠN HÀNG ---
Câu hỏi: "Hôm nay cửa hàng có bao nhiêu đơn hàng?" (as_of_date = "2025-10-18")
```python
def solution(data):
    return int(count_orders(data, start_date="2025-10-18", end_date="2025-10-18", as_of_date="2025-10-18", status="valid"))
```""",

    "cancelled_orders": """--- VÍ DỤ: ĐẾM SỐ ĐƠN BỊ HỦY ---
Câu hỏi: "Đếm số đơn đã huỷ trong tháng 12/2025" (as_of_date = "2026-06-02")
```python
def solution(data):
    return int(count_orders(data, start_date="2025-12-01", end_date="2025-12-31", as_of_date="2026-06-02", status="cancelled"))
```""",

    "quantity_sum": r"""--- VÍ DỤ: TÍNH TỔNG SỐ LƯỢNG MẶT HÀNG ĐÃ BÁN ---
Câu hỏi: "Trong tháng 5/2025 cửa hàng bán được bao nhiêu kg thép cuộn phi 6 Hòa Phát?" (as_of_date = "2026-05-16")
```python
def solution(data):
    df = get_sales_table(data)
    if df is None or df.empty:
        return 0
    d_c, q_c, i_c = get_date_col(df), get_qty_col(df), get_item_col(df)
    if not (d_c and q_c and i_c):
        return 0
    df['clean_date'] = clean_date(df[d_c])
    df = filter_valid_sales(df)
    df = df[(df['clean_date'].dt.year == 2025) & (df['clean_date'].dt.month == 5)]
    matched = df[df[i_c].astype(str).str.contains(r'thép cuộn.*phi\s*6', case=False, regex=True, na=False)]
    return int(round(clean_num(matched[q_c]).sum()))
```""",

    "price_lookup": r"""--- VÍ DỤ: TRA CỨU ĐƠN GIÁ MẶT HÀNG ---
Câu hỏi: "Giá bán một ly soda chanh dây (M) vào ngày 01/12/2025 là bao nhiêu?" (as_of_date = "2026-07-31")
```python
def solution(data):
    for df in data.values():
        cols = df.columns.tolist()
        i_c = next((c for c in cols if any(k in str(c).lower() for k in ['tên hàng', 'sản phẩm', 'mặt hàng', 'tên món'])), None)
        p_c = next((c for c in cols if any(k in str(c).lower() for k in ['đơn giá', 'giá bán', 'giá mới', 'giá'])), None)
        if i_c and p_c:
            m = df[i_c].astype(str).str.contains('soda chanh dây', case=False, na=False) & df[i_c].astype(str).str.contains(r'\(m\)|\bm\b', case=False, regex=True, na=False)
            matched = df[m]
            if not matched.empty:
                return int(round(clean_num(matched[p_c]).iloc[0]))
    return 0
```""",

    "multitable_join": r"""--- VÍ DỤ: DOANH THU THEO MẶT HÀNG (GHÉP BẢNG) ---
Câu hỏi: "Tháng 8/2025 cửa hàng thu được bao nhiêu tiền từ mặt hàng thép cuộn phi 6?" (as_of_date = "2026-06-25")
```python
def solution(data):
    total = revenue(data, start_date="2025-08-01", end_date="2025-08-31", as_of_date="2026-06-25", product=r"thép cuộn.*phi\s*6")
    return int(round(total))
```""",

    "relational_join": r"""--- VÍ DỤ: GHÉP NỐI BẢNG HEADER & DETAIL (TOP HÀNG BÁN CHẠY) ---
Câu hỏi: "Tháng 11/2025 top 5 hàng bán chạy nhất là gì?" (as_of_date = "2026-06-25")
```python
def solution(data):
    df_hdr = next((df for n, df in data.items() if any(k in str(c).lower() for c in df.columns for k in ['ngày', 'date', 'thời gian']) and not any(k in str(n).lower() for k in ['nhap', 'kho', 'chiphi'])), None)
    df_det = next((df for n, df in data.items() if any(k in str(c).lower() for c in df.columns for k in ['tên hàng', 'sản phẩm']) and any(k in str(c).lower() for c in df.columns for k in ['số lượng', 'sl'])), None)
    if df_hdr is None or df_det is None:
        return []
    kh = next(c for c in df_hdr.columns if any(k in str(c).lower() for k in ['mã đơn', 'mã hóa đơn', 'order_id', 'mã']))
    kd = next(c for c in df_det.columns if any(k in str(c).lower() for k in ['mã đơn', 'mã hóa đơn', 'order_id', 'mã']))
    dh = get_date_col(df_hdr)
    merged = pd.merge(df_det, df_hdr[[kh, dh]], left_on=kd, right_on=kh)
    merged['clean_date'] = clean_date(merged[dh])
    p_c, q_c = get_item_col(merged), get_qty_col(merged)
    df_p = merged[(merged['clean_date'].dt.year == 2025) & (merged['clean_date'].dt.month == 11)]
    if df_p.empty:
        return []
    grp = df_p.groupby(p_c, as_index=False)[q_c].apply(lambda s: clean_num(s).sum())
    return grp.sort_values(by=[q_c, p_c], ascending=[False, True]).head(5)[p_c].astype(str).tolist()
```""",

    "delivery_batches": """--- VÍ DỤ: ĐẾM SỐ ĐỢT GIAO HÀNG ---
Câu hỏi: "Tháng này cửa hàng đã chở giao bao nhiêu đợt hàng cho khách nhỉ?" (as_of_date = "2026-09-07")
```python
def solution(data):
    df_del = next((df for n, df in data.items() if any(k in str(n).lower() for k in ['giaohang', 'vanchuyen', 'chohang'])), None)
    if df_del is None:
        raise CannotAnswer("Không tìm thấy bảng giao hàng / vận chuyển")
    d_c = get_date_col(df_del)
    df_del['clean_date'] = clean_date(df_del[d_c])
    df_p = df_del[(df_del['clean_date'].dt.year == 2026) & (df_del['clean_date'].dt.month == 9) & (df_del['clean_date'] <= '2026-09-07')]
    if df_p.empty:
        return 0
    ord_c = next((c for c in df_del.columns if any(k in str(c).lower() for k in ['mã đơn', 'mã bill', 'mã phiếu', 'order_id'])), None)
    trip_c = next((c for c in df_del.columns if any(k in str(c).lower() for k in ['lượt giao', 'đợt giao', 'lần giao'])), None)
    if ord_c and trip_c:
        return int(len(df_p[[ord_c, trip_c]].drop_duplicates()))
    return int(df_p[trip_c or ord_c].dropna().nunique()) if (trip_c or ord_c) else len(df_p)
```""",

    "shift_revenue": r"""--- VÍ DỤ: DOANH THU THEO CA (CA CHIỀU) ---
Câu hỏi: "Ca chiều tuần trước doanh thu bao nhiêu?" (as_of_date = "2026-06-25")
```python
def solution(data):
    df = get_sales_table(data)
    if df is None:
        raise CannotAnswer("Không tìm thấy bảng bán hàng")
    t_c = next((c for c in df.columns if any(k in str(c).lower() for k in ['thời gian tạo', 'created_at', 'giờ', 'thoigian']) and 'ngày' not in str(c).lower()), get_date_col(df))
    amt_c = get_amount_col(df)
    df['clean_dt'] = clean_date(df[t_c])
    df_p = df[(df['clean_dt'].dt.date >= pd.to_datetime('2026-06-08').date()) & (df['clean_dt'].dt.date <= pd.to_datetime('2026-06-14').date())]
    df_shift = df_p[(df_p['clean_dt'].dt.hour >= 14) & (df_p['clean_dt'].dt.hour <= 21)]
    if df_shift.empty:
        return 0
    return int(round(clean_num(df_shift[amt_c]).sum()))
```""",

    "ranking_topk": """--- VÍ DỤ: XẾP HẠNG TOP 5 HÀNG BÁN CHẠY ---
Câu hỏi: "Tháng 9/2025 top 5 hàng bán chạy nhất là gì?" (as_of_date = "2026-09-03")
```python
def solution(data):
    df = get_sales_table(data)
    if df is None:
        raise CannotAnswer("Không tìm thấy bảng bán hàng")
    d_c, p_c, q_c = get_date_col(df), get_item_col(df), get_qty_col(df)
    code_c = next((c for c in df.columns if any(k in str(c).lower() for k in ['mã hàng', 'mã hh', 'mã sp'])), p_c)
    df['clean_date'] = clean_date(df[d_c])
    df_p = df[(df['clean_date'].dt.year == 2025) & (df['clean_date'].dt.month == 9)]
    if df_p.empty:
        return []
    grp = df_p.groupby([p_c, code_c], as_index=False)[q_c].apply(lambda s: clean_num(s).sum()).rename(columns={q_c: 'total_qty'})
    grp = grp.sort_values(by=['total_qty', code_c], ascending=[False, True])
    return grp.head(5)[p_c].astype(str).tolist()
```""",

    "ranking_customer": """--- VÍ DỤ: TOP KHÁCH HÀNG CHI TIÊU NHIỀU NHẤT ---
Câu hỏi: "Liệt kê 3 khách chi tiêu nhiều nhất trong tháng 6 năm 2025" (as_of_date = "2026-06-16")
```python
def solution(data):
    df = get_sales_table(data)
    if df is None:
        raise CannotAnswer("Không tìm thấy bảng bán hàng")
    d_c, a_c = get_date_col(df), get_amount_col(df)
    c_c = next((c for c in df.columns if any(k in str(c).lower() for k in ['tên khách', 'khách hàng', 'customer', 'tên kh'])), None)
    if not c_c:
        raise CannotAnswer("Không tìm thấy cột khách hàng")
    code_c = next((c for c in df.columns if any(k in str(c).lower() for k in ['mã khách', 'mã kh', 'makh'])), c_c)
    df['clean_date'] = clean_date(df[d_c])
    df_p = df[(df['clean_date'].dt.year == 2025) & (df['clean_date'].dt.month == 6)]
    df_p = df_p[~df_p[c_c].astype(str).str.contains(r'lẻ|khách lẻ|nan|none|^$', case=False, na=False)]
    if df_p.empty:
        return []
    grp = df_p.groupby([c_c, code_c], as_index=False)[a_c].apply(lambda s: clean_num(s).sum()).rename(columns={a_c: 'total_amt'})
    grp = grp.sort_values(by=['total_amt', code_c], ascending=[False, True])
    return grp.head(3)[c_c].astype(str).tolist()
```""",

    "average_order_value": """--- VÍ DỤ: GIÁ TRỊ TRUNG BÌNH MỘT ĐƠN HÀNG (AOV) ---
Câu hỏi: "Giá trị trung bình một đơn tháng 10/2025 là bao nhiêu?" (as_of_date = "2026-05-29")
```python
def solution(data):
    df = get_sales_table(data)
    if df is None:
        raise CannotAnswer("Không tìm thấy bảng bán hàng")
    d_c, a_c = get_date_col(df), get_amount_col(df)
    o_c = next((c for c in df.columns if any(k in str(c).lower() for k in ['mã đơn', 'mã hóa đơn', 'mã hd', 'order_id'])), None)
    df['clean_date'] = clean_date(df[d_c])
    df_p = df[(df['clean_date'].dt.year == 2025) & (df['clean_date'].dt.month == 10)]
    if df_p.empty:
        return 0
    df_p['clean_amt'] = clean_num(df_p[a_c])
    aov = df_p.groupby(o_c)['clean_amt'].sum().mean() if o_c else df_p['clean_amt'].mean()
    return int(round(aov))
```""",

    "rate_percentage": """--- VÍ DỤ: TỈ LỆ PHẦN TRĂM (%) ---
Câu hỏi: "Tháng 6/2026 tỉ lệ hủy đơn là bao nhiêu phần trăm?" (as_of_date = "2026-06-30")
```python
def solution(data):
    df = get_sales_table(data)
    if df is None:
        raise CannotAnswer("Không tìm thấy bảng bán hàng")
    d_c = get_date_col(df)
    s_c = next((c for c in df.columns if any(k in str(c).lower() for k in ['trạng thái', 'status', 'tình trạng'])), None)
    o_c = next((c for c in df.columns if any(k in str(c).lower() for k in ['mã đơn', 'mã hd', 'order_id'])), None)
    if not s_c:
        raise CannotAnswer("Không tìm thấy cột trạng thái đơn hàng")
    df['clean_date'] = clean_date(df[d_c])
    df_p = df[(df['clean_date'] >= '2026-06-01') & (df['clean_date'] <= '2026-06-30 23:59:59')]
    if df_p.empty:
        return 0.0
    cancel_mask = df_p[s_c].astype(str).str.contains(r'hủy|huỷ|huy|cancel', case=False, na=False)
    total_orders = df_p[o_c].dropna().nunique() if o_c else len(df_p)
    cancel_orders = df_p[cancel_mask][o_c].dropna().nunique() if o_c else int(cancel_mask.sum())
    if total_orders == 0:
        return 0.0
    return round(float(cancel_orders / total_orders * 100.0), 2)
```""",

    "category_share_percentage": """--- VÍ DỤ MINH HỌA: TỈ TRỌNG DOANH THU NHÓM HÀNG / MẶT HÀNG (%) ---
Câu hỏi: "Tỉ trọng của nhóm cát đá trong doanh thu tháng 8/2026 là bao nhiêu %?" (as_of_date = "2026-09-04")
```python
def solution(data):
    # Dùng hàm chuẩn revenue() đã tự động xử lý chiết khấu dòng, loại đơn hủy/trả và khớp theo Tên hàng / Nhóm hàng
    rev_group = revenue(data, start_date="2026-08-01", end_date="2026-08-31", product="Cát đá")
    rev_total = revenue(data, start_date="2026-08-01", end_date="2026-08-31")
    if rev_total == 0:
        return 0.0
    return round(float(rev_group / rev_total * 100.0), 2)
```""",

    "price_increase_impact": """--- VÍ DỤ: TÁC ĐỘNG TĂNG GIÁ (%) ---
Câu hỏi: "So số ly Cà phê muối bán ra trong 30 ngày kể từ ngày 2026-04-09 với 30 ngày ngay trước ngày đó: tăng hay giảm bao nhiêu %?" (as_of_date = "2026-06-27")
```python
def solution(data):
    df = get_sales_table(data)
    if df is None:
        raise CannotAnswer("Không tìm thấy bảng bán hàng")
    d_c, p_c = get_date_col(df), get_item_col(df)
    q_c = next((c for c in df.columns if 'quy đổi' in str(c).lower()), None) or get_qty_col(df)
    df['clean_date'] = clean_date(df[d_c])
    matched = df[df[p_c].astype(str).str.contains('Cà phê muối', case=False, na=False)]
    if matched.empty:
        raise CannotAnswer("Không tìm thấy sản phẩm Cà phê muối trong lịch sử")
    m_after = (matched['clean_date'] >= '2026-04-09') & (matched['clean_date'] <= '2026-05-08 23:59:59')
    m_before = (matched['clean_date'] >= '2026-03-10') & (matched['clean_date'] <= '2026-04-08 23:59:59')
    q_after = clean_num(matched[m_after][q_c]).sum()
    q_before = clean_num(matched[m_before][q_c]).sum()
    if q_before == 0:
        return 0.0
    return round(float(((q_after - q_before) / q_before) * 100.0), 2)
```""",

    "table_debt": """--- VÍ DỤ: BẢNG TOP KHÁCH HÀNG NỢ (TABLE DICT) ---
Câu hỏi: "Cho danh sách 3 khách hàng đang nợ nhiều nhất kèm số tiền còn nợ hiện tại?" (as_of_date = "2026-06-30")
```python
def solution(data):
    df_no = next((df for n, df in data.items() if any(k in str(n).lower() for k in ['no', 'congno', 'khachno'])), None)
    if df_no is None:
        raise CannotAnswer("Không tìm thấy bảng công nợ")
    cols = df_no.columns.tolist()
    c_cust = next((c for c in cols if any(k in str(c).lower() for k in ['khách', 'người nợ', 'tên kh'])), None)
    c_rem = next((c for c in cols if any(k in str(c).lower() for k in ['còn nợ', 'dư nợ', 'phải thu'])), None)
    df_no['clean_debt'] = clean_num(df_no[c_rem])
    grp = df_no.groupby(c_cust, as_index=False)['clean_debt'].sum()
    grp = grp[grp['clean_debt'] > 0].sort_values(by=['clean_debt', c_cust], ascending=[False, True]).head(3)
    rows = [[str(r[c_cust]).strip(), int(round(r['clean_debt']))] for _, r in grp.iterrows()]
    return {'columns': ['khach_hang', 'so_tien_no'], 'rows': rows}
```""",

    "date_peak_revenue": """--- VÍ DỤ: TÌM NGÀY DOANH THU CAO NHẤT ('YYYY-MM-DD') ---
Câu hỏi: "Trong tháng 8/2025, ngày nào cửa hàng có doanh thu cao nhất?" (as_of_date = "2026-06-30")
```python
def solution(data):
    df = get_sales_table(data)
    if df is None:
        raise CannotAnswer("Không tìm thấy bảng bán hàng")
    d_c, a_c = get_date_col(df), get_amount_col(df)
    df['clean_date'] = clean_date(df[d_c])
    df_p = df[(df['clean_date'] >= '2025-08-01') & (df['clean_date'] <= '2025-08-31 23:59:59')].copy()
    if df_p.empty:
        raise CannotAnswer("Không có dữ liệu bán hàng tháng 8/2025")
    df_p['day_str'] = df_p['clean_date'].dt.strftime('%Y-%m-%d')
    daily = df_p.groupby('day_str', as_index=False)[a_c].apply(lambda s: clean_num(s).sum()).rename(columns={a_c: 'total'})
    return str(daily.sort_values(by=['total', 'day_str'], ascending=[False, True]).iloc[0]['day_str'])
```""",

    "inventory_unit_conversion": """--- VÍ DỤ: TỒN KHO & QUY ĐỔI ĐƠN VỊ ---
Câu hỏi: "Sản phẩm Hapacol 650 còn tồn bao nhiêu hộp chẵn và bao nhiêu viên lẻ?" (as_of_date = "2026-07-31")
```python
def solution(data):
    df_stock = next((df for n, df in data.items() if any(k in str(n).lower() for k in ['tonkho', 'kho', 'thekho'])), None)
    if df_stock is None:
        raise CannotAnswer("Không tìm thấy bảng tồn kho")
    p_c = get_item_col(df_stock)
    rem_c = next((c for c in df_stock.columns if any(k in str(c).lower() for k in ['tồn cuối', 'tồn kho', 'tồn thực'])), None)
    unit_c = next((c for c in df_stock.columns if any(k in str(c).lower() for k in ['quy cách', 'đơn vị', 'đvt'])), None)
    matched = df_stock[df_stock[p_c].astype(str).str.contains('hapacol 650', case=False, na=False)]
    if matched.empty:
        raise CannotAnswer("Không tìm thấy sản phẩm Hapacol 650 trong danh mục")
    total_units = int(round(clean_num(matched[rem_c]).iloc[0]))
    pack = 100
    if unit_c and not matched[unit_c].isna().all():
        m = re.search(r'\d+', str(matched[unit_c].iloc[0]))
        if m:
            pack = int(m.group(0))
    boxes, pills = divmod(total_units, pack)
    return [int(boxes), int(pills)]
```""",

    "time_series": """--- VÍ DỤ: SO SÁNH TĂNG TRƯỞNG DOANH THU (%) ---
Câu hỏi: "Doanh thu tháng này tăng hay giảm bao nhiêu phần trăm so với tháng trước?" (as_of_date = "2026-05-25")
```python
def solution(data):
    rev_curr = revenue(data, start_date="2026-05-01", end_date="2026-05-25", as_of_date="2026-05-25")
    rev_prev = revenue(data, start_date="2026-04-01", end_date="2026-04-25", as_of_date="2026-05-25")
    if rev_prev == 0:
        return 0.0
    return round(float((rev_curr - rev_prev) / rev_prev * 100.0), 2)
```""",

    "boolean_trend": """--- VÍ DỤ: KIỂM TRA XU HƯỚNG TĂNG LIÊN TỤC (BOOLEAN) ---
Câu hỏi: "Từ tháng 7/2025 qua tháng 8/2025 rồi tháng 9/2025, doanh thu có tăng liên tục không?" (as_of_date = "2026-06-24")
```python
def solution(data):
    r7 = revenue(data, start_date="2025-07-01", end_date="2025-07-31")
    r8 = revenue(data, start_date="2025-08-01", end_date="2025-08-31")
    r9 = revenue(data, start_date="2025-09-01", end_date="2025-09-30")
    return bool(r7 < r8 < r9)
```""",

    "unanswerable_suspect": """--- VÍ DỤ MINH HỌA: CÂU HỎI THIẾU DỮ LIỆU HOẶC KHÔNG THỂ TRẢ LỜI ---
Câu hỏi: "Nhân viên nào có tay nghề cao nhất tiệm?" (as_of_date = "2026-07-31")
```python
def solution(data):
    has_skill = any('tay nghề' in str(c).lower() or 'trình độ' in str(c).lower() for df in data.values() for c in df.columns)
    if not has_skill:
        raise CannotAnswer("Dữ liệu cửa hàng không có thông tin về tay nghề hoặc trình độ của nhân viên")
    return None
```""",
}


def retrieve_dynamic_few_shot(question: str, intent: str, entity_matches: Optional[List[Any]] = None) -> str:
    """Truy hồi ví dụ minh họa tối ưu nhất cho câu hỏi."""
    q_low = question.lower()

    if is_table_question(question):
        example = EXEMPLAR_BANK.get("table_debt")
    elif is_boolean_question(question):
        example = EXEMPLAR_BANK.get("boolean_trend")
    elif is_date_question(question):
        example = EXEMPLAR_BANK.get("date_peak_revenue")
    elif any(k in q_low for k in ["ngày tăng giá", "đợt tăng giá", "ngay trước ngày đó"]):
        example = EXEMPLAR_BANK.get("price_increase_impact")
    elif any(k in q_low for k in ["tỉ trọng", "ti trong", "tỷ trọng", "ty trong", "chiếm bao nhiêu %", "chiem bao nhieu %", "chiếm mấy %"]):
        example = EXEMPLAR_BANK.get("category_share_percentage")
    elif any(k in q_low for k in ["khách", "khach"]) and any(k in q_low for k in ["chi tiêu", "chi tieu", "mua nhiều", "nhiều nhất", "top", "cao nhất", "tiêu nhiều", "nhiều tiền"]):
        example = EXEMPLAR_BANK.get("ranking_customer")
    elif intent == "average_order_value" or re.search(r"(?:gi[aá]s?\s*tr[iị]\s*)?trung\s*b[iì]nh\s*(?:m[oộ]t|1)\s*đ[oơ]n|tb\s*(?:m[oộ]t|1)\s*đ[oơ]n|\baov\b", q_low):
        example = EXEMPLAR_BANK.get("average_order_value")
    elif any(k in q_low for k in ["hộp chẵn", "viên lẻ", "thùng và chai", "tồn kho"]):
        example = EXEMPLAR_BANK.get("inventory_unit_conversion")
    elif any(k in q_low for k in ["tăng liên tục", "so với", "cùng kỳ", "cung ky", "thay đổi bao nhiêu", "tăng trưởng", "hơn hay kém", "hon hay kem"]):
        example = EXEMPLAR_BANK.get("time_series")
    elif any(k in q_low for k in ["bán chạy", "nhiều nhất", "top", "cao nhất", "ít nhất", "thấp nhất"]):
        example = EXEMPLAR_BANK.get("ranking_topk")
    elif any(k in q_low for k in ["công nợ", "cong no", "còn nợ", "con no", "tuổi nợ", "hạn nợ", "hạn trả", "phải thu", "khách nợ", "sổ nợ", "chưa trả"]):
        example = EXEMPLAR_BANK.get("cong_no")
    elif any(k in q_low for k in ["nhập hàng", "phiếu nhập", "tiền nhập", "nhap hang", "phieu nhap", "mua hàng", "cần trả ncc", "nhập kho", "nhập vào", "giá nhập", "nhap vao", "gia nhap"]):
        example = EXEMPLAR_BANK.get("purchase_import")
    elif any(k in q_low for k in ["%", "phần trăm", "tỉ lệ", "tỷ lệ"]):
        example = EXEMPLAR_BANK.get("rate_percentage")
    elif any(k in q_low for k in ["đợt giao", "lượt giao", "chở giao", "giao hàng", "dot giao", "đợt hàng"]):
        example = EXEMPLAR_BANK.get("delivery_batches")
    elif any(k in q_low for k in ["ca chiều", "ca sang", "ca sáng", "ca tối", "theo ca"]):
        example = EXEMPLAR_BANK.get("shift_revenue")
    elif any(k in q_low for k in ["hôm nay", "ngày hôm nay", "hom nay", "doanh thu ngày", "doanh số ngày", "trong ngày"]):
        example = EXEMPLAR_BANK.get("daily_revenue", EXEMPLAR_BANK["aggregation"])
    elif intent == "cancelled_orders" or (any(k in q_low for k in ["huỷ", "hủy", "cancel"]) and any(k in q_low for k in ["đơn", "bill", "hoá đơn"])):
        example = EXEMPLAR_BANK.get("cancelled_orders")
    elif intent == "count_orders" or any(k in q_low for k in ["đếm số đơn", "bao nhiêu đơn", "mấy đơn", "co bao nhiu don"]):
        example = EXEMPLAR_BANK.get("count_orders")
    elif intent == "price_lookup" or any(k in q_low for k in ["giá bán", "gia ban", "đơn giá", "bao nhiêu tiền một", "bn một"]):
        example = EXEMPLAR_BANK.get("price_lookup")
    elif intent == "quantity_sum" or any(k in q_low for k in ["mấy ly", "bao nhiêu ly", "mấy kg", "bao nhiêu kg"]):
        example = EXEMPLAR_BANK.get("quantity_sum")
    elif intent == "multitable_join" or any(k in q_low for k in ["hoạt chất", "kê đơn", "ghép bảng", "chi tiết đơn", "thép"]):
        example = EXEMPLAR_BANK.get("multitable_join")
    elif intent in EXEMPLAR_BANK:
        example = EXEMPLAR_BANK[intent]
    else:
        example = EXEMPLAR_BANK["aggregation"]

    return f"""==================== VÍ DỤ MINH HỌA PHÙ HỢP NHẤT ====================
{example}
"""


FEW_SHOT_LIBRARY: Dict[str, str] = EXEMPLAR_BANK


def select_few_shots(intent: str) -> str:
    """Chọn ví dụ mẫu tương thích ngược."""
    example = FEW_SHOT_LIBRARY.get(intent) or FEW_SHOT_LIBRARY.get("aggregation", "")
    return f"==================== VÍ DỤ MINH HỌA PHÙ HỢP NHẤT ====================\n{example}\n"


# ==============================================================================
# 7. BỘ NHỚ SCHEMA LIÊN CÂU HỎI (EPISODIC SHOP MEMORY) & BUILD_PROMPT
# ==============================================================================

class ShopExecutionMemory:
    """Bộ nhớ nhẹ theo từng business_id (chỉ lưu chuỗi) giúp tránh lặp lại lỗi schema giữa các câu hỏi cùng shop."""

    def __init__(self, max_items_per_shop: int = 5):
        self._max_items = max_items_per_shop
        self._store: Dict[str, Dict[str, List[str]]] = {}

    def _entry(self, business_id: str) -> Dict[str, List[str]]:
        if business_id not in self._store:
            self._store[business_id] = {"verified_refs": [], "avoid_hints": []}
        return self._store[business_id]

    @staticmethod
    def _append_unique(lst: List[str], item: str, cap: int) -> None:
        item_clean = item.strip()
        if not item_clean or item_clean in lst:
            return
        lst.append(item_clean)
        if len(lst) > cap:
            del lst[0]

    def record_attempt(self, business_id: str, code: str, error_msg: Optional[str] = None) -> None:
        """Ghi nhận bảng/cột đã chạy thành công hoặc lỗi KeyError/bảng cần tránh cho các câu hỏi sau của cùng shop."""
        if not business_id:
            return
        entry = self._entry(str(business_id))
        if error_msg:
            err_str = str(error_msg)
            m_key = re.search(r"KeyError\s*:\s*['\"]([^'\"]{1,60})['\"]", err_str)
            if m_key:
                self._append_unique(
                    entry["avoid_hints"],
                    f"Cột/khóa '{m_key.group(1)}' không tồn tại trực tiếp; hãy kiểm tra tên cột thực trong schema.",
                    self._max_items,
                )
            elif "DataNotFound" in err_str or "not found" in err_str.lower():
                first_line = err_str.splitlines()[0][:110]
                self._append_unique(entry["avoid_hints"], f"Tránh lặp lỗi truy cập: {first_line}", self._max_items)
            return

        if not code or "return None" in code:
            return
        # Trích tên bảng đã truy cập thành công qua data['...']
        for tbl_name in re.findall(r"data\s*\[\s*['\"]([^'\"]{2,50})['\"]\s*\]", code):
            self._append_unique(entry["verified_refs"], f"data['{tbl_name}']", self._max_items)
        # Ghi nhận các helper nghiệp vụ đã chạy sạch
        for helper in ("revenue(", "count_orders(", "debt(", "get_sales_table("):
            if helper in code:
                self._append_unique(entry["verified_refs"], f"helper {helper[:-1]}()", self._max_items)

    def get_hints(self, business_id: str, max_chars: int = 350) -> str:
        """Trả về gợi ý schema ngắn gọn tích lũy từ các câu hỏi trước của cùng cửa hàng."""
        entry = self._store.get(str(business_id)) if business_id else None
        if not entry:
            return ""
        lines: List[str] = []
        if entry["verified_refs"]:
            lines.append("- Đã xác minh chạy đúng trên shop này: " + ", ".join(entry["verified_refs"][:4]))
        for hint in entry["avoid_hints"][-3:]:
            lines.append(f"- Cảnh báo từ lượt trước: {hint}")
        text = "\n".join(lines).strip()
        return text[:max_chars] if len(text) > max_chars else text


def build_prompt(
    schema_str: str,
    as_of_date: str,
    question: str,
    rulebook_content: Optional[str] = None,
    business_note: Optional[str] = None,
    candidates: Optional[List[Any]] = None,
    entity_matches: Optional[List[Any]] = None,
    return_messages: bool = False,
    force_full_schema: bool = False,
    calendar_path: Optional[str] = None,
    shop_memory_hints: Optional[str] = None,
) -> Any:
    """Ráp nối toàn bộ thông tin thành Prompt tinh gọn cho mô hình Qwen2.5-Coder-3B."""
    intent = classify_intent(question)
    few_shot_block = retrieve_dynamic_few_shot(question=question, intent=intent, entity_matches=entity_matches)

    if force_full_schema:
        active_schema = schema_str
    else:
        active_schema = prune_schema_by_intent(
            schema_str=schema_str,
            intent=intent,
            question=question,
            entity_matches=entity_matches,
        )

    temporal_info = resolve_temporal_context(question, as_of_date, calendar_path=calendar_path)
    temporal_text = format_temporal_for_prompt(temporal_info)

    entity_block = ""
    matches = entity_matches
    if matches is None and candidates and link_entities is not None:
        try:
            matches = link_entities(question, candidates=candidates, threshold=0.55)
        except Exception:
            matches = None

    if matches:
        q_unacc = _strip_accents(question).lower()
        entity_lines = []
        for m in matches[:5]:
            val = getattr(m, "matched_value", str(m))
            term = getattr(m, "query_term", "")
            score = getattr(m, "score", 1.0)
            meta = getattr(m, "metadata", {}) or {}

            # Không in mục "THỰC THỂ" nếu câu hỏi không chứa thực thể (kiểm tra độ xuất hiện trong câu hỏi)
            val_unacc = _strip_accents(val).lower()
            term_unacc = _strip_accents(term).lower() if term else ""
            _stop_words = {"bao", "thung", "chai", "hop", "goi", "lon", "cai", "chiec", "kg", "gam", "lit", "ngay", "thang", "nam", "tong", "tien", "so", "don", "hang", "san", "pham", "khach", "loai"}
            val_words = [w for w in re.findall(r"\w+", val_unacc) if len(w) >= 3 and w not in _stop_words]

            has_in_question = (
                (term_unacc and len(term_unacc) >= 3 and term_unacc in q_unacc)
                or (val_unacc and len(val_unacc) >= 4 and val_unacc in q_unacc)
                or (val_words and any(w in q_unacc for w in val_words))
            )
            if not has_in_question or score < 0.60:
                continue

            src_tbl = meta.get("source_table", "")
            src_col = meta.get("source_col", "")
            loc = f" (ở bảng '{src_tbl}', cột '{src_col}')" if src_tbl and src_col else ""
            term_note = f" (từ '{term}')" if term and term.lower() != val.lower() else ""

            row_ctx = meta.get("row_context") or {}
            ctx_items = []
            for k, v in row_ctx.items():
                k_clean = str(k).strip()
                v_clean = str(v).strip()
                if not v_clean or v_clean.lower() in ("nan", "none", "null"):
                    continue
                if src_col and k_clean.lower() == src_col.lower():
                    continue
                if k_clean.lower() in ("tên hàng", "tên sản phẩm", "ten_hang", "tên thuốc") and v_clean.lower() == val.lower():
                    continue
                ctx_items.append(f"{k_clean}: {v_clean}")
            ctx_str = f" [Thông tin: {', '.join(ctx_items)}]" if ctx_items else ""

            entity_lines.append(f"- '{val}'{loc}{term_note}{ctx_str}")

        if entity_lines:
            entity_block = (
                "\nTHỰC THỂ KHỚP TRONG CSDL (ENTITY LINKING):\n"
                + "\n".join(entity_lines)
                + "\n-> LƯU Ý: Dùng chính xác các giá trị chuỗi hoặc Mã hàng / SKU tương ứng khi lọc trong code.\n"
            )

    rulebook_block = ""
    if rulebook_content and rulebook_content.strip():
        rb_text = extract_relevant_rulebook_clauses(
            rulebook_content,
            question,
            max_chars=220,
            schema_str=active_schema,
            business_note=business_note or "",
        )
        if rb_text:
            rulebook_block = f"\n{rb_text}\n"

    biz_context = ""
    if business_note and business_note.strip():
        note_str = business_note.strip()
        if len(note_str) > 500:
            if "## Quy ước" in note_str:
                note_str = "## Quy ước" + note_str.split("## Quy ước")[-1][:500]
            elif "## Quy định" in note_str:
                note_str = "## Quy định" + note_str.split("## Quy định")[-1][:500]
            else:
                note_str = note_str[:500]
        biz_context = f"\nGHI CHÚ DOANH NGHIỆP:\n{note_str}\n"

    if shop_memory_hints and shop_memory_hints.strip():
        biz_context += f"\nKINH NGHIỆM SCHEMA ĐÃ XÁC MINH CHO CỬA HÀNG NÀY:\n{shop_memory_hints.strip()}\n"

    req_3 = "3. Ưu tiên gọi các hàm nghiệp vụ tất định có sẵn trong sandbox: `revenue(data, start_date=..., end_date=..., as_of_date=..., product=...)` để tính doanh thu, `count_orders(data, start_date=..., end_date=..., status='valid'|'cancelled')` để đếm đơn, và `debt(data, end_date=...)` để tính công nợ."
    if intent in ("count_orders", "cancelled_orders"):
        req_3 += " Khi đếm đơn, tìm cột mã đơn order_col = next(...) và đếm int(df[order_col].dropna().nunique()). TUYỆT ĐỐI CẤM dùng len(df) hay df.shape[0]!"
    elif intent == "quantity_sum":
        req_3 += " Khi tính số lượng (ly, kg), BẮT BUỘC tìm cột số lượng qty_col = next(...) và tính tổng int(round(clean_num(df[qty_col]).sum())). TUYỆT ĐỐI CẤM tính tổng cột tiền."
    elif intent == "price_lookup":
        req_3 += " Khi tra cứu giá, tìm cột đơn giá / giá bán của đúng sản phẩm. TUYỆT ĐỐI CẤM tính trung bình toàn bộ danh mục df['Giá bán'].mean() và TUYỆT ĐỐI CẤM tính tổng doanh thu."

    shop_static_prefix = (
        "==================== HỒ SƠ SCHEMA & GHI CHÚ CỬA HÀNG (STATIC SHOP PREFIX) ====================\n"
        f"DANH SÁCH BẢNG VÀ CỘT DỮ LIỆU TRONG `data`:\n{active_schema}\n{biz_context}".strip()
    )
    dynamic_sys_instruction = build_dynamic_system_instruction(
        intent=intent,
        question=question,
        shop_static_prefix=shop_static_prefix,
    )
    system_prompt = f"{dynamic_sys_instruction}\n{rulebook_block}\n{few_shot_block}".strip()

    return_format_instruction = get_return_format_instruction(question, for_retry=False)

    user_prompt = f"""==================== CÂU HỎI & RÀNG BUỘC CỐT LÕI ====================
CÂU HỎI CỦA NGƯỜI DÙNG:
"{question}"

RÀNG BUỘC MỐC THỜI GIAN & THỰC THỂ:
{temporal_text}
{entity_block}
YÊU CẦU THỰC HIỆN:
1. Quan sát danh sách bảng và cột ở System Prompt để chọn đúng bảng và cột. Không đoán tên bảng có ký tự lạ.
2. Áp dụng khoảng thời gian đã được giải mã và mốc as_of_date để lọc dữ liệu.
{req_3}
{return_format_instruction}
5. Chỉ viết duy nhất một hàm `def solution(data):` trả về kết quả, không viết giải thích bên ngoài.
6. Viết code ngắn gọn, không viết comment dài dòng để tránh bị cắt cụt token.
"""

    if return_messages:
        return system_prompt, user_prompt

    return f"{system_prompt}\n\n{user_prompt}"


def build_retry_prompt(
    question: str,
    failed_code: str,
    error_message: str,
    schema_str: str,
    as_of_date: str,
    temporal_text: Optional[str] = None,
    retry_round: int = 1,
    missed_mentions: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, str]:
    """Xây dựng prompt tự sửa lỗi (Self-Correction) siêu gọn, hỗ trợ feedback thực thể bị bỏ sót."""
    retry_format_instruction = get_return_format_instruction(question, for_retry=True)
    retry_sys_prompt = f"""Bạn là chuyên gia sửa lỗi mã nguồn Python/Pandas phân tích dữ liệu.
Nhiệm vụ: Sửa lỗi mã nguồn vừa sinh và viết lại duy nhất một hàm hoàn chỉnh:
```python
def solution(data):
    # logic tính toán an toàn đã sửa lỗi
    return result
```
NGUYÊN TẮC:
- Quan sát lỗi gặp phải và sửa đúng dòng bị sai.
- Dùng các tiện ích đã có sẵn: `clean_num`, `clean_date`, `apply_tie_breaker`, `filter_future_data`.
- TUYỆT ĐỐI DÙNG `clean_date(df[date_col])` và lọc `df['clean_date'].dt.year`, `df['clean_date'].dt.month`. TUYỆT ĐỐI CẤM gọi `.dt.date` trước `.dt.year` hoặc `.dt.month` (vì `.dt.date` sinh ra Series object mất accessor `.dt`)!
- Khi câu hỏi hỏi về ngày cụ thể (hôm nay, ngày X), BẮT BUỘC lọc `df['clean_date'].dt.date == pd.to_datetime(target_date).date()` trước khi tính toán!
- Khi đếm số đơn (`bao nhiêu đơn`, `số đơn`, `đơn huỷ`), BẮT BUỘC đếm theo cột mã đơn `int(df[order_col].dropna().nunique())`, TUYỆT ĐỐI KHÔNG đếm trên cột ngày tháng!
- Khi tính số lượng (`ly`, `kg`), BẮT BUỘC tính tổng cột số lượng `qty_col`, KHÔNG tính tổng cột tiền!
- Khi tra cứu đơn giá, BẮT BUỘC lọc theo tên sản phẩm để lấy `Giá bán`. TUYỆT ĐỐI CẤM tính trung bình `df['Giá bán'].mean()` trên toàn bộ bảng danh mục!
- Nếu câu hỏi hỏi sản phẩm cụ thể, BẮT BUỘC lọc theo tên sản phẩm trước khi tính toán!
{retry_format_instruction}
- Không hardcode tên cột cố định (như `trang_thai`). Dùng `next(...)` để tìm cột động nếu gặp KeyError.
- Không viết giải thích ngoài lề, chỉ trả về khối ```python ... ```."""

    clean_failed_code = failed_code.strip() if failed_code else "# Không có code"
    if len(clean_failed_code) > 2000:
        clean_failed_code = clean_failed_code[:2000] + "\n    # ... [đoạn sau được rút gọn]"

    temporal_info_str = f"\nRÀNG BUỘC THỜI GIAN:\n{temporal_text}\n" if temporal_text else ""

    missed_block = ""
    if missed_mentions:
        hints = []
        for m in missed_mentions[:3]:
            if isinstance(m, dict):
                t = m.get("term", "")
                c = m.get("candidate", "")
                col = m.get("col", "")
                tbl = m.get("table", "")
                loc = f" ở bảng '{tbl}', cột '{col}'" if tbl and col else ""
                hints.append(f"- '{t}' (giá trị thực tế: '{c}'{loc})")
            else:
                hints.append(f"- '{str(m)}'")
        if hints:
            missed_block = (
                "\n⚠️ GỢI Ý THỰC THỂ BỎ SÓT: Câu hỏi nhắc tới các thực thể sau nhưng mã trước chưa áp dụng:\n"
                + "\n".join(hints)
                + "\n-> Bắt buộc bổ sung điều kiện lọc hoặc truy vấn chính xác các thực thể này trong code.\n"
            )

    retry_user_prompt = f"""==================== THÔNG TIN SỬA LỖI (SELF-CORRECTION VÒNG {retry_round}) ====================
DANH SÁCH BẢNG VÀ CỘT DỮ LIỆU ĐẦY ĐỦ TRONG `data`:
{schema_str}

CÂU HỎI CỦA NGƯỜI DÙNG:
"{question}"
(Mốc tham chiếu as_of_date: {as_of_date})
{temporal_info_str}{missed_block}
==================== MÃ NGUỒN VỪA SINH BỊ LỖI ====================
```python
{clean_failed_code}
```

==================== CHI TIẾT LỖI GẶP PHẢI ====================
{error_message}

HƯỚNG DẪN SỬA LỖI:
1. Đọc kỹ chi tiết lỗi ở trên (KeyError, DataNotFoundError, TypeError, logic sai lệch).
2. Kiểm tra danh sách bảng và cột thực tế trong data để chọn đúng cột và bảng:
   - Ưu tiên dùng các hàm helper tích hợp sẵn: `revenue(...)`, `count_orders(...)`, `debt(...)`, `get_sales_table(...)`.
   - Nếu thiếu bảng/cột cần thiết hoặc thực thể không tồn tại trong toàn bộ lịch sử cửa hàng: BẮT BUỘC `raise CannotAnswer("lý do")`. Chỉ return 0 khi thực thể có tồn tại nhưng không phát sinh giao dịch trong kỳ được hỏi.
3. Viết lại hàm `def solution(data):` hoàn chỉnh, ngắn gọn, trực diện:
```python
"""
    return retry_sys_prompt.strip(), retry_user_prompt


__all__ = [
    "build_prompt",
    "build_retry_prompt",
    "classify_intent",
    "prune_schema_by_intent",
    "build_dynamic_system_instruction",
    "resolve_temporal_context",
    "get_tet_dates_from_calendar",
    "extract_relevant_rulebook_clauses",
    "retrieve_dynamic_few_shot",
    "is_boolean_question",
    "is_table_question",
    "is_date_question",
    "is_numeric_list_question",
    "is_topk_list_question",
    "is_top1_string_question",
    "get_return_format_instruction",
    "EXEMPLAR_BANK",
    "FEW_SHOT_LIBRARY",
    "select_few_shots",
    "TET_SOLAR_RANGES",
    "load_rulebook",
    "ShopExecutionMemory",
]
