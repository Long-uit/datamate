"""
cleaner.py — Module thực hiện tiền xử lý dữ liệu và hiện thực hoá Quy tắc 8 (Rule 8 Data Cleaner).

Quy tắc 8 (Rulebook):
1. Group Forward-Fill: Các ô để trống ở các dòng sau của cùng một nhóm đơn hàng
   được điền giá trị của dòng đầu đơn (khách hàng, ngày, ghi chú, trạng thái...).
2. Deduplicate: Hai dòng của cùng một đơn giống nhau ở mọi ô là lỗi xuất file POS,
   chỉ tính một lần. Hai dòng giống nhau của hai đơn khác nhau là hai lần bán riêng,
   phải giữ cả hai.
3. Bảng không ghi theo đơn: Mỗi dòng là một lần ghi độc lập, không khử trùng lặp.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional
import pandas as pd

from datamate.ingestion.loader import BusinessData, TableInfo


# Từ khóa nhận diện cột mã đơn hàng
ORDER_ID_KEYWORDS = [
    r"m[aã][\s_-]*đ[oơ]n",
    r"m[aã][\s_-]*phi[eế]u",
    r"s[oố][\s_-]*phi[eế]u",
    r"s[oố][\s_-]*h[oó]a[\s_-]*đ[oơ]n",
    r"s[oố][\s_-]*hđ",
    r"m[aã][\s_-]*ch[uứ]ng[\s_-]*t[uừ]",
    r"order[\s_-]*id",
    r"invoice[\s_-]*id",
    r"m[aã][\s_-]*h[oó]a[\s_-]*đ[oơ]n",
]

# Từ khóa nhận diện cột cấp đơn (order-level) cần forward-fill theo Rule 8
# CHÚ Ý: Theo Rule 8, chỉ forward-fill các thuộc tính định tính của đơn (khách hàng, ngày, ghi chú, trạng thái...)
# TUYỆT ĐỐI KHÔNG forward-fill các cột số tiền, giảm giá, chiết khấu vì sẽ làm sai lệch doanh thu dòng hàng (Rule 1).
ORDER_LEVEL_KEYWORDS = [
    r"ng[aà]y",
    r"th[oờ]i\s*gian",
    r"date",
    r"time",
    r"kh[aá]ch\s*h[aà]ng",
    r"t[eê]n\s*kh[aá]ch",
    r"m[aã]\s*kh[aá]ch",
    r"customer",
    r"s[đd][t|ti]",
    r"phone",
    r"tr[aạ]ng\s*th[aá]i",
    r"t[iì]nh\s*tr[aạ]ng",
    r"status",
    r"ghi\s*ch[uú]",
    r"note",
    r"nh[aâ]n\s*vi[eê]n",
    r"ng[uư][oờ]i\s*b[aá]n",
    r"thu\s*ng[aâ]n",
    r"staff",
    r"k[eê]nh\s*b[aá]n",
    r"chi\s*nh[aá]nh",
    r"branch",
]

# Từ khóa nhận diện cột số thứ tự / chỉ mục dòng (cần bỏ qua khi khử trùng lặp)
ROW_INDEX_KEYWORDS = [
    r"^stt$",
    r"^s[oố]\s*tt$",
    r"^s[oố]\s*th[uứ]\s*t[uự]$",
    r"^no\.?$",
    r"^index$",
    r"^#$",
    r"^d[oò]ng$",
]


def _normalize_str(text: str) -> str:
    """Chuẩn hóa chuỗi so khớp regex (NFC, lowercase, gộp khoảng trắng)."""
    text = unicodedata.normalize("NFC", str(text)).lower()
    return re.sub(r"\s+", " ", text).strip()


def find_order_id_col(columns: list[str]) -> Optional[str]:
    """
    Tìm cột mã đơn hàng trong danh sách cột.
    Ưu tiên cột khớp chính xác hoặc bắt đầu bằng từ khóa mã đơn.
    """
    for col in columns:
        norm = _normalize_str(col)
        for pattern in ORDER_ID_KEYWORDS:
            if re.search(pattern, norm):
                return col
    return None


def find_order_level_cols(columns: list[str], order_id_col: str) -> list[str]:
    """
    Tìm tất cả các cột cấp đơn hàng (cần forward-fill) trong danh sách cột.
    """
    order_cols = [order_id_col]
    for col in columns:
        if col == order_id_col:
            continue
        norm = _normalize_str(col)
        for pattern in ORDER_LEVEL_KEYWORDS:
            if re.search(pattern, norm):
                order_cols.append(col)
                break
    return order_cols


def is_row_index_col(col: str) -> bool:
    """Kiểm tra cột có phải là cột số thứ tự / chỉ mục dòng (STT, No...) hay không."""
    norm = _normalize_str(col)
    return any(re.search(pat, norm) for pat in ROW_INDEX_KEYWORDS)


def is_empty_value(val: object) -> bool:
    """Kiểm tra ô có phải là rỗng / NaN / None / chuỗi trắng / 'nan' / 'null'."""
    if val is None or pd.isna(val):
        return True
    s = str(val).strip().lower()
    return s in ("", "nan", "none", "null")


def apply_group_forward_fill(df: pd.DataFrame, order_id_col: Optional[str] = None) -> pd.DataFrame:
    """
    Thực hiện Group Forward-Fill theo Quy tắc 8:
    - Nếu bảng có cột mã đơn, các ô trống ở các dòng sau của cùng một đơn
      được điền giá trị của dòng đầu đơn (khách hàng, ngày, ghi chú, trạng thái...).
    - Nếu bảng không có cột mã đơn, trả về bản sao df không thay đổi.
    """
    if df.empty or len(df.columns) == 0:
        return df.copy()

    df_clean = df.copy()

    # Xác định cột mã đơn
    if order_id_col is None or order_id_col not in df_clean.columns:
        detected = find_order_id_col(list(df_clean.columns))
        if detected is None:
            return df_clean
        order_id_col = detected

    # Chuẩn hóa các ô rỗng về None để hàm ffill hoạt động chính xác
    # Chuẩn hóa các ô rỗng về None để hàm ffill hoạt động chính xác (tương thích cả pandas cũ và mới)
    if hasattr(df_clean, "map"):
        mask_empty = df_clean.map(is_empty_value)
    elif hasattr(df_clean, "applymap"):
        mask_empty = df_clean.applymap(is_empty_value)
    else:
        mask_empty = df_clean.apply(lambda col: col.map(is_empty_value))
    for col in df_clean.columns:
        if mask_empty[col].any():
            df_clean.loc[mask_empty[col], col] = None

    # Forward-fill cột mã đơn trước để xác định ranh giới từng đơn hàng
    df_clean[order_id_col] = df_clean[order_id_col].ffill()

    # Tìm các cột cấp đơn cần điền
    order_level_cols = find_order_level_cols(list(df_clean.columns), order_id_col)

    # Forward-fill các cột cấp đơn trong phạm vi từng đơn hàng (group by order_id)
    # Lưu ý: dùng transform('ffill') theo nhóm order_id với dropna=False để không tràn sang đơn khác
    for col in order_level_cols:
        if col in df_clean.columns:
            df_clean[col] = df_clean.groupby(order_id_col, dropna=False)[col].ffill()

    return df_clean


def deduplicate_order_rows(df: pd.DataFrame, order_id_col: Optional[str] = None) -> pd.DataFrame:
    """
    Thực hiện Khử trùng lặp dòng theo Quy tắc 8:
    - Bảng có ghi theo đơn: Hai dòng của CÙNG MỘT ĐƠN giống nhau ở mọi ô là lỗi
      xuất file POS, chỉ giữ lại một dòng.
      Hai dòng giống nhau của HAI ĐƠN KHÁC NHAU là hai lần bán độc lập, giữ cả hai.
    - Loại bỏ các cột STT / chỉ số dòng (STT, No...) khỏi tập kiểm tra để tránh
      việc lỗi xuất POS tự tăng STT làm trôi dòng trùng lặp.
    - Bảng không ghi theo đơn: Mỗi dòng là một lần ghi độc lập, không khử trùng lặp.
    """
    if df.empty or len(df.columns) == 0:
        return df.copy()

    # Kiểm tra xem bảng có ghi theo đơn hay không
    if order_id_col is None or order_id_col not in df.columns:
        detected = find_order_id_col(list(df.columns))
        if detected is None:
            # Bảng không ghi theo đơn: giữ nguyên 100% các dòng
            return df.copy()
        order_id_col = detected

    # Tập cột để so khớp trùng lặp: loại trừ cột STT/chỉ mục dòng nếu có
    subset_cols = [c for c in df.columns if not is_row_index_col(c)]
    if not subset_cols:
        subset_cols = list(df.columns)

    # Khi bảng ghi theo đơn:
    # Sau khi ffill, hai dòng giống nhau ở MỌI Ô (trừ STT) trong cùng một đơn
    # chính là trùng lặp -> drop_duplicates loại bỏ dòng thừa.
    # Nếu hai dòng giống nhau ở chi tiết nhưng khác order_id_col -> giữ lại cả hai.
    df_dedup = df.drop_duplicates(subset=subset_cols, keep="first").reset_index(drop=True)
    return df_dedup


SUMMARY_ROW_PATTERNS = [
    r"^t[oổ]ng(?:\s*c[oộ]ng)?$",
    r"^t[oổ]ng\s*ti[eề]n$",
    r"^t[oổ]ng\s*s[oố]$",
    r"^t[oổ]ng\s*k[eế]t$",
    r"^c[oộ]ng$",
    r"^total$",
    r"^grand\s*total$",
    r"^sum$",
]

EMBEDDED_SUBTOTAL_PATTERN = re.compile(
    r"^\s*(?:t[oổ]ng\s*(?:ng[aà]y|th[aá]ng|c[oộ]ng|h[oợ]p|k[eế]t)?|c[oộ]ng|b[aá]o\s*c[aá]o|subtotal|grand\s*total)\b",
    re.IGNORECASE
)


def strip_summary_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tự động phát hiện và loại bỏ các dòng 'Tổng cộng / Total' ở cuối bảng.
    Giúp tránh việc lệnh .sum() trong code tính toán bị nhân đôi kết quả.
    """
    if df.empty or len(df) <= 1:
        return df

    check_n = min(3, len(df))
    drop_indices = []

    for idx in range(len(df) - 1, len(df) - 1 - check_n, -1):
        row = df.iloc[idx]
        is_summary = False
        for col in df.columns[:5]:
            val = row[col]
            if val is not None and not pd.isna(val):
                s = _normalize_str(str(val))
                if any(re.match(pat, s) for pat in SUMMARY_ROW_PATTERNS):
                    is_summary = True
                    break
        if is_summary:
            drop_indices.append(idx)
        else:
            break

    if drop_indices:
        df = df.drop(df.index[drop_indices]).reset_index(drop=True)

    return df


