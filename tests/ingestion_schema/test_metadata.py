"""
test_metadata.py — Kiểm thử trích xuất BusinessMeta (ingestion_schema/metadata.py).
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
from datamate.ingestion_schema.metadata import get_metadata, extract_date_range, extract_categories


class TestMetadataExtraction(unittest.TestCase):
    def setUp(self):
        df_orders = pd.DataFrame({
            "Mã đơn": ["DH1", "DH2", "DH3"],
            "Ngày tạo": ["2024-02-15", "2024-06-20", "2024-11-05"],
            "Trạng thái": ["Hoàn thành", "Trả hàng", "Huỷ đơn"],
            "Kênh bán": ["Tại quầy", "Shopee", "Tại quầy"],
        })
        df_items = pd.DataFrame({
            "Mã đơn": ["DH1", "DH2", "DH3"],
            "Sản phẩm": ["Áo sơ mi", "Quần jean", "Áo khoác"],
            "Loại hàng": ["Thời trang nam", "Thời trang nữ", "Thời trang nam"],
        })

        t1 = TableInfo(
            table_id="don_hang",
            source_file=Path("don_hang.csv"),
            fixed_file_name="don_hang.csv",
            sheet_name="",
            df=df_orders,
            header_row_detected=0,
            n_rows=len(df_orders),
            columns=list(df_orders.columns),
        )
        t2 = TableInfo(
            table_id="chi_tiet",
            source_file=Path("chi_tiet.csv"),
            fixed_file_name="chi_tiet.csv",
            sheet_name="",
            df=df_items,
            header_row_detected=0,
            n_rows=len(df_items),
            columns=list(df_items.columns),
        )
        self.sample_business = BusinessData(
            business_id="shop_test_01",
            tables=[t1, t2],
            readme_text="Ghi chú test shop",
            errors=[],
        )

    def test_extract_date_range(self):
        min_date, max_date = extract_date_range(self.sample_business)
        self.assertEqual(min_date, "2024-02-15")
        self.assertEqual(max_date, "2024-11-05")

    def test_extract_categories(self):
        cats = extract_categories(self.sample_business)
        self.assertTrue("Trạng thái" in cats or "don_hang.Trạng thái" in cats)
        status_vals = cats.get("Trạng thái") or cats.get("don_hang.Trạng thái")
        self.assertEqual(set(status_vals), {"Hoàn thành", "Trả hàng", "Huỷ đơn"})

    def test_get_metadata_interface(self):
        meta = get_metadata(self.sample_business)
        self.assertEqual(meta.business_id, "shop_test_01")
        self.assertEqual(meta.date_range, ("2024-02-15", "2024-11-05"))
        self.assertIn("don_hang", meta.tables)
        self.assertIn("chi_tiet", meta.tables)
        self.assertIn("Mã đơn", meta.columns_by_table["don_hang"])
        self.assertIn("Sản phẩm", meta.columns_by_table["chi_tiet"])


if __name__ == "__main__":
    unittest.main()

