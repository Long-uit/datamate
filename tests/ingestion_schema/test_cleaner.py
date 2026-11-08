"""
test_cleaner.py — Kiểm thử toàn diện cho Rule 8 Data Cleaner (ingestion_schema).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent.parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import pandas as pd

from datamate.ingestion_schema.cleaner import (
    StatusClassification,
    apply_group_forward_fill,
    classify_status_value,
    clean_business,
    clean_dataframe,
    deduplicate_order_rows,
    detect_line_return_columns,
    detect_status_columns,
    filter_business_order_status,
    filter_order_status,
    find_order_id_col,
    find_order_level_cols,
    get_business_excluded_order_ids,
    get_excluded_order_ids,
    get_order_status_sets,
)
from datamate.ingestion_schema.loader import BusinessData, TableInfo


class TestRule8Cleaner(unittest.TestCase):
    def test_find_order_id_col(self):
        self.assertEqual(find_order_id_col(["Mã đơn hàng", "Tên khách"]), "Mã đơn hàng")
        self.assertEqual(find_order_id_col(["Số phiếu", "Ngày"]), "Số phiếu")
        self.assertEqual(find_order_id_col(["order_id", "amount"]), "order_id")
        self.assertIsNone(find_order_id_col(["Tên sản phẩm", "Đơn giá"]))

    def test_find_order_level_cols(self):
        cols = ["Mã đơn", "Ngày tạo", "Tên khách", "Trạng thái", "Sản phẩm", "Số lượng", "Đơn giá"]
        order_cols = find_order_level_cols(cols, "Mã đơn")
        self.assertIn("Mã đơn", order_cols)
        self.assertIn("Ngày tạo", order_cols)
        self.assertIn("Tên khách", order_cols)
        self.assertIn("Trạng thái", order_cols)
        self.assertNotIn("Sản phẩm", order_cols)
        self.assertNotIn("Số lượng", order_cols)

    def test_group_forward_fill_order_level(self):
        raw_data = {
            "Mã đơn": ["DH01", None, "DH02"],
            "Ngày": ["2024-01-05", "", "2024-01-06"],
            "Khách hàng": ["Chị Lan", None, "Anh Tuấn"],
            "Trạng thái": ["Hoàn thành", None, "Đang giao"],
            "Sản phẩm": ["SP A", "SP B", "SP C"],
            "Số lượng": [2, 1, 3],
        }
        df = pd.DataFrame(raw_data)
        df_clean = apply_group_forward_fill(df, "Mã đơn")

        self.assertEqual(list(df_clean["Mã đơn"]), ["DH01", "DH01", "DH02"])
        self.assertEqual(list(df_clean["Ngày"]), ["2024-01-05", "2024-01-05", "2024-01-06"])
        self.assertEqual(list(df_clean["Khách hàng"]), ["Chị Lan", "Chị Lan", "Anh Tuấn"])
        self.assertEqual(list(df_clean["Trạng thái"]), ["Hoàn thành", "Hoàn thành", "Đang giao"])
        self.assertEqual(list(df_clean["Sản phẩm"]), ["SP A", "SP B", "SP C"])

    def test_deduplicate_same_order_vs_different_order(self):
        raw_data = {
            "Mã đơn": ["DH01", "DH01", "DH02"],
            "Sản phẩm": ["Sting dâu", "Sting dâu", "Sting dâu"],
            "Số lượng": [2, 2, 2],
            "Đơn giá": [10000, 10000, 10000],
        }
        df = pd.DataFrame(raw_data)
        df_dedup = deduplicate_order_rows(df, "Mã đơn")

        self.assertEqual(len(df_dedup), 2)
        self.assertEqual(list(df_dedup["Mã đơn"]), ["DH01", "DH02"])

    def test_table_without_order_id_keeps_all_rows(self):
        raw_data = {
            "Tên chi phí": ["Tiền điện", "Tiền điện"],
            "Số tiền": [500000, 500000],
        }
        df = pd.DataFrame(raw_data)
        df_clean = clean_dataframe(df)

        self.assertEqual(len(df_clean), 2)

    def test_deduplicate_with_stt_column(self):
        raw_data = {
            "STT": [1, 2, 3],
            "Mã đơn": ["DH01", "DH01", "DH02"],
            "Sản phẩm": ["Sting dâu", "Sting dâu", "Sting dâu"],
            "Số lượng": [2, 2, 2],
        }
        df = pd.DataFrame(raw_data)
        df_dedup = deduplicate_order_rows(df, "Mã đơn")

        self.assertEqual(len(df_dedup), 2)
        self.assertEqual(list(df_dedup["STT"]), [1, 3])

    def test_no_forward_fill_on_numeric_and_discount_columns(self):
        raw_data = {
            "Mã đơn": ["DH01", None],
            "Khách hàng": ["Anh Nam", None],
            "Sản phẩm": ["Áo sơ mi", "Quần âu"],
            "Giảm giá": [20000, None],
            "Tổng tiền": [500000, None],
        }
        df = pd.DataFrame(raw_data)
        df_clean = apply_group_forward_fill(df, "Mã đơn")

        self.assertEqual(list(df_clean["Khách hàng"]), ["Anh Nam", "Anh Nam"])
        self.assertEqual(df_clean["Giảm giá"].iloc[0], 20000)
        self.assertTrue(pd.isna(df_clean["Giảm giá"].iloc[1]))
        self.assertEqual(df_clean["Tổng tiền"].iloc[0], 500000)
        self.assertTrue(pd.isna(df_clean["Tổng tiền"].iloc[1]))

    def test_clean_dataframe_pipeline(self):
        raw_data = {
            "Mã đơn hàng": ["ORD100", None, "ORD100"],
            "Ngày": ["2024-05-10", None, "2024-05-10"],
            "Sản phẩm": ["Cà phê đen", "Cà phê đen", "Cà phê đen"],
            "Số lượng": [1, 1, 1],
        }
        df = pd.DataFrame(raw_data)
        df_clean = clean_dataframe(df)

        self.assertEqual(len(df_clean), 1)
        self.assertEqual(df_clean.iloc[0]["Mã đơn hàng"], "ORD100")

    def test_order_level_never_includes_amounts_or_quantities(self):
        financial_cols = [
            "Mã đơn", "Ngày đặt", "Trạng thái",
            "Đơn giá", "Thành tiền", "Số lượng", "Chiết khấu",
            "Giảm giá", "VAT", "Tổng cộng", "Tiền ship",
            "Amount", "Quantity", "Discount", "Line Total"
        ]
        order_cols = find_order_level_cols(financial_cols, "Mã đơn")
        # Ensure only qualitative order-level attributes are included
        self.assertIn("Mã đơn", order_cols)
        self.assertIn("Ngày đặt", order_cols)
        self.assertIn("Trạng thái", order_cols)
        # Ensure numerical / amount / discount columns are strictly excluded
        for col in ["Đơn giá", "Thành tiền", "Số lượng", "Chiết khấu", "Giảm giá",
                    "VAT", "Tổng cộng", "Tiền ship", "Amount", "Quantity", "Discount", "Line Total"]:
            self.assertNotIn(col, order_cols, f"{col} should never be marked as an order-level forward fill column")

    def test_two_identical_rows_across_different_orders_preserved(self):
        raw_data = {
            "STT": [1, 2, 3],
            "Mã đơn": ["DH101", "DH101", "DH102"],
            "Tên sản phẩm": ["Trà sữa trân châu", "Trà sữa trân châu", "Trà sữa trân châu"],
            "Số lượng": [1, 1, 1],
            "Đơn giá": [35000, 35000, 35000],
        }
        df = pd.DataFrame(raw_data)
        # DH101 has two identical lines (duplicate export error) -> should be deduplicated to 1 row
        # DH102 has an identical line to DH101 -> MUST be preserved
        df_dedup = deduplicate_order_rows(df, "Mã đơn")
        self.assertEqual(len(df_dedup), 2)
        self.assertEqual(list(df_dedup["Mã đơn"]), ["DH101", "DH102"])
        self.assertEqual(list(df_dedup["STT"]), [1, 3])

    def test_order_forward_fill_boundary_isolation(self):
        raw_data = {
            "Mã đơn": ["DH01", None, "DH02", None],
            "Khách hàng": ["Khách A", None, None, None],
            "Ghi chú": ["Giao hỏa tốc", None, None, None],
            "Sản phẩm": ["SP1", "SP2", "SP3", "SP4"],
        }
        df = pd.DataFrame(raw_data)
        df_clean = apply_group_forward_fill(df, "Mã đơn")

        # DH01 items get Khách A and Giao hỏa tốc
        self.assertEqual(df_clean.loc[0, "Khách hàng"], "Khách A")
        self.assertEqual(df_clean.loc[1, "Khách hàng"], "Khách A")
        self.assertEqual(df_clean.loc[0, "Ghi chú"], "Giao hỏa tốc")
        self.assertEqual(df_clean.loc[1, "Ghi chú"], "Giao hỏa tốc")

        # DH02 items had None for Khách hàng and Ghi chú -> must NOT inherit from DH01
        self.assertTrue(pd.isna(df_clean.loc[2, "Khách hàng"]))
        self.assertTrue(pd.isna(df_clean.loc[3, "Khách hàng"]))
        self.assertTrue(pd.isna(df_clean.loc[2, "Ghi chú"]))
        self.assertTrue(pd.isna(df_clean.loc[3, "Ghi chú"]))


class TestStatusClassification(unittest.TestCase):
    """Kiểm thử bộ phân loại giá trị trạng thái theo phân cấp ngữ nghĩa."""

    def test_classify_cancel_values(self):
        cancel_samples = [
            "hủy", "huỷ", "đã hủy", "đã huỷ", "hủy đơn", "huỷ đơn",
            "đã hủy đơn", "khách hủy", "cancelled", "cancel", "không giao được"
        ]
        for val in cancel_samples:
            cat, reason = classify_status_value(val)
            self.assertEqual(cat, "loại (huỷ)", f"Failed for '{val}': {reason}")
            self.assertEqual(classify_status_value(val), "loại (huỷ)")

    def test_classify_return_values(self):
        return_samples = [
            "hoàn hàng", "hoàn trả", "hàng hoàn", "hoàn tiền", "trả hàng",
            "đã trả hàng", "hàng trả về", "trả lại", "returned", "đổi trả", "đã hoàn hàng"
        ]
        for val in return_samples:
            cat, reason = classify_status_value(val)
            self.assertEqual(cat, "loại (trả)", f"Failed for '{val}': {reason}")
            self.assertEqual(classify_status_value(val), "loại (trả)")

    def test_classify_success_and_pending_values(self):
        keep_samples = [
            "hoàn thành", "hoàn tất", "completed", "đã giao", "thành công",
            "xong", "đã xong", "đã lấy", "ok", "received", "đang giao",
            "đang vận chuyển", "đang xử lý", "đang gửi", "shipping", "chờ giao",
            "đang giao dịch", "đang giao hàng"
        ]
        for val in keep_samples:
            cat, reason = classify_status_value(val)
            self.assertEqual(cat, "giữ", f"Failed for '{val}': {reason}")
            self.assertEqual(classify_status_value(val), "giữ")

    def test_classify_null_empty_blank_returns_giu(self):
        null_samples = [None, "", "   ", float("nan"), "nan", "null", "none"]
        for val in null_samples:
            cat, reason = classify_status_value(val)
            self.assertEqual(cat, "giữ", f"Failed for null sample '{val}': {reason}")
            self.assertEqual(classify_status_value(val), "giữ")

    def test_classify_novel_unseen_values_returns_unknown_and_logs(self):
        novel_samples = [
            "Đã bàn giao bưu tá",
            "Người nhận từ chối nhận hàng",
            "Xác nhận thất lạc hàng",
            "Khác lạ chưa từng thấy"
        ]
        with self.assertLogs("datamate.ingestion_schema.cleaner", level="WARNING") as cm:
            for val in novel_samples:
                cat, reason = classify_status_value(val)
                self.assertEqual(cat, "unknown")
                self.assertIn("UNSEEN STATUS VALUE", reason)
        self.assertTrue(any("UNSEEN STATUS VALUE" in log_msg for log_msg in cm.output))

    def test_priority_hierarchy_and_no_bare_hoan_trap(self):
        # 'Đã hoàn thành' must NOT be classified as return
        self.assertEqual(classify_status_value("Đã hoàn thành"), "giữ")
        self.assertEqual(classify_status_value("hoàn tất"), "giữ")
        # 'Đã hoàn hàng' must NOT be classified as success
        self.assertEqual(classify_status_value("Đã hoàn hàng"), "loại (trả)")
        self.assertEqual(classify_status_value("hoàn trả tiền"), "loại (trả)")

    def test_status_classification_type_compatibility(self):
        res = classify_status_value("Hoàn thành")
        self.assertIsInstance(res, StatusClassification)
        self.assertIsInstance(res, tuple)
        self.assertEqual(len(res), 2)
        # Tuple unpacking
        cat, reason = res
        self.assertEqual(cat, "giữ")
        # Direct string equality
        self.assertEqual(res, "giữ")
        self.assertEqual(res.category, "giữ")
        self.assertIn("success", res.reason)


class TestStatusColumnDetection(unittest.TestCase):
    """Kiểm thử nhận diện cột trạng thái dựa trên nội dung (Content-Based Column Detection)."""

    def test_detect_status_columns_standard(self):
        df = pd.DataFrame({
            "Mã đơn": ["DH01", "DH02", "DH03"],
            "Trạng thái": ["Hoàn thành", "Đã hủy", "Đang giao"],
            "Số tiền": [100000, 200000, 150000],
        })
        cols = detect_status_columns(df)
        self.assertEqual(cols, ["Trạng thái"])

    def test_detect_status_columns_content_based_renamed(self):
        # Even with arbitrary renamed columns like TinhTrang or CustomState
        df = pd.DataFrame({
            "order_id": ["O1", "O2", "O3", "O4"],
            "TinhTrang": ["Xong", "Đã hủy", "Đổi trả", "Đang giao"],
            "CustomState": ["completed", "cancelled", "returned", "shipping"],
        })
        cols = detect_status_columns(df)
        self.assertIn("TinhTrang", cols)
        self.assertIn("CustomState", cols)

    def test_detect_status_columns_excludes_non_status_columns(self):
        # Non-status columns must be strictly excluded
        df = pd.DataFrame({
            "Mã đơn": ["DH1", "DH2", "DH3"],
            "Tên sản phẩm": ["Áo thun", "Quần jean", "Áo khoác"],
            "Phương thức thanh toán": ["Tiền mặt", "Chuyển khoản", "COD"],
            "Tên khách hàng": ["Nguyễn Văn A", "Trần Thị B", "Lê Văn C"],
            "Tên nhân viên": ["Thu ngân 1", "Thu ngân 2", "Thu ngân 1"],
            "Ghi chú": ["Giao giờ hành chính", "Gọi trước khi giao", "Hàng dễ vỡ"],
            "Trạng thái": ["Hoàn thành", "Đang giao", "Đã hủy"],
        })
        cols = detect_status_columns(df)
        self.assertEqual(cols, ["Trạng thái"])

    def test_detect_status_columns_cardinality_and_coverage(self):
        # Column with high cardinality (> 25 unique non-null values) is not a status column
        high_card_vals = [f"Status_{i}" for i in range(30)]
        df = pd.DataFrame({
            "ID": list(range(30)),
            "HighCard": high_card_vals,
        })
        self.assertEqual(detect_status_columns(df), [])


class TestLineReturnDetection(unittest.TestCase):
    """Kiểm thử nhận diện cột trả hàng cấp dòng (Line Return Columns)."""

    def test_detect_line_return_columns_variations(self):
        df = pd.DataFrame({
            "Mã đơn": ["DH01", "DH02"],
            "Số lượng trả (ĐVT cơ bản)": [1, 0],
            "SL trả": [0, 2],
            "SLTraQuyDoi": [0.5, 0.0],
            "Tiền hoàn": [50000, 0],
            "Số lượng": [2, 3],  # Standard quantity, not return
            "Thành tiền": [100000, 150000],
        })
        detected = detect_line_return_columns(df)
        self.assertIn("Số lượng trả (ĐVT cơ bản)", detected)
        self.assertIn("SL trả", detected)
        self.assertIn("SLTraQuyDoi", detected)
        self.assertIn("Tiền hoàn", detected)
        self.assertNotIn("Số lượng", detected)
        self.assertNotIn("Thành tiền", detected)

    def test_detect_line_return_columns_ignore_zeros(self):
        # If all values are 0 (no returns ever occurred), don't flag as active return column
        df = pd.DataFrame({
            "Mã đơn": ["DH01", "DH02"],
            "Số lượng trả": [0, 0],
        })
        self.assertEqual(detect_line_return_columns(df), [])

    def test_detect_line_return_columns_ignore_non_numeric(self):
        df = pd.DataFrame({
            "Mã đơn": ["DH01", "DH02"],
            "Số lượng trả": ["chưa rõ", "không"],
        })
        self.assertEqual(detect_line_return_columns(df), [])


class TestRule1WholeOrderExclusion(unittest.TestCase):
    """Kiểm thử loại bỏ nguyên đơn theo Rule 1 và triệt tiêu tính trùng lặp (Set Union)."""

    def test_whole_order_exclusion_status_cancelled(self):
        raw_data = {
            "Mã đơn": ["DH01", "DH01", "DH02", "DH02"],
            "Sản phẩm": ["SP A", "SP B", "SP C", "SP D"],
            "Trạng thái": ["Hoàn thành", "Hoàn thành", "Đã hủy", "Đã hủy"],
            "Thành tiền": [100000, 150000, 200000, 50000],
        }
        df = pd.DataFrame(raw_data)
        excluded_ids = get_excluded_order_ids(df, "Mã đơn")
        self.assertEqual(excluded_ids, {"DH02"})

        filtered_df = filter_order_status(df, "Mã đơn")
        self.assertEqual(len(filtered_df), 2)
        self.assertEqual(list(filtered_df["Mã đơn"].unique()), ["DH01"])

    def test_whole_order_exclusion_status_returned(self):
        raw_data = {
            "Mã đơn": ["DH10", "DH11"],
            "Trạng thái": ["Đã trả hàng", "Đang giao"],
            "Tiền": [300000, 400000],
        }
        df = pd.DataFrame(raw_data)
        excluded_ids = get_excluded_order_ids(df, "Mã đơn")
        self.assertEqual(excluded_ids, {"DH10"})

        filtered_df = filter_order_status(df, "Mã đơn")
        self.assertEqual(list(filtered_df["Mã đơn"]), ["DH11"])

    def test_whole_order_exclusion_line_return(self):
        # DH01 has 3 line items. Only item 2 has return_qty = 1.
        # Rule 1: Exclude the entire order (all 3 lines of DH01).
        raw_data = {
            "Mã đơn": ["DH01", "DH01", "DH01", "DH02", "DH02"],
            "Dòng": [1, 2, 3, 1, 2],
            "Sản phẩm": ["Mì tôm", "Xúc xích", "Nước ngọt", "Bánh mì", "Sữa tươi"],
            "Số lượng": [5, 2, 3, 1, 2],
            "Số lượng trả": [0, 1, 0, 0, 0],
            "Thành tiền": [50000, 30000, 30000, 20000, 25000],
        }
        df = pd.DataFrame(raw_data)
        status_sets = get_order_status_sets(df, "Mã đơn")
        self.assertIn("DH01", status_sets["line_returned"])
        self.assertNotIn("DH02", status_sets["line_returned"])

        filtered_df = filter_order_status(df, "Mã đơn")
        # All 3 rows of DH01 must be completely removed!
        self.assertEqual(len(filtered_df), 2)
        self.assertEqual(list(filtered_df["Mã đơn"].unique()), ["DH02"])

    def test_zero_double_counting_union(self):
        # Order DH99 has BOTH status return and line return
        raw_data = {
            "Mã đơn": ["DH99", "DH99", "DH100"],
            "Trạng thái": ["Đã trả hàng", "Đã trả hàng", "Hoàn thành"],
            "Số lượng trả": [1, 0, 0],
            "Thành tiền": [100000, 50000, 200000],
        }
        df = pd.DataFrame(raw_data)
        status_sets = get_order_status_sets(df, "Mã đơn")
        self.assertIn("DH99", status_sets["status_returned"])
        self.assertIn("DH99", status_sets["line_returned"])
        # Union has DH99 only once
        self.assertEqual(status_sets["excluded"], {"DH99"})

        filtered_df = filter_order_status(df, "Mã đơn")
        self.assertEqual(len(filtered_df), 1)
        self.assertEqual(list(filtered_df["Mã đơn"]), ["DH100"])

    def test_clean_dataframe_pipeline_with_filter_status(self):
        raw_data = {
            "Mã đơn": ["DH01", None, "DH02", None],
            "Trạng thái": ["Hoàn thành", None, "Đã hủy", None],
            "Sản phẩm": ["SP1", "SP2", "SP3", "SP4"],
            "Thành tiền": [10000, 20000, 30000, 40000],
        }
        df = pd.DataFrame(raw_data)
        # Default filter_status=False preserves all rows (Rule 8 only)
        df_rule8 = clean_dataframe(df, filter_status=False)
        self.assertEqual(len(df_rule8), 4)

        # filter_status=True applies Rule 8 + Rule 1
        df_rule1 = clean_dataframe(df, filter_status=True)
        self.assertEqual(len(df_rule1), 2)
        self.assertEqual(list(df_rule1["Mã đơn"]), ["DH01", "DH01"])

    def test_business_level_order_exclusion(self):
        # Table 1: Invoice header with status
        df_header = pd.DataFrame({
            "Mã đơn": ["DH01", "DH02", "DH03"],
            "Trạng thái": ["Hoàn thành", "Không giao được", "Đang giao"],
        })
        # Table 2: Invoice items with line return
        df_items = pd.DataFrame({
            "Mã đơn": ["DH01", "DH03", "DH03"],
            "Sản phẩm": ["A", "B", "C"],
            "Số lượng trả": [0, 2, 0],  # DH03 has line return!
        })
        t1 = TableInfo("header", "f1.xlsx", "f1.xlsx", "S1", df_header, True, 3, list(df_header.columns), [])
        t2 = TableInfo("items", "f2.xlsx", "f2.xlsx", "S1", df_items, True, 3, list(df_items.columns), [])
        biz = BusinessData("biz_test", [t1, t2], "", [])

        excluded_ids = get_business_excluded_order_ids(biz)
        # DH02 excluded via status (Không giao được), DH03 excluded via line return!
        self.assertEqual(excluded_ids, {"DH02", "DH03"})

        filtered_biz = filter_business_order_status(biz)
        self.assertEqual(len(filtered_biz.tables[0].df), 1)
        self.assertEqual(list(filtered_biz.tables[0].df["Mã đơn"]), ["DH01"])
        self.assertEqual(len(filtered_biz.tables[1].df), 1)
        self.assertEqual(list(filtered_biz.tables[1].df["Mã đơn"]), ["DH01"])


class TestZeroShopBranching(unittest.TestCase):
    """Kiểm chứng không có nhánh rẽ nào theo business_id hoặc tên shop trong cleaner.py."""

    def test_no_shop_or_business_id_branching_in_cleaner(self):
        cleaner_file = Path(_SRC_DIR) / "datamate" / "ingestion_schema" / "cleaner.py"
        content = cleaner_file.read_text(encoding="utf-8")

        # Must not contain any conditions like `if business_id ==` or `if 'biz_' in`
        self.assertNotIn("if business_id ==", content)
        self.assertNotIn("if business_id in", content)
        self.assertNotIn("if shop_name ==", content)
        self.assertNotIn("if 'biz_' in", content)
        self.assertNotIn('if "biz_" in', content)


if __name__ == "__main__":
    unittest.main()


