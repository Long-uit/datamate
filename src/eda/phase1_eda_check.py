import os
import sys
import json
import sqlite3
import argparse
from pathlib import Path
from typing import Dict, List, Any

# Ép stdout console Windows sang UTF-8 để tránh UnicodeEncodeError
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import pandas as pd
except ImportError:
    print("[ERROR] pandas chưa được cài đặt. Vui lòng chạy: pip install pandas openpyxl")
    sys.exit(1)

try:
    import openpyxl
except ImportError:
    openpyxl = None


def check_sqlite(file_path: Path) -> Dict[str, Any]:
    """Kiểm tra file SQLite chi tiết: bảng, views, indexes, số dòng, cột, types, PK/FK.
    Dùng Path.as_uri() + '?mode=ro' để an toàn tuyệt đối với đường dẫn có khoảng trắng trên Windows.
    """
    result = {"status": "OK", "tables": {}, "views": [], "indexes": [], "error": None}
    try:
        uri = f"{file_path.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        cursor = conn.cursor()

        # Lấy views và indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='view';")
        result["views"] = [r[0] for r in cursor.fetchall()]

        cursor.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_autoindex%';")
        result["indexes"] = [f"{r[0]} ({r[1]})" for r in cursor.fetchall()]

        # Lấy tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            tbl_info: Dict[str, Any] = {"rows": 0, "columns": [], "pk": [], "fk": []}
            try:
                cursor.execute(f'SELECT COUNT(*) FROM "{table}";')
                tbl_info["rows"] = cursor.fetchone()[0]
            except Exception as e:
                tbl_info["rows"] = f"Error: {e}"

            try:
                cursor.execute(f'PRAGMA table_info("{table}");')
                for col in cursor.fetchall():
                    c_name, c_type, is_pk = col[1], col[2], col[5]
                    tbl_info["columns"].append(f"{c_name} ({c_type or 'ANY'})")
                    if is_pk:
                        tbl_info["pk"].append(c_name)
            except Exception:
                pass

            try:
                cursor.execute(f'PRAGMA foreign_key_list("{table}");')
                for fk in cursor.fetchall():
                    tbl_info["fk"].append(f"{fk[3]} -> {fk[2]}.{fk[4]}")
            except Exception:
                pass

            result["tables"][table] = tbl_info

        conn.close()
    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
    return result


def check_csv(file_path: Path) -> Dict[str, Any]:
    """Kiểm tra CSV: ưu tiên utf-8-sig trước, cảnh báo nếu dùng encoding khác, đọc đếm dòng bằng chunk."""
    result = {
        "status": "OK",
        "encoding": "utf-8",
        "row_count": 0,
        "col_count": 0,
        "columns": [],
        "warnings": [],
        "dtypes": {},
        "error": None,
    }
    encodings = ["utf-8-sig", "utf-8", "latin1", "cp1252", "cp1258"]
    loaded = False
    chosen_enc = None

    for enc in encodings:
        try:
            sample_df = pd.read_csv(file_path, encoding=enc, nrows=10)
            chosen_enc = enc
            loaded = True
            break
        except Exception:
            continue

    if not loaded:
        result["status"] = "ERROR"
        result["error"] = "Không thể đọc CSV với các encoding phổ biến"
        return result

    result["encoding"] = chosen_enc
    if chosen_enc not in ("utf-8", "utf-8-sig"):
        result["warnings"].append(f"CẢNH BÁO: Dùng encoding không chuẩn UTF-8 ({chosen_enc})")

    # Kiểm tra BOM hoặc khoảng trắng thừa ở cột
    raw_cols = list(sample_df.columns)
    for c in raw_cols:
        col_str = str(c)
        if "\ufeff" in col_str:
            result["warnings"].append(f"Cột '{col_str}' dính BOM (\\ufeff)")
        if col_str != col_str.strip():
            result["warnings"].append(f"Cột '{col_str}' có khoảng trắng thừa ở đầu/cuối")

    result["columns"] = [str(c).strip() for c in raw_cols]
    result["col_count"] = len(result["columns"])

    # Đếm dòng và suy luận dtypes bằng chunking
    total_rows = 0
    try:
        dtypes_dict = {}
        for chunk in pd.read_csv(file_path, encoding=chosen_enc, chunksize=20000, low_memory=False):
            total_rows += len(chunk)
            if not dtypes_dict:
                dtypes_dict = {str(k): str(v) for k, v in chunk.dtypes.items()}
        result["row_count"] = total_rows
        result["dtypes"] = dtypes_dict
    except Exception as e:
        result["warnings"].append(f"Lỗi khi đếm dòng qua chunk: {e}")
        try:
            with open(file_path, "r", encoding=chosen_enc, errors="ignore") as f:
                result["row_count"] = max(0, sum(1 for _ in f) - 1)
        except Exception as e2:
            result["row_count"] = f"Error: {e2}"

    if result["warnings"]:
        result["status"] = "WARNING"
    return result


