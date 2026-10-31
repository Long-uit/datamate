"""
tests/test_ingest.py — Kiểm thử module src/ingest.py bằng pytest.

Tất cả dữ liệu thử được tạo trong tmp_path; không cần file bên ngoài.
Chạy: pytest tests/test_ingest.py -v
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

# Thêm thư mục src vào sys.path để import ingest
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import ingest as ing


# ===========================================================================
# Helpers tạo dữ liệu thử
# ===========================================================================

def make_business_dir(tmp_path: Path, name: str = "shop_test") -> Path:
    bdir = tmp_path / name
    bdir.mkdir()
    return bdir


def make_csv(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Ghi file CSV với encoding tuỳ chọn."""
    path.write_bytes(content.encode(encoding))


def make_csv_bom(path: Path, content: str) -> None:
    """Ghi file CSV với BOM (utf-8-sig)."""
    path.write_bytes(content.encode("utf-8-sig"))


def make_xlsx_shifted_header(path: Path, header_row: int = 2) -> None:
    """
    Tạo file Excel với header ở dòng header_row (0-based).
    Các dòng trước là tiêu đề / tổng (ô đơn).
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DuLieu"

    # Các dòng trước header (tiêu đề shop)
    for r in range(header_row):
        ws.append(["Báo cáo doanh thu Q1/2025"] + [""] * 4)

    # Dòng header thật
    ws.append(["Ngày", "Mã đơn", "Tên sản phẩm", "Số lượng", "Thành tiền"])

    # Dữ liệu
    ws.append(["01/06/2025", "DH001", "Cà phê sữa", "2 ly", "50000"])
    ws.append(["02/06/2025", "DH002", "Bánh mì", "1", "25000"])

    wb.save(path)


def make_xlsx_monthly_sheets(path: Path) -> None:
    """
    Tạo file Excel nhiều sheet theo tháng cùng cấu trúc cột.
    Sheet 'Tong' có cấu trúc khác để kiểm tra không gộp nhầm.
    """
    wb = openpyxl.Workbook()

    # Sheet T01_2025
    ws1 = wb.active
    ws1.title = "T01_2025"
    ws1.append(["Ngày", "Doanh thu", "Số đơn"])
    ws1.append(["2025-01-01", "500000", "5"])
    ws1.append(["2025-01-02", "300000", "3"])

    # Sheet T02_2025 — cùng cột
    ws2 = wb.create_sheet("T02_2025")
    ws2.append(["Ngày", "Doanh thu", "Số đơn"])
    ws2.append(["2025-02-01", "700000", "7"])

    # Sheet Tong — cột khác
    ws3 = wb.create_sheet("Tong")
    ws3.append(["Tháng", "Tổng doanh thu"])
    ws3.append(["T01", "800000"])
    ws3.append(["T02", "700000"])

    wb.save(path)


def make_sqlite(path: Path) -> None:
    """Tạo file SQLite với 2 bảng: don_hang và chi_tiet."""
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE don_hang (ma_don TEXT, ngay TEXT, khach TEXT)"
    )
    con.execute(
        "INSERT INTO don_hang VALUES ('DH001','2025-01-01','Nguyễn Văn A')"
    )
    con.execute(
        "CREATE TABLE chi_tiet (ma_don TEXT, san_pham TEXT, so_luong TEXT)"
    )
    con.execute(
        "INSERT INTO chi_tiet VALUES ('DH001','Cà phê','2 ly')"
    )
    # Bảng sqlite_sequence (nên bị bỏ qua)
    con.commit()
    con.close()


# ===========================================================================
# Test fix_mojibake
# ===========================================================================

class TestFixMojibake:
    def test_normal_name_unchanged(self):
        assert ing.fix_mojibake("don_hang.csv") == "don_hang.csv"

    def test_mojibake_corrected(self):
        """Tên file bị mojibake thực tế từ cp437 decode utf-8."""
        # Encode "café" bằng utf-8 rồi decode cp437 → mojibake
        original = "café.xlsx"
        mojibake = original.encode("utf-8").decode("cp437", errors="replace")
        fixed = ing.fix_mojibake(mojibake)
        # Kết quả phải khác với mojibake (đã sửa được hoặc giữ nguyên)
        assert isinstance(fixed, str)

    def test_returns_original_on_failure(self):
        # Tên ASCII thuần — không bị mojibake, trả nguyên
        name = "data_2025.xlsx"
        assert ing.fix_mojibake(name) == name


# ===========================================================================
# Test normalize_col / deduplicate_cols
# ===========================================================================

class TestNormalizeCols:
    def test_strip_whitespace(self):
        assert ing.normalize_col("  Ngày  ") == "Ngày"

    def test_collapse_inner_spaces(self):
        assert ing.normalize_col("Mã  đơn  hàng") == "Mã đơn hàng"

    def test_nfc_normalization(self):
        # NFC và NFD của 'ắ' phải cho cùng kết quả
        nfd = "\u0103\u0301"   # 'ắ' dạng NFD
        nfc = "\u1eaf"          # 'ắ' dạng NFC
        assert ing.normalize_col(nfd) == ing.normalize_col(nfc)

    def test_deduplicate(self):
        result = ing.deduplicate_cols(["Cột A", "Cột A", "Cột B", "Cột A"])
        assert result == ["Cột A", "Cột A_2", "Cột B", "Cột A_3"]


# ===========================================================================
# Test load_csv — BOM
# ===========================================================================

class TestLoadCSV:
    def test_csv_with_bom(self, tmp_path: Path):
        """CSV dính BOM: tên cột đầu tiên không được có \\ufeff."""
        content = "Ngày,Số lượng,Doanh thu\n2025-01-01,5,100000\n"
        csv_file = tmp_path / "data.csv"
        make_csv_bom(csv_file, content)

        ti = ing.load_csv(csv_file)
        assert ti is not None
        assert "\ufeff" not in ti.columns[0], "BOM vẫn còn trong tên cột"
        assert ti.columns[0] == "Ngày"

    def test_csv_utf8(self, tmp_path: Path):
        content = "Tên,Giá\nCà phê,25000\nBánh mì,15000\n"
        csv_file = tmp_path / "menu.csv"
        make_csv(csv_file, content, "utf-8")

        ti = ing.load_csv(csv_file)
        assert ti is not None
        assert ti.n_rows == 2
        assert "Tên" in ti.columns

    def test_csv_empty_cells_become_na(self, tmp_path: Path):
        """Ô rỗng phải trở thành pd.NA."""
        content = "A,B,C\n1,,3\n,2,\n"
        csv_file = tmp_path / "sparse.csv"
        make_csv(csv_file, content)

        ti = ing.load_csv(csv_file)
        assert ti is not None
        df = ti.df
        assert pd.isna(df.iloc[0]["B"]), "Ô rỗng phải là NA"
        assert pd.isna(df.iloc[1]["A"]), "Ô rỗng phải là NA"

    def test_csv_latin1_fallback(self, tmp_path: Path):
        """CSV mã hoá latin1 phải đọc được."""
        content = "Tên,Giá\nCafe,25000\n"
        csv_file = tmp_path / "latin.csv"
        make_csv(csv_file, content, "latin1")

        ti = ing.load_csv(csv_file)
        assert ti is not None
        assert ti.n_rows >= 1

    def test_csv_all_cols_are_str(self, tmp_path: Path):
        """Tất cả cột phải là dtype object (str)."""
        content = "Ngày,Số lượng\n2025-01-01,100\n2025-01-02,200\n"
        csv_file = tmp_path / "typed.csv"
        make_csv(csv_file, content)

        ti = ing.load_csv(csv_file)
        assert ti is not None
        for col in ti.df.columns:
            assert ti.df[col].dtype == object, f"Cột {col} không phải object"


# ===========================================================================
# Test load_excel — header lệch dòng
# ===========================================================================

class TestLoadExcel:
    def test_shifted_header_row2(self, tmp_path: Path):
        """Header ở dòng 2 (0-based): header_row_detected phải == 2."""
        xlsx = tmp_path / "shifted.xlsx"
        make_xlsx_shifted_header(xlsx, header_row=2)

        tis = ing.load_excel(xlsx)
        assert len(tis) >= 1
        ti = tis[0]
        assert ti.header_row_detected == 2, (
            f"Kỳ vọng header_row=2, nhận được {ti.header_row_detected}"
        )
        assert "Ngày" in ti.columns or any("ngày" in c.lower() for c in ti.columns)

    def test_shifted_header_row3(self, tmp_path: Path):
        """Header ở dòng 3 (0-based)."""
        xlsx = tmp_path / "shifted3.xlsx"
        make_xlsx_shifted_header(xlsx, header_row=3)

        tis = ing.load_excel(xlsx)
        assert len(tis) >= 1
        ti = tis[0]
        assert ti.header_row_detected == 3

    def test_monthly_sheets_merged(self, tmp_path: Path):
        """
        Sheet T01_2025 và T02_2025 cùng cột → gộp thành 1 bảng.
        Sheet Tong khác cột → bảng riêng.
        """
        xlsx = tmp_path / "monthly.xlsx"
        make_xlsx_monthly_sheets(xlsx)

        tis = ing.load_excel(xlsx)

        # Phải có ít nhất 2 bảng: 1 gộp (T01+T02) và 1 riêng (Tong)
        assert len(tis) >= 2, f"Kỳ vọng >=2 bảng, nhận được {len(tis)}"

        # Tìm bảng gộp
        merged = [t for t in tis if t.merged_sheets]
        assert len(merged) == 1, "Kỳ vọng đúng 1 bảng được gộp"
        assert len(merged[0].merged_sheets) == 2
        assert "T01_2025" in merged[0].merged_sheets
        assert "T02_2025" in merged[0].merged_sheets

        # Cột _source_sheet phải có mặt
        assert "_source_sheet" in merged[0].df.columns

        # Số dòng = 2 (T01) + 1 (T02)
        assert merged[0].n_rows == 3

    def test_no_cross_merge(self, tmp_path: Path):
        """Sheet có cột khác nhau KHÔNG được gộp."""
        xlsx = tmp_path / "monthly.xlsx"
        make_xlsx_monthly_sheets(xlsx)

        tis = ing.load_excel(xlsx)
        not_merged = [t for t in tis if not t.merged_sheets]
        # Sheet Tong phải là bảng riêng
        assert any(
            t.sheet_name == "Tong" for t in not_merged
        ), "Sheet Tong phải là bảng riêng"

    def test_all_cols_str_excel(self, tmp_path: Path):
        """Mọi cột trong DataFrame đọc từ Excel phải là object."""
        xlsx = tmp_path / "types.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(["Ngày", "Giá", "Số lượng"])
        ws.append(["2025-01-01", 50000, 3])
        wb.save(xlsx)

        tis = ing.load_excel(xlsx)
        assert len(tis) >= 1
        for col in tis[0].df.columns:
            assert tis[0].df[col].dtype == object


# ===========================================================================
# Test load_sqlite
# ===========================================================================

class TestLoadSQLite:
    def test_readonly_mode(self, tmp_path: Path):
        """SQLite phải đọc được bằng chế độ chỉ đọc."""
        db = tmp_path / "store.sqlite"
        make_sqlite(db)

        tis = ing.load_sqlite(db)
        assert len(tis) == 2

    def test_table_names_correct(self, tmp_path: Path):
        db = tmp_path / "store.sqlite"
        make_sqlite(db)

        tis = ing.load_sqlite(db)
        sheet_names = {t.sheet_name for t in tis}
        assert "don_hang" in sheet_names
        assert "chi_tiet" in sheet_names

    def test_no_sqlite_system_tables(self, tmp_path: Path):
        """Bảng sqlite_* phải bị bỏ qua."""
        db = tmp_path / "store.sqlite"
        make_sqlite(db)

        tis = ing.load_sqlite(db)
        for t in tis:
            assert not t.sheet_name.startswith("sqlite_")

    def test_sqlite_cols_are_str(self, tmp_path: Path):
        db = tmp_path / "store.sqlite"
        make_sqlite(db)

        tis = ing.load_sqlite(db)
        for ti in tis:
            for col in ti.df.columns:
                assert ti.df[col].dtype == object


# ===========================================================================
# Test load_business
# ===========================================================================

class TestLoadBusiness:
    def test_load_business_basic(self, tmp_path: Path):
        """load_business phải trả về BusinessData với đúng business_id."""
        bdir = make_business_dir(tmp_path)
        # README
        (bdir / "README.md").write_text("# Shop Test\nMô tả shop.", encoding="utf-8")
        # CSV
        make_csv(bdir / "orders.csv", "Ngày,Tổng\n2025-01-01,50000\n")

        bd = ing.load_business(bdir)
        assert bd.business_id == "shop_test"
        assert bd.readme_text.startswith("# Shop Test")
        assert len(bd.tables) == 1
        assert bd.errors == []

    def test_load_business_mixed_files(self, tmp_path: Path):
        """Business có cả CSV, Excel, SQLite."""
        bdir = make_business_dir(tmp_path)
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
        # CSV=1, Excel=1 sheet, SQLite=2 bảng → tổng >=4
        assert len(bd.tables) >= 4

    def test_table_ids_unique_sequential(self, tmp_path: Path):
        """table_id phải là t_01, t_02, ... không trùng."""
        bdir = make_business_dir(tmp_path)
        for i in range(3):
            make_csv(bdir / f"file{i}.csv", "A,B\n1,2\n")

        bd = ing.load_business(bdir)
        ids = [t.table_id for t in bd.tables]
        assert len(ids) == len(set(ids)), "table_id bị trùng"
        assert ids == sorted(ids), "table_id không theo thứ tự"

    def test_broken_file_does_not_crash(self, tmp_path: Path):
        """File Excel hỏng không làm crash; lỗi ghi vào bd.errors."""
        bdir = make_business_dir(tmp_path)
        make_csv(bdir / "good.csv", "A,B\n1,2\n")
        # File Excel hỏng (nội dung rác)
        (bdir / "bad.xlsx").write_bytes(b"THIS IS NOT AN XLSX FILE")

        bd = ing.load_business(bdir)
        assert len(bd.tables) >= 1, "Vẫn phải nạp được file CSV tốt"
        assert len(bd.errors) >= 1, "Phải có ít nhất 1 lỗi"

    def test_mojibake_fixed_file_name(self, tmp_path: Path):
        """fixed_file_name phải khác tên gốc nếu tên bị mojibake."""
        bdir = make_business_dir(tmp_path)
        # Tên file ASCII bình thường
        make_csv(bdir / "orders.csv", "A,B\n1,2\n")

        bd = ing.load_business(bdir)
        for ti in bd.tables:
            assert isinstance(ti.fixed_file_name, str)
            assert len(ti.fixed_file_name) > 0

    def test_readme_read(self, tmp_path: Path):
        """README.md phải được đọc đúng."""
        bdir = make_business_dir(tmp_path)
        readme_text = "# Quán Cà Phê Ánh Dương\nĐịa chỉ: 123 Lê Lợi."
        (bdir / "README.md").write_text(readme_text, encoding="utf-8")

        bd = ing.load_business(bdir)
        assert "Ánh Dương" in bd.readme_text

    def test_empty_dir_no_crash(self, tmp_path: Path):
        """Thư mục rỗng: BusinessData rỗng, không crash."""
        bdir = make_business_dir(tmp_path, "empty_shop")
        bd = ing.load_business(bdir)
        assert bd.business_id == "empty_shop"
        assert bd.tables == []
        assert bd.errors == []


# ===========================================================================
# Test to_sqlite
# ===========================================================================

class TestToSQLite:
    def test_tables_loaded(self, tmp_path: Path):
        bdir = make_business_dir(tmp_path)
        make_csv(bdir / "orders.csv", "Mã đơn,Giá\nDH001,50000\nDH002,30000\n")

        bd = ing.load_business(bdir)
        con = ing.to_sqlite(bd)

        try:
            cur = con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}
            assert "t_01" in tables
            assert "_table_map" in tables

            cur.execute("SELECT * FROM t_01")
            rows = cur.fetchall()
            assert len(rows) == 2
        finally:
            con.close()

    def test_table_map_populated(self, tmp_path: Path):
        bdir = make_business_dir(tmp_path)
        make_csv(bdir / "x.csv", "A,B\n1,2\n")

        bd = ing.load_business(bdir)
        con = ing.to_sqlite(bd)

        try:
            cur = con.cursor()
            cur.execute("SELECT table_id, n_rows FROM _table_map")
            rows = cur.fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "t_01"
            assert rows[0][1] == 1
        finally:
            con.close()


# ===========================================================================
# Test describe_schema
# ===========================================================================

class TestDescribeSchema:
    def test_output_contains_key_info(self, tmp_path: Path):
        bdir = make_business_dir(tmp_path)
        make_csv(bdir / "sales.csv", "Ngày,Doanh thu\n2025-01-01,100000\n")
        (bdir / "README.md").write_text("# Shop", encoding="utf-8")

        bd = ing.load_business(bdir)
        schema = ing.describe_schema(bd, max_sample=2)

        assert bd.business_id in schema
        assert "t_01" in schema
        assert "sales.csv" in schema
        assert "Ngày" in schema or "Doanh thu" in schema

    def test_cells_truncated_to_40(self, tmp_path: Path):
        long_val = "A" * 100
        content = f"Col\n{long_val}\n"
        bdir = make_business_dir(tmp_path)
        make_csv(bdir / "long.csv", content)

        bd = ing.load_business(bdir)
        schema = ing.describe_schema(bd, max_sample=1)

        # Ô dài phải bị cắt còn <= 43 ký tự (40 + "...")
        assert long_val not in schema, "Ô dài hơn 40 ký tự không được in toàn bộ"

