"""
test_error_analysis.py — Kiểm thử công cụ phân tích lỗi (Task 4 Phase 3).
"""

import pytest

from benchmark.error_analysis import (
    classify_error,
    generate_markdown_report,
    run_error_analysis,
)


class TestErrorAnalysis:
    def test_classify_correct_numeric(self):
        pred = {"id": "q1", "type": "number", "answer": 150000}
        truth = {"id": "q1", "type": "number", "answer": 150000}
        score, cat, _ = classify_error(pred, truth)
        assert score == 1
        assert "CORRECT" in cat

    def test_classify_unanswerable_cases(self):
        # 1. Unanswerable đúng -> +1
        p1 = {"type": "unanswerable", "answer": None}
        t1 = {"type": "unanswerable", "answer": None}
        score1, cat1, _ = classify_error(p1, t1)
        assert score1 == 1
        assert cat1 == "CORRECT_UNANSWERABLE"

        # 2. Đáng lẽ unanswerable nhưng cố đoán số -> -1 (UNANSWERABLE_MISSED)
        p2 = {"type": "number", "answer": 5000}
        t2 = {"type": "unanswerable", "answer": None}
        score2, cat2, _ = classify_error(p2, t2)
        assert score2 == -1
        assert cat2 == "UNANSWERABLE_MISSED"

        # 3. Có đáp án nhưng lại báo unanswerable -> -1 (UNANSWERABLE_FALSE_POSITIVE)
        p3 = {"type": "unanswerable", "answer": None}
        t3 = {"type": "number", "answer": 5000}
        score3, cat3, _ = classify_error(p3, t3)
        assert score3 == -1
        assert cat3 == "UNANSWERABLE_FALSE_POSITIVE"

    def test_run_analysis_and_report(self):
        preds = [
            {"id": "q1", "type": "number", "answer": 100},
            {"id": "q2", "type": "number", "answer": 200},  # Sai
            {"id": "q3", "type": "abstain", "answer": None},  # 0 điểm
        ]
        truth = [
            {"id": "q1", "question": "Câu 1", "type": "number", "answer": 100},
            {"id": "q2", "question": "Câu 2", "type": "number", "answer": 300},
            {"id": "q3", "question": "Câu 3", "type": "number", "answer": 500},
        ]
        summary = run_error_analysis(preds, truth)
        assert summary.total == 3
        assert summary.correct == 1
        assert summary.wrong == 1
        assert summary.abstain == 1
        # PA = (1 - 1) / 3 = 0.0
        assert summary.penalized_accuracy == 0.0

        # Kiểm tra sinh báo cáo Markdown
        report = generate_markdown_report(summary)
        assert "# 📊 BÁO CÁO PHÂN TÍCH LỖI VÀ ĐỘ TIN CẬY" in report
        assert "Penalized Accuracy (PA)" in report

