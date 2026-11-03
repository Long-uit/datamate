"""
test_temporal.py — Kiểm thử giải mã biểu thức thời gian tương đối theo Điều 2 Rulebook.
"""

from pathlib import Path
import pandas as pd
import pytest

from datamate.grounding.lunar_calendar import LunarCalendar
from datamate.grounding.temporal import filter_future_data, resolve_temporal


@pytest.fixture
def mock_calendar(tmp_path: Path) -> LunarCalendar:
    rows = [
        ("2024-02-02", 5, 23, 12, 2023, "false", ""),
        ("2024-02-19", 1, 10, 1, 2024, "false", ""),
        ("2024-02-01", 4, 22, 12, 2023, "false", ""),
        ("2024-01-15", 1, 5, 12, 2023, "false", ""),
    ]
    csv_file = tmp_path / "calendar.csv"
    with open(csv_file, "w", encoding="utf-8") as f:
        f.write("date,weekday,lunar_day,lunar_month,lunar_year,lunar_leap,holiday\n")
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")
    return LunarCalendar.from_csv(csv_file)


class TestTemporalGrounder:
    def test_today_and_yesterday(self):
        # 2025-05-15 là Thứ Năm
        wins = resolve_temporal("Doanh thu ngày hôm nay là bao nhiêu?", as_of_date="2025-05-15")
        assert len(wins) == 1
        assert wins[0].start_date == "2025-05-15"
        assert wins[0].end_date == "2025-05-15"
        assert wins[0].label == "today"

        wins_yesterday = resolve_temporal("Số đơn bán được hôm qua", as_of_date="2025-05-15")
        assert len(wins_yesterday) == 1
        assert wins_yesterday[0].start_date == "2025-05-14"
        assert wins_yesterday[0].end_date == "2025-05-14"
        assert wins_yesterday[0].label == "yesterday"

    def test_this_week_and_last_week(self):
        # 2025-05-15 (Thứ Năm).
        # Thứ Hai đầu tuần là 2025-05-12.
        # Rulebook: Tuần này: Từ thứ Hai đầu tuần chứa D đến hết ngày D.
        wins_week = resolve_temporal("Tổng tiền tuần này", as_of_date="2025-05-15")
        assert any(w.label == "this_week" for w in wins_week)
        w = next(w for w in wins_week if w.label == "this_week")
        assert w.start_date == "2025-05-12"
        assert w.end_date == "2025-05-15"

        # Rulebook: Tuần trước: Từ thứ Hai đến Chủ Nhật của tuần ngay trước tuần chứa D.
        # Thứ Hai tuần trước: 2025-05-05. Chủ Nhật tuần trước: 2025-05-11.
        wins_last_week = resolve_temporal("So sánh với tuần trước", as_of_date="2025-05-15")
        assert any(w.label == "last_week" for w in wins_last_week)
        lw = next(w for w in wins_last_week if w.label == "last_week")
        assert lw.start_date == "2025-05-05"
        assert lw.end_date == "2025-05-11"

    def test_this_month_and_last_month(self):
        # 2025-05-15: Tháng này từ 2025-05-01 đến 2025-05-15
        wins_month = resolve_temporal("Khách hàng mua nhiều nhất trong tháng này", as_of_date="2025-05-15")
        tm = next(w for w in wins_month if w.label == "this_month")
        assert tm.start_date == "2025-05-01"
        assert tm.end_date == "2025-05-15"

        # Tháng trước độc lập (không so sánh): 2025-04-01 đến 2025-04-30
        wins_lm = resolve_temporal("Doanh thu tháng trước", as_of_date="2025-05-15")
        lm = next(w for w in wins_lm if w.label == "last_month")
        assert lm.start_date == "2025-04-01"
        assert lm.end_date == "2025-04-30"

        # So sánh tháng này với tháng trước (Rulebook Điều 2: lấy cùng số ngày của tháng trước)
        # as_of_date: 2025-05-15 (ngày 15) -> Tháng trước kỳ so sánh: 2025-04-01 đến 2025-04-15
        wins_cmp = resolve_temporal("Doanh thu tháng này tăng bao nhiêu so với tháng trước", as_of_date="2025-05-15")
        lmc = next(w for w in wins_cmp if w.label == "last_month_compared")
        assert lmc.start_date == "2025-04-01"
        assert lmc.end_date == "2025-04-15"

    def test_month_without_year(self):
        # as_of_date: 2025-05-15
        # "tháng 3": không sau hôm nay -> năm 2025 (2025-03-01 đến 2025-03-31)
        wins_m3 = resolve_temporal("Doanh số tháng 3", as_of_date="2025-05-15")
        assert any(w.start_date == "2025-03-01" and w.end_date == "2025-03-31" for w in wins_m3)

        # "tháng 8": sau hôm nay -> của năm trước (2024-08-01 đến 2024-08-31)
        wins_m8 = resolve_temporal("Doanh số tháng 8", as_of_date="2025-05-15")
        assert any(w.start_date == "2024-08-01" and w.end_date == "2024-08-31" for w in wins_m8)

    def test_quarter_without_year(self):
        # as_of_date: 2025-05-15 (Đang ở Quý 2)
        # "quý 1": tháng 1-3 không sau hôm nay -> Quý 1/2025
        wins_q1 = resolve_temporal("Lợi nhuận quý 1", as_of_date="2025-05-15")
        assert any(w.start_date == "2025-01-01" and w.end_date == "2025-03-31" for w in wins_q1)

        # "quý 3": sau hôm nay -> Quý 3/2024 (2024-07-01 đến 2024-09-30)
        wins_q3 = resolve_temporal("Lợi nhuận quý 3", as_of_date="2025-05-15")
        assert any(w.start_date == "2024-07-01" and w.end_date == "2024-09-30" for w in wins_q3)

    def test_n_days_recent(self):
        # as_of_date: 2025-05-15. "7 ngày gần nhất": [2025-05-09, 2025-05-15]
        wins = resolve_temporal("Số đơn bán trong 7 ngày gần nhất", as_of_date="2025-05-15")
        assert any(w.label == "7_days_recent" for w in wins)
        w7 = next(w for w in wins if w.label == "7_days_recent")
        assert w7.start_date == "2025-05-09"
        assert w7.end_date == "2025-05-15"

    def test_year_to_date(self):
        # "từ đầu năm tới nay"
        wins = resolve_temporal("Doanh thu từ đầu năm tới nay", as_of_date="2025-05-15")
        assert any(w.label == "year_to_date" for w in wins)
        wy = next(w for w in wins if w.label == "year_to_date")
        assert wy.start_date == "2025-01-01"
        assert wy.end_date == "2025-05-15"

    def test_tet_and_pre_tet_window(self, mock_calendar: LunarCalendar):
        wins = resolve_temporal("Doanh thu dịp Tết năm 2024", as_of_date="2024-05-01", calendar=mock_calendar)
        assert any(w.label == "tet_2024" for w in wins)
        wt = next(w for w in wins if w.label == "tet_2024")
        assert wt.start_date == "2024-02-02"
        assert wt.end_date == "2024-02-19"

        wins_pre = resolve_temporal("So với trước Tết năm 2024 thì sao", as_of_date="2024-05-01", calendar=mock_calendar)
        assert any(w.label == "pre_tet_2024" for w in wins_pre)
        wpt = next(w for w in wins_pre if w.label == "pre_tet_2024")
        assert wpt.start_date == "2024-01-15"
        assert wpt.end_date == "2024-02-01"

    def test_filter_future_data(self):
        df = pd.DataFrame({
            "Mã đơn": ["DH1", "DH2", "DH3"],
            "Ngày": ["2025-05-10", "2025-05-15", "2025-05-16"],
            "Trạng thái": ["Hoàn thành", "Hoàn thành", "Hoàn thành"],
            "Tiền": [100, 200, 300],
        })
        # as_of_date: 2025-05-15 -> lọc bỏ DH3 (2025-05-16)
        df_filtered = filter_future_data(df, "Ngày", as_of_date="2025-05-15")
        assert len(df_filtered) == 2
        assert list(df_filtered["Mã đơn"]) == ["DH1", "DH2"]

    def test_filter_future_data_preserves_returns(self):
        """
        Rulebook Điều 2: 'Riêng trạng thái huỷ, trả hàng của đơn lấy theo trạng thái ghi trên đơn,
        kể cả khi phiếu trả ghi ngày sau hôm nay.'
        """
        df = pd.DataFrame({
            "Mã đơn": ["DH1", "DH2", "DH3_RETURN"],
            "Ngày": ["2025-05-10", "2025-05-14", "2025-05-20"],
            "Trạng thái": ["Hoàn thành", "Hoàn thành", "Trả hàng"],
            "Tiền": [100, 200, 300],
        })
        # DH3_RETURN phát sinh sau 2025-05-15 nhưng là phiếu trả hàng -> phải được giữ lại!
        df_filtered = filter_future_data(df, "Ngày", as_of_date="2025-05-15", preserve_returns=True)
        assert len(df_filtered) == 3
        assert "DH3_RETURN" in list(df_filtered["Mã đơn"])

