"""Chấm file prediction theo hợp đồng answer và Penalized Accuracy (PA).

Mô-đun này là evaluator nội bộ của thư mục ``benchmark``; nó không gọi model
hay suy luận đáp án. Luồng xử lý là: đọc prediction/gold JSONL, lấy đúng eval
IDs, kiểm tra schema, so từng answer theo type, rồi tổng hợp PA và báo cáo.
Các quy tắc answer matching được đối chiếu với mục 9 của rulebook train và
public_test. JSONL lỗi, ID trùng hoặc gold không đầy đủ làm evaluator dừng;
prediction thiếu được tính là abstain.

Chạy từ thư mục gốc repository, ví dụ::

    python -m benchmark.evaluate --pred submission.jsonl --gold benchmark/splits/within_business_v1/val_answers.jsonl --val-ids benchmark/splits/within_business_v1/val_ids.json --report-json results/report.json

``compare_value`` so một answer; ``evaluate_records`` chấm mapping đã đọc trong
bộ nhớ. CLI dùng cùng các hàm này để thống nhất chấm trong code và khi chạy lệnh.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Optional

# Các type được phép trong gold và prediction. ``abstain`` chỉ hợp lệ ở prediction.
# ---------------------------------------------------------------------------
# Các type và độ chính xác số dùng chung
# ---------------------------------------------------------------------------
SUPPORTED_TYPES = {
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
# Giữ số JSON ở dạng Decimal khi có thể; percent được làm tròn tới hai chữ số.
_NUMERIC_TYPES = (int, float, Decimal)
_PERCENT_QUANTUM = Decimal("0.01")


# Reconfigure console để thông báo lỗi/chấm tiếng Việt hiển thị đúng trên Windows.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Chuẩn hóa và so sánh scalar: số, chuỗi, ngày và phần tử list
# ---------------------------------------------------------------------------
def _is_number(value: Any) -> bool:
    """Kiểm tra JSON number hữu hạn; bool bị loại dù Python coi bool là int."""
    if isinstance(value, bool) or not isinstance(value, _NUMERIC_TYPES):
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Decimal):
        return value.is_finite()
    return True


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Đưa số hợp lệ về Decimal, tránh mất chính xác khi so số thập phân."""
    if not _is_number(value):
        return None
    try:
        if isinstance(value, Decimal):
            result = value
        elif isinstance(value, int):
            result = Decimal(value)
        else:
            result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _numeric_equal(pred: Any, gold: Any) -> bool:
    """So số chính xác; chỉ nới tối đa một ULP cho sai số float nhỏ.

    Số nguyên luôn phải bằng nhau tuyệt đối để không cho phép lệch tiền hoặc
    số đếm. Dung sai chỉ dùng khi ULP nhỏ hơn một đơn vị.
    """
    p_num = _to_decimal(pred)
    g_num = _to_decimal(gold)
    if p_num is None or g_num is None:
        return False
    if p_num == g_num:
        return True

    # Không nới dung sai cho số nguyên: ở độ lớn trên 2**53, một ULP có thể
    # lớn hơn 1 và nếu áp dụng sẽ làm hai số đếm/tiền kề nhau thành bằng nhau.
    if p_num == p_num.to_integral_value() and g_num == g_num.to_integral_value():
        return False
    try:
        p_float = float(p_num)
        g_float = float(g_num)
    except (OverflowError, ValueError):
        return False
    if not math.isfinite(p_float) or not math.isfinite(g_float):
        return False

    ulp = max(math.ulp(p_float), math.ulp(g_float))
    # Ở độ lớn khiến một ULP đạt 1 đơn vị trở lên, đó không còn là sai số
    # biểu diễn nhỏ an toàn cho tiền/số đếm.
    if ulp >= 1:
        return False
    tolerance = Decimal(str(ulp))
    return abs(p_num - g_num) <= tolerance


def _normalize_string(value: str) -> str:
    """Chuẩn hóa NFC/casefold, bỏ dấu câu và khoảng trắng nhưng giữ dấu Việt.

    Ký tự chữ, dấu kết hợp Unicode và chữ số được giữ; cách làm này tránh coi
    hai tên khác dấu tiếng Việt là một.
    """
    text = unicodedata.normalize("NFC", value).casefold()
    chars: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        if category[0] in {"L", "M", "N"}:
            chars.append(char)
    return "".join(chars)


