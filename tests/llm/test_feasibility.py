"""
Tệp kiểm thử: tests/llm/test_feasibility.py
Mục đích: Kiểm thử tự động Module 3 — Deterministic Feasibility Gate (feasibility.py).

================================================================================
CÁC TIÊU CHÍ ĐÁNH GIÁ ĐẶT RA:
1. Rào chắn 1 (Thuộc tính chủ quan / phi dữ liệu POS):
   - Phát hiện các câu hỏi về tay nghề, kinh nghiệm, thái độ, nhân viên giỏi nhất,
     mức độ hài lòng, thời tiết, khoảng cách địa lý, liều lượng uống thuốc... -> Trả về unanswerable.
2. Rào chắn 2 (Khoảng thời gian câu hỏi & kỳ đối chiếu theo Điều 7 Rulebook):
   - Kỳ hỏi kết thúc trước mốc min_date của shop -> Bất khả thi (unanswerable).
   - Kỳ hỏi bắt đầu sau mốc max_date của shop -> Bất khả thi (unanswerable).
   - Kỳ hỏi nằm trong dữ liệu nhưng kỳ đối chiếu ('so với tháng liền trước') rơi ra trước min_date -> Bất khả thi.
   - Kỳ hỏi có một phần gối vào khoảng dữ liệu của shop -> Khả thi (feasible).
3. Rào chắn 3 (Thiếu bảng / cột thông tin nghiệp vụ):
   - Hỏi nhà cung cấp / giá nhập khi shop không có bảng nhập hàng hoặc không ghi giá nhập -> Bất khả thi.
   - Hỏi lãi ròng / lãi gộp khi shop thiếu sổ chi phí hoặc giá vốn -> Bất khả thi.
   - Hỏi nhóm khách thân thiết / địa chỉ / giới tính / kênh bán / hình thức thanh toán / lý do hủy trả khi thiếu cột -> Bất khả thi.
   - Hỏi tồn kho cuối ngày: bất khả thi nếu không có bảng tồn kho và không theo dõi lô; khả thi nếu có theo dõi lô (Điều 5 Rulebook).
4. Kiểm tra câu hỏi hợp lệ (Pass-through):
   - Các câu hỏi doanh thu, số đơn, top sản phẩm trong kỳ dữ liệu -> Khả thi.
5. Kiểm tra hàm trích xuất metadata và khoảng ngày (extract helpers):
   - extract_shop_metadata nhận diện đúng min_date, max_date (từ README.md và cột ngày), danh mục bảng/cột.
   - extract_query_date_range bóc tách đúng khoảng ngày từ câu hỏi tiếng Việt (kể cả không dấu/viết tắt).
================================================================================
"""

import sys
import unittest
from datetime import date
from typing import Any, Dict

# Đảm bảo hiển thị Unicode tiếng Việt trên console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from datamate.llm.feasibility import (
    check_feasibility,
    extract_shop_metadata,
    extract_query_date_range,
)


