"""
Unit tests cho Bước 3 — Unified relational view và chọn bảng/cột.
Kiểm chứng trên dữ liệu thật (biz_106, biz_107, biz_109, biz_114, biz_125, biz_127, biz_129):
(a) Ngày và tiền nằm ở hai bảng khác nhau (don_hang tách khỏi chi_tiet_don);
(b) Tên cột dạng không dấu/snake_case (ngay_ban, trang_thai) hoặc tiếng Anh/viết tắt (Amount, Tổng);
(c) Bảng tồn kho (BaoCaoTonKho) không bị loại nhầm và có đủ thông tin Ngày snapshot + Quy cách quy đổi;
(d) Lỗi DataNotFoundError (lỗi schema) không kích hoạt vòng tự sửa lỗi bằng LLM.
"""

from pathlib import Path
import pytest

from datamate.ingestion_schema.loader import load_business
from datamate.ingestion_schema.cleaner import clean_business
from datamate.llm_execution.sandbox import clean_num
from datamate.llm_execution.prompt import prune_schema_by_intent
from datamate.ingestion_schema.schema_profiler import profile_business_schema

TRAIN_DATA_ROOT = Path("competition_data/train/data")


def test_hypothesis_b_column_normalization_and_aliases():
    """(b) Chuẩn hoá tên cột (bỏ dấu, lowercase, thay _ và - bằng khoảng trắng) và gắn alias chuẩn."""
    from datamate.ingestion_schema.cleaner import normalize_col_for_match
    assert normalize_col_for_match("ngay_ban") == "ngay ban"
    assert normalize_col_for_match("Ngày-bán") == "ngay ban"
    assert normalize_col_for_match("trang_thai") == "trang thai"
    assert normalize_col_for_match("T.Tiền (đ)") == "t tien d"

    # Kiểm tra trên dữ liệu thật biz_107, biz_114, biz_125
    for biz_id in ("biz_107", "biz_114", "biz_125"):
        bd = clean_business(load_business(TRAIN_DATA_ROOT / biz_id))
        sales_tbl = bd.tables[0].df
        cols_low = [str(c).lower() for c in sales_tbl.columns]
        has_date = any(any(k in c for k in ["ngày", "date", "thời gian"]) for c in cols_low)
        has_amt = any(any(k in c for k in ["thành tiền", "tổng tiền", "tiền bán", "doanh thu"]) for c in cols_low)
        has_status = any(any(k in c for k in ["trạng thái", "status"]) for c in cols_low)
        assert has_date, f"{biz_id} thiếu cột ngày chuẩn hoá trong {sales_tbl.columns.tolist()}"
        assert has_amt, f"{biz_id} thiếu cột thành tiền chuẩn hoá trong {sales_tbl.columns.tolist()}"
        assert has_status, f"{biz_id} thiếu cột trạng thái chuẩn hoá trong {sales_tbl.columns.tolist()}"


def test_hypothesis_a_separated_header_and_detail_join():
    """(a) Join bảng đơn hàng (don_hang) với bảng chi tiết (chi_tiet_don) và sản phẩm (san_pham) theo khoá."""
    for biz_id in ("biz_127", "biz_129"):
        bd = clean_business(load_business(TRAIN_DATA_ROOT / biz_id))
        tables_by_name = {Path(t.fixed_file_name).stem: t.df for t in bd.tables}
        ct_df = tables_by_name["chi_tiet_don"]
        dh_df = tables_by_name["don_hang"]

        # Bảng chi_tiet_don phải có cả cột ngày, cột thành tiền, cột trạng thái và tên hàng
        ct_cols_low = [str(c).lower() for c in ct_df.columns]
        assert any("ngày" in c for c in ct_cols_low), f"{biz_id} chi_tiet_don thiếu cột Ngày sau khi join"
        assert any("thành tiền" in c for c in ct_cols_low), f"{biz_id} chi_tiet_don thiếu cột Thành tiền"
        assert any("trạng thái" in c for c in ct_cols_low), f"{biz_id} chi_tiet_don thiếu cột Trạng thái"
        assert any("tên hàng" in c or "tên sp" in c or "tên sản phẩm" in c for c in ct_cols_low), (
            f"{biz_id} chi_tiet_don thiếu cột Tên hàng sau khi join san_pham"
        )

        # Bảng don_hang phải có cột Thành tiền (tổng thành tiền dòng hàng theo Rulebook §1)
        dh_cols_low = [str(c).lower() for c in dh_df.columns]
        assert any("thành tiền" in c for c in dh_cols_low), f"{biz_id} don_hang thiếu cột Thành tiền"

    # Kiểm tra clean_num xử lý '1,45tr' trong biz_129
    assert clean_num("1,45tr") == 1450000.0
    assert clean_num("1,156tr") == 1156000.0


def test_hypothesis_c_inventory_table_preserved_and_enriched():
    """(c) Không loại bảng chỉ vì tên chứa 'kho' và bổ sung Ngày snapshot + Quy cách cho BaoCaoTonKho."""
    bd106 = clean_business(load_business(TRAIN_DATA_ROOT / "biz_106"))
    schema106 = profile_business_schema(bd106)
    pruned = prune_schema_by_intent(schema106, intent="aggregation", question="Số lượng bánh croissant hôm nay")
    assert "BaoCaoTonKho" in pruned

    tk106 = next(t.df for t in bd106.tables if "BaoCaoTonKho" in t.fixed_file_name)
    cols106_low = [str(c).lower() for c in tk106.columns]
    assert any("ngày" in c for c in cols106_low), "BaoCaoTonKho thiếu cột Ngày snapshot"
    assert any("quy cách" in c for c in cols106_low), "BaoCaoTonKho thiếu cột Quy cách từ DanhSachDonViTinh"


def test_no_retry_on_data_not_found_error():
    """Với lỗi DataNotFoundError (lỗi schema) thì KHÔNG chạy vòng tự sửa lỗi bằng LLM."""
    from datamate.llm_execution.sandbox import should_retry_self_correction

    assert should_retry_self_correction(
        exec_err="Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền",
        sanity_err=None,
        err_type="DataNotFoundError",
    ) is False
    assert should_retry_self_correction(
        exec_err="DataNotFoundError: Không tìm thấy cột ngày",
        sanity_err=None,
        err_type="RuntimeError",
    ) is False
    assert should_retry_self_correction(
        exec_err="KeyError: 'unknown_col'",
        sanity_err=None,
        err_type="KeyError",
    ) is True
