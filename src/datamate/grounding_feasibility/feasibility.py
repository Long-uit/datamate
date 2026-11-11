"""
Module: src/datamate/llm/feasibility.py
Mục đích: Module 3 — Deterministic Feasibility Gate (Lá chắn chống phạt điểm âm).
          Tự động phát hiện các câu hỏi bất khả thi từ dữ liệu và trả về ngay
          'unanswerable' (+1 điểm) mà không cần gọi LLM sinh mã.

Quy tắc nghiệp vụ cốt lõi (Rulebook Zalo AI Challenge 2026):
1. Điều 7 (Kỳ câu hỏi nằm ngoài khoảng dữ liệu):
   - Nếu khoảng thời gian của câu hỏi (hoặc kỳ đối chiếu bắt buộc như 'so với tháng liền trước')
     nằm HOÀN TOÀN ngoài khoảng ngày giao dịch [min_date, max_date] của shop
     -> Bắt buộc trả về 'unanswerable'.
   - Nếu câu hỏi có một phần nằm trong khoảng dữ liệu của shop
     -> Vẫn khả thi (tính trên phần có dữ liệu).
2. Dữ liệu không chứa loại thông tin được hỏi:
   - Câu hỏi đòi hỏi các thuộc tính chủ quan (tay nghề, lành nghề, tận tâm, lễ phép, chu đáo,
     khách khen, quý mến, thái độ, mức độ hài lòng, thời tiết...) hoặc kiến thức y khoa ngoài dữ liệu.
   - Câu hỏi đòi hỏi bảng/cột nghiệp vụ mà shop không hề có (tồn kho, hạn dùng, giá nhập, công nợ,
     địa chỉ khách, giới tính khách, nhóm khách thân thiết, kênh bán, hình thức thanh toán, lý do hủy/trả...).
3. Tối ưu thời gian và chi phí:
   - Ngắt luồng sớm, không nạp LLM vào GPU cho các câu unanswerable, tiết kiệm 30-50s/câu.
Tác giả: Long (AI Architect & Model Lead)
"""

from __future__ import annotations

import calendar
import datetime
import re
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import unicodedata
except ImportError:
    unicodedata = None

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from .temporal import (
        extract_query_date_range,
        extract_comparison_date_range,
        resolve_temporal,
        get_calendar,
    )
    _extract_comparison_date_range = extract_comparison_date_range
except ImportError:
    resolve_temporal = None
    get_calendar = None


def _nfc(text: str) -> str:
    if unicodedata is not None and text:
        return unicodedata.normalize("NFC", str(text))
    return str(text) if text is not None else ""


# ==============================================================================
# TỪ ĐIỂN TỪ KHÓA BẤT KHẢ THI (UNANSWERABLE KEYWORDS & PATTERNS)
# ==============================================================================

# Nhóm 1: Thuộc tính chủ quan, đánh giá cảm tính hoặc kiến thức y khoa ngoài dữ liệu POS
SUBJECTIVE_UNANSWERABLE_PATTERNS = [
    r"bằng\s*cấp",
    r"chuyên\s*môn",
    r"sở\s*thích",
    r"tay\s*nghề",
    r"lành\s*nghề",
    r"kinh\s*nghiệm",
    r"thái\s*độ",
    r"tận\s*tâm",
    r"lễ\s*phép",
    r"chu\s*đáo",
    r"quý\s*mến",
    r"khách\s*(?:hàng\s*)?(?:hay\s*)?khen",
    r"nhân\s*viên\s*(?:nào\s*)?(?:giỏi|tốt|chăm|xuất\s*sắc|đẹp(?:\s*trai|\s*gái)?|xinh(?:\s*gái|\s*đẹp)?|thân\s*thiện|vui\s*tính|chuyên\s*nghiệp)\s*nhất",
    r"chất\s*lượng\s*(?:phục\s*vụ|dịch\s*vụ)",
    r"độ\s*hài\s*lòng",
    r"(?:khách\s*hàng\s*)?(?:thích|ưa\s*chuộng|yêu\s*thích)(?:\s+\w+){0,4}\s*nhất",
    r"ưa\s*chuộng",
    r"thời\s*tiết",
    r"nhiệt\s*độ",
    r"vị\s*trí\s*địa\s*lý",
    r"khoảng\s*cách",
    r"tâm\s*trạng",
    r"uống\s*mỗi\s*lần\s*mấy\s*viên",
    r"liều\s*lượng\s*(?:uống|dùng)",
]

# Nhóm 2: Yêu cầu thông tin chi phí vận hành / lãi ròng
PROFIT_KEYWORDS = [
    "lãi ròng",
    "lợi nhuận thuần",
    "chi phí mặt bằng",
    "tiền điện",
    "tiền nước",
    "lương nhân viên",
]

