"""
cleaner.py — Module thực hiện tiền xử lý dữ liệu, Quy tắc 8 (Rule 8 Data Cleaner)
và Quy tắc 1 (Rule 1 Order Status & Return Filter).

Quy tắc 8 (Rulebook):
1. Group Forward-Fill: Các ô để trống ở các dòng sau của cùng một nhóm đơn hàng
   được điền giá trị của dòng đầu đơn (khách hàng, ngày, ghi chú, trạng thái...).
2. Deduplicate: Hai dòng của cùng một đơn giống nhau ở mọi ô là lỗi xuất file POS,
   chỉ tính một lần. Hai dòng giống nhau của hai đơn khác nhau là hai lần bán riêng,
   phải giữ cả hai.
3. Bảng không ghi theo đơn: Mỗi dòng là một lần ghi độc lập, không khử trùng lặp.

Quy tắc 1 (Rulebook & User Approvals):
1. Nhận diện cột trạng thái và cột trả hàng cấp dòng dựa trên nội dung (Content-Based),
   không hardcode tên cột, tuyệt đối không rẽ nhánh theo business_id hoặc tên shop.
2. Phân loại giá trị trạng thái theo phân cấp ngữ nghĩa chuẩn hoá:
   - "giữ": đơn thành công hoặc đang giao dịch / đang giao
   - "loại (huỷ)": đơn bị huỷ bỏ, không giao được
   - "loại (trả)": đơn trả hàng, hoàn hàng, đổi trả
   - "giữ": ô trống / rỗng / null (mặc định giao dịch hoạt động)
   - "unknown": giá trị lạ chưa từng thấy -> ghi log cảnh báo, không tự đoán
3. Loại bỏ nguyên đơn (Whole-Order Exclusion):
   - Đơn có bất kỳ dòng nào có số lượng/giá trị trả > 0 thì loại toàn bộ các dòng của đơn.
   - Hợp tập hợp (Set Union): Excluded_Orders = Cancelled_IDs | Status_Return_IDs | Line_Return_IDs
     để triệt tiêu hoàn toàn lỗi tính trùng / loại kép (zero double counting).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Optional, Tuple, Union
import pandas as pd

try:
    from datamate.ingestion_schema.loader import BusinessData, TableInfo
except ImportError:
    from datamate.ingestion.loader import BusinessData, TableInfo

log = logging.getLogger(__name__)

# ==============================================================================
# HẰNG SỐ NHẬN DIỆN CỘT VÀ TỪ KHÓA QUY TẮC 8
# ==============================================================================

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


# ==============================================================================
# HẰNG SỐ NGỮ NGHĨA PHÂN LOẠI TRẠNG THÁI VÀ TRẢ HÀNG QUY TẮC 1
# ==============================================================================

# Cụm từ ngữ nghĩa theo vòng đời đơn hàng
STATUS_SEMANTIC_CLUSTERS = {
    "RETURN": [
        "hoàn hàng", "hoàn trả", "hàng hoàn", "hoàn tiền", "đã hoàn hàng",
        "trả hàng", "đã trả hàng", "hàng trả về", "trả lại", "returned", "đổi trả",
    ],
    "SUCCESS": [
        "hoàn thành", "hoàn tất", "completed", "đã giao", "thành công",
        "xong", "đã xong", "đã lấy", "ok", "received",
    ],
    "CANCEL": [
        "hủy", "huỷ", "đã hủy", "đã huỷ", "hủy đơn", "huỷ đơn", "đã hủy đơn",
        "khách hủy", "cancelled", "cancel", "không giao được",
    ],
    "PENDING": [
        "đang giao", "đang vận chuyển", "đang xử lý", "đang gửi", "shipping",
        "chờ giao", "đang giao dịch", "đang giao hàng",
    ],
}

# Alias tương thích ngược cho scripts/test_generalization_5shops.py
SEMANTIC_CLUSTERS = STATUS_SEMANTIC_CLUSTERS

# Các mẫu tên cột rõ ràng là phi trạng thái (cần loại trừ khỏi bộ dò cột trạng thái)
NON_STATUS_NAME_PATTERNS = [
    r"t[eê]n\s*(?:s[aả]n\s*ph[aẩ]m|h[aà]ng|sp|m[aặ]t\s*h[aà]ng)|product[\s_-]*name|item[\s_-]*name",
    r"(?:ph[uư][oơ]ng\s*th[uứ]c|h[iì]nh\s*th[uứ]c)\s*thanh\s*to[aá]n|payment[\s_-]*(?:method|type)|pttt",
    r"t[eê]n\s*kh[aá]ch|customer[\s_-]*name",
    r"t[eê]n\s*nh[aâ]n\s*vi[eê]n|staff[\s_-]*name|ng[uư][oờ]i\s*b[aá]n",
    r"^(?:ghi[\s_-]*ch[uú]|note|di[eễ]n[\s_-]*gi[aả]i|m[oô][\s_-]*t[aả]|description)$",
    r"^(?:kh[aá]ch\s*h[aà]ng|customer|nh[aâ]n\s*vi[eê]n|staff)$",
]

# Các mẫu nhận diện cột trả hàng cấp dòng (Line-level return columns)
LINE_RETURN_COLUMN_PATTERNS = [
    re.compile(r"(số\s*lượng|sl|tiền|giá\s*trị)\s*(trả|hoàn|trả\s*lại|quy\s*đổi)", re.IGNORECASE),
    re.compile(r"(s[oố]\s*l[uư][oơ]ng|sl|ti[eề]n|gi[aá]\s*tr[iị])\s*(tr[aả]|ho[aà]n|tr[aả]\s*l[aạ]i|quy\s*đ[oổ]i)", re.IGNORECASE),
]


# ==============================================================================
# HÀM CHUẨN HÓA VÀ ĐỊNH DANH PHÂN LOẠI
# ==============================================================================

def _normalize_str(text: str) -> str:
    """Chuẩn hóa chuỗi so khớp regex (NFC, lowercase, gộp khoảng trắng)."""
    text = unicodedata.normalize("NFC", str(text)).lower()
    return re.sub(r"\s+", " ", text).strip()


def normalize_status_text(text: Any) -> str:
    """Chuẩn hóa chuỗi so khớp ngữ nghĩa trạng thái (NFKC/NFC, lowercase, loại dấu câu lạ, gộp space)."""
    if text is None or pd.isna(text):
        return ""
    s = unicodedata.normalize("NFKC", str(text)).lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Alias cho scripts/test_generalization_5shops.py
normalize_text = normalize_status_text


class StatusClassification(tuple):
    """
    Tuple chứa (category, reason) hỗ trợ đồng thời:
    1. Unpacking: cat, reason = classify_status_value(...)
    2. Indexing: classify_status_value(...)[0]
    3. Direct string comparison: classify_status_value(...) == "giữ"
    4. Property access: result.category, result.reason
    """
    def __new__(cls, category: str, reason: str = ""):
        return super().__new__(cls, (category, reason))

    @property
    def category(self) -> str:
        return self[0]

    @property
    def reason(self) -> str:
        return self[1]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self[0] == other
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash((self[0], self[1]))


def classify_status_value(raw_val: Any) -> StatusClassification:
    """
    Phân loại giá trị trạng thái theo phân cấp ngữ nghĩa tất định (Strict Priority Hierarchy).
    Trả về: StatusClassification((category, reason))
    Categories: 'giữ', 'loại (huỷ)', 'loại (trả)', 'unknown'

    - null / empty / blank: return "giữ" (mặc định giao dịch hoạt động theo quyết định người dùng).
    - novel / unseen values: log warning UNKNOWN, trả về "unknown", tuyệt đối không tự đoán.
    """
    s = normalize_status_text(raw_val)
    if not s or s in ("nan", "none", "na", "null", "rỗng"):
        return StatusClassification("giữ", "Null/Empty value: retained as default active transaction")

    # Ưu tiên 1: Cụm từ TRẢ HÀNG (kiểm tra trước để bẫy cụm 'hoàn hàng', 'hoàn trả' trước chữ 'hoàn')
    for phrase in STATUS_SEMANTIC_CLUSTERS["RETURN"]:
        if phrase in s:
            return StatusClassification("loại (trả)", f"Matches return semantic phrase: '{phrase}'")

    # Ưu tiên 2: Cụm từ THÀNH CÔNG (giữ trọn vẹn 'hoàn thành', 'hoàn tất'...)
    for phrase in STATUS_SEMANTIC_CLUSTERS["SUCCESS"]:
        if phrase in s:
            return StatusClassification("giữ", f"Matches success semantic phrase: '{phrase}'")

    # Ưu tiên 3: Cụm từ HUỶ ĐƠN
    for phrase in STATUS_SEMANTIC_CLUSTERS["CANCEL"]:
        if phrase in s:
            return StatusClassification("loại (huỷ)", f"Matches cancel semantic phrase: '{phrase}'")

    # Ưu tiên 4: Cụm từ ĐANG GIAO / ĐANG XỬ LÝ (Rule 1: Đang giao vẫn tính)
    for phrase in STATUS_SEMANTIC_CLUSTERS["PENDING"]:
        if phrase in s:
            return StatusClassification("giữ", f"Matches pending/in-transit semantic phrase (Rule 1): '{phrase}'")

    # Ưu tiên 5: GIÁ TRỊ LẠ CHƯA TỪNG THẤY -> KHÔNG TỰ ĐOÁN, GHI LOG CẢNH BÁO
    log.warning("UNSEEN STATUS VALUE: '%s' does not match any known semantic cluster", raw_val)
    return StatusClassification("unknown", f"UNSEEN STATUS VALUE: '{raw_val}' does not match any known semantic cluster")


def is_non_status_column_name(col_name: str) -> bool:
    """Kiểm tra tên cột có rõ ràng là cột phi trạng thái (sản phẩm, thanh toán, khách hàng, nhân viên, ghi chú)."""
    norm = _normalize_str(col_name)
    for pat in NON_STATUS_NAME_PATTERNS:
        if re.search(pat, norm):
            return True
    return False


# ==============================================================================
# BỘ DÒ CỘT TRẠNG THÁI VÀ CỘT TRẢ HÀNG CẤP DÒNG DỰA TRÊN NỘI DUNG (CONTENT-BASED)
# ==============================================================================

def detect_status_columns(df: pd.DataFrame, min_cluster_coverage: float = 0.50) -> list[str]:
    """
    Nhận diện các cột trạng thái đơn hàng dựa trên phân tích nội dung (Content-Based Column Detection):
    - Dạng chuỗi / object / category.
    - Phân bố thấp (Low Cardinality): unique <= 25 hoặc unique / tổng dòng < 0.05.
    - Độ phủ ngữ nghĩa vòng đời đơn hàng >= min_cluster_coverage (mặc định 50%).
    - Loại trừ các cột không phải trạng thái: tên sản phẩm, hình thức thanh toán, khách hàng, nhân viên, ghi chú.
    - Hoàn toàn không rẽ nhánh theo business_id hoặc tên shop.
    """
    if df.empty or len(df.columns) == 0:
        return []

    status_cols: list[tuple[str, float, int]] = []
    total_cluster_phrases = [p for cluster in STATUS_SEMANTIC_CLUSTERS.values() for p in cluster]

    for col in df.columns:
        col_str = str(col)
        # Bỏ qua nếu tên cột rõ ràng là cột phi trạng thái
        if is_non_status_column_name(col_str):
            continue

        # Bỏ qua nếu cột là số hoặc datetime chuẩn
        series = df[col]
        if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
            continue

        non_null_series = series.dropna()
        if len(non_null_series) == 0:
            continue

        # Kiểm tra Low Cardinality (unique <= 25 hoặc tỉ lệ < 0.05)
        nunique = non_null_series.nunique()
        is_low_cardinality = (nunique <= 25) or (nunique / len(non_null_series) < 0.05)
        if not is_low_cardinality:
            continue

        # Kiểm tra độ phủ ngữ nghĩa vòng đời
        str_series = non_null_series.astype(str).str.strip()
        valid_items = str_series[str_series.ne("") & ~str_series.str.lower().isin(["nan", "none", "null"])]
        if len(valid_items) == 0:
            continue

        matches = 0
        for val in valid_items:
            norm_val = normalize_status_text(val)
            if any(p in norm_val for p in total_cluster_phrases):
                matches += 1

        coverage = matches / len(valid_items)
        if coverage >= min_cluster_coverage:
            status_cols.append((col_str, coverage, nunique))

    # Sắp xếp theo độ phủ giảm dần, sau đó theo số giá trị phân biệt tăng dần
    status_cols.sort(key=lambda x: (-x[1], x[2]))
    return [col for col, cov, nunique in status_cols]


def detect_line_return_columns(df: pd.DataFrame) -> list[str]:
    """
    Nhận diện cột trả hàng cấp dòng dựa trên ngữ nghĩa tên cột và dữ liệu số (Line Return Columns):
    - Tên cột khớp regex: r"(số\\s*lượng|sl|tiền|giá\\s*trị)\\s*(trả|hoàn|trả\\s*lại|quy\\s*đổi)"
    - Kiểu dữ liệu số (hoặc chuỗi số) có trên 50% dòng hợp lệ.
    - Chứa ít nhất một giá trị > 0 (xác nhận có phát sinh trả hàng).
    """
    if df.empty or len(df.columns) == 0:
        return []

    line_ret_cols: list[str] = []
    for col in df.columns:
        norm_name = unicodedata.normalize("NFKC", str(col)).lower()
        if not any(pat.search(norm_name) for pat in LINE_RETURN_COLUMN_PATTERNS):
            continue

        # Kiểm tra tính chất số
        series = df[col]
        num = pd.to_numeric(
            series.astype(str).str.replace(",", "", regex=False).str.strip(),
            errors="coerce"
        )
        if len(df) > 0 and (num.notna().sum() > len(df) * 0.5):
            # Bắt buộc phải có giá trị > 0
            if (num > 0).any():
                line_ret_cols.append(str(col))

    return line_ret_cols


# ==============================================================================
# QUY TẮC 1: BỘ LỌC ĐƠN HUỶ / TRẢ VÀ LOẠI TRỪ NGUYÊN ĐƠN (WHOLE-ORDER EXCLUSION)
# ==============================================================================

def get_order_status_sets(
    df: pd.DataFrame,
    order_id_col: Optional[str] = None,
) -> dict[str, set[Any]]:
    """
    Trả về chi tiết các tập hợp mã đơn theo phân loại trạng thái:
    - 'cancelled': Set(Cancelled_IDs)
    - 'status_returned': Set(Status_Return_IDs)
    - 'line_returned': Set(Line_Return_IDs)
    - 'excluded': Set(Cancelled_IDs) | Set(Status_Return_IDs) | Set(Line_Return_IDs)
    """
    cancelled_ids: set[Any] = set()
    status_return_ids: set[Any] = set()
    line_return_ids: set[Any] = set()

    if df.empty or len(df.columns) == 0:
        return {
            "cancelled": cancelled_ids,
            "status_returned": status_return_ids,
            "line_returned": line_return_ids,
            "excluded": set(),
        }

    if order_id_col is None or order_id_col not in df.columns:
        detected = find_order_id_col(list(df.columns))
        if detected is None:
            return {
                "cancelled": cancelled_ids,
                "status_returned": status_return_ids,
                "line_returned": line_return_ids,
                "excluded": set(),
            }
        order_id_col = detected

    # 1. Quét qua các cột trạng thái
    status_cols = detect_status_columns(df)
    for col in status_cols:
        for order_id, val in zip(df[order_id_col], df[col]):
            if is_empty_value(order_id):
                continue
            cat, _ = classify_status_value(val)
            if cat == "loại (huỷ)":
                cancelled_ids.add(order_id)
            elif cat == "loại (trả)":
                status_return_ids.add(order_id)

    # 2. Quét qua các cột trả hàng cấp dòng
    # Rule 1: Đơn có bất kỳ dòng nào trả hàng > 0 là loại cả đơn
    line_ret_cols = detect_line_return_columns(df)
    for col in line_ret_cols:
        num = pd.to_numeric(
            df[col].astype(str).str.replace(",", "", regex=False).str.strip(),
            errors="coerce"
        ).fillna(0)
        has_return = num > 0
        if has_return.any():
            returned_ids = df.loc[has_return, order_id_col].dropna().unique()
            line_return_ids.update(returned_ids)

    # 3. Hợp tập hợp (Set Union) để đảm bảo zero double counting
    excluded = cancelled_ids | status_return_ids | line_return_ids
    return {
        "cancelled": cancelled_ids,
        "status_returned": status_return_ids,
        "line_returned": line_return_ids,
        "excluded": excluded,
    }


def get_excluded_order_ids(
    df: pd.DataFrame,
    order_id_col: Optional[str] = None,
) -> set[Any]:
    """
    Xác định toàn bộ tập mã đơn hàng cần loại trừ theo Rule 1:
    - Đơn có trạng thái huỷ (Cancelled_IDs)
    - Đơn có trạng thái trả (Status_Return_IDs)
    - Đơn có bất kỳ dòng nào phát sinh trả hàng ở cấp dòng (Line_Return_IDs: SL trả > 0 hoặc tiền trả > 0)
    Áp dụng toán tử hợp tập hợp (Set Union):
        Excluded_Orders = Set(Cancelled_IDs) | Set(Status_Return_IDs) | Set(Line_Return_IDs)
    đảm bảo đơn vừa có trạng thái trả vừa có dòng trả chỉ bị loại bỏ 1 lần duy nhất,
    triệt tiêu hoàn toàn lỗi tính trừ hai lần (zero double counting).
    """
    if df.empty or len(df.columns) == 0:
        return set()

    if order_id_col is None or order_id_col not in df.columns:
        detected = find_order_id_col(list(df.columns))
        if detected is None:
            return set()
        order_id_col = detected

    status_sets = get_order_status_sets(df, order_id_col=order_id_col)
    return status_sets["excluded"]


def filter_order_status(
    df: pd.DataFrame,
    order_id_col: Optional[str] = None,
    excluded_order_ids: Optional[set[Any]] = None,
) -> pd.DataFrame:
    """
    Áp dụng bộ lọc Rule 1 loại bỏ toàn bộ các dòng của mọi mã đơn thuộc tập Excluded_Orders.
    """
    if df.empty or len(df.columns) == 0:
        return df.copy()

    if order_id_col is None or order_id_col not in df.columns:
        detected = find_order_id_col(list(df.columns))
        if detected is None:
            return df.copy()
        order_id_col = detected

    if excluded_order_ids is None:
        excluded_order_ids = get_excluded_order_ids(df, order_id_col=order_id_col)

    if not excluded_order_ids:
        return df.copy()

    # Rule 1 Whole-Order Exclusion: loại bỏ toàn bộ các dòng của các đơn bị loại trừ
    mask_keep = ~df[order_id_col].isin(excluded_order_ids)
    return df.loc[mask_keep].reset_index(drop=True)


def get_business_excluded_order_ids(business: BusinessData) -> set[Any]:
    """
    Thu thập tập mã đơn cần loại trừ trên TOÀN BỘ các bảng trong một shop (business).
    Hợp tất cả các mã đơn huỷ/trả từ bảng hóa đơn và bảng chi tiết dòng trả hàng.
    """
    all_excluded: set[Any] = set()
    for table in business.tables:
        if table.df is not None and not table.df.empty:
            excluded = get_excluded_order_ids(table.df)
            all_excluded.update(excluded)
    return all_excluded


def filter_business_order_status(
    business: BusinessData,
    excluded_order_ids: Optional[set[Any]] = None,
) -> BusinessData:
    """
    Áp dụng bộ lọc Rule 1 loại bỏ toàn bộ các đơn huỷ/trả trên tất cả các bảng của BusinessData.
    """
    if excluded_order_ids is None:
        excluded_order_ids = get_business_excluded_order_ids(business)

    if not excluded_order_ids:
        return business

    filtered_tables = []
    for table in business.tables:
        if table.df is not None and not table.df.empty:
            order_col = find_order_id_col(list(table.df.columns))
            if order_col:
                new_df = table.df.loc[~table.df[order_col].isin(excluded_order_ids)].reset_index(drop=True)
                filtered_tables.append(
                    TableInfo(
                        table_id=table.table_id,
                        source_file=table.source_file,
                        fixed_file_name=table.fixed_file_name,
                        sheet_name=table.sheet_name,
                        df=new_df,
                        header_row_detected=table.header_row_detected,
                        n_rows=len(new_df),
                        columns=list(new_df.columns),
                        merged_sheets=list(table.merged_sheets),
                    )
                )
            else:
                filtered_tables.append(table)
        else:
            filtered_tables.append(table)

    return BusinessData(
        business_id=business.business_id,
        tables=filtered_tables,
        readme_text=business.readme_text,
        errors=list(business.errors),
    )


# ==============================================================================
# CÁC HÀM TIỀN XỬ LÝ QUY TẮC 8 (FORWARD-FILL & DEDUPLICATION)
# ==============================================================================

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

    # Tập cột để so khớp trùng lặp: loại trừ cột STT/chỉ mục dòng nếu có.
    subset_cols = [c for c in df.columns if not is_row_index_col(c)]
    if not subset_cols:
        subset_cols = list(df.columns)
    elif order_id_col not in subset_cols:
        subset_cols.append(order_id_col)

    # Drop duplicates trên cùng một đơn
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


# ==============================================================================
# PIPELINE LÀM SẠCH ĐẦY ĐỦ (DATA CLEANING PIPELINE)
# ==============================================================================

def clean_dataframe(df: pd.DataFrame, filter_status: bool = False) -> pd.DataFrame:
    """
    Pipeline làm sạch đầy đủ cho một DataFrame:
    1. Cắt dòng tổng kết ở đáy bảng (nếu có).
    2. Group Forward-Fill theo Quy tắc 8 (nếu có cột mã đơn).
    3. Khử trùng lặp dòng lỗi xuất POS theo Quy tắc 8.
    4. Tùy chọn filter_status=True: Lọc bỏ đơn huỷ/trả theo Quy tắc 1.
    """
    if df.empty:
        return df.copy()

    # 0. Loại bỏ dòng tổng kết ở đáy bảng (nếu có)
    df_no_summary = strip_summary_rows(df)

    order_col = find_order_id_col(list(df_no_summary.columns))
    if order_col is None:
        # Không có cấu trúc đơn -> không can thiệp Rule 8
        return df_no_summary.copy()

    # 1. Forward-fill các cột cấp đơn
    df_ffilled = apply_group_forward_fill(df_no_summary, order_id_col=order_col)
    # 2. Khử trùng lặp dòng lỗi xuất file POS
    df_cleaned = deduplicate_order_rows(df_ffilled, order_id_col=order_col)

    # 3. Tùy chọn: Lọc bỏ đơn huỷ / trả theo Rule 1
    if filter_status:
        df_cleaned = filter_order_status(df_cleaned, order_id_col=order_col)

    return df_cleaned


def clean_table(table: TableInfo, filter_status: bool = False) -> TableInfo:
    """Làm sạch một TableInfo theo Quy tắc 8 (tùy chọn Quy tắc 1)."""
    cleaned_df = clean_dataframe(table.df, filter_status=filter_status)
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


def clean_business(business: BusinessData, filter_status: bool = False) -> BusinessData:
    """Làm sạch toàn bộ các bảng của BusinessData theo Quy tắc 8 (tùy chọn Quy tắc 1)."""
    cleaned_tables = [clean_table(t, filter_status=False) for t in business.tables]
    cleaned_biz = BusinessData(
        business_id=business.business_id,
        tables=cleaned_tables,
        readme_text=business.readme_text,
        errors=list(business.errors),
    )
    if filter_status:
        cleaned_biz = filter_business_order_status(cleaned_biz)
    return cleaned_biz
