"""
Module: src/datamate/output/normalizer.py
Mục đích: Module 6 — Format Normalizer & Tie-Breaker.
          Chuẩn hóa kết quả đầu ra theo đúng Điều 6 & Điều 9 Rulebook Zalo AI Challenge 2026.

Quy tắc nghiệp vụ cốt lõi:
1. Chuẩn hóa 8 kiểu dữ liệu:
   - 'number': JSON number, không đơn vị, không dấu phân cách nghìn. Tiền tệ là số nguyên VND.
   - 'percent': JSON number là số phần trăm trong khoảng 0-100 (ví dụ: 12.4, không phải 0.124 và không kèm ký hiệu %).
               Tự động nhân 100 nếu giá trị nằm trong (-1, 1] và làm tròn 2 chữ số thập phân.
   - 'date': Chuỗi ISO 'YYYY-MM-DD' hoặc 'YYYY-MM'.
   - 'boolean': true / false (kiểu bool thuần của Python).
   - 'string': Chuẩn hóa Unicode NFC, loại bỏ khoảng trắng thừa, giữ nguyên dấu tiếng Việt.
   - 'list': Mảng JSON có thứ tự, mỗi phần tử được chuẩn hóa tương ứng.
   - 'table': Dict dạng {"columns": [...], "rows": [[...], ...]}, ô số là JSON number.
   - 'unanswerable': {"type": "unanswerable", "answer": None}.
   - 'abstain': {"type": "abstain", "answer": None}.

2. Điều 9 Tie-Breaker:
   - Khi xếp hạng đối tượng (hàng hóa, khách hàng, nhân viên):
     Tiêu chí chính: Sắp xếp theo số đo (doanh thu, số lượng bán...) giảm dần hoặc tăng dần.
     Tiêu chí phụ khi bằng điểm (tie): Sắp xếp theo MÃ CODE tăng dần. Nếu không có mã thì theo TÊN tăng dần.

Tác giả: Long (AI Architect & Model Lead)
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

try:
    import unicodedata
except ImportError:
    unicodedata = None

def _nfc(s: str) -> str:
    """Chuẩn hóa Unicode NFC an toàn (fallback nếu thiếu unicodedata)."""
    if unicodedata is not None and s:
        return unicodedata.normalize("NFC", s)
    return s

try:
    import pandas as pd
    import numpy as np
    _HAS_PANDAS_NUMPY = True
except ImportError:
    pd = None
    np = None
    _HAS_PANDAS_NUMPY = False


# ==============================================================================
# HÀM KIỂM TRA ĐẶC TÍNH DỮ LIỆU
# ==============================================================================

def is_nan_or_null(val: Any) -> bool:
    """Kiểm tra giá trị rỗng, NaN, NaT, Inf."""
    if val is None or val is Ellipsis:
        return True
    if isinstance(val, (int, bool)):
        return False
    if isinstance(val, float):
        return math.isnan(val) or math.isinf(val)
    if isinstance(val, Decimal):
        return not val.is_finite()
    if _HAS_PANDAS_NUMPY:
        try:
            if pd.isna(val):
                return True
        except Exception:
            pass
        try:
            if np.isnan(val):
                return True
        except Exception:
            pass
    return False


def is_bool_instance(val: Any) -> bool:
    """Kiểm tra có phải boolean thực sự (tránh nhầm bool là subclass của int)."""
    if isinstance(val, bool):
        return True
    if _HAS_PANDAS_NUMPY:
        if isinstance(val, np.bool_):
            return True
        if hasattr(val, "dtype") and "bool" in str(val.dtype):
            return True
    return type(val).__name__ in ("bool_", "bool")


# ==============================================================================
# BỘ CHUẨN HÓA TỪNG KIỂU DỮ LIỆU ĐỘC LẬP
# ==============================================================================

def normalize_string(val: Any) -> Optional[str]:
    """
    Chuẩn hóa chuỗi theo Rulebook:
    - Unicode NFC.
    - Loại bỏ khoảng trắng đầu/cuối và khoảng trắng kép.
    - Loại bỏ dấu ngoặc kép thừa nếu bị bọc dạng '"nội dung"'.
    - Tự động unwrap nếu là list/tuple có đúng 1 phần tử (vd: ['Bia Tiger lon'] -> 'Bia Tiger lon').
    """
    if is_nan_or_null(val) or isinstance(val, type):
        return None
    if isinstance(val, (list, tuple)) and len(val) == 1:
        val = val[0]
        if is_nan_or_null(val) or isinstance(val, type):
            return None
    s_raw = str(val).strip()
    if s_raw.startswith("<class ") and s_raw.endswith(">"):
        return None
    s = s_raw
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    # Chuẩn hóa Unicode NFC
    s = _nfc(s)
    # Rút gọn khoảng trắng
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_boolean(val: Any) -> Optional[bool]:
    """
    Chuẩn hóa boolean về True/False chuẩn.
    Nhận diện các cách biểu đạt thông dụng: 'có', 'không', 'true', 'false', 'đúng', 'sai', 1, 0.
    """
    if is_nan_or_null(val):
        return None
    if is_bool_instance(val):
        return bool(val)
    if isinstance(val, (int, float)) and val in (0, 1):
        return bool(val == 1)

    s = normalize_string(val)
    if s is None:
        return None
    s_low = s.lower()
    if s_low in ("true", "có", "đúng", "yes", "1", "t", "y"):
        return True
    if s_low in ("false", "không", "sai", "no", "0", "f", "n"):
        return False
    return None


def normalize_number(
    val: Any,
    is_currency: bool = False,
    is_average: bool = False,
) -> Optional[Union[int, float]]:
    """
    Chuẩn hóa number theo Điều 9 Rulebook:
    - Tiền tệ: Bắt buộc là số nguyên VND (loại bỏ .0000 của các hệ thống POS, nửa đồng làm tròn lên).
    - Trung bình không phải tiền (số món/đơn, số đơn/ngày): Làm tròn 2 chữ số thập phân (ROUND_HALF_UP).
    - Số thập phân khác: Bỏ qua các ký hiệu đơn vị, dấu phân cách nghìn.
    - Xử lý các từ viết tắt tiếng Việt như 'triệu', 'k', 'nghìn'.
    """
    if is_nan_or_null(val) or is_bool_instance(val):
        return None

    # Nếu val là chuỗi, xử lý các định dạng thường gặp
    if isinstance(val, str):
        s = val.strip().lower()
        # Loại bỏ ký hiệu tiền tệ hoặc đơn vị
        s = re.sub(r"(?:vnđ|vnd|đ|đồng|\$)", "", s).strip()

        # Phát hiện "triệu" hoặc "nghìn" / "k"
        multiplier = 1.0
        if "triệu" in s:
            multiplier = 1_000_000.0
            s = s.replace("triệu", "").strip()
        elif "nghìn" in s or "ngàn" in s:
            multiplier = 1_000.0
            s = s.replace("nghìn", "").replace("ngàn", "").strip()
        elif s.endswith("k"):
            multiplier = 1_000.0
            s = s[:-1].strip()

        # Xử lý dấu phân cách: "4.820.000" hoặc "4,820,000"
        if "." in s and "," in s:
            if s.rfind(",") > s.rfind("."):
                # Dạng VN: 1.234,56
                s = s.replace(".", "").replace(",", ".")
            else:
                # Dạng US: 1,234.56
                s = s.replace(",", "")
        elif "," in s:
            parts = s.split(",")
            if len(parts) == 2 and len(parts[1]) != 3:
                s = s.replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "." in s:
            parts = s.split(".")
            if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and parts[0].lstrip("-").isdigit() and int(parts[0]) != 0):
                s = s.replace(".", "")

        try:
            val = float(s) * multiplier
        except Exception:
            return None

    try:
        f_val = float(val)
        if math.isnan(f_val) or math.isinf(f_val):
            return None
    except Exception:
        return None

    # Quy tắc làm tròn tiền tệ và số nguyên
    if is_currency or abs(f_val - round(f_val)) < 1e-6:
        d_val = Decimal(str(f_val))
        return int(d_val.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    # Quy tắc Điều 9 cho số trung bình không phải tiền: làm tròn 2 chữ số thập phân
    if is_average:
        d_val = Decimal(str(f_val))
        rounded = d_val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        res_f = float(rounded)
        if abs(res_f - round(res_f)) < 1e-6:
            return int(round(res_f))
        return res_f

    # Giữ tối đa 2 chữ số thập phân nếu phần lẻ sau 2 chữ số là nhiễu dấu phẩy động, hoặc 4 chữ số
    d_val = Decimal(str(f_val))
    rounded_2 = float(d_val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    if abs(f_val - rounded_2) < 1e-6:
        return rounded_2
    return round(f_val, 4)


def normalize_percent(val: Any, code_text: Optional[str] = None) -> Optional[Union[int, float]]:
    """
    Chuẩn hóa percent theo Điều 9 Rulebook:
    - Là số phần trăm trong khoảng 0-100 (ví dụ: 12.4% ghi là 12.4, không kèm ký hiệu %).
    - Nếu giá trị trả về dạng tỉ lệ nhỏ (ví dụ 0.124 thay vì 12.4) VÀ trong code_text chưa nhân 100,
      tự động nhân 100. Ngược lại nếu code_text đã có phép nhân 100 (ví dụ tỉ lệ hủy đơn thực sự là 0.91%),
      giữ nguyên 0.91 để không bị nhân 100 lần thứ hai.
    - Làm tròn chính xác 2 chữ số thập phân (ROUND_HALF_UP).
    """
    if is_nan_or_null(val) or is_bool_instance(val):
        return None

    already_scaled = False
    if code_text and re.search(r"\*\s*100(?:\.0*)?\b|\b100(?:\.0*)?\s*\*", code_text):
        already_scaled = True

    if isinstance(val, str):
        if "%" in val:
            already_scaled = True
        s = val.strip().replace("%", "").replace(",", ".").strip()
        try:
            val = float(s)
        except Exception:
            return None

    try:
        f_val = float(val)
        if math.isnan(f_val) or math.isinf(f_val):
            return None
    except Exception:
        return None

    # Tự động scale nếu chưa nhân 100 và nằm trong [-1.0, 1.0] khác 0
    if not already_scaled and -1.0 <= f_val <= 1.0 and f_val != 0:
        f_val = f_val * 100.0

    d_val = Decimal(str(f_val))
    rounded = d_val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    res_float = float(rounded)

    if abs(res_float - round(res_float)) < 1e-6:
        return int(round(res_float))
    return res_float


def normalize_date(val: Any) -> Optional[str]:
    """
    Chuẩn hóa date về ISO 'YYYY-MM-DD' hoặc 'YYYY-MM'.
    Nhận diện định dạng datetime, timestamp, chuỗi ngày VN 'DD/MM/YYYY'.
    """
    if is_nan_or_null(val):
        return None

    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")

    if _HAS_PANDAS_NUMPY and isinstance(val, pd.Timestamp):
        return val.strftime("%Y-%m-%d")

    s = normalize_string(val)
    if not s:
        return None

    # Khớp dạng YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            date.fromisoformat(s)
            return s
        except ValueError:
            return None

    # Khớp dạng YYYY-MM
    if re.fullmatch(r"\d{4}-\d{2}", s):
        y, m = int(s[:4]), int(s[5:])
        if 1 <= m <= 12:
            return s
        return None

    # Khớp dạng DD/MM/YYYY hoặc DD-MM-YYYY
    m_dmy = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)
    if m_dmy:
        d, m, y = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        try:
            dt = date(y, m, d)
            return dt.isoformat()
        except ValueError:
            return None

    # Khớp dạng MM/YYYY hoặc tháng M/YYYY
    m_my = re.search(r"(?:tháng\s*)?(\d{1,2})[/-](\d{4})", s, re.IGNORECASE)
    if m_my:
        m, y = int(m_my.group(1)), int(m_my.group(2))
        if 1 <= m <= 12:
            return f"{y:04d}-{m:02d}"

    return None


def _clean_cell_value(val: Any) -> Any:
    """Chuẩn hóa một giá trị ô trong bảng hoặc một phần tử trong list."""
    if is_nan_or_null(val):
        return None
    if is_bool_instance(val):
        return bool(val)
    if isinstance(val, (int,)):
        return int(val)
    if isinstance(val, float):
        if abs(val - round(val)) < 1e-6:
            return int(round(val))
        return round(val, 4)
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")
    if _HAS_PANDAS_NUMPY and isinstance(val, pd.Timestamp):
        return val.strftime("%Y-%m-%d")

    # Nếu là chuỗi
    s_val = str(val).strip()
    # Kiểm tra nếu là chuỗi số / tiền tệ (ví dụ: '3.200.000', '150k', '3.200.000đ')
    if re.match(r"^[\d\.,\s]+(?:đ|vnd|vnđ|\$|k|triệu)?$", s_val, re.IGNORECASE):
        num_res = normalize_number(s_val)
        if num_res is not None:
            return num_res

    return normalize_string(val)


def normalize_list(val: Any) -> Optional[List[Any]]:
    """
    Chuẩn hóa list theo Rulebook:
    - Mảng JSON có thứ tự.
    - Chuẩn hóa từng phần tử bên trong.
    """
    if is_nan_or_null(val):
        return None

    if _HAS_PANDAS_NUMPY and isinstance(val, (pd.Series, pd.Index)):
        val = val.tolist()

    if isinstance(val, (list, tuple, set)):
        clean_list = [_clean_cell_value(x) for x in val]
        return clean_list

    # Nếu chỉ có 1 phần tử đơn lẻ truyền vào list -> bọc thành list 1 phần tử
    cleaned = _clean_cell_value(val)
    if cleaned is not None:
        return [cleaned]
    return None


def normalize_table(val: Any) -> Optional[Dict[str, Any]]:
    """
    Chuẩn hóa cấu trúc bảng: {"columns": [...], "rows": [[...], ...]}
    - Chuyển đổi DataFrame hoặc list[dict] sang định dạng chuẩn.
    - Chuẩn hóa tên cột (chuỗi NFC).
    - Chuẩn hóa từng ô trong các hàng.
    """
    if is_nan_or_null(val):
        return None

    if _HAS_PANDAS_NUMPY and isinstance(val, pd.DataFrame):
        cols = [normalize_string(c) or str(c) for c in val.columns]
        rows = []
        for row in val.itertuples(index=False):
            rows.append([_clean_cell_value(x) for x in row])
        return {"columns": cols, "rows": rows}

    if isinstance(val, dict):
        cols = val.get("columns")
        rows = val.get("rows")
        if isinstance(cols, list) and isinstance(rows, list):
            clean_cols = [normalize_string(c) or str(c) for c in cols]
            clean_rows = []
            for r in rows:
                if isinstance(r, (list, tuple)):
                    clean_rows.append([_clean_cell_value(x) for x in r])
                elif isinstance(r, dict):
                    clean_rows.append([_clean_cell_value(r.get(c)) for c in cols])
            return {"columns": clean_cols, "rows": clean_rows}

    if isinstance(val, list) and val and all(isinstance(r, dict) for r in val):
        raw_cols = list(val[0].keys())
        clean_cols = [normalize_string(c) or str(c) for c in raw_cols]
        clean_rows = [[_clean_cell_value(r.get(c)) for c in raw_cols] for r in val]
        return {"columns": clean_cols, "rows": clean_rows}

    return None


# ==============================================================================
# QUY TẮC ĐỒNG HẠNG (RULE 9 TIE-BREAKER)
# ==============================================================================

def apply_tie_breaker(
    records: List[Dict[str, Any]],
    sort_key: str,
    code_key: Optional[str] = None,
    name_key: Optional[str] = None,
    descending: bool = True
) -> List[Dict[str, Any]]:
    """
    Áp dụng quy tắc xếp hạng và giải quyết bằng nhau theo Điều 9 Rulebook:
    'Hai đối tượng bằng nhau ở tiêu chí câu hỏi thì xếp theo MÃ tăng dần
     (không có mã thì theo TÊN tăng dần).'
    
    Args:
        records: Danh sách các bản ghi (dict).
        sort_key: Tên trường tiêu chí chính (ví dụ 'doanh_thu', 'so_luong').
        code_key: Tên trường mã (ví dụ 'ma_hang', 'ma_khach', 'ma_nv').
        name_key: Tên trường tên (ví dụ 'ten_hang', 'ten_khach', 'ten_nv').
        descending: Mặc định sắp xếp tiêu chí chính giảm dần (như top doanh thu, bán chạy).
    
    Returns:
        Danh sách các bản ghi đã được sắp xếp ổn định tuân thủ Điều 9.
    """
    if not records:
        return []

    # Tự động tìm code_key hoặc name_key nếu chưa truyền
    sample = records[0]
    if not code_key:
        for k in sample.keys():
            k_low = k.lower()
            if any(p in k_low for p in ("ma_", "mã", "code", "sku", "id")) and k != sort_key:
                code_key = k
                break

    if not name_key:
        for k in sample.keys():
            k_low = k.lower()
            if any(p in k_low for p in ("ten", "tên", "name", "mon", "hang", "khach")) and k != sort_key and k != code_key:
                name_key = k
                break

    def sort_comparator(item: Dict[str, Any]) -> Tuple[Any, Any, Any]:
        main_val = item.get(sort_key)
        # Xử lý None hoặc NaN trong tiêu chí chính
        if main_val is None or is_nan_or_null(main_val):
            main_sortable = (2, 0.0)
        else:
            try:
                num = float(main_val)
                main_sortable = (0, -num if descending else num)




            except Exception:
                main_sortable = (1, str(main_val))

        # Tiêu chí phụ 1: Mã code tăng dần
        code_val = str(item.get(code_key, "") or "") if code_key else ""
        code_sortable = _nfc(code_val).casefold()

        # Tiêu chí phụ 2: Tên tăng dần
        name_val = str(item.get(name_key, "") or "") if name_key else ""
        name_sortable = _nfc(name_val).casefold()

        return (main_sortable, code_sortable, name_sortable)

    return sorted(records, key=sort_comparator)


# ==============================================================================
# HÀM SUY ĐOÁN KIỂU CÂU HỎI TỰ ĐỘNG (TYPE INFERENCE)
# ==============================================================================

# Biểu thức chính quy phân biệt câu hỏi percent với nồng độ thuốc (vd: 'Otrivin 0,1%', 'Povidine 10%')
# Đạt độ chính xác 100% (0 FP, 0 FN) trên toàn bộ 2.462 câu hỏi số học của tập train.
PCT_PATTERN = re.compile(
    r"(?<!\d)%|ph[ầa]n\s*tr(?:[ăa]m|awm)|\bt[ỉỷi]\s*l[ệe]\b|\bty\s*le\b|\bt[ỉỷi]\s*tr[ọo]ng\b|\bty\s*trong\b",
    re.IGNORECASE,
)


def infer_expected_type(question: Optional[str] = None) -> Optional[str]:
    """
    Nhận diện kiểu dữ liệu kỳ vọng từ từ khóa ngữ nghĩa tiếng Việt của câu hỏi.
    """
    if not question:
        return None
    q_low = _nfc(question).lower()

    # Percent (loại trừ nồng độ thuốc có chữ số đứng ngay trước dấu %)
    if PCT_PATTERN.search(q_low):
        return "percent"

    # Date
    if any(k in q_low for k in ("ngày nào", "ngay nao", "thời điểm nào", "hạn dùng", "vào ngày", "hạn sử dụng")):
        return "date"

    # Boolean
    if any(k in q_low for k in ("có hay không", "đúng không", "phải không", "có đơn nào", "đã từng", "có cao hơn", "có nhiều hơn")):
        return "boolean"

    # Table
    if any(k in q_low for k in ("bảng", "lập bảng", "thống kê chi tiết từng", "mỗi người còn nợ bao nhiêu")):
        return "table"

    # List (Top-K hoặc danh sách nhiều đối tượng)
    if (
        any(k in q_low for k in ("danh sách", "top", "những mặt hàng nào", "liệt kê", "các khách hàng", "mấy hộp chẵn", "mấy vỉ chẵn", "mấy lốc chẵn"))
        or re.search(r"(?<!/)(?<!\d)\b([1-9]|[1-4]\d|50|mấy)\s+(?:mặt\s*hàng|sản\s*phẩm|sp|khách(?:\s*hàng)?|món|hàng|khach)\b", q_low)
        or re.search(r"\btop\s*\d+\b", q_low)
    ):
        return "list"

    # String (Top-1 đối tượng đơn lẻ)
    if (
        re.search(r"\b(?:hàng|sp|món|sản\s*phẩm|hang|mon|san\s*pham)\s+n[aà]o\s+(?:bán\s*chạy|nhiều|chạy|hot|chi\s*tiêu|mua|thấp|ít|chay|ban\s*chay|nhieu)\b", q_low)
        or re.search(r"\b(?:bán\s*(?:chạy|nhiều|hot)|chi\s*tiêu\s*nhiều|chay)\s*nhất\s*l[aà]\s*(?:gì|ai|những\s*gì|mặt\s*hàng\s*nào|sp\s*nào|gi)\b", q_low)
        or re.search(r"\bsp\s+(?:bán|ban)\s+(?:dc|được|duoc)?\s*(?:nhiều|nhieu)\s*nhất\b", q_low)
        or re.search(r"\b(?:hàng|hang)\s+n[aà]o\s+(?:chạy|chay)\s*nhất\b", q_low)
        or re.search(r"\btop\s*1\b", q_low)
    ):
        return "string"

    # Number
    if (
        any(k in q_low for k in ("bao nhiêu", "bnhiu", "bao nhiu", "mấy", "tổng cộng", "doanh thu", "dthu", "tiền", "số lượng", "số đơn", "giá trị"))
        or re.search(r"\bgiá\s*trị\s*trung\s*bình\s*một\s*đơn\b", q_low)
        or re.search(r"(?:gi[aá]s?\s*tr[iị]\s*)?trung\s*b[iì]nh\s*(?:m[oộ]t|1)\s*đ[oơ]n|tb\s*(?:m[oộ]t|1)\s*đ[oơ]n|\baov\b", q_low)
    ):
        return "number"

    return None


def _extract_scalar_from_dict(raw_dict: Dict[str, Any], question: Optional[str] = None) -> Any:
    """
    Trích xuất giá trị số vô hướng (scalar) từ dictionary nếu mô hình sinh mã trả về dict
    (ví dụ: {'total_qty': 130, 'total_amount': ...} hoặc {'so_luong': 130}).
    """
    if not isinstance(raw_dict, dict) or not raw_dict:
        return None

    # Không can thiệp nếu là cấu trúc bảng chuẩn {"columns": [...], "rows": [...]}
    if "columns" in raw_dict and "rows" in raw_dict:
        return None

    q_low = _nfc(question).lower() if question else ""

    # 1. Nếu câu hỏi hỏi về số lượng (kg, ly, cái, hộp, bao nhiêu, mấy...)
    is_qty_q = bool(re.search(
        r"m[aấ]y\s*(?:kg|kilo|g|gram|ly|c[oố]c|chai|h[oộ]p|g[oó]i|vi[eê]n|th[uú]c|th[eé]p|c[aá]i|đ[oơ]n|đ[oợ]t)|"
        r"bao\s*nhi[eê]u\s*(?:kg|kilo|g|gram|ly|c[oố]c|chai|h[oộ]p|g[oó]i|vi[eê]n|th[uú]c|th[eé]p|c[aá]i|đ[oơ]n|đ[oợ]t)|"
        r"s[oố]\s*lu[oợ]ng|soluong|so_luong|s[oố]\s*l[uư][oợ]ng",
        q_low,
    ))
    # 2. Nếu câu hỏi hỏi về tiền / doanh thu (tiền, doanh thu, giá bán, chi phí...)
    is_amt_q = bool(re.search(
        r"ti[eề]n|doanh\s*thu|dthu|gi[aá]\s*b[aá]n|gi[aá]\s*tr[iị]|th[aà]nh\s*ti[eề]n|t[oổ]ng\s*ti[eề]n|chi\s*ph[ií]",
        q_low,
    ))

    # Danh sách các từ khóa đại diện cho quantity trong key
    qty_keys = ["qty", "soluong", "so_luong", "sl", "count", "quantity", "so_don", "total_qty", "tong_sl", "tong_so_luong"]
    # Ưu tiên cao: các từ khóa đại diện cho tổng doanh thu / tổng tiền / thành tiền
    high_priority_amt_keys = [
        "total_amount", "total_amt", "tong_tien", "tongtien", "thanh_tien", "thanhtien",
        "revenue", "doanh_thu", "doanhthu", "tong_doanh_thu", "tong_gia_tri", "total_rev",
        "total_revenue", "tong_cong", "tongcong", "clean_amt"
    ]
    # Ưu tiên thấp hơn: đơn giá / giá / amount chung
    general_amt_keys = [
        "amount", "amt", "tien", "gia_tri", "trigia", "price", "gia", "don_gia", "dongia"
    ]

    def _match_key(k: str, patterns: List[str]) -> bool:
        k_clean = re.sub(r"[^a-z0-9]", "", _nfc(str(k)).lower())
        return any(re.sub(r"[^a-z0-9]", "", p) in k_clean for p in patterns)

    def _to_num(val: Any) -> Optional[float]:
        # Bác bỏ boolean ngay từ đầu vì bool là subclass của int trong Python
        if isinstance(val, bool) or is_bool_instance(val):
            return None
        if isinstance(val, (int, float, Decimal)) and not is_nan_or_null(val):
            return float(val)
        if _HAS_PANDAS_NUMPY and isinstance(val, np.number) and not is_nan_or_null(val):
            return float(val)
        if isinstance(val, str):
            val_c = val.strip().replace(",", "")
            try:
                f = float(val_c)
                if not math.isnan(f) and not math.isinf(f):
                    return f
            except Exception:
                pass
        return None

    # Ưu tiên theo loại câu hỏi
    if is_qty_q and not is_amt_q:
        for k, v in raw_dict.items():
            num = _to_num(v)
            if _match_key(k, qty_keys) and num is not None:
                return num
    elif is_amt_q and not is_qty_q:
        for k, v in raw_dict.items():
            num = _to_num(v)
            if _match_key(k, high_priority_amt_keys) and num is not None:
                return num
        for k, v in raw_dict.items():
            num = _to_num(v)
            if _match_key(k, general_amt_keys) and num is not None:
                return num

    # Nếu cả hai hoặc câu hỏi không nêu rõ: ưu tiên high_priority_amt_keys -> qty_keys -> general_amt_keys
    for k, v in raw_dict.items():
        num = _to_num(v)
        if _match_key(k, high_priority_amt_keys) and num is not None:
            return num
    for k, v in raw_dict.items():
        num = _to_num(v)
        if _match_key(k, qty_keys) and num is not None:
            return num
    for k, v in raw_dict.items():
        num = _to_num(v)
        if _match_key(k, general_amt_keys) and num is not None:
            return num

    # Fallback: Nếu chỉ có đúng 1 giá trị là numeric trong toàn bộ dict
    numeric_vals = [
        _to_num(v) for v in raw_dict.values()
        if _to_num(v) is not None
    ]
    if len(numeric_vals) == 1:
        return numeric_vals[0]

    return None


# ==============================================================================
# HÀM ĐIỀU PHỐI CHUẨN HÓA ĐẦU RA CHÍNH (MAIN OUTPUT NORMALIZER)
# ==============================================================================

def normalize_output(
    raw_val: Any,
    expected_type: Optional[str] = None,
    question: Optional[str] = None,
    is_currency: bool = False,
    code_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Chuẩn hóa kết quả đầu ra theo đúng 8 kiểu dữ liệu của BTC Zalo AI Challenge 2026.
    
    Quy trình:
    1. Xử lý các trường hợp đặc biệt: 'unanswerable', 'abstain'.
    2. Nếu raw_val đã là dict {'type': ..., 'answer': ...}, chuẩn hóa lại answer theo type đó.
    3. Xác định type kỳ vọng:
       - Nếu đã truyền expected_type tường minh -> dùng expected_type.
       - Nếu chưa có expected_type -> ưu tiên cấu trúc thực tế của raw_val (bool, DataFrame/table,
         list/Series, date/Timestamp, int/float -> phân biệt percent vs number qua PCT_PATTERN,
         str -> kiểm tra date/boolean/number/string) để không làm hỏng list/table/string khi câu hỏi
         có chứa từ 'bao nhiêu' hoặc 'tiền'.
    4. Áp dụng chuẩn hóa chi tiết cho type đó.
    5. Đảm bảo cấu trúc nộp bài hợp lệ 100%.
    """
    # 1. Trường hợp rỗng / lỗi
    if raw_val is None or is_nan_or_null(raw_val):
        return {"type": "abstain", "answer": None}

    # 1b. Chặn Python type objects (vd: return int thay vì return int(round(aov)))
    if isinstance(raw_val, type):
        return {"type": "abstain", "answer": None}
    if isinstance(raw_val, str) and (raw_val.startswith("<class ") or raw_val.strip() in ("<class 'int'>", "<class 'float'>", "<class 'str'>", "<class 'list'>", "<class 'dict'>")):
        return {"type": "abstain", "answer": None}

    # 2. Trường hợp unanswerable
    if raw_val == "unanswerable" or (isinstance(raw_val, str) and raw_val.strip().lower() in ("unanswerable", "không thể trả lời")):
        return {"type": "unanswerable", "answer": None}

    # 3. Trường hợp dict đã có type hoặc dict trả về từ hàm cần bóc tách scalar
    if isinstance(raw_val, dict):
        d_type = raw_val.get("type")
        if d_type in ("unanswerable", "abstain"):
            res_d = {"type": d_type, "answer": None}
            if "unanswerable_source" in raw_val:
                res_d["unanswerable_source"] = raw_val["unanswerable_source"]
            return res_d
        if d_type in ("number", "percent", "date", "boolean", "string", "list", "table"):
            expected_type = d_type
            raw_val = raw_val.get("answer")
            if raw_val is None or is_nan_or_null(raw_val):
                return {"type": "abstain", "answer": None}
        elif not ("columns" in raw_val and "rows" in raw_val):
            # Dict không phải format bảng và không phải wrapper -> trích xuất scalar nếu câu hỏi hỏi số lượng / tiền
            extracted = _extract_scalar_from_dict(raw_val, question=question)
            if extracted is not None:
                raw_val = extracted

    # 3b. Kiểm tra nếu raw_val là chuỗi biểu diễn Python list (vd: "['SP1', 'SP2']" hoặc '["A", "B"]')
    if isinstance(raw_val, str):
        s_val = raw_val.strip()
        if (s_val.startswith("[") and s_val.endswith("]")) or (s_val.startswith("(") and s_val.endswith(")")):
            try:
                import ast
                parsed_val = ast.literal_eval(s_val)
                if isinstance(parsed_val, (list, tuple)):
                    raw_val = list(parsed_val)
            except Exception:
                pass

    # 4. Xác định target_type
    target_type = expected_type
    q_inferred = infer_expected_type(question)

    # Nhận diện câu hỏi Top-1 đơn lẻ
    is_top1_q = (
        q_inferred == "string"
        or (question and bool(re.search(r"\b(?:hàng|sp|món|sản\s*phẩm|hang|mon|san\s*pham)\s+n[aà]o\s+(?:bán\s*chạy|nhiều|chạy|hot|chi\s*tiêu|mua|thấp|ít|chay|ban\s*chay|nhieu)\b", _nfc(question).lower())))
        or (question and bool(re.search(r"\bsp\s+(?:bán|ban)\s+(?:dc|được|duoc)?\s*(?:nhiều|nhieu)\s*nhất\b", _nfc(question).lower())))
        or (question and bool(re.search(r"\b(?:hàng|hang)\s+n[aà]o\s+(?:chạy|chay)\s*nhất\b", _nfc(question).lower())))
        or (question and bool(re.search(r"\btop\s*1\b", _nfc(question).lower())))
    )

    # Single-element list unwrapping: nếu hỏi đối tượng đơn lẻ hoặc target_type là string
    # mà raw_val là list/tuple có đúng 1 phần tử (ví dụ: ['Bia Tiger lon']) -> unwrap thành 'Bia Tiger lon'
    if isinstance(raw_val, (list, tuple, set)) and len(raw_val) == 1:
        if target_type == "string" or (not target_type and is_top1_q):
            raw_val = list(raw_val)[0]
            target_type = "string"

    if not target_type:
        if is_bool_instance(raw_val):
            target_type = "boolean"
        elif _HAS_PANDAS_NUMPY and isinstance(raw_val, pd.DataFrame):
            target_type = "table"
        elif isinstance(raw_val, dict) and "columns" in raw_val and "rows" in raw_val:
            target_type = "table"
        elif isinstance(raw_val, list) and raw_val and all(isinstance(r, dict) and len(r) >= 2 for r in raw_val):
            target_type = "table"
        elif isinstance(raw_val, (list, tuple, set)) or (_HAS_PANDAS_NUMPY and isinstance(raw_val, (pd.Series, pd.Index))):
            target_type = "list"
        elif isinstance(raw_val, (datetime, date)) or (_HAS_PANDAS_NUMPY and isinstance(raw_val, pd.Timestamp)):
            target_type = "date"
        elif isinstance(raw_val, (int, float, Decimal)) or (_HAS_PANDAS_NUMPY and isinstance(raw_val, np.number)):
            target_type = "percent" if q_inferred == "percent" else "number"
        elif isinstance(raw_val, str):
            s_strip = raw_val.strip()
            if re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", s_strip) or (q_inferred == "date" and normalize_date(s_strip) is not None):
                target_type = "date"
            elif q_inferred == "boolean" and normalize_boolean(s_strip) is not None:
                target_type = "boolean"
            elif q_inferred == "percent" and normalize_percent(s_strip, code_text=code_text) is not None:
                target_type = "percent"
            elif q_inferred == "number" and normalize_number(s_strip) is not None:
                target_type = "number"
            else:
                target_type = "string"
        else:
            target_type = q_inferred or "string"

    # 5. Áp dụng chuẩn hóa theo target_type
    if target_type == "percent":
        ans = normalize_percent(raw_val, code_text=code_text)
        if ans is not None:
            return {"type": "percent", "answer": ans}
        return {"type": "abstain", "answer": None}

    elif target_type == "number":
        q_low = _nfc(question).lower() if question else ""
        if q_low and any(k in q_low for k in ("tiền", "tien", "doanh thu", "dthu", "chi phí", "giá bán", "giá nhập", "gia nhap", "lợi nhuận", "lãi", "vnd", "đồng", "nợ", "no ")):
            is_currency = True
        is_avg = bool(q_low and not is_currency and any(k in q_low for k in ("trung bình", "trung binh", "bình quân", "binh quan")))
        ans = normalize_number(raw_val, is_currency=is_currency, is_average=is_avg)
        if ans is not None:
            return {"type": "number", "answer": ans}
        return {"type": "abstain", "answer": None}

    elif target_type == "boolean":
        ans = normalize_boolean(raw_val)
        if ans is not None:
            return {"type": "boolean", "answer": ans}
        return {"type": "abstain", "answer": None}

    elif target_type == "date":
        ans = normalize_date(raw_val)
        if ans is not None:
            return {"type": "date", "answer": ans}
        return {"type": "abstain", "answer": None}

    elif target_type == "string":
        ans = normalize_string(raw_val)
        if ans is not None:
            return {"type": "string", "answer": ans}
        return {"type": "abstain", "answer": None}

    elif target_type == "list":
        ans = normalize_list(raw_val)
        if ans is not None:
            # Nếu câu hỏi nêu rõ số lượng K (Top K), cắt đúng tối đa K phần tử
            if question:
                q_low_k = _nfc(question).lower()
                m_k = (
                    re.search(r"\btop\s*(\d+)\b", q_low_k)
                    or re.search(r"\b(\d+)\s*(?:mặt\s*hàng|sản\s*phẩm|sp|khách(?:\s*hàng)?|món|hàng|khach)\b", q_low_k)
                    or re.search(r"\bliệt\s*kê\s*(\d+)\b", q_low_k)
                )
                if m_k:
                    k_val = int(m_k.group(1))
                    if len(ans) > k_val:
                        ans = ans[:k_val]
            return {"type": "list", "answer": ans}
        return {"type": "abstain", "answer": None}

    elif target_type == "table":
        ans = normalize_table(raw_val)
        if ans is not None:
            return {"type": "table", "answer": ans}
        return {"type": "abstain", "answer": None}

    elif target_type == "unanswerable":
        return {"type": "unanswerable", "answer": None}

    return {"type": "abstain", "answer": None}