# Nhóm 3: Yêu cầu thông tin nhà cung cấp
SUPPLIER_KEYWORDS = [
    "nhà cung cấp",
    "nơi nhập",
    "cty nhập",
    "công ty cung cấp",
    "đơn vị giao hàng",
]

# Các cột ngày KHÔNG phải ngày giao dịch phát sinh (loại trừ khi tính min_date/max_date hoạt động)
NON_TRANSACTION_DATE_PATTERNS = [
    r"hạn\s*sử\s*dụng",
    r"hạn\s*dùng",
    r"han_su_dung",
    r"han_dung",
    r"\bhsd\b",
    r"hạn\s*thanh\s*toán",
    r"han\s*tra",
    r"han_tra",
    r"ngày\s*tạo\s*khách",
    r"ngày\s*tạo\s*mặt\s*hàng",
    r"ngày\s*đăng\s*ký",
    r"ngày\s*vào\s*làm",
    r"ngày\s*sinh",
    r"ngày\s*áp\s*dụng",
    r"ngay_ap_dung",
    r"từ\s*ngày",
    r"đến\s*ngày",
]

# Các bảng danh mục tĩnh (không dùng để tính min_date/max_date giao dịch)
CATALOG_TABLE_PATTERNS = [
    "banggia",
    "lichsugia",
    "lich_su_gia",
    "khachhang",
    "khach_hang",
    "sanpham",
    "san_pham",
    "hanghoa",
    "hang_hoa",
    "danhmuc",
    "danh_muc",
    "quydoi",
    "quy_doi",
    "donvitinh",
    "don_vi",
    "thuoc",
    "nhanvien",
    "nhan_vien",
]


def _is_transaction_date_col(col_name: str) -> bool:
    c_low = _nfc(col_name).lower()
    if any(re.search(pat, c_low) for pat in NON_TRANSACTION_DATE_PATTERNS):
        return False
    return any(k in c_low for k in ["ngày", "ngay", "date", "ngaylap", "thoigian", "thời gian", "thoi_gian"])


def _is_catalog_table(table_name: str) -> bool:
    t_low = _nfc(table_name).lower().replace(" ", "_")
    # Nếu bảng là hóa đơn / đơn hàng / bán hàng / nhập hàng / phiếu thu -> bảng giao dịch
    if any(k in t_low for k in ["donhang", "don_hang", "hoadon", "hoa_don", "banhang", "ban_hang", "chi_tiet", "chitiet", "nhaphang", "nhap_hang", "phieuthu", "phieu_thu", "soquy", "so_quy"]):
        return False
    return any(k in t_low for k in CATALOG_TABLE_PATTERNS)


# ==============================================================================
# HÀM TRÍCH XUẤT METADATA CỬA HÀNG (SHOP METADATA EXTRACTION)
# ==============================================================================

