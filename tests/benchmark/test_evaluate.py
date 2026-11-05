"""Kiểm tra hợp đồng so khớp answer và tính Penalized Accuracy.

Các test được nhóm theo: format từng answer type, cấu trúc list/table, cách
tính PA và xử lý input lỗi. File này mô tả expected behavior của evaluator;
không tạo hay sửa artifact benchmark thật.
"""

import json
from decimal import Decimal

import pytest

from benchmark.evaluate import (
    compare_value,
    evaluate_records,
    load_jsonl_to_dict,
    print_report,
)


def test_compare_value_types_and_strict_formats():
    """Xác nhận từng type nhận đúng JSON format và áp dụng quy tắc so giá trị."""
    assert compare_value(100000, 100000, "number")
    assert compare_value(100000.0, 100000, "number")
    assert compare_value(0.1 + 0.2, 0.3, "number")
    assert not compare_value(100001, 100000, "number")
    assert compare_value(Decimal("0.30000000000000004"), Decimal("0.3"), "number")
    assert not compare_value(9007199254740992, 9007199254740993, "number")
    assert not compare_value("100000", 100000, "number")
    assert not compare_value(True, 1, "number")

    assert compare_value(12.344, 12.34, "percent")
    assert compare_value(Decimal("-12.345"), Decimal("-12.35"), "percent")
    assert not compare_value(12.345, 12.34, "percent")
    assert not compare_value("12.34", 12.34, "percent")
    assert not compare_value(0.1234, 12.34, "percent")

    assert compare_value(True, True, "boolean")
    assert compare_value(False, False, "boolean")
    assert not compare_value("false", False, "boolean")
    assert not compare_value(0, False, "boolean")

    assert compare_value("2026-08-15", "2026-08-15", "date")
    assert compare_value("2025-09", "2025-09", "date")
    assert not compare_value("2026-02-30", "2026-02-30", "date")
    assert not compare_value("15/08/2026", "2026-08-15", "date")


def test_string_normalization_preserves_accents_and_accepts_aliases():
    """Chuỗi bỏ qua dấu câu/space nhưng phải giữ dấu Việt và giới hạn alias."""
    assert compare_value("Cà phê-sữa!", "cà phê sữa", "string")
    assert compare_value("AB-C", "a b c", "string")
    assert compare_value("CFS", "Cà phê sữa", "string", aliases=["CFS", "Cafe sữa"])
    assert not compare_value("ca phe sua", "cà phê sữa", "string")
    assert not compare_value(["Cà phê sữa"], "Cà phê sữa", "string")


def test_list_is_ordered_and_uses_element_aliases():
    """List phải cùng độ dài/thứ tự; alias được xét ở vị trí của phần tử gold."""
    aliases = [["SP0003"], [], ["SKU-X"]]
    assert compare_value(
        ["SP0003", "B", "SKU-X"],
        ["Tên A", "B", "Tên C"],
        "list",
        aliases=aliases,
    )
    assert not compare_value(["B", "SP0003", "SKU-X"], ["Tên A", "B", "Tên C"], "list", aliases)
    assert not compare_value(["A"], ["A", "B"], "list")
    assert not compare_value("A", ["A"], "list")


def test_table_compares_columns_cells_aliases_and_unordered_rows():
    """Bảng so từng ô, căn cột, nhận alias và không bỏ số lần hàng trùng."""
    gold = {
        "columns": ["khach_hang", "so_tien_no"],
        "rows": [["Alice", 100], ["Bob", 200]],
    }
    aliases = [["KH1"], ["KH2"]]
    pred = {
        "columns": ["so_tien_no", "khach_hang"],
        "rows": [[200, "KH2"], [100, "KH1"]],
    }
    assert compare_value(pred, gold, "table", aliases)

    wrong_cell = {
        "columns": ["khach_hang", "so_tien_no"],
        "rows": [["Alice", 101], ["Bob", 200]],
    }
    assert not compare_value(wrong_cell, gold, "table", aliases)

    wrong_width = {"columns": ["khach_hang", "so_tien_no"], "rows": [["Alice"]]}
    assert not compare_value(wrong_width, gold, "table", aliases)

    duplicate_gold = {"columns": ["x"], "rows": [["A"], ["A"]]}
    one_row = {"columns": ["x"], "rows": [["A"]]}
    assert not compare_value(one_row, duplicate_gold, "table")


