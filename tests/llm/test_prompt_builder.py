"""
Tệp kiểm thử: test_prompt_builder.py
Mục đích: Kiểm thử tự động các chức năng của module src/models/prompt_builder.py.

================================================================================
CÁC TIÊU CHÍ ĐÁNH GIÁ ĐẶT RA CHO MODULE PROMPT_BUILDER:
1. Phân loại ý định câu hỏi (Intent Classification):
   - Nhận diện chính xác 6 nhóm nghiệp vụ: tính tổng (aggregation), tỉ lệ % (rate_percentage),
     xếp hạng (ranking_topk), tra cứu liên kết bảng (multitable_join),
     so sánh thời gian (time_series), và câu hỏi thiếu thông tin (unanswerable_suspect).
2. Lựa chọn ví dụ mẫu động (Dynamic Few-shot Selection):
   - Chỉ chọn duy nhất 1 ví dụ phù hợp nhất với nhóm ý định của câu hỏi.
   - Không nạp thừa các ví dụ khác để tiết kiệm token đầu vào và tránh làm nhiễu mô hình.
3. Giải mã thời gian tự động (Temporal Grounding):
   - Chuyển đổi chính xác mốc Tết âm lịch (2024, 2025, 2026, 2027) thành khoảng ngày dương lịch ISO.
   - Tính toán chính xác khoảng N ngày gần nhất (kết thúc tại ngày as_of_date).
   - Xác định đúng ngày bắt đầu và kết thúc của một tháng cụ thể (tháng M/YYYY) hoặc quý (quý Q/YYYY).
   - Diễn giải đúng "tháng này" (từ ngày 01 đến as_of_date), "hôm nay", "hôm qua", "tuần này", "tuần trước".
4. Bảo đảm nguyên tắc chống rò rỉ dữ liệu tương lai:
   - Tất cả các gợi ý lọc thời gian đều tuân thủ nguyên tắc không vượt quá ngày as_of_date.
5. Định dạng đầu ra linh hoạt và chuẩn hóa:
   - Hàm build_prompt hỗ trợ trả về chuỗi văn bản gộp hoặc tuple (system_prompt, user_prompt)
     phù hợp với định dạng hội thoại ChatML của Qwen.
================================================================================
"""

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

from datamate.llm.prompt_builder import (
    classify_intent,
    select_few_shots,
    resolve_temporal_context,
    build_prompt,
    TET_SOLAR_RANGES,
    FEW_SHOT_LIBRARY,
)


