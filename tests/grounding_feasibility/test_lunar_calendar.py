"""
test_lunar_calendar.py — Kiểm thử tra cứu lịch âm và tính toán dịp Tết (grounding_feasibility).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent.parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from datamate.grounding_feasibility.lunar_calendar import LunarCalendar, get_calendar


class TestLunarCalendar(unittest.TestCase):
    def setUp(self):
        self._temp_dir_obj = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._temp_dir_obj.name)

        rows = [
            ("2024-02-02", 5, 23, 12, 2023, "false", "Ông Táo"),
            ("2024-02-19", 1, 10, 1, 2024, "false", "Vía Thần Tài"),
            ("2024-02-01", 4, 22, 12, 2023, "false", ""),
            ("2024-01-15", 1, 5, 12, 2023, "false", ""),
        ]
        self.csv_file = self.tmp_path / "calendar.csv"
        with open(self.csv_file, "w", encoding="utf-8") as f:
            f.write("date,weekday,lunar_day,lunar_month,lunar_year,lunar_leap,holiday\n")
            for r in rows:
                f.write(",".join(str(x) for x in r) + "\n")

    def tearDown(self):
        self._temp_dir_obj.cleanup()

    def test_tet_window_calculation(self):
        cal = LunarCalendar.from_csv(self.csv_file)
        start, end = cal.get_tet_window(2024)
        self.assertEqual(start, "2024-02-02")
        self.assertEqual(end, "2024-02-19")

    def test_pre_tet_window_calculation(self):
        cal = LunarCalendar.from_csv(self.csv_file)
        pre_start, pre_end = cal.get_pre_tet_window(2024)
        self.assertEqual(pre_end, "2024-02-01")
        self.assertEqual(pre_start, "2024-01-15")

    def test_solar_to_lunar_lookup(self):
        cal = LunarCalendar.from_csv(self.csv_file)
        info = cal.get_lunar_info("2024-02-02")
        self.assertIsNotNone(info)
        self.assertEqual(int(info["lunar_day"]), 23)
        self.assertEqual(int(info["lunar_month"]), 12)
        self.assertEqual(int(info["lunar_year"]), 2023)


if __name__ == "__main__":
    unittest.main()

