"""
test_evaluate.py — Kiểm thử bộ tính điểm Penalized Accuracy (PA).
"""

from benchmark.evaluate import compare_value, evaluate_records


def test_compare_value_types():
    # Number
    assert compare_value(100000, 100000, "number") is True
    assert compare_value(100000.0, 100000, "number") is True
    assert compare_value(100001, 100000, "number") is False

    # Percent
    assert compare_value(12.34, 12.34, "percent") is True
    assert compare_value(12.344, 12.34, "percent") is True

    # Boolean
    assert compare_value(True, True, "boolean") is True
    assert compare_value(False, True, "boolean") is False

    # String & Alias
    assert compare_value("Cà phê sữa", "cà phê sữa", "string") is True
    assert compare_value("CFS", "Cà phê sữa", "string", aliases=["CFS", "Cafe sữa"]) is True

    # List
    assert compare_value(["A", "B"], ["A", "B"], "list") is True
    assert compare_value(["B", "A"], ["A", "B"], "list") is False

    # Unanswerable
    assert compare_value(None, None, "unanswerable") is True


def test_evaluate_records_pa_calculation():
    """
    3 câu:
    - Câu 1 đúng (+1)
    - Câu 2 sai (-1)
    - Câu 3 abstain (0)
    PA = (1 - 1) / 3 = 0.0
    """
    golds = {
        "q1": {"id": "q1", "type": "number", "answer": 50},
        "q2": {"id": "q2", "type": "string", "answer": "Món A"},
        "q3": {"id": "q3", "type": "boolean", "answer": True},
    }
    preds = {
        "q1": {"id": "q1", "type": "number", "answer": 50},       # Đúng (+1)
        "q2": {"id": "q2", "type": "string", "answer": "Món B"},   # Sai (-1)
        "q3": {"id": "q3", "type": "abstain", "answer": None},     # Abstain (0)
    }

    metrics = evaluate_records(predictions=preds, golds=golds)
    assert metrics["total"] == 3
    assert metrics["correct"] == 1
    assert metrics["wrong"] == 1
    assert metrics["abstain"] == 1
    assert metrics["pa"] == 0.0


def test_evaluate_records_perfect_score():
    golds = {
        "q1": {"id": "q1", "type": "unanswerable", "answer": None},
        "q2": {"id": "q2", "type": "number", "answer": 120},
    }
    preds = {
        "q1": {"id": "q1", "type": "unanswerable", "answer": None},
        "q2": {"id": "q2", "type": "number", "answer": 120},
    }
    metrics = evaluate_records(predictions=preds, golds=golds)
    assert metrics["correct"] == 2
    assert metrics["wrong"] == 0
    assert metrics["pa"] == 1.0
