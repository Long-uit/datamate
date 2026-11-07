"""
test_sqlite_mirror.py — Kiểm thử In-Memory SQLite Mirror, lập chỉ mục và Cache (ingestion_schema).
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
from datamate.ingestion_schema.sqlite_mirror import (
    clear_sqlite_cache,
    create_indexes,
    get_sqlite_mirror,
    to_sqlite,
)


class TestSQLiteMirror(unittest.TestCase):
    def setUp(self):
        clear_sqlite_cache()

    def tearDown(self):
        clear_sqlite_cache()

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
        cur = con.execute("SELECT COUNT(*) FROM t_01")
        self.assertEqual(cur.fetchone()[0], 2)

        cur_map = con.execute("SELECT table_id, n_rows FROM _table_map")
        res_map = cur_map.fetchall()
        self.assertEqual(res_map, [("t_01", 2)])

        cur_idx = con.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [r[0] for r in cur_idx.fetchall()]
        self.assertTrue(any("order" in idx for idx in indexes))
        self.assertTrue(any("date" in idx for idx in indexes))
        self.assertTrue(any("sku" in idx for idx in indexes))
        self.assertTrue(any("customer" in idx for idx in indexes))

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
        self.assertIs(con1, con2)


if __name__ == "__main__":
    unittest.main()

