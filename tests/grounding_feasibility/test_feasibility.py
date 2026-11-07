"""
tests/grounding_feasibility/test_feasibility.py — Kiểm thử tự động Module Feasibility Gate (grounding_feasibility/feasibility.py).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict

_SRC_DIR = str(Path(__file__).resolve().parent.parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from datamate.grounding_feasibility.feasibility import (
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

    def test_subjective_queries(self):
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

    def test_date_range_completely_before(self):
        q = "Doanh thu trong tháng 5 năm 2023 là bao nhiêu?"
        is_feasible, reason = check_feasibility(q, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
        self.assertFalse(is_feasible)
        self.assertIn("Điều 7", reason)

    def test_date_range_completely_after(self):
        q = "Doanh thu năm 2025 của cửa hàng đạt bao nhiêu?"
        is_feasible, reason = check_feasibility(q, as_of_date="2024-12-31", shop_meta=self.standard_shop_meta)
        self.assertFalse(is_feasible)
        self.assertIn("Điều 7", reason)

    def test_comparison_period_before_min_date(self):
        q1 = "Tháng 1/2024 doanh thu thay đổi bao nhiêu % so với tháng liền trước?"
        is_feasible, reason = check_feasibility(q1, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
        self.assertFalse(is_feasible)
        self.assertIn("Kỳ so sánh", reason)

        q2 = "coi gium so vs thang lien trc, doanh thu thang 1 nam 2024 thay doi bao nhieu % do"
        is_feasible2, _ = check_feasibility(q2, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
        self.assertFalse(is_feasible2)

    def test_date_range_partial_overlap_is_feasible(self):
        q1 = "Doanh thu tháng 12 năm 2024 là bao nhiêu?"
        is_feasible, reason = check_feasibility(q1, as_of_date="2024-12-31", shop_meta=self.standard_shop_meta)
        self.assertTrue(is_feasible)
        self.assertIsNone(reason)

        q2 = "Tổng doanh thu năm 2024 là bao nhiêu?"
        is_feasible2, reason2 = check_feasibility(q2, as_of_date="2024-12-31", shop_meta=self.standard_shop_meta)
        self.assertTrue(is_feasible2)
        self.assertIsNone(reason2)

    def test_missing_supplier_and_import_price(self):
        q_ncc = "Nhà cung cấp nào nhập nhiều hàng nhất trong tháng?"
        is_feasible, reason = check_feasibility(q_ncc, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
        self.assertFalse(is_feasible)
        self.assertIn("Nhà cung cấp", reason)

        shop_qty_only = dict(self.standard_shop_meta)
        shop_qty_only["has_import_table"] = True
        shop_qty_only["has_import_price"] = False
        q_price = "trong thang 2/2024, acemuc kids nhap vao gia binh quan mot hop la bao nhiu"
        is_f_price, _ = check_feasibility(q_price, as_of_date="2024-06-15", shop_meta=shop_qty_only)
        self.assertFalse(is_f_price)

    def test_missing_profit_and_cost_data(self):
        q = "Lãi ròng của cửa hàng trong tháng này là bao nhiêu?"
        is_feasible, reason = check_feasibility(q, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
        self.assertFalse(is_feasible)
        self.assertIn("chi phí", reason)

        q_gross = "Tháng 6/2024 lãi gộp tính theo giá vốn mặt hàng là bao nhiêu?"
        is_f_gross, _ = check_feasibility(q_gross, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
        self.assertFalse(is_f_gross)

    def test_inventory_and_batch_tracking_rule5(self):
        q_inv = "hết hôm nay, bia tiger 330ml còn lại mấy lon trong kho"
        is_f1, _ = check_feasibility(q_inv, as_of_date="2024-06-15", shop_meta=self.standard_shop_meta)
        self.assertFalse(is_f1)

        shop_batch = dict(self.standard_shop_meta)
        shop_batch["all_columns"] = set(self.standard_shop_meta["all_columns"]) | {"mã lô", "số lượng nhập", "số lượng trả"}
        is_f2, _ = check_feasibility(q_inv, as_of_date="2024-06-15", shop_meta=shop_batch)
        self.assertTrue(is_f2)

    def test_missing_customer_and_order_attributes(self):
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

    def test_valid_queries_passthrough(self):
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

    def test_extract_query_date_range_and_readme_metadata(self):
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


if __name__ == "__main__":
    unittest.main()