def check_excel(file_path: Path) -> Dict[str, Any]:
    """Kiểm tra Excel: mở openpyxl 1 lần duy nhất cho cả workbook; đếm dòng thực tế và dò header lệch."""
    result = {"status": "OK", "sheets": {}, "warnings": [], "error": None}
    wb = None
    sheet_max_rows = {}
    if openpyxl:
        try:
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            for sname in wb.sheetnames:
                ws = wb[sname]
                sheet_max_rows[sname] = max(0, (ws.max_row or 1) - 1)
        except Exception:
            pass
        finally:
            if wb:
                try:
                    wb.close()
                except Exception:
                    pass

    try:
        excel_file = pd.ExcelFile(file_path)
        for sheet_name in excel_file.sheet_names:
            sheet_info: Dict[str, Any] = {
                "rows": sheet_max_rows.get(sheet_name, 0),
                "cols": 0,
                "columns": [],
                "unnamed_cols": [],
                "header_shift_detected": False,
                "detected_header_row": None,
            }

            try:
                head_df = pd.read_excel(excel_file, sheet_name=sheet_name, nrows=10, header=0)
                sheet_info["cols"] = len(head_df.columns)
                sheet_info["columns"] = [str(c) for c in head_df.columns]

                unnamed = [c for c in sheet_info["columns"] if "Unnamed:" in c]
                sheet_info["unnamed_cols"] = unnamed

                if unnamed:
                    result["warnings"].append(f"Sheet '{sheet_name}' có {len(unnamed)} cột Unnamed (nghi lệch header hoặc merged cells)")
                    sheet_info["header_shift_detected"] = True

                    # Dò header hợp lý trong 10 dòng đầu
                    raw_sample = pd.read_excel(excel_file, sheet_name=sheet_name, nrows=10, header=None)
                    best_row = None
                    max_non_null = 0
                    for r_idx in range(len(raw_sample)):
                        row_vals = raw_sample.iloc[r_idx]
                        str_count = sum(1 for v in row_vals if isinstance(v, str) and v.strip())
                        if str_count > max_non_null and str_count >= len(row_vals) * 0.4:
                            max_non_null = str_count
                            best_row = r_idx

                    if best_row is not None and best_row > 0:
                        sheet_info["detected_header_row"] = best_row
                        result["warnings"].append(f"Dò thấy dòng {best_row + 1} (index {best_row}) có thể là header thực sự của sheet '{sheet_name}'")
            except Exception as e:
                sheet_info["error"] = str(e)

            result["sheets"][sheet_name] = sheet_info

    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)

    if result["warnings"] and result["status"] == "OK":
        result["status"] = "WARNING"
    return result


def check_jsonl(file_path: Path) -> Dict[str, Any]:
    """Kiểm tra JSONL: đếm số bản ghi, kiểm tra cú pháp JSON từng dòng."""
    result = {"status": "OK", "total_lines": 0, "valid_json": 0, "sample_keys": [], "error": None}
    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                result["total_lines"] += 1
                try:
                    data = json.loads(line)
                    result["valid_json"] += 1
                    if idx == 0 and isinstance(data, dict):
                        result["sample_keys"] = list(data.keys())
                except Exception as e:
                    if result["error"] is None:
                        result["error"] = f"Lỗi parse JSON ở dòng {idx + 1}: {e}"
    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
    return result


