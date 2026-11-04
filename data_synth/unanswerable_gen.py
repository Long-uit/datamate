"""
unanswerable_gen.py — Sinh các mẫu câu hỏi bất khả thi (Unanswerable) có chủ đích.

Mục tiêu huấn luyện:
Dạy mô hình LLM tuyệt đối KHÔNG đoán mò khi thông tin nằm ngoài phạm vi dữ liệu,
trả về đúng định dạng {"type": "unanswerable", "answer": null} để ăn trọn +1 điểm theo cơ chế phạt TrustSQL.
"""

from __future__ import annotations

import random
from typing import Any

# Danh sách các mặt hàng giả định không có trong tiệm tạp hóa / cafe thông thường
NON_EXISTENT_PRODUCTS = [
    "Vé máy bay đi Paris",
    "Tủ lạnh Samsung 4 cánh",
    "Xe máy Honda SH 150i",
    "Điện thoại iPhone 16 Pro Max",
    "Phở bò Kobe đặc biệt",
    "Căn hộ cao cấp Vinhomes",
]

# Danh sách thuộc tính vô lý không có trong CSDL bán lẻ
MISSING_ATTRIBUTES = [
    "chiều cao trung bình của khách hàng",
    "nhiệt độ phòng lúc đặt hàng",
    "tâm trạng của nhân viên thu ngân",
    "màu sắc chiếc xe của người giao hàng",
    "chỉ số BMI của người mua",
]


def generate_unanswerable_questions(
    business_id: str,
    as_of_date: str,
    date_range: tuple[str | None, str | None] = (None, None),
) -> list[dict[str, Any]]:
    """
    Sinh các cặp mẫu (question, target_answer, reason) thuộc nhóm Unanswerable.
    """
    samples: list[dict[str, Any]] = []

    # 1. Hỏi ngoài phạm vi thời gian (Date out of range)
    min_date, max_date = date_range
    far_future_year = 2030
    far_past_year = 2018

    q_future = f"Doanh thu của shop trong tháng 10 năm {far_future_year} là bao nhiêu?"
    samples.append({
        "business_id": business_id,
        "as_of_date": as_of_date,
        "question": q_future,
        "type": "unanswerable",
        "reason": f"Kỳ hỏi năm {far_future_year} nằm hoàn toàn ngoài phạm vi dữ liệu",
        "answer": None,
    })

    q_past = f"Tổng số đơn hàng đã bán vào năm {far_past_year}"
    samples.append({
        "business_id": business_id,
        "as_of_date": as_of_date,
        "question": q_past,
        "type": "unanswerable",
        "reason": f"Kỳ hỏi năm {far_past_year} nằm ngoài phạm vi hoạt động của cửa hàng",
        "answer": None,
    })

    # 2. Hỏi sản phẩm hoàn toàn không tồn tại trong danh mục
    fake_product = random.choice(NON_EXISTENT_PRODUCTS)
    q_product = f"Sản phẩm {fake_product} bán được bao nhiêu cái trong tuần này?"
    samples.append({
        "business_id": business_id,
        "as_of_date": as_of_date,
        "question": q_product,
        "type": "unanswerable",
        "reason": f"Mặt hàng '{fake_product}' không có trong danh mục sản phẩm của shop",
        "answer": None,
    })

    # 3. Hỏi thông tin/thuộc tính không có trong CSDL
    missing_attr = random.choice(MISSING_ATTRIBUTES)
    q_attr = f"Thống kê {missing_attr} khi mua hàng hôm nay"
    samples.append({
        "business_id": business_id,
        "as_of_date": as_of_date,
        "question": q_attr,
        "type": "unanswerable",
        "reason": f"Cơ sở dữ liệu không lưu trữ thông tin về {missing_attr}",
        "answer": None,
    })

    return samples
