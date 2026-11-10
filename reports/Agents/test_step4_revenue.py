"""
Unit & regression tests cho Bước 4 — Hàm revenue() / count_orders() tất định theo Rulebook:
1. Doanh thu = tổng giá trị dòng hàng sau chiết khấu cấp dòng; không trừ voucher cấp đơn;
   không gồm VAT và phí giao hàng; loại CẢ ĐƠN nếu đơn bị hủy hoặc có bất kỳ mặt hàng nào bị trả.
2. Tránh cộng lặp các cột cấp đơn (Tổng bill, Khách trả, Tổng tiền cấp đơn) bị forward-fill lặp trên mỗi dòng sản phẩm.
3. Hồi quy trên dữ liệu thật tập train cho 4 case trong đề bài:
   - Q3 (q_e0bed6042dfe, biz_104): lệch 96,000 (6,501,500 vs Gold 6,405,500)
   - Q21 (q_260318057077, biz_121): lệch 0.7% (803,177,000 vs Gold 797,461,200)
   - Q10 (q_e390c3cb0b3b, biz_111): lệch 1.7x (18,252,000 vs Gold 10,792,500)
   - Q9 (q_4d7fc53fcc41, biz_111): lệch 4.1x (7,467,600 vs Gold 1,828,785)
4. Prompt hướng dẫn LLM gọi hàm revenue() / count_orders() thay vì tự chọn cột tiền.
"""

from pathlib import Path
import pandas as pd
import pytest

from tests.inspect_pipeline import load_business_data, execute_solution


DATA_ROOT = Path(__file__).resolve().parents[2] / "competition_data" / "train" / "data"


def test_deterministic_revenue_and_count_orders_rulebook_synthetic():
    """
    Kiểm tra hàm revenue() và count_orders() tất định:
    - Loại CẢ ĐƠN nếu đơn có bất kỳ dòng nào bị trả (dù chỉ trả 1 phần) hoặc bị hủy.
    - Không trừ voucher cấp đơn, không cộng VAT/phí ship, không cộng lặp cột cấp đơn bị forward-fill.
    """
    from datamate.llm_execution.sandbox import revenue, count_orders

    # ORD1: 2 dòng hợp lệ (100k + 50k = 150k), Tổng bill cấp đơn (kèm ship 20k, trừ voucher 10k) = 160k bị forward-fill
    # ORD2: 2 dòng, trong đó dòng 2 bị trả hàng -> phải loại CẢ ĐƠN ORD2 (không được cộng dòng 1 = 200k)
    # ORD3: 1 dòng bị hủy -> loại CẢ ĐƠN ORD3
    df_detail = pd.DataFrame({
        "Mã đơn hàng": ["ORD1", "ORD1", "ORD2", "ORD2", "ORD3"],
        "Ngày bán": ["2026-05-01", "2026-05-01", "2026-05-01", "2026-05-01", "2026-05-01"],
        "Tên hàng": ["SP A", "SP B", "SP A", "SP C", "SP B"],
        "Số lượng": ["1", "1", "2", "1", "1"],
        "Thành tiền": ["100000", "50000", "200000", "80000", "90000"],
        "Tổng bill": ["160000", "160000", "280000", "280000", "90000"],
        "Khách trả": ["160000", "160000", "280000", "280000", "0"],
        "Phí giao hàng": ["20000", "20000", "0", "0", "0"],
        "VAT": ["10000", "10000", "0", "0", "0"],
        "Voucher đơn": ["10000", "10000", "0", "0", "0"],
        "Trạng thái": ["Hoàn thành", "Hoàn thành", "Hoàn thành", "Trả hàng 1 phần", "Đã hủy"],
    })
    data = {"chi_tiet_don": df_detail}

    assert revenue(data, start_date="2026-05-01", end_date="2026-05-01") == 150000
    assert count_orders(data, start_date="2026-05-01", end_date="2026-05-01") == 1


