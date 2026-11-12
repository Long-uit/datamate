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
    r"s[oố][\s_-]*ct\b",
    r"s[oố][\s_-]*ch[uứ]ng[\s_-]*t[uừ]",
    r"m[aã][\s_-]*gd\b",
    r"m[aã][\s_-]*giao[\s_-]*d[iị]ch",
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
        "đã nhập hàng", "đã nhập kho", "đã nhận hàng",
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
# Chú ý: KHÔNG khớp 'Số lượng quy đổi' (là số lượng bán đã quy đổi ra đơn vị cơ sở, không phải trả hàng)
LINE_RETURN_COLUMN_PATTERNS = [
    re.compile(r"(số\s*lượng|sl|tiền|giá\s*trị)\s*(trả|hoàn|trả\s*lại)", re.IGNORECASE),
    re.compile(r"(s[oố]\s*l[uư][oơ]ng|sl|ti[eề]n|gi[aá]\s*tr[iị])\s*(tr[aả]|ho[aà]n|tr[aả]\s*l[aạ]i)", re.IGNORECASE),
]


# ==============================================================================
# HÀM CHUẨN HÓA VÀ ĐỊNH DANH PHÂN LOẠI
# ==============================================================================

def _normalize_str(text: str) -> str:
    """Chuẩn hóa chuỗi so khớp regex (NFC, lowercase, thay _ và - bằng khoảng trắng, gộp khoảng trắng)."""
    text = unicodedata.normalize("NFC", str(text)).lower()
    text = re.sub(r"[_\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_col_for_match(col_name: Any) -> str:
    """
    Chuẩn hóa tên cột trước khi match (Bước 3):
    - Chuẩn hóa Unicode NFC, lowercase.
    - Bỏ dấu tiếng Việt (đ/Đ -> d, loại bỏ combining marks Mn).
    - Thay '_', '-', '.', '/', '(', ')' bằng khoảng trắng.
    - Gộp khoảng trắng liên tiếp.
    Ví dụ: 'ngay_ban' -> 'ngay ban', 'Ngày-bán' -> 'ngay ban', 'T.Tiền (đ)' -> 't tien d'.
    """
    if col_name is None:
        return ""
    s = unicodedata.normalize("NFC", str(col_name)).lower()
    s = s.replace("đ", "d").replace("Đ", "d")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"[_\-./()]+", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


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

        # Kiểm tra độ phủ ngữ nghĩa vòng đời (vectorized theo unique values để tăng tốc độ)
        str_series = non_null_series.astype(str).str.strip()
        valid_items = str_series[str_series.ne("") & ~str_series.str.lower().isin(["nan", "none", "null"])]
        if len(valid_items) == 0:
            continue

        vc = valid_items.value_counts()
        matches = 0
        for val_str, count in vc.items():
            norm_val = normalize_status_text(val_str)
            if any(p in norm_val for p in total_cluster_phrases):
                matches += int(count)

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

    # 1. Quét qua các cột trạng thái (dùng bảng ánh xạ unique values để tránh lặp từng dòng)
    status_cols = detect_status_columns(df)
    for col in status_cols:
        uniq_vals = df[col].dropna().unique()
        cancel_vals = set()
        return_vals = set()
        for uv in uniq_vals:
            cat, _ = classify_status_value(uv)
            if cat == "loại (huỷ)":
                cancel_vals.add(uv)
            elif cat == "loại (trả)":
                return_vals.add(uv)
        if cancel_vals:
            c_ids = df.loc[df[col].isin(cancel_vals), order_id_col].dropna().unique()
            cancelled_ids.update(x for x in c_ids if not is_empty_value(x))
        if return_vals:
            r_ids = df.loc[df[col].isin(return_vals), order_id_col].dropna().unique()
            status_return_ids.update(x for x in r_ids if not is_empty_value(x))

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
    Nếu bảng không có cột mã đơn riêng biệt (ví dụ SoBanHang mỗi dòng là 1 giao dịch),
    lọc trực tiếp theo cột trạng thái được nhận diện bởi detect_status_columns(df).
    """
    if df.empty or len(df.columns) == 0:
        return df.copy()

    if order_id_col is None or order_id_col not in df.columns:
        detected = find_order_id_col(list(df.columns))
        if detected is None:
            status_cols = detect_status_columns(df)
            if not status_cols:
                return df.copy()
            keep_mask = pd.Series(True, index=df.index)
            for st_col in status_cols:
                uniq_vals = df[st_col].dropna().unique()
                bad_vals = {uv for uv in uniq_vals if classify_status_value(uv)[0] in ("loại (huỷ)", "loại (trả)")}
                if bad_vals:
                    keep_mask &= ~df[st_col].isin(bad_vals)
            return df.loc[keep_mask].reset_index(drop=True)
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
    Ưu tiên cột khớp chính xác hoặc bắt đầu bằng từ khóa mã đơn, hỗ trợ cả tên không dấu/snake_case.
    """
    unaccented_keywords = [
        r"\bma\s*don\b",
        r"\bma\s*phieu\b",
        r"\bso\s*phieu\b",
        r"\bso\s*hoa\s*don\b",
        r"\bso\s*hd\b",
        r"\bma\s*chung\s*tu\b",
        r"\bso\s*ct\b",
        r"\bso\s*chung\s*tu\b",
        r"\bma\s*gd\b",
        r"\bma\s*giao\s*dich\b",
        r"\border\s*id\b",
        r"\binvoice\s*id\b",
        r"\bma\s*hoa\s*don\b",
        r"\bma\s*hd\b",
    ]
    for col in columns:
        norm = _normalize_str(col)
        for pattern in ORDER_ID_KEYWORDS:
            if re.search(pattern, norm):
                return col
        norm_match = normalize_col_for_match(col)
        for pat in unaccented_keywords:
            if re.search(pat, norm_match):
                return col
    return None


def find_order_level_cols(columns: list[str], order_id_col: str) -> list[str]:
    """
    Tìm tất cả các cột cấp đơn hàng (cần forward-fill) trong danh sách cột.
    """
    unaccented_order_keywords = [
        r"\bngay\b", r"\bthoi\s*gian\b", r"\bdate\b", r"\btime\b",
        r"\bkhach\s*hang\b", r"\bten\s*khach\b", r"\bma\s*khach\b", r"\bcustomer\b",
        r"\bsdt\b", r"\bphone\b", r"\btrang\s*thai\b", r"\btinh\s*trang\b", r"\bstatus\b",
        r"\bghi\s*chu\b", r"\bnote\b", r"\bnhan\s*vien\b", r"\bnguoi\s*ban\b",
        r"\bthu\s*ngan\b", r"\bstaff\b", r"\bkenh\s*ban\b", r"\bchi\s*nhanh\b", r"\bbranch\b",
    ]
    order_cols = [order_id_col]
    for col in columns:
        if col == order_id_col:
            continue
        norm = _normalize_str(col)
        matched = False
        for pattern in ORDER_LEVEL_KEYWORDS:
            if re.search(pattern, norm):
                order_cols.append(col)
                matched = True
                break
        if not matched:
            norm_match = normalize_col_for_match(col)
            for pat in unaccented_order_keywords:
                if re.search(pat, norm_match):
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


# ==============================================================================
# PIPELINE LÀM SẠCH ĐẦY ĐỦ (DATA CLEANING PIPELINE)
# ==============================================================================

def clean_dataframe(df: pd.DataFrame, filter_status: bool = False) -> pd.DataFrame:
    """
    Pipeline làm sạch đầy đủ cho một DataFrame:
    1. Cắt dòng tổng kết ở đáy bảng (nếu có).
    2. Cắt dòng subtotal nhúng giữa bảng POS (nếu có).
    3. Group Forward-Fill theo Quy tắc 8 (nếu có cột mã đơn).
    4. Khử trùng lặp dòng lỗi xuất POS theo Quy tắc 8.
    5. Lan truyền trạng thái đơn trả hàng 1 phần sang toàn bộ đơn (Luật §1).
    6. Tùy chọn filter_status=True: Lọc bỏ đơn huỷ/trả theo Quy tắc 1.
    """
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
    df_cleaned = propagate_partial_return_status(df_cleaned, order_id_col=order_col)

    # 4. Tùy chọn: Lọc bỏ đơn huỷ / trả theo Rule 1
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


def _parse_money_series(s: pd.Series) -> pd.Series:
    """Chuyển đổi Series tiền tệ (bao gồm định dạng '1,45tr', '396.000đ') sang float."""
    def _parse_val(val: Any) -> float:
        if val is None or pd.isna(val):
            return 0.0
        if isinstance(val, (int, float)):
            return 0.0 if pd.isna(val) else float(val)
        st = str(val).strip()
        if not st or st.lower() in ("nan", "none", "null"):
            return 0.0
        neg = False
        if st.startswith("(") and st.endswith(")"):
            neg = True
            st = st[1:-1].strip()
        elif st.startswith("-"):
            neg = True
            st = st[1:].strip()
        s_clean = re.sub(r"(?i)(?:vnđ|vnd|đ|đồng|\$|(?<=\d|\s)d$)", "", st).strip().lower()
        mult = 1.0
        if "triệu" in s_clean or re.search(r"(?<=\d)\s*tr\b", s_clean):
            mult = 1_000_000.0
            s_clean = re.sub(r"triệu|tr\b", "", s_clean).strip()
        elif "nghìn" in s_clean or "ngàn" in s_clean:
            mult = 1_000.0
            s_clean = s_clean.replace("nghìn", "").replace("ngàn", "").strip()
        elif s_clean.endswith("k"):
            mult = 1_000.0
            s_clean = s_clean[:-1].strip()
        if "." in s_clean and "," in s_clean:
            if s_clean.rfind(",") > s_clean.rfind("."):
                s_clean = s_clean.replace(".", "").replace(",", ".")
            else:
                s_clean = s_clean.replace(",", "")
        elif "," in s_clean:
            parts = s_clean.split(",")
            if mult > 1.0 or (len(parts) == 2 and len(parts[1]) != 3):
                s_clean = s_clean.replace(",", ".")
            else:
                s_clean = s_clean.replace(",", "")
        elif "." in s_clean:
            parts = s_clean.split(".")
            if mult == 1.0 and (len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and parts[0].isdigit() and int(parts[0]) != 0)):
                s_clean = s_clean.replace(".", "")
        try:
            v = float(s_clean) * mult
            return -v if neg else v
        except Exception:
            return 0.0

    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce").fillna(0.0).astype(float)
    return s.map(_parse_val)