def _string_equal(pred: Any, gold: Any, aliases: Any = None) -> bool:
    """So chuỗi với gold hoặc alias được khai báo trong bản ghi gold."""
    if not isinstance(pred, str) or not isinstance(gold, str):
        return False
    normalized_pred = _normalize_string(pred)
    accepted = [_normalize_string(gold)]
    if aliases is None:
        aliases = []
    if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
        return False
    accepted.extend(_normalize_string(alias) for alias in aliases)
    return normalized_pred in accepted


def _valid_date(value: Any) -> bool:
    """Kiểm tra date ISO dạng YYYY-MM-DD hoặc YYYY-MM, gồm cả tính hợp lệ lịch."""
    if not isinstance(value, str):
        return False
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            date.fromisoformat(value)
            return True
        except ValueError:
            return False
    if re.fullmatch(r"\d{4}-\d{2}", value):
        year, month = (int(part) for part in value.split("-"))
        return year >= 1 and 1 <= month <= 12
    return False


def _list_element_equal(pred: Any, gold: Any, aliases: Any = None) -> bool:
    """So phần tử list theo type gold; hỗ trợ list lồng và alias theo vị trí."""
    if isinstance(gold, bool):
        return isinstance(pred, bool) and pred is gold
    if _is_number(gold):
        return _numeric_equal(pred, gold)
    if isinstance(gold, str):
        return _string_equal(pred, gold, aliases)
    if gold is None:
        return pred is None
    if isinstance(gold, list):
        if not isinstance(pred, list) or len(pred) != len(gold):
            return False
        nested_aliases = aliases if isinstance(aliases, list) else []
        if nested_aliases and len(nested_aliases) != len(gold):
            return False
        return all(
            _list_element_equal(
                p_item,
                g_item,
                nested_aliases[i] if nested_aliases else None,
            )
            for i, (p_item, g_item) in enumerate(zip(pred, gold))
        )
    return type(pred) is type(gold) and pred == gold


# ---------------------------------------------------------------------------
# So cấu trúc bảng, bao gồm căn cột, alias tên và hàng trùng
# ---------------------------------------------------------------------------
def _table_parts(value: Any) -> Optional[tuple[list[str], list[list[Any]]]]:
    """Trích columns/rows khi bảng đúng cấu trúc, nếu sai trả về None."""
    if not isinstance(value, dict):
        return None
    columns = value.get("columns")
    rows = value.get("rows")
    if not isinstance(columns, list) or not columns:
        return None
    if any(not isinstance(column, str) for column in columns):
        return None
    if not isinstance(rows, list):
        return None
    if any(not isinstance(row, list) or len(row) != len(columns) for row in rows):
        return None
    return columns, rows


def _table_cell_equal(pred: Any, gold: Any, aliases: Any = None) -> bool:
    """So một ô bảng theo type gold; alias chỉ có ý nghĩa với ô string."""
    if isinstance(gold, bool):
        return isinstance(pred, bool) and pred is gold
    if _is_number(gold):
        return _numeric_equal(pred, gold)
    if isinstance(gold, str):
        return _string_equal(pred, gold, aliases)
    if gold is None:
        return pred is None
    return type(pred) is type(gold) and pred == gold


