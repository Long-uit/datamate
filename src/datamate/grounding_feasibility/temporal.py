"""
temporal.py — Giải mã biểu thức thời gian tiếng Việt, lịch Âm - Dương theo Điều 2 Rulebook và lọc dữ liệu tương lai.

Module hợp nhất duy nhất (Single Source of Truth) chịu trách nhiệm:
1. Tra cứu các mốc Tết âm lịch (23 Chạp đến mùng 10 Giêng) qua calendar.csv hoặc hằng số TET_SOLAR_RANGES.
2. Giải mã tất cả các biểu thức thời gian tiếng Việt (hôm nay, hôm qua, tuần này/trước, tháng này/trước,
   nửa đầu/cuối tháng, 10 ngày, quý, năm, N ngày gần nhất, rằm, mùng 1 âm).
3. Cung cấp API chuẩn cho Feasibility Gate: `extract_query_date_range` và `extract_comparison_date_range`.
4. Cung cấp API chuẩn cho Prompt Builder: `resolve_temporal_context`.
5. Lọc bỏ dữ liệu tương lai: `filter_future_data`.
"""

from __future__ import annotations

import calendar as pycalendar
import csv
from datetime import date, datetime, timedelta
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import unicodedata

try:
    import pandas as pd
except ImportError:
    pd = None

from datamate.types import TimeWindow

log = logging.getLogger(__name__)


# ==============================================================================
# QUẢN LÝ LỊCH ÂM VÀ TRA CỨU TẾT (LUNAR CALENDAR ENGINE)
# ==============================================================================

_CALENDAR_CACHE: Dict[str, LunarCalendar] = {}


