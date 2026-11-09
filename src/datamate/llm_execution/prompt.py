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
    from datamate.grounding_feasibility.rulebook import load_rulebook
except ImportError:
    def load_rulebook(split_dir: Optional[str] = None) -> str:
        if split_dir:
            p = Path(split_dir) / "rulebook.md"
            if p.exists():
                return p.read_text(encoding="utf-8")
        return ""

try:
    from datamate.grounding_feasibility.temporal import (
        TET_SOLAR_RANGES,
        get_calendar,
        get_tet_dates_from_calendar,
        parse_date,
        resolve_temporal,
        resolve_temporal_context,
    )
except ImportError:
    resolve_temporal = None
    resolve_temporal_context = None
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

def classify_intent(question: str) -> str:
    """Phân loại câu hỏi thành các nhóm nghiệp vụ chính."""
    q_lower = question.lower()

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
        "nhập hàng", "phiếu nhập", "tiền nhập", "nhap hang", "phieu nhap",
        "phiếu nhập hàng", "tiền mua hàng", "giá trị các phiếu nhập",
        "nhập vào", "giá nhập", "gia nhap", "nhap vao"
    ]) or re.search(r"giá\s*(?:bình\s*quân|trung\s*bình).*nhập|nhập.*giá\s*(?:bình\s*quân|trung\s*bình)", q_lower):
        return "purchase_import"

    if re.search(r"(?:gi[aá]s?\s*tr[iị]\s*)?trung\s*b[iì]nh\s*(?:m[oộ]t|1)\s*đ[oơ]n|tb\s*(?:m[oộ]t|1)\s*đ[oơ]n|\baov\b", q_lower):
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

    if any(k in q_lower for k in [
        "bán chạy nhất", "bán chạy", "nhiều nhất", "nhiều tiền nhất", "cao nhất",
        "thấp nhất", "lời nhất", "đắt nhất", "top", "xếp thứ", "hot nhất", "giỏi nhất"
    ]) or (any(k in q_lower for k in ["khách", "khach"]) and any(k in q_lower for k in ["chi tiêu", "chi tieu", "mua nhiều", "tiêu nhiều"])):
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

        if is_product and any(k in q_low for k in ["sản phẩm", "mặt hàng", "thuốc", "bảng giá", "giá bán", "đơn giá", "món"]):
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
        if is_cust and not explicit_customer and intent not in ("ranking_topk", "ranking_customer", "aggregation", "cancelled_orders", "average_order_value"):
            continue

        kept_names.add(p["name"])

    # --- NGUYÊN TẮC VÀNG 2: BẢO VỆ PHẠM VI THỜI GIAN (Temporal Range Protection) ---
    # Đảm bảo luôn có ít nhất một bảng bán hàng có ngày giao dịch
    has_kept_sales = any(
        any(k in p["role"].lower() for k in ["bán hàng", "hóa đơn"])
        for p in parsed_tables if p["name"] in kept_names
    )
    if not has_kept_sales:
        for p in parsed_tables:
            if any(k in p["role"].lower() for k in ["bán hàng", "hóa đơn"]) or any(k in p["name"].lower() for k in ["donhang", "hoadon", "banhang"]):
                kept_names.add(p["name"])
                break

    # --- NGUYÊN TẮC VÀNG 3: QUAN HỆ KHÓA NGOẠI (Foreign Key Relational Closure) ---
    # Nếu giữ bảng chi tiết dòng hàng (chi_tiet_don, DanhSachHoaDonChiTiet), bắt buộc giữ bảng đơn hàng (don_hang, DanhSachHoaDon)
    for p in parsed_tables:
        if p["name"] in kept_names:
            p_low = p["name"].lower()
            if any(k in p_low for k in ["chitiet", "chi_tiet", "detail"]):
                # Tìm bảng cha tương ứng
                for parent_p in parsed_tables:
                    parent_low = parent_p["name"].lower()
                    if not any(k in parent_low for k in ["chitiet", "chi_tiet", "detail"]):
                        if (
                            ("don" in p_low and "don" in parent_low)
                            or ("hoadon" in p_low and "hoadon" in parent_low)
                            or ("banhang" in p_low and "banhang" in parent_low)
                        ):
                            kept_names.add(parent_p["name"])

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

    # --- TÁI CẤU TRÚC ĐỒNG BỘ NGUYÊN KHỐI (Atomic Re-rendering) ---
    kept_detail_blocks = [p["raw"] for p in parsed_tables if p["name"] in kept_names]

    if has_dual_sections and summary_section.strip():
        # Lọc lại phần summary header tương ứng với kept_names
        summary_lines = summary_section.strip().split("\n")
        filtered_summary_lines = []
        for line in summary_lines:
            if not line.strip().startswith("- Bảng"):
                filtered_summary_lines.append(line)
            else:
                tbl_m = re.search(r"Bảng\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?", line)
                if tbl_m and tbl_m.group(1) in kept_names:
                    filtered_summary_lines.append(line)
        return "\n".join(filtered_summary_lines) + "\n\n### CHI TIẾT CÁC BẢNG VÀ CỘT:\n" + "\n\n".join(kept_detail_blocks)
    else:
        prefix = f"{header.strip()}\n\n" if header.strip() else ""
        return prefix + "\n\n".join(kept_detail_blocks)


# ==============================================================================
# 4. CHỈ DẪN HỆ THỐNG ĐỘNG (INTENT-DRIVEN SYSTEM INSTRUCTION) & RETURN FORMAT ADAPTER
# ==============================================================================

def is_topk_list_question(question: str) -> bool:
    """Kiểm tra câu hỏi có yêu cầu trả về danh sách Top-K (K >= 2 hoặc danh sách nhiều đối tượng) hay không."""
    if not question:
        return False
    q_low = question.lower()
    patterns = [
        r"\btop\s*\d+\b",
        r"(?<!/)(?<!\d)\b([1-9]|[1-4]\d|50)\s+(?:mặt\s*hàng|sản\s*phẩm|sp|khách(?:\s*hàng)?|món|hàng|khach)\b",
        r"\bliệt\s*kê\s+([1-9]|[1-4]\d|50)\b",
        r"\blist\s*\d+\b",
        r"\bcho\s+(?:tôi|mình|em)?\s*([1-9]|[1-4]\d|50)\s+(?:mặt\s*hàng|sp|sản\s*phẩm|khách|hàng)\b",
        r"\bnhững\s*(?:mặt\s*hàng|sản\s*phẩm|sp|khách)\s*nào\b",
        r"\bdanh\s*sách\s*(?:mặt\s*hàng|sản\s*phẩm|sp|khách)\b",
    ]
    return any(re.search(p, q_low) for p in patterns)


def is_top1_string_question(question: str) -> bool:
    """Kiểm tra câu hỏi có yêu cầu trả về duy nhất 1 mặt hàng / đối tượng đứng đầu (Top-1 scalar string) hay không."""
    if not question:
        return False
    if is_topk_list_question(question):
        return False
    q_low = question.lower()
    patterns = [
        r"\b(?:hàng|sp|sản\s*phẩm|món|hang|san\s*pham|mon)\s+n[aà]o\s+(?:bán\s*chạy|nhiều|chạy|hot|chi\s*tiêu|mua|thấp|ít|chay|ban\s*chay|nhieu)\b",
        r"\b(?:bán\s*(?:chạy|nhiều|hot)|chi\s*tiêu\s*nhiều|chay)\s*nhất\s*l[aà]\s*(?:gì|ai|những\s*gì|mặt\s*hàng\s*nào|sp\s*nào|gi)\b",
        r"\bsp\s*bán\s*(?:dc|được|duoc)?\s*nhiều\s*nhất\b",
        r"\b(?:hàng|hang)\s*n[aà]o\s*(?:chạy|chay)\s*nhất\b",
        r"\b(?:khách|khach)\s*n[aà]o\s*chi\s*tiêu\s*nhiều\s*nhất\b",
        r"\btop\s*1\b",
    ]
    return any(re.search(p, q_low) for p in patterns)


def get_return_format_instruction(question: str, for_retry: bool = False) -> str:
    """Sinh chỉ dẫn định dạng trả về (Requirement 4) tương thích hoàn hảo với ý định câu hỏi."""
    if is_topk_list_question(question):
        if for_retry:
            return "- BẮT BUỘC trả về DANH SÁCH các chuỗi tên (list of strings: ['Tên 1', 'Tên 2', ...]) đúng số lượng K được yêu cầu theo thứ tự từ cao xuống thấp. TUYỆT ĐỐI KHÔNG trả về một số, dict hay chuỗi đơn lẻ!"
        return "4. BẮT BUỘC trả về DANH SÁCH các chuỗi tên (list of strings: ['Tên 1', 'Tên 2', ...]) đúng số lượng K được yêu cầu theo thứ tự từ cao xuống thấp. TUYỆT ĐỐI KHÔNG trả về một số hay một chuỗi đơn lẻ!"

    if is_top1_string_question(question):
        if for_retry:
            return "- BẮT BUỘC trả về một chuỗi ký tự đơn lẻ (scalar string: 'Tên hàng') là tên mặt hàng đứng đầu. TUYỆT ĐỐI KHÔNG trả về dạng list hay dict!"
        return "4. BẮT BUỘC trả về một chuỗi ký tự đơn lẻ (scalar string: 'Tên hàng') là tên mặt hàng đứng đầu. TUYỆT ĐỐI KHÔNG trả về dạng list hay dict!"

    # Mặc định: câu hỏi AOV, doanh thu, đơn giá, số lượng, số đơn
    if for_retry:
        return "- BẮT BUỘC trả về một số duy nhất (scalar number: int/float), làm tròn theo quy tắc làm tròn về đồng (int(round(...))). TUYỆT ĐỐI KHÔNG trả về dictionary hay list!"
    return "4. BẮT BUỘC trả về một số duy nhất (scalar number: int/float), làm tròn theo quy tắc làm tròn về đồng (int(round(...))). TUYỆT ĐỐI KHÔNG trả về dictionary hay list!"


