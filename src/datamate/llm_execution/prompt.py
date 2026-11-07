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
        "phiếu nhập hàng", "tiền mua hàng", "giá trị các phiếu nhập"
    ]):
        return "purchase_import"

    if re.search(
        r"(?<!\d)%|ph[ầa]n\s*tr(?:[ăa]m|awm)|\bt[ỉỷi]\s*l[ệe]\b|\bty\s*le\b|\bt[ỉỷi]\s*tr[ọo]ng\b",
        q_lower,
    ):
        return "rate_percentage"

    if any(k in q_lower for k in ["tăng liên tục", "tăng giảm", "so với", "thay đổi bao nhiêu", "tăng trưởng"]):
        return "time_series"

    if any(k in q_lower for k in [
        "bán chạy nhất", "bán chạy", "nhiều nhất", "nhiều tiền nhất", "cao nhất",
        "thấp nhất", "lời nhất", "đắt nhất", "top", "xếp thứ", "hot nhất", "giỏi nhất"
    ]):
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
) -> str:
    """
    Rút gọn Schema động: Chỉ giữ lại các bảng liên quan đến Intent và câu hỏi.
    Loại bỏ các bảng nội bộ (chi phí, sổ quỹ, lương, chấm công) khi không được hỏi
    để giải phóng Context Window và ngăn chặn mô hình chọn nhầm bảng.
    """
    if not schema_str or not schema_str.strip():
        return ""

    q_low = question.lower()

    entity_tables = set()
    if entity_matches:
        for m in entity_matches:
            meta = getattr(m, "metadata", {}) or {}
            tbl = meta.get("source_table")
            if tbl:
                entity_tables.add(str(tbl).lower())

    explicit_expense = any(k in q_low for k in ["chi phí", "khoản chi", "sổ quỹ", "tiền điện", "tiền nước", "mặt bằng", "chi_phi"])
    explicit_import = any(k in q_low for k in ["nhập hàng", "phiếu nhập", "nhà cung cấp", "tiền nhập", "nhap_hang"])
    explicit_debt = any(k in q_low for k in ["công nợ", "sổ nợ", "còn nợ", "tuổi nợ", "hạn nợ", "phải thu"])
    explicit_employee = any(k in q_low for k in ["nhân viên", "lương", "chấm công", "ca làm"])
    explicit_customer = any(k in q_low for k in ["khách hàng", "khách", "sđt", "điện thoại"])
    explicit_inventory = any(k in q_low for k in ["tồn kho", "thẻ kho", "còn tồn", "tồn cuối", "hộp", "viên"])

    table_blocks = re.split(r"(?=(?:^|\n)-\s*Bảng\s+)", schema_str)
    header = table_blocks[0] if table_blocks and not table_blocks[0].strip().startswith("- Bảng") else ""
    table_items = [b.strip() for b in table_blocks if b.strip().startswith("- Bảng")]

    if len(table_items) <= 3:
        return schema_str

    kept_tables: List[str] = []
    for item in table_items:
        item_low = item.lower()
        tbl_name_m = re.search(r"Bảng\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?", item)
        tbl_name = tbl_name_m.group(1).lower() if tbl_name_m else ""

        if tbl_name and (tbl_name in q_low or tbl_name in entity_tables):
            kept_tables.append(item)
            continue

        is_sales = any(k in item_low for k in ["bán hàng", "hóa đơn", "donhang", "hoadon", "banhang", "pos"])
        is_product = any(k in item_low for k in ["sản phẩm", "thuốc", "hanghoa", "sanpham", "danhmuc", "bảng giá"])
        is_expense = any(k in item_low for k in ["chi phí", "chiphi", "sổ quỹ", "soquy"])
        is_import = any(k in item_low for k in ["nhập hàng", "nhaphang", "nhà cung cấp", "ncc"])
        is_debt = any(k in item_low for k in ["công nợ", "congno", "sổ nợ", "sono"])
        is_cust = any(k in item_low for k in ["khách hàng", "khachhang", "customer"])
        is_inv = any(k in item_low for k in ["tồn kho", "tonkho", "thekho"])
        is_hr = any(k in item_low for k in ["lương", "nhân viên", "nhanvien", "chamcong"])

        if intent == "cong_no":
            if is_debt or is_cust or is_sales or explicit_debt:
                kept_tables.append(item)
            continue

        if intent == "purchase_import":
            if is_import or is_product or explicit_import:
                kept_tables.append(item)
            continue

        if intent == "inventory_unit_conversion":
            if is_inv or is_product or is_sales or explicit_inventory:
                kept_tables.append(item)
            continue

        if is_expense and not explicit_expense:
            continue
        if is_hr and not explicit_employee:
            continue
        if is_debt and not explicit_debt:
            continue
        if is_import and not explicit_import:
            continue
        if is_cust and not explicit_customer and intent not in ("ranking_topk", "aggregation"):
            continue

        kept_tables.append(item)

    if len(kept_tables) < 2:
        return schema_str

    prefix = f"{header.strip()}\n\n" if header.strip() else ""
    return prefix + "\n\n".join(kept_tables)