def _find_col_by_norm(columns: list[str], exact_or_sub_keywords: list[str], exact_only: bool = False) -> Optional[str]:
    """Tìm cột đầu tiên khớp với danh sách từ khóa đã chuẩn hóa qua normalize_col_for_match."""
    for col in columns:
        norm = normalize_col_for_match(col)
        for kw in exact_or_sub_keywords:
            if exact_only:
                if norm == kw:
                    return col
            else:
                if kw in norm:
                    return col
    return None


def _standardize_status_alias_series(s: pd.Series) -> pd.Series:
    """
    Chuẩn hóa cột alias 'Trạng thái' sao cho các giá trị thuộc nhóm loại (huỷ) hoặc loại (trả)
    luôn chứa từ khóa tiếng Việt chuẩn ('đã hủy' / 'trả hàng') để regex của LLM nhận diện chính xác.
    """
    uniq_vals = s.dropna().unique()
    val_map: dict[Any, Any] = {}
    for val in uniq_vals:
        cat, _ = classify_status_value(val)
        s_val = str(val).strip()
        s_low = s_val.lower()
        if cat == "loại (huỷ)" and not any(k in s_low for k in ("hủy", "huỷ", "huy", "cancel")):
            val_map[val] = f"{s_val} (đã hủy)"
        elif cat == "loại (trả)" and not any(k in s_low for k in ("trả", "tra")):
            val_map[val] = f"{s_val} (trả hàng)"
        else:
            val_map[val] = val
    if not val_map:
        return s
    return s.map(lambda x: val_map.get(x, x))


