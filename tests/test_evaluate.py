"""
tests/test_evaluate.py
Unit tests cho scripts/evaluate.py:
  - Kiểm tra thuật toán so khớp 8 kiểu đáp án chuẩn Mục 9 Rulebook
  - Kiểm tra tính toán Penalized Accuracy (PA), Accuracy, Coverage
  - Kiểm tra diff mode, phát hiện đảo trạng thái (state flips) và cảnh báo regression
"""

import json
import pytest
from decimal import Decimal
from pathlib import Path
from scripts.keep.evaluate import (
    compare_single_answer,
    _numeric_equal,
    _norm_str,
    evaluate_predictions,
    diff_evaluation_reports,
)


def test_numeric_equal_integer_and_float():
    # Số nguyên phải khớp chính xác
    assert _numeric_equal(100, 100)
    assert not _numeric_equal(100, 101)

    # Decimal / Float
    assert _numeric_equal(10.5, Decimal("10.5"))
    assert _numeric_equal(123.45, Decimal("123.45"))
    assert not _numeric_equal(10.5, 10.6)


def test_compare_number_type():
    pred = {"type": "number", "answer": 500000}
    gold = {"type": "number", "answer": 500000}
    ok, reason = compare_single_answer(pred, gold)
    assert ok and reason is None

    pred_wrong = {"type": "number", "answer": 499999}
    ok2, reason2 = compare_single_answer(pred_wrong, gold)
    assert not ok2 and "không khớp" in reason2


def test_compare_percent_type_rounding():
    # Percent làm tròn 2 chữ số thập phân
    pred = {"type": "percent", "answer": 12.344}
    gold = {"type": "percent", "answer": 12.34}
    ok, _ = compare_single_answer(pred, gold)
    assert ok

    pred2 = {"type": "percent", "answer": 12.346}  # Làm tròn thành 12.35
    ok2, reason = compare_single_answer(pred2, gold)
    assert not ok2 and "12.35" in reason


def test_compare_string_and_aliases():
    pred = {"type": "string", "answer": "Cà Phê Sữa"}
    gold = {"type": "string", "answer": "cà phê sữa", "alias": ["cf sua", "cafe sua"]}
    ok, _ = compare_single_answer(pred, gold)
    assert ok

    pred_alias = {"type": "string", "answer": "CF SUA"}
    ok_alias, _ = compare_single_answer(pred_alias, gold)
    assert ok_alias


def test_compare_unanswerable_and_abstain():
    pred = {"type": "unanswerable", "answer": None}
    gold = {"type": "unanswerable", "answer": None}
    ok, _ = compare_single_answer(pred, gold)
    assert ok


def test_compare_list():
    pred = {"type": "list", "answer": ["Mì tôm", "Bột ngọt", 100]}
    gold = {"type": "list", "answer": ["mì tôm", "bột ngọt", "100"]}
    ok, _ = compare_single_answer(pred, gold)
    assert ok

    pred_short = {"type": "list", "answer": ["Mì tôm"]}
    ok2, reason = compare_single_answer(pred_short, gold)
    assert not ok2 and "Độ dài list không khớp" in reason


def test_compare_table():
    pred = {
        "type": "table",
        "answer": {
            "columns": ["Tên Hàng", "Doanh Thu"],
            "rows": [["Mì Hảo Hảo", 1000], ["Nước ngọt", 2000]],
        },
    }
    gold = {
        "type": "table",
        "answer": {
            "columns": ["tên hàng", "doanh thu"],
            "rows": [["Nước ngọt", "2000"], ["mì hảo hảo", 1000]],  # Khác thứ tự dòng
        },
    }
    ok, _ = compare_single_answer(pred, gold)
    assert ok


def test_evaluate_predictions_end_to_end(tmp_path):
    preds_file = tmp_path / "preds.jsonl"
    golds_file = tmp_path / "golds.jsonl"

    preds = [
        {"id": "q1", "type": "number", "answer": 100},  # Correct (+1)
        {"id": "q2", "type": "number", "answer": 200},  # Wrong (-1)
        {"id": "q3", "type": "abstain", "answer": None},  # Abstain (0)
        {"id": "q4", "type": "percent", "answer": 50.0},  # Correct (+1)
    ]
    golds = [
        {"id": "q1", "type": "number", "answer": 100},
        {"id": "q2", "type": "number", "answer": 999},
        {"id": "q3", "type": "number", "answer": 50},
        {"id": "q4", "type": "percent", "answer": 50.001},
    ]

    with open(preds_file, "w", encoding="utf-8") as f:
        for p in preds:
            f.write(json.dumps(p) + "\n")
    with open(golds_file, "w", encoding="utf-8") as f:
        for g in golds:
            f.write(json.dumps(g) + "\n")

    report = evaluate_predictions(preds_file, golds_file)
    s = report["summary"]
    assert s["total"] == 4
    assert s["correct"] == 2
    assert s["wrong"] == 1
    assert s["abstain"] == 1
    # PA = (2 - 1) / 4 = 0.25
    assert s["pa"] == 0.25
    assert s["coverage"] == 0.75
    # Accuracy = 2 / (2 + 1) = 0.6667
    assert s["accuracy"] == 0.6667


def test_diff_reports(tmp_path):
    run1_path = tmp_path / "run1.json"
    run2_path = tmp_path / "run2.json"

    rep1 = {
        "summary": {"pa": -0.25, "correct": 1, "wrong": 2, "abstain": 1, "total": 4},
        "per_question": [
            {"id": "q1", "status": "wrong", "score": -1.0, "pred_val": 50, "gold_val": 100},
            {"id": "q2", "status": "correct", "score": 1.0, "pred_val": 200, "gold_val": 200},
            {"id": "q3", "status": "abstain", "score": 0.0, "pred_val": None, "gold_val": 300},
            {"id": "q4", "status": "wrong", "score": -1.0, "pred_val": 40, "gold_val": 400},
        ],
    }

    rep2 = {
        "summary": {"pa": 0.50, "correct": 3, "wrong": 1, "abstain": 0, "total": 4},
        "per_question": [
            {"id": "q1", "status": "correct", "score": 1.0, "pred_val": 100, "gold_val": 100},  # wrong -> correct (+2)
            {"id": "q2", "status": "correct", "score": 1.0, "pred_val": 200, "gold_val": 200},  # no change
            {"id": "q3", "status": "correct", "score": 1.0, "pred_val": 300, "gold_val": 300},  # abstain -> correct (+1)
            {"id": "q4", "status": "wrong", "score": -1.0, "pred_val": 40, "gold_val": 400},    # no change
        ],
    }

    with open(run1_path, "w", encoding="utf-8") as f:
        json.dump(rep1, f)
    with open(run2_path, "w", encoding="utf-8") as f:
        json.dump(rep2, f)

    diff = diff_evaluation_reports(run1_path, run2_path)
    assert diff["pa_delta"] == 0.75
    assert diff["correct_delta"] == 2
    assert diff["wrong_delta"] == -1
    assert diff["total_flips"] == 2
    assert diff["total_regressions_to_wrong"] == 0
    assert len(diff["improvements"]) == 2