# ==============================================================================
# 4. CHỈ DẪN HỆ THỐNG ĐỘNG (INTENT-DRIVEN SYSTEM INSTRUCTION)
# ==============================================================================

def build_dynamic_system_instruction(intent: str, question: str) -> str:
    """Tạo chỉ dẫn hệ thống tinh gọn, chỉ chứa đúng các quy tắc cần thiết cho câu hỏi."""
    q_low = question.lower()

    core = """Bạn là một chuyên gia phân tích dữ liệu kinh doanh bằng Python/Pandas.
Nhiệm vụ của bạn là viết một hàm duy nhất:
```python
def solution(data):
    # logic tính toán an toàn
    return result
```
NGUYÊN TẮC THIẾT KẾ MÃ NGUỒN (CODE GENERATION RULES):
1. THAM SỐ `data`: Dictionary `{tên_bảng: DataFrame}` chứa dữ liệu gốc từ Excel/CSV (hỗ trợ tra cứu mềm không phân biệt dấu/hoa thường).
   - Tuyệt đối KHÔNG lặp dict comprehension trên toàn bộ `data` để lọc ngày (bảng sản phẩm không có ngày!).
   - Tìm đúng bảng cần dùng -> tìm cột ngày gốc `d_c = next(...)` -> tạo `df['clean_date'] = clean_date(df[d_c])`.
   - Lọc ngày: `(df['clean_date'].dt.date >= pd.to_datetime(start_date).date()) & (df['clean_date'].dt.date <= pd.to_datetime(end_date).date())`.
   - Dùng biến cột động `amt_col = next(...)` và `clean_num(df[amt_col])` thay vì hardcode tên cột.
2. TIỆN ÍCH CÓ SẴN Ở GLOBAL SCOPE: `clean_num`, `clean_date`, `apply_tie_breaker`, `filter_future_data`, `re`, `math`, `datetime`, `date`, `timedelta`, `pct`.
   - TUYỆT ĐỐI CẤM định nghĩa lại hoặc import lại các hàm/module này trong code.
3. Bản ghi có ngày > as_of_date coi như chưa xảy ra (loại bỏ khỏi tính toán).
4. XỬ LÝ KHI DỮ LIỆU RỖNG HOẶC KHÔNG PHÁT SINH:
   - Nếu sau khi lọc theo ngày/điều kiện mà DataFrame rỗng (không có đơn hàng nào trong kỳ):
     * Doanh thu / Tiền hàng / Số lượng: BẮT BUỘC return 0 (không có doanh thu / 0 đơn).
     * Tỉ lệ phần trăm %: BẮT BUỘC return 0.0 (tỉ lệ hủy là 0.0%).
     * Top K / Mặt hàng: return "" hoặc [].
     * TUYỆT ĐỐI CẤM return None hoặc raise lỗi khi chỉ đơn giản là không có giao dịch trong kỳ.
5. Chỉ raise DataNotFoundError khi dữ liệu hoàn toàn thiếu hẳn bảng nghiệp vụ mà câu hỏi yêu cầu. TUYỆT ĐỐI CẤM trả về chuỗi 'unanswerable'."""

    conditional_rules: List[str] = []

    if any(k in q_low for k in ["mấy đơn", "bao nhiêu đơn", "số đơn", "số lượng đơn", "so don"]):
        conditional_rules.append(
            "- [Đếm số lượng đơn]: Câu hỏi hỏi 'mấy đơn' / 'bao nhiêu đơn' -> kết quả BẮT BUỘC là đếm số lượng: `int(len(df))` hoặc `int(df[ma_don].nunique())`, TUYỆT ĐỐI KHÔNG TÍNH TỔNG TIỀN."
        )

    if any(k in q_low for k in ["doanh thu", "tiền bán", "tổng tiền", "bán chạy", "doanh so", "doanh số", "mua nhiều"]):
        conditional_rules.append(
            "- [Doanh thu hợp lệ]: Chỉ tính đơn KHÔNG huỷ và KHÔNG trả hàng (`trang_thai NOT IN ('huỷ', 'trả hàng', 'hủy', 'tra_hang')`)."
        )

    is_ranking = intent == "ranking_topk" or any(k in q_low for k in ["nhất", "top", "xếp hạng", "cao nhất", "thấp nhất", "nhiều nhất", "ít nhất"])
    if is_ranking:
        conditional_rules.append(
            "- [Quy tắc đồng hạng (Điều 9)]: Khi hai đối tượng bằng điểm nhau, sắp xếp theo MÃ tăng dần (nếu không có mã thì theo TÊN tăng dần). "
            "Dùng `apply_tie_breaker(records, sort_key, code_key, name_key)` hoặc `df.sort_values(by=[tieu_chi, ma_hoac_ten], ascending=[False, True])`."
        )

    is_pharma_inv = intent in ("inventory_unit_conversion", "multitable_join") or any(k in q_low for k in ["hộp", "viên", "chai", "thùng", "quy đổi", "divmod", "tồn"])
    if is_pharma_inv:
        conditional_rules.append(
            "- [Quy đổi tồn kho (Điều 5)]: Dùng `divmod(tong_so_luong, quy_cach)` để trả về list 2 số nguyên: `[số_hộp_chẵn, số_viên_lẻ]`."
        )

    if "khách" in q_low or "khach" in q_low:
        conditional_rules.append(
            "- [Khách hàng (Điều 3)]: Khi xếp hạng hoặc đếm khách, loại bỏ khách lẻ/vãng lai ('lẻ', 'khách lẻ', 'kl', 'nan', 'none')."
        )

    if intent in ("rate_percentage", "time_series") or any(k in q_low for k in ["%", "phần trăm", "tỉ lệ", "tỷ lệ", "so với", "tăng trưởng"]):
        conditional_rules.append(
            "- [Tỉ lệ / Phần trăm]: Trả về float làm tròn 2 chữ số thập phân (vd: `12.50`, `1.06`), không kèm ký tự '%'."
        )

    rules_text = "\n".join(conditional_rules) if conditional_rules else "- Tính toán chính xác theo đúng yêu cầu trong câu hỏi."

    output_format = """ĐỊNH DẠNG ĐÁP ÁN:
- Số nguyên/tiền: `int` | Tỉ lệ %: `float` (làm tròn 2 chữ số) | Ngày: `"YYYY-MM-DD"` | Top K: `list` | Bảng: `dict`.
- Viết code ngắn gọn, súc tích trong duy nhất hàm `def solution(data):`, không viết comment dài dòng."""

    return f"{core}\n\nQUY TẮC NGHIỆP VỤ BẮT BUỘC:\n{rules_text}\n\n{output_format}"


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
        df_nhap = df_nhap[~df_nhap[st_c].astype(str).str.lower().str.contains('hủy|huỷ|cancel')]

    return int(round(clean_num(df_nhap[a_c]).sum()))