class LunarCalendar:
    """Quản lý tra cứu lịch âm và tính toán các mốc Tết."""

    def __init__(self, data: Any, source_path: Optional[Path] = None):
        self.source_path = source_path
        self._date_map: Dict[str, dict] = {}
        self._lunar_map: Dict[Tuple[int, int, int], str] = {}

        if pd is not None and isinstance(data, pd.DataFrame):
            self.df = data.copy()
            self.df["date"] = self.df["date"].astype(str)
            self.df["lunar_day"] = pd.to_numeric(self.df["lunar_day"], errors="coerce").fillna(0).astype(int)
            self.df["lunar_month"] = pd.to_numeric(self.df["lunar_month"], errors="coerce").fillna(0).astype(int)
            self.df["lunar_year"] = pd.to_numeric(self.df["lunar_year"], errors="coerce").fillna(0).astype(int)

            self._date_map = self.df.set_index("date").to_dict(orient="index")
            for _, row in self.df.iterrows():
                key = (int(row["lunar_year"]), int(row["lunar_month"]), int(row["lunar_day"]))
                if key not in self._lunar_map:
                    self._lunar_map[key] = str(row["date"])
        elif isinstance(data, list):
            self.df = None
            for row in data:
                d_str = str(row.get("date", "")).strip()
                try:
                    ly = int(row.get("lunar_year", 0))
                    lm = int(row.get("lunar_month", 0))
                    ld = int(row.get("lunar_day", 0))
                except (ValueError, TypeError):
                    continue
                self._date_map[d_str] = row
                key = (ly, lm, ld)
                if key not in self._lunar_map and d_str:
                    self._lunar_map[key] = d_str
        else:
            self.df = None

    @classmethod
    def from_csv(cls, path: str | Path) -> LunarCalendar:
        """Nạp calendar.csv từ đường dẫn chỉ định."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Không tìm thấy file calendar: {path}")

        if pd is not None:
            try:
                df = pd.read_csv(path)
                return cls(df, source_path=path)
            except Exception:
                pass

        # Fallback dùng csv stdlib nếu không có pandas
        rows = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
        return cls(rows, source_path=path)

    def get_solar_date(self, lunar_year: int, lunar_month: int, lunar_day: int) -> Optional[str]:
        """Tra ngày dương lịch (YYYY-MM-DD) từ ngày âm lịch."""
        return self._lunar_map.get((lunar_year, lunar_month, lunar_day))

    def get_lunar_info(self, solar_date_str: str) -> Optional[dict]:
        """Tra thông tin ngày âm từ ngày dương lịch (YYYY-MM-DD)."""
        return self._date_map.get(solar_date_str)

    def get_tet_window(self, year: int) -> Tuple[str, str]:
        """
        Lấy khoảng ngày Dương lịch của 'Tết năm Y':
        - Từ 23 tháng Chạp (năm âm Y - 1)
        - Đến hết mùng 10 tháng Giêng (năm âm Y)
        Trả về: (start_date, end_date) dưới dạng YYYY-MM-DD
        """
        start = self.get_solar_date(lunar_year=year - 1, lunar_month=12, lunar_day=23)
        end = self.get_solar_date(lunar_year=year, lunar_month=1, lunar_day=10)

        if not start or not end:
            raise ValueError(f"Không tìm thấy dữ liệu Tết cho năm {year} trong calendar.csv")

        return start, end

    def get_pre_tet_window(self, year: int) -> Tuple[str, str]:
        """
        Lấy khoảng ngày Dương lịch của 'So với trước Tết năm Y':
        - Cùng số ngày ngay trước ngày 23 tháng Chạp.
        Trả về: (pre_start_date, pre_end_date) dưới dạng YYYY-MM-DD
        """
        tet_start_str, tet_end_str = self.get_tet_window(year)
        tet_start = datetime.strptime(tet_start_str, "%Y-%m-%d").date()
        tet_end = datetime.strptime(tet_end_str, "%Y-%m-%d").date()

        n_days = (tet_end - tet_start).days + 1

        pre_end = tet_start - timedelta(days=1)
        pre_start = tet_start - timedelta(days=n_days)

        return pre_start.isoformat(), pre_end.isoformat()


def find_calendar_file(base_dir: Optional[Path | str] = None) -> Optional[Path]:
    """Tìm calendar.csv theo thứ tự ưu tiên."""
    candidates = []
    if base_dir:
        b = Path(base_dir)
        candidates.append(b / "calendar.csv" if b.is_dir() else b)
    candidates.extend([
        Path("competition_data/public_test/calendar.csv"),
        Path("competition_data/train/calendar.csv"),
        Path("/data/calendar.csv"),
    ])
    for c in candidates:
        if c.exists():
            return c
    return None


def get_calendar(hint_path: Optional[Path | str] = None) -> Optional[LunarCalendar]:
    """Lấy hoặc nạp LunarCalendar instance có cache."""
    global _CALENDAR_CACHE
    cal_file = find_calendar_file(hint_path) if hint_path is None or Path(hint_path).is_dir() else Path(hint_path)

    if not cal_file or not cal_file.exists():
        return None

    key = str(cal_file.resolve())
    if key not in _CALENDAR_CACHE:
        _CALENDAR_CACHE[key] = LunarCalendar.from_csv(cal_file)

    return _CALENDAR_CACHE[key]


# ==============================================================================
# HẰNG SỐ VÀ TIỆN ÍCH LỊCH TẾT NGUYÊN ĐÁN (TET SOLAR RANGES)
# ==============================================================================

# Tra cứu mốc Tết cố định: 23 tháng Chạp (năm Y-1) đến mùng 10 tháng Giêng (năm Y)
TET_SOLAR_RANGES: Dict[int, Tuple[str, str]] = {
    2024: ("2024-02-02", "2024-02-19"),
    2025: ("2025-01-22", "2025-02-07"),
    2026: ("2026-02-10", "2026-02-26"),
    2027: ("2027-01-30", "2027-02-16"),
}


def _normalize_text(text: str) -> str:
    """Chuẩn hóa tiếng Việt (NFC, chữ thường, gộp khoảng trắng)."""
    text = unicodedata.normalize("NFC", str(text)).lower()
    return re.sub(r"\s+", " ", text).strip()


def parse_date(date_str: str) -> date:
    """Chuyển đổi chuỗi ngày YYYY-MM-DD sang date object."""
    date_str = str(date_str).strip()[:10]
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def get_month_end(year: int, month: int) -> date:
    """Lấy ngày cuối cùng của một tháng."""
    last_day = pycalendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def get_tet_dates_from_calendar(year: int, calendar_path: Optional[str | Path] = None) -> Optional[Tuple[str, str]]:
    """Tra cứu mốc ngày dương lịch của Tết năm Y từ tệp calendar.csv động hoặc fallback."""
    cal = get_calendar(calendar_path)
    if cal is not None:
        try:
            return cal.get_tet_window(year)
        except Exception:
            pass
    return TET_SOLAR_RANGES.get(year)


# ==============================================================================
# BỘ GIẢI MÃ THỜI GIAN THEO ĐIỀU 2 RULEBOOK (RESOLVE TEMPORAL)
# ==============================================================================

def resolve_temporal(
    question: str,
    as_of_date: str,
    calendar: Optional[LunarCalendar] = None,
) -> List[TimeWindow]:
    """
    Phân tích câu hỏi tiếng Việt kết hợp ngày mốc as_of_date và calendar.csv
    để trích xuất các cửa sổ thời gian (TimeWindow) theo Điều 2 Rulebook.
    """
    d = parse_date(as_of_date)
    q = _normalize_text(question)
    windows: List[TimeWindow] = []

    if calendar is None:
        calendar = get_calendar()

    # 1. Hôm nay / ngày mốc
    if re.search(r"\bh[oô]m nay\b|\bng[aà]y m[oố]c\b|\bhnay\b|\bb[uữ]a nay\b", q):
        windows.append(TimeWindow(
            start_date=d.isoformat(),
            end_date=d.isoformat(),
            label="today",
            description=f"Hôm nay ({d.isoformat()})",
        ))

    # 2. Hôm qua
    if re.search(r"\bh[oô]m qua\b", q):
        yesterday = d - timedelta(days=1)
        windows.append(TimeWindow(
            start_date=yesterday.isoformat(),
            end_date=yesterday.isoformat(),
            label="yesterday",
            description=f"Hôm qua ({yesterday.isoformat()})",
        ))

    # 3. Tuần này (Thứ Hai đầu tuần chứa D đến hết D)
    if re.search(r"\btu[aầ]n n[aà]y\b|\btrong tu[aầ]n n[aà]y\b", q):
        monday = d - timedelta(days=d.weekday())
        windows.append(TimeWindow(
            start_date=monday.isoformat(),
            end_date=d.isoformat(),
            label="this_week",
            description=f"Tuần này (từ {monday.isoformat()} đến {d.isoformat()})",
        ))

    # 4. Tuần trước / tuần rồi (Thứ Hai đến Chủ Nhật của tuần ngay trước)
    if re.search(r"\btu[aầ]n tr[uư][oớ]c\b|\btu[aầ]n r[oồ]i\b", q):
        last_week_monday = d - timedelta(days=d.weekday() + 7)
        last_week_sunday = last_week_monday + timedelta(days=6)
        windows.append(TimeWindow(
            start_date=last_week_monday.isoformat(),
            end_date=last_week_sunday.isoformat(),
            label="last_week",
            description=f"Tuần trước (từ {last_week_monday.isoformat()} đến {last_week_sunday.isoformat()})",
        ))

    # 5. Tháng này (Từ 01 của tháng chứa D đến hết D)
    has_this_month = bool(re.search(r"\bth[aá]ng n[aà]y\b|\btrong th[aá]ng n[aà]y\b|\bthang nay\b", q))
    if has_this_month:
        month_start = d.replace(day=1)
        windows.append(TimeWindow(
            start_date=month_start.isoformat(),
            end_date=d.isoformat(),
            label="this_month",
            description=f"Tháng này (từ {month_start.isoformat()} đến {d.isoformat()})",
        ))

    # 6. Tháng trước / tháng rồi
    if re.search(r"\bth[aá]ng tr[uư][oớ]c\b|\bth[aá]ng r[oồ]i\b|\bthang truoc\b|\bthang roi\b", q):
        if d.month == 1:
            lm_year = d.year - 1
            lm_month = 12
        else:
            lm_year = d.year
            lm_month = d.month - 1
        lm_start = date(lm_year, lm_month, 1)
        lm_end_full = get_month_end(lm_year, lm_month)

        is_comparison = bool(
            has_this_month
            or re.search(r"so\s*(v[oớ]i|s[aá]nh)?\s*th[aá]ng\s*(tr[uư][oớ]c|r[oồ]i|li[eề]n\s*tr[uư][oớ]c)", q)
            or re.search(r"(t[aă]ng|gi[aả]m|ch[eê]nh\s*l[eệ]ch|thay\s*đ[oổ]i)\b.*th[aá]ng\s*(tr[uư][oớ]c|r[oồ]i)", q)
        )

        if is_comparison:
            cmp_day = min(d.day, lm_end_full.day)
            lm_end_cmp = date(lm_year, lm_month, cmp_day)
            windows.append(TimeWindow(
                start_date=lm_start.isoformat(),
                end_date=lm_end_cmp.isoformat(),
                label="last_month_compared",
                description=f"Tháng trước kỳ so sánh (từ {lm_start.isoformat()} đến {lm_end_cmp.isoformat()})",
            ))
        else:
            windows.append(TimeWindow(
                start_date=lm_start.isoformat(),
                end_date=lm_end_full.isoformat(),
                label="last_month",
                description=f"Tháng trước (tháng {lm_month}/{lm_year})",
            ))

    # 7. Từ đầu năm / từ đầu năm tới nay / từ đầu năm đến nay
    if re.search(r"t[uừ]\s*đ[aầ]u\s*n[aă]m(\s*(t[oớ]i|đ[eế]n)\s*nay)?", q):
        year_start = date(d.year, 1, 1)
        windows.append(TimeWindow(
            start_date=year_start.isoformat(),
            end_date=d.isoformat(),
            label="year_to_date",
            description=f"Từ đầu năm đến hôm nay ({year_start.isoformat()} - {d.isoformat()})",
        ))

    # 8. N ngày gần nhất / N ngày qua / N ngày vừa qua / N ngày gần đây
    m_ndays = re.search(r"(\d+)\s*ng[aà]y\s*(g[aầ]n\s*nh[aấ]t|qua|v[uừ]a\s*qua|g[aầ]n\s*đ[aâ]y)", q)
    if m_ndays:
        n = int(m_ndays.group(1))
        start_ndays = d - timedelta(days=n - 1)
        windows.append(TimeWindow(
            start_date=start_ndays.isoformat(),
            end_date=d.isoformat(),
            label=f"{n}_days_recent",
            description=f"{n} ngày gần nhất (từ {start_ndays.isoformat()} đến {d.isoformat()})",
        ))

    # 9. Tháng M (có hoặc không ghi năm)
    m_month = re.search(r"\bth(?:[aá]ng|ang|angs)\s*(\d{1,2})(?:\s*(?:/|n[aă]m|[\s\-])\s*(\d{4}))?\b", q)
    if (
        m_month
        and not re.search(r"\bth[aá]ng\s*(n[aà]y|tr[uư][oớ]c|r[oồ]i)\b", m_month.group(0))
        and not re.search(r"n[uử]a\s*(đ[aầ]u|cu[oố]i)|10\s*ng[aà]y\s*(đ[aầ]u|gi[uữ]a|cu[oố]i)|\b(r[aăằ]m|ram|m[uù]ng\s*1)\b", q)
    ):
        m_val = int(m_month.group(1))
        if 1 <= m_val <= 12:
            if m_month.group(2):
                y_val = int(m_month.group(2))
            else:
                if date(d.year, m_val, 1) <= d:
                    y_val = d.year
                else:
                    y_val = d.year - 1

            m_start = date(y_val, m_val, 1)
            m_end = get_month_end(y_val, m_val)
            windows.append(TimeWindow(
                start_date=m_start.isoformat(),
                end_date=m_end.isoformat(),
                label=f"month_{y_val}_{m_val:02d}",
                description=f"Tháng {m_val}/{y_val}",
            ))

    # 9.1. Nửa đầu tháng / Nửa cuối tháng
    m_half = re.search(r"n[uử]a\s*(đ[aầ]u|cu[oố]i)\s*th[aá]ng(?:\s*(\d{1,2})(?:\s*(?:/|n[aă]m)\s*(\d{4}))?|\s*n[aà]y)?", q)
    if m_half:
        which_half = "first" if "đầu" in m_half.group(1).lower() or "dau" in _normalize_text(m_half.group(1)) else "second"
        if m_half.group(2):
            hm_month = int(m_half.group(2))
            hm_year = int(m_half.group(3)) if m_half.group(3) else (d.year if date(d.year, hm_month, 1) <= d else d.year - 1)
        else:
            hm_month = d.month
            hm_year = d.year

        hm_end_full = get_month_end(hm_year, hm_month)
        if which_half == "first":
            h_start = date(hm_year, hm_month, 1)
            h_end = date(hm_year, hm_month, 15)
            h_desc = f"Nửa đầu tháng {hm_month}/{hm_year} (từ 01 đến 15)"
        else:
            h_start = date(hm_year, hm_month, 16)
            h_end = hm_end_full
            if hm_year == d.year and hm_month == d.month and d < hm_end_full:
                h_end = max(h_start, d)
            h_desc = f"Nửa cuối tháng {hm_month}/{hm_year} (từ 16 đến {h_end.day:02d})"

        windows.append(TimeWindow(
            start_date=h_start.isoformat(),
            end_date=h_end.isoformat(),
            label=f"half_{which_half}_{hm_year}_{hm_month:02d}",
            description=h_desc,
        ))

    # 9.2. 10 ngày đầu tháng / giữa tháng / cuối tháng
    m_tendays = re.search(r"10\s*ng[aà]y\s*(đ[aầ]u|gi[uữ]a|cu[oố]i)\s*th[aá]ng(?:\s*(\d{1,2})(?:\s*(?:/|n[aă]m)\s*(\d{4}))?|\s*n[aà]y)?", q)
    if m_tendays:
        pos = m_tendays.group(1).lower()
        which_ten = "first" if "đầu" in pos else ("middle" if "giữa" in pos else "last")
        if m_tendays.group(2):
            tm_month = int(m_tendays.group(2))
            tm_year = int(m_tendays.group(3)) if m_tendays.group(3) else (d.year if date(d.year, tm_month, 1) <= d else d.year - 1)
        else:
            tm_month = d.month
            tm_year = d.year

        tm_end_full = get_month_end(tm_year, tm_month)
        if which_ten == "first":
            t_start = date(tm_year, tm_month, 1)
            t_end = date(tm_year, tm_month, 10)
            t_desc = f"10 ngày đầu tháng {tm_month}/{tm_year} (01 đến 10)"
        elif which_ten == "middle":
            t_start = date(tm_year, tm_month, 11)
            t_end = date(tm_year, tm_month, 20)
            t_desc = f"10 ngày giữa tháng {tm_month}/{tm_year} (11 đến 20)"
        else:
            t_start = date(tm_year, tm_month, 21)
            t_end = tm_end_full
            t_desc = f"10 ngày cuối tháng {tm_month}/{tm_year} (21 đến {tm_end_full.day:02d})"

        windows.append(TimeWindow(
            start_date=t_start.isoformat(),
            end_date=t_end.isoformat(),
            label=f"tendays_{which_ten}_{tm_year}_{tm_month:02d}",
            description=t_desc,
        ))

    # 9.3. Rằm (15 âm lịch) và Mùng 1 âm lịch
    m_lunar_day = re.search(r"\b(r[aăằ]m|ram|r[aà]m|m[uù]ng\s*1)\b(?:\s*(?:th[aá]ng|thg)?\s*(\d{1,2}|gi[eê]ng|ch[aạ]p|b[aả]y|t[aá]m|ch[ií]n|m[uư][oờ]i))?", q)
    if m_lunar_day and calendar is not None:
        target_ld = 15 if any(k in _normalize_text(m_lunar_day.group(1)) for k in ["răm", "rằm", "ram", "ràm"]) else 1
        l_month_raw = m_lunar_day.group(2)
        if l_month_raw:
            lm_raw_norm = _normalize_text(l_month_raw)
            month_map = {"gieng": 1, "chap": 12, "bay": 7, "tam": 8, "chin": 9, "muoi": 10}
            if lm_raw_norm.isdigit():
                target_lm = int(lm_raw_norm)
            else:
                target_lm = month_map.get(lm_raw_norm, 1)
        else:
            target_lm = d.month

        solar_date_found = None
        for test_year in (d.year, d.year - 1, d.year + 1):
            s_d = calendar.get_solar_date(test_year, target_lm, target_ld)
            if s_d:
                if parse_date(s_d) <= d:
                    solar_date_found = s_d
                    break
                elif solar_date_found is None:
                    solar_date_found = s_d

        if solar_date_found:
            day_label = "Rằm (15 âm)" if target_ld == 15 else "Mùng 1 âm"
            windows.append(TimeWindow(
                start_date=solar_date_found,
                end_date=solar_date_found,
                label=f"lunar_{target_ld}_{target_lm}",
                description=f"{day_label} tháng {target_lm} âm lịch (ngày dương {solar_date_found})",
            ))

    # 10. Quý Q (có hoặc không ghi năm)
    m_quarter = re.search(r"\bqu[yý]\s*([1-4])(?:\s*(?:/|n[aă]m)\s*(\d{4}))?\b", q)
    if m_quarter:
        q_val = int(m_quarter.group(1))
        start_month = (q_val - 1) * 3 + 1
        end_month = q_val * 3

        if m_quarter.group(2):
            q_year = int(m_quarter.group(2))
        else:
            if date(d.year, start_month, 1) <= d:
                q_year = d.year
            else:
                q_year = d.year - 1

        q_start = date(q_year, start_month, 1)
        q_end = get_month_end(q_year, end_month)
        windows.append(TimeWindow(
            start_date=q_start.isoformat(),
            end_date=q_end.isoformat(),
            label=f"quarter_{q_year}_Q{q_val}",
            description=f"Quý {q_val}/{q_year}",
        ))

    # 10.5. Cả năm YYYY cụ thể (Ví dụ: "năm 2024", "cả năm 2024", "suốt năm 2024")
    m_year = re.search(r"(?:trong|c[aả]|su[oố]t)?\s*n[aă]m\s*(\d{4})\b", q)
    if m_year and not re.search(r"\bth[aá]ng\s*\d{1,2}|qu[yý]\s*[1-4]|t[eế]t", q):
        y_val = int(m_year.group(1))
        windows.append(TimeWindow(
            start_date=f"{y_val}-01-01",
            end_date=f"{y_val}-12-31",
            label=f"year_{y_val}",
            description=f"Cả năm {y_val} (từ 01/01/{y_val} đến 31/12/{y_val})",
        ))

    # 11. Tết năm Y / dịp Tết / mùa Tết / trước Tết
    m_tet = re.search(r"(so\s*v[oớ]i\s*)?(tr[uư][oớ]c\s*)?(d[iị]p\s*|m[uù]a\s*)?t[eế]t(?:\s*n[aă]m\s*(\d{4}))?", q)
    if m_tet:
        if m_tet.group(4):
            tet_year = int(m_tet.group(4))
        else:
            tet_year = d.year

        is_pre_tet = bool(m_tet.group(2) or m_tet.group(1))

        tet_found: Optional[Tuple[str, str]] = None
        # 1. Tra cứu qua calendar instance nếu có
        if calendar is not None:
            try:
                if is_pre_tet:
                    tet_found = calendar.get_pre_tet_window(tet_year)
                else:
                    tet_found = calendar.get_tet_window(tet_year)
            except Exception:
                pass

        # 2. Fallback qua TET_SOLAR_RANGES
        if not tet_found and tet_year in TET_SOLAR_RANGES:
            s_d, e_d = TET_SOLAR_RANGES[tet_year]
            if is_pre_tet:
                tet_s = datetime.strptime(s_d, "%Y-%m-%d").date()
                tet_e = datetime.strptime(e_d, "%Y-%m-%d").date()
                n_days = (tet_e - tet_s).days + 1
                pre_e = tet_s - timedelta(days=1)
                pre_s = tet_s - timedelta(days=n_days)
                tet_found = (pre_s.isoformat(), pre_e.isoformat())
            else:
                tet_found = (s_d, e_d)

        if tet_found:
            t_start, t_end = tet_found
            if is_pre_tet:
                windows.append(TimeWindow(
                    start_date=t_start,
                    end_date=t_end,
                    label=f"pre_tet_{tet_year}",
                    description=f"Giai đoạn trước Tết năm {tet_year} ({t_start} đến {t_end})",
                ))
            else:
                windows.append(TimeWindow(
                    start_date=t_start,
                    end_date=t_end,
                    label=f"tet_{tet_year}",
                    description=f"Tết năm {tet_year} (từ 23 Chạp đến mùng 10 Giêng: {t_start} đến {t_end})",
                ))

    return windows


# ==============================================================================
# INTERFACE HỢP NHẤT CHO TOÀN BỘ PIPELINE (PROMPT, FEASIBILITY, EVAL)
# ==============================================================================

def resolve_temporal_context(
    question: str,
    as_of_date_str: str,
    calendar_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """
    Phân tích câu hỏi và as_of_date để xác định khoảng thời gian cụ thể (ngày dương ISO),
    bao gồm kỳ chính, kỳ đối chiếu (nếu có), mô tả nghiệp vụ và gợi ý lọc code Python/Pandas.
    Single Source of Truth cho toàn bộ pipeline.
    """
    cal = get_calendar(calendar_path)
    try:
        wins = resolve_temporal(question, as_of_date=as_of_date_str, calendar=cal)
    except Exception:
        wins = []

    if wins:
        comp_win = next((w for w in wins if any(k in w.label for k in ["compared", "pre_tet", "last_month_compared"])), None)
        primary_win = next((w for w in wins if w != comp_win), wins[0])

        if comp_win is not None and primary_win is not None:
            desc = f"Kỳ chính: {primary_win.description} | Kỳ đối chiếu: {comp_win.description}"
            code_hint = (
                f"# Kỳ chính: (df[date_col].dt.date >= pd.to_datetime('{primary_win.start_date}').date()) & (df[date_col].dt.date <= pd.to_datetime('{primary_win.end_date}').date())\n"
                f"# Kỳ so sánh: (df[date_col].dt.date >= pd.to_datetime('{comp_win.start_date}').date()) & (df[date_col].dt.date <= pd.to_datetime('{comp_win.end_date}').date())"
            )
            return {
                "as_of_date": as_of_date_str,
                "start_date": primary_win.start_date,
                "end_date": primary_win.end_date,
                "comparison_start": comp_win.start_date,
                "comparison_end": comp_win.end_date,
                "comparison_desc": comp_win.description,
                "description": desc,
                "code_hint": code_hint,
            }
        elif primary_win is not None:
            if primary_win.start_date == primary_win.end_date:
                code_hint = f"df[date_col].dt.date == pd.to_datetime('{primary_win.start_date}').date()"
            else:
                code_hint = f"(df[date_col].dt.date >= pd.to_datetime('{primary_win.start_date}').date()) & (df[date_col].dt.date <= pd.to_datetime('{primary_win.end_date}').date())"
            return {
                "as_of_date": as_of_date_str,
                "start_date": primary_win.start_date,
                "end_date": primary_win.end_date,
                "comparison_start": None,
                "comparison_end": None,
                "comparison_desc": None,
                "description": primary_win.description,
                "code_hint": code_hint,
            }

    # Fallback mặc định
    return {
        "as_of_date": as_of_date_str,
        "start_date": None,
        "end_date": as_of_date_str,
        "comparison_start": None,
        "comparison_end": None,
        "comparison_desc": None,
        "description": f"Mốc thời gian tham chiếu (hôm nay): {as_of_date_str}",
        "code_hint": f"df[date_col].dt.date <= pd.to_datetime('{as_of_date_str}').date()",
    }


def extract_query_date_range(
    question: str,
    as_of_date_str: str,
    calendar_path: Optional[str | Path] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Trích xuất khoảng ngày chính [start_date, end_date] mà câu hỏi nhắm tới (YYYY-MM-DD).
    Cung cấp cho Feasibility Gate để kiểm tra Điều 7 Rulebook.
    """
    ctx = resolve_temporal_context(question, as_of_date_str, calendar_path=calendar_path)
    s, e = ctx.get("start_date"), ctx.get("end_date")
    if s and e:
        return s, e
    return None, None


