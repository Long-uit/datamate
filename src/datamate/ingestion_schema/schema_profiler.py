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

        # 2. Nhận diện cột tiền tệ / số lượng (kiểm tra trước phân loại để tránh nhầm số thành categorical)
        is_num_keyword = any(k in c_low for k in ["tiền", "giá", "số lượng", "soluong", "doanh thu", "chiết khấu", "thuế", "vat", "nợ", "tồn", "cần trả", "đơn giá"])
        sample_val = _normalize_text(non_null.iloc[0])
        if len(sample_val) > 20:
            sample_val = sample_val[:17] + "..."

        if is_num_keyword:
            col_previews.append(f"'{col_name}' (số/tiền, vd: '{sample_val}')")
            continue

        # 3. Nhận diện cột phân loại (categorical):
        # Chỉ đánh nhãn phân loại khi tên cột có ngữ nghĩa phân loại HOẶC khi bảng có đủ dòng (>= 15 dòng) và n_unique <= 6
        is_cat_keyword = any(k in c_low for k in ["trạng thái", "status", "tình trạng", "kênh", "channel", "loại", "hình thức", "phương thức", "nhóm", "phân loại", "đơn vị", "đvt", "dvt", "gender", "giới tính"])
        is_valid_categorical = is_cat_keyword or (n_rows >= 15 and 1 <= n_unique <= 6)
        
        if is_valid_categorical and 1 <= n_unique <= 6:
            unique_vals = [_normalize_text(v) for v in non_null.unique() if _normalize_text(v)]
            unique_vals = [v for v in unique_vals if v.lower() not in ("nan", "none", "null")]
            if unique_vals:
                vals_str = ", ".join(f"'{v[:18]}...'" if len(v) > 20 else f"'{v}'" for v in unique_vals[:3])
                col_previews.append(f"'{col_name}' (phân loại: [{vals_str}])")
                continue

        # 4. Mặc định là chuỗi / mã
        col_previews.append(f"'{col_name}' (vd: '{sample_val}')")

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

    # 1. Sổ giao hàng / Vận chuyển (đợt giao, lượt giao, ngày chở/giao, mã vận đơn, biển số xe)
    is_delivery = (
        any(k in t_clean for k in ["giaohang", "phieugiao", "vanchuyen", "chohang", "sochohang", "delivery", "ship"])
        or any(any(k in c for k in ["ngày giao", "ngày chở", "lần giao", "lượt giao", "biển số", "người chở", "người giao", "sl thực giao", "đợt giao"]) for c in cols_low)
    ) and not has_money
    if is_delivery:
        return "Sổ giao hàng / Vận chuyển (đợt giao, lượt giao, ngày chở/giao, mã vận đơn, biển số xe)"

    # 2. Bán hàng (Ưu tiên kiểm tra trước công nợ để tránh bảng hóa đơn có cột 'Còn nợ' bị nhầm thành nợ)
    if (has_sales_name and (has_date or has_money or has_qty or has_sales_id)) or (has_sales_id and (has_date or has_money or has_item)) or (has_date and has_money):
        if has_item and has_qty:
            return "Bán hàng chi tiết (từng mặt hàng, số lượng, thành tiền)"
        return "Bán hàng tổng hợp (hóa đơn, tổng tiền, ngày bán, trạng thái/ghi chú TT)"

    # 3. Kiểm tra nhập hàng / phiếu nhập
    is_import = (
        any(k in t_clean for k in ["nhap", "ncc", "nhacungcap", "phieunhap"])
        or any(any(k in c for k in ["ngày nhập", "ngay_nhap", "phiếu nhập", "cần trả ncc", "tiền nhập", "giá trị nhập", "đơn giá nhập"]) for c in cols_low)
    )
    if is_import:
        if any(any(k in c for k in ["mã hàng", "tên hàng", "sản phẩm", "product", "sku"]) for c in cols_low):
            return "Nhập hàng chi tiết (mặt hàng, số lượng, giá nhập)"
        return "Nhập hàng tổng hợp (phiếu nhập, ngày nhập, tiền nhập)"

    # 4. Kiểm tra tồn kho / thẻ kho
    is_inv = (
        any(k in t_clean for k in ["tonkho", "thekho"])
        or any(any(k in c for k in ["tồn kho", "tồn cuối", "tồn thực", "số lượng tồn", "sl tồn", "tồn đầu"]) for c in cols_low)
    )
    if is_inv:
        return "Tồn kho / Thẻ kho (số lượng tồn, tồn thực)"

    # 5. Kiểm tra chi phí vận hành
    is_cost = (
        any(k in t_clean for k in ["chiphi"])
        or any(any(k in c for k in ["chi phí", "khoản chi", "loại chi"]) for c in cols_low)
    )
    if is_cost:
        return "Sổ chi phí vận hành"

    # 6. Kiểm tra công nợ / sổ nợ (Chỉ nhận diện khi tên bảng rõ ràng hoặc có cột nợ chuyên biệt và KHÔNG phải bảng bán hàng)
    is_debt = (
        any(k in t_clean for k in ["congno", "sono", "sogop", "phaithu", "phaitra", "hanno", "phieuthu", "soquy"])
        or (any(any(k in c for k in ["hạn nợ", "số ngày được nợ", "tuổi nợ", "thu nợ"]) for c in cols_low) and not has_sales_id)
    )
    if is_debt:
        return "Công nợ / Sổ theo dõi nợ & thanh toán"

    # 7. Kiểm tra danh mục khách hàng (không có ngày giao dịch và không có tiền)
    is_cust = (
        any(k in t_clean for k in ["khachhang", "customer"])
        or any(any(k in c for k in ["mã khách", "tên khách", "nhóm khách", "sđt", "điện thoại", "tenkh", "makh"]) for c in cols_low)
    ) and not has_date and not has_money
    if is_cust:
        return "Danh mục khách hàng (mã khách, tên khách, nhóm khách, địa chỉ)"

    # 8. Kiểm tra danh mục sản phẩm / thuốc / bảng giá (không có ngày giao dịch và không có tiền)
    is_prod = (
        any(k in t_clean for k in ["sanpham", "hanghoa", "danhmuc", "thuoc", "banggia"])
        or has_item
    ) and not has_date and not has_money
    if is_prod:
        return "Danh mục sản phẩm / thuốc / bảng giá (mã hàng, tên hàng, hoạt chất, quy cách, giá)"

    # 9. Fallback bán hàng nếu có has_item và has_qty
    if has_item and has_qty:
        return "Bán hàng chi tiết (từng mặt hàng, số lượng, thành tiền)"

    return "Bảng dữ liệu khác"