class TestFeasibilityGate(unittest.TestCase):
    """Bộ kiểm thử cho Module 3: Deterministic Feasibility Gate."""

    def setUp(self):
        """Khởi tạo metadata giả lập cho một cửa hàng chuẩn hoạt động năm 2024."""
        self.standard_shop_meta: Dict[str, Any] = {
            "min_date": "2024-01-01",
            "max_date": "2024-12-31",
            "table_names": ["don_hang", "chi_tiet_don_hang", "khach_hang", "san_pham"],
            "columns_by_table": {
                "don_hang": ["ma_don", "ngay_tao", "trang_thai", "tong_tien", "ma_khach"],
                "chi_tiet_don_hang": ["ma_don", "ma_sp", "so_luong", "thanh_tien"],
                "khach_hang": ["ma_khach", "ten_khach", "so_dien_thoai"],
                "san_pham": ["ma_sp", "ten_sp", "gia_ban", "danh_muc"],
            },
            "all_columns": {
                "ma_don", "ngay_tao", "trang_thai", "tong_tien", "ma_khach",
                "ma_sp", "so_luong", "thanh_tien", "ten_khach", "so_dien_thoai",
                "ten_sp", "gia_ban", "danh_muc"
            },
            "has_import_table": False,
            "has_import_price": False,
            "has_debt_table": False,
            "has_cost_data": False,
            "has_inventory": False,
            "has_expiry_date": False,
        }

    # --------------------------------------------------------------------------
    # Tiêu chí 1: Rào chắn thuộc tính chủ quan
    # --------------------------------------------------------------------------
    def test_subjective_queries(self):
        """Kiểm tra nhận diện câu hỏi về thuộc tính chủ quan phi dữ liệu bán hàng."""
        criterion = "Chỉ tiêu 1.1: Phát hiện câu hỏi thuộc tính chủ quan / y khoa ngoài dữ liệu POS"
        try:
            questions = [
                "Nhân viên nào có tay nghề giỏi nhất shop?",
                "Kinh nghiệm làm việc của nhân viên bán hàng ra sao?",
                "Thái độ phục vụ của nhân viên trong tháng 5 như thế nào?",
                "Mức độ hài lòng của khách hàng trong tuần qua?",
                "Thời tiết hôm nay ảnh hưởng thế nào đến doanh số?",
                "Khách hàng ưa chuộng thức uống nào nhất?",
                "Panadol Extra đỏ hộp 15 vỉ x 12 viên người lớn uống mỗi lần mấy viên vậy?",
            ]
            for q in questions:
                is_feasible, reason = check_feasibility(q, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
                self.assertFalse(is_feasible, f"Câu hỏi phải bất khả thi: {q}")
                self.assertIsNotNone(reason)

            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    # --------------------------------------------------------------------------
    # Tiêu chí 2: Rào chắn khoảng thời gian Điều 7 Rulebook
    # --------------------------------------------------------------------------
    def test_date_range_completely_before(self):
        """Kiểm tra câu hỏi có kỳ hỏi kết thúc hoàn toàn trước ngày mở shop."""
        criterion = "Chỉ tiêu 2.1: Phát hiện kỳ hỏi kết thúc trước mốc min_date của shop (Điều 7)"
        try:
            q = "Doanh thu trong tháng 5 năm 2023 là bao nhiêu?"
            is_feasible, reason = check_feasibility(q, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
            self.assertFalse(is_feasible)
            self.assertIn("Điều 7", reason)
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_date_range_completely_after(self):
        """Kiểm tra câu hỏi có kỳ hỏi bắt đầu hoàn toàn sau ngày đóng dữ liệu shop."""
        criterion = "Chỉ tiêu 2.2: Phát hiện kỳ hỏi bắt đầu sau mốc max_date của shop (Điều 7)"
        try:
            q = "Doanh thu năm 2025 của cửa hàng đạt bao nhiêu?"
            is_feasible, reason = check_feasibility(q, as_of_date="2024-12-31", shop_meta=self.standard_shop_meta)
            self.assertFalse(is_feasible)
            self.assertIn("Điều 7", reason)
            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_comparison_period_before_min_date(self):
        """Kiểm tra câu hỏi so sánh tháng mở shop với tháng liền trước (không có dữ liệu)."""
        criterion = "Chỉ tiêu 2.3: Phát hiện kỳ đối chiếu 'so với tháng liền trước' rơi ra trước min_date (Điều 7)"
        try:
            # Tháng 1/2024 có dữ liệu, nhưng 'so với tháng liền trước' cần tháng 12/2023 (< min_date 2024-01-01)
            q1 = "Tháng 1/2024 doanh thu thay đổi bao nhiêu % so với tháng liền trước?"
            is_feasible, reason = check_feasibility(q1, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
            self.assertFalse(is_feasible)
            self.assertIn("Kỳ so sánh", reason)

            # Kiểm tra biến thể viết tắt không dấu
            q2 = "coi gium so vs thang lien trc, doanh thu thang 1 nam 2024 thay doi bao nhieu % do"
            is_feasible2, _ = check_feasibility(q2, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
            self.assertFalse(is_feasible2)

            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_date_range_partial_overlap_is_feasible(self):
        """Kiểm tra câu hỏi có kỳ hỏi gối một phần vào khoảng dữ liệu shop (vẫn khả thi)."""
        criterion = "Chỉ tiêu 2.4: Kỳ hỏi nằm trong hoặc gối một phần vào khoảng dữ liệu shop được xác định khả thi (Điều 7)"
        try:
            q1 = "Doanh thu tháng 12 năm 2024 là bao nhiêu?"
            is_feasible, reason = check_feasibility(q1, as_of_date="2024-12-31", shop_meta=self.standard_shop_meta)
            self.assertTrue(is_feasible)
            self.assertIsNone(reason)

            q2 = "Tổng doanh thu năm 2024 là bao nhiêu?"
            is_feasible2, reason2 = check_feasibility(q2, as_of_date="2024-12-31", shop_meta=self.standard_shop_meta)
            self.assertTrue(is_feasible2)
            self.assertIsNone(reason2)

            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    # --------------------------------------------------------------------------
    # Tiêu chí 3: Rào chắn thiếu thông tin cấu trúc dữ liệu
    # --------------------------------------------------------------------------
    def test_missing_supplier_and_import_price(self):
        """Kiểm tra câu hỏi về nhà cung cấp và giá nhập khi shop thiếu bảng/cột."""
        criterion = "Chỉ tiêu 3.1: Phát hiện hỏi Nhà cung cấp hoặc Giá nhập khi shop không ghi nhận"
        try:
            q_ncc = "Nhà cung cấp nào nhập nhiều hàng nhất trong tháng?"
            is_feasible, reason = check_feasibility(q_ncc, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
            self.assertFalse(is_feasible)
            self.assertIn("Nhà cung cấp", reason)

            # Shop có bảng nhập hàng nhưng chỉ ghi số lượng nhập, không ghi giá nhập (has_import_price=False)
            shop_qty_only = dict(self.standard_shop_meta)
            shop_qty_only["has_import_table"] = True
            shop_qty_only["has_import_price"] = False
            q_price = "trong thang 2/2024, acemuc kids nhap vao gia binh quan mot hop la bao nhiu"
            is_f_price, _ = check_feasibility(q_price, as_of_date="2024-06-15", shop_meta=shop_qty_only)
            self.assertFalse(is_f_price)

            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_missing_profit_and_cost_data(self):
        """Kiểm tra câu hỏi về lãi ròng/chi phí và lãi gộp khi shop thiếu dữ liệu."""
        criterion = "Chỉ tiêu 3.2: Phát hiện hỏi Lãi ròng / Lãi gộp khi shop thiếu sổ chi phí hoặc giá vốn"
        try:
            q = "Lãi ròng của cửa hàng trong tháng này là bao nhiêu?"
            is_feasible, reason = check_feasibility(q, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
            self.assertFalse(is_feasible)
            self.assertIn("chi phí", reason)

            q_gross = "Tháng 6/2024 lãi gộp tính theo giá vốn mặt hàng là bao nhiêu?"
            is_f_gross, _ = check_feasibility(q_gross, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
            self.assertFalse(is_f_gross)

            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_inventory_and_batch_tracking_rule5(self):
        """Kiểm tra câu hỏi tồn kho cuối ngày: hỗ trợ tính tồn theo lô (Điều 5 Rulebook)."""
        criterion = "Chỉ tiêu 3.3: Chặn hỏi tồn kho khi không có kho/lô, và cho phép khi có theo dõi lô (Điều 5)"
        try:
            q_inv = "hết hôm nay, bia tiger 330ml còn lại mấy lon trong kho"
            # Shop chuẩn không có tồn kho và không có lô -> Bất khả thi
            is_f1, _ = check_feasibility(q_inv, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
            self.assertFalse(is_f1)

            # Shop nhà thuốc không có bảng TonKho nhưng có theo dõi lô (DonHang_Lo / mã lô) -> Khả thi theo Điều 5
            shop_batch = dict(self.standard_shop_meta)
            shop_batch["all_columns"] = set(self.standard_shop_meta["all_columns"]) | {"mã lô", "số lượng nhập", "số lượng trả"}
            is_f2, _ = check_feasibility(q_inv, as_of_date="2024-06-15", shop_meta=shop_batch)
            self.assertTrue(is_f2)

            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    def test_missing_customer_and_order_attributes(self):
        """Kiểm tra các rào chắn thuộc tính khách hàng, kênh bán, thanh toán và lý do hủy/trả."""
        criterion = "Chỉ tiêu 3.4: Phát hiện thiếu nhóm khách, địa chỉ, giới tính, kênh bán, PTTT, lý do hủy/trả"
        try:
            cases = [
                "Doanh thu từ khách hàng thân thiết trong tháng 6 là bao nhiêu?",
                "Tháng 5/2024 có mấy khách nhà ở đường Nguyễn Trãi đã mua hàng?",
                "Tháng 5/2024 khách nữ mang lại bao nhiêu doanh thu?",
                "Tháng này doanh thu các đơn bán qua điện thoại là bao nhiêu?",
                "Tháng 5/2024 doanh thu các đơn trả bằng COD là bao nhiêu?",
                "thang 5/2024 co bnhiu don bi huy vi giao tre",
            ]
            for q in cases:
                is_f, _ = check_feasibility(q, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
                self.assertFalse(is_f, f"Phải chặn câu hỏi thiếu cột: {q}")

            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    # --------------------------------------------------------------------------
    # Tiêu chí 4: Câu hỏi hợp lệ thông thường (Pass-through)
    # --------------------------------------------------------------------------
    def test_valid_queries_passthrough(self):
        """Kiểm tra các câu hỏi kinh doanh hợp lệ nằm trong phạm vi dữ liệu."""
        criterion = "Chỉ tiêu 4.1: Câu hỏi hợp lệ trong phạm vi dữ liệu được chuyển tiếp cho LLM"
        try:
            valid_questions = [
                "Tổng doanh thu tháng 6 năm 2024 là bao nhiêu?",
                "Top 5 mặt hàng bán chạy nhất trong tháng này?",
                "Đơn hàng nào có giá trị cao nhất ngày 2024-06-15?",
                "Số lượng trà sữa trân châu bán được trong tuần qua?",
            ]
            for q in valid_questions:
                is_feasible, reason = check_feasibility(q, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
                self.assertTrue(is_feasible, f"Câu hỏi hợp lệ bị chặn sai: {q}")
                self.assertIsNone(reason)

            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise

    # --------------------------------------------------------------------------
    # Tiêu chí 5: Bóc tách khoảng ngày câu hỏi & trích xuất README metadata
    # --------------------------------------------------------------------------
    def test_extract_query_date_range_and_readme_metadata(self):
        """Kiểm tra trích xuất khoảng ngày và phân tích README.md của shop."""
        criterion = "Chỉ tiêu 5.1: Trích xuất chính xác khoảng ngày câu hỏi và metadata từ README.md"
        try:
            s, e = extract_query_date_range("Doanh thu tháng 5/2024 là bao nhiêu", "2024-06-01")
            self.assertEqual((s, e), ("2024-05-01", "2024-05-31"))

            s, e = extract_query_date_range("tổng doanh thu năm 2024", "2024-12-31")
            self.assertEqual((s, e), ("2024-01-01", "2024-12-31"))

            s, e = extract_query_date_range("tháng này bán được bao nhiêu đơn", "2024-06-20")
            self.assertEqual((s, e), ("2024-06-01", "2024-06-20"))

            s, e = extract_query_date_range("doanh thu 7 ngày gần nhất", "2024-06-10")
            self.assertEqual((s, e), ("2024-06-04", "2024-06-10"))

            sample_readme = (
                "## Cột trong `DonHang.xlsx`\n"
                "- **Mã đơn hàng**: mã đơn\n"
                "- **Hình thức thanh toán**: phương thức trả tiền\n"
                "## Quy ước\n"
                "- Dữ liệu có đến hết 14/09/2026.\n"
                "- **Tồn kho**: **Tồn cuối kỳ** là tồn cuối ngày.\n"
            )
            meta = extract_shop_metadata(readme_text=sample_readme)
            self.assertEqual(meta["max_date"], "2026-09-14")
            self.assertTrue(meta["has_inventory"])
            self.assertTrue(meta["has_payment_method"])

            print(f"  • {criterion} -> [ĐẠT]")
        except Exception as exc:
            print(f"  • {criterion} -> [KHÔNG ĐẠT: {exc}]")
            raise


if __name__ == "__main__":
    print("=" * 80)
    print("BẮT ĐẦU KIỂM THỬ TỰ ĐỘNG MODULE 3: FEASIBILITY GATE (feasibility.py)")
    print("=" * 80)
    unittest.main(verbosity=0)