def check_readme(file_path: Path) -> Dict[str, Any]:
    """Kiểm tra README.md của shop: số dòng, độ dài, in 10 dòng đầu, gắn cờ nếu quá ngắn."""
    result = {"status": "OK", "total_lines": 0, "size_chars": 0, "first_10_lines": [], "warning": None}
    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as f:
            lines = [l.rstrip("\r\n") for l in f]
        result["total_lines"] = len(lines)
        result["size_chars"] = sum(len(l) for l in lines)
        result["first_10_lines"] = lines[:10]
        if len(lines) < 15:
            result["warning"] = f"CẢNH BÁO: README rất ngắn ({len(lines)} dòng < 15 dòng)"
            result["status"] = "WARNING"
    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
    return result


def check_calendar(file_path: Path) -> Dict[str, Any]:
    """Kiểm tra calendar.csv: in tên cột, số dòng, 5 dòng đầu, min/max ngày dương."""
    result = {"status": "OK", "row_count": 0, "columns": [], "sample_rows": [], "min_date": None, "max_date": None, "error": None}
    try:
        df = pd.read_csv(file_path, encoding="utf-8-sig")
        result["columns"] = list(df.columns)
        result["row_count"] = len(df)
        result["sample_rows"] = df.head(5).to_dict(orient="records")

        date_col = next((c for c in df.columns if any(k in c.lower() for k in ["date", "ngay", "ngày"])), df.columns[0])
        try:
            parsed_dates = pd.to_datetime(df[date_col], errors="coerce")
            valid = parsed_dates.dropna()
            if not valid.empty:
                result["min_date"] = str(valid.min().date())
                result["max_date"] = str(valid.max().date())
        except Exception:
            pass
    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
    return result