def extract_shop_metadata(
    business_obj: Any = None,
    data_dict: Optional[Dict[str, Any]] = None,
    readme_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Trích xuất metadata chuẩn hóa từ dữ liệu của một cửa hàng:
    - min_date, max_date: Khoảng thời gian giao dịch thực tế (quét toàn bộ cột ngày giao dịch,
      kết hợp thông tin sheet tháng và README.md, tuyệt đối không cắt .head(2000)).
    - table_names, columns_by_table, all_columns.
    - Các cờ năng lực nghiệp vụ (has_import_table, has_import_price, has_inventory,
      has_expiry_date, has_debt_table, has_cost_data, has_cogs, has_customer_info,
      has_customer_address, has_customer_gender, has_customer_group, has_sales_channel,
      has_payment_method, has_cancel_return_reason).
    """
    metadata: Dict[str, Any] = {
        "min_date": None,
        "max_date": None,
        "table_names": [],
        "columns_by_table": {},
        "all_columns": set(),
        "has_import_table": False,
        "has_import_price": False,
        "has_debt_table": False,
        "has_cost_data": False,
        "has_cogs": False,
        "has_inventory": False,
        "has_expiry_date": False,
        "has_customer_info": False,
        "has_customer_address": False,
        "has_customer_gender": False,
        "has_customer_group": False,
        "has_sales_channel": False,
        "has_payment_method": False,
        "has_cancel_return_reason": False,
    }

    if readme_text is None and business_obj is not None:
        readme_text = getattr(business_obj, "readme_text", None) or getattr(business_obj, "readme", "") or ""
    readme_norm = _nfc(readme_text or "")
    readme_low = readme_norm.lower()

    tables: Dict[str, Any] = {}
    sheet_months: List[Tuple[int, int]] = []

    if business_obj and hasattr(business_obj, "tables"):
        for ti in business_obj.tables:
            t_base = Path(getattr(ti, "fixed_file_name", getattr(ti, "table_id", "table"))).stem
            s_name = getattr(ti, "sheet_name", None)
            t_key = f"{t_base}_{s_name}" if s_name and s_name != "Sheet1" else t_base
            tables[t_key] = getattr(ti, "df", None)
            # Thu thập các sheet tháng nếu có (vd: 04.2025, T04_2025, Thang 02 2025, T01-2025)
            for sh in ([s_name] if s_name else []) + list(getattr(ti, "merged_sheets", [])):
                if sh:
                    m_sh = re.search(r"(?:t|th[aá]ng\s*)?(\d{1,2})[._\-\s/]+(202\d)", str(sh), re.IGNORECASE)
                    if m_sh:
                        mm, yy = int(m_sh.group(1)), int(m_sh.group(2))
                        if 1 <= mm <= 12:
                            sheet_months.append((yy, mm))
    elif data_dict:
        # Lọc bớt các alias trùng lặp như t_01, t_02 nếu đã có tên bảng gốc
        for k, v in data_dict.items():
            if not re.fullmatch(r"t_\d+", str(k)):
                tables[k] = v
        if not tables:
            tables.update(data_dict)

    metadata["table_names"] = list(tables.keys())
    all_min_dates: List[str] = []
    all_max_dates: List[str] = []

    for t_name, df in tables.items():
        if df is None or (hasattr(df, "empty") and df.empty):
            continue

        cols = [_nfc(c) for c in df.columns]
        cols_low = [c.lower() for c in cols]
        metadata["columns_by_table"][t_name] = cols
        metadata["all_columns"].update(cols_low)

        t_name_low = _nfc(t_name).lower()

        # 1. Kiểm tra bảng nhập hàng & giá nhập
        is_import_tbl = any(k in t_name_low for k in ["nhap", "ncc", "nhacungcap", "phieunhap"])
        if is_import_tbl:
            metadata["has_import_table"] = True
            if any(any(p in c for p in ["giá", "gia", "tiền", "tien", "cần trả", "can_tra"]) for c in cols_low):
                metadata["has_import_price"] = True

        # 2. Kiểm tra bảng công nợ (loại trừ bảng chỉ có hạn nợ/hạn thanh toán mà không có tiền thu/nợ)
        if any(k in t_name_low for k in ["phieuthu", "phieu_thu", "soquy", "so_quy", "thanh_toan", "thanhtoan", "sono", "so_no", "sogop", "so_gop"]):
            metadata["has_debt_table"] = True
        elif any(k in t_name_low for k in ["congno", "cong_no", "phaithu", "phaitra"]) and " hạn" not in t_name_low and "_han" not in t_name_low and "hanno" not in t_name_low:
            if any(any(p in c for p in ["tiền", "tien", "còn nợ", "con_no", "đã trả", "da_tra", "thu"]) for c in cols_low):
                metadata["has_debt_table"] = True

        # 3. Kiểm tra bảng chi phí vận hành
        if any(k in t_name_low for k in ["chiphi", "chi_phi", "chiphikhac"]):
            metadata["has_cost_data"] = True

        # 4. Kiểm tra bảng tồn kho
        if any(k in t_name_low for k in ["tonkho", "ton_kho", "thekho", "the_kho", "baocaotonkho"]):
            metadata["has_inventory"] = True

        # 5. Quét ngày giao dịch trên toàn bộ dòng (không dùng .head(2000))
        if pd is not None and not _is_catalog_table(t_name_low):
            for c in df.columns:
                if _is_transaction_date_col(str(c)):
                    try:
                        s_raw = df[c].dropna().astype(str).str.strip()
                        if s_raw.empty:
                            continue
                        s_slice = s_raw.str[:10]
                        # Ưu tiên fast-path cho định dạng chuẩn YYYY-MM-DD
                        iso_mask = s_slice.str.match(r"^202\d-\d{2}-\d{2}$", na=False)
                        if iso_mask.any():
                            valid_iso = s_slice[iso_mask]
                            all_min_dates.append(str(valid_iso.min()))
                            all_max_dates.append(str(valid_iso.max()))
                        else:
                            with warnings.catch_warnings():
                                warnings.simplefilter("ignore")
                                s_dt = pd.to_datetime(s_slice, errors="coerce", dayfirst=True).dropna()
                            if not s_dt.empty:
                                reasonable = s_dt[(s_dt.dt.year >= 2020) & (s_dt.dt.year <= 2030)]
                                if not reasonable.empty:
                                    all_min_dates.append(reasonable.min().strftime("%Y-%m-%d"))
                                    all_max_dates.append(reasonable.max().strftime("%Y-%m-%d"))
                    except Exception:
                        pass

    # Kết hợp thông tin từ sheet_months nếu chưa tìm được ngày từ bảng hoặc để bổ sung
    if sheet_months:
        min_y, min_m = min(sheet_months)
        max_y, max_m = max(sheet_months)
        last_d = calendar.monthrange(max_y, max_m)[1]
        sheet_min_str = f"{min_y:04d}-{min_m:02d}-01"
        sheet_max_str = f"{max_y:04d}-{max_m:02d}-{last_d:02d}"
        all_min_dates.append(sheet_min_str)
        if not all_max_dates:
            all_max_dates.append(sheet_max_str)

    if all_min_dates:
        metadata["min_date"] = min(all_min_dates)
    if all_max_dates:
        metadata["max_date"] = max(all_max_dates)

    # Nếu README ghi rõ "Dữ liệu có đến hết DD/MM/YYYY" -> dùng làm mốc max_date chính xác
    m_end_readme = re.search(r"dữ\s*liệu\s*có\s*đến\s*hết\s*(\d{1,2})/(\d{1,2})/(\d{4})", readme_low)
    if m_end_readme:
        dd, mm, yy = int(m_end_readme.group(1)), int(m_end_readme.group(2)), int(m_end_readme.group(3))
        readme_max = f"{yy:04d}-{mm:02d}-{dd:02d}"
        if metadata["max_date"] is None or readme_max < metadata["max_date"]:
            metadata["max_date"] = readme_max

    # Bổ sung tên cột được liệt kê trong README.md (mục ## Cột trong ...)
    in_cols_sec = False
    for line in readme_norm.splitlines():
        if line.startswith("## Cột trong"):
            in_cols_sec = True
        elif line.startswith("## "):
            in_cols_sec = False
        elif in_cols_sec and line.startswith("- **") and "**:" in line:
            c_readme = line.split("**")[1].strip().lower()
            if c_readme:
                metadata["all_columns"].add(c_readme)

    # Tổng hợp các cờ năng lực từ all_columns, table_names và readme_low
    all_cols = metadata["all_columns"]
    t_names_low = " ".join(_nfc(t).lower() for t in metadata["table_names"])

    if any(any(k in c for k in ["ngày nhập", "ngay_nhap", "ngaynhap", "mã đơn nhập", "ma_don_nhap", "mã phiếu nhập", "maphieunhap", "số lượng nhập", "sl nhập", "slnhap", "nhà cung cấp", "nhacungcap", "ncc"]) for c in all_cols) or "**nhập hàng**:" in readme_low or "ngày nhập" in readme_low:
        metadata["has_import_table"] = True

    if any(any(k in c for k in ["giá nhập", "gia_nhap", "gianhap", "đơn giá nhập", "don_gia_nhap", "dongianhap", "cần trả ncc", "tiền nhập", "tổng tiền phiếu nhập", "tonggiatrinhap"]) for c in all_cols) or "**nhập hàng**:" in readme_low or "giá nhập một đơn vị" in readme_low:
        metadata["has_import_price"] = True

    if any(any(k in c for k in ["hạn sử dụng", "han_su_dung", "hansudung", "hạn dùng", "han_dung", "handung", "hsd"]) for c in all_cols) or "**lô, hạn dùng**:" in readme_low or ": hạn sử dụng" in readme_low:
        metadata["has_expiry_date"] = True

    # Theo Điều 5 Rulebook: Nếu shop có theo dõi lô hàng (nhập theo lô + bán/trả theo lô) thì tính được tồn kho cuối ngày
    has_batch_tracking = (
        metadata["has_expiry_date"]
        or any(k in t_names_low for k in ["donhang_lo", "bantheolo", "chi_tiet_don_lo", "lo_hang", "lohang"])
        or any(c in ("mã lô", "ma_lo", "malo", "số lô", "so_lo") for c in all_cols)
    )
    if (
        any(any(k in c for k in ["tồn kho", "ton_kho", "tonkho", "tồn cuối", "ton_cuoi", "toncuoi", "tồn thực", "ton_thuc", "tonthuc"]) for c in all_cols)
        or "**tồn kho**:" in readme_low
        or ": tồn kho" in readme_low
        or has_batch_tracking
    ):
        metadata["has_inventory"] = True

    if any(any(k in c for k in ["còn nợ", "con_no", "conno", "conphaithu", "đã thanh toán", "da_thanh_toan", "số tiền thu", "so_tien_thu", "sotienthu", "khách còn nợ", "khách đã trả", "khachdatra", "số khách còn nợ"]) for c in all_cols) or any(k in readme_low for k in ["**công nợ**:", "**còn nợ**:", "**sổ nợ**:", "**sổ góp**:"]):
        metadata["has_debt_table"] = True

    if any(any(k in c for k in ["chi phí", "chi_phi", "chiphi", "lương"]) for c in all_cols) or "**sổ chi phí**:" in readme_low:
        metadata["has_cost_data"] = True

    if metadata["has_import_price"] or any(any(k in c for k in ["giá vốn", "gia_von", "giavon"]) for c in all_cols) or "**giá vốn**:" in readme_low or ": giá vốn" in readme_low:
        metadata["has_cogs"] = True

    if any(any(k in c for k in ["khách", "khach", "tenkh", "makh", "customer"]) for c in all_cols) or any(k in readme_low for k in [": tên khách", ": mã khách", "khach_hang", "khachhang"]):
        metadata["has_customer_info"] = True

    if any(any(k in c for k in ["địa chỉ", "dia_chi", "diachi", "address"]) for c in all_cols) or ": địa chỉ" in readme_low:
        metadata["has_customer_address"] = True

    if any(any(k in c for k in ["giới tính", "gioi_tinh", "gioitinh", "phái", "namnu", "nam_nu", "gender"]) for c in all_cols) or ": giới tính" in readme_low:
        metadata["has_customer_gender"] = True

    if any(any(k in c for k in ["nhóm khách", "nhom_khach", "nhomkhach", "loại khách", "loai_khach", "loaikhach", "hạng khách", "hang_khach", "loai_hinh_kh"]) or c in ("hạng", "hang") for c in all_cols) or ": nhóm khách" in readme_low:
        metadata["has_customer_group"] = True

    if any(any(k in c for k in ["kênh", "kenh", "channel"]) for c in all_cols) or ": kênh bán" in readme_low:
        metadata["has_sales_channel"] = True

    if any(any(k in c for k in ["hình thức", "hinh_thuc", "hinhthuc", "phương thức", "phuong_thuc", "phuongthuc", "payment", "pttt"]) or ("thanh toán" in c and "hạn" not in c and "đã" not in c and "tổng" not in c) for c in all_cols) or ": hình thức thanh toán" in readme_low:
        metadata["has_payment_method"] = True

    if any(any(k in c for k in ["lý do", "ly_do", "lydo", "nguyên nhân", "nguyen_nhan", "nguyennhan"]) for c in all_cols) or "lý do" in readme_low:
        metadata["has_cancel_return_reason"] = True

    return metadata


# ==============================================================================
# HÀM BÓC TÁCH KHOẢNG NGÀY TRONG CÂU HỎI
# ==============================================================================
# HÀM BÓC TÁCH KHOẢNG THỜI GIAN (ỦY QUYỀN TRỰC TIẾP CHO TEMPORAL.PY)
# ==============================================================================

# extract_query_date_range và extract_comparison_date_range được hợp nhất hoàn toàn
# và ủy quyền trực tiếp cho Single Source of Truth tại `datamate.grounding_feasibility.temporal`.
# Giúp loại bỏ 100% trùng lặp logic regex và tránh rủi ro lệch quy tắc ngày tháng.
_extract_comparison_date_range = extract_comparison_date_range


# ==============================================================================
# HÀM KIỂM TRA TÍNH KHẢ THI CỐT LÕI (FEASIBILITY CHECKER)
# ==============================================================================

def check_feasibility(
    question: str,
    as_of_date: str,
    shop_meta: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Kiểm tra xem câu hỏi có thể trả lời được từ dữ liệu cửa hàng hay không (Feasibility Gate).

    Quy tắc nghiệp vụ:
    - Trả về (True, None) nếu câu hỏi khả thi -> Chuyển sang cho LLM sinh mã.
    - Trả về (False, "lý do") nếu câu hỏi bất khả thi -> Trả về ngay 'unanswerable' (+1 điểm).
    """
    if not question or not question.strip():
        return False, "Câu hỏi rỗng"

    q_lower = _nfc(question).lower()

    # --------------------------------------------------------------------------
    # Rào chắn 1: Các câu hỏi về thuộc tính chủ quan / phi dữ liệu kinh doanh POS
    # --------------------------------------------------------------------------
    for pat in SUBJECTIVE_UNANSWERABLE_PATTERNS:
        if re.search(pat, q_lower):
            return False, f"Câu hỏi đòi hỏi dữ liệu đánh giá chủ quan hoặc ngoài phạm vi POS (khớp mẫu: '{pat}')"

    # --------------------------------------------------------------------------
    # Rào chắn 2: Khoảng thời gian câu hỏi nằm HOÀN TOÀN ngoài dữ liệu (Điều 7)
    # --------------------------------------------------------------------------
    shop_min = shop_meta.get("min_date")
    shop_max = shop_meta.get("max_date")

    if shop_min and shop_max:
        q_start, q_end = extract_query_date_range(question, as_of_date)
        if q_start and q_end:
            if q_end < shop_min:
                return False, f"Kỳ hỏi ({q_start} đến {q_end}) kết thúc trước mốc dữ liệu sớm nhất của shop ({shop_min}) [Điều 7 Rulebook]"
            if q_start > shop_max:
                return False, f"Kỳ hỏi ({q_start} đến {q_end}) bắt đầu sau mốc dữ liệu muộn nhất của shop ({shop_max}) [Điều 7 Rulebook]"

            # Kiểm tra thêm kỳ đối chiếu bắt buộc (ví dụ: 'so với tháng liền trước')
            cmp_start, cmp_end = _extract_comparison_date_range(question, q_start, q_end, as_of_date)
            if cmp_start and cmp_end:
                if cmp_end < shop_min:
                    return False, f"Kỳ so sánh ({cmp_start} đến {cmp_end}) kết thúc trước mốc dữ liệu sớm nhất của shop ({shop_min}) [Điều 7 Rulebook]"
                if cmp_start > shop_max:
                    return False, f"Kỳ so sánh ({cmp_start} đến {cmp_end}) bắt đầu sau mốc dữ liệu muộn nhất của shop ({shop_max}) [Điều 7 Rulebook]"

    # --------------------------------------------------------------------------
    # Rào chắn 3: Yêu cầu loại thông tin mà cấu trúc dữ liệu shop không hỗ trợ
    # --------------------------------------------------------------------------
    table_names_joined = " ".join(str(t) for t in shop_meta.get("table_names", [])).lower()
    all_cols = { _nfc(c).lower() for c in shop_meta.get("all_columns", set()) }

    # 3.1. Hỏi về nhà cung cấp nhưng không có bảng hoặc cột nhà cung cấp
    if any(k in q_lower for k in SUPPLIER_KEYWORDS):
        has_ncc = (
            shop_meta.get("has_import_table", False)
            or "ncc" in table_names_joined
            or "nhacungcap" in table_names_joined
            or any("cung cấp" in c or "nhà cc" in c or "ncc" in c for c in all_cols)
        )
        if not has_ncc:
            return False, "Dữ liệu cửa hàng không có bảng hoặc cột thông tin về Nhà cung cấp"

    # 3.2. Hỏi về tiền nhập hàng / giá nhập bình quân nhưng shop không có bảng nhập hoặc không ghi giá nhập
    if re.search(
        r"ti(?:ền|en)\s*nh(?:ập|ap)\s*h(?:àng|ang)|gi(?:á|a)\s*nh(?:ập|ap)\s*b(?:ình|inh)\s*qu(?:ân|an)|nh(?:ập|ap)\s*v(?:ào|ao)\s*gi(?:á|a)\s*b(?:ình|inh)\s*qu(?:ân|an)|nh(?:ập|ap)\s+.*?\bb(?:ình|inh)\s*qu(?:ân|an)\s*(?:bao\s*nhiêu|bao\s*nhiu|bnhiu|bn)\s*ti(?:ền|en)",
        q_lower,
    ):
        has_imp_price = (
            shop_meta.get("has_import_price", False)
            or any(any(k in c for k in ["giá nhập", "gia_nhap", "gianhap", "đơn giá nhập", "dongianhap", "tiền nhập", "cần trả ncc", "tonggiatrinhap"]) for c in all_cols)
        )
        # Tương thích ngược nếu shop_meta truyền thủ công chỉ có has_import_table=True và không truyền has_import_price
        if "has_import_price" not in shop_meta and shop_meta.get("has_import_table", False):
            has_imp_price = True
        if not has_imp_price:
            return False, "Dữ liệu cửa hàng không ghi nhận thông tin giá nhập / tiền nhập hàng"

    # 3.3. Hỏi về lãi ròng / chi phí vận hành nhưng không có sổ chi phí
    if any(k in q_lower for k in PROFIT_KEYWORDS):
        has_cost = shop_meta.get("has_cost_data", False) or any("chi phí" in c or "chiphi" in c or "lương" in c for c in all_cols)
        if not has_cost:
            return False, "Dữ liệu cửa hàng chỉ có doanh thu bán hàng, không ghi nhận sổ chi phí để tính lãi ròng"

    # 3.4. Hỏi về lãi gộp / tính theo giá vốn nhưng shop không có cột giá vốn và không có giá nhập
    if re.search(r"lãi\s*gộp|lợi\s*nhuận\s*gộp|tính\s*theo\s*giá\s*vốn", q_lower):
        has_cogs = (
            shop_meta.get("has_cogs", False)
            or shop_meta.get("has_import_price", False)
            or any("giá vốn" in c or "gia_von" in c or "giavon" in c for c in all_cols)
        )
        if not has_cogs:
            return False, "Dữ liệu cửa hàng không ghi nhận giá vốn mặt hàng"

    # 3.5. Hỏi về tồn kho cuối ngày nhưng shop không có bảng/cột tồn kho và không theo dõi lô hàng (Điều 5 Rulebook)
    if re.search(
        r"\btồn\s*kho\b|\bton\s*kho\b|trong\s*kho\s*(?:còn|con)|kho\s*(?:còn|con)\s*(?:tồn|ton)|(?:còn|con)\s*(?:lại\s*|lai\s*|laị\s*|laij\s*|tồn\s*|ton\s*)?(?:bao\s*nhiêu|bao\s*nhiu|bnhiu|bn|mấy|may)\s+\w+\s+trong\s*kho|(?:hết\s*hôm\s*nay|het\s*hom\s*nay|heets\s*hoom\s*nay|cuối\s*ngày\s*hôm\s*nay|cuoi\s*ngay\s*hom\s*nay).*?\b(?:còn|con)\s*(?:lại\s*|lai\s*|laị\s*|laij\s*|tồn\s*|ton\s*)?(?:bao\s*nhiêu|bao\s*nhiu|bnhiu|bn|mấy|may)\b",
        q_lower,
    ):
        has_inv = (
            shop_meta.get("has_inventory", False)
            or shop_meta.get("has_expiry_date", False)
            or any(k in table_names_joined for k in ["tonkho", "ton_kho", "thekho", "the_kho", "donhang_lo", "bantheolo", "chi_tiet_don_lo", "lo_hang", "lohang"])
            or any(any(k in c for k in ["tồn kho", "ton_kho", "tonkho", "tồn cuối", "ton_cuoi", "toncuoi", "tồn thực", "ton_thuc", "tonthuc", "mã lô", "ma_lo", "malo", "số lô", "so_lo"]) for c in all_cols)
        )
        if not has_inv:
            return False, "Dữ liệu cửa hàng không có bảng hoặc cột theo dõi tồn kho"

    # 3.6. Hỏi về hạn dùng / hàng hết hạn nhưng shop không có cột hạn sử dụng
    if re.search(r"\bhạn\s*dùng\b|\bhan\s*dung\b|\bhạn\s*sử\s*dụng\b|hết\s*hạn\s*trong\s*\d+\s*ngày", q_lower):
        has_exp = (
            shop_meta.get("has_expiry_date", False)
            or any(any(k in c for k in ["hạn sử dụng", "han_su_dung", "hansudung", "hạn dùng", "han_dung", "handung", "hsd"]) for c in all_cols)
        )
        if not has_exp:
            return False, "Dữ liệu cửa hàng không ghi nhận lô và hạn sử dụng của sản phẩm"

    # 3.7. Hỏi về số tiền còn nợ / thu hồi công nợ / ghi nợ thêm nhưng shop không theo dõi tiền công nợ
    if re.search(r"còn\s*nợ|con\s*no|còn\s*thiếu|đang\s*nợ|nợ\s*nhiều\s*nhất|no\s*nhieu\s*nhat|ghi\s*nợ\s*thêm|thu\s*hồi\s*.*?\bcông\s*nợ", q_lower):
        has_debt = (
            shop_meta.get("has_debt_table", False)
            or any(any(k in c for k in ["còn nợ", "con_no", "conno", "conphaithu", "đã thanh toán", "số tiền thu", "sotienthu", "khách còn nợ"]) for c in all_cols)
        )
        if not has_debt:
            return False, "Dữ liệu cửa hàng không theo dõi số tiền công nợ / thanh toán công nợ của khách"

    # 3.8. Hỏi về nhóm khách hàng thân thiết nhưng shop không phân nhóm khách
    if "thân thiết" in q_lower:
        has_customer_group = (
            shop_meta.get("has_customer_group", False)
            or any(any(k in c for k in ["nhóm khách", "nhom_khach", "nhomkhach", "loại khách", "loai_khach", "loaikhach", "hạng khách", "hang_khach", "loai_hinh_kh"]) or c in ("hạng", "hang") for c in all_cols)
            or (
                "has_customer_group" not in shop_meta
                and (any(k in table_names_joined for k in ["khachhang", "customer"]) and any("nhóm" in c or "loại" in c for c in all_cols))
            )
        )
        if not has_customer_group:
            return False, "Dữ liệu cửa hàng không ghi nhận phân loại nhóm khách hàng thân thiết"

    # 3.9. Hỏi về địa chỉ khách hàng (ở đường ...) nhưng shop không có cột địa chỉ
    if re.search(r"khách\s*(?:hàng\s*)?(?:nhà\s*)?ở\s*đường|khách\s+đường\s+", q_lower):
        has_addr = (
            shop_meta.get("has_customer_address", False)
            or any(any(k in c for k in ["địa chỉ", "dia_chi", "diachi", "address"]) for c in all_cols)
        )
        if not has_addr:
            return False, "Dữ liệu cửa hàng không ghi nhận thông tin địa chỉ của khách hàng"

    # 3.10. Hỏi về giới tính khách hàng (khách nam / khách nữ) nhưng shop không có cột giới tính
    if re.search(r"\bkhách\s*(?:hàng\s*)?(?:nữ|nam)\b|\bkhach\s*(?:hang\s*)?(?:nu|nam)\b", q_lower):
        has_gender = (
            shop_meta.get("has_customer_gender", False)
            or any(any(k in c for k in ["giới tính", "gioi_tinh", "gioitinh", "phái", "namnu", "nam_nu", "gender"]) for c in all_cols)
        )
        if not has_gender:
            return False, "Dữ liệu cửa hàng không ghi nhận thông tin giới tính của khách hàng"

    # 3.11. Hỏi đếm/xếp hạng khách hàng khi shop không hề lưu thông tin khách hàng trên đơn
    if re.search(r"(?:bao\s*nhiêu|bao\s*nhiu|bnhiu|bn|mấy|may|dem\s*so|đếm\s*số)\s*kh(?:ách|ach)\s*(?:đã\s*|da\s*)?mua|trong\s*(?:số|so)\s*kh(?:ách|ach)\s*(?:đã|da)\s*mua|kh(?:ách|ach)\s*(?:hàng\s*|hang\s*)?(?:nào|nao)\s*mua\s*nhi(?:ều|u|eu)|ai\s*l(?:à|a)\s*kh(?:ách|ach)\s*mua", q_lower):
        has_cust = (
            shop_meta.get("has_customer_info", False)
            or any(any(k in c for k in ["khách", "khach", "tenkh", "makh", "customer"]) for c in all_cols)
            or any(k in table_names_joined for k in ["khach", "customer"])
        )
        if all_cols and not has_cust:
            return False, "Dữ liệu cửa hàng không lưu thông tin định danh khách hàng trên đơn bán"

    # 3.12. Hỏi kênh bán hàng (qua điện thoại, zalo oa, tại quầy) khi shop không có cột kênh bán
    if re.search(r"đơn\s*bán\s*qua\s*(?:điện\s*thoại|zalo)|đơn\s*bán\s*tại\s*quầy", q_lower):
        has_chan = (
            shop_meta.get("has_sales_channel", False)
            or any(any(k in c for k in ["kênh", "kenh", "channel"]) for c in all_cols)
        )
        if not has_chan:
            return False, "Dữ liệu cửa hàng không ghi nhận thông tin kênh bán hàng"

    # 3.13. Hỏi doanh thu theo hình thức thanh toán (trả bằng COD / ví điện tử) khi shop không có cột thanh toán
    if re.search(r"đơn\s*trả\s*bằng\s*(?:cod|ví\s*điện\s*tử|tiền\s*mặt)|dthu\s*các\s*đơn\s*trả\s*bằng", q_lower):
        has_pmt = (
            shop_meta.get("has_payment_method", False)
            or any(any(k in c for k in ["hình thức", "hinh_thuc", "hinhthuc", "phương thức", "phuong_thuc", "phuongthuc", "payment", "pttt"]) or ("thanh toán" in c and "hạn" not in c and "đã" not in c and "tổng" not in c) for c in all_cols)
        )
        if not has_pmt:
            return False, "Dữ liệu cửa hàng không ghi nhận cột hình thức thanh toán của đơn hàng"

    # 3.14. Hỏi lý do hủy / lý do trả hàng (hủy vì giao trễ, trả vì lỗi vs mua nhầm) khi không có cột lý do
    if re.search(r"(?:hủy|huỷ|huy)\s*v(?:ì|i)\s*giao\s*tr(?:ễ|e)|tr(?:ả|a)\s*(?:h(?:à|a)ng\s*)?v(?:ì|i)\s*l(?:ỗ|o)i\s*v(?:à|a)\s*tr(?:ả|a)\s*v(?:ì|i)\s*mua\s*nh(?:ầ|a)m", q_lower):
        has_reason = (
            shop_meta.get("has_cancel_return_reason", False)
            or any(any(k in c for k in ["lý do", "ly_do", "lydo", "nguyên nhân", "nguyen_nhan", "nguyennhan"]) for c in all_cols)
        )
        if not has_reason:
            return False, "Dữ liệu cửa hàng không ghi nhận lý do hủy hoặc lý do trả hàng"

    return True, None