```""",

    "aggregation": """--- VÍ DỤ MINH HỌA: TÍNH TỔNG DOANH THU / SỐ TIỀN / LƯỢNG BÁN ---
Câu hỏi: "Tháng này tổng giá trị các đơn bán hàng là bao nhiêu?" (as_of_date = "2026-05-25")
```python
def solution(data):
    df_sales = None
    date_col = None
    amt_col = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        if any(k in n_clean for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            date_col = d_c
            amt_col = a_c
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền", table_name="bán hàng", available_tables=list(data.keys()))

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    cols_s = df_sales.columns.tolist()
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'tình trạng'])), None)
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains('hủy|huỷ|trả|cancel')]

    df_sales['clean_amt'] = clean_num(df_sales[amt_col])
    mask = (df_sales['clean_date'].dt.year == 2026) & (df_sales['clean_date'].dt.month == 5) & (df_sales['clean_date'].dt.date <= pd.to_datetime("2026-05-25").date())
    return int(round(df_sales[mask]['clean_amt'].sum()))
```""",

    "ranking_topk": """--- VÍ DỤ MINH HỌA: TÌM ĐỐI TƯỢNG NHIỀU NHẤT / XẾP HẠNG (RANKING TOP-K) / ĐỒNG HẠNG ---
Câu hỏi: "Dịp Tết 2026, mặt hàng nào bán chạy nhất?" (as_of_date = "2026-06-28")
```python
def solution(data):
    df_sales = None
    date_col = None
    prod_col = None
    qty_col = None

    # 1. Tìm bảng có đủ cột hoặc tìm bảng chi tiết và bảng hóa đơn để ghép nối
    for name, df in data.items():
        if any(k in name.lower() for k in ['nhap', 'chiphi', 'tonkho', 'ncc']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
        p_c = next((c for c in cols if any(k in str(c).lower() for k in ['tên hàng', 'sản phẩm', 'mặt hàng', 'product', 'tên thuốc'])), None)
        q_c = next((c for c in cols if any(k in str(c).lower() for k in ['số lượng', 'soluong', 'sl', 'quy đổi', 'slquydoi'])), None)
        if d_c and p_c and q_c:
            df_sales = df.copy()
            date_col, prod_col, qty_col = d_c, p_c, q_c
            break

    # Nếu bảng chi tiết (chứa tên hàng, số lượng) tách rời với bảng hóa đơn (chứa ngày bán):
    if df_sales is None:
        df_detail = next((df.copy() for n, df in data.items() if any(k in str(c).lower() for c in df.columns for k in ['tên hàng', 'sản phẩm', 'tên thuốc']) and any(k in str(c).lower() for c in df.columns for k in ['số lượng', 'sl'])), None)
        df_order = next((df.copy() for n, df in data.items() if any(k in str(c).lower() for c in df.columns for k in ['ngày', 'date', 'thời gian']) and any(k in str(c).lower() for c in df.columns for k in ['mã', 'hóa đơn', 'đơn'])), None)
        if df_detail is not None and df_order is not None:
            kd = next((c for c in df_detail.columns if any(k in str(c).lower() for k in ['mã', 'đơn', 'hóa đơn', 'mahd', 'order'])), None)
            ko = next((c for c in df_order.columns if any(k in str(c).lower() for k in ['mã', 'đơn', 'hóa đơn', 'mahd', 'order'])), None)
            if kd and ko:
                d_c = next((c for c in df_order.columns if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
                df_sales = pd.merge(df_detail, df_order[[ko, d_c]], left_on=kd, right_on=ko, how='inner')
                date_col = d_c
                prod_col = next((c for c in df_sales.columns if any(k in str(c).lower() for k in ['tên hàng', 'sản phẩm', 'mặt hàng', 'product', 'tên thuốc'])), None)
                qty_col = next((c for c in df_sales.columns if any(k in str(c).lower() for k in ['số lượng', 'soluong', 'sl'])), None)

    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày, tên hàng và số lượng", table_name="bán hàng", available_tables=list(data.keys()))

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    cols_s = df_sales.columns.tolist()
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt'])), None)
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains('hủy|huỷ|trả|cancel')]

    df_sales['clean_qty'] = clean_num(df_sales[qty_col])
    # Dịp Tết 2026: 2026-02-10 đến 2026-02-26
    mask = (df_sales['clean_date'].dt.date >= pd.to_datetime("2026-02-10").date()) & (df_sales['clean_date'].dt.date <= pd.to_datetime("2026-02-26").date())
    df_period = df_sales[mask]
    if df_period.empty:
        return ""

    code_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['mã hàng', 'mã hh', 'ma hang', 'mã sp', 'mã thuốc'])), prod_col)
    grp = df_period.groupby([prod_col, code_col], as_index=False)['clean_qty'].sum()
    grp = grp.sort_values(by=['clean_qty', code_col], ascending=[False, True])
    return str(grp.iloc[0][prod_col])
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

    cancelled_count = len(df_period[df_period[status_col].astype(str).str.lower().str.contains('hủy|huỷ|cancel')])
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

    if any(k in q_low for k in ["hộp chẵn", "viên lẻ", "thùng và chai", "tồn kho"]):
        example = EXEMPLAR_BANK.get("inventory_unit_conversion")
    elif any(k in q_low for k in ["tăng liên tục", "so với", "thay đổi bao nhiêu", "tăng trưởng"]):
        example = EXEMPLAR_BANK.get("time_series")
    elif any(k in q_low for k in ["bán chạy", "nhiều nhất", "top", "cao nhất", "ít nhất", "thấp nhất"]):
        example = EXEMPLAR_BANK.get("ranking_topk")
    elif any(k in q_low for k in ["công nợ", "cong no", "còn nợ", "con no", "tuổi nợ", "hạn nợ", "hạn trả", "phải thu", "khách nợ", "sổ nợ", "chưa trả"]):
        example = EXEMPLAR_BANK.get("cong_no")
    elif any(k in q_low for k in ["nhập hàng", "phiếu nhập", "tiền nhập", "nhap hang", "phieu nhap", "mua hàng", "cần trả ncc", "nhập kho"]):
        example = EXEMPLAR_BANK.get("purchase_import")
    elif any(k in q_low for k in ["%", "phần trăm", "tỉ lệ", "tỷ lệ"]):
        example = EXEMPLAR_BANK.get("rate_percentage")
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

    dynamic_sys_instruction = build_dynamic_system_instruction(intent=intent, question=question)
    system_prompt = f"{dynamic_sys_instruction}\n{rulebook_block}\n{few_shot_block}".strip()

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
3. Không lặp dict comprehension lọc ngày trên toàn bộ `data`. Tìm bảng cụ thể, tìm cột ngày gốc bằng `d_c = next(...)`, tự tạo `df['clean_date'] = clean_date(df[d_c])` và dùng biến cột động `amt_col` thay vì hardcode tên cột.
4. Chỉ viết duy nhất một hàm `def solution(data):` trả về kết quả, không viết giải thích bên ngoài.
5. Viết code ngắn gọn, không viết comment dài dòng để tránh bị cắt cụt token.
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
    retry_sys_prompt = """Bạn là chuyên gia sửa lỗi mã nguồn Python/Pandas phân tích dữ liệu.
Nhiệm vụ: Sửa lỗi mã nguồn vừa sinh và viết lại duy nhất một hàm hoàn chỉnh:
```python
def solution(data):
    # logic tính toán an toàn đã sửa lỗi
    return result
```
NGUYÊN TẮC:
- Quan sát lỗi gặp phải và sửa đúng dòng bị sai.
- Dùng các tiện ích đã có sẵn: `clean_num`, `clean_date`, `apply_tie_breaker`, `filter_future_data`.
- Không hardcode tên cột cố định. Dùng `next(...)` để tìm cột động nếu gặp KeyError.
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
