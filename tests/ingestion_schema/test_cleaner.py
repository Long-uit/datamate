"""
test_cleaner.py — Kiểm thử toàn diện cho Rule 8 Data Cleaner (ingestion_schema).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent.parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import pandas as pd

from datamate.ingestion_schema.cleaner import (
    apply_group_forward_fill,
    clean_dataframe,
    deduplicate_order_rows,
    find_order_id_col,
    find_order_level_cols,
)


class TestRule8Cleaner(unittest.TestCase):
    def test_find_order_id_col(self):
        self.assertEqual(find_order_id_col(["Mã đơn hàng", "Tên khách"]), "Mã đơn hàng")
        self.assertEqual(find_order_id_col(["Số phiếu", "Ngày"]), "Số phiếu")
        self.assertEqual(find_order_id_col(["order_id", "amount"]), "order_id")
        self.assertIsNone(find_order_id_col(["Tên sản phẩm", "Đơn giá"]))

    def test_find_order_level_cols(self):
        cols = ["Mã đơn", "Ngày tạo", "Tên khách", "Trạng thái", "Sản phẩm", "Số lượng", "Đơn giá"]
        order_cols = find_order_level_cols(cols, "Mã đơn")
        self.assertIn("Mã đơn", order_cols)
        self.assertIn("Ngày tạo", order_cols)
        self.assertIn("Tên khách", order_cols)
        self.assertIn("Trạng thái", order_cols)
        self.assertNotIn("Sản phẩm", order_cols)
        self.assertNotIn("Số lượng", order_cols)

    def test_group_forward_fill_order_level(self):
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

        self.assertEqual(list(df_clean["Mã đơn"]), ["DH01", "DH01", "DH02"])
        self.assertEqual(list(df_clean["Ngày"]), ["2024-01-05", "2024-01-05", "2024-01-06"])
        self.assertEqual(list(df_clean["Khách hàng"]), ["Chị Lan", "Chị Lan", "Anh Tuấn"])
        self.assertEqual(list(df_clean["Trạng thái"]), ["Hoàn thành", "Hoàn thành", "Đang giao"])
        self.assertEqual(list(df_clean["Sản phẩm"]), ["SP A", "SP B", "SP C"])

    def test_deduplicate_same_order_vs_different_order(self):
        raw_data = {
            "Mã đơn": ["DH01", "DH01", "DH02"],
            "Sản phẩm": ["Sting dâu", "Sting dâu", "Sting dâu"],
            "Số lượng": [2, 2, 2],
            "Đơn giá": [10000, 10000, 10000],
        }
        df = pd.DataFrame(raw_data)
        df_dedup = deduplicate_order_rows(df, "Mã đơn")

        self.assertEqual(len(df_dedup), 2)
        self.assertEqual(list(df_dedup["Mã đơn"]), ["DH01", "DH02"])

    def test_table_without_order_id_keeps_all_rows(self):
        raw_data = {
            "Tên chi phí": ["Tiền điện", "Tiền điện"],
            "Số tiền": [500000, 500000],
        }
        df = pd.DataFrame(raw_data)
        df_clean = clean_dataframe(df)

        self.assertEqual(len(df_clean), 2)

    def test_deduplicate_with_stt_column(self):
        raw_data = {
            "STT": [1, 2, 3],
            "Mã đơn": ["DH01", "DH01", "DH02"],
            "Sản phẩm": ["Sting dâu", "Sting dâu", "Sting dâu"],
            "Số lượng": [2, 2, 2],
        }
        df = pd.DataFrame(raw_data)
        df_dedup = deduplicate_order_rows(df, "Mã đơn")

        self.assertEqual(len(df_dedup), 2)
        self.assertEqual(list(df_dedup["STT"]), [1, 3])

    def test_no_forward_fill_on_numeric_and_discount_columns(self):
        raw_data = {
            "Mã đơn": ["DH01", None],
            "Khách hàng": ["Anh Nam", None],
            "Sản phẩm": ["Áo sơ mi", "Quần âu"],
            "Giảm giá": [20000, None],
            "Tổng tiền": [500000, None],
        }
        df = pd.DataFrame(raw_data)
        df_clean = apply_group_forward_fill(df, "Mã đơn")

        self.assertEqual(list(df_clean["Khách hàng"]), ["Anh Nam", "Anh Nam"])
        self.assertEqual(df_clean["Giảm giá"].iloc[0], 20000)
        self.assertTrue(pd.isna(df_clean["Giảm giá"].iloc[1]))
        self.assertEqual(df_clean["Tổng tiền"].iloc[0], 500000)
        self.assertTrue(pd.isna(df_clean["Tổng tiền"].iloc[1]))

    def test_clean_dataframe_pipeline(self):
        raw_data = {
            "Mã đơn hàng": ["ORD100", None, "ORD100"],
            "Ngày": ["2024-05-10", None, "2024-05-10"],
            "Sản phẩm": ["Cà phê đen", "Cà phê đen", "Cà phê đen"],
            "Số lượng": [1, 1, 1],
        }
        df = pd.DataFrame(raw_data)
        df_clean = clean_dataframe(df)

        self.assertEqual(len(df_clean), 1)
        self.assertEqual(df_clean.iloc[0]["Mã đơn hàng"], "ORD100")


if __name__ == "__main__":
    unittest.main()

