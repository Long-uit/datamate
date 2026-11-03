"""
Tệp kiểm thử: tests/output/test_normalizer.py
Mục đích: Kiểm thử tự động Module 6 — Format Normalizer & Tie-Breaker (normalizer.py).

================================================================================
CÁC TIÊU CHÍ ĐÁNH GIÁ ĐẶT RA:
1. Chuẩn hóa kiểu 'number' (Điều 9 Rulebook):
   - Tiền tệ ép về số nguyên VND (loại bỏ phần thập phân .0000 của POS).
   - Trung bình không phải tiền (số món/đơn, số đơn/ngày) làm tròn 2 chữ số thập phân.
   - Xử lý chuỗi có đơn vị hoặc dấu phân cách nghìn ("4.820.000đ", "4820K", "4.82 triệu").
2. Chuẩn hóa kiểu 'percent' (Điều 9 Rulebook):
   - Tự động nhân 100 nếu giá trị nằm trong [-1, 1] khác 0 VÀ code_text chưa nhân 100 (0.124 -> 12.4).
   - Không nhân 100 lần thứ hai nếu code_text đã có `* 100` (bảo vệ các đáp án tỉ lệ nhỏ <= 1% như 0.91%).
   - Không nhận nhầm nồng độ thuốc ('Otrivin 0,1%', 'Povidine 10%') là câu hỏi percent.
3. Chuẩn hóa kiểu 'date' (Điều 9 Rulebook):
   - Chuỗi ISO YYYY-MM-DD hoặc YYYY-MM; chuyển đổi DD/MM/YYYY và tháng M/YYYY.
4. Chuẩn hóa kiểu 'boolean' (Điều 9 Rulebook):
   - True / False thuần; nhận diện 'có', 'không', 'đúng', 'sai', 1, 0.
5. Chuẩn hóa kiểu 'string' (Điều 9 Rulebook):
   - Giữ nguyên dấu tiếng Việt, chuẩn hóa Unicode NFC, loại bỏ khoảng trắng thừa.
6. Chuẩn hóa kiểu 'list' và 'table' (Điều 9 Rulebook):
   - Ưu tiên cấu trúc thực tế của raw_val (list, table, string) ngay cả khi câu hỏi có chữ 'bao nhiêu' hay 'tiền'.
7. Chuẩn hóa 'unanswerable' và 'abstain':
   - unanswerable -> {"type": "unanswerable", "answer": None}.
   - abstain -> {"type": "abstain", "answer": None}.
8. Quy tắc đồng hạng (Điều 9 Tie-Breaker):
   - Khi bằng điểm ở tiêu chí chính, xếp phụ theo MÃ CODE tăng dần; nếu không có mã thì theo TÊN tăng dần.
================================================================================
"""

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

from datamate.output.normalizer import (
    normalize_output,
    normalize_number,
    normalize_percent,
    normalize_date,
    normalize_boolean,
    normalize_string,
    normalize_list,
    normalize_table,
    apply_tie_breaker,
)


