"""
submission.py — Module xử lý và kiểm tra định dạng submission cho DataMate (Phase 1).

Chịu trách nhiệm:
1. Suy luận type tối giản từ kết quả thực thi (to_answer).
2. Tạo đáp án abstain an toàn (make_abstain).
3. Ghi kết quả ra submission.jsonl an toàn (flush + fsync từng dòng) kèm file log (SubmissionWriter).
4. Kiểm tra tính toàn vẹn và hợp lệ của file submission (validate_submission).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

VALID_TYPES = {
    "string",
    "number",
    "percent",
    "date",
    "boolean",
    "list",
    "table",
    "unanswerable",
    "abstain",
}

DEFAULT_OUTPUT_FILE = Path("/result/submission.jsonl")
DEFAULT_LOG_DIR = Path("/result/logs")


# ---------------------------------------------------------------------------
# Tiện ích chuyển đổi kiểu dữ liệu & làm sạch ký tự
# ---------------------------------------------------------------------------

def _is_bool(val: Any) -> bool:
    """Kiểm tra giá trị có phải là boolean (bao gồm cả numpy.bool_)."""
    if isinstance(val, bool):
        return True
    if hasattr(val, "dtype") and "bool" in str(val.dtype):
        return True
    return type(val).__name__ in ("bool_", "bool")


def _is_nan(val: Any) -> bool:
    """Kiểm tra giá trị có phải NaN/NA hay không."""
    if val is None:
        return False
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return True
    try:
        import pandas as pd
        if pd.isna(val):
            return True
    except Exception:
        pass
    try:
        import numpy as np
        if np.isnan(val):
            return True
    except Exception:
        pass
    return False


def _clean_for_json(val: Any) -> Any:
    """Chuyển scalar numpy/pandas, NaN/NA sang kiểu Python thuần có thể serialize JSON."""
    if val is None or val is Ellipsis:
        return None
    if _is_bool(val):
        return bool(val)
    if _is_nan(val):
        return None
    if isinstance(val, (int,)):
        return int(val)
    if isinstance(val, float):
        return float(val)

    type_name = type(val).__name__
    module_name = type(val).__module__

    if "numpy" in module_name or "pandas" in module_name:
        if hasattr(val, "item"):
            try:
                return _clean_for_json(val.item())
            except Exception:
                pass
        if hasattr(val, "isoformat"):
            return val.isoformat()
        if type_name in ("NAType", "NaTType"):
            return None

    if hasattr(val, "isoformat"):
        return val.isoformat()

    if isinstance(val, (list, tuple, set)):
        return [_clean_for_json(x) for x in val]

    if isinstance(val, dict):
        return {str(k): _clean_for_json(v) for k, v in val.items()}

    return str(val)


def _sanitize_filename(name: str) -> str:
    """Làm sạch question_id để dùng an toàn làm tên file log, chống path traversal."""
    clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(name))
    clean = clean.strip("_")
    return clean or "unknown"


# ---------------------------------------------------------------------------
# Các hàm khởi tạo đáp án
# ---------------------------------------------------------------------------

def make_abstain(reason: str = "") -> dict:
    """Tạo đối tượng đáp án abstain chủ động từ chối trả lời."""
    res: dict[str, Any] = {"type": "abstain", "answer": None}
    if reason:
        res["reason"] = str(reason)
    return res


def to_answer(final_result: Any) -> dict:
    """
    Chuyển đổi kết quả thực thi (final_result) sang cấu trúc đáp án {"type": ..., "answer": ...}.

    Quy tắc:
    - Nếu final_result là dict có đúng 2 khóa 'type' và 'answer' -> giữ nguyên (dành cho module normalizer).
    - bool (kiểm tra trước int) -> boolean.
    - int / float -> number.
    - str -> string.
    - list / tuple -> list.
    - None / NaN / kiểu lạ không xác định -> abstain.
    """
    if _is_nan(final_result) or final_result is None:
        return make_abstain("NaN or None result")

    # Nếu đã là dict có đúng 2 khóa type và answer (hoặc unanswerable/abstain)
    if isinstance(final_result, dict):
        keys = set(final_result.keys())
        if keys == {"type", "answer"}:
            res = dict(final_result)
            if _is_nan(res.get("answer")):
                return make_abstain("NaN in answer")
            res["answer"] = _clean_for_json(res["answer"])
            return res
        if "type" in final_result and final_result["type"] in ("unanswerable", "abstain"):
            res = dict(final_result)
            if "answer" in res:
                res["answer"] = _clean_for_json(res["answer"])
            return res
        return make_abstain("Unsupported dict structure")

    # Boolean phải kiểm tra trước int (vì bool là subclass của int)
    if _is_bool(final_result):
        return {"type": "boolean", "answer": bool(final_result)}

    # Số nguyên
    try:
        import numpy as np
        is_np_int = isinstance(final_result, np.integer)
        is_np_float = isinstance(final_result, np.floating)
    except Exception:
        is_np_int = False
        is_np_float = False

    if isinstance(final_result, int) or is_np_int:
        return {"type": "number", "answer": int(final_result)}

    if isinstance(final_result, float) or is_np_float:
        val = float(final_result)
        if math.isnan(val) or math.isinf(val):
            return make_abstain("NaN or Inf float")
        return {"type": "number", "answer": val}

    # Chuỗi
    if isinstance(final_result, str):
        return {"type": "string", "answer": str(final_result)}

    # Danh sách
    if isinstance(final_result, (list, tuple)):
        return {"type": "list", "answer": [_clean_for_json(x) for x in final_result]}

    # Các kiểu không xác định khác
    return make_abstain(f"Unsupported type: {type(final_result).__name__}")


# ---------------------------------------------------------------------------
# SubmissionWriter (Context Manager)
# ---------------------------------------------------------------------------

class SubmissionWriter:
    """
    Context manager ghi kết quả submission.jsonl và nhật ký log từng câu hỏi.

    Đảm bảo:
    - Ghi mỗi câu một dòng, flush + os.fsync ngay lập tức để không mất dữ liệu nếu tiến trình dừng đột ngột.
    - Lưu file log an toàn tại log_dir/<question_id>.json.
    - Tự động tạo thư mục đầu ra nếu chưa tồn tại.
    """

    def __init__(
        self,
        output_file: Path | str = DEFAULT_OUTPUT_FILE,
        log_dir: Path | str = DEFAULT_LOG_DIR,
        mode: str = "w",
    ) -> None:
        self.output_file = Path(output_file)
        self.log_dir = Path(log_dir)
        self.mode = mode
        self._file: Any = None

    def open(self) -> SubmissionWriter:
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._file = open(self.output_file, self.mode, encoding="utf-8")
        return self

    def close(self) -> None:
        if self._file and not self._file.closed:
            try:
                self._file.flush()
                os.fsync(self._file.fileno())
            except Exception:
                pass
            self._file.close()
            self._file = None

    def __enter__(self) -> SubmissionWriter:
        return self.open()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def write(
        self,
        question_id: str,
        answer: dict,
        *,
        code: str = "",
        raw_result: Any = None,
        error: str | None = None,
        elapsed_ms: int = 0,
        confidence: float | None = None,
        unanswerable_source: str = "none",
        selected_tables: list | None = None,
        selected_columns: list | None = None,
        self_correction_count: int = 0,
    ) -> None:
        """
        Ghi 1 dòng vào submission.jsonl (flush + fsync ngay) và xuất file log chi tiết.
        """
        if self._file is None or self._file.closed:
            self.open()

        # Chuẩn bị bản ghi submission
        ans_copy = dict(answer)
        sub_type = ans_copy.get("type", "abstain")

        # Kiểm tra NaN trong answer
        if sub_type != "abstain" and _is_nan(ans_copy.get("answer")):
            ans_copy = make_abstain("NaN result replaced with abstain")
            sub_type = "abstain"

        record: dict[str, Any] = {
            "id": str(question_id),
            "type": sub_type,
        }

        # Nếu có answer (không None) hoặc type cần answer rõ ràng
        if "answer" in ans_copy and ans_copy["answer"] is not None:
            record["answer"] = _clean_for_json(ans_copy["answer"])
        elif sub_type in ("unanswerable", "abstain"):
            # Đối với unanswerable/abstain, có thể để answer là null hoặc omit
            record["answer"] = None
        else:
            record["answer"] = _clean_for_json(ans_copy.get("answer"))

        if "reason" in ans_copy and ans_copy["reason"]:
            record["reason"] = str(ans_copy["reason"])

        # Ghi vào submission.jsonl, flush + fsync ngay
        line = json.dumps(record, ensure_ascii=False)
        self._file.write(line + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())

        # Ghi log chi tiết ra log_dir/<question_id>.json
        safe_qid = _sanitize_filename(question_id)
        log_file = self.log_dir / f"{safe_qid}.json"

        log_payload = {
            "question_id": str(question_id),
            "answer": record,
            "elapsed_ms": int(elapsed_ms),
            "confidence": confidence,
            "code": str(code),
            "raw_result": _clean_for_json(raw_result),
            "error": str(error) if error is not None else None,
            "unanswerable_source": unanswerable_source,
            "selected_tables": selected_tables or [],
            "selected_columns": selected_columns or [],
            "self_correction_count": int(self_correction_count),
        }

        try:
            log_file.write_text(
                json.dumps(log_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as log_err:
            sys.stderr.write(f"Warning: Cannot write log for {question_id}: {log_err}\n")


# ---------------------------------------------------------------------------
# Kiểm tra file submission (validate_submission)
# ---------------------------------------------------------------------------

def validate_submission(submission_path: Path, questions_path: Path) -> list[str]:
    """
    Kiểm tra tính toàn vẹn của tệp submission.jsonl dựa trên questions.jsonl.

    Trả về:
        Danh sách các thông báo lỗi phát hiện được (danh sách rỗng = hợp lệ 100%).
    """
    errors: list[str] = []

    if not submission_path.exists():
        return [f"File submission không tồn tại: {submission_path}"]
    if not questions_path.exists():
        return [f"File questions không tồn tại: {questions_path}"]

    # Đọc danh sách question ID kỳ vọng
    expected_ids: set[str] = set()
    with open(questions_path, "r", encoding="utf-8", errors="replace") as qf:
        for idx, line in enumerate(qf, start=1):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                q_item = json.loads(line_str)
                if "id" in q_item:
                    expected_ids.add(str(q_item["id"]))
                else:
                    errors.append(f"questions.jsonl dòng {idx}: Thiếu trường 'id'")
            except Exception as exc:
                errors.append(f"questions.jsonl dòng {idx}: Lỗi cú pháp JSON ({exc})")

    seen_ids: set[str] = set()

    with open(submission_path, "r", encoding="utf-8", errors="replace") as sf:
        for line_no, line in enumerate(sf, start=1):
            line_str = line.strip()
            if not line_str:
                errors.append(f"Dòng {line_no}: Dòng trống")
                continue

            try:
                row = json.loads(line_str)
            except Exception as exc:
                errors.append(f"Dòng {line_no}: Lỗi cú pháp JSON ({exc})")
                continue

            if not isinstance(row, dict):
                errors.append(f"Dòng {line_no}: Dòng không phải là JSON object (dict)")
                continue

            # Kiểm tra id và type
            if "id" not in row or not row["id"]:
                errors.append(f"Dòng {line_no}: Thiếu trường 'id'")
                continue
            if "type" not in row or not row["type"]:
                errors.append(f"Dòng {line_no}: Thiếu trường 'type'")
                continue

            qid = str(row["id"])
            stype = str(row["type"])

            # Kiểm tra trùng id
            if qid in seen_ids:
                errors.append(f"Dòng {line_no}: Trùng lặp id '{qid}'")
            seen_ids.add(qid)

            # Kiểm tra id có thuộc questions.jsonl không
            if qid not in expected_ids:
                errors.append(f"Dòng {line_no}: id '{qid}' không tồn tại trong questions.jsonl (id lạ)")

            # Kiểm tra type hợp lệ
            if stype not in VALID_TYPES:
                errors.append(
                    f"Dòng {line_no}: type '{stype}' không hợp lệ. Phải thuộc: {sorted(VALID_TYPES)}"
                )
                continue

            answer_val = row.get("answer")

            # Kiểm tra kiểu của answer khớp với type
            if stype == "number":
                if (
                    answer_val is None
                    or _is_bool(answer_val)
                    or not isinstance(answer_val, (int, float))
                    or math.isnan(answer_val)
                    or math.isinf(answer_val)
                ):
                    errors.append(f"Dòng {line_no}: type='number' nhưng answer không phải số hợp lệ: {answer_val!r}")

            elif stype == "percent":
                if (
                    answer_val is None
                    or _is_bool(answer_val)
                    or not isinstance(answer_val, (int, float))
                    or math.isnan(answer_val)
                    or math.isinf(answer_val)
                ):
                    errors.append(f"Dòng {line_no}: type='percent' nhưng answer không phải số hợp lệ: {answer_val!r}")

            elif stype == "boolean":
                if not isinstance(answer_val, bool):
                    errors.append(f"Dòng {line_no}: type='boolean' nhưng answer không phải bool: {answer_val!r}")

            elif stype == "string":
                if not isinstance(answer_val, str):
                    errors.append(f"Dòng {line_no}: type='string' nhưng answer không phải string: {answer_val!r}")

            elif stype == "date":
                if not isinstance(answer_val, str) or not re.match(r"^\d{4}-\d{2}(-\d{2})?$", answer_val):
                    errors.append(f"Dòng {line_no}: type='date' nhưng answer không phải định dạng YYYY-MM-DD hoặc YYYY-MM: {answer_val!r}")

            elif stype == "list":
                if not isinstance(answer_val, list):
                    errors.append(f"Dòng {line_no}: type='list' nhưng answer không phải list: {answer_val!r}")

            elif stype == "table":
                if (
                    not isinstance(answer_val, dict)
                    or "columns" not in answer_val
                    or "rows" not in answer_val
                    or not isinstance(answer_val["columns"], list)
                    or not isinstance(answer_val["rows"], list)
                ):
                    errors.append(f"Dòng {line_no}: type='table' nhưng answer thiếu 'columns' hoặc 'rows' dạng list")

            elif stype == "unanswerable":
                if answer_val is not None:
                    errors.append(f"Dòng {line_no}: type='unanswerable' yêu cầu answer là null (hoặc bỏ trống), nhưng nhận được: {answer_val!r}")
                if "reason" in row and not isinstance(row["reason"], str):
                    errors.append(f"Dòng {line_no}: type='unanswerable' có trường 'reason' không phải chuỗi")

            elif stype == "abstain":
                if "reason" in row and not isinstance(row["reason"], str):
                    errors.append(f"Dòng {line_no}: type='abstain' có trường 'reason' không phải chuỗi")

    # Kiểm tra thiếu câu hỏi
    missing_ids = expected_ids - seen_ids
    if missing_ids:
        sample_missing = sorted(list(missing_ids))[:5]
        errors.append(
            f"Thiếu {len(missing_ids)}/{len(expected_ids)} câu hỏi từ questions.jsonl (ví dụ: {sample_missing})"
        )

    return errors


# ---------------------------------------------------------------------------
# Giao diện dòng lệnh CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Kiểm tra tính hợp lệ của tệp submission.jsonl cho cuộc thi DataMate."
    )
    parser.add_argument(
        "--validate",
        type=Path,
        required=True,
        help="Đường dẫn đến file submission.jsonl cần kiểm tra",
    )
    parser.add_argument(
        "--questions",
        type=Path,
        required=True,
        help="Đường dẫn đến file questions.jsonl tương ứng để so khớp",
    )

    args = parser.parse_args()

    errs = validate_submission(args.validate, args.questions)
    if not errs:
        print("✓ HỢP LỆ: Tệp submission tuân thủ 100% quy chuẩn BTC (0 lỗi).")
        sys.exit(0)
    else:
        print(f"⚠ PHÁT HIỆN {len(errs)} LỖI TRONG FILE SUBMISSION:")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)


if __name__ == "__main__":
    _cli()