def extract_comparison_date_range(
    question: str,
    q_start: Optional[str] = None,
    q_end: Optional[str] = None,
    as_of_date_str: Optional[str] = None,
    calendar_path: Optional[str | Path] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Trích xuất khoảng ngày của kỳ đối chiếu [comp_start, comp_end] nếu câu hỏi có so sánh
    (ví dụ: so với tháng trước, so với trước Tết) để kiểm tra Điều 7 Rulebook.
    """
    if as_of_date_str:
        ctx = resolve_temporal_context(question, as_of_date_str, calendar_path=calendar_path)
        cs, ce = ctx.get("comparison_start"), ctx.get("comparison_end")
        if cs and ce:
            return cs, ce

    if q_start and q_end:
        try:
            d_start = parse_date(q_start)
            if d_start.day == 1:
                q_norm = _normalize_text(question)
                has_prev_month_cmp = bool(
                    re.search(r"so\s*(?:v[oớ]i|vs|voi)?\s*th(?:[aá]ng|ang|angs)\s*(?:li(?:[eề]n|en)\s*)?(?:tr[uư][oớ]c|truoc|trc)", q_norm)
                    or re.search(r"th(?:[aá]ng|ang|angs)\s*(?:li(?:[eề]n|en)\s*)?(?:tr[uư][oớ]c|truoc|trc)\s*(?:đ[oó]|do)?", q_norm)
                )
                if has_prev_month_cmp:
                    if d_start.month == 1:
                        prev_y, prev_m = d_start.year - 1, 12
                    else:
                        prev_y, prev_m = d_start.year, d_start.month - 1
                    last_d = pycalendar.monthrange(prev_y, prev_m)[1]
                    return f"{prev_y:04d}-{prev_m:02d}-01", f"{prev_y:04d}-{prev_m:02d}-{last_d:02d}"
        except Exception:
            pass

    return None, None


def find_status_col(columns: List[str]) -> Optional[str]:
    """Tìm cột trạng thái đơn trong danh sách cột."""
    for col in columns:
        norm = _normalize_text(col)
        if re.search(r"tr[aạ]ng\s*th[aá]i|t[iì]nh\s*tr[aạ]ng|status", norm):
            return col
    return None


def filter_future_data(
    df: pd.DataFrame,
    date_col: str,
    as_of_date: str,
    status_col: Optional[str] = None,
    preserve_returns: bool = True,
) -> pd.DataFrame:
    """
    Lọc bỏ các bản ghi có ngày phát sinh > as_of_date theo Điều 2 Rulebook:
    'Mọi bản ghi có ngày phát sinh > D được lọc bỏ (coi như chưa xảy ra),
    ngoại trừ trạng thái huỷ/trả của đơn (lấy theo trạng thái ghi trên đơn,
    kể cả khi phiếu trả ghi ngày sau hôm nay).'
    """
    if df.empty or date_col not in df.columns:
        return df.copy()

    d_cutoff = str(as_of_date).strip()[:10]
    dates = df[date_col].astype(str).str.strip().str[:10]
    valid_dates = pd.to_datetime(dates, format="%Y-%m-%d", errors="coerce")
    cutoff_dt = pd.to_datetime(d_cutoff, format="%Y-%m-%d")

    mask = valid_dates.isna() | (valid_dates <= cutoff_dt)

    if preserve_returns:
        if status_col is None or status_col not in df.columns:
            status_col = find_status_col(list(df.columns))

        if status_col is not None and status_col in df.columns:
            status_norm = df[status_col].astype(str).str.lower()
            is_return_or_cancel = status_norm.str.contains(
                r"hu[yỷ]|tr[aả]\s*h[aà]ng|cancel|return",
                regex=True,
                na=False,
            )
            mask = mask | is_return_or_cancel

    return df[mask].copy().reset_index(drop=True)


__all__ = [
    "TET_SOLAR_RANGES",
    "get_tet_dates_from_calendar",
    "parse_date",
    "get_month_end",
    "resolve_temporal",
    "resolve_temporal_context",
    "extract_query_date_range",
    "extract_comparison_date_range",
    "filter_future_data",
    "find_status_col",
    "LunarCalendar",
    "get_calendar",
]
