"""
Tệp kiểm thử: tests/output_abstention/test_normalizer.py
Mục đích: Kiểm thử tự động Module 6 — Format Normalizer & Tie-Breaker (normalizer.py).
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from typing import Any, Dict, List

# Đảm bảo hiển thị Unicode tiếng Việt trên console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from datamate.output_abstention.normalizer import (
    normalize_output,
    normalize_number,
    normalize_percent,
    normalize_date,
    normalize_boolean,
    normalize_string,
    normalize_list,
    normalize_table,
    apply_tie_breaker,
    check_result_sanity,
)


class TestFormatNormalizer(unittest.TestCase):
    """Bộ kiểm thử cho Module 6: Format Normalizer & Tie-Breaker."""

    def test_normalize_number_currency_and_average(self):
        """Kiểm tra tiền tệ làm tròn số nguyên VND và trung bình không phải tiền làm tròn 2 số lẻ."""
        self.assertEqual(normalize_number(150000.0, is_currency=True), 150000)
        self.assertEqual(normalize_number(4820000.0000, is_currency=True), 4820000)
        self.assertEqual(normalize_number(12500.5, is_currency=True), 12501)
        self.assertEqual(normalize_number(3.4567, is_currency=False, is_average=True), 3.46)

    def test_normalize_number_strings_and_units(self):
        """Kiểm tra bóc tách chuỗi số có đơn vị hoặc dấu phân cách nghìn."""
        self.assertEqual(normalize_number("4.820.000"), 4820000)
        self.assertEqual(normalize_number("4,820,000 VND"), 4820000)
        self.assertEqual(normalize_number("4.82 triệu"), 4820000)
        self.assertEqual(normalize_number("150k"), 150000)
        self.assertEqual(normalize_number(18.6), 18.6)

    def test_normalize_percent_scaling_and_code_guard(self):
        """Kiểm tra nhân 100 cho tỉ lệ thô và chống nhân 100 kép khi code_text đã nhân 100."""
        # Tỉ lệ thô chưa nhân 100 -> nhân 100
        self.assertEqual(normalize_percent(0.124), 12.4)
        self.assertEqual(normalize_percent(0.05), 5)
        self.assertEqual(normalize_percent(-0.075), -7.5)
        # Khi code của LLM đã có * 100.0 (ví dụ tỉ lệ hủy thực tế là 0.91%) -> KHÔNG nhân 100 lần nữa
        self.assertEqual(normalize_percent(0.91, code_text="rate = (cancelled / total) * 100.0\nreturn rate"), 0.91)
        self.assertEqual(normalize_percent(-0.8, code_text="return (a - b) / b * 100"), -0.8)

    def test_medicine_concentration_not_confused_with_percent(self):
        """Kiểm tra câu hỏi chứa nồng độ thuốc (0,1%, 10%) không bị ép nhầm sang kiểu percent."""
        q_med = "Tháng 7/2025 mặt hàng Otrivin 0,1% xịt mũi chai 10ml bán được tổng cộng bao nhiêu chai?"
        res = normalize_output(77, question=q_med)
        self.assertEqual(res, {"type": "number", "answer": 77})

    def test_normalize_date(self):
        """Kiểm tra chuẩn hóa định dạng ngày tháng ISO YYYY-MM-DD và YYYY-MM."""
        self.assertEqual(normalize_date("2026-08-15"), "2026-08-15")
        self.assertEqual(normalize_date("2025-09"), "2025-09")
        self.assertEqual(normalize_date(date(2026, 8, 15)), "2026-08-15")
        self.assertEqual(normalize_date("15/08/2026"), "2026-08-15")
        self.assertEqual(normalize_date("tháng 9/2025"), "2025-09")

    def test_normalize_boolean(self):
        """Kiểm tra chuẩn hóa boolean về True/False chuẩn."""
        self.assertIs(normalize_boolean(True), True)
        self.assertIs(normalize_boolean(False), False)
        self.assertIs(normalize_boolean("có"), True)
        self.assertIs(normalize_boolean("không"), False)
        self.assertIs(normalize_boolean(1), True)
        self.assertIs(normalize_boolean(0), False)

    def test_normalize_string_and_structural_priority(self):
        """Kiểm tra bảo toàn kiểu list, table, string khi câu hỏi có từ khóa 'bao nhiêu' hoặc 'tiền'."""
        # Câu hỏi có chữ 'tiền' nhưng trả về tên khách hàng (string)
        r_str = normalize_output("  Lâm Hoa Long  ", question="Tuần rồi khách nào mua nhiều tiền nhất?")
        self.assertEqual(r_str, {"type": "string", "answer": "Lâm Hoa Long"})

        # Câu hỏi có chữ 'mấy' nhưng trả về [hộp chẵn, cái lẻ] (list)
        r_list = normalize_output([13, 2], question="Cuối ngày hôm nay Bánh croissant còn mấy hộp chẵn, mấy cái lẻ?")
        self.assertEqual(r_list, {"type": "list", "answer": [13, 2]})

        # Câu hỏi có chữ 'bao nhiêu' nhưng trả về bảng công nợ (table)
        r_tbl = normalize_output(
            {"columns": ["Khách hàng", "Còn nợ"], "rows": [["Chị Lan", "3.200.000"]]},
            question="3 khách nào đang nợ nhiều nhất, mỗi người còn nợ bao nhiêu?",
        )
        self.assertEqual(r_tbl, {"type": "table", "answer": {"columns": ["Khách hàng", "Còn nợ"], "rows": [["Chị Lan", 3200000]]}})

    def test_normalize_unanswerable_and_abstain(self):
        """Kiểm tra unanswerable và abstain xuất đúng định dạng."""
        self.assertEqual(normalize_output("unanswerable"), {"type": "unanswerable", "answer": None})
        self.assertEqual(normalize_output({"type": "unanswerable"}), {"type": "unanswerable", "answer": None})
        self.assertEqual(normalize_output(None), {"type": "abstain", "answer": None})

    def test_apply_tie_breaker(self):
        """Kiểm tra giải quyết bằng điểm: xếp phụ theo mã code tăng dần, sau đó theo tên."""
        records = [
            {"ma_sp": "SP002", "ten_sp": "Bạc xỉu", "doanh_thu": 1000000},
            {"ma_sp": "SP001", "ten_sp": "Cà phê sữa", "doanh_thu": 1000000},
            {"ma_sp": "SP003", "ten_sp": "Trà đào", "doanh_thu": 2000000},
        ]
        sorted_records = apply_tie_breaker(records, sort_key="doanh_thu", code_key="ma_sp", descending=True)
        self.assertEqual([r["ma_sp"] for r in sorted_records], ["SP003", "SP001", "SP002"])

    def test_check_result_sanity(self):
        """Kiểm tra bộ lọc tính hợp lý hậu thực thi (Sanity Check)."""
        # 1. Số âm bất thường cho câu hỏi doanh thu
        ans_neg_rev = {"type": "number", "answer": -500000}
        is_sane, err = check_result_sanity(ans_neg_rev, question="Tổng doanh thu tháng này là bao nhiêu?")
        self.assertFalse(is_sane)
        self.assertIn("Số âm bất thường", err)

        # 2. Số âm được phép cho câu hỏi biến động / tăng giảm / lãi lỗ
        is_sane_change, _ = check_result_sanity(ans_neg_rev, question="Doanh thu tăng hay giảm bao nhiêu tiền so với tháng trước?")
        self.assertTrue(is_sane_change)

        # 3. Kết quả 0 vô lý cho câu hỏi xếp hạng mặt hàng bán chạy nhất
        ans_zero = {"type": "number", "answer": 0}
        is_sane_rank, err_rank = check_result_sanity(ans_zero, question="Dịp Tết 2026, mặt hàng nào bán chạy nhất?")
        self.assertFalse(is_sane_rank)
        self.assertIn("vô lý", err_rank)

        # 4. Danh sách rỗng
        ans_empty_list = {"type": "list", "answer": []}
        is_sane_list, err_list = check_result_sanity(ans_empty_list, question="Top 3 mặt hàng bán chạy nhất")
        self.assertFalse(is_sane_list)

        # 5. Kết quả hợp lệ
        ans_valid = {"type": "number", "answer": 12500000}
        is_sane_valid, _ = check_result_sanity(ans_valid, question="Tổng doanh thu tháng này là bao nhiêu?")
        self.assertTrue(is_sane_valid)


if __name__ == "__main__":
    unittest.main()

