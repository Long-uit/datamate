"""
lunar_calendar.py — Tra cứu lịch Âm - Dương và tính toán thời gian Tết theo Quy tắc 2 Rulebook.

Quy tắc 2 (Rulebook):
- Tết năm Y, dịp Tết, mùa Tết: từ ngày dương của 23 tháng Chạp (năm âm Y - 1)
  đến hết ngày dương của mùng 10 tháng Giêng (năm âm Y).
- So với trước Tết: cùng số ngày ngay trước ngày 23 tháng Chạp.
- Tra cứu lịch âm trong `calendar.csv`.
"""

from __future__ import annotations

import csv
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Any

try:
    import pandas as pd
except ImportError:
    pd = None

log = logging.getLogger(__name__)

# Cache các instance LunarCalendar theo đường dẫn file
_CALENDAR_CACHE: dict[str, LunarCalendar] = {}


class LunarCalendar:
    """Quản lý tra cứu lịch âm và tính toán các mốc Tết."""

    def __init__(self, data: Any, source_path: Optional[Path] = None):
        self.source_path = source_path
        self._date_map: dict[str, dict] = {}
        self._lunar_map: dict[tuple[int, int, int], str] = {}

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

    def get_tet_window(self, year: int) -> tuple[str, str]:
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

    def get_pre_tet_window(self, year: int) -> tuple[str, str]:
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