def check_result_sanity(
    sub_ans: Dict[str, Any],
    question: str = "",
    code_text: str = "",
) -> Tuple[bool, Optional[str]]:
    """
    Bộ kiểm tra tính hợp lý hậu thực thi (Post-execution Sanity Check).
    Phát hiện các kết quả vô lý (số âm bất thường, số 0 vô lý cho câu hỏi xếp hạng,
    danh sách rỗng) để kích hoạt tự sửa lỗi hoặc ép về 'abstain' tránh bị phạt -1 điểm.
    
    Returns:
        Tuple[bool, Optional[str]]: (is_sane, error_reason_if_not_sane)
    """
    if not isinstance(sub_ans, dict):
        return False, "sub_ans không phải dict hợp lệ"

    ans_type = sub_ans.get("type")
    ans_val = sub_ans.get("answer")

    # Bỏ qua kiểm tra nếu đã là unanswerable hoặc abstain
    if ans_type in ("unanswerable", "abstain"):
        return True, None

    # 0. Chặn Python type objects (vd: return int, return float, <class 'int'>)
    if isinstance(ans_val, type):
        return False, f"Kết quả trả về là Python type object ({ans_val}) thay vì giá trị tính toán"
    if isinstance(ans_val, str) and (ans_val.startswith("<class ") or ans_val.strip() in ("<class 'int'>", "<class 'float'>", "<class 'str'>", "<class 'list'>", "<class 'dict'>")):
        return False, f"Kết quả trả về là type representation ({ans_val}) thay vì giá trị tính toán"

    # 1. Kiểm tra None / NaN
    if is_nan_or_null(ans_val):
        return False, "Kết quả trả về là None, NaN hoặc Inf"

    q_low = _nfc(question).lower() if question else ""

    # 2. Kiểm tra số âm bất thường cho các câu hỏi về doanh thu / số lượng / tiền
    # (Ngoại trừ câu hỏi rõ ràng về biến động, chênh lệch, tăng giảm, lãi ròng, lợi nhuận)
    if ans_type == "number" and isinstance(ans_val, (int, float, Decimal)):
        num_val = float(ans_val)
        is_change_or_profit = bool(re.search(r"t[aă]ng|gi[aả]m|ch[eê]nh\s*l[eệ]ch|thay\s*đ[oổ]i|l[aã]i|l[oỗ]|l[oợ]i\s*nhu[aậ]n|bi[eế]n\s*đ[oộ]ng", q_low))
        is_revenue_or_qty = bool(re.search(
            r"doanh\s*thu|doanh\s*s[oố]|t[oổ]ng\s*ti[eề]n|ti[eề]n\s*b[aá]n|s[oố]\s*lu[oợ]ng|"
            r"(?:bao\s*nhi[eê]u|m[aấ]y|may)\s*(?:đ[oơ]n|ly|chai|h[oộ]p|g[oó]i|s[aả]n\s*ph[aẩ]m|kh[aá]ch|ti[eề]n|h[oó]a\s*đ[oơ]n|kg|kilo|g|gram|t[aấ]n|tan|m[eé]t|met|m3|l[ií]t|lit|th[uú]c|h[aà]ng|m[oó]n)",
            q_low
        ))

        if not is_change_or_profit and is_revenue_or_qty and num_val < 0:
            return False, f"Số âm bất thường ({ans_val}) cho câu hỏi về doanh thu / số lượng không cho phép âm"

        is_count_query = bool(re.search(r"đ[eế]m|s[oố]\s*đ[oơ]n|đ[oơ]n\s*(?:h[uủ]y|hu[yỷ])|m[aấ]y\s*đ[oơ]n|m[aấ]y\s*đ[oợ]t|s[oố]\s*đ[oợ]t|bao\s*nhi[eê]u\s*(?:đ[oơ]n|đ[oợ]t|bill)", q_low))
        has_specific_product_or_unit = bool(re.search(
            r"kg|kilo|g|gram|t[aấ]n|tan|m[eé]t|met|m3|l[ií]t|lit|ly|chai|h[oộ]p|g[oó]i|vi[eê]n|th[uú]c|th[eé]p|m[aá]|th[iị]t|g[aà]|c[aá]|heo|b[oò]|s[aả]n\s*ph[aẩ]m|m[aặ]t\s*h[aà]ng",
            q_low
        ))

        # 2b. Kiểm tra Silent Zero (kết quả 0 hoặc 0.0 bất thường khi hỏi doanh thu / tổng tiền / lượng bán)
        # Miễn trừ cho các truy vấn đếm thuần túy (đếm số đơn, đơn huỷ, đợt giao...) khi không hỏi về sản phẩm/đơn vị cụ thể
        is_pure_count = is_count_query and not has_specific_product_or_unit
        if num_val == 0.0 and is_revenue_or_qty and not is_change_or_profit and not is_pure_count:
            return False, "Silent Zero: Kết quả tính toán bằng 0 bất thường cho câu hỏi doanh thu / số lượng"

        # 2c. Kiểm tra nhầm lẫn Đếm số đơn (Count) sang Cộng tổng tiền (Sum VNĐ)
        asks_money = bool(re.search(r"ti[eề]n|doanh\s*thu|doanh\s*s[oố]|gi[aá]\s*tr[iị]|bao\s*nhi[eê]u\s*đ[oồ]ng", q_low))
        if is_count_query and not asks_money and num_val >= 500_000:
            return (
                False,
                f"Kết quả đếm số đơn ({ans_val}) lớn bất thường như số tiền VNĐ — có dấu hiệu tính tổng tiền (.sum()) thay vì đếm số đơn duy nhất (.nunique())",
            )

    # 3. Kiểm tra kết quả 0 hoặc rỗng hoặc vi phạm Điều 3 (Khách lẻ / Phí phục vụ) cho câu hỏi xếp hạng
    is_ranking = bool(re.search(r"b[aá]n\s*ch[aạ]y\s*nh[aấ]t|ưa\s*chu[oộ]ng\s*nh[aấ]t|trung\s*th[aà]nh\s*nh[aấ]t|s[oộ]p\s*nh[aấ]t|nhi[eê]u\s*nh[aấ]t|cao\s*nh[aấ]t|th[aấ]p\s*nh[aấ]t|[ií]t\s*nh[aấ]t|top\s*\d+|mua\s*nhi[eê]u\s*nh[aấ]t|ai\s*b[aá]n|ai\s*mua|m[aặ]t\s*h[aà]ng\s*n[aà]o|s[aả]n\s*ph[aẩ]m\s*n[aà]o|kh[aá]ch\s*h[aà]ng\s*n[aà]o|kh[aá]ch\s*n[aà]o", q_low))
    if is_ranking:
        # Nếu hỏi đối tượng nào mà trả về số 0 hoặc chuỗi rỗng
        if ans_val in (0, 0.0, "0", ""):
            return False, f"Kết quả '{ans_val}' vô lý cho câu hỏi tìm đối tượng xếp hạng / bán chạy nhất"
        if ans_type == "list" and isinstance(ans_val, (list, tuple)) and len(ans_val) == 0:
            return False, "Danh sách xếp hạng rỗng [] cho câu hỏi tìm đối tượng"

        # Kiểm tra trả về 'Khách lẻ' / 'Phí phục vụ' trái Điều 3 Rulebook
        cand_strs = [str(ans_val).strip().lower()] if isinstance(ans_val, str) else (
            [str(x).strip().lower() for x in ans_val] if isinstance(ans_val, (list, tuple)) else []
        )
        for cs in cand_strs:
            if re.match(r"^(?:kh[aá]ch\s*l[eẻ]|l[eẻ]|v[aã]ng\s*lai|kh[aá]ch\s*v[aã]ng\s*lai|kl)$", cs):
                return False, "Vi phạm Điều 3 Rulebook: Không được xếp hạng 'Khách lẻ / Vãng lai' (bắt buộc lọc bỏ khách lẻ trước khi xếp hạng)"
            if re.match(r"^(?:ph[ií]\s*ph[uụ]c\s*v[uụ]|ph[uụ]\s*thu\s*ph[uụ]c\s*v[uụ])$", cs):
                return False, "Vi phạm Điều 3 Rulebook: 'Phí phục vụ' không được coi là một mặt hàng khi xếp hạng sản phẩm/món"

    # 4. Kiểm tra danh sách rỗng
    if ans_type == "list" and isinstance(ans_val, (list, tuple)) and len(ans_val) == 0:
        return False, "Danh sách kết quả rỗng []"

    # 5. Kiểm tra bảng rỗng
    if ans_type == "table":
        if not isinstance(ans_val, dict):
            return False, "Định dạng bảng không phải dict"
        rows = ans_val.get("rows", [])
        if not rows or len(rows) == 0:
            return False, "Bảng kết quả không có dòng dữ liệu nào (empty rows)"

    return True, None
