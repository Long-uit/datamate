"""
test_cleaner.py — Kiểm thử toàn diện cho Module 1 (Rule 8 Data Cleaner).
"""

import pandas as pd
import pytest

from datamate.ingestion.cleaner import (
    apply_group_forward_fill,
    clean_dataframe,
    deduplicate_order_rows,
    find_order_id_col,
    find_order_level_cols,
)


class TestRule8Cleaner:
    def test_find_order_id_col(self):
        assert find_order_id_col(["Mã đơn hàng", "Tên khách"]) == "Mã đơn hàng"
        assert find_order_id_col(["Số phiếu", "Ngày"]) == "Số phiếu"
        assert find_order_id_col(["order_id", "amount"]) == "order_id"
        assert find_order_id_col(["Tên sản phẩm", "Đơn giá"]) is None

    def test_find_order_level_cols(self):
        cols = ["Mã đơn", "Ngày tạo", "Tên khách", "Trạng thái", "Sản phẩm", "Số lượng", "Đơn giá"]
        order_cols = find_order_level_cols(cols, "Mã đơn")
        assert "Mã đơn" in order_cols
        assert "Ngày tạo" in order_cols
        assert "Tên khách" in order_cols
        assert "Trạng thái" in order_cols
        assert "Sản phẩm" not in order_cols
        assert "Số lượng" not in order_cols

    def test_group_forward_fill_order_level(self):
        """
        Dòng 1: Đơn DH01, 2024-01-05, Chị Lan, Hoàn thành, SP A, 2
        Dòng 2: None, None, None, None, SP B, 1  -> phải được ffill từ DH01
        Dòng 3: Đơn DH02, 2024-01-06, Anh Tuấn, Đang giao, SP C, 3
        """
        raw_data = {
            "Mã đơn": ["DH01", None, "DH02"],
            "Ngày": ["2024-01-05", "", "2024-01-06"],
            "Khách hàng": ["Chị Lan", None, "Anh Tuấn"],
            "Trạng thái": ["Hoàn thành", None, "Đang giao"],
            "Sản phẩm": ["SP A", "SP B", "SP C"],
            "Số lượng": [2, 1, 3],
        }
        df = pd.DataFrame(raw_data)
        df_clean = apply_group_forward_fill(df, "Mã đơn")

        assert list(df_clean["Mã đơn"]) == ["DH01", "DH01", "DH02"]
        assert list(df_clean["Ngày"]) == ["2024-01-05", "2024-01-05", "2024-01-06"]
        assert list(df_clean["Khách hàng"]) == ["Chị Lan", "Chị Lan", "Anh Tuấn"]
        assert list(df_clean["Trạng thái"]) == ["Hoàn thành", "Hoàn thành", "Đang giao"]
        # Cột chi tiết không bị ffill đè
        assert list(df_clean["Sản phẩm"]) == ["SP A", "SP B", "SP C"]

    def test_deduplicate_same_order_vs_different_order(self):
        """
        Rule 8:
        - Hai dòng của CÙNG MỘT ĐƠN giống nhau ở mọi ô -> tính một lần.
        - Hai dòng giống nhau của HAI ĐƠN KHÁC NHAU -> tính cả hai.
        """
        raw_data = {
            "Mã đơn": ["DH01", "DH01", "DH02"],
            "Sản phẩm": ["Sting dâu", "Sting dâu", "Sting dâu"],
            "Số lượng": [2, 2, 2],
            "Đơn giá": [10000, 10000, 10000],
        }
        df = pd.DataFrame(raw_data)
        df_dedup = deduplicate_order_rows(df, "Mã đơn")

        # DH01 có 2 dòng giống hệt nhau -> giữ 1
        # DH02 có 1 dòng giống -> giữ lại
        # Tổng số dòng còn 2
        assert len(df_dedup) == 2
        assert list(df_dedup["Mã đơn"]) == ["DH01", "DH02"]

    def test_table_without_order_id_keeps_all_rows(self):
        """
        Rule 8:
        - Bảng không ghi theo đơn: mỗi dòng là một lần ghi; hai dòng giống nhau trong cùng file vẫn tính cả hai.
        """
        raw_data = {
            "Tên chi phí": ["Tiền điện", "Tiền điện"],
            "Số tiền": [500000, 500000],
        }
        df = pd.DataFrame(raw_data)
        df_clean = clean_dataframe(df)

        assert len(df_clean) == 2  # Không bị deduplicate

    def test_deduplicate_with_stt_column(self):
        """
        Bảng có cột STT tăng dần, nhưng POS xuất lỗi nhân đôi một món trong cùng đơn.
        Hàm deduplicate phải loại trừ cột STT để phát hiện và loại bỏ dòng trùng.
        """
        raw_data = {
            "STT": [1, 2, 3],
            "Mã đơn": ["DH01", "DH01", "DH02"],
            "Sản phẩm": ["Sting dâu", "Sting dâu", "Sting dâu"],
            "Số lượng": [2, 2, 2],
        }
        df = pd.DataFrame(raw_data)
        df_dedup = deduplicate_order_rows(df, "Mã đơn")

        assert len(df_dedup) == 2
        assert list(df_dedup["STT"]) == [1, 3]

    def test_no_forward_fill_on_numeric_and_discount_columns(self):
        """
        Rule 8 & Rule 1: Không được ffill cột giảm giá hoặc số tiền của đơn/dòng.
        Món 2 không có giảm giá thì phải giữ None/NaN, không được kế thừa từ món 1.
        """
        raw_data = {
            "Mã đơn": ["DH01", None],
            "Khách hàng": ["Anh Nam", None],
            "Sản phẩm": ["Áo sơ mi", "Quần âu"],
            "Giảm giá": [20000, None],
            "Tổng tiền": [500000, None],
        }
        df = pd.DataFrame(raw_data)
        df_clean = apply_group_forward_fill(df, "Mã đơn")

        assert list(df_clean["Khách hàng"]) == ["Anh Nam", "Anh Nam"]
        # Cột Giảm giá và Tổng tiền không được ffill
        assert df_clean["Giảm giá"].iloc[0] == 20000
        assert pd.isna(df_clean["Giảm giá"].iloc[1])
        assert df_clean["Tổng tiền"].iloc[0] == 500000
        assert pd.isna(df_clean["Tổng tiền"].iloc[1])

    def test_clean_dataframe_pipeline(self):
        """Kiểm thử kết hợp vừa forward-fill vừa deduplicate."""
        raw_data = {
            "Mã đơn hàng": ["ORD100", None, "ORD100"],
            "Ngày": ["2024-05-10", None, "2024-05-10"],
            "Sản phẩm": ["Cà phê đen", "Cà phê đen", "Cà phê đen"],
            "Số lượng": [1, 1, 1],
        }
        df = pd.DataFrame(raw_data)
        df_clean = clean_dataframe(df)

        # Dòng 2 được ffill thành ORD100, và giống hệt Dòng 1 -> deduplicate thành 1 dòng duy nhất!
        assert len(df_clean) == 1
        assert df_clean.iloc[0]["Mã đơn hàng"] == "ORD100"