def _table_equal(pred: Any, gold: Any, aliases: Any = None) -> bool:
    """So bảng, căn cột theo tên hoặc vị trí và không phụ thuộc thứ tự hàng.

    Matching hàng một-một bảo toàn số lần xuất hiện của hàng trùng; alias được
    gắn với hàng gold tương ứng thay vì vị trí của hàng prediction.
    """
    p_parts = _table_parts(pred)
    g_parts = _table_parts(gold)
    if p_parts is None or g_parts is None:
        return False

    p_columns, p_rows = p_parts
    g_columns, g_rows = g_parts
    if len(p_columns) != len(g_columns) or len(p_rows) != len(g_rows):
        return False

    p_norm = [_normalize_string(x) for x in p_columns]
    g_norm = [_normalize_string(x) for x in g_columns]
    if len(set(p_norm)) == len(p_norm) and len(set(g_norm)) == len(g_norm) and set(p_norm) == set(g_norm):
        p_index_by_name = {name: index for index, name in enumerate(p_norm)}
        p_order = [p_index_by_name[name] for name in g_norm]
    else:
        p_order = list(range(len(g_columns)))

    if aliases is None or aliases == []:
        row_aliases: list[list[str]] = [[] for _ in g_rows]
    elif (
        isinstance(aliases, list)
        and len(aliases) == len(g_rows)
        and all(isinstance(item, list) and all(isinstance(x, str) for x in item) for item in aliases)
    ):
        row_aliases = aliases
    else:
        return False

    def rows_equal(p_row: list[Any], g_row: list[Any], g_row_index: int) -> bool:
        for g_col_index, g_cell in enumerate(g_row):
            p_cell = p_row[p_order[g_col_index]]
            cell_aliases = row_aliases[g_row_index] if g_col_index == 0 else None
            if not _table_cell_equal(p_cell, g_cell, cell_aliases):
                return False
        return True

    edges = [
        [g_index for g_index, g_row in enumerate(g_rows) if rows_equal(p_row, g_row, g_index)]
        for p_row in p_rows
    ]
    if any(not matches for matches in edges):
        return False

    order = sorted(range(len(edges)), key=lambda p_index: len(edges[p_index]))
    gold_to_pred: dict[int, int] = {}

    def augment(p_index: int, seen_gold: set[int]) -> bool:
        for g_index in edges[p_index]:
            if g_index in seen_gold:
                continue
            seen_gold.add(g_index)
            previous = gold_to_pred.get(g_index)
            if previous is None or augment(previous, seen_gold):
                gold_to_pred[g_index] = p_index
                return True
        return False

    return all(augment(p_index, set()) for p_index in order)


# ---------------------------------------------------------------------------
# Điều phối so answer và xác thực schema của gold/prediction
# ---------------------------------------------------------------------------
def compare_value(
    pred_val: Any,
    gold_val: Any,
    ans_type: str,
    aliases: Any = None,
) -> bool:
    """So một answer theo type gold và hợp đồng ở mục 9 rulebook.

    Hàm này chỉ trả kết quả so giá trị. Kiểm tra ID/record, xử lý abstain và
    cộng điểm nằm trong ``evaluate_records``.
    """
    if ans_type == "unanswerable":
        return True
    if ans_type == "number":
        return _numeric_equal(pred_val, gold_val)
    if ans_type == "percent":
        p_num = _to_decimal(pred_val)
        g_num = _to_decimal(gold_val)
        if p_num is None or g_num is None:
            return False
        try:
            p_rounded = p_num.quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP)
            g_rounded = g_num.quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return False
        return p_rounded == g_rounded
    if ans_type == "boolean":
        return isinstance(pred_val, bool) and isinstance(gold_val, bool) and pred_val is gold_val
    if ans_type == "date":
        return _valid_date(pred_val) and _valid_date(gold_val) and pred_val == gold_val
    if ans_type == "string":
        return _string_equal(pred_val, gold_val, aliases)
    if ans_type == "list":
        if not isinstance(pred_val, list) or not isinstance(gold_val, list):
            return False
        if len(pred_val) != len(gold_val):
            return False
        if aliases is None or aliases == []:
            element_aliases: list[list[str]] = [[] for _ in gold_val]
        elif (
            isinstance(aliases, list)
            and len(aliases) == len(gold_val)
            and all(isinstance(item, list) and all(isinstance(x, str) for x in item) for item in aliases)
        ):
            element_aliases = aliases
        else:
            return False
        return all(
            _list_element_equal(p_item, g_item, element_aliases[index])
            for index, (p_item, g_item) in enumerate(zip(pred_val, gold_val))
        )
    if ans_type == "table":
        return _table_equal(pred_val, gold_val, aliases)
    return False


def _prediction_format_valid(pred_type: Any, answer: Any) -> bool:
    """Kiểm tra format ngoài của answer, không đánh giá giá trị đúng/sai."""
    if pred_type in {"number", "percent"}:
        return _is_number(answer)
    if pred_type == "boolean":
        return isinstance(answer, bool)
    if pred_type == "date":
        return _valid_date(answer)
    if pred_type == "string":
        return isinstance(answer, str)
    if pred_type == "list":
        return isinstance(answer, list)
    if pred_type == "table":
        return _table_parts(answer) is not None
    if pred_type == "unanswerable":
        return answer is None
    return False


