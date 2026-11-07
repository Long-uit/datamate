"""
tests/ingestion_schema/test_loader.py — Kiểm thử nạp dữ liệu đa định dạng (CSV, XLSX, SQLite) của ingestion_schema.
Tương thích hoàn toàn với unittest chuẩn của Python.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent.parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import openpyxl
import pandas as pd

import datamate.ingestion_schema.loader as ing


# ===========================================================================
# Helpers tạo dữ liệu thử
# ===========================================================================

def make_business_dir(tmp_path: Path, name: str = "shop_test") -> Path:
    bdir = tmp_path / name
    bdir.mkdir(parents=True, exist_ok=True)
    return bdir


def make_csv(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.write_bytes(content.encode(encoding))


def make_csv_bom(path: Path, content: str) -> None:
    path.write_bytes(content.encode("utf-8-sig"))


def make_xlsx_shifted_header(path: Path, header_row: int = 2) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DuLieu"
    for r in range(header_row):
        ws.append(["Báo cáo doanh thu Q1/2025"] + [""] * 4)
    ws.append(["Ngày", "Mã đơn", "Tên sản phẩm", "Số lượng", "Thành tiền"])
    ws.append(["01/06/2025", "DH001", "Cà phê sữa", "2 ly", "50000"])
    ws.append(["02/06/2025", "DH002", "Bánh mì", "1", "25000"])
    wb.save(path)


def make_xlsx_monthly_sheets(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "T01_2025"
    ws1.append(["Ngày", "Doanh thu", "Số đơn"])
    ws1.append(["2025-01-01", "500000", "5"])
    ws1.append(["2025-01-02", "300000", "3"])

    ws2 = wb.create_sheet("T02_2025")
    ws2.append(["Ngày", "Doanh thu", "Số đơn"])
    ws2.append(["2025-02-01", "700000", "7"])

    ws3 = wb.create_sheet("Tong")
    ws3.append(["Tháng", "Tổng doanh thu"])
    ws3.append(["T01", "800000"])
    ws3.append(["T02", "700000"])
    wb.save(path)


def make_sqlite(path: Path) -> None:
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE don_hang (ma_don TEXT, ngay TEXT, khach TEXT)")
    con.execute("INSERT INTO don_hang VALUES ('DH001','2025-01-01','Nguyễn Văn A')")
    con.execute("CREATE TABLE chi_tiet (ma_don TEXT, san_pham TEXT, so_luong TEXT)")
    con.execute("INSERT INTO chi_tiet VALUES ('DH001','Cà phê','2 ly')")
    con.commit()
    con.close()


class BaseTempTestCase(unittest.TestCase):
    def setUp(self):
        self._temp_dir_obj = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._temp_dir_obj.name)

    def tearDown(self):
        self._temp_dir_obj.cleanup()


class TestFixMojibake(unittest.TestCase):
    def test_normal_name_unchanged(self):
        self.assertEqual(ing.fix_mojibake("don_hang.csv"), "don_hang.csv")

    def test_mojibake_corrected(self):
        original = "café.xlsx"
        mojibake = original.encode("utf-8").decode("cp437", errors="replace")
        fixed = ing.fix_mojibake(mojibake)
        self.assertIsInstance(fixed, str)

    def test_returns_original_on_failure(self):
        name = "data_2025.xlsx"
        self.assertEqual(ing.fix_mojibake(name), name)


class TestNormalizeCols(unittest.TestCase):
    def test_strip_whitespace(self):
        self.assertEqual(ing.normalize_col("  Ngày  "), "Ngày")

    def test_collapse_inner_spaces(self):
        self.assertEqual(ing.normalize_col("Mã  đơn  hàng"), "Mã đơn hàng")

    def test_nfc_normalization(self):
        nfd = "\u0103\u0301"
        nfc = "\u1eaf"
        self.assertEqual(ing.normalize_col(nfd), ing.normalize_col(nfc))

    def test_deduplicate(self):
        result = ing.deduplicate_cols(["Cột A", "Cột A", "Cột B", "Cột A"])
        self.assertEqual(result, ["Cột A", "Cột A_2", "Cột B", "Cột A_3"])


class TestLoadCSV(BaseTempTestCase):
    def test_csv_with_bom(self):
        content = "Ngày,Số lượng,Doanh thu\n2025-01-01,5,100000\n"
        csv_file = self.tmp_path / "data.csv"
        make_csv_bom(csv_file, content)

        ti = ing.load_csv(csv_file)
        self.assertIsNotNone(ti)
        self.assertNotIn("\ufeff", ti.columns[0])
        self.assertEqual(ti.columns[0], "Ngày")

    def test_csv_utf8(self):
        content = "Tên,Giá\nCà phê,25000\nBánh mì,15000\n"
        csv_file = self.tmp_path / "menu.csv"
        make_csv(csv_file, content, "utf-8")

        ti = ing.load_csv(csv_file)
        self.assertIsNotNone(ti)
        self.assertEqual(ti.n_rows, 2)
        self.assertIn("Tên", ti.columns)

    def test_csv_empty_cells_become_na(self):
        content = "A,B,C\n1,,3\n,2,\n"
        csv_file = self.tmp_path / "sparse.csv"
        make_csv(csv_file, content)

        ti = ing.load_csv(csv_file)
        self.assertIsNotNone(ti)
        df = ti.df
        self.assertTrue(pd.isna(df.iloc[0]["B"]))
        self.assertTrue(pd.isna(df.iloc[1]["A"]))

    def test_csv_latin1_fallback(self):
        content = "Tên,Giá\nCafe,25000\n"
        csv_file = self.tmp_path / "latin.csv"
        make_csv(csv_file, content, "latin1")

        ti = ing.load_csv(csv_file)
        self.assertIsNotNone(ti)
        self.assertGreaterEqual(ti.n_rows, 1)

    def test_csv_all_cols_are_str(self):
        content = "Ngày,Số lượng\n2025-01-01,100\n2025-01-02,200\n"
        csv_file = self.tmp_path / "typed.csv"
        make_csv(csv_file, content)

        ti = ing.load_csv(csv_file)
        self.assertIsNotNone(ti)
        for col in ti.df.columns:
            self.assertEqual(ti.df[col].dtype, object)


class TestLoadExcel(BaseTempTestCase):
    def test_shifted_header_row2(self):
        xlsx = self.tmp_path / "shifted.xlsx"
        make_xlsx_shifted_header(xlsx, header_row=2)

        tis = ing.load_excel(xlsx)
        self.assertGreaterEqual(len(tis), 1)
        self.assertEqual(tis[0].header_row_detected, 2)
        self.assertTrue("Ngày" in tis[0].columns or any("ngày" in c.lower() for c in tis[0].columns))

    def test_shifted_header_row3(self):
        xlsx = self.tmp_path / "shifted3.xlsx"
        make_xlsx_shifted_header(xlsx, header_row=3)

        tis = ing.load_excel(xlsx)
        self.assertGreaterEqual(len(tis), 1)
        self.assertEqual(tis[0].header_row_detected, 3)

    def test_monthly_sheets_merged(self):
        xlsx = self.tmp_path / "monthly.xlsx"
        make_xlsx_monthly_sheets(xlsx)

        tis = ing.load_excel(xlsx)
        self.assertGreaterEqual(len(tis), 2)

        merged = [t for t in tis if t.merged_sheets]
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0].merged_sheets), 2)
        self.assertIn("T01_2025", merged[0].merged_sheets)
        self.assertIn("T02_2025", merged[0].merged_sheets)
        self.assertIn("_source_sheet", merged[0].df.columns)
        self.assertEqual(merged[0].n_rows, 3)

    def test_no_cross_merge(self):
        xlsx = self.tmp_path / "monthly.xlsx"
        make_xlsx_monthly_sheets(xlsx)

        tis = ing.load_excel(xlsx)
        not_merged = [t for t in tis if not t.merged_sheets]
        self.assertTrue(any(t.sheet_name == "Tong" for t in not_merged))

    def test_excel_column_mismatch_padded(self):
        xlsx = self.tmp_path / "mismatch.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(["Mã đơn", "Ngày", "Tiền", "Ghi chú"])
        ws.append(["ORD01", "2025-01-01", 100000])
        ws.append(["ORD02", "2025-01-02", 200000, "Có ghi chú"])
        wb.save(xlsx)

        tis = ing.load_excel(xlsx)
        self.assertEqual(len(tis), 1)
        df = tis[0].df
        self.assertEqual(len(df), 2)
        self.assertIn("Ghi chú", df.columns)
        self.assertTrue(pd.isna(df.iloc[0]["Ghi chú"]))
        self.assertEqual(df.iloc[1]["Ghi chú"], "Có ghi chú")

    def test_all_cols_str_excel(self):
        xlsx = self.tmp_path / "types.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(["Ngày", "Giá", "Số lượng"])
        ws.append(["2025-01-01", 50000, 3])
        wb.save(xlsx)

        tis = ing.load_excel(xlsx)
        self.assertGreaterEqual(len(tis), 1)
        for col in tis[0].df.columns:
            self.assertEqual(tis[0].df[col].dtype, object)


class TestLoadSQLite(BaseTempTestCase):
    def test_readonly_mode(self):
        db = self.tmp_path / "store.sqlite"
        make_sqlite(db)

        tis = ing.load_sqlite(db)
        self.assertEqual(len(tis), 2)

    def test_table_names_correct(self):
        db = self.tmp_path / "store.sqlite"
        make_sqlite(db)

        tis = ing.load_sqlite(db)
        sheet_names = {t.sheet_name for t in tis}
        self.assertIn("don_hang", sheet_names)
        self.assertIn("chi_tiet", sheet_names)

    def test_no_sqlite_system_tables(self):
        db = self.tmp_path / "store.sqlite"
        make_sqlite(db)

        tis = ing.load_sqlite(db)
        for t in tis:
            self.assertFalse(t.sheet_name.startswith("sqlite_"))

    def test_sqlite_cols_are_str(self):
        db = self.tmp_path / "store.sqlite"
        make_sqlite(db)

        tis = ing.load_sqlite(db)
        for ti in tis:
            for col in ti.df.columns:
                self.assertEqual(ti.df[col].dtype, object)


class TestLoadBusiness(BaseTempTestCase):
    def test_load_business_basic(self):
        bdir = make_business_dir(self.tmp_path)
        (bdir / "README.md").write_text("# Shop Test\nMô tả shop.", encoding="utf-8")
        make_csv(bdir / "orders.csv", "Ngày,Tổng\n2025-01-01,50000\n")

        bd = ing.load_business(bdir)
        self.assertEqual(bd.business_id, "shop_test")
        self.assertTrue(bd.readme_text.startswith("# Shop Test"))
        self.assertEqual(len(bd.tables), 1)
        self.assertEqual(bd.errors, [])

    def test_load_business_mixed_files(self):
        bdir = make_business_dir(self.tmp_path)
        make_csv(bdir / "a.csv", "X,Y\n1,2\n3,4\n")

        xlsx = bdir / "b.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Data"
        ws.append(["A", "B"])
        ws.append(["x", "y"])
        wb.save(xlsx)

        make_sqlite(bdir / "c.sqlite")

        bd = ing.load_business(bdir)
        self.assertGreaterEqual(len(bd.tables), 4)

    def test_table_ids_unique_sequential(self):
        bdir = make_business_dir(self.tmp_path)
        for i in range(3):
            make_csv(bdir / f"file{i}.csv", "A,B\n1,2\n")

        bd = ing.load_business(bdir)
        ids = [t.table_id for t in bd.tables]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, sorted(ids))

    def test_broken_file_does_not_crash(self):
        bdir = make_business_dir(self.tmp_path)
        make_csv(bdir / "good.csv", "A,B\n1,2\n")
        (bdir / "bad.xlsx").write_bytes(b"THIS IS NOT AN XLSX FILE")

        bd = ing.load_business(bdir)
        self.assertGreaterEqual(len(bd.tables), 1)
        self.assertGreaterEqual(len(bd.errors), 1)

    def test_readme_read(self):
        bdir = make_business_dir(self.tmp_path)
        (bdir / "README.md").write_text("# Quán Cà Phê Ánh Dương\nĐịa chỉ: 123 Lê Lợi.", encoding="utf-8")

        bd = ing.load_business(bdir)
        self.assertIn("Ánh Dương", bd.readme_text)

    def test_empty_dir_no_crash(self):
        bdir = make_business_dir(self.tmp_path, "empty_shop")
        bd = ing.load_business(bdir)
        self.assertEqual(bd.business_id, "empty_shop")
        self.assertEqual(bd.tables, [])
        self.assertEqual(bd.errors, [])


class TestToSQLite(BaseTempTestCase):
    def test_tables_loaded(self):
        bdir = make_business_dir(self.tmp_path)
        make_csv(bdir / "orders.csv", "Mã đơn,Giá\nDH001,50000\nDH002,30000\n")

        bd = ing.load_business(bdir)
        con = ing.to_sqlite(bd)

        try:
            cur = con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}
            self.assertIn("t_01", tables)
            self.assertIn("_table_map", tables)

            cur.execute("SELECT * FROM t_01")
            rows = cur.fetchall()
            self.assertEqual(len(rows), 2)
        finally:
            con.close()

    def test_table_map_populated(self):
        bdir = make_business_dir(self.tmp_path)
        make_csv(bdir / "x.csv", "A,B\n1,2\n")

        bd = ing.load_business(bdir)
        con = ing.to_sqlite(bd)

        try:
            cur = con.cursor()
            cur.execute("SELECT table_id, n_rows FROM _table_map")
            rows = cur.fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "t_01")
            self.assertEqual(rows[0][1], 1)
        finally:
            con.close()


class TestDescribeSchema(BaseTempTestCase):
    def test_output_contains_key_info(self):
        bdir = make_business_dir(self.tmp_path)
        make_csv(bdir / "sales.csv", "Ngày,Doanh thu\n2025-01-01,100000\n")
        (bdir / "README.md").write_text("# Shop", encoding="utf-8")

        bd = ing.load_business(bdir)
        schema = ing.describe_schema(bd, max_sample=2)

        self.assertIn(bd.business_id, schema)
        self.assertIn("t_01", schema)
        self.assertIn("sales.csv", schema)
        self.assertTrue("Ngày" in schema or "Doanh thu" in schema)

    def test_cells_truncated_to_40(self):
        long_val = "A" * 100
        content = f"Col\n{long_val}\n"
        bdir = make_business_dir(self.tmp_path)
        make_csv(bdir / "long.csv", content)

        bd = ing.load_business(bdir)
        schema = ing.describe_schema(bd, max_sample=1)
        self.assertNotIn(long_val, schema)


if __name__ == "__main__":
    unittest.main()

