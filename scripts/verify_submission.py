"""
verify_submission.py — Thẩm định toàn vẹn tệp nộp bài submission.jsonl (Submission Validator).
Phân hệ: Phase 4 — Zalo AI Challenge 2026 (DataMate Track).
Tác giả: DataMate Team (Long & Phat)

Mục đích:
- Kiểm tra toàn bộ các quy định định dạng nghiêm ngặt nhất của Ban Tổ Chức:
  1. File JSONL hợp lệ, mỗi dòng là một JSON object độc lập, kết thúc bằng newline.
  2. Bắt buộc có các trường: 'id', 'type', 'answer'. Trường 'reason' là tùy chọn (nếu có phải là string).
  3. Kiểu dữ liệu 'type' phải thuộc tập 9 kiểu chuẩn:
     {'number', 'percent', 'string', 'date', 'boolean', 'list', 'table', 'unanswerable', 'abstain'}.
  4. Quy chuẩn giá trị 'answer':
     - unanswerable / abstain: answer bắt buộc là None/null.
     - number: số int hoặc float (không được là boolean).
     - percent: số float trong đoạn [0.0, 100.0] (không kèm ký hiệu '%').
     - string: chuỗi ký tự, giữ nguyên dấu tiếng Việt NFC.
     - date: định dạng ISO 'YYYY-MM-DD' hoặc 'YYYY-MM'.
     - boolean: True hoặc False.
     - list: danh sách các phần tử.
     - table: từ điển chứa 2 khóa 'columns' (list[str]) và 'rows' (list[list]).
  5. Không có bất kỳ ID nào bị trùng lặp.
  6. Nếu truyền --questions: Đối chiếu 1-1 không được sót câu hỏi và không được thừa ID lạ.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path
from typing import Any, Dict, List, Set

VALID_TYPES = {
    "number",
    "percent",
    "string",
    "date",
    "boolean",
    "list",
    "table",
    "unanswerable",
    "abstain",
}

DATE_REGEX = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")


def parse_args():
    parser = argparse.ArgumentParser(description="Thẩm định toàn vẹn file nộp bài submission.jsonl theo chuẩn BTC")
    parser.add_argument("--submission", type=str, default="submission.jsonl", help="Đường dẫn file submission.jsonl")
    parser.add_argument("--questions", type=str, default=None, help="Đường dẫn file questions.jsonl để đối chiếu ID")
    return parser.parse_args()


def validate_submission_file(
    sub_path: Path,
    q_path: Path | None = None,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Kiểm tra toàn bộ quy chuẩn của file nộp bài."""
    errors: List[str] = []
    seen_ids: Set[str] = set()
    records_count = 0
    type_counts: Dict[str, int] = {t: 0 for t in VALID_TYPES}

    if not sub_path.exists():
        return False, [f"Tệp không tồn tại: {sub_path}"], {}

    if sub_path.stat().st_size == 0:
        return False, [f"Tệp rỗng (0 bytes): {sub_path}"], {}

    with open(sub_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str:
                errors.append(f"Dòng {line_no}: Dòng trống không hợp lệ trong file JSONL")
                continue

            try:
                rec = json.loads(line_str)
            except json.JSONDecodeError as exc:
                errors.append(f"Dòng {line_no}: Lỗi cú pháp JSON: {exc}")
                continue

            records_count += 1

            if not isinstance(rec, dict):
                errors.append(f"Dòng {line_no}: Dòng phải là một JSON Object dict")
                continue

            qid = rec.get("id")
            ans_type = rec.get("type")
            ans_val = rec.get("answer")

            # 1. Kiểm tra ID
            if not qid or not isinstance(qid, str):
                errors.append(f"Dòng {line_no}: Trường 'id' thiếu hoặc không phải string")
                continue

            if qid in seen_ids:
                errors.append(f"Dòng {line_no}: ID '{qid}' bị xuất hiện trùng lặp")
            seen_ids.add(qid)

            # 2. Kiểm tra Type
            if not ans_type or not isinstance(ans_type, str):
                errors.append(f"Dòng {line_no} (ID: {qid}): Trường 'type' thiếu hoặc không phải string")
                continue

            ans_type_clean = ans_type.strip().lower()
            if ans_type_clean not in VALID_TYPES:
                errors.append(f"Dòng {line_no} (ID: {qid}): Type '{ans_type}' không hợp lệ. Phải thuộc {VALID_TYPES}")
                continue

            type_counts[ans_type_clean] += 1

            # 3. Kiểm tra trường reason nếu có
            if "reason" in rec and rec["reason"] is not None and not isinstance(rec["reason"], str):
                errors.append(f"Dòng {line_no} (ID: {qid}): Trường 'reason' nếu có phải là kiểu string")

            # 4. Kiểm tra Answer theo từng Type
            if ans_type_clean in ("unanswerable", "abstain"):
                if ans_val is not None:
                    errors.append(f"Dòng {line_no} (ID: {qid}): Type '{ans_type_clean}' bắt buộc answer phải là null/None")

            elif ans_type_clean == "number":
                if isinstance(ans_val, bool) or not isinstance(ans_val, (int, float)):
                    errors.append(f"Dòng {line_no} (ID: {qid}): Type 'number' yêu cầu answer là int hoặc float (nhận được {type(ans_val).__name__})")

            elif ans_type_clean == "percent":
                if isinstance(ans_val, bool) or not isinstance(ans_val, (int, float)):
                    errors.append(f"Dòng {line_no} (ID: {qid}): Type 'percent' yêu cầu answer là số float (nhận được {type(ans_val).__name__})")
                elif ans_val < 0.0 or ans_val > 100.0:
                    errors.append(f"Dòng {line_no} (ID: {qid}): Giá trị percent={ans_val} nằm ngoài khoảng hợp lệ [0, 100]")

            elif ans_type_clean == "string":
                if not isinstance(ans_val, str):
                    errors.append(f"Dòng {line_no} (ID: {qid}): Type 'string' yêu cầu answer là str (nhận được {type(ans_val).__name__})")

            elif ans_type_clean == "date":
                if not isinstance(ans_val, str) or not DATE_REGEX.match(ans_val):
                    errors.append(f"Dòng {line_no} (ID: {qid}): Type 'date' yêu cầu định dạng YYYY-MM-DD hoặc YYYY-MM (nhận được '{ans_val}')")

            elif ans_type_clean == "boolean":
                if not isinstance(ans_val, bool):
                    errors.append(f"Dòng {line_no} (ID: {qid}): Type 'boolean' yêu cầu answer là True/False (nhận được {type(ans_val).__name__})")

            elif ans_type_clean == "list":
                if not isinstance(ans_val, list):
                    errors.append(f"Dòng {line_no} (ID: {qid}): Type 'list' yêu cầu answer là list (nhận được {type(ans_val).__name__})")

            elif ans_type_clean == "table":
                if not isinstance(ans_val, dict) or "columns" not in ans_val or "rows" not in ans_val:
                    errors.append(f"Dòng {line_no} (ID: {qid}): Type 'table' yêu cầu dict có 2 khóa 'columns' và 'rows'")

    # 5. Đối chiếu với danh sách câu hỏi gốc nếu được cung cấp
    expected_ids: Set[str] = set()
    if q_path and q_path.exists():
        with open(q_path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    try:
                        q_obj = json.loads(line_str)
                        if "id" in q_obj:
                            expected_ids.add(q_obj["id"])
                    except Exception:
                        pass

        missing_ids = expected_ids - seen_ids
        extra_ids = seen_ids - expected_ids

        if missing_ids:
            errors.append(f"Thiếu {len(missing_ids)} ID câu hỏi so với {q_path.name} (ví dụ: {list(missing_ids)[:5]})")
        if extra_ids:
            errors.append(f"Thừa {len(extra_ids)} ID không tồn tại trong {q_path.name} (ví dụ: {list(extra_ids)[:5]})")

    is_valid = (len(errors) == 0 and records_count > 0)
    summary = {
        "file": str(sub_path),
        "total_records": records_count,
        "unique_ids": len(seen_ids),
        "type_counts": {k: v for k, v in type_counts.items() if v > 0},
        "errors_count": len(errors),
        "is_valid": is_valid,
    }
    return is_valid, errors, summary


def main():
    args = parse_args()
    print("=" * 75)
    print("DATAMATE — THẨM ĐỊNH ĐỊNH DẠNG SUBMISSION (PHASE 4 SUBMISSION VERIFIER)")
    print("=" * 75)

    sub_file = Path(args.submission)
    q_file = Path(args.questions) if args.questions else None

    is_valid, errors, summary = validate_submission_file(sub_file, q_file)

    print(f"• Tệp kiểm tra : {sub_file}")
    if q_file:
        print(f"• Tệp đối chiếu: {q_file}")
    print(f"• Tổng số dòng : {summary.get('total_records', 0)}")
    print(f"• Thống kê type: {summary.get('type_counts', {})}")

    print("=" * 75)
    if is_valid:
        print("✅ KẾT QUẢ: FILE NỘP BÀI ĐẠT CHUẨN 100% (0 LỖI FORMAT)!")
        print("🎉 Sẵn sàng nộp bài lên hệ thống Zalo AI Challenge 2026!")
        print("=" * 75)
        sys.exit(0)
    else:
        print(f"❌ KẾT QUẢ: PHÁT HIỆN {len(errors)} LỖI ĐỊNH DẠNG:")
        for err in errors[:20]:
            print(f"  - {err}")
        if len(errors) > 20:
            print(f"  - ... và {len(errors) - 20} lỗi khác.")
        print("=" * 75)
        sys.exit(1)


if __name__ == "__main__":
    main()
