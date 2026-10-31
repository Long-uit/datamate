"""
ingest.py — Module nạp dữ liệu cho DataMate (Zalo AI Challenge 2026).

Đọc dữ liệu thô từ thư mục business (*.csv, *.xlsx, *.sqlite, README.md),
trả về BusinessData; không ghi file; không hard-code tên cột / tên file.
"""

from __future__ import annotations

import argparse
import io
import logging
import re
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import openpyxl
import pandas as pd

# ---------------------------------------------------------------------------
# Cấu hình logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stdout,
    format="%(levelname)s | %(message)s",
    level=logging.WARNING,
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hằng số
# ---------------------------------------------------------------------------
CSV_ENCODINGS = ["utf-8-sig", "utf-8", "cp1258", "cp1252", "latin1"]
HEADER_SEARCH_ROWS = 10          # Số dòng đầu dùng để dò header Excel
MIN_STR_RATIO = 0.50             # Tỷ lệ ô chuỗi tối thiểu của dòng header
CHUNK_SIZE = 50_000              # Chunk khi đọc CSV lớn


# ---------------------------------------------------------------------------
# Kiểu dữ liệu
# ---------------------------------------------------------------------------
@dataclass
class TableInfo:
    """Thông tin một bảng dữ liệu đã nạp."""
    table_id: str                    # t_01, t_02, ...
    source_file: Path                # Đường dẫn file gốc
    fixed_file_name: str             # Tên file sau khi sửa mojibake
    sheet_name: Optional[str]        # None với CSV / SQLite
    df: pd.DataFrame                 # Tất cả cột kiểu object (chuỗi)
    header_row_detected: Optional[int]  # Dòng header 0-index (None nếu không dò)
    n_rows: int
    columns: list[str]

    # Các sheet gộp vào bảng này (nếu có gộp theo tháng)
    merged_sheets: list[str] = field(default_factory=list)


@dataclass
class BusinessData:
    """Kết quả nạp một business."""
    business_id: str
    tables: list[TableInfo] = field(default_factory=list)
    readme_text: str = ""
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tiện ích chuỗi / tên cột
# ---------------------------------------------------------------------------

def fix_mojibake(name: str) -> str:
    """Thử sửa tên file bị mojibake (encode cp437/cp850 rồi decode utf-8)."""
    for enc in ("cp437", "cp850"):
        try:
            fixed = name.encode(enc).decode("utf-8")
            if fixed != name:
                return fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name


def normalize_col(name: str) -> str:
    """Chuẩn hoá tên cột: NFC, strip, gộp khoảng trắng; giữ dấu tiếng Việt."""
    name = unicodedata.normalize("NFC", str(name))
    name = re.sub(r"\s+", " ", name).strip()
    return name


def deduplicate_cols(cols: list[str]) -> list[str]:
    """Thêm hậu tố _2, _3... cho cột trùng tên."""
    seen: dict[str, int] = {}
    result: list[str] = []
    for c in cols:
        if c not in seen:
            seen[c] = 1
            result.append(c)
        else:
            seen[c] += 1
            result.append(f"{c}_{seen[c]}")
    return result