def strip_embedded_subtotal_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tự động phát hiện và loại bỏ các dòng tổng ngày / tổng tháng / subtotal
    do hệ thống POS chèn vào giữa bảng chi tiết bán hàng (như biz_130).
    """
    if df.empty or len(df) <= 1:
        return df

    target_cols = [
        c for c in df.columns
        if any(k in str(c).lower() for k in [
            'hàng', 'món', 'sản phẩm', 'item', 'product', 'diễn giải', 'nội dung', 'tên', 'mặt hàng'
        ])
    ]
    if not target_cols:
        target_cols = [c for c in df.columns[:3] if df[c].dtype == object or str(df[c].dtype) == "string"]

    if not target_cols:
        return df

    drop_mask = pd.Series(False, index=df.index)
    for col in target_cols:
        s_norm = df[col].astype(str)
        drop_mask |= s_norm.str.contains(EMBEDDED_SUBTOTAL_PATTERN, na=False)

    if drop_mask.any():
        return df[~drop_mask].reset_index(drop=True)
    return df


def propagate_partial_return_status(
    df: pd.DataFrame,
    order_id_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    Thực thi Luật §1 Rulebook tại tầng dữ liệu:
    "Đơn có trả hàng, kể cả chỉ trả một phần, là đơn trả hàng: bỏ cả đơn."
    Nếu trong cùng một bảng đơn hàng/chi tiết đơn hàng (không có cột ngày trả riêng),
    một mã đơn có bất kỳ dòng nào mang trạng thái trả hàng / trả một phần / hoàn hàng,
    lan truyền trạng thái 'Trả hàng (bỏ cả đơn)' cho toàn bộ các dòng của mã đơn đó.
    """
    if df.empty or len(df) <= 1:
        return df

    if order_id_col is None or order_id_col not in df.columns:
        order_id_col = find_order_id_col(list(df.columns))
    if not order_id_col or order_id_col not in df.columns:
        return df

    # Nếu bảng có cột ngày trả hàng riêng biệt thì việc coi đơn đã trả hay chưa
    # phụ thuộc vào as_of_date lúc truy vấn (do filter_valid_sales xử lý).
    has_separate_return_date = any(
        any(k in _normalize_str(str(c)) for k in ["ngay tra", "ngày trả", "ngay hoan", "ngày hoàn", "return date"])
        for c in df.columns
    )
    if has_separate_return_date:
        return df

    status_cols = [
        c for c in df.columns
        if any(k in _normalize_str(str(c)) for k in [
            "trang thai", "trạng thái", "tinh trang", "tình trạng", "status", "ghi chu tt", "xử lý", "xu ly"
        ])
    ]
    if not status_cols:
        return df

    out = df.copy()
    partial_return_pat = re.compile(
        r"tr[aả]\s*(?:1|m[oộ]t)\s*ph[aầ]n|tr[aả]\s*h[aà]ng|ho[aà]n\s*h[aà]ng|đ[aã]\s*tr[aả]|\breturn(?:ed)?\b",
        re.IGNORECASE,
    )

    for st_col in status_cols:
        s_str = out[st_col].astype(str)
        is_ret_row = s_str.str.contains(partial_return_pat, na=False)
        if is_ret_row.any() and not is_ret_row.all():
            ret_order_ids = set(out.loc[is_ret_row, order_id_col].dropna().astype(str).str.strip())
            ret_order_ids.discard("")
            ret_order_ids.discard("nan")
            if ret_order_ids:
                same_order_mask = out[order_id_col].astype(str).str.strip().isin(ret_order_ids)
                # Những dòng cùng mã đơn nhưng chưa gắn nhãn trả hàng -> cập nhật thành 'Trả hàng (đơn trả 1 phần)'
                needs_update = same_order_mask & (~is_ret_row)
                if needs_update.any():
                    out.loc[needs_update, st_col] = "Trả hàng"

    return out


