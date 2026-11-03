"""
test_lunar_calendar.py — Kiểm thử tra cứu lịch âm và tính toán dịp Tết.
"""

from pathlib import Path
import pandas as pd
import pytest

from datamate.grounding.lunar_calendar import LunarCalendar, get_calendar


@pytest.fixture
def dummy_calendar_csv(tmp_path: Path) -> Path:
    rows = [
        # date, weekday, lunar_day, lunar_month, lunar_year, lunar_leap, holiday
        # 23 tháng Chạp 2023 (năm âm)
        ("2024-02-02", 5, 23, 12, 2023, "false", "Ông Táo"),
        # mùng 10 tháng Giêng 2024 (năm âm)
        ("2024-02-19", 1, 10, 1, 2024, "false", "Vía Thần Tài"),
        # 22 tháng Chạp 2023
        ("2024-02-01", 4, 22, 12, 2023, "false", ""),
        ("2024-01-15", 1, 5, 12, 2023, "false", ""),
    ]
    csv_file = tmp_path / "calendar.csv"
    with open(csv_file, "w", encoding="utf-8") as f:
        f.write("date,weekday,lunar_day,lunar_month,lunar_year,lunar_leap,holiday\n")
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")
    return csv_file


class TestLunarCalendar:
    def test_tet_window_calculation(self, dummy_calendar_csv: Path):
        cal = LunarCalendar.from_csv(dummy_calendar_csv)
        start, end = cal.get_tet_window(2024)
        # Tết 2024: 23 Chạp (2023 âm) -> 10 Giêng (2024 âm)
        assert start == "2024-02-02"
        assert end == "2024-02-19"

    def test_pre_tet_window_calculation(self, dummy_calendar_csv: Path):
        cal = LunarCalendar.from_csv(dummy_calendar_csv)
        pre_start, pre_end = cal.get_pre_tet_window(2024)
        # Khoảng cách từ 2024-02-02 đến 2024-02-19 là 18 ngày
        # pre_end phải là 2024-02-01 (ngay trước 23 Chạp)
        assert pre_end == "2024-02-01"
        assert pre_start == "2024-01-15"

    def test_solar_to_lunar_lookup(self, dummy_calendar_csv: Path):
        cal = LunarCalendar.from_csv(dummy_calendar_csv)
        info = cal.get_lunar_info("2024-02-02")
        assert info is not None
        assert info["lunar_day"] == 23
        assert info["lunar_month"] == 12
        assert info["lunar_year"] == 2023

