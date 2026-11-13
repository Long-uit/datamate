"""
test_schema_profiler.py — Kiểm thử Rich Schema Profiler (ingestion_schema/schema_profiler.py).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent.parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import pandas as pd

from datamate.ingestion_schema.loader import BusinessData, TableInfo
from datamate.ingestion_schema.schema_profiler import (
    infer_table_role,
    profile_business_schema,
    profile_table_columns,
)


class TestSchemaProfiler(unittest.TestCase):
    def setUp(self):
        df_orders = pd.DataFrame({
            "Mã đơn": ["DH01", "DH02", "DH03"],
            "Ngày tạo": ["2026-01-10", "2026-02-15", "2026-03-20"],
            "Tổng tiền": ["150.000 đ", "250.000", "500000"],
            "Trạng thái": ["Hoàn thành", "Hoàn thành", "Đang giao"],
        })
        df_items = pd.DataFrame({
            "Mã hàng": ["SP01", "SP02"],
            "Tên hàng": ["Thuốc Hapacol", "Khẩu trang 4D"],
            "Giá bán": [35000, 45000],
        })

        t1 = TableInfo(
            table_id="HoaDon",
            source_file=Path("HoaDon.csv"),
            fixed_file_name="HoaDon.csv",
            sheet_name="",
            df=df_orders,
            header_row_detected=0,
            n_rows=3,
            columns=list(df_orders.columns),
        )
        t2 = TableInfo(
            table_id="SanPham",
            source_file=Path("SanPham.csv"),
            fixed_file_name="SanPham.csv",
            sheet_name="",
            df=df_items,
            header_row_detected=0,
            n_rows=2,
            columns=list(df_items.columns),
        )
        self.bd = BusinessData(
            business_id="biz_profiler_test",
            tables=[t1, t2],
            readme_text="Test store",
            errors=[],
        )

    def test_infer_table_role(self):
        role_sales = infer_table_role("HoaDon", self.bd.tables[0].df)
        self.assertIn("Bán hàng", role_sales)

        role_prod = infer_table_role("SanPham", self.bd.tables[1].df)
        self.assertIn("sản phẩm", role_prod.lower())

    def test_profile_table_columns(self):
        cols_summary = profile_table_columns(self.bd.tables[0].df)
        self.assertTrue(any("ngày" in c.lower() for c in cols_summary))
        self.assertTrue(any("hoàn thành" in c.lower() for c in cols_summary))

    def test_profile_business_schema(self):
        schema_text = profile_business_schema(self.bd)
        self.assertIn("Vai trò", schema_text)
        self.assertIn("HoaDon", schema_text)
        self.assertIn("SanPham", schema_text)
        self.assertIn("CHI TIẾT CÁC BẢNG VÀ CỘT", schema_text)


if __name__ == "__main__":
    unittest.main()