def build_unified_relational_views(business: BusinessData) -> BusinessData:
    """
    Bước 3 — Unified relational view và chuẩn hóa chọn bảng/cột:
    1. Lan truyền trạng thái đơn bị trả hàng một phần / trả hàng theo lô giữa các bảng cùng shop.
    2. Khi bảng đơn hàng (don_hang / HoaDon) tách rời khỏi bảng chi tiết dòng hàng (chi_tiet_don / ChiTietHoaDon):
       - Join các thuộc tính cấp đơn (Ngày, Trạng thái, Khách hàng) từ bảng đơn sang bảng chi tiết.
       - Join Tên hàng / Nhóm hàng từ bảng danh mục sản phẩm (san_pham / HangHoa) sang bảng chi tiết.
       - Tính tổng thành tiền dòng hàng hợp lệ của từng đơn gắn vào cột 'Thành tiền' của bảng đơn hàng (nếu bảng đơn chưa có cột thành tiền dòng hàng).
    3. Gắn cột alias tiếng Việt có dấu chuẩn ('Ngày bán', 'Thành tiền', 'Trạng thái', 'Mã đơn hàng', 'Tên hàng', 'Số lượng')
       khi bảng chỉ có tên cột không dấu / snake_case / viết tắt ('ngay_ban', 'trang_thai', 'Amount', 'Tổng', 'S.L', 'Nội dung').
    4. Làm giàu bảng tồn kho snapshot (BaoCaoTonKho) với cột 'Ngày' (ngày giao dịch gần nhất của shop) và 'Quy cách' từ bảng đơn vị tính.
    """
    if not business or not getattr(business, "tables", None):
        return business

    tables = list(business.tables)

    # --- 1. Thu thập các mã đơn có phát sinh trả hàng từ bảng trả hàng / bảng lô ---
    cross_table_returned_orders: set[str] = set()
    for t in tables:
        df = t.df
        if df is None or df.empty:
            continue
        ord_col = find_order_id_col(list(df.columns))
        if not ord_col:
            continue
        # Kiểm tra cột ngày trả riêng: nếu có cột ngày trả riêng thì để filter_valid_sales xử lý theo as_of_date
        has_sep_ret_date = any(
            any(k in normalize_col_for_match(c) for k in ["ngay tra", "ngay hoan", "return date"])
            for c in df.columns
        )
        if has_sep_ret_date:
            continue
        t_stem_norm = normalize_col_for_match(t.fixed_file_name or t.table_id)
        # Nếu là bảng phiếu trả hàng riêng không có cột ngày trả riêng
        if any(k in t_stem_norm for k in ["tra hang", "phieu tra", "hoan hang"]):
            oids = set(df[ord_col].dropna().astype(str).str.strip())
            cross_table_returned_orders.update(x for x in oids if x and x.lower() != "nan")
            continue
        # Kiểm tra cột trả hàng cấp dòng (SL trả > 0) hoặc trạng thái dòng trả hàng
        status_sets = get_order_status_sets(df, order_id_col=ord_col)
        for oid in (status_sets["status_returned"] | status_sets["line_returned"]):
            s_oid = str(oid).strip()
            if s_oid and s_oid.lower() != "nan":
                cross_table_returned_orders.add(s_oid)

    # Lan truyền trạng thái 'Trả hàng' cho các đơn nằm trong cross_table_returned_orders
    if cross_table_returned_orders:
        for t in tables:
            df = t.df
            if df is None or df.empty:
                continue
            ord_col = find_order_id_col(list(df.columns))
            if not ord_col:
                continue
            st_cols = detect_status_columns(df)
            if not st_cols:
                continue
            mask_ret = df[ord_col].astype(str).str.strip().isin(cross_table_returned_orders)
            if mask_ret.any():
                df_copy = df.copy()
                for st_c in st_cols:
                    # Chỉ cập nhật các dòng đang ở trạng thái thành công/giữ sang 'Trả hàng'
                    cur_cats = [classify_status_value(v)[0] for v in df_copy.loc[mask_ret, st_c]]
                    if any(c == "giữ" for c in cur_cats):
                        df_copy.loc[mask_ret, st_c] = "Trả hàng"
                t.df = df_copy
                t.columns = list(df_copy.columns)

    # --- 2. Nhận diện bảng Header (đơn hàng), Detail (chi tiết đơn), Product (sản phẩm) ---
    header_table: Optional[TableInfo] = None
    detail_table: Optional[TableInfo] = None
    product_table: Optional[TableInfo] = None

    for t in tables:
        if t.df is None or t.df.empty:
            continue
        stem_norm = normalize_col_for_match(t.fixed_file_name or t.table_id)
        if any(k in stem_norm for k in ["chi tiet", "chitiet", "detail"]) and not any(k in stem_norm for k in ["lo", "lot"]):
            if detail_table is None:
                detail_table = t
        elif any(k in stem_norm for k in ["don hang", "donhang", "hoa don", "hoadon"]) and not any(
            k in stem_norm for k in ["chi tiet", "chitiet", "detail", "lo", "lot", "tra hang"]
        ):
            if header_table is None:
                header_table = t
        elif any(k in stem_norm for k in ["san pham", "sanpham", "hang hoa", "hanghoa", "danh muc", "danhmuc"]) and not any(
            k in stem_norm for k in ["don vi", "donvi", "quy doi", "quydoi", "nhom"]
        ):
            if product_table is None:
                product_table = t

    if header_table is not None and detail_table is not None:
        h_df = header_table.df.copy()
        d_df = detail_table.df.copy()
        h_ord = find_order_id_col(list(h_df.columns))
        d_ord = find_order_id_col(list(d_df.columns))

        if h_ord and d_ord:
            # 2a. Join Ngày, Trạng thái, Khách hàng từ Header sang Detail
            h_date_col = _find_col_by_norm(list(h_df.columns), ["ngay", "date", "thoi gian"])
            h_status_cols = detect_status_columns(h_df)
            h_status_col = h_status_cols[0] if h_status_cols else _find_col_by_norm(
                list(h_df.columns), ["trang thai", "tinh trang", "status"]
            )
            h_cust_cols = [
                c for c in h_df.columns
                if any(k in normalize_col_for_match(c) for k in ["khach hang", "ten khach", "ma kh", "so kh", "customer"])
                and not any(bad in normalize_col_for_match(c) for bad in ["tra", "tien", "no", "thanh toan", "bill"])
                and c != h_ord
            ]

            join_cols = []
            for cand_c in ([h_date_col, h_status_col] + h_cust_cols):
                if cand_c and cand_c in h_df.columns and cand_c not in join_cols and cand_c not in d_df.columns:
                    join_cols.append(cand_c)

            if join_cols:
                h_lookup = h_df[[h_ord] + join_cols].drop_duplicates(subset=[h_ord], keep="first").copy()
                h_lookup["_join_ord_key"] = h_lookup[h_ord].astype(str).str.strip()
                d_df["_join_ord_key"] = d_df[d_ord].astype(str).str.strip()
                d_df = d_df.merge(h_lookup.drop(columns=[h_ord]), on="_join_ord_key", how="left")
                d_df.drop(columns=["_join_ord_key"], inplace=True)

            # 2b. Tính tổng thành tiền dòng hàng theo đơn và gắn 'Thành tiền' vào bảng Header nếu Header chưa có
            d_amt_col = _find_col_by_norm(
                list(d_df.columns),
                ["thanh tien", "t tien", "tien ban", "tri gia", "tong tien", "doanh thu", "amount", "line total"],
            ) or _find_col_by_norm(list(d_df.columns), ["tong"], exact_only=True)

            h_has_line_amt = any(
                any(k in normalize_col_for_match(c) for k in ["thanh tien", "tong tien", "tien ban", "doanh thu", "tien hang"])
                for c in h_df.columns
            )
            if d_amt_col and not h_has_line_amt:
                # Kiểm tra xem Detail có cột trạng thái dòng riêng (예: TT dòng = đã hủy) không
                d_line_st_col = _find_col_by_norm(list(d_df.columns), ["tt dong", "trang thai dong"])
                d_valid = d_df.copy()
                if d_line_st_col and d_line_st_col in d_valid.columns:
                    uniq_d_st = d_valid[d_line_st_col].dropna().unique()
                    bad_d_st = {uv for uv in uniq_d_st if classify_status_value(uv)[0] in ("loại (huỷ)", "loại (trả)")}
                    if bad_d_st:
                        d_valid = d_valid.loc[~d_valid[d_line_st_col].isin(bad_d_st)].copy()
                d_valid["_line_amt_num"] = _parse_money_series(d_valid[d_amt_col])
                d_valid["_ord_key"] = d_valid[d_ord].astype(str).str.strip()
                ord_sums = d_valid.groupby("_ord_key")["_line_amt_num"].sum()
                h_keys = h_df[h_ord].astype(str).str.strip()
                # Đặt 'Thành tiền' trước các cột cấp đơn như 'Tổng bill' / 'Khách trả' để ưu tiên doanh thu dòng hàng
                if "Thành tiền" not in h_df.columns:
                    h_df.insert(0, "Thành tiền", h_keys.map(ord_sums).fillna(0.0))
                else:
                    h_df["Thành tiền"] = h_keys.map(ord_sums).fillna(0.0)

                # Nếu tất cả các đơn có trong Detail đều bị hủy dòng hàng trên Detail, cập nhật trạng thái Header
                if d_line_st_col and h_status_col and d_line_st_col in d_df.columns:
                    all_ords = set(d_df[d_ord].dropna().astype(str).str.strip())
                    valid_ords = set(d_valid[d_ord].dropna().astype(str).str.strip())
                    fully_cancelled_ords = all_ords - valid_ords
                    if fully_cancelled_ords:
                        mask_fc = h_df[h_ord].astype(str).str.strip().isin(fully_cancelled_ords)
                        h_df.loc[mask_fc, h_status_col] = "cancelled (đã hủy)"

            header_table.df = h_df
            header_table.columns = list(h_df.columns)
            header_table.n_rows = len(h_df)

            detail_table.df = d_df
            detail_table.columns = list(d_df.columns)
            detail_table.n_rows = len(d_df)

    # 2c. Join bảng sản phẩm (san_pham) vào bảng Detail (hoặc bảng bán hàng thiếu Tên hàng)
    if product_table is not None and product_table.df is not None and not product_table.df.empty:
        p_df = product_table.df
        p_id_col = _find_col_by_norm(
            list(p_df.columns),
            ["ma hang", "ma hh", "ma mat hang", "ma san pham", "ma sp", "id sp", "mahanghoa", "sku", "product id"],
        )
        p_name_col = _find_col_by_norm(
            list(p_df.columns),
            ["ten hang", "ten mat hang", "ten san pham", "ten sp", "ten thuoc", "product name"],
        )
        p_cat_col = _find_col_by_norm(
            list(p_df.columns),
            ["nhom hang", "loai hang", "danh muc", "nhom sp", "category"],
        )
        if p_id_col and p_name_col:
            p_join_cols = [p_name_col] + ([p_cat_col] if p_cat_col and p_cat_col != p_name_col else [])
            p_lookup = p_df[[p_id_col] + p_join_cols].drop_duplicates(subset=[p_id_col], keep="first").copy()
            p_lookup["_prod_join_key"] = p_lookup[p_id_col].astype(str).str.strip()

            for t in tables:
                if t is product_table or t.df is None or t.df.empty:
                    continue
                df = t.df
                has_prod_name = any(
                    any(k in normalize_col_for_match(c) for k in ["ten hang", "ten sp", "ten san pham", "ten mat hang", "ten mon", "san pham", "noi dung"])
                    for c in df.columns
                )
                if has_prod_name:
                    continue
                t_pid_col = _find_col_by_norm(
                    list(df.columns),
                    ["ma hang", "ma hh", "ma mat hang", "ma san pham", "ma sp", "id sp", "mahanghoa", "sku"],
                )
                if t_pid_col:
                    df_merged = df.copy()
                    df_merged["_prod_join_key"] = df_merged[t_pid_col].astype(str).str.strip()
                    cols_to_add = [c for c in p_join_cols if c not in df_merged.columns]
                    if cols_to_add:
                        df_merged = df_merged.merge(
                            p_lookup[["_prod_join_key"] + cols_to_add],
                            on="_prod_join_key",
                            how="left",
                        )
                    df_merged.drop(columns=["_prod_join_key"], inplace=True)
                    t.df = df_merged
                    t.columns = list(df_merged.columns)

            # Join bổ sung Nhóm hàng (Category) từ product_table qua Tên hàng nếu bảng giao dịch đã có Tên hàng nhưng thiếu Nhóm hàng
            if p_cat_col:
                cat_lookup = p_df[[p_name_col, p_cat_col]].dropna(subset=[p_name_col]).drop_duplicates(subset=[p_name_col], keep="first").copy()
                cat_lookup["_prod_name_key"] = cat_lookup[p_name_col].astype(str).str.strip().str.lower()
                for t in tables:
                    if t is product_table or t.df is None or t.df.empty:
                        continue
                    df = t.df
                    t_pname_col = _find_col_by_norm(
                        list(df.columns),
                        ["ten hang", "ten sp", "ten san pham", "ten mat hang", "ten mon", "san pham", "noi dung"],
                    )
                    t_pcat_col = _find_col_by_norm(list(df.columns), ["nhom hang", "loai hang", "danh muc", "nhom sp"])
                    if t_pname_col and not t_pcat_col:
                        df_with_cat = df.copy()
                        df_with_cat["_prod_name_key"] = df_with_cat[t_pname_col].astype(str).str.strip().str.lower()
                        df_with_cat = df_with_cat.merge(
                            cat_lookup[["_prod_name_key", p_cat_col]],
                            on="_prod_name_key",
                            how="left",
                        )
                        df_with_cat.drop(columns=["_prod_name_key"], inplace=True)
                        t.df = df_with_cat
                        t.columns = list(df_with_cat.columns)

    # --- 3. Gắn cột alias chuẩn tiếng Việt có dấu cho các bảng bán hàng / giao dịch ---
    max_shop_date_str: Optional[str] = None
    for t in tables:
        df = t.df
        if df is None or df.empty:
            continue
        stem_norm = normalize_col_for_match(f"{t.fixed_file_name or ''} {t.sheet_name or ''} {t.table_id or ''}")
        is_non_tx_table = any(
            k in stem_norm for k in ["ton kho", "tonkho", "the kho", "thekho", "khach hang", "khachhang", "san pham", "sanpham", "hang hoa", "hanghoa", "nhan vien", "nhanvien", "don vi tinh", "donvitinh", "quy doi", "quydoi"]
        )
        if is_non_tx_table:
            continue

        df_mod = df.copy()
        cols_low = [str(c).lower() for c in df_mod.columns]

        # 3a. Alias cột Ngày ('Ngày bán') nếu cột hiện tại không dấu (예: 'ngay_ban')
        has_accented_date = any(any(k in c for k in ["ngày", "date", "thời gian"]) for c in cols_low)
        if not has_accented_date:
            raw_date_col = _find_col_by_norm(list(df_mod.columns), ["ngay", "date", "thoi gian"])
            if raw_date_col:
                df_mod["Ngày bán"] = df_mod[raw_date_col]

        # Cập nhật max_shop_date_str từ cột ngày của bảng giao dịch
        date_col_for_max = _find_col_by_norm(list(df_mod.columns), ["ngay", "date", "thoi gian"])
        if date_col_for_max:
            try:
                from datamate.llm_execution.sandbox import clean_date as _sb_clean_date
                s_dt = _sb_clean_date(df_mod[date_col_for_max])
                if s_dt.notna().any():
                    cur_max = s_dt.max().strftime("%Y-%m-%d")
                    if max_shop_date_str is None or cur_max > max_shop_date_str:
                        max_shop_date_str = cur_max
            except Exception:
                pass

        # 3b. Alias cột Thành tiền ('Thành tiền') nếu bảng dùng tên 'Tổng', 'Amount', 'Tiền bán', 'thanh_tien', 'T.Tiền'
        has_std_amt = any(any(k in c for k in ["thành tiền", "tổng tiền", "doanh thu"]) for c in cols_low)
        if not has_std_amt:
            raw_amt_col = (
                _find_col_by_norm(list(df_mod.columns), ["thanh tien", "t tien", "tien ban", "tri gia", "tong tien", "doanh thu", "amount", "line total"])
                or _find_col_by_norm(list(df_mod.columns), ["tong"], exact_only=True)
            )
            if raw_amt_col:
                df_mod["Thành tiền"] = _parse_money_series(df_mod[raw_amt_col])
        else:
            # Nếu cột tiền đang chứa chuỗi kiểu '1,45tr', chuẩn hóa cột 'Tiền bán' / 'Thành tiền'
            for c in list(df_mod.columns):
                if normalize_col_for_match(c) in ("tien ban", "thanh tien"):
                    if df_mod[c].dtype == object and df_mod[c].astype(str).str.contains(r"\d\s*tr\b", case=False, regex=True, na=False).any():
                        df_mod[c] = _parse_money_series(df_mod[c])

        # 3c. Alias cột Trạng thái ('Trạng thái') và đặt lên đầu danh sách cột để ưu tiên trước 'TT dòng'
        st_cols_detected = detect_status_columns(df_mod)
        raw_st_col = st_cols_detected[0] if st_cols_detected else _find_col_by_norm(
            list(df_mod.columns), ["trang thai", "tinh trang", "status", "xu ly"]
        )
        if raw_st_col:
            std_st_series = _standardize_status_alias_series(df_mod[raw_st_col])
            df_mod[raw_st_col] = std_st_series
            if "Trạng thái" not in df_mod.columns:
                df_mod.insert(0, "Trạng thái", std_st_series)
            else:
                df_mod["Trạng thái"] = _standardize_status_alias_series(df_mod["Trạng thái"])

        # 3d. Alias cột Mã đơn hàng ('Mã đơn hàng') nếu dùng 'Số CT', 'Số phiếu', 'Mã GD'
        has_std_ord = any(any(k in c for k in ["mã đơn", "mã hóa đơn", "mã hđ", "order_id", "order id"]) for c in cols_low)
        if not has_std_ord:
            raw_ord_col = find_order_id_col(list(df_mod.columns))
            if raw_ord_col and "Mã đơn hàng" not in df_mod.columns:
                df_mod["Mã đơn hàng"] = df_mod[raw_ord_col]

        # 3e. Alias cột Số lượng ('Số lượng') nếu dùng 'Sluong', 'S.L', 'SL', 'Qty'
        has_std_qty = any("số lượng" in c for c in cols_low)
        if not has_std_qty:
            raw_qty_col = _find_col_by_norm(
                list(df_mod.columns),
                ["so luong", "sluong", "s l", "qty", "quantity"],
            ) or _find_col_by_norm(list(df_mod.columns), ["sl"], exact_only=True)
            if raw_qty_col and "Số lượng" not in df_mod.columns:
                df_mod["Số lượng"] = df_mod[raw_qty_col]

        # 3f. Alias cột Tên hàng ('Tên hàng') nếu dùng 'Nội dung', 'Tên món', 'Sản phẩm', 'Tên mặt hàng'
        has_std_item = any(any(k in c for k in ["tên hàng", "tên sản phẩm", "tên sp"]) for c in cols_low)
        if not has_std_item:
            raw_item_col = _find_col_by_norm(
                list(df_mod.columns),
                ["ten hang", "ten mat hang", "ten san pham", "ten sp", "ten mon", "san pham", "mat hang", "noi dung", "ten thuoc"],
            )
            if raw_item_col and "Tên hàng" not in df_mod.columns:
                df_mod["Tên hàng"] = df_mod[raw_item_col]

        t.df = df_mod
        t.columns = list(df_mod.columns)
        t.n_rows = len(df_mod)

    # --- 4. Làm giàu bảng tồn kho snapshot (BaoCaoTonKho) với 'Ngày' và 'Quy cách' ---
    unit_conv_table: Optional[TableInfo] = None
    for t in tables:
        if t.df is None or t.df.empty:
            continue
        t_full_norm = normalize_col_for_match(f"{t.fixed_file_name or ''} {t.sheet_name or ''} {t.table_id or ''}")
        if any(k in t_full_norm for k in ["don vi tinh", "donvitinh", "quy doi", "quydoi"]):
            unit_conv_table = t
            break

    for t in tables:
        df = t.df
        if df is None or df.empty:
            continue
        t_full_norm = normalize_col_for_match(f"{t.fixed_file_name or ''} {t.sheet_name or ''} {t.table_id or ''}")
        is_inv_snapshot = any(k in t_full_norm for k in ["bao cao ton kho", "baocaotonkho", "ton kho", "tonkho"]) and not any(
            k in t_full_norm for k in ["the kho", "thekho"]
        )
        if not is_inv_snapshot:
            continue

        df_inv = df.copy()
        has_date_col = any(any(k in normalize_col_for_match(c) for k in ["ngay", "date"]) for c in df_inv.columns)
        if not has_date_col and max_shop_date_str:
            df_inv["Ngày"] = max_shop_date_str

        has_qc_col = any(any(k in normalize_col_for_match(c) for k in ["quy cach", "quy doi", "he so"]) for c in df_inv.columns)
        if not has_qc_col and unit_conv_table is not None and unit_conv_table.df is not None:
            u_df = unit_conv_table.df
            u_item_col = _find_col_by_norm(list(u_df.columns), ["ma hang", "ma sp", "ten hang", "san pham"])
            u_factor_col = _find_col_by_norm(list(u_df.columns), ["quy doi", "he so", "quy cach", "ty le"])
            inv_item_col = _find_col_by_norm(list(df_inv.columns), ["ma hang", "ma sp", "ten hang", "san pham"])
            inv_dvt_col = _find_col_by_norm(list(df_inv.columns), ["dvt", "don vi"])

            if u_item_col and u_factor_col and inv_item_col:
                qc_map: dict[str, str] = {}
                for _, r in u_df.iterrows():
                    ik = str(r[u_item_col]).strip()
                    fv = r[u_factor_col]
                    if not ik or pd.isna(fv):
                        continue
                    try:
                        f_int = int(float(fv))
                    except Exception:
                        continue
                    if f_int > 1:
                        # Đặt số hệ số quy đổi đứng đầu (vd: '6 cái/hộp') để regex r'\d+' lấy đúng hệ số quy đổi
                        qc_map[ik] = f"{f_int}"

                if qc_map:
                    qc_series = df_inv[inv_item_col].astype(str).str.strip().map(lambda x: qc_map.get(x, "1"))
                    # Đặt cột 'Quy cách' đứng trước cột 'ĐVT' để vòng lặp tìm cột quy cách khớp 'Quy cách' trước 'ĐVT'
                    if inv_dvt_col and inv_dvt_col in df_inv.columns:
                        dvt_idx = list(df_inv.columns).index(inv_dvt_col)
                        df_inv.insert(dvt_idx, "Quy cách", qc_series)
                    else:
                        df_inv["Quy cách"] = qc_series

        # Đảm bảo cột 'Tên hàng' đứng trước 'Mã hàng' trong bảng tồn kho để biểu thức tìm cột có từ khóa 'hàng' khớp 'Tên hàng' trước
        if "Tên hàng" in df_inv.columns and "Mã hàng" in df_inv.columns:
            cols_inv = list(df_inv.columns)
            if cols_inv.index("Mã hàng") < cols_inv.index("Tên hàng"):
                cols_inv.remove("Tên hàng")
                cols_inv.insert(cols_inv.index("Mã hàng"), "Tên hàng")
                df_inv = df_inv[cols_inv]

        t.df = df_inv
        t.columns = list(df_inv.columns)
        t.n_rows = len(df_inv)

    return BusinessData(
        business_id=business.business_id,
        tables=tables,
        readme_text=business.readme_text,
        errors=list(business.errors),
    )


def clean_business(business: BusinessData, filter_status: bool = False) -> BusinessData:
    """Làm sạch toàn bộ các bảng của BusinessData theo Quy tắc 8, dựng Unified Relational View (Bước 3) và tùy chọn Quy tắc 1."""
    cleaned_tables = [clean_table(t, filter_status=False) for t in business.tables]
    cleaned_biz = BusinessData(
        business_id=business.business_id,
        tables=cleaned_tables,
        readme_text=business.readme_text,
        errors=list(business.errors),
    )
    cleaned_biz = build_unified_relational_views(cleaned_biz)
    if filter_status:
        cleaned_biz = filter_business_order_status(cleaned_biz)
    return cleaned_biz
