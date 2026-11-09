"""
tests/output_abstention/test_abstention.py — Kiểm thử Calibrated Abstention Gate & Grounding Coverage (Phase 4).
"""

from __future__ import annotations

import unittest
from datamate.output_abstention.abstention import (
    compute_confidence_score,
    apply_abstention_gate,
    find_optimal_threshold,
    evaluate_grounding_coverage,
)
from datamate.llm_execution.prompt import build_retry_prompt


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

    # --------------------------------------------------------------------------
    # CÁC TEST CASE CHO GIAI ĐOẠN 4: GROUNDING COVERAGE & CALIBRATED PENALTY
    # --------------------------------------------------------------------------
    def test_mention_grouping_avoids_false_penalty(self):
        """Một mention khớp 2 ứng viên ở 2 bảng khác nhau, code dùng 1 ứng viên -> Không bị phạt oan."""
        matches = [
            {
                "query_term": "Hapacol 650",
                "matched_value": "Hapacol 650mg vỉ 10 viên",
                "score": 0.95,
                "metadata": {"source_table": "TonKho", "source_col": "TenSP"}
            },
            {
                "query_term": "Hapacol 650",
                "matched_value": "Hapacol 650 hộp 100 viên",
                "score": 0.92,
                "metadata": {"source_table": "SanPham", "source_col": "TenHang"}
            }
        ]
        # Code dùng ứng viên 'Hapacol 650'
        code = """
def solution(data):
    df = data['TonKho']
    matched = df[df['TenSP'].str.contains('Hapacol 650', na=False)]
    return int(matched['SoLuong'].sum())
"""
        eval_res = evaluate_grounding_coverage(code_text=code, entity_matches=matches)
        self.assertEqual(eval_res["entity_coverage"], 1.0)
        self.assertEqual(eval_res["entity_penalty"], 0.0)
        self.assertEqual(len(eval_res["missed_mentions"]), 0)

    def test_stopword_filtering(self):
        """Linker khớp từ 'tháng' (score 0.90) nhưng đây là từ chung chung -> Bỏ qua, không phạt oan."""
        matches = [
            {
                "query_term": "tháng",
                "matched_value": "Thang",
                "score": 0.90,
                "metadata": {"source_table": "DonHang", "source_col": "Thang"}
            }
        ]
        code = "def solution(data):\n    return 42"
        eval_res = evaluate_grounding_coverage(code_text=code, entity_matches=matches)
        self.assertEqual(eval_res["total_valid_mentions"], 0)
        self.assertEqual(eval_res["entity_penalty"], 0.0)

    def test_missing_entity_penalized(self):
        """Câu hỏi nhắc tới thực thể cụ thể (Áo thun cotton basic) nhưng code không hề dùng -> Bị phạt."""
        matches = [
            {
                "query_term": "Áo thun",
                "matched_value": "Áo thun cotton basic trắng",
                "score": 0.95,
                "metadata": {"source_table": "HoaDonChiTiet", "source_col": "TenSP"}
            }
        ]
        code = """
def solution(data):
    # Code tính tổng toàn bộ shop mà quên lọc Áo thun
    df = data['HoaDonChiTiet']
    return int(df['ThanhTien'].sum())
"""
        eval_res = evaluate_grounding_coverage(code_text=code, entity_matches=matches)
        self.assertEqual(eval_res["entity_coverage"], 0.0)
        self.assertGreater(eval_res["entity_penalty"], 0.30)
        self.assertEqual(len(eval_res["missed_mentions"]), 1)
        self.assertEqual(eval_res["missed_mentions"][0]["term"], "Áo thun")

    def test_temporal_constraint_penalty(self):
        """Câu hỏi có ràng buộc ngày (Tết 2026: 2026-02-10 -> 2026-02-26) nhưng code không lọc ngày -> Bị phạt."""
        temp_info = {
            "start_date": "2026-02-10",
            "end_date": "2026-02-26",
        }
        code_no_time = """
def solution(data):
    df = data['DonHang']
    return int(df['TongTien'].sum())
"""
        eval_res = evaluate_grounding_coverage(code_text=code_no_time, temporal_info=temp_info)
        self.assertEqual(eval_res["temporal_coverage"], 0.0)
        self.assertEqual(eval_res["temporal_penalty"], 0.25)

    def test_calibrated_confidence_forces_abstain(self):
        """
        KỊCH BẢN QUYẾT ĐỊNH CỦA GIAI ĐOẠN 4:
        Mã chạy thành công không crash (Base = 1.0) nhưng bỏ quên Entity (-0.35) và Ngày (-0.25).
        -> Điểm C = 1.0 - 0.35 - 0.25 = 0.40 < tau* (0.50)
        -> Cổng từ chối ép thành 'abstain', tránh bị phạt -1 điểm!
        """
        matches = [
            {
                "query_term": "Áo thun",
                "matched_value": "Áo thun cotton",
                "score": 0.95,
                "metadata": {"source_table": "HoaDonChiTiet", "source_col": "TenSP"}
            }
        ]
        temp_info = {"start_date": "2026-02-10", "end_date": "2026-02-26"}

        # Code chạy đúng về mặt cú pháp nhưng bỏ sót thực thể & ngày
        code = "def solution(data):\n    df = data['HoaDon']\n    return int(df['TongTien'].sum())\n"
        sub_ans = {"type": "number", "answer": 50000000}

        conf = compute_confidence_score(
            sub_ans=sub_ans,
            exec_error=None,
            exec_ms=50,
            retry_count=0,
            sanity_passed=True,
            code_text=code,
            entity_matches=matches,
            temporal_info=temp_info,
        )
        self.assertLess(conf, 0.50)
        self.assertAlmostEqual(conf, 0.40, places=2)

        # Đưa qua cổng từ chối
        final_ans, is_abs = apply_abstention_gate(sub_ans, confidence=conf, threshold=0.50)
        self.assertTrue(is_abs)
        self.assertEqual(final_ans["type"], "abstain")
        self.assertIn("Confidence 0.40 < threshold 0.50", final_ans["reason"])

    def test_build_retry_prompt_with_missed_mentions(self):
        """Kiểm tra tích hợp missed_mentions vào prompt retry (Feedback ở Turn 2)."""
        missed = [
            {
                "term": "áo thun",
                "candidate": "Áo thun cotton basic",
                "table": "HoaDonChiTiet",
                "col": "TenSP",
                "score": 0.95,
            }
        ]
        sys_p, usr_p = build_retry_prompt(
            question="Doanh thu áo thun",
            failed_code="def solution(data):\n    return 1",
            error_message="Mã chưa lọc theo sản phẩm",
            schema_str="- Bảng 'HoaDonChiTiet': [TenSP, ThanhTien]",
            as_of_date="2026-06-28",
            missed_mentions=missed,
        )
        self.assertIn("GỢI Ý THỰC THỂ BỎ SÓT", usr_p)
        self.assertIn("áo thun", usr_p)
        self.assertIn("Áo thun cotton basic", usr_p)
        self.assertIn("HoaDonChiTiet", usr_p)


if __name__ == "__main__":
    unittest.main()

