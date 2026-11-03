"""
test_metadata.py — Kiểm thử trích xuất BusinessMeta (Module Metadata).
"""

import pandas as pd
import pytest

from datamate.ingestion.loader import BusinessData, TableInfo
from datamate.ingestion.metadata import get_metadata, extract_date_range, extract_categories


@pytest.fixture
def sample_business():
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
        source_file="don_hang.csv",
        fixed_file_name="don_hang.csv",
        sheet_name="",
        df=df_orders,
        header_row_detected=0,
        n_rows=len(df_orders),
        columns=list(df_orders.columns),
    )
    t2 = TableInfo(
        table_id="chi_tiet",
        source_file="chi_tiet.csv",
        fixed_file_name="chi_tiet.csv",
        sheet_name="",
        df=df_items,
        header_row_detected=0,
        n_rows=len(df_items),
        columns=list(df_items.columns),
    )
    return BusinessData(
        business_id="shop_test_01",
        tables=[t1, t2],
        readme_text="Ghi chú test shop",
        errors=[],
    )


class TestMetadataExtraction:
    def test_extract_date_range(self, sample_business):
        min_date, max_date = extract_date_range(sample_business)
        assert min_date == "2024-02-15"
        assert max_date == "2024-11-05"

    def test_extract_categories(self, sample_business):
        cats = extract_categories(sample_business)
        assert "Trạng thái" in cats or "don_hang.Trạng thái" in cats
        # Phải chứa các giá trị độc nhất
        status_vals = cats.get("Trạng thái") or cats.get("don_hang.Trạng thái")
        assert set(status_vals) == {"Hoàn thành", "Trả hàng", "Huỷ đơn"}

    def test_get_metadata_interface(self, sample_business):
        meta = get_metadata(sample_business)
        assert meta.business_id == "shop_test_01"
        assert meta.date_range == ("2024-02-15", "2024-11-05")
        assert "don_hang" in meta.tables
        assert "chi_tiet" in meta.tables
        assert "Mã đơn" in meta.columns_by_table["don_hang"]
        assert "Sản phẩm" in meta.columns_by_table["chi_tiet"]