def test_table_falls_back_to_column_position_when_names_differ():
    """Tên cột khác thì dùng vị trí; đảo sai vị trí phải bị chấm sai."""
    gold = {"columns": ["Tên", "Số lượng"], "rows": [["Món A", 3]]}
    pred = {"columns": ["Item", "Qty"], "rows": [["món-a", 3]]}
    assert compare_value(pred, gold, "table")
    pred_wrong_position = {"columns": ["Qty", "Item"], "rows": [[3, "Món A"]]}
    assert not compare_value(pred_wrong_position, gold, "table")


def test_evaluate_records_pa_and_missing_extra_counts():
    """PA tính đúng/sai/thiếu một lần mỗi eval ID; prediction thừa bị loại."""
    golds = {
        "q1": {"id": "q1", "type": "number", "answer": 50, "alias": []},
        "q2": {"id": "q2", "type": "string", "answer": "Món A", "alias": []},
        "q3": {"id": "q3", "type": "boolean", "answer": True, "alias": []},
    }
    preds = {
        "q1": {"id": "q1", "type": "number", "answer": 50},
        "q2": {"id": "q2", "type": "string", "answer": "Món B"},
        "extra": {"id": "extra", "type": "number", "answer": 999},
    }

    metrics = evaluate_records(predictions=preds, golds=golds)
    assert metrics["total"] == 3
    assert metrics["correct"] == 1
    assert metrics["wrong"] == 1
    assert metrics["abstain"] == 1
    assert metrics["missing_predictions"] == 1
    assert metrics["extra_prediction_ids"] == ["extra"]
    assert metrics["invalid_format"] == 0
    assert [detail["status"] for detail in metrics["details"]] == ["correct", "wrong", "abstain"]
    assert metrics["coverage"] == pytest.approx(2 / 3, abs=1e-4)
    assert metrics["pa"] == 0.0


def test_unanswerable_and_invalid_reason_follow_rulebook():
    """Unanswerable đúng type được nhận; reason sai type biến record thành abstain."""
    golds = {
        "q1": {"id": "q1", "type": "unanswerable", "answer": None, "alias": []},
        "q2": {"id": "q2", "type": "number", "answer": 1, "alias": []},
    }
    preds = {
        "q1": {"id": "q1", "type": "unanswerable", "reason": "Thiếu dữ liệu"},
        "q2": {"id": "q2", "type": "number", "answer": 1, "reason": 7},
    }
    metrics = evaluate_records(preds, golds)
    assert metrics["correct"] == 1
    assert metrics["abstain"] == 1
    assert metrics["invalid_format"] == 1
    assert metrics["details"][1]["reason"] == "reason_not_string"
    assert metrics["pa"] == 0.5


def test_missing_gold_and_invalid_gold_alias_fail_fast():
    """Thiếu gold hoặc alias sai schema là lỗi dữ liệu, không âm thầm bỏ qua."""
    with pytest.raises(ValueError, match="Thiếu gold"):
        evaluate_records({}, {"q1": {"id": "q1", "type": "number", "answer": 1}}, {"q1", "q2"})

    malformed_gold = {
        "q1": {
            "id": "q1",
            "type": "list",
            "answer": ["A", "B"],
            "alias": [["A-only"]],
        }
    }
    with pytest.raises(ValueError, match="alias sai cấu trúc"):
        evaluate_records({}, malformed_gold)


def test_empty_report_does_not_divide_by_zero(capsys):
    """Tập eval rỗng vẫn tạo report an toàn và không chia cho 0."""
    metrics = evaluate_records({}, {}, set())
    print_report(metrics)
    assert metrics["total"] == 0
    assert "Không có câu để chấm" in capsys.readouterr().out


def test_jsonl_loader_rejects_bad_lines_and_duplicate_ids(tmp_path):
    """Loader báo lỗi cú pháp/ID trùng, còn JSON decimal được giữ dưới dạng Decimal."""
    bad_json = tmp_path / "bad.jsonl"
    bad_json.write_text('{"id":"q1"}\n{bad json}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="JSON không hợp lệ"):
        load_jsonl_to_dict(bad_json)

    duplicate_ids = tmp_path / "duplicate.jsonl"
    duplicate_ids.write_text('{"id":"q1"}\n{"id":"q1"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="ID trùng"):
        load_jsonl_to_dict(duplicate_ids)

    valid = tmp_path / "valid.jsonl"
    valid.write_text('{"id":"q1","type":"number","answer":0.1}\n', encoding="utf-8")
    loaded = load_jsonl_to_dict(valid)
    assert loaded["q1"]["answer"] == Decimal("0.1")