def validate_gold_record(qid: str, gold: Any) -> None:
    """Xác thực schema gold và alias; raise ValueError nếu dữ liệu gold lỗi.

    Splitter dùng chung hàm này để cách kiểm tra dữ liệu nguồn nhất quán với
    evaluator.
    """
    if not isinstance(gold, dict):
        raise ValueError(f"Gold record {qid!r} phải là JSON object")
    if gold.get("id", qid) != qid:
        raise ValueError(f"Gold key/id không khớp tại {qid!r}")
    ans_type = gold.get("type")
    if not isinstance(ans_type, str) or ans_type not in SUPPORTED_TYPES - {"abstain"}:
        raise ValueError(f"Gold {qid!r} có type không hỗ trợ: {ans_type!r}")

    answer = gold.get("answer")
    if ans_type in {"number", "percent"} and not _is_number(answer):
        raise ValueError(f"Gold {qid!r} type={ans_type} phải có answer là JSON number")
    if ans_type == "boolean" and not isinstance(answer, bool):
        raise ValueError(f"Gold {qid!r} type=boolean phải có answer true/false")
    if ans_type == "date" and not _valid_date(answer):
        raise ValueError(f"Gold {qid!r} có date sai format: {answer!r}")
    if ans_type == "string" and not isinstance(answer, str):
        raise ValueError(f"Gold {qid!r} type=string phải có answer là string")
    if ans_type == "list" and not isinstance(answer, list):
        raise ValueError(f"Gold {qid!r} type=list phải có answer là array")
    if ans_type == "table" and _table_parts(answer) is None:
        raise ValueError(f"Gold {qid!r} type=table có columns/rows sai cấu trúc")
    if ans_type == "unanswerable" and answer is not None:
        raise ValueError(f"Gold {qid!r} type=unanswerable phải có answer null")

    aliases = gold.get("alias", [])
    if aliases is None:
        aliases = []
    if ans_type == "string":
        valid = isinstance(aliases, list) and all(isinstance(x, str) for x in aliases)
    elif ans_type in {"list", "table"}:
        expected_length = len(answer) if ans_type == "list" else len(answer["rows"])
        valid = (
            aliases == []
            or (
                isinstance(aliases, list)
                and len(aliases) == expected_length
                and all(isinstance(item, list) and all(isinstance(x, str) for x in item) for item in aliases)
            )
        )
    else:
        valid = aliases == []
    if not valid:
        raise ValueError(f"Gold {qid!r} có alias sai cấu trúc cho type={ans_type}")