def extract_unit_conversion_map(business: BusinessData) -> dict:
    """
    Trích xuất bảng ánh xạ quy đổi đơn vị cơ sở (Luật §3 & §10 Rulebook) từ các bảng
    QuyĐổiĐơnVị / DanhSachQuyDoi / DanhMuc.
    Trả về dict: {(key_norm, unit_norm): float_multiplier}
    """
    conv_map = {}
    if not business or not getattr(business, "tables", None):
        return conv_map

    for t in business.tables:
        df = t.df
        if df is None or df.empty:
            continue
        cols = list(df.columns)
        cols_norm = {_normalize_str(str(c)): c for c in cols}

        # Tìm cột hệ số quy đổi
        factor_col = next(
            (orig for norm, orig in cols_norm.items() if any(k in norm for k in [
                "he so", "hệ số", "ty le quy doi", "tỷ lệ quy đổi", "quy cach", "quy cách", "so luong quy doi", "sl quy doi"
            ])),
            None,
        )
        if not factor_col:
            continue

        unit_big_col = next(
            (orig for norm, orig in cols_norm.items() if any(k in norm for k in [
                "don vi lon", "đơn vị lớn", "dvt lon", "đơn vị quy đổi", "don vi quy doi", "don vi ban", "đơn vị tính", "dvt"
            ])),
            None,
        )
        item_col = next(
            (orig for norm, orig in cols_norm.items() if any(k in norm for k in [
                "ma hang", "mã hàng", "ma sp", "mã sp", "ten hang", "tên hàng", "san pham", "sản phẩm", "sku"
            ])),
            None,
        )

        for _, row in df.iterrows():
            try:
                raw_f = row[factor_col]
                if pd.isna(raw_f):
                    continue
                f_val = float(re.sub(r"[^\d.]", "", str(raw_f)))
                if f_val <= 0:
                    continue
                u_key = _normalize_str(str(row[unit_big_col])) if unit_big_col and not pd.isna(row[unit_big_col]) else ""
                i_key = _normalize_str(str(row[item_col])) if item_col and not pd.isna(row[item_col]) else ""
                if i_key and u_key:
                    conv_map[(i_key, u_key)] = f_val
                elif u_key:
                    conv_map[("*", u_key)] = f_val
            except Exception:
                continue

    return conv_map


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Pipeline làm sạch đầy đủ cho một DataFrame (Cắt dòng tổng đáy + Cắt dòng subtotal nhúng + Quy tắc 8 + Luật §1 Trả 1 phần)."""
    if df.empty:
        return df.copy()

    # 0a. Loại bỏ dòng tổng kết ở đáy bảng (nếu có)
    df_no_summary = strip_summary_rows(df)

    # 0b. Loại bỏ các dòng tổng ngày / tổng tháng / subtotal chèn giữa bảng POS
    df_no_subtotals = strip_embedded_subtotal_rows(df_no_summary)

    order_col = find_order_id_col(list(df_no_subtotals.columns))
    if order_col is None:
        # Không có cấu trúc đơn -> không can thiệp Rule 8
        return df_no_subtotals.copy()

    # 1. Forward-fill các cột cấp đơn
    df_ffilled = apply_group_forward_fill(df_no_subtotals, order_id_col=order_col)
    # 2. Khử trùng lặp dòng lỗi xuất file POS
    df_cleaned = deduplicate_order_rows(df_ffilled, order_id_col=order_col)
    # 3. Lan truyền trạng thái đơn trả hàng 1 phần sang toàn bộ đơn (Luật §1)
    df_final = propagate_partial_return_status(df_cleaned, order_id_col=order_col)
    return df_final


def clean_table(table: TableInfo) -> TableInfo:
    """Làm sạch một TableInfo theo Quy tắc 8."""
    cleaned_df = clean_dataframe(table.df)
    return TableInfo(
        table_id=table.table_id,
        source_file=table.source_file,
        fixed_file_name=table.fixed_file_name,
        sheet_name=table.sheet_name,
        df=cleaned_df,
        header_row_detected=table.header_row_detected,
        n_rows=len(cleaned_df),
        columns=list(cleaned_df.columns),
        merged_sheets=list(table.merged_sheets),
    )


def clean_business(business: BusinessData) -> BusinessData:
    """Làm sạch toàn bộ các bảng của BusinessData theo Quy tắc 8."""
    cleaned_tables = [clean_table(t) for t in business.tables]
    return BusinessData(
        business_id=business.business_id,
        tables=cleaned_tables,
        readme_text=business.readme_text,
        errors=list(business.errors),
    )