def scan_dataset(root_dir: Path):
    print("=" * 80)
    print(f"BẮT ĐẦU QUÉT DỮ LIỆU: {root_dir.resolve()}")
    print("=" * 80)

    if not root_dir.exists():
        print(f"[ERROR] Thư mục không tồn tại: {root_dir}")
        return

    data_dir = root_dir / "data"

    print("\n--- 1. CÁC TỆP QUY TẮC & CÂU HỎI CHÍNH ---")
    root_files = list(root_dir.glob("*.*"))
    for file in sorted(root_files):
        if not file.is_file():
            continue
        ext = file.suffix.lower()
        if ext == ".jsonl":
            res = check_jsonl(file)
            print(f"[{res['status']}] {file.name} | Hợp lệ: {res['valid_json']}/{res['total_lines']} | Khóa: {res['sample_keys']}")
            if res["error"]:
                print(f"      [LỖI] {res['error']}")
        elif file.name.lower() == "calendar.csv":
            res = check_calendar(file)
            print(f"[{res['status']}] {file.name} | {res['row_count']} dòng | Cột: {res['columns']} | Khoảng ngày: {res['min_date']} -> {res['max_date']}")
        elif ext == ".csv":
            res = check_csv(file)
            print(f"[{res['status']}] {file.name} (enc={res['encoding']}) | ~{res['row_count']} dòng x {res['col_count']} cột")
            for w in res.get("warnings", []):
                print(f"      [CẢNH BÁO] {w}")
        else:
            size_kb = file.stat().st_size / 1024
            print(f"[INFO] {file.name} ({size_kb:.1f} KB)")

    if data_dir.exists():
        print(f"\n--- 2. CHI TIẾT TỪNG SHOP TRONG {data_dir.name}/ ---")
        shops = [d for d in data_dir.iterdir() if d.is_dir()]
        print(f"-> Tìm thấy {len(shops)} shop: {[s.name for s in sorted(shops)]}")

        for shop in sorted(shops):
            print(f"\n📁 Shop: {shop.name}")
            shop_files = list(shop.rglob("*.*"))
            if not shop_files:
                print("   (Thư mục trống!)")
                continue

            for sf in sorted(shop_files):
                rel_path = sf.relative_to(shop)
                ext = sf.suffix.lower()

                if sf.name.lower() == "readme.md":
                    res = check_readme(sf)
                    print(f"   [{res['status']}] {rel_path} | {res['total_lines']} dòng ({res['size_chars']} ký tự)")
                    if res.get("warning"):
                        print(f"         {res['warning']}")

                elif ext in [".xlsx", ".xls"]:
                    res = check_excel(sf)
                    sheets_summary = []
                    for s_name, s_meta in res["sheets"].items():
                        if isinstance(s_meta, dict):
                            r_c = f"{s_meta.get('rows', '?')}d x {s_meta.get('cols', '?')}c"
                            if s_meta.get("header_shift_detected"):
                                r_c += f" [LỆCH HEADER, dò được row {s_meta.get('detected_header_row', '?')}]"
                            sheets_summary.append(f"{s_name} ({r_c})")
                        else:
                            sheets_summary.append(f"{s_name} (Lỗi)")
                    print(f"   [{res['status']}] {rel_path} | Sheets: {', '.join(sheets_summary)}")
                    for w in res.get("warnings", []):
                        print(f"         [CẢNH BÁO] {w}")

                elif ext == ".csv":
                    res = check_csv(sf)
                    print(f"   [{res['status']}] {rel_path} (enc={res['encoding']}) | {res['row_count']} dòng x {res['col_count']} cột")
                    for w in res.get("warnings", []):
                        print(f"         [CẢNH BÁO] {w}")

                elif ext in [".sqlite", ".db", ".sqlite3"]:
                    res = check_sqlite(sf)
                    if res["status"] == "OK":
                        tables_str = ", ".join([f"{t} ({meta['rows']}d, {len(meta['columns'])}c, PK={meta['pk']})" for t, meta in res["tables"].items()])
                        print(f"   [{res['status']}] {rel_path} | Bảng: {tables_str}")
                        if res["views"]:
                            print(f"         Views: {res['views']}")
                        if res["indexes"]:
                            print(f"         Indexes: {res['indexes']}")
                    else:
                        print(f"   [{res['status']}] {rel_path} | Lỗi: {res['error']}")
                else:
                    print(f"   [OTHER] {rel_path} ({sf.stat().st_size / 1024:.1f} KB)")
    else:
        print(f"\n[WARNING] Không tìm thấy thư mục: {data_dir}")


def main():
    parser = argparse.ArgumentParser(description="Kiểm tra tính toàn vẹn dữ liệu DataMate (Phase 1 EDA Check)")
    parser.add_argument("--root", type=str, default=None, help="Đường dẫn thư mục competition_data")
    args = parser.parse_args()

    if args.root:
        base_dir = Path(args.root).resolve()
    else:
        candidates = [
            Path.cwd() / "competition_data",
            Path.cwd().parent / "competition_data",
            Path(__file__).resolve().parent.parent / "competition_data",
            Path(__file__).resolve().parent.parent.parent / "competition_data",
        ]
        base_dir = next((c for c in candidates if c.exists()), candidates[0])

    print("================================================================================")
    print(f"           DATAMATE - EDA CHECK TÍNH TOÀN VẸN DỮ LIỆU (PHẦN A)                 ")
    print(f"           Thư mục gốc: {base_dir}                                             ")
    print("================================================================================")

    train_dir = base_dir / "train"
    public_test_dir = base_dir / "public_test"

    if train_dir.exists():
        scan_dataset(train_dir)
    else:
        print(f"[SKIP] Không thấy thư mục train tại {train_dir}")

    print("\n\n")
    if public_test_dir.exists():
        scan_dataset(public_test_dir)
    else:
        print(f"[SKIP] Không thấy thư mục public_test tại {public_test_dir}")

    print("\n" + "=" * 80)
    print("HOÀN TẤT QUÉT DỮ LIỆU PHẦN A. Kiểm tra kỹ các dòng [CẢNH BÁO] và [ERROR] ở trên.")
    print("=" * 80)


if __name__ == "__main__":
    main()