class TestPromptBuilder(unittest.TestCase):
    """Bộ kiểm thử cho các chức năng trong prompt_builder.py."""

    # --------------------------------------------------------------------------
    # Tiêu chí 1: Phân loại ý định câu hỏi
    # --------------------------------------------------------------------------
    def test_classify_intent_aggregation(self):
        """Kiểm tra nhận diện câu hỏi tính tổng tiền / đếm số đơn."""
        criterion = "Chỉ tiêu 1.1: Nhận diện chính xác intent 'aggregation' (tính tổng doanh thu, đếm đơn)"
        try:
            q1 = "Tổng doanh thu tháng 5 năm 2025 là bao nhiêu?"
            q2 = "tháng này tổng giá trị các phiếu nhập hàng là bao nhiu"
            self.assertEqual(classify_intent(q1), "aggregation")
            self.assertEqual(classify_intent(q2), "purchase_import")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_classify_intent_rate_percentage(self):
        """Kiểm tra nhận diện câu hỏi tính tỉ lệ hoặc phần trăm."""
        criterion = "Chỉ tiêu 1.2: Nhận diện chính xác intent 'rate_percentage' (tính tỷ lệ, phần trăm)"
        try:
            q1 = "tháng 9/2025 cửa hangf có bao nhiêu % đơn bij huỷ"
            q2 = "tỉ lệ hủy đơn của shop trong tháng 6 là bao nhiêu"
            q3 = "doanh thu khách thân thiết chiếm bao nhiêu phần trăm tổng doanh thu"
            self.assertEqual(classify_intent(q1), "rate_percentage")
            self.assertEqual(classify_intent(q2), "rate_percentage")
            self.assertEqual(classify_intent(q3), "rate_percentage")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_classify_intent_ranking_topk(self):
        """Kiểm tra nhận diện câu hỏi xếp hạng hoặc tìm đối tượng nhiều nhất."""
        criterion = "Chỉ tiêu 1.3: Nhận diện chính xác intent 'ranking_topk' (xếp hạng, bán chạy nhất, top K)"
        try:
            q1 = "Dịp Tết 2026, mặt hàng nào bán chạy nhất ạ?"
            q2 = "Khách hàng nào mua nhiều tiền nhất trong tháng vừa rồi?"
            q3 = "Top 3 mặt hàng mang lại doanh thu cao nhất"
            self.assertEqual(classify_intent(q1), "ranking_topk")
            self.assertEqual(classify_intent(q2), "ranking_topk")
            self.assertEqual(classify_intent(q3), "ranking_topk")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_classify_intent_multitable_join(self):
        """Kiểm tra nhận diện câu hỏi tra cứu hoạt chất hoặc quy đổi đơn vị giữa nhiều bảng."""
        criterion = "Chỉ tiêu 1.4: Nhận diện chính xác intent 'multitable_join' (tra cứu hoạt chất, quy đổi đơn vị)"
        try:
            q1 = "Thuốc có hoạt chất Paracetamol tháng này bán được bao nhiêu tiền?"
            q2 = "Thuốc kê đơn nào có doanh thu cao nhất tháng 7/2025?"
            q3 = "Hàng bán theo đơn vị quy đổi lớn là bao nhiêu thùng?"
            self.assertEqual(classify_intent(q1), "multitable_join")
            self.assertEqual(classify_intent(q2), "multitable_join")
            self.assertEqual(classify_intent(q3), "multitable_join")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_classify_intent_time_series(self):
        """Kiểm tra nhận diện câu hỏi so sánh chuỗi thời gian."""
        criterion = "Chỉ tiêu 1.5: Nhận diện chính xác intent 'time_series' (so sánh chuỗi thời gian liên tục)"
        try:
            q = "Cho mình hỏi doanh thu 3 tháng 6/2026, 7/2026, 8/2026 có tăng liên tục không?"
            self.assertEqual(classify_intent(q), "time_series")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_classify_intent_unanswerable_suspect(self):
        """Kiểm tra nhận diện câu hỏi hỏi thông tin không có trong hồ sơ kinh doanh."""
        criterion = "Chỉ tiêu 1.6: Nhận diện chính xác intent 'unanswerable_suspect' (câu hỏi thiếu dữ liệu kinh doanh)"
        try:
            q = "nhân viên nào có tay nghề cao nhất tiệm"
            self.assertEqual(classify_intent(q), "unanswerable_suspect")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    # --------------------------------------------------------------------------
    # Tiêu chí 2: Lựa chọn ví dụ mẫu động (Dynamic Few-shot)
    # --------------------------------------------------------------------------
    def test_select_few_shots_selection(self):
        """Kiểm tra chọn đúng ví dụ theo intent và không bị thừa ví dụ khác."""
        criterion = "Chỉ tiêu 2.1: Chọn đúng duy nhất 1 ví dụ phù hợp nhất, không nạp thừa ví dụ khác"
        try:
            few_shot_rate = select_few_shots("rate_percentage")
            self.assertIn("TÍNH TỈ LỆ PHẦN TRĂM", few_shot_rate)
            self.assertNotIn("Dịp Tết 2026, mặt hàng nào bán chạy nhất", few_shot_rate)

            few_shot_rank = select_few_shots("ranking_topk")
            self.assertIn("TÌM ĐỐI TƯỢNG NHIỀU NHẤT", few_shot_rank)
            self.assertNotIn("TÍNH TỈ LỆ PHẦN TRĂM", few_shot_rank)

            few_shot_unans = select_few_shots("unanswerable_suspect")
            self.assertIn("CÂU HỎI THIẾU DỮ LIỆU", few_shot_unans)
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    # --------------------------------------------------------------------------
    # Tiêu chí 3: Giải mã thời gian tự động (Temporal Grounding)
    # --------------------------------------------------------------------------
    def test_resolve_temporal_context_tet_2026(self):
        """Kiểm tra giải mã mốc Tết 2026 sang ngày dương lịch chuẩn."""
        criterion = "Chỉ tiêu 3.1: Giải mã chính xác mốc Tết 2026 sang khoảng ngày dương lịch ISO (2026-02-10 đến 2026-02-26)"
        try:
            q = "Dịp Tết 2026, mặt hàng nào bán chạy nhất ạ?"
            res = resolve_temporal_context(q, as_of_date_str="2026-06-28")
            self.assertEqual(res["start_date"], "2026-02-10")
            self.assertEqual(res["end_date"], "2026-02-26")
            self.assertIn("2026-02-10", res["code_hint"])
            self.assertIn("2026-02-26", res["code_hint"])
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_resolve_temporal_context_tet_2025(self):
        """Kiểm tra giải mã mốc Tết 2025 sang ngày dương lịch chuẩn."""
        criterion = "Chỉ tiêu 3.2: Giải mã chính xác mốc Tết 2025 sang khoảng ngày dương lịch ISO (2025-01-22 đến 2025-02-07)"
        try:
            q = "Dịp Tết năm 2025 cửa hàng có bao nhiêu đơn hàng?"
            res = resolve_temporal_context(q, as_of_date_str="2025-06-01")
            self.assertEqual(res["start_date"], "2025-01-22")
            self.assertEqual(res["end_date"], "2025-02-07")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_resolve_temporal_context_n_days_recent(self):
        """Kiểm tra giải mã 7 ngày gần nhất kết thúc tại ngày as_of_date."""
        criterion = "Chỉ tiêu 3.3: Giải mã chính xác N ngày gần nhất kết thúc tại as_of_date"
        try:
            q = "7 ngày gần nhất doanh thu được bao nhiêu?"
            res = resolve_temporal_context(q, as_of_date_str="2025-09-09")
            self.assertEqual(res["start_date"], "2025-09-03")
            self.assertEqual(res["end_date"], "2025-09-09")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_resolve_temporal_context_specific_month(self):
        """Kiểm tra giải mã tháng cụ thể (ví dụ: tháng 9/2025)."""
        criterion = "Chỉ tiêu 3.4: Giải mã chính xác tháng cụ thể M/YYYY thành ngày đầu và ngày cuối tháng"
        try:
            q = "tháng 9/2025 cửa hàng có bao nhiêu đơn bị hủy"
            res = resolve_temporal_context(q, as_of_date_str="2026-05-25")
            self.assertEqual(res["start_date"], "2025-09-01")
            self.assertEqual(res["end_date"], "2025-09-30")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_resolve_temporal_context_this_month(self):
        """Kiểm tra giải mã 'tháng này' từ ngày 1 đến hết ngày as_of_date."""
        criterion = "Chỉ tiêu 3.5: Giải mã chính xác 'tháng này' từ ngày 01 đến hết as_of_date (chống rò rỉ dữ liệu)"
        try:
            q = "Tháng này doanh thu được bao nhiêu tiền?"
            res = resolve_temporal_context(q, as_of_date_str="2026-09-14")
            self.assertEqual(res["start_date"], "2026-09-01")
            self.assertEqual(res["end_date"], "2026-09-14")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_resolve_temporal_context_today(self):
        """Kiểm tra giải mã từ 'hôm nay'."""
        criterion = "Chỉ tiêu 3.6: Giải mã chính xác mốc 'hôm nay' bằng đúng ngày as_of_date"
        try:
            q = "Hôm nay có bao nhiêu khách mua hàng?"
            res = resolve_temporal_context(q, as_of_date_str="2026-05-20")
            self.assertEqual(res["start_date"], "2026-05-20")
            self.assertEqual(res["end_date"], "2026-05-20")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    # --------------------------------------------------------------------------
    # Tiêu chí 4 & 5: Cấu trúc Prompt hoàn chỉnh và phân chia ChatML
    # --------------------------------------------------------------------------
    def test_build_prompt_string_output(self):
        """Kiểm tra tạo prompt dạng chuỗi gộp truyền thống."""
        criterion = "Chỉ tiêu 4.1: Tạo chuỗi prompt gộp hoàn chỉnh chứa đủ schema, thời gian và template code"
        try:
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
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_build_prompt_messages_output(self):
        """Kiểm tra tạo prompt dạng tuple (system_prompt, user_prompt) cho ChatML."""
        criterion = "Chỉ tiêu 5.1: Phân tách ChatML (system_prompt và user_prompt) đúng chuẩn định dạng hội thoại"
        try:
            schema = "- Bảng 'DonHang': [Mã đơn, Ngày đặt, Thành tiền]"
            sys_p, usr_p = build_prompt(
                schema_str=schema,
                as_of_date="2026-06-28",
                question="Dịp Tết 2026, mặt hàng nào bán chạy nhất ạ?",
                return_messages=True
            )
            self.assertIsInstance(sys_p, str)
            self.assertIsInstance(usr_p, str)
            self.assertIn("NGUYÊN TẮC THIẾT KẾ MÃ NGUỒN", sys_p)
            self.assertIn("VÍ DỤ MINH HỌA PHÙ HỢP NHẤT", sys_p)
            self.assertIn("Dịp Tết 2026, mặt hàng nào bán chạy nhất ạ?", usr_p)
            self.assertIn("2026-02-10", usr_p)
            self.assertIn("2026-02-26", usr_p)
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise


    def test_classify_intent_inventory_unit_conversion(self):
        """Kiểm tra nhận diện câu hỏi quy đổi đơn vị và tồn kho (hộp chẵn, viên lẻ)."""
        criterion = "Chỉ tiêu 1.7: Nhận diện chính xác intent 'inventory_unit_conversion' (tồn kho, hộp chẵn, viên lẻ)"
        try:
            q1 = "Hiện tại thuốc Hapacol 650 còn tồn bao nhiêu hộp và viên lẻ?"
            q2 = "Cho biết số lượng tồn kho theo hộp và viên"
            self.assertEqual(classify_intent(q1), "inventory_unit_conversion")
            self.assertEqual(classify_intent(q2), "inventory_unit_conversion")
            few_shot = select_few_shots("inventory_unit_conversion")
            self.assertIn("TỒN KHO & QUY ĐỔI ĐƠN VỊ", few_shot)
            self.assertIn("divmod", few_shot)
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_few_shot_time_series(self):
        """Kiểm tra ví dụ mẫu cho intent time_series."""
        criterion = "Chỉ tiêu 2.2: Chọn đúng ví dụ mẫu chuỗi thời gian time_series (không bị fallback)"
        try:
            few_shot = select_few_shots("time_series")
            self.assertIn("PHÂN TÍCH CHUỖI THỜI GIAN", few_shot)
            self.assertIn("pct_change", few_shot)
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_temporal_comparison_period(self):
        """Kiểm tra giải mã kỳ chính và kỳ đối chiếu khi câu hỏi yêu cầu so sánh với tháng trước."""
        criterion = "Chỉ tiêu 3.7: Giải mã cả kỳ chính và kỳ đối chiếu (so sánh tháng trước)"
        try:
            q = "Doanh thu tháng này tăng bao nhiêu so với tháng trước?"
            res = resolve_temporal_context(q, as_of_date_str="2026-05-15")
            self.assertEqual(res["start_date"], "2026-05-01")
            self.assertEqual(res["end_date"], "2026-05-15")
            self.assertEqual(res["comparison_start"], "2026-04-01")
            self.assertEqual(res["comparison_end"], "2026-04-15")
            self.assertIn("Kỳ đối chiếu", res["description"])
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_temporal_half_month(self):
        """Kiểm tra giải mã nửa đầu / nửa cuối tháng."""
        criterion = "Chỉ tiêu 3.8: Giải mã chính xác nửa đầu tháng và nửa cuối tháng"
        try:
            q1 = "Nửa đầu tháng 5/2026 doanh thu là bao nhiêu?"
            res1 = resolve_temporal_context(q1, as_of_date_str="2026-05-25")
            self.assertEqual(res1["start_date"], "2026-05-01")
            self.assertEqual(res1["end_date"], "2026-05-15")

            q2 = "Nửa cuối tháng 5/2026 có bao nhiêu đơn hàng?"
            res2 = resolve_temporal_context(q2, as_of_date_str="2026-06-01")
            self.assertEqual(res2["start_date"], "2026-05-16")
            self.assertEqual(res2["end_date"], "2026-05-31")
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise


if __name__ == "__main__":
    print("=" * 80)
    print("BẮT ĐẦU KIỂM THỬ: tests/test_prompt_builder.py")
    print("=" * 80)
    unittest.main()
