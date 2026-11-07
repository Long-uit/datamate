"""
test_temporal.py — Kiểm thử giải mã biểu thức thời gian tương đối theo Điều 2 Rulebook (grounding_feasibility).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent.parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import pandas as pd

from datamate.grounding_feasibility.lunar_calendar import LunarCalendar
from datamate.grounding_feasibility.temporal import (
    filter_future_data,
    resolve_temporal,
    resolve_temporal_context,
    extract_query_date_range,
    extract_comparison_date_range,
    TET_SOLAR_RANGES,
)


class TestTemporalGrounder(unittest.TestCase):
    def setUp(self):
        self._temp_dir_obj = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._temp_dir_obj.name)

        rows = [
            ("2024-02-02", 5, 23, 12, 2023, "false", ""),
            ("2024-02-19", 1, 10, 1, 2024, "false", ""),
            ("2024-02-01", 4, 22, 12, 2023, "false", ""),
            ("2024-01-15", 1, 5, 12, 2023, "false", ""),
        ]
        self.csv_file = self.tmp_path / "calendar.csv"
        with open(self.csv_file, "w", encoding="utf-8") as f:
            f.write("date,weekday,lunar_day,lunar_month,lunar_year,lunar_leap,holiday\n")
            for r in rows:
                f.write(",".join(str(x) for x in r) + "\n")
        self.mock_calendar = LunarCalendar.from_csv(self.csv_file)

    def tearDown(self):
        self._temp_dir_obj.cleanup()

    def test_today_and_yesterday(self):
        wins = resolve_temporal("Doanh thu ngày hôm nay là bao nhiêu?", as_of_date="2025-05-15")
        self.assertEqual(len(wins), 1)
        self.assertEqual(wins[0].start_date, "2025-05-15")
        self.assertEqual(wins[0].end_date, "2025-05-15")
        self.assertEqual(wins[0].label, "today")

        wins_yesterday = resolve_temporal("Số đơn bán được hôm qua", as_of_date="2025-05-15")
        self.assertEqual(len(wins_yesterday), 1)
        self.assertEqual(wins_yesterday[0].start_date, "2025-05-14")
        self.assertEqual(wins_yesterday[0].end_date, "2025-05-14")
        self.assertEqual(wins_yesterday[0].label, "yesterday")

    def test_this_week_and_last_week(self):
        wins_week = resolve_temporal("Tổng tiền tuần này", as_of_date="2025-05-15")
        self.assertTrue(any(w.label == "this_week" for w in wins_week))
        w = next(w for w in wins_week if w.label == "this_week")
        self.assertEqual(w.start_date, "2025-05-12")
        self.assertEqual(w.end_date, "2025-05-15")

        wins_last_week = resolve_temporal("So sánh với tuần trước", as_of_date="2025-05-15")
        self.assertTrue(any(w.label == "last_week" for w in wins_last_week))
        lw = next(w for w in wins_last_week if w.label == "last_week")
        self.assertEqual(lw.start_date, "2025-05-05")
        self.assertEqual(lw.end_date, "2025-05-11")

    def test_this_month_and_last_month(self):
        wins_month = resolve_temporal("Khách hàng mua nhiều nhất trong tháng này", as_of_date="2025-05-15")
        tm = next(w for w in wins_month if w.label == "this_month")
        self.assertEqual(tm.start_date, "2025-05-01")
        self.assertEqual(tm.end_date, "2025-05-15")

        wins_lm = resolve_temporal("Doanh thu tháng trước", as_of_date="2025-05-15")
        lm = next(w for w in wins_lm if w.label == "last_month")
        self.assertEqual(lm.start_date, "2025-04-01")
        self.assertEqual(lm.end_date, "2025-04-30")

        wins_cmp = resolve_temporal("Doanh thu tháng này tăng bao nhiêu so với tháng trước", as_of_date="2025-05-15")
        lmc = next(w for w in wins_cmp if w.label == "last_month_compared")
        self.assertEqual(lmc.start_date, "2025-04-01")
        self.assertEqual(lmc.end_date, "2025-04-15")

    def test_month_without_year(self):
        wins_m3 = resolve_temporal("Doanh số tháng 3", as_of_date="2025-05-15")
        self.assertTrue(any(w.start_date == "2025-03-01" and w.end_date == "2025-03-31" for w in wins_m3))

        wins_m8 = resolve_temporal("Doanh số tháng 8", as_of_date="2025-05-15")
        self.assertTrue(any(w.start_date == "2024-08-01" and w.end_date == "2024-08-31" for w in wins_m8))

    def test_quarter_without_year(self):
        wins_q1 = resolve_temporal("Lợi nhuận quý 1", as_of_date="2025-05-15")
        self.assertTrue(any(w.start_date == "2025-01-01" and w.end_date == "2025-03-31" for w in wins_q1))

        wins_q3 = resolve_temporal("Lợi nhuận quý 3", as_of_date="2025-05-15")
        self.assertTrue(any(w.start_date == "2024-07-01" and w.end_date == "2024-09-30" for w in wins_q3))

    def test_n_days_recent(self):
        wins = resolve_temporal("Số đơn bán trong 7 ngày gần nhất", as_of_date="2025-05-15")
        self.assertTrue(any(w.label == "7_days_recent" for w in wins))
        w7 = next(w for w in wins if w.label == "7_days_recent")
        self.assertEqual(w7.start_date, "2025-05-09")
        self.assertEqual(w7.end_date, "2025-05-15")

    def test_year_to_date(self):
        wins = resolve_temporal("Doanh thu từ đầu năm tới nay", as_of_date="2025-05-15")
        self.assertTrue(any(w.label == "year_to_date" for w in wins))
        wy = next(w for w in wins if w.label == "year_to_date")
        self.assertEqual(wy.start_date, "2025-01-01")
        self.assertEqual(wy.end_date, "2025-05-15")

    def test_tet_and_pre_tet_window(self):
        wins = resolve_temporal("Doanh thu dịp Tết năm 2024", as_of_date="2024-05-01", calendar=self.mock_calendar)
        self.assertTrue(any(w.label == "tet_2024" for w in wins))
        wt = next(w for w in wins if w.label == "tet_2024")
        self.assertEqual(wt.start_date, "2024-02-02")
        self.assertEqual(wt.end_date, "2024-02-19")

        wins_pre = resolve_temporal("So với trước Tết năm 2024 thì sao", as_of_date="2024-05-01", calendar=self.mock_calendar)
        self.assertTrue(any(w.label == "pre_tet_2024" for w in wins_pre))
        wpt = next(w for w in wins_pre if w.label == "pre_tet_2024")
        self.assertEqual(wpt.start_date, "2024-01-15")
        self.assertEqual(wpt.end_date, "2024-02-01")

    def test_filter_future_data(self):
        df = pd.DataFrame({
            "Mã đơn": ["DH1", "DH2", "DH3"],
            "Ngày": ["2025-05-10", "2025-05-15", "2025-05-16"],
            "Trạng thái": ["Hoàn thành", "Hoàn thành", "Hoàn thành"],
            "Tiền": [100, 200, 300],
        })
        df_filtered = filter_future_data(df, "Ngày", as_of_date="2025-05-15")
        self.assertEqual(len(df_filtered), 2)
        self.assertEqual(list(df_filtered["Mã đơn"]), ["DH1", "DH2"])

    def test_filter_future_data_preserves_returns(self):
        df = pd.DataFrame({
            "Mã đơn": ["DH1", "DH2", "DH3_RETURN"],
            "Ngày": ["2025-05-10", "2025-05-14", "2025-05-20"],
            "Trạng thái": ["Hoàn thành", "Hoàn thành", "Trả hàng"],
            "Tiền": [100, 200, 300],
        })
        df_filtered = filter_future_data(df, "Ngày", as_of_date="2025-05-15", preserve_returns=True)
        self.assertEqual(len(df_filtered), 3)
        self.assertIn("DH3_RETURN", list(df_filtered["Mã đơn"]))


if __name__ == "__main__":
    unittest.main()