def build_dynamic_system_instruction(intent: str, question: str, shop_static_prefix: str = "") -> str:
    """
    Tạo chỉ dẫn hệ thống tinh gọn, đặt phần tĩnh của cửa hàng (Core Instruction + Shop Schema + Business README)
    lên đầu tiên để tối đa hóa tỷ lệ trúng KV-Cache (Prefix Caching) khi gom nhóm theo business_id.
    """
    q_low = question.lower()

    core = r"""Bạn là một chuyên gia phân tích dữ liệu kinh doanh bằng Python/Pandas.
Nhiệm vụ của bạn là viết một hàm duy nhất:
```python
def solution(data):
    # logic tính toán an toàn
    return result
```
NGUYÊN TẮC THIẾT KẾ MÃ NGUỒN (CODE GENERATION RULES):
1. THAM SỐ `data`: Dictionary `{tên_bảng: DataFrame}` chứa dữ liệu gốc từ Excel/CSV (hỗ trợ tra cứu mềm không phân biệt dấu/hoa thường).
   - Tuyệt đối KHÔNG lặp dict comprehension trên toàn bộ `data` để lọc ngày (bảng sản phẩm không có ngày!).
   - HỢP NHẤT BẢNG PHÂN MẢNH (Partitioned Tables): Khi cửa hàng có nhiều bảng bán hàng phân mảnh (vd: `So_chi_tiet_ban_hang_1`, `So_chi_tiet_ban_hang_2`), BẮT BUỘC gộp lại:
     `sales_tables = [df for name, df in data.items() if any(k in str(name).lower() for k in ['ban_hang', 'so_chi_tiet', 'chitietbanhang'])]`
     `df_sales = pd.concat(sales_tables, ignore_index=True) if sales_tables else None`
     SAU ĐÓ BẮT BUỘC gán tên cột từ `cols_s = df_sales.columns.tolist()` TRƯỚC KHI sử dụng:
     `date_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)`
     `amt_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)`
     TUYỆT ĐỐI CẤM gọi `date_col` hoặc `amt_col` trước khi gán (để tránh lỗi UnboundLocalError / NameError)!
   - BẮT BUỘC ĐẶT NGOẶC ĐƠN QUANH TỪNG BIỂU THỨC ĐIỀU KIỆN KHI DÙNG TOÁN TỬ BITWISE `&` HOẶC `|`:
     Toán tử bitwise `&` có độ ưu tiên cao hơn `>=` và `<=`.
     BẮT BUỘC viết: `mask = (df['clean_date'] >= start) & (df['clean_date'] <= end)`.
     TUYỆT ĐỐI CẤM viết `df['col'] >= start & df['col'] <= end` không có ngoặc đơn!
   - BẮT BUỘC GỌI `clean_num(df[col]).sum()` HOẶC `clean_num(df[col]).mean()` TRÊN TỔNG/TRUNG BÌNH:
     Trên mọi phép tính tổng hoặc trung bình tiền hàng, doanh thu, số lượng, BẮT BUỘC gọi `clean_num(df[col]).sum()` hoặc `clean_num(df[col]).mean()` để tránh lỗi nối chuỗi ký tự ('12,000' + '5,000' -> '12,0005,000').
   - TÌM CỘT ĐỘNG (Dynamic Column Resolution Fallback):
     `qty_col = next((c for c in cols if any(k in str(c).lower() for k in ['số lượng', 'so luong', 'soluong', 'sl', 'khối lượng', 'trọng lượng'])), None)`
     `amt_col = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'thanh tien', 'tổng tiền', 'tong tien', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)`
     `order_col = next((c for c in cols if any(k in str(c).lower() for k in ['mã đơn', 'ma don', 'mã hoá đơn', 'mã hd', 'order_id', 'order id', 'mã chứng từ', 'mã gd', 'mã'])), None)`
     `status_col = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'tình trạng', 'xử lý'])), None)`
   - LỌC TRẠNG THÁI VÀ MẶT HÀNG MỀM DẺO (Relaxed Matching):
     * Lọc trạng thái hủy/trả: `df[status_col].astype(str).str.contains(r'hủy|huỷ|huy|trả|tra|cancel|return', case=False, na=False)`
     * Lọc kích cỡ (Size): Dùng regex linh hoạt `r'\(m\)|\bsize\s*m\b'` cho size M, TUYỆT ĐỐI KHÔNG ghép chữ 'ly' vào tên hàng!
   - Tìm đúng bảng cần dùng -> tìm cột ngày gốc `d_c = next(...)` -> tạo `df['clean_date'] = clean_date(df[d_c])` hoặc `pd.to_datetime(df[d_c], errors='coerce')` trước khi gọi bất kỳ thuộc tính `.dt` nào. TUYỆT ĐỐI CẤM gọi `.dt` trên cột chuỗi/object chưa convert datetime!
   - TUYỆT ĐỐI CẤM chuỗi `.dt.date.dt.year` hoặc `.dt.date.dt.month` (vì `.dt.date` không còn accessor `.dt`). Dùng `df['clean_date'].dt.year`, `df['clean_date'].dt.month` hoặc so sánh trực tiếp: `(df['clean_date'].dt.date >= pd.to_datetime(start_date).date()) & (df['clean_date'].dt.date <= pd.to_datetime(end_date).date())`.
   - LỌC THỜI GIAN THEO ĐÚNG KỲ YÊU CẦU: Nếu câu hỏi hỏi về tháng X năm Y hoặc tuần trước, BẮT BUỘC lọc đúng khoảng thời gian của kỳ đó: ví dụ `(df['clean_date'].dt.year == 2025) & (df['clean_date'].dt.month == 6)`. TUYỆT ĐỐI KHÔNG chỉ lọc `<= today`!
2. TIỆN ÍCH CÓ SẴN Ở GLOBAL SCOPE: `clean_num`, `clean_date`, `filter_valid_sales`, `convert_to_base_qty`, `_strip_accents`, `apply_tie_breaker`, `filter_future_data`, `re`, `math`, `datetime`, `date`, `timedelta`, `pct`.
   - TUYỆT ĐỐI CẤM định nghĩa lại hoặc import lại các hàm/module này trong code.
   - TUYỆT ĐỐI KHÔNG import các DataFrame methods từ pandas (ví dụ: KHÔNG ĐƯỢC dùng 'from pandas import sort_values'). Hãy gọi trực tiếp df.sort_values(...).
3. Bản ghi có ngày > as_of_date coi như chưa xảy ra (loại bỏ khỏi tính toán).
4. MẶC ĐỊNH LOẠI BỎ ĐƠN HỦY / TRẢ HÀNG: Trừ khi câu hỏi hỏi đích danh về đơn bị hủy ('đơn hủy', 'đã huỷ', 'bị huỷ'), mọi câu hỏi về số đơn, doanh thu, lượng bán đều BẮT BUỘC loại bỏ đơn hủy/trả hàng:
   `status_col = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'tình trạng', 'xử lý'])), None)`
   `if status_col: df = df[~df[status_col].astype(str).str.contains(r'hủy|huỷ|huy|trả|tra|cancel|return', case=False, na=False)]`
5. XỬ LÝ KHI DỮ LIỆU RỖNG HOẶC KHÔNG PHÁT SINH:
   - Nếu sau khi lọc theo ngày/điều kiện mà DataFrame rỗng:
     * Doanh thu / Tiền hàng / Số đơn / Số lượng: BẮT BUỘC return 0 (không có doanh thu / 0 đơn).
     * Tỉ lệ phần trăm %: BẮT BUỘC return 0.0 (tỉ lệ hủy là 0.0%).
     * Top K / Mặt hàng: return "" hoặc [].
     * TUYỆT ĐỐI CẤM return None hoặc raise lỗi khi chỉ đơn giản là không có giao dịch trong kỳ.
6. LỌC DOANH THU THEO NGÀY CỤ THỂ / HÔM NAY (SINGLE-DAY REVENUE FILTERING):
   Khi câu hỏi hỏi về doanh thu trong một ngày cụ thể (ví dụ: "hôm nay", "ngày hôm nay", "ngày 30/04/2025"):
   BẮT BUỘC lọc đúng ngày trên `clean_date`:
   `df_sales = df_sales[df_sales['clean_date'].dt.date == pd.to_datetime(target_date).date()]`
   TRƯỚC KHI tính tổng tiền! TUYỆT ĐỐI CẤM tính tổng mà quên lọc ngày khiến kết quả bị cộng dồn toàn bộ lịch sử cửa hàng!
7. GIÁ TRỊ TRẢ VỀ CỦA HÀM `solution(data)`:
   BẮT BUỘC trả về một giá trị vô hướng (scalar number: int hoặc float), chuỗi (str), boolean (bool) hoặc list/table theo yêu cầu câu hỏi.
   TUYỆT ĐỐI CẤM trả về dictionary chứa nhiều thông tin như `{'total_qty': ..., 'total_amount': ...}` khi câu hỏi chỉ hỏi về một đại lượng!
8. Chỉ raise DataNotFoundError khi dữ liệu hoàn toàn thiếu hẳn bảng/cột nghiệp vụ mà câu hỏi yêu cầu. TUYỆT ĐỐI CẤM trả về chuỗi 'unanswerable'."""

    conditional_rules: List[str] = []

    if any(k in q_low for k in ["mấy đơn", "bao nhiêu đơn", "số đơn", "số lượng đơn", "so don", "có bao nhiêu đơn", "co bao nhiu don", "đếm số đơn", "dem so don", "bao nhiu don"]):
        conditional_rules.append(
            "- [Đếm số lượng đơn]: BẮT BUỘC tìm cột mã đơn `order_col = next((c for c in cols if any(k in str(c).lower() for k in ['mã đơn', 'ma don', 'mã hoá đơn', 'mã hd', 'order_id', 'order id', 'mã chứng từ', 'mã gd', 'mã'])), None)` "
            "và đếm số đơn duy nhất bằng `int(df[order_col].dropna().nunique())`. "
            "TUYỆT ĐỐI CẤM đếm trên cột ngày tháng `df[date_col].nunique()` và TUYỆT ĐỐI CẤM tính tổng doanh thu/tiền hàng!"
        )

    if any(k in q_low for k in ["huỷ", "hủy", "cancel", "huy"]) and any(k in q_low for k in ["đơn", "bill", "hoá đơn", "don"]):
        conditional_rules.append(
            "- [Đơn bị hủy]: Lọc GIỮ LẠI đơn có trạng thái hủy (cả có dấu và không dấu): "
            "`df[status_col].astype(str).str.contains(r'hủy|huỷ|huy|cancel', case=False, na=False)` "
            "và đếm số đơn bằng `int(df[order_col].dropna().nunique())`. TUYỆT ĐỐI CẤM đếm trên cột ngày tháng!"
        )

    if any(k in q_low for k in ["ca sáng", "ca chiều", "ca sang", "ca chieu", "ca làm"]):
        conditional_rules.append(
            "- [Ca làm việc (Điều 2 Rulebook)]: Ca sáng: 06:00 đến 13:59 (`df['clean_date'].dt.hour.between(6, 13)`). "
            "Ca chiều: 14:00 đến 21:59 (`df['clean_date'].dt.hour.between(14, 21)`). "
            "BẮT BUỘC sử dụng bảng hóa đơn/bán hàng có cột thời gian có chứa giờ (ví dụ: 'Thời gian tạo', 'Giờ', 'ThoiGian') để trích xuất `.dt.hour`."
        )

    if any(k in q_low for k in ["đợt giao", "lượt giao", "chở giao", "giao hàng", "dot giao", "đợt hàng"]):
        conditional_rules.append(
            "- [Số đợt giao hàng / Vận chuyển (Điều 6 Rulebook)]: Khi câu hỏi hỏi về số đợt giao / lượt giao / chở hàng, "
            "BẮT BUỘC sử dụng bảng có vai trò 'Sổ giao hàng / Vận chuyển' (ví dụ: SoGiaoHang, Bảng kê phiếu giao hàng). "
            "Sử dụng cột ngày chở/giao và đếm lượt giao bằng: `int(df.drop_duplicates(subset=[col_don, col_lan]).shape[0])` hoặc `df[order_col].nunique()` hoặc `len(df)`. "
            "TUYỆT ĐỐI KHÔNG tìm kiếm cột tiền/doanh thu trong bảng giao hàng!"
        )

    if any(k in q_low for k in ["huỷ", "hủy", "cancel", "huy"]) and any(k in q_low for k in ["đơn", "bill", "hoá đơn", "don"]):
        conditional_rules.append(
            "- [Đơn bị hủy]: BẮT BUỘC sử dụng bảng bán hàng / hóa đơn (So_chi_tiet_ban_hang, don_hang, DanhSachHoaDon). "
            "TUYỆT ĐỐI KHÔNG sử dụng bảng giao hàng (vì phiếu giao hàng không chứa trạng thái hủy đơn)!"
        )

    if any(k in q_low for k in ["doanh thu", "tiền bán", "tổng tiền", "bán chạy", "doanh so", "doanh số", "mua nhiều"]):
        conditional_rules.append(
            "- [Doanh thu hợp lệ]: Chỉ tính đơn KHÔNG huỷ và KHÔNG trả hàng. Tìm cột trạng thái động: `st_col = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'tình trạng', 'xử lý'])), None)`. "
            "Nếu có st_col, lọc: `df = df[~df[st_col].astype(str).str.contains(r'hủy|huỷ|huy|trả|tra|cancel|return', case=False, na=False)]`. "
            "BẮT BUỘC gọi `clean_num(df[amt_col]).sum()` để tính tổng doanh thu."
        )

    # Lọc sản phẩm cụ thể nếu câu hỏi đề cập
    conditional_rules.append(
        "- [Lọc sản phẩm / mặt hàng cụ thể]: Nếu câu hỏi đề cập tới tên món / mặt hàng / sản phẩm / hoạt chất cụ thể (ví dụ: 'nước ép dưa hấu', 'má heo', 'soda chanh dây', 'Natri clorid', 'thép cuộn phi 6'): "
        "BẮT BUỘC tìm cột tên hàng `prod_col = next((c for c in cols if any(k in str(c).lower() for k in ['hàng', 'tên món', 'tên hàng', 'sản phẩm', 'món', 'mặt hàng', 'product', 'item'])), None)` "
        "và lọc sản phẩm bằng regex linh hoạt chứa từ khóa câu hỏi: `df = df[df[prod_col].astype(str).str.contains(..., case=False, na=False)]` TRƯỚC KHI tính tổng tiền hoặc số lượng!"
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

    if intent == "multitable_join" or any(k in q_low for k in ["hoạt chất", "kê đơn", "thuốc", "natri"]):
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

    if is_topk_list_question(question):
        conditional_rules.append(
            "- [Định dạng trả về Top-K (Danh sách)]: BẮT BUỘC trả về DANH SÁCH các chuỗi tên (list of strings: ['Tên 1', 'Tên 2', ...]) đúng số lượng K theo thứ tự xếp hạng. TUYỆT ĐỐI KHÔNG trả về một số hay một chuỗi đơn lẻ!"
        )
    elif is_top1_string_question(question):
        conditional_rules.append(
            "- [Định dạng trả về Top-1 (Mặt hàng đứng đầu)]: BẮT BUỘC trả về một chuỗi ký tự đơn lẻ (scalar string: 'Tên hàng') là tên mặt hàng đứng đầu. TUYỆT ĐỐI KHÔNG trả về dạng list hay dict!"
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

    if any(k in q_low for k in ["hàng ế", "hang e", "không bán được", "khong ban duoc", "tăng giá", "tang gia"]):
        conditional_rules.append(
            "- [Hàng ế & Đợt tăng giá (Điều 5)]: `'Hàng ế'` là mặt hàng đã từng bán trước kỳ nhưng có 0 đơn hợp lệ trong kỳ. "
            "`'Ảnh hưởng của đợt tăng giá'` tính từ ngày đầu tiên `D` có giá bán cao hơn giá liền trước: so sánh `N` ngày từ `D` (gồm cả `D`) với `N` ngày liền trước `D`."
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

def extract_relevant_rulebook_clauses(rulebook_content: str, question: str, max_chars: int = 1000) -> str:
    """Trích xuất thông minh các điều khoản Rulebook liên quan trực tiếp đến câu hỏi (giới hạn ~1.000 ký tự)."""
    if not rulebook_content or not rulebook_content.strip():
        return ""

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
    "cong_no": """--- VÍ DỤ MINH HỌA: TÍNH CÔNG NỢ / TUỔI NỢ / KHÁCH CÒN NỢ ---
Câu hỏi: "Tính đến hết ngày 19/08/2026, có bao nhiêu khách còn nợ cửa hàng?" (as_of_date = "2026-08-19")
```python
def solution(data):
    # 1. Tìm bảng công nợ / sổ nợ (KHÔNG dùng cột thành tiền của bảng bán hàng)
    df_debt = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        cols_low = [str(c).lower() for c in df.columns]
        is_debt_tbl = (
            any(k in n_clean for k in ['congno', 'sono', 'sogop', 'phaithu', 'hanno', 'phieuthu', 'soquy', 'thanhtoan'])
            or any(any(k in c for k in ['còn nợ', 'tiền nợ', 'phải thu', 'hạn trả']) for c in cols_low)
        )
        if is_debt_tbl:
            df_debt = df.copy()
            break
    if df_debt is None:
        raise DataNotFoundError("Không tìm thấy bảng công nợ / sổ nợ trong dữ liệu", table_name="công nợ", available_tables=list(data.keys()))

    cols = df_debt.columns.tolist()
    cust_col = next((c for c in cols if any(k in str(c).lower() for k in ['khách hàng', 'mã khách', 'tenkh', 'tên khách', 'makh', 'so kh'])), None)
    debt_col = next((c for c in cols if any(k in str(c).lower() for k in ['còn nợ', 'tiền nợ', 'phải thu', 'cần thu', 'số tiền', 'tiền']) and 'hạn' not in str(c).lower()), None)
    if not cust_col or not debt_col:
        raise DataNotFoundError("Thiếu cột khách hàng hoặc cột tiền nợ trong bảng công nợ", column_name="còn nợ/khách", available_columns=cols)

    # 2. Lọc thời gian <= as_of_date nếu có cột ngày
    d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian', 'ngaylap', 'hạn trả', 'han tra'])), None)
    if d_c:
        df_debt['clean_date'] = clean_date(df_debt[d_c])
        df_debt = df_debt[df_debt['clean_date'].dt.date <= pd.to_datetime("2026-08-19").date()]

    # 3. Lọc khoản còn nợ (> 0), loại bỏ khách lẻ
    df_debt['clean_debt'] = clean_num(df_debt[debt_col])
    valid_debt = df_debt[(df_debt['clean_debt'] > 0) & (~df_debt[cust_col].astype(str).str.lower().str.contains('lẻ|khách lẻ|nan|none'))]
    if valid_debt.empty:
        return 0

    return int(valid_debt[cust_col].dropna().nunique())
```""",

    "purchase_import": """--- VÍ DỤ MINH HỌA: TÍNH TỔNG TIỀN / GIÁ TRỊ PHIẾU NHẬP HÀNG ---
Câu hỏi: "Tháng này tổng giá trị các phiếu nhập hàng là bao nhiêu?" (as_of_date = "2026-09-07")
```python
def solution(data):
    # 1. Tìm bảng nhập hàng (ưu tiên bảng tổng hợp phiếu nhập, tránh bảng chi tiết)
    df_nhap = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        if 'nhap' in n_clean and not any(k in n_clean for k in ['chitiet', 'chi_tiet', 'detail', 'lohang']):
            df_nhap = df.copy()
            break
    if df_nhap is None:
        df_nhap = next((df.copy() for name, df in data.items() if 'nhap' in re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())), None)
    if df_nhap is None:
        raise DataNotFoundError("Không tìm thấy bảng nhập hàng trong dữ liệu", table_name="nhập hàng", available_tables=list(data.keys()))

    # 2. Tìm cột ngày và cột tiền
    cols = df_nhap.columns.tolist()
    d_c = next((c for c in cols if any(k in str(c).lower() for k in ['thời gian', 'ngày', 'date', 'ngaylap'])), None)
    a_c = next((c for c in cols if any(k in str(c).lower() for k in ['cần trả ncc', 'tổng tiền', 'tong tien', 'thành tiền', 'giá trị']) and 'trả hàng' not in str(c).lower()), None)
    if not d_c or not a_c:
        raise DataNotFoundError("Bảng nhập hàng thiếu cột ngày hoặc cột tiền", column_name="ngày/tiền", available_columns=cols)

    # 3. Lọc đúng kỳ tháng này: năm 2026, tháng 9, từ ngày 1 đến hết as_of_date
    df_nhap['clean_date'] = clean_date(df_nhap[d_c])
    df_nhap = df_nhap[(df_nhap['clean_date'].dt.year == 2026) & (df_nhap['clean_date'].dt.month == 9) & (df_nhap['clean_date'].dt.date <= pd.to_datetime("2026-09-07").date())]

    # 4. Loại bỏ phiếu hủy nếu có trạng thái hoặc ghi chú
    st_c = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'ghi chú', 'cancel'])), None)
    if st_c:
        df_nhap = df_nhap[~df_nhap[st_c].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|cancel')]

    return int(round(clean_num(df_nhap[a_c]).sum()))
```""",

    "daily_revenue": r"""--- VÍ DỤ MINH HỌA: TÍNH DOANH THU TRONG NGÀY (DAILY REVENUE / HÔM NAY) ---
Câu hỏi: "Hôm nay doanh thu của cửa hàng là bao nhiêu?" (as_of_date = "2026-05-15")
```python
def solution(data):
    # 1. Tìm bảng bán hàng
    df_sales = None
    date_col = amt_col = status_col = None
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian', 'ngày tạo'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower() and 'giảm' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            date_col, amt_col = d_c, a_c
            status_col = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'tình trạng'])), None)
            break

    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền", table_name="bán hàng")

    # 2. Xử lý ngày và loại bỏ đơn hủy / trả hàng (diacritic-insensitive)
    df_sales['clean_date'] = clean_date(df_sales[date_col])
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|tra|cancel|return')]

    # 3. BẮT BUỘC LỌC ĐÚNG NGÀY TRÊN clean_date (SINGLE-DAY DATE FILTERING):
    target_date = pd.to_datetime("2026-05-15").date()
    df_sales = df_sales[df_sales['clean_date'].dt.date == target_date]
    if df_sales.empty:
        return 0

    # 4. Trả về tổng tiền hàng dạng vô hướng (scalar float/int)
    return int(round(clean_num(df_sales[amt_col]).sum()))
```""",

    "aggregation": r"""--- VÍ DỤ MINH HỌA: TÍNH DOANH THU / TIỀN BÁN HÀNG ---
Câu hỏi: "Tháng 3/2026 hàng nước ép dưa hấu (L) thu về bao nhiêu tiền?" (as_of_date = "2026-06-24")
```python
def solution(data):
    # Khởi tạo các biến cột để tránh lỗi UnboundLocalError
    df_sales = None
    date_col = amt_col = status_col = item_col = None

    # 1. Tìm bảng bán hàng (hỗ trợ tự động gộp các bảng bán hàng phân mảnh nếu có)
    sales_tables = [
        df.copy() for name, df in data.items()
        if any(k in str(name).lower() for k in ['ban_hang', 'so_chi_tiet', 'chitietbanhang'])
        and not any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho'])
    ]
    if sales_tables:
        df_sales = pd.concat(sales_tables, ignore_index=True)
    else:
        for name, df in data.items():
            if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
                continue
            cols = df.columns.tolist()
            d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
            a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
            if d_c and a_c:
                df_sales = df.copy()
                break

    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền", table_name="bán hàng", available_tables=list(data.keys()))

    cols_s = df_sales.columns.tolist()
    date_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
    amt_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
    item_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['hàng', 'tên món', 'tên hàng', 'sản phẩm', 'mặt hàng', 'product'])), None)
    if not date_col or not amt_col:
        raise DataNotFoundError("Bảng bán hàng thiếu cột ngày hoặc cột tiền", column_name="ngày/tiền", available_columns=cols_s)

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'tình trạng'])), None)
    if status_col:
        # BẮT BUỘC loại bỏ đơn hủy / trả hàng khi tính doanh thu (Rulebook Điều 1 - diacritic-insensitive):
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|tra|cancel|return')]

    # Lọc bỏ các dòng tổng ngày / tổng tháng do hệ thống POS chèn vào bảng chi tiết bán hàng:
    if item_col:
        df_sales = df_sales[~df_sales[item_col].astype(str).str.contains(r'^\s*(?:tổng\s*(?:ngày|tháng|cộng)?|cộng)\b', case=False, na=False)]

    # 2. Lọc thời gian: Tháng 3/2026 (BẮT BUỘC có ngoặc đơn quanh từng điều kiện bitwise &)
    # LƯU Ý: Nếu câu hỏi hỏi một ngày cụ thể (ví dụ hôm nay / ngày X), lọc: df_sales['clean_date'].dt.date == pd.to_datetime(target_date).date()
    mask = (df_sales['clean_date'].dt.year == 2026) & (df_sales['clean_date'].dt.month == 3)
    df_sales = df_sales[mask]

    # 3. CHỈ LỌC MẶT HÀNG KHI CÂU HỎI HỎI RIÊNG MẶT HÀNG ĐÓ:
    # Tuyệt đối CẤM lọc mặt hàng khi câu hỏi hỏi tổng doanh thu chung ("tổng doanh thu hôm nay", "doanh thu tháng 5")!
    if item_col:
        mask_prod = df_sales[item_col].astype(str).str.contains('nước ép dưa hấu', case=False, na=False) & df_sales[item_col].astype(str).str.contains(r'\(l\)|\bl\b', case=False, regex=True, na=False)
        df_sales = df_sales[mask_prod]

    if df_sales.empty:
        return 0

    # BẮT BUỘC tính tổng trên cột doanh thu / thành tiền (Tổng tiền hàng, Thành tiền).
    # TUYỆT ĐỐI KHÔNG dùng 'Tổng sau giảm giá' (Rulebook Điều 1) và KHÔNG dùng 'Khách đã trả'! Trả về scalar int/float.
    return int(round(clean_num(df_sales[amt_col]).sum()))
```""",

    "count_orders": """--- VÍ DỤ MINH HỌA: ĐẾM SỐ ĐƠN HÀNG (COUNT DISTINCT ORDERS) ---
Câu hỏi: "Hôm nay cửa hàng có bao nhiêu đơn hàng?" (as_of_date = "2025-10-18")
```python
def solution(data):
    df_sales = None
    order_col = date_col = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        if any(k in n_clean for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho', 'khachhang']):
            continue
        cols = df.columns.tolist()
        o_c = next((c for c in cols if any(k in str(c).lower() for k in ['mã đơn', 'ma don', 'mã hoá đơn', 'mã hd', 'order_id', 'order id', 'mã chứng từ', 'mã giao dịch'])), None)
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian', 'ngày tạo'])), None)
        if o_c and d_c:
            df_sales = df.copy()
            order_col, date_col = o_c, d_c
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột mã đơn và cột ngày", table_name="bán hàng", available_tables=list(data.keys()))

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    # Mặc định loại bỏ đơn hủy/trả hàng trừ khi được hỏi rõ (diacritic-insensitive)
    cols_s = df_sales.columns.tolist()
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'tình trạng', 'xử lý'])), None)
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|tra|cancel|return')]

    # Lọc theo kỳ câu hỏi yêu cầu (ví dụ ngày mốc '2025-10-18', hoặc nếu hỏi tháng/khoảng thời gian thì dùng .dt.month/.dt.year hoặc range)
    mask = df_sales['clean_date'].dt.date == pd.to_datetime("2025-10-18").date()
    df_filtered = df_sales[mask]
    if df_filtered.empty:
        return 0
    # BẮT BUỘC dùng nunique() thay vì len() vì một đơn hàng có thể có nhiều dòng sản phẩm
    return int(df_filtered[order_col].dropna().nunique())
```""",

    "cancelled_orders": """--- VÍ DỤ MINH HỌA: ĐẾM SỐ ĐƠN BỊ HỦY (CANCELLED ORDERS COUNT) ---
Câu hỏi: "Đếm số đơn đã huỷ trong tháng 12/2025" (as_of_date = "2026-06-02")
```python
def solution(data):
    df_sales = None
    order_col = None
    date_col = None
    status_col = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        if any(k in n_clean for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        o_c = next((c for c in cols if any(k in str(c).lower() for k in ['mã đơn', 'ma don', 'mã hoá đơn', 'mã hd', 'order_id', 'order id', 'mã chứng từ', 'mã giao dịch', 'mã phiếu', 'mã'])), None)
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian', 'ngày tạo', 'ngày đặt'])), None)
        st_c = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'tình trạng', 'xử lý'])), None)
        if o_c and d_c and st_c:
            df_sales = df.copy()
            order_col, date_col, status_col = o_c, d_c, st_c
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột mã đơn, ngày và trạng thái", table_name="bán hàng", available_tables=list(data.keys()))

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    # Lọc giữ lại đơn có trạng thái hủy (cả có dấu và không dấu: hủy|huỷ|huy|cancel)
    df_cancelled = df_sales[df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|cancel')]

    # Lọc thời gian: tháng 12/2025 (dùng trực tiếp .dt.year và .dt.month, KHÔNG gọi .dt.date trước!)
    mask = (df_cancelled['clean_date'].dt.year == 2025) & (df_cancelled['clean_date'].dt.month == 12)
    df_filtered = df_cancelled[mask]
    if df_filtered.empty:
        return 0
    # BẮT BUỘC đếm theo cột mã đơn (order_col), TUYỆT ĐỐI KHÔNG đếm theo cột ngày (date_col)!
    return int(df_filtered[order_col].dropna().nunique())

```""",

    "quantity_sum": r"""--- VÍ DỤ MINH HỌA: TÍNH TỔNG SỐ LƯỢNG MẶT HÀNG ĐÃ BÁN ---
Câu hỏi: "Trong tháng 5/2025 cửa hàng bán được bao nhiêu kg thép cuộn phi 6 Hòa Phát?" (as_of_date = "2026-05-16")
```python
def solution(data):
    # 1. Tìm bảng bán hàng chi tiết (có cột mặt hàng, số lượng, ngày)
    df_sales = None
    date_col = item_col = qty_col = None
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
        i_c = next((c for c in cols if any(k in str(c).lower() for k in ['hàng', 'tên món', 'tên hàng', 'sản phẩm', 'mặt hàng', 'product'])), None)
        q_c = next((c for c in cols if any(k in str(c).lower() for k in ['số lượng', 'so_luong', 'soluong', 'sl', 'khối lượng', 'trọng lượng'])), None)
        if d_c and i_c and q_c:
            df_sales = df.copy()
            date_col, item_col, qty_col = d_c, i_c, q_c
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày, mặt hàng và số lượng", table_name="bán hàng", available_tables=list(data.keys()))

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    cols_s = df_sales.columns.tolist()
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'tình trạng'])), None)
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|tra|cancel|return')]

    # 2. Lọc mặt hàng ĐỘNG theo đúng thực thể câu hỏi yêu cầu (KHÔNG copy-paste tên hàng cố định):
    # LƯU Ý PHÂN TÁCH ĐƠN VỊ VÀ SIZE (ví dụ 'bao nhiêu ly Đá xay cookie (M)'):
    # - Từ chỉ đơn vị ('ly', 'cốc', 'chai', 'kg') thuộc cột Đơn vị tính (Unit / ĐVT nếu có).
    # - Tên sản phẩm và kích cỡ ('(M)', 'phi 6') nằm ở cột tên hàng.
    # Lọc tên hàng theo sản phẩm và kích cỡ (size):
    # m_prod = df_sales[item_col].astype(str).str.contains('đá xay cookie', case=False, na=False) & df_sales[item_col].astype(str).str.contains(r'\(m\)|\bm\b', case=False, regex=True, na=False)
    # TUYỆT ĐỐI CẤM ghép đơn vị 'ly' vào regex tên hàng như r'ly.*đá xay cookie'!
    mask_item = df_sales[item_col].astype(str).str.contains(r'thép cuộn.*phi\s*6', case=False, regex=True, na=False)

    # 3. Lọc theo khoảng thời gian giải mã (tháng 5/2025)
    mask_date = (df_sales['clean_date'].dt.year == 2025) & (df_sales['clean_date'].dt.month == 5)
    df_filtered = df_sales[mask_item & mask_date]
    if df_filtered.empty:
        return 0

    # BẮT BUỘC tính tổng cột số lượng bằng clean_num, TUYỆT ĐỐI KHÔNG tính tổng cột tiền!
    return int(round(clean_num(df_filtered[qty_col]).sum()))
```""",

    "price_lookup": r"""--- VÍ DỤ MINH HỌA: TRA CỨU ĐƠN GIÁ / GIÁ BÁN (TWO-TIER LOOKUP) ---
Câu hỏi: "Giá bán một ly soda chanh dây (M) vào ngày 01/12/2025 là bao nhiêu?" (as_of_date = "2026-07-31")
```python
def solution(data):
    target_date = pd.to_datetime("2025-12-01").date()

    # BƯỚC 1: Tìm trong nhật ký bán hàng có ngày giao dịch (Ưu tiên số 1 theo Điều 5 Rulebook)
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc']):
            continue
        cols = df.columns.tolist()
        i_c = next((c for c in cols if any(k in str(c).lower() for k in ['tên hàng', 'hàng', 'tên món', 'sản phẩm', 'mặt hàng'])), None)
        p_c = next((c for c in cols if any(k in str(c).lower() for k in ['đơn giá', 'giá bán', 'giá lẻ', 'gia_ban', 'đơn giá bán'])), None)
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)

        if i_c and p_c and d_c:
            m_prod = df[i_c].astype(str).str.contains('soda chanh dây', case=False, na=False) & df[i_c].astype(str).str.contains(r'\(m\)|\bm\b', case=False, regex=True, na=False)
            matched = df[m_prod].copy()
            if not matched.empty:
                matched['clean_date'] = clean_date(matched[d_c])
                matched_day = matched[matched['clean_date'].dt.date == target_date]
                if not matched_day.empty:
                    # Tìm thấy giao dịch trong ngày: Lấy đơn giá dòng bán
                    return int(round(clean_num(matched_day[p_c]).iloc[0]))

    # BƯỚC 2: Nếu không có giao dịch trong ngày, tra cứu Bảng giá (BangGia) hoặc Danh mục hàng hóa (DanhMuc, DanhSachHangHoa, DanhSachSanPham)
    # LƯU Ý SỐNG CÒN: TUYỆT ĐỐI CẤM tính giá trung bình toàn bộ danh mục (data['Danh sách hàng hóa']['Giá bán'].mean())!
    # BẮT BUỘC lọc đúng mặt hàng theo tên/kích cỡ trước khi lấy Giá bán!
    for name, df in data.items():
        cols = df.columns.tolist()
        i_c = next((c for c in cols if any(k in str(c).lower() for k in ['tên hàng', 'hàng', 'tên món', 'sản phẩm', 'mặt hàng', 'tên thuốc'])), None)
        p_c = next((c for c in cols if any(k in str(c).lower() for k in ['giá mới', 'giá bán', 'giá', 'đơn giá', 'giá lẻ'])), None)
        if i_c and p_c:
            m_prod = df[i_c].astype(str).str.contains('soda chanh dây', case=False, na=False) & df[i_c].astype(str).str.contains(r'\(m\)|\bm\b', case=False, regex=True, na=False)
            matched = df[m_prod].copy()
            if not matched.empty:
                # Nếu bảng giá có cột ngày áp dụng, lấy mức giá áp dụng gần nhất trước ngày cần tra
                d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày áp dụng', 'ngày', 'date'])), None)
                if d_c:
                    matched['clean_date'] = clean_date(matched[d_c])
                    valid = matched[matched['clean_date'].dt.date <= target_date]
                    if not valid.empty:
                        valid = valid.sort_values(by='clean_date', ascending=False)
                        return int(round(clean_num(valid[p_c]).iloc[0]))
                return int(round(clean_num(matched[p_c]).iloc[0]))

    raise DataNotFoundError("Không tìm thấy giá bán của sản phẩm yêu cầu", column_name="giá bán")
```""",

    "multitable_join": r"""--- VÍ DỤ MINH HỌA: GHÉP BẢNG BÁN HÀNG TỔNG HỢP & CHI TIẾT (MULTI-TABLE JOIN: DON_HANG + CHI_TIET_DON + SAN_PHAM / THUOC) ---
Câu hỏi: "Tháng 8/2025 cửa hàng thu được bao nhiêu tiền từ mặt hàng thép cuộn phi 6?" (as_of_date = "2026-06-25")
```python
def solution(data):
    # 1. Tìm bảng đơn hàng (header), bảng chi tiết (detail) và bảng sản phẩm/danh mục (catalog)
    # Hỗ trợ cả mô hình bán lẻ / vật liệu và mô hình nhà thuốc:
    # - Header: BanHang_HoaDon, DonHang, HoaDon (chứa ngày bán, Order ID)
    # - Detail: BanHang_ChiTietHoaDon, ChiTietDonHang, Detail (chứa Mã giao dịch, Ma hang, So luong, Don gia)
    # - Catalog: BanHang_Thuoc, HangHoa, SanPham, DanhMuc (chứa Mã HH, Hoạt chất, Ten hang)
    df_order = None
    df_detail = None
    df_catalog = None
    for name, df in data.items():
        n_clean = str(name).lower()
        if any(k in n_clean for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho', 'khachhang', 'soquy']):
            continue
        cols = [str(c).lower() for c in df.columns]
        if any(k in n_clean for k in ['chi_tiet', 'chitiet', 'detail', 'chitiethoadon']) or (any(k in c for k in ['mã hàng', 'ma hang', 'mã sp', 'mã hh', 'mã mặt hàng']) and any('tiền' in c or 'lượng' in c or 'giá' in c for c in cols)):
            if df_detail is None:
                df_detail = df.copy()
        elif any(k in n_clean for k in ['don_hang', 'donhang', 'hoadon', 'hoa_don', 'banhang_hoadon']) or any(k in c for c in cols for k in ['ngày bán', 'ngay_ban', 'ngày đặt', 'thời gian tạo']):
            if df_order is None:
                df_order = df.copy()
        elif any(k in n_clean for k in ['san_pham', 'sanpham', 'hang_hoa', 'thuoc', 'danhmuc', 'banhang_thuoc']):
            if df_catalog is None:
                df_catalog = df.copy()

    # 2. Ghép nối Header và Detail với xử lý tên khóa phân kỳ (divergent keys)
    # Ví dụ nhà thuốc: Header 'Order ID' ghép với Detail 'Mã giao dịch'
    if df_order is not None and df_detail is not None:
        ord_cols = df_order.columns.tolist()
        det_cols = df_detail.columns.tolist()
        k_ord = next((c for c in ord_cols if any(k in str(c).lower() for k in ['order id', 'order_id', 'mã chứng từ', 'mã hóa đơn', 'mã hd', 'mã đơn', 'mã giao dịch', 'mã gd', 'số hóa đơn'])), None)
        k_det = next((c for c in det_cols if any(k in str(c).lower() for k in ['mã giao dịch', 'mã gd', 'order id', 'order_id', 'mã đơn hàng', 'mã đơn', 'mã chứng từ', 'mã hóa đơn'])), None)
        
        if k_ord and k_det:
            merged = pd.merge(df_order, df_detail, left_on=k_ord, right_on=k_det, how='inner')
        else:
            merged = df_detail
    elif df_detail is not None:
        merged = df_detail
    elif df_order is not None:
        merged = df_order
    else:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng trong dữ liệu", table_name="bán hàng")

    # 3. Ghép nối Catalog nếu cần tra tên mặt hàng hoặc hoạt chất (ví dụ Detail 'Ma hang' ghép với Catalog 'Mã HH')
    if df_catalog is not None:
        m_cols = merged.columns.tolist()
        cat_cols = df_catalog.columns.tolist()
        k_m = next((c for c in m_cols if any(k in str(c).lower() for k in ['ma hang', 'mã hàng', 'mã hh', 'ma_hh', 'mã sp', 'ma_sp', 'mã mặt hàng'])), None)
        k_cat = next((c for c in cat_cols if any(k in str(c).lower() for k in ['mã hh', 'ma_hh', 'ma hang', 'mã hàng', 'mã sản phẩm bán', 'mã sp', 'ma_sp'])), None)
        if k_m and k_cat:
            merged = pd.merge(merged, df_catalog, left_on=k_m, right_on=k_cat, how='inner')

    # 4. Xử lý cột ngày và lọc thời gian
    cols = merged.columns.tolist()
    d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian', 'ngaylap', 'ngay_ban'])), None)
    if not d_c:
        raise DataNotFoundError("Không tìm thấy cột ngày bán", column_name="ngày")
    merged['clean_date'] = clean_date(merged[d_c])

    # 5. BẮT BUỘC loại bỏ đơn hủy / trả hàng (diacritic-insensitive)
    st_c = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'tình trạng', 'status', 'ghi chú tt'])), None)
    if st_c:
        merged = merged[~merged[st_c].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|tra|cancel|return')]

    # 6. Lọc theo kỳ tháng 8/2025: BẮT BUỘC có ngoặc đơn quanh từng điều kiện bitwise &
    mask_date = (merged['clean_date'].dt.year == 2025) & (merged['clean_date'].dt.month == 8)
    merged = merged[mask_date]

    # 7. Lọc mặt hàng theo từ khóa regex linh hoạt (hoặc theo cột hoạt chất)
    item_c = next((c for c in cols if any(k in str(c).lower() for k in ['tên sp', 'hàng', 'tên món', 'tên hàng', 'sản phẩm', 'mặt hàng', 'product', 'hoạt chất', 'tên thuốc'])), None)
    if item_c:
        mask_item = merged[item_c].astype(str).str.contains(r'thép cuộn.*phi\s*6', case=False, regex=True, na=False)
        merged = merged[mask_item]

    if merged.empty:
        return 0

    # 8. Tính tiền: Ưu tiên (SoLuong * Đơn giá) hoặc thành tiền
    qty_c = next((c for c in cols if any(k in str(c).lower() for k in ['soluong', 'số lượng', 'sl', 'slg'])), None)
    price_c = next((c for c in cols if any(k in str(c).lower() for k in ['đơn giá (đ)', 'đơn giá', 'don gia', 'giá bán', 'giá'])), None)
    amt_c = next((c for c in cols if any(k in str(c).lower() for k in ['amount', 'thành tiền', 'thanh tien', 'tổng tiền', 'tong tien', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower() and 'giảm' not in str(c).lower()), None)
    
    if qty_c and price_c:
        return int(round((clean_num(merged[qty_c]) * clean_num(merged[price_c])).sum()))
    elif amt_c:
        return int(round(clean_num(merged[amt_c]).sum()))
    return 0
```""",

    "relational_join": r"""--- VÍ DỤ MINH HỌA: GHÉP NỐI BẢNG HEADER VÀ DETAIL (RELATIONAL TABLE JOIN) ---
Câu hỏi: "Tháng 11/2025 top 5 hàng bán chạy nhất là gì?" (as_of_date = "2026-06-25")
```python
def solution(data):
    # 1. Tìm bảng Header (DanhSachHoaDon / don_hang chứa ngày) và Detail (DanhSachHoaDonChiTiet / chi_tiet_don chứa mặt hàng, số lượng)
    df_hdr = next((df for n, df in data.items() if any(k in str(n).lower() for k in ['hoadon', 'hoa_don', 'don_hang', 'donhang']) or (any(k in str(c).lower() for c in df.columns for k in ['ngày', 'date', 'thời gian']) and not any(k in str(n).lower() for k in ['nhap', 'kho', 'chiphi']))), None)
    df_det = next((df for n, df in data.items() if any(k in str(n).lower() for k in ['chitiethoadon', 'chi_tiet', 'chitiet']) or (any(k in str(c).lower() for c in df.columns for k in ['tên hàng', 'mặt hàng', 'sản phẩm']) and any(k in str(c).lower() for c in df.columns for k in ['số lượng', 'soluong', 'sl']))), None)

    if df_hdr is None or df_det is None:
        raise DataNotFoundError("Không tìm thấy đủ bảng Header và Detail để ghép nối", table_name="bán hàng")

    # 2. Ghép nối Header và Detail trên khóa mã hóa đơn / mã đơn hàng
    kh = next((c for c in df_hdr.columns if any(k in str(c).lower() for k in ['mã hóa đơn', 'mã đơn hàng', 'mã đơn', 'mahd', 'mã hd', 'order_id', 'mã'])), None)
    kd = next((c for c in df_det.columns if any(k in str(c).lower() for k in ['mã hóa đơn', 'mã đơn hàng', 'mã đơn', 'mahd', 'mã hd', 'order_id', 'mã'])), None)
    dh = next((c for c in df_hdr.columns if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)

    merged = pd.merge(df_det, df_hdr[[kh, dh]], left_on=kd, right_on=kh, how='inner')
    merged['clean_date'] = clean_date(merged[dh])

    # 3. Lọc bỏ đơn hủy và lọc theo kỳ thời gian yêu cầu (ví dụ: tháng 11/2025)
    cols = merged.columns.tolist()
    st_c = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt'])), None)
    if st_c:
        merged = merged[~merged[st_c].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|cancel', regex=True, na=False)]

    mask_date = (merged['clean_date'].dt.year == 2025) & (merged['clean_date'].dt.month == 11)
    df_period = merged[mask_date]
    if df_period.empty:
        return []

    # 4. Tính tổng số lượng và xếp hạng theo Điều 9 Tie-Breaker
    prod_c = next((c for c in cols if any(k in str(c).lower() for k in ['tên hàng', 'sản phẩm', 'mặt hàng', 'tên món', 'tên thuốc'])), None)
    qty_c = next((c for c in cols if any(k in str(c).lower() for k in ['số lượng', 'soluong', 'sl', 'quy đổi'])), None)
    code_c = next((c for c in cols if any(k in str(c).lower() for k in ['mã hàng', 'mã hh', 'ma hang', 'mã mặt hàng', 'mã sp', 'mã'])), prod_c)

    df_period['clean_qty'] = clean_num(df_period[qty_c])
    grp = df_period.groupby([prod_c, code_c], as_index=False)['clean_qty'].sum()
    grp = grp.sort_values(by=['clean_qty', code_c], ascending=[False, True])

    return grp.head(5)[prod_c].astype(str).tolist()
```""",

    "delivery_batches": """--- VÍ DỤ MINH HỌA: ĐẾM SỐ ĐỢT GIAO HÀNG / LƯỢT GIAO (DELIVERY BATCH ROUTING) ---
Câu hỏi: "Tháng này cửa hàng đã chở giao bao nhiêu đợt hàng cho khách nhỉ?" (as_of_date = "2026-09-07")
```python
def solution(data):
    # 1. BẮT BUỘC tìm bảng Sổ giao hàng / Vận chuyển (SoGiaoHang, BangKeGiaoHang, PhieuGiaoHang, GiaoHang)
    df_delivery = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        cols_low = [str(c).lower() for c in df.columns]
        if (
            any(k in n_clean for k in ['giaohang', 'sogiaohang', 'phieugiao', 'vanchuyen', 'chohang', 'phieuxuat'])
            or any(any(k in c for k in ['lượt giao', 'đợt giao', 'ngày chở', 'ngày giao', 'người chở', 'biển số']) for c in cols_low)
        ):
            df_delivery = df.copy()
            break

    if df_delivery is None:
        raise DataNotFoundError("Không tìm thấy bảng sổ giao hàng / vận chuyển", table_name="sổ giao hàng", available_tables=list(data.keys()))

    cols = df_delivery.columns.tolist()
    d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày chở', 'ngay cho', 'ngày giao', 'ngay giao', 'thời gian', 'ngày', 'date'])), None)
    if not d_c:
        raise DataNotFoundError("Bảng giao hàng thiếu cột ngày giao/chở", column_name="ngày giao", available_columns=cols)

    df_delivery['clean_date'] = clean_date(df_delivery[d_c])

    # 2. Lọc thời gian tháng này (năm 2026, tháng 9, đến hết as_of_date): BẮT BUỘC có ngoặc đơn
    mask = (
        (df_delivery['clean_date'].dt.year == 2026)
        & (df_delivery['clean_date'].dt.month == 9)
        & (df_delivery['clean_date'].dt.date <= pd.to_datetime("2026-09-07").date())
    )
    df_filtered = df_delivery[mask]
    if df_filtered.empty:
        return 0

    # 3. Đếm số đợt / lượt giao:
    # BẮT BUỘC DÙNG CẶP KHÓA KẾT HỢP len(df_filtered[[ord_col, trip_col]].drop_duplicates()) vì 1 đơn có thể giao thành nhiều đợt!
    ord_col = next((c for c in cols if any(k in str(c).lower() for k in ['mã bill', 'ma bill', 'mã đơn', 'ma don', 'mã đơn hàng', 'mã phiếu', 'order_id'])), None)
    trip_col = next((c for c in cols if any(k in str(c).lower() for k in ['lượt giao', 'luot giao', 'lần giao', 'lan giao', 'đợt giao', 'dot giao'])), None)

    if ord_col and trip_col:
        return int(len(df_filtered[[ord_col, trip_col]].drop_duplicates()))
    elif trip_col:
        return int(df_filtered[trip_col].dropna().nunique())
    elif ord_col:
        return int(df_filtered[ord_col].dropna().nunique())

    return int(len(df_filtered))
```""",

    "shift_revenue": r"""--- VÍ DỤ MINH HỌA: TÍNH DOANH THU THEO CA (CA SÁNG / CA CHIỀU) ---
Câu hỏi: "Ca chiều tuần trước doanh thu bao nhiêu?" (as_of_date = "2026-06-25")
```python
def solution(data):
    # 1. Tìm bảng hóa đơn bán hàng
    df_sales = None
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        # BẮT BUỘC tìm cột thời gian có đủ GIỜ VÀ PHÚT (ví dụ 'Thời gian tạo' hoặc 'ThoiGianTao', KHÔNG dùng cột chỉ có ngày 'Thời gian')
        dt_c = next((c for c in cols if any(k in str(c).lower() for k in ['thời gian tạo', 'thoigiantao', 'created_at', 'gio', 'giờ']) and 'ngày' not in str(c).lower()), None)
        if not dt_c:
            dt_c = next((c for c in cols if any(k in str(c).lower() for k in ['thời gian', 'thoigian', 'date', 'ngày'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['tổng tiền hàng', 'thành tiền', 'tổng tiền', 'doanh thu']) and 'sau giảm' not in str(c).lower() and 'thuế' not in str(c).lower()), None)
        if dt_c and a_c:
            df_sales = df.copy()
            time_col, amt_col = dt_c, a_c
            break

    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột thời gian và tiền hàng", table_name="bán hàng")

    df_sales['clean_dt'] = clean_date(df_sales[time_col])
    cols_s = df_sales.columns.tolist()
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'tình trạng'])), None)
    if status_col:
        # BẮT BUỘC loại bỏ đơn hủy / trả hàng (diacritic-insensitive)
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|tra|cancel|return')]

    # 2. Lọc khoảng thời gian tuần trước (start_date <= date <= end_date)
    # Ví dụ tuần trước: 2026-06-08 đến 2026-06-14
    start_date = pd.to_datetime("2026-06-08").date()
    end_date = pd.to_datetime("2026-06-14").date()
    mask_date = (df_sales['clean_dt'].dt.date >= start_date) & (df_sales['clean_dt'].dt.date <= end_date)
    df_period = df_sales[mask_date]

    # 3. Lọc theo ca làm việc (Shift Filtering) trên cột timestamp:
    # - Ca sáng: từ 06:00 đến 13:59 (6 <= hour <= 13)
    # - Ca chiều: từ 14:00 đến 21:59 (14 <= hour <= 21)
    mask_shift = (df_period['clean_dt'].dt.hour >= 14) & (df_period['clean_dt'].dt.hour <= 21)
    df_shift = df_period[mask_shift]
    if df_shift.empty:
        return 0

    # BẮT BUỘC dùng Tổng tiền hàng (gross revenue), TUYỆT ĐỐI KHÔNG dùng Tổng sau giảm giá hoặc Khách đã trả
    return int(round(clean_num(df_shift[amt_col]).sum()))
```""",

    "ranking_topk": """--- VÍ DỤ MINH HỌA: TÌM ĐỐI TƯỢNG NHIỀU NHẤT / XẾP HẠNG (RANKING TOP-K) / ĐỒNG HẠNG ---
Câu hỏi: "Tháng 9/2025 top 5 hàng bán chạy nhất là gì?" (as_of_date = "2026-09-03")
```python
def solution(data):
    # 1. Tìm bảng bán hàng: nếu tách rời Header (DanhSachHoaDon / don_hang có ngày) và Detail (DanhSachHoaDonChiTiet / chi_tiet_don có tên hàng, số lượng), ghép nối qua mã hóa đơn
    df_sales = None
    df_hdr = next((df for n, df in data.items() if any(k in str(c).lower() for c in df.columns for k in ['ngày', 'date', 'thời gian']) and not any(k in str(n).lower() for k in ['nhap', 'kho', 'chiphi'])), None)
    df_det = next((df for n, df in data.items() if any(k in str(c).lower() for c in df.columns for k in ['tên hàng', 'sản phẩm', 'mặt hàng', 'tên thuốc', 'hàng']) and any(k in str(c).lower() for c in df.columns for k in ['số lượng', 'soluong', 'sl'])), None)

    if df_det is not None and df_hdr is not None and df_det is not df_hdr:
        kd = next((c for c in df_det.columns if any(k in str(c).lower() for k in ['mã hóa đơn', 'mã đơn hàng', 'mã đơn', 'mahd', 'mã hd', 'order_id', 'mã'])), None)
        kh = next((c for c in df_hdr.columns if any(k in str(c).lower() for k in ['mã hóa đơn', 'mã đơn hàng', 'mã đơn', 'mahd', 'mã hd', 'order_id', 'mã'])), None)
        dh = next((c for c in df_hdr.columns if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        if kd and kh and dh:
            df_sales = pd.merge(df_det, df_hdr[[kh, dh]], left_on=kd, right_on=kh, how='inner')
            df_sales['clean_date'] = clean_date(df_sales[dh])
    elif df_det is not None and any(k in str(c).lower() for c in df_det.columns for k in ['ngày', 'date', 'thời gian']):
        df_sales = df_det.copy()
        d_c = next((c for c in df_sales.columns if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        df_sales['clean_date'] = clean_date(df_sales[d_c])
    elif df_hdr is not None:
        df_sales = df_hdr.copy()
        d_c = next((c for c in df_sales.columns if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        df_sales['clean_date'] = clean_date(df_sales[d_c])

    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy dữ liệu bán hàng phù hợp", table_name="bán hàng")

    cols = df_sales.columns.tolist()
    prod_col = next((c for c in cols if any(k in str(c).lower() for k in ['tên hàng', 'sản phẩm', 'mặt hàng', 'tên thuốc', 'hàng'])), None)
    qty_col = next((c for c in cols if any(k in str(c).lower() for k in ['số lượng', 'soluong', 'sl', 'quy đổi'])), None)
    code_col = next((c for c in cols if any(k in str(c).lower() for k in ['mã hàng', 'mã hh', 'ma hang', 'mã sp', 'mã'])), prod_col)
    st_col = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt'])), None)

    # 2. Loại bỏ đơn hủy và lọc theo kỳ thời gian yêu cầu (ví dụ: tháng 9/2025)
    if st_col:
        df_sales = df_sales[~df_sales[st_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|cancel', regex=True, na=False)]
    mask = (df_sales['clean_date'].dt.year == 2025) & (df_sales['clean_date'].dt.month == 9)
    df_period = df_sales[mask]
    if df_period.empty:
        return []

    # 3. Tính tổng số lượng và xếp hạng theo Điều 9 Tie-Breaker
    df_period['clean_qty'] = clean_num(df_period[qty_col])
    grp = df_period.groupby([prod_col, code_col], as_index=False)['clean_qty'].sum()
    grp = grp.sort_values(by=['clean_qty', code_col], ascending=[False, True])

    # NẾU CÂU HỎI HỎI TOP-K (K >= 2, vd: "top 5 hàng bán chạy nhất", "3 mặt hàng bán nhiều nhất"):
    # BẮT BUỘC trả về danh sách chuỗi tên (list of strings đúng K phần tử):
    return grp.head(5)[prod_col].astype(str).tolist()

    # NẾU CÂU HỎI CHỈ HỎI 1 MẶT HÀNG ĐỨNG ĐẦU (Top-1, vd: "hàng nào chạy nhất", "sp bán chạy nhất"):
    # BẮT BUỘC trả về chuỗi ký tự đơn lẻ (scalar string):
    # return str(grp.iloc[0][prod_col])
```""",

    "ranking_customer": """--- VÍ DỤ MINH HỌA: XẾP HẠNG KHÁCH HÀNG CHI TIÊU NHIỀU NHẤT (TOP-K CUSTOMERS) ---
Câu hỏi: "Liệt kê 3 khách chi tiêu nhiều nhất trong tháng 6 năm 2025" (as_of_date = "2026-06-16")
```python
def solution(data):
    df_sales = None
    date_col = None
    cust_col = None
    amt_col = None

    # 1. Tìm bảng bán hàng/hóa đơn có cột ngày, cột khách hàng và cột thành tiền
    for name, df in data.items():
        if any(k in name.lower() for k in ['nhap', 'chiphi', 'tonkho', 'ncc']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
        c_c = next((c for c in cols if any(k in str(c).lower() for k in ['tên khách', 'khách hàng', 'khach_hang', 'customer', 'tên kh', 'khách'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tongtien', 'doanh thu', 'thực thu', 'khách phải trả', 'tổng cộng'])), None)
        if d_c and c_c and a_c:
            df_sales = df.copy()
            date_col, cust_col, amt_col = d_c, c_c, a_c
            break

    # Nếu bảng bán hàng tách rời bảng khách hàng:
    if df_sales is None:
        df_ord = next((df.copy() for n, df in data.items() if any(k in str(c).lower() for c in df.columns for k in ['ngày', 'date', 'thời gian']) and any(k in str(c).lower() for c in df.columns for k in ['khách', 'customer'])), None)
        if df_ord is not None:
            cols_o = df_ord.columns.tolist()
            d_c = next((c for c in cols_o if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
            c_c = next((c for c in cols_o if any(k in str(c).lower() for k in ['tên khách', 'khách hàng', 'khach_hang', 'customer', 'tên kh', 'khách'])), None)
            a_c = next((c for c in cols_o if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tongtien', 'doanh thu', 'thực thu', 'khách phải trả', 'tổng cộng'])), None)
            if d_c and c_c and a_c:
                df_sales = df_ord
                date_col, cust_col, amt_col = d_c, c_c, a_c

    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày, khách hàng và thành tiền", table_name="bán hàng", available_tables=list(data.keys()))

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    cols_s = df_sales.columns.tolist()
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt'])), None)
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|tra|cancel')]

    # Lọc thời gian: tháng 6 năm 2025
    mask = (df_sales['clean_date'].dt.year == 2025) & (df_sales['clean_date'].dt.month == 6)
    df_period = df_sales[mask]
    if df_period.empty:
        return []

    # Rulebook Điều 3: Bỏ khách lẻ / lẻ / nan / none
    df_cust = df_period[~df_period[cust_col].astype(str).str.lower().str.contains(r'lẻ|khách lẻ|khach le|nan|none|^$', regex=True, na=False)]
    if df_cust.empty:
        return []

    df_cust['clean_amt'] = clean_num(df_cust[amt_col])
    code_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['mã khách', 'mã kh', 'makh', 'ma_kh', 'customer_id'])), cust_col)

    # Xếp theo tổng tiền chi tiêu (doanh thu) giảm dần
    grp_cust = df_cust.groupby([cust_col, code_col], as_index=False)['clean_amt'].sum()
    grp_cust = grp_cust.sort_values(by=['clean_amt', code_col], ascending=[False, True])

    # Trả về danh sách Top-K tên khách hàng (list of strings: ['Tên 1', 'Tên 2', ...])
    return grp_cust.head(3)[cust_col].astype(str).tolist()
```""",

    "average_order_value": """--- VÍ DỤ MINH HỌA: TÍNH GIÁ TRỊ TRUNG BÌNH MỘT ĐƠN HÀNG (AOV) ---
Câu hỏi: "Giá trị trung bình một đơn tháng 10/2025 là bao nhiêu?" (as_of_date = "2026-05-29")
```python
def solution(data):
    # 1. Tìm bảng đơn hàng: nếu tách rời Header (DanhSachHoaDon / don_hang có ngày) và Detail (DanhSachHoaDonChiTiet / chi_tiet_don có tiền), ghép nối qua mã hóa đơn
    df_sales = None
    df_hdr = next((df for n, df in data.items() if any(k in str(c).lower() for c in df.columns for k in ['ngày', 'date', 'thời gian']) and not any(k in str(n).lower() for k in ['nhap', 'kho', 'chiphi'])), None)
    df_det = next((df for n, df in data.items() if any(k in str(c).lower() for c in df.columns for k in ['thành tiền', 'tổng tiền', 'tongtien', 'tiền']) and any(k in str(c).lower() for c in df.columns for k in ['mã', 'hóa đơn', 'đơn', 'order'])), None)

    if df_det is not None and df_hdr is not None and df_det is not df_hdr:
        kd = next((c for c in df_det.columns if any(k in str(c).lower() for k in ['mã hóa đơn', 'mã đơn hàng', 'mã đơn', 'mahd', 'order_id', 'mã'])), None)
        kh = next((c for c in df_hdr.columns if any(k in str(c).lower() for k in ['mã hóa đơn', 'mã đơn hàng', 'mã đơn', 'mahd', 'order_id', 'mã'])), None)
        dh = next((c for c in df_hdr.columns if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        if kd and kh and dh:
            df_sales = pd.merge(df_det, df_hdr[[kh, dh]], left_on=kd, right_on=kh, how='inner')
            df_sales['clean_date'] = clean_date(df_sales[dh])
    elif df_hdr is not None:
        df_sales = df_hdr.copy()
        d_c = next((c for c in df_sales.columns if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        df_sales['clean_date'] = clean_date(df_sales[d_c])

    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy dữ liệu đơn hàng phù hợp", table_name="đơn hàng")

    cols = df_sales.columns.tolist()
    order_col = next((c for c in cols if any(k in str(c).lower() for k in ['mã đơn hàng', 'mã hóa đơn', 'mã đơn', 'mahd', 'order_id', 'mã hd', 'mã'])), None)
    amt_col = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tongtien', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
    st_col = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt'])), None)

    # 2. Loại bỏ đơn hủy và lọc theo kỳ thời gian yêu cầu (ví dụ: tháng 10 năm 2025)
    if st_col:
        df_sales = df_sales[~df_sales[st_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|cancel', regex=True, na=False)]
    mask = (df_sales['clean_date'].dt.year == 2025) & (df_sales['clean_date'].dt.month == 10)
    df_period = df_sales[mask]
    if df_period.empty:
        return 0

    # 3. Tính doanh thu từng đơn và lấy giá trị trung bình một đơn (AOV)
    df_period['clean_amt'] = clean_num(df_period[amt_col])
    order_rev = df_period.groupby(order_col)['clean_amt'].sum()
    aov = order_rev.mean()
    # Làm tròn về đồng theo Điều 3 & Điều 9 (BẮT BUỘC return int(round(aov)), TUYỆT ĐỐI CẤM return int)
    return int(round(aov))
```""",

    "rate_percentage": """--- VÍ DỤ MINH HỌA: TÍNH TỈ LỆ PHẦN TRĂM (%) ---
Câu hỏi: "Tháng 6/2026 tỉ lệ hủy đơn là bao nhiêu phần trăm?" (as_of_date = "2026-06-30")
```python
def solution(data):
    df_ord = None
    date_col = None
    status_col = None
    for name, df in data.items():
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
        s_c = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'tình trạng', 'ghi chú tt'])), None)
        if d_c and s_c:
            df_ord = df.copy()
            date_col = d_c
            status_col = s_c
            break

    if df_ord is None:
        raise DataNotFoundError("Không tìm thấy bảng có cột ngày và trạng thái đơn", table_name="đơn hàng", available_tables=list(data.keys()))

    df_ord['clean_date'] = clean_date(df_ord[date_col])
    mask = (df_ord['clean_date'].dt.year == 2026) & (df_ord['clean_date'].dt.month == 6)
    df_period = df_ord[mask]
    total_orders = len(df_period)
    if total_orders == 0:
        return 0.0

    cancelled_count = len(df_period[df_period[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|cancel')])
    rate = (cancelled_count / total_orders) * 100.0
    return round(float(rate), 2)
```""",

    "inventory_unit_conversion": """--- VÍ DỤ MINH HỌA: TỒN KHO & QUY ĐỔI ĐƠN VỊ (HỘP VÀ VIÊN LẺ) ---
Câu hỏi: "Sản phẩm Hapacol 650 còn tồn bao nhiêu hộp chẵn và bao nhiêu viên lẻ?" (as_of_date = "2026-07-31")
```python
def solution(data):
    df_stock = None
    prod_col = None
    remain_col = None
    unit_col = None
    for name, df in data.items():
        cols = df.columns.tolist()
        r_c = next((c for c in cols if any(k in str(c).lower() for k in ['tồn cuối', 'số lượng tồn', 'tồn kho', 'soluongton', 'tồn thực'])), None)
        p_c = next((c for c in cols if any(k in str(c).lower() for k in ['tên hàng', 'sản phẩm', 'mặt hàng', 'product'])), None)
        if r_c and p_c:
            df_stock = df.copy()
            remain_col = r_c
            prod_col = p_c
            unit_col = next((c for c in cols if any(k in str(c).lower() for k in ['quy cách', 'đơn vị', 'đvt'])), None)
            break

    if df_stock is None:
        raise DataNotFoundError("Không tìm thấy bảng tồn kho trong dữ liệu", table_name="tồn kho", available_tables=list(data.keys()))

    matched = df_stock[df_stock[prod_col].astype(str).str.lower().str.contains('hapacol 650', na=False)]
    if matched.empty:
        raise DataNotFoundError("Không tìm thấy mặt hàng trong bảng tồn kho", column_name=prod_col)

    total_units = int(round(clean_num(matched[remain_col]).iloc[0]))
    packing_size = 100
    if unit_col and not matched[unit_col].isna().all():
        val = matched[unit_col].iloc[0]
        m = re.search(r"\\d+", str(val))
        if m:
            packing_size = int(m.group(0))

    boxes, pills = divmod(total_units, packing_size)
    return [int(boxes), int(pills)]
```""",

    "time_series": """--- VÍ DỤ MINH HỌA: PHÂN TÍCH CHUỖI THỜI GIAN & SO SÁNH KỲ LIỀN TRƯỚC ---
Câu hỏi: "Doanh thu tháng này tăng hay giảm bao nhiêu phần trăm so với tháng trước?" (as_of_date = "2026-05-25")
```python
def solution(data):
    df_sales = None
    date_col = None
    amt_col = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        if any(k in n_clean for k in ['nhap', 'kho', 'chiphi', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            date_col = d_c
            amt_col = a_c
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền", table_name="bán hàng", available_tables=list(data.keys()))

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    df_sales['clean_amt'] = clean_num(df_sales[amt_col])

    mask_curr = (df_sales['clean_date'].dt.date >= pd.to_datetime("2026-05-01").date()) & (df_sales['clean_date'].dt.date <= pd.to_datetime("2026-05-25").date())
    mask_prev = (df_sales['clean_date'].dt.date >= pd.to_datetime("2026-04-01").date()) & (df_sales['clean_date'].dt.date <= pd.to_datetime("2026-04-25").date())

    rev_curr = df_sales[mask_curr]['clean_amt'].sum()
    rev_prev = df_sales[mask_prev]['clean_amt'].sum()

    if rev_prev == 0:
        return 0.0

    pct_change = ((rev_curr - rev_prev) / rev_prev) * 100.0
    return round(float(pct_change), 2)
```""",

    "unanswerable_suspect": """--- VÍ DỤ MINH HỌA: CÂU HỎI THIẾU DỮ LIỆU HOẶC KHÔNG THỂ TRẢ LỜI ---
Câu hỏi: "Nhân viên nào có tay nghề cao nhất tiệm?" (as_of_date = "2026-07-31")
```python
def solution(data):
    has_skill = any('tay nghề' in str(c).lower() or 'trình độ' in str(c).lower() for df in data.values() for c in df.columns)
    if not has_skill:
        raise DataNotFoundError("Dữ liệu không có thông tin về tay nghề hoặc trình độ", column_name="tay nghề")
    return None
```""",
}


def retrieve_dynamic_few_shot(question: str, intent: str, entity_matches: Optional[List[Any]] = None) -> str:
    """Truy hồi ví dụ minh họa tối ưu nhất cho câu hỏi."""
    q_low = question.lower()

    if any(k in q_low for k in ["khách", "khach"]) and any(k in q_low for k in ["chi tiêu", "chi tieu", "mua nhiều", "nhiều nhất", "top", "cao nhất", "tiêu nhiều", "nhiều tiền"]):
        example = EXEMPLAR_BANK.get("ranking_customer")
    elif intent == "average_order_value" or re.search(r"(?:gi[aá]s?\s*tr[iị]\s*)?trung\s*b[iì]nh\s*(?:m[oộ]t|1)\s*đ[oơ]n|tb\s*(?:m[oộ]t|1)\s*đ[oơ]n|\baov\b", q_low):
        example = EXEMPLAR_BANK.get("average_order_value")
    elif any(k in q_low for k in ["hộp chẵn", "viên lẻ", "thùng và chai", "tồn kho"]):
        example = EXEMPLAR_BANK.get("inventory_unit_conversion")
    elif any(k in q_low for k in ["tăng liên tục", "so với", "thay đổi bao nhiêu", "tăng trưởng"]):
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
# 7. HÀM TẠO PROMPT CHÍNH & PROMPT SỬA LỖI
# ==============================================================================

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

    temporal_info = resolve_temporal_context(question, as_of_date)
    temporal_lines = [f"- Mốc tham chiếu (as_of_date / hôm nay): {temporal_info['as_of_date']}"]
    if temporal_info.get("comparison_start") and temporal_info.get("comparison_end"):
        temporal_lines.append(f"- Kỳ chính: từ '{temporal_info.get('start_date')}' đến '{temporal_info.get('end_date')}'")
        temporal_lines.append(f"- Kỳ đối chiếu: từ '{temporal_info.get('comparison_start')}' đến '{temporal_info.get('comparison_end')}' ({temporal_info.get('comparison_desc', '')})")
    else:
        temporal_lines.append(f"- Khoảng thời gian giải mã: {temporal_info['description']}")
    temporal_lines.append(f"- Gợi ý lọc Pandas: {temporal_info['code_hint']}")
    temporal_text = "\n".join(temporal_lines)

    entity_block = ""
    matches = entity_matches
    if matches is None and candidates and link_entities is not None:
        try:
            matches = link_entities(question, candidates=candidates, threshold=0.55)
        except Exception:
            matches = None

    if matches:
        entity_lines = []
        for m in matches[:5]:
            val = getattr(m, "matched_value", str(m))
            term = getattr(m, "query_term", "")
            meta = getattr(m, "metadata", {}) or {}
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
        rb_text = extract_relevant_rulebook_clauses(rulebook_content, question, max_chars=1000)
        if rb_text:
            rulebook_block = f"\n==================== QUY TẮC NGHIỆP VỤ BẮT BUỘC ====================\n{rb_text}\n"

    biz_context = ""
    if business_note and business_note.strip():
        biz_context = f"\nGHI CHÚ DOANH NGHIỆP:\n{business_note.strip()}\n"

    req_3 = "3. Không lặp dict comprehension lọc ngày trên toàn bộ `data`. Tìm bảng cụ thể, tìm cột ngày gốc bằng `d_c = next(...)`, tự tạo `df['clean_date'] = clean_date(df[d_c])` và dùng trực tiếp `df['clean_date'].dt.year`, `df['clean_date'].dt.month`. TUYỆT ĐỐI CẤM gọi `.dt.date` trước `.dt.year` hoặc `.dt.month`."
    if intent in ("count_orders", "cancelled_orders"):
        req_3 += " Khi đếm đơn, BẮT BUỘC tìm cột mã đơn order_col = next(...) và đếm int(df[order_col].dropna().nunique()). TUYỆT ĐỐI CẤM đếm theo cột ngày tháng và TUYỆT ĐỐI CẤM tính tổng doanh thu."
    elif intent == "quantity_sum":
        req_3 += " Khi tính số lượng (ly, kg), BẮT BUỘC tìm cột số lượng qty_col = next(...) và tính tổng int(round(clean_num(df[qty_col]).sum())). TUYỆT ĐỐI CẤM tính tổng cột tiền. Phân tách rõ: 'ly' là đơn vị tính, kích cỡ '(M)' nằm ở tên hàng."
    elif intent == "price_lookup":
        req_3 += " Khi tra cứu giá, tìm cột đơn giá / giá bán của đúng sản phẩm. TUYỆT ĐỐI CẤM tính trung bình toàn bộ danh mục df['Giá bán'].mean() và TUYỆT ĐỐI CẤM tính tổng doanh thu."
    else:
        req_3 += " Dùng biến cột động amt_col = next(...) và tính tổng clean_num(df[amt_col]).sum(). Nếu câu hỏi hỏi một ngày cụ thể (như hôm nay), BẮT BUỘC lọc df['clean_date'].dt.date == pd.to_datetime(target_date).date(). Nếu câu hỏi hỏi riêng một sản phẩm/món, BẮT BUỘC lọc theo cột tên hàng trước."

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

    user_prompt = f"""==================== DỮ LIỆU ĐẦU VÀO CHO BÀI TOÁN CẦN GIẢI ====================
DANH SÁCH BẢNG VÀ CỘT DỮ LIỆU TRONG `data`:
{active_schema}
{biz_context}
==================== CÂU HỎI & RÀNG BUỘC CỐT LÕI ====================
CÂU HỎI CỦA NGƯỜI DÙNG:
"{question}"

RÀNG BUỘC MỐC THỜI GIAN & THỰC THỂ:
{temporal_text}
{entity_block}
YÊU CẦU THỰC HIỆN:
1. Quan sát danh sách bảng và cột ở trên để chọn đúng bảng và cột. Không đoán tên bảng có ký tự lạ.
2. Áp dụng khoảng thời gian đã được giải mã và mốc as_of_date để lọc dữ liệu.
{req_3}
{return_format_instruction}
5. Chỉ viết duy nhất một hàm `def solution(data):` trả về kết quả, không viết giải thích bên ngoài.
6. Viết code ngắn gọn, không viết comment dài dòng để tránh bị cắt cụt token.
```python
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
2. Kiểm tra danh sách bảng và cột thực tế trong data để chọn đúng cột và bảng.
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
    "EXEMPLAR_BANK",
    "FEW_SHOT_LIBRARY",
    "select_few_shots",
    "TET_SOLAR_RANGES",
    "load_rulebook",
]