# ---------------------------------------------------------------------------
# Chấm cả tập và tổng hợp metric toàn cục/theo answer type
# ---------------------------------------------------------------------------
def evaluate_records(
    predictions: dict[str, dict],
    golds: dict[str, dict],
    eval_ids: Optional[set[str] | list[str]] = None,
) -> dict[str, Any]:
    """Chấm các prediction trên tập eval IDs và tổng hợp metric.

    Mỗi eval ID được tính đúng một lần. Thiếu prediction là abstain; ID thừa
    được báo nhưng không tham gia mẫu số. Gold thiếu hoặc sai schema là lỗi
    dữ liệu nghiêm trọng nên dừng thay vì âm thầm tính điểm trên tập nhỏ hơn.
    """
    if any(not isinstance(qid, str) or not qid for qid in predictions):
        raise ValueError("prediction keys phải là ID string không rỗng")
    if any(not isinstance(qid, str) or not qid for qid in golds):
        raise ValueError("gold keys phải là ID string không rỗng")
    if eval_ids is None:
        target_ids = sorted(golds)
    else:
        if any(not isinstance(qid, str) or not qid for qid in eval_ids):
            raise ValueError("eval_ids phải chứa ID string không rỗng")
        target_ids = sorted(eval_ids)

    if len(target_ids) != len(set(target_ids)):
        raise ValueError("eval_ids chứa ID trùng")

    missing_gold = sorted(set(target_ids) - set(golds))
    if missing_gold:
        raise ValueError(f"Thiếu gold cho {len(missing_gold)} eval ID, ví dụ: {missing_gold[:5]}")

    # Bộ đếm toàn cục và breakdown theo type luôn phải cộng lại bằng total.
    correct = 0
    wrong = 0
    abstain = 0
    invalid_format = 0
    details: list[dict[str, Any]] = []
    breakdown: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "correct": 0, "wrong": 0, "abstain": 0}
    )

    # Chấm theo từng ID để không phụ thuộc thứ tự dòng trong prediction/gold.
    for qid in target_ids:
        gold = golds[qid]
        validate_gold_record(qid, gold)
        gold_type = gold["type"]
        breakdown[gold_type]["total"] += 1

        # Không có dòng prediction tương đương abstain theo rulebook: 0 điểm.
        if qid not in predictions:
            abstain += 1
            breakdown[gold_type]["abstain"] += 1
            details.append({"id": qid, "type": gold_type, "status": "abstain", "reason": "prediction_missing"})
            continue

        pred = predictions[qid]
        if not isinstance(pred, dict) or pred.get("id") != qid:
            wrong += 1
            invalid_format += 1
            breakdown[gold_type]["wrong"] += 1
            details.append({"id": qid, "type": gold_type, "status": "wrong", "reason": "invalid_prediction_record", "invalid_format": True})
            continue

        # Rulebook quy định reason sai type khiến cả dòng không đọc được.
        if "reason" in pred and not isinstance(pred["reason"], str):
            abstain += 1
            invalid_format += 1
            breakdown[gold_type]["abstain"] += 1
            details.append({"id": qid, "type": gold_type, "status": "abstain", "reason": "reason_not_string", "invalid_format": True})
            continue

        pred_type = pred.get("type")
        if pred_type == "abstain":
            abstain += 1
            breakdown[gold_type]["abstain"] += 1
            details.append({"id": qid, "type": gold_type, "status": "abstain", "reason": "explicit_abstain"})
            continue

        # Mỗi answer type có một output format; sai type là sai, không ép kiểu.
        if pred_type != gold_type:
            wrong += 1
            invalid_format += 1
            breakdown[gold_type]["wrong"] += 1
            details.append({"id": qid, "type": gold_type, "status": "wrong", "reason": "type_mismatch", "predicted_type": pred_type, "invalid_format": True})
            continue

        if gold_type == "unanswerable":
            if "answer" in pred and pred["answer"] is not None:
                wrong += 1
                invalid_format += 1
                breakdown[gold_type]["wrong"] += 1
                details.append({"id": qid, "type": gold_type, "status": "wrong", "reason": "unanswerable_answer_must_be_null_or_absent", "invalid_format": True})
            else:
                correct += 1
                breakdown[gold_type]["correct"] += 1
                details.append({"id": qid, "type": gold_type, "status": "correct", "reason": "unanswerable_type_matched"})
            continue

        if "answer" not in pred:
            wrong += 1
            invalid_format += 1
            breakdown[gold_type]["wrong"] += 1
            details.append({"id": qid, "type": gold_type, "status": "wrong", "reason": "answer_missing", "invalid_format": True})
            continue

        format_valid = _prediction_format_valid(pred_type, pred["answer"])
        if not format_valid:
            invalid_format += 1

        matched = compare_value(
            pred_val=pred["answer"],
            gold_val=gold["answer"],
            ans_type=gold_type,
            aliases=gold.get("alias", []),
        )
        if matched:
            correct += 1
            breakdown[gold_type]["correct"] += 1
            details.append({"id": qid, "type": gold_type, "status": "correct", "reason": "answer_matched"})
        else:
            wrong += 1
            breakdown[gold_type]["wrong"] += 1
            details.append({
                "id": qid,
                "type": gold_type,
                "status": "wrong",
                "reason": "invalid_answer_format" if not format_valid else "answer_mismatch",
                "invalid_format": not format_valid,
            })

    # Tính metric trên eval IDs, kể cả các trường hợp abstain.
    total = len(target_ids)
    if correct + wrong + abstain != total:
        raise AssertionError("Số đúng/sai/abstain không cộng lại bằng total")

    extra_ids = sorted(set(predictions) - set(target_ids))
    pa = (correct - wrong) / total if total else 0.0
    accuracy = correct / total if total else 0.0
    coverage = (correct + wrong) / total if total else 0.0

    return {
        "total": total,
        "correct": correct,
        "wrong": wrong,
        "abstain": abstain,
        "invalid_format": invalid_format,
        "missing_predictions": sum(qid not in predictions for qid in target_ids),
        "extra_prediction_ids": extra_ids,
        "accuracy": round(accuracy, 4),
        "coverage": round(coverage, 4),
        "pa": round(pa, 4),
        "breakdown": dict(breakdown),
        "details": details,
    }