def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Áp dụng normalize_col + deduplicate_cols lên toàn bộ cột DataFrame."""
    df.columns = deduplicate_cols([normalize_col(c) for c in df.columns])
    return df


def _empty_to_na(df: pd.DataFrame) -> pd.DataFrame:
    """Chuyển chuỗi rỗng / chỉ khoảng trắng thành pd.NA."""
    return df.where(df.apply(lambda col: col.str.strip() != ""), other=pd.NA)


def _col_signature(df: pd.DataFrame) -> frozenset[str]:
    """Tập tên cột chuẩn hoá dùng để so sánh khi gộp sheet."""
    return frozenset(df.columns.tolist())


# ---------------------------------------------------------------------------
# Đọc README
# ---------------------------------------------------------------------------

def read_readme(business_dir: Path) -> str:
    """Đọc README.md (utf-8-sig, errors='replace'); trả về chuỗi rỗng nếu không có."""
    readme = business_dir / "README.md"
    if not readme.exists():
        return ""
    try:
        return readme.read_text(encoding="utf-8-sig", errors="replace")
    except Exception as exc:
        log.warning("Không đọc được README: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Đọc CSV
# ---------------------------------------------------------------------------

def _read_csv_single(path: Path) -> pd.DataFrame:
    """Đọc CSV thử từng encoding; trả về DataFrame mọi cột dạng str."""
    last_exc: Exception | None = None
    for enc in CSV_ENCODINGS:
        try:
            # Đọc theo chunk để xử lý file lớn
            chunks: list[pd.DataFrame] = []
            for chunk in pd.read_csv(
                path,
                encoding=enc,
                dtype=str,
                keep_default_na=False,
                chunksize=CHUNK_SIZE,
            ):
                chunks.append(chunk)
            df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
            if enc != "utf-8-sig" and enc != "utf-8":
                log.warning("CSV %s: dùng encoding %s", path.name, enc)
            return df
        except (UnicodeDecodeError, Exception) as exc:
            last_exc = exc
            continue
    raise ValueError(f"Không đọc được CSV {path}: {last_exc}") from last_exc


def load_csv(path: Path) -> TableInfo | None:
    """Nạp một file CSV thành TableInfo; trả None nếu lỗi (lỗi ghi ngoài)."""
    df = _read_csv_single(path)
    # Strip BOM khỏi tên cột đầu tiên
    if df.columns.size > 0:
        df.columns = pd.Index([
            c.lstrip("\ufeff") if i == 0 else c
            for i, c in enumerate(df.columns)
        ])
    df = normalize_cols(df)
    df = _empty_to_na(df)
    return TableInfo(
        table_id="",           # Gán sau
        source_file=path,
        fixed_file_name=fix_mojibake(path.name),
        sheet_name=None,
        df=df,
        header_row_detected=None,
        n_rows=len(df),
        columns=df.columns.tolist(),
    )


# ---------------------------------------------------------------------------
# Dò header Excel
# ---------------------------------------------------------------------------

def _detect_header_row(ws, max_rows: int = HEADER_SEARCH_ROWS) -> int:
    """
    Dò dòng header trong max_rows dòng đầu của sheet openpyxl.

    Heuristic: chọn dòng có nhiều ô chuỗi không rỗng nhất,
    tỷ lệ ô chuỗi >= MIN_STR_RATIO, và không phải tiêu đề đơn ô.
    Trả về chỉ số 0-based.
    """
    rows_data: list[list] = []
    for row in ws.iter_rows(max_row=max_rows, values_only=True):
        rows_data.append(list(row))

    if not rows_data:
        return 0

    best_row = 0
    best_score = -1

    for idx, row in enumerate(rows_data):
        non_empty = [c for c in row if c is not None and str(c).strip() != ""]
        if not non_empty:
            continue
        str_count = sum(1 for c in non_empty if isinstance(c, str))
        ratio = str_count / max(len(row), 1)
        # Bỏ qua dòng có < 2 ô không rỗng (tiêu đề đơn ô)
        if len(non_empty) < 2:
            continue
        score = len(non_empty) + (5 if ratio >= MIN_STR_RATIO else 0)
        if score > best_score:
            best_score = score
            best_row = idx

    return best_row


# ---------------------------------------------------------------------------
# Đọc Excel
# ---------------------------------------------------------------------------

def _read_sheet_with_header(ws, header_row: int) -> pd.DataFrame:
    """
    Đọc toàn bộ sheet; dùng dòng header_row (0-based) làm tên cột.
    Mọi giá trị chuyển thành str.
    """
    all_rows: list[list] = list(ws.iter_rows(values_only=True))
    if not all_rows or header_row >= len(all_rows):
        return pd.DataFrame()

    header = [
        str(c) if c is not None else ""
        for c in all_rows[header_row]
    ]
    data_rows = all_rows[header_row + 1:]
    df = pd.DataFrame(data_rows, columns=header)
    # Ép mọi ô thành str
    df = df.astype(str)
    # Xoá dòng / cột trống hoàn toàn
    df = df.replace({"None": pd.NA, "nan": pd.NA, "": pd.NA})
    df = df.dropna(how="all", axis=0).dropna(how="all", axis=1)
    df = df.reset_index(drop=True)
    # Trả về dạng object (str)
    df = df.astype(str).replace({"<NA>": pd.NA, "nan": pd.NA})
    return df


def load_excel(path: Path) -> list[TableInfo]:
    """
    Nạp tất cả sheet của file Excel.
    Gộp sheet cùng cấu trúc cột (theo tháng) thành một bảng.
    """
    fixed_name = fix_mojibake(path.name)
    results: list[TableInfo] = []

    # Mở workbook một lần (read_only để tiết kiệm RAM)
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(f"Không mở được workbook {path}: {exc}") from exc

    # Thu thập thông tin từng sheet
    sheet_tables: list[tuple[str, pd.DataFrame, int]] = []  # (sheet_name, df, header_row)
    try:
        for sheet_name in wb.sheetnames:
            try:
                ws = wb[sheet_name]
                header_row = _detect_header_row(ws)
                df = _read_sheet_with_header(ws, header_row)
                df = normalize_cols(df)
                df = _empty_to_na(df)
                sheet_tables.append((sheet_name, df, header_row))
            except Exception as exc:
                log.warning("Sheet '%s' trong %s: %s", sheet_name, path.name, exc)
    finally:
        wb.close()

    if not sheet_tables:
        return results

    # ------------------------------------------------------------------
    # Gộp sheet theo tháng: nhóm các sheet có cùng tập tên cột
    # ------------------------------------------------------------------
    sig_to_sheets: dict[frozenset, list[tuple[str, pd.DataFrame, int]]] = {}
    for sheet_name, df, hrow in sheet_tables:
        sig = _col_signature(df)
        sig_to_sheets.setdefault(sig, []).append((sheet_name, df, hrow))

    for sig, group in sig_to_sheets.items():
        if len(group) == 1:
            sheet_name, df, hrow = group[0]
            ti = TableInfo(
                table_id="",
                source_file=path,
                fixed_file_name=fixed_name,
                sheet_name=sheet_name,
                df=df,
                header_row_detected=hrow,
                n_rows=len(df),
                columns=df.columns.tolist(),
            )
            results.append(ti)
        else:
            # Gộp nhiều sheet cùng cấu trúc
            dfs: list[pd.DataFrame] = []
            merged_names: list[str] = []
            max_hrow = 0
            for sheet_name, df, hrow in group:
                df = df.copy()
                df["_source_sheet"] = sheet_name
                dfs.append(df)
                merged_names.append(sheet_name)
                max_hrow = max(max_hrow, hrow)
            merged_df = pd.concat(dfs, ignore_index=True)
            ti = TableInfo(
                table_id="",
                source_file=path,
                fixed_file_name=fixed_name,
                sheet_name=f"[gộp: {', '.join(merged_names[:3])}{'...' if len(merged_names) > 3 else ''}]",
                df=merged_df,
                header_row_detected=max_hrow,
                n_rows=len(merged_df),
                columns=merged_df.columns.tolist(),
                merged_sheets=merged_names,
            )
            results.append(ti)

    return results


# ---------------------------------------------------------------------------
# Đọc SQLite
# ---------------------------------------------------------------------------

def load_sqlite(path: Path) -> list[TableInfo]:
    """
    Nạp mọi bảng (trừ sqlite_*) từ file SQLite bằng chế độ chỉ đọc.
    Mọi cột đọc dạng str.
    """
    path = path.resolve()
    fixed_name = fix_mojibake(path.name)
    uri = path.as_uri() + "?mode=ro"
    results: list[TableInfo] = []

    try:
        con = sqlite3.connect(uri, uri=True)
    except Exception as exc:
        raise ValueError(f"Không mở được SQLite {path}: {exc}") from exc

    try:
        cur = con.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        table_names = [row[0] for row in cur.fetchall()]

        for tbl in table_names:
            try:
                df = pd.read_sql_query(
                    f'SELECT * FROM "{tbl}"', con, dtype=str
                )
                df = normalize_cols(df)
                df = _empty_to_na(df)
                results.append(TableInfo(
                    table_id="",
                    source_file=path,
                    fixed_file_name=fixed_name,
                    sheet_name=tbl,
                    df=df,
                    header_row_detected=None,
                    n_rows=len(df),
                    columns=df.columns.tolist(),
                ))
            except Exception as exc:
                log.warning("Bảng '%s' trong %s: %s", tbl, path.name, exc)
    finally:
        con.close()

    return results


# ---------------------------------------------------------------------------
# Hàm chính
# ---------------------------------------------------------------------------

def load_business(business_dir: Path) -> BusinessData:
    """
    Nạp toàn bộ dữ liệu của một business từ thư mục business_dir.

    Trả về BusinessData gồm: business_id, danh sách TableInfo,
    readme_text, và danh sách lỗi gặp phải (không làm crash).
    """
    business_id = business_dir.name
    bd = BusinessData(business_id=business_id)
    bd.readme_text = read_readme(business_dir)

    counter = 1  # Bộ đếm table_id

    def next_table_id() -> str:
        nonlocal counter
        tid = f"t_{counter:02d}"
        counter += 1
        return tid

    for fpath in sorted(business_dir.iterdir()):
        if not fpath.is_file():
            continue

        suffix = fpath.suffix.lower()

        # ---- CSV ----
        if suffix == ".csv":
            try:
                ti = load_csv(fpath)
                if ti is not None:
                    ti.table_id = next_table_id()
                    bd.tables.append(ti)
            except Exception as exc:
                bd.errors.append(f"CSV {fpath}: {exc}")

        # ---- Excel ----
        elif suffix in (".xlsx", ".xls", ".xlsm"):
            try:
                tis = load_excel(fpath)
                for ti in tis:
                    ti.table_id = next_table_id()
                    bd.tables.append(ti)
            except Exception as exc:
                bd.errors.append(f"Excel {fpath}: {exc}")

        # ---- SQLite ----
        elif suffix in (".sqlite", ".db", ".sqlite3"):
            try:
                tis = load_sqlite(fpath)
                for ti in tis:
                    ti.table_id = next_table_id()
                    bd.tables.append(ti)
            except Exception as exc:
                bd.errors.append(f"SQLite {fpath}: {exc}")

        # README đã đọc riêng
        elif fpath.name.lower() == "readme.md":
            continue

    return bd


# ---------------------------------------------------------------------------
# to_sqlite
# ---------------------------------------------------------------------------

def to_sqlite(business: BusinessData) -> sqlite3.Connection:
    """
    Nạp mọi bảng trong BusinessData vào SQLite in-memory.

    Tạo bảng _table_map(table_id, source_file, fixed_file_name, sheet_name, n_rows).
    Tên cột được quote bằng dấu ngoặc kép khi tạo bảng.
    Trả về sqlite3.Connection (caller chịu trách nhiệm đóng).
    """
    con = sqlite3.connect(":memory:")

    # Tạo bảng _table_map
    con.execute("""
        CREATE TABLE IF NOT EXISTS _table_map (
            table_id TEXT,
            source_file TEXT,
            fixed_file_name TEXT,
            sheet_name TEXT,
            n_rows INTEGER
        )
    """)

    for ti in business.tables:
        # Nạp DataFrame
        try:
            ti.df.to_sql(
                ti.table_id,
                con,
                if_exists="replace",
                index=False,
            )
        except Exception as exc:
            log.warning("to_sqlite: không nạp được %s: %s", ti.table_id, exc)
            continue

        # Ghi metadata
        con.execute(
            "INSERT INTO _table_map VALUES (?, ?, ?, ?, ?)",
            (
                ti.table_id,
                str(ti.source_file),
                ti.fixed_file_name,
                ti.sheet_name or "",
                ti.n_rows,
            ),
        )

    con.commit()
    return con


# ---------------------------------------------------------------------------
# describe_schema
# ---------------------------------------------------------------------------

def describe_schema(business: BusinessData, max_sample: int = 3) -> str:
    """
    Mô tả ngắn gọn từng bảng để đưa vào prompt LLM.

    Gồm: table_id, fixed_file_name, sheet, số dòng, danh sách cột,
    và tối đa max_sample dòng mẫu (ô cắt còn 40 ký tự).
    """
    buf = io.StringIO()
    buf.write(f"=== Business: {business.business_id} ===\n")
    if business.readme_text:
        snippet = business.readme_text[:300].replace("\n", " ")
        buf.write(f"README (300 ký tự đầu): {snippet}\n")
    buf.write(f"Tổng số bảng: {len(business.tables)}\n\n")

    for ti in business.tables:
        buf.write(f"[{ti.table_id}] {ti.fixed_file_name}")
        if ti.sheet_name:
            buf.write(f" | sheet: {ti.sheet_name}")
        buf.write(f" | {ti.n_rows} dòng")
        if ti.header_row_detected is not None:
            buf.write(f" | header dòng {ti.header_row_detected}")
        if ti.merged_sheets:
            buf.write(f" | gộp {len(ti.merged_sheets)} sheet")
        buf.write("\n")

        buf.write(f"  Cột ({len(ti.columns)}): {', '.join(ti.columns)}\n")

        if max_sample > 0 and not ti.df.empty:
            sample = ti.df.head(max_sample)
            for _, row in sample.iterrows():
                cells = []
                for c in ti.columns:
                    val = str(row.get(c, ""))
                    if len(val) > 40:
                        val = val[:37] + "..."
                    cells.append(val)
                buf.write("  | " + " | ".join(cells) + "\n")

        buf.write("\n")

    if business.errors:
        buf.write("=== LỖI ===\n")
        for err in business.errors:
            buf.write(f"  - {err}\n")

    return buf.getvalue()


# ---------------------------------------------------------------------------
# CLI __main__
# ---------------------------------------------------------------------------

def _cli() -> None:
    # Ép stdout/stderr sang UTF-8 để không lỗi ký tự tiếng Việt trên Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Nạp dữ liệu DataMate và in tóm tắt."
    )
    parser.add_argument(
        "--data_dir",
        type=Path,
        required=True,
        help="Thư mục gốc chứa các thư mục business (mỗi thư mục là một business_id).",
    )
    args = parser.parse_args()

    data_dir: Path = args.data_dir
    if not data_dir.exists():
        print(f"ERROR: Thư mục không tồn tại: {data_dir}", file=sys.stderr)
        sys.exit(1)

    # Tìm tất cả thư mục con (mỗi thư mục là một business)
    business_dirs = sorted(
        p for p in data_dir.iterdir() if p.is_dir()
    )
    if not business_dirs:
        # Thử coi data_dir chính là thư mục business
        business_dirs = [data_dir]

    total_tables = 0
    total_rows = 0

    for bdir in business_dirs:
        bd = load_business(bdir)
        n_tables = len(bd.tables)
        n_rows = sum(t.n_rows for t in bd.tables)
        total_tables += n_tables
        total_rows += n_rows

        status = f"✓" if not bd.errors else f"⚠ {len(bd.errors)} lỗi"
        print(
            f"{bd.business_id:<30} | {n_tables:>3} bảng | "
            f"{n_rows:>8,} dòng | {status}"
        )
        for err in bd.errors:
            print(f"   LỖI: {err}")

    print("-" * 70)
    print(f"TỔNG: {len(business_dirs)} business | {total_tables} bảng | {total_rows:,} dòng")


if __name__ == "__main__":
    _cli()

