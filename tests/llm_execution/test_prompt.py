"""
Tệp kiểm thử: tests/llm_execution/test_prompt.py
Mục đích: Kiểm thử tự động các chức năng của module src/datamate/llm_execution/prompt.py.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Đảm bảo console Windows hiển thị đúng tiếng Việt có dấu
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from datamate.llm_execution.prompt import (
    classify_intent,
    select_few_shots,
    resolve_temporal_context,
    build_prompt,
    TET_SOLAR_RANGES,
    FEW_SHOT_LIBRARY,
)


class TestPromptBuilder(unittest.TestCase):
    """Bộ kiểm thử cho các chức năng trong prompt.py."""

    # --------------------------------------------------------------------------
    # Tiêu chí 1: Phân loại ý định câu hỏi
    # --------------------------------------------------------------------------
    def test_classify_intent_aggregation(self):
        """Kiểm tra nhận diện câu hỏi tính tổng tiền / đếm số đơn."""
        q1 = "Tổng doanh thu tháng 5 năm 2025 là bao nhiêu?"
        q2 = "tháng này tổng số lượng sản phẩm bán ra là bao nhiêu"
        self.assertEqual(classify_intent(q1), "aggregation")
        self.assertEqual(classify_intent(q2), "aggregation")

    def test_classify_intent_purchase_import(self):
        """Kiểm tra nhận diện câu hỏi nhóm nhập hàng / phiếu nhập."""
        q = "tháng này tổng giá trị các phiếu nhập hàng là bao nhiu"
        self.assertEqual(classify_intent(q), "purchase_import")

    def test_classify_intent_rate_percentage(self):
        """Kiểm tra nhận diện câu hỏi tính tỉ lệ hoặc phần trăm."""
        q1 = "tháng 9/2025 cửa hangf có bao nhiêu % đơn bij huỷ"
        q2 = "tỉ lệ hủy đơn của shop trong tháng 6 là bao nhiêu"
        q3 = "doanh thu khách thân thiết chiếm bao nhiêu phần trăm tổng doanh thu"
        self.assertEqual(classify_intent(q1), "rate_percentage")
        self.assertEqual(classify_intent(q2), "rate_percentage")
        self.assertEqual(classify_intent(q3), "rate_percentage")

    def test_classify_intent_ranking_topk(self):
        """Kiểm tra nhận diện câu hỏi xếp hạng hoặc tìm đối tượng nhiều nhất."""
        q1 = "Dịp Tết 2026, mặt hàng nào bán chạy nhất ạ?"
        q2 = "Khách hàng nào mua nhiều tiền nhất trong tháng vừa rồi?"
        q3 = "Top 3 mặt hàng mang lại doanh thu cao nhất"
        self.assertEqual(classify_intent(q1), "ranking_topk")
        self.assertEqual(classify_intent(q2), "ranking_topk")
        self.assertEqual(classify_intent(q3), "ranking_topk")

    def test_classify_intent_multitable_join(self):
        """Kiểm tra nhận diện câu hỏi tra cứu hoạt chất hoặc quy đổi đơn vị giữa nhiều bảng."""
        q1 = "Thuốc có hoạt chất Paracetamol tháng này bán được bao nhiêu tiền?"
        q2 = "Thuốc kê đơn nào có doanh thu cao nhất tháng 7/2025?"
        q3 = "Hàng bán theo đơn vị quy đổi lớn là bao nhiêu thùng?"
        self.assertEqual(classify_intent(q1), "multitable_join")
        self.assertEqual(classify_intent(q2), "multitable_join")
        self.assertEqual(classify_intent(q3), "multitable_join")

    def test_classify_intent_time_series(self):
        """Kiểm tra nhận diện câu hỏi so sánh chuỗi thời gian."""
        q = "Cho mình hỏi doanh thu 3 tháng 6/2026, 7/2026, 8/2026 có tăng liên tục không?"
        self.assertEqual(classify_intent(q), "time_series")

    def test_classify_intent_unanswerable_suspect(self):
        """Kiểm tra nhận diện câu hỏi hỏi thông tin không có trong hồ sơ kinh doanh."""
        q = "nhân viên nào có tay nghề cao nhất tiệm"
        self.assertEqual(classify_intent(q), "unanswerable_suspect")

    def test_classify_intent_inventory_unit_conversion(self):
        """Kiểm tra nhận diện câu hỏi quy đổi đơn vị và tồn kho (hộp chẵn, viên lẻ)."""
        q1 = "Hiện tại thuốc Hapacol 650 còn tồn bao nhiêu hộp và viên lẻ?"
        q2 = "Cho biết số lượng tồn kho theo hộp và viên"
        self.assertEqual(classify_intent(q1), "inventory_unit_conversion")
        self.assertEqual(classify_intent(q2), "inventory_unit_conversion")
        few_shot = select_few_shots("inventory_unit_conversion")
        self.assertIn("TỒN KHO & QUY ĐỔI ĐƠN VỊ", few_shot)
        self.assertIn("divmod", few_shot)

    # --------------------------------------------------------------------------
    # Tiêu chí 2: Lựa chọn ví dụ mẫu động (Dynamic Few-shot)
    # --------------------------------------------------------------------------
    def test_select_few_shots_selection(self):
        """Kiểm tra chọn đúng ví dụ theo intent và không bị thừa ví dụ khác."""
        few_shot_rate = select_few_shots("rate_percentage")
        self.assertIn("TỈ LỆ PHẦN TRĂM", few_shot_rate)
        self.assertNotIn("Dịp Tết 2026, mặt hàng nào bán chạy nhất", few_shot_rate)

        few_shot_rank = select_few_shots("ranking_topk")
        self.assertIn("XẾP HẠNG TOP", few_shot_rank)
        self.assertNotIn("TỈ LỆ PHẦN TRĂM", few_shot_rank)

        few_shot_unans = select_few_shots("unanswerable_suspect")
        self.assertIn("CÂU HỎI THIẾU DỮ LIỆU", few_shot_unans)

    def test_few_shot_time_series(self):
        """Kiểm tra ví dụ mẫu cho intent time_series."""
        few_shot = select_few_shots("time_series")
        self.assertIn("TĂNG TRƯỞNG DOANH THU", few_shot)
        self.assertIn("revenue", few_shot)

    # --------------------------------------------------------------------------
    # Tiêu chí 3: Giải mã thời gian tự động (Temporal Grounding)
    # --------------------------------------------------------------------------
    def test_resolve_temporal_context_tet_2026(self):
        """Kiểm tra giải mã mốc Tết 2026 sang ngày dương lịch chuẩn."""
        q = "Dịp Tết 2026, mặt hàng nào bán chạy nhất ạ?"
        res = resolve_temporal_context(q, as_of_date_str="2026-06-28")
        self.assertEqual(res["start_date"], "2026-02-10")
        self.assertEqual(res["end_date"], "2026-02-26")
        self.assertIn("2026-02-10", res["code_hint"])
        self.assertIn("2026-02-26", res["code_hint"])

    def test_resolve_temporal_context_tet_2025(self):
        """Kiểm tra giải mã mốc Tết 2025 sang ngày dương lịch chuẩn."""
        q = "Dịp Tết năm 2025 cửa hàng có bao nhiêu đơn hàng?"
        res = resolve_temporal_context(q, as_of_date_str="2025-06-01")
        self.assertEqual(res["start_date"], "2025-01-22")
        self.assertEqual(res["end_date"], "2025-02-07")

    def test_resolve_temporal_context_n_days_recent(self):
        """Kiểm tra giải mã 7 ngày gần nhất kết thúc tại ngày as_of_date."""
        q = "7 ngày gần nhất doanh thu được bao nhiêu?"
        res = resolve_temporal_context(q, as_of_date_str="2025-09-09")
        self.assertEqual(res["start_date"], "2025-09-03")
        self.assertEqual(res["end_date"], "2025-09-09")

    def test_resolve_temporal_context_specific_month(self):
        """Kiểm tra giải mã tháng cụ thể (ví dụ: tháng 9/2025)."""
        q = "tháng 9/2025 cửa hàng có bao nhiêu đơn bị hủy"
        res = resolve_temporal_context(q, as_of_date_str="2026-05-25")
        self.assertEqual(res["start_date"], "2025-09-01")
        self.assertEqual(res["end_date"], "2025-09-30")

    def test_resolve_temporal_context_this_month(self):
        """Kiểm tra giải mã 'tháng này' từ ngày 1 đến hết ngày as_of_date."""
        q = "Tháng này doanh thu được bao nhiêu tiền?"
        res = resolve_temporal_context(q, as_of_date_str="2026-09-14")
        self.assertEqual(res["start_date"], "2026-09-01")
        self.assertEqual(res["end_date"], "2026-09-14")

    def test_resolve_temporal_context_today(self):
        """Kiểm tra giải mã từ 'hôm nay'."""
        q = "Hôm nay có bao nhiêu khách mua hàng?"
        res = resolve_temporal_context(q, as_of_date_str="2026-05-20")
        self.assertEqual(res["start_date"], "2026-05-20")
        self.assertEqual(res["end_date"], "2026-05-20")

    def test_temporal_comparison_period(self):
        """Kiểm tra giải mã kỳ chính và kỳ đối chiếu khi câu hỏi yêu cầu so sánh với tháng trước."""
        q = "Doanh thu tháng này tăng bao nhiêu so với tháng trước?"
        res = resolve_temporal_context(q, as_of_date_str="2026-05-15")
        self.assertEqual(res["start_date"], "2026-05-01")
        self.assertEqual(res["end_date"], "2026-05-15")
        self.assertEqual(res["comparison_start"], "2026-04-01")
        self.assertEqual(res["comparison_end"], "2026-04-15")
        self.assertIn("Kỳ đối chiếu", res["description"])

    def test_temporal_half_month(self):
        """Kiểm tra giải mã nửa đầu / nửa cuối tháng."""
        q1 = "Nửa đầu tháng 5/2026 doanh thu là bao nhiêu?"
        res1 = resolve_temporal_context(q1, as_of_date_str="2026-05-25")
        self.assertEqual(res1["start_date"], "2026-05-01")
        self.assertEqual(res1["end_date"], "2026-05-15")

        q2 = "Nửa cuối tháng 5/2026 có bao nhiêu đơn hàng?"
        res2 = resolve_temporal_context(q2, as_of_date_str="2026-06-01")
        self.assertEqual(res2["start_date"], "2026-05-16")
        self.assertEqual(res2["end_date"], "2026-05-31")

    # --------------------------------------------------------------------------
    # Tiêu chí 4 & 5: Cấu trúc Prompt hoàn chỉnh và phân chia ChatML
    # --------------------------------------------------------------------------
    def test_build_prompt_string_output(self):
        """Kiểm tra tạo prompt dạng chuỗi gộp truyền thống."""
        schema = "- Bảng 'DonHang': [Mã đơn, Ngày đặt, Thành tiền]"
        prompt_str = build_prompt(
            schema_str=schema,
            as_of_date="2026-05-25",
            question="Tháng này bán được bao nhiêu tiền?",
            return_messages=False
        )
        self.assertIsInstance(prompt_str, str)
        self.assertIn("DonHang", prompt_str)
        self.assertIn("2026-05-25", prompt_str)
        self.assertIn("def solution(data):", prompt_str)

    def test_build_prompt_messages_output(self):
        """Kiểm tra tạo prompt dạng tuple (system_prompt, user_prompt) cho ChatML."""
        schema = "- Bảng 'DonHang': [Mã đơn, Ngày đặt, Thành tiền]"
        sys_p, usr_p = build_prompt(
            schema_str=schema,
            as_of_date="2026-06-28",
            question="Dịp Tết 2026, mặt hàng nào bán chạy nhất ạ?",
            return_messages=True
        )
        self.assertIsInstance(sys_p, str)
        self.assertIsInstance(usr_p, str)
        self.assertIn("QUY TẮC CỐT LÕI", sys_p)
        self.assertIn("VÍ DỤ MINH HỌA PHÙ HỢP NHẤT", sys_p)
        self.assertIn("Dịp Tết 2026, mặt hàng nào bán chạy nhất ạ?", usr_p)
        self.assertIn("2026-02-10", usr_p)
        self.assertIn("2026-02-26", usr_p)

    def test_return_format_and_question_classification(self):
        """Kiểm tra nhận diện câu hỏi Top-1 chuỗi, Boolean xu hướng và định dạng trả về."""
        from datamate.llm_execution.prompt import (
            is_boolean_question,
            is_top1_string_question,
            get_return_format_instruction,
        )
        # 1. Câu hỏi Boolean xu hướng (Question 5)
        q_bool = "Từ tháng 7/2025 qua tháng 8/2025 rồi tháng 9/2025, doanh thu có tăng liên tục không?"
        self.assertTrue(is_boolean_question(q_bool))
        fmt_bool = get_return_format_instruction(q_bool)
        self.assertIn("Boolean", fmt_bool)
        self.assertIn("True hoặc False", fmt_bool)

        # 2. Câu hỏi Top-1 String nhà cung cấp (Question 4)
        q_supplier = "coi giùm tháng 5/2026 cuwar hàng nhập nhiều tiền hàng nhất từ nhaf cung cấp nào"
        self.assertTrue(is_top1_string_question(q_supplier))
        fmt_str = get_return_format_instruction(q_supplier)
        self.assertIn("chuỗi ký tự đơn lẻ", fmt_str)
        self.assertIn("scalar string", fmt_str)

        # 3. Câu hỏi đếm đơn bị hủy (Question 1)
        q_cancel = "so don bi huy trong thang 5 nam 2025 la bao nhieu z"
        self.assertEqual(classify_intent(q_cancel), "cancelled_orders")
        fmt_cancel = get_return_format_instruction(q_cancel)
        self.assertIn("scalar number", fmt_cancel)


if __name__ == "__main__":
    unittest.main()

