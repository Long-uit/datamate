"""
schema.py — Trích xuất và mô tả cấu trúc lược đồ dữ liệu (Schema Profiling).

Tách từ loader.py, sinh định dạng mô tả bảng biểu cô đọng cho prompt LLM
theo nghiên cứu SheetCompressor (SpreadSheetLLM) và EHRSQL.
"""

from __future__ import annotations

import io
from datamate.ingestion.loader import BusinessData


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