# ---------------------------------------------------------------------------
# Đọc file, in report và giao diện dòng lệnh
# ---------------------------------------------------------------------------
def load_jsonl_to_dict(path: Path | str) -> dict[str, dict]:
    """Đọc JSONL thành mapping theo ID với kiểm tra nghiêm ngặt.

    Số thập phân được parse thành Decimal. Dòng JSON lỗi, dòng không phải
    object, ID thiếu hoặc ID trùng đều báo file và số dòng.
    """
    result: dict[str, dict] = {}
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Không tìm thấy JSONL: {file_path}")

    with file_path.open("r", encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line, parse_float=Decimal)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{file_path}:{line_no}: JSON không hợp lệ: {exc.msg}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{file_path}:{line_no}: mỗi dòng phải là JSON object")
            qid = record.get("id")
            if not isinstance(qid, str) or not qid.strip():
                raise ValueError(f"{file_path}:{line_no}: thiếu ID string không rỗng")
            if qid in result:
                raise ValueError(f"{file_path}:{line_no}: ID trùng {qid!r}")
            result[qid] = record
    return result


def print_report(metrics: dict[str, Any]) -> None:
    """In metric toàn tập và breakdown answer type; hỗ trợ cả tập rỗng."""
    total = metrics["total"]

    def pct(count: int) -> float:
        return 100.0 * count / total if total else 0.0

    print("\n" + "=" * 72)
    print("BÁO CÁO ĐÁNH GIÁ BENCHMARK (PA)")
    print("=" * 72)
    print(f"Tổng số câu:           {total}")
    print(f"Số câu đúng (+1):      {metrics['correct']} ({pct(metrics['correct']):.1f}%)")
    print(f"Số câu sai (-1):       {metrics['wrong']} ({pct(metrics['wrong']):.1f}%)")
    print(f"Số câu abstain (0):    {metrics['abstain']} ({pct(metrics['abstain']):.1f}%)")
    print(f"Format sai:            {metrics['invalid_format']}")
    print(f"Coverage:              {metrics['coverage']:.4f}")
    print(f"Accuracy:              {metrics['accuracy']:.4f}")
    print(f"Penalized Accuracy:    {metrics['pa']:.4f}")
    print(f"Prediction thiếu:      {metrics['missing_predictions']}")
    print(f"Prediction ngoài tập:  {len(metrics['extra_prediction_ids'])}")
    if not total:
        print("Không có câu để chấm.")
    print("-" * 72)
    print(f"{'Type':<16} | {'Total':>6} | {'Correct':>7} | {'Wrong':>6} | {'Abstain':>7} | {'PA':>8}")
    print("-" * 72)
    for ans_type, stat in sorted(metrics.get("breakdown", {}).items()):
        subtype_total = stat["total"]
        subtype_pa = (stat["correct"] - stat["wrong"]) / subtype_total if subtype_total else 0.0
        print(
            f"{ans_type:<16} | {subtype_total:>6} | {stat['correct']:>7} | "
            f"{stat['wrong']:>6} | {stat['abstain']:>7} | {subtype_pa:>+8.3f}"
        )
    print("=" * 72)


def _load_eval_ids(path: Path | str) -> list[str]:
    """Đọc danh sách eval IDs dạng JSON array, kiểm tra ID rỗng/trùng."""
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, list) or any(not isinstance(qid, str) or not qid for qid in value):
        raise ValueError(f"{file_path}: eval IDs phải là JSON array các ID string")
    if len(value) != len(set(value)):
        raise ValueError(f"{file_path}: eval IDs bị trùng")
    return value


def main() -> None:
    """Định nghĩa CLI: nạp input, chấm, in report và tùy chọn lưu JSON."""
    parser = argparse.ArgumentParser(description="Chấm Penalized Accuracy theo rulebook DataMate")
    parser.add_argument("--pred", required=True, help="JSONL kết quả dự đoán")
    parser.add_argument("--gold", default="benchmark/val_answers.jsonl", help="JSONL đáp án chuẩn")
    parser.add_argument("--val-ids", default="benchmark/val_ids.json", help="JSON array eval IDs")
    parser.add_argument("--report-json", help="Tùy chọn lưu chỉ số ra JSON")
    args = parser.parse_args()

    predictions = load_jsonl_to_dict(args.pred)
    golds = load_jsonl_to_dict(args.gold)
    eval_ids = _load_eval_ids(args.val_ids) if args.val_ids else None
    metrics = evaluate_records(predictions, golds, eval_ids)
    print_report(metrics)

    if args.report_json:
        report_path = Path(args.report_json)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    # Điểm vào khi gọi evaluator từ terminal.
    main()
