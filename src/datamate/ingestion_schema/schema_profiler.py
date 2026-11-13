"""
schema_profiler.py — Bộ trích xuất hồ sơ dữ liệu chi tiết (Rich Schema Profiler) cho DataMate.

Cung cấp thông tin phong phú về từng bảng và cột:
- Số dòng thực tế của bảng.
- Kiểu dữ liệu ngữ nghĩa của cột: date (kèm min date -> max date), categorical (kèm toàn bộ giá trị nếu <= 6),
  numeric/currency (kèm ví dụ), string/ID (kèm ví dụ).
- Chống phân loại nhầm trên bảng ít dòng (small-sample protection).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, List, Optional
import pandas as pd
import numpy as np

from datamate.ingestion.loader import BusinessData, TableInfo


def _normalize_text(s: Any) -> str:
    if s is None or pd.isna(s):
        return ""
    text = unicodedata.normalize("NFC", str(s)).strip()
    return re.sub(r"\s+", " ", text)


def profile_table_columns(df: pd.DataFrame, max_cols: int = 15) -> List[str]:
    """Phân tích và tạo mô tả giàu ngữ nghĩa cho từng cột trong bảng (tối ưu hóa token để chống tràn VRAM)."""
    col_previews: List[str] = []
    
    for c in df.columns[:max_cols]:
        col_name = str(c)
        c_low = col_name.lower()
        non_null = df[c].dropna()
        n_unique = non_null.nunique()
        n_rows = len(df)
        
        if non_null.empty:
            col_previews.append(f"'{col_name}' (rỗng)")
            continue

        # 1. Nhận diện cột ngày tháng
        is_date_col = any(k in c_low for k in ["ngày", "date", "ngaylap", "thời gian", "thoigian", "hsd", "hạn dùng"])
        if is_date_col:
            try:
                from datamate.llm_execution.sandbox import clean_date
                dt_series = clean_date(non_null).dropna()
                if not dt_series.empty:
                    min_d = dt_series.min().strftime("%Y-%m-%d")
                    max_d = dt_series.max().strftime("%Y-%m-%d")
                    col_previews.append(f"'{col_name}' (ngày: '{min_d}' -> '{max_d}')")
                    continue
            except Exception:
                pass

        # 2. Nhận diện cột tiền tệ / số lượng
        is_num_keyword = (
            any(k in c_low for k in ["tiền", "giá", "số lượng", "soluong", "doanh thu", "chiết khấu", "giảm giá", "thuế", "vat", "nợ", "tồn", "cần trả", "đã trả", "đơn giá", "phí ship", "phí vận chuyển"])
            or bool(re.search(r"\bsl\b", c_low))
        )

        if is_num_keyword:
            if any(k in c_low for k in ["quy đổi", "quy doi", "cơ sở", "co so"]):
                num_tag = "SL quy đổi"
            elif any(k in c_low for k in ["số lượng", "soluong"]) or bool(re.search(r"\bsl\b", c_low)):
                num_tag = "số lượng"
            elif any(k in c_low for k in ["đơn giá", "don gia", "giá bán", "gia ban", "giá nhập", "gia nhap"]):
                num_tag = "đơn giá"
            elif any(k in c_low for k in ["chiết khấu", "chiet khau", "giảm giá", "giam gia", "thuế", "vat", "phí ship"]):
                num_tag = "giảm giá/thuế"
            elif any(k in c_low for k in ["khách cần trả", "khách đã trả", "thanh toán", "tổng bill", "khach tra"]):
                num_tag = "tiền thanh toán"
            elif any(k in c_low for k in ["thành tiền", "thanh tien", "tổng tiền hàng", "tong tien hang", "doanh thu", "tổng sau giảm"]):
                num_tag = "tiền hàng/doanh thu"
            else:
                num_tag = "tiền"
            col_previews.append(f"'{col_name}' ({num_tag})")
            continue

        # 3. Nhận diện cột phân loại (categorical)
        is_cat_keyword = any(k in c_low for k in ["trạng thái", "status", "tình trạng", "kênh", "channel", "phương thức", "hình thức"])
        if is_cat_keyword and 1 <= n_unique <= 6:
            unique_vals = [_normalize_text(v) for v in non_null.unique() if _normalize_text(v)]
            unique_vals = [v for v in unique_vals if v.lower() not in ("nan", "none", "null")]
            if unique_vals:
                vals_str = ", ".join(f"'{v[:10]}'" for v in unique_vals[:2])
                col_previews.append(f"'{col_name}' (phân loại: [{vals_str}])")
                continue
        elif 1 <= n_unique <= 6 and n_rows >= 15:
            col_previews.append(f"'{col_name}' (phân loại)")
            continue

        # 4. Mặc định là chuỗi / mã
        col_previews.append(f"'{col_name}'")

    return col_previews


def infer_table_role(table_name: str, df: pd.DataFrame) -> str:
    """
    Xác định vai trò nghiệp vụ thực tế của bảng (Table Role) dựa trên cột và nội dung.
    Không dựa vào tên bảng cố định.
    """
    if df is None or (hasattr(df, "empty") and df.empty):
        return "Bảng rỗng / Chưa có dữ liệu"

    t_norm = unicodedata.normalize("NFKD", str(table_name)).lower().encode("ascii", "ignore").decode("utf-8")
    t_clean = re.sub(r"[^a-z0-9]", "", t_norm)
    
    cols_raw = [str(c) for c in df.columns]
    cols_low = [c.lower() for c in cols_raw]

    # Nhận diện các loại cột nghiệp vụ
    # Ngày giao dịch thực tế (loại trừ ngày sinh, ngày tạo metadata, hsd)
    trans_dates = [
        c for c in cols_low
        if any(k in c for k in ["ngày", "date", "ngaylap", "thời gian", "thoigian", "ngay_ban"])
        and not any(k in c for k in ["ngày sinh", "ngaysinh", "thời gian tạo", "thoigiantao", "ngày tạo", "ngaytao", "hsd", "hạn dùng"])
    ]
    has_date = bool(trans_dates)

    has_money = any(
        any(k in c for k in ["thành tiền", "tổng tiền", "tiền", "doanh thu", "tiền bán", "khách cần trả", "tổng thanh toán", "tổng tiền hàng", "tổng sau giảm giá", "tổng đơn"])
        and "nhap" not in c for c in cols_low
    )
    has_item = any(any(k in c for k in ["mã hàng", "tên hàng", "sản phẩm", "tên thuốc", "mã sp", "product", "sku", "hoạt chất", "tên món", "mặt hàng"]) for c in cols_low)
    has_qty = any(any(k in c for k in ["số lượng", "sl", "quy đổi", "slquydoi"]) for c in cols_low)
    has_sales_name = any(k in t_clean for k in ["banhang", "donhang", "hoadon", "sobanhang", "pos", "giaodich", "chitietdon", "hoadonchitiet", "chitietbanhang", "danhsachhoadon"])
    has_sales_id = any(any(k in c for k in ["mã đơn", "mã hoá đơn", "mã hd", "mã bill", "mã phiếu", "order_id", "mã chứng từ"]) for c in cols_low)

    # 1. Sổ giao hàng / Vận chuyển
    is_delivery = (
        any(k in t_clean for k in ["giaohang", "phieugiao", "vanchuyen", "chohang", "sochohang", "delivery", "ship"])
        or any(any(k in c for k in ["ngày giao", "ngày chở", "lần giao", "lượt giao", "biển số", "người chở", "người giao", "sl thực giao", "đợt giao"]) for c in cols_low)
    ) and not has_money
    if is_delivery:
        return "Sổ giao hàng"

    # 2. Bán hàng
    if (has_sales_name and (has_date or has_money or has_qty or has_sales_id)) or (has_sales_id and (has_date or has_money or has_item)) or (has_date and has_money):
        if has_item and has_qty:
            return "Bán hàng chi tiết"
        return "Bán hàng tổng hợp"

    # 3. Kiểm tra nhập hàng / phiếu nhập
    is_import = (
        any(k in t_clean for k in ["nhap", "ncc", "nhacungcap", "phieunhap"])
        or any(any(k in c for k in ["ngày nhập", "ngay_nhap", "phiếu nhập", "cần trả ncc", "tiền nhập", "giá trị nhập", "đơn giá nhập"]) for c in cols_low)
    )
    if is_import:
        if any(any(k in c for k in ["mã hàng", "tên hàng", "sản phẩm", "product", "sku"]) for c in cols_low):
            return "Nhập hàng chi tiết"
        return "Nhập hàng tổng hợp"

    # 4. Kiểm tra tồn kho / thẻ kho
    is_inv = (
        any(k in t_clean for k in ["tonkho", "thekho"])
        or any(any(k in c for k in ["tồn kho", "tồn cuối", "tồn thực", "số lượng tồn", "sl tồn", "tồn đầu"]) for c in cols_low)
    )
    if is_inv:
        return "Tồn kho"

    # 5. Kiểm tra chi phí vận hành
    is_cost = (
        any(k in t_clean for k in ["chiphi"])
        or any(any(k in c for k in ["chi phí", "khoản chi", "loại chi"]) for c in cols_low)
    )
    if is_cost:
        return "Sổ chi phí"

    # 6. Kiểm tra công nợ / sổ nợ
    is_debt = (
        any(k in t_clean for k in ["congno", "sono", "sogop", "phaithu", "phaitra", "hanno", "phieuthu", "soquy"])
        or (any(any(k in c for k in ["hạn nợ", "số ngày được nợ", "tuổi nợ", "thu nợ"]) for c in cols_low) and not has_sales_id)
    )
    if is_debt:
        return "Công nợ"

    # 7. Kiểm tra danh mục khách hàng
    is_cust = (
        any(k in t_clean for k in ["khachhang", "customer"])
        or any(any(k in c for k in ["mã khách", "tên khách", "nhóm khách", "sđt", "điện thoại", "tenkh", "makh"]) for c in cols_low)
    ) and not has_date and not has_money
    if is_cust:
        return "Danh mục khách hàng"

    # 8. Kiểm tra danh mục sản phẩm
    is_prod = (
        any(k in t_clean for k in ["sanpham", "hanghoa", "danhmuc", "thuoc", "banggia"])
        or has_item
    ) and not has_date and not has_money
    if is_prod:
        return "Danh mục sản phẩm"

    # 9. Fallback bán hàng nếu có has_item và has_qty
    if has_item and has_qty:
        return "Bán hàng chi tiết"

    return "Bảng dữ liệu khác"


def infer_table_granularity(df: pd.DataFrame) -> str:
    """Phân biệt bảng Cấp Đơn hàng (1 dòng/đơn) vs Cấp Chi tiết mặt hàng (nhiều dòng/đơn)."""
    if df is None or df.empty:
        return ""
    order_col = next(
        (
            c for c in df.columns
            if any(k in str(c).lower() for k in ["mã đơn", "ma don", "mã hoá đơn", "mã hóa đơn", "mã hd", "order_id", "order id", "số hđ", "so hd", "mã chứng từ"])
        ),
        None,
    )
    if not order_col:
        return ""
    non_null = df[order_col].dropna()
    if non_null.empty:
        return ""
    n_unique = non_null.nunique()
    if len(non_null) > n_unique * 1.05:
        return "Nhiều dòng/đơn"
    return "1 dòng/đơn"


def discover_join_keys(business: BusinessData) -> List[str]:
    """Tự động phát hiện các cột khóa ngoại dùng để join giữa các bảng."""
    table_cols = {}
    for ti in business.tables:
        if ti.df is None or ti.df.empty:
            continue
        t_base = Path(ti.fixed_file_name).stem if hasattr(ti, "fixed_file_name") and ti.fixed_file_name else ti.table_id
        t_name = f"{t_base}_{ti.sheet_name}" if ti.sheet_name and ti.sheet_name != "Sheet1" else t_base
        key_cols = {}
        for c in ti.columns:
            c_low = unicodedata.normalize("NFKD", str(c)).lower().encode("ascii", "ignore").decode("utf-8")
            c_norm = re.sub(r"[^a-z0-9]", "", c_low)
            if any(k in c_norm for k in ["madon", "mahoadon", "mahd", "orderid", "sohd", "mahang", "masp", "sku", "makh", "makhach", "manhap", "maphieu", "bienso"]):
                key_cols[c_norm] = str(c)
        if key_cols:
            table_cols[t_name] = key_cols

    join_hints: List[str] = []
    t_names = list(table_cols.keys())
    for i in range(len(t_names)):
        for j in range(i + 1, len(t_names)):
            t1, t2 = t_names[i], t_names[j]
            shared = set(table_cols[t1].keys()) & set(table_cols[t2].keys())
            if shared:
                cols_str = ", ".join(f"'{table_cols[t1][k]}'" for k in sorted(shared)[:2])
                join_hints.append(f"- '{t1}' <-> '{t2}' qua cột: {cols_str}")
            if len(join_hints) >= 6:
                return join_hints
    return join_hints


def profile_business_schema(business: BusinessData, max_cols: int = 10) -> str:
    """Tạo bản tóm tắt schema phong phú (Rich Schema) kèm Table Roles, Granularity và Join Keys."""
    schema_lines: List[str] = []
    for ti in business.tables:
        t_base = Path(ti.fixed_file_name).stem if hasattr(ti, "fixed_file_name") and ti.fixed_file_name else ti.table_id
        t_name = f"{t_base}_{ti.sheet_name}" if ti.sheet_name and ti.sheet_name != "Sheet1" else t_base

        role = infer_table_role(t_name, ti.df)
        granularity = infer_table_granularity(ti.df)
        gran_tag = f" | {granularity}" if granularity else ""

        cols_desc = profile_table_columns(ti.df, max_cols=max_cols)
        extra_note = f", ... và {len(ti.columns) - max_cols} cột khác" if len(ti.columns) > max_cols else ""
        
        schema_lines.append(
            f"- Bảng '{t_name}' [Vai trò: {role}{gran_tag}] ({ti.n_rows} dòng):\n"
            f"  Cột ({len(ti.columns)}): [{', '.join(cols_desc)}{extra_note}]"
        )

    join_hints = discover_join_keys(business)
    join_block = ""
    if join_hints:
        join_block = "### LIÊN KẾT BẢNG (JOIN KEYS):\n" + "\n".join(join_hints) + "\n\n"

    return f"{join_block}### CHI TIẾT CÁC BẢNG VÀ CỘT:\n" + "\n".join(schema_lines)


def describe_schema(business: BusinessData, max_sample: int = 3) -> str:
    """
    Mô tả ngắn gọn từng bảng để đưa vào prompt LLM (định dạng cơ bản).

    Gồm: table_id, fixed_file_name, sheet, số dòng, danh sách cột,
    và tối đa max_sample dòng mẫu (ô cắt còn 40 ký tự).
    """
    import io
    buf = io.StringIO()
    buf.write(f"=== Business: {business.business_id} ===\n")
    if business.readme_text:
        snippet = business.readme_text[:300].replace("\n", " ")
        buf.write(f"README (300 ký tự đầu): {snippet}\n")
    buf.write(f"Tổng số bảng: {len(business.tables)}\n\n")

    for ti in business.tables:
        buf.write(f"[{ti.table_id}] {ti.fixed_file_name}")
        if ti.sheet_name:
            buf.write(f" | sheet: {ti.sheet_name}")
        buf.write(f" | {ti.n_rows} dòng")
        if ti.header_row_detected is not None:
            buf.write(f" | header dòng {ti.header_row_detected}")
        if ti.merged_sheets:
            buf.write(f" | gộp {len(ti.merged_sheets)} sheet")
        buf.write("\n")

        buf.write(f"  Cột ({len(ti.columns)}): {', '.join(ti.columns)}\n")

        if max_sample > 0 and not ti.df.empty:
            sample = ti.df.head(max_sample)
            for _, row in sample.iterrows():
                cells = []
                for c in ti.columns:
                    val = str(row.get(c, ""))
                    if len(val) > 40:
                        val = val[:37] + "..."
                    cells.append(val)
                buf.write("  | " + " | ".join(cells) + "\n")

        buf.write("\n")

    if business.errors:
        buf.write("=== LỖI ===\n")
        for err in business.errors:
            buf.write(f"  - {err}\n")

    return buf.getvalue()
