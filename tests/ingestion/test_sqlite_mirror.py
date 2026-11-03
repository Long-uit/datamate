"""
test_sqlite_mirror.py — Kiểm thử cho In-Memory SQLite Mirror, lập chỉ mục và Cache.
"""

from pathlib import Path
import pandas as pd
import pytest

from datamate.ingestion.loader import BusinessData, TableInfo
from datamate.ingestion.sqlite_mirror import (
    clear_sqlite_cache,
    create_indexes,
    get_sqlite_mirror,
    to_sqlite,
)


@pytest.fixture(autouse=True)
def clean_cache():
    clear_sqlite_cache()
    yield
    clear_sqlite_cache()


class TestSQLiteMirror:
    def test_to_sqlite_and_index_creation(self):
        df_order = pd.DataFrame({
            "Mã đơn": ["DH1", "DH2"],
            "Ngày": ["2024-01-01", "2024-01-02"],
            "SKU": ["SKU01", "SKU02"],
            "Khách hàng": ["Anh An", "Chị Bình"],
            "Tiền": ["100000", "200000"],
        })
        t1 = TableInfo(
            table_id="t_01",
            source_file=Path("orders.csv"),
            fixed_file_name="orders.csv",
            sheet_name=None,
            df=df_order,
            header_row_detected=0,
            n_rows=2,
            columns=list(df_order.columns),
        )
        bd = BusinessData(business_id="biz_test", tables=[t1])

        con = to_sqlite(bd, clean=True)
        # Kiểm tra bảng được nạp
        cur = con.execute("SELECT COUNT(*) FROM t_01")
        assert cur.fetchone()[0] == 2

        # Kiểm tra bảng metadata _table_map
        cur_map = con.execute("SELECT table_id, n_rows FROM _table_map")
        res_map = cur_map.fetchall()
        assert res_map == [("t_01", 2)]

        # Kiểm tra các index được tạo tự động
        cur_idx = con.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [r[0] for r in cur_idx.fetchall()]
        assert any("order" in idx for idx in indexes)
        assert any("date" in idx for idx in indexes)
        assert any("sku" in idx for idx in indexes)
        assert any("customer" in idx for idx in indexes)

    def test_sqlite_mirror_caching(self):
        df = pd.DataFrame({"colA": ["1", "2"]})
        t1 = TableInfo(
            table_id="t_01",
            source_file=Path("f.csv"),
            fixed_file_name="f.csv",
            sheet_name=None,
            df=df,
            header_row_detected=0,
            n_rows=2,
            columns=["colA"],
        )
        bd = BusinessData(business_id="biz_cached", tables=[t1])

        con1 = get_sqlite_mirror(bd, use_cache=True)
        con2 = get_sqlite_mirror(bd, use_cache=True)

        # Cùng trả về 1 instance connection từ cache
        assert con1 is con2