class TestFormatNormalizer(unittest.TestCase):
    """Bộ kiểm thử cho Module 6: Format Normalizer & Tie-Breaker."""

    def test_normalize_number_currency_and_average(self):
        """Kiểm tra tiền tệ làm tròn số nguyên VND và trung bình không phải tiền làm tròn 2 số lẻ."""
        criterion = "Chỉ tiêu 1.1: Tiền tệ làm tròn số nguyên VND, trung bình không phải tiền làm tròn 2 số thập phân"
        try:
            self.assertEqual(normalize_number(150000.0, is_currency=True), 150000)
            self.assertEqual(normalize_number(4820000.0000, is_currency=True), 4820000)
            self.assertEqual(normalize_number(12500.5, is_currency=True), 12501)
            self.assertEqual(normalize_number(3.4567, is_currency=False, is_average=True), 3.46)
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_normalize_number_strings_and_units(self):
        """Kiểm tra bóc tách chuỗi số có đơn vị hoặc dấu phân cách nghìn."""
        criterion = "Chỉ tiêu 1.2: Bóc tách chuỗi số có ký hiệu đơn vị, từ viết tắt hoặc dấu phân cách"
        try:
            self.assertEqual(normalize_number("4.820.000"), 4820000)
            self.assertEqual(normalize_number("4,820,000 VND"), 4820000)
            self.assertEqual(normalize_number("4.82 triệu"), 4820000)
            self.assertEqual(normalize_number("150k"), 150000)
            self.assertEqual(normalize_number(18.6), 18.6)
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_normalize_percent_scaling_and_code_guard(self):
        """Kiểm tra nhân 100 cho tỉ lệ thô và chống nhân 100 kép khi code_text đã nhân 100."""
        criterion = "Chỉ tiêu 2.1: Tự động nhân 100 cho tỉ lệ thô và giữ nguyên tỉ lệ nhỏ <=1% khi code đã nhân 100"
        try:
            # Tỉ lệ thô chưa nhân 100 -> nhân 100
            self.assertEqual(normalize_percent(0.124), 12.4)
            self.assertEqual(normalize_percent(0.05), 5)
            self.assertEqual(normalize_percent(-0.075), -7.5)
            # Khi code của LLM đã có * 100.0 (ví dụ tỉ lệ hủy thực tế là 0.91%) -> KHÔNG nhân 100 lần nữa
            self.assertEqual(normalize_percent(0.91, code_text="rate = (cancelled / total) * 100.0\nreturn rate"), 0.91)
            self.assertEqual(normalize_percent(-0.8, code_text="return (a - b) / b * 100"), -0.8)
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_medicine_concentration_not_confused_with_percent(self):
        """Kiểm tra câu hỏi chứa nồng độ thuốc (0,1%, 10%) không bị ép nhầm sang kiểu percent."""
        criterion = "Chỉ tiêu 2.2: Phân biệt chính xác nồng độ thuốc ('Otrivin 0,1%') với câu hỏi phần trăm"
        try:
            q_med = "Tháng 7/2025 mặt hàng Otrivin 0,1% xịt mũi chai 10ml bán được tổng cộng bao nhiêu chai?"
            res = normalize_output(77, question=q_med)
            self.assertEqual(res, {"type": "number", "answer": 77})
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_normalize_date(self):
        """Kiểm tra chuẩn hóa định dạng ngày tháng ISO YYYY-MM-DD và YYYY-MM."""
        criterion = "Chỉ tiêu 3.1: Chuẩn hóa date về ISO YYYY-MM-DD hoặc YYYY-MM"
        try:
            self.assertEqual(normalize_date("2026-08-15"), "2026-08-15")
            self.assertEqual(normalize_date("2025-09"), "2025-09")
            self.assertEqual(normalize_date(date(2026, 8, 15)), "2026-08-15")
            self.assertEqual(normalize_date("15/08/2026"), "2026-08-15")
            self.assertEqual(normalize_date("tháng 9/2025"), "2025-09")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_normalize_boolean(self):
        """Kiểm tra chuẩn hóa boolean về True/False chuẩn."""
        criterion = "Chỉ tiêu 4.1: Chuẩn hóa boolean từ True/False, chuỗi 'có'/'không', 1/0"
        try:
            self.assertIs(normalize_boolean(True), True)
            self.assertIs(normalize_boolean(False), False)
            self.assertIs(normalize_boolean("có"), True)
            self.assertIs(normalize_boolean("không"), False)
            self.assertIs(normalize_boolean(1), True)
            self.assertIs(normalize_boolean(0), False)
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_normalize_string_and_structural_priority(self):
        """Kiểm tra bảo toàn kiểu list, table, string khi câu hỏi có từ khóa 'bao nhiêu' hoặc 'tiền'."""
        criterion = "Chỉ tiêu 5.1: Bảo toàn cấu trúc list/table/string trước từ khóa 'bao nhiêu'/'tiền' trong câu hỏi"
        try:
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
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_normalize_unanswerable_and_abstain(self):
        """Kiểm tra unanswerable và abstain xuất đúng định dạng."""
        criterion = "Chỉ tiêu 6.1: Xử lý đúng cấu trúc unanswerable và abstain"
        try:
            self.assertEqual(normalize_output("unanswerable"), {"type": "unanswerable", "answer": None})
            self.assertEqual(normalize_output({"type": "unanswerable"}), {"type": "unanswerable", "answer": None})
            self.assertEqual(normalize_output(None), {"type": "abstain", "answer": None})
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_apply_tie_breaker(self):
        """Kiểm tra giải quyết bằng điểm: xếp phụ theo mã code tăng dần, sau đó theo tên."""
        criterion = "Chỉ tiêu 7.1: Giải quyết đồng hạng (Tie-Breaker) theo mã code tăng dần theo Điều 9"
        try:
            records = [
                {"ma_sp": "SP002", "ten_sp": "Bạc xỉu", "doanh_thu": 1000000},
                {"ma_sp": "SP001", "ten_sp": "Cà phê sữa", "doanh_thu": 1000000},
                {"ma_sp": "SP003", "ten_sp": "Trà đào", "doanh_thu": 2000000},
            ]
            sorted_records = apply_tie_breaker(records, sort_key="doanh_thu", code_key="ma_sp", descending=True)
            self.assertEqual([r["ma_sp"] for r in sorted_records], ["SP003", "SP001", "SP002"])
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise


if __name__ == "__main__":
    print("=" * 80)
    print("KIỂM THỬ MODULE 6: FORMAT NORMALIZER & TIE-BREAKER (normalizer.py)")
    print("=" * 80)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestFormatNormalizer)
    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)
    print("-" * 80)
    print(f"Kết quả: {result.testsRun} bài kiểm thử đã chạy.")
    if result.wasSuccessful():
        print("Tất cả các tiêu chí kiểm thử Format Normalizer đều ĐẠT (100% PASS).")
    else:
        print(f"Có {len(result.failures)} lỗi và {len(result.errors)} ngoại lệ.")
        sys.exit(1)
