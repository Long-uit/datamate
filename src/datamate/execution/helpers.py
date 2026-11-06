"""
helpers.py — Các hàm tiện ích hỗ trợ xử lý dữ liệu chuẩn hóa trong Sandbox.

Được tự động nạp sẵn vào namespace thực thi của hàm `solution(data)`.
Giúp code LLM sinh ra ngắn gọn, an toàn và chống các lỗi thường gặp:
- clean_num: Xử lý chuẩn mọi định dạng tiền tệ VN ('1.250.000'), US ('1,250.00'), 'đ', 'VND', 'triệu', 'k'.
- clean_date: Parse ngày tháng linh hoạt ('DD/MM/YYYY', 'YYYY-MM-DD', timestamp).
"""

from __future__ import annotations

import re
import math
from typing import Any
import pandas as pd
import numpy as np


def clean_num(series_or_val: Any) -> Any:
    """
    Chuyển đổi an toàn Series, mảng hoặc giá trị đơn lẻ sang kiểu số thực (float/int).
    
    Quy tắc xử lý:
    - Loại bỏ ký hiệu tiền tệ 'đ', 'vnđ', 'vnd', '$', khoảng trắng.
    - Xử lý ngoặc đơn kế toán: '(100)' -> -100.
    - Phân biệt định dạng VN ('1.250.000' hoặc '1.250.000,50') và US ('1,250,000' hoặc '1,250.50').
    - Hỗ trợ từ viết tắt: 'triệu', 'k', 'nghìn'.
    """
    def _parse_scalar(val: Any) -> float:
        if val is None or pd.isna(val):
            return 0.0
        if isinstance(val, (int, float, np.number)):
            if math.isnan(val) or math.isinf(val):
                return 0.0
            return float(val)
        
        s = str(val).strip()
        if not s or s.lower() in ("nan", "none", "null", ""):
            return 0.0
        
        # Ngoặc đơn kế toán: (500) -> -500
        is_negative = False
        if s.startswith("(") and s.endswith(")"):
            is_negative = True
            s = s[1:-1].strip()
        elif s.startswith("-"):
            is_negative = True
            s = s[1:].strip()
            
        s_low = s.lower()
        s_clean = re.sub(r"(?:vnđ|vnd|đ|đồng|\$)", "", s_low).strip()
        
        multiplier = 1.0
        if "triệu" in s_clean:
            multiplier = 1_000_000.0
            s_clean = s_clean.replace("triệu", "").strip()
        elif "nghìn" in s_clean or "ngàn" in s_clean:
            multiplier = 1_000.0
            s_clean = s_clean.replace("nghìn", "").replace("ngàn", "").strip()
        elif s_clean.endswith("k"):
            multiplier = 1_000.0
            s_clean = s_clean[:-1].strip()
            
        # Xử lý dấu phân cách
        if "." in s_clean and "," in s_clean:
            if s_clean.rfind(",") > s_clean.rfind("."):
                # Dạng VN: 1.250.000,50
                s_clean = s_clean.replace(".", "").replace(",", ".")
            else:
                # Dạng US: 1,250,000.50
                s_clean = s_clean.replace(",", "")
        elif "," in s_clean:
            parts = s_clean.split(",")
            # Nếu sau dấu phẩy là 3 chữ số -> phân cách nghìn kiểu US (1,250)
            if len(parts) == 2 and len(parts[1]) != 3:
                s_clean = s_clean.replace(",", ".")
            else:
                s_clean = s_clean.replace(",", "")
        elif "." in s_clean:
            parts = s_clean.split(".")
            # Nếu có nhiều hơn 1 dấu chấm (1.250.000) hoặc có 3 chữ số sau dấu chấm (1.250) -> phân cách nghìn VN
            if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and parts[0].isdigit() and int(parts[0]) != 0):
                s_clean = s_clean.replace(".", "")
                
        try:
            num = float(s_clean) * multiplier
            return -num if is_negative else num
        except Exception:
            # Dự phòng regex bóc tách chữ số nếu vẫn còn lẫn text
            m = re.search(r"[-+]?\d*\.?\d+", s_clean)
            if m:
                try:
                    num = float(m.group(0)) * multiplier
                    return -num if is_negative else num
                except Exception:
                    return 0.0
            return 0.0

    if isinstance(series_or_val, pd.Series):
        return series_or_val.apply(_parse_scalar)
    elif isinstance(series_or_val, (list, tuple)):
        return [_parse_scalar(x) for x in series_or_val]
    elif isinstance(series_or_val, np.ndarray):
        return np.vectorize(_parse_scalar)(series_or_val)
    else:
        return _parse_scalar(series_or_val)


def clean_date(series_or_val: Any, dayfirst: Optional[bool] = None) -> Any:
    """
    Chuyển đổi an toàn sang chuẩn pd.to_datetime:
    - Nếu dữ liệu dạng ISO ('2025-10-05'): Luôn giữ chuẩn YYYY-MM-DD (chống lỗi đảo ngày/tháng do dayfirst=True).
    - Nếu dữ liệu dạng Việt Nam ('05/10/2025'): Tự động bật dayfirst=True (DD/MM/YYYY).
    """
    def _parse_scalar(val: Any) -> Any:
        if val is None or pd.isna(val):
            return pd.NaT
        s = str(val).strip()
        if not s or s.lower() in ("nan", "none", "null", "nat"):
            return pd.NaT
        # Nếu chuỗi bắt đầu bằng 4 chữ số (YYYY-MM-DD...) -> Tuyệt đối không đảo ngày tháng
        if re.match(r"^\d{4}[-/]", s):
            try:
                return pd.to_datetime(s, dayfirst=False)
            except Exception:
                return pd.to_datetime(s, errors="coerce")
        # Chuỗi dạng DD/MM/YYYY -> Bật dayfirst=True
        use_df = dayfirst if dayfirst is not None else True
        try:
            return pd.to_datetime(s, dayfirst=use_df, errors="coerce")
        except Exception:
            return pd.NaT

    if isinstance(series_or_val, pd.Series):
        non_na = series_or_val.dropna()
        if not non_na.empty:
            first_val = str(non_na.iloc[0]).strip()
            if re.match(r"^\d{4}[-/]", first_val):
                # Định dạng ISO: YYYY-MM-DD
                try:
                    return pd.to_datetime(series_or_val, dayfirst=False, errors="coerce")
                except Exception:
                    pass
        use_df = dayfirst if dayfirst is not None else True
        try:
            return pd.to_datetime(series_or_val, dayfirst=use_df, format="mixed", errors="coerce")
        except Exception:
            try:
                return pd.to_datetime(series_or_val, dayfirst=use_df, errors="coerce")
            except Exception:
                return pd.to_datetime(series_or_val, errors="coerce")

    elif isinstance(series_or_val, (list, tuple)):
        return [_parse_scalar(x) for x in series_or_val]
    else:
        return _parse_scalar(series_or_val)
