"""
test_abstention.py — Kiểm thử Calibrated Abstention Gate (Module 6.2).
"""

import unittest
from datamate.output.abstention import (
    compute_confidence_score,
    apply_abstention_gate,
    find_optimal_threshold,
)


class TestAbstentionGate(unittest.TestCase):
    def test_compute_confidence_healthy(self):
        sub_ans = {"type": "number", "answer": 1500000}
        code = "def solution(data):\n    # Calculate valid total revenue\n    return 1500000"
        conf = compute_confidence_score(
            sub_ans=sub_ans,
            exec_error=None,
            exec_ms=120,
            retry_count=0,
            sanity_passed=True,
            code_text=code,
        )
        self.assertGreaterEqual(conf, 0.90)

    def test_compute_confidence_error_or_insane(self):
        # Có lỗi thực thi
        sub_ans = {"type": "abstain", "answer": None}
        conf = compute_confidence_score(
            sub_ans=sub_ans,
            exec_error="KeyError: 'thanh_tien'",
            sanity_passed=False,
        )
        self.assertEqual(conf, 0.0)

    def test_apply_abstention_gate_rejection(self):
        sub_ans = {"type": "number", "answer": 120}
        # Điểm tin cậy 0.40 dưới ngưỡng 0.50 -> Bị ép về abstain
        final_ans, is_abs = apply_abstention_gate(sub_ans, confidence=0.40, threshold=0.50)
        self.assertTrue(is_abs)
        self.assertEqual(final_ans["type"], "abstain")

        # Điểm tin cậy 0.75 trên ngưỡng 0.50 -> Được giữ nguyên
        final_ans2, is_abs2 = apply_abstention_gate(sub_ans, confidence=0.75, threshold=0.50)
        self.assertFalse(is_abs2)
        self.assertEqual(final_ans2["type"], "number")
        self.assertEqual(final_ans2["answer"], 120)

    def test_find_optimal_threshold(self):
        preds = [
            {"id": "q1", "answer": {"type": "number", "answer": 10}, "confidence": 0.95}, # Đúng
            {"id": "q2", "answer": {"type": "number", "answer": 99}, "confidence": 0.30}, # Sai, confidence thấp
            {"id": "q3", "answer": {"type": "number", "answer": 20}, "confidence": 0.85}, # Đúng
        ]
        golds = [
            {"id": "q1", "type": "number", "answer": 10},
            {"id": "q2", "type": "number", "answer": 50},
            {"id": "q3", "type": "number", "answer": 20},
        ]
        best_tau, best_pa = find_optimal_threshold(preds, golds, threshold_candidates=[0.20, 0.50, 0.80])
        # Ngưỡng 0.50 loại bỏ q2 (nhận 0 điểm thay vì -1), giữ q1 và q3 (+2 điểm) -> PA = 2/3 = 0.67
        self.assertGreaterEqual(best_pa, 0.66)
        self.assertEqual(best_tau, 0.50)


if __name__ == "__main__":
    unittest.main()