def profile_business_schema(business: BusinessData, max_cols: int = 15) -> str:
    """Tạo bản tóm tắt schema phong phú (Rich Schema) kèm Table Roles cho toàn bộ shop."""
    schema_lines: List[str] = []
    role_summary_lines: List[str] = ["### VAI TRÒ DỰ ĐOÁN CỦA CÁC BẢNG (TABLE ROLES):"]

    for ti in business.tables:
        t_base = Path(ti.fixed_file_name).stem if hasattr(ti, "fixed_file_name") and ti.fixed_file_name else ti.table_id
        t_name = f"{t_base}_{ti.sheet_name}" if ti.sheet_name and ti.sheet_name != "Sheet1" else t_base

        role = infer_table_role(t_name, ti.df)
        role_summary_lines.append(f"- Bảng '{t_name}' (alias: '{ti.table_id}'): {role}")

        cols_desc = profile_table_columns(ti.df, max_cols=max_cols)
        extra_note = f", ... và {len(ti.columns) - max_cols} cột khác" if len(ti.columns) > max_cols else ""
        
        schema_lines.append(
            f"- Bảng '{t_name}' [Vai trò: {role}] ({ti.n_rows} dòng):\n"
            f"  Cột ({len(ti.columns)}): [{', '.join(cols_desc)}{extra_note}]"
        )

    return "\n".join(role_summary_lines) + "\n\n### CHI TIẾT CÁC BẢNG VÀ CỘT:\n" + "\n".join(schema_lines)


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
