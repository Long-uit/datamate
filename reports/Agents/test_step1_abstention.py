"""
Kiểm thử Bước 1 — Cổng abstention tất định (không dùng LLM):
1. Kết quả number = 0 hoặc rỗng trên câu hỏi doanh thu/số lượng/trung bình thì hạ C xuống dưới ngưỡng (có cờ cấu hình bật/tắt).
2. Kiểu câu hỏi là percent mà code không tính tỷ lệ thì abstain.
3. Kiểu trả về không khớp kiểu câu hỏi thì abstain.
4. Điều kiện lọc luôn rỗng (ví dụ day >= 27 & day <= 3) thì báo lỗi và hạ C xuống dưới ngưỡng.
"""

from __future__ import annotations

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import pytest

from src.datamate.output_abstention.abstention import (
    compute_confidence_score,
    apply_abstention_gate,
    evaluate_semantic_rule_compliance,
)
from src.datamate.output_abstention.normalizer import check_result_sanity


def test_step1_zero_on_revenue_qty_average_configurable():
    """
    Khi câu hỏi hỏi doanh thu / số lượng / trung bình (vd: AOV) mà kết quả trả về 0,
    điểm tin cậy C phải bị hạ xuống dưới ngưỡng tau* = 0.50 khi bật cờ penalize_zero_revenue_qty=True,
    và giữ trên ngưỡng khi tắt cờ penalize_zero_revenue_qty=False.
    """
    question = "Giá trị trung bình một đơn tuần trước là bao nhiêu?"
    code = """def solution(data):
    df = data['DonHang']
    return 0
"""
    sub_ans = {"type": "number", "answer": 0}

    # Khi bật cờ (mặc định True): C < 0.50 -> abstain
    c_on = compute_confidence_score(
        sub_ans=sub_ans,
        code_text=code,
        question=question,
        penalize_zero_revenue_qty=True,
    )
    assert c_on < 0.50
    final_ans, abstained = apply_abstention_gate(sub_ans, c_on, threshold=0.50)
    assert abstained is True
    assert final_ans["type"] == "abstain"

    # Khi tắt cờ (False): C >= 0.50 -> không bị phạt bởi quy tắc zero
    c_off = compute_confidence_score(
        sub_ans=sub_ans,
        code_text=code,
        question=question,
        penalize_zero_revenue_qty=False,
    )
    assert c_off >= 0.50


def test_step1_percent_without_ratio_computation_abstains():
    """
    Kiểu câu hỏi là percent (tăng hay giảm bao nhiêu %, tỉ trọng bao nhiêu %)
    mà code chỉ tính tổng (.sum()) không có phép chia tỷ lệ (/, pct_change, ratio) -> abstain.
    Tái hiện lỗi của q_f3d30bcd1487 và q_f95fc735e3bc.
    """
    question = "So số ly Sinh tố xoài (L) bán ra trong 30 ngày kể từ ngày 04/09/2025 với 30 ngày ngay trước ngày đó: tăng hay giảm bao nhiêu % nhỉ?"
    code = """def solution(data):
    df_ord = data['DonHang']
    total_sales = clean_num(df_ord['Thành tiền']).sum()
    return int(round(total_sales))
"""
    sub_ans = {"type": "percent", "answer": 0}
    sane, err = check_result_sanity(sub_ans, question=question, code_text=code)
    conf = compute_confidence_score(
        sub_ans=sub_ans,
        sanity_passed=sane,
        sanity_error=err,
        code_text=code,
        question=question,
    )
    assert conf < 0.50
    final_ans, abstained = apply_abstention_gate(sub_ans, conf, threshold=0.50)
    assert abstained is True
    assert final_ans["type"] == "abstain"


def test_step1_return_type_mismatch_abstains():
    """
    Kiểu trả về không khớp kiểu câu hỏi kỳ vọng (ví dụ hỏi khách hàng nào / mặt hàng nào -> string,
    nhưng trả về number; hoặc hỏi bao nhiêu tiền -> number, nhưng trả về string/list) -> abstain.
    """
    q_str = "Tháng 6/2025 khách hàng nào mua nhiều tiền nhất?"
    sub_num = {"type": "number", "answer": 1250000}
    code = "def solution(data):\n    return 1250000\n"
    sane, err = check_result_sanity(sub_num, question=q_str, code_text=code)
    conf = compute_confidence_score(
        sub_ans=sub_num,
        sanity_passed=sane,
        sanity_error=err,
        code_text=code,
        question=q_str,
    )
    assert conf < 0.50
    final_ans, abstained = apply_abstention_gate(sub_num, conf, threshold=0.50)
    assert abstained is True
    assert final_ans["type"] == "abstain"


def test_step1_always_empty_filter_condition_flagged_and_abstains():
    """
    Điều kiện lọc luôn rỗng trong code (ví dụ dt.day >= 27 & dt.day <= 3 trên cùng 1 tháng
    như ở q_9602e7257869, hoặc start_date > end_date) -> báo lỗi và hạ C xuống dưới ngưỡng.
    """
    question = "Giá trị trung bình một đơn tuần trước là bao nhiêu?"
    code = """def solution(data):
    df_sales = data['BanHang']
    mask = (df_sales['clean_date'].dt.year == 2026) & (df_sales['clean_date'].dt.month == 5) & (df_sales['clean_date'].dt.day >= 27) & (df_sales['clean_date'].dt.day <= 3)
    df_period = df_sales[mask]
    return 150000
"""
    sub_ans = {"type": "number", "answer": 150000}
    sem = evaluate_semantic_rule_compliance(code_text=code, question=question, sub_ans=sub_ans)
    assert sem["is_compliant"] is False
    assert any("rỗng" in v.lower() or "day" in v.lower() for v in sem["violations"])

    sane, err = check_result_sanity(sub_ans, question=question, code_text=code)
    assert sane is False
    conf = compute_confidence_score(
        sub_ans=sub_ans,
        sanity_passed=sane,
        sanity_error=err,
        code_text=code,
        question=question,
    )
    assert conf < 0.50