def test_regression_q3_and_q21_returned_status_hoan_hang():
    """
    Hồi quy Q3 (q_e0bed6042dfe, biz_104, Gold=6,405,500) và Q21 (q_260318057077, biz_121, Gold=797,461,200):
    Đơn có trạng thái 'Đã hoàn hàng' phải bị loại trừ hoàn toàn khỏi doanh thu (cả khi gọi revenue() lẫn khi chạy code).
    """
    from datamate.llm_execution.sandbox import revenue

    # Q3: biz_104, ngày 2025-07-24 (hôm qua của 2025-07-25)
    data_104, con_104, _, bd_104, _, _ = load_business_data("biz_104", DATA_ROOT)
    assert revenue(data_104, start_date="2025-07-24", end_date="2025-07-24", as_of_date="2025-07-25") == 6405500

    # Kiểm tra cả khi chạy lại code của Q3 trong logs
    code_q3 = (
        "def solution(data):\n"
        "    df_sales = data['DonHang_ChiTiet'].copy()\n"
        "    df_sales['clean_date'] = clean_date(df_sales['Ngày đặt hàng'])\n"
        "    df_sales = df_sales[~df_sales['Trạng thái đơn hàng'].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|cancel', regex=True, na=False)]\n"
        "    df_sales = df_sales[df_sales['clean_date'].dt.date == pd.to_datetime('2025-07-24').date()]\n"
        "    return int(round(clean_num(df_sales['Tổng tiền']).sum()))\n"
    )
    val_q3, err_q3, _ = execute_solution(
        code_q3, DATA_ROOT / "biz_104", data_104, con_104, bd_104, use_sandbox=False, as_of_date="2025-07-25"
    )
    assert err_q3 is None
    assert val_q3 == 6405500

    # Q21: biz_121, quý 2/2026 (2026-04-01 -> 2026-06-30)
    data_121, con_121, _, bd_121, _, _ = load_business_data("biz_121", DATA_ROOT)
    assert revenue(data_121, start_date="2026-04-01", end_date="2026-06-30", as_of_date="2026-09-20") == 797461200


def test_regression_q10_and_q9_biz_111_line_revenue_and_no_forward_fill_payment():
    """
    Hồi quy Q10 (q_e390c3cb0b3b, biz_111, Gold=10,792,500) và Q9 (q_4d7fc53fcc41, biz_111, Gold=1,828,785):
    - chi_tiet_don không được nối nhầm cột cấp đơn 'Khách trả' lặp trên từng dòng sản phẩm.
    - Bảng don_hang phải có cột 'Thành tiền' tính từ tổng dòng hàng 'T.Tiền' (không gồm phí ship/VAT của 'Tổng bill').
    - Các bản ghi sau ngày as_of_date (2025-09-28) phải được lọc bỏ theo Điều 5 Rulebook.
    - Từ viết tắt/lỗi gõ Telex 'nowj' trong Q9 phải được giải mã thành 'nợ', và hàm debt() tính đúng 1,828,785.
    """
    from datamate.llm_execution.sandbox import revenue, debt
    from datamate.grounding_feasibility.entity_linker import explain_and_expand_abbreviations

    data_111, con_111, _, bd_111, _, _ = load_business_data("biz_111", DATA_ROOT)

    # 1. chi_tiet_don không chứa cột cấp đơn 'Khách trả' bị lặp theo dòng
    assert "Khách trả" not in data_111["chi_tiet_don"].columns

    # 2. Q10: doanh thu ngày 2025-09-28 (as_of_date = 2025-09-28) = 10,792,500
    assert revenue(data_111, start_date="2025-09-28", end_date="2025-09-28", as_of_date="2025-09-28") == 10792500

    # Chạy lại đúng code Q10 đã sinh trong log (với as_of_date="2025-09-28") phải ra đúng 10,792,500
    q10_code = Path("datamate_runs/train_eval/logs/q_e390c3cb0b3b.json")
    import json
    code_str = json.loads(q10_code.read_text(encoding="utf-8"))["code"]
    val_q10, err_q10, _ = execute_solution(
        code_str, DATA_ROOT / "biz_111", data_111, con_111, bd_111, use_sandbox=False, as_of_date="2025-09-28"
    )
    assert err_q10 is None
    assert int(round(val_q10)) == 10792500

    # 3. Q9: 'nowj' -> 'nợ' và debt() tính đến 2026-08-19 = 1,828,785
    norm_q9, expanded_q9 = explain_and_expand_abbreviations(
        "tính đến hết ngày 19/08/2026, khách hàng còn nowj cửa hàng tổng cộng bao nhiêu tiền"
    )
    assert "nợ" in norm_q9.lower()
    assert debt(data_111, end_date="2026-08-19", as_of_date="2026-08-19") == 1828785


def test_prompt_instructs_llm_to_use_revenue_and_count_orders():
    """Prompt sinh code phải hướng dẫn LLM gọi hàm revenue() / count_orders() thay vì tự chọn cột tiền."""
    from datamate.llm_execution.prompt import build_prompt

    messages = build_prompt(
        schema_str="Bảng don_hang: ['Ngày bán', 'Thành tiền', 'Trạng thái']",
        question="Doanh thu hôm nay là bao nhiêu?",
        as_of_date="2025-09-28",
    )
    full_prompt = messages if isinstance(messages, str) else "\n".join(m["content"] for m in messages)
    assert "revenue(" in full_prompt
    assert "count_orders(" in full_prompt
